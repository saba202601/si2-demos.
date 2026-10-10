"""Synthetic Personal Auto data and the SI² canonical model.

Everything here is generated from a fixed seed so every visitor sees the same sample.
Nothing is real policyholder data.
"""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

STATES = {  # state: (numeric state code used in the illustrative layout, ZIP3 range)
    "FL": ("09", (320, 349)),
    "GA": ("10", (300, 319)),
    "NC": ("32", (270, 289)),
    "NY": ("31", (100, 149)),
    "OH": ("34", (430, 458)),
    "TX": ("42", (750, 799)),
}

COVERAGES = {  # code: (description, limit options, deductible options, base premium)
    "BI": ("Bodily injury liability", ["25/50", "50/100", "100/300", "250/500"], [0], 420),
    "PD": ("Property damage liability", ["25", "50", "100"], [0], 310),
    "PIP": ("Personal injury protection", ["10"], [0], 160),
    "UM": ("Uninsured motorist", ["25/50", "50/100", "100/300"], [0], 95),
    "COLL": ("Collision", ["ACV"], [250, 500, 1000], 520),
    "COMP": ("Comprehensive", ["ACV"], [100, 250, 500, 1000], 180),
}

CAUSES = {"COLL": "01", "COMP": "02", "BI": "03", "PD": "04", "PIP": "05", "UM": "06"}

FIRST = ["Maria", "James", "Aisha", "Robert", "Linh", "Carlos", "Emily", "David", "Priya", "Michael",
         "Sofia", "Daniel", "Grace", "Omar", "Hannah", "Kevin", "Rosa", "Thomas", "Nia", "Samuel"]
LAST = ["Garcia", "Smith", "Johnson", "Nguyen", "Brown", "Patel", "Williams", "Lopez", "Davis", "Miller",
        "Wilson", "Moore", "Taylor", "Anderson", "Thomas", "Jackson", "White", "Harris", "Martin", "Clark"]
MAKES = ["Toyota", "Ford", "Honda", "Chevrolet", "Nissan", "Hyundai", "Subaru", "Kia", "Jeep", "Tesla"]
VIN_CHARS = "ABCDEFGHJKLMNPRSTUVWXYZ0123456789"


def _date(d: dt.date) -> str:
    return d.strftime("%Y-%m-%d")


def legacy_policy_extract(n_policies: int = 40, seed: int = 7) -> pd.DataFrame:
    """A flat 'source system' extract: one row per policy, vehicle and coverage."""
    rng = np.random.default_rng(seed)
    rows = []
    start = dt.date(2025, 7, 1)
    for i in range(n_policies):
        st_ = rng.choice(list(STATES))
        lo, hi = STATES[st_][1]
        zip5 = f"{rng.integers(lo, hi + 1):03d}{rng.integers(0, 100):02d}"
        eff = start + dt.timedelta(days=int(rng.integers(0, 365)))
        dob = dt.date(int(rng.integers(1950, 2006)), int(rng.integers(1, 13)), int(rng.integers(1, 29)))
        name = f"{rng.choice(LAST).upper()}, {rng.choice(FIRST).upper()}"
        trn = rng.choice(["NB", "RN"], p=[0.4, 0.6])
        pol = f"PA{2026000 + i:07d}"
        for v in range(1, int(rng.integers(1, 3)) + 1):
            vin = "".join(rng.choice(list(VIN_CHARS), 17))
            year = int(rng.integers(2010, 2027))
            symbol = int(rng.integers(5, 28))
            use = rng.choice(["P", "W", "B"], p=[0.55, 0.4, 0.05])
            covs = ["BI", "PD", "UM"] + (["PIP"] if st_ in ("FL", "NY", "TX") else [])
            if year >= 2014 or rng.random() < 0.5:
                covs += ["COLL", "COMP"]
            for c in covs:
                desc, limits, deds, base = COVERAGES[c]
                prem = round(base * float(rng.uniform(0.6, 1.8)), 0)
                rows.append({
                    "POL_NO": pol, "TRN_TYP": trn, "TRN_DT": _date(eff - dt.timedelta(days=int(rng.integers(0, 20)))),
                    "EFF_DT": _date(eff), "EXP_DT": _date(eff.replace(year=eff.year + 1)),
                    "ST": st_, "ZIP5": zip5, "INSD_NM": name, "INSD_DOB": _date(dob),
                    "VEH_SEQ": v, "VEH_YR": year, "VEH_MAKE": rng.choice(MAKES), "VIN": vin,
                    "SYM": symbol, "USE_CD": use, "COV_CD": c, "LMT": rng.choice(limits),
                    "DED": int(rng.choice(deds)), "WRTN_PREM": prem,
                })
    return pd.DataFrame(rows)


def legacy_claims_extract(policies: pd.DataFrame, n_claims: int = 25, seed: int = 11) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    covs = policies[["POL_NO", "VEH_SEQ", "COV_CD", "EFF_DT", "EXP_DT", "ST"]].drop_duplicates()
    picks = covs.sample(n=min(n_claims, len(covs)), random_state=seed).reset_index(drop=True)
    rows = []
    for i, r in picks.iterrows():
        eff = dt.date.fromisoformat(r.EFF_DT)
        acc = eff + dt.timedelta(days=int(rng.integers(5, 300)))
        rpt = acc + dt.timedelta(days=int(rng.integers(0, 40)))
        paid = round(float(rng.gamma(2.0, 2500.0)), 2)
        rows.append({
            "CLM_NO": f"CL{26000 + i:06d}", "POL_NO": r.POL_NO, "VEH_SEQ": r.VEH_SEQ, "COV_CD": r.COV_CD,
            "ST": r.ST, "ACC_DT": _date(acc), "RPT_DT": _date(rpt), "COL_CD": CAUSES[r.COV_CD],
            "PAID_LOSS": paid, "OS_RSV": round(float(rng.choice([0, rng.gamma(2.0, 1500.0)])), 2),
            "ALAE": round(paid * float(rng.uniform(0.0, 0.12)), 2),
            "CLM_STS": rng.choice(["O", "C"], p=[0.45, 0.55]),
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- canonical model
CANONICAL_ENTITIES = {
    "Party": ["party_id", "party_type", "full_name", "birth_date"],
    "Policy": ["policy_id", "policy_number", "line_of_business", "state", "effective_date",
               "expiration_date", "named_insured_party_id"],
    "Location": ["location_id", "policy_id", "postal_code", "state"],
    "RiskItem": ["risk_item_id", "policy_id", "risk_type", "sequence", "model_year", "make",
                 "vin", "rating_symbol", "use_type"],
    "Coverage": ["coverage_id", "risk_item_id", "coverage_code", "coverage_name", "limit", "deductible"],
    "PremiumTransaction": ["premium_txn_id", "coverage_id", "transaction_type", "transaction_date",
                           "written_premium"],
    "Claim": ["claim_id", "claim_number", "policy_id", "coverage_id", "accident_date", "report_date",
              "cause_of_loss", "status"],
    "LossTransaction": ["loss_txn_id", "claim_id", "paid_loss", "outstanding_reserve", "alae"],
}

RELATIONSHIPS = [  # (from, to, label)
    ("Party", "Policy", "is named insured on"),
    ("Policy", "Location", "garaged at"),
    ("Policy", "RiskItem", "insures 1..*"),
    ("RiskItem", "Coverage", "has 1..*"),
    ("Coverage", "PremiumTransaction", "earns 1..*"),
    ("Policy", "Claim", "has 0..*"),
    ("Claim", "Coverage", "made under"),
    ("Claim", "LossTransaction", "has 1..*"),
]

MAPPING = [  # source field -> canonical attribute, transform
    ("POL_NO", "Policy.policy_number", "copy"),
    ("ST", "Policy.state", "copy; validate USPS code"),
    ("EFF_DT", "Policy.effective_date", "parse ISO date"),
    ("EXP_DT", "Policy.expiration_date", "parse ISO date"),
    ("INSD_NM", "Party.full_name", "'LAST, FIRST' to 'First Last'"),
    ("INSD_DOB", "Party.birth_date", "parse ISO date"),
    ("ZIP5", "Location.postal_code", "copy; keep leading zeros"),
    ("VEH_SEQ", "RiskItem.sequence", "copy"),
    ("VEH_YR", "RiskItem.model_year", "integer"),
    ("VEH_MAKE", "RiskItem.make", "copy"),
    ("VIN", "RiskItem.vin", "upper case; 17 characters"),
    ("SYM", "RiskItem.rating_symbol", "integer"),
    ("USE_CD", "RiskItem.use_type", "P=Pleasure, W=Commute, B=Business"),
    ("COV_CD", "Coverage.coverage_code", "copy; look up name"),
    ("LMT", "Coverage.limit", "copy"),
    ("DED", "Coverage.deductible", "integer"),
    ("TRN_TYP", "PremiumTransaction.transaction_type", "NB=New business, RN=Renewal"),
    ("TRN_DT", "PremiumTransaction.transaction_date", "parse ISO date"),
    ("WRTN_PREM", "PremiumTransaction.written_premium", "decimal"),
]

USE_TYPES = {"P": "Pleasure", "W": "Commute", "B": "Business"}
TRN_TYPES = {"NB": "New business", "RN": "Renewal", "EN": "Endorsement", "CN": "Cancellation"}


def _proper_name(legacy: str) -> str:
    if "," in legacy:
        last, first = [p.strip() for p in legacy.split(",", 1)]
        return f"{first.title()} {last.title()}"
    return legacy.title()


def build_canonical(policies: pd.DataFrame, claims: pd.DataFrame | None = None) -> dict[str, pd.DataFrame]:
    """Map the flat legacy extract into canonical entity tables."""
    out: dict[str, list[dict]] = {k: [] for k in CANONICAL_ENTITIES}
    for p_idx, (pol_no, g) in enumerate(policies.groupby("POL_NO", sort=False), start=1):
        first = g.iloc[0]
        party_id, policy_id = f"PTY-{p_idx:05d}", f"POL-{p_idx:05d}"
        out["Party"].append({"party_id": party_id, "party_type": "Person",
                             "full_name": _proper_name(first.INSD_NM), "birth_date": first.INSD_DOB})
        out["Policy"].append({"policy_id": policy_id, "policy_number": pol_no, "line_of_business": "Personal Auto",
                              "state": first.ST, "effective_date": first.EFF_DT, "expiration_date": first.EXP_DT,
                              "named_insured_party_id": party_id})
        out["Location"].append({"location_id": f"LOC-{p_idx:05d}", "policy_id": policy_id,
                                "postal_code": str(first.ZIP5).zfill(5), "state": first.ST})
        for seq, vg in g.groupby("VEH_SEQ"):
            v = vg.iloc[0]
            risk_id = f"{policy_id}-V{seq}"
            out["RiskItem"].append({"risk_item_id": risk_id, "policy_id": policy_id, "risk_type": "Vehicle",
                                    "sequence": int(seq), "model_year": int(v.VEH_YR), "make": v.VEH_MAKE,
                                    "vin": str(v.VIN).upper(), "rating_symbol": int(v.SYM),
                                    "use_type": USE_TYPES.get(v.USE_CD, v.USE_CD)})
            for _, c in vg.iterrows():
                cov_id = f"{risk_id}-{c.COV_CD}"
                out["Coverage"].append({"coverage_id": cov_id, "risk_item_id": risk_id, "coverage_code": c.COV_CD,
                                        "coverage_name": COVERAGES.get(c.COV_CD, ("Unknown",))[0],
                                        "limit": c.LMT, "deductible": int(c.DED)})
                out["PremiumTransaction"].append({"premium_txn_id": f"{cov_id}-P1", "coverage_id": cov_id,
                                                  "transaction_type": TRN_TYPES.get(c.TRN_TYP, c.TRN_TYP),
                                                  "transaction_date": c.TRN_DT,
                                                  "written_premium": float(c.WRTN_PREM)})
    if claims is not None:
        pol_ids = {r["policy_number"]: r["policy_id"] for r in out["Policy"]}
        for _, c in claims.iterrows():
            pid = pol_ids.get(c.POL_NO)
            out["Claim"].append({"claim_id": c.CLM_NO, "claim_number": c.CLM_NO, "policy_id": pid,
                                 "coverage_id": f"{pid}-V{c.VEH_SEQ}-{c.COV_CD}", "accident_date": c.ACC_DT,
                                 "report_date": c.RPT_DT, "cause_of_loss": c.COL_CD,
                                 "status": "Open" if c.CLM_STS == "O" else "Closed"})
            out["LossTransaction"].append({"loss_txn_id": f"{c.CLM_NO}-L1", "claim_id": c.CLM_NO,
                                           "paid_loss": float(c.PAID_LOSS), "outstanding_reserve": float(c.OS_RSV),
                                           "alae": float(c.ALAE)})
    return {k: pd.DataFrame(v, columns=CANONICAL_ENTITIES[k]) for k, v in out.items()}


def policy_document(tables: dict[str, pd.DataFrame], policy_number: str) -> dict:
    """One policy as a nested canonical JSON document."""
    pol = tables["Policy"].query("policy_number == @policy_number").iloc[0].to_dict()
    pid = pol["policy_id"]
    party = tables["Party"].query("party_id == @pol['named_insured_party_id']").iloc[0].to_dict()
    loc = tables["Location"].query("policy_id == @pid").to_dict("records")
    risks = []
    for r in tables["RiskItem"].query("policy_id == @pid").to_dict("records"):
        covs = []
        for c in tables["Coverage"].query("risk_item_id == @r['risk_item_id']").to_dict("records"):
            c["premium_transactions"] = tables["PremiumTransaction"].query(
                "coverage_id == @c['coverage_id']").to_dict("records")
            covs.append(c)
        r["coverages"] = covs
        risks.append(r)
    claims = tables["Claim"].query("policy_id == @pid").to_dict("records") if len(tables["Claim"]) else []
    for c in claims:
        c["loss_transactions"] = tables["LossTransaction"].query("claim_id == @c['claim_id']").to_dict("records")
    return {**pol, "named_insured": party, "locations": loc, "risk_items": risks, "claims": claims}
