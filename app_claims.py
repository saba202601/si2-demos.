"""SI² demo: Claims Triage.

Scores first notices of loss for severity, checks common investigation indicators,
and routes each claim to fast track, standard, complex or special investigation,
with the reasons written out for the adjuster.
"""
import numpy as np
import pandas as pd
import streamlit as st

from si2_common import branding, gate

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


def triage(r: dict, cfg: dict) -> dict:
    score = CAUSES[r["cause"]][1]
    reasons = [f"{r['cause']}: {CAUSES[r['cause']][1]} base points"]
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


with st.sidebar:
    st.header("Routing settings")
    cfg = {
        "fast_track_score": st.slider("Fast track at or below score", 10, 60, 35),
        "complex_score": st.slider("Complex at or above score", 40, 100, 55),
        "siu_flags": st.slider("Special investigation at indicators", 1, 4, 2),
        "new_policy_days": st.number_input("New policy window (days)", 0, 365, 30),
        "late_report_days": st.number_input("Late report after (days)", 0, 90, 14),
    }

claims = fnol()
res = [triage(r, cfg) for r in claims.to_dict("records")]
queue = pd.concat([claims, pd.DataFrame([{k: v for k, v in r.items() if k in ("tier", "severity", "indicators")}
                                         for r in res])], axis=1)
queue["tier_rank"] = queue.tier.map({t: i for i, t in enumerate(TIER_ORDER)})
queue = queue.sort_values(["tier_rank", "severity"], ascending=[True, False])

counts = queue.tier.value_counts()
cols = st.columns(4)
for col, t in zip(cols, TIER_ORDER):
    col.metric(t, int(counts.get(t, 0)))

tab_q, tab_detail, tab_how = st.tabs(["Work queue", "Claim detail", "How scoring works"])

with tab_q:
    tiers = st.multiselect("Show", TIER_ORDER, default=TIER_ORDER)
    st.dataframe(
        queue[queue.tier.isin(tiers)].drop(columns=["tier_rank"])[
            ["claim", "tier", "severity", "indicators", "line", "cause", "estimate", "injury", "attorney",
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

branding.note_synthetic()
branding.footer()
