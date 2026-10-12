"""Canonical Gaps: shared logic for every SI² app (bureau reporting, migration, ...).

A *gap* is something a source or destination uses that the canonical model does not
have yet: an element, a pick list, a pick-list code, or a destination code. Each app
supplies an adapter that finds its gaps and applies the SME's decision; this module
supplies what is common: naming, matching, drafting a complete proposal, and the
Gap record itself. Nothing here talks to a database or to Streamlit.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

KINDS = {
    "ELEMENT": "Missing element",
    "PICKLIST": "Missing pick list",
    "CODE": "Missing pick-list code",
    "DEST_ELEMENT": "Destination field without canonical element",
    "DEST_CODE": "Missing destination code",
}

ABBR = {
    "ACCT": "ACCOUNT", "ADDR": "ADDRESS", "AGT": "AGENT", "AGCY": "AGENCY", "AMT": "AMOUNT", "AUTH": "AUTHOR",
    "CD": "CODE", "CL": "CLAIM", "CLM": "CLAIM", "CNT": "COUNT", "CO": "COMPANY", "COV": "COVERAGE", "CNTY": "COUNTY",
    "DED": "DEDUCTIBLE", "DESC": "DESCRIPTION", "DISC": "DISCOUNT", "DT": "DATE", "EFF": "EFFECTIVE",
    "EXP": "EXPIRATION", "IND": "INDICATOR", "INS": "INSURED", "LOB": "LINE OF BUSINESS", "NBR": "NUMBER",
    "NM": "NAME", "NO": "NUMBER", "NUM": "NUMBER", "OS": "OUTSTANDING", "PD": "PAID", "PMT": "PAYMENT",
    "POL": "POLICY", "PREM": "PREMIUM", "QTY": "QUANTITY", "RSV": "RESERVE", "ST": "STATE", "STAT": "STATUS",
    "TERR": "TERRITORY", "TXN": "TRANSACTION", "TYP": "TYPE", "VEH": "VEHICLE", "YR": "YEAR",
}
STOP = {"THE", "OF", "AND", "A", "AN", "TO", "FOR", "IN"}


def words(name: str) -> list[str]:
    """'TelematicsInd' / 'CL-OS-RSV' / 'agt_comment' -> business words, abbreviations expanded."""
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", str(name or ""))
    s = re.sub(r"[^A-Za-z0-9]+", " ", s).upper().split()
    out = []
    for w in s:
        out.extend(ABBR.get(w, w).split())
    return [w for w in out if w not in STOP]


def to_code(name: str, max_len: int = 30) -> str:
    """Canonical code by naming standard: UPPER_SNAKE, abbreviations expanded."""
    return "_".join(words(name))[:max_len].strip("_") or "NEW_ITEM"


def to_title(name: str) -> str:
    return " ".join(w.capitalize() for w in words(name)) or str(name)


def to_pascal(name: str) -> str:
    return "".join(w.capitalize() for w in words(name)) or str(name)


def similarity(a: str | list[str], b: str | list[str]) -> float:
    """Token overlap (0..1) after normalisation."""
    A = set(words(a) if isinstance(a, str) else a)
    B = set(words(b) if isinstance(b, str) else b)
    if not A or not B:
        return 0.0
    return len(A & B) / len(A | B)


def rank(name: str, candidates: list[tuple[str, str, list[str]]], top: int = 3, floor: float = 0.15):
    """candidates: (key, label, [names / synonyms]) -> best (key, label, score) list."""
    scored = []
    for key, label, names in candidates:
        s = max((similarity(name, n) for n in [key, label, *names] if n), default=0.0)
        if s >= floor:
            scored.append((key, label, round(s, 2)))
    scored.sort(key=lambda x: -x[2])
    return scored[:top]


def infer_type(samples: list[str]) -> str:
    vals = [str(v).strip() for v in samples if str(v).strip()]
    if not vals:
        return "TEXT"
    if all(v.upper() in ("Y", "N", "YES", "NO", "TRUE", "FALSE") for v in vals):
        return "CODE"
    if all(re.fullmatch(r"\d{4}-\d{2}-\d{2}", v) or re.fullmatch(r"\d{8}", v) for v in vals):
        return "DATE"
    if all(re.fullmatch(r"-?\d+(\.\d+)?", v) for v in vals):
        return "DECIMAL" if any("." in v for v in vals) else "NUMBER"
    distinct = set(vals)
    if len(distinct) <= 12 and all(len(v) <= 20 for v in distinct) and len(vals) >= 2 * len(distinct):
        return "CODE"
    return "TEXT"


def draft_description(name: str, data_type: str, samples: list[str] | None = None,
                      source: str = "", values: dict | None = None) -> str:
    """Business description drafted from the evidence; the SME edits it if needed."""
    title = to_title(name)
    ws = words(name)
    if data_type == "CODE" and set(values or {}) <= {"Y", "N"} and values:
        body = f"Indicates whether {title.lower().replace(' indicator', '')} applies (Y / N)."
    elif data_type == "CODE":
        opts = ", ".join(f"{k} = {v}" for k, v in list((values or {}).items())[:6])
        body = f"Coded value for {title.lower()}" + (f" ({opts})." if opts else ".")
    elif data_type == "DATE":
        body = f"Date of {title.lower().replace(' date', '')}."
    elif data_type in ("AMOUNT", "DECIMAL"):
        body = f"Amount of {title.lower().replace(' amount', '')} in dollars and cents."
    elif "NAME" in ws:
        body = f"Name of the {title.lower().replace(' name', '')}."
    elif "COMMENT" in ws or "NOTE" in ws or "TEXT" in ws:
        body = f"Free-text {title.lower()}; not used in rating or reporting."
    else:
        body = f"{title}."
    ex = f" Examples: {', '.join(map(str, (samples or [])[:3]))}." if samples else ""
    src = f" First seen in {source}." if source else ""
    return f"{body}{ex}{src} (Drafted by SI² - edit if needed.)"


@dataclass
class Gap:
    gap_id: str
    kind: str                      # key of KINDS
    side: str                      # SOURCE | DESTINATION
    system: str                    # Guidewire, DuckCreek, ISO layout, INSURE/400 ...
    ref: str                       # where it was found (attribute / field / value)
    name: str                      # the thing that is missing (element name or code value)
    context: str = ""              # pick list / element / layout it belongs to
    meaning: str = ""              # description of a value, when known
    data_type: str = ""
    samples: list = field(default_factory=list)
    values: dict = field(default_factory=dict)          # observed code -> meaning
    occurrences: int = 0
    risk: str = "Medium"
    candidates: list = field(default_factory=list)      # (key, label, score)
    proposal: dict = field(default_factory=dict)        # complete draft for "Add new"
    actions: tuple = ("map", "add", "skip")             # which buttons apply

    @property
    def kind_label(self) -> str:
        return KINDS.get(self.kind, self.kind)

    @property
    def best(self) -> str:
        return f"{self.candidates[0][1]} ({int(self.candidates[0][2] * 100)}%)" if self.candidates else ""

    def row(self) -> dict:
        return {"gap": self.gap_id, "type": self.kind_label, "side": self.side, "system": self.system,
                "found in": self.ref, "missing": self.name, "belongs to": self.context, "risk": self.risk,
                "seen": self.occurrences, "closest existing": self.best,
                "proposed new": self.proposal.get("code") or self.proposal.get("field", "")}
