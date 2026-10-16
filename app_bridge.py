"""SI² Data Bridge: any source to any destination through SI2Canonical.

A legacy policy extract goes to a modern policy system and to an ISO-style statistical record, with every value
translated through the canonical element and option, every record checked, and every value's lineage kept.
Runs on the approved mappings in SI2Canonical (SI2_SQL_SERVER, after run_bridge.bat) or on the same mappings in memory.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent
ENGINE = next((p for p in (ROOT / "sql" / "si2_canonical", ROOT.parent / "si2_canonical_db", ROOT) if (p / "bridge.py").exists()), ROOT)
sys.path.insert(0, str(ENGINE))
sys.path.insert(0, str(ROOT))

import bridge as B  # noqa: E402
import bridge_systems as S  # noqa: E402
from si2_common import branding, gate  # noqa: E402

branding.page("Data Bridge", "Any source to any destination through SI2Canonical: map each system once, to the canonical model, and it reaches every other system.")
gate.require_access()
ss = st.session_state


def dictionary():
    server = os.environ.get("SI2_SQL_SERVER", "").strip()
    if server and ss.get("br_server") != server:
        ss.br_server = server
        try:
            from si2_common.master_source import SqlSource
            d = B.SqlDictionary(SqlSource(server, os.environ.get("SI2_SQL_DATABASE", "SI2Canonical")).cn)
            if d.fields("LEGACY_PAS"):
                ss.br_dict = d
                ss.pop("br_note", None)
            else:
                ss.br_note = "SI2Canonical does not have the demo systems' mappings yet: run run_bridge.bat once. Showing them in memory meanwhile."
        except Exception as exc:  # noqa: BLE001
            ss.br_note = f"Could not read SI2Canonical on {server}: {exc}. Showing the mappings in memory."
    if "br_dict" not in ss:
        ss.br_dict = B.MemoryDictionary()
    return ss.br_dict


d = dictionary()

with st.sidebar:
    page = st.radio("Go to", ["Run the bridge", "One record end to end", "Mappings", "Value crosswalk", "Issues"], key="bridge_page")
    n = st.select_slider("Legacy records", [50, 100, 200, 500, 1000], value=200, key="br_rows")
    st.divider()
    if d.kind == "sql":
        st.success(f"Mappings from SI2Canonical on {ss.br_server}")
    else:
        st.info("Mappings in memory (synthetic, as if approved).")
    if ss.get("br_note"):
        st.warning(ss.br_note)

if ss.get("br_key") != (n, d.kind):
    ss.br_rows_data = S.legacy_extract(n)
    ss.br_res = B.run(ss.br_rows_data, S.LEGACY_PAS, S.DESTINATIONS, d)
    ss.br_key = (n, d.kind)
rows, res = ss.br_rows_data, ss.br_res
stats = res.stats()

if page == "Run the bridge":
    c = st.columns([3, 1, 3, 1, 3])
    c[0].markdown(f"**Source**  \n{S.LEGACY_PAS.name}  \n`{S.LEGACY_PAS.code}`")
    c[0].metric("Records read", f"{stats['records']:,}")
    c[1].markdown("<div style='font-size:2rem;text-align:center;padding-top:1.2rem'>→</div>", unsafe_allow_html=True)
    c[2].markdown("**SI2Canonical**  \none element, one option, one meaning")
    c[2].metric("Passed the checks", f"{stats['passed']:,}", delta=f"{stats['held']} held" if stats["held"] else None, delta_color="inverse")
    c[3].markdown("<div style='font-size:2rem;text-align:center;padding-top:1.2rem'>→</div>", unsafe_allow_html=True)
    with c[4]:
        for x in S.DESTINATIONS:
            st.markdown(f"**{x.name}** `{x.code}` — {stats['to ' + x.code]:,} records")
    st.caption(f"{stats['lineage rows']:,} values carry their lineage. Held records stay out of every destination until fixed: see Issues.")
    tabs = st.tabs(["Legacy input", "Canonical records"] + [x.name for x in S.DESTINATIONS])
    with tabs[0]:
        st.caption(S.LEGACY_PAS.note)
        st.dataframe(pd.DataFrame(rows[:50]), hide_index=True, use_container_width=True)
        st.download_button("Download legacy input", B.to_csv(rows), "1_legacy_input.csv", "text/csv", key="dl_src")
    with tabs[1]:
        st.caption("Canonical element codes as columns; code values are canonical options.")
        st.dataframe(pd.DataFrame(B.canonical_rows(res)[:50]), hide_index=True, use_container_width=True)
        st.download_button("Download canonical records", B.to_csv(B.canonical_rows(res)), "2_canonical_records.csv", "text/csv", key="dl_can")
    for i, x in enumerate(S.DESTINATIONS, 2):
        with tabs[i]:
            st.caption(x.note)
            if x.kind == "FIXED":
                ruler = "".join(f.name[: f.width].ljust(f.width, "·")[: f.width] for f in x.fields)
                st.code(ruler + "\n" + "\n".join(res.outputs[x.code][:30]), language=None)
                st.dataframe(pd.DataFrame([{"Field": f.name, "Width": f.width, "Element": f.element} for f in x.fields]),
                             hide_index=True, use_container_width=True)
            else:
                st.dataframe(pd.DataFrame(res.outputs[x.code][:50]), hide_index=True, use_container_width=True)
            st.download_button(f"Download {x.name}", B.output_text(res, x.code), f"{x.code.lower()}.{'txt' if x.kind == 'FIXED' else 'csv'}",
                               key=f"dl_{x.code}")

elif page == "One record end to end":
    keys = [r["Record"] for r in res.canonical if r["Record"] not in res.held]
    key = st.selectbox("Policy", keys, key="br_rec")
    lin = [x for x in res.lineage if x["Record"] == key]
    by_el = {}
    for x in lin:
        r = by_el.setdefault(x["Element"], {"Canonical element": x["Element"], "Legacy": f"{x['Source field']} = {x['Source value']}",
                                            "Legacy to canonical": x["Source to canonical"], "Canonical value": x["Canonical value"],
                                            **{dd.code: "—" for dd in S.DESTINATIONS}})
        r[x["Destination"]] = f"{x['Destination field']} = {x['Destination value']}"
    table = list(by_el.values())
    st.dataframe(pd.DataFrame(table), hide_index=True, use_container_width=True, height=36 * len(table) + 40)
    with st.expander("How each destination value was written"):
        st.dataframe(pd.DataFrame([{"Element": x["Element"], "Destination": x["Destination"], "Field": x["Destination field"],
                                    "Value": x["Destination value"], "Canonical to destination": x["Canonical to destination"]} for x in lin]),
                     hide_index=True, use_container_width=True)
    st.caption("Every destination value is traced to its legacy field and value, the canonical element and option, and the mapping used.")

elif page == "Mappings":
    st.markdown("Each system field is an alias of a canonical element, tagged with the system and approved by a second person. "
                "A new system is mapped once, to these elements, and reaches every other system.")
    st.dataframe(pd.DataFrame(B.mapping_matrix(d)), hide_index=True, use_container_width=True)
    if res.unmapped_fields:
        st.warning(f"Not mapped yet in {S.LEGACY_PAS.code}: {', '.join(res.unmapped_fields)} — carried nowhere until an SME says what it is.")

elif page == "Value crosswalk":
    pls = [p for p in ("CONSTRUCTION", "POLICY_FORM", "LOB", "DEDUCTIBLE", "TRANSACTION_TYPE", "PROTECTION_CLASS", "STATE") if d.options.get(p)]
    pl = st.selectbox("Pick list", pls, key="br_pl")
    st.dataframe(pd.DataFrame(B.value_crosswalk(d, pl)), hide_index=True, use_container_width=True)
    st.caption("Legacy and modern-system values are approved aliases of the canonical option; ISO codes come from the bureau codes in SI2Canonical. "
               "— means that system has no value for the option yet.")

else:  # Issues
    held = [x for x in res.issues if x["Severity"] == "ERROR"]
    c1, c2 = st.columns(2)
    c1.metric("Records held", len(res.held))
    c2.metric("Fields not mapped yet", len(res.unmapped_fields))
    st.dataframe(pd.DataFrame(res.issues), hide_index=True, use_container_width=True)
    if held:
        st.caption("A held record goes to no destination until it is fixed at the source or an SME adds the missing mapping "
                   "(for example the legacy value as an alias of a canonical option, approved by a second person).")
    st.download_button("Download issues", B.to_csv(res.issues), "issues.csv", "text/csv", key="dl_issues")

branding.footer()
