"""SI² demo: P&C Business Rule Engine.

Underwriting eligibility and referral rules written as readable conditions, edited
in a table and run against sample Personal Auto submissions, with an audit trail
of which rules fired.
"""
import numpy as np
import pandas as pd
import streamlit as st

from si2_common import branding, gate
from si2_common.rules import RuleError, compile_rule, evaluate, fields_used

branding.page("Business Rule Engine",
              "Eligibility, referral and pricing rules in plain conditions, with a full audit of every decision.")
gate.require_access()

ACTIONS = ["DECLINE", "REFER", "SURCHARGE %", "CREDIT %"]
DEFAULT_RULES = pd.DataFrame([
    (True, "R01", "Ineligible state", "state not in ['FL', 'GA', 'NC', 'NY', 'OH', 'TX']", "DECLINE", 0),
    (True, "R02", "Frequent claims", "prior_claims >= 3", "DECLINE", 0),
    (True, "R03", "Rideshare use", "use_type == 'Rideshare'", "DECLINE", 0),
    (True, "R04", "Young driver, high-value vehicle", "driver_age < 21 and vehicle_value > 40000", "REFER", 0),
    (True, "R05", "Multiple violations", "violations >= 2", "REFER", 0),
    (True, "R06", "Lapse in coverage", "coverage_lapse_days > 30", "SURCHARGE %", 10),
    (True, "R07", "High annual mileage", "annual_miles > 25000", "SURCHARGE %", 5),
    (True, "R08", "Experienced clean driver", "years_licensed >= 10 and prior_claims == 0 and violations == 0",
     "CREDIT %", 5),
], columns=["active", "rule_id", "name", "condition", "action", "value"])

FIELDS = {
    "state": "Two-letter state", "driver_age": "Age of the principal driver", "years_licensed": "Years licensed",
    "prior_claims": "At-fault claims, last 3 years", "violations": "Moving violations, last 3 years",
    "vehicle_value": "Vehicle value ($)", "model_year": "Vehicle model year",
    "use_type": "Pleasure, Commute, Business or Rideshare", "annual_miles": "Estimated annual miles",
    "coverage_lapse_days": "Days without insurance before this policy",
}


@st.cache_data
def submissions(n: int = 15, seed: int = 21) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n):
        age = int(rng.integers(17, 80))
        rows.append({
            "submission": f"SUB-{3100 + i}", "state": rng.choice(["FL", "GA", "NC", "NY", "OH", "TX", "AL", "SC"],
                                                             p=[.2, .15, .12, .1, .12, .21, .05, .05]),
            "driver_age": age, "years_licensed": max(0, age - 16 - int(rng.integers(0, 4))),
            "prior_claims": int(rng.choice([0, 0, 0, 1, 1, 2, 3])), "violations": int(rng.choice([0, 0, 0, 1, 2, 3])),
            "vehicle_value": int(rng.integers(6, 75)) * 1000, "model_year": int(rng.integers(2008, 2027)),
            "use_type": rng.choice(["Pleasure", "Commute", "Business", "Rideshare"], p=[.45, .4, .1, .05]),
            "annual_miles": int(rng.integers(4, 32)) * 1000,
            "coverage_lapse_days": int(rng.choice([0, 0, 0, 0, 15, 45, 120])),
        })
    return pd.DataFrame(rows)


def compile_all(rules: pd.DataFrame):
    compiled, problems = [], []
    for _, r in rules.iterrows():
        if not r.active or not str(r.condition).strip():
            continue
        try:
            tree = compile_rule(str(r.condition))
            unknown = fields_used(tree) - set(FIELDS)
            if unknown:
                raise RuleError(f"Unknown field: {', '.join(sorted(unknown))}.")
            compiled.append((r, tree))
        except RuleError as exc:
            problems.append(f"{r.rule_id} · {r['name']}: {exc}")
    return compiled, problems


def decide(record: dict, compiled) -> dict:
    fired = []
    for r, tree in compiled:
        try:
            if evaluate(tree, record):
                fired.append(r)
        except RuleError:
            continue
    actions = [r.action for r in fired]
    def pct(r):
        return float(r.value) if pd.notna(r.value) else 0.0

    adj = sum(pct(r) for r in fired if r.action == "SURCHARGE %") - \
        sum(pct(r) for r in fired if r.action == "CREDIT %")
    if "DECLINE" in actions:
        decision = "Decline"
    elif "REFER" in actions:
        decision = "Refer to underwriter"
    else:
        decision = "Accept"
    return {"decision": decision, "premium adjustment %": adj,
            "rules fired": ", ".join(f"{r.rule_id} {r['name']}" for r in fired) or "None"}


if "rules" not in st.session_state:
    st.session_state.rules = DEFAULT_RULES.copy()

tab_rules, tab_run, tab_one = st.tabs(["Rules", "Run on submissions", "Test one submission"])

with tab_rules:
    st.caption("Edit any cell, add rows at the bottom, or switch rules off. Conditions use the fields listed below.")
    edited = st.data_editor(
        st.session_state.rules, num_rows="dynamic", hide_index=True, width="stretch", key="rule_editor",
        column_config={
            "active": st.column_config.CheckboxColumn("On", width="small"),
            "rule_id": st.column_config.TextColumn("ID", width="small"),
            "name": st.column_config.TextColumn("Rule name"),
            "condition": st.column_config.TextColumn("Condition (when this is true…)", width="large"),
            "action": st.column_config.SelectboxColumn("…then", options=ACTIONS),
            "value": st.column_config.NumberColumn("%", min_value=0, max_value=100, step=1, width="small"),
        })
    compiled, problems = compile_all(edited)
    for p in problems:
        st.error(p)
    if not problems:
        st.success(f"{len(compiled)} active rules checked and ready.")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Fields you can use**")
        st.dataframe(pd.DataFrame(FIELDS.items(), columns=["field", "meaning"]), hide_index=True,
                     width="stretch")
    with c2:
        st.markdown("**How to write a condition**")
        st.markdown(
            "- Compare: `driver_age < 25`, `state == 'FL'`\n"
            "- Combine: `prior_claims >= 1 and violations >= 1`\n"
            "- Lists: `state in ['FL', 'GA']`, `use_type not in ['Business']`\n"
            "- Group with parentheses: `(driver_age < 21 or driver_age > 80) and violations > 0`\n\n"
            "When several rules fire, **Decline** wins over **Refer**, and surcharges and credits add up.")
    if st.button("Reset to the sample rules"):
        st.session_state.rules = DEFAULT_RULES.copy()
        st.session_state.pop("rule_editor", None)
        st.rerun()

with tab_run:
    subs = submissions()
    results = pd.DataFrame([decide(r, compiled) for r in subs.to_dict("records")])
    out = pd.concat([subs[["submission", "state", "driver_age", "prior_claims", "violations", "use_type"]], results],
                    axis=1)
    counts = results.decision.value_counts()
    c1, c2, c3 = st.columns(3)
    c1.metric("Accept", int(counts.get("Accept", 0)))
    c2.metric("Refer to underwriter", int(counts.get("Refer to underwriter", 0)))
    c3.metric("Decline", int(counts.get("Decline", 0)))
    st.dataframe(out, hide_index=True, width="stretch")
    with st.expander("See the full submission data"):
        st.dataframe(subs, hide_index=True, width="stretch")
    st.download_button("Download decisions with audit trail (CSV)", out.to_csv(index=False),
                       "si2_rule_decisions.csv", "text/csv")

with tab_one:
    with st.form("one"):
        c1, c2, c3 = st.columns(3)
        rec = {
            "state": c1.selectbox("State", ["FL", "GA", "NC", "NY", "OH", "TX", "AL", "SC"]),
            "driver_age": c1.number_input("Driver age", 16, 99, 19),
            "years_licensed": c1.number_input("Years licensed", 0, 80, 2),
            "prior_claims": c2.number_input("At-fault claims (3 yrs)", 0, 10, 0),
            "violations": c2.number_input("Violations (3 yrs)", 0, 10, 1),
            "vehicle_value": c2.number_input("Vehicle value ($)", 1000, 250000, 48000, step=1000),
            "model_year": c3.number_input("Model year", 1990, 2027, 2024),
            "use_type": c3.selectbox("Use", ["Pleasure", "Commute", "Business", "Rideshare"]),
            "annual_miles": c3.number_input("Annual miles", 0, 100000, 12000, step=1000),
            "coverage_lapse_days": c3.number_input("Days without coverage", 0, 3650, 0),
        }
        go = st.form_submit_button("Run rules", type="primary")
    res = decide(rec, compiled)
    tone = {"Accept": st.success, "Refer to underwriter": st.warning, "Decline": st.error}[res["decision"]]
    tone(f"**{res['decision']}** · premium adjustment {res['premium adjustment %']:+.0f}%")
    st.write("Rules fired:", res["rules fired"])

branding.note_synthetic()
branding.footer()
