"""Field catalog: layouts, aliases and pick lists for each bureau spec.

The catalog JSON is produced by `specparse` from the WCIO PDFs. This module adds what an SME
needs on top: record keys and names, generated aliases, NCCI state codes, a confidence score for
each parsed pick list, and a layout QA (gaps / overlaps per record).
"""
from __future__ import annotations

import collections
import json
import re
from functools import lru_cache
from pathlib import Path

import pandas as pd

DATA = Path(__file__).parent / "data"

SPEC_INFO = {
    "WCSTAT": {"title": "Unit Statistical Reporting", "record_length": 250, "frequency": "Per unit report level"},
    "WCPOLS": {"title": "Policy Reporting", "record_length": 300, "frequency": "Per policy transaction"},
    "WCIND": {"title": "Indemnity Data Call", "record_length": 300, "frequency": "Quarterly"},
    "WCMED": {"title": "Medical Data Call", "record_length": 350, "frequency": "Quarterly"},
}

LINES_OF_BUSINESS = {
    "Workers Compensation": ["WCSTAT", "WCPOLS", "WCIND", "WCMED"],
    "Commercial Auto": [],
    "General Liability": [],
    "Homeowners": [],
}

# NCCI state codes used in WCIO specifications (two-digit numeric).
NCCI_STATE = {
    "AL": "01", "AZ": "02", "AR": "03", "CA": "04", "CO": "05", "CT": "06", "DE": "07", "DC": "08", "FL": "09",
    "GA": "10", "ID": "11", "IL": "12", "IN": "13", "IA": "14", "KS": "15", "KY": "16", "LA": "17", "ME": "18",
    "MD": "19", "MA": "20", "MI": "21", "MN": "22", "MS": "23", "MO": "24", "MT": "25", "NE": "26", "NV": "27",
    "NH": "28", "NJ": "29", "NM": "30", "NY": "31", "NC": "32", "ND": "33", "OH": "34", "OK": "35", "OR": "36",
    "PA": "37", "RI": "38", "SC": "39", "SD": "40", "TN": "41", "TX": "42", "UT": "43", "VT": "44", "VA": "45",
    "WA": "46", "WV": "47", "WI": "48", "WY": "49", "HI": "52", "AK": "54",
}
STATE_FROM_CODE = {v: k for k, v in NCCI_STATE.items()}

# Record keys used for the four files this workbench generates.
RECORD_NAMES = {
    "WCSTAT": {"0": "Link Data", "1": "Header", "2": "Name", "3": "Address", "4": "Exposure", "5": "Loss",
               "6": "Unit Total", "9": "File Control"},
    "WCPOLS": {"00": "Link Data", "01": "Header", "02": "Name", "03": "Address", "04": "State Premium",
               "05": "Exposure"},
    "WCIND": {"FILE CONTROL RECORD": "File Control (03)", "TRANSACTIONAL RECORD": "Transactional (01)",
              "QUARTERLY RECORD": "Quarterly (02)", "KEY FIELD CHANGE RECORD": "Key Field Change (04)"},
    "WCMED": {"FILE CONTROL RECORD": "File Control (SUBCTRLREC)", "MEDICAL DATA CALL RECORD": "Medical Data Call",
              "KEY FIELD CHANGE RECORD": "Key Field Change"},
}

# Pick lists whose PDF tables wrap badly; curated from the same spec pages so the SME sees clean values.
CURATED_CODES = {
    ("WCIND", "TRANSACTIONAL RECORD", "BENEFIT TYPE CODE"): [
        ("01", "Death Benefits"), ("02", "Permanent Total Disability Benefits"),
        ("03", "Scheduled Permanent Partial Disability Benefits"),
        ("04", "Unscheduled Permanent Partial Disability Benefits"), ("05", "Temporary Total Disability Benefits"),
        ("09", "Disfigurement Benefits"), ("11", "Temporary Partial Disability Benefits"),
        ("12", "Employers Liability"), ("15", "Supplemental Benefits"), ("20", "Claimant Legal Amount Paid"),
        ("30", "Indemnity Recovery Reimbursement Amount—Third Party Actions"),
        ("31", "Indemnity Recovery Reimbursement Amount—State Administered Funds"),
        ("48", "Penalties, Assessments, Interest"), ("49", "Indemnity and Medical Combined"),
        ("50", "Other Specified Indemnity Benefits"), ("60", "Vocational Rehabilitation—Evaluation Benefit Costs"),
        ("61", "Vocational Rehabilitation—Education Benefit Costs"),
        ("62", "Vocational Rehabilitation—Maintenance Benefit Costs"),
        ("63", "Vocational Rehabilitation—Payment NOC"), ("79", "Lump Sum Including Multiple Indemnity"),
        ("99", "Other Indemnity Benefits Not Otherwise Specified")],
    ("WCIND", "TRANSACTIONAL RECORD", "LUMP SUM INDICATOR"): [
        ("Y", "Claim has been settled by an agreement to a lump sum amount"),
        ("N", "Claim has not been settled by an agreement to a lump sum amount")],
    ("WCMED", "MEDICAL DATA CALL RECORD", "TRANSACTION CODE"): [
        ("01", "Original"), ("02", "Cancellation"), ("03", "Replacement")],
    ("WCMED", "MEDICAL DATA CALL RECORD", "CLAIMANT GENDER CODE"): [("1", "Male"), ("2", "Female"), ("3", "Other")],
    ("WCIND", "QUARTERLY RECORD", "ATTORNEY OR AUTHORIZED REPRESENTATIVE INDICATOR"): [
        ("Y", "Claimant is represented by an attorney or authorized representative"),
        ("N", "Claimant is not represented by an attorney or authorized representative")],
    ("WCIND", "QUARTERLY RECORD", "CLAIMANT GENDER CODE"): [("1", "Male"), ("2", "Female"), ("3", "Other")],
}

ABBREV = {
    "NUMBER": ["NO", "NUM", "NBR", "NUMBER"], "IDENTIFIER": ["ID", "IDENT"], "DATE": ["DT", "DATE"],
    "AMOUNT": ["AMT", "AMOUNT"], "CODE": ["CD", "CODE"], "POLICY": ["POL", "POLICY"], "CLAIM": ["CLM", "CLAIM"],
    "EFFECTIVE": ["EFF"], "EXPIRATION": ["EXP"], "CLASSIFICATION": ["CLASS", "CLS"], "INCURRED": ["INC", "INCD"],
    "INDEMNITY": ["IND", "INDEM"], "MEDICAL": ["MED"], "PREMIUM": ["PREM"], "EXPOSURE": ["EXPO"],
    "STATE": ["ST", "STATE"], "INSURED": ["INSD", "INS"], "ADDRESS": ["ADDR"], "TRANSACTION": ["TRAN", "TRANS", "TXN"],
    "MODIFICATION": ["MOD"], "EXPERIENCE": ["EXPER", "XMOD"], "FEDERAL EMPLOYER IDENTIFICATION NUMBER": ["FEIN", "EIN", "TAX ID"],
    "ALLOCATED LOSS ADJUSTMENT EXPENSE": ["ALAE"], "ACCIDENT": ["ACC", "LOSS"], "CARRIER": ["CARR", "CO"],
    "PAID": ["PD", "PAID"], "WEEKLY WAGE": ["AWW"],
}


def _norm(s: str) -> str:
    return re.sub(r"[^A-Z0-9 ]", " ", s.upper()).strip()


def make_aliases(name: str) -> list[str]:
    """Generate the aliases a source system commonly uses for a bureau field name."""
    base = _norm(name)
    words = [w for w in base.split() if w not in {"OF", "THE", "AND", "OR", "FOR", "TO", "BY"}]
    out = {"_".join(words), "".join(w[0] for w in words) if len(words) > 1 else words[0] if words else ""}
    for phrase, alts in ABBREV.items():
        if phrase in base:
            for a in alts:
                out.add(re.sub(r"\s+", "_", base.replace(phrase, a)))
    short = []
    for w in words:
        alts = ABBREV.get(w)
        short.append(alts[0] if alts else w)
    out.add("_".join(short))
    return sorted(a for a in out if a and a != "_")[:8]


def record_key(f: dict) -> str:
    return f["page_record"] if f["spec"] in ("WCSTAT", "WCPOLS") else f["record_title"]


BORROW = {"TYPE OF SETTLEMENT CODE": "TYPE OF SETTLEMENT CODE", "ACT—LOSS CONDITION CODE": "LOSS COVERAGE ACT CODE"}
DEC = re.compile(r"assumed decimal(?: point)? between\s+positions\s+(\d+)\s*(?:and|-|–)\s*(\d+)", re.I)


def _decimals(f: dict) -> int:
    """Implied decimals from the spec text ("assumed decimal point between positions 89 and 90")."""
    d = f.get("description", "").lower()
    if "payroll" in d and "whole dollar" in d:
        return 0          # payroll exposure is whole dollars; decimals apply only to non-payroll bases
    m = DEC.search(f.get("description", ""))
    if m:
        return max(0, f["end"] - int(m.group(1)))
    return int(f.get("implied_decimals", 0) or 0)


def _codes_confidence(codes: list[dict], length: int) -> float:
    if not codes:
        return 0.0
    ok = sum(1 for c in codes if len(c["code"]) <= max(length, 2) and not re.search(r"\b\d{2}\s+[A-Z][a-z]", c["description"]))
    return round(ok / len(codes), 2)


CONNECT = re.compile(r"(\bBY|\bOF|\bAND|\bOR|\bFOR|\bTO|\bTHE|-|–|/)$")
CONT = re.compile(r"^([A-Z0-9][A-Z0-9 \-–/&()'’,.]+?)(?=\s+[A-Z][a-z]|\s*$)")


def _full_name(f: dict) -> tuple[str, str]:
    """Rejoin field titles that wrap onto the next line of the PDF."""
    name, desc = re.sub(r"\s+\d+$", "", f["name"].upper().strip()), f.get("description", "")
    m = CONT.match(desc)
    if m and len(m.group(1)) > 3 and not name.startswith("RESERVED") and "RECORD" not in m.group(1) \
            and "ENDORSEMENT" not in m.group(1):
        seg = m.group(1).strip()
        words = seg.split()
        if CONNECT.search(name) or (2 <= len(words) <= 4 and not seg.startswith(("N/A", "NOT ", "OPTIONAL", "FOR ", "NCCI"))
                                    and not any(w in name for w in words)):
            return re.sub(r"\s+\d+\b", "", f"{name} {seg}").strip(), desc[m.end():].strip()
    return name, desc


@lru_cache(maxsize=1)
def load() -> pd.DataFrame:
    raw = json.loads((DATA / "catalog.json").read_text())
    rows = []
    for f in raw:
        f = dict(f)
        f["name"], f["description"] = _full_name(f)
        key = record_key(f)
        codes = [dict(c, na_states="" if re.search(rf"\b{re.escape(c['code'])} - ", c["description"]) else c["na_states"])
                 for c in f.get("codes", [])]
        cur = CURATED_CODES.get((f["spec"], key, f["name"]))
        source = "PDF"
        if cur:
            codes = [{"code": c, "description": d, "na_states": "", "reserved": False} for c, d in cur]
            source = "PDF + SME curated"
        rows.append({
            "spec": f["spec"], "record_key": key,
            "record_name": RECORD_NAMES.get(f["spec"], {}).get(key, f["record_title"].title()),
            "field_no": f["field_no"], "name": f["name"], "class": f["class"], "start": f["start"],
            "end": f["end"], "length": f["length"], "format": f.get("format", ""),
            "implied_decimals": _decimals(f), "signed": f.get("signed", False),
            "constant": f.get("constant", ""), "not_applicable": f.get("not_applicable", ""),
            "optional": f.get("optional", ""), "description": f.get("description", ""),
            "codes": codes, "pick_list_source": source if codes else "",
            "pick_list_confidence": 1.0 if cur else _codes_confidence(codes, f["length"]),
            "aliases": make_aliases(f["name"]),
        })
    df = pd.DataFrame(rows)
    df["field_id"] = df.spec + "|" + df.record_key + "|" + df.start.astype(str)
    # A one-value "pick list" on a long free-format field is description text, not a code list.
    junk = df.codes.apply(len).eq(1) & (df.length > 2) & df.apply(
        lambda r: bool(r.codes) and len(r.codes[0]["code"]) != r.length, axis=1)
    df.loc[junk, "codes"] = df.loc[junk, "codes"].apply(lambda _: [])
    df.loc[junk, ["pick_list_source", "pick_list_confidence"]] = ["", 0.0]
    # Borrow a clean pick list from WCSTAT for the same field name when the parsed one is weak.
    good = {r["name"]: r["codes"] for _, r in df[(df.spec == "WCSTAT") & (df.pick_list_confidence >= 0.9)].iterrows()
            if r["codes"]}
    weak = df.spec.isin(["WCIND", "WCMED"]) & df.name.isin(BORROW) & df.name.map(lambda n: BORROW.get(n) in good)
    df.loc[weak, "codes"] = df.loc[weak, "name"].map(lambda n: good[BORROW[n]])
    df.loc[weak, "pick_list_source"] = "Borrowed from WCSTAT (SME verify)"
    df.loc[weak, "pick_list_confidence"] = 0.9
    return df


def record_fields(spec: str, key: str) -> pd.DataFrame:
    df = load()
    return df[(df.spec == spec) & (df.record_key == key)].sort_values("start").reset_index(drop=True)


def records_for(spec: str) -> pd.DataFrame:
    df = load()
    g = df[df.spec == spec].groupby("record_key", sort=False)
    out = g.agg(record_name=("record_name", "first"), fields=("name", "size"), last_position=("end", "max"),
                pick_lists=("codes", lambda s: sum(1 for c in s if c))).reset_index()
    return out


def layout_qa(spec: str) -> pd.DataFrame:
    """Gaps and overlaps per record, so the SME knows exactly what to review."""
    df = load()
    rec_len = SPEC_INFO[spec]["record_length"]
    out = []
    for key, g in df[df.spec == spec].groupby("record_key", sort=False):
        g = g.sort_values("start")
        pos, issues = 1, []
        for _, f in g.iterrows():
            if f.start > pos:
                issues.append(f"gap {pos}-{f.start - 1}")
            elif f.start < pos and not (f["name"] == "LINK DATA" or f.start == 1):
                issues.append(f"overlap at {f.start}")
            pos = max(pos, f.end + 1)
        if key not in ("0", "00") and pos - 1 < rec_len - 1:
            issues.append(f"ends at {pos - 1} of {rec_len}")
        out.append({"record_key": key, "record_name": g.record_name.iloc[0], "fields": len(g),
                    "status": "Complete" if not issues else "Review", "issues": "; ".join(issues)})
    return pd.DataFrame(out)


def pick_list(field_row) -> dict[str, str]:
    return {c["code"]: c["description"] for c in field_row["codes"]}


def summary() -> pd.DataFrame:
    df = load()
    rows = []
    for spec, info in SPEC_INFO.items():
        d = df[df.spec == spec]
        rows.append({"spec": spec, "title": info["title"], "records": d.record_key.nunique(), "fields": len(d),
                     "pick_lists": int((d.codes.str.len() > 0).sum()),
                     "pick_list_values": int(d.codes.str.len().sum()),
                     "date_formats": int((d.format != "").sum())})
    return pd.DataFrame(rows)
