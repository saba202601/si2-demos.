"""Who is using the app: the company's single sign-on when configured, a typed name in demo mode.

Single sign-on uses Streamlit's built-in OpenID Connect login (st.login): Microsoft Entra ID, Google, Okta, Auth0 ...
Configure it in .streamlit/secrets.toml (see .streamlit/secrets.toml.example) and every approval, audit entry and
two-person check uses the signed-in email instead of a typed name.
"""
from __future__ import annotations

import streamlit as st


def sso_configured() -> bool:
    try:
        return "auth" in st.secrets
    except Exception:
        return False


def signed_in() -> bool:
    try:
        return bool(st.user.is_logged_in)
    except Exception:
        return False


def user_label() -> str:
    try:
        return str(st.user.get("email") or st.user.get("name") or "")
    except Exception:
        return ""


def name_input(label: str = "SME name", key: str = "sme_name", placeholder: str = "Your name for approvals",
               default: str = "") -> str:
    """Call inside `with st.sidebar:`. Returns the identity used for proposals, approvals and the audit trail."""
    if signed_in():
        st.session_state[key] = user_label()
        st.caption(f"🔐 Signed in as **{st.session_state[key]}**")
        if st.button("Sign out", key=f"{key}_logout"):
            st.logout()
        return st.session_state[key]
    if sso_configured():
        st.caption("🔐 Sign in with your company account to propose or approve changes.")
        if st.button("Sign in", key=f"{key}_login", type="primary"):
            st.login()
        st.session_state[key] = ""
        return ""
    if default and key not in st.session_state:
        st.session_state[key] = default
    v = st.text_input(label, key=key, placeholder=placeholder,
                      help="Demo mode: type a name. With single sign-on configured, your company login is used instead.")
    return v
