"""Streamlit side of the store: restore an app's decisions at start, save them after every change.

    persist.restore(APP, KEYS, fresh)   # in init(): returns True when a saved state was restored
    persist.checkpoint(APP, KEYS)       # at the end of the script: saves only the keys that changed
    persist.sidebar(APP, on_reset)      # "saved" caption + reset button
"""
from __future__ import annotations

import streamlit as st

from . import store


def restore(app: str, keys: list[str]) -> bool:
    ss = st.session_state
    try:
        saved = store.load(app)
    except Exception as exc:                                # store unreachable: run in memory, say so
        ss[f"_{app}_store_error"] = str(exc)
        return False
    if not saved:
        return False
    try:
        values = {k: store.loads(saved[k]) for k in keys if k in saved}
    except Exception as exc:                                # older / incompatible save: start fresh
        ss[f"_{app}_store_error"] = f"saved state could not be read ({exc}); starting fresh"
        return False
    for k, v in values.items():
        ss[k] = v
        ss[f"_{app}_h_{k}"] = store.digest(saved[k])
    return True


def checkpoint(app: str, keys: list[str], actor: str = "") -> int:
    ss = st.session_state
    if ss.get(f"_{app}_store_error"):
        return 0
    n = 0
    for k in keys:
        if k not in ss:
            continue
        text = store.dumps(ss[k])
        h = store.digest(text)
        if ss.get(f"_{app}_h_{k}") != h:
            try:
                store.save(app, k, text, actor)
            except Exception as exc:
                ss[f"_{app}_store_error"] = str(exc)
                return n
            ss[f"_{app}_h_{k}"] = h
            n += 1
    return n


def sidebar(app: str, on_reset=None):
    ss = st.session_state
    err = ss.get(f"_{app}_store_error")
    if err:
        st.caption(f"⚠️ Decisions are kept for this session only: {err[:120]}")
    else:
        when = store.last_saved(app)
        st.caption(f"💾 Decisions saved to {store.describe()}" + (f" · last {when[11:16]}" if when else ""))
    with st.popover("Reset demo data"):
        st.caption("Clears every saved decision and approval for this app and starts from the sample data.")
        if st.button("Reset now", key=f"_{app}_reset"):
            store.reset(app)
            for k in list(ss.keys()):
                del ss[k]
            if on_reset:
                on_reset()
            st.rerun()
