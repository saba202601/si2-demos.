"""SI² Rule Studio: every business rule for every line, product, state, company and role, in one governed engine.

A CEO, an underwriter, a claims adjuster or a compliance officer says what they want in plain English. SI² picks the
template, asks only the questions it still needs, shows the rule in plain English, writes its test cases, shows what
it would change on a synthetic book of business, and sends it for approval. Nothing goes live until a second person
approves it (Saba proposes, Sabasi approves).

Runs on the SI2Canonical SQL Server database (set SI2_SQL_SERVER, Windows authentication) or, without it, on an
in-memory copy of the rule library with synthetic data.
"""
from __future__ import annotations

import datetime as dt
import os
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent
# the engine lives in sql/si2_canonical in the repo, or in ..\si2_canonical_db next to the studio on a PC
ENGINE = next((p for p in (ROOT / "sql" / "si2_canonical", ROOT.parent / "si2_canonical_db", ROOT) if (p / "rule_engine.py").exists()), ROOT)
sys.path.insert(0, str(ENGINE))
sys.path.insert(0, str(ROOT))

import rule_assistant as A  # noqa: E402
import rule_engine as E  # noqa: E402
import rule_repo as R  # noqa: E402
import synthetic_book as B  # noqa: E402
from si2_common import ai, branding, gate  # noqa: E402

branding.page("Rule Studio", "Every rule for every line, product, state, company and role: asked in plain English, tested, approved by two people.")
gate.require_access()

TODAY = dt.date.today().isoformat()
LOBS = {"HO": "Homeowners / dwelling", "PA": "Personal auto", "UMB": "Umbrella", "BP": "Businessowners", "CP": "Commercial property",
        "GL": "General liability", "CA": "Commercial auto", "WC": "Workers compensation", "CYB": "Cyber"}
OPERATORS = E.OPERATORS
FIXED_VALUE = {"SIU_REFER": "SIU", "REIN_FAC": "Reinsurance"}
TEMPLATE_RULESET = {"UW_DECLINE": "UW_ELIGIBILITY", "UW_REFER": "UW_REFERRAL", "UW_AUTHORITY": "UW_AUTHORITY", "RATE_SURCHARGE": "RATING_ADJUSTMENTS",
                    "RATE_CREDIT": "RATING_ADJUSTMENTS", "RATE_CHANGE_CAP": "UW_AUTHORITY", "FORM_ATTACH": "FORMS", "COMP_PROHIBIT": "COMPLIANCE_STATE",
                    "COMP_NOTICE": "COMPLIANCE_STATE", "BILL_ACTION": "BILLING", "CLAIM_ROUTE": "CLAIMS_ROUTING", "CLAIM_AUTHORITY": "CLAIMS_AUTHORITY",
                    "SIU_REFER": "SIU_REFERRALS", "DIST_ELIGIBILITY": "DISTRIBUTION", "REIN_FAC": "REINSURANCE", "EXEC_ALERT": "EXECUTIVE_GUARDRAILS",
                    "DQ_REQUIRED": "DATA_QUALITY", "DQ_WARN": "DATA_QUALITY"}
CODE_PREFIX = {"HO": "HO", "PA": "PA", "UMB": "UMB", "BP": "BOP", "CP": "CP", "GL": "GL", "CA": "CA", "WC": "WC", "CYB": "CY"}
TEMPLATE_PREFIX = {"COMP_PROHIBIT": "CO", "COMP_NOTICE": "CO", "BILL_ACTION": "BI", "CLAIM_ROUTE": "CL", "CLAIM_AUTHORITY": "CL", "SIU_REFER": "SIU",
                   "DIST_ELIGIBILITY": "DI", "REIN_FAC": "RE", "EXEC_ALERT": "EX", "RATE_CHANGE_CAP": "PR", "DQ_REQUIRED": "DQ", "DQ_WARN": "DQ"}
LETTER = {"ELIGIBILITY": "E", "REFERRAL": "R", "RATING": "P", "FORMS": "F", "AUTHORITY": "A"}
EXAMPLES = {
    "CEO": ["Alert me when the combined ratio passes 98%", "Alert the CEO when retention falls below 82%"],
    "CFO": ["Alert the CFO when the expense ratio is above 33%"],
    "CUO": ["Rate changes above 20% need CEO approval", "Coverage A above 2 million needs CUO approval on homeowners"],
    "UNDERWRITER": ["Decline homes in Georgia with a roof older than 20 years", "Refer drivers under 21 with a vehicle worth more than $60,000",
                    "Decline cyber risks without MFA or without offline backups"],
    "SR_UNDERWRITER": ["Refer commercial property with TIV above 30 million to the CUO"],
    "PRICING": ["Surcharge 12% for homeowners with 3 or more prior claims in Texas", "Give a 5% credit for central station alarms on HO-3 in Florida"],
    "PRODUCT": ["Attach HO 04 90 Personal Property Replacement Cost when coverage c above 100,000 on HO-3"],
    "COMPLIANCE": ["Cancellation for non-payment notice less than 15 days in North Carolina is not allowed"],
    "BILLING": ["Send to collections when more than 45 days past due and balance above 1,000"],
    "CLAIMS_ADJUSTER": ["Route claims with an attorney to the litigation unit", "Fast track claims with incurred under 1,500 on homeowners"],
    "CLAIMS_MANAGER": ["Claim payments over 100k need approval by the Claims VP"],
    "SIU": ["Send to SIU when the claim is reported more than 45 days late"],
    "DISTRIBUTION": ["Decline when the producer is not licensed in the state"],
    "REINSURANCE": ["Refer to reinsurance when TIV above 40 million"],
    "ERM": ["Alert the Chief Risk Officer when the loss ratio is above 75% on homeowners"],
    "DATA_STEWARD": ["Reject when the roof age is missing", "Warn when the year built is before 1900"],
}


# ------------------------------------------------------------------------------------------ connection
def connect():
    server = os.environ.get("SI2_SQL_SERVER", "").strip()
    if server and st.session_state.get("repo_server") != server:
        try:
            st.session_state.repo = R.SqlRepo(server, os.environ.get("SI2_SQL_DATABASE", "SI2Canonical"))
            st.session_state.repo_server = server
        except Exception as exc:  # noqa: BLE001 - fall back to the demo library
            st.session_state.repo_error = f"Could not open SI2Canonical on {server}: {exc}"
    if "repo" not in st.session_state:
        st.session_state.repo = R.MemoryRepo()
    return st.session_state.repo


repo = connect()


@st.cache_data
def book() -> list[dict]:
    return B.book()


def names() -> dict:
    return repo.catalog.names()


def plain(rule: E.Rule) -> str:
    return E.describe(rule, names())


def role_name(code: str | None) -> str:
    return next((r["name"] for r in repo.roles if r["code"] == code), code or "")


def rule_rows(rules: list[E.Rule]) -> pd.DataFrame:
    return pd.DataFrame([{"Code": r.code, "Rule": r.name, "Owner": role_name(r.role), "Phase": r.phase, "In plain English": plain(r),
                          "Company": ", ".join(r.scope.get("COMPANY", [])), "Line": ", ".join(r.scope.get("LOB", [])),
                          "Product": ", ".join(r.scope.get("PRODUCT", [])), "State": ", ".join(r.scope.get("STATE", [])),
                          "Overrides": r.override_key or "", "From": r.effective_from, "Status": r.status} for r in rules])


# ------------------------------------------------------------------------------------------ sidebar
with st.sidebar:
    st.markdown("**Signed in as**")
    user = st.selectbox("Person", ["Saba", "Sabasi"], key="user", label_visibility="collapsed",
                        help="Two-person rule: one person proposes, the other approves.")
    page = st.radio("Go to", ["Ask SI²", "Rule library", "Try a case", "Decision tables", "Authority", "Approvals", "Coverage by role"], key="page")
    st.divider()
    if repo.kind == "sql":
        st.success(f"SI2Canonical on {repo.server}")
    else:
        st.info("Demo library in memory (synthetic). Set SI2_SQL_SERVER to work on SI2Canonical.")
    if st.session_state.get("repo_error"):
        st.warning(st.session_state.repo_error)
    st.caption(ai.status())
    pending = len(repo.pending())
    if pending:
        st.caption(f"⏳ {pending} change(s) waiting for approval")

branding.note_synthetic()


# ------------------------------------------------------------------------------------------ Ask SI²
def draft_rule(d: dict, code: str, template: dict) -> E.Rule:
    conds = [(c["element"], c["operator"], None if c.get("value1") in ("", None) else str(c["value1"]),
              None if c.get("value2") in ("", None) else str(c["value2"])) for c in d["conditions"] if c.get("element")]
    return E.Rule(code=code, name=d["name"], action=template["action"], conditions=conds, phase=template["phase"], logic=d["logic"],
                  action_value=d.get("action_value") or FIXED_VALUE.get(template["code"]), scope={k: v for k, v in d["scope"].items() if v},
                  override_key=d.get("override_key") or None, role=template["role"], template=template["code"],
                  ruleset=TEMPLATE_RULESET.get(template["code"], "UW_REFERRAL"), severity="ERROR" if template["action"] in ("DECLINE", "REJECT") else "INFO",
                  message=d.get("message") or d["name"], effective_from=d["effective_from"])


def suggest_code(template: dict, scope: dict) -> str:
    lob = (scope.get("LOB") or [""])[0]
    fixed = TEMPLATE_PREFIX.get(template["code"])
    prefix = f"{fixed}-" if fixed else f"{CODE_PREFIX.get(lob, 'GEN')}-{LETTER.get(template['phase'], 'X')}"
    return R.next_code({r.code for r in repo.rules}, prefix)


def page_ask():
    st.subheader("Tell SI² what you would like to do")
    roles = {r["code"]: r["name"] for r in repo.roles}
    c1, c2 = st.columns([1, 2])
    role = c1.selectbox("Your role", list(roles), format_func=lambda c: roles[c], index=list(roles).index("UNDERWRITER") if "UNDERWRITER" in roles else 0,
                        key="ask_role")
    examples = EXAMPLES.get(role, [])
    ex = c2.selectbox("Start from an example (or write your own below)", ["—"] + examples, key="ask_example")
    text = st.text_area("In your own words", value="" if ex == "—" else ex, key=f"ask_text_{ex}", height=80,
                        placeholder="e.g. Decline homes in Georgia with a roof older than 20 years")
    if st.button("Draft the rule", type="primary", disabled=not text.strip()):
        d = None
        if ai.available():
            d = A.with_claude(text, repo.catalog, repo.templates, role, lambda p: ai.ask(p, max_tokens=900))
        d = d or A.parse(text, repo.catalog, repo.templates, role)
        st.session_state.draft = {**d, "conditions": [dict(zip(["element", "operator", "value1", "value2"], c)) for c in d["conditions"]],
                                  "effective_from": TODAY, "role": role}
        st.session_state.pop("proposed", None)
    d = st.session_state.get("draft")
    if not d:
        st.caption("SI² picks the right template, asks only what it still needs, and shows the rule, its tests and its impact before anyone approves it.")
        with st.expander("The templates SI² uses"):
            st.dataframe(pd.DataFrame([{"Template": t["name"], "Owner": role_name(t["role"]), "Says": t["sentence"], "Example": t["example"]}
                                       for t in repo.templates]), hide_index=True, width="stretch")
        return

    st.divider()
    st.caption(f"Read by {d['source']}.")
    for n in d.get("notes", []):
        st.info(n)
    tcodes = [t["code"] for t in repo.templates]
    tcode = st.selectbox("Template", tcodes, index=tcodes.index(d["template"]) if d["template"] in tcodes else 0,
                         format_func=lambda c: f"{repo.template(c)['name']} — {role_name(repo.template(c)['role'])}", key="d_template")
    template = repo.template(tcode)

    st.markdown("**1. When should it happen?**")
    el_codes = sorted(repo.catalog.elements)
    conds = st.data_editor(pd.DataFrame(d["conditions"] or [{"element": None, "operator": ">", "value1": None, "value2": None}],
                                        columns=["element", "operator", "value1", "value2"]),
                           num_rows="dynamic", width="stretch", key="d_conds",
                           column_config={"element": st.column_config.SelectboxColumn("Data element", options=el_codes, required=True),
                                          "operator": st.column_config.SelectboxColumn("Comparison", options=OPERATORS, required=True),
                                          "value1": st.column_config.TextColumn("Value"), "value2": st.column_config.TextColumn("And (between)")})
    conds = conds.astype(object).where(pd.notna(conds), None).to_dict("records")
    for c in conds:
        opts = repo.catalog.element_options(c.get("element") or "")
        if opts:
            st.caption(f"{repo.catalog.name(c['element'])} codes: " + ", ".join(f"{o} = {n}" for o, n in opts[:20]))
    logic = st.radio("Match", ["ALL", "ANY"], index=0 if d["logic"] == "ALL" else 1, horizontal=True, key="d_logic",
                     format_func=lambda x: "all of these" if x == "ALL" else "any of these")

    st.markdown("**2. Where does it apply?** (leave empty for everywhere)")
    s1, s2, s3, s4 = st.columns(4)
    scope = {
        "COMPANY": s1.multiselect("Company", [c["code"] for c in repo.companies], default=[x for x in d["scope"].get("COMPANY", []) if x in {c["code"] for c in repo.companies}], key="d_co"),
        "LOB": s2.multiselect("Line", list(LOBS), default=[x for x in d["scope"].get("LOB", []) if x in LOBS], format_func=lambda x: f"{x} {LOBS[x]}", key="d_lob"),
        "PRODUCT": s3.multiselect("Product", [p["code"] for p in repo.products], default=[x for x in d["scope"].get("PRODUCT", []) if x in {p["code"] for p in repo.products}], key="d_prod"),
        "STATE": s4.multiselect("State", list(A.STATES), default=[x for x in d["scope"].get("STATE", []) if x in A.STATES], key="d_state"),
    }

    st.markdown("**3. The rest**")
    q = {x["name"]: x for x in template.get("questions", [])}
    a1, a2, a3 = st.columns(3)
    action_value = None
    if "action_value" in q:
        qq = q["action_value"]
        if qq.get("choices"):
            ch = qq["choices"]
            action_value = a1.selectbox(qq["question"], ch, index=ch.index(d["action_value"]) if d.get("action_value") in ch else 0, key="d_av")
        else:
            action_value = a1.text_input(qq["question"], value=d.get("action_value") or "", key="d_av_t")
    else:
        action_value = FIXED_VALUE.get(tcode)
    name = a2.text_input("Rule name", value=d["name"], key="d_name")
    eff = a3.date_input("From", value=dt.date.fromisoformat(d["effective_from"]), key="d_from").isoformat()
    message = st.text_input(q["message"]["question"] if "message" in q else "Message shown with the decision", value=d.get("message") or "", key="d_msg")

    draft = {"conditions": conds, "logic": logic, "scope": scope, "action_value": action_value, "name": name, "message": message,
             "effective_from": eff, "override_key": None}
    code = suggest_code(template, scope)
    rule = draft_rule(draft, code, template)
    rel = A.related(rule, repo.rules)
    override = next((x["rule"] for x in rel if x["kind"] == "replaces here" and x["rule"].override_key), None)
    if override:
        rule.override_key = override.override_key
    code = st.text_input("Rule code", value=code, key=f"d_code_{code}")
    rule.code = code

    st.divider()
    st.markdown("**SI² will add this rule:**")
    st.success(plain(rule))
    if override:
        st.info(f"Here it replaces **{override.code} {override.name}** ({plain(override)}). Everywhere else {override.code} still applies.")
    for x in rel:
        if x["rule"] is not override:
            st.warning(f"Related: **{x['rule'].code}** {plain(x['rule'])} — {x['kind']}.")
    problems = [f"{c[0]} is not a canonical data element" for c in rule.conditions if c[0] not in repo.catalog.elements]
    problems += [f"{repo.catalog.name(c[0])}: '{v}' is not one of its codes" for c in rule.conditions for v in str(c[2] or "").split(",")
                 if c[1] in ("=", "<>", "IN", "NOT IN") and repo.catalog.element_options(c[0]) and v.strip() not in {o for o, _ in repo.catalog.element_options(c[0])}]
    if not rule.conditions:
        problems.append("Add at least one condition.")
    if template["action"] in ("SURCHARGE_PCT", "CREDIT_PCT") and not E._num(action_value):
        problems.append("Give the percentage.")
    if code in {r.code for r in repo.rules if r.status == "ACTIVE"}:
        problems.append(f"Rule code {code} is already used.")
    for p in problems:
        st.error(p)

    tests = E.generate_tests(rule) if not problems else []
    t1, t2 = st.columns(2)
    with t1:
        st.markdown(f"**Test cases SI² wrote ({len(tests)})**")
        if tests:
            st.dataframe(pd.DataFrame([{"Case": t["name"].split(": ", 1)[-1], **{k: v for k, v in t["input"].items()}, "Fires": "yes" if t["fires"] else "no"}
                                       for t in tests]), hide_index=True, width="stretch")
    with t2:
        st.markdown("**What it changes on the synthetic book**")
        if not problems:
            imp = E.impact(repo.rules, rule, book(), TODAY)
            m1, m2, m3 = st.columns(3)
            m1.metric("Cases it applies to", imp["in_scope"])
            m2.metric("Fires on", imp["fires"])
            m3.metric("Decisions change", imp["changed"])
            if imp["premium_before"]:
                st.caption(f"Written premium in scope: {imp['premium_before']:,.0f} → {imp['premium_after']:,.0f}")
            if imp["by_outcome"]:
                st.dataframe(pd.DataFrame([{"Change": k, "Cases": v} for k, v in imp["by_outcome"].items()]), hide_index=True, width="stretch")
            if imp["examples"]:
                with st.expander("Examples"):
                    st.dataframe(pd.DataFrame(imp["examples"]), hide_index=True, width="stretch")

    if st.session_state.get("proposed"):
        st.success(st.session_state.proposed)
    elif st.button(f"Send for approval as {user}", type="primary", disabled=bool(problems)):
        payload = R.rule_payload(rule, rule.ruleset, template["rule_type"], tests, description=d.get("text"))
        rid = repo.propose("RULE", "ADD", rule.code, payload, user, f"{rule.code}: {plain(rule)}")
        other = "Sabasi" if user == "Saba" else "Saba"
        st.session_state.proposed = f"Request {rid} sent. {other} approves it under Approvals; until then nothing changes."
        st.rerun()


# ------------------------------------------------------------------------------------------ library
def page_library():
    st.subheader("Rule library")
    f1, f2, f3, f4, f5 = st.columns(5)
    roles = {r["code"]: r["name"] for r in repo.roles}
    role = f1.selectbox("Owner", ["All"] + list(roles), format_func=lambda c: roles.get(c, c), key="lib_role")
    lob = f2.selectbox("Line", ["All"] + list(LOBS), key="lib_lob")
    state = f3.selectbox("State", ["All"] + list(A.STATES), key="lib_state")
    company = f4.selectbox("Company", ["All"] + [c["code"] for c in repo.companies], key="lib_co")
    phase = f5.selectbox("Phase", ["All"] + E.PHASES, key="lib_phase")
    show_expired = st.checkbox("Show expired rules", key="lib_exp")

    def keep(r: E.Rule) -> bool:
        if r.status != "ACTIVE" and not show_expired:
            return False
        if role != "All" and r.role != role:
            return False
        if phase != "All" and r.phase != phase:
            return False
        for dim, v in (("LOB", lob), ("STATE", state), ("COMPANY", company)):
            if v != "All" and r.scope.get(dim) and v not in r.scope[dim]:
                return False
        return True

    rules = [r for r in repo.rules if keep(r)]
    st.caption(f"{len(rules)} rules. A rule with no state, line or company applies everywhere; a state rule replaces the countrywide rule with the same override key.")
    st.dataframe(rule_rows(rules), hide_index=True, width="stretch", height=420)
    if not rules:
        return
    pick = st.selectbox("Look at a rule", [r.code for r in rules], format_func=lambda c: f"{c} {next(r.name for r in rules if r.code == c)}", key="lib_pick")
    r = next(x for x in rules if x.code == pick)
    st.markdown(f"**{r.code} {r.name}** — owner {role_name(r.role)}, phase {r.phase}, from {r.effective_from}")
    st.info(plain(r))
    if r.description:
        st.caption(r.description)
    tests = E.generate_tests(r)
    if tests:
        st.dataframe(pd.DataFrame([{"Case": t["name"].split(": ", 1)[-1], **t["input"], "Fires": "yes" if t["fires"] else "no"} for t in tests]),
                     hide_index=True, width="stretch")
    if r.status == "ACTIVE" and st.button(f"Ask to retire {r.code} (as {user})", key="lib_expire"):
        rid = repo.propose("RULE", "EXPIRE", r.code, {"code": r.code, "effective_to": TODAY, "scope": "GLOBAL"}, user, f"Retire {r.code}: {r.name}")
        st.success(f"Request {rid} sent for approval.")


# ------------------------------------------------------------------------------------------ try a case
def page_try():
    st.subheader("Try a case")
    items = book()
    kinds = {"POLICY": "New business / renewal", "CLAIM": "Claim", "BILLING": "Billing account", "RESULTS": "Line results"}
    k1, k2 = st.columns([1, 2])
    kind = k1.selectbox("What", list(kinds), format_func=kinds.get, key="try_kind")
    subset = [i for i in items if i["kind"] == kind][:120]
    pick = k2.selectbox("Synthetic case", [i["id"] for i in subset],
                        format_func=lambda x: (lambda i: f"{x} · " + " · ".join(str(v) for v in i["case"].values()))(next(i for i in subset if i["id"] == x)),
                        key="try_pick")
    item = next(i for i in subset if i["id"] == pick)
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Where**")
        case = st.data_editor(pd.DataFrame([item["case"]]), hide_index=True, width="stretch", key=f"try_case_{pick}").iloc[0].to_dict()
    with c2:
        st.markdown("**Facts** (change any value)")
        facts_df = st.data_editor(pd.DataFrame([{"Element": k, "Name": repo.catalog.name(k), "Value": "" if v is None else str(v)} for k, v in item["facts"].items()]),
                                  hide_index=True, width="stretch", disabled=["Element", "Name"], key=f"try_facts_{pick}")
    facts = {r["Element"]: r["Value"] for r in facts_df.to_dict("records")}
    as_of = st.date_input("As of", value=dt.date.today(), key="try_asof").isoformat()
    d = E.evaluate(repo.rules, case, facts, as_of, repo.engine_tables())
    icon = {"ACCEPT": "✅", "REFER": "🟡", "DECLINE": "⛔", "DATA ERRORS": "⚠️"}.get(d.outcome, "")
    st.markdown(f"### {icon} {d.outcome}")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Premium factor", d.premium_factor)
    m2.metric("Surcharges", f"{d.surcharge_pct:g}%")
    m3.metric("Credits", f"{d.credit_pct:g}%")
    m4.metric("Rules fired", len(d.fired))
    for label, vals in (("Approvals needed", d.approvals), ("Routed to", d.routes), ("Forms", d.forms), ("Alerts", d.alerts), ("Data errors", d.data_errors)):
        if vals:
            st.markdown(f"**{label}:** " + "; ".join(str(v) for v in vals))
    if d.lookups:
        st.markdown("**From decision tables:** " + "; ".join(f"{t}: " + ", ".join(f"{k} {v}" for k, v in o.items()) for t, o in d.lookups.items()))
    st.markdown("**Why**")
    for line in d.explain(names()) or ["No rule fired: accepted as submitted."]:
        st.markdown(f"- {line}")


# ------------------------------------------------------------------------------------------ decision tables
def page_tables():
    st.subheader("Decision tables")
    st.caption("Values that change by state, line or product live in tables, not in rules. The most specific row wins; * means any.")
    if not repo.tables:
        st.info("No decision tables yet.")
        return
    code = st.selectbox("Table", list(repo.tables), format_func=lambda c: repo.tables[c]["name"], key="dt_pick")
    t = repo.tables[code]
    if t.get("illustrative"):
        st.warning("Illustrative values: confirm with compliance or the company before use.")
    st.caption(t.get("description") or "")
    rows = [{**r["inputs"], **r["outputs"], "Status": r["status"], "From": r.get("effective_from"), "Row": r["id"]} for r in t["rows"]]
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    with st.form("dt_add"):
        st.markdown("**Propose a row**")
        cols = st.columns(len(t["inputs"]) + len(t["outputs"]) + 1)
        ins = {k: cols[i].text_input(k, value="*", key=f"dt_in_{code}_{k}") for i, k in enumerate(t["inputs"])}
        outs = {k: cols[len(t["inputs"]) + i].number_input(k, value=0.0, key=f"dt_out_{code}_{k}") for i, k in enumerate(t["outputs"])}
        eff = cols[-1].date_input("From", value=dt.date.today(), key=f"dt_from_{code}").isoformat()
        if st.form_submit_button(f"Send for approval as {user}"):
            payload = {"table": code, "inputs": {k: v.strip().upper() or "*" for k, v in ins.items()},
                       "outputs": {k: (int(v) if float(v).is_integer() else v) for k, v in outs.items()}, "effective_from": eff, "scope": "GLOBAL"}
            rid = repo.propose("DTABLE_ROW", "ADD", code, payload, user, f"{t['name']}: {payload['inputs']} -> {payload['outputs']}")
            st.success(f"Request {rid} sent for approval.")


# ------------------------------------------------------------------------------------------ authority
def page_authority():
    st.subheader("Authority by role")
    st.caption("How much each role may bind, reserve or pay. A new limit closes the old one the day before; history is kept.")
    df = pd.DataFrame([{"Role": role_name(a["role"]), "Authority": a["authority"], "Line": a["lob"], "Limit": a["limit"], "Status": a["status"],
                        "From": a["effective_from"], "To": a["effective_to"] or "", "Note": a["note"] or ""} for a in repo.authority])
    st.dataframe(df, hide_index=True, width="stretch")
    with st.form("auth_add"):
        st.markdown("**Propose a new limit**")
        c = st.columns(5)
        role = c[0].selectbox("Role", [r["code"] for r in repo.roles], format_func=role_name, key="au_role")
        kind = c[1].selectbox("Authority", sorted({a["authority"] for a in repo.authority} | {"BIND_TIV", "PREMIUM", "RESERVE_CHANGE", "CLAIM_PAYMENT"}), key="au_kind")
        lob = c[2].selectbox("Line", ["*"] + list(LOBS), key="au_lob")
        limit = c[3].number_input("Limit", min_value=0.0, value=100000.0, step=5000.0, key="au_limit")
        eff = c[4].date_input("From", value=dt.date.today(), key="au_from").isoformat()
        if st.form_submit_button(f"Send for approval as {user}"):
            payload = {"role": role, "authority": kind, "lob": lob, "limit": limit, "effective_from": eff, "scope": "GLOBAL"}
            rid = repo.propose("AUTHORITY", "ADD", f"{role}.{kind}.{lob}", payload, user, f"{role_name(role)} {kind} {lob}: {limit:,.0f}")
            st.success(f"Request {rid} sent for approval.")


# ------------------------------------------------------------------------------------------ approvals
def page_approvals():
    st.subheader("Approvals")
    st.caption(f"You are {user}. You can approve what someone else proposed, never your own request.")
    pend = repo.pending()
    if not pend:
        st.info("Nothing is waiting for approval.")
    for r in pend:
        with st.container(border=True):
            st.markdown(f"**#{r['id']} {r['object_type']} {r['change_type']} {r['code']}** — proposed by {r['requested_by']} at {r['requested_at']}")
            st.write(r["summary"])
            p = r["payload"]
            if r["object_type"] == "RULE" and r["change_type"] == "ADD":
                rule = R.payload_rule(p)
                imp = E.impact(repo.rules, rule, book(), TODAY)
                st.caption(f"{len(p.get('tests', []))} test cases · applies to {imp['in_scope']} synthetic cases · fires on {imp['fires']} · "
                           f"changes {imp['changed']} decisions")
            with st.expander("Details"):
                st.json(p)
            own = r["requested_by"] == user
            note = st.text_input("Note", key=f"ap_note_{r['id']}")
            b1, b2 = st.columns(2)
            if b1.button("Approve", key=f"ap_yes_{r['id']}", type="primary", disabled=own):
                st.session_state.ap_msg = repo.decide(r["id"], user, True, note or None)
                st.rerun()
            if b2.button("Reject", key=f"ap_no_{r['id']}", disabled=own):
                st.session_state.ap_msg = repo.decide(r["id"], user, False, note or None)
                st.rerun()
            if own:
                st.caption("Switch to the other person in the sidebar to approve this.")
    if st.session_state.get("ap_msg"):
        status, result = st.session_state.ap_msg
        (st.success if status == "APPROVED" else st.warning)(f"{status}: {result}")
    hist = [r for r in repo.history() if r["status"] != "PENDING"]
    if hist:
        st.markdown("**Decided**")
        st.dataframe(pd.DataFrame([{"#": r["id"], "Change": f"{r['object_type']} {r['change_type']}", "Code": r["code"], "By": r["requested_by"],
                                    "Decided by": r["decided_by"], "Status": r["status"], "Result": r["result"]} for r in hist]),
                     hide_index=True, width="stretch")


# ------------------------------------------------------------------------------------------ coverage
def page_coverage():
    st.subheader("Coverage by role")
    active = [r for r in repo.rules if r.status == "ACTIVE"]
    grid = {}
    for r in active:
        for lob in r.scope.get("LOB") or ["All lines"]:
            grid.setdefault(role_name(r.role) or "(no owner)", {}).setdefault(lob, 0)
            grid[role_name(r.role) or "(no owner)"][lob] += 1
    st.markdown("**Rules by owner and line**")
    st.dataframe(pd.DataFrame(grid).T.fillna(0).astype(int), width="stretch")
    st.markdown("**Gaps** — lines with no rule in a phase (countrywide rules count for every line)")
    gaps = []
    for lob in LOBS:
        for ph in ("ELIGIBILITY", "REFERRAL", "RATING", "FORMS"):
            if not any(r.phase == ph and (not r.scope.get("LOB") or lob in r.scope["LOB"]) for r in active):
                gaps.append({"Line": f"{lob} {LOBS[lob]}", "Missing": ph.title()})
    st.dataframe(pd.DataFrame(gaps), hide_index=True, width="stretch") if gaps else st.success("Every line has rules in every phase.")
    st.markdown("**Rules that never fire on the synthetic book**")
    fired = set()
    for item in book():
        fired |= {r.code for r, _ in E.evaluate(active, item["case"], item["facts"], TODAY).fired}
    idle = [r for r in active if r.code not in fired]
    st.dataframe(rule_rows(idle)[["Code", "Rule", "Owner", "In plain English"]] if idle else pd.DataFrame(), hide_index=True, width="stretch")
    st.markdown("**Conflicts** — opposite actions on the same data where both apply")
    cf = E.conflicts(active)
    st.dataframe(pd.DataFrame(cf), hide_index=True, width="stretch") if cf else st.success("No conflicts.")


{"Ask SI²": page_ask, "Rule library": page_library, "Try a case": page_try, "Decision tables": page_tables, "Authority": page_authority,
 "Approvals": page_approvals, "Coverage by role": page_coverage}[page]()
branding.footer()
