"""Two-person approval inbox, shared by every SI² app.

    approvals_ui.render(APP, actor, on_decided, note_label="Filing reference")

`on_decided(request)` applies the decision (request["status"] is "Approved" or "Rejected", request["payload"]
is what the maker submitted). The checker must be a different person from the maker.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from . import store


def pending_count(app: str, kinds=None) -> int:
    try:
        return len([r for r in store.approvals(app, "Pending") if not kinds or r["kind"] in kinds])
    except Exception:
        return 0


def render(app: str, actor: str, on_decided, note_label: str = "Note", note_default: str = "",
           detail=None, key: str = "appr", kinds=None) -> None:
    if msg := st.session_state.pop(f"{key}__flash", None):
        (st.error if msg[0] == "error" else st.success)(msg[1])
    st.caption("Two-person rule: the person who proposed a change cannot approve it. Names come from the sidebar; "
               "in production they come from the company's single sign-on.")
    try:
        pend = [r for r in store.approvals(app, "Pending") if not kinds or r["kind"] in kinds]
    except Exception as exc:
        st.warning(f"Approvals are unavailable: {exc}")
        return
    if not pend:
        st.success("Nothing waiting for approval.")
    for r in pend:
        with st.container(border=True):
            st.markdown(f"**#{r['id']} · {r['kind']}** · {r['summary']}  \nProposed by **{r['maker']}** at {r['made_at']}")
            if detail:
                detail(r)
            c1, c2, c3 = st.columns([3, 1, 1])
            note = c1.text_input(note_label, note_default, key=f"{key}_note_{r['id']}")
            for col, label, ok in ((c2, "Approve", True), (c3, "Reject", False)):
                if col.button(label, key=f"{key}_{label}_{r['id']}", type="primary" if ok else "secondary"):
                    try:
                        done = store.decide(app, r["id"], actor, ok, note)
                        msg = on_decided(done) or f"#{r['id']} {done['status'].lower()} by {actor}."
                        st.session_state[f"{key}__flash"] = ("ok", msg)
                    except ValueError as exc:
                        st.session_state[f"{key}__flash"] = ("error", str(exc))
                    st.rerun()
    hist = [h for h in store.approvals(app) if h["status"] != "Pending" and (not kinds or h["kind"] in kinds)]
    with st.expander(f"Decided ({len(hist)})"):
        if hist:
            st.dataframe(pd.DataFrame(hist)[["id", "kind", "summary", "maker", "made_at", "status", "checker",
                                             "checked_at", "note"]], hide_index=True, width="stretch")
        else:
            st.caption("No decisions yet.")
