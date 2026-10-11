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
