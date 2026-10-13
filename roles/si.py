"""SI² Role-Based Super Intelligence: the analytics behind each role. Pure functions over the synthetic book (no
Streamlit). Every function returns its result AND the reasons, so the person in the role can see why and decide.
"""
from __future__ import annotations

import datetime as dt
from collections import defaultdict

import numpy as np
import pandas as pd

from . import book as B

RNG_SEED = 7


# ============================================================================== shared: the rating model SI uses
def rating_model(p: pd.DataFrame) -> pd.DataFrame:
    """SI's estimate of expected loss with every driver's contribution (log-relativity), learned from the book."""
    rel = B._relativities(p)
    base = np.array([B.PRODUCTS[x][1] * B.PRODUCTS[x][2] for x in p["product"]])
    sev_adj = np.where(p["product"].isin(["Commercial Property", "Cyber"]), (p.tiv / 330000) ** 0.25, 1.0)
    ded = 1 - np.clip(np.log(p.deductible / 500) * 0.06, 0, 0.25)
    out = pd.DataFrame({"expected_loss": base * rel.prod(axis=1) * sev_adj * ded}, index=p.index)
    contrib = np.log(rel).assign(deductible=np.log(ded))
    return out.join(contrib)


DRIVER_NAMES = {"territory": "Territory", "roof": "Roof age", "construction": "Construction", "protection": "Fire protection class",
                "prior_claims": "Prior claims", "credit": "Credit-based insurance score", "sensor": "Water-leak sensor",
                "cat_zone": "Catastrophe zone", "driver_age": "Driver age", "cyber_controls": "Cyber controls (MFA, backups)",
                "deductible": "Deductible"}


def explain(row: pd.Series, top: int = 4) -> list[str]:
    items = [(DRIVER_NAMES[k], float(row[k])) for k in DRIVER_NAMES if k in row and abs(float(row[k])) > 0.02]
    items.sort(key=lambda x: -abs(x[1]))
    return [f"{n} {'raises' if v > 0 else 'lowers'} expected loss by {abs(np.exp(v) - 1):.0%}" for n, v in items[:top]]


# ============================================================================== 1. Underwriter
DEFAULT_UW = {"accept_max": 55, "decline_min": 85, "authority_tiv": 2_000_000, "target_lr": B.TARGET_LR}


def underwrite(subs: pd.DataFrame, bnd: dict) -> pd.DataFrame:
    m = rating_model(subs)
    lr = m.expected_loss / subs.quoted_premium
    score = (100 * (1 - np.exp(-lr / bnd["target_lr"] * 0.9))).round(0)
    out = subs[["submission_id", "applicant", "product", "state", "cat_zone", "tiv", "quoted_premium"]].copy()
    out["expected_loss"] = m.expected_loss.round(0)
    out["expected_lr"] = lr.round(2)
    out["risk_score"] = score
    rec, why, modify = [], [], []
    for i, r in out.iterrows():
        drivers = explain(m.loc[i])
        if r.risk_score >= bnd["decline_min"]:
            rec.append("Decline")
        elif r.tiv > bnd["authority_tiv"]:
            rec.append("Refer (over authority)")
        elif r.risk_score > bnd["accept_max"]:
            rec.append("Modify terms")
        else:
            rec.append("Accept")
        why.append("; ".join(drivers) or "No driver moves expected loss by more than 2%")
        s = subs.loc[i]
        opts = []
        if s["product"] in ("Homeowners", "Commercial Property") and s.roof_age > 20:
            opts.append("roof inspection or replacement")
        if s["product"] in ("Homeowners",) and not s.leak_sensor:
            opts.append("water-leak sensor (-18% frequency)")
        if s.deductible < 2500 and s["product"] != "Cyber":
            opts.append("deductible to $2,500")
        if s["product"] == "Cyber" and not s.mfa:
            opts.append("require MFA")
        price = max(r.expected_loss / bnd["target_lr"], 0)
        if price > r.quoted_premium * 1.05:
            opts.append(f"premium to ${price:,.0f}")
        modify.append("; ".join(opts))
    out["si_recommendation"], out["why"], out["suggested_terms"] = rec, why, modify
    return out


def concentration(p: pd.DataFrame, limit_share: float = 0.30) -> pd.DataFrame:
    prop = p[p["product"].isin(["Homeowners", "Commercial Property"])]
    g = prop.groupby(["state", "cat_zone"]).agg(policies=("policy_no", "count"), tiv=("tiv", "sum")).reset_index()
    g["share_of_tiv"] = (g.tiv / prop.tiv.sum()).round(3)
    g["status"] = np.where(g.share_of_tiv > limit_share, "Over appetite",
                           np.where(g.share_of_tiv > limit_share * 0.8, "Watch", "Within appetite"))
    return g.sort_values("tiv", ascending=False)


# ============================================================================== 2. Pricing analyst
def rate_adequacy(p: pd.DataFrame, c: pd.DataFrame, by=("product", "state"), target: float = B.TARGET_LR) -> pd.DataFrame:
    h = c[(c.accident_year >= 2023) & (c.accident_year <= 2025)].merge(p[["policy_no", *[b for b in by if b not in c]]],
                                                                       on="policy_no", how="left") if any(b not in c for b in by) else \
        c[(c.accident_year >= 2023) & (c.accident_year <= 2025)]
    trend = 1.04 ** (2026.5 - h.accident_year)
    h = h.assign(trended=h.ultimate_true * trend)
    loss = h.groupby(list(by)).agg(losses=("trended", "sum"), claims=("claim_no", "count")) / [3, 3]
    prem = p.groupby(list(by)).agg(premium=("premium", "sum"), policies=("policy_no", "count"))
    t = prem.join(loss, how="left").fillna(0)
    t["loss_ratio"] = (t.losses / t.premium).round(3)
    t["credibility"] = np.minimum(1, np.sqrt(t.claims * 3 / 1082)).round(2)      # classical full credibility: 1,082 claims
    overall = t.losses.sum() / t.premium.sum()
    t["indicated_change"] = ((t.credibility * t.loss_ratio + (1 - t.credibility) * overall) / target - 1).round(3)
    t["si_flag"] = np.select([t.indicated_change > 0.08, t.indicated_change < -0.08], ["Rate inadequate", "Possibly over-priced"], "Adequate")
    return t.reset_index().sort_values("indicated_change", ascending=False)


def leakage(p: pd.DataFrame) -> pd.DataFrame:
    d = p.assign(gap=p.rate_plan_premium - p.premium)
    lk = d[d.gap > d.rate_plan_premium * 0.05].copy()
    lk["leak_pct"] = (lk.gap / lk.rate_plan_premium).round(3)
    return lk[["policy_no", "product", "state", "agent_id", "rate_plan_premium", "premium", "gap", "leak_pct"]].sort_values("gap", ascending=False)


def simulate_rates(p: pd.DataFrame, c: pd.DataFrame, changes: dict, n: int = 2000, seed: int = RNG_SEED) -> pd.DataFrame:
    """changes: {(product, state) or product: pct}. Monte Carlo over trend, retention elasticity and cat load."""
    rng = np.random.default_rng(seed)
    adq = rate_adequacy(p, c, by=("product", "state"))
    pct = np.array([changes.get((r["product"], r["state"]), changes.get(r["product"], 0.0)) for r in adq.to_dict("records")])
    trend = rng.normal(0.05, 0.02, (n, 1))
    elastic = rng.normal(-0.8, 0.25, (n, 1))
    cat = rng.lognormal(0, 0.25, (n, 1))
    retention = np.clip(0.88 + elastic * pct / 100, 0.5, 0.99)
    prem = (adq.premium.values * (1 + pct / 100)) * retention
    loss = adq.losses.values * (1 + trend) * retention * np.where(adq["product"].isin(["Homeowners", "Commercial Property"]).values, cat, 1)
    out = pd.DataFrame({"premium": prem.sum(1), "losses": loss.sum(1)})
    out["loss_ratio"] = out.losses / out.premium
    out["policies_kept"] = (retention * adq.policies.values).sum(1)
    return out


# ============================================================================== 3. Catastrophe underwriter
PERIL_ZONE = {"Hurricane": "Coastal hurricane", "Wildfire": "Wildfire WUI", "Hail": "Hail belt"}
PERIL_RATE = {"Hurricane": 0.55, "Wildfire": 0.45, "Hail": 1.6}            # events per year hitting the book's regions


def cat_event_set(p: pd.DataFrame, years: int = 5000, seed: int = RNG_SEED) -> pd.DataFrame:
    """Synthetic stochastic event set -> one row per event: year, peril, state, intensity, loss."""
    rng = np.random.default_rng(seed)
    prop = p[p["product"].isin(["Homeowners", "Commercial Property", "Personal Auto"])]
    rows = []
    for peril, rate in PERIL_RATE.items():
        st_list = [s for s, v in B.STATES.items() if v[2] == peril]
        expo = {s: prop[(prop.state == s)] for s in st_list}
        k = rng.poisson(rate, years)
        for y in np.flatnonzero(k):
            for _ in range(k[y]):
                s = rng.choice(st_list)
                e = expo[s]
                inten = rng.pareto(2.2) + 0.2
                hit = rng.random(len(e)) < min(0.9, 0.12 + 0.18 * inten)
                zone_mult = np.where(e.cat_zone.values == PERIL_ZONE[peril], 1.0, 0.25)
                auto = np.where(e["product"].values == "Personal Auto", 0.6 if peril == "Hail" else 0.15, 1.0)
                dr = np.clip(0.0008 * inten ** 1.6 * zone_mult * auto * rng.lognormal(0, 0.5, len(e)), 0, 1)
                loss = float((e.tiv.values * dr * hit).sum() * 40)       # x40: the book is a 1-in-40 sample of the company
                rows.append((y, peril, s, round(inten, 2), loss))
    return pd.DataFrame(rows, columns=["year", "peril", "state", "intensity", "loss"])


def ep_curve(events: pd.DataFrame, years: int = 5000, net=None) -> dict:
    loss = events.loss if net is None else net(events.loss)
    occ = events.assign(l=loss).groupby("year").l.max().reindex(range(years), fill_value=0)
    agg = events.assign(l=loss).groupby("year").l.sum().reindex(range(years), fill_value=0)
    rp = {f"1-in-{r}": (float(np.quantile(occ, 1 - 1 / r)), float(np.quantile(agg, 1 - 1 / r))) for r in (10, 50, 100, 200, 250)}
    return {"AAL": float(agg.mean()), "OEP_AEP": rp, "occ": occ, "agg": agg}


def event_impact(p: pd.DataFrame, peril: str, lat: float, lon: float, radius_km: float, intensity: float) -> dict:
    d = np.hypot((p.lat - lat) * 111, (p.lon - lon) * 111 * np.cos(np.radians(lat)))
    hit = p[(d <= radius_km) & p["product"].isin(["Homeowners", "Commercial Property", "Personal Auto"])].copy()
    if hit.empty:
        return {"policies": 0, "tiv": 0, "p10": 0, "p50": 0, "p90": 0, "by_product": pd.DataFrame()}
    closeness = 1 - d[hit.index] / radius_km
    zone = np.where(hit.cat_zone == PERIL_ZONE.get(peril, ""), 1.0, 0.35)
    base = (0.002 * intensity ** 1.6 * (0.3 + closeness) * zone * hit.tiv).values
    sims = np.random.default_rng(RNG_SEED).lognormal(0, 0.45, (500, len(hit))) * base
    tot = sims.sum(1) * 40
    hit["est_loss"] = base * 40
    return {"policies": len(hit), "tiv": float(hit.tiv.sum() * 40), "p10": float(np.quantile(tot, .1)),
            "p50": float(np.quantile(tot, .5)), "p90": float(np.quantile(tot, .9)),
            "by_product": hit.groupby("product").agg(policies=("policy_no", "count"), est_loss=("est_loss", "sum")).reset_index()}


# ============================================================================== 4. Claims adjuster
def reserve_recommendation(c: pd.DataFrame) -> pd.DataFrame:
    """For each open claim: P10/P50/P90 ultimate from similar closed claims, scaled by the image damage estimate."""
    closed = c[(c.status == "Closed") & (c.ultimate_true > 0)]
    ref = closed.groupby(["product", "cause"]).ultimate_true.apply(lambda s: np.log(s).agg(["mean", "std", "count"]).tolist())
    rows = []
    for r in c[c.status == "Open"].itertuples():
        mu, sd, n = ref.get((r.product, r.cause), [np.log(max(r.paid_to_date, 1000)), 1.0, 0])
        sd = sd if n >= 5 and sd > 0 else 1.0
        adj = 0.0
        if not np.isnan(r.image_damage_score):
            adj = (r.image_damage_score - 50) / 50 * 0.6 * r.image_confidence
        if r.injury:
            adj += 0.5
        if r.attorney:
            adj += 0.35
        m = mu + adj
        p10, p50, p90 = np.exp(m - 1.2816 * sd * 0.7), np.exp(m), np.exp(m + 1.2816 * sd * 0.7)
        p50 = max(p50, r.paid_to_date * 1.05)
        rows.append({"claim_no": r.claim_no, "rec_ultimate_p50": round(p50, -2), "p10": round(max(p10, r.paid_to_date), -2),
                     "p90": round(max(p90, p50), -2), "rec_reserve": round(max(p50 - r.paid_to_date, 0), -2),
                     "similar_claims": int(n)})
    return pd.DataFrame(rows)


def liability(c: pd.DataFrame) -> pd.Series:
    """Probability the insured is liable (auto third-party claims), from simple, explainable features."""
    z = -0.3 + 1.2 * c.cause.isin(["Collision"]) + 0.8 * c.injury - 0.4 * c.attorney + 0.3 * (c.report_date == c.accident_date)
    return (1 / (1 + np.exp(-z))).where(c["product"] == "Personal Auto")


# ============================================================================== 5. SIU
def fraud_network(c: pd.DataFrame, min_claims: int = 3) -> tuple[pd.DataFrame, dict]:
    """Union claims that share a phone, an address, a repair vendor + attorney pair; score each connected group."""
    recent = c[c.accident_year >= 2024].reset_index(drop=True)
    parent = list(range(len(recent)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    links = defaultdict(list)
    for col in ("claimant_phone", "claimant_address"):
        for v, g in recent.groupby(col).groups.items():
            if len(g) > 1:
                links[(col, v)] = list(g)
    for (v, a), g in recent[recent.attorney_id != ""].groupby(["vendor_id", "attorney_id"]).groups.items():
        if len(g) > 1:
            links[("vendor+attorney", f"{v}+{a}")] = list(g)
    for idx in links.values():
        for j in idx[1:]:
            parent[find(j)] = find(idx[0])
    groups = defaultdict(list)
    for i in range(len(recent)):
        groups[find(i)].append(i)
    rows, members = [], {}
    for k, idx in groups.items():
        if len(idx) < min_claims:
            continue
        g = recent.loc[idx]
        shared = [f"{col.replace('claimant_', '')} {v}" for (col, v), ii in links.items() if set(ii) & set(idx)]
        lag = (pd.to_datetime(g.report_date) - pd.to_datetime(g.accident_date)).dt.days.mean()
        anomaly = min(100, 12 * len(g) + 6 * len(shared) + (15 if lag > 10 else 0) + 10 * g.attorney.mean())
        gid = f"N{len(rows) + 1:02d}"
        rows.append({"network": gid, "claims": len(g), "shared_links": len(shared), "incurred": float((g.paid_to_date + g.case_reserve).sum()),
                     "avg_report_lag_days": round(lag, 1), "attorney_share": round(g.attorney.mean(), 2), "si_score": round(anomaly),
                     "evidence": "; ".join(shared[:6])})
        members[gid] = g
    out = pd.DataFrame(rows)
    if len(out):
        out = out.sort_values("si_score", ascending=False).reset_index(drop=True)
    return out, members


# ============================================================================== 6. Loss control
MITIGATIONS = [  # (name, applies, frequency reduction, cost $)
    ("Roof replacement or reinforcement", lambda s: s["product"] in ("Homeowners", "Commercial Property") and s.roof_age > 18, 0.25, 12000),
    ("Water-leak sensors with auto shut-off", lambda s: s["product"] in ("Homeowners", "Commercial Property") and not s.leak_sensor, 0.18, 400),
    ("Defensible space and ember-resistant vents", lambda s: s.cat_zone == "Wildfire WUI", 0.25, 3500),
    ("Hurricane shutters and opening protection", lambda s: s.cat_zone == "Coastal hurricane", 0.22, 6000),
    ("Automatic sprinklers", lambda s: s["product"] == "Commercial Property" and s.construction == "Frame", 0.35, 45000),
    ("MFA and offline backups", lambda s: s["product"] == "Cyber" and (not s.mfa or not s.backups), 0.35, 2500),
]


def site_risk(p: pd.DataFrame) -> pd.DataFrame:
    m = rating_model(p)
    s = p[p["product"] != "Personal Auto"].copy()
    s["expected_loss"] = m.loc[s.index, "expected_loss"]
    s["site_score"] = np.clip(40 + (100 - s.aerial_roof_score) * 0.35 + 8 * s.iot_alerts_12m + 10 * (s.cat_zone != "Low")
                              + 6 * s.prior_claims, 0, 100).round(0)
    recs, red, cost = [], [], []
    for _, r in s.iterrows():
        ms = [(n, f, c_) for n, ok, f, c_ in MITIGATIONS if ok(r)]
        recs.append("; ".join(n for n, _, _ in ms))
        red.append(r.expected_loss * (1 - np.prod([1 - f for _, f, _ in ms])) if ms else 0.0)
        cost.append(sum(c_ for _, _, c_ in ms))
    s["recommendations"], s["expected_loss_reduction"], s["mitigation_cost"] = recs, np.round(red, 0), cost
    s["visit_priority"] = (s.expected_loss_reduction * (0.5 + s.site_score / 100)).round(0)
    return s.sort_values("visit_priority", ascending=False)[
        ["policy_no", "product", "state", "cat_zone", "tiv", "site_score", "aerial_roof_score", "iot_alerts_12m",
         "expected_loss", "recommendations", "expected_loss_reduction", "mitigation_cost", "visit_priority"]]


# ============================================================================== 7. Actuary
def triangle(pay: pd.DataFrame, product: str | None = None) -> pd.DataFrame:
    d = pay if product is None else pay[pay["product"] == product]
    t = d.groupby(["accident_year", "dev_year"]).amount.sum().unstack().sort_index()
    return t.cumsum(axis=1).where(t.notna().cumsum(axis=1) > 0)


def chain_ladder(tri: pd.DataFrame, boot: int = 1000, seed: int = RNG_SEED) -> dict:
    t = tri.copy()
    cols = list(t.columns)
    ldf, ratios = [], []
    for a, b in zip(cols[:-1], cols[1:]):
        m = t[a].notna() & t[b].notna()
        ldf.append(t.loc[m, b].sum() / t.loc[m, a].sum() if m.any() else 1.0)
        ratios.append((t.loc[m, b] / t.loc[m, a]).values if m.any() else np.array([1.0]))
    cdf = np.cumprod(ldf[::-1])[::-1].tolist() + [1.0]
    latest = t.ffill(axis=1).iloc[:, -1]
    last_dev = t.notna().sum(axis=1)
    ult = latest * [cdf[int(k) - 1] for k in last_dev]
    ibnr = ult - latest
    rng = np.random.default_rng(seed)
    sims = []
    for _ in range(boot):
        l2 = [rng.choice(r) for r in ratios]
        c2 = np.cumprod(l2[::-1])[::-1].tolist() + [1.0]
        sims.append(float((latest * [c2[int(k) - 1] for k in last_dev]).sum() - latest.sum()))
    sims = np.array(sims)
    return {"ldf": ldf, "cdf": cdf, "table": pd.DataFrame({"paid_to_date": latest, "cdf": [cdf[int(k) - 1] for k in last_dev],
                                                            "ultimate": ult, "ibnr": ibnr}).round(0),
            "ibnr_total": float(ibnr.sum()), "p50": float(np.quantile(sims, .5)), "p75": float(np.quantile(sims, .75)),
            "p995": float(np.quantile(sims, .995)), "sims": sims}


CANDIDATES = ["territory", "roof_age", "construction", "protection_class", "prior_claims", "credit_tier", "leak_sensor",
              "cat_zone", "driver_age", "mfa", "aerial_roof_score", "iot_alerts_12m", "tenure_years", "year_built", "deductible"]


def feature_discovery(p: pd.DataFrame, c: pd.DataFrame, product: str = "Homeowners") -> pd.DataFrame:
    pp = p[p["product"] == product].copy()
    n = c[(c.accident_year.between(2021, 2025))].groupby("policy_no").size()
    pp["claims"] = pp.policy_no.map(n).fillna(0) / 5
    rows = []
    for f in CANDIDATES:
        if pp[f].nunique() < 2:
            continue
        x = pp[f]
        b = pd.qcut(x.rank(method="first"), 5, labels=False) if x.dtype.kind in "if" and x.nunique() > 6 else x.astype(str)
        g = pp.groupby(b).claims.agg(["mean", "count"])
        g = g[g["count"] >= 20]
        if len(g) < 2:
            continue
        lift = g["mean"].max() / max(g["mean"].min(), 1e-6)
        overall = pp.claims.mean()
        chi = float((((g["mean"] - overall) ** 2) * g["count"] / max(overall, 1e-6)).sum())
        rows.append({"feature": f, "frequency_lift": round(lift, 2), "signal_strength": round(chi, 1),
                     "highest_band": str(g["mean"].idxmax()), "in_rating_plan": f in ("territory", "roof_age", "construction",
                                                                                    "protection_class", "prior_claims", "credit_tier", "deductible")})
    out = pd.DataFrame(rows).sort_values("signal_strength", ascending=False)
    out["si_note"] = np.where(~out.in_rating_plan & (out.frequency_lift > 1.3), "Candidate new rating variable", "")
    return out


def model_monitor(p: pd.DataFrame, c: pd.DataFrame) -> pd.DataFrame:
    """Actual vs expected claim counts by quarter, with a recalibration factor and drift alert."""
    m = rating_model(p)
    exp_freq = (m.expected_loss / np.array([B.PRODUCTS[x][2] for x in p["product"]])).sum() / 4
    c2 = c[c.accident_year >= 2024].copy()
    c2["q"] = pd.to_datetime(c2.accident_date).dt.to_period("Q").astype(str)
    a = c2.groupby("q").size()
    out = pd.DataFrame({"actual": a, "expected": np.round(exp_freq * np.array([1.04 ** ((int(q[:4]) - 2024) + (int(q[-1]) - 1) / 4) for q in a.index]), 1)})
    out["a_to_e"] = (out.actual / out.expected).round(2)
    out["alert"] = np.where((out.a_to_e - 1).abs() > 0.15, "Drift: review", "")
    return out.reset_index().rename(columns={"index": "quarter", "q": "quarter"})


# ============================================================================== 8. Enterprise risk / capital
DEFAULT_ERM = {"available_capital": 900_000_000, "max_net_cat_share": 0.25, "max_zone_share": 0.30, "min_solvency": 1.5}


def capital(p: pd.DataFrame, c: pd.DataFrame, events: pd.DataFrame, cl: dict, net_fn, bnd: dict) -> dict:
    prem = p.premium.sum() * 40
    lr_sd = 0.08
    premium_risk = 2.576 * lr_sd * prem
    reserve_risk = (cl["p995"] - cl["p50"]) * 40
    cat_net = ep_curve(events, net=net_fn)["OEP_AEP"]["1-in-200"][1]
    market_credit = 0.06 * bnd["available_capital"]
    comps = np.array([premium_risk, reserve_risk, cat_net, market_credit])
    corr = np.array([[1, .5, .25, .25], [.5, 1, .25, .25], [.25, .25, 1, .25], [.25, .25, .25, 1]])
    total = float(np.sqrt(comps @ corr @ comps))
    return {"components": pd.DataFrame({"risk": ["Premium risk", "Reserve risk", "Catastrophe risk (net, 1-in-200)", "Market and credit"],
                                        "capital": comps.round(-5)}),
            "undiversified": float(comps.sum()), "required": total, "solvency_ratio": bnd["available_capital"] / total,
            "cat_net_200": cat_net}


# ============================================================================== 9. Reinsurance
def xol(ret: float, lim: float):
    return lambda loss: loss - np.clip(loss - ret, 0, lim)


def optimize_cat_xol(events: pd.DataFrame, bnd: dict, years: int = 5000) -> pd.DataFrame:
    gross = ep_curve(events)
    rows = []
    for ret in (50e6, 100e6, 150e6, 250e6):
        for lim in (250e6, 500e6, 750e6, 1000e6):
            rec = np.clip(events.loss - ret, 0, lim)
            el = float(rec.groupby(events.year).sum().reindex(range(years), fill_value=0).mean())
            attach_prob = float((events.groupby("year").loss.max().reindex(range(years), fill_value=0) > ret).mean())
            price = el * (1.6 + 0.8 * (1 - min(attach_prob * 5, 1))) + 0.01 * lim       # synthetic market pricing
            net = ep_curve(events, net=xol(ret, lim))
            net200 = net["OEP_AEP"]["1-in-200"][1]
            cost = price - el + 0.10 * net200                                          # margin + cost of capital at 10%
            rows.append({"retention": ret, "limit": lim, "expected_recovery": round(el, -4), "premium": round(price, -4),
                         "rate_on_line": round(price / lim, 3), "net_1_in_200": round(net200, -5),
                         "within_appetite": net200 <= bnd["max_net_cat_share"] * bnd["available_capital"],
                         "total_cost": round(cost, -4)})
    out = pd.DataFrame(rows)
    ok = out[out.within_appetite]
    best = (ok if len(ok) else out).total_cost.idxmin()
    out["si_choice"] = np.where(out.index == best, "SI² recommended", "")
    return out.sort_values("total_cost").reset_index(drop=True), gross


def counterparty(reins: pd.DataFrame, expected_recoveries: float) -> pd.DataFrame:
    pd_ = {"A+": 0.0005, "A": 0.001, "A-": 0.0015, "BBB+": 0.004}
    r = reins.copy()
    r["default_prob_1y"] = [0.0 if c else pd_.get(x, 0.01) for x, c in zip(r.rating, r.collateralized)]
    r["exposure"] = (r.share * expected_recoveries).round(-3)
    r["expected_credit_loss"] = (r.exposure * r.default_prob_1y * 0.5).round(0)
    r["si_note"] = np.select([r.share > 0.25, r.rating.str.startswith("BBB")],
                             ["Concentration above 25% of the program", "Below A- rating: consider collateral"], "")
    return r


# ============================================================================== 10-12. Distribution, service, product
def coverage_gaps(p: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for r in p.itertuples():
        gaps = []
        if r.product in ("Homeowners", "Commercial Property") and r.tiv < 0.9 * r.replacement_cost:
            gaps.append(("Under-insured", f"Coverage ${r.tiv:,.0f} vs replacement cost ${r.replacement_cost:,.0f}", 3))
        if r.product == "Homeowners" and r.cat_zone == "Coastal hurricane" and not r.has_flood:
            gaps.append(("No flood cover in a coastal zone", "Offer flood policy", 3))
        if r.product == "Homeowners" and not r.has_umbrella and r.tiv > 600000:
            gaps.append(("No umbrella for a high-value home", "Offer $1M umbrella", 2))
        if r.product == "Personal Auto" and r.liability_limit < 300000:
            gaps.append(("Low liability limit", f"${r.liability_limit:,.0f}: suggest 300/500 or higher", 2))
        if r.product == "Homeowners" and r.tiv > 1.15 * r.replacement_cost:
            gaps.append(("Possibly over-insured", "Review coverage A vs replacement cost", 1))
        if r.product == "Cyber" and not r.mfa:
            gaps.append(("Cyber controls gap", "MFA lowers premium and risk", 2))
        for g, a, pr in gaps:
            rows.append({"policy_no": r.policy_no, "customer_id": r.customer_id, "agent_id": r.agent_id, "product": r.product,
                         "state": r.state, "gap": g, "advice": a, "priority": pr})
    return pd.DataFrame(rows).sort_values("priority", ascending=False)


def competitive(p: pd.DataFrame) -> pd.DataFrame:
    g = p.groupby(["product", "state"]).agg(our_premium=("premium", "sum"), market=("market_premium", "sum")).reset_index()
    g["price_index"] = (g.our_premium / g.market).round(2)
    g["position"] = np.select([g.price_index > 1.08, g.price_index < 0.92], ["Above market", "Below market"], "At market")
    return g


def retention(p: pd.DataFrame, c: pd.DataFrame) -> pd.DataFrame:
    recent = c[c.accident_year >= 2025].groupby("policy_no").size()
    s = p.copy()
    s["recent_claims"] = s.policy_no.map(recent).fillna(0)
    z = (-2.2 + 0.09 * s.rate_change_pct + 0.5 * s.late_payments_12m + 0.9 * s.complaints_12m + 0.3 * s.recent_claims
         - 0.08 * s.tenure_years + 0.6 * (s.premium > s.market_premium * 1.08))
    s["lapse_risk"] = (1 / (1 + np.exp(-z))).round(2)
    drivers, nba = [], []
    for r in s.itertuples():
        d = []
        if r.rate_change_pct > 10:
            d.append(f"renewal increase {r.rate_change_pct:.0f}%")
        if r.complaints_12m:
            d.append(f"{r.complaints_12m} complaint(s)")
        if r.late_payments_12m >= 2:
            d.append("late payments")
        if r.premium > r.market_premium * 1.08:
            d.append("priced above market")
        drivers.append(", ".join(d) or "no strong driver")
        nba.append("Call: review coverage and discounts" if r.premium > r.market_premium * 1.08 else
                   "Resolve the complaint first" if r.complaints_12m else
                   "Offer payment plan / autopay" if r.late_payments_12m >= 2 else
                   "Explain the increase and offer a higher deductible" if r.rate_change_pct > 10 else "Standard renewal")
    s["drivers"], s["next_best_action"] = drivers, nba
    return s.sort_values("lapse_risk", ascending=False)


def product_performance(p: pd.DataFrame, c: pd.DataFrame) -> pd.DataFrame:
    t = rate_adequacy(p, c, by=("product",))
    return t[["product", "policies", "premium", "losses", "loss_ratio", "indicated_change", "si_flag"]]


def coverage_demand(c: pd.DataFrame) -> pd.DataFrame:
    d = c[c.denied_reason != ""].groupby(["product", "cause", "denied_reason"]).agg(denied_claims=("claim_no", "count")).reset_index()
    return d.sort_values("denied_claims", ascending=False)


def simulate_endorsement(p: pd.DataFrame, c: pd.DataFrame, cause: str, price: float, take_up: float, limit: float) -> dict:
    ho = p[p["product"] == "Homeowners"]
    freq = len(c[(c.cause == cause) & (c.accident_year.between(2021, 2025))]) / 5 / len(ho)
    sev = min(limit, 9000 if cause == "Sewer backup" else 22000)
    buyers = len(ho) * take_up * 40
    prem = buyers * price
    loss = buyers * freq * 1.3 * sev                    # anti-selection load 1.3
    return {"buyers": buyers, "premium": prem, "expected_losses": loss, "loss_ratio": loss / prem if prem else 0,
            "frequency": freq, "break_even_price": freq * 1.3 * sev / B.TARGET_LR}


# ============================================================================== 13. Data / analytics
def data_quality(b: dict) -> pd.DataFrame:
    rows = []
    keys = {"policies": ["policy_no"], "claims": ["claim_no"], "payments": ["claim_no", "dev_year"], "submissions": ["submission_id"]}
    for name, key in keys.items():
        df = b[name]
        rows.append({"dataset": name, "rows": len(df), "completeness": round(1 - df.isna().mean().mean(), 3),
                     "duplicate_keys": int(df.duplicated(key).sum()),
                     "freshness": B.VAL.isoformat()})
    c = b["claims"]
    checks = [("Claims reported before the accident", int((pd.to_datetime(c.report_date) < pd.to_datetime(c.accident_date)).sum())),
              ("Open claims with no reserve", int(((c.status == "Open") & (c.case_reserve <= 0)).sum())),
              ("Policies with premium below rate plan by >5%", int((b["policies"].premium < b["policies"].rate_plan_premium * 0.95).sum())),
              ("Claims with no policy", int((~c.policy_no.isin(b["policies"].policy_no)).sum()))]
    return pd.DataFrame(rows), pd.DataFrame(checks, columns=["rule", "failures"])


# ============================================================================== 14. Compliance
def fairness(decisions: pd.DataFrame, group_col: str, favorable: str = "Accept") -> pd.DataFrame:
    """Adverse impact ratio (four-fifths rule of thumb) of favourable outcomes by group."""
    if decisions.empty:
        return pd.DataFrame()
    g = decisions.groupby(group_col).apply(lambda d: pd.Series({"decisions": len(d), "favorable_rate": (d.outcome == favorable).mean()}),
                                           include_groups=False)
    best = g.favorable_rate.max() or 1
    g["impact_ratio"] = (g.favorable_rate / best).round(2)
    g["si_flag"] = np.where(g.impact_ratio < 0.8, "Below 0.80: review for unfair discrimination", "")
    return g.reset_index()


RESTRICTED_FACTORS = {  # editable in the app; illustrative, to be confirmed with counsel
    ("credit_tier", "Personal Auto"): ["CA", "MA", "HI"],
}


# ============================================================================== 15. Strategy / emerging risk
EXPOSURE_RULE = {  # emerging risk -> (products affected, filter on policies, assumed severity shock)
    "Wildfire in the WUI": (["Homeowners", "Commercial Property"], lambda p: p.cat_zone == "Wildfire WUI", 0.40),
    "Secondary perils (hail, wind)": (["Homeowners", "Commercial Property", "Personal Auto"], lambda p: p.cat_zone == "Hail belt", 0.25),
    "Hurricane severity": (["Homeowners", "Commercial Property"], lambda p: p.cat_zone == "Coastal hurricane", 0.25),
    "Social inflation": (["Personal Auto", "Commercial Property"], lambda p: p["product"] == "Personal Auto", 0.20),
    "Vehicle repair cost inflation": (["Personal Auto"], lambda p: p["product"] == "Personal Auto", 0.15),
    "Cyber systemic event": (["Cyber"], lambda p: p["product"] == "Cyber", 0.60),
    "Flood outside mapped zones": (["Homeowners"], lambda p: (p["product"] == "Homeowners") & ~p.has_flood, 0.10),
    "AI-enabled fraud": (["Personal Auto", "Homeowners", "Cyber"], lambda p: p["product"] != "Commercial Property", 0.05),
    "PFAS liability": (["Commercial Property"], lambda p: p["product"] == "Commercial Property", 0.10),
    "Extreme heat": (["Commercial Property"], lambda p: (p["product"] == "Commercial Property") & p.state.isin(["TX", "FL", "LA", "CA"]), 0.08),
    "AI governance and fairness rules": (["Personal Auto", "Homeowners"], lambda p: p["product"].isin(["Personal Auto", "Homeowners"]), 0.0),
}


def horizon_scan(signals: pd.DataFrame, p: pd.DataFrame) -> pd.DataFrame:
    g = signals.groupby("risk").agg(signals=("signal", "count"), momentum=("momentum", "mean"),
                                    categories=("category", lambda s: ", ".join(sorted(set(s))))).reset_index()
    prem = []
    for r in g.risk:
        rule = EXPOSURE_RULE.get(r)
        prem.append(float(p[rule[1](p)].premium.sum() * 40) if rule else 0.0)
    g["premium_exposed"] = prem
    tot = p.premium.sum() * 40
    g["priority"] = (g.momentum * 12 + g.signals * 6 + 40 * np.array(prem) / tot).round(0)
    return g.sort_values("priority", ascending=False)


def scenario(risk: str, p: pd.DataFrame, years: int = 5, severity: float | None = None) -> dict:
    prods, filt, shock = EXPOSURE_RULE.get(risk, ([], lambda x: x.index == -1, 0.0))
    shock = shock if severity is None else severity
    expo = p[filt(p)]
    losses = expo.true_expected_loss.sum() * 40
    path = [{"year": 2026 + y, "extra_losses": losses * shock * (1 + 0.15 * (y - 1)), "loss_ratio_points":
             round(100 * losses * shock * (1 + 0.15 * (y - 1)) / (p.premium.sum() * 40), 1)} for y in range(1, years + 1)]
    return {"policies": len(expo) * 40, "premium": float(expo.premium.sum() * 40), "path": pd.DataFrame(path),
            "products": prods, "shock": shock}
