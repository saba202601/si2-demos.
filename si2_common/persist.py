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


def workspace_picker():
    """Client workspace selector: each client's decisions and approvals are kept apart."""
    ss = st.session_state
    try:
        options = store.workspaces()
    except Exception:
        return
    cur = store.workspace()
    if cur not in options:
        options = sorted(set(options) | {cur})
    pick = st.selectbox("Client workspace", options, index=options.index(cur), key="_ws_pick",
                        help="Each client's data, decisions and approvals are kept separately.")
    if not store.allowed_workspaces():
        with st.popover("New workspace"):
            name = st.text_input("Name (e.g. carrier short name)", key="_ws_new")
            if st.button("Create", key="_ws_create") and name.strip():
                pick = "".join(ch for ch in name.strip().lower().replace(" ", "-") if ch.isalnum() or ch in "-_")[:40]
    if pick != cur:
        for k in list(ss.keys()):
            del ss[k]
        ss["si2_workspace"] = pick
        st.rerun()


def backup_panel(actor: str = ""):
    with st.popover("Backup / restore"):
        ws = store.workspace()
        st.caption(f"Everything saved for workspace **{ws}** (all apps and approvals) in one file.")
        st.download_button("Download backup", store.export_workspace(ws), f"SI2_backup_{ws}.json", "application/json",
                           key="_bk_dl")
        up = st.file_uploader("Restore from a backup file", type=["json"], key="_bk_up")
        if up is not None and st.button("Restore (replaces this workspace)", key="_bk_go"):
            try:
                res = store.import_workspace(up.getvalue().decode(), ws, actor)
                for k in [k for k in st.session_state.keys() if k != "si2_workspace"]:
                    del st.session_state[k]
                st.session_state["si2_workspace"] = ws
                st.success(f"Restored {res['state']} saved items and {res['approvals']} approvals.")
                st.rerun()
            except (ValueError, KeyError) as exc:
                st.error(f"Restore failed: {exc}")


def sidebar(app: str, on_reset=None):
    ss = st.session_state
    workspace_picker()
    err = ss.get(f"_{app}_store_error")
    if err:
        st.caption(f"⚠️ Decisions are kept for this session only: {err[:120]}")
    else:
        when = store.last_saved(app)
        st.caption(f"💾 Decisions saved to {store.describe()}" + (f" · last {when[11:16]}" if when else ""))
    backup_panel(ss.get("sme_name", ""))
    with st.popover("Reset demo data"):
        st.caption("Clears every saved decision and approval for this app and starts from the sample data.")
        if st.button("Reset now", key=f"_{app}_reset"):
            store.reset(app)
            ws = ss.get("si2_workspace")
            for k in list(ss.keys()):
                del ss[k]
            if ws:
                ss["si2_workspace"] = ws
            if on_reset:
                on_reset()
            st.rerun()
