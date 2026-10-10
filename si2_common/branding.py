"""SI² look and feel shared by every demo app."""
import streamlit as st

WEBSITE = "https://si2insure.com"
CONTACT = "hello@si2insure.com"

SHIELD_SVG = """
<svg width="44" height="50" viewBox="0 0 120 136" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="SI squared logo">
  <path d="M60 6 L110 24 V64 C110 97 88 119 60 130 C32 119 10 97 10 64 V24 Z" fill="#0B1B2B"/>
  <path d="M60 16 L100 31 V64 C100 91 83 109 60 119 C37 109 20 91 20 64 V31 Z" fill="none" stroke="#2B4CF2" stroke-width="2"/>
  <text x="55" y="88" text-anchor="middle" font-family="Arial, sans-serif" font-weight="800" font-size="46" fill="#FFFFFF">SI</text>
  <text x="88" y="60" text-anchor="middle" font-family="Arial, sans-serif" font-weight="700" font-size="22" fill="#2B4CF2">2</text>
</svg>
"""

CSS = """
<style>
.si2-head{display:flex;align-items:center;gap:14px;padding:4px 0 14px;border-bottom:1px solid #D8DFE7;margin-bottom:18px}
.si2-head h1{font-size:1.7rem;margin:0;padding:0;line-height:1.2;color:#0B1B2B}
.si2-head p{margin:2px 0 0;color:#4A5868;font-size:.95rem}
.si2-pill{display:inline-block;font-size:.75rem;font-weight:600;letter-spacing:.06em;text-transform:uppercase;
  color:#2B4CF2;border:1px solid #2B4CF2;border-radius:999px;padding:1px 10px;margin-left:8px;vertical-align:middle}
.si2-foot{margin-top:36px;padding-top:14px;border-top:1px solid #D8DFE7;color:#4A5868;font-size:.9rem}
.si2-foot a{color:#2B4CF2}
</style>
"""


def page(title: str, subtitle: str) -> None:
    """Set up the page and draw the SI² header. Call first in every app."""
    st.set_page_config(page_title=f"{title} | SI²", page_icon="🛡️", layout="wide")
    st.markdown(CSS, unsafe_allow_html=True)
    st.markdown(
        f"""<div class="si2-head">{SHIELD_SVG}
        <div><h1>{title}<span class="si2-pill">Demo</span></h1><p>{subtitle}</p></div></div>""",
        unsafe_allow_html=True,
    )


def note_synthetic() -> None:
    st.caption(
        "All data in this demo is synthetic. Codes, layouts and factors are illustrative "
        "and are not official bureau or company values."
    )


def footer() -> None:
    st.markdown(
        f"""<div class="si2-foot"><b>SI²</b> · Super Intelligence for Insurance ·
        Want this on your own data? Email <b>{CONTACT}</b> or visit
        <a href="{WEBSITE}" target="_blank">si2insure.com</a></div>""",
        unsafe_allow_html=True,
    )
