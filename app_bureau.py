"""SI² demo: Bureau Statistical Reporting.

Builds statistical-plan-style premium and loss records from canonical data, runs
edit checks, explains each error and suggests the fix before submission.
The record layout and edits are illustrative, not an official ISO, NCCI or AAIS plan.
"""
import datetime as dt

import pandas as pd
import streamlit as st

from si2_common import branding, data, gate

branding.page("Bureau Statistical Reporting",
              "Statistical-plan-style records with edit checks, plain-language errors and suggested fixes.")
gate.require_access()

QUARTERS = {"2026 Q3": (dt.date(2026, 7, 1), dt.date(2026, 9, 30)),
            "2026 Q4": (dt.date(2026, 10, 1), dt.date(2026, 12, 31))}
LIABILITY = {"BI", "PD", "PIP", "UM"}
ASL = {"liability": "192", "physical": "211"}  # NAIC annual statement lines 19.2 and 21.1
LIMIT_CODES = {"25/50": "01", "50/100": "02", "100/300": "03", "250/500": "04", "25": "11", "50": "12",
               "100": "13", "10": "21", "ACV": "90"}

# field, length, description
LAYOUT = [("rec_type", 1, "P = premium, L = loss"), ("state", 2, "State code"),
          ("acct_ym", 6, "Accounting year and month (YYYYMM)"), ("asl", 3, "Annual statement line"),
          ("coverage", 4, "Coverage code"), ("zip", 5, "Garaging ZIP code"),
          ("eff_date", 8, "Policy effective date (YYYYMMDD)"), ("exposure", 2, "Car-months written"),
          ("model_year", 4, "Vehicle model year"), ("symbol", 2, "Rating symbol"), ("use", 1, "Vehicle use"),
          ("deductible", 5, "Deductible amount"), ("limit", 2, "Limit code"),
          ("amount", 11, "Signed amount in cents"), ("ref_no", 10, "Policy or claim number"),
          ("acc_date", 8, "Accident date (losses only)"), ("cause", 2, "Cause of loss (losses only)")]

EDITS = {
    "E01": ("Fatal", "State code is not valid.", "Correct the state code from the policy's garaging state."),
    "E02": ("Error", "ZIP code does not belong to the reported state.", "Check the garaging address; re-key ZIP or state."),
    "E03": ("Error", "Coverage is reported under the wrong annual statement line.",
            "Liability coverages go to line 192; collision and comprehensive go to line 211."),
    "E04": ("Error", "Accounting date is outside the reporting quarter.",
            "Move the transaction to the quarter it was booked in, or hold it for the next submission."),
    "E05": ("Warning", "Written premium is zero or negative on a new or renewal transaction.",
            "Confirm the premium; returns belong on endorsement or cancellation records."),
    "E06": ("Error", "Exposure must be between 1 and 12 car-months.", "Recalculate exposure from the term dates."),
    "E07": ("Error", "Vehicle model year is out of range.", "Check the VIN decode; model year can't be after next year."),
    "E08": ("Error", "Deductible doesn't fit the coverage.",
            "Liability coverages carry no deductible; physical damage needs one."),
    "E09": ("Fatal", "Accident date is after the accounting date or before the policy took effect.",
            "Verify the date of loss against the claim file and policy term."),
    "E10": ("Error", "Cause of loss doesn't match the coverage.", "Use the cause of loss code for the coverage paid."),
}
CAUSE_FOR = data.CAUSES


@st.cache_data
def build_records(quarter: str, inject: bool) -> pd.DataFrame:
    pols = data.legacy_policy_extract()
    clms = data.legacy_claims_extract(pols)
    t = data.build_canonical(pols, clms)
    q_start, q_end = QUARTERS[quarter]
    acct = q_start.strftime("%Y%m")
    cov = (t["Coverage"].merge(t["RiskItem"], on="risk_item_id").merge(t["Policy"], on="policy_id")
           .merge(t["Location"][["policy_id", "postal_code"]], on="policy_id")
           .merge(t["PremiumTransaction"], on="coverage_id"))
    recs = []
    for _, r in cov.iterrows():
        recs.append({"rec_type": "P", "state": data.STATES[r.state][0], "acct_ym": acct,
                     "asl": ASL["liability" if r.coverage_code in LIABILITY else "physical"],
                     "coverage": r.coverage_code, "zip": r.postal_code, "eff_date": r.effective_date.replace("-", ""),
                     "exposure": 12, "model_year": r.model_year, "symbol": r.rating_symbol, "use": r.use_type[0],
                     "deductible": r.deductible, "limit": LIMIT_CODES.get(r.limit, "99"),
                     "amount": int(round(r.written_premium * 100)), "ref_no": r.policy_number,
                     "acc_date": "", "cause": "", "_state_abbr": r.state})
    lc = (t["Claim"].merge(t["LossTransaction"], on="claim_id")
          .merge(t["Coverage"], on="coverage_id").merge(t["RiskItem"].drop(columns="policy_id"), on="risk_item_id")
          .merge(t["Policy"], on="policy_id").merge(t["Location"][["policy_id", "postal_code"]], on="policy_id"))
    for _, r in lc.iterrows():
        eff = dt.date.fromisoformat(r.effective_date)
        acc = dt.date.fromisoformat(r.accident_date)
        acc = max(eff + dt.timedelta(days=5), min(acc, q_start - dt.timedelta(days=10)))
        recs.append({"rec_type": "L", "state": data.STATES[r.state][0], "acct_ym": acct,
                     "asl": ASL["liability" if r.coverage_code in LIABILITY else "physical"],
                     "coverage": r.coverage_code, "zip": r.postal_code, "eff_date": r.effective_date.replace("-", ""),
                     "exposure": 0, "model_year": r.model_year, "symbol": r.rating_symbol, "use": r.use_type[0],
                     "deductible": r.deductible, "limit": LIMIT_CODES.get(r.limit, "99"),
                     "amount": int(round(r.paid_loss * 100)), "ref_no": r.claim_number,
                     "acc_date": acc.strftime("%Y%m%d"), "cause": r.cause_of_loss, "_state_abbr": r.state})
    df = pd.DataFrame(recs)
    if inject:
        prem = df.index[df.rec_type == "P"].tolist()
        loss = df.index[df.rec_type == "L"].tolist()
        df.loc[prem[3], "state"] = "99"
        other_zip = "75201" if df.loc[prem[7], "_state_abbr"] != "TX" else "32801"
        df.loc[prem[7], "zip"] = other_zip
        coll = [i for i in prem if df.loc[i, "coverage"] == "COLL"]
        df.loc[coll[1], "asl"] = "192"
        prior = (q_start - dt.timedelta(days=40)).strftime("%Y%m")
        df.loc[prem[18], "acct_ym"] = prior
        df.loc[prem[22], "amount"] = 0
        df.loc[prem[27], "exposure"] = 14
        df.loc[prem[31], "model_year"] = q_start.year + 5
        bi = [i for i in prem if df.loc[i, "coverage"] == "BI"]
        df.loc[bi[4], "deductible"] = 500
        df.loc[loss[2], "acc_date"] = (q_end + dt.timedelta(days=15)).strftime("%Y%m%d")
        coll_loss = [i for i in loss if df.loc[i, "coverage"] in ("COLL", "COMP")] or loss
        df.loc[coll_loss[0], "cause"] = "03"
    df.insert(0, "record", range(1, len(df) + 1))
    return df


def run_edits(df: pd.DataFrame, quarter: str) -> pd.DataFrame:
    q_start, q_end = QUARTERS[quarter]
    valid_states = {v[0]: k for k, v in data.STATES.items()}
    out = []

    def hit(r, edit, field, value):
        sev, msg, fix = EDITS[edit]
        out.append({"record": r.record, "ref_no": r.ref_no, "edit": edit, "severity": sev, "field": field,
                    "value": str(value), "problem": msg, "suggested fix": fix})

    for _, r in df.iterrows():
        abbr = valid_states.get(r.state)
        if abbr is None:
            hit(r, "E01", "state", r.state)
        else:
            lo, hi = data.STATES[abbr][1]
            if not (str(r.zip).isdigit() and lo <= int(str(r.zip)[:3]) <= hi):
                hit(r, "E02", "zip", r.zip)
        expected = ASL["liability" if r.coverage in LIABILITY else "physical"]
        if r.asl != expected:
            hit(r, "E03", "asl", r.asl)
        y, m = int(r.acct_ym[:4]), int(r.acct_ym[4:])
        if not (q_start <= dt.date(y, m, 1) <= q_end):
            hit(r, "E04", "acct_ym", r.acct_ym)
        if r.model_year > q_start.year + 1 or r.model_year < 1981:
            hit(r, "E07", "model_year", r.model_year)
        if (r.coverage in LIABILITY and r.deductible) or (r.coverage not in LIABILITY and not r.deductible):
            hit(r, "E08", "deductible", r.deductible)
        if r.rec_type == "P":
            if r.amount <= 0:
                hit(r, "E05", "amount", r.amount)
            if not 1 <= r.exposure <= 12:
                hit(r, "E06", "exposure", r.exposure)
        else:
            acc = dt.datetime.strptime(r.acc_date, "%Y%m%d").date()
            eff = dt.datetime.strptime(r.eff_date, "%Y%m%d").date()
            if acc > q_end or acc < eff:
                hit(r, "E09", "acc_date", r.acc_date)
            if r.cause != CAUSE_FOR.get(r.coverage):
                hit(r, "E10", "cause", r.cause)
    return pd.DataFrame(out, columns=["record", "ref_no", "edit", "severity", "field", "value", "problem",
                                      "suggested fix"])


def fixed_width(df: pd.DataFrame) -> str:
    lines = []
    for _, r in df.iterrows():
        parts = []
        for field, length, _ in LAYOUT:
            v = r[field]
            if field == "amount":
                parts.append(("-" if v < 0 else "+") + f"{abs(int(v)):0{length - 1}d}")
            elif isinstance(v, (int, float)) and not isinstance(v, bool):
                parts.append(f"{int(v):0{length}d}"[-length:])
            else:
                parts.append(str(v).ljust(length)[:length])
        lines.append("".join(parts))
    return "\n".join(lines)


with st.sidebar:
    st.header("Submission")
    quarter = st.selectbox("Reporting quarter", list(QUARTERS))
    inject = st.toggle("Include common data errors", value=True,
                       help="Seeds the sample with the kinds of errors bureaus reject most often.")
    st.caption("Line of business: Personal Auto")

recs = build_records(quarter, inject)
errs = run_edits(recs, quarter)

bad_records = errs.record.nunique()
c1, c2, c3, c4 = st.columns(4)
c1.metric("Records", f"{len(recs):,}")
c2.metric("Pass rate", f"{(1 - bad_records / len(recs)):.1%}")
c3.metric("Records with errors", bad_records)
c4.metric("Fatal errors", int((errs.severity == "Fatal").sum()))

tab_err, tab_rec, tab_file, tab_rules = st.tabs(["Edit results", "Records", "Submission file", "Edit catalog"])

with tab_err:
    if errs.empty:
        st.success("No edit failures. This submission is ready to send.")
    else:
        by_edit = errs.groupby("edit").size().rename("errors")
        st.bar_chart(by_edit, color="#2B4CF2", height=220)
        sev = st.multiselect("Severity", ["Fatal", "Error", "Warning"], default=["Fatal", "Error", "Warning"])
        st.dataframe(errs[errs.severity.isin(sev)], hide_index=True, width="stretch")
        st.download_button("Download error report (CSV)", errs.to_csv(index=False),
                           f"si2_edit_report_{quarter.replace(' ', '_')}.csv", "text/csv")

with tab_rec:
    show = recs.drop(columns=["_state_abbr"])
    flagged = st.toggle("Only records with errors")
    if flagged:
        show = show[show.record.isin(errs.record)]
    st.dataframe(show, hide_index=True, width="stretch")

with tab_file:
    st.caption("Fixed-width submission file built from the records, one record per line.")
    text = fixed_width(recs)
    st.code("\n".join(text.splitlines()[:30]) + "\n…", language=None)
    st.download_button("Download submission file (.txt)", text, f"si2_stat_{quarter.replace(' ', '_')}.txt")
    pos, rows = 1, []
    for f, length, desc in LAYOUT:
        rows.append({"field": f, "start": pos, "end": pos + length - 1, "length": length, "description": desc})
        pos += length
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")

with tab_rules:
    st.dataframe(pd.DataFrame([{"edit": k, "severity": v[0], "check": v[1], "suggested fix": v[2]}
                               for k, v in EDITS.items()]), hide_index=True, width="stretch")

branding.note_synthetic()
branding.footer()
