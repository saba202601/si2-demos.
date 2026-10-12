"""Canonical Gaps screen shared by every SI² app.

render(gaps, handler) draws the inbox: metrics, filter, bulk actions, and for one
selected gap the evidence plus three pre-filled actions: Map to existing, Add new,
Not needed. The app-specific `handler` applies the decision:

    handler.map_options(gap)            -> [(key, label)]  every existing target, best first
    handler.proposal_fields(gap)        -> [(field, label, options_or_None)] editable fields of the draft
    handler.map_existing(gap, key)      -> message
    handler.add_new(gap, proposal)      -> message
    handler.not_needed(gap, reason)     -> message
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from .gaps import KINDS, Gap


def _flash(key: str, msg: str):
    st.session_state[f"{key}__flash"] = msg


def render(gaps: list[Gap], handler, key: str = "gaps", intro: str = "") -> None:
    if msg := st.session_state.pop(f"{key}__flash", None):
        st.success(msg)
    if intro:
        st.caption(intro)
    if not gaps:
        st.success("No gaps: every source and destination element, pick list and code is in the canonical model.")
        return

    kinds = [k for k in KINDS if any(g.kind == k for g in gaps)]
    cols = st.columns(len(kinds) + 1)
    cols[0].metric("Open gaps", len(gaps))
    for c, k in zip(cols[1:], kinds):
        c.metric(KINDS[k], sum(g.kind == k for g in gaps))

    f1, f2 = st.columns(2)
    show = f1.multiselect("Type", [KINDS[k] for k in kinds], key=f"{key}_type")
    sides = f2.multiselect("Side", sorted({g.side for g in gaps}), key=f"{key}_side")
    vis = [g for g in gaps if (not show or g.kind_label in show) and (not sides or g.side in sides)]

    df = pd.DataFrame([{"select": False, **g.row()} for g in vis])
    ed = st.data_editor(df, hide_index=True, width="stretch", key=f"{key}_table_{len(vis)}",
                        disabled=[c for c in df.columns if c != "select"],
                        column_config={"select": st.column_config.CheckboxColumn("✓", width="small")})
    chosen = [vis[i] for i, v in enumerate(ed["select"]) if v] if len(df) else []
    b1, b2, _ = st.columns([1.3, 1.3, 3])
    addable = [g for g in chosen if "add" in g.actions]
    skippable = [g for g in chosen if "skip" in g.actions]
    if b1.button(f"Add selected as drafted ({len(addable)})", type="primary", disabled=not addable, key=f"{key}_bulk_add"):
        msgs = [handler.add_new(g, dict(g.proposal)) for g in addable]
        _flash(key, f"{len(msgs)} added. " + " ".join(msgs[:3]) + (" ..." if len(msgs) > 3 else ""))
        st.rerun()
    if b2.button(f"Mark selected not needed ({len(skippable)})", disabled=not skippable, key=f"{key}_bulk_skip"):
        for g in skippable:
            handler.not_needed(g, "Bulk: not needed")
        _flash(key, f"{len(skippable)} marked not needed; they will not come back as gaps.")
        st.rerun()

    st.divider()
    gid = st.selectbox("Resolve one gap", [g.gap_id for g in vis], key=f"{key}_pick",
                       format_func=lambda i: next(f"{g.gap_id} · {g.kind_label} · {g.name} ({g.ref})" for g in vis if g.gap_id == i))
    g = next(x for x in vis if x.gap_id == gid)

    ev = st.columns([2, 3])
    with ev[0]:
        st.markdown(f"**{g.kind_label}**  \n{g.side} · {g.system}  \nFound in `{g.ref}`  \nRisk: **{g.risk}** · seen {g.occurrences}×")
        if g.meaning:
            st.markdown(f"Meaning: *{g.meaning}*")
    with ev[1]:
        if g.values:
            st.markdown("Observed values")
            st.dataframe(pd.DataFrame([{"value": k, "meaning / count": v} for k, v in g.values.items()]),
                         hide_index=True, width="stretch", height=min(35 * (len(g.values) + 1) + 3, 260))
        elif g.samples:
            st.markdown("Sample values: " + ", ".join(f"`{s}`" for s in g.samples[:6]))

    a, b, c = st.columns(3)
    with a:
        st.markdown("##### 1 · Map to existing")
        if "map" in g.actions:
            opts = handler.map_options(g)
            if opts:
                labels = {k: l for k, l in opts}
                tgt = st.selectbox("Existing item", list(labels), format_func=lambda k: labels[k], key=f"{key}_map_{gid}")
                st.caption("Use when it is really a synonym of something already in the model.")
                if st.button("Map to existing", key=f"{key}_mapbtn_{gid}"):
                    _flash(key, handler.map_existing(g, tgt))
                    st.rerun()
            else:
                st.caption("Nothing comparable exists yet.")
        else:
            st.caption("Not applicable for this gap.")
    with b:
        st.markdown("##### 2 · Add new")
        if "add" in g.actions:
            prop = dict(g.proposal)
            with st.form(f"{key}_add_{gid}"):
                for fld, label, options in handler.proposal_fields(g):
                    cur = prop.get(fld, "")
                    if options:
                        prop[fld] = st.selectbox(label, options, index=options.index(cur) if cur in options else 0)
                    elif fld in ("description", "business_description"):
                        prop[fld] = st.text_area(label, str(cur), height=90)
                    else:
                        prop[fld] = st.text_input(label, str(cur))
                if st.form_submit_button("Add new", type="primary"):
                    _flash(key, handler.add_new(g, prop))
                    st.rerun()
        else:
            st.caption("Not applicable for this gap.")
    with c:
        st.markdown("##### 3 · Not needed")
        if "skip" in g.actions:
            reason = st.text_input("Reason", "Not used downstream", key=f"{key}_why_{gid}")
            st.caption("It is recorded and will not come back as a gap.")
            if st.button("Mark not needed", key=f"{key}_skip_{gid}"):
                _flash(key, handler.not_needed(g, reason))
                st.rerun()
        else:
            st.caption("Not applicable: this item must be resolved.")
