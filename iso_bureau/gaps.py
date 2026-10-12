"""Canonical Gaps for ISO bureau reporting.

Finds what the sources and the ISO layouts use that the canonical model lacks, and
applies the SME's decision as new effective-dated rows (never updates or deletes):

* source element gaps  - a source attribute with no source mapping
* code gaps            - a source value of a mapped pick-list element with no option or alias
* destination element  - a layout field whose canonical element does not exist (e.g. imported layout)
* destination code     - a pick-list option used by a reported field with no ISO code
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import date

from si2_common.gaps import Gap, draft_description, infer_type, rank, to_code, to_title

from . import db
from .engine import in_scope

NOT_REPORTED = "NOT_REPORTED"
LIVE = "status IN ('APPROVED','PENDING')"
HIGH_RISK_TYPES = {"CODE", "DATE", "AMOUNT", "DECIMAL", "NUMBER"}


def _elements(con):
    els = db.rows(con, f"SELECT element_code, element_name, picklist_code, data_type FROM canonical_element WHERE {LIVE}")
    aliases = defaultdict(list)
    for a in db.rows(con, f"SELECT element_code, alias_name FROM element_alias WHERE {LIVE}"):
        aliases[a["element_code"]].append(a["alias_name"])
    for m in db.rows(con, f"SELECT element_code, source_attribute FROM source_mapping WHERE {LIVE}"):
        aliases[m["element_code"]].append(m["source_attribute"])
    seen, out = set(), []
    for e in els:
        if e["element_code"] in seen or e["element_code"] == NOT_REPORTED:
            continue
        seen.add(e["element_code"])
        out.append(e | {"aliases": aliases[e["element_code"]]})
    return out


def _reported_elements(con) -> dict[str, set]:
    """element -> LOBs whose live layouts report it."""
    out = defaultdict(set)
    for r in db.rows(con, f"""SELECT f.element_code, v.lob_code FROM layout_field f JOIN layout_version v ON v.layout_id=f.layout_id
                              WHERE f.{LIVE.replace('status', 'status')} AND v.status IN ('APPROVED','PENDING')"""):
        out[r["element_code"]].add(r["lob_code"])
    return out


def scan(con) -> list[Gap]:
    gaps: list[Gap] = []
    elements = _elements(con)
    el_by_code = {e["element_code"]: e for e in elements}
    cand_elements = [(e["element_code"], f"{e['element_code']} · {e['element_name']}", [e["element_name"], *e["aliases"]])
                     for e in elements]
    maps = {(m["source_system"], m["source_attribute"]): m["element_code"]
            for m in db.rows(con, f"SELECT source_system, source_attribute, element_code FROM source_mapping WHERE {LIVE}")}
    reported = _reported_elements(con)

    # ---- profile current source transactions
    attr_vals: dict = defaultdict(Counter)
    attr_lobs: dict = defaultdict(set)
    attr_entity: dict = {}
    for t in db.rows(con, """SELECT t.source_system, t.lob_code, t.record_type, t.payload_json FROM source_transaction t
                             WHERE NOT EXISTS (SELECT 1 FROM source_transaction c WHERE c.corrects_txn_id=t.txn_id)"""):
        for k, v in json.loads(t["payload_json"]).items():
            key = (t["source_system"], k)
            attr_vals[key][str(v)] += 1
            attr_lobs[key].add(t["lob_code"])
            attr_entity.setdefault(key, "Policy extract" if t["record_type"] == "PREMIUM" else "Claim extract")

    # ---- 1. source element gaps
    for (system, attr), cnt in sorted(attr_vals.items()):
        if (system, attr) in maps:
            continue
        samples = [v for v, _ in cnt.most_common(6) if v]
        dtype = infer_type([v for v, n in cnt.items() for _ in range(n)])
        values = {v: f"{n}×" for v, n in cnt.most_common(12)} if dtype == "CODE" else {}
        code = to_code(attr)
        prop = {"code": code, "name": to_title(attr), "data_type": dtype,
                "description": draft_description(attr, dtype, samples, f"{system}.{attr}",
                                                 {v: v for v in values}),
                "picklist": (code if dtype == "CODE" and not set(values) <= {"Y", "N"} else ("YES_NO" if dtype == "CODE" else "")),
                "lob_scope": ",".join(sorted(attr_lobs[(system, attr)]))}
        gaps.append(Gap(gap_id="", kind="ELEMENT", side="SOURCE", system=system, ref=f"{system}.{attr}", name=attr,
                        context=attr_entity[(system, attr)], data_type=dtype, samples=samples, values=values,
                        occurrences=sum(cnt.values()), risk="Medium" if dtype in ("TEXT",) else "High",
                        candidates=rank(attr, cand_elements), proposal=prop))

    # ---- 2. code gaps on mapped pick-list elements
    options = db.rows(con, f"SELECT picklist_code, option_code, option_name, lob_scope FROM picklist_option WHERE {LIVE}")
    opt_by_pl = defaultdict(list)
    for o in options:
        opt_by_pl[o["picklist_code"]].append(o)
    aliases = defaultdict(set)
    for a in db.rows(con, f"SELECT picklist_code, source_system, source_value FROM picklist_option_alias WHERE {LIVE}"):
        aliases[(a["picklist_code"], a["source_system"])].add(a["source_value"].lower())
    for (system, attr), cnt in sorted(attr_vals.items()):
        el = el_by_code.get(maps.get((system, attr), ""))
        if not el or not el["picklist_code"]:
            continue
        pl = el["picklist_code"]
        codes = {o["option_code"].lower() for o in opt_by_pl[pl]}
        known = aliases[(pl, system)] | aliases[(pl, "*")] | codes
        for val, n in cnt.items():
            if not val or val.lower() in known:
                continue
            lobs = sorted(attr_lobs[(system, attr)])
            cands = rank(val, [(o["option_code"], f"{o['option_code']} · {o['option_name']}", [o["option_name"]])
                               for o in opt_by_pl[pl]])
            gaps.append(Gap(gap_id="", kind="CODE", side="SOURCE", system=system, ref=f"{system}.{attr} = '{val}'",
                            name=val, context=f"{pl} (element {el['element_code']})", occurrences=n,
                            risk="High" if el["element_code"] in reported else "Medium", candidates=cands,
                            proposal={"code": to_code(val, 12), "name": to_title(val), "picklist": pl,
                                      "lob_scope": ",".join(lobs),
                                      "description": f"{to_title(val)}. Added from {system} value '{val}'. (Drafted by SI² - edit if needed.)"},
                            actions=("map", "add")))

    # ---- 3. destination fields whose element is missing
    for f in db.rows(con, f"""SELECT f.field_id, f.bureau_field_name, f.element_code, f.bureau_description, v.lob_code, v.record_type, v.version_no
                              FROM layout_field f JOIN layout_version v ON v.layout_id=f.layout_id
                              WHERE f.status IN ('APPROVED','PENDING') AND v.status IN ('APPROVED','PENDING')"""):
        if f["element_code"] in el_by_code or f["element_code"] in ("FILLER",):
            continue
        name = f["bureau_field_name"]
        gaps.append(Gap(gap_id="", kind="DEST_ELEMENT", side="DESTINATION", system="ISO layout",
                        ref=f"{f['lob_code']} {f['record_type']} v{f['version_no']} · {name}", name=name,
                        context=f"field id {f['field_id']}", meaning=f["bureau_description"] or "", risk="High",
                        candidates=rank(name, cand_elements),
                        proposal={"code": to_code(name), "name": to_title(name), "data_type": "TEXT", "picklist": "",
                                  "description": f["bureau_description"] or draft_description(name, "TEXT"),
                                  "field_id": f["field_id"]},
                        actions=("map", "add")))

    # ---- 4. destination codes: option used by a reported field but no ISO code
    cmaps = defaultdict(list)
    for m in db.rows(con, f"SELECT picklist_code, option_code, lob_scope FROM bureau_code_map WHERE bureau_code='ISO' AND {LIVE}"):
        cmaps[(m["picklist_code"], m["option_code"])].append(m["lob_scope"])
    for el_code, lobs in reported.items():
        el = el_by_code.get(el_code)
        if not el or not el["picklist_code"]:
            continue
        for o in opt_by_pl[el["picklist_code"]]:
            used = [l for l in lobs if in_scope(o["lob_scope"], l)]
            missing = [l for l in used if not any(in_scope(s, l) for s in cmaps[(el["picklist_code"], o["option_code"])])]
            if missing:
                gaps.append(Gap(gap_id="", kind="DEST_CODE", side="DESTINATION", system="ISO",
                                ref=f"{el_code} · {', '.join(missing)}", name=o["option_code"],
                                context=el["picklist_code"], meaning=o["option_name"], risk="High",
                                proposal={"bureau_value": "", "lob_scope": ",".join(missing),
                                          "picklist": el["picklist_code"], "code": o["option_code"]},
                                actions=("add",)))
    for i, g in enumerate(gaps, 1):
        g.gap_id = f"G{i:03d}"
    return gaps


class Handler:
    """Applies the SME's decision. approve_now=True: the SME's click is the approval."""

    def __init__(self, con, actor: str, approve_now: bool = True, eff_date: str | None = None):
        self.con, self.actor, self.approve_now = con, actor, approve_now
        # New items apply to all data on file unless the SME picks another date
        self.eff = eff_date or "2000-01-01"

    # -- helpers
    def _add(self, table, data, comment):
        new_id = db.add_pending(self.con, table, {**data, "eff_date": data.get("eff_date", self.eff)}, self.actor, comment)
        if self.approve_now:
            db.set_status(self.con, table, new_id, "APPROVED", self.actor, f"Approved from Canonical Gaps: {comment}")
        return new_id

    def _status(self):
        return "approved" if self.approve_now else "sent to the Approval Queue"

    def _ensure_not_reported(self):
        if not db.one(self.con, f"SELECT 1 FROM canonical_element WHERE element_code=? AND {LIVE}", (NOT_REPORTED,)):
            self._add("canonical_element", {"element_code": NOT_REPORTED, "element_name": "Not reported / out of scope",
                                            "business_description": "Source attributes the SME marked as not needed for bureau reporting.",
                                            "data_type": "TEXT", "eff_date": "2000-01-01"}, "Out-of-scope bucket")

    # -- protocol
    def map_options(self, g: Gap):
        if g.kind in ("ELEMENT", "DEST_ELEMENT"):
            allx = [(e["element_code"], f"{e['element_code']} · {e['element_name']}") for e in _elements(self.con)]
        elif g.kind == "CODE":
            pl = g.context.split(" ")[0]
            allx = [(o["option_code"], f"{o['option_code']} · {o['option_name']}")
                    for o in db.rows(self.con, f"SELECT DISTINCT option_code, option_name FROM picklist_option WHERE picklist_code=? AND {LIVE}", (pl,))]
        else:
            return []
        first = [(k, f"{l}  ({int(s * 100)}% match)") for k, l, s in g.candidates]
        keys = {k for k, _ in first}
        return first + sorted((k, l) for k, l in allx if k not in keys)

    def proposal_fields(self, g: Gap):
        if g.kind in ("ELEMENT", "DEST_ELEMENT"):
            return [("code", "Element code", None), ("name", "Element name", None),
                    ("data_type", "Data type", ["CODE", "TEXT", "DATE", "AMOUNT", "NUMBER", "DECIMAL", "INTEGER"]),
                    ("picklist", "Pick list (CODE only)", None), ("description", "Business description", None)]
        if g.kind == "CODE":
            return [("code", "Option code", None), ("name", "Option name", None), ("lob_scope", "Lines (* = all)", None),
                    ("description", "Business description", None)]
        return [("bureau_value", "ISO code value", None), ("lob_scope", "Lines", None)]

    def map_existing(self, g: Gap, key: str) -> str:
        with db.tx(self.con):
            if g.kind == "ELEMENT":
                system, attr = g.ref.split(".", 1)
                self._add("source_mapping", {"source_system": system, "source_entity": g.context, "source_attribute": attr,
                                             "element_code": key}, f"{g.ref} mapped to {key}")
                self._add("element_alias", {"element_code": key, "alias_name": attr, "alias_context": f"SOURCE:{system}"}, "Gap alias")
                return f"{g.ref} → {key} ({self._status()}). Future runs read it automatically."
            if g.kind == "CODE":
                pl = g.context.split(" ")[0]
                self._add("picklist_option_alias", {"picklist_code": pl, "option_code": key, "source_system": g.system,
                                                    "source_value": g.name, "eff_date": "2000-01-01"},
                          f"{g.system} '{g.name}' = {pl} {key}")
                return f"{g.system} value '{g.name}' → {pl} {key} ({self._status()})."
            if g.kind == "DEST_ELEMENT":
                return self._remap_field(g, key)
        return "Nothing to do."

    def add_new(self, g: Gap, p: dict) -> str:
        with db.tx(self.con):
            if g.kind in ("ELEMENT", "DEST_ELEMENT"):
                code = to_code(p["code"], 40)
                if db.one(self.con, f"SELECT 1 FROM canonical_element WHERE element_code=? AND {LIVE}", (code,)):
                    return f"{code} already exists. Use Map to existing instead."
                pl = (p.get("picklist") or "").strip() if p.get("data_type") == "CODE" else ""
                if pl and not db.one(self.con, f"SELECT 1 FROM picklist WHERE picklist_code=? AND {LIVE}", (pl,)):
                    self._add("picklist", {"picklist_code": pl, "picklist_name": p["name"], "business_description": p["description"]}, "Gap pick list")
                    for v in g.values or {}:
                        oc = to_code(v, 12)
                        self._add("picklist_option", {"picklist_code": pl, "lob_scope": p.get("lob_scope") or "*", "option_code": oc,
                                                      "option_name": to_title(v), "business_description": to_title(v)}, "Gap option")
                        if oc != v:
                            self._add("picklist_option_alias", {"picklist_code": pl, "option_code": oc, "source_system": g.system,
                                                                "source_value": v, "eff_date": "2000-01-01"}, "Gap option alias")
                self._add("canonical_element", {"element_code": code, "element_name": p["name"], "business_description": p["description"],
                                                "data_type": p["data_type"], "picklist_code": pl or None}, "Added from Canonical Gaps")
                self._add("element_alias", {"element_code": code, "alias_name": g.name, "alias_context": f"{g.side}:{g.system}"}, "Gap alias")
                if g.kind == "ELEMENT":
                    system, attr = g.ref.split(".", 1)
                    self._add("source_mapping", {"source_system": system, "source_entity": g.context, "source_attribute": attr,
                                                 "source_data_type": p["data_type"], "element_code": code}, "Gap mapping")
                    extra = f" with pick list {pl} ({len(g.values)} options)" if pl and g.values else ""
                    return f"New canonical element {code}{extra} added and {g.ref} mapped ({self._status()})."
                return self._remap_field(g, code, created=True)
            if g.kind == "CODE":
                pl, oc = g.context.split(" ")[0], to_code(p["code"], 12)
                self._add("picklist_option", {"picklist_code": pl, "lob_scope": p.get("lob_scope") or "*", "option_code": oc,
                                              "option_name": p["name"], "business_description": p["description"], "eff_date": "2000-01-01"},
                          f"New {pl} option {oc}")
                if oc != g.name:
                    self._add("picklist_option_alias", {"picklist_code": pl, "option_code": oc, "source_system": g.system,
                                                        "source_value": g.name, "eff_date": "2000-01-01"}, "Gap option alias")
                return (f"New {pl} code {oc} added ({self._status()}). If ISO reports {pl}, its ISO code now shows "
                        "as a destination-code gap.")
            if g.kind == "DEST_CODE":
                if not p.get("bureau_value"):
                    return "Enter the ISO code value first."
                self._add("bureau_code_map", {"bureau_code": "ISO", "lob_scope": p.get("lob_scope") or "*", "picklist_code": p["picklist"],
                                              "option_code": p["code"], "bureau_value": str(p["bureau_value"]).strip(), "eff_date": "2000-01-01"},
                          f"ISO code for {p['picklist']} {p['code']}")
                return f"ISO code {p['bureau_value']} added for {p['picklist']} {p['code']} ({self._status()})."
        return "Nothing to do."

    def not_needed(self, g: Gap, reason: str) -> str:
        if g.kind != "ELEMENT":
            return "Only source elements can be marked not needed."
        with db.tx(self.con):
            self._ensure_not_reported()
            system, attr = g.ref.split(".", 1)
            self._add("source_mapping", {"source_system": system, "source_entity": g.context, "source_attribute": attr,
                                         "element_code": NOT_REPORTED, "notes": reason}, f"Not needed: {reason}")
        return f"{g.ref} marked not needed ({reason}); it will be ignored in runs and won't come back as a gap."

    def _remap_field(self, g: Gap, element: str, created: bool = False) -> str:
        """Layout fields are never edited: reject the unmapped row and add a corrected copy."""
        fid = int(g.proposal.get("field_id") or g.context.split()[-1])
        f = db.one(self.con, "SELECT * FROM layout_field WHERE field_id=?", (fid,))
        db.set_status(self.con, "layout_field", fid, "REJECTED", self.actor, f"Replaced: element {element}")
        el = db.one(self.con, f"SELECT picklist_code, business_description FROM canonical_element WHERE element_code=? AND {LIVE}", (element,))
        data = {k: v for k, v in f.items() if k not in ("field_id", "status", "created_by", "created_at", "approved_by",
                                                         "approved_at", "supersedes_id")}
        data.update({"element_code": element, "business_description": el["business_description"] if el else None,
                     "transform_rule_code": "TR_CODE_MAP" if el and el["picklist_code"] else data["transform_rule_code"]})
        new_id = db.add_pending(self.con, "layout_field", data, self.actor, f"Field {f['bureau_field_name']} → {element}")
        if self.approve_now:
            db.set_status(self.con, "layout_field", new_id, "APPROVED", self.actor, "Approved from Canonical Gaps")
        return (f"{'New element ' + element + ' added; ' if created else ''}layout field '{f['bureau_field_name']}' now maps to "
                f"{element} ({self._status()}).")
