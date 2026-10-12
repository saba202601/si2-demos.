"""Canonical Gaps for the Fraud Engine: the data each fraud type needs that the book does not have yet.

Every catalog row lists its `data_needed`. SI² checks each item against the tables and columns of the book
(the fraud canonical data). Items it cannot find are gaps:

* Map to existing  - the data is there under another name (e.g. "Claim notes" -> claims.cause)
* Add new          - a data request to the data team: target table / column / type / source system, drafted by SI²
* Not needed       - the fraud type is out of scope for now
"""
from __future__ import annotations

import datetime as dt

from si2_common.gaps import Gap, rank, similarity, to_title, words

SOURCES = {  # where a P&C carrier usually gets it
    "IDENTITY": "Identity verification vendor (e.g. KYC service)", "VERIFICATION": "Identity verification vendor",
    "PAYROLL": "Premium audit / policy admin", "FINANCE": "Premium finance company feed", "VIN": "VIN history service",
    "MEDICAL": "Bill review system", "NOTES": "Claims system notes", "ACCESS": "Security / IAM logs",
    "RESERVE": "Claims system reserve history", "COMPLAINTS": "Complaints register", "COLLECTIONS": "Reinsurance accounting",
    "COMMUTATIONS": "Reinsurance accounting", "RECOVERY": "Claims system (salvage / subrogation)",
    "INSPECTION": "Field inspection vendor", "CONTACT": "Policy admin (party contact points)",
}


HAVE = {  # catalog wording -> where the book holds it
    "POLICY PERIOD": "policies.eff_date", "POLICY TRANSACTION": "policies", "CANCELLATION": "policies.status",
    "WEATHER": "cat_events", "CAT EVENT": "cat_events", "BILLING": "premium_payments", "LIMIT": "policies.limit",
    "DEDUCTIBLE": "policies.deductible", "CLAIM": "claims", "PAYMENT": "claim_payments", "INVOICE": "invoices",
    "VENDOR": "vendors", "EMPLOYEE": "employees", "TREATY": "treaties", "THEFT DATE": "claims.loss_date",
    "REPORT DATE": "claims.report_date", "ESTIMATE": "claims.reserve", "CAUSE CODE": "claims.cause",
}


TABLE_HINT = {"CONTACT": "parties", "PAYROLL": "policies", "CLASS": "policies", "FINANCE": "premium_payments",
              "COMMISSIONS": "agents", "RECOVERY": "claims", "VIN": "objects", "MEDICAL": "invoices",
              "COLLECTIONS": "treaties", "COMMUTATIONS": "treaties", "ACCESS": "employees", "COMPLAINTS": "claims",
              "INSPECTION": "invoices", "IDENTITY": "parties", "VERIFICATION": "parties"}


def _sing(text: str) -> set:
    return {w[:-1] if w.endswith("S") and len(w) > 3 else w for w in words(text)}


def have(item: str, d: dict) -> str:
    w = _sing(item)
    for k, v in HAVE.items():
        if set(k.split()) <= w:
            return v
    for t, df in d.items():
        if hasattr(df, "columns"):
            if _sing(t) & w and len(w) <= 2:
                return t
            for c in df.columns:
                cw = _sing(c)
                if cw and cw <= w | {"ID", "DATE", "AMOUNT"} and len(cw & w) >= max(1, len(w) - 1):
                    return f"{t}.{c}"
    return ""


def book_columns(d: dict) -> list[tuple[str, str, list]]:
    out = []
    for t, df in d.items():
        if hasattr(df, "columns"):
            out.append((t, t, [t]))
            out += [(f"{t}.{c}", f"{t}.{c}", [c]) for c in df.columns]
    return out


def needed(cat) -> dict[str, list[str]]:
    items = {}
    for r in cat.itertuples():
        for it in str(r.data_needed or "").split(","):
            it = it.strip()
            if it:
                items.setdefault(it, []).append(r.fraud_id)
    return items


def scan(cat, d: dict, ss) -> list[Gap]:
    cols = book_columns(d)
    mapped = getattr(ss, "fraud_data_map", {})
    requested = getattr(ss, "fraud_requests", {})
    ignored = getattr(ss, "fraud_gap_ignored", set())
    live = set(cat[cat.engine_rule == "Yes"].fraud_id)
    gaps = []
    for item, ids in needed(cat[cat.engine_rule != "Yes"]).items():   # live rules already have their data
        if item in mapped or item in requested or item in ignored or have(item, d):
            continue
        best = rank(item, cols, top=3, floor=0.2)
        w = set(words(item))
        table = next((v for k, v in TABLE_HINT.items() if k in w), None) or \
            next((t for t, _, _ in cols if "." not in t and similarity(item, t) > 0), "external")
        src = next((v for k, v in SOURCES.items() if k in w), "Source system to be confirmed")
        waiting = [i for i in ids if i not in live]
        gaps.append(Gap(gap_id="", kind="ELEMENT", side="DETECTION", system="Fraud catalog", ref=", ".join(ids[:5]),
                        name=item, context=f"needed by {len(ids)} fraud type(s)", occurrences=len(ids),
                        meaning=(f"{len(waiting)} of them have no live rule yet: " + ", ".join(waiting[:4])) if waiting else "",
                        risk="High" if waiting else "Medium", candidates=best,
                        proposal={"table": table, "column": "_".join(x.lower() for x in to_title(item).split()),
                                  "type": "date" if {"DATE", "DT"} & w else "text", "source": src,
                                  "description": f"{to_title(item)} for fraud detection ({', '.join(ids[:3])}). "
                                                 f"Requested from: {src}. (Drafted by SI² - edit if needed.)"}))
    for i, g in enumerate(gaps, 1):
        g.gap_id = f"F{i:03d}"
    return gaps


class Handler:
    def __init__(self, ss, d: dict, actor: str, log):
        self.ss, self.d, self.actor, self._log = ss, d, actor, log
        for a, v in (("fraud_data_map", {}), ("fraud_requests", {}), ("fraud_gap_ignored", set())):
            if not hasattr(ss, a):
                setattr(ss, a, v)

    def map_options(self, g):
        first = [(k, f"{l}  ({int(s * 100)}% match)") for k, l, s in g.candidates]
        keys = {k for k, _ in first}
        return first + [(k, l) for k, l, _ in book_columns(self.d) if k not in keys]

    def proposal_fields(self, g):
        tables = [t for t, df in self.d.items() if hasattr(df, "columns")] + ["external"]
        return [("table", "Target table", tables), ("column", "New column", None),
                ("type", "Type", ["text", "date", "amount", "code", "number"]), ("source", "Get it from", None),
                ("description", "Business description", None)]

    def map_existing(self, g, key):
        self.ss.fraud_data_map[g.name] = key
        self._log(self.actor, "Fraud data mapped (Canonical Gaps)", f"{g.name} → {key}")
        return f"'{g.name}' is {key} in the book; {g.ref} can use it."

    def add_new(self, g, p):
        if not p.get("column", "").strip():
            raise ValueError("Name the new column.")
        self.ss.fraud_requests[g.name] = {**p, "fraud_types": g.ref, "status": "Requested from the data team",
                                          "by": self.actor, "at": dt.datetime.now().strftime("%Y-%m-%d %H:%M")}
        self._log(self.actor, "Fraud data requested (Canonical Gaps)", f"{g.name} → {p['table']}.{p['column']} from {p['source']}")
        return f"Data request for {p['table']}.{p['column']} ('{g.name}') sent to the data team; it unlocks {g.ref}."

    def not_needed(self, g, reason):
        self.ss.fraud_gap_ignored.add(g.name)
        self._log(self.actor, "Fraud data not needed (Canonical Gaps)", f"{g.name}: {reason}")
        return f"'{g.name}' marked not needed ({reason})."
