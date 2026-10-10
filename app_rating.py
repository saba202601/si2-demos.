"""SI² demo: Personal Auto Rating Engine.

A transparent multiplicative rating algorithm: base rate times each rating factor,
shown step by step per coverage. All rates and factors are illustrative.
"""
import datetime as dt

import pandas as pd
import streamlit as st

from si2_common import branding, gate

branding.page("Rating Engine",
              "Personal Auto premium built step by step: base rate, every factor, and the final premium per coverage.")
gate.require_access()

BASE = {"BI": 360.0, "PD": 280.0, "PIP": 190.0, "UM": 110.0, "COLL": 450.0, "COMP": 140.0}
COV_NAME = {"BI": "Bodily injury", "PD": "Property damage", "PIP": "Personal injury protection",
            "UM": "Uninsured motorist", "COLL": "Collision", "COMP": "Comprehensive"}
PIP_STATES = {"FL", "NY"}
STATE_REL = {"FL": 1.32, "GA": 1.08, "NC": 0.86, "NY": 1.28, "OH": 0.82, "TX": 1.05}
TERRITORY = {"1 · Urban core": 1.35, "2 · Urban": 1.15, "3 · Suburban": 1.00, "4 · Small town": 0.92, "5 · Rural": 0.85}
AGE_BANDS = [(16, 19, 2.10), (20, 24, 1.55), (25, 29, 1.20), (30, 49, 1.00), (50, 64, 0.92), (65, 74, 1.00),
             (75, 120, 1.18)]
CLAIMS = {0: 1.00, 1: 1.25, 2: 1.60, 3: 2.00}
VIOLATIONS = {0: 1.00, 1: 1.15, 2: 1.35, 3: 1.60}
USE = {"Pleasure": 0.95, "Commute": 1.00, "Business": 1.15}
BI_LIMIT = {"25/50": 0.80, "50/100": 1.00, "100/300": 1.22, "250/500": 1.45}
PD_LIMIT = {"25": 0.90, "50": 1.00, "100": 1.10}
COLL_DED = {250: 1.12, 500: 1.00, 1000: 0.82}
COMP_DED = {100: 1.15, 250: 1.05, 500: 1.00, 1000: 0.85}
POLICY_FEE = 25.0


def age_factor(age: int) -> float:
    return next(f for lo, hi, f in AGE_BANDS if lo <= age <= hi)


def veh_age_factor(model_year: int) -> float:
    age = dt.date.today().year - model_year
    return 1.10 if age <= 1 else 1.00 if age <= 4 else 0.88 if age <= 9 else 0.75


def rate(inp: dict) -> pd.DataFrame:
    covs = ["BI", "PD", "UM"] + (["PIP"] if inp["state"] in PIP_STATES else [])
    if inp["phys"]:
        covs += ["COLL", "COMP"]
    rows = []
    for c in covs:
        f = {"State": STATE_REL[inp["state"]], "Territory": TERRITORY[inp["territory"]],
             "Driver age": age_factor(inp["age"]), "Claims": CLAIMS[min(inp["claims"], 3)],
             "Violations": VIOLATIONS[min(inp["violations"], 3)], "Use": USE[inp["use"]]}
        f["Limit / deductible"] = (BI_LIMIT[inp["bi"]] if c in ("BI", "UM") else PD_LIMIT[inp["pd"]] if c == "PD"
                                   else COLL_DED[inp["coll_ded"]] if c == "COLL"
                                   else COMP_DED[inp["comp_ded"]] if c == "COMP" else 1.0)
        f["Symbol"] = 0.70 + 0.04 * inp["symbol"] if c in ("COLL", "COMP") else 1.0
        f["Vehicle age"] = veh_age_factor(inp["model_year"]) if c in ("COLL", "COMP") else 1.0
        prem = BASE[c]
        for v in f.values():
            prem *= v
        rows.append({"Coverage": COV_NAME[c], "Base rate": BASE[c], **{k: round(v, 3) for k, v in f.items()},
                     "Premium": round(prem, 0)})
    return pd.DataFrame(rows)


with st.sidebar:
    st.header("Risk")
    inp = {
        "state": st.selectbox("State", list(STATE_REL), index=0),
        "territory": st.selectbox("Territory", list(TERRITORY), index=2),
        "age": st.slider("Driver age", 16, 90, 34),
        "claims": st.selectbox("At-fault claims (3 yrs)", [0, 1, 2, 3], format_func=lambda x: "3 or more" if x == 3 else str(x)),
        "violations": st.selectbox("Violations (3 yrs)", [0, 1, 2, 3], format_func=lambda x: "3 or more" if x == 3 else str(x)),
        "use": st.radio("Vehicle use", list(USE), index=1, horizontal=True),
        "model_year": st.number_input("Model year", 1995, dt.date.today().year + 1, 2021),
        "symbol": st.slider("Physical damage symbol", 1, 27, 14, help="Higher symbols mean costlier vehicles to repair."),
    }
    st.header("Coverage")
    inp["bi"] = st.selectbox("BI / UM limits ($000)", list(BI_LIMIT), index=2)
    inp["pd"] = st.selectbox("PD limit ($000)", list(PD_LIMIT), index=1)
    inp["phys"] = st.toggle("Include collision and comprehensive", value=True)
    inp["coll_ded"] = st.selectbox("Collision deductible", list(COLL_DED), index=1, disabled=not inp["phys"])
    inp["comp_ded"] = st.selectbox("Comprehensive deductible", list(COMP_DED), index=2, disabled=not inp["phys"])

sheet = rate(inp)
total = sheet.Premium.sum() + POLICY_FEE

c1, c2, c3 = st.columns(3)
c1.metric("Annual premium", f"${total:,.0f}")
c2.metric("Six-month premium", f"${total / 2:,.0f}")
c3.metric("Coverages rated", len(sheet))

tab_ws, tab_what, tab_tables = st.tabs(["Rating worksheet", "What if", "Factor tables"])

with tab_ws:
    st.caption("Premium = base rate × every factor. Factors that don't apply to a coverage show 1.000.")
    st.dataframe(sheet, hide_index=True, width="stretch",
                 column_config={"Base rate": st.column_config.NumberColumn(format="$%.0f"),
                                "Premium": st.column_config.NumberColumn(format="$%.0f")})
    st.write(f"Coverage premium **${sheet.Premium.sum():,.0f}** + policy fee **${POLICY_FEE:,.0f}** = "
             f"**${total:,.0f}** per year.")
    st.download_button("Download worksheet (CSV)", sheet.to_csv(index=False), "si2_rating_worksheet.csv", "text/csv")

with tab_what:
    st.caption("Annual premium for this same risk as only the driver's age changes.")
    ages = list(range(16, 86))
    curve = pd.DataFrame({"Driver age": ages,
                          "Annual premium": [rate({**inp, "age": a}).Premium.sum() + POLICY_FEE for a in ages]})
    st.line_chart(curve, x="Driver age", y="Annual premium", color="#2B4CF2", height=300)
    st.caption("Annual premium by deductible choice")
    if inp["phys"]:
        opts = pd.DataFrame([{"Collision deductible": f"${d:,}",
                              "Annual premium": rate({**inp, "coll_ded": d}).Premium.sum() + POLICY_FEE}
                             for d in COLL_DED])
        st.bar_chart(opts, x="Collision deductible", y="Annual premium", color="#2B4CF2", height=240)
    else:
        st.info("Turn on collision and comprehensive to compare deductibles.")

with tab_tables:
    cols = st.columns(3)
    tables = {
        "Base rates": pd.DataFrame({"coverage": list(BASE), "base rate": list(BASE.values())}),
        "State": pd.DataFrame({"state": list(STATE_REL), "factor": list(STATE_REL.values())}),
        "Territory": pd.DataFrame({"territory": list(TERRITORY), "factor": list(TERRITORY.values())}),
        "Driver age": pd.DataFrame([{"ages": f"{lo}–{hi}" if hi < 120 else f"{lo}+", "factor": f} for lo, hi, f in AGE_BANDS]),
        "At-fault claims": pd.DataFrame({"claims": ["0", "1", "2", "3+"], "factor": list(CLAIMS.values())}),
        "Violations": pd.DataFrame({"violations": ["0", "1", "2", "3+"], "factor": list(VIOLATIONS.values())}),
        "Use": pd.DataFrame({"use": list(USE), "factor": list(USE.values())}),
        "BI / UM limits": pd.DataFrame({"limit": list(BI_LIMIT), "factor": list(BI_LIMIT.values())}),
        "Collision deductible": pd.DataFrame({"deductible": list(COLL_DED), "factor": list(COLL_DED.values())}),
    }
    for i, (name, df) in enumerate(tables.items()):
        with cols[i % 3]:
            st.markdown(f"**{name}**")
            st.dataframe(df, hide_index=True, width="stretch")

branding.note_synthetic()
branding.footer()
