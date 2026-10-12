"""SI² demo: P&C Business Rule Engine.

Underwriting eligibility and referral rules written as readable conditions, edited
in a table and run against sample Personal Auto submissions, with an audit trail
of which rules fired.
"""
import numpy as np
import pandas as pd
import streamlit as st

from si2_common import approvals_ui, branding, gate, gaps_ui, persist, store
from si2_common import rules_gaps as RG
from si2_common.rules_gaps import BASE_DOMAINS, FIELDS
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
    # imported from the 2026 filing / a field analyst: they use words the vocabulary does not have yet
    (True, "R09", "Low telematics score on delivery use", "telematics_score < 40 and use_type == 'Delivery'",
     "SURCHARGE %", 15),
    (True, "R10", "Senior driver with a violation", "drv_age >= 80 and violations >= 1", "REFER", 0),
    (True, "R11", "Florida high mileage", "state == 'FLA' and annual_miles > 20000", "SURCHARGE %", 5),
], columns=["active", "rule_id", "name", "condition", "action", "value"])



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


def to_label(field: str) -> str:
    return field.replace("_", " ").capitalize()


def compile_all(rules: pd.DataFrame):
    vocab = RG.vocabulary(FIELDS, st.session_state)
    compiled, problems = [], []
    for _, r in rules.iterrows():
        if not r.active or not str(r.condition).strip():
            continue
        try:
            tree = compile_rule(str(r.condition))
            unknown = fields_used(tree) - set(vocab)
            if unknown:
                raise RuleError(f"Unknown field: {', '.join(sorted(unknown))}. Resolve it on the 🧩 Rule gaps tab.")
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


APP = "rules"
KEYS = ["rules", "rules_prod", "fields_ext", "domains_ext", "gap_ignored", "rule_audit"]
if "_rules_ready" not in st.session_state:
    persist.restore(APP, KEYS)
    st.session_state._rules_ready = True
if "rules" not in st.session_state:
    st.session_state.rules = DEFAULT_RULES.copy()                   # the draft the SME edits
if "rules_prod" not in st.session_state:
    st.session_state.rules_prod = DEFAULT_RULES.iloc[:8].copy()     # approved and in production (R09-R11 are proposals)


def actor() -> str:
    return st.session_state.get("sme_name") or "SME"


def rule_diff(draft: pd.DataFrame, prod: pd.DataFrame) -> list[str]:
    cols = ["active", "name", "condition", "action", "value"]
    d = draft.dropna(subset=["rule_id"]).set_index("rule_id")
    p = prod.set_index("rule_id")
    out = [f"added {i}" for i in d.index if i not in p.index] + [f"removed {i}" for i in p.index if i not in d.index]
    for i in d.index.intersection(p.index):
        ch = [c for c in cols if str(d.at[i, c]) != str(p.at[i, c])]
        if ch:
            out.append(f"changed {i} ({', '.join(ch)})")
    return out


def decide_rules(req: dict) -> str:
    ss = st.session_state
    if req["status"] == "Approved":
        ss.rules_prod = req["payload"]["rules"].reset_index(drop=True)
        ss.setdefault("rule_audit", []).append({"time": req["checked_at"], "by": req["checker"],
                                                "event": "Rule set approved for production", "detail": req["summary"]})
        return f"Rule set approved by {req['checker']} and now in production."
    return f"Rule changes rejected by {req['checker']}; production is unchanged. The draft stays for rework."


with st.sidebar:
    st.text_input("Your name", key="sme_name", placeholder="Name for proposals and approvals")
    persist.sidebar(APP)

n_pend = approvals_ui.pending_count(APP)
tab_rules, tab_run, tab_one, tab_gaps, tab_appr = st.tabs(
    ["Rules (draft)", "Run on submissions", "Test one submission", "🧩 Rule gaps",
     f"✅ Approvals ({n_pend})" if n_pend else "✅ Approvals"])
compiled_prod, problems_prod = compile_all(st.session_state.rules_prod)
VOCAB = RG.vocabulary(FIELDS, st.session_state)
DOMS = RG.domains(BASE_DOMAINS, st.session_state)
EXT = getattr(st.session_state, "fields_ext", {})

with tab_rules:
    st.caption("Edit any cell, add rows at the bottom, or switch rules off. Changes are a draft: submissions are decided "
               "by the production rules until a second person approves the draft.")
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
    changes = rule_diff(edited, st.session_state.rules_prod)
    if changes:
        st.warning(f"Draft differs from production: {'; '.join(changes)}.")
        waiting = [r for r in store.approvals(APP, "Pending") if r["ref"] == "rules"] if n_pend else []
        if waiting:
            st.info(f"Submitted by {waiting[0]['maker']} at {waiting[0]['made_at']}; waiting for a second person on the "
                    "Approvals tab. Submitting again replaces that request.")
        if st.button("Submit the draft for approval", type="primary", disabled=bool(problems), key="rules_submit",
                     help="Fix the errors above first." if problems else "A different person approves it on the Approvals tab."):
            try:
                store.request(APP, "Rule set change", "rules", "; ".join(changes), {"rules": edited.reset_index(drop=True)},
                              actor())
                st.session_state.rules = edited.reset_index(drop=True)
                st.session_state.pop("rule_editor", None)
                st.session_state.setdefault("rule_audit", []).append(
                    {"time": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"), "by": actor(),
                     "event": "Rule changes submitted for approval", "detail": "; ".join(changes)})
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))
    else:
        st.caption("✅ The draft matches the rules in production.")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Fields you can use**")
        st.dataframe(pd.DataFrame([(k, m, "SME added" if k in EXT else "") for k, m in VOCAB.items()],
                                  columns=["field", "meaning", "origin"]), hide_index=True, width="stretch")
    with c2:
        st.markdown("**How to write a condition**")
        st.markdown(
            "- Compare: `driver_age < 25`, `state == 'FL'`\n"
            "- Combine: `prior_claims >= 1 and violations >= 1`\n"
            "- Lists: `state in ['FL', 'GA']`, `use_type not in ['Business']`\n"
            "- Group with parentheses: `(driver_age < 21 or driver_age > 80) and violations > 0`\n\n"
            "When several rules fire, **Decline** wins over **Refer**, and surcharges and credits add up.")
    if st.button("Discard the draft (back to production)"):
        st.session_state.rules = st.session_state.rules_prod.copy()
        st.session_state.pop("rule_editor", None)
        st.rerun()

with tab_run:
    subs = RG.extend_submissions(submissions(), st.session_state)
    st.caption(f"Decided by the {len(compiled_prod)} active rules in production (the approved rule set).")
    results = pd.DataFrame([decide(r, compiled_prod) for r in subs.to_dict("records")])
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
            "state": c1.selectbox("State", ["FL", "GA", "NC", "NY", "OH", "TX", "AL", "SC"] +
                                  [c for c in DOMS["state"] if c not in RG.US_STATES]),
            "driver_age": c1.number_input("Driver age", 16, 99, 19),
            "years_licensed": c1.number_input("Years licensed", 0, 80, 2),
            "prior_claims": c2.number_input("At-fault claims (3 yrs)", 0, 10, 0),
            "violations": c2.number_input("Violations (3 yrs)", 0, 10, 1),
            "vehicle_value": c2.number_input("Vehicle value ($)", 1000, 250000, 48000, step=1000),
            "model_year": c3.number_input("Model year", 1990, 2027, 2024),
            "use_type": c3.selectbox("Use", DOMS["use_type"]),
            "annual_miles": c3.number_input("Annual miles", 0, 100000, 12000, step=1000),
            "coverage_lapse_days": c3.number_input("Days without coverage", 0, 3650, 0),
        }
        for i, (f, spec) in enumerate(EXT.items()):
            col = (c1, c2, c3)[i % 3]
            rec[f] = (col.selectbox(to_label(f), spec["values"]) if spec["values"]
                      else col.number_input(to_label(f), value=int(RG.sample_column(f, spec, 1)[0])) if spec["type"] == "number"
                      else col.text_input(to_label(f)))
        go = st.form_submit_button("Run rules", type="primary")
    use_draft = st.toggle("Test with the draft rules instead of production", key="one_draft")
    res = decide(rec, compiled if use_draft else compiled_prod)
    tone = {"Accept": st.success, "Refer to underwriter": st.warning, "Decline": st.error}[res["decision"]]
    tone(f"**{res['decision']}** · premium adjustment {res['premium adjustment %']:+.0f}%")
    st.write("Rules fired:", res["rules fired"])

with tab_gaps:
    gaps_ui.render(RG.scan(edited, FIELDS, BASE_DOMAINS, st.session_state),
                   RG.Handler(st.session_state, edited, FIELDS, BASE_DOMAINS, "SME"), key="rule_gaps",
                   intro="Rules use a fixed vocabulary of fields and codes - the rules' canonical model. Fields and codes a rule "
                         "uses that the vocabulary does not have are listed here: map them to an existing one (the "
                         "conditions are rewritten), add them (the vocabulary, sample data and test form get them), or switch "
                         "the rules off.")
    log = getattr(st.session_state, "rule_audit", [])
    with st.expander(f"Rule vocabulary decisions ({len(log)})"):
        if log:
            st.dataframe(pd.DataFrame(log), hide_index=True, width="stretch")
        else:
            st.caption("No decisions yet.")

with tab_appr:
    def _show(r):
        p = r["payload"]["rules"]
        st.dataframe(p, hide_index=True, width="stretch", height=min(35 * (len(p) + 1) + 3, 320))
    approvals_ui.render(APP, actor(), decide_rules, note_label="Note", detail=_show, key="rules_appr")
    prod = st.session_state.rules_prod
    with st.expander(f"Rules in production ({int(prod.active.sum())} active)"):
        st.dataframe(prod, hide_index=True, width="stretch")

persist.checkpoint(APP, KEYS, actor())
branding.note_synthetic()
branding.footer()
