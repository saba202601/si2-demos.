"""SI² demo: Claims Triage.

Scores first notices of loss for severity, checks common investigation indicators,
and routes each claim to fast track, standard, complex or special investigation,
with the reasons written out for the adjuster.
"""
import datetime as dt

import numpy as np
import pandas as pd
import streamlit as st

from si2_common import ai, ai_ui, approvals_ui, branding, gate, gaps_ui, identity, persist, store
from si2_common import claims_gaps as CG

branding.page("Claims Triage",
              "Every new claim scored, flagged and routed to the right desk, with the reasons spelled out.")
gate.require_access()

CAUSES = {  # cause: (line, base severity points)
    "Rear-end collision": ("Personal Auto", 20), "Intersection collision": ("Personal Auto", 30),
    "Single-vehicle collision": ("Personal Auto", 25), "Vehicle theft": ("Personal Auto", 25),
    "Hail": ("Homeowners", 15), "Water damage": ("Homeowners", 20), "Kitchen fire": ("Homeowners", 35),
    "Wind": ("Homeowners", 20),
}
TIER_ORDER = ["Special investigation", "Complex", "Standard", "Fast track"]


@st.cache_data
def fnol(n: int = 30, seed: int = 5) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n):
        cause = rng.choice(list(CAUSES))
        line = CAUSES[cause][0]
        injury = line == "Personal Auto" and "collision" in cause and rng.random() < 0.35
        rows.append({
            "claim": f"CL-{48210 + i}", "line": line, "cause": cause,
            "estimate": float(round(rng.gamma(2.2, 4200 if line == "Homeowners" else 3100), -1)),
            "injury": bool(injury), "attorney": bool(injury and rng.random() < 0.4),
            "days_to_report": int(rng.choice([0, 0, 1, 1, 2, 3, 5, 9, 18, 33])),
            "policy_age_days": int(rng.choice([12, 60, 180, 400, 900, 1500, 2600, 3100])),
            "prior_claims_3yr": int(rng.choice([0, 0, 0, 1, 1, 2, 3])),
            "police_report": bool(rng.random() < (0.85 if line == "Personal Auto" else 0.2)),
        })
    return pd.DataFrame(rows)


# a new intake channel (mobile app FNOL) with causes of loss the triage model has not seen
INCOMING = pd.DataFrame([
    ("CL-48301", "Personal Auto", "Animal collision", 3800.0, False, False, 0, 900, 0, True),
    ("CL-48302", "Personal Auto", "Glass breakage", 650.0, False, False, 1, 1500, 0, False),
    ("CL-48303", "Homeowners", "Sewer backup", 14200.0, False, False, 2, 400, 1, False),
    ("CL-48304", "Homeowners", "Lightning", 9100.0, False, False, 0, 2600, 0, False),
    ("CL-48305", "Personal Auto", "Animal collision", 5200.0, True, False, 0, 60, 0, True),
    ("CL-48306", "Personal Auto", "Rear-end collision", 7400.0, True, True, 1, 20, 2, True),
], columns=["claim", "line", "cause", "estimate", "injury", "attorney", "days_to_report", "policy_age_days",
            "prior_claims_3yr", "police_report"])
DEFAULT_CFG = {"fast_track_score": 35, "complex_score": 55, "siu_flags": 2, "new_policy_days": 30, "late_report_days": 14}
APP, KEYS = "claims", ["cfg_prod", "claim_overrides", "cause_ext", "claims_gap_ignored", "claims_audit"]


def triage(r: dict, cfg: dict, causes: dict | None = None) -> dict:
    causes = causes or CAUSES
    if r["cause"] not in causes:
        return {"tier": "Standard", "severity": 0, "indicators": 0, "flags": [],
                "score detail": [f"'{r['cause']}' has no triage score yet: manual review (see 🧩 Claim gaps)"]}
    score = causes[r["cause"]][1]
    reasons = [f"{r['cause']}: {causes[r['cause']][1]} base points"]
    amt_pts = min(35, int(r["estimate"] / 1000) * 2)
    score += amt_pts
    reasons.append(f"Estimate ${r['estimate']:,.0f}: +{amt_pts}")
    if r["injury"]:
        score += 25
        reasons.append("Bodily injury reported: +25")
    if r["attorney"]:
        score += 15
        reasons.append("Attorney already involved: +15")
    score = min(score, 100)

    flags = []
    if r["policy_age_days"] < cfg["new_policy_days"]:
        flags.append(f"Loss {r['policy_age_days']} days after the policy started")
    if r["days_to_report"] > cfg["late_report_days"]:
        flags.append(f"Reported {r['days_to_report']} days after the loss")
    if r["prior_claims_3yr"] >= 2:
        flags.append(f"{r['prior_claims_3yr']} prior claims in 3 years")
    if r["cause"] == "Vehicle theft" and not r["police_report"]:
        flags.append("Theft with no police report")
    if r["attorney"] and r["days_to_report"] <= 1:
        flags.append("Attorney involved within a day of the loss")

    if len(flags) >= cfg["siu_flags"]:
        tier = "Special investigation"
    elif score >= cfg["complex_score"]:
        tier = "Complex"
    elif score <= cfg["fast_track_score"] and not flags:
        tier = "Fast track"
    else:
        tier = "Standard"
    return {"tier": tier, "severity": score, "indicators": len(flags), "score detail": reasons, "flags": flags}


ss = st.session_state
if "_claims_ready" not in ss:
    persist.restore(APP, KEYS)
    ss._claims_ready = True
ss.setdefault("cfg_prod", dict(DEFAULT_CFG))
ss.setdefault("claim_overrides", {})
ss.setdefault("cause_ext", {})
ss.setdefault("claims_audit", [])
CAUSES_ALL = {**CAUSES, **{c: (v[0], v[1]) for c, v in ss.cause_ext.items()}}


def actor() -> str:
    return ss.get("sme_name") or "SME"


def clog(event, detail=""):
    ss.claims_audit.append({"time": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "by": actor(), "event": event,
                            "detail": detail})


def decide(req: dict) -> str:
    p = req["payload"]
    if req["kind"] == "Routing settings":
        if req["status"] == "Approved":
            ss.cfg_prod = dict(p["cfg"])
            clog("Routing settings approved for production", req["summary"])
            return f"Routing settings approved by {req['checker']} and in production."
        return f"Routing settings rejected by {req['checker']}; production unchanged."
    if req["status"] == "Approved":
        ss.claim_overrides[p["claim"]] = {"tier": p["tier"], "reason": p["reason"], "by": req["maker"],
                                          "approved_by": req["checker"], "at": req["checked_at"]}
        clog("SIU release approved", f"{p['claim']} → {p['tier']}")
        return f"{p['claim']} released from special investigation to {p['tier']} (approved by {req['checker']})."
    return f"Release of {p['claim']} rejected by {req['checker']}; it stays with special investigation."


with st.sidebar:
    identity.name_input("Your name", "sme_name", "Name for decisions and approvals")
    persist.sidebar(APP)
    st.header("Routing settings (draft)")
    p_ = ss.cfg_prod
    cfg = {
        "fast_track_score": st.slider("Fast track at or below score", 10, 60, p_["fast_track_score"]),
        "complex_score": st.slider("Complex at or above score", 40, 100, p_["complex_score"]),
        "siu_flags": st.slider("Special investigation at indicators", 1, 4, p_["siu_flags"]),
        "new_policy_days": st.number_input("New policy window (days)", 0, 365, p_["new_policy_days"]),
        "late_report_days": st.number_input("Late report after (days)", 0, 90, p_["late_report_days"]),
    }
    changed = {k: (p_[k], v) for k, v in cfg.items() if v != p_[k]}
    if changed:
        st.warning("Draft differs from production: " + "; ".join(f"{k} {a} → {b}" for k, (a, b) in changed.items()))
        if st.button("Submit settings for approval", key="cfg_submit"):
            try:
                store.request(APP, "Routing settings", "cfg", "; ".join(f"{k} {a} → {b}" for k, (a, b) in changed.items()),
                              {"cfg": cfg}, actor())
                clog("Routing settings submitted", str(changed))
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))
    else:
        st.caption("✅ Same as production.")

claims = fnol()
use_draft = st.toggle("Preview the queue with the draft settings", key="use_draft", disabled=not changed)
live_cfg = cfg if use_draft else ss.cfg_prod
res = [triage(r, live_cfg, CAUSES_ALL) for r in claims.to_dict("records")]
queue = pd.concat([claims, pd.DataFrame([{k: v for k, v in r.items() if k in ("tier", "severity", "indicators")}
                                         for r in res])], axis=1)
queue["model tier"] = queue.tier
for c_, o in ss.claim_overrides.items():
    queue.loc[queue.claim == c_, "tier"] = o["tier"]
if use_draft:
    prod_tiers = [triage(r, ss.cfg_prod, CAUSES_ALL)["tier"] for r in claims.to_dict("records")]
    moved = int(sum(a != b for a, b in zip(prod_tiers, queue["model tier"])))
    st.info(f"Draft settings move {moved} of {len(queue)} claims to a different desk.")
queue["tier_rank"] = queue.tier.map({t: i for i, t in enumerate(TIER_ORDER)})
queue = queue.sort_values(["tier_rank", "severity"], ascending=[True, False])

counts = queue.tier.value_counts()
cols = st.columns(4)
for col, t in zip(cols, TIER_ORDER):
    col.metric(t, int(counts.get(t, 0)))

n_pend = approvals_ui.pending_count(APP)
tab_q, tab_detail, tab_in, tab_gaps, tab_appr, tab_how, tab_audit = st.tabs(
    ["Work queue", "Claim detail", "📥 New FNOL (mobile app)", "🧩 Claim gaps",
     f"✅ Approvals ({n_pend})" if n_pend else "✅ Approvals", "How scoring works", "Audit trail"])

with tab_q:
    tiers = st.multiselect("Show", TIER_ORDER, default=TIER_ORDER)
    st.dataframe(
        queue[queue.tier.isin(tiers)].drop(columns=["tier_rank"])[
            ["claim", "tier", "model tier", "severity", "indicators", "line", "cause", "estimate", "injury", "attorney",
             "days_to_report", "policy_age_days", "prior_claims_3yr", "police_report"]],
        hide_index=True, width="stretch",
        column_config={"severity": st.column_config.ProgressColumn("Severity", min_value=0, max_value=100,
                                                                   format="%d"),
                       "estimate": st.column_config.NumberColumn("Estimate", format="$%.0f")})
    st.download_button("Download queue (CSV)", queue.drop(columns=["tier_rank"]).to_csv(index=False),
                       "si2_claims_queue.csv", "text/csv")

with tab_detail:
    pick = st.selectbox("Claim", queue.claim.tolist())
    i = claims.index[claims.claim == pick][0]
    r, t = claims.loc[i], res[i]
    st.subheader(f"{pick} · {t['tier']}")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown(f"**Severity {t['severity']} / 100**")
        for line in t["score detail"]:
            st.write("•", line)
    with c2:
        st.markdown(f"**Investigation indicators ({len(t['flags'])})**")
        if t["flags"]:
            for f in t["flags"]:
                st.write("•", f)
        else:
            st.write("None found.")
    st.dataframe(pd.DataFrame([r]), hide_index=True, width="stretch")
    st.markdown("**Adjuster decision**")
    cur = queue.set_index("claim").at[pick, "tier"]
    o1, o2, o3 = st.columns([1.2, 2, 1])
    new_tier = o1.selectbox("Route to", TIER_ORDER, index=TIER_ORDER.index(cur), key=f"ov_{pick}")
    why = o2.text_input("Reason", key=f"ovr_{pick}", placeholder="e.g. police report received; recorded statement consistent")
    if o3.button("Save routing", key=f"ovb_{pick}", disabled=new_tier == cur or not why.strip()):
        if cur == "Special investigation":
            try:
                store.request(APP, "SIU release", pick, f"{pick}: special investigation → {new_tier}. {why}",
                              {"claim": pick, "tier": new_tier, "reason": why}, actor())
                clog("SIU release requested", f"{pick} → {new_tier}: {why}")
                st.info("Releasing a claim from special investigation needs a second person: see ✅ Approvals.")
            except ValueError as exc:
                st.error(str(exc))
        else:
            ss.claim_overrides[pick] = {"tier": new_tier, "reason": why, "by": actor(), "at": dt.datetime.now().strftime("%Y-%m-%d %H:%M")}
            clog("Claim re-routed", f"{pick} {cur} → {new_tier}: {why}")
            st.rerun()
    if pick in ss.claim_overrides:
        st.caption(f"Routed by an adjuster: {ss.claim_overrides[pick]}")
    ai_ui.badge()
    ai_ui.explain_button("🤖 Explain this routing", f"ai_claim_{pick}", ai.answer,
                         f"Why was {pick} routed to {t['tier']}, and what should the adjuster check first?",
                         {"claim": pick, "line": r["line"], "cause": r["cause"], "estimate": r["estimate"],
                          "injury": r["injury"], "attorney": r["attorney"], "tier": t["tier"],
                          "severity detail": t["score detail"], "investigation indicators": t["flags"],
                          "routing settings": live_cfg})

with tab_in:
    st.caption("Claims from the new mobile-app FNOL channel. A cause of loss the triage model has no score for cannot be "
               "routed automatically; resolve it on 🧩 Claim gaps.")
    rin = [triage(r, live_cfg, CAUSES_ALL) for r in INCOMING.to_dict("records")]
    view = INCOMING.assign(tier=[x["tier"] for x in rin], severity=[x["severity"] for x in rin],
                           status=["Routed" if c in CAUSES_ALL else ("Manual review" if c in ss.get("claims_gap_ignored", set())
                                                                     else "Waiting on a gap") for c in INCOMING.cause])
    k1, k2 = st.columns(2)
    k1.metric("Routed automatically", int((view.status == "Routed").sum()))
    k2.metric("Waiting on a gap", int((view.status == "Waiting on a gap").sum()))
    st.dataframe(view, hide_index=True, width="stretch",
                 column_config={"estimate": st.column_config.NumberColumn("Estimate", format="$%.0f")})

with tab_gaps:
    gaps_ui.render(CG.scan(INCOMING, CAUSES_ALL, ss), CG.Handler(ss, CAUSES_ALL, actor()), key="claim_gaps",
                   intro="Causes of loss on new FNOL feeds that the triage model has no score for. Score them as an existing "
                         "cause, add them with a base severity (SI² drafts it from the most similar cause), or send those "
                         "claims to manual review.")

with tab_appr:
    st.caption("Routing settings and releases from special investigation need a second person.")
    approvals_ui.render(APP, actor(), decide, note_label="Note", key="claims_appr")

with tab_audit:
    a_ = pd.DataFrame(ss.claims_audit)
    st.dataframe(a_.iloc[::-1] if len(a_) else a_, hide_index=True, width="stretch")

with tab_how:
    st.markdown(
        "**Severity (0–100)** adds base points for the cause of loss, 2 points per $1,000 of estimate "
        "(up to 35), 25 for a reported injury and 15 when an attorney is already involved.\n\n"
        "**Investigation indicators** are common early warning signs: a loss soon after the policy starts, "
        "a late report, several prior claims, a theft with no police report, and very early attorney involvement. "
        "An indicator is a reason to look closer, not a finding of fraud.\n\n"
        "**Routing**: enough indicators send a claim to special investigation; otherwise high severity goes to "
        "the complex desk, low severity with no indicators goes to fast track, and the rest go to standard "
        "adjusters. Change the thresholds in the sidebar and the queue updates.")

persist.checkpoint(APP, KEYS, actor())
branding.note_synthetic()
branding.footer()
