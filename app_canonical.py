"""SI² demo: P&C Canonical Data Model.

Shows how a flat legacy Personal Auto extract maps into one canonical model that
every downstream use (bureau reporting, rating, rules, claims) can share.
"""
import json

import pandas as pd
import streamlit as st

from si2_common import branding, data, gate

branding.page("Canonical Data Model",
              "One shared model for policy, risk, coverage, premium and claim data, mapped from any source system.")
gate.require_access()


@st.cache_data
def sample():
    pols = data.legacy_policy_extract()
    clms = data.legacy_claims_extract(pols)
    return pols, clms


pols, clms = sample()

tab_model, tab_map, tab_doc = st.tabs(["The model", "Map a source file", "Canonical policy document"])

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
