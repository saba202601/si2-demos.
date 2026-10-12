"""Canonical Gaps for the NCCI Bureau Reporting Workbench (WCSTAT, WCPOLS, WCIND, WCMED).

* source element gap     - a source column no canonical attribute uses
* unsourced canonical    - a canonical attribute with no source column
* bureau field gap       - a WCIO spec field needing review with no canonical attribute behind it
* bureau code gap        - a source value with no WCIO pick-list code (NCCI owns these lists: map only)

Decisions update the workbench session the same way its mapping screens do, and every
decision is written to the workbench audit trail.
"""
from __future__ import annotations

import pandas as pd

from si2_common.gaps import Gap, draft_description, infer_type, rank, to_title

from . import canonical as cn
from . import catalog
from . import generate as gen

TABLE_OF_SOURCE = {src: t for t, srcs in cn.SOURCE_FOR.items() for src in srcs}
TYPE_FROM = {"CODE": "code", "DATE": "date", "DECIMAL": "money", "NUMBER": "int", "TEXT": "text"}


def _snake(name: str) -> str:
    return "_".join(w.lower() for w in to_title(name).split()) or "new_attribute"


def _canonical_cols(ss) -> list[tuple[str, str, list[str]]]:
    """(table.column, label, names) for every canonical attribute, including SME-added ones."""
    out = []
    for r in ss.smap.itertuples():
        typ, desc, aliases = cn.SCHEMA.get(r.canonical_table, {}).get(r.canonical_column, (r.type, r.description, []))
        out.append((f"{r.canonical_table}.{r.canonical_column}", f"{r.canonical_table}.{r.canonical_column} · {desc}",
                    [r.canonical_column.replace("_", " "), desc, *aliases]))
    for t, cols in gen.DERIVED_COLS.items():
        for c, (typ, names) in cols.items():
            out.append((f"{t}.{c}", f"{t}.{c} · SI² derived", [c.replace("_", " "), *names]))
    return out


NO_SOURCE = "(none yet: source it later)"


def _table_for(spec: str, record: str) -> str:
    """Grain of the WCIO record: exposure / loss / state / payment / bill line / policy."""
    rec = str(record).upper()
    if spec == "WCMED":
        return "medical_bill_line"
    if "EXPOSURE" in rec:
        return "exposure"
    if "STATE" in rec:
        return "policy_state"
    if spec == "WCIND" and "PAYMENT" in rec:
        return "indemnity_payment"
    if spec in ("WCSTAT", "WCIND") and ("LOSS" in rec or spec == "WCIND"):
        return "claim"
    return "policy"


def _source_cols(ss, table: str):
    """Only the source table that feeds a canonical table can feed its attributes (same grain / row count)."""
    return [(f"{t}.{c}", f"{t}.{c}", [c]) for t in cn.SOURCE_FOR.get(table, []) if t in ss.src for c in ss.src[t].columns]


def _best_source(ss, table: str, name: str) -> str:
    cols = _source_cols(ss, table)
    best = rank(name, cols, top=1, floor=0.34)
    return best[0][0] if best else NO_SOURCE


def scan(ss) -> list[Gap]:
    gaps: list[Gap] = []
    ignored = getattr(ss, "gap_ignored", set())
    canon_cols = _canonical_cols(ss)
    used = {(r.source_table, r.source_column) for r in ss.smap.itertuples() if r.source_column}

    # 1. source columns no canonical attribute uses
    for t, df in ss.src.items():
        for c in df.columns:
            if (t, c) in used or f"src:{t}.{c}" in ignored:
                continue
            vals = [str(v) for v in df[c].dropna().astype(str) if str(v).strip()]
            dtype = infer_type(vals[:200])
            codes = sorted(set(vals))[:12] if dtype == "CODE" else []
            gaps.append(Gap(gap_id="", kind="ELEMENT", side="SOURCE", system="Source system", ref=f"{t}.{c}", name=c,
                            context=TABLE_OF_SOURCE.get(t, ""), data_type=dtype, samples=vals[:5],
                            values={v: "" for v in codes}, occurrences=len(vals), risk="Medium",
                            candidates=rank(c, canon_cols),
                            proposal={"table": TABLE_OF_SOURCE.get(t, "policy"), "column": _snake(c),
                                      "type": TYPE_FROM.get(dtype, "text"),
                                      "description": draft_description(c, dtype, vals[:3], f"{t}.{c}")}))

    # 2. canonical attributes nothing feeds
    for r in ss.smap.itertuples():
        if r.source_column or f"can:{r.canonical_table}.{r.canonical_column}" in ignored:
            continue
        src_cols = _source_cols(ss, r.canonical_table)
        gaps.append(Gap(gap_id="", kind="UNSOURCED", side="CANONICAL", system="SI² canonical",
                        ref=f"{r.canonical_table}.{r.canonical_column}", name=r.canonical_column, context=r.canonical_table,
                        meaning=r.description, risk="High",
                        candidates=rank(f"{r.canonical_column} {r.description}", src_cols), actions=("map", "skip")))

    # 3. WCIO fields that need a canonical attribute
    src_options = [f"{t}.{c}" for t, df in ss.src.items() for c in df.columns]
    for spec, fm in ss.fmaps.items():
        for r in fm[(fm.status == "Needs SME review") & (fm.canonical == "")].itertuples():
            gaps.append(Gap(gap_id="", kind="DEST_ELEMENT", side="DESTINATION", system=spec,
                            ref=f"{spec} · {r.record_name} · {r.field_name} ({r.start}-{r.end})", name=r.field_name,
                            context=f"{spec}|{r.Index}", risk="High", candidates=rank(r.field_name, canon_cols),
                            proposal={"table": (tbl := _table_for(spec, r.record_name)),
                                      "column": _snake(r.field_name),
                                      "type": "code" if r.pick_list else ("money" if "AMOUNT" in r.field_name else
                                                                         "date" if "DATE" in r.field_name else "text"),
                                      "source": _best_source(ss, tbl, r.field_name),
                                      "description": f"{to_title(r.field_name)} as reported in {spec}. (Drafted by SI² - edit if needed.)"}))

    # 4. source values with no WCIO code
    cat = catalog.load().set_index("field_id")
    for spec, vm in ss.vmaps.items():
        for r in vm[(vm.status == "Needs SME review") & (vm.bureau_code == "")].itertuples():
            codes = cat.loc[r.field_id].codes
            gaps.append(Gap(gap_id="", kind="CODE", side="DESTINATION", system=spec,
                            ref=f"{spec} · {r.field_name} = '{r.source_value}'", name=r.source_value,
                            context=f"{spec}|{r.Index}", meaning=f"{r.canonical} value", risk="High",
                            candidates=rank(r.source_value, [(c["code"], f"{c['code']} · {c['description']}", [c["description"]])
                                                             for c in codes if not c.get("reserved")]),
                            values={c["code"]: c["description"] for c in codes[:12]}, actions=("map",)))
    for i, g in enumerate(gaps, 1):
        g.gap_id = f"N{i:03d}"
    return gaps


class Handler:
    def __init__(self, ss, actor: str, rebuild, log):
        self.ss, self.actor, self._rebuild, self._log = ss, actor, rebuild, log
        if not hasattr(ss, "gap_ignored"):
            ss.gap_ignored = set()

    def _refresh_values(self, spec: str):
        ss = self.ss
        ss.vmaps[spec] = gen.auto_value_map(ss.canon, ss.fmaps[spec]).pipe(
            lambda new: pd.concat([ss.vmaps[spec][ss.vmaps[spec].status == "SME approved"], new]).drop_duplicates(
                ["field_id", "source_value"], keep="first"))

    def _new_attribute(self, table, column, typ, desc, src_table="", src_col=""):
        ss = self.ss
        if ((ss.smap.canonical_table == table) & (ss.smap.canonical_column == column)).any():
            return False
        row = {"canonical_table": table, "canonical_column": column, "type": typ, "description": desc,
               "source_table": src_table, "source_column": src_col, "confidence": 1.0,
               "band": "High" if src_col else "Unmapped", "status": "SME approved" if src_col else "Unmapped"}
        ss.smap = pd.concat([ss.smap, pd.DataFrame([row])], ignore_index=True)
        return True

    # -- protocol
    def map_options(self, g: Gap):
        ss = self.ss
        if g.kind in ("ELEMENT", "DEST_ELEMENT"):
            allx = [(k, l) for k, l, _ in _canonical_cols(ss)]
        elif g.kind == "UNSOURCED":
            allx = [(k, l) for k, l, _ in _source_cols(ss, g.context)]
        else:
            spec, idx = g.context.split("|")
            fid = ss.vmaps[spec].at[int(idx), "field_id"]
            allx = [(c["code"], f"{c['code']} · {c['description']}") for c in catalog.load().set_index("field_id").loc[fid].codes]
        first = [(k, f"{l}  ({int(s * 100)}% match)") for k, l, s in g.candidates]
        keys = {k for k, _ in first}
        return first + [(k, l) for k, l in allx if k not in keys]

    def proposal_fields(self, g: Gap):
        tables = list(cn.SCHEMA)
        base = [("table", "Canonical table", tables), ("column", "New canonical attribute", None),
                ("type", "Type", ["text", "code", "date", "money", "int", "factor", "rate"]),
                ("description", "Business description", None)]
        if g.kind == "DEST_ELEMENT":
            opts = [NO_SOURCE] + [f"{t}.{c}" for t in cn.SOURCE_FOR.get(g.proposal.get("table"), [])
                                  if t in self.ss.src for c in self.ss.src[t].columns]
            cur = g.proposal.get("source")
            return base[:3] + [("source", "Fed by source column", ([cur] if cur in opts else []) + [o for o in opts if o != cur])] + base[3:]
        return base

    def map_existing(self, g: Gap, key: str) -> str:
        ss = self.ss
        if g.kind == "ELEMENT":
            t, c = key.split(".", 1)
            src_t, src_c = g.ref.split(".", 1)
            hit = (ss.smap.canonical_table == t) & (ss.smap.canonical_column == c)
            if not hit.any():
                raise ValueError(f"{key} is SI²-derived; it is calculated, not fed from a source column.")
            ss.smap.loc[hit, ["source_table", "source_column", "confidence", "band", "status"]] = [src_t, src_c, 1.0, "High", "SME approved"]
            self._rebuild()
            self._log(self.actor, "Source mapping approved (Canonical Gaps)", f"{g.ref} → {key}")
            return f"{g.ref} now feeds {key}."
        if g.kind == "UNSOURCED":
            src_t, src_c = key.split(".", 1)
            if src_t not in cn.SOURCE_FOR.get(g.context, []):
                raise ValueError(f"{g.context} is fed by {', '.join(cn.SOURCE_FOR.get(g.context, []))}; pick a column from that table.")
            hit = (ss.smap.canonical_table == g.context) & (ss.smap.canonical_column == g.name)
            ss.smap.loc[hit, ["source_table", "source_column", "confidence", "band", "status"]] = [src_t, src_c, 1.0, "High", "SME approved"]
            self._rebuild()
            self._log(self.actor, "Source mapping approved (Canonical Gaps)", f"{key} → {g.ref}")
            return f"{key} now feeds {g.ref}."
        spec, idx = g.context.split("|")
        if g.kind == "DEST_ELEMENT":
            fm = ss.fmaps[spec]
            fm.at[int(idx), "canonical"] = key
            fm.at[int(idx), "source"] = "SI² derived" if key.split(".")[0] in gen.DERIVED_COLS else "Canonical"
            fm.at[int(idx), "status"] = "SME approved"
            self._refresh_values(spec)
            self._log(self.actor, f"{spec} field mapping approved (Canonical Gaps)", f"{g.name} ← {key}")
            return f"{spec} {g.name} now reports {key}."
        vm = ss.vmaps[spec]
        fid = vm.at[int(idx), "field_id"]
        vm.at[int(idx), "bureau_code"] = key
        vm.at[int(idx), "code_description"] = catalog.pick_list(catalog.load().set_index("field_id").loc[fid]).get(key, "")
        vm.at[int(idx), "status"] = "SME approved"
        self._log(self.actor, f"{spec} value mapping approved (Canonical Gaps)", f"{g.name} → {key}")
        return f"'{g.name}' reports as NCCI code {key} in {spec}."

    def add_new(self, g: Gap, p: dict) -> str:
        ss = self.ss
        col = _snake(p["column"])
        if g.kind == "ELEMENT":
            src_t, src_c = g.ref.split(".", 1)
            if src_t not in cn.SOURCE_FOR.get(p["table"], []):
                raise ValueError(f"{g.ref} comes from {src_t}; choose the canonical table fed by it ({TABLE_OF_SOURCE.get(src_t, '?')}).")
            if not self._new_attribute(p["table"], col, p["type"], p["description"], src_t, src_c):
                raise ValueError(f"{p['table']}.{col} already exists. Use Map to existing instead.")
            self._rebuild()
            self._log(self.actor, "Canonical attribute added (Canonical Gaps)", f"{p['table']}.{col} ← {g.ref}")
            return f"New canonical attribute {p['table']}.{col} added, fed by {g.ref}. It can now be mapped to any WCIO field."
        if g.kind == "DEST_ELEMENT":
            src_t, src_c = ("", "") if p.get("source", NO_SOURCE) == NO_SOURCE else p["source"].split(".", 1)
            if src_t and src_t not in cn.SOURCE_FOR.get(p["table"], []):
                raise ValueError(f"{p['table']} is fed by {', '.join(cn.SOURCE_FOR.get(p['table'], []))}; pick a source column from that "
                        "table (or choose another canonical table).")
            if not self._new_attribute(p["table"], col, p["type"], p["description"], src_t, src_c):
                raise ValueError(f"{p['table']}.{col} already exists. Use Map to existing instead.")
            self._rebuild()
            spec, idx = g.context.split("|")
            fm = ss.fmaps[spec]
            fm.at[int(idx), "canonical"], fm.at[int(idx), "source"], fm.at[int(idx), "status"] = f"{p['table']}.{col}", "Canonical", "SME approved"
            self._refresh_values(spec)
            self._log(self.actor, "Canonical attribute added (Canonical Gaps)", f"{p['table']}.{col} → {spec} {g.name}")
            fed = f"from {src_t}.{src_c}" if src_c else "no source yet: it is listed as a canonical gap until sourced"
            return f"New canonical attribute {p['table']}.{col} ({fed}) now reports {spec} {g.name}."
        return "NCCI owns this code list: map the value to an existing NCCI code."

    def not_needed(self, g: Gap, reason: str) -> str:
        ss = self.ss
        if g.kind == "ELEMENT":
            ss.gap_ignored.add(f"src:{g.ref}")
        elif g.kind == "UNSOURCED":
            ss.gap_ignored.add(f"can:{g.ref}")
        elif g.kind == "DEST_ELEMENT":
            spec, idx = g.context.split("|")
            ss.fmaps[spec].at[int(idx), "status"] = "Blank/zero fill"
            self._log(self.actor, f"{spec} field set to blank/zero fill (Canonical Gaps)", f"{g.name}: {reason}")
            return f"{spec} {g.name} will be reported blank / zero-filled ({reason})."
        self._log(self.actor, "Marked not needed (Canonical Gaps)", f"{g.ref}: {reason}")
        return f"{g.ref} marked not needed ({reason})."
