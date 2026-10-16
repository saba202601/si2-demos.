"""SI² Canonical Master: browse the master vocabulary in SI2Canonical.

Every data element with its pick list, options, aliases and where it is used (insurance forms, databases),
the forms with each field and its element, and the Party-first entity model.

Runs on SI2Canonical (set SI2_SQL_SERVER, Windows authentication) or, without it, on the commercial
application model in memory. Read only: changes go through the two-person approval in the Rule Studio and collector.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent
ENGINE = next((p for p in (ROOT / "sql" / "si2_canonical", ROOT.parent / "si2_canonical_db", ROOT)
               if (p / "commercial_app_model.py").exists()), ROOT)
sys.path.insert(0, str(ENGINE))
sys.path.insert(0, str(ROOT))

from si2_common import branding, gate  # noqa: E402

branding.page("Canonical Master", "One vocabulary for P&C: every element, pick list, option and alias, and every form field it comes from.")
gate.require_access()

from si2_common.master_source import ModelSource, SqlSource  # noqa: E402


def source():
    server = os.environ.get("SI2_SQL_SERVER", "").strip()
    ss = st.session_state
    if server and ss.get("cm_server") != server:
        try:
            ss.cm_src = SqlSource(server, os.environ.get("SI2_SQL_DATABASE", "SI2Canonical"))
            ss.cm_server = server
        except Exception as exc:  # noqa: BLE001 - the model in memory still shows the pages
            ss.cm_error = f"Could not open SI2Canonical on {server}: {exc}"
    if "cm_src" not in ss:
        ss.cm_src = ModelSource()
    return ss.cm_src


src = source()

with st.sidebar:
    page = st.radio("Go to", ["Overview", "Find an element", "Forms", "Pick lists", "Party model"], key="cm_page")
    st.divider()
    if src.kind == "sql":
        st.success(f"SI2Canonical on {src.server}")
    else:
        st.info("Commercial application model in memory. Set SI2_SQL_SERVER to browse SI2Canonical.")
    if st.session_state.get("cm_error"):
        st.warning(st.session_state.cm_error)


def n(v) -> str:
    try:
        return f"{int(v):,}"
    except (TypeError, ValueError):
        return "—"


def show_element(code: str) -> None:
    e = src.element(code)
    if not e:
        st.info("Not found.")
        return
    st.markdown(f"#### {e['Name']}  \n`{e['ElementCode']}` · {e.get('SubjectAreaCode') or '—'} · {e.get('DataType')}"
                + (" · 🔒 personal data" if e.get("IsPII") else ""))
    if e.get("BusinessDescription"):
        st.write(e["BusinessDescription"])
    c1, c2 = st.columns(2)
    with c1:
        st.markdown(f"**Pick list:** {e.get('PickListName') or 'none'}" + (f" (`{e['PickListCode']}`)" if e.get("PickListCode") else ""))
        if len(e["options"]):
            st.dataframe(e["options"], hide_index=True, use_container_width=True, height=min(35 * len(e["options"]) + 38, 320))
    with c2:
        st.markdown(f"**Aliases:** {len(e['aliases'])}")
        if len(e["aliases"]):
            st.dataframe(e["aliases"], hide_index=True, use_container_width=True, height=min(35 * len(e["aliases"]) + 38, 320))
    st.markdown(f"**Where it is used:** {len(e['usage'])}")
    if len(e["usage"]):
        st.dataframe(e["usage"], hide_index=True, use_container_width=True, height=min(35 * len(e["usage"]) + 38, 360))


# ------------------------------------------------------------------------------------------ pages
if page == "Overview":
    s = src.summary()
    cols = st.columns(5)
    for col, (label, key) in zip(cols, [("Data elements", "DataElements"), ("Pick lists", "PickLists"), ("Options", "PickListOptions"),
                                        ("Aliases", "Synonyms"), ("Where used", "WhereUsed")]):
        col.metric(label, n(s.get(key)))
    forms = src.forms()
    if len(forms):
        st.markdown("##### Insurance forms in the master")
        st.dataframe(forms, hide_index=True, use_container_width=True)
    st.markdown("##### How the master grows")
    st.markdown("1. **Collect** — databases, insurance forms and models are read; every field, list and value is matched to the master.\n"
                "2. **Propose** — only what is new becomes a change request; known items gain aliases instead of duplicates.\n"
                "3. **Approve** — a second person approves (two-person rule); history is kept, nothing is ever deleted.\n"
                "4. **Use** — rules, rating, claims and bureau reporting all speak the same element codes.")

elif page == "Find an element":
    c1, c2 = st.columns([3, 1])
    text = c1.text_input("Search by name, code or alias", key="cm_q", placeholder="e.g. FEIN, roof, model year, payroll")
    subject = c2.selectbox("Subject area", [""] + src.subjects(), key="cm_subject", format_func=lambda v: v or "All")
    df = src.elements(text or "", subject or "")
    st.caption(f"{len(df)} element(s)" + (" (first 300)" if len(df) >= 300 else ""))
    if len(df):
        st.dataframe(df, hide_index=True, use_container_width=True, height=320)
        pick = st.selectbox("Open an element", df["Code"].tolist(), key="cm_pick",
                            format_func=lambda c: f"{df.loc[df.Code == c, 'Name'].iloc[0]}  ({c})")
        if pick:
            show_element(pick)

elif page == "Forms":
    forms = src.forms()
    if not len(forms):
        st.info("No forms in this master yet. Put fillable PDF forms in acord_forms and run run_forms.bat.")
    else:
        form = st.selectbox("Form", forms["Form"].tolist(), key="cm_form")
        fields = src.form_fields(form)
        row = forms[forms.Form == form].iloc[0]
        c1, c2, c3 = st.columns(3)
        c1.metric("Fields linked", n(row["Fields"]))
        c2.metric("Elements", n(row["Elements"]))
        c3.metric("With a pick list", n(fields["PickList"].notna().sum()) if len(fields) else "0")
        flt = st.text_input("Filter fields", key="cm_ffilter", placeholder="e.g. vehicle, limit, address")
        if flt:
            m = fields.apply(lambda r: flt.lower() in " ".join(str(v) for v in r.values).lower(), axis=1)
            fields = fields[m]
        st.dataframe(fields, hide_index=True, use_container_width=True, height=420)
        if len(fields):
            pick = st.selectbox("Open an element", sorted(fields["Element"].unique()), key="cm_fpick")
            if pick:
                show_element(pick)

elif page == "Pick lists":
    text = st.text_input("Search pick lists", key="cm_plq", placeholder="e.g. construction, state, coverage")
    df = src.picklists(text or "")
    st.caption(f"{len(df)} pick list(s)")
    if len(df):
        st.dataframe(df, hide_index=True, use_container_width=True, height=320)
        pick = st.selectbox("Open a pick list", df["Code"].tolist(), key="cm_plpick",
                            format_func=lambda c: f"{df.loc[df.Code == c, 'Name'].iloc[0]}  ({c})")
        if pick:
            st.dataframe(src.options(pick), hide_index=True, use_container_width=True)

else:  # Party model
    df = src.entity_model()
    if not len(df):
        st.info("The entity model is not installed yet (09_commercial_app.sql).")
    else:
        ents = df.drop_duplicates("Entity")[["Entity", "EntityName", "ParentEntity"]]
        missing = int((df["InMaster"] == "NOT YET").sum())
        c1, c2, c3 = st.columns(3)
        c1.metric("Entities", n(len(ents)))
        c2.metric("Entity elements", n(len(df)))
        c3.metric("Not yet in the master", n(missing))
        ent = st.selectbox("Entity", ents["Entity"].tolist(), key="cm_entity",
                           format_func=lambda c: f"{ents.loc[ents.Entity == c, 'EntityName'].iloc[0]}  ({c})")
        parent = ents.loc[ents.Entity == ent, "ParentEntity"].iloc[0]
        kids = ents.loc[ents.ParentEntity == ent, "EntityName"].tolist()
        st.caption((f"Part of {parent}. " if parent else "") + (f"Holds: {', '.join(kids)}." if kids else ""))
        st.dataframe(df[df.Entity == ent][["Seq", "ElementCode", "ElementName", "DataType", "PickList", "SubjectArea", "InMaster"]],
                     hide_index=True, use_container_width=True)

branding.footer()
