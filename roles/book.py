"""A self-contained synthetic insurance company for the Role-Based Super Intelligence app.

No legacy system and no outside data: policies, submissions, claims with their payments, fraud rings, reinsurance,
customers, agents and horizon-scanning signals are generated here, seeded, so every run is identical.
Underlying "true" risk follows the same factors the SI models estimate, plus noise the models do not see.
"""
from __future__ import annotations

import datetime as dt
from functools import lru_cache

import numpy as np
import pandas as pd

VAL = dt.date(2026, 9, 30)                       # valuation date of the book
STATES = {  # state: (lat, lon, main peril)
    "FL": (27.8, -81.7, "Hurricane"), "TX": (31.0, -97.5, "Hail"), "LA": (30.9, -92.0, "Hurricane"),
    "NC": (35.5, -79.4, "Hurricane"), "CA": (36.8, -119.4, "Wildfire"), "CO": (39.0, -105.5, "Hail"),
    "NY": (42.9, -75.5, "None"), "OH": (40.4, -82.8, "None"),
}
PRODUCTS = {  # product: (share, base frequency, mean severity, base premium rate per 1,000 TIV or flat)
    "Homeowners": (0.45, 0.060, 14000), "Personal Auto": (0.30, 0.110, 7000),
    "Commercial Property": (0.17, 0.050, 60000), "Cyber": (0.08, 0.035, 90000),
}
CAUSES = {
    "Homeowners": ["Wind", "Hail", "Water damage", "Fire", "Theft", "Wildfire", "Sewer backup", "Flood"],
    "Personal Auto": ["Collision", "Comprehensive", "Bodily injury", "Property damage", "Glass"],
    "Commercial Property": ["Fire", "Wind", "Water damage", "Equipment breakdown", "Hail", "Flood"],
    "Cyber": ["Ransomware", "Data breach", "Business email compromise", "System outage"],
}
EXCLUDED = {"Sewer backup": "Sewer backup excluded without endorsement", "Flood": "Flood excluded (separate policy)"}
TARGET_LR = 0.62


def _relativities(p: pd.DataFrame) -> pd.DataFrame:
    """Multiplicative frequency relativities by factor (the 'true' model)."""
    r = pd.DataFrame(index=p.index)
    r["territory"] = p.territory.map({1: 0.80, 2: 0.92, 3: 1.00, 4: 1.15, 5: 1.35})
    r["roof"] = np.where(p["product"].isin(["Homeowners", "Commercial Property"]),
                         np.select([p.roof_age > 20, p.roof_age > 12], [1.45, 1.15], 0.90), 1.0)
    r["construction"] = p.construction.map({"Frame": 1.15, "Masonry": 1.0, "Fire resistive": 0.80}).fillna(1.0)
    r["protection"] = np.where(p["product"].isin(["Homeowners", "Commercial Property"]), 0.85 + 0.04 * p.protection_class, 1.0)
    r["prior_claims"] = 1 + 0.30 * p.prior_claims
    r["credit"] = p.credit_tier.map({"A": 0.85, "B": 0.95, "C": 1.10, "D": 1.35}).fillna(1.0)
    r["sensor"] = np.where(p.leak_sensor, 0.82, 1.0)
    r["cat_zone"] = p.cat_zone.map({"Coastal hurricane": 1.30, "Wildfire WUI": 1.25, "Hail belt": 1.20, "Low": 1.0})
    r["driver_age"] = np.where(p["product"] == "Personal Auto",
                               np.select([p.driver_age < 25, p.driver_age > 75], [1.6, 1.2], 1.0), 1.0)
    r["cyber_controls"] = np.where(p["product"] == "Cyber", np.where(p.mfa, 0.70, 1.25) * np.where(p.backups, 0.85, 1.15), 1.0)
    return r


@lru_cache(maxsize=1)
def build(n_pol: int = 3000, seed: int = 26) -> dict:
    rng = np.random.default_rng(seed)
    prod = rng.choice(list(PRODUCTS), n_pol, p=[v[0] for v in PRODUCTS.values()])
    st = rng.choice(list(STATES), n_pol, p=[.22, .18, .07, .09, .15, .08, .11, .10])
    lat = np.array([STATES[s][0] for s in st]) + rng.normal(0, 1.1, n_pol)
    lon = np.array([STATES[s][1] for s in st]) + rng.normal(0, 1.4, n_pol)
    peril = np.array([STATES[s][2] for s in st])
    coastal = rng.random(n_pol) < 0.45
    cat_zone = np.where((peril == "Hurricane") & coastal, "Coastal hurricane",
                        np.where(peril == "Wildfire", np.where(rng.random(n_pol) < 0.5, "Wildfire WUI", "Low"),
                                 np.where(peril == "Hail", "Hail belt", "Low")))
    cat_zone = np.where(prod == "Cyber", "Low", cat_zone)
    tiv = np.where(prod == "Homeowners", rng.lognormal(12.9, 0.45, n_pol),
                   np.where(prod == "Commercial Property", rng.lognormal(15.2, 0.8, n_pol),
                            np.where(prod == "Personal Auto", rng.lognormal(10.2, 0.4, n_pol), rng.lognormal(14.5, 0.7, n_pol))))
    eff = pd.to_datetime("2025-10-01") + pd.to_timedelta(rng.integers(0, 365, n_pol), "D")
    p = pd.DataFrame({
        "policy_no": [f"P{100000 + i}" for i in range(n_pol)], "customer_id": [f"C{50000 + i // 1}" for i in range(n_pol)],
        "product": prod, "state": st, "zip": [f"{z:05d}" for z in rng.integers(1000, 99950, n_pol)],
        "lat": lat.round(3), "lon": lon.round(3), "cat_zone": cat_zone, "territory": rng.integers(1, 6, n_pol),
        "tiv": tiv.round(-2), "deductible": rng.choice([500, 1000, 2500, 5000], n_pol, p=[.3, .4, .2, .1]),
        "eff_date": eff.date, "agent_id": rng.choice([f"AG{100 + i}" for i in range(24)], n_pol),
        "year_built": rng.integers(1955, 2025, n_pol), "roof_age": rng.integers(1, 32, n_pol),
        "construction": rng.choice(["Frame", "Masonry", "Fire resistive"], n_pol, p=[.55, .35, .10]),
        "protection_class": rng.integers(1, 11, n_pol), "prior_claims": rng.choice([0, 0, 0, 1, 1, 2, 3], n_pol),
        "credit_tier": rng.choice(list("ABCD"), n_pol, p=[.35, .35, .2, .1]),
        "leak_sensor": rng.random(n_pol) < 0.22, "driver_age": rng.integers(17, 88, n_pol),
        "mfa": rng.random(n_pol) < 0.6, "backups": rng.random(n_pol) < 0.65,
        "aerial_roof_score": rng.integers(20, 100, n_pol), "iot_alerts_12m": rng.poisson(0.4, n_pol),
        "tenure_years": rng.integers(0, 18, n_pol), "late_payments_12m": rng.choice([0, 0, 0, 0, 1, 2, 3], n_pol),
        "complaints_12m": rng.choice([0, 0, 0, 0, 0, 1, 2], n_pol), "rate_change_pct": rng.normal(6, 5, n_pol).round(1),
        "zip_income_tier": rng.choice(["Lower-income ZIP", "Middle-income ZIP", "Higher-income ZIP"], n_pol, p=[.3, .45, .25]),
        "has_umbrella": rng.random(n_pol) < 0.18, "has_flood": rng.random(n_pol) < 0.12,
        "liability_limit": rng.choice([100000, 300000, 500000, 1000000], n_pol, p=[.25, .4, .25, .1]),
        "replacement_cost": 0.0,
    })
    p.loc[p["product"] == "Cyber", ["construction", "roof_age"]] = ["Fire resistive", 0]
    p["exp_date"] = (pd.to_datetime(p.eff_date) + pd.Timedelta(days=365)).dt.date
    p["replacement_cost"] = (p.tiv * rng.normal(1.10, 0.14, n_pol)).round(-2)
    rel = _relativities(p)
    freq = np.array([PRODUCTS[x][1] for x in p["product"]]) * rel.prod(axis=1)
    sev = np.array([PRODUCTS[x][2] for x in p["product"]]) * np.where(p["product"].isin(["Commercial Property", "Cyber"]),
                                                                      (p.tiv / p.tiv.median()) ** 0.25, 1.0)
    p["true_expected_loss"] = (freq * sev).round(0)
    # charged premium: rate plan (expected loss / target LR) with a little noise and some rating errors
    load = np.select([p["product"] == "Personal Auto", p["product"] == "Cyber"], [1.40, 2.0], 1.12)       # trend and injury load in the rate plan
    plan = p.true_expected_loss * load / TARGET_LR * rng.normal(1.0, 0.06, n_pol)
    leak = rng.random(n_pol) < 0.04
    p["rate_plan_premium"] = plan.round(0)
    p["premium"] = np.where(leak, plan * rng.uniform(0.6, 0.85, n_pol), plan * rng.normal(1.0, 0.03, n_pol)).round(0)
    p["market_premium"] = (plan * rng.normal(1.02, 0.10, n_pol)).round(0)

    # ---- claims over accident years 2021-2026 (history of the same book)
    claims, pays = [], []
    cid = 0
    for ay in range(2021, 2027):
        expo = 1.0 if ay < 2026 else 0.75
        n = rng.poisson(freq * expo * (1 + 0.04 * (ay - 2021)))
        for i in np.flatnonzero(n):
            for _ in range(n[i]):
                cid += 1
                pr = p.at[i, "product"]
                cause = rng.choice(CAUSES[pr])
                acc = dt.date(ay, 1, 1) + dt.timedelta(days=int(rng.integers(0, 365 if ay < 2026 else 270)))
                lag = int(rng.choice([0, 1, 2, 3, 5, 9, 20, 40]))
                ult = float(sev[i] * rng.lognormal(-0.35, 0.85) * (1.04 ** (ay - 2021)))
                injury = pr == "Personal Auto" and cause in ("Bodily injury", "Collision") and rng.random() < 0.35
                if injury:
                    ult *= 2.4
                excluded = cause in EXCLUDED and rng.random() < 0.8
                if excluded:
                    ult = 0.0
                # payment pattern by product (share paid in development years 1..6)
                pattern = {"Homeowners": [.62, .30, .06, .02, 0, 0], "Personal Auto": [.38, .30, .17, .09, .04, .02],
                           "Commercial Property": [.45, .33, .14, .06, .02, 0], "Cyber": [.30, .35, .20, .10, .05, 0]}[pr]
                if injury:
                    pattern = [.18, .26, .24, .17, .10, .05]
                paid = 0.0
                last_dev = max(d for d, x in enumerate(pattern) if x)
                for d, share in enumerate(pattern):
                    if ay + d > VAL.year:
                        break
                    if share and ult:
                        amt = ult * share * rng.normal(1, 0.08)
                        paid += amt
                        pays.append({"claim_no": f"CL{cid:06d}", "accident_year": ay, "dev_year": d + 1,
                                     "calendar_year": ay + d, "amount": round(amt, 2), "product": pr})
                age = VAL.year - ay
                p_open = {"Homeowners": [.70, .25, .08, .03, .01, .01], "Personal Auto": [.85, .50, .30, .15, .08, .03],
                          "Commercial Property": [.80, .40, .15, .05, .02, .01], "Cyber": [.90, .60, .30, .10, .05, .02]}[pr][min(age, 5)]
                open_ = not excluded and rng.random() < (min(.95, p_open * 1.4) if injury else p_open)
                if not open_ and not excluded and ult > paid:
                    amt = ult - paid
                    paid = ult
                    pays.append({"claim_no": f"CL{cid:06d}", "accident_year": ay, "dev_year": min(last_dev, age) + 1,
                                 "calendar_year": ay + min(last_dev, age), "amount": round(amt, 2), "product": pr})
                claims.append({
                    "claim_no": f"CL{cid:06d}", "policy_no": p.at[i, "policy_no"], "product": pr, "state": p.at[i, "state"],
                    "cause": cause, "accident_date": acc, "report_date": acc + dt.timedelta(days=lag), "accident_year": ay,
                    "status": "Open" if open_ else "Closed", "ultimate_true": round(ult, 2), "paid_to_date": round(paid, 2),
                    "case_reserve": round(max(ult - paid, 0) * rng.normal(0.9, 0.2), 2) if open_ else 0.0,
                    "injury": injury, "attorney": bool(injury and rng.random() < 0.45), "photos": int(rng.integers(0, 9)),
                    "denied_reason": EXCLUDED.get(cause, "") if excluded else "", "zip_income_tier": p.at[i, "zip_income_tier"],
                    "claimant_phone": f"555-{rng.integers(1000, 9999)}", "claimant_address": f"{rng.integers(10, 9999)} {rng.choice(['Oak', 'Pine', 'Main', 'Cedar', 'Lake', 'Hill'])} St",
                    "vendor_id": rng.choice([f"V{200 + j}" for j in range(40)]), "attorney_id": "", "fraud_truth": "",
                })
    c = pd.DataFrame(claims)
    # calibrate premium so each product's 2021-2025 loss ratio tells a clear story (auto inadequate, others near target)
    h3 = c[c.accident_year.between(2023, 2025)]
    hist = (h3.ultimate_true * 1.04 ** (2026.5 - h3.accident_year)).groupby(h3["product"]).sum() / 3
    story = {"Homeowners": 1.00, "Personal Auto": 1.12, "Commercial Property": 0.93, "Cyber": 0.97}
    for pr_, f in story.items():
        m = p["product"] == pr_
        scale = hist.get(pr_, 0) / (p.loc[m, "premium"].sum() * TARGET_LR * f)
        for col in ("premium", "rate_plan_premium", "market_premium"):
            p.loc[m, col] = (p.loc[m, col] * scale).round(0)
    seg = (p.state == "TX") & (p["product"] == "Homeowners")
    for col in ("premium", "rate_plan_premium"):
        p.loc[seg, col] = (p.loc[seg, col] * 0.55).round(0)
    c.loc[c.attorney, "attorney_id"] = rng.choice([f"ATT{300 + j}" for j in range(25)], int(c.attorney.sum()))
    # ---- planted fraud rings (shared phone / address / vendor / attorney), recent open auto and property claims
    recent = c[(c.accident_year >= 2025) & (c.status == "Open") & c["product"].isin(["Personal Auto", "Homeowners"])].index
    ring_idx = rng.choice(recent, 22, replace=False)
    rings = np.array_split(ring_idx, 4)
    for k, grp in enumerate(rings):
        phone, addr, vend, att = f"555-90{k}{k}", f"{100 + k} Harbor View Dr", f"V9{k}0", f"ATT9{k}"
        for j, ix in enumerate(grp):
            if j % 2 == 0:
                c.at[ix, "claimant_phone"] = phone
            if j % 3 != 2:
                c.at[ix, "claimant_address"] = addr
            c.at[ix, "vendor_id"] = vend
            if k % 2 == 0:
                c.at[ix, "attorney"], c.at[ix, "attorney_id"] = True, att
            c.at[ix, "report_date"] = c.at[ix, "accident_date"] + dt.timedelta(days=int(rng.integers(12, 40)))
            c.at[ix, "fraud_truth"] = f"Ring {k + 1}"
    # image damage model output (simulated): severity estimate with confidence, for open claims with photos
    c["image_damage_score"] = np.where(c.photos > 0, np.clip(c.ultimate_true / (c.ultimate_true.median() * 3) * 100
                                                             + rng.normal(0, 12, len(c)), 3, 99).round(0), np.nan)
    c["image_confidence"] = np.where(c.photos > 0, np.clip(0.55 + 0.05 * c.photos + rng.normal(0, .05, len(c)), .3, .97).round(2), np.nan)
    pay = pd.DataFrame(pays)

    # ---- new submissions for the underwriter (same generator, not yet bound)
    subs = p.sample(90, random_state=seed + 1).copy().reset_index(drop=True)
    subs["submission_id"] = [f"S{7000 + i}" for i in range(len(subs))]
    jit = np.random.default_rng(seed + 2)
    subs["roof_age"] = jit.integers(1, 34, len(subs))
    subs["prior_claims"] = jit.choice([0, 0, 1, 1, 2, 3, 4], len(subs))
    subs["tiv"] = (subs.tiv * jit.uniform(0.6, 2.2, len(subs))).round(-2)
    subs["quoted_premium"] = (subs.premium * jit.uniform(0.85, 1.1, len(subs))).round(0)
    subs["applicant"] = [f"Applicant {i + 1}" for i in range(len(subs))]

    treaties = pd.DataFrame([
        ("Quota share 20%", "Quota share", 0.20, None, None, "All property", 0.31),
        ("Per-risk XoL 1M xs 1M", "Per-risk excess", None, 1_000_000, 1_000_000, "Commercial Property", None),
        ("Cat XoL 150M xs 50M", "Catastrophe excess", None, 50_000_000, 150_000_000, "All property", None),
    ], columns=["treaty", "type", "cession", "retention", "limit", "scope", "ceding_commission"])
    reinsurers = pd.DataFrame([
        ("Atlas Re", "A+", 0.30, False), ("Northbridge Re", "A", 0.25, False), ("Meridian Re", "A-", 0.20, False),
        ("Halcyon Re", "BBB+", 0.10, False), ("Coral Cat Capital (ILS)", "NR · collateralized", 0.15, True),
    ], columns=["reinsurer", "rating", "share", "collateralized"])
    signals = pd.DataFrame(SIGNALS, columns=["signal", "category", "source_type", "month", "momentum", "lines", "risk"])
    agents = pd.DataFrame({"agent_id": [f"AG{100 + i}" for i in range(24)],
                           "agency": [f"Agency {chr(65 + i)}" for i in range(24)],
                           "state": np.random.default_rng(seed + 3).choice(list(STATES), 24)})
    return {"policies": p, "claims": c, "payments": pay, "submissions": subs, "treaties": treaties,
            "reinsurers": reinsurers, "signals": signals, "agents": agents, "relativities": rel}


# illustrative horizon-scanning signals (synthetic summaries of the kind of evidence a strategy team tracks)
SIGNALS = [
    ("Wildland-urban interface housing growth continues", "Climate", "Census and land-use data", "2026-08", 4, "Homeowners", "Wildfire in the WUI"),
    ("Longer fire seasons in western states", "Climate", "Scientific publication", "2026-06", 4, "Homeowners, Commercial Property", "Wildfire in the WUI"),
    ("Severe convective storm losses rising year over year", "Climate", "Industry loss data", "2026-07", 5, "Homeowners, Commercial Property, Personal Auto", "Secondary perils (hail, wind)"),
    ("Hail size and frequency shifting north and east", "Climate", "Scientific publication", "2026-03", 3, "Homeowners, Personal Auto", "Secondary perils (hail, wind)"),
    ("Rapid intensification of Atlantic hurricanes", "Climate", "Scientific publication", "2026-05", 4, "Homeowners, Commercial Property", "Hurricane severity"),
    ("Flood losses outside mapped flood zones", "Climate", "Claims data", "2026-04", 3, "Homeowners", "Flood outside mapped zones"),
    ("Large jury awards increasing in liability cases", "Society", "Court verdict tracking", "2026-08", 5, "Personal Auto, Commercial Property", "Social inflation"),
    ("Third-party litigation funding growth", "Society", "Industry report", "2026-02", 4, "Personal Auto", "Social inflation"),
    ("Attorney involvement rising in auto injury claims", "Society", "Claims data", "2026-07", 4, "Personal Auto", "Social inflation"),
    ("Advanced driver-assistance sensors raise repair costs", "Technology", "Repair cost data", "2026-06", 4, "Personal Auto", "Vehicle repair cost inflation"),
    ("EV battery damage leads to total losses", "Technology", "Claims data", "2026-05", 3, "Personal Auto", "Vehicle repair cost inflation"),
    ("Autonomous driving pilots expand in more cities", "Technology", "Regulatory filings", "2026-03", 2, "Personal Auto", "Liability shift to manufacturers"),
    ("Ransomware groups target small businesses", "Technology", "Threat intelligence", "2026-08", 5, "Cyber", "Cyber systemic event"),
    ("Concentration in a few cloud providers", "Technology", "Market data", "2026-04", 4, "Cyber, Commercial Property", "Cyber systemic event"),
    ("Generative AI used in phishing and claims fraud", "Technology", "Threat intelligence", "2026-07", 4, "Cyber, Personal Auto, Homeowners", "AI-enabled fraud"),
    ("AI system errors create new liability questions", "Regulation", "Regulatory proposal", "2026-06", 3, "Commercial Property, Cyber", "AI liability"),
    ("State regulators issue guidance on AI in insurance decisions", "Regulation", "Regulatory bulletin", "2026-05", 4, "All lines", "AI governance and fairness rules"),
    ("Restrictions on use of credit-based scores expand", "Regulation", "Legislative tracking", "2026-03", 3, "Personal Auto, Homeowners", "AI governance and fairness rules"),
    ("PFAS ('forever chemicals') litigation widens", "Regulation", "Court filings", "2026-07", 4, "Commercial Property", "PFAS liability"),
    ("Climate-related disclosure requirements for insurers", "Regulation", "Regulatory proposal", "2026-02", 3, "All lines", "Climate disclosure"),
    ("Extreme heat days increase worker injury claims", "Climate", "Scientific publication", "2026-08", 3, "Commercial Property", "Extreme heat"),
    ("Reinsurance capacity for secondary perils tightening", "Market", "Reinsurance renewal reports", "2026-07", 4, "Homeowners, Commercial Property", "Secondary perils (hail, wind)"),
    ("Homeowners leaving high-risk states' private markets", "Market", "Regulatory data", "2026-06", 3, "Homeowners", "Wildfire in the WUI"),
    ("Insurtech embedded insurance at point of sale", "Market", "Market data", "2026-04", 2, "Personal Auto, Homeowners", "Distribution shift"),
]
