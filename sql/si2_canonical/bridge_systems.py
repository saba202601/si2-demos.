"""Synthetic systems for the SI² Data Bridge demo (all names, layouts and values are illustrative).

    LEGACY_PAS   a legacy policy admin extract: short column names, YYYYMMDD dates, one-letter codes, implied decimals
    POLICYCLOUD  a modern policy system: readable field names and its own code values
    ISO_STAT     an ISO-style statistical premium record: fixed width, values from SI2Canonical's ISO bureau codes

Each system says which canonical element each of its fields is, and how its values translate to canonical options.
Those mappings are registered in SI2Canonical as aliases tagged with the system (two-person approval), and the bridge
reads them back from there: a new system is mapped once, to the canonical model, and reaches every other system.
"""
from __future__ import annotations

import datetime as dt
import random
from dataclasses import dataclass, field


@dataclass
class Field:
    name: str
    element: str | None            # canonical element (None: not mapped yet - the bridge reports it)
    fmt: str = "text"              # how the system writes the value (see bridge.parse / bridge.emit)
    width: int = 0                 # fixed-width layouts only
    values: dict = field(default_factory=dict)   # system value -> canonical option code


@dataclass
class System:
    code: str
    name: str
    role: str                      # SOURCE or DESTINATION
    kind: str                      # CSV or FIXED
    value_source: str              # SYNONYM: the system's own values; BUREAU:ISO: the bureau codes in SI2Canonical
    fields: list
    note: str = ""

    def field(self, name):
        return next((f for f in self.fields if f.name == name), None)


LOB_LEGACY = {"H": "HO", "B": "BP"}
FORM_LEGACY = {"3": "HO3", "4": "HO4", "5": "HO5", "6": "HO6", "BS": "STD", "BP": "SPC"}
CONST_LEGACY = {"F": "FR", "J": "JM", "N": "NC", "M": "MAS", "R": "FRS", "V": "VEN"}
DED_LEGACY = {"250": "D250", "500": "D500", "1000": "D1000", "2500": "D2500", "5000": "D5000", "1%": "P1", "2%": "P2"}
TRN_LEGACY = {"N": "NB", "R": "RN", "E": "EN", "X": "CN"}

LEGACY_PAS = System("LEGACY_PAS", "Legacy policy admin extract", "SOURCE", "CSV", "SYNONYM", [
    Field("POL_NO", "POLICY_NUMBER", "upper"),
    Field("LOB_CD", "LINE_OF_BUSINESS", "code", values=LOB_LEGACY),
    Field("FORM_CD", "POLICY_FORM", "code", values=FORM_LEGACY),
    Field("EFF_DT", "POLICY_EFFECTIVE_DATE", "date:%Y%m%d"),
    Field("EXP_DT", "POLICY_EXPIRATION_DATE", "date:%Y%m%d"),
    Field("INS_NM", "INSURED_NAME", "name_last_first"),
    Field("RSK_ST", "STATE", "code"),
    Field("ZIP5", "ZIP_CODE", "text"),
    Field("CONST_CD", "CONSTRUCTION", "code", values=CONST_LEGACY),
    Field("PROT_CL", "PROTECTION_CLASS", "pad2"),
    Field("YR_BLT", "YEAR_BUILT", "int"),
    Field("COV_A", "COVERAGE_A_LIMIT", "amount"),
    Field("DED_AMT", "DEDUCTIBLE", "code", values=DED_LEGACY),
    Field("TRN_CD", "TRANSACTION_TYPE", "code", values=TRN_LEGACY),
    Field("WRT_PREM", "WRITTEN_PREMIUM", "implied2"),
    Field("AGT_CD", None, "text"),                       # nobody has said what this is yet: reported, not guessed
], note="Short column names, dates as YYYYMMDD, one-letter codes, premium with two implied decimals.")

POLICYCLOUD = System("POLICYCLOUD", "Modern policy system", "DESTINATION", "CSV", "SYNONYM", [
    Field("policyNumber", "POLICY_NUMBER"),
    Field("lineOfBusiness", "LINE_OF_BUSINESS", "code", values={"Homeowners": "HO", "Businessowners": "BP"}),
    Field("policyForm", "POLICY_FORM", "code", values={"HO-3": "HO3", "HO-4": "HO4", "HO-5": "HO5", "HO-6": "HO6",
                                                       "BOP-Standard": "STD", "BOP-Special": "SPC"}),
    Field("effectiveDate", "POLICY_EFFECTIVE_DATE", "date:%Y-%m-%d"),
    Field("expirationDate", "POLICY_EXPIRATION_DATE", "date:%Y-%m-%d"),
    Field("insuredName", "INSURED_NAME", "name_natural"),
    Field("riskState", "STATE", "code"),
    Field("postalCode", "ZIP_CODE"),
    Field("constructionType", "CONSTRUCTION", "code", values={"frame": "FR", "joistedMasonry": "JM", "nonCombustible": "NC",
                                                              "masonry": "MAS", "fireResistive": "FRS", "masonryVeneer": "VEN"}),
    Field("protectionClass", "PROTECTION_CLASS", "int"),
    Field("yearBuilt", "YEAR_BUILT", "int"),
    Field("dwellingLimit", "COVERAGE_A_LIMIT", "amount"),
    Field("deductible", "DEDUCTIBLE", "code", values={"USD_250": "D250", "USD_500": "D500", "USD_1000": "D1000", "USD_2500": "D2500",
                                                      "USD_5000": "D5000", "PCT_1": "P1", "PCT_2": "P2"}),
    Field("transactionType", "TRANSACTION_TYPE", "code", values={"NewBusiness": "NB", "Renewal": "RN", "Endorsement": "EN",
                                                                 "Cancellation": "CN"}),
    Field("writtenPremium", "WRITTEN_PREMIUM", "amount2"),
], note="Readable names, ISO dates, its own code values (frame, HO-3, NewBusiness).")

ISO_STAT = System("ISO_STAT", "ISO-style statistical premium record", "DESTINATION", "FIXED", "BUREAU:ISO", [
    Field("LINE", "LINE_OF_BUSINESS", "code", 2),
    Field("STATE", "STATE", "code", 2),
    Field("TRANSACTION", "TRANSACTION_TYPE", "code", 2),
    Field("POLICY FORM", "POLICY_FORM", "code", 2),
    Field("CONSTRUCTION", "CONSTRUCTION", "code", 2),
    Field("PROTECTION CLASS", "PROTECTION_CLASS", "code", 2),
    Field("DEDUCTIBLE", "DEDUCTIBLE", "code", 2),
    Field("EFFECTIVE YYYYMM", "POLICY_EFFECTIVE_DATE", "date:%Y%m", 6),
    Field("ZIP", "ZIP_CODE", "text", 5),
    Field("YEAR BUILT", "YEAR_BUILT", "int", 4),
    Field("COV A IN THOUSANDS", "COVERAGE_A_LIMIT", "thousands", 6),
    Field("WRITTEN PREMIUM", "WRITTEN_PREMIUM", "dollars", 9),
    Field("POLICY NUMBER", "POLICY_NUMBER", "text", 14),
], note="Fixed width; every code comes from the ISO bureau codes in SI2Canonical (illustrative layout, not the official stat plan).")

SYSTEMS = {s.code: s for s in (LEGACY_PAS, POLICYCLOUD, ISO_STAT)}
SOURCES = [s for s in SYSTEMS.values() if s.role == "SOURCE"]
DESTINATIONS = [s for s in SYSTEMS.values() if s.role == "DESTINATION"]
ALIAS_TYPE = {"SOURCE": "LEGACY", "DESTINATION": "APP"}

# For the in-memory dictionary (no SQL Server): the canonical facts the bridge needs, as seeded in SI2Canonical.
ELEMENTS = {
    "POLICY_NUMBER": ("Policy Number", "TEXT", None), "LINE_OF_BUSINESS": ("Line of Business", "CODE", "LOB"),
    "POLICY_FORM": ("Policy Form", "CODE", "POLICY_FORM"), "POLICY_EFFECTIVE_DATE": ("Policy Effective Date", "DATE", None),
    "POLICY_EXPIRATION_DATE": ("Policy Expiration Date", "DATE", None), "INSURED_NAME": ("Insured Name", "TEXT", None),
    "STATE": ("State", "CODE", "STATE"), "ZIP_CODE": ("ZIP Code", "TEXT", None), "CONSTRUCTION": ("Construction", "CODE", "CONSTRUCTION"),
    "PROTECTION_CLASS": ("Protection Class", "CODE", "PROTECTION_CLASS"), "YEAR_BUILT": ("Year Built", "INTEGER", None),
    "COVERAGE_A_LIMIT": ("Coverage A Dwelling Limit", "AMOUNT", None), "DEDUCTIBLE": ("Deductible", "CODE", "DEDUCTIBLE"),
    "TRANSACTION_TYPE": ("Transaction Type", "CODE", "TRANSACTION_TYPE"), "WRITTEN_PREMIUM": ("Written Premium", "AMOUNT", None),
}
STATE_ISO = {"FL": "09", "GA": "10", "NY": "31", "NC": "32", "TX": "42", "SC": "39", "AL": "01", "LA": "17"}
ISO_CODES = {
    "LOB": {"HO": "01", "BP": "40"},
    "POLICY_FORM": {"HO2": "02", "HO3": "03", "HO4": "04", "HO5": "05", "HO6": "06", "STD": "01", "SPC": "02"},
    "CONSTRUCTION": {"FR": "01", "JM": "02", "NC": "03", "MNC": "04", "MFR": "05", "FRS": "06", "MAS": "07", "VEN": "08"},
    "PROTECTION_CLASS": {f"{i:02d}": f"{i:02d}" for i in range(1, 11)},
    "DEDUCTIBLE": {"D0": "00", "D250": "01", "D500": "02", "D1000": "03", "D2500": "04", "D5000": "05", "D10000": "06",
                   "P1": "07", "P2": "08", "P5": "09"},
    "TRANSACTION_TYPE": {"NB": "10", "RN": "11", "EN": "12", "CN": "13", "RI": "14", "AU": "15"},
    "STATE": STATE_ISO,
}
OPTIONS = {pl: set(codes) for pl, codes in ISO_CODES.items()}


# ------------------------------------------------------------------------------------------ mappings to register
def proposals(systems=None) -> list[dict]:
    """Change requests (aliases tagged with the system) that teach SI2Canonical each system's fields and values."""
    out = []
    for s in (systems or SYSTEMS.values()):
        for f in s.fields:
            if not f.element:
                continue
            out.append({"object_type": "SYNONYM", "change": "ADD", "code": f.element,
                        "summary": f"{s.name}: field '{f.name}' is {f.element}",
                        "payload": {"object_type": "ELEMENT", "object_code": f.element, "text": f.name,
                                    "type": "BUREAU" if s.value_source.startswith("BUREAU") else ALIAS_TYPE[s.role], "source": s.code}})
            pl = ELEMENTS.get(f.element, (None, None, None))[2]
            for v, opt in f.values.items():
                out.append({"object_type": "SYNONYM", "change": "ADD", "code": f"{pl}.{opt}",
                            "summary": f"{s.name}: value '{v}' of {f.name} is {pl} {opt}",
                            "payload": {"object_type": "OPTION", "object_code": opt, "picklist": pl, "text": v, "type": "VALUE", "source": s.code}})
    return out


# ------------------------------------------------------------------------------------------ synthetic legacy extract
FIRST = ["JOHN", "MARIA", "JAMES", "LINDA", "ROBERT", "PATRICIA", "DAVID", "SUSAN", "CARLOS", "AISHA", "WEI", "PRIYA", "OMAR", "GRACE"]
LAST = ["SMITH", "GARCIA", "JOHNSON", "NGUYEN", "BROWN", "PATEL", "WILLIAMS", "LOPEZ", "DAVIS", "KIM", "MARTIN", "OKAFOR", "ROSSI"]
ZIPS = {"FL": "33", "GA": "30", "NY": "12", "NC": "27", "TX": "75", "SC": "29", "AL": "35", "LA": "70"}


def legacy_extract(n: int = 200, seed: int = 7, problems: bool = True) -> list[dict]:
    """A legacy policy extract; with problems=True a few rows carry the faults real extracts have."""
    rnd = random.Random(seed)
    rows = []
    for i in range(n):
        bop = rnd.random() < 0.15
        st = rnd.choice(list(ZIPS))
        eff = dt.date(2026, 1, 1) + dt.timedelta(days=rnd.randrange(0, 270))
        exp = eff.replace(year=eff.year + 1)
        cov = rnd.choice([150, 200, 250, 300, 350, 450, 600, 850]) * 1000
        prem = round(cov * rnd.uniform(0.0035, 0.009) * (1.8 if st in ("FL", "LA") else 1.0), 2)
        trn = rnd.choices(["N", "R", "E", "X"], [30, 55, 10, 5])[0]
        if trn == "X":
            prem = -round(prem * rnd.uniform(0.2, 0.8), 2)
        rows.append({
            "POL_NO": f"{'B' if bop else 'H'}{st}{100000 + i:06d}",
            "LOB_CD": "B" if bop else "H",
            "FORM_CD": rnd.choice(["BS", "BP"]) if bop else rnd.choices(["3", "5", "6", "4"], [70, 12, 10, 8])[0],
            "EFF_DT": eff.strftime("%Y%m%d"), "EXP_DT": exp.strftime("%Y%m%d"),
            "INS_NM": f"{rnd.choice(LAST)}, {rnd.choice(FIRST)}",
            "RSK_ST": st, "ZIP5": ZIPS[st] + f"{rnd.randrange(0, 1000):03d}",
            "CONST_CD": rnd.choices(list(CONST_LEGACY), [50, 15, 5, 15, 5, 10])[0],
            "PROT_CL": str(rnd.choices(range(1, 11), [3, 6, 12, 16, 16, 14, 11, 9, 7, 6])[0]),
            "YR_BLT": str(rnd.randrange(1950, 2025)),
            "COV_A": str(cov),
            "DED_AMT": rnd.choices(list(DED_LEGACY), [5, 20, 35, 20, 5, 10, 5])[0],
            "TRN_CD": trn,
            "WRT_PREM": f"{'-' if prem < 0 else ''}{abs(round(prem * 100)):09d}",
            "AGT_CD": f"A{rnd.randrange(100, 140)}",
        })
    if problems and n >= 20:
        rows[3]["CONST_CD"] = "Z"              # a code nobody has mapped
        rows[7]["EFF_DT"] = "20261341"         # not a date
        rows[11]["RSK_ST"] = ""                # missing state
        rows[15]["DED_AMT"] = "750"            # a deductible the canonical list does not have
    return rows
