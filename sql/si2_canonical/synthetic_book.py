"""A synthetic book of business for trying rules before they go live.

Policies for every product of the two synthetic companies, plus claims, billing accounts and line results, all with
canonical element codes and real pick-list codes. Deterministic: the same seed gives the same book, so an impact
number Saba sees is the number Sabasi sees when approving.
"""
from __future__ import annotations

import random

from rule_library import PRODUCTS

SIM_STATES = ["FL", "GA", "AL", "SC", "NC", "TX"]
SIS_STATES = ["FL", "TX", "CA", "NY", "IL", "OH", "PA", "GA", "NC", "WA", "ND", "WY", "AZ", "CO", "NJ", "MA"]
BASE_PREMIUM = {"HO": 1800, "PA": 1400, "UMB": 350, "BP": 2500, "CA": 9000, "CP": 12000, "GL": 6000, "WC": 15000, "CYB": 4000}


def _pick(rng, values, weights=None):
    return rng.choices(values, weights=weights)[0]


def _policy_facts(rng: random.Random, lob: str, state: str) -> dict:
    f = {"STATE": state, "RATE_CHANGE_PCT": round(max(-10.0, rng.gauss(4, 6)), 1),
         "PRODUCER_LICENSED_IND": _pick(rng, ["Y", "N"], [97, 3])}
    if lob == "HO":
        coastal = state in ("FL", "AL", "SC", "NC", "TX")
        f.update({"ROOF_AGE": int(rng.triangular(0, 35, 8)), "OCCUPANCY": _pick(rng, ["OWNER", "TENANT", "SEASONAL", "VACANT", "UNOCCUPIED"], [80, 9, 6, 3, 2]),
                  "PROTECTION_CLASS": f"{_pick(rng, range(1, 11), [4, 8, 12, 14, 14, 12, 10, 9, 9, 8]):02d}",
                  "FLOOD_ZONE": _pick(rng, ["X", "X500", "AE", "A", "VE", "V"], [60, 12, 15, 6, 5, 2] if coastal else [80, 10, 7, 3, 0, 0]),
                  "DISTANCE_TO_COAST": round(rng.uniform(0.1, 30 if coastal else 300), 1), "YEAR_BUILT": rng.randint(1920, 2025),
                  "COVERAGE_A_LIMIT": (rng.randrange(1_500_000, 5_000_000, 50_000) if rng.random() < 0.08    # high-value homes
                                       else rng.randrange(150_000, 1_500_000, 10_000)), "COVERAGE_C_LIMIT": rng.randrange(50_000, 400_000, 5_000),
                  "WILDFIRE_SCORE": rng.randint(0, 100), "WIND_MITIGATION": _pick(rng, ["", "HURRICANE_STRAPS", "SHUTTERS", "FORTIFIED", "ROOF_DECK"], [55, 20, 12, 5, 8]),
                  "ALARM_TYPE": _pick(rng, ["NONE", "LOCAL", "CENTRAL", "POLICE_FIRE"], [45, 30, 20, 5]), "PRIOR_CLAIMS": _pick(rng, [0, 1, 2, 3], [65, 22, 9, 4])})
    elif lob == "PA":
        f.update({"DRIVER_AGE": rng.randint(16, 85), "LICENSE_STATUS": _pick(rng, ["VALID", "PERMIT", "SUSPENDED", "REVOKED", "EXPIRED"], [92, 3, 2, 1, 2]),
                  "VIOLATION_TYPE": _pick(rng, ["", "SPEED_MINOR", "SPEED_MAJOR", "AT_FAULT_ACC", "DUI", "DISTRACTED"], [70, 12, 4, 8, 2, 4]),
                  "VEHICLE_VALUE": rng.randrange(5_000, 140_000, 1_000), "GOOD_STUDENT_IND": _pick(rng, ["Y", "N"], [12, 88]),
                  "ANTI_THEFT": _pick(rng, ["NONE", "PASSIVE", "ACTIVE", "ALARM", "TRACKING"], [30, 35, 15, 10, 10]),
                  "VEHICLE_USE": _pick(rng, ["PLEASURE", "COMMUTE", "BUSINESS", "RIDESHARE", "DELIVERY"], [40, 42, 8, 6, 4]),
                  "INSURANCE_SCORE_IND": _pick(rng, ["Y", "N"], [85, 15])})
    elif lob == "UMB":
        f.update({"UNDERLYING_LIABILITY_LIMIT": _pick(rng, [100_000, 250_000, 300_000, 500_000], [10, 50, 25, 15]), "DRIVER_AGE": rng.randint(16, 80)})
    elif lob == "BP":
        f.update({"ANNUAL_REVENUE": rng.randrange(100_000, 8_000_000, 50_000), "SQUARE_FEET": rng.randrange(800, 45_000, 100),
                  "NAICS_SECTOR": _pick(rng, ["44-45", "72", "54", "81", "53", "23", "62", "22"], [22, 18, 18, 14, 12, 8, 6, 2])})
    elif lob == "CP":
        f.update({"CONSTRUCTION": _pick(rng, ["FR", "JM", "NC", "MNC", "MFR", "FRS"], [30, 25, 15, 15, 8, 7]),
                  "TOTAL_INSURED_VALUE": rng.randrange(500_000, 80_000_000, 100_000), "SQUARE_FEET": rng.randrange(2_000, 250_000, 500),
                  "SPRINKLER_TYPE": _pick(rng, ["NONE", "PARTIAL", "FULL", "DRY", "ESFR"], [35, 15, 35, 8, 7]),
                  "PROTECTION_CLASS": f"{rng.randint(1, 10):02d}", "FLOOD_ZONE": _pick(rng, ["X", "X500", "AE", "A", "VE"], [70, 12, 10, 5, 3])})
    elif lob == "GL":
        f.update({"NAICS_SECTOR": _pick(rng, ["23", "31-33", "42", "44-45", "54", "72", "21", "56"], [20, 15, 10, 15, 15, 12, 3, 10]),
                  "ANNUAL_REVENUE": rng.randrange(200_000, 90_000_000, 100_000), "YEARS_IN_BUSINESS": rng.randint(0, 60),
                  "PRIOR_CLAIMS": _pick(rng, [0, 1, 2, 3], [60, 25, 10, 5])})
    elif lob == "CA":
        f.update({"VEHICLE_TYPE": _pick(rng, ["PICKUP", "VAN", "LIGHT_TRUCK", "MEDIUM_TRUCK", "HEAVY_TRUCK", "TRACTOR"], [30, 25, 20, 12, 8, 5]),
                  "NUMBER_OF_VEHICLES": rng.randint(1, 120), "DRIVER_AGE": rng.randint(18, 75), "VIOLATIONS": _pick(rng, [0, 1, 2, 3, 4], [55, 22, 12, 7, 4])})
    elif lob == "WC":
        f.update({"EXPERIENCE_MODIFICATION_FACTOR": round(rng.uniform(0.6, 1.6), 2), "ANNUAL_PAYROLL": rng.randrange(100_000, 25_000_000, 50_000)})
    elif lob == "CYB":
        f.update({"MFA_IND": _pick(rng, ["Y", "N"], [85, 15]), "EDR_IND": _pick(rng, ["Y", "N"], [70, 30]),
                  "BACKUP_OFFLINE_IND": _pick(rng, ["Y", "N"], [75, 25]), "RECORDS_HELD": rng.randrange(1_000, 5_000_000, 1_000)})
    return f


def policies(n: int = 600, seed: int = 2026) -> list[dict]:
    """Policies spread over every product; each is {id, kind, case, facts, premium}."""
    rng = random.Random(seed)
    out = []
    for i in range(n):
        code, lob, _, company, states = PRODUCTS[i % len(PRODUCTS)]
        state = _pick(rng, states or SIS_STATES)
        premium = round(BASE_PREMIUM.get(lob, 1000) * rng.uniform(0.5, 2.5), 0)
        out.append({"id": f"POL-{10001 + i}", "kind": "POLICY",
                    "case": {"COMPANY": company, "LOB": lob, "PRODUCT": code, "STATE": state,
                             "CHANNEL": _pick(rng, ["AGENT", "DIRECT", "BROKER"], [70, 15, 15])},
                    "facts": _policy_facts(rng, lob, state), "premium": premium})
    return out


def claims(n: int = 300, seed: int = 2027) -> list[dict]:
    rng = random.Random(seed)
    out = []
    for i in range(n):
        code, lob, _, company, states = PRODUCTS[rng.randrange(len(PRODUCTS))]
        state = _pick(rng, states or SIS_STATES)
        paid = round(rng.lognormvariate(8.5, 1.4), 0)
        out.append({"id": f"CLM-{50001 + i}", "kind": "CLAIM", "case": {"COMPANY": company, "LOB": lob, "PRODUCT": code, "STATE": state},
                    "facts": {"LITIGATION_IND": _pick(rng, ["Y", "N"], [8, 92]), "CATASTROPHE_IND": _pick(rng, ["Y", "N"], [10, 90]),
                              "ATTORNEY_INDICATOR": _pick(rng, ["Y", "N"], [12, 88]), "INCURRED_LOSS": paid, "CLAIM_PAYMENT_AMOUNT": paid,
                              "DAYS_TO_REPORT": int(rng.expovariate(1 / 6)), "PRIOR_CLAIMS": _pick(rng, [0, 1, 2, 3, 4], [55, 25, 10, 6, 4])},
                    "premium": 0})
    return out


def billing(n: int = 200, seed: int = 2028) -> list[dict]:
    rng = random.Random(seed)
    out = []
    for i in range(n):
        code, lob, _, company, states = PRODUCTS[rng.randrange(len(PRODUCTS))]
        state = _pick(rng, states or SIS_STATES)
        out.append({"id": f"ACC-{70001 + i}", "kind": "BILLING", "case": {"COMPANY": company, "LOB": lob, "PRODUCT": code, "STATE": state},
                    "facts": {"DAYS_PAST_DUE": _pick(rng, [0, 5, 12, 20, 35, 60], [55, 15, 10, 8, 7, 5]),
                              "ACCOUNT_BALANCE": round(rng.uniform(0, 3000), 2), "CANCEL_REASON": _pick(rng, ["", "NONPAY", "UW", "INSURED_REQ"], [70, 15, 5, 10]),
                              "NOTICE_DAYS_GIVEN": _pick(rng, [7, 10, 15, 30, 45], [10, 40, 20, 20, 10])},
                    "premium": 0})
    return out


def results(seed: int = 2029) -> list[dict]:
    """Line results by company: what the CEO, CFO and CUO watch."""
    rng = random.Random(seed)
    out = []
    for company, lobs in (("SIM", ["HO", "PA", "UMB", "BP"]), ("SIS", ["CP", "GL", "CA", "WC", "CYB", "UMB"])):
        for lob in lobs:
            lr, er = round(rng.uniform(0.45, 0.85), 3), round(rng.uniform(0.24, 0.38), 3)
            out.append({"id": f"{company}-{lob}-2026", "kind": "RESULTS", "case": {"COMPANY": company, "LOB": lob},
                        "facts": {"LOSS_RATIO": lr, "EXPENSE_RATIO": er, "COMBINED_RATIO": round(lr + er, 3),
                                  "PREMIUM_GROWTH_PCT": round(rng.uniform(-15, 35), 1), "RETENTION_RATE": round(rng.uniform(0.72, 0.92), 3)},
                        "premium": 0})
    return out


def book() -> list[dict]:
    return policies() + claims() + billing() + results()
