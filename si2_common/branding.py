"""SI² look and feel shared by every demo app."""
import base64
from pathlib import Path

import streamlit as st

WEBSITE = "https://si2insure.com"
try:
    VERSION = (Path(__file__).resolve().parents[1] / "VERSION").read_text().strip()
except OSError:
    VERSION = "dev"
DISCLAIMER = ("SI² is independent and is not affiliated with, endorsed or sponsored by NCCI, ISO / Verisk, ACORD, "
              "Guidewire, Duck Creek or any rating bureau, standards body or software vendor. Their names are used only "
              "to describe the formats SI² works with; all trademarks belong to their owners.")
CONTACT = "hello@si2insure.com"

SHIELD_SVG = """
<svg width="44" height="50" viewBox="0 0 120 136" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="SI squared logo">
  <path d="M60 6 L110 24 V64 C110 97 88 119 60 130 C32 119 10 97 10 64 V24 Z" fill="#0B1B2B"/>
  <path d="M60 16 L100 31 V64 C100 91 83 109 60 119 C37 109 20 91 20 64 V31 Z" fill="none" stroke="#2B4CF2" stroke-width="2"/>
  <text x="55" y="88" text-anchor="middle" font-family="Arial, sans-serif" font-weight="800" font-size="46" fill="#FFFFFF">SI</text>
  <text x="88" y="60" text-anchor="middle" font-family="Arial, sans-serif" font-weight="700" font-size="22" fill="#2B4CF2">2</text>
</svg>
"""

LOGO_URI = "data:image/svg+xml;base64," + base64.b64encode(SHIELD_SVG.strip().encode()).decode()

CSS = """
<style>
.si2-head{display:flex;align-items:center;gap:14px;padding:4px 0 14px;border-bottom:1px solid #D8DFE7;margin-bottom:18px}
.si2-title{font-size:1.7rem;font-weight:700;margin:0;line-height:1.2;color:#0B1B2B}
.si2-head p{margin:2px 0 0;color:#4A5868;font-size:.95rem}
.si2-pill{display:inline-block;font-size:.75rem;font-weight:600;letter-spacing:.06em;text-transform:uppercase;
  color:#2B4CF2;border:1px solid #2B4CF2;border-radius:999px;padding:1px 10px;margin-left:8px;vertical-align:middle}
.si2-foot{margin-top:36px;padding-top:14px;border-top:1px solid #D8DFE7;color:#4A5868;font-size:.9rem}
.si2-foot a{color:#2B4CF2}
</style>
"""


# the demo hub: suggested order for a client walk-through
DEMOS = [
    ("SI² Command Center", "https://si2-command.streamlit.app", "ROI calculator, bureau reporting calendar, all demos"),
    ("Role-Based Super Intelligence", "https://si2-roles.streamlit.app", "15 roles, 5 departments: SI² prepares, the person decides"),
    ("Canonical Data Model", "https://si2-canonical.streamlit.app", "Start here: one company model, where-used across every app"),
    ("Legacy-to-Cloud Migration Workbench", "https://si2-migrate.streamlit.app", "Initial load, mapping, gaps, delta loads, sign-off"),
    ("ISO Bureau Reporting", "https://si2-iso-bureau.streamlit.app", "All ISO lines: effective-dated layouts, generate, validate, submit"),
    ("Bureau Reporting Workbench", "https://si2-bureau.streamlit.app", "NCCI WCSTAT · WCPOLS · WCIND · WCMED"),
    ("Business Rule Engine", "https://si2-rules.streamlit.app", "Rules in plain conditions, draft → approval → production"),
    ("Rating Engine", "https://si2-rating.streamlit.app", "Step-by-step premium; new factors approved by an actuary"),
    ("Claims Triage", "https://si2-claims.streamlit.app", "Score and route new claims"),
    ("Fraud Engine", "https://si2-fraud.streamlit.app", "Detect, prevent and investigate fraud"),
]

TOURS = {
    "Role-Based Super Intelligence": [
        "**Overview**: 15 roles in 5 departments, each with how many decisions were made and how often people agreed with SI².",
        "**Underwriter**: every submission scored and explained; accept / refer / decline within your own boundaries.",
        "**Claims Adjuster**: triage, image damage, liability and a reserve range; changes above your authority go to a second person.",
        "**Reinsurance → Enterprise Risk**: choose a catastrophe program and see the solvency ratio move from gross to net.",
        "**Compliance**: fairness of SI²'s recommendations and of people's decisions, restricted factors, and the full audit trail.",
    ],
    "SI² Command Center": [
        "**💰 ROI calculator**: enter a carrier's hours and error rates; every SI² assumption is editable.",
        "**📅 Reporting calendar**: NCCI and ISO submissions due in the next 12 months, with status.",
        "**🧭 All demos**: the walk-through order for a client meeting."],
    "Canonical Data Model": [
        "Open **🏢 Company model**: 150 business terms harvested from all six SI² apps.",
        "Pick **Policy Number** under Where used: one concept, seven elements, four apps.",
        "Govern it: edit the definition or add a synonym, submit, change the sidebar name and approve: it is published to every app.",
        "Untick *Shared terms only* to see every term; download the model with where-used.",
        "Open **The model** and **Map a source file** to see one legacy file mapped into the core model."],
    "Legacy-to-Cloud Migration Workbench": [
        "Step **0 · Initial load** → *Use the sample upload set*: Excel, CSV, Oracle DDL, ACORD XML, JSON and an API.",
        "**Data quality** shows the bureau-style edits; **Keys & pick lists** → *Approve all ≥ 90%* (pick the driver link yourself).",
        "**Approve & load**: submit the plan, change the sidebar name, approve it, then *Create tables and load*.",
        "**Delta loads** → *Load the sample delta*: changed rows get a new version, history is kept.",
        "**🤖 Ask SI²**: which keys need my decision, why rows were quarantined.",
        "**Use in migration** → then Steps 3-9: discovery, mapping, canonical gaps, inject, test, two-person sign-off."],
    "ISO Bureau Reporting": [
        "**▶️ Bureau Run**: pick a line, accounting period and record type; generate, validate, approve.",
        "**✅ SME Validation Workbench**: approve fields, descriptions, pick lists and mappings.",
        "**🧩 Canonical Gaps**: map, add or skip what the canonical model lacks.",
        "**📐 Layouts**: compare effective-dated layout versions."],
    "Bureau Reporting Workbench": [
        "Step **3 · Canonical model & mapping** → **🧩 Canonical gaps**: resolve WCIO fields and codes.",
        "Step **5**: enter your name in the sidebar and generate a WCSTAT file.",
        "Step **6**: the person who generated it cannot approve it; change the name, approve and submit.",
        "Step **6**: 🤖 *Explain these errors and how to fix them*; Step **7**: resubmit a revision."],
    "Business Rule Engine": [
        "**Rules (draft)** → ✍️ *Write a rule in plain English*: e.g. Decline drivers under 18 in Florida.",
        "**🧩 Rule gaps**: map `drv_age`, fix `'FLA'`, add `telematics_score` and `'Delivery'`.",
        "**Rules (draft)**: enter your name, *Submit the draft for approval*.",
        "**✅ Approvals**: change the sidebar name and approve; the draft goes to production.",
        "**Run on submissions** now uses the approved rules."],
    "Rating Engine": [
        "**📥 Incoming quotes**: 7 of 8 quotes cannot be rated.",
        "**🧩 Rating gaps**: rate AL as GA, add the 500/1000 and $2,000 factors (SI² drafts them).",
        "**✅ Approvals**: an actuary (a different name) approves with a filing reference.",
        "Back on **Incoming quotes**: indications become bindable."],
    "Claims Triage": ["**📥 New FNOL**: 5 mobile-app claims cannot be routed: their cause of loss has no score.",
                      "**🧩 Claim gaps**: score Animal collision as Single-vehicle collision, add Glass breakage (SI² drafts 8 points).",
                      "**Claim detail**: 🤖 Explain this routing; re-route a claim; releasing one from SIU needs a second person.",
                      "Sidebar: change a routing threshold, submit it, approve it under another name on **✅ Approvals**."],
    "Fraud Engine": ["**3 · Run the engine**, then **4 · Prevent**: money stopped at the gates.",
                     "**5 · SIU cases**: 🤖 summarise a case; releasing it as a false positive needs a second person.",
                     "**7 · Data gaps**: the data the remaining fraud types need; raise a data request.",
                     "**✅ Approvals**: approve the release under another name."],
}


def _html(text: str) -> str:
    """Flatten HTML to one line. Indented lines would otherwise render as a code block."""
    return "".join(line.strip() for line in text.splitlines())


def page(title: str, subtitle: str) -> None:
    """Set up the page and draw the SI² header. Call first in every app."""
    st.set_page_config(page_title=f"{title} | SI²", page_icon="🛡️", layout="wide")
    st.markdown(_html(CSS), unsafe_allow_html=True)
    # st.html renders the header as HTML directly, with no Markdown step that could turn it into a code block.
    st.html(_html(f"""<div class="si2-head"><img src="{LOGO_URI}" width="44" height="50" alt="SI² logo">
        <div><div class="si2-title">{title}<span class="si2-pill">Demo</span></div><p>{subtitle}</p></div></div>"""))
    st.session_state["_si2_title"] = title
    if title in TOURS:
        with st.expander("Two-minute guided tour"):
            st.markdown("\n".join(f"{i}. {t}" for i, t in enumerate(TOURS[title], 1)))


def note_synthetic() -> None:
    st.caption(
        "All data in this demo is synthetic. Codes, layouts, edits and factors are illustrative "
        "and are not official bureau or company values; confirm them against the bureau manuals and filed rates. "
        + DISCLAIMER
    )


def demo_links() -> None:
    """The SI² demo hub in the sidebar, current app first in bold."""
    cur = st.session_state.get("_si2_title", "")
    with st.sidebar:
        st.divider()
        st.markdown("**SI² demos**")
        st.markdown("\n".join(f"{i}. " + (f"**{t}** (you are here)" if t == cur else f"[{t}]({u})") + f"  \n   <small>{d}</small>"
                              for i, (t, u, d) in enumerate(DEMOS, 1)), unsafe_allow_html=True)


def footer() -> None:
    demo_links()
    st.markdown(
        f'<div class="si2-foot"><b>SI²</b> · Super Intelligence for Insurance · '
        f'Want this on your own data? Email <b>{CONTACT}</b> or visit '
        f'<a href="{WEBSITE}" target="_blank">si2insure.com</a> · v{VERSION}</div>',
        unsafe_allow_html=True,
    )
