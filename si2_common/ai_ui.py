"""Small Streamlit pieces for SI² AI assistance (all suggestions; nothing changes data without the SME)."""
from __future__ import annotations

import streamlit as st

from . import ai


def badge():
    st.caption(ai.status())


def explain_button(label: str, key: str, fn, *args):
    """Run fn(*args) -> (text, source) on click and keep the answer on screen."""
    if st.button(label, key=key):
        with st.spinner("SI² is reading ..."):
            st.session_state[f"{key}__ans"] = fn(*args)
    if ans := st.session_state.get(f"{key}__ans"):
        with st.container(border=True):
            st.markdown(ans[0])
            st.caption(f"Answered by {ans[1]} · a suggestion for the SME, not a decision.")


def ask_box(key: str, facts_fn, suggestions: list[str]):
    """'Ask SI²' about the data on screen. facts_fn() returns masked facts only."""
    badge()
    cols = st.columns(len(suggestions)) if suggestions else []
    q = None
    for c, s_ in zip(cols, suggestions):
        if c.button(s_, key=f"{key}_s_{s_[:20]}"):
            q = s_
    typed = st.text_input("Ask SI² about this data", key=f"{key}_q", placeholder="e.g. Which keys still need my decision?")
    if st.button("Ask", key=f"{key}_go") and typed.strip():
        q = typed.strip()
    if q:
        with st.spinner("SI² is reading ..."):
            st.session_state[f"{key}__ans"] = (q, *ai.answer(q, facts_fn()))
    if ans := st.session_state.get(f"{key}__ans"):
        with st.container(border=True):
            st.markdown(f"**{ans[0]}**\n\n{ans[1]}")
            st.caption(f"Answered by {ans[2]} from masked facts on this screen (no personal data is sent).")
