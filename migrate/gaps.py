"""Canonical Gaps for the Legacy-to-Cloud Migration Workbench.

* source element gap      - a legacy element with no canonical match (and not marked not migrated)
* code gap                - a legacy pick-list value with no cloud code
* destination field gap   - a required cloud field that no legacy element feeds yet

Decisions update the workbench state the same way the SME queue does (map overrides,
value overrides, NOT_MIGRATED); "Add new" extends the cloud destination (new column or
new pick-list code), which rebuilds the canonical model from it.
"""
from __future__ import annotations

import pandas as pd

from si2_common.gaps import Gap, draft_description, rank, to_pascal, to_title

from . import engine as E

TYPE_MAP = {"text": "string", "integer": "integer", "decimal": "decimal", "date": "date", "date (YYYYMMDD)": "date",
            "flag": "boolean", "email": "string", "phone": "string"}
TABLE_FOR = {"Policy": "policy", "Claim": "claim", "ClaimPayment": "claim_payment", "Producer": "producer",
             "Coverage": "coverage", "Party": "party"}


def _snake(name: str) -> str:
    return "_".join(w.lower() for w in to_title(name).split()) or "new_field"


def scan(ss) -> list[Gap]:
    gaps: list[Gap] = []
    canon, m, vm, inv = ss.canon, ss.m, ss.vm, ss.inv.set_index("element_id")
    cands = [(r.canonical_id, f"{r.canonical_id} ({r.destination_fields})", [s.strip() for s in r.synonyms.split(",")])
             for r in canon.itertuples()]
    tables = list(dict.fromkeys(ss.src["dest_schema"].table))
    for r in m.itertuples():
        if r.status != "Needs SME review" or r.element_id in ss.map_ov or r.confidence >= 60:
            continue
        e = inv.loc[r.element_id]
        default_table = TABLE_FOR.get(E.CONTEXT.get(r.entity, ""), tables[0])
        dtype = TYPE_MAP.get(e.data_type, "string")
        vals = dict(e.pick) if isinstance(e.pick, dict) else {}
        field = _snake(r.alias or r.element)
        gaps.append(Gap(gap_id="", kind="ELEMENT", side="SOURCE", system=e.source_type, ref=r.element_id,
                        name=r.element, context=r.entity, data_type=dtype,
                        samples=[s.strip() for s in str(e.samples).split(",") if s.strip()], values=vals,
                        occurrences=int(e.distinct), risk="Medium",
                        candidates=rank(r.alias or r.element, cands),
                        proposal={"table": default_table, "field": field, "type": "picklist" if vals else dtype,
                                  "pick_list": to_pascal(field) if vals else "", "length": str(int(e.length or 50)),
                                  "description": draft_description(r.alias or r.element, "CODE" if vals else dtype.upper(),
                                                                   [s.strip() for s in str(e.samples).split(",")][:3],
                                                                   r.element_id, vals)}))
    pls = ss.src["dest_picklists"]
    for r in vm.itertuples():
        if r.status != "Needs SME review" or (r.element_id, r.legacy_value) in ss.val_ov or r.confidence >= 50:
            continue
        codes = pls[pls.pick_list == r.pick_list]
        gaps.append(Gap(gap_id="", kind="CODE", side="SOURCE", system="Legacy", ref=f"{r.element_id} = '{r.legacy_value}'",
                        name=r.legacy_value, context=r.pick_list, meaning=r.legacy_meaning, risk="High",
                        candidates=rank(r.legacy_meaning, [(c.code, f"{c.code} · {c.description}", [c.description])
                                                           for c in codes.itertuples()]),
                        proposal={"code": to_pascal(r.legacy_meaning), "description": to_title(r.legacy_meaning),
                                  "element_id": r.element_id},
                        actions=("map", "add")))
    mapped = set(m.loc[(m.status != "Needs SME review") & (m.canonical_id != E.NOT_MIGRATED), "canonical_id"])
    elements = [(eid, f"{eid} ({inv.at[eid, 'alias']})", [inv.at[eid, "alias"]]) for eid in inv.index]
    for r in canon[canon.required].itertuples():
        if r.canonical_id in mapped:
            continue
        gaps.append(Gap(gap_id="", kind="DEST_ELEMENT", side="DESTINATION", system="Cloud destination",
                        ref=r.destination_fields, name=r.canonical_id, context="required field", meaning=r.description,
                        risk="High", candidates=rank(r.attribute, elements), actions=("map",)))
    for i, g in enumerate(gaps, 1):
        g.gap_id = f"M{i:03d}"
    return gaps


class Handler:
    def __init__(self, ss, actor: str, recompute, log, invalidate):
        self.ss, self.actor, self._recompute, self._log, self._invalidate = ss, actor, recompute, log, invalidate

    def _done(self, event, detail, msg):
        self._log(self.actor, event, detail)
        self._recompute()
        self._invalidate("canonical gap resolved")
        return msg + f" Mapping is now {self.ss.cov['pct']}%."

    def map_options(self, g: Gap):
        ss = self.ss
        if g.kind == "ELEMENT":
            allx = [(c, f"{c} ({d})") for c, d in zip(ss.canon.canonical_id, ss.canon.destination_fields)]
        elif g.kind == "CODE":
            pls = ss.src["dest_picklists"]
            allx = [(c.code, f"{c.code} · {c.description}") for c in pls[pls.pick_list == g.context].itertuples()]
        else:
            allx = [(e, e) for e in ss.inv.element_id]
        first = [(k, f"{l}  ({int(s * 100)}% match)") for k, l, s in g.candidates]
        keys = {k for k, _ in first}
        return first + [(k, l) for k, l in allx if k not in keys]

    def proposal_fields(self, g: Gap):
        if g.kind == "ELEMENT":
            tables = list(dict.fromkeys(self.ss.src["dest_schema"].table))
            return [("table", "Cloud table", tables), ("field", "New cloud column", None),
                    ("type", "Type", ["string", "integer", "decimal", "date", "boolean", "picklist"]),
                    ("pick_list", "Pick list (picklist only)", None), ("description", "Business description", None)]
        return [("code", "New cloud code", None), ("description", "Description", None)]

    def map_existing(self, g: Gap, key: str) -> str:
        ss = self.ss
        if g.kind == "ELEMENT":
            ss.map_ov[g.ref] = key
            ss.rejected.discard(g.ref)
            return self._done("Mapping approved (Canonical Gaps)", f"{g.ref} → {key}", f"{g.ref} → {key}.")
        if g.kind == "CODE":
            eid = g.ref.split(" = ")[0]
            ss.val_ov[(eid, g.name)] = key
            return self._done("Value mapping approved (Canonical Gaps)", f"{eid} '{g.name}' → {key}", f"'{g.name}' → {key}.")
        ss.map_ov[key] = g.name
        return self._done("Mapping approved (Canonical Gaps)", f"{key} → {g.name}", f"{key} now feeds {g.name}.")

    def add_new(self, g: Gap, p: dict) -> str:
        ss = self.ss
        if g.kind == "ELEMENT":
            ds = ss.src["dest_schema"]
            if ((ds.table == p["table"]) & (ds.field == p["field"])).any():
                return f"{p['table']}.{p['field']} already exists. Use Map to existing instead."
            row = {"table": p["table"], "field": p["field"], "type": p["type"], "length": p.get("length", "50"),
                   "required": "", "key": "", "pick_list": p.get("pick_list", "") if p["type"] == "picklist" else "",
                   "description": p["description"]}
            src = dict(ss.src)
            src["dest_schema"] = pd.concat([ds, pd.DataFrame([row])], ignore_index=True)
            if row["pick_list"] and g.values:
                pls = src["dest_picklists"]
                new = [{"pick_list": row["pick_list"], "code": to_pascal(v), "description": str(v).upper()}
                       for v in g.values.values() if not ((pls.pick_list == row["pick_list"]) & (pls.code == to_pascal(v))).any()]
                src["dest_picklists"] = pd.concat([pls, pd.DataFrame(new)], ignore_index=True)
            ss.src = src
            cid = f"{E.pascal(p['table'])}.{E.pascal(p['field'])}"
            ss.map_ov[g.ref] = cid
            return self._done("Canonical element added (Canonical Gaps)", f"{cid} → {p['table']}.{p['field']} from {g.ref}",
                              f"New canonical element {cid} and cloud column {p['table']}.{p['field']} added; {g.ref} mapped.")
        if g.kind == "CODE":
            pls = ss.src["dest_picklists"]
            code = to_pascal(p["code"])
            src = dict(ss.src)
            if not ((pls.pick_list == g.context) & (pls.code == code)).any():
                src["dest_picklists"] = pd.concat([pls, pd.DataFrame([{"pick_list": g.context, "code": code,
                                                                        "description": p["description"]}])], ignore_index=True)
                ss.src = src
            ss.val_ov[(g.proposal["element_id"], g.name)] = code
            return self._done("Pick-list code added (Canonical Gaps)", f"{g.context}.{code} for '{g.name}'",
                              f"New {g.context} code {code} added; legacy '{g.name}' maps to it.")
        return "Nothing to do."

    def not_needed(self, g: Gap, reason: str) -> str:
        self.ss.map_ov[g.ref] = E.NOT_MIGRATED
        return self._done("Marked not migrated (Canonical Gaps)", f"{g.ref}: {reason}", f"{g.ref} stays in the archive ({reason}).")
