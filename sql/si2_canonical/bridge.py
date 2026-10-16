"""SI² Data Bridge: any source to any destination through the canonical model in SI2Canonical.

    source row --(source field aliases, value aliases)--> canonical record --(destination aliases / bureau codes)--> destination

Every system is mapped once, to the canonical model, with aliases tagged with the system (approved by two people);
the bridge reads those mappings from SI2Canonical (SqlDictionary) or, without SQL Server, from the system definitions
(MemoryDictionary). Nothing is guessed: an unmapped field, an unknown value or a missing required element is reported,
the record is held, and every value that reaches a destination carries its lineage.
"""
from __future__ import annotations

import csv
import datetime as dt
import io
from collections import defaultdict
from dataclasses import dataclass, field

import bridge_systems as BS

REQUIRED = ["POLICY_NUMBER", "LINE_OF_BUSINESS", "STATE", "POLICY_EFFECTIVE_DATE", "TRANSACTION_TYPE", "WRITTEN_PREMIUM"]


def _key(v) -> str:
    return str(v).strip().upper()


# ------------------------------------------------------------------------------------------ dictionaries
class Dictionary:
    """What SI2Canonical knows: elements, the fields and values of each system, and the bureau codes."""
    kind = "memory"

    def __init__(self):
        self.elements = {}                         # code -> (name, type, pick list)
        self.field_alias = defaultdict(dict)       # system -> field name -> element
        self.value_in = defaultdict(dict)          # (system, pick list) -> SYSTEM VALUE (upper) -> option
        self.value_out = defaultdict(dict)         # (system, pick list) -> option -> system value
        self.options = defaultdict(set)            # pick list -> option codes
        self.bureau_codes = defaultdict(dict)      # (bureau, pick list) -> option -> code

    def element(self, code):
        return self.elements.get(code)

    def fields(self, system: str) -> dict:
        return self.field_alias.get(system, {})

    def to_canonical(self, system, picklist, value):
        """(option, how) or (None, why)."""
        m = self.value_in.get((system, picklist))
        if m:
            opt = m.get(_key(value))
            return (opt, f"{system} value '{value}' = {picklist} {opt}") if opt else (None, f"'{value}' is not a known {system} value of {picklist}")
        if value in self.options.get(picklist, ()):
            return value, f"same code in {picklist}"
        return None, f"'{value}' is not an option of {picklist}"

    def from_canonical(self, system, value_source, picklist, option):
        if value_source.startswith("BUREAU:"):
            b = value_source.split(":", 1)[1]
            code = self.bureau_codes.get((b, picklist), {}).get(option)
            return (code, f"{b} code of {picklist} {option}") if code else (None, f"no {b} code for {picklist} {option}")
        m = self.value_out.get((system, picklist))
        if m:
            v = m.get(option)
            return (v, f"{picklist} {option} = {system} '{v}'") if v else (None, f"{system} has no value for {picklist} {option}")
        return option, f"same code in {system}"


class MemoryDictionary(Dictionary):
    """The system definitions as if their mappings were approved (no SQL Server needed)."""

    def __init__(self, systems=None):
        super().__init__()
        self.elements = dict(BS.ELEMENTS)
        for pl, opts in BS.OPTIONS.items():
            self.options[pl] |= opts
        for pl, codes in BS.ISO_CODES.items():
            self.bureau_codes[("ISO", pl)] = dict(codes)
        for s in (systems or BS.SYSTEMS.values()):
            for f in s.fields:
                if not f.element:
                    continue
                self.field_alias[s.code][f.name] = f.element
                pl = self.elements[f.element][2]
                for v, opt in f.values.items():
                    self.value_in[(s.code, pl)][_key(v)] = opt
                    self.value_out[(s.code, pl)].setdefault(opt, v)


class SqlDictionary(Dictionary):
    """The approved mappings in SI2Canonical (aliases tagged with each system, pick lists, ISO bureau codes)."""
    kind = "sql"

    def __init__(self, con, systems=None):
        super().__init__()
        codes = [s.code for s in (systems or BS.SYSTEMS.values())]
        marks = ",".join("?" * len(codes))
        cur = con.cursor()
        cur.execute("SELECT e.ElementCode, e.Name, e.DataType, p.PickListCode FROM canon.DataElement e "
                    "LEFT JOIN canon.PickList p ON p.PickListId = e.PickListId WHERE e.ScopeId = 1 AND e.Status <> 'EXPIRED'")
        self.elements = {r[0]: (r[1], r[2], r[3]) for r in cur.fetchall()}
        cur.execute("SELECT s.SourceSystem, s.SynonymText, e.ElementCode FROM canon.Synonym s JOIN canon.DataElement e "
                    "ON s.ObjectType = 'ELEMENT' AND e.ElementId = s.ObjectId WHERE s.Status = 'ACTIVE' AND s.SourceSystem IN (" + marks + ")", tuple(codes))
        for sysc, text, el in cur.fetchall():
            self.field_alias[sysc][text] = el
        cur.execute("SELECT s.SourceSystem, p.PickListCode, o.OptionCode, s.SynonymText FROM canon.Synonym s "
                    "JOIN canon.PickListOption o ON s.ObjectType = 'OPTION' AND o.OptionId = s.ObjectId JOIN canon.PickList p ON p.PickListId = o.PickListId "
                    "WHERE s.Status = 'ACTIVE' AND s.SourceSystem IN (" + marks + ")", tuple(codes))
        for sysc, pl, opt, text in cur.fetchall():
            self.value_in[(sysc, pl)][_key(text)] = opt
            self.value_out[(sysc, pl)].setdefault(opt, text)
        cur.execute("SELECT p.PickListCode, o.OptionCode FROM canon.PickListOption o JOIN canon.PickList p ON p.PickListId = o.PickListId "
                    "WHERE p.ScopeId = 1 AND o.Status <> 'EXPIRED'")
        for pl, opt in cur.fetchall():
            self.options[pl].add(opt)
        cur.execute("SELECT b.Bureau, p.PickListCode, o.OptionCode, b.BureauCode, b.LobScope FROM canon.BureauCodeMap b "
                    "JOIN canon.PickListOption o ON o.OptionId = b.OptionId JOIN canon.PickList p ON p.PickListId = o.PickListId "
                    "WHERE b.Status = 'ACTIVE' ORDER BY CASE WHEN b.LobScope = '*' THEN 0 ELSE 1 END")
        for bureau, pl, opt, code, _lob in cur.fetchall():
            self.bureau_codes[(bureau, pl)].setdefault(opt, code)
        self.kind = "sql"


# ------------------------------------------------------------------------------------------ formats
FORMAT_NAME = {"date:%Y%m%d": "date YYYYMMDD", "date:%Y-%m-%d": "date YYYY-MM-DD", "date:%Y%m": "YYYYMM", "implied2": "two implied decimals",
               "name_last_first": "LAST, FIRST", "name_natural": "First Last", "amount2": "amount with cents", "dollars": "whole dollars",
               "thousands": "thousands", "pad2": "two digits", "upper": "upper case", "int": "number", "amount": "amount"}


def fmt_name(fmt: str) -> str:
    return FORMAT_NAME.get(fmt, fmt)


def parse(raw, fmt):
    """System value -> canonical value. Raises ValueError for a value the format cannot read."""
    s = "" if raw is None else str(raw).strip()
    if s == "":
        return None
    if fmt.startswith("date:"):
        return dt.datetime.strptime(s, fmt[5:]).date()
    if fmt == "upper":
        return s.upper()
    if fmt == "int":
        return int(s)
    if fmt in ("amount", "amount2"):
        return float(s.replace(",", "").replace("$", ""))
    if fmt == "implied2":
        return int(s) / 100
    if fmt == "pad2":
        return f"{int(s):02d}"
    if fmt == "name_last_first":
        last, _, first = s.partition(",")
        return " ".join(w.capitalize() for w in f"{first} {last}".split()) if first.strip() else s.title()
    return s


def emit(v, fmt, width: int = 0) -> str:
    """Canonical value -> how the destination writes it (fixed width when width > 0)."""
    if v is None:
        out, numeric = "", False
    elif fmt.startswith("date:"):
        out, numeric = v.strftime(fmt[5:]), False
    elif fmt == "int":
        out, numeric = str(int(v)), True
    elif fmt == "amount":
        out, numeric = (f"{v:.0f}" if float(v).is_integer() else f"{v:.2f}"), True
    elif fmt == "amount2":
        out, numeric = f"{v:.2f}", True
    elif fmt == "dollars":
        out, numeric = str(round(v)), True
    elif fmt == "thousands":
        out, numeric = str(round(v / 1000)), True
    else:
        out, numeric = str(v), False
    if not width:
        return out
    if numeric and out.startswith("-"):
        return "-" + out[1:].rjust(width - 1, "0")
    return out.rjust(width, "0") if numeric else out.ljust(width)[:width]


# ------------------------------------------------------------------------------------------ the run
@dataclass
class Result:
    source: str
    destinations: list
    canonical: list = field(default_factory=list)         # one dict per record: element -> value
    outputs: dict = field(default_factory=dict)           # destination -> list of dicts (CSV) or str lines (FIXED)
    lineage: list = field(default_factory=list)
    issues: list = field(default_factory=list)
    held: set = field(default_factory=set)
    unmapped_fields: list = field(default_factory=list)

    def stats(self) -> dict:
        return {"records": len(self.canonical), "passed": len(self.canonical) - len(self.held), "held": len(self.held),
                **{f"to {d}": len(self.outputs.get(d, [])) for d in self.destinations}, "lineage rows": len(self.lineage),
                "issues": len(self.issues)}


def run(rows: list[dict], source: BS.System, destinations: list, d: Dictionary) -> Result:
    res = Result(source.code, [x.code for x in destinations])
    smap = d.fields(source.code)
    res.unmapped_fields = [f.name for f in source.fields if f.name not in smap]
    for name in res.unmapped_fields:
        res.issues.append({"Record": "*", "Severity": "INFO", "System": source.code, "Field": name, "Element": "", "Value": "",
                           "Problem": "Field has no canonical element yet: not carried; an SME decides what it is"})
    for dsys in destinations:
        res.outputs[dsys.code] = []
    for i, row in enumerate(rows, 1):
        rec, origin = {}, {}
        key = str(row.get("POL_NO") or f"row {i}")

        def issue(sev, fieldname, el, value, problem, system=source.code):
            res.issues.append({"Record": key, "Severity": sev, "System": system, "Field": fieldname, "Element": el, "Value": value, "Problem": problem})
            if sev == "ERROR":
                res.held.add(key)

        for f in source.fields:
            el = smap.get(f.name)
            if not el:
                continue
            raw = row.get(f.name, "")
            meta = d.element(el) or ("", "TEXT", None)
            try:
                v = parse(raw, f.fmt)
            except (ValueError, TypeError):
                issue("ERROR", f.name, el, raw, f"Cannot read '{raw}' as {fmt_name(f.fmt)}")
                continue
            how = f"read as {fmt_name(f.fmt)}" if f.fmt not in ("text", "code") else "as is"
            if v is not None and meta[1] == "CODE" and meta[2]:
                v, how = d.to_canonical(source.code, meta[2], v)
                if v is None:
                    issue("ERROR", f.name, el, raw, how)
                    continue
            rec[el] = v
            origin[el] = (f.name, raw, how)
        for el in REQUIRED:
            if rec.get(el) in (None, "") and not any(x["Record"] == key and x["Element"] == el for x in res.issues):
                f = next((x.name for x in source.fields if smap.get(x.name) == el), "")
                issue("ERROR", f, el, row.get(f, ""), "Required for every destination and missing")
        rec_out = {"Record": key, **rec}
        res.canonical.append(rec_out)
        if key in res.held:
            continue
        staged = {}
        for dsys in destinations:
            dmap = d.fields(dsys.code)
            out, lin, ok = {}, [], True
            for f in dsys.fields:
                el = dmap.get(f.name)
                if not el:
                    issue("WARN", f.name, "", "", "Destination field has no canonical element mapped", dsys.code)
                    out[f.name] = emit(None, f.fmt, f.width)
                    continue
                v = rec.get(el)
                meta = d.element(el) or ("", "TEXT", None)
                how = ""
                if v is not None and meta[1] == "CODE" and meta[2]:
                    v, how = d.from_canonical(dsys.code, dsys.value_source, meta[2], v)
                    if v is None:
                        issue("ERROR", f.name, el, rec.get(el), how, dsys.code)
                        ok = False
                        continue
                text = emit(v, f.fmt, f.width)
                if f.width and len(text.rstrip()) > f.width:
                    issue("ERROR", f.name, el, text, f"Longer than {f.width} characters", dsys.code)
                    ok = False
                out[f.name] = text
                src = origin.get(el, ("", "", ""))
                lin.append({"Record": key, "Source": source.code, "Source field": src[0], "Source value": src[1], "Element": el,
                            "Canonical value": _show(rec.get(el)), "Destination": dsys.code, "Destination field": f.name,
                            "Destination value": text.strip() if f.width else text, "Source to canonical": src[2],
                            "Canonical to destination": how or (f"written as {fmt_name(f.fmt)}" if f.fmt not in ("text", "code") else "as is")})
            if ok:
                staged[dsys.code] = (out, lin)
        if key in res.held:
            continue
        for code, (out, lin) in staged.items():
            sysdef = BS.SYSTEMS.get(code) or next(x for x in destinations if x.code == code)
            res.outputs[code].append("".join(out[f.name] for f in sysdef.fields) if sysdef.kind == "FIXED" else out)
            res.lineage += lin
    return res


def _plain(v):
    if isinstance(v, dt.date):
        return v.isoformat()
    if isinstance(v, float):
        return f"{v:.2f}"
    return "" if v is None else str(v)


def _show(v):
    if isinstance(v, dt.date):
        return v.isoformat()
    if isinstance(v, float):
        return f"{v:,.2f}"
    return "" if v is None else str(v)


# ------------------------------------------------------------------------------------------ files and views
def to_csv(rows: list[dict]) -> str:
    if not rows:
        return ""
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(rows[0].keys()), lineterminator="\n")
    w.writeheader()
    for r in rows:
        w.writerow({k: _plain(v) for k, v in r.items()})
    return buf.getvalue()


def output_text(res: Result, code: str) -> str:
    rows = res.outputs.get(code, [])
    if rows and isinstance(rows[0], str):
        return "\n".join(rows) + "\n"
    return to_csv(rows)


def canonical_rows(res: Result) -> list[dict]:
    cols = ["Record"] + list(BS.ELEMENTS)
    return [{c: r.get(c) for c in cols} for r in res.canonical]


def mapping_matrix(d: Dictionary, systems=None) -> list[dict]:
    """Each canonical element and the field that holds it in every system."""
    systems = systems or list(BS.SYSTEMS.values())
    rev = {s.code: {el: f for f, el in d.fields(s.code).items()} for s in systems}
    els = [e for e in BS.ELEMENTS if any(e in rev[s.code] for s in systems)]
    return [{"Element": e, "Name": (d.element(e) or (e,))[0], **{s.code: rev[s.code].get(e, "—") for s in systems}} for e in els]


def value_crosswalk(d: Dictionary, picklist: str, systems=None) -> list[dict]:
    """Each option of a pick list and how every system writes it."""
    systems = systems or list(BS.SYSTEMS.values())
    rows = []
    for opt in sorted(d.options.get(picklist, ())):
        row = {"Canonical option": opt}
        for s in systems:
            if s.value_source.startswith("BUREAU:"):
                v, _ = d.from_canonical(s.code, s.value_source, picklist, opt)
            elif s.role == "SOURCE":
                vals = [k for k, o in d.value_in.get((s.code, picklist), {}).items() if o == opt]
                v = ", ".join(vals) if vals else (opt if not d.value_in.get((s.code, picklist)) else None)
            else:
                v, _ = d.from_canonical(s.code, s.value_source, picklist, opt)
            row[s.code] = v or "—"
        if any(row[s.code] != "—" for s in systems):
            rows.append(row)
    return rows
