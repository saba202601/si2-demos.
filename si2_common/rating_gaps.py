"""Canonical Gaps for the Rating Engine.

The rating tables (state relativities, use, limits, deductibles ...) are the canonical
model a quote is rated against. A quote coming in from an agency upload or a comparative
rater can carry a value no table has a factor for: a new state, "Rideshare" use, a 500/1000
limit, a $2,000 deductible. Each one is a gap:

* Map to existing - "rate as": the value uses an existing entry's factor (e.g. AL rated as GA)
* Add new         - a new factor, drafted by SI² (neighbouring state, increased-limits curve,
                    deductible curve); it is flagged until an actuary confirms it against the
                    filed rates
* Not needed      - the value is not written: those quotes are declined with a reason
"""
from __future__ import annotations

import datetime as dt
import math
import re

import pandas as pd

from .gaps import Gap, rank

NEIGHBOURS = {"AL": ["GA", "TX"], "SC": ["NC", "GA"], "TN": ["GA", "NC"], "VA": ["NC"], "PA": ["NY", "OH"],
              "NJ": ["NY"], "MI": ["OH"], "IN": ["OH"], "KY": ["OH"], "LA": ["TX"], "OK": ["TX"], "MS": ["GA"]}
LOADS = {"Rideshare": ("Business", 1.20, "Business use + 20% for transportation network driving; most carriers "
                                          "write this only with a rideshare endorsement"),
         "Delivery": ("Business", 1.15, "Business use + 15% for commercial delivery")}


def _num(key) -> float | None:
    m = re.match(r"\s*\$?(\d[\d,]*)", str(key))
    return float(m.group(1).replace(",", "")) if m else None


def draft_factor(value, table: dict, kind: str) -> tuple[float, str]:
    """Expert first draft of a factor for a value the table does not have."""
    if kind == "state":
        for n in NEIGHBOURS.get(str(value), []):
            if n in table:
                return table[n], f"Neighbouring state {n} relativity"
        return 1.00, "Countrywide average (1.000); no neighbouring state on file"
    if kind == "use" and value in LOADS:
        base, load, why = LOADS[value]
        if base in table:
            return round(table[base] * load, 3), why
    x = _num(value)
    pts = sorted((_num(k), f) for k, f in table.items() if _num(k))
    if x and len(pts) >= 2:
        (x1, f1), (x2, f2) = (pts[-2], pts[-1]) if x > pts[-1][0] else (pts[0], pts[1]) if x < pts[0][0] else \
            next(((a, b) for a, b in zip(pts, pts[1:]) if a[0] <= x <= b[0]))
        slope = (math.log(f2) - math.log(f1)) / (math.log(x2) - math.log(x1))
        f = math.exp(math.log(f1) + slope * (math.log(x) - math.log(x1)))
        curve = "increased-limits" if kind == "limit" else "deductible"
        return round(f, 3), f"Log-linear {curve} curve through {x1:g} and {x2:g}"
    return 1.00, "No basis on file; neutral 1.000"


def _key(value, table: dict):
    """Keep the table's key type (deductibles are numbers, limits are text)."""
    if table and all(isinstance(k, int) for k in table):
        n = _num(value)
        return int(n) if n is not None else value
    return str(value).strip()


def scan(quotes: pd.DataFrame, spec: dict, ss) -> list[Gap]:
    """spec: quote column -> (table key, label, factor dict, kind)."""
    gaps: list[Gap] = []
    declined = getattr(ss, "rate_declined", set())
    for col, (tkey, label, table, kind) in spec.items():
        if col not in quotes:
            continue
        missing = quotes.loc[~quotes[col].map(lambda v: _key(v, table) in table), col]
        for value, n in missing.value_counts().items():
            if f"{tkey}:{value}" in declined:
                continue
            factor, basis = draft_factor(_key(value, table), table, kind)
            cands = rank(str(value), [(str(k), f"{k} · {f}", []) for k, f in table.items()])
            if kind == "state":
                cands = [(nb, f"{nb} · {table[nb]} (neighbouring state)", 0.6) for nb in NEIGHBOURS.get(value, []) if nb in table] or cands
            elif kind == "use" and value in LOADS and LOADS[value][0] in table:
                cands = [(LOADS[value][0], f"{LOADS[value][0]} · {table[LOADS[value][0]]}", 0.5)]
            elif _num(value):
                near = sorted(table, key=lambda k: abs((_num(k) or 0) - _num(value)))[:2]
                cands = [(str(k), f"{k} · {table[k]} (nearest)", 0.4) for k in near]
            quote_ids = quotes.loc[quotes[col] == value, "quote"].tolist()
            gaps.append(Gap(gap_id="", kind="FACTOR", side="QUOTE", system="Incoming quotes", ref=f"{col} = {value}",
                            name=str(value), context=label, meaning=f"Quotes {', '.join(quote_ids[:4])}"
                            + (" ..." if len(quote_ids) > 4 else ""), occurrences=int(n), risk="High",
                            values={str(k): f for k, f in table.items()}, candidates=cands,
                            proposal={"value": str(value), "factor": f"{factor:.3f}", "basis": basis,
                                      "description": f"{basis}. SI² draft: an actuary / SME must confirm it against "
                                                     f"the filed rates before it is used on a policy."}))
    for i, g in enumerate(gaps, 1):
        g.gap_id = f"F{i:03d}"
    return gaps


def apply_extensions(spec_tables: dict, ss) -> None:
    """Merge SME-approved factors into the live factor dicts (called on every run)."""
    for tkey, ext in getattr(ss, "factor_ext", {}).items():
        if tkey in spec_tables:
            for k, row in ext.items():
                spec_tables[tkey][k] = row["factor"]


PENDING = "Pending actuary approval"


class Handler:
    def __init__(self, ss, spec: dict, actor: str, approval=None):
        """approval(kind, ref, summary, payload) files a two-person approval request (raises ValueError to refuse)."""
        self.ss, self.spec, self.actor, self.approval = ss, spec, actor, approval
        for attr, default in (("factor_ext", {}), ("rate_declined", set()), ("rating_audit", [])):
            if not hasattr(ss, attr):
                setattr(ss, attr, default)

    def _entry(self, g: Gap):
        col = g.ref.split(" = ")[0]
        return self.spec[col]

    def _log(self, event, detail):
        self.ss.rating_audit.append({"time": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "by": self.actor,
                                     "event": event, "detail": detail})

    def map_options(self, g: Gap):
        _, _, table, _ = self._entry(g)
        first = [(k, f"{l}") for k, l, _ in g.candidates]
        keys = {k for k, _ in first}
        return first + [(str(k), f"{k} · {f}") for k, f in table.items() if str(k) not in keys]

    def proposal_fields(self, g: Gap):
        return [("value", "Value", None), ("factor", "Factor (draft)", None), ("description", "Basis / note", None)]

    def _add(self, g: Gap, factor: float, basis: str, status: str):
        tkey, label, table, _ = self._entry(g)
        k = _key(g.name, table)
        self.ss.factor_ext.setdefault(tkey, {})[k] = {"factor": factor, "basis": basis, "status": status,
                                                    "by": self.actor, "effective": dt.date.today().isoformat()}
        return tkey, label, k

    def map_existing(self, g: Gap, key: str) -> str:
        tkey, label, table, _ = self._entry(g)
        src = _key(key, table)
        f = table[src]
        self._add(g, f, f"Rated as {src}", "SME approved")
        self._log("Factor mapped (Canonical Gaps)", f"{label} {g.name} rated as {src} ({f})")
        return f"{label} {g.name} is rated as {src} (factor {f}). {g.occurrences} quote(s) can now be rated."

    def add_new(self, g: Gap, p: dict) -> str:
        try:
            f = float(p["factor"])
        except (TypeError, ValueError):
            raise ValueError(f"'{p.get('factor')}' is not a number.")
        if not 0.1 <= f <= 10:
            raise ValueError(f"A factor of {f} is outside the 0.1 - 10 range; check it.")
        tkey, label, table, _ = self._entry(g)
        k = _key(g.name, table)
        if self.approval:
            self.approval("New rating factor", f"{tkey}:{k}", f"{label} {k} = {f:.3f} ({p.get('basis', '')})",
                          {"tkey": tkey, "key": k, "factor": round(f, 3), "label": label})
        self._add(g, round(f, 3), p.get("description") or p.get("basis", ""), PENDING if self.approval else "Draft - actuary to confirm")
        self._log("Factor added (Canonical Gaps)", f"{label} {k} = {f} ({p.get('basis', '')})")
        return (f"New {label} factor {k} = {f:.3f} added and sent to an actuary for approval. Until then, "
                f"{g.occurrences} quote(s) get an indication only." if self.approval else
                f"New {label} factor {k} = {f:.3f} added as a draft (actuary to confirm against the filed rates). "
                f"{g.occurrences} quote(s) can now be rated.")

    def not_needed(self, g: Gap, reason: str) -> str:
        tkey, label, _, _ = self._entry(g)
        self.ss.rate_declined.add(f"{tkey}:{g.name}")
        self._log("Value not written (Canonical Gaps)", f"{label} {g.name}: {reason}")
        return f"{label} {g.name} is not written: those quotes are declined ({reason})."


def decide_factor(ss, request: dict) -> str:
    """Apply an actuary's decision on a new factor."""
    p = request["payload"]
    ext = getattr(ss, "factor_ext", {}).get(p["tkey"], {})
    if p["key"] not in ext:
        return "The factor was already removed."
    if request["status"] == "Approved":
        ext[p["key"]]["status"] = "Approved" + (f" · {request['note']}" if request.get("note") else "")
        ext[p["key"]]["approved_by"] = request["checker"]
        return f"{p['label']} {p['key']} = {p['factor']} approved by {request['checker']}; quotes using it can be bound."
    ext.pop(p["key"])
    return f"{p['label']} {p['key']} rejected by {request['checker']}; it is back on the gaps list."


def declined_reason(quote: dict, spec: dict, ss) -> str:
    declined = getattr(ss, "rate_declined", set())
    for col, (tkey, label, _, _) in spec.items():
        if f"{tkey}:{quote.get(col)}" in declined:
            return f"Not written: {label} {quote[col]}"
    return ""


def missing_reason(quote: dict, spec: dict) -> str:
    out = [f"{label} {quote[col]}" for col, (_, label, table, _) in spec.items()
           if col in quote and _key(quote[col], table) not in table]
    return ("No factor for " + ", ".join(out)) if out else ""
