"""Canonical Gaps for the Business Rule Engine.

The rule vocabulary (fields and their allowed codes) is the canonical model a rule is
written against. Gaps appear when an analyst, a filing or an imported rule set uses
something the vocabulary does not have yet:

* element gap - a rule names a field the vocabulary does not have (`drv_age`, `telematics_score`)
* code gap    - a rule compares a coded field with a value outside its code list (`state == 'FLA'`)

Map to existing rewrites the rule conditions; Add new extends the vocabulary (and the
sample data and test form, so the rule can run at once); Not needed switches the rules
that depend on it off. Every decision is written to the rule audit log.
"""
from __future__ import annotations

import ast
import datetime as dt
import re
import zlib

import numpy as np
import pandas as pd

from .gaps import Gap, draft_description, rank, to_title
from .rules import RuleError, compile_rule, fields_used

US_STATES = ["AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "DC", "FL", "GA", "HI", "ID", "IL", "IN", "IA", "KS",
             "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC",
             "ND", "OH", "OK", "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY"]


# the rule vocabulary of the Personal Auto demo (fields and coded domains)
FIELDS = {
    "state": "Two-letter state", "driver_age": "Age of the principal driver", "years_licensed": "Years licensed",
    "prior_claims": "At-fault claims, last 3 years", "violations": "Moving violations, last 3 years",
    "vehicle_value": "Vehicle value ($)", "model_year": "Vehicle model year",
    "use_type": "Pleasure, Commute, Business or Rideshare", "annual_miles": "Estimated annual miles",
    "coverage_lapse_days": "Days without insurance before this policy",
}
BASE_DOMAINS = {"state": US_STATES, "use_type": ["Pleasure", "Commute", "Business", "Rideshare"]}


def _snake(name: str) -> str:
    return "_".join(w.lower() for w in to_title(name).split()) or "new_field"


def vocabulary(base_fields: dict, ss) -> dict:
    """Field -> meaning, base plus SME-approved additions."""
    return {**base_fields, **{k: v["meaning"] for k, v in getattr(ss, "fields_ext", {}).items()}}


def domains(base_domains: dict, ss) -> dict:
    ext = getattr(ss, "domains_ext", {})
    out = {k: list(v) for k, v in base_domains.items()}
    for f, codes in ext.items():
        out.setdefault(f, [])
        out[f] += [c for c in codes if c not in out[f]]
    for f, spec in getattr(ss, "fields_ext", {}).items():
        if spec.get("values"):
            out[f] = list(spec["values"]) + [c for c in out.get(f, []) if c not in spec["values"]]
    return out


def _literals(tree) -> list[tuple[str, str]]:
    """(field, text literal) pairs compared in a condition: field == 'X', field in ['X', 'Y']."""
    out = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Compare) and isinstance(n.left, ast.Name):
            for comp in n.comparators:
                items = comp.elts if isinstance(comp, (ast.List, ast.Tuple)) else [comp]
                out += [(n.left.id, e.value) for e in items if isinstance(e, ast.Constant) and isinstance(e.value, str)]
    return out


def _numbers(tree, field: str) -> list[float]:
    out = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Compare) and isinstance(n.left, ast.Name) and n.left.id == field:
            out += [c.value for c in n.comparators if isinstance(c, ast.Constant) and isinstance(c.value, (int, float))]
    return out


def scan(rules: pd.DataFrame, base_fields: dict, base_domains: dict, ss) -> list[Gap]:
    vocab, doms = vocabulary(base_fields, ss), domains(base_domains, ss)
    ignored = getattr(ss, "gap_ignored", set())
    unknown: dict[str, dict] = {}
    bad_codes: dict[tuple[str, str], list[str]] = {}
    for r in rules.itertuples():
        try:
            tree = compile_rule(str(r.condition))
        except RuleError:
            continue
        for f in sorted(fields_used(tree) - set(vocab)):
            u = unknown.setdefault(f, {"rules": [], "text": [], "nums": []})
            u["rules"].append(r.rule_id)
            u["text"] += [v for fld, v in _literals(tree) if fld == f]
            u["nums"] += _numbers(tree, f)
        for f, v in _literals(tree):
            if f in doms and v not in doms[f]:
                bad_codes.setdefault((f, v), []).append(r.rule_id)

    gaps: list[Gap] = []
    field_cands = [(k, f"{k} · {m}", [m]) for k, m in vocab.items()]
    for f, u in unknown.items():
        if f"field:{f}" in ignored:
            continue
        coded = bool(u["text"])
        values = list(dict.fromkeys(u["text"]))
        gaps.append(Gap(gap_id="", kind="ELEMENT", side="RULE", system="Rule set", ref=", ".join(u["rules"]), name=f,
                        context="rule vocabulary", data_type="CODE" if coded else "NUMBER",
                        samples=[str(x) for x in (values or u["nums"])][:5], occurrences=len(u["rules"]),
                        risk="High", candidates=rank(f, field_cands),
                        proposal={"field": _snake(f), "type": "code" if coded else "number",
                                  "values": ", ".join(values),
                                  "meaning": draft_description(f, "CODE" if coded else "NUMBER",
                                                               values or [str(x) for x in u["nums"]],
                                                               f"rule {u['rules'][0]}").replace(" (Drafted by SI² - edit if needed.)", "")}))
    for (f, v), ids in bad_codes.items():
        cands = [(c, c, [c]) for c in doms[f]]
        best = rank(v, cands) or [(c, c, 0.2) for c in doms[f] if c[:2].upper() == v[:2].upper()][:3]
        gaps.append(Gap(gap_id="", kind="CODE", side="RULE", system="Rule set", ref=", ".join(ids), name=v,
                        context=f, meaning=f"Compared with {f} in {', '.join(ids)}", risk="High",
                        occurrences=len(ids), values={c: "" for c in doms[f][:12]}, candidates=best,
                        proposal={"code": v.strip(), "description": to_title(v)}, actions=("map", "add")))
    for i, g in enumerate(gaps, 1):
        g.gap_id = f"R{i:03d}"
    return gaps


def sample_column(name: str, spec: dict, n: int, seed_hint: int = 0) -> list:
    """Synthetic values for a field added by the SME, so the rule runs against sample data at once."""
    rng = np.random.default_rng(zlib.crc32(name.encode()) + seed_hint)
    if spec.get("values"):
        return list(rng.choice(list(spec["values"]), n))
    hi = max(10.0, 2.5 * max([abs(float(x)) for x in spec.get("thresholds", [])] or [40]))
    return [int(x) for x in rng.integers(0, int(hi) + 1, n)]


def extend_submissions(subs: pd.DataFrame, ss) -> pd.DataFrame:
    out = subs.copy()
    for f, spec in getattr(ss, "fields_ext", {}).items():
        if f not in out:
            out[f] = sample_column(f, spec, len(out))
    return out


def _sub_field(cond: str, old: str, new: str) -> str:
    # field names only: never inside quoted text
    parts = re.split(r"('(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\")", cond)
    return "".join(p if i % 2 else re.sub(rf"\b{re.escape(old)}\b", new, p) for i, p in enumerate(parts))


def _sub_literal(cond: str, old: str, new: str) -> str:
    return re.sub(rf"(['\"]){re.escape(old)}\1", f"'{new}'", cond)


class Handler:
    def __init__(self, ss, rules: pd.DataFrame, base_fields: dict, base_domains: dict, actor: str):
        self.ss, self.rules, self.base_fields, self.base_domains, self.actor = ss, rules.copy(), base_fields, base_domains, actor
        for attr, default in (("fields_ext", {}), ("domains_ext", {}), ("gap_ignored", set()), ("rule_audit", [])):
            if not hasattr(ss, attr):
                setattr(ss, attr, default)

    def _save(self, event: str, detail: str):
        self.ss.rules = self.rules.reset_index(drop=True)
        try:
            del self.ss["rule_editor"]          # editor re-reads the rules (edits are already in self.rules)
        except (KeyError, TypeError):
            pass
        self.ss.rule_audit.append({"time": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "by": self.actor,
                                   "event": event, "detail": detail})

    def _ids(self, g: Gap):
        return [i.strip() for i in g.ref.split(",")]

    def map_options(self, g: Gap):
        if g.kind == "ELEMENT":
            allx = [(k, f"{k} · {m}") for k, m in vocabulary(self.base_fields, self.ss).items()]
        else:
            allx = [(c, c) for c in domains(self.base_domains, self.ss).get(g.context, [])]
        first = [(k, f"{l}  ({int(s * 100)}% match)") for k, l, s in g.candidates]
        keys = {k for k, _ in first}
        return first + [(k, l) for k, l in allx if k not in keys]

    def proposal_fields(self, g: Gap):
        if g.kind == "ELEMENT":
            return [("field", "New field name", None), ("type", "Type", ["number", "code", "text"]),
                    ("values", "Allowed codes (code type, comma separated)", None),
                    ("meaning", "Business description", None)]
        return [("code", f"New {g.context} code", None), ("description", "Description", None)]

    def map_existing(self, g: Gap, key: str) -> str:
        hit = self.rules.rule_id.isin(self._ids(g))
        if g.kind == "ELEMENT":
            self.rules.loc[hit, "condition"] = [_sub_field(c, g.name, key) for c in self.rules.loc[hit, "condition"]]
            self._save("Rule field mapped (Canonical Gaps)", f"{g.name} → {key} in {g.ref}")
            return f"'{g.name}' is now '{key}' in {g.ref}."
        self.rules.loc[hit, "condition"] = [_sub_literal(c, g.name, key) for c in self.rules.loc[hit, "condition"]]
        self._save("Rule code mapped (Canonical Gaps)", f"{g.context} '{g.name}' → '{key}' in {g.ref}")
        return f"{g.context} '{g.name}' is now '{key}' in {g.ref}."

    def add_new(self, g: Gap, p: dict) -> str:
        ss = self.ss
        if g.kind == "ELEMENT":
            name = _snake(p["field"])
            if name in vocabulary(self.base_fields, ss):
                raise ValueError(f"'{name}' already exists. Use Map to existing instead.")
            values = [v.strip() for v in str(p.get("values", "")).split(",") if v.strip()] if p["type"] == "code" else []
            nums = [float(x) for x in g.samples if re.fullmatch(r"-?\d+(\.\d+)?", str(x))]
            ss.fields_ext[name] = {"meaning": p["meaning"], "type": p["type"], "values": values, "thresholds": nums,
                                   "added_by": self.actor, "effective": dt.date.today().isoformat()}
            if name != g.name:
                hit = self.rules.rule_id.isin(self._ids(g))
                self.rules.loc[hit, "condition"] = [_sub_field(c, g.name, name) for c in self.rules.loc[hit, "condition"]]
            self._save("Rule field added (Canonical Gaps)", f"{name} ({p['type']}): {p['meaning']}")
            return (f"New field '{name}' added to the rule vocabulary, the sample submissions and the test form; "
                    f"{g.ref} can now run.")
        code = p["code"].strip()
        if code in domains(self.base_domains, ss).get(g.context, []):
            raise ValueError(f"{code} is already a {g.context} code. Use Map to existing instead.")
        ss.domains_ext.setdefault(g.context, []).append(code)
        if code != g.name:
            hit = self.rules.rule_id.isin(self._ids(g))
            self.rules.loc[hit, "condition"] = [_sub_literal(c, g.name, code) for c in self.rules.loc[hit, "condition"]]
        self._save("Rule code added (Canonical Gaps)", f"{g.context} code {code}: {p.get('description', '')}")
        return f"New {g.context} code '{code}' added; {g.ref} can use it."

    def not_needed(self, g: Gap, reason: str) -> str:
        hit = self.rules.rule_id.isin(self._ids(g))
        self.rules.loc[hit, "active"] = False
        self.ss.gap_ignored.add(f"field:{g.name}")
        self._save("Rules switched off (Canonical Gaps)", f"{g.ref} use '{g.name}': {reason}")
        return f"{g.ref} switched off: '{g.name}' is not part of the vocabulary ({reason})."

