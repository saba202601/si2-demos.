"""Optional access code.

If you add APP_ACCESS_CODE to the app's Secrets in Streamlit Cloud, visitors must
enter that code before they see the demo. With no secret set, the app is open.
"""
import streamlit as st


def _configured_code():
    try:
        return st.secrets.get("APP_ACCESS_CODE")
    except Exception:  # no secrets file at all
        return None


def require_access() -> None:
    code = _configured_code()
    if not code or st.session_state.get("si2_ok"):
        return
    st.info("Enter the access code from your SI² demo invitation.")
    entered = st.text_input("Access code", type="password")
    if st.button("Open demo", type="primary"):
        if entered.strip() == str(code):
            st.session_state["si2_ok"] = True
            st.rerun()
        else:
            st.error("That code didn't match. Check your invitation email or request access at si2insure.com.")
    st.stop()
