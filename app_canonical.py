"""SI² demo: P&C Canonical Data Model.

Shows how a flat legacy Personal Auto extract maps into one canonical model that
every downstream use (bureau reporting, rating, rules, claims) can share.
"""
import json

import pandas as pd
import streamlit as st

from si2_common import approvals_ui, branding, data, gate, identity, store
from si2_common import registry as R

branding.page("Canonical Data Model",
              "One shared model for policy, risk, coverage, premium and claim data, mapped from any source system.")
gate.require_access()


@st.cache_data
def sample():
    pols = data.legacy_policy_extract()
    clms = data.legacy_claims_extract(pols)
    return pols, clms


pols, clms = sample()

tab_co, tab_model, tab_map, tab_doc = st.tabs(["🏢 Company model (all apps)", "The model", "Map a source file",
                                               "Canonical policy document"])


def company_model():
    where = R.harvest()
    return where, R.terms(where)


def actor() -> str:
    return st.session_state.get("sme_name") or "SME"


def decide_term(req: dict) -> str:
    if req["status"] != "Approved":
        return f"Change to {req['ref']} rejected by {req['checker']}; the published version is unchanged."
    e = R.publish(req["ref"], req["payload"]["change"], req["maker"], req["checker"], req.get("note", ""))
    return (f"{req['ref']} v{e['version']} published by {req['checker']}: every SI² app now uses the new definition and "
            "synonyms (initial-load descriptions, migration matching, company model).")


with st.sidebar:
    identity.name_input("Your name", "sme_name", "Name for proposals and approvals")
    st.caption(f"💾 Company model saved to {store.describe()}")


with tab_co:
    where, terms = company_model()
    st.caption("Every SI² app has its own model today: the ISO element catalog, the NCCI canonical tables, the cloud "
               "canonical of the migration, the rule vocabulary and the rating variables. SI² harvests all of them into "
               "one company model of business terms, with every name each term goes by and where it is used: one "
               "definition to govern, and impact analysis before anything changes.")
    m = st.columns(4)
    m[0].metric("Business terms", len(terms))
    m[1].metric("Shared by 2+ apps", int((terms.apps >= 2).sum()))
    m[2].metric("Used by every app", int((terms.apps == len(R.APPS)).sum()))
    m[3].metric("Names for the shared terms", int(terms[terms.apps >= 2]["names in use"].sum()))
    f1, f2 = st.columns([1, 3])
    shared = f1.toggle("Shared terms only", True, key="co_shared")
    apps = f2.multiselect("Used by", R.APPS, key="co_apps")
    view = terms[(terms.apps >= 2) | (not shared)]
    for a in apps:
        view = view[view[a] == "✓"]
    st.dataframe(view[["business name", "standard name", "status", "apps", "names in use", *R.APPS, "definition"]],
                 hide_index=True, width="stretch", height=420,
                 column_config={"definition": st.column_config.TextColumn(width="large")})
    st.markdown("**Where used**")
    pick = st.selectbox("Business term", view.term.tolist(), key="co_term",
                        format_func=lambda t: f"{t.replace('_', ' ').title()}  ·  {int(terms.set_index('term').at[t, 'apps'])} app(s)")
    if pick:
        w = where[where.term == pick][["app", "entity", "element", "type", "description"]]
        st.dataframe(w, hide_index=True, width="stretch")
        st.caption(f"Changing **{pick.replace('_', ' ').title()}** touches {len(w)} element(s) in {w.app.nunique()} app(s). "
                   f"Standard name proposed by SI²: `{pick.lower()}`.")
    st.divider()
    st.markdown("**Govern a term: propose → impact → second-person approval → published to every app**")
    if pick:
        pub = R.published().get(pick, {})
        row = terms.set_index("term").loc[pick]
        with st.form(f"gov_{pick}"):
            g1, g2 = st.columns([1, 2])
            std = g1.text_input("Standard name", pub.get("standard_name") or row["standard name"])
            owner = g1.text_input("Data owner", pub.get("owner", ""), placeholder="e.g. Policy admin / Underwriting ops")
            dfn = g2.text_area("Definition", pub.get("definition") or row["definition"], height=80)
            names = sorted(set(where[where.term == pick].element.str.split(".").str[-1]))
            syn = g2.text_input("Synonyms (comma separated)", ", ".join(pub.get("synonyms", []) or names))
            impact = where[where.term == pick]
            st.caption(f"Impact: {len(impact)} element(s) in {impact.app.nunique()} app(s): "
                       + ", ".join(f"{a} ({n})" for a, n in impact.app.value_counts().items()))
            if st.form_submit_button("Submit the change for approval", type="primary"):
                change = {"standard_name": std.strip(), "definition": dfn.strip(), "owner": owner.strip(),
                          "synonyms": [x.strip() for x in syn.split(",") if x.strip()]}
                try:
                    store.request(R.GOV_APP, "Term change", pick,
                                  f"{pick}: {std} · {dfn[:80]} · {len(change['synonyms'])} synonyms · impact {len(impact)} "
                                  f"elements in {impact.app.nunique()} apps", {"change": change}, actor())
                    st.success("Submitted. A second person approves it below.")
                except ValueError as exc:
                    st.error(str(exc))
    approvals_ui.render(R.GOV_APP, actor(), decide_term, note_label="Note", key="gov_appr")
    hist = R.history()
    with st.expander(f"Published versions ({len(hist)})"):
        if hist:
            st.dataframe(pd.DataFrame(hist).iloc[::-1], hide_index=True, width="stretch")
        else:
            st.caption("Nothing published yet: every term is a harvested draft.")
    st.download_button("Download the company model with where-used (CSV)",
                       where.merge(terms[["term", "business name", "standard name", "definition"]], on="term")
                       .to_csv(index=False), "SI2_company_canonical_model.csv", "text/csv", key="co_dl")

with tab_model:
    left, right = st.columns([3, 2], gap="large")
    with left:
        st.subheader("Entities and relationships")
        dot = ["digraph G {", 'rankdir=LR; bgcolor="transparent";',
               'node [shape=box, style="rounded,filled", fillcolor="#FFFFFF", color="#0B1B2B", fontname="Helvetica", fontsize=11];',
               'edge [color="#2B4CF2", fontname="Helvetica", fontsize=9, fontcolor="#4A5868"];']
        for ent in data.CANONICAL_ENTITIES:
            dot.append(f'"{ent}";')
        for a, b, label in data.RELATIONSHIPS:
            dot.append(f'"{a}" -> "{b}" [label="{label}"];')
        dot.append("}")
        st.graphviz_chart("\n".join(dot), width="stretch")
    with right:
        st.subheader("Attributes")
        ent = st.selectbox("Entity", list(data.CANONICAL_ENTITIES))
        st.dataframe(pd.DataFrame({"attribute": data.CANONICAL_ENTITIES[ent]}), hide_index=True,
                     width="stretch")
        st.markdown(
            "**Why a canonical model?** Each source system names fields differently. Mapping them once into "
            "a shared model means bureau reporting, rating, rules and analytics all read the same, validated data."
        )

with tab_map:
    st.subheader("1 · Source extract")
    up = st.file_uploader("Upload your own CSV with the same columns, or use the sample below", type="csv")
    src = pols
    if up is not None:
        try:
            src = pd.read_csv(up, dtype={"ZIP5": str})
            missing = [c for c in pols.columns if c not in src.columns]
            if missing:
                st.error(f"Your file is missing these columns: {', '.join(missing)}. Showing the sample instead.")
                src = pols
        except Exception as exc:  # noqa: BLE001
            st.error(f"Couldn't read that CSV ({exc}). Showing the sample instead.")
            src = pols
    st.caption(f"{src.POL_NO.nunique()} policies · {len(src)} coverage rows")
    st.dataframe(src.head(25), hide_index=True, width="stretch")
    st.download_button("Download sample extract (CSV)", pols.to_csv(index=False), "si2_sample_policy_extract.csv",
                       "text/csv")

    st.subheader("2 · Field mapping")
    st.dataframe(pd.DataFrame(data.MAPPING, columns=["Source field", "Canonical attribute", "Transform"]),
                 hide_index=True, width="stretch")

    st.subheader("3 · Canonical tables")
    tables = data.build_canonical(src, clms if up is None else None)
    counts = {k: len(v) for k, v in tables.items()}
    cols = st.columns(4)
    for i, (k, n) in enumerate(list(counts.items())[:8]):
        cols[i % 4].metric(k, f"{n:,}")
    pick = st.selectbox("Show table", list(tables), index=list(tables).index("RiskItem"))
    st.dataframe(tables[pick], hide_index=True, width="stretch")

    st.subheader("4 · Mapping checks")
    issues = []
    bad_vin = tables["RiskItem"][tables["RiskItem"].vin.str.len() != 17]
    if len(bad_vin):
        issues.append(f"{len(bad_vin)} vehicles have a VIN that is not 17 characters.")
    bad_state = tables["Policy"][~tables["Policy"].state.isin(list(data.STATES))]
    if len(bad_state):
        issues.append(f"{len(bad_state)} policies have a state outside this demo's list.")
    neg = tables["PremiumTransaction"][tables["PremiumTransaction"].written_premium < 0]
    if len(neg):
        issues.append(f"{len(neg)} premium transactions are negative; confirm they are returns.")
    if issues:
        for msg in issues:
            st.warning(msg)
    else:
        st.success("All rows mapped. VINs, states and premium signs passed the basic checks.")

with tab_doc:
    tables = data.build_canonical(pols, clms)
    pol_no = st.selectbox("Policy", tables["Policy"].policy_number.tolist())
    doc = data.policy_document(tables, pol_no)
    st.caption("The same policy as one nested canonical document, ready for an API or a downstream system.")
    st.json(doc, expanded=2)
    st.download_button("Download JSON", json.dumps(doc, indent=2, default=str), f"{pol_no}.json",
                       "application/json")

branding.note_synthetic()
branding.footer()
