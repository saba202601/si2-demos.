"""SI² Studio: every SI² engine in one app on your own PC.

    streamlit run si2_studio.py

The Rule Studio (My desk, rules, authority, approvals, claim coverage, policy forms) and the Canonical Master (elements, pick lists,
aliases, insurance forms, Party model) work on SI2Canonical when
SI2_SQL_SERVER is set; the other engines run on their synthetic demo data. One menu, one sign-in, nothing online.
"""
import streamlit as st

st.set_page_config(page_title="SI² Studio", page_icon="🛡️", layout="wide")
st.session_state["_si2_studio"] = True          # the apps show this menu instead of links to the online demos

PAGES = {
    "Your work": [
        st.Page("app_rule_studio.py", title="Rule Studio · My desk", icon="🧭", default=True, url_path="studio"),
        st.Page("app_canonical_master.py", title="Canonical Master", icon="📚", url_path="canonical-master"),
        st.Page("app_bridge.py", title="Data Bridge", icon="🌉", url_path="data-bridge"),
    ],
    "Start here": [
        st.Page("app_hub.py", title="Command Center", icon="💰", url_path="command-center"),
        st.Page("app_roles.py", title="Role-Based Super Intelligence", icon="👥", url_path="roles"),
        st.Page("app_canonical.py", title="Canonical Data Model", icon="🏛️", url_path="canonical"),
    ],
    "Data and reporting": [
        st.Page("app_migration.py", title="Legacy-to-Cloud Migration", icon="🚚", url_path="migration"),
        st.Page("app_iso_bureau.py", title="ISO Bureau Reporting", icon="📊", url_path="iso-bureau"),
        st.Page("app_bureau.py", title="NCCI Bureau Reporting", icon="🧾", url_path="ncci-bureau"),
    ],
    "Decisions": [
        st.Page("app_rules.py", title="Business Rule Engine (demo)", icon="⚖️", url_path="rules-demo"),
        st.Page("app_rating.py", title="Rating Engine", icon="🧮", url_path="rating"),
        st.Page("app_claims.py", title="Claims Triage", icon="🚑", url_path="claims-triage"),
        st.Page("app_fraud.py", title="Fraud Engine", icon="🔎", url_path="fraud"),
    ],
}
# A few engines keep working data under the same names (src, audit): each engine gets its own copy back when you return.
SHARED = ("src", "audit")
ss = st.session_state
page = st.navigation(PAGES, position="sidebar", expanded=True)
owner, current = ss.get("_si2_owner"), page.url_path
if owner != current:
    stash = ss.setdefault("_si2_stash", {})
    if owner is not None:
        stash[owner] = {k: ss[k] for k in SHARED if k in ss}
    for k in SHARED:
        ss.pop(k, None)
    ss.update(stash.get(current, {}))
    ss["_si2_owner"] = current
page.run()
