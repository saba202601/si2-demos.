"""SI² Role-Based Super Intelligence: 15 insurance roles, each with an SI² workbench that prepares, scores and explains
the work while the person in the role decides. Self-contained: its own synthetic insurance company, no legacy system,
no other tools. Every decision is saved; agreement and overrides feed Compliance and the Data team; changes to decision
boundaries need a second person.
"""
import datetime as dt
import json
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

from roles import book as B
from roles import si as S
from si2_common import ai, ai_ui, approvals_ui, branding, gate, identity, persist, store

branding.page("Role-Based Super Intelligence",
              "Fifteen insurance roles, one SI² each: it prepares, scores and explains the work; the person decides.")
gate.require_access()

CATALOG = json.loads((Path(__file__).resolve().parent / "roles" / "data" / "roles.json").read_text())
ROLE = {r["role"]: r for r in CATALOG}
DEPTS = list(dict.fromkeys(r["department"] for r in CATALOG))
APP, KEYS = "roles", ["role_decisions", "role_bounds"]
BOUNDS = {
    "Underwriter": {"accept_max": 55, "decline_min": 85, "authority_tiv": 2_000_000},
    "Pricing Analyst / Product Pricing": {"target_lr": 0.62, "max_rate_change_pct": 15},
    "Catastrophe / Specialty Underwriter": {"capacity_1_in_200": 1_100_000_000},
    "Claims Adjuster / Handler": {"reserve_authority": 25_000},
    "Enterprise Risk / Capital Manager": {"available_capital": 900_000_000, "max_net_cat_share": 0.25,
                                          "max_zone_share": 0.30, "min_solvency": 1.5},
}
ss = st.session_state
if "_roles_ready" not in ss:
    persist.restore(APP, KEYS)
    ss._roles_ready = True
ss.setdefault("role_decisions", [])
ss.setdefault("role_bounds", {k: dict(v) for k, v in BOUNDS.items()})
for k, v in BOUNDS.items():
    ss.role_bounds.setdefault(k, dict(v))


# ------------------------------------------------------------------------------------------ data (cached)
@st.cache_resource(show_spinner="Building the synthetic insurance company ...")
def bk():
    return B.build()


@st.cache_resource(show_spinner="Simulating 5,000 years of catastrophe events ...")
def events():
    return S.cat_event_set(bk()["policies"])


@st.cache_resource(show_spinner=False)
def reserving():
    return S.chain_ladder(S.triangle(bk()["payments"]))


@st.cache_resource(show_spinner=False)
def reinsurance_options():
    return S.optimize_cat_xol(events(), {**BOUNDS["Enterprise Risk / Capital Manager"]})


def money(x, d=0):
    if abs(x) >= 1e9:
        return f"${x / 1e9:,.2f}B"
    if abs(x) >= 1e6:
        return f"${x / 1e6:,.1f}M"
    return f"${x:,.{d}f}"


def actor():
    return ss.get("sme_name") or "SME"


def decided(role):
    return [d for d in ss.role_decisions if d["role"] == role]


# ------------------------------------------------------------------------------------------ shared panels
def decision_panel(role: str, items: pd.DataFrame, id_col: str, rec_col: str, options: list[str], key: str,
                   show_cols: list[str], context_cols: list[str] = (), height: int = 320):
    """SI² recommends; the person agrees or decides otherwise with a reason. Every decision is saved."""
    done = {d["item"]: d for d in decided(role)}
    view = items[show_cols].copy()
    view.insert(0, "your decision", [done.get(i, {}).get("decision", "") for i in items[id_col]])
    view.insert(1, "reason", [done.get(i, {}).get("reason", "") for i in items[id_col]])
    ed = st.data_editor(view, hide_index=True, width="stretch", height=height, key=f"dec_{key}_{len(done)}",
                        disabled=[c for c in view.columns if c not in ("your decision", "reason")],
                        column_config={"your decision": st.column_config.SelectboxColumn(
                            "your decision", options=[""] + options, width="medium"),
                            "reason": st.column_config.TextColumn("reason (needed when you differ)", width="medium")})
    c1, c2 = st.columns([1, 3])
    if c1.button("Save my decisions", type="primary", key=f"save_{key}"):
        n, missing = 0, []
        for r, (_, src) in zip(ed.itertuples(), items.iterrows()):
            dec, why = ed.at[r.Index, "your decision"], ed.at[r.Index, "reason"]
            dec = "" if pd.isna(dec) else str(dec)
            why = "" if pd.isna(why) else str(why)
            if not dec or done.get(src[id_col], {}).get("decision") == dec and done.get(src[id_col], {}).get("reason", "") == why:
                continue
            agreed = dec == src[rec_col] or dec.startswith("Agree")
            if not agreed and not why.strip():
                missing.append(str(src[id_col]))
                continue
            ss.role_decisions = [d for d in ss.role_decisions if not (d["role"] == role and d["item"] == src[id_col])]
            ss.role_decisions.append({"role": role, "item": src[id_col], "si_recommendation": str(src[rec_col]),
                                      "decision": dec, "agreed": bool(agreed), "reason": why, "by": actor(),
                                      "at": dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
                                      **{c: str(src[c]) for c in context_cols}})
            n += 1
        if missing:
            st.error("Give a reason where you differ from SI²: " + ", ".join(missing[:8]))
        if n:
            st.success(f"{n} decision(s) saved.")
            st.rerun()
    agree = [d["agreed"] for d in decided(role)]
    c2.caption(f"{len(agree)} decided · agreed with SI² on {sum(agree)} · decided otherwise on {len(agree) - sum(agree)}. "
               "Choose **Agree with SI²** or another decision; a different decision needs a reason.")


def boundary_panel(role: str, fmt: dict):
    """Decision boundaries the role sets for SI²; a change takes effect after a second person approves."""
    cur = ss.role_bounds[role]
    st.markdown("**Decision boundaries SI² works within**")
    cols = st.columns(len(cur))
    new = {}
    for col, (k, v) in zip(cols, cur.items()):
        label, step = fmt.get(k, (k.replace("_", " "), None))
        new[k] = col.number_input(label, value=float(v) if isinstance(v, float) else int(v), step=step, key=f"bnd_{role}_{k}")
    changed = {k: (cur[k], new[k]) for k in cur if new[k] != cur[k]}
    if changed and st.button("Submit the new boundaries for approval", key=f"bsub_{role}"):
        try:
            store.request(APP, "Decision boundaries", role, f"{role}: " + "; ".join(f"{k} {a} → {b}" for k, (a, b) in changed.items()),
                          {"role": role, "values": new}, actor())
            st.success("Submitted. A second person approves it below.")
        except ValueError as exc:
            st.error(str(exc))

    def apply(req):
        if req["status"] == "Approved":
            ss.role_bounds[req["payload"]["role"]] = dict(req["payload"]["values"])
            return f"New boundaries for {req['payload']['role']} approved by {req['checker']} and in effect."
        return f"Boundary change rejected by {req['checker']}."
    approvals_ui.render(APP, actor(), apply, note_label="Note", key=f"appr_{role[:10]}", kinds=["Decision boundaries"])


def role_header(role: str):
    r = ROLE[role]
    st.subheader(role)
    st.caption(r["department"])
    a, b = st.columns(2)
    with a.container(border=True):
        st.markdown("**Today**")
        st.write(r["today"])
    with b.container(border=True):
        st.markdown("**Tomorrow, with SI²**")
        st.write(r["tomorrow"])


def intelligence_tab(role: str):
    r = ROLE[role]
    st.markdown(f"**Primary intelligence tasks:** {r['tasks']}")
    st.markdown(f"**How SI² improves intelligence:** {r['si']}")
    st.markdown("**Implemented in this workbench**")
    for line in IMPLEMENTED.get(role, []):
        st.markdown(f"- {line}")
    st.caption("All data is a synthetic company generated inside SI². Model outputs (for example the image damage score "
               "and the catastrophe event set) are simulations that stand in for the company's own models and data feeds.")


# ------------------------------------------------------------------------------------------ the 15 workbenches
def wb_underwriter(role):
    b = bk()
    bnd = {**S.DEFAULT_UW, **ss.role_bounds[role]}
    u = S.underwrite(b["submissions"], bnd)
    m = st.columns(5)
    for col, k in zip(m, ["Accept", "Modify terms", "Refer (over authority)", "Decline"]):
        col.metric(k, int((u.si_recommendation == k).sum()))
    m[4].metric("Waiting for you", int(len(u) - len({d["item"] for d in decided(role)})))
    st.caption("SI² scores each submission from its rating model (expected loss vs quoted premium), explains the drivers, and "
               "suggests terms. You decide; large and unusual risks stay with you.")
    pick = st.selectbox("Look at a submission", u.submission_id, key="uw_pick",
                        format_func=lambda s: f"{s} · {u.set_index('submission_id').at[s, 'applicant']} · "
                                              f"{u.set_index('submission_id').at[s, 'si_recommendation']}")
    r = u.set_index("submission_id").loc[pick]
    c1, c2 = st.columns([1, 1.3])
    with c1:
        st.metric("Risk score", int(r.risk_score), help="0-100; above the accept boundary SI² suggests terms or a referral")
        st.write(f"**{r['product']}**, {r.state}, {r.cat_zone} · TIV {money(r.tiv)} · quoted {money(r.quoted_premium)} · "
                 f"expected loss {money(r.expected_loss)} (expected loss ratio {r.expected_lr:.0%})")
        st.markdown(f"**SI² recommends: {r.si_recommendation}**")
        if r.suggested_terms:
            st.markdown(f"Suggested terms: {r.suggested_terms}")
    with c2:
        mm = S.rating_model(b["submissions"]).loc[b["submissions"].index[b["submissions"].submission_id == pick][0]]
        drv = pd.DataFrame([(S.DRIVER_NAMES[k], round(float(np.exp(mm[k]) - 1) * 100, 1)) for k in S.DRIVER_NAMES
                            if k in mm and abs(mm[k]) > 0.01], columns=["driver", "effect on expected loss (%)"])
        st.markdown("Why: the drivers of expected loss")
        st.bar_chart(drv, x="driver", y="effect on expected loss (%)", horizontal=True, height=230, color="#2B4CF2")
    st.markdown("**Your decisions**")
    decision_panel(role, u, "submission_id", "si_recommendation", ["Agree with SI²", "Accept", "Modify terms", "Refer", "Decline"],
                   "uw", ["submission_id", "applicant", "product", "state", "risk_score", "si_recommendation", "suggested_terms"],
                   context_cols=["product", "state"])
    with st.expander("Portfolio concentration (property TIV by state and catastrophe zone)"):
        st.dataframe(S.concentration(b["policies"]), hide_index=True, width="stretch",
                     column_config={"tiv": st.column_config.NumberColumn(format="$%,.0f")})
    return {"submissions": len(u), "recommendations": u.si_recommendation.value_counts().to_dict(),
            "highest risk": u.nlargest(3, "risk_score")[["submission_id", "risk_score", "why"]].to_dict("records"),
            "boundaries": bnd}


def wb_pricing(role):
    b = bk()
    bnd = ss.role_bounds[role]
    a = S.rate_adequacy(b["policies"], b["claims"], target=bnd["target_lr"])
    lk = S.leakage(b["policies"])
    m = st.columns(4)
    m[0].metric("Segments flagged inadequate", int((a.si_flag == "Rate inadequate").sum()))
    m[1].metric("Book loss ratio (trended 2023-25)", f"{a.losses.sum() / a.premium.sum():.1%}", f"target {bnd['target_lr']:.0%}")
    m[2].metric("Premium leakage", money(lk.gap.sum() * 40), f"{len(lk)} policies below the rate plan")
    m[3].metric("Credibility standard", "1,082 claims")
    st.caption("SI² compares trended losses with premium by product and state, weights each segment by its credibility, "
               "and finds policies charged below the rate plan (leakage). You set the target and approve indications.")
    a2 = a.assign(proposal=lambda d: (d.indicated_change.clip(-bnd["max_rate_change_pct"] / 100, bnd["max_rate_change_pct"] / 100) * 100).round(1))
    a2["segment"] = a2["product"] + " · " + a2.state
    a2["si_recommendation"] = np.where(a2.si_flag == "Rate inadequate", "Increase " + a2.proposal.astype(str) + "%",
                                       np.where(a2.si_flag == "Possibly over-priced", "Decrease " + a2.proposal.abs().astype(str) + "%", "No change"))
    decision_panel(role, a2, "segment", "si_recommendation", ["Agree with SI²", "Smaller change", "Larger change", "No change", "Gather more data"],
                   "pr", ["segment", "premium", "loss_ratio", "credibility", "indicated_change", "si_recommendation"], height=300)
    st.markdown("**Simulate a rate change before filing it** (2,000 scenarios of trend, retention and catastrophe load)")
    segs = st.multiselect("Segments to change", a2.segment.tolist(), default=a2[a2.si_flag == "Rate inadequate"].segment.tolist()[:3], key="pr_segs")
    pct = st.slider("Rate change for those segments (%)", -15, 25, 12, key="pr_pct")
    changes = {tuple(s.split(" · ")): pct for s in segs}
    sim = S.simulate_rates(b["policies"], b["claims"], changes)
    base = S.simulate_rates(b["policies"], b["claims"], {})
    k = st.columns(4)
    k[0].metric("Loss ratio, median", f"{sim.loss_ratio.median():.1%}", f"{(sim.loss_ratio.median() - base.loss_ratio.median()) * 100:+.1f} pts")
    k[1].metric("Loss ratio, 95th percentile", f"{sim.loss_ratio.quantile(.95):.1%}")
    k[2].metric("Premium, median", money(sim.premium.median() * 40), f"{(sim.premium.median() / base.premium.median() - 1):+.1%}")
    k[3].metric("Policies kept", f"{sim.policies_kept.median() * 40:,.0f}", f"{(sim.policies_kept.median() / base.policies_kept.median() - 1):+.1%}")
    hist = pd.DataFrame({"with change": np.histogram(sim.loss_ratio, bins=np.linspace(0.3, 1.2, 37))[0],
                         "no change": np.histogram(base.loss_ratio, bins=np.linspace(0.3, 1.2, 37))[0]},
                        index=[f"{x:.0%}" for x in np.linspace(0.3, 1.2, 37)[:-1]])
    st.bar_chart(hist, height=220, color=["#2B4CF2", "#C8CDD3"], stack=False)
    with st.expander(f"Premium leakage: {len(lk)} policies charged below the rate plan"):
        st.dataframe(lk.head(60), hide_index=True, width="stretch")
        st.dataframe(lk.groupby("agent_id").gap.agg(["count", "sum"]).sort_values("sum", ascending=False).head(8)
                     .rename(columns={"count": "policies", "sum": "gap ($, sample)"}), width="stretch")
    return {"inadequate segments": a2[a2.si_flag == "Rate inadequate"][["segment", "loss_ratio", "indicated_change"]].to_dict("records"),
            "leakage policies": len(lk), "simulated median loss ratio": round(float(sim.loss_ratio.median()), 3), "target": bnd["target_lr"]}


def wb_cat(role):
    b = bk()
    ev = events()
    ep = S.ep_curve(ev)
    cap = ss.role_bounds[role]["capacity_1_in_200"]
    m = st.columns(4)
    m[0].metric("Average annual loss", money(ep["AAL"]))
    m[1].metric("1-in-100 occurrence", money(ep["OEP_AEP"]["1-in-100"][0]))
    m[2].metric("1-in-200 aggregate", money(ep["OEP_AEP"]["1-in-200"][1]), f"capacity {money(cap)}")
    m[3].metric("Simulated years", "5,000")
    curve = pd.DataFrame([{"return period (years)": rp, "occurrence loss ($M)": float(np.quantile(ep["occ"], 1 - 1 / rp)) / 1e6,
                           "aggregate loss ($M)": float(np.quantile(ep["agg"], 1 - 1 / rp)) / 1e6} for rp in (5, 10, 25, 50, 100, 200, 250, 500)])
    st.line_chart(curve, x="return period (years)", y=["occurrence loss ($M)", "aggregate loss ($M)"], height=240,
                  color=["#2B4CF2", "#0A7A3D"])
    st.markdown("**Real-time event impact**: describe an event; SI² estimates the loss on the book")
    c1, c2, c3, c4 = st.columns(4)
    peril = c1.selectbox("Peril", list(S.PERIL_RATE), key="cat_peril")
    st_ = c2.selectbox("Centre (state)", [s for s, v in B.STATES.items() if v[2] == peril], key="cat_state")
    radius = c3.slider("Radius (km)", 25, 300, 120, key="cat_rad")
    inten = c4.slider("Intensity (1 = moderate, 3 = extreme)", 0.5, 3.0, 1.8, 0.1, key="cat_int")
    lat, lon = B.STATES[st_][:2]
    imp = S.event_impact(b["policies"], peril, lat, lon, radius, inten)
    k = st.columns(4)
    k[0].metric("Policies affected", f"{imp['policies'] * 40:,}")
    k[1].metric("Loss estimate P50", money(imp["p50"]))
    k[2].metric("Range P10 - P90", f"{money(imp['p10'])} - {money(imp['p90'])}")
    k[3].metric("Insured value in footprint", money(imp["tiv"]))
    if len(imp["by_product"]):
        st.dataframe(imp["by_product"].assign(est_loss=lambda d: d.est_loss), hide_index=True, width="stretch",
                     column_config={"est_loss": st.column_config.NumberColumn("loss estimate", format="$%,.0f")})
    st.markdown("**Stress tests**")
    by = ev.groupby(["peril", "state"]).loss.agg(["mean", lambda s: s.quantile(0.98)]).reset_index()
    by.columns = ["peril", "state", "average event", "1-in-50 event"]
    two = 2 * float(ev[ev.peril == "Hurricane"].loss.quantile(0.98))
    stress = pd.DataFrame([("Two major hurricanes in one season", two), ("1-in-50 hail outbreak across TX and CO",
                           float(ev[ev.peril == "Hail"].groupby("year").loss.sum().quantile(0.98))),
                           ("1-in-100 wildfire year in CA", float(ev[ev.peril == "Wildfire"].groupby("year").loss.sum().quantile(0.99)))],
                          columns=["scenario", "loss"])
    stress["vs capacity"] = (stress.loss / cap).round(2)
    st.dataframe(stress, hide_index=True, width="stretch", column_config={"loss": st.column_config.NumberColumn(format="$%,.0f")})
    st.markdown("**Capacity decisions for large property submissions in catastrophe zones**")
    subs = b["submissions"]
    big = subs[(subs.cat_zone != "Low") & subs["product"].isin(["Homeowners", "Commercial Property"])].copy()
    big["marginal_1_in_200"] = (big.tiv * big.cat_zone.map({"Coastal hurricane": 0.11, "Wildfire WUI": 0.09, "Hail belt": 0.04}) * 40).round(-3)
    used = ep["OEP_AEP"]["1-in-200"][1]
    big["si_recommendation"] = np.where(used + big.marginal_1_in_200 > cap, "Decline: over capacity",
                                        np.where(big.marginal_1_in_200 > 5e6, "Accept with sub-limit", "Accept"))
    decision_panel(role, big, "submission_id", "si_recommendation", ["Agree with SI²", "Accept", "Accept with sub-limit", "Decline: over capacity", "Buy facultative cover"],
                   "cat", ["submission_id", "product", "state", "cat_zone", "tiv", "marginal_1_in_200", "si_recommendation"], height=260)
    return {"AAL": ep["AAL"], "1-in-200 aggregate": ep["OEP_AEP"]["1-in-200"][1], "capacity": cap,
            "event estimate": {k: imp[k] for k in ("policies", "p10", "p50", "p90")}, "stress tests": stress.to_dict("records")}


def wb_claims(role):
    b = bk()
    c = b["claims"]
    auth = ss.role_bounds[role]["reserve_authority"]
    rr = S.reserve_recommendation(c)
    op = c[c.status == "Open"].merge(rr, on="claim_no")
    op["liability_prob"] = S.liability(c).reindex(c[c.status == "Open"].index).values
    net, mem = S.fraud_network(c)
    flagged = {cl for g in mem.values() for cl in g.claim_no} if len(net) else set()
    op["fraud_flag"] = np.where(op.claim_no.isin(flagged), "Linked to a network (SIU)", "")
    op["tier"] = np.select([op.fraud_flag != "", op.injury | op.attorney | (op.rec_ultimate_p50 > 60000), op.rec_ultimate_p50 < 5000],
                           ["Special investigation", "Complex", "Fast track"], "Standard")
    op["reserve_change"] = (op.rec_reserve - op.case_reserve).round(-2)
    op["si_recommendation"] = np.where(op.reserve_change.abs() < 500, "Keep reserve", "Set reserve to " + op.rec_reserve.map(lambda x: f"${x:,.0f}"))
    m = st.columns(5)
    for col, t in zip(m, ["Fast track", "Standard", "Complex", "Special investigation"]):
        col.metric(t, int((op.tier == t).sum()))
    m[4].metric("Reserve changes over your authority", int((op.reserve_change.abs() > auth).sum()), f"authority {money(auth)}")
    st.caption("SI² triages every open claim, reads the photos (simulated image damage model with a confidence), estimates "
               "liability for auto claims, and recommends a reserve with a P10-P90 range from similar closed claims. "
               "Changes above your authority go to a second person.")
    tiers = st.multiselect("Show tiers", ["Special investigation", "Complex", "Standard", "Fast track"],
                           default=["Special investigation", "Complex"], key="cl_tiers")
    q = op[op.tier.isin(tiers)].sort_values("rec_ultimate_p50", ascending=False).head(60)
    pick = st.selectbox("Open a claim", q.claim_no.tolist(), key="cl_pick") if len(q) else None
    if pick:
        r = q.set_index("claim_no").loc[pick]
        a1, a2, a3 = st.columns(3)
        with a1.container(border=True):
            st.markdown(f"**{pick}** · {r['product']} · {r.cause}  \nAccident {r.accident_date} · reported {r.report_date}  \n"
                        f"Injury: {'yes' if r.injury else 'no'} · attorney: {'yes' if r.attorney else 'no'} · photos: {int(r.photos)}")
        with a2.container(border=True):
            dmg = "no photos" if np.isnan(r.image_damage_score) else f"{r.image_damage_score:.0f}/100 (confidence {r.image_confidence:.0%})"
            st.markdown(f"**Image damage assessment**  \n{dmg}  \n**Liability (insured at fault)**  \n"
                        + ("n/a" if np.isnan(r.liability_prob) else f"{r.liability_prob:.0%}"))
        with a3.container(border=True):
            st.markdown(f"**Reserve**  \nCurrent {money(r.case_reserve)} · paid {money(r.paid_to_date)}  \n"
                        f"SI² ultimate P50 {money(r.rec_ultimate_p50)} (P10 {money(r.p10)} - P90 {money(r.p90)})  \n"
                        f"Recommended reserve **{money(r.rec_reserve)}** from {int(r.similar_claims)} similar claims")
        if r.fraud_flag:
            st.warning(f"{r.fraud_flag}: see the SIU workbench before settling.")
    st.markdown("**Your reserve decisions**")
    decision_panel(role, q, "claim_no", "si_recommendation", ["Agree with SI²", "Keep reserve", "Set a different reserve", "Escalate to manager"],
                   "cl", ["claim_no", "tier", "product", "cause", "case_reserve", "rec_reserve", "reserve_change", "fraud_flag", "si_recommendation"],
                   context_cols=["product", "zip_income_tier"], height=300)
    big = [d for d in decided(role) if d["agreed"]]
    over = q[q.claim_no.isin([d["item"] for d in big]) & (q.reserve_change.abs() > auth)]
    if len(over) and st.button(f"Send {len(over)} reserve change(s) above my authority for approval", key="cl_auth"):
        try:
            store.request(APP, "Reserve above authority", ",".join(over.claim_no.head(10)),
                          f"{len(over)} reserve change(s) above {money(auth)}, total {money(over.reserve_change.sum())}",
                          {"claims": over.claim_no.tolist()}, actor())
            st.success("Sent to a second person (claims manager).")
        except ValueError as exc:
            st.error(str(exc))
    approvals_ui.render(APP, actor(), lambda r: f"Reserve changes {r['status'].lower()} by {r['checker']}.", key="cl_appr",
                        kinds=["Reserve above authority"])
    return {"open claims": len(op), "tiers": op.tier.value_counts().to_dict(), "reserve authority": auth,
            "largest recommended changes": op.nlargest(3, "reserve_change")[["claim_no", "case_reserve", "rec_reserve"]].to_dict("records")}


def wb_siu(role):
    b = bk()
    net, mem = S.fraud_network(b["claims"])
    m = st.columns(4)
    m[0].metric("Networks found", len(net))
    m[1].metric("Claims in networks", int(net.claims.sum()) if len(net) else 0)
    m[2].metric("Incurred in networks", money(net.incurred.sum() * 40) if len(net) else "$0")
    m[3].metric("High priority (score ≥ 80)", int((net.si_score >= 80).sum()) if len(net) else 0)
    st.caption("SI² links claims that share a phone number, an address, or the same repair shop and attorney, scores each "
               "network (size, shared links, report lag, attorney involvement) and builds the evidence package. You direct "
               "the investigation.")
    if not len(net):
        st.info("No networks above the minimum size.")
        return {}
    pick = st.selectbox("Open a network", net.network.tolist(), key="siu_pick",
                        format_func=lambda n: f"{n} · score {int(net.set_index('network').at[n, 'si_score'])} · {int(net.set_index('network').at[n, 'claims'])} claims")
    g = mem[pick]
    dot = ['graph G { layout=neato; overlap=false; bgcolor="transparent"; node [fontname="Helvetica", fontsize=9, style="filled", fillcolor="white"]; edge [color="#9AA5B1"];']
    for r in g.itertuples():
        dot.append(f'"{r.claim_no}" [shape=box, fillcolor="#E7ECFE", label="{r.claim_no}\\n{r.cause}\\n${r.paid_to_date + r.case_reserve:,.0f}"];')
        dot.append(f'"ph{r.claimant_phone}" [shape=note, label="☎ {r.claimant_phone}"]; "{r.claim_no}" -- "ph{r.claimant_phone}";')
        dot.append(f'"ad{r.claimant_address}" [shape=note, label="{r.claimant_address}"]; "{r.claim_no}" -- "ad{r.claimant_address}";')
        dot.append(f'"{r.vendor_id}" [shape=ellipse, fillcolor="#FFF6E5", label="Shop {r.vendor_id}"]; "{r.claim_no}" -- "{r.vendor_id}";')
        if r.attorney_id:
            dot.append(f'"{r.attorney_id}" [shape=ellipse, fillcolor="#FDECEC", label="Attorney {r.attorney_id}"]; "{r.claim_no}" -- "{r.attorney_id}";')
    st.graphviz_chart("\n".join(dict.fromkeys(dot)) + "}", width="stretch")
    st.markdown("**Evidence package**")
    st.dataframe(g[["claim_no", "policy_no", "product", "cause", "accident_date", "report_date", "paid_to_date", "case_reserve",
                    "claimant_phone", "claimant_address", "vendor_id", "attorney_id"]], hide_index=True, width="stretch")
    net2 = net.assign(si_recommendation=np.select([net.si_score >= 80, net.si_score >= 55], ["Open investigation", "Desk review"], "Monitor"))
    st.markdown("**Your decisions**")
    decision_panel(role, net2, "network", "si_recommendation", ["Agree with SI²", "Open investigation", "Desk review", "Refer to law enforcement",
                                                                "Close: no fraud", "Monitor"],
                   "siu", ["network", "claims", "shared_links", "incurred", "avg_report_lag_days", "si_score", "evidence", "si_recommendation"], height=260)
    with st.expander("Demo answer key (planted rings; the engine never reads this)"):
        st.dataframe(pd.DataFrame([{"network": k, "planted": ", ".join(sorted(set(v.fraud_truth) - {""})) or "none (coincidental link)"}
                                   for k, v in mem.items()]), hide_index=True, width="stretch")
    return {"networks": net.to_dict("records")[:5]}


def wb_losscontrol(role):
    b = bk()
    s = S.site_risk(b["policies"])
    per_week = st.slider("Site visits you can make per week", 2, 30, 10, key="lc_cap")
    plan = s.head(per_week * 4)
    m = st.columns(4)
    m[0].metric("Sites scored", f"{len(s) * 40:,}")
    m[1].metric("Visits in the next 4 weeks", len(plan))
    m[2].metric("Expected loss reduction (plan)", money(plan.expected_loss_reduction.sum() * 40) + " / yr")
    m[3].metric("Mitigation cost (plan)", money(plan.mitigation_cost.sum() * 40))
    st.caption("SI² scores every site from aerial roof imagery, IoT alerts, catastrophe zone and claims, recommends mitigations "
               "with the expected loss reduction, and ranks visits by the loss they can prevent. You choose the visits.")
    plan2 = plan.assign(si_recommendation=np.where(plan.site_score >= 75, "On-site visit", "Virtual inspection"))
    decision_panel(role, plan2, "policy_no", "si_recommendation", ["Agree with SI²", "On-site visit", "Virtual inspection", "Letter to client", "No action"],
                   "lc", ["policy_no", "product", "state", "cat_zone", "site_score", "recommendations", "expected_loss_reduction", "si_recommendation"])
    return {"plan": plan2[["policy_no", "site_score", "recommendations", "expected_loss_reduction"]].head(5).to_dict("records")}


def wb_actuary(role):
    b = bk()
    tri = S.triangle(b["payments"])
    cl = reserving()
    m = st.columns(4)
    m[0].metric("IBNR (chain ladder)", money(cl["ibnr_total"] * 40))
    m[1].metric("Bootstrap P50", money(cl["p50"] * 40))
    m[2].metric("P75", money(cl["p75"] * 40))
    m[3].metric("P99.5 (reserve risk)", money(cl["p995"] * 40))
    st.caption("SI² builds the paid triangle from the claims payments, selects volume-weighted development factors, bootstraps "
               "the uncertainty, discovers predictive features and monitors models every quarter. You select and sign off.")
    t1, t2, t3 = st.tabs(["Reserving", "Feature discovery", "Model monitoring"])
    with t1:
        st.dataframe((tri / 1e3).round(0), width="stretch")
        st.caption("Cumulative paid ($000, sample book) by accident year and development year.")
        st.dataframe(pd.DataFrame({"SI² factor": np.round(cl["ldf"], 3), "cumulative": np.round(cl["cdf"][:-1], 3)},
                                  index=[f"{i + 1}-{i + 2}" for i in range(len(cl["ldf"]))]).T, width="stretch")
        st.dataframe(cl["table"], width="stretch")
        h = np.histogram(cl["sims"] * 40 / 1e6, bins=30)
        st.bar_chart(pd.DataFrame({"simulations": h[0]}, index=[f"{x:,.0f}" for x in h[1][:-1]]), height=200, color="#2B4CF2")
        st.caption("Bootstrap distribution of IBNR ($M, company scale).")
        ind = pd.DataFrame([{"item": "IBNR selection", "si_recommendation": f"Book P50 {money(cl['p50'] * 40)}",
                             "detail": f"P75 {money(cl['p75'] * 40)}"}])
        decision_panel(role, ind, "item", "si_recommendation", ["Agree with SI²", "Book at P75", "Book a different amount"],
                       "act", ["item", "si_recommendation", "detail"], height=80)
    with t2:
        prod = st.selectbox("Product", list(B.PRODUCTS), key="act_prod")
        fd = S.feature_discovery(b["policies"], b["claims"], prod)
        st.dataframe(fd, hide_index=True, width="stretch")
        st.caption("Frequency lift = highest band / lowest band; signal strength = chi-square style contribution. "
                   "Candidates not in the rating plan are flagged for review.")
    with t3:
        mon = S.model_monitor(b["policies"], b["claims"])
        st.line_chart(mon, x="quarter", y=["actual", "expected"], height=220, color=["#2B4CF2", "#9AA5B1"])
        st.dataframe(mon, hide_index=True, width="stretch")
    return {"IBNR": cl["ibnr_total"] * 40, "P99.5": cl["p995"] * 40, "development factors": [round(x, 3) for x in cl["ldf"]]}


def wb_erm(role):
    b = bk()
    bnd = ss.role_bounds[role]
    opt, _ = reinsurance_options()
    chosen = next((d for d in reversed(decided("Reinsurance Specialist")) if "option_index" in d), None)
    row = opt[opt.si_choice != ""].iloc[0] if chosen is None else opt.iloc[int(chosen.get("option_index", 0))]
    cap = S.capital(b["policies"], b["claims"], events(), reserving(), S.xol(row.retention, row.limit), bnd)
    gross = S.capital(b["policies"], b["claims"], events(), reserving(), lambda x: x, bnd)
    conc = S.concentration(b["policies"], bnd["max_zone_share"])
    m = st.columns(4)
    m[0].metric("Required capital", money(cap["required"]), f"diversification {money(cap['undiversified'] - cap['required'])}")
    m[1].metric("Available capital", money(bnd["available_capital"]))
    m[2].metric("Solvency ratio", f"{cap['solvency_ratio']:.2f}", f"gross of reinsurance {gross['solvency_ratio']:.2f}")
    m[3].metric("Reinsurance in the model", f"{money(row.limit)} xs {money(row.retention)}")
    st.bar_chart(cap["components"].assign(capital=lambda d: d.capital / 1e6), x="risk", y="capital", horizontal=True, height=200,
                 color="#2B4CF2")
    lim = pd.DataFrame([
        ("Net 1-in-200 catastrophe loss / capital", cap["cat_net_200"] / bnd["available_capital"], bnd["max_net_cat_share"]),
        ("Largest state-zone share of property TIV", float(conc.share_of_tiv.max()), bnd["max_zone_share"]),
        ("Solvency ratio (minimum)", cap["solvency_ratio"], bnd["min_solvency"]),
    ], columns=["appetite measure", "current", "limit"])
    lim["status"] = [("Breach" if (c > l if i < 2 else c < l) else "Within appetite") for i, (c, l) in enumerate(zip(lim.current, lim.limit))]
    st.dataframe(lim.round(3), hide_index=True, width="stretch")
    mon = S.model_monitor(b["policies"], b["claims"])
    warn = [f"Model drift in {q}: actual / expected {v:.2f}" for q, v, a in zip(mon.quarter, mon.a_to_e, mon.alert) if a]
    warn += [f"{r.state} {r.cat_zone}: {r.share_of_tiv:.0%} of property TIV ({r.status})" for r in conc.itertuples() if r.status != "Within appetite"]
    st.markdown("**Early warnings**")
    for w in warn or ["None this quarter."]:
        st.markdown(f"- {w}")
    st.caption("Capital: premium, reserve, catastrophe (net of the reinsurance chosen by the Reinsurance Specialist, or SI²'s "
               "recommendation) and market / credit risk, combined with a correlation matrix. Illustrative standard-formula style.")
    return {"required capital": cap["required"], "solvency ratio": cap["solvency_ratio"], "gross solvency": gross["solvency_ratio"],
            "appetite": lim.to_dict("records"), "warnings": warn}


def wb_reinsurance(role):
    b = bk()
    opt, gross = reinsurance_options()
    best = opt[opt.si_choice != ""].iloc[0]
    m = st.columns(4)
    m[0].metric("Gross 1-in-200", money(gross["OEP_AEP"]["1-in-200"][1]))
    m[1].metric("SI² program", f"{money(best.limit)} xs {money(best.retention)}")
    m[2].metric("Net 1-in-200 with it", money(best.net_1_in_200))
    m[3].metric("Reinsurance premium", money(best.premium), f"rate on line {best.rate_on_line:.1%}")
    st.caption("SI² tests 16 catastrophe excess-of-loss structures against the 5,000-year event set: expected recovery, "
               "price, net 1-in-200 and total cost (margin plus 10% cost of capital), within the risk appetite.")
    st.scatter_chart(opt.assign(net=lambda d: d.net_1_in_200 / 1e6, cost=lambda d: d.total_cost / 1e6), x="net", y="cost",
                     color="within_appetite", height=240)
    opt2 = opt.assign(option=[f"{money(r.limit)} xs {money(r.retention)}" for r in opt.itertuples()],
                      si_recommendation=np.where(opt.si_choice != "", "Buy this program", "Not recommended"))
    st.markdown("**Choose the program** (the Enterprise Risk workbench uses your choice)")
    decision_panel(role, opt2.head(8), "option", "si_recommendation", ["Agree with SI²", "Buy this program", "Not recommended"],
                   "ri", ["option", "expected_recovery", "premium", "rate_on_line", "net_1_in_200", "within_appetite", "total_cost", "si_recommendation"],
                   height=300)
    for d in ss.role_decisions:
        buys = d["decision"] == "Buy this program" or (d["decision"] == "Agree with SI²" and d["si_recommendation"] == "Buy this program")
        if d["role"] == role and buys and "option_index" not in d:
            idx = opt2.index[opt2.option == d["item"]]
            d["option_index"] = int(idx[0]) if len(idx) else 0
    st.markdown("**Counterparties**")
    st.dataframe(S.counterparty(b["reinsurers"], best.expected_recovery), hide_index=True, width="stretch")
    ev = events()
    hur = ev[ev.peril == "Hurricane"]
    basis = float(np.corrcoef(hur.intensity, hur.loss)[0, 1])
    st.caption(f"Basis risk for the collateralized (parametric-style) layer: correlation between event intensity and the "
               f"company's actual loss is {basis:.2f}; the lower it is, the more an index trigger can pay differently from the loss.")
    return {"recommended": f"{best.limit:,.0f} xs {best.retention:,.0f}", "net 1-in-200": best.net_1_in_200, "basis correlation": basis}


def wb_agent(role):
    b = bk()
    gaps = S.coverage_gaps(b["policies"])
    ag = st.selectbox("Agency", b["agents"].agent_id, key="ag_pick",
                      format_func=lambda a: f"{a} · {b['agents'].set_index('agent_id').at[a, 'agency']}")
    mine = gaps[gaps.agent_id == ag].head(40)
    m = st.columns(3)
    m[0].metric("Clients with a coverage gap", mine.customer_id.nunique())
    m[1].metric("Under-insured homes and buildings", int((mine.gap == "Under-insured").sum()))
    m[2].metric("Missing flood or umbrella", int(mine.gap.isin(["No flood cover in a coastal zone", "No umbrella for a high-value home"]).sum()))
    st.caption("SI² checks each client's coverage against replacement cost, catastrophe zone, assets and limits, and ranks "
               "the conversations worth having. You decide what to recommend.")
    mine = mine.assign(item=mine.policy_no + " · " + mine.gap, si_recommendation="Discuss with client")
    decision_panel(role, mine, "item", "si_recommendation", ["Agree with SI²", "Discuss with client", "Not suitable for this client"],
                   "ag", ["item", "product", "state", "advice", "priority", "si_recommendation"])
    st.markdown("**Competitive position** (our price index vs the market, by product and state)")
    st.dataframe(S.competitive(b["policies"]), hide_index=True, width="stretch")
    return {"agency": ag, "gaps": mine.gap.value_counts().to_dict()}


def wb_service(role):
    b = bk()
    rt = S.retention(b["policies"], b["claims"])
    m = st.columns(3)
    m[0].metric("High lapse risk (≥ 60%)", int((rt.lapse_risk >= 0.6).sum()) * 40)
    m[1].metric("Renewals above market", int((rt.premium > rt.market_premium * 1.08).sum()) * 40)
    m[2].metric("Open complaints", int(rt.complaints_12m.sum()) * 40)
    st.caption("SI² brings policy, billing and claims together for each customer (personal data masked), scores lapse risk with "
               "its drivers, and suggests the next best action. You handle the conversation.")
    top = rt.head(40)
    pick = st.selectbox("Customer", top.policy_no.tolist(), key="cs_pick")
    r = top.set_index("policy_no").loc[pick]
    cl = b["claims"][b["claims"].policy_no == pick]
    a1, a2, a3 = st.columns(3)
    a1.markdown(f"**Policy {pick}**  \n{r['product']} · {r.state}  \nPremium {money(r.premium)} (market {money(r.market_premium)})  \n"
                f"Tenure {int(r.tenure_years)} years")
    a2.markdown(f"**Billing**  \nRenewal change {r.rate_change_pct:+.1f}%  \nLate payments (12 months): {int(r.late_payments_12m)}  \n"
                f"Complaints: {int(r.complaints_12m)}")
    a3.markdown(f"**Claims**  \n{len(cl)} claim(s), {int((cl.status == 'Open').sum())} open  \n**Lapse risk {r.lapse_risk:.0%}**  \n{r.drivers}")
    st.info(f"Next best action: **{r.next_best_action}**")
    top2 = top.assign(si_recommendation=top.next_best_action)
    decision_panel(role, top2, "policy_no", "si_recommendation", ["Agree with SI²", "Called: retained", "Called: will shop around", "No action"],
                   "cs", ["policy_no", "product", "lapse_risk", "drivers", "si_recommendation"])
    return {"customer": pick, "lapse risk": float(r.lapse_risk), "drivers": r.drivers, "next best action": r.next_best_action,
            "claims": len(cl)}


def wb_product(role):
    b = bk()
    perf = S.product_performance(b["policies"], b["claims"])
    st.dataframe(perf, hide_index=True, width="stretch")
    st.markdown("**Coverage gaps customers hit** (claims denied for exclusions)")
    dem = S.coverage_demand(b["claims"])
    st.dataframe(dem, hide_index=True, width="stretch")
    st.markdown("**Simulate a new endorsement**")
    c1, c2, c3, c4 = st.columns(4)
    cause = c1.selectbox("Cover", ["Sewer backup", "Flood"], key="pm_cause")
    price = c2.number_input("Annual price ($)", 10, 2000, 295, key="pm_price")
    take = c3.slider("Take-up", 0.05, 0.6, 0.25, key="pm_take")
    limit = c4.number_input("Limit ($)", 5000, 250000, 10000, step=5000, key="pm_lim")
    sim = S.simulate_endorsement(b["policies"], b["claims"], cause, price, take, limit)
    k = st.columns(4)
    k[0].metric("Buyers", f"{sim['buyers']:,.0f}")
    k[1].metric("Premium", money(sim["premium"]))
    k[2].metric("Loss ratio", f"{sim['loss_ratio']:.0%}")
    k[3].metric("Break-even price", money(sim["break_even_price"]))
    rec = "Launch at this price" if sim["loss_ratio"] <= B.TARGET_LR else f"Raise price to {money(sim['break_even_price'])}"
    item = pd.DataFrame([{"idea": f"{cause} endorsement at ${price} with a ${limit:,} limit", "loss_ratio": round(sim["loss_ratio"], 2),
                          "si_recommendation": rec}])
    decision_panel(role, item, "idea", "si_recommendation", ["Agree with SI²", "Launch at this price", "Test in one state", "Not now"],
                   "pm", ["idea", "loss_ratio", "si_recommendation"], height=80)
    return {"performance": perf.to_dict("records"), "denied": dem.head(3).to_dict("records"), "endorsement": sim}


def wb_data(role):
    b = bk()
    dq, chk = S.data_quality(b)
    st.markdown("**Data quality**")
    st.dataframe(dq, hide_index=True, width="stretch")
    st.dataframe(chk, hide_index=True, width="stretch")
    st.markdown("**Model registry and monitoring**")
    mon = S.model_monitor(b["policies"], b["claims"])
    dec = pd.DataFrame(ss.role_decisions)
    agree = dec.groupby("role").agreed.agg(["count", "mean"]).rename(columns={"count": "decisions", "mean": "agreement"}) if len(dec) else pd.DataFrame()
    reg = pd.DataFrame([
        ("Underwriting risk score", "Underwriter", "Expected loss / premium; drivers explained", f"A/E last quarter {mon.a_to_e.iloc[-1]:.2f}"),
        ("Reserve recommendation", "Claims Adjuster / Handler", "Similar-claims lognormal + image damage", "P10-P90 coverage tracked"),
        ("Catastrophe event set", "Catastrophe / Specialty Underwriter", "5,000-year synthetic event set", "Recalibrate yearly"),
        ("Fraud network detection", "Special Investigations Unit (SIU) / Fraud Investigator", "Shared phone / address / vendor + attorney", "Precision tracked by SIU outcomes"),
        ("Lapse risk", "Customer Service / Policy Service", "Logistic score with drivers", "Retention outcomes tracked"),
        ("Chain ladder + bootstrap", "Actuary (Pricing, Reserving, Capital)", "Paid triangle", "Actual vs expected each quarter"),
    ], columns=["model", "role", "method", "monitoring"])
    if len(agree):
        reg = reg.merge(agree.reset_index(), on="role", how="left")
    st.dataframe(reg, hide_index=True, width="stretch")
    st.markdown("**Insights SI² generated this week** (route each one to an owner)")
    a = S.rate_adequacy(b["policies"], b["claims"])
    net, _ = S.fraud_network(b["claims"])
    ins = pd.DataFrame([
        ("I1", f"{(a.si_flag == 'Rate inadequate').sum()} product-state segments are rate inadequate; largest: "
               f"{a.iloc[0]['product']} {a.iloc[0].state} ({a.iloc[0].indicated_change:+.0%})", "Pricing Analyst / Product Pricing"),
        ("I2", f"Model drift: {', '.join(mon[mon.alert != ''].quarter) or 'none'}", "Actuary (Pricing, Reserving, Capital)"),
        ("I3", f"{len(net)} claim networks found; top score {int(net.si_score.max()) if len(net) else 0}", "Special Investigations Unit (SIU) / Fraud Investigator"),
        ("I4", f"{int(chk.failures.iloc[1])} open claims have no reserve", "Claims Adjuster / Handler"),
        ("I5", f"{int(chk.failures.iloc[2])} policies charged >5% below the rate plan", "Pricing Analyst / Product Pricing"),
    ], columns=["insight", "finding", "si_recommendation"])
    decision_panel(role, ins, "insight", "si_recommendation", ["Agree with SI²"] + [r["role"] for r in CATALOG] + ["Dismiss"],
                   "dt", ["insight", "finding", "si_recommendation"], height=230)
    return {"data quality": chk.to_dict("records"), "models": reg.to_dict("records")}


def wb_compliance(role):
    b = bk()
    u = S.underwrite(b["submissions"], {**S.DEFAULT_UW, **ss.role_bounds["Underwriter"]})
    u = u.merge(b["submissions"][["submission_id", "zip_income_tier", "credit_tier"]], on="submission_id")
    si_out = u.assign(outcome=np.where(u.si_recommendation == "Accept", "Accept", "Other"))
    st.markdown("**Fairness monitoring: underwriting outcomes by ZIP income tier** (adverse impact ratio; below 0.80 is flagged)")
    c1, c2 = st.columns(2)
    with c1:
        st.caption("SI² recommendations (all submissions)")
        st.dataframe(S.fairness(si_out, "zip_income_tier"), hide_index=True, width="stretch")
    hum = pd.DataFrame([d for d in ss.role_decisions if d["role"] == "Underwriter"])
    with c2:
        st.caption("Human decisions so far")
        if len(hum):
            hum = hum.merge(b["submissions"][["submission_id", "zip_income_tier"]], left_on="item", right_on="submission_id", how="left")
            hum["outcome"] = np.where(hum.decision.isin(["Accept"]) | (hum.agreed & (hum.si_recommendation == "Accept")), "Accept", "Other")
            st.dataframe(S.fairness(hum, "zip_income_tier"), hide_index=True, width="stretch")
        else:
            st.info("No underwriting decisions yet.")
    st.markdown("**Restricted rating factors** (states listed are editable assumptions to confirm with counsel)")
    restr = st.text_input("States where a credit-based score may not be used for personal auto", "CA, MA, HI", key="cp_states")
    states = [x.strip().upper() for x in restr.split(",") if x.strip()]
    p = b["policies"]
    hit = p[(p["product"] == "Personal Auto") & p.state.isin(states)]
    st.write(f"The SI² rating model applies the credit factor to **{len(hit) * 40:,}** personal auto policies in {', '.join(states) or 'no state'}.")
    exc = []
    if len(hit):
        exc.append(("E1", f"Credit factor used for personal auto in {', '.join(sorted(hit.state.unique()))}", "High", "Remove the factor in those states"))
    dec = pd.DataFrame(ss.role_decisions)
    if len(dec):
        no_reason = dec[(~dec.agreed) & (dec.reason.str.strip() == "")]
        if len(no_reason):
            exc.append(("E2", f"{len(no_reason)} overrides without a reason", "Medium", "Ask the decision makers for reasons"))
        over = dec.groupby("role").agreed.mean()
        for r_, v in over.items():
            if v < 0.5 and dec[dec.role == r_].shape[0] >= 5:
                exc.append((f"E3-{r_[:6]}", f"{r_}: SI² recommendations overridden {1 - v:.0%} of the time", "Medium",
                            "Review the boundaries or the model with the Data team"))
    exc.append(("E4", "Explainability: every SI² recommendation in this app carries its drivers; every override carries a reason", "Low", "No action"))
    ex = pd.DataFrame(exc, columns=["exception", "finding", "priority", "si_recommendation"])
    st.markdown("**Exceptions, highest priority first**")
    decision_panel(role, ex, "exception", "si_recommendation", ["Agree with SI²", "Remediate", "Accept the risk", "Escalate to the regulator liaison"],
                   "cp", ["exception", "finding", "priority", "si_recommendation"], height=200)
    st.markdown("**Audit trail** (every role's decisions, with SI²'s recommendation)")
    if len(dec):
        st.dataframe(dec.iloc[::-1], hide_index=True, width="stretch", height=260)
    st.download_button("Download the audit trail (CSV)", (dec if len(dec) else pd.DataFrame()).to_csv(index=False),
                       "SI2_role_decisions_audit.csv", "text/csv", key="cp_dl")
    appr = store.approvals(APP)
    st.caption(f"Approvals on record: {len(appr)} (boundary changes and reserve changes above authority).")
    return {"fairness SI": S.fairness(si_out, "zip_income_tier").to_dict("records"), "restricted factor policies": len(hit) * 40,
            "exceptions": ex.to_dict("records")}


def wb_strategy(role):
    b = bk()
    hs = S.horizon_scan(b["signals"], b["policies"])
    st.caption("SI² reads the signals the team tracks (illustrative here: climate science, court verdicts, regulation, "
               "technology, market), groups them into emerging risks, sizes the company's exposure and generates scenarios. "
               "You interpret them and decide what goes to the board.")
    st.dataframe(hs, hide_index=True, width="stretch", column_config={"premium_exposed": st.column_config.NumberColumn(format="$%,.0f"),
                                                                      "priority": st.column_config.ProgressColumn(min_value=0, max_value=100)})
    with st.expander(f"Signals ({len(b['signals'])})"):
        st.dataframe(b["signals"], hide_index=True, width="stretch")
    risk = st.selectbox("Generate a scenario", hs.risk.tolist(), key="sg_risk")
    base = S.EXPOSURE_RULE.get(risk, (None, None, 0.0))[2]
    sev = st.slider("Severity (extra losses on exposed business)", 0.0, 1.0, float(base), 0.05, key=f"sg_sev_{risk}")
    sc = S.scenario(risk, b["policies"], severity=sev)
    k = st.columns(3)
    k[0].metric("Policies exposed", f"{sc['policies']:,}")
    k[1].metric("Premium exposed", money(sc["premium"]))
    k[2].metric("Loss-ratio impact by year 5", f"+{sc['path'].loss_ratio_points.iloc[-1]:.1f} pts")
    st.line_chart(sc["path"], x="year", y="loss_ratio_points", height=200, color="#2B4CF2")
    IMPL = {"Wildfire in the WUI": "Tighten WUI appetite, require defensible space, revisit wildfire reinsurance.",
            "Secondary perils (hail, wind)": "Roof-age underwriting, hail deductibles in TX and CO, reinsurance for aggregate.",
            "Hurricane severity": "Coastal concentration limits, opening-protection credits, cat XoL review.",
            "Social inflation": "Early claim resolution, litigation management, auto liability rate review.",
            "Vehicle repair cost inflation": "Severity trend in auto rates, repair network strategy.",
            "Cyber systemic event": "Cloud-outage exclusions or sub-limits, accumulation scenarios, controls-based pricing.",
            "Flood outside mapped zones": "Offer flood endorsements beyond mapped zones.",
            "AI-enabled fraud": "Image and document forensics in claims, SIU network monitoring.",
            "PFAS liability": "Review exclusions and exposure in commercial lines.",
            "Extreme heat": "Loss control for heat-sensitive operations.",
            "AI governance and fairness rules": "Model governance, fairness testing and explanations (see Compliance)."}
    item = pd.DataFrame([{"risk": risk, "implication": IMPL.get(risk, "Monitor."),
                          "si_recommendation": "Board agenda" if sc["path"].loss_ratio_points.iloc[-1] >= 1 else "Monitor"}])
    st.info(f"Strategic implication: {item.implication.iloc[0]}")
    decision_panel(role, item, "risk", "si_recommendation", ["Agree with SI²", "Board agenda", "Monitor", "Dismiss"],
                   "sg", ["risk", "implication", "si_recommendation"], height=80)
    return {"top risks": hs.head(5)[["risk", "priority", "premium_exposed"]].to_dict("records"), "scenario": risk,
            "loss ratio points year 5": float(sc["path"].loss_ratio_points.iloc[-1])}


WORKBENCH = {
    "Underwriter": wb_underwriter, "Pricing Analyst / Product Pricing": wb_pricing, "Catastrophe / Specialty Underwriter": wb_cat,
    "Claims Adjuster / Handler": wb_claims, "Special Investigations Unit (SIU) / Fraud Investigator": wb_siu,
    "Loss Control / Risk Engineering Specialist": wb_losscontrol, "Actuary (Pricing, Reserving, Capital)": wb_actuary,
    "Enterprise Risk / Capital Manager": wb_erm, "Reinsurance Specialist": wb_reinsurance,
    "Agent / Broker / Producer Support": wb_agent, "Customer Service / Policy Service": wb_service, "Product Manager": wb_product,
    "Data / Analytics / Insights Teams": wb_data, "Compliance / Regulatory / Audit": wb_compliance,
    "Strategy / Emerging Risk Teams": wb_strategy,
}
IMPLEMENTED = {
    "Underwriter": ["Risk score from the rating model with explained drivers", "Accept / modify / refer / decline with suggested terms",
                    "Decision boundaries (accept, decline, authority) changed only with a second person", "Portfolio concentration by state and catastrophe zone"],
    "Pricing Analyst / Product Pricing": ["Trended loss ratio and credibility-weighted indications by product and state",
                                          "Premium leakage: policies charged below the rate plan", "Monte Carlo simulation of rate changes (2,000 scenarios)"],
    "Catastrophe / Specialty Underwriter": ["5,000-year synthetic event set, AAL and occurrence / aggregate curves", "Real-time event impact with P10-P90",
                                            "Stress tests and capacity decisions for large submissions"],
    "Claims Adjuster / Handler": ["Triage of every open claim", "Image damage assessment (simulated) and liability for auto",
                                  "Reserve with P10-P90 from similar claims", "Changes above authority go to a second person", "Early fraud flag from SIU networks"],
    "Special Investigations Unit (SIU) / Fraud Investigator": ["Network detection over shared phones, addresses, shops and attorneys",
                                                               "Scored, prioritized networks with evidence package and link chart"],
    "Loss Control / Risk Engineering Specialist": ["Site risk from aerial roof score, IoT alerts, catastrophe zone and claims",
                                                   "Mitigations with expected loss reduction and cost", "Visit plan within your weekly capacity"],
    "Actuary (Pricing, Reserving, Capital)": ["Paid triangle, chain ladder and bootstrap uncertainty", "Automatic feature discovery",
                                              "Quarterly actual-vs-expected monitoring with drift alerts"],
    "Enterprise Risk / Capital Manager": ["Premium, reserve, catastrophe and market risk aggregated with correlations",
                                          "Solvency ratio net and gross of reinsurance", "Risk-appetite limits and early warnings"],
    "Reinsurance Specialist": ["16 catastrophe XoL structures optimized on cost and net 1-in-200", "Counterparty and concentration checks", "Basis-risk measure"],
    "Agent / Broker / Producer Support": ["Coverage gap analysis per client (under-insured, flood, umbrella, limits, cyber controls)", "Competitive price position"],
    "Customer Service / Policy Service": ["Customer view across policy, billing and claims", "Lapse risk with drivers and next best action"],
    "Product Manager": ["Product performance and indications", "Coverage gaps from denied claims", "Endorsement simulator with break-even price"],
    "Data / Analytics / Insights Teams": ["Data-quality checks", "Model registry with monitoring and human agreement rates", "Insight feed routed to owners"],
    "Compliance / Regulatory / Audit": ["Adverse impact ratio by group for SI² and for people", "Restricted-factor check", "Prioritized exceptions",
                                        "Complete audit trail of every role's decisions"],
    "Strategy / Emerging Risk Teams": ["Signals grouped into emerging risks with exposure and priority", "Scenario generator with loss-ratio impact",
                                       "Strategic implications and board decision"],
}


# ------------------------------------------------------------------------------------------ page
with st.sidebar:
    identity.name_input("Your name", "sme_name", "Name for decisions and approvals")
    persist.sidebar(APP)
    dept = st.selectbox("Department", ["Overview"] + DEPTS, key="dept")
    role = None
    if dept != "Overview":
        role = st.radio("Role", [r["role"] for r in CATALOG if r["department"] == dept], key=f"role_{dept[:12]}")

if role is None:
    st.subheader("Fifteen roles, one SI² each")
    st.markdown("Every role keeps the decision. SI² does the preparation a person cannot do at scale: scoring every case, "
                "reading every signal, simulating thousands of scenarios, and explaining each recommendation. "
                "Choose a department and role in the sidebar.")
    dec = pd.DataFrame(ss.role_decisions)
    stats = dec.groupby("role").agreed.agg(["count", "mean"]) if len(dec) else pd.DataFrame(columns=["count", "mean"])
    for d in DEPTS:
        st.markdown(f"#### {d}")
        cols = st.columns(3)
        for col, r in zip(cols, [x for x in CATALOG if x["department"] == d]):
            with col.container(border=True):
                n = int(stats.loc[r["role"], "count"]) if r["role"] in stats.index else 0
                agr = f" · agreed with SI² {stats.loc[r['role'], 'mean']:.0%}" if n else ""
                st.markdown(f"**{r['role']}**  \n<small>{r['tasks']}</small>", unsafe_allow_html=True)
                st.caption(f"{n} decision(s){agr}")
    st.markdown("#### How people stay in charge")
    st.markdown("- **SI² recommends, the person decides**; a decision different from SI²'s needs a reason.\n"
                "- **Decision boundaries** (authority, appetite, targets) are set by the role and changed only with a second person.\n"
                "- **Everything is recorded**: Compliance sees fairness and overrides; the Data team sees model performance and agreement.\n"
                "- **Personal data is masked**; AI answers use masked facts only.")
else:
    role_header(role)
    tabs = st.tabs(["SI² workbench", "Decisions & boundaries", "Intelligence", "🤖 Ask SI²"])
    with tabs[0]:
        facts = WORKBENCH[role](role) or {}
    with tabs[1]:
        d = pd.DataFrame(decided(role))
        st.markdown(f"**{len(d)} decision(s) in this role**")
        if len(d):
            st.dataframe(d.iloc[::-1], hide_index=True, width="stretch")
        if role in ss.role_bounds:
            fmt = {"accept_max": ("Accept at or below risk score", 1), "decline_min": ("Decline at or above risk score", 1),
                   "authority_tiv": ("Your authority (TIV $)", 100000), "target_lr": ("Target loss ratio", 0.01),
                   "max_rate_change_pct": ("Largest rate change per segment (%)", 1),
                   "capacity_1_in_200": ("Catastrophe capacity, 1-in-200 ($)", 50_000_000),
                   "reserve_authority": ("Reserve change authority ($)", 5000),
                   "available_capital": ("Available capital ($)", 50_000_000), "max_net_cat_share": ("Max net 1-in-200 cat / capital", 0.01),
                   "max_zone_share": ("Max state-zone share of property TIV", 0.01), "min_solvency": ("Minimum solvency ratio", 0.05)}
            boundary_panel(role, fmt)
        else:
            st.caption("This role has no numeric decision boundaries; its decisions are recorded above.")
    with tabs[2]:
        intelligence_tab(role)
    with tabs[3]:
        ai_ui.ask_box(f"ask_{role[:12]}", lambda: {"role": role, **{k: v for k, v in facts.items()}},
                      ["What needs my attention first?", "Explain the top recommendation", "What changed since last quarter?"])

persist.checkpoint(APP, KEYS, actor())
branding.note_synthetic()
branding.footer()
