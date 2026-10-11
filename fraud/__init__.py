
"""SI² Fraud Engine: detect → prevent → monitor.

Every rule is keyed to a catalog fraud_id. run() replays the book through all enabled rules and returns
alerts with evidence, amount at risk and the action the control takes (block, hold, verify, refer, recover).
"""
from __future__ import annotations

import datetime as dt
import math

import pandas as pd

from . import catalog
from .data import FX, ZIP_INFO

DEFAULTS = {
    "late_remit_days": 30, "early_attorney_days": 3, "early_attorney_reserve": 10000, "contents_ratio": 0.30,
    "bank_change_days": 3, "ring_min_claims": 3, "repeat_claimant_claims": 3, "override_pct": -20.0,
    "override_pairs": 3, "steer_share": 0.60, "steer_min_jobs": 6, "steer_pvalue": 0.01, "split_band": 0.90, "bordereau_ratio": 0.80,
    "arson_window_days": 120, "weather_window_days": 3, "ded_tolerance": 0.05, "siu_threshold": 60,
}
ACTION_CLASS = {"Block": "Prevent", "Hold": "Prevent", "Step-up": "Prevent", "Refer": "Investigate",
                "Recover": "Recover"}


def _usd(amount, ccy):
    return round(float(amount or 0) * FX.get(ccy, 1.0), 2)


def run(d: dict, params: dict | None = None, enabled: set | None = None) -> pd.DataFrame:
    p = {**DEFAULTS, **(params or {})}
    cat = catalog.load().set_index("fraud_id")
    pol, clm, cp = d["policies"], d["claims"], d["claim_payments"]
    pay, ext, par, emp = d["premium_payments"], d["external"], d["parties"], d["employees"]
    pidx = pol.set_index("policy_id")
    eidx = ext.set_index("policy_id")
    paid = cp.groupby("claim_id").amount.sum() if len(cp) else pd.Series(dtype=float)
    alerts = []

    def on(fid):
        return enabled is None or fid in enabled

    def add(fid, entity, eid, evidence, amount_usd=0.0, policy_id="", claim_id="", action=None, extra_sev=0):
        c = cat.loc[fid]
        act = action or c.trigger_action.split(";")[0].strip()
        verb = act.split()[0]
        alerts.append({"fraud_id": fid, "domain": c.domain, "fraud_type": c.fraud_type, "entity": entity,
                       "entity_id": eid, "policy_id": policy_id, "claim_id": claim_id, "evidence": evidence,
                       "amount_at_risk": round(amount_usd, 2), "severity": int(min(5, c.severity + extra_sev)),
                       "action": act, "control": ACTION_CLASS.get(verb, "Investigate"), "stage": c.lifecycle_stage,
                       "owner": c.owner})

    def claim_exposure(c):
        return _usd(float(paid.get(c.claim_id, 0)) + float(c.reserve or 0), c.currency)

    terr = lambda z: ZIP_INFO.get(z, {}).get("territory", "")  # noqa: E731

    # ---------------------------------------------------------------- policy & underwriting
    if on("FR-P01"):
        loss_zip = clm.groupby("policy_id").loss_zip.agg(lambda s: set(s))
        for r in pol[pol.lob.isin(["PA", "CA"])].itertuples():
            zs = {r.mailing_zip} | loss_zip.get(r.policy_id, set())
            urban = [z for z in zs if terr(z) == "Urban"]
            if terr(r.risk_zip) == "Rural" and urban:
                add("FR-P01", "policy", r.policy_id, f"Garaged in rural {r.risk_zip}; mailing/loss in urban {', '.join(sorted(urban))}",
                    _usd(r.premium * 0.4, r.currency), r.policy_id)
    if on("FR-P02"):
        for r in pol[(pol.lob == "HO") & (pol.usage == "Owner occupied")].itertuples():
            if bool(eidx.at[r.policy_id, "str_listing_found"]):
                add("FR-P02", "policy", r.policy_id, "Declared owner occupied; short-term rental listing found at the address",
                    _usd(r.limit * 0.01, r.currency), r.policy_id)
    if on("FR-P03"):
        for r in pol[pol.sprinkler_declared == True].itertuples():  # noqa: E712
            if eidx.at[r.policy_id, "inspection_sprinkler"] is False or eidx.at[r.policy_id, "inspection_sprinkler"] == False:  # noqa: E712
                add("FR-P03", "policy", r.policy_id, "Sprinkler declared; inspection found no sprinkler",
                    _usd(r.limit * 0.02, r.currency), r.policy_id)
    if on("FR-P04"):
        for r in pol.itertuples():
            found = int(eidx.at[r.policy_id, "prior_claims_found"] or 0)
            if found >= 2 and found > int(r.prior_claims_declared or 0):
                add("FR-P04", "policy", r.policy_id, f"Declared {r.prior_claims_declared} prior claims; loss history shows {found}",
                    _usd(r.premium * 0.5, r.currency), r.policy_id)
    if on("FR-P05"):
        cc = clm[(clm.driver_party.fillna("") != "")]
        for pid, g in cc.groupby("policy_id"):
            listed = set(str(pidx.at[pid, "drivers"]).split(","))
            un = g[~g.driver_party.isin(listed)]
            if len(un) >= 2:
                add("FR-P05", "policy", pid, f"{len(un)} claims name driver {un.driver_party.iat[0]}, who is not on the policy",
                    sum(claim_exposure(c) for c in un.itertuples()), pid)
    if on("FR-P06"):
        for c in clm.itertuples():
            iss = pidx.at[c.policy_id, "issue_date"]
            if iss > c.loss_date:
                add("FR-P06", "claim", c.claim_id, f"Loss {c.loss_date}; policy issued {iss} (after the loss)",
                    claim_exposure(c), c.policy_id, c.claim_id)

    # ---------------------------------------------------------------- billing
    val = d["valuation_date"]
    if on("FR-B01"):
        for r in pay[(pay.collected_by_agent.fillna("") != "") & pay.remitted_date.isna()].itertuples():
            age = (val - r.date).days
            if age > p["late_remit_days"]:
                ccy = pidx.at[r.policy_id, "currency"]
                add("FR-B01", "policy", r.policy_id, f"Agent {r.collected_by_agent} collected {r.amount:,.2f} on {r.date}; not remitted after {age} days",
                    _usd(r.amount, ccy), r.policy_id)
    if on("FR-B02") and len(d["refunds"]):
        for r in d["refunds"].itertuples():
            payer = set(pay[pay.policy_id == r.policy_id].payer_acct)
            insured = pidx.at[r.policy_id, "insured_party"]
            bc = d["bank_changes"][(d["bank_changes"].entity_id == insured)]
            same_clerk = r.approved_by in set(bc.changed_by)
            if r.to_acct not in payer or same_clerk:
                why = "refund to an account that never paid premium" + ("; same clerk changed the bank details and approved the refund" if same_clerk else "")
                add("FR-B02", "policy", r.policy_id, f"{r.refund_id}: {why}", _usd(r.amount, pidx.at[r.policy_id, "currency"]), r.policy_id)
    if on("FR-B03"):
        for r in pay[pay.status.isin(["Chargeback"])].itertuples():
            cl = clm[clm.policy_id == r.policy_id]
            amt = float(paid[paid.index.isin(cl.claim_id)].sum())
            if amt > 0:
                add("FR-B03", "policy", r.policy_id, f"Premium {r.status.lower()} after {amt:,.2f} of claim payments",
                    _usd(r.amount + amt, pidx.at[r.policy_id, "currency"]), r.policy_id)

    # ---------------------------------------------------------------- claims
    for c in clm.itertuples():
        pr = pidx.loc[c.policy_id]
        if on("FR-C01") and (c.loss_date < pr.eff_date or c.loss_date > pr.exp_date):
            add("FR-C01", "claim", c.claim_id, f"Loss {c.loss_date} outside policy period {pr.eff_date} – {pr.exp_date}",
                claim_exposure(c), c.policy_id, c.claim_id)
        if on("FR-C02") and pr.status == "Cancelled" and pd.notna(pr.cancel_date) and c.loss_date > pr.cancel_date:
            add("FR-C02", "claim", c.claim_id, f"Loss {c.loss_date} after cancellation on {pr.cancel_date}",
                claim_exposure(c), c.policy_id, c.claim_id)
        tot = float(paid.get(c.claim_id, 0))
        if on("FR-C03") and tot > pr.limit:
            add("FR-C03", "claim", c.claim_id, f"Paid {tot:,.2f} against a {pr.limit:,.0f} limit",
                _usd(tot - pr.limit, c.currency), c.policy_id, c.claim_id)
        if on("FR-C09") and c.attorney_id and pd.notna(c.attorney_date):
            lag = (c.attorney_date - c.loss_date).days
            if lag <= p["early_attorney_days"] and c.reserve < p["early_attorney_reserve"]:
                add("FR-C09", "claim", c.claim_id, f"Attorney {c.attorney_id} retained {lag} day(s) after a loss reserved at {c.reserve:,.0f}",
                    claim_exposure(c), c.policy_id, c.claim_id)
        if on("FR-C10") and c.cause in ("Wind", "Hail"):
            ev = d["cat_events"]
            hit = ev[(ev.peril == c.cause) & ev.zips.str.contains(str(c.loss_zip)) &
                     ev.date.apply(lambda x: abs((x - c.loss_date).days) <= p["weather_window_days"])]
            if hit.empty:
                o = d["objects"][d["objects"].object_id == c.object_id].iloc[0]
                extra = []
                if pd.notna(o.get("roof_year")) and o.get("roof_year") and val.year - int(o["roof_year"]) > 20:
                    extra.append(f"roof {val.year - int(o['roof_year'])} years old")
                if eidx.at[c.policy_id, "roof_condition_at_inspection"] == "Damaged":
                    extra.append("roof already damaged at inspection")
                add("FR-C10", "claim", c.claim_id, f"No {c.cause.lower()} event for {c.loss_zip} within {p['weather_window_days']} days of {c.loss_date}"
                    + (f"; {', '.join(extra)}" if extra else ""), claim_exposure(c), c.policy_id, c.claim_id,
                    extra_sev=1 if extra else 0)
        if on("FR-C11") and c.cause == "Fire" and pd.notna(pr.coverage_change_date):
            gap = (c.loss_date - pr.coverage_change_date).days
            nsf = (pay[(pay.policy_id == c.policy_id)].status.isin(["NSF", "Chargeback"])).any()
            vacant = "vacant" in str(c.description).lower()
            if 0 <= gap <= p["arson_window_days"] and (nsf or vacant):
                add("FR-C11", "claim", c.claim_id, f"Limit raised {pr.prior_limit:,.0f} → {pr.limit:,.0f} {gap} days before the fire"
                    + ("; premium bounced" if nsf else "") + ("; building vacant" if vacant else ""),
                    claim_exposure(c), c.policy_id, c.claim_id)
        if on("FR-C12") and c.cause == "Theft" and c.lob == "HO" and c.contents_claimed / pr.limit > p["contents_ratio"]:
            add("FR-C12", "claim", c.claim_id, f"Contents claimed {c.contents_claimed:,.0f} = {c.contents_claimed / pr.limit:.0%} of the dwelling limit",
                _usd(c.contents_claimed, c.currency), c.policy_id, c.claim_id)
        if on("FR-C16") and pd.notna(c.employer_termination_date):
            t = c.employer_termination_date
            if c.report_date > t and (t - c.loss_date).days <= 7:
                add("FR-C16", "claim", c.claim_id, f"Terminated {t}; injury dated {c.loss_date}; reported {c.report_date}",
                    claim_exposure(c), c.policy_id, c.claim_id)
    if on("FR-C04") and len(cp):
        j = cp.merge(clm[["claim_id", "policy_id", "currency"]], on="claim_id")
        for r in j.itertuples():
            ded = pidx.at[r.policy_id, "deductible"]
            if ded > 0 and r.deductible_applied == 0:
                add("FR-C04", "claim", r.claim_id, f"{r.cpay_id} paid {r.amount:,.2f} with no deductible (policy deductible {ded:,.0f})",
                    _usd(ded, r.currency), r.policy_id, r.claim_id)
    if on("FR-C05"):
        o = d["objects"].set_index("object_id")
        k = clm.assign(desc=clm.object_id.map(o.description))
        for _, g in k.groupby(["claimant_party", "loss_date", "desc"]):
            if g.claim_id.nunique() > 1:
                first = g.iloc[0]
                for c in g.iloc[1:].itertuples():
                    add("FR-C05", "claim", c.claim_id, f"Same claimant, object and loss date as {first.claim_id} (policy {first.policy_id})",
                        claim_exposure(c), c.policy_id, c.claim_id)
    if on("FR-C06") and len(cp):
        inv = cp[cp.invoice_no.fillna("") != ""]
        for no, g in inv.groupby("invoice_no"):
            if len(g) > 1:
                c = clm[clm.claim_id == g.claim_id.iat[0]].iloc[0]
                add("FR-C06", "claim", c.claim_id, f"Invoice {no} paid {len(g)} times ({', '.join(g.cpay_id)})",
                    _usd(g.amount.iloc[1:].sum(), c.currency), c.policy_id, c.claim_id)
    if on("FR-C07") and len(d["invoices"]):
        j = d["invoices"].merge(clm[["claim_id", "policy_id", "adjuster_estimate", "currency"]], on="claim_id")
        for r in j.itertuples():
            ded = pidx.at[r.policy_id, "deductible"]
            if ded > 0 and r.adjuster_estimate > 0 and abs(r.amount - r.adjuster_estimate - ded) <= p["ded_tolerance"] * ded:
                add("FR-C07", "claim", r.claim_id, f"{r.vendor_id} invoice {r.amount:,.2f} = adjuster estimate {r.adjuster_estimate:,.2f} + deductible {ded:,.0f}",
                    _usd(ded, r.currency), r.policy_id, r.claim_id)
    if on("FR-C08"):
        for comp, why in rings(d, p["ring_min_claims"]):
            sub = clm[clm.claim_id.isin(comp)]
            for c in sub.itertuples():
                add("FR-C08", "claim", c.claim_id, f"Linked to {len(comp) - 1} other claims by {why}",
                    claim_exposure(c), c.policy_id, c.claim_id)
    if on("FR-C15") and len(d["bank_changes"]) and len(cp):
        bc = d["bank_changes"]
        for r in cp.itertuples():
            m = bc[(bc.new_acct == r.payee_acct)]
            for b in m.itertuples():
                lag = (r.date - b.date).days
                if 0 <= lag <= p["bank_change_days"]:
                    c = clm[clm.claim_id == r.claim_id].iloc[0]
                    add("FR-C15", "claim", r.claim_id, f"{r.cpay_id} {r.amount:,.2f} sent to an account changed {lag} day(s) earlier by {b.changed_by}",
                        _usd(r.amount, c.currency), c.policy_id, r.claim_id)
    if on("FR-C17"):
        for party, g in clm.groupby("claimant_party"):
            if g.claim_id.nunique() >= p["repeat_claimant_claims"] and g.policy_id.nunique() >= 2:
                add("FR-C17", "party", party, f"Claimant on {g.claim_id.nunique()} claims against {g.policy_id.nunique()} policies",
                    sum(claim_exposure(c) for c in g.itertuples()))

    # ---------------------------------------------------------------- reinsurance
    ces, tre = d["cessions"], d["treaties"].set_index("treaty_id")
    if on("FR-R01") and len(ces):
        cc = ces[ces.claim_id.isin(clm.claim_id)]
        for cid, g in cc.groupby("claim_id"):
            loss = float(paid.get(cid, 0))
            if g.recovery_billed.sum() > loss * 1.0001:
                c = clm[clm.claim_id == cid].iloc[0]
                add("FR-R01", "claim", cid, f"Recoveries billed {g.recovery_billed.sum():,.2f} on paid loss {loss:,.2f} across {', '.join(g.treaty_id)}",
                    g.recovery_billed.sum() - loss, c.policy_id, cid)
    if on("FR-R02") and len(ces):
        j = ces.merge(clm[["claim_id", "loss_date", "policy_id"]], on="claim_id")
        for r in j.itertuples():
            t = tre.loc[r.treaty_id]
            if r.loss_date < t.start or r.loss_date > t.end:
                add("FR-R02", "claim", r.claim_id, f"{r.treaty_id} in force {t.start} – {t.end}; loss {r.loss_date}",
                    r.recovery_billed, r.policy_id, r.claim_id)
    if on("FR-R03"):
        for tid, t in tre[tre.aad > 0].iterrows():
            yr = clm[(clm.lob == t.lob) & (clm.loss_date >= t.start) & (clm.loss_date <= t.end) & (clm.country == "US")]
            retained = float(paid[paid.index.isin(yr.claim_id)].sum()) * 0.6
            billed = float(ces[ces.treaty_id == tid].recovery_billed.sum())
            if billed > 0 and retained < t.aad:
                add("FR-R03", "treaty", tid, f"Billed {billed:,.0f}; retained {t.lob} losses {retained:,.0f} are below the {t.aad:,.0f} AAD",
                    billed)
    if on("FR-R04"):
        rei = d["reinsurers"].set_index("reinsurer_id")
        for tid, t in tre.iterrows():
            re_ = rei.loc[t.reinsurer_id]
            if re_.rating == "NR" and (re_.capital_usd < t.limit or not re_.collateral_posted):
                add("FR-R04", "treaty", tid, f"{re_['name']} ({re_.domicile}): unrated, capital {re_.capital_usd:,.0f} vs limit {t.limit:,.0f}, "
                    + ("no collateral" if not re_.collateral_posted else "collateral posted"),
                    float(ces[ces.treaty_id == tid].recovery_billed.sum() - ces[ces.treaty_id == tid].recovery_collected.sum()))
    if on("FR-R05") and len(d["bordereau"]):
        b = d["bordereau"]
        bad = b[b.tiv_reported / b.tiv_actual < p["bordereau_ratio"]]
        if len(bad):
            add("FR-R05", "treaty", bad.treaty_id.iat[0], f"Bordereau under-reports {len(bad)} ZIP(s): {', '.join(bad.zip)}; "
                f"TIV {bad.tiv_reported.sum():,.0f} reported vs {bad.tiv_actual.sum():,.0f} actual",
                0.0)

    # ---------------------------------------------------------------- internal
    emp_phone, emp_bank = dict(zip(emp.phone, emp.emp_id)), dict(zip(emp.bank_acct, emp.emp_id))
    if on("FR-I01"):
        pt = par.set_index("party_id")
        for r in pol[pol.issued_by == "Manual"].itertuples():
            ins = pt.loc[r.insured_party]
            who = emp_phone.get(ins.phone) or emp_bank.get(ins.bank_acct)
            if who:
                nopay = not (pay.policy_id == r.policy_id).any()
                add("FR-I01", "policy", r.policy_id, f"Manually issued by {r.underwriter_id}; insured shares phone/bank with employee {who}"
                    + ("; no premium ever received" if nopay else ""), _usd(r.limit * 0.05, r.currency), r.policy_id)
                for c in clm[clm.policy_id == r.policy_id].itertuples():
                    add("FR-I01", "claim", c.claim_id, f"Claim on employee-linked policy {r.policy_id}",
                        _usd(float(paid.get(c.claim_id, 0)) + c.reserve, c.currency), r.policy_id, c.claim_id)
    if on("FR-I02"):
        ov = pol[pol.rate_override_pct <= p["override_pct"]]
        for (u, a), g in ov.groupby(["underwriter_id", "agent_id"]):
            if len(g) >= p["override_pairs"]:
                for r in g.itertuples():
                    add("FR-I02", "policy", r.policy_id, f"{r.rate_override_pct:.0f}% override by {u} for agent {a} ({len(g)} such policies)",
                        _usd(r.premium * abs(r.rate_override_pct) / 100, r.currency), r.policy_id)
    if on("FR-I03") and len(cp):
        for r in cp[cp.payee_acct.isin(emp_bank)].itertuples():
            c = clm[clm.claim_id == r.claim_id].iloc[0]
            add("FR-I03", "claim", r.claim_id, f"{r.cpay_id} {r.amount:,.2f} paid to the bank account of employee {emp_bank[r.payee_acct]}",
                _usd(r.amount, c.currency), c.policy_id, r.claim_id)
    if on("FR-I04") and len(cp):
        auth = dict(zip(emp.emp_id, emp.authority_limit))
        for (cid, day), g in cp.groupby(["claim_id", "date"]):
            lim = auth.get(g.approved_by.iat[0], 0)
            near = g[(g.amount >= p["split_band"] * lim) & (g.amount < lim)] if lim else g.iloc[0:0]
            if len(near) >= 2:
                c = clm[clm.claim_id == cid].iloc[0]
                add("FR-I04", "claim", cid, f"{len(near)} payments on {day} of {', '.join(f'{x:,.0f}' for x in near.amount)} under {g.approved_by.iat[0]}'s {lim:,.0f} authority",
                    _usd(near.amount.sum(), c.currency), c.policy_id, cid)
    if on("FR-I05") and len(d["invoices"]):
        vt = d["vendors"].set_index("vendor_id").vendor_type
        j = d["invoices"].merge(clm[["claim_id", "adjuster_id", "policy_id", "currency"]], on="claim_id")
        j["trade"] = j.vendor_id.map(vt)
        for (a, trade), g in j.groupby(["adjuster_id", "trade"]):
            if (vt == trade).sum() < 2:
                continue                                   # only one vendor in the trade: no choice to steer
            vc = g.vendor_id.value_counts()
            k, n = int((vt == trade).sum()), len(g)
            chance = sum(math.comb(n, x) * (1 / k) ** x * (1 - 1 / k) ** (n - x) for x in range(vc.iloc[0], n + 1))
            if n >= p["steer_min_jobs"] and vc.iloc[0] / n >= p["steer_share"] and chance < p["steer_pvalue"]:
                v = vc.index[0]
                for r in g[g.vendor_id == v].itertuples():
                    add("FR-I05", "claim", r.claim_id, f"Adjuster {a} sent {vc.iloc[0]} of {len(g)} {trade.lower()} jobs ({vc.iloc[0] / len(g):.0%}) to {v}; chance of this by fair rotation {chance:.2%}",
                        _usd(r.amount, r.currency), r.policy_id, r.claim_id)

    a = pd.DataFrame(alerts, columns=["fraud_id", "domain", "fraud_type", "entity", "entity_id", "policy_id", "claim_id",
                                      "evidence", "amount_at_risk", "severity", "action", "control", "stage", "owner"])
    a.insert(0, "alert_id", [f"AL{i + 1:04d}" for i in range(len(a))])
    return a


def rings(d: dict, min_claims: int = 3) -> list[tuple[set, str]]:
    """Connected claims: different claimants sharing a phone or address, or the same attorney, across claims."""
    clm, par = d["claims"], d["parties"].set_index("party_id")
    c = clm[["claim_id", "claimant_party", "attorney_id"]].copy()
    c["phone"] = c.claimant_party.map(par.phone)
    c["address"] = c.claimant_party.map(par.address)
    parent = {x: x for x in c.claim_id}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    strong = set()
    for key in ("phone", "address"):
        for _, g in c.groupby(key):
            if g.claimant_party.nunique() > 1:
                ids = list(g.claim_id)
                for x in ids[1:]:
                    parent[find(x)] = find(ids[0])
                strong.update(ids)
    for _, g in c[c.attorney_id.fillna("") != ""].groupby("attorney_id"):
        ids = list(g.claim_id)
        for x in ids[1:]:
            parent[find(x)] = find(ids[0])
    comps = {}
    for x in c.claim_id:
        comps.setdefault(find(x), set()).add(x)
    out = []
    for comp in comps.values():
        if len(comp) >= min_claims and comp & strong:
            att = set(c[c.claim_id.isin(comp)].attorney_id.dropna()) - {""}
            why = "shared phones/addresses" + (f" and attorney {', '.join(sorted(att))}" if att else "")
            out.append((comp, why))
    return out


def scores(alerts: pd.DataFrame, d: dict) -> pd.DataFrame:
    """Claim risk score 0-100: each alert on the claim or its policy adds independent evidence,
    score = 100 × (1 − Π(1 − 0.15 × severity)). One severity-5 alert = 75; two severity-3 alerts = 70."""
    clm = d["claims"]
    pol_alerts = alerts[alerts.entity == "policy"].groupby("entity_id").severity.apply(list)
    clm_alerts = alerts[alerts.entity == "claim"].groupby("entity_id").severity.apply(list)
    s = clm[["claim_id", "policy_id", "lob", "country", "cause", "loss_date", "adjuster_id", "reserve", "currency"]].copy()
    vals = []
    for r in s.itertuples():
        q = 1.0
        for x in list(clm_alerts.get(r.claim_id, [])) + list(pol_alerts.get(r.policy_id, [])):
            q *= 1 - 0.15 * x
        vals.append(int(round(100 * (1 - q))))
    s["score"] = vals
    ca = s.claim_id.map(alerts[alerts.entity == "claim"].groupby("entity_id").fraud_id.apply(lambda x: ", ".join(sorted(set(x))))).fillna("")
    pa = s.policy_id.map(alerts[alerts.entity == "policy"].groupby("entity_id").fraud_id.apply(lambda x: ", ".join(sorted(set(x))))).fillna("")
    s["alerts"] = [", ".join(sorted({x for x in (a + ", " + b).split(", ") if x})) for a, b in zip(ca, pa)]
    return s.sort_values(["score", "reserve"], ascending=False)


def evaluate(alerts: pd.DataFrame, truth: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Detection rate against the seeded scenarios."""
    hit = set(zip(alerts.fraud_id, alerts.entity_id))
    t = truth.copy()
    t["detected"] = [(f, e) in hit for f, e in zip(t.fraud_id, t.entity_id)]
    true_keys = set(zip(truth.fraud_id, truth.entity_id))
    seeded_entities = set(truth.entity_id)
    a = alerts.copy()
    a["truth"] = "Seeded scenario"
    other = [(f, e) not in true_keys for f, e in zip(a.fraud_id, a.entity_id)]
    on_seeded = [bool({e, pid, cid} & seeded_entities) for e, pid, cid in zip(a.entity_id, a.policy_id, a.claim_id)]
    a.loc[[o and s for o, s in zip(other, on_seeded)], "truth"] = "Extra rule on a seeded case"
    a.loc[[o and not s for o, s in zip(other, on_seeded)], "truth"] = "Clean data (false positive)"
    return t, {"scenarios": len(t), "detected": int(t.detected.sum()), "alerts": len(a),
               "extra_on_seeded": int((a.truth == "Extra rule on a seeded case").sum()),
               "false_positives": int((a.truth == "Clean data (false positive)").sum()), "alerts_labeled": a}


def monthly(alerts: pd.DataFrame, d: dict) -> pd.DataFrame:
    """Alerts per month by domain, dated by the claim's report date or policy's issue date."""
    clm = d["claims"].set_index("claim_id")
    pol = d["policies"].set_index("policy_id")

    def when(r):
        if r.claim_id and r.claim_id in clm.index:
            return clm.at[r.claim_id, "report_date"]
        if r.policy_id and r.policy_id in pol.index:
            return pol.at[r.policy_id, "issue_date"]
        return d["valuation_date"]
    a = alerts.copy()
    a["month"] = [pd.Timestamp(when(r)).to_period("M").strftime("%Y-%m") for r in a.itertuples()]
    return a.pivot_table(index="month", columns="domain", values="alert_id", aggfunc="count", fill_value=0)

"""Synthetic P&C book for the SI² Fraud Engine.

A clean book (policies, objects, billing, claims, payments, reinsurance) with fraud scenarios seeded on top.
Every seeded scenario is recorded in `truth` so the engine's detection rate can be measured.
All names, numbers and accounts are invented.
"""
from __future__ import annotations

import datetime as dt
import random

import pandas as pd

D = dt.date
FIRST = ["James", "Maria", "Robert", "Linda", "Michael", "Patricia", "David", "Jennifer", "Carlos", "Aisha", "Wei",
         "Priya", "Daniel", "Sofia", "Kevin", "Grace", "Omar", "Elena", "Brian", "Nadia", "Luis", "Hannah", "Raj",
         "Chloe", "Tyrone", "Mei", "Victor", "Fatima", "Sean", "Lucia"]
LAST = ["Smith", "Garcia", "Johnson", "Patel", "Nguyen", "Brown", "Rodriguez", "Lee", "Williams", "Martinez", "Khan",
        "Davis", "Lopez", "Wilson", "Clark", "Singh", "Lewis", "Young", "Walker", "Hall", "Allen", "Rivera", "Moore",
        "Taylor", "Thomas", "Hernandez", "Scott", "Adams", "Baker", "Chen"]
STREETS = ["Palm Ave", "Ocean Dr", "Main St", "Oak St", "Pine Rd", "Bay Blvd", "Cedar Ln", "Lake Dr", "Hill St",
           "Park Ave", "River Rd", "Elm St", "Coral Way", "Sunset Blvd", "Harbor Dr"]
# zip, state, territory, coastal
ZIPS = [("33139", "FL", "Urban", True), ("33125", "FL", "Urban", True), ("33602", "FL", "Urban", True),
        ("32801", "FL", "Urban", False), ("34102", "FL", "Suburban", True), ("32052", "FL", "Rural", False),
        ("32066", "FL", "Rural", False), ("77002", "TX", "Urban", True), ("79843", "TX", "Rural", False),
        ("75201", "TX", "Urban", False), ("10001", "NY", "Urban", True), ("13820", "NY", "Rural", False),
        ("30303", "GA", "Urban", False), ("31512", "GA", "Rural", False), ("90012", "CA", "Urban", True),
        ("93545", "CA", "Rural", False)]
ZIP_INFO = {z: {"state": s, "territory": t, "coastal": c} for z, s, t, c in ZIPS}
INTL = {"CA": [("M5V", "ON", "Urban", False), ("K0K", "ON", "Rural", False)],
        "UK": [("E1", "LDN", "Urban", False), ("LL55", "WLS", "Rural", False)],
        "IN": [("400001", "MH", "Urban", True), ("413001", "MH", "Rural", False)]}
for c, lst in INTL.items():
    for z, s, t, co in lst:
        ZIP_INFO[z] = {"state": s, "territory": t, "coastal": co}
CCY = {"US": "USD", "CA": "CAD", "UK": "GBP", "IN": "INR"}
FX = {"USD": 1.0, "CAD": 0.73, "GBP": 1.27, "INR": 0.012}
LOB_LINE = {"HO": "Personal", "PA": "Personal", "CP": "Commercial", "CA": "Commercial", "WC": "Commercial",
            "GL": "Commercial"}
PRODUCT = {"HO": "HO-3 Homeowners", "PA": "Personal Auto", "CP": "Commercial Property", "CA": "Commercial Auto",
           "WC": "Workers Compensation", "GL": "Commercial General Liability"}
OBJECT = {"HO": "Building", "CP": "Building", "PA": "Vehicle", "CA": "Vehicle", "WC": "Location", "GL": "Location"}
CAUSES = {"HO": ["Wind", "Water", "Fire", "Theft", "Hail"], "CP": ["Wind", "Fire", "Water", "Theft"],
          "PA": ["Collision", "Theft", "Comprehensive", "Bodily Injury"], "CA": ["Collision", "Bodily Injury"],
          "WC": ["Strain", "Fall", "Laceration"], "GL": ["Slip and Fall", "Products"]}
VAL = D(2026, 9, 30)


class G:
    def __init__(self, seed=2026):
        self.r = random.Random(seed)
        self.n = {}

    def id(self, prefix, width=4):
        self.n[prefix] = self.n.get(prefix, 0) + 1
        return f"{prefix}{self.n[prefix]:0{width}d}"

    def name(self):
        return f"{self.r.choice(FIRST)} {self.r.choice(LAST)}"

    def phone(self):
        return f"({self.r.randint(201, 989)}) {self.r.randint(200, 999)}-{self.r.randint(1000, 9999)}"

    def acct(self):
        return f"****{self.r.randint(1000, 9999)}-{self.r.randint(10, 99)}"

    def addr(self, zip_):
        return f"{self.r.randint(100, 9999)} {self.r.choice(STREETS)}, {zip_}"

    def date(self, a: D, b: D) -> D:
        return a + dt.timedelta(days=self.r.randint(0, max(0, (b - a).days)))


def build(seed: int = 2026) -> dict:
    g = G(seed)
    r = g.r
    truth = []

    def label(entity, eid, fraud_id, note):
        truth.append({"entity": entity, "entity_id": eid, "fraud_id": fraud_id, "scenario": note})

    # ------------------------------------------------------------------ people and companies
    employees = []
    for role, n, auth in [("Underwriter", 6, 0), ("Adjuster", 10, 25000), ("Billing clerk", 4, 0)]:
        for _ in range(n):
            employees.append({"emp_id": g.id("E", 3), "name": g.name(), "role": role, "authority_limit": auth,
                              "phone": g.phone(), "address": g.addr(r.choice(ZIPS)[0]), "bank_acct": g.acct()})
    emp = pd.DataFrame(employees)
    uw = list(emp[emp.role == "Underwriter"].emp_id)
    adj = list(emp[emp.role == "Adjuster"].emp_id)
    clerks = list(emp[emp.role == "Billing clerk"].emp_id)

    agents = pd.DataFrame([{"agent_id": g.id("AG", 2), "name": f"{r.choice(LAST)} Insurance Agency",
                            "country": "US", "state": s, "bank_acct": g.acct()} for s in
                           ["FL", "FL", "FL", "TX", "NY", "GA", "CA", "FL"]])
    vend_types = ["Roofer", "Water mitigation", "Body shop", "Body shop", "Tow", "Medical clinic", "Medical clinic",
                  "Restoration", "Public adjuster", "Roofer", "Restoration", "Water mitigation", "Restoration"]
    vendors = pd.DataFrame([{"vendor_id": g.id("V", 2), "name": f"{r.choice(LAST)} {t}", "vendor_type": t,
                             "phone": g.phone(), "address": g.addr(r.choice(ZIPS)[0]), "bank_acct": g.acct()}
                            for t in vend_types])
    attorneys = pd.DataFrame([{"attorney_id": g.id("AT", 2), "name": g.name(), "firm": f"{r.choice(LAST)} Law"}
                              for _ in range(6)])

    # ------------------------------------------------------------------ policies and objects
    parties, policies, objects, external = [], [], [], []

    def new_party(zip_, country="US"):
        p = {"party_id": g.id("PT"), "name": g.name(), "phone": g.phone(), "email": "", "address": g.addr(zip_),
             "zip": zip_, "country": country, "bank_acct": g.acct()}
        p["email"] = p["name"].lower().replace(" ", ".") + f"{r.randint(1, 99)}@example.com"
        parties.append(p)
        return p

    lob_mix = ["HO"] * 40 + ["PA"] * 35 + ["CP"] * 10 + ["CA"] * 5 + ["WC"] * 7 + ["GL"] * 3
    for i in range(420):
        country = "US" if i < 360 else r.choice(["CA", "UK", "IN"])
        lob = r.choice(lob_mix) if country == "US" else r.choice(["HO", "PA"])
        if country == "US":
            zip_, state, _, _ = r.choice(ZIPS if lob != "HO" else [z for z in ZIPS if z[1] in ("FL", "TX", "NY", "GA", "CA")])
        else:
            zip_, state, _, _ = r.choice(INTL[country])
        p = new_party(zip_, country)
        eff = g.date(D(2025, 1, 1), D(2026, 6, 30))
        limit = {"HO": r.choice([250000, 350000, 500000]), "CP": r.choice([1000000, 2500000]),
                 "PA": r.choice([25000, 50000, 100000]), "CA": 1000000, "WC": 1000000, "GL": 1000000}[lob]
        ded = {"HO": r.choice([1000, 2500, 5000]), "CP": r.choice([5000, 10000]), "PA": r.choice([500, 1000]),
               "CA": 1000, "WC": 0, "GL": 0}[lob]
        prem = round({"HO": r.uniform(2500, 9000) if state == "FL" else r.uniform(1200, 3500),
                      "PA": r.uniform(900, 2600), "CP": r.uniform(8000, 40000), "CA": r.uniform(6000, 20000),
                      "WC": r.uniform(5000, 30000), "GL": r.uniform(3000, 15000)}[lob], 2)
        pol = {"policy_id": g.id("POL", 5), "country": country, "currency": CCY[country], "state": state,
               "line": LOB_LINE[lob], "lob": lob, "product": PRODUCT[lob], "insured_party": p["party_id"],
               "agent_id": r.choice(list(agents.agent_id)) if country == "US" else "",
               "underwriter_id": r.choice(uw), "issue_date": eff - dt.timedelta(days=r.randint(3, 30)),
               "eff_date": eff, "exp_date": eff + dt.timedelta(days=365), "premium": prem, "limit": limit,
               "deductible": ded, "aggregate_deductible": 50000 if lob == "CP" else 0,
               "risk_zip": zip_, "mailing_zip": zip_, "status": "In force", "cancel_date": None,
               "issued_by": "System", "rate_override_pct": 0.0, "usage": "Owner occupied" if lob == "HO" else "",
               "sprinkler_declared": (lob == "CP" and r.random() < 0.6), "prior_claims_declared": 0,
               "drivers": p["party_id"] if lob in ("PA", "CA") else "", "coverage_change_date": None,
               "prior_limit": None}
        policies.append(pol)
        ob = {"object_id": g.id("OBJ", 5), "policy_id": pol["policy_id"], "object_type": OBJECT[lob],
              "description": "", "value": 0, "year": 0, "zip": zip_}
        if OBJECT[lob] == "Building":
            ob["year"] = r.randint(1975, 2022)
            ob["roof_year"] = r.randint(max(ob["year"], 2000), 2024)
            ob["value"] = limit
            ob["description"] = f"{'Dwelling' if lob == 'HO' else 'Commercial building'} built {ob['year']}"
        elif OBJECT[lob] == "Vehicle":
            ob["year"] = r.randint(2012, 2026)
            ob["value"] = r.randint(8000, 60000)
            ob["description"] = f"{ob['year']} {r.choice(['Sedan', 'SUV', 'Pickup', 'Van'])} VIN …{r.randint(10000, 99999)}"
        else:
            ob["description"] = f"Operations at {zip_}"
            ob["value"] = 0
        objects.append(ob)
        external.append({"policy_id": pol["policy_id"], "str_listing_found": False,
                         "inspection_sprinkler": pol["sprinkler_declared"] if lob == "CP" else None,
                         "prior_claims_found": 0, "roof_condition_at_inspection": "Good" if lob in ("HO", "CP") else "",
                         "employer_termination_date": None})

    pol = pd.DataFrame(policies)
    obj = pd.DataFrame(objects)
    ext = pd.DataFrame(external)
    ext.index = ext.policy_id
    obj["roof_year"] = obj.get("roof_year")

    # ------------------------------------------------------------------ premium billing
    payments, refunds, bank_changes = [], [], []
    for p in policies:
        via_agent = p["agent_id"] != "" and r.random() < 0.35
        payer = next(x for x in parties if x["party_id"] == p["insured_party"])
        d0 = p["issue_date"] + dt.timedelta(days=r.randint(0, 10))
        payments.append({"payment_id": g.id("PAY", 5), "policy_id": p["policy_id"], "date": d0,
                         "amount": p["premium"], "method": r.choice(["ACH", "Card", "Check"]),
                         "payer_acct": payer["bank_acct"], "status": "Cleared",
                         "collected_by_agent": p["agent_id"] if via_agent else "",
                         "remitted_date": d0 + dt.timedelta(days=r.randint(3, 20)) if via_agent else None})

    # ------------------------------------------------------------------ cat events
    cat = pd.DataFrame([
        {"event_id": "CAT-25-HU1", "peril": "Wind", "date": D(2025, 9, 24), "zips": "33139,33125,34102,33602"},
        {"event_id": "CAT-26-HL1", "peril": "Hail", "date": D(2026, 4, 12), "zips": "75201,77002,30303"},
        {"event_id": "CAT-26-HU2", "peril": "Wind", "date": D(2026, 8, 30), "zips": "33602,34102,32801"},
    ])

    # ------------------------------------------------------------------ clean claims
    claims, cpays, invoices = [], [], []
    pol_idx = {p["policy_id"]: p for p in policies}
    obj_by_pol = {o["policy_id"]: o for o in objects}

    def add_claim(p, loss, cause, claimant=None, adjuster=None, reserve=None, attorney="", atty_date=None,
                  contents=0.0, report_lag=None, desc="", status="Open", cat_event=""):
        c = {"claim_id": g.id("CLM", 5), "policy_id": p["policy_id"], "object_id": obj_by_pol[p["policy_id"]]["object_id"],
             "country": p["country"], "currency": p["currency"], "lob": p["lob"], "loss_date": loss,
             "report_date": loss + dt.timedelta(days=report_lag if report_lag is not None else r.randint(0, 6)),
             "cause": cause, "claimant_party": claimant or p["insured_party"], "adjuster_id": adjuster or r.choice(adj),
             "reserve": reserve if reserve is not None else round(r.uniform(2000, 30000), 2),
             "attorney_id": attorney, "attorney_date": atty_date, "contents_claimed": contents,
             "adjuster_estimate": 0.0, "description": desc or f"{cause} loss", "status": status,
             "cat_event": cat_event, "driver_party": ""}
        claims.append(c)
        return c

    def pay(c, amount, payee_type="Insured", payee_id=None, acct=None, coverage="Primary", ded_applied=True,
            approved_by=None, date=None, invoice=""):
        p = pol_idx[c["policy_id"]]
        if payee_type == "Insured":
            payee_id = payee_id or c["claimant_party"]
            acct = acct or next(x for x in parties if x["party_id"] == payee_id)["bank_acct"]
        cp = {"cpay_id": g.id("CP", 5), "claim_id": c["claim_id"], "date": date or c["report_date"] + dt.timedelta(days=r.randint(10, 60)),
              "payee_type": payee_type, "payee_id": payee_id, "payee_acct": acct, "amount": round(amount, 2),
              "coverage": coverage, "deductible_applied": p["deductible"] if ded_applied else 0,
              "approved_by": approved_by or c["adjuster_id"], "invoice_no": invoice}
        cpays.append(cp)
        return cp

    clean_pols = [p for p in policies]
    r.shuffle(clean_pols)
    for p in clean_pols[:230]:
        loss = g.date(p["eff_date"] + dt.timedelta(days=20), min(p["exp_date"], VAL) - dt.timedelta(days=5))
        if loss <= p["eff_date"]:
            continue
        cause = r.choice(CAUSES[p["lob"]])
        evt = ""
        if cause in ("Wind", "Hail"):
            ev = cat[(cat.peril == cause)]
            ev = ev[ev.zips.str.contains(p["risk_zip"])]
            if len(ev):
                e = ev.iloc[r.randrange(len(ev))]
                loss, evt = e.date, e.event_id
                if not (p["eff_date"] <= loss <= p["exp_date"]):
                    cause, evt = "Water", ""
                    loss = g.date(p["eff_date"] + dt.timedelta(days=20), min(p["exp_date"], VAL) - dt.timedelta(days=5))
            else:
                cause = "Water" if p["lob"] in ("HO", "CP") else cause
        c = add_claim(p, loss, cause, cat_event=evt)
        gross = round(min(r.uniform(1500, 40000), p["limit"] * 0.5), 2)
        c["adjuster_estimate"] = gross
        net = max(gross - p["deductible"], 0)
        if net > 0 and loss < VAL - dt.timedelta(days=40):
            if p["lob"] in ("HO", "CP") and r.random() < 0.5:
                v = vendors.loc[r.choice(list(vendors[vendors.vendor_type.isin(["Roofer", "Water mitigation", "Restoration"])].index))]
                inv = f"INV-{r.randint(10000, 99999)}"
                invoices.append({"invoice_no": inv, "vendor_id": v.vendor_id, "claim_id": c["claim_id"],
                                 "amount": gross, "date": c["report_date"] + dt.timedelta(days=r.randint(5, 20))})
                pay(c, net, "Vendor", v.vendor_id, v.bank_acct, invoice=inv)
            elif p["lob"] in ("PA", "CA") and r.random() < 0.5:
                v = vendors.loc[r.choice(list(vendors[vendors.vendor_type == "Body shop"].index))]
                inv = f"INV-{r.randint(10000, 99999)}"
                invoices.append({"invoice_no": inv, "vendor_id": v.vendor_id, "claim_id": c["claim_id"],
                                 "amount": gross, "date": c["report_date"] + dt.timedelta(days=r.randint(5, 20))})
                pay(c, net, "Vendor", v.vendor_id, v.bank_acct, invoice=inv)
            else:
                pay(c, net)
            c["status"] = "Closed" if r.random() < 0.6 else "Open"
            c["reserve"] = 0.0 if c["status"] == "Closed" else c["reserve"]

    party_df = lambda: pd.DataFrame(parties)  # noqa: E731

    def pick(lob=None, country="US", state=None, used=set()):
        cand = [p for p in policies if p["country"] == country and (lob is None or p["lob"] in lob)
                and (state is None or p["state"] == state) and p["policy_id"] not in used
                and not any(c["policy_id"] == p["policy_id"] for c in claims)]
        p = r.choice(cand)
        used.add(p["policy_id"])
        return p

    # ------------------------------------------------------------------ seeded fraud: policy & underwriting
    for _ in range(3):   # FR-P01 rate evasion: rural garaging, urban life
        p = pick(("PA",))
        p["risk_zip"] = r.choice(["32052", "79843", "13820", "31512"])
        p["mailing_zip"] = r.choice(["33125", "77002", "10001", "30303"])
        c = add_claim(p, g.date(p["eff_date"] + dt.timedelta(days=40), min(p["exp_date"], VAL)), "Collision")
        c["description"] = f"Collision near {p['mailing_zip']}"
        c["loss_zip"] = p["mailing_zip"]
        label("policy", p["policy_id"], "FR-P01", "Garaged in a rural ZIP, mailing and loss location urban")
    for _ in range(3):   # FR-P02 STR misrepresentation
        p = pick(("HO",))
        ext.loc[p["policy_id"], "str_listing_found"] = True
        label("policy", p["policy_id"], "FR-P02", "Declared owner occupied; short-term rental listing found")
    for _ in range(2):   # FR-P03 sprinkler misrepresentation
        p = pick(("CP",))
        p["sprinkler_declared"] = True
        ext.loc[p["policy_id"], "inspection_sprinkler"] = False
        label("policy", p["policy_id"], "FR-P03", "Sprinkler declared; inspection found none")
    for _ in range(3):   # FR-P04 concealed prior losses
        p = pick(("HO", "PA"))
        ext.loc[p["policy_id"], "prior_claims_found"] = r.randint(2, 4)
        label("policy", p["policy_id"], "FR-P04", "Declared no prior claims; loss history shows several")
    for _ in range(2):   # FR-P05 undisclosed driver (fronting)
        p = pick(("PA", "CA"))
        driver = new_party(p["risk_zip"])
        for k in range(2):
            c = add_claim(p, g.date(p["eff_date"] + dt.timedelta(days=30), min(p["exp_date"], VAL)), "Collision")
            c["driver_party"] = driver["party_id"]
        label("policy", p["policy_id"], "FR-P05", "Claims keep naming a driver who is not on the policy")
    # FR-I01 ghost policy issued by underwriter + ghost claim
    for _ in range(2):
        u = emp[emp.emp_id == r.choice(uw)].iloc[0]
        p = pick(("HO",), state="FL")
        insured = next(x for x in parties if x["party_id"] == p["insured_party"])
        insured["phone"], insured["bank_acct"] = u.phone, u.bank_acct
        p["issued_by"], p["underwriter_id"] = "Manual", u.emp_id
        payments[:] = [x for x in payments if x["policy_id"] != p["policy_id"]]
        c = add_claim(p, p["eff_date"] + dt.timedelta(days=r.randint(15, 40)), "Water", reserve=0)
        pay(c, r.uniform(18000, 24000))
        c["status"] = "Closed"
        label("policy", p["policy_id"], "FR-I01", f"Manual issue by {u.emp_id}; insured shares the underwriter's phone and bank; no premium; quick claim")
        label("claim", c["claim_id"], "FR-I01", "Claim on a ghost policy")
    for _ in range(3):   # FR-P06 backdated coverage: bound after the loss
        p = pick(("HO", "PA"))
        loss = p["eff_date"] + dt.timedelta(days=r.randint(1, 5))
        p["issue_date"] = loss + dt.timedelta(days=r.randint(2, 6))
        c = add_claim(p, loss, r.choice(CAUSES[p["lob"]]), report_lag=r.randint(8, 12))
        label("claim", c["claim_id"], "FR-P06", "Policy issued after the loss date, with the effective date backdated")
    for _ in range(4):   # FR-I02 underwriter rate overrides for one agent
        p = pick(("HO", "CP"))
        p["agent_id"], p["underwriter_id"], p["rate_override_pct"] = "AG03", uw[1], -round(r.uniform(25, 40), 1)
        label("policy", p["policy_id"], "FR-I02", f"Large rate override by {uw[1]} concentrated on agent AG03")

    # ------------------------------------------------------------------ seeded fraud: billing
    for _ in range(3):   # FR-B01 premium diversion
        p = pick(("HO", "PA", "CP"))
        x = next(x for x in payments if x["policy_id"] == p["policy_id"])
        x["collected_by_agent"], x["remitted_date"] = p["agent_id"] or "AG05", None
        x["date"] = VAL - dt.timedelta(days=r.randint(45, 120))
        label("policy", p["policy_id"], "FR-B01", "Agent collected premium and never remitted it")
    for _ in range(2):   # FR-B02 refund to a different account, after bank change by clerk
        p = pick(("HO", "PA"))
        clerk = r.choice(clerks)
        new_acct = g.acct()
        bank_changes.append({"entity": "party", "entity_id": p["insured_party"], "date": VAL - dt.timedelta(days=12),
                             "old_acct": next(x for x in parties if x["party_id"] == p["insured_party"])["bank_acct"],
                             "new_acct": new_acct, "changed_by": clerk})
        p["status"], p["cancel_date"] = "Cancelled", VAL - dt.timedelta(days=10)
        refunds.append({"refund_id": g.id("RF", 4), "policy_id": p["policy_id"], "date": VAL - dt.timedelta(days=9),
                        "amount": round(p["premium"] * 0.6, 2), "to_acct": new_acct, "approved_by": clerk})
        label("policy", p["policy_id"], "FR-B02", f"Bank account changed and refund approved by the same clerk {clerk}")
    for _ in range(2):   # FR-B03 premium charged back after the claim is paid
        p = pick(("PA", "HO"))
        c = add_claim(p, p["eff_date"] + dt.timedelta(days=r.randint(25, 60)), r.choice(CAUSES[p["lob"]]))
        cp = pay(c, r.uniform(6000, 12000))
        x = next(x for x in payments if x["policy_id"] == p["policy_id"])
        x["status"], x["method"] = "Chargeback", "Card"
        x["chargeback_date"] = cp["date"] + dt.timedelta(days=r.randint(3, 15))
        label("policy", p["policy_id"], "FR-B03", "Card premium charged back after the claim was paid")

    # ------------------------------------------------------------------ seeded fraud: claims
    for _ in range(3):   # FR-C01 loss outside the policy period
        p = pick(("HO", "PA", "CP"))
        c = add_claim(p, p["eff_date"] - dt.timedelta(days=r.randint(5, 40)), r.choice(CAUSES[p["lob"]]))
        label("claim", c["claim_id"], "FR-C01", "Loss date before the policy started")
    for _ in range(2):   # FR-C02 loss after cancellation
        p = pick(("HO", "PA"))
        p["status"], p["cancel_date"] = "Cancelled", p["eff_date"] + dt.timedelta(days=90)
        c = add_claim(p, min(p["cancel_date"] + dt.timedelta(days=r.randint(5, 30)), VAL - dt.timedelta(days=3)),
                      r.choice(CAUSES[p["lob"]]))
        label("claim", c["claim_id"], "FR-C02", "Loss after the policy was cancelled")
    for _ in range(3):   # FR-C03 paid beyond limit
        p = pick(("PA",))
        c = add_claim(p, p["eff_date"] + dt.timedelta(days=60), "Collision")
        pay(c, p["limit"] * 0.7)
        pay(c, p["limit"] * 0.6)
        label("claim", c["claim_id"], "FR-C03", "Payments exceed the coverage limit")
    for _ in range(3):   # FR-C04 deductible not applied
        p = pick(("HO", "CP"))
        c = add_claim(p, p["eff_date"] + dt.timedelta(days=80), "Water")
        c["adjuster_estimate"] = 15000.0
        pay(c, 15000.0, ded_applied=False)
        label("claim", c["claim_id"], "FR-C04", "Full estimate paid; deductible never applied")
    for _ in range(2):   # FR-C05 duplicate claim on two policies
        p1, p2 = pick(("HO",)), pick(("HO",))
        o1 = obj_by_pol[p1["policy_id"]]
        o2 = obj_by_pol[p2["policy_id"]]
        o2["description"], o2["zip"] = o1["description"], o1["zip"]
        same_party = next(x for x in parties if x["party_id"] == p1["insured_party"])
        p2["insured_party"] = same_party["party_id"]
        loss = max(p1["eff_date"], p2["eff_date"]) + dt.timedelta(days=30)
        c1 = add_claim(p1, loss, "Theft", contents=12000)
        c2 = add_claim(p2, loss, "Theft", contents=12000)
        label("claim", c2["claim_id"], "FR-C05", f"Same loss also claimed on {c1['claim_id']}")
    for _ in range(2):   # FR-C06 duplicate vendor invoice
        p = pick(("HO", "CP"))
        c = add_claim(p, p["eff_date"] + dt.timedelta(days=50), "Water")
        v = vendors[vendors.vendor_type == "Water mitigation"].iloc[0]
        inv = f"INV-{r.randint(10000, 99999)}"
        invoices.append({"invoice_no": inv, "vendor_id": v.vendor_id, "claim_id": c["claim_id"], "amount": 8400.0,
                         "date": c["report_date"] + dt.timedelta(days=7)})
        pay(c, 8400 - p["deductible"], "Vendor", v.vendor_id, v.bank_acct, invoice=inv)
        pay(c, 8400 - p["deductible"], "Vendor", v.vendor_id, v.bank_acct, invoice=inv,
            date=c["report_date"] + dt.timedelta(days=40))
        label("claim", c["claim_id"], "FR-C06", "Same vendor invoice paid twice")
    storm = D(2026, 8, 30)
    for _ in range(3):   # FR-C07 deductible absorbed by contractor (estimate inflated by the deductible)
        cand = [x for x in policies if x["lob"] == "HO" and x["risk_zip"] in ("33602", "34102", "32801")
                and x["eff_date"] <= storm <= x["exp_date"] and not any(c["policy_id"] == x["policy_id"] for c in claims)]
        p = r.choice(cand)
        c = add_claim(p, storm, "Wind", cat_event="CAT-26-HU2")
        est = round(r.uniform(9000, 16000), 2)
        c["adjuster_estimate"] = est
        v = vendors[vendors.vendor_type == "Roofer"].iloc[1]
        inv = f"INV-{r.randint(10000, 99999)}"
        invoices.append({"invoice_no": inv, "vendor_id": v.vendor_id, "claim_id": c["claim_id"],
                         "amount": est + p["deductible"], "date": c["report_date"] + dt.timedelta(days=9)})
        label("claim", c["claim_id"], "FR-C07", "Roofer invoice = adjuster estimate + deductible (deductible waived)")
    # FR-C08 staged-accident ring: shared phone/address, same attorney and body shop
    ring_phone, ring_addr = g.phone(), g.addr("33125")
    shop = vendors[vendors.vendor_type == "Body shop"].iloc[0]
    for k in range(5):
        p = pick(("PA",), state="FL")
        claimant = new_party("33125")
        claimant["phone"] = ring_phone if k % 2 == 0 else claimant["phone"]
        claimant["address"] = ring_addr if k % 2 == 1 else claimant["address"]
        loss = D(2026, 3, 1) + dt.timedelta(days=k * 9)
        c = add_claim(p, max(loss, p["eff_date"] + dt.timedelta(days=10)), "Bodily Injury", claimant=claimant["party_id"],
                      attorney="AT01", reserve=round(r.uniform(18000, 45000), 2))
        c["attorney_date"] = c["loss_date"] + dt.timedelta(days=1)
        c["description"] = "Rear-end at intersection; sudden stop by lead vehicle"
        inv = f"INV-{r.randint(10000, 99999)}"
        invoices.append({"invoice_no": inv, "vendor_id": shop.vendor_id, "claim_id": c["claim_id"],
                         "amount": round(r.uniform(6000, 9000), 2), "date": c["report_date"] + dt.timedelta(days=5)})
        clinic = vendors[vendors.vendor_type == "Medical clinic"].iloc[0]
        invoices.append({"invoice_no": f"MED-{r.randint(10000, 99999)}", "vendor_id": clinic.vendor_id,
                         "claim_id": c["claim_id"], "amount": round(r.uniform(9000, 15000), 2),
                         "date": c["report_date"] + dt.timedelta(days=12)})
        label("claim", c["claim_id"], "FR-C08", "Staged-accident ring: shared phone or address, same attorney, body shop and clinic")
    for _ in range(3):   # FR-C10 wind claim with no storm on record; old roof already damaged
        p = pick(("HO",), state="FL")
        o = obj_by_pol[p["policy_id"]]
        o["roof_year"] = r.randint(1998, 2003)
        ext.loc[p["policy_id"], "roof_condition_at_inspection"] = "Damaged"
        c = add_claim(p, p["eff_date"] + dt.timedelta(days=r.randint(30, 120)), "Wind", reserve=round(r.uniform(25000, 60000), 2))
        c["description"] = "Roof damaged by hurricane winds"
        label("claim", c["claim_id"], "FR-C10", "Wind claim on a date and ZIP with no storm; roof was already damaged at inspection")
    for _ in range(2):   # FR-C11 arson for profit pattern
        p = pick(("CP", "HO"))
        p["prior_limit"] = p["limit"]
        p["limit"] = int(p["limit"] * 1.6)
        p["coverage_change_date"] = p["eff_date"] + dt.timedelta(days=60)
        x = next(x for x in payments if x["policy_id"] == p["policy_id"])
        x["status"] = "NSF"
        c = add_claim(p, p["coverage_change_date"] + dt.timedelta(days=r.randint(20, 50)), "Fire",
                      reserve=round(p["limit"] * 0.8, 2))
        c["description"] = "Total fire loss; building vacant at the time"
        label("claim", c["claim_id"], "FR-C11", "Limit raised 60% weeks before a total fire; premium payment bounced; vacant")
    for _ in range(3):   # FR-C12 inflated contents
        p = pick(("HO",))
        c = add_claim(p, p["eff_date"] + dt.timedelta(days=100), "Theft", contents=round(p["limit"] * r.uniform(0.32, 0.45), 2))
        label("claim", c["claim_id"], "FR-C12", "Contents claimed far above typical share of the dwelling limit")
    for _ in range(2):   # FR-C14 ghost claim: payee account belongs to the adjuster
        p = pick(("HO", "PA"))
        a = emp[emp.emp_id == r.choice(adj)].iloc[0]
        c = add_claim(p, p["eff_date"] + dt.timedelta(days=70), r.choice(CAUSES[p["lob"]]), adjuster=a.emp_id)
        pay(c, r.uniform(7000, 14000), "Insured", p["insured_party"], a.bank_acct)
        label("claim", c["claim_id"], "FR-I03", f"Claim payment sent to adjuster {a.emp_id}'s bank account")
    for _ in range(2):   # FR-I04 split payments under authority
        p = pick(("HO", "CP"))
        a = emp[emp.emp_id == r.choice(adj)].iloc[0]
        c = add_claim(p, p["eff_date"] + dt.timedelta(days=90), "Water", adjuster=a.emp_id, reserve=60000)
        d0 = c["report_date"] + dt.timedelta(days=20)
        for _k in range(3):
            pay(c, round(r.uniform(23500, 24900), 2), date=d0)
        label("claim", c["claim_id"], "FR-I04", f"Three same-day payments just under {a.emp_id}'s $25,000 authority")
    # FR-I05 adjuster steering to one vendor
    steer_adj = adj[4]
    rest = vendors[vendors.vendor_type == "Restoration"].iloc[0]
    for _ in range(9):
        p = pick(("HO", "CP"))
        c = add_claim(p, p["eff_date"] + dt.timedelta(days=r.randint(30, 150)), "Water", adjuster=steer_adj)
        inv = f"INV-{r.randint(10000, 99999)}"
        amt = round(r.uniform(12000, 19000), 2)
        invoices.append({"invoice_no": inv, "vendor_id": rest.vendor_id, "claim_id": c["claim_id"], "amount": amt,
                         "date": c["report_date"] + dt.timedelta(days=6)})
        pay(c, amt - p["deductible"], "Vendor", rest.vendor_id, rest.bank_acct, invoice=inv)
        label("claim", c["claim_id"], "FR-I05", f"Adjuster {steer_adj} sends nearly every job to {rest.vendor_id}")
    for _ in range(2):   # FR-C15 payee bank account changed just before payment
        p = pick(("HO",))
        c = add_claim(p, p["eff_date"] + dt.timedelta(days=60), "Water")
        new_acct = g.acct()
        d = c["report_date"] + dt.timedelta(days=25)
        bank_changes.append({"entity": "party", "entity_id": p["insured_party"], "date": d - dt.timedelta(days=1),
                             "old_acct": next(x for x in parties if x["party_id"] == p["insured_party"])["bank_acct"],
                             "new_acct": new_acct, "changed_by": "Web portal"})
        pay(c, r.uniform(9000, 15000), "Insured", p["insured_party"], new_acct, date=d)
        label("claim", c["claim_id"], "FR-C15", "Payee bank details changed one day before a large payment")
    for _ in range(2):   # FR-C16 workers comp claim after termination
        p = pick(("WC",))
        worker = new_party(p["risk_zip"])
        term = p["eff_date"] + dt.timedelta(days=100)
        c = add_claim(p, term - dt.timedelta(days=2), "Strain", claimant=worker["party_id"], report_lag=9)
        c["employer_termination_date"] = term
        label("claim", c["claim_id"], "FR-C16", "Injury reported after the worker was terminated, dated just before")
    # FR-C09 early attorney on a minor claim
    for _ in range(3):
        p = pick(("PA",))
        c = add_claim(p, p["eff_date"] + dt.timedelta(days=80), "Collision", attorney=r.choice(["AT02", "AT03"]),
                      reserve=3200.0)
        c["attorney_date"] = c["loss_date"] + dt.timedelta(days=1)
        label("claim", c["claim_id"], "FR-C09", "Attorney retained the day after a minor collision")
    # FR-C17 repeat claimant
    rep = new_party("77002")
    for k in range(3):
        p = pick(("PA", "GL"))
        add_claim(p, p["eff_date"] + dt.timedelta(days=30 + k), r.choice(["Bodily Injury", "Slip and Fall"])
                  if p["lob"] == "GL" else "Bodily Injury", claimant=rep["party_id"])
    label("party", rep["party_id"], "FR-C17", "Same claimant on three injury claims against different insureds")
    # international examples
    p = pick(("PA",), country="UK")
    c = add_claim(p, p["eff_date"] + dt.timedelta(days=40), "Collision", attorney="AT04", reserve=9000)
    c["attorney_date"] = c["loss_date"] + dt.timedelta(days=2)
    c["description"] = "Crash-for-cash pattern: induced rear-end, multiple passengers"
    label("claim", c["claim_id"], "FR-C09", "UK motor: claims-management firm engaged two days after an induced collision")
    p = pick(("HO",), country="IN")
    c = add_claim(p, p["eff_date"] - dt.timedelta(days=12), "Theft")
    label("claim", c["claim_id"], "FR-C01", "India home: theft dated before cover began")

    # look-alikes that are NOT fraud, so the SME has false positives to clear
    for _ in range(2):   # collector with scheduled jewellery and art: high contents, genuine
        p = pick(("HO",))
        add_claim(p, p["eff_date"] + dt.timedelta(days=150), "Theft", contents=round(p["limit"] * 0.34, 2),
                  desc="Burglary; scheduled jewellery and art with appraisals on file")
    for _ in range(2):   # serious injury where the family called a lawyer at once: genuine
        p = pick(("PA",))
        c = add_claim(p, p["eff_date"] + dt.timedelta(days=120), "Collision", attorney="AT05", reserve=8500.0,
                      desc="Police report confirms other driver ran a red light")
        c["attorney_date"] = c["loss_date"] + dt.timedelta(days=2)

    clm = pd.DataFrame(claims)
    for col in ("loss_zip", "employer_termination_date"):
        if col not in clm:
            clm[col] = None
    clm["loss_zip"] = clm.loss_zip.fillna(clm.policy_id.map(lambda x: pol_idx[x]["risk_zip"]))

    # ------------------------------------------------------------------ reinsurance
    reinsurers = pd.DataFrame([
        {"reinsurer_id": "RE01", "name": "Atlas Re", "domicile": "US", "rating": "A+", "capital_usd": 4.5e9, "collateral_posted": True},
        {"reinsurer_id": "RE02", "name": "Meridian Re", "domicile": "Bermuda", "rating": "A", "capital_usd": 2.1e9, "collateral_posted": True},
        {"reinsurer_id": "RE03", "name": "Harborline Re", "domicile": "UK", "rating": "A-", "capital_usd": 9.0e8, "collateral_posted": True},
        {"reinsurer_id": "RE04", "name": "Bluewater Assurance Ltd", "domicile": "Offshore (unrated jurisdiction)", "rating": "NR",
         "capital_usd": 6.0e6, "collateral_posted": False},
    ])
    treaties = pd.DataFrame([
        {"treaty_id": "TR-QS-HO", "reinsurer_id": "RE01", "type": "Quota share 40%", "lob": "HO", "start": D(2025, 1, 1),
         "end": D(2026, 12, 31), "share": 0.40, "retention": 0, "limit": 5e6, "aad": 0},
        {"treaty_id": "TR-XL-PR", "reinsurer_id": "RE02", "type": "Per-risk XoL 250k xs 250k", "lob": "CP", "start": D(2025, 6, 1),
         "end": D(2026, 5, 31), "share": 1.0, "retention": 250000, "limit": 250000, "aad": 0},
        {"treaty_id": "TR-AGG", "reinsurer_id": "RE03", "type": "Aggregate stop loss", "lob": "HO", "start": D(2025, 1, 1),
         "end": D(2025, 12, 31), "share": 1.0, "retention": 0, "limit": 2e6, "aad": 1.5e6},
        {"treaty_id": "TR-CAT-FR", "reinsurer_id": "RE04", "type": "Fronted cat XoL (100% ceded)", "lob": "HO", "start": D(2025, 6, 1),
         "end": D(2026, 5, 31), "share": 1.0, "retention": 0, "limit": 2.5e7, "aad": 0},
    ])
    cp_df = pd.DataFrame(cpays)
    paid = cp_df.groupby("claim_id").amount.sum() if len(cp_df) else pd.Series(dtype=float)
    cessions = []
    ho = clm[(clm.lob == "HO") & (clm.country == "US") & clm.claim_id.isin(paid.index)]
    for c in ho.itertuples():
        if D(2025, 1, 1) <= c.loss_date <= D(2026, 12, 31):
            loss = float(paid[c.claim_id])
            cessions.append({"cession_id": g.id("CS", 4), "claim_id": c.claim_id, "treaty_id": "TR-QS-HO",
                             "ceded_loss": round(loss * 0.4, 2), "recovery_billed": round(loss * 0.4, 2),
                             "recovery_collected": round(loss * 0.4, 2) if r.random() < 0.85 else 0.0})
    # FR-R01 double ceding: same claim billed 40% to QS and 100% again under the fronted cat treaty
    for cid in list(ho.claim_id)[:2]:
        loss = float(paid[cid])
        cessions.append({"cession_id": g.id("CS", 4), "claim_id": cid, "treaty_id": "TR-CAT-FR",
                         "ceded_loss": loss, "recovery_billed": loss, "recovery_collected": 0.0})
        label("claim", cid, "FR-R01", "Same loss recovered under two treaties: billed 140% of paid")
    # FR-R02 recovery outside the treaty period
    out = clm[(clm.lob == "HO") & (clm.loss_date < D(2025, 6, 1)) & clm.claim_id.isin(paid.index)]
    for cid in list(out.claim_id)[:2]:
        loss = float(paid[cid])
        cessions.append({"cession_id": g.id("CS", 4), "claim_id": cid, "treaty_id": "TR-CAT-FR",
                         "ceded_loss": loss, "recovery_billed": loss, "recovery_collected": 0.0})
        label("claim", cid, "FR-R02", "Recovery billed for a loss before the treaty incepted")
    # FR-R03 aggregate stop billed before the annual aggregate deductible is used up
    cessions.append({"cession_id": g.id("CS", 4), "claim_id": "AGG-2025", "treaty_id": "TR-AGG",
                     "ceded_loss": 400000.0, "recovery_billed": 400000.0, "recovery_collected": 0.0})
    label("treaty", "TR-AGG", "FR-R03", "Aggregate stop recovery billed although 2025 retained losses are under the $1.5M AAD")
    label("treaty", "TR-CAT-FR", "FR-R04", "100% fronted to an unrated offshore reinsurer with $6M capital and no collateral")
    label("treaty", "TR-CAT-FR", "FR-R05", "Bordereau under-reports coastal Florida exposure")
    bordereau = []
    pdf_ = pd.DataFrame(policies)
    for z, g_ in pdf_[(pdf_.lob == "HO") & (pdf_.country == "US")].groupby("risk_zip"):
        actual = float(g_.limit.sum())
        coastal = ZIP_INFO[z]["coastal"] and ZIP_INFO[z]["state"] == "FL"
        bordereau.append({"treaty_id": "TR-CAT-FR", "zip": z, "policies_reported": len(g_) if not coastal else max(1, len(g_) // 3),
                          "tiv_reported": actual if not coastal else round(actual * 0.35, 0), "tiv_actual": actual})

    pol = pd.DataFrame(policies)
    obj = pd.DataFrame(objects)
    ext = ext.reset_index(drop=True)
    pay_df = pd.DataFrame(payments)
    if "chargeback_date" not in pay_df:
        pay_df["chargeback_date"] = None
    return {
        "policies": pol, "objects": obj, "parties": pd.DataFrame(parties), "employees": emp, "agents": agents,
        "vendors": vendors, "attorneys": attorneys, "external": ext, "premium_payments": pay_df,
        "refunds": pd.DataFrame(refunds, columns=["refund_id", "policy_id", "date", "amount", "to_acct", "approved_by"]),
        "bank_changes": pd.DataFrame(bank_changes, columns=["entity", "entity_id", "date", "old_acct", "new_acct", "changed_by"]),
        "claims": clm, "claim_payments": pd.DataFrame(cpays), "invoices": pd.DataFrame(invoices), "cat_events": cat,
        "reinsurers": reinsurers, "treaties": treaties, "cessions": pd.DataFrame(cessions),
        "bordereau": pd.DataFrame(bordereau), "truth": pd.DataFrame(truth), "valuation_date": VAL,
    }

"""SI² P&C fraud catalog: what the fraud is, who commits it, where it shows up, how to catch it,
how to stop it before money moves, and how to keep watching for it.

Each row has an id. Rows with engine_rule = "Yes" have a working detection rule in fraud/engine.py.
"""
import pandas as pd

COLUMNS = [
    "fraud_id", "domain", "fraud_type", "description", "perpetrator", "countries", "country_notes", "line", "lob",
    "module", "object", "lifecycle_stage", "red_flags", "detection_method", "detection_rule", "data_needed",
    "prevention_control", "trigger_action", "monitoring_kpi", "severity", "owner", "engine_rule",
]

ALL = "US, Canada, UK, India, Global"
P, C = "Personal", "Commercial"
PC = "Personal, Commercial"


def row(fid, domain, ftype, desc, perp, countries, notes, line, lob, module, obj, stage, flags, method, rule, data,
        prevent, action, kpi, sev, owner, engine="No"):
    return dict(zip(COLUMNS, [fid, domain, ftype, desc, perp, countries, notes, line, lob, module, obj, stage, flags,
                              method, rule, data, prevent, action, kpi, sev, owner, engine]))


ROWS = [
    # ------------------------------------------------------------------ policy & underwriting
    row("FR-P01", "Policy & underwriting", "Rate evasion (garaging / territory)",
        "False garaging or risk address to get a cheaper territory.", "Insured", ALL,
        "US: urban drivers using rural relatives' addresses. UK: postcode manipulation.", PC, "PA, CA, HO",
        "Policy admin, Rating", "Vehicle, Location, Party", "Quote / bind / renewal",
        "Garaging ZIP rural while mailing, billing, claim or telematics locations are urban.", "Rule",
        "Risk ZIP territory = Rural AND (mailing ZIP or loss ZIP) territory = Urban.",
        "Risk ZIP, mailing ZIP, loss location, territory table", "Address verification at quote; telematics or photo inspection",
        "Step-up verification; re-rate", "Territory mismatch rate by agent", 3, "Underwriting", "Yes"),
    row("FR-P02", "Policy & underwriting", "Material misrepresentation of use",
        "Home declared owner-occupied but rented out short-term or run as a business.", "Insured", ALL,
        "US: short-term rentals in FL, TX, CA coastal markets.", P, "HO", "Policy admin", "Building, Location",
        "Bind / renewal", "Short-term rental listing at the address; many guests; business licence at address.",
        "External data", "Declared usage = Owner occupied AND rental listing found for the address.",
        "Usage, address, rental listing data", "Rental-listing search before bind and at renewal",
        "Step-up verification; endorse or non-renew", "Listings found per 1,000 HO policies", 3, "Underwriting", "Yes"),
    row("FR-P03", "Policy & underwriting", "Application fraud (protection / safety)",
        "False sprinkler, alarm, roof or safety certification to qualify or cut premium.", "Insured, Agent", ALL,
        "", C, "CP, HO", "Policy admin, Inspection", "Building", "Bind", "Declared protection contradicted by inspection.",
        "Rule", "Sprinkler declared = Y AND inspection sprinkler = N.", "Declarations, inspection report",
        "Inspection before bind above a TIV threshold", "Block bind until verified", "Inspection contradictions by agent",
        4, "Underwriting", "Yes"),
    row("FR-P04", "Policy & underwriting", "Concealed loss history",
        "Prior claims hidden on the application.", "Insured, Agent", ALL,
        "US: CLUE-type loss histories. UK: CUE. India: NCB certificate checks.", PC, "HO, PA, CP", "Policy admin",
        "Party", "Quote / bind", "Declared 0 prior claims; external loss history shows 2+.", "External data",
        "Prior claims declared < prior claims found.", "Application, loss-history report",
        "Automatic loss-history pull at quote", "Re-rate; rescind if material", "Undisclosed-loss rate", 3, "Underwriting", "Yes"),
    row("FR-P05", "Policy & underwriting", "Fronting (undisclosed operator)",
        "Low-risk person named as insured while a high-risk driver or operator actually uses the risk.", "Insured", ALL,
        "Common in young-driver auto (UK: 'fronting'; US: undisclosed household drivers).", PC, "PA, CA",
        "Policy admin, Claims", "Vehicle, Party", "Mid-term / claim", "Claims repeatedly name a driver not on the policy.",
        "Rule", "2+ claims where driver is not a listed driver.", "Listed drivers, claim driver", "Driver household check at bind",
        "Refer SIU; endorse driver", "Unlisted-driver claims per 100 auto claims", 3, "Underwriting / Claims", "Yes"),
    row("FR-P06", "Policy & underwriting", "Post-loss / backdated coverage",
        "Coverage bought or backdated after the loss already happened.", "Insured, Agent, Underwriter", ALL, "", PC,
        "All", "Policy admin, Claims", "Policy", "Bind / first notice of loss", "Issue date after loss date; loss within days of inception.",
        "Rule", "Policy issue date > loss date.", "Issue date, effective date, loss date",
        "No retroactive effective dates without supervisor approval", "Hold payment; refer SIU",
        "Claims on policies issued after the loss", 5, "Underwriting / SIU", "Yes"),
    row("FR-P07", "Policy & underwriting", "Ghost broking / fake policies",
        "Fake or doctored policies sold to consumers by an unlicensed intermediary.", "Third party (ghost broker)",
        "UK, India, US", "UK: ghost broking on social media.", P, "PA", "Distribution", "Party, Policy",
        "Quote / bind", "Many policies with one email or phone; cancelled after documents issued.", "Network",
        "Same contact details across many unrelated insureds; cancel within 30 days of issue.", "Contact details, cancellations",
        "Contact-data reuse checks at quote", "Block bind", "Shared-contact policies", 4, "Distribution"),
    row("FR-P08", "Policy & underwriting", "Identity theft / synthetic identity",
        "Policy bought with a stolen or invented identity, usually to stage claims or launder money.", "Third party",
        ALL, "", P, "PA, HO", "Policy admin, Billing", "Party", "Quote / bind", "ID fails verification; new identity with no history.",
        "External data", "Identity verification score below threshold.", "Identity verification service",
        "Identity check at bind", "Block bind", "Failed ID checks", 4, "Underwriting"),
    row("FR-P09", "Policy & underwriting", "Payroll / class misreporting (WC premium fraud)",
        "Employer under-reports payroll or puts workers in cheaper class codes.", "Insured (employer)", "US, Canada",
        "US: workers compensation premium audit.", C, "WC", "Policy admin, Premium audit", "Party, Location",
        "Bind / audit", "Payroll per employee far below industry; claims from classes not on policy.", "Anomaly",
        "Claims in a class code not on the policy; payroll per head < peer floor.", "Payroll, class codes, claims",
        "Premium audit; payroll verification", "Re-audit; refer SIU", "Audit additional premium", 4, "Premium audit"),
    # ------------------------------------------------------------------ billing & premium
    row("FR-B01", "Billing & premium", "Premium diversion by agent",
        "Agent collects premium and keeps it, sometimes issuing fake certificates.", "Agent", ALL, "", PC, "All",
        "Billing, Agency", "Payment, Policy", "Collection", "Agent-collected premium not remitted after 30 days.", "Rule",
        "Collected by agent AND not remitted AND age > 30 days.", "Agent collections, remittances",
        "Direct bill; trust-account reconciliation", "Hold commissions; refer SIU", "Unremitted premium by agent", 4,
        "Billing / Agency", "Yes"),
    row("FR-B02", "Billing & premium", "Refund diversion",
        "Cancellation refund sent to an account that did not pay the premium, often after a bank-detail change.",
        "Employee (billing), Third party", ALL, "", PC, "All", "Billing", "Payment, Party", "Cancellation / refund",
        "Refund account differs from payer account; same clerk changed bank details and approved refund.", "Rule",
        "Refund to_acct != payer acct OR approver = person who changed bank details.", "Refunds, payments, bank-change log",
        "Refund only to the original payment method; dual approval", "Block refund", "Refunds to new accounts", 4,
        "Billing", "Yes"),
    row("FR-B03", "Billing & premium", "Premium chargeback / NSF after claim",
        "Premium paid by card or cheque that is reversed after the claim is paid.", "Insured", ALL, "", P, "PA, HO",
        "Billing, Claims", "Payment", "Collection / claim payment", "Premium reversed after a claim payment.", "Rule",
        "Premium status in (Chargeback, NSF) AND a claim payment exists on the policy.", "Premium payments, claim payments",
        "Clear funds before paying claims on new policies", "Hold payment; recover", "Chargebacks after claim", 3,
        "Billing", "Yes"),
    row("FR-B04", "Billing & premium", "Premium finance fraud",
        "Inflated or fictitious policies financed through a premium finance company.", "Agent, Insured", "US",
        "", C, "All", "Billing, Distribution", "Policy, Payment", "Bind", "Finance agreement premium exceeds policy premium.",
        "Rule", "Financed amount > billed premium.", "Premium finance notices", "Reconcile finance notices to policies",
        "Refer SIU", "Mismatched finance notices", 3, "Billing"),
    row("FR-B05", "Billing & premium", "Commission churning / twisting",
        "Agent rewrites or replaces policies to earn new-business commission.", "Agent", ALL, "", PC, "All",
        "Agency, Policy admin", "Policy", "Renewal / rewrite", "High cancel-and-rewrite rate on one agent's book.", "Anomaly",
        "Rewrite rate > 3x peer average.", "Policy transactions, commissions", "Commission claw-back rules",
        "Hold commissions", "Rewrite rate by agent", 2, "Agency"),
    # ------------------------------------------------------------------ claims
    row("FR-C01", "Claims", "Loss outside policy period",
        "Loss happened before cover started or after it ended.", "Insured, Claimant", ALL, "", PC, "All",
        "Claims, Policy admin", "Policy", "First notice of loss", "Loss date before effective or after expiration date.",
        "Rule", "Loss date < effective date OR > expiration date.", "Policy period, loss date",
        "Coverage verification at FNOL", "Block payment", "Out-of-period claims", 5, "Claims", "Yes"),
    row("FR-C02", "Claims", "Loss after cancellation", "Claim on a policy that was already cancelled.",
        "Insured", ALL, "", PC, "All", "Claims, Policy admin", "Policy", "First notice of loss",
        "Loss date after cancellation date.", "Rule", "Status = Cancelled AND loss date > cancel date.",
        "Policy status, cancel date", "Coverage verification at FNOL", "Block payment", "Claims on cancelled policies", 5,
        "Claims", "Yes"),
    row("FR-C03", "Claims", "Payment beyond limit", "Claim payments total more than the coverage limit.",
        "Employee (adjuster), Insured", ALL, "", PC, "All", "Claims", "Payment, Coverage", "Payment",
        "Paid to date > limit.", "Rule", "Sum of payments > coverage limit.", "Limits, claim payments",
        "Hard limit check in the payment system", "Block payment", "Over-limit payment attempts", 4, "Claims", "Yes"),
    row("FR-C04", "Claims", "Deductible not applied", "Loss paid without taking the deductible.",
        "Employee (adjuster), Insured", ALL, "", PC, "HO, CP, PA", "Claims", "Payment, Coverage", "Payment",
        "Deductible applied = 0 on a policy with a deductible.", "Rule", "Policy deductible > 0 AND deductible applied = 0.",
        "Deductible, payments", "System-applied deductible", "Hold payment", "Payments missing deductible", 3, "Claims", "Yes"),
    row("FR-C05", "Claims", "Duplicate claim / double dipping",
        "Same loss claimed on two policies or with two insurers.", "Insured", ALL,
        "Industry claim databases (US ISO ClaimSearch, UK CUE, India IIB) find cross-carrier duplicates.", PC, "All",
        "Claims", "Party, Building, Vehicle", "First notice of loss", "Same insured, object and loss date on 2+ claims.",
        "Rule", "Same claimant + same object description + same loss date on different claims.",
        "Claims, objects, industry claim index", "Search claim index at FNOL", "Hold payment; refer SIU",
        "Duplicate hits", 4, "Claims / SIU", "Yes"),
    row("FR-C06", "Claims", "Duplicate / phantom vendor invoice",
        "Vendor bills twice or bills for work not done.", "Vendor", ALL, "", PC, "All", "Claims, Vendor management",
        "Payment, Invoice", "Payment", "Same invoice number paid twice.", "Rule", "Invoice number paid more than once.",
        "Invoices, payments", "Duplicate-invoice block in AP", "Block payment; recover", "Duplicate invoices", 3,
        "Claims / Finance", "Yes"),
    row("FR-C07", "Claims", "Deductible forgiveness / estimate inflation",
        "Contractor inflates the bill by the deductible so the insured pays nothing.", "Vendor, Insured", "US, Canada",
        "US-FL: roofing contractors; assignment-of-benefits abuse (AOB restricted for FL policies issued from 2023).",
        P, "HO", "Claims, Vendor management", "Building, Invoice", "Estimate / payment",
        "Vendor invoice − adjuster estimate ≈ deductible.", "Rule", "|invoice − estimate − deductible| ≤ 5% of deductible.",
        "Invoices, adjuster estimates, deductible", "Pay to adjuster estimate; insured signs deductible acknowledgement",
        "Hold payment; refer SIU", "Invoice-over-estimate gap by vendor", 3, "Claims", "Yes"),
    row("FR-C08", "Claims", "Staged accident ring",
        "Organised groups stage crashes ('swoop and squat', induced rear-ends) and feed claims to the same lawyers, clinics and shops.",
        "Claimant, Attorney, Medical provider, Vendor", "US, Canada, UK",
        "UK: crash-for-cash. US-FL/NY: PIP clinic rings. Canada-ON: staged collisions.", P, "PA, CA", "Claims",
        "Party, Vehicle", "First notice of loss / medical", "Claimants share phones or addresses; same attorney, clinic and body shop.",
        "Network", "Cluster of 3+ claims linked by shared phone, address, attorney or provider.",
        "Party contacts, attorneys, vendors", "Network scoring at FNOL; independent medical exams", "Refer SIU; hold payment",
        "Ring clusters detected", 5, "SIU", "Yes"),
    row("FR-C09", "Claims", "Early attorney / claims-management involvement",
        "Representation within days of a minor loss, often a sign of soliciting or build-up.", "Attorney, Claimant",
        "US, UK, Canada", "UK: claims-management companies. US: early letters of representation.", PC, "PA, CA, GL, HO",
        "Claims, Litigation", "Party", "First notice of loss", "Attorney date within 3 days of loss on a low reserve.",
        "Rule", "Attorney within 3 days of loss AND reserve < 10,000.", "Attorney date, reserve",
        "Fast contact with claimant; early settlement offer", "Refer SIU (soft)", "Early-representation rate by attorney", 2,
        "Claims / Litigation", "Yes"),
    row("FR-C10", "Claims", "Weather-mismatch / pre-existing damage",
        "Wind or hail claim with no storm at that place and date, or damage that existed before.", "Insured, Vendor",
        "US, Canada", "US-FL/TX: roof claims after named storms.", PC, "HO, CP", "Claims", "Building",
        "First notice of loss", "No weather event for ZIP and date; old roof already damaged at inspection.",
        "External data", "Cause in (Wind, Hail) AND no CAT event for loss ZIP within 3 days; plus roof age / inspection.",
        "Weather data, inspections, roof age", "Weather verification at FNOL; aerial imagery", "Hold payment; refer SIU",
        "Weather-mismatch claims", 4, "Claims", "Yes"),
    row("FR-C11", "Claims", "Arson for profit", "Owner burns the property to collect insurance.", "Insured",
        ALL, "", PC, "CP, HO", "Claims, Policy admin", "Building", "First notice of loss",
        "Limit increased shortly before; financial distress; vacant; total loss.", "Rule",
        "Fire claim AND limit increase within 120 days AND (NSF premium OR vacant).", "Policy changes, billing, claim notes",
        "Cause-and-origin investigation on large fires", "Hold payment; refer SIU", "Fire claims with recent limit increase",
        5, "SIU", "Yes"),
    row("FR-C12", "Claims", "Inflated contents", "Value or quantity of stolen or damaged items overstated.",
        "Insured", ALL, "", P, "HO", "Claims", "Building, Party", "Settlement", "Contents claimed > 30% of dwelling limit on theft.",
        "Rule", "Contents claimed / limit > 0.30.", "Contents schedule, limit", "Receipts or photos for high-value items",
        "Step-up verification", "Contents-to-limit ratio", 3, "Claims", "Yes"),
    row("FR-C13", "Claims", "Owner give-up / phantom theft",
        "Vehicle reported stolen but hidden, sold or dumped by the owner.", "Insured", ALL, "", P, "PA", "Claims",
        "Vehicle", "First notice of loss", "Late theft report; loan in arrears; vehicle later found burned.",
        "Rule", "Theft reported > 3 days after loss.", "Theft date, report date, recovery",
        "Telematics; check finance arrears", "Refer SIU", "Late theft reports", 3, "Claims"),
    row("FR-C14", "Claims", "Total-loss / salvage fraud", "Salvage vehicles rebuilt and re-insured, or VIN cloned.",
        "Third party, Vendor", "US, Canada", "", P, "PA", "Claims, Salvage", "Vehicle", "Bind / total loss",
        "VIN previously total-lossed.", "External data", "VIN has prior total-loss brand.", "VIN history",
        "VIN history at bind", "Block bind", "Branded-VIN hits", 3, "Underwriting"),
    row("FR-C15", "Claims", "Payee account takeover", "Bank details changed just before a large claim payment.",
        "Third party, Employee", ALL, "", PC, "All", "Claims, Billing", "Party, Payment", "Payment",
        "Bank change within 3 days before payment.", "Rule", "Payment to an account changed ≤ 3 days earlier.",
        "Bank-change log, payments", "Call-back verification on bank changes", "Hold payment", "Payments after bank change",
        4, "Claims / Finance", "Yes"),
    row("FR-C16", "Claims", "Post-termination workers comp claim",
        "Injury reported after notice of termination, dated before it.", "Claimant", "US, Canada", "", C, "WC", "Claims",
        "Party", "First notice of loss", "Report after termination; loss just before; no witnesses.", "Rule",
        "Report date > termination date AND loss date within 7 days before termination.", "Employer termination data",
        "Employer statement; recorded statement", "Refer SIU", "Post-termination claims", 3, "Claims", "Yes"),
    row("FR-C17", "Claims", "Repeat claimant", "Same person on several injury claims against different insureds.",
        "Claimant", ALL, "", PC, "PA, GL", "Claims", "Party", "First notice of loss", "3+ claims in 3 years.", "Rule",
        "Claimant on ≥ 3 claims.", "Claims, party index", "Industry index search", "Refer SIU", "Repeat claimants", 3, "SIU", "Yes"),
    row("FR-C18", "Claims", "Medical upcoding / phantom treatment",
        "Providers bill more expensive or unnecessary treatment.", "Medical provider", "US, Canada, India",
        "US-FL/NY: PIP. India: motor injury claims.", PC, "PA, WC, GL", "Claims, Medical bill review", "Invoice",
        "Medical bill", "Same treatment pattern for every patient; high bill per claimant.", "Anomaly",
        "Provider bill per claim > 2x peer average.", "Medical bills", "Bill review; fee schedules", "Hold payment",
        "Provider outliers", 4, "Medical bill review"),
    row("FR-C19", "Claims", "Excluded peril paid as covered",
        "Flood, wear-and-tear or other excluded cause recorded as a covered peril.", "Insured, Vendor, Employee",
        ALL, "", PC, "HO, CP", "Claims", "Building, Coverage", "Coverage decision",
        "Cause changes after inspection; flood zone with 'wind' damage only below waterline.", "Text",
        "Claim notes mention excluded terms while cause is covered.", "Claim notes, cause codes",
        "Coverage review on cause changes", "Hold payment", "Cause-code changes", 3, "Claims"),
    row("FR-C20", "Claims", "Aggregate / per-occurrence deductible manipulation",
        "Several occurrences combined or split to dodge a per-occurrence or aggregate deductible.", "Insured, Broker",
        ALL, "", C, "CP, GL", "Claims", "Coverage", "Settlement", "Related losses split into separate claims under the deductible.",
        "Rule", "Same insured, same cause, ≤ 7 days apart, each just under deductible.", "Claims, deductibles",
        "Occurrence definition review", "Hold payment", "Split-occurrence alerts", 3, "Claims"),
    # ------------------------------------------------------------------ reinsurance
    row("FR-R01", "Reinsurance", "Double ceding / double recovery",
        "Same risk or loss recovered from more than one treaty or reinsurer.", "Cedent", "Global",
        "Cross-market data gaps between reinsurers.", C, "All", "Reinsurance", "Treaty, Claim", "Recovery billing",
        "Total recoveries billed on a claim > paid loss.", "Rule", "Σ recovery billed per claim > paid loss.",
        "Cessions, claim payments", "Cession register with one claim → treaty allocation", "Block recovery bill",
        "Over-ceded claims", 5, "Reinsurance", "Yes"),
    row("FR-R02", "Reinsurance", "Recovery outside treaty period",
        "Loss billed to a treaty that was not in force on the loss date.", "Cedent", "Global", "", C, "All",
        "Reinsurance", "Treaty, Claim", "Recovery billing", "Loss date outside treaty dates.", "Rule",
        "Loss date < treaty start OR > treaty end.", "Treaties, claims", "Treaty attachment check",
        "Block recovery bill", "Out-of-period cessions", 4, "Reinsurance", "Yes"),
    row("FR-R03", "Reinsurance", "Aggregate deductible misapplied",
        "Aggregate stop-loss recovery billed before the annual aggregate deductible is used up.", "Cedent", "Global",
        "", C, "All", "Reinsurance", "Treaty", "Recovery billing", "Retained losses for the year < AAD.", "Rule",
        "Recovery billed > 0 AND retained treaty-year losses < AAD.", "Treaty terms, retained losses",
        "AAD erosion ledger", "Block recovery bill", "AAD erosion vs billing", 4, "Reinsurance", "Yes"),
    row("FR-R04", "Reinsurance", "Fronting scheme / offshore shell reinsurer",
        "Risk fronted 100% to an under-capitalised or unregulated reinsurer that cannot pay.", "Reinsurer, MGA",
        "Global", "", C, "All", "Reinsurance", "Treaty, Reinsurer", "Placement", "Unrated, offshore, capital < limit, no collateral.",
        "Rule", "Reinsurer rating = NR AND (capital < treaty limit OR no collateral).", "Reinsurer financials, collateral",
        "Security committee approval; collateral requirements", "Block placement", "Exposure to unrated reinsurers", 5,
        "Reinsurance", "Yes"),
    row("FR-R05", "Reinsurance", "Misrepresented risk pool (bordereau)",
        "Cedent under-reports catastrophe concentration or loss history to reinsurers.", "Cedent", "Global", "", C,
        "HO, CP", "Reinsurance", "Treaty, Building", "Placement / bordereau", "Bordereau TIV < policy-system TIV in coastal ZIPs.",
        "Rule", "Bordereau TIV / actual TIV < 0.8 for any ZIP.", "Bordereau, policy exposures",
        "Bordereau reconciled to policy system", "Hold renewal; restate bordereau", "Bordereau variance", 4,
        "Reinsurance", "Yes"),
    row("FR-R06", "Reinsurance", "Reinsurer collections manipulation",
        "Recoveries written off, offset or commuted to hide unpaid balances or kickbacks.", "Employee, Reinsurer",
        "Global", "", C, "All", "Reinsurance, Finance", "Treaty", "Collection",
        "Large write-offs; commutation well below expected value.", "Anomaly", "Commutation < 60% of actuarial value.",
        "Collections, commutations", "Dual approval for write-offs", "Refer audit", "Aged recoverables", 3, "Finance"),
    # ------------------------------------------------------------------ internal (employee) and corporate
    row("FR-I01", "Internal (employee)", "Ghost policy by underwriter",
        "Employee issues a fake policy to themselves or an accomplice, then files a claim on it.", "Employee (underwriter)",
        ALL, "", PC, "All", "Policy admin, Claims", "Policy, Party", "Bind / claim",
        "Manual issue; insured shares employee phone, address or bank; no premium; early claim.", "Network",
        "Insured contact or bank = employee's AND issued manually.", "Employee master, parties, premium",
        "Maker-checker on manual issue; employee data screening", "Block payment; refer SIU", "Employee-linked policies",
        5, "SIU / Internal audit", "Yes"),
    row("FR-I02", "Internal (employee)", "Underwriter–agent collusion (rate overrides)",
        "Underwriter gives one agent's business large unjustified discounts.", "Employee (underwriter), Agent", ALL, "",
        PC, "All", "Rating, Policy admin", "Policy", "Bind", "Overrides concentrated on one underwriter–agent pair.",
        "Anomaly", "Override ≤ −20% AND same underwriter–agent pair ≥ 3 times.", "Rating overrides",
        "Override authority limits; peer review", "Refer audit", "Override concentration", 3, "Underwriting", "Yes"),
    row("FR-I03", "Internal (employee)", "Ghost claim / payment to employee",
        "Adjuster creates or redirects a claim payment to their own account.", "Employee (adjuster)", ALL, "", PC,
        "All", "Claims, Finance", "Payment", "Payment", "Payee account = employee account.", "Network",
        "Payee bank account matches any employee bank account.", "Employee master, payments",
        "Payee screening against employee master", "Block payment; refer SIU", "Employee-linked payments", 5,
        "SIU / Internal audit", "Yes"),
    row("FR-I04", "Internal (employee)", "Payment splitting under authority",
        "Payments split to stay just under the adjuster's authority limit.", "Employee (adjuster)", ALL, "", PC, "All",
        "Claims", "Payment", "Payment", "2+ same-day payments each 90–100% of authority.", "Rule",
        "Same claim, same day, ≥ 2 payments between 90% and 100% of authority.", "Payments, authority limits",
        "Cumulative authority check", "Hold payment", "Near-limit payment clusters", 4, "Claims", "Yes"),
    row("FR-I05", "Internal (employee)", "Vendor steering / kickbacks",
        "Adjuster sends work to one vendor in return for kickbacks.", "Employee (adjuster), Vendor", ALL, "", PC, "All",
        "Claims, Vendor management", "Invoice, Party", "Assignment", "One vendor gets most of an adjuster's jobs.", "Anomaly",
        "Within a trade: one vendor gets ≥ 60% of an adjuster's ≥ 6 jobs and fair rotation would give that < 1% of the time.", "Vendor assignments", "Rotation / managed repair network",
        "Refer audit", "Vendor concentration by adjuster", 3, "Claims / Internal audit", "Yes"),
    row("FR-I06", "Internal (employee)", "Data theft / sale of customer data",
        "Employee sells claimant or policyholder data to runners or ghost brokers.", "Employee", ALL, "", PC, "All",
        "All modules", "Party", "Any", "Bulk record views unrelated to assigned work.", "Anomaly",
        "Records viewed > 5x peer average without assignment.", "Access logs", "Least-privilege access; DLP",
        "Refer security", "Unassigned record views", 4, "Security"),
    row("FR-I07", "Corporate / insurer conduct", "Reserve manipulation",
        "Case reserves understated or overstated to manage results or reinsurance recoveries.", "Employee, Management",
        ALL, "", PC, "All", "Claims, Finance, Reinsurance", "Claim", "Reserving",
        "Reserves cut just before quarter end then raised after.", "Anomaly",
        "Reserve change pattern around period ends.", "Reserve history", "Independent reserve review", "Refer audit",
        "Reserve development", 4, "Actuarial / Audit"),
    row("FR-I08", "Corporate / insurer conduct", "Systematic underpayment of valid claims",
        "Valid claims routinely underpaid or denied (insurer-side misconduct; regulators treat this as unfair claims practice).",
        "Insurer", ALL, "", PC, "All", "Claims", "Claim", "Settlement", "Settlements far below estimates; high reopen and complaint rates.",
        "Anomaly", "Paid / estimate < 60% on covered claims; complaint ratio outlier.", "Payments, estimates, complaints",
        "Claim quality audits", "Refer compliance", "Complaint ratio, reopen rate", 4, "Compliance"),
    row("FR-V01", "Vendor & provider", "Storm chasers / solicitation",
        "Contractors canvass after a storm, sign homeowners up and inflate claims.", "Vendor", "US",
        "US-FL/TX after hurricanes and hail.", P, "HO", "Claims, Vendor management", "Building, Invoice",
        "First notice of loss", "Out-of-area vendor; many claims in days after an event; same estimate templates.",
        "Anomaly", "Vendor claim count in 14 days post-event > 5x baseline.", "Vendor, claims, CAT events",
        "Preferred vendor programme; licence checks", "Step-up verification", "New vendors after CAT", 3, "Claims"),
    row("FR-V02", "Vendor & provider", "Parts substitution",
        "Shop bills for OEM parts but fits cheaper aftermarket or used parts.", "Vendor", ALL, "", PC, "PA, CA",
        "Claims", "Vehicle, Invoice", "Repair", "OEM parts billed; re-inspection finds aftermarket.", "External data",
        "Re-inspection mismatch.", "Invoices, re-inspection", "Random re-inspections", "Recover", "Re-inspection fail rate",
        2, "Claims"),
]


PRODUCTS = {"HO": "HO-3 Homeowners", "PA": "Personal Auto", "CP": "Commercial Property", "CA": "Commercial Auto",
            "WC": "Workers Compensation", "GL": "Commercial General Liability"}


def _products(lob: str) -> str:
    if lob.strip() == "All":
        return "All products"
    return ", ".join(PRODUCTS.get(x.strip(), x.strip()) for x in lob.split(","))


def load() -> pd.DataFrame:
    df = pd.DataFrame(ROWS, columns=COLUMNS)
    df.insert(COLUMNS.index("lob") + 1, "product", df.lob.apply(_products))
    df["severity"] = df.severity.astype(int)
    return df


SUGGESTED_COLUMNS = {
    "perpetrator": "Who commits it: insured, claimant, agent, vendor, attorney, employee, cedent, reinsurer, insurer",
    "country_notes": "How the scheme shows up in each country and the local data sources (CUE, ISO ClaimSearch, IIB …)",
    "lifecycle_stage": "Where in the policy / claim / reinsurance lifecycle it happens, so the control sits at that gate",
    "red_flags": "Plain-language indicators an underwriter, adjuster or auditor can recognise",
    "detection_method": "Rule, anomaly, network (link analysis), text or external data",
    "detection_rule": "The exact machine test the engine runs",
    "data_needed": "Data elements and external sources the rule depends on",
    "prevention_control": "Control that stops it before money moves",
    "trigger_action": "Block, hold payment, step-up verification, refer SIU, recover",
    "monitoring_kpi": "What to trend on the dashboard",
    "severity": "1 (nuisance) to 5 (large or criminal)",
    "product": "Products the scheme hits (derived from line of business)",
    "owner": "Accountable team",
    "engine_rule": "Whether SI² has a working rule for it in this demo",
}

"""SI² Fraud Engine: P&C fraud catalog → synthetic book → detect → prevent → investigate → monitor."""
import datetime as dt

import pandas as pd
import streamlit as st

from fraud import catalog, data, engine
from si2_common import branding, gate

branding.page("Fraud Engine",
              "Policy, billing, claims, reinsurance and internal fraud: detect it, stop it before money moves, and keep watching.")
gate.require_access()

STEPS = ["Overview", "1 · Fraud catalog", "2 · Synthetic book", "3 · Run the engine", "4 · Prevent (gates)",
         "5 · SIU cases", "6 · Monitor", "Audit trail"]
DECISIONS = ["", "Confirmed fraud", "False positive · release", "Refer to SIU", "Needs more information"]


@st.cache_data(show_spinner=False)
def _book():
    return data.build()


def log(who, event, detail=""):
    st.session_state.audit.append({"time": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "by": who,
                                   "event": event, "detail": detail})


def sme():
    return st.session_state.get("sme_name") or "SME"


def run_engine():
    ss = st.session_state
    ss.alerts = engine.run(ss.d, ss.params, ss.enabled)
    ss.truth_eval, ss.metrics = engine.evaluate(ss.alerts, ss.d["truth"])
    ss.scores = engine.scores(ss.alerts, ss.d)
    log("SI²", "Engine run", f"{len(ss.alerts)} alerts from {len(ss.enabled)} rules")


def init():
    ss = st.session_state
    if "ready" in ss:
        return
    ss.audit, ss.decisions = [], {}
    ss.d = _book()
    ss.cat = catalog.load()
    ss.params = dict(engine.DEFAULTS)
    ss.enabled = set(ss.cat[ss.cat.engine_rule == "Yes"].fraud_id)
    log("SI²", "Synthetic book loaded", f"{len(ss.d['policies'])} policies, {len(ss.d['claims'])} claims")
    run_engine()
    ss.ready = True


def decision_of(row):
    return st.session_state.decisions.get((row.fraud_id, row.entity_id), {}).get("decision", "")


def with_decisions(a):
    a = a.copy()
    a["decision"] = [decision_of(r) for r in a.itertuples()]
    return a


def save_decisions(edited, original):
    n = 0
    for r, o in zip(edited.itertuples(), original.itertuples()):
        if r.decision != o.decision:
            st.session_state.decisions[(o.fraud_id, o.entity_id)] = {
                "decision": r.decision, "by": sme(), "at": dt.datetime.now().strftime("%Y-%m-%d %H:%M")}
            log(sme(), "Alert decision", f"{o.alert_id} {o.fraud_id} {o.entity_id}: {r.decision or 'cleared'}")
            n += 1
    return n


def usd(x):
    return f"${x:,.0f}"


init()
ss = st.session_state
A = with_decisions(ss.alerts)

with st.sidebar:
    st.markdown("**Workflow**")
    step = st.radio("Step", STEPS, label_visibility="collapsed", key="step")
    st.divider()
    st.text_input("SME name", key="sme_name", placeholder="Your name for decisions")
    st.metric("Open alerts", int((A.decision == "").sum()))
    st.caption(f"{len(ss.enabled)} of {len(ss.cat)} catalog fraud types have live rules")

# ------------------------------------------------------------------------------------------ Overview
if step == "Overview":
    m = ss.metrics
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Fraud types catalogued", len(ss.cat))
    c2.metric("Alerts raised", len(A))
    c3.metric("Stopped at a gate", usd(A[A.control == "Prevent"].amount_at_risk.sum()))
    c4.metric("Seeded scenarios caught", f"{m['detected']}/{m['scenarios']}")
    st.subheader("How it works")
    st.graphviz_chart("""
digraph G { rankdir=LR; bgcolor="transparent";
 node [shape=box, style="rounded,filled", fillcolor="#FFFFFF", color="#0B1B2B", fontname="Helvetica", fontsize=10];
 edge [color="#2B4CF2"];
 cat [label="Fraud catalog\\ncountry · line · LOB · product\\nmodule · object · perpetrator"];
 src [label="Policy · billing · claims\\npayments · vendors\\nreinsurance · employees"];
 eng [label="SI² Fraud Engine\\nrules · anomalies\\nnetwork links · external data", fillcolor="#E7ECFE"];
 gate [label="Prevent\\nblock bind · hold payment\\nverify · block recovery"];
 siu [label="SIU cases\\nrisk score · evidence\\nlink chart", fillcolor="#E7ECFE"];
 mon [label="Monitor\\nKPIs · trends · hot spots\\nrule precision"];
 cat -> eng; src -> eng -> gate -> siu -> mon; mon -> eng [style=dashed, label=" tune"]; }""", width="stretch")
    st.markdown(
        "**The problem.** The Coalition Against Insurance Fraud's 2022 study put U.S. insurance fraud at about "
        "**\\$308.6 billion a year** across all lines. The property and casualty part is roughly **\\$45 billion**, from the "
        "long-quoted estimate that about 10% of P&C losses involve fraud. Those figures are widely debated: a 2024 "
        "Rutgers paper by Prof. Jay Feinman argues the 10% figure rests on decades-old adjuster surveys and leaves out "
        "insurer-side misconduct. So the catalog includes insurer conduct (reserve manipulation, underpaying valid claims), "
        "and the engine measures its own hit rate instead of quoting industry totals.\n\n"
        "**The demo.** A synthetic book of 420 policies in the US, Canada, the UK and India, with about 300 claims, billing, "
        "vendor invoices, employees and four reinsurance treaties. 92 fraud scenarios are planted across every domain, "
        "plus a few genuine claims that only look suspicious. Walk the steps on the left: catalog → data → engine → "
        "gates → SIU → monitoring.")

# ------------------------------------------------------------------------------------------ 1. Catalog
elif step == STEPS[1]:
    st.subheader("Fraud catalog")
    cat = ss.cat

    def opts(col):
        vals = set()
        for v in cat[col].dropna():
            vals.update(x.strip() for x in str(v).split(","))
        return sorted(v for v in vals if v)

    f1, f2, f3, f4 = st.columns(4)
    dom = f1.multiselect("Domain", sorted(cat.domain.unique()), key="f_dom")
    ctry = f2.multiselect("Country", ["US", "Canada", "UK", "India", "Global"], key="f_ctry")
    lob = f3.multiselect("Line of business", opts("lob"), key="f_lob")
    perp = f4.multiselect("Perpetrator", opts("perpetrator"), key="f_perp")
    f5, f6, f7, f8 = st.columns(4)
    mod = f5.multiselect("Module", opts("module"), key="f_mod")
    obj = f6.multiselect("Object", opts("object"), key="f_obj")
    meth = f7.multiselect("Detection method", sorted(cat.detection_method.unique()), key="f_meth")
    live = f8.selectbox("Engine rule", ["All", "Live rule", "Catalog only"], key="f_live")
    v = cat
    for col, sel in [("domain", dom), ("countries", ctry), ("perpetrator", perp), ("module", mod), ("object", obj),
                     ("detection_method", meth)]:
        if sel:
            v = v[v[col].apply(lambda s: any(x in str(s) for x in sel))]
    if lob:
        v = v[v.lob.apply(lambda s: "All" in s or any(x in s for x in lob))]
    if live != "All":
        v = v[v.engine_rule == ("Yes" if live == "Live rule" else "No")]
    st.caption(f"{len(v)} of {len(cat)} fraud types. Edit cells or add rows; the catalog is yours to extend.")
    ed = st.data_editor(v, num_rows="dynamic", hide_index=True, width="stretch", key="cat_editor",
                        column_config={"severity": st.column_config.NumberColumn(min_value=1, max_value=5)},
                        disabled=["engine_rule"])
    c1, c2 = st.columns(2)
    if c1.button("Save catalog changes", type="primary"):
        keep = cat[~cat.fraud_id.isin(v.fraud_id)]
        new = pd.concat([keep, ed], ignore_index=True)
        new["engine_rule"] = new.engine_rule.fillna("No")
        ss.cat = new.sort_values("fraud_id").reset_index(drop=True)
        log(sme(), "Catalog updated", f"{len(ss.cat)} fraud types")
        st.success("Catalog saved.")
    c2.download_button("Download catalog (CSV)", ss.cat.to_csv(index=False), "SI2_fraud_catalog.csv", "text/csv")
    with st.expander("Columns SI² added to your list, and why"):
        st.dataframe(pd.DataFrame(catalog.SUGGESTED_COLUMNS.items(), columns=["column", "why it matters"]),
                     hide_index=True, width="stretch")
    with st.expander("Coverage: fraud types by domain and detection method"):
        st.dataframe(pd.crosstab(cat.domain, cat.detection_method, margins=True), width="stretch")

# ------------------------------------------------------------------------------------------ 2. Synthetic book
elif step == STEPS[2]:
    st.subheader("Synthetic book")
    d = ss.d
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Policies", len(d["policies"]))
    c2.metric("Claims", len(d["claims"]))
    c3.metric("Claim payments", len(d["claim_payments"]))
    c4.metric("Countries", d["policies"].country.nunique())
    c5.metric("Treaties", len(d["treaties"]))
    groups = {
        "Policies & objects": ["policies", "objects", "external"],
        "Parties & people": ["parties", "employees", "agents", "vendors", "attorneys"],
        "Billing": ["premium_payments", "refunds", "bank_changes"],
        "Claims": ["claims", "claim_payments", "invoices", "cat_events"],
        "Reinsurance": ["reinsurers", "treaties", "cessions", "bordereau"],
    }
    tabs = st.tabs(list(groups) + ["Answer key"])
    for t, (g, names) in zip(tabs, groups.items()):
        with t:
            for n in names:
                st.markdown(f"**{n}** · {len(d[n])} rows")
                st.dataframe(d[n], hide_index=True, width="stretch", height=260)
    with tabs[-1]:
        st.caption("The fraud scenarios planted in the data. The engine never reads this; it is only used to measure detection.")
        st.dataframe(d["truth"].merge(ss.cat[["fraud_id", "fraud_type"]], on="fraud_id", how="left"),
                     hide_index=True, width="stretch")

# ------------------------------------------------------------------------------------------ 3. Run
elif step == STEPS[3]:
    st.subheader("Run the engine")
    live = ss.cat[ss.cat.engine_rule == "Yes"]
    with st.expander("Rules on / off", expanded=False):
        cols = st.columns(3)
        chosen = set()
        for i, r in enumerate(live.itertuples()):
            if cols[i % 3].checkbox(f"{r.fraud_id} · {r.fraud_type}", value=r.fraud_id in ss.enabled, key=f"rule_{r.fraud_id}"):
                chosen.add(r.fraud_id)
    with st.expander("Thresholds", expanded=False):
        p = dict(ss.params)
        c1, c2, c3 = st.columns(3)
        p["late_remit_days"] = c1.number_input("Agent remittance overdue after (days)", 1, 120, p["late_remit_days"])
        p["early_attorney_days"] = c2.number_input("Early attorney within (days)", 0, 30, p["early_attorney_days"])
        p["early_attorney_reserve"] = c3.number_input("…on reserves below", 0, 100000, p["early_attorney_reserve"], step=1000)
        p["contents_ratio"] = c1.slider("Contents / dwelling limit", 0.1, 0.8, p["contents_ratio"], 0.05)
        p["bank_change_days"] = c2.number_input("Payment within N days of a bank change", 0, 30, p["bank_change_days"])
        p["ring_min_claims"] = c3.number_input("Ring: minimum linked claims", 2, 10, p["ring_min_claims"])
        p["override_pct"] = c1.slider("Rate override at or below (%)", -60.0, 0.0, p["override_pct"], 5.0)
        p["steer_share"] = c2.slider("Vendor steering share", 0.3, 1.0, p["steer_share"], 0.05)
        p["arson_window_days"] = c3.number_input("Arson: limit increase within (days)", 10, 365, p["arson_window_days"])
        p["siu_threshold"] = c1.slider("SIU referral score", 20, 100, p["siu_threshold"], 10)
    if st.button("Run the engine", type="primary"):
        ss.params, ss.enabled = p, chosen
        run_engine()
        st.rerun()
    m = ss.metrics
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Alerts", m["alerts"])
    c2.metric("Seeded scenarios caught", f"{m['detected']}/{m['scenarios']}")
    c3.metric("Extra rules on seeded cases", m["extra_on_seeded"])
    c4.metric("Alerts on clean data", m["false_positives"])
    st.caption("Extra rules on seeded cases are real corroboration (a backdated policy that is also a weather mismatch). "
               "Alerts on clean data are false positives for the SME to clear in step 4.")
    view = A.merge(m["alerts_labeled"][["alert_id", "truth"]], on="alert_id", how="left")
    flt = st.multiselect("Domain", sorted(view.domain.unique()), key="run_dom")
    if flt:
        view = view[view.domain.isin(flt)]
    st.dataframe(view[["alert_id", "fraud_id", "fraud_type", "entity", "entity_id", "evidence", "amount_at_risk",
                       "severity", "action", "truth", "decision"]], hide_index=True, width="stretch",
                 column_config={"amount_at_risk": st.column_config.NumberColumn("at risk (USD)", format="$%,.0f")})
    te = ss.truth_eval
    miss = te[~te.detected]
    if len(miss):
        st.warning(f"{len(miss)} seeded scenarios not detected with the current rules and thresholds.")
        st.dataframe(miss, hide_index=True, width="stretch")

# ------------------------------------------------------------------------------------------ 4. Prevent
elif step == STEPS[4]:
    st.subheader("Prevent: transactions stopped at a gate")
    g = A[A.control == "Prevent"]
    c1, c2, c3 = st.columns(3)
    c1.metric("Held or blocked", len(g))
    c2.metric("Amount stopped", usd(g.amount_at_risk.sum()))
    c3.metric("Waiting for SME", int((g.decision == "").sum()))
    st.caption("Each alert sits at the gate where the control acts: bind, payment, refund or reinsurance billing. "
               "Confirm to keep it stopped, release a false positive, or refer it to SIU.")
    by = g.groupby("action").agg(alerts=("alert_id", "count"), amount=("amount_at_risk", "sum")).reset_index()
    st.dataframe(by, hide_index=True, width="stretch",
                 column_config={"amount": st.column_config.NumberColumn("amount (USD)", format="$%,.0f")})
    show = st.radio("Show", ["Waiting for SME", "All"], horizontal=True, key="prev_show")
    q = g if show == "All" else g[g.decision == ""]
    if q.empty:
        st.success("Nothing waiting.")
    else:
        q = q.sort_values(["severity", "amount_at_risk"], ascending=False)
        ed = st.data_editor(
            q[["alert_id", "fraud_id", "fraud_type", "entity_id", "evidence", "amount_at_risk", "action", "decision"]],
            column_config={"decision": st.column_config.SelectboxColumn("SME decision", options=DECISIONS),
                           "amount_at_risk": st.column_config.NumberColumn("at risk (USD)", format="$%,.0f")},
            disabled=["alert_id", "fraud_id", "fraud_type", "entity_id", "evidence", "amount_at_risk", "action"],
            hide_index=True, width="stretch", key=f"prev_editor_{show}")
        if st.button("Save decisions", type="primary"):
            n = save_decisions(ed, q)
            st.success(f"{n} decision(s) saved.")
            st.rerun()

# ------------------------------------------------------------------------------------------ 5. SIU
elif step == STEPS[5]:
    st.subheader("SIU cases")
    thr = ss.params["siu_threshold"]
    s = ss.scores[ss.scores.score >= thr]
    st.caption(f"Claims scoring {thr}+. Every alert on the claim or its policy adds evidence: score = 100 × (1 − Π(1 − 0.15 × severity)), "
               "so one severity-5 alert scores 75 and two severity-3 alerts score 70.")
    st.dataframe(s, hide_index=True, width="stretch",
                 column_config={"score": st.column_config.ProgressColumn("risk score", min_value=0, max_value=100, format="%d")})
    pick = st.selectbox("Open case", list(s.claim_id), key="siu_pick") if len(s) else None
    if pick:
        d = ss.d
        c = d["claims"][d["claims"].claim_id == pick].iloc[0]
        pol = d["policies"][d["policies"].policy_id == c.policy_id].iloc[0]
        par = d["parties"].set_index("party_id")
        a = A[(A.claim_id == pick) | ((A.entity == "policy") & (A.entity_id == c.policy_id))]
        c1, c2 = st.columns(2)
        with c1:
            st.markdown(f"**{pick}** · {c.lob} · {c.cause} · loss {c.loss_date} · reported {c.report_date}")
            st.write(f"Policy {pol.policy_id} ({pol['product']}, {pol.country}-{pol.state}) {pol.eff_date} – {pol.exp_date}, "
                     f"limit {pol.limit:,.0f}, deductible {pol.deductible:,.0f}, issued {pol.issue_date} by {pol.issued_by}")
            st.write(f"Claimant {c.claimant_party} · {par.at[c.claimant_party, 'name']} · adjuster {c.adjuster_id}"
                     + (f" · attorney {c.attorney_id}" if c.attorney_id else ""))
            st.caption(c.description)
        with c2:
            pays = d["claim_payments"][d["claim_payments"].claim_id == pick]
            st.metric("Paid + reserve", f"{pays.amount.sum() + c.reserve:,.0f} {c.currency}")
            st.dataframe(pays[["cpay_id", "date", "payee_type", "payee_id", "payee_acct", "amount", "deductible_applied"]],
                         hide_index=True, width="stretch")
        st.markdown("**Alerts and evidence**")
        st.dataframe(a[["alert_id", "fraud_id", "fraud_type", "evidence", "severity", "action", "decision"]],
                     hide_index=True, width="stretch")
        # link chart: claimant, phone, address, attorney, vendors, payee accounts, employees
        dot = ['graph L { layout=neato; overlap=false; bgcolor="transparent"; node [shape=box, style="rounded,filled", '
               'fontname="Helvetica", fontsize=9, fillcolor="#FFFFFF"]; edge [color="#9AA5B1"];']
        claims = d["claims"]
        rel = claims[claims.claim_id == pick]
        ring = [comp for comp, _ in engine.rings(d, 2) if pick in comp]
        if ring:
            rel = claims[claims.claim_id.isin(ring[0])]
        emp_bank = dict(zip(d["employees"].bank_acct, d["employees"].emp_id))
        inv = d["invoices"]
        for r in rel.itertuples():
            col = "#E7ECFE" if r.claim_id == pick else "#FFFFFF"
            dot.append(f'"{r.claim_id}" [fillcolor="{col}"];')
            pp = par.loc[r.claimant_party]
            dot.append(f'"{r.claimant_party}" [label="{pp["name"]}", shape=ellipse]; "{r.claim_id}" -- "{r.claimant_party}";')
            dot.append(f'"ph{pp.phone}" [label="☎ {pp.phone}", shape=note]; "{r.claimant_party}" -- "ph{pp.phone}";')
            dot.append(f'"ad{pp.address}" [label="{pp.address}", shape=note]; "{r.claimant_party}" -- "ad{pp.address}";')
            if r.attorney_id:
                dot.append(f'"{r.attorney_id}" [label="Attorney {r.attorney_id}", fillcolor="#FDECEC"]; "{r.claim_id}" -- "{r.attorney_id}";')
            for v in inv[inv.claim_id == r.claim_id].vendor_id.unique():
                dot.append(f'"{v}" [label="Vendor {v}", fillcolor="#FFF6E5"]; "{r.claim_id}" -- "{v}";')
            for acct in d["claim_payments"][d["claim_payments"].claim_id == r.claim_id].payee_acct.unique():
                dot.append(f'"b{acct}" [label="Bank {acct}", shape=note]; "{r.claim_id}" -- "b{acct}";')
                if acct in emp_bank:
                    dot.append(f'"{emp_bank[acct]}" [label="Employee {emp_bank[acct]}", fillcolor="#FDECEC"]; "b{acct}" -- "{emp_bank[acct]}" [color="#B42318", penwidth=2];')
        dot.append("}")
        st.markdown("**Link chart**")
        st.graphviz_chart("\n".join(dict.fromkeys(dot)), width="stretch")
        dec = st.selectbox("Case decision", DECISIONS[1:], key="case_dec")
        note = st.text_input("Case note", key="case_note")
        if st.button("Record case decision", type="primary"):
            for r in a.itertuples():
                ss.decisions[(r.fraud_id, r.entity_id)] = {"decision": dec, "by": sme(),
                                                           "at": dt.datetime.now().strftime("%Y-%m-%d %H:%M")}
            log(sme(), "SIU case decision", f"{pick}: {dec}. {note}")
            st.success(f"{pick}: {dec}")
            st.rerun()

# ------------------------------------------------------------------------------------------ 6. Monitor
elif step == STEPS[6]:
    st.subheader("Monitor")
    decided = A[A.decision != ""]
    conf = int((decided.decision == "Confirmed fraud").sum())
    fp = int((decided.decision == "False positive · release").sum())
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Alerts", len(A))
    c2.metric("Stopped at gates", usd(A[A.control == "Prevent"].amount_at_risk.sum()))
    c3.metric("SIU cases", int((ss.scores.score >= ss.params["siu_threshold"]).sum()))
    c4.metric("SME decisions", len(decided))
    c5.metric("Precision", f"{conf / (conf + fp):.0%}" if conf + fp else "—", help="Confirmed fraud ÷ (confirmed + false positives)")
    t1, t2, t3, t4 = st.tabs(["Where", "Who", "Trend", "Rule performance"])
    with t1:
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Amount at risk by domain (USD)**")
            st.bar_chart(A.groupby("domain").amount_at_risk.sum().sort_values(), horizontal=True)
        with c2:
            st.markdown("**Alerts by line of business**")
            lob = A.merge(ss.d["policies"][["policy_id", "lob", "country"]], on="policy_id", how="left")
            st.bar_chart(lob.lob.fillna("Treaty / party").value_counts().sort_values(), horizontal=True)
        st.markdown("**Alerts by country**")
        st.dataframe(lob.country.fillna("Global").value_counts().rename("alerts"), width="stretch")
    with t2:
        st.caption("Hot spots: the people and firms that keep appearing in alerts.")
        d = ss.d
        j = A.merge(d["claims"][["claim_id", "adjuster_id", "attorney_id"]], on="claim_id", how="left") \
             .merge(d["policies"][["policy_id", "agent_id", "underwriter_id"]], on="policy_id", how="left")
        inv = d["invoices"].groupby("claim_id").vendor_id.agg(lambda s: ", ".join(sorted(set(s))))
        j["vendors"] = j.claim_id.map(inv)
        rows = []
        for role, col in [("Adjuster", "adjuster_id"), ("Underwriter", "underwriter_id"), ("Agent", "agent_id"),
                          ("Attorney", "attorney_id"), ("Vendor", "vendors")]:
            s = j[col].dropna()
            s = s[s != ""]
            if col == "vendors":
                s = s.str.split(", ").explode()
            for who, n in s.value_counts().head(5).items():
                rows.append({"role": role, "who": who, "alerts": int(n),
                             "fraud types": ", ".join(sorted(set(j.loc[j[col].fillna("").str.contains(who, regex=False), "fraud_id"])))})
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    with t3:
        st.markdown("**Alerts per month by domain**")
        st.bar_chart(engine.monthly(A, ss.d))
    with t4:
        perf = A.groupby(["fraud_id", "fraud_type"]).agg(alerts=("alert_id", "count"),
                                                       at_risk=("amount_at_risk", "sum")).reset_index()
        dec = A.groupby("fraud_id").decision.agg(
            confirmed=lambda s: int((s == "Confirmed fraud").sum()),
            false_pos=lambda s: int((s == "False positive · release").sum())).reset_index()
        perf = perf.merge(dec, on="fraud_id")
        perf["precision"] = [f"{c / (c + f):.0%}" if c + f else "—" for c, f in zip(perf.confirmed, perf.false_pos)]
        st.dataframe(perf, hide_index=True, width="stretch",
                     column_config={"at_risk": st.column_config.NumberColumn("at risk (USD)", format="$%,.0f")})
        st.caption("Rules with low precision get their thresholds tuned in step 3. Catalog-only fraud types are next in line for a rule.")
        st.download_button("Download alerts with decisions (CSV)", A.to_csv(index=False), "SI2_fraud_alerts.csv", "text/csv")

# ------------------------------------------------------------------------------------------ Audit
elif step == "Audit trail":
    st.subheader("Audit trail")
    a = pd.DataFrame(ss.audit)
    st.dataframe(a.iloc[::-1], hide_index=True, width="stretch")
    st.download_button("Download audit trail (CSV)", a.to_csv(index=False), "SI2_fraud_audit.csv", "text/csv")

branding.note_synthetic()
branding.footer()

# SI² Demo Apps

Five Streamlit demos for **SI² · Super Intelligence for Insurance** (https://si2insure.com).
All data is synthetic. Codes, record layouts and rating factors are illustrative.

| App file | Demo | Planned address |
|---|---|---|
| `app_canonical.py` | Canonical Data Model | https://si2-canonical.streamlit.app |
| `app_bureau.py` | Bureau Reporting Workbench (WCSTAT, WCPOLS, WCIND, WCMED) | https://si2-bureau.streamlit.app |
| `app_rules.py` | Business Rule Engine | https://si2-rules.streamlit.app |
| `app_rating.py` | Rating Engine | https://si2-rating.streamlit.app |
| `app_claims.py` | Claims Triage | https://si2-claims.streamlit.app |
| `app_migration.py` | Legacy-to-Cloud Migration Workbench | https://si2-migrate.streamlit.app |
| `app_fraud.py` | Fraud Engine | https://si2-fraud.streamlit.app |

Shared code lives in `si2_common/` (branding, access code, synthetic data, rule evaluator).

## Bureau Reporting Workbench (`bureau/`)

| File | What it does |
|---|---|
| `specparse.py` | Reads WCIO spec PDFs (layout text) into fields: record, positions, class, formats, constants, pick lists, N/A states |
| `data/catalog.json` | Field catalog parsed from WCPOLS, WCSTAT, WCIND and WCMED (2,548 fields) |
| `catalog.py` | Record keys, aliases, implied decimals, NCCI state codes, pick-list confidence, layout QA |
| `source.py` | Demo legacy source system (policy admin, claims, bill review) with seeded data problems |
| `canonical.py` | SI² canonical bureau model, source → canonical auto mapping, value → code mapping |
| `generate.py` | Canonical → bureau field map and fixed-width / flat CSV generation per spec positions |
| `edits.py` | Simulated bureau intake: parses the file by positions and runs edits; returns an error file |
| `revise.py` | Turns errors into revision proposals (rules, or Claude with `ANTHROPIC_API_KEY`) and applies approved ones |

Optional secrets for the workbench (Streamlit Cloud → app → Settings → Secrets):

```toml
ANTHROPIC_API_KEY = "sk-ant-..."
ANTHROPIC_MODEL = "claude-sonnet-5-5"
```

## Legacy-to-Cloud Migration Workbench (`migrate/`)

| File | What it does |
|---|---|
| `legacy.py` | Reads COBOL copybooks (PIC, COMP-3, OCCURS, 88-levels) and fixed-width data, DB tables, code tables, PDF forms, notes and COBOL programs; classifies uploaded files |
| `engine.py` | Discovery inventory, canonical model with synonyms, source → canonical → destination matching, pick-list value maps, transform, load (SQLite), reconciliation and the PREMCALC business-rule test |
| `samples/` | INSURE/400 demo legacy system and the cloud destination schema and pick lists |

## Fraud Engine (`fraud/`)

| File | What it does |
|---|---|
| `catalog.py` | 50 P&C fraud types (policy, billing, claims, reinsurance, internal, vendor, insurer conduct) by country, line, LOB, product, module, object and perpetrator, with red flags, detection rule, prevention control, trigger action and monitoring KPI |
| `data.py` | Synthetic book (US, Canada, UK, India): policies, objects, parties, employees, agents, vendors, billing, claims, payments, invoices, reinsurance, with 92 planted scenarios and an answer key |
| `engine.py` | 34 live rules (rules, anomaly, network rings, external data), risk scoring, gate actions, evaluation against the answer key, monthly monitoring |

## Run on your computer

```bash
pip install -r requirements.txt
streamlit run app_canonical.py
```

## Deploy on Streamlit Community Cloud

1. Put this folder in a GitHub repository (for example `si2-demos`).
2. Sign in at https://share.streamlit.io with GitHub and choose **Create app**.
3. Pick the repository, branch `main`, and set **Main file path** to one of the app files above.
4. Under **App URL**, type the planned address (for example `si2-canonical`).
5. Click **Deploy**. Repeat for each app file.

## Optional access code

To require a code before visitors see a demo, open the app's **Settings → Secrets** in Streamlit Cloud and add:

```toml
APP_ACCESS_CODE = "your-code-here"
```

Without this secret the demo is open to anyone with the link.
