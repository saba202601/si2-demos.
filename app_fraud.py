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
