"""One company canonical model across every SI² app, with where-used.

Each app has its own model today: the ISO element catalog, the NCCI canonical tables, the migration's
cloud canonical, the rule vocabulary, the rating variables, and the core canonical entities. This module
harvests all of them and unifies them into company business terms, so one term (Policy Number) shows every
name it has in every app (POLICY_NUMBER, policy.policy_number, Policy.PolicyNumber ...). That is the
starting point for one governed company model: a single definition, a standard name, and where-used for
impact analysis before anything changes.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from .gaps import to_title, words

ROOT = Path(__file__).resolve().parents[1]

# business term -> word sets that mean it (after abbreviation expansion); first match wins, exact sets first
CONCEPTS = {
    "POLICY_NUMBER": [{"POLICY", "NUMBER"}, {"POLICY", "IDENTIFIER"}],
    "POLICY_EFFECTIVE_DATE": [{"POLICY", "EFFECTIVE", "DATE"}, {"EFFECTIVE", "DATE"}],
    "POLICY_EXPIRATION_DATE": [{"POLICY", "EXPIRATION", "DATE"}, {"EXPIRATION", "DATE"}],
    "STATE": [{"STATE"}, {"STATE", "CODE"}, {"BASE", "STATE"}, {"RISK", "STATE"}, {"PRIMARY", "STATE"}, {"STATE", "REL"}],
    "ZIP_CODE": [{"ZIP"}, {"ZIP", "CODE"}, {"POSTAL", "CODE"}, {"RISK", "ZIP"}],
    "LINE_OF_BUSINESS": [{"LINE", "BUSINESS"}, {"LINE", "BUSINESS", "CODE"}],
    "WRITTEN_PREMIUM": [{"WRITTEN", "PREMIUM"}, {"PREMIUM", "AMOUNT"}, {"PREMIUM"}],
    "CLAIM_NUMBER": [{"CLAIM", "NUMBER"}, {"CLAIM", "IDENTIFIER"}],
    "LOSS_DATE": [{"LOSS", "DATE"}, {"ACCIDENT", "DATE"}, {"DATE", "LOSS"}, {"ACCIDENT", "DATE", "LOSS"}],
    "REPORT_DATE": [{"REPORT", "DATE"}, {"REPORTED", "DATE"}, {"CLAIM", "REPORT", "DATE"}],
    "PAID_LOSS": [{"PAID", "LOSS"}, {"LOSS", "PAID"}, {"PAID", "AMOUNT"}, {"PAYMENT", "AMOUNT"}, {"INDEMNITY", "PAID"}],
    "OUTSTANDING_RESERVE": [{"OUTSTANDING", "RESERVE"}, {"RESERVE"}, {"RESERVE", "AMOUNT"}, {"OUTSTANDING", "LOSS"}],
    "CLAIM_STATUS": [{"CLAIM", "STATUS"}, {"CLAIM", "STATUS", "CODE"}],
    "POLICY_STATUS": [{"POLICY", "STATUS"}],
    "CAUSE_OF_LOSS": [{"CAUSE", "LOSS"}, {"LOSS", "CAUSE"}, {"CAUSE", "LOSS", "CODE"}],
    "CLASS_CODE": [{"CLASS", "CODE"}, {"CLASSIFICATION", "CODE"}],
    "EXPOSURE": [{"EXPOSURE"}, {"EXPOSURE", "AMOUNT"}, {"PAYROLL"}],
    "DRIVER_AGE": [{"DRIVER", "AGE"}, {"AGE"}],
    "DRIVER_BIRTH_DATE": [{"BIRTH", "DATE"}, {"DATE", "BIRTH"}],
    "VEHICLE_MODEL_YEAR": [{"MODEL", "YEAR"}, {"VEHICLE", "YEAR"}],
    "VEHICLE_USE": [{"USE"}, {"USE", "TYPE"}, {"VEHICLE", "USE"}],
    "VIN": [{"VIN"}, {"VEHICLE", "IDENTIFICATION", "NUMBER"}],
    "COVERAGE_CODE": [{"COVERAGE", "CODE"}, {"COVERAGE"}, {"COVERAGE", "TYPE"}],
    "LIMIT": [{"LIMIT"}, {"BI", "LIMIT"}, {"PD", "LIMIT"}, {"LIMIT", "AMOUNT"}, {"COVERAGE", "LIMIT"}],
    "DEDUCTIBLE": [{"DEDUCTIBLE"}, {"DEDUCTIBLE", "AMOUNT"}, {"COLL", "DEDUCTIBLE"}, {"COMP", "DEDUCTIBLE"}],
    "TERRITORY": [{"TERRITORY"}, {"TERRITORY", "CODE"}, {"RATING", "TERRITORY"}],
    "PRODUCER_CODE": [{"PRODUCER", "CODE"}, {"AGENT", "CODE"}, {"AGENT", "NUMBER"}, {"PRODUCER"}],
    "INSURED_NAME": [{"INSURED", "NAME"}, {"NAMED", "INSURED"}, {"FULL", "NAME"}, {"NAME", "INSURED"}],
    "FEIN": [{"FEIN"}, {"FEDERAL", "EMPLOYER", "IDENTIFICATION", "NUMBER"}],
    "PRIOR_CLAIMS": [{"PRIOR", "CLAIMS"}, {"CLAIMS"}, {"AT", "FAULT", "CLAIMS"}],
    "VIOLATIONS": [{"VIOLATIONS"}, {"VIOLATION", "COUNT"}],
    "ACCOUNTING_DATE": [{"ACCOUNTING", "DATE"}, {"TRANSACTION", "DATE"}],
    "TRANSACTION_TYPE": [{"TRANSACTION", "TYPE"}, {"TRANSACTION", "CODE"}],
    "CARRIER_CODE": [{"CARRIER", "CODE"}, {"COMPANY", "CODE"}, {"CARRIER", "GROUP", "CODE"}],
    "PAYMENT_PLAN": [{"PAYMENT", "PLAN"}, {"BILL", "PLAN"}],
}
APPS = ["Core canonical", "ISO bureau", "NCCI bureau", "Migration (cloud)", "Rule engine", "Rating engine"]

RATING_VARIABLES = [  # (name, description, type)
    ("base_rate", "Base rate per coverage", "money"), ("state", "State relativity", "code"),
    ("territory", "Rating territory", "code"), ("driver_age", "Driver age band", "number"),
    ("prior_claims", "At-fault claims, last 3 years", "number"), ("violations", "Moving violations, last 3 years", "number"),
    ("use", "Vehicle use", "code"), ("bi_limit", "Bodily injury / UM limit", "code"), ("pd_limit", "Property damage limit", "code"),
    ("coll_deductible", "Collision deductible", "money"), ("comp_deductible", "Comprehensive deductible", "money"),
    ("model_year", "Vehicle model year", "number"), ("symbol", "Physical damage symbol", "number"),
    ("policy_fee", "Policy fee", "money"),
]


# ------------------------------------------------------------------------------------------ governance
GOV_APP = "company_model"


def published() -> dict:
    """Approved company terms: {term: {standard_name, definition, synonyms, owner, version, effective_from, ...}}."""
    try:
        from . import store
        raw = store.load(GOV_APP).get("terms")
        return store.loads(raw) if raw else {}
    except Exception:
        return {}


def history() -> list:
    try:
        from . import store
        raw = store.load(GOV_APP).get("history")
        return store.loads(raw) if raw else []
    except Exception:
        return []


def publish(term: str, change: dict, proposed_by: str, approved_by: str, note: str = "") -> dict:
    import datetime as dt
    from . import store
    terms, hist = published(), history()
    cur = terms.get(term, {})
    entry = {**cur, **change, "version": int(cur.get("version", 0)) + 1, "proposed_by": proposed_by,
             "approved_by": approved_by, "effective_from": dt.date.today().isoformat(), "note": note}
    terms[term] = entry
    hist.append({"term": term, **entry})
    store.save(GOV_APP, "terms", store.dumps(terms), approved_by)
    store.save(GOV_APP, "history", store.dumps(hist), approved_by)
    return entry


def _synonym_index() -> dict:
    out = {}
    for term, e in published().items():
        for syn in [e.get("standard_name", "")] + list(e.get("synonyms", [])):
            w = frozenset(words(syn))
            if w:
                out[w] = term
    return out


def concept_of(name: str, _syn: dict | None = None) -> str:
    w = set(words(name))
    if not w:
        return ""
    syn = _syn if _syn is not None else _synonym_index()
    if frozenset(w) in syn:
        return syn[frozenset(w)]
    for concept, pats in CONCEPTS.items():
        if any(w == p for p in pats):
            return concept
    for concept, pats in CONCEPTS.items():
        if any(len(p) >= 2 and p <= w and len(w) - len(p) <= 1 for p in pats):
            return concept
    return "_".join(words(name))


def harvest() -> pd.DataFrame:
    rows = []

    def add(app, entity, element, typ, desc):
        rows.append({"app": app, "entity": entity, "element": element, "type": str(typ or "").lower(),
                     "description": desc or ""})
    try:
        from . import data
        for ent, cols in data.CANONICAL_ENTITIES.items():
            for c in cols:
                add("Core canonical", ent, f"{ent}.{c}", "", to_title(c))
    except Exception:
        pass
    try:
        from iso_bureau import catalog as C
        for code, spec in {**C.ELEMENTS, **getattr(C, "NEW_2027_ELEMENTS", {})}.items():
            add("ISO bureau", "ISO element", code, spec[1], spec[3])
    except Exception:
        pass
    try:
        from bureau import canonical as cn
        for t, cols in cn.SCHEMA.items():
            for c, spec in cols.items():
                add("NCCI bureau", t, f"{t}.{c}", spec[0], spec[1])
    except Exception:
        pass
    try:
        from migrate import engine as E
        ds = pd.read_csv(ROOT / "migrate" / "samples" / "destination_schema.csv", dtype=str).fillna("")
        pl = pd.read_csv(ROOT / "migrate" / "samples" / "destination_picklists.csv", dtype=str).fillna("")
        for r in E.build_canonical(ds, pl).itertuples():
            add("Migration (cloud)", r.entity, r.canonical_id, r.data_type, r.description)
    except Exception:
        pass
    try:
        from .rules_gaps import FIELDS
        for f, m in FIELDS.items():
            add("Rule engine", "Submission", f, "", m)
    except Exception:
        pass
    for n, d, t in RATING_VARIABLES:
        add("Rating engine", "Rating variable", n, t, d)
    df = pd.DataFrame(rows)
    syn = _synonym_index()
    df["term"] = [concept_of(e.split(".")[-1], syn) for e in df.element]
    return df


def terms(where: pd.DataFrame) -> pd.DataFrame:
    """One row per company business term, with the apps that use it and every name it goes by."""
    out = []
    pub = published()
    for term, g in where.groupby("term"):
        descs = [d for d in g.description if d and len(d) > 3]
        core = g[g.app == "Core canonical"]
        p = pub.get(term, {})
        out.append({"term": term, "business name": to_title(term.replace("_", " ")),
                    "standard name": p.get("standard_name") or term.lower(),
                    "status": f"Published v{p['version']}" if p else "Draft (harvested)",
                    "definition": p.get("definition") or (max(descs, key=len) if descs else to_title(term.replace("_", " "))),
                    "apps": int(g.app.nunique()), "names in use": int(g.element.str.split(".").str[-1].str.lower().nunique()),
                    **{a: "✓" if (g.app == a).any() else "" for a in APPS},
                    "in core model": "Yes" if len(core) else "No"})
    df = pd.DataFrame(out)
    return df.sort_values(["apps", "term"], ascending=[False, True]).reset_index(drop=True)


def definition_for(name: str) -> tuple[str, str]:
    """(term, published definition) for a column name; ('', '') when the company has not published one."""
    pub = published()
    t = concept_of(name)
    return (t, pub[t]["definition"]) if t in pub and pub[t].get("definition") else (t if t in CONCEPTS or t in pub else "", "")


def migration_synonyms(where: pd.DataFrame | None = None) -> dict:
    """Published synonyms for the migration's canonical ids (feeds its matching)."""
    pub = published()
    if not pub:
        return {}
    where = harvest() if where is None else where
    out = {}
    for r in where[(where.app == "Migration (cloud)") & where.term.isin(list(pub))].itertuples():
        out[r.element] = [x for x in pub[r.term].get("synonyms", []) if x]
    return out
