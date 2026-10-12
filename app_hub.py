"""SI² Command Center: ROI calculator, bureau reporting calendar, and every SI² demo in one place."""
import datetime as dt

import numpy as np
import pandas as pd
import streamlit as st

from si2_common import branding, gate

branding.page("SI² Command Center",
              "What SI² is worth to a carrier, what is due to the bureaus and when, and every SI² demo in one place.")
gate.require_access()

TODAY = dt.date.today()
tab_roi, tab_cal, tab_demos = st.tabs(["💰 ROI calculator", "📅 Reporting calendar", "🧭 All demos"])


def add_months(d: dt.date, m: int) -> dt.date:
    y, mo = divmod(d.month - 1 + m, 12)
    return dt.date(d.year + y, mo + 1, 1)


def month_end(d: dt.date) -> dt.date:
    return add_months(d, 1) - dt.timedelta(days=1)


# ------------------------------------------------------------------------------------------ ROI
with tab_roi:
    st.caption("Enter a carrier's numbers (or keep the illustrative mid-size defaults). Every assumption about what SI² "
               "changes is on screen and editable; the results are estimates for a business case, not a guarantee.")
    a, b = st.columns(2)
    with a:
        st.markdown("**Today**")
        lines = st.number_input("Lines of business reported to bureaus", 1, 40, 6)
        states = st.number_input("States written", 1, 56, 18)
        records = st.number_input("Statistical records per year", 1_000, 50_000_000, 2_400_000, step=100_000)
        sme_rep = st.number_input("SME hours per month: preparing, validating, submitting bureau files", 0, 5000, 320)
        sme_map = st.number_input("SME hours per month: mappings, code tables, layout changes", 0, 5000, 140)
        sme_fix = st.number_input("SME hours per month: bureau errors and resubmissions", 0, 5000, 180)
        it_hrs = st.number_input("IT hours per month: extracts and fixes for reporting", 0, 5000, 120)
        rate = st.number_input("Loaded cost per hour ($)", 30, 400, 95)
        fta = st.slider("First-time acceptance rate today", 0.50, 0.99, 0.82, 0.01)
        fines = st.number_input("Bureau / regulator timeliness and quality fines last year ($)", 0, 5_000_000, 45_000, step=5_000)
        migr = st.number_input("One-time: data migration or new-bureau onboarding effort avoided (hours)", 0, 50_000, 1_200)
    with b:
        st.markdown("**What SI² changes** (editable assumptions)")
        r_rep = st.slider("Preparation and validation effort reduced by", 0.0, 0.9, 0.60, 0.05)
        r_map = st.slider("Mapping and code-table effort reduced by (Canonical Gaps, AI drafts)", 0.0, 0.9, 0.55, 0.05)
        fta_new = st.slider("First-time acceptance with SI² edits before submission", 0.50, 0.995, 0.95, 0.005)
        r_it = st.slider("IT effort reduced by", 0.0, 0.9, 0.40, 0.05)
        r_fines = st.slider("Fines avoided", 0.0, 1.0, 0.80, 0.05)
        cost = st.number_input("SI² annual subscription ($, illustrative)", 0, 5_000_000, 180_000, step=10_000)
        impl = st.number_input("One-time implementation ($)", 0, 5_000_000, 60_000, step=5_000)
    err_today, err_new = 1 - fta, 1 - fta_new
    r_fix = 1 - err_new / err_today if err_today > 0 else 0.0
    rows = [("Bureau file preparation & validation", sme_rep, r_rep), ("Mappings, code tables, layouts", sme_map, r_map),
            ("Errors & resubmissions", sme_fix, r_fix), ("IT extracts & fixes", it_hrs, r_it)]
    tbl = pd.DataFrame([{"activity": n, "hours / year today": h * 12, "hours / year with SI²": round(h * 12 * (1 - r)),
                         "hours saved": round(h * 12 * r), "$ saved": round(h * 12 * r * rate)} for n, h, r in rows])
    saved_hours = int(tbl["hours saved"].sum())
    saved_labor = float(tbl["$ saved"].sum())
    saved_fines = fines * r_fines
    one_time = migr * rate
    annual = saved_labor + saved_fines
    net1 = annual + one_time - cost - impl
    payback = (cost + impl) / max(annual / 12, 1)
    m = st.columns(5)
    m[0].metric("Hours saved a year", f"{saved_hours:,}", f"{saved_hours / 1800:.1f} FTE")
    m[1].metric("Annual savings", f"${annual:,.0f}")
    m[2].metric("First-time acceptance", f"{fta_new:.1%}", f"+{(fta_new - fta) * 100:.1f} pts")
    m[3].metric("Year-1 net (after SI² cost)", f"${net1:,.0f}")
    m[4].metric("Payback", f"{payback:.1f} months")
    st.dataframe(tbl, hide_index=True, width="stretch",
                 column_config={"$ saved": st.column_config.NumberColumn(format="$%,.0f")})
    chart = pd.DataFrame({"Today": [h * 12 for _, h, _ in rows], "With SI²": [h * 12 * (1 - r) for _, h, r in rows]},
                         index=[n for n, _, _ in rows])
    st.bar_chart(chart, horizontal=True, height=260, color=["#C8CDD3", "#2B4CF2"], stack=False)
    rej_today, rej_new = records * err_today, records * err_new
    st.caption(f"Records needing correction: about {rej_today:,.0f} a year today vs {rej_new:,.0f} with SI² "
               f"({lines} lines, {states} states). One-time effort avoided: ${one_time:,.0f}. "
               "Basis: SI² runs bureau-style edits before submission, drafts mappings and descriptions, and keeps every "
               "decision so it is made once.")
    summary = tbl.assign(rate=rate)
    st.download_button("Download the business case (CSV)", summary.to_csv(index=False), "SI2_business_case.csv", "text/csv")

# ------------------------------------------------------------------------------------------ calendar
with tab_cal:
    st.caption("Upcoming bureau submissions for a sample workers compensation and ISO book, with status. The WCSTAT rule "
               "follows the unit statistical plan; the other deadlines are editable defaults: confirm each one with the "
               "bureau or your data agreement.")
    with st.expander("Due-date rules (editable)", expanded=False):
        c1, c2, c3 = st.columns(3)
        pol_days = c1.number_input("Policy data (WCPOLS): days after inception / issuance", 1, 120, 60,
                                   help="WCIRB (California) requires 60 days; NCCI-state requirements may differ.")
        dc_lag = c2.number_input("Indemnity / medical data calls: months after quarter end", 1, 6, 3,
                                 help="Quarterly; due by the end of the following quarter (3 months).")
        iso_lag = c3.number_input("ISO statistical data: months after quarter end", 1, 6, 2)
        st.markdown(
            "- **WCSTAT unit statistical reports**: first report valued at month 18 after the policy effective date, due "
            "by the end of month 20; later reports every 12 months (valued 30, 42 … 126 months).\n"
            "- **WCPOLS policy data**: new and renewal policies within the set number of days of inception; endorsements "
            "and cancellations within the same number of days of issuance.\n"
            "- **WCIND / WCMED data calls**: quarterly.\n- **ISO statistical plans**: quarterly by line.")
    rng = np.random.default_rng(TODAY.toordinal() // 30)
    items = []
    for k in range(-2, 13):                                   # WCSTAT by policy effective month
        eff = add_months(TODAY.replace(day=1), k - 20)
        for n, (val_m, due_m) in enumerate([(18, 20), (30, 32), (42, 44)], 1):
            e2 = add_months(eff, -12 * (n - 1))
            items.append({"due": month_end(add_months(e2, due_m - 1)), "bureau": "NCCI", "report": f"WCSTAT report {n}",
                          "scope": f"policies effective {e2:%b %Y} (valued {add_months(e2, val_m):%b 1, %Y})",
                          "units": int(rng.integers(40, 260))})
    for k in range(-2, 13):
        mth = add_months(TODAY.replace(day=1), k - 2)
        items.append({"due": mth + dt.timedelta(days=int(pol_days)), "bureau": "NCCI", "report": "WCPOLS policy data",
                      "scope": f"new / renewal policies incepting {mth:%b %Y}", "units": int(rng.integers(150, 600))})
    q0 = (TODAY.month - 1) // 3
    for k in range(-2, 5):
        qy, qn = divmod(q0 + k, 4)
        q_end = month_end(dt.date(TODAY.year + qy, qn * 3 + 3, 1))
        for rep in ("WCIND indemnity data call", "WCMED medical data call"):
            items.append({"due": month_end(add_months(q_end, dc_lag)), "bureau": "NCCI", "report": rep,
                          "scope": f"payments Q{qn + 1} {TODAY.year + qy}", "units": int(rng.integers(300, 4000))})
        for lob in ("Personal Auto", "Homeowners", "Commercial Auto", "General Liability"):
            items.append({"due": month_end(add_months(q_end, iso_lag)), "bureau": "ISO", "report": f"{lob} statistical data",
                          "scope": f"premium and loss Q{qn + 1} {TODAY.year + qy}", "units": int(rng.integers(5000, 90000))})
    cal = pd.DataFrame(items).drop_duplicates(["due", "report", "scope"])
    cal = cal[(cal.due >= TODAY - dt.timedelta(days=75)) & (cal.due <= TODAY + dt.timedelta(days=365))].sort_values("due")
    days = (pd.to_datetime(cal.due) - pd.Timestamp(TODAY)).dt.days
    submitted = (days < 0) & (rng.random(len(cal)) < 0.93)
    cal["days left"] = days.values
    cal["status"] = np.select([submitted, days < 0, days <= 21, days <= 60], ["Submitted", "Overdue", "Due soon", "In progress"],
                              "Scheduled")
    k = st.columns(4)
    k[0].metric("Due in the next 30 days", int(((days >= 0) & (days <= 30)).sum()))
    k[1].metric("Overdue", int((cal.status == "Overdue").sum()))
    k[2].metric("Submitted (last 75 days)", int((cal.status == "Submitted").sum()))
    k[3].metric("Next 12 months", int((days >= 0).sum()))
    flt = st.multiselect("Bureau", ["NCCI", "ISO"], default=["NCCI", "ISO"], key="cal_b")
    show = cal[cal.bureau.isin(flt)]

    def colour(v):
        return {"Overdue": "color:#B42318;font-weight:600", "Due soon": "color:#B54708;font-weight:600",
                "Submitted": "color:#0A7A3D"}.get(v, "")
    st.dataframe(show.style.map(colour, subset=["status"]), hide_index=True, width="stretch", height=420,
                 column_config={"due": st.column_config.DateColumn("due", format="MMM D, YYYY")})
    st.markdown("**Data quality and timeliness trend** (sample book)")
    months = [add_months(TODAY.replace(day=1), -i) for i in range(11, -1, -1)]
    fta_s = np.clip(0.80 + np.cumsum(rng.normal(0.012, 0.01, 12)), 0, 0.995)
    trend = pd.DataFrame({"month": [f"{m:%b %y}" for m in months], "first-time acceptance": fta_s,
                          "on-time submissions": np.clip(0.86 + np.cumsum(rng.normal(0.01, 0.008, 12)), 0, 1)})
    st.line_chart(trend, x="month", y=["first-time acceptance", "on-time submissions"], height=260,
                  color=["#2B4CF2", "#0A7A3D"])
    st.download_button("Download the calendar (CSV)", show.to_csv(index=False), "SI2_bureau_calendar.csv", "text/csv")

# ------------------------------------------------------------------------------------------ demos
with tab_demos:
    st.caption("Walk-through order for a client meeting. Each demo has a two-minute guided tour at the top.")
    cols = st.columns(2)
    for i, (title, url, desc) in enumerate(branding.DEMOS):
        with cols[i % 2].container(border=True):
            st.markdown(f"**{i + 1}. [{title}]({url})**  \n{desc}")
            tour = branding.TOURS.get(title, [])
            if tour:
                st.caption("Tour: " + " → ".join(t.split("**")[1] if "**" in t else t[:40] for t in tour[:4]))

branding.note_synthetic()
branding.footer()
