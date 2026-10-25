"""SI² Financial Reporting: the NAIC Property & Casualty Annual Statement (Yellow Book).

Every Yellow Book field as data -> tables on SQLite or SQL Server -> connect the company's feeds -> generate the
statement -> cross-check edits -> Schedule P -> financial reporting ontology -> two-person approval and filing package.
"""
from __future__ import annotations

import datetime as dt
import io
import zipfile

import pandas as pd
import streamlit as st

from finance import blank as B
from finance import db as fdb
from finance import engine as E
from finance import ontology as O
from finance import source as S
from si2_common import ai, approvals_ui, branding, gate, identity, store

APP = "finance"
branding.page("Financial Reporting",
              "NAIC P&C Annual Statement (Yellow Book): every field, your feeds, the generated statement, edits, Schedule P and the ontology.")
gate.require_access()

STEPS = ["Overview", "1 · Yellow Book fields", "2 · Tables", "3 · Connect source", "4 · Generate statement",
         "5 · Validate (edits)", "6 · Schedule P", "7 · Ontology", "8 · Approve & file", "Audit trail"]
SOURCES = ["SI² synthetic company (generated)", "Database tables (fin.Src* or your own views)", "Upload CSV feeds"]


# ------------------------------------------------------------------------------------------ state
@st.cache_data(show_spinner=False)
def _fields():
    return B.fields(), B.pages(), B.summary()


@st.cache_data(show_spinner=False)
def _synthetic(late: float):
    return S.build(late_gl_entry=late)


@st.cache_data(show_spinner=False)
def _onto():
    return O.concepts(), O.relations(), O.field_concepts()


def log(event, detail=""):
    st.session_state.fin_audit.append({"time": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "by": actor or "SME",
                                       "event": event, "detail": detail})


def init():
    ss = st.session_state
    if "fin_ready" in ss:
        return
    ss.fin_audit, ss.fin_src, ss.fin_src_label, ss.fin_stmt, ss.fin_edits, ss.fin_run = [], None, "", None, None, None
    ss.fin_late = 0.0
    ss.fin_src, ss.fin_src_label = _synthetic(0.0), SOURCES[0]
    ss.fin_ready = True


def database():
    """The configured database (SQL Server on the desktop, SQLite online). Cached per session."""
    ss = st.session_state
    if ss.get("fin_db") is None:
        try:
            ss.fin_db, ss.fin_db_error = fdb.Db(), ""
        except Exception as exc:  # noqa: BLE001 - fall back to SQLite and say why
            ss.fin_db, ss.fin_db_error = fdb.Db("sqlite"), f"SQL Server not available ({exc}); using SQLite."
    return ss.fin_db


def money(v):
    return "" if v is None or isinstance(v, str) else f"{v:,.0f}"


def generate():
    ss = st.session_state
    ss.fin_stmt = E.generate(ss.fin_src)
    ss.fin_edits = E.edits(ss.fin_stmt)
    ss.fin_run = f"YB{B.YEAR}-{dt.datetime.now():%m%d%H%M%S}"
    log("Statement generated", f"{ss.fin_run}: {len(ss.fin_stmt.values):,} values, "
        f"{int((ss.fin_edits.result != 'PASS').sum())} edit(s) failing; source {ss.fin_src_label}")


def styled_page(df: pd.DataFrame) -> pd.DataFrame:
    """Numbers as the statement shows them (no decimals, thousands separators); blank cells stay blank."""
    out = df.copy()
    for c in out.columns:
        if c in ("Line", "Caption"):
            continue
        out[c] = [("" if v is None or (isinstance(v, float) and pd.isna(v)) else v if isinstance(v, str) else f"{v:,.0f}")
                  for v in out[c]]
    return out


init()
ss = st.session_state
F, PAGES, SUMMARY = _fields()

with st.sidebar:
    st.markdown("**Workflow**")
    step = st.radio("Step", STEPS, label_visibility="collapsed", key="step")
    st.divider()
    actor = identity.name_input("Preparer / approver name", "fin_actor", "Your name for approvals", default="Saba")
    st.caption(f"Source: {ss.fin_src_label}")
    if ss.fin_edits is not None:
        bad = int((ss.fin_edits.result != "PASS").sum())
        st.metric("Edits", "all pass" if bad == 0 else f"{bad} failing")

# ------------------------------------------------------------------------------------------ Overview
if step == "Overview":
    c = st.columns(5)
    c[0].metric("Pages and schedules", SUMMARY["pages"])
    c[1].metric("Lines", f"{SUMMARY['lines']:,}")
    c[2].metric("Fields (cells)", f"{SUMMARY['fields']:,}")
    c[3].metric("Annual statement lines", SUMMARY["asl_lines"])
    c[4].metric("Schedule P lines", SUMMARY["sched_p_lines"])
    st.subheader("How it works")
    st.graphviz_chart("""
digraph G { rankdir=LR; bgcolor="transparent";
 node [shape=box, style="rounded,filled", fillcolor="#FFFFFF", color="#0B1B2B", fontname="Helvetica", fontsize=10];
 edge [color="#2B4CF2"];
 yb [label="NAIC P&C Annual Statement\\n(Yellow Book)\\npages · lines · columns"];
 cat [label="Field catalog\\n17,000+ cells\\nfin.YbField"];
 src [label="Company feeds\\npremium · claims · reserves\\nIBNR · GL · expenses\\ninvestments · reinsurers"];
 onto [label="Financial reporting\\nontology", fillcolor="#E7ECFE"];
 gen [label="Generate statement\\nPages 2-5 · UIE · state page\\nSchedule F · Schedule P · 5-year"];
 ed [label="Cross-check edits\\npage ties · crossfoots\\nreconciliations"];
 ok [label="Two-person approval\\nfiling package", fillcolor="#E7ECFE"];
 yb -> cat -> gen; src -> gen -> ed -> ok; cat -> onto; onto -> gen [style=dashed, label=" meaning"]; }""", width="stretch")
    st.markdown(
        "**What it does.** SI² holds the statutory annual statement blank as data: every page, line and column, and every "
        "cell as a field with its own id (for example `P4.L1.C1` = Page 4, line 1 *Premiums earned*, current year). It "
        "creates the tables on SQL Server (schema `fin` in SI2Canonical) or SQLite, connects the company's feeds, generates "
        "the statement, runs the cross-checks the NAIC and the states run, and builds the financial reporting ontology "
        "that says what every number means and how it is derived.\n\n"
        "**Sources.** The captions of the Assets, Liabilities, Income and Cash Flow pages and the Underwriting and "
        "Investment Exhibit (Parts 1, 1A, 1B, 2, 2A, 3) and the Exhibit of Net Investment Income were read from the NAIC "
        "2026 P&C Annual Statement Blank. Schedule P, the state page, Schedule F Part 3 and Five-Year Historical Data "
        "follow SI²'s outline of the blank and are marked *SI² outline – verify* until checked line by line against the "
        "blank for the filing year. The company and every amount are synthetic.")
    st.dataframe(PAGES.groupby(["page_group", "source"], as_index=False).agg(pages=("page_code", "count"),
                                                                          fields=("field_count", "sum")),
                 hide_index=True, width="stretch")

# ------------------------------------------------------------------------------------------ 1. Fields
elif step == STEPS[1]:
    st.subheader("Yellow Book fields")
    c = st.columns(4)
    c[0].metric("Fields", f"{SUMMARY['fields']:,}")
    c[1].metric("Read from the NAIC 2026 blank", f"{SUMMARY['verified_fields']:,}")
    c[2].metric("SI² outline – verify", f"{SUMMARY['fields'] - SUMMARY['verified_fields']:,}")
    c[3].metric("Pages", SUMMARY["pages"])
    t1, t2, t3 = st.tabs(["Pages", "Fields of a page", "Search all fields"])
    with t1:
        st.dataframe(PAGES, hide_index=True, width="stretch", height=420)
    with t2:
        labels = [f"{r.page_code} · {r.page_name}" for r in PAGES.itertuples()]
        pick = st.selectbox("Page", labels, key="fld_page")
        code = pick.split(" · ")[0]
        ln = B.lines().query("page_code == @code")
        co = B.columns().query("page_code == @code")
        a, b = st.columns([3, 2])
        a.markdown("**Lines**")
        a.dataframe(ln[["line_no", "caption", "line_kind"]], hide_index=True, width="stretch", height=360)
        b.markdown("**Columns**")
        b.dataframe(co[["col_no", "caption"]], hide_index=True, width="stretch", height=360)
        st.caption("Line kind: D = value, T = total computed from other lines, H = heading (no value).")
    with t3:
        q = st.text_input("Search captions", "unearned", key="fld_q")
        hit = F[F.line_caption.str.contains(q, case=False, na=False) | F.col_caption.str.contains(q, case=False, na=False)] if q else F
        st.caption(f"{len(hit):,} fields")
        st.dataframe(hit[["field_id", "page_name", "line_no", "line_caption", "col_no", "col_caption", "data_type", "source"]].head(2000),
                     hide_index=True, width="stretch", height=420)
    st.download_button("Download every field (CSV)", F.to_csv(index=False), "SI2_YellowBook_fields.csv", "text/csv")

# ------------------------------------------------------------------------------------------ 2. Tables
elif step == STEPS[2]:
    st.subheader("Tables")
    d = database()
    if ss.get("fin_db_error"):
        st.warning(ss.fin_db_error)
    st.info(f"Database: **{d.describe()}**. On SI² Studio with SI2_SQL_SERVER set, the tables go into schema `fin` of SI2Canonical.")
    t1, t2, t3 = st.tabs(["Create and load", "SQL Server script", "SQLite script"])
    with t1:
        st.markdown("Creates the Yellow Book tables (pages, lines, columns, fields, annual statement lines), the ontology "
                    "tables, the source-feed tables and the statement tables, then loads the Yellow Book and the ontology.")
        if st.button("Create tables and load the Yellow Book + ontology", type="primary"):
            with st.spinner("Creating and loading ..."):
                try:
                    d.create()
                    concepts, relations, fcon = _onto()
                    n = fdb.load_catalog(d, concepts, relations, fcon)
                    log("Tables created and Yellow Book loaded", ", ".join(f"{k} {v:,}" for k, v in n.items()))
                    st.success("Loaded: " + " · ".join(f"{d.t(k)} {v:,}" for k, v in n.items()))
                except Exception as exc:  # noqa: BLE001
                    st.error(f"Could not create the tables: {exc}")
        try:
            st.dataframe(d.counts(), hide_index=True, width="stretch")
        except Exception as exc:  # noqa: BLE001
            st.caption(f"Table counts unavailable: {exc}")
    with t2:
        sql = fdb.ddl("mssql")
        st.download_button("Download 01_create_fin.sql", sql, "01_create_fin.sql", "text/plain")
        st.caption("The Yellow Book seed (02_seed_yellowbook.sql) is in finance/sql; or run `python -m finance.install`.")
        st.code(sql, language="sql")
    with t3:
        st.code(fdb.ddl("sqlite"), language="sql")

# ------------------------------------------------------------------------------------------ 3. Connect
elif step == STEPS[3]:
    st.subheader("Connect source")
    mode = st.radio("Source", SOURCES, horizontal=True, key="fin_mode")
    if mode == SOURCES[0]:
        late = st.checkbox("Simulate a late manual GL entry: $1,250,000 homeowners premium booked in the GL but not in the policy system",
                           value=ss.fin_late > 0, key="fin_late_cb")
        if st.button("Use the synthetic company", type="primary"):
            ss.fin_late = 1_250_000.0 if late else 0.0
            ss.fin_src, ss.fin_src_label = _synthetic(ss.fin_late), SOURCES[0] + (" + late GL entry" if late else "")
            ss.fin_stmt = ss.fin_edits = None
            log("Source connected", ss.fin_src_label)
            st.success("Connected. Go to step 4 to generate the statement.")
        if st.button("Copy the synthetic feeds into the database tables (fin.Src*)"):
            d = database()
            try:
                d.create()
                n = fdb.load_source(d, ss.fin_src)
                log("Synthetic feeds loaded to database", ", ".join(f"{k} {v:,}" for k, v in n.items()))
                st.success(f"Loaded into {d.describe()}: " + " · ".join(f"{k} {v:,}" for k, v in n.items()))
            except Exception as exc:  # noqa: BLE001
                st.error(str(exc))
    elif mode == SOURCES[1]:
        d = database()
        st.caption(f"Reads the nine feeds from {d.describe()}. Point them at your warehouse by creating views with the same "
                   "names and columns (fin.SrcPremiumTxn, fin.SrcClaimTxn …).")
        if st.button("Connect to the database", type="primary"):
            try:
                ss.fin_src = fdb.read_source(d, _synthetic(0.0))
                ss.fin_src_label = f"Database: {d.describe()}"
                ss.fin_stmt = ss.fin_edits = None
                log("Source connected", ss.fin_src_label)
                st.success("Connected.")
            except Exception as exc:  # noqa: BLE001
                st.error(f"{exc}. Use step 2 to create the tables, then load the synthetic feeds or your own.")
    else:
        st.caption("Upload one CSV per feed with the column names shown below (download the templates). Feeds you do not "
                   "upload keep the synthetic data.")
        ups = st.file_uploader("Feed CSV files (named after the feed, e.g. premium_txn.csv)", type="csv",
                               accept_multiple_files=True, key="fin_up")
        if ups and st.button("Use uploaded feeds", type="primary"):
            src = dict(_synthetic(0.0))
            used = []
            for f in ups:
                key = f.name.rsplit(".", 1)[0].lower()
                if key in S.FEEDS:
                    df = pd.read_csv(f)
                    for c in ("eff_date", "exp_date"):
                        if c in df:
                            df[c] = pd.to_datetime(df[c]).dt.date
                    src[key] = df
                    used.append(key)
            ss.fin_src, ss.fin_src_label = src, f"Uploaded: {', '.join(used) or 'none'}"
            ss.fin_stmt = ss.fin_edits = None
            log("Source connected", ss.fin_src_label)
            st.success(f"Using uploaded feeds: {', '.join(used) or 'none recognised'}.")
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for k in S.FEEDS:
                z.writestr(f"{k}.csv", ss.fin_src[k].head(200).to_csv(index=False))
        st.download_button("Download feed templates with sample rows (ZIP)", buf.getvalue(), "SI2_finance_feed_templates.zip")
    st.markdown("**Connected feeds**")
    st.dataframe(pd.DataFrame([{"feed": k, "table": fdb.tname(fdb.FEED_TABLE[k], "mssql"), "rows": len(ss.fin_src[k]),
                                "columns": ", ".join(ss.fin_src[k].columns)} for k in S.FEEDS]), hide_index=True, width="stretch")
    feed = st.selectbox("Preview", S.FEEDS, key="fin_prev")
    st.dataframe(ss.fin_src[feed].head(200), hide_index=True, width="stretch", height=280)
    with st.expander("How each feed reaches the Yellow Book"):
        st.dataframe(pd.DataFrame([
            ("premium_txn", "policy_id, state, asl_code, basis, written, eff/exp dates", "WRITTEN_PREMIUM, STATE, LINE_OF_BUSINESS", "Part 1A, Part 1 (unearned), state page"),
            ("gl_premium", "asl_code, basis, affiliate, written", "WRITTEN_PREMIUM, CEDED_PREMIUM", "Part 1B, Schedule F"),
            ("claim_txn", "pay_type LOSS / DCC / AO / SALVAGE, accident and calendar year", "PAID_LOSS, PAID_ALAE, RECOVERY_AMOUNT", "Part 2, Part 3, state page, Schedule P"),
            ("claim_reserve", "case_loss, case_dcc by valuation year", "OUTSTANDING_RESERVE, ALAE_RESERVE", "Part 2A, Page 3, Schedule P"),
            ("ibnr", "bulk + IBNR loss and DCC, A&O unpaid", "IBNR_RESERVE (proposed), ULAE_RESERVE (proposed)", "Part 2A, Page 3, Schedule P"),
            ("expense_ledger", "Part 3 line, amount, LAE / UW / investment split", "COMMISSION_AMOUNT (proposed)", "Part 3, Page 4"),
            ("gl_balance", "account, statement line, current / prior, nonadmitted", "ACCOUNT_BALANCE", "Pages 2 and 3"),
            ("investment", "exhibit line, collected, earned", "INVESTMENT_INCOME (proposed)", "Exhibit of Net Investment Income, Page 4"),
            ("reinsurer", "reinsurer id, NAIC code, domicile, share", "REINSURER_NAME, TREATY_ID", "Schedule F Part 3"),
        ], columns=["feed", "key columns", "SI2Canonical element", "Yellow Book pages"]), hide_index=True, width="stretch")

# ------------------------------------------------------------------------------------------ 4. Generate
elif step == STEPS[4]:
    st.subheader("Generate statement")
    if st.button("Generate the annual statement", type="primary"):
        with st.spinner("Generating every page ..."):
            generate()
    stmt = ss.fin_stmt
    if stmt is None:
        st.info("Press *Generate the annual statement*.")
    else:
        bad = int((ss.fin_edits.result != "PASS").sum())
        c = st.columns(5)
        c[0].metric("Values", f"{len(stmt.values):,}")
        c[1].metric("Premiums earned", money(stmt.get("P4", "1", "1")))
        c[2].metric("Net income", money(stmt.get("P4", "20", "1")))
        c[3].metric("Policyholder surplus", money(stmt.get("P3", "37", "1")))
        c[4].metric("Edits", "all pass" if bad == 0 else f"{bad} failing")
        main = [p for p in PAGES.itertuples() if not p.page_code.startswith(("SP1", "SP2", "SP3"))]
        pick = st.selectbox("Page", [f"{p.page_code} · {p.page_name}" for p in main], key="gen_page")
        code = pick.split(" · ")[0]
        dim = ""
        if code == "SP":
            states = sorted({d for (f, d) in stmt.values if f.startswith("SP.") and d})
            dim = st.selectbox("State", ["Total"] + [s for s in states if s != "Total"], key="gen_state")
        elif code == "SF3":
            dim = st.selectbox("Reinsurer", sorted({d for (f, d) in stmt.values if f.startswith("SF3.") and d}), key="gen_rein")
        view = E.page_view(stmt, code, dim)
        if code == "SF3" and dim:
            tot = E.page_view(stmt, code, "")
            view = pd.concat([view.iloc[:1], tot.iloc[1:]])
        st.dataframe(styled_page(view), hide_index=True, width="stretch", height=520)
        with st.expander("Where did a number come from? (lineage and meaning)"):
            fc = _onto()[2].set_index("field_id")
            lines_ = B.lines().query("page_code == @code and line_kind != 'H'")
            cols_ = B.columns().query("page_code == @code")
            a, b = st.columns(2)
            ln = a.selectbox("Line", [f"{r.line_no} · {r.caption}" for r in lines_.itertuples()], key="lin_l").split(" · ")[0]
            co = b.selectbox("Column", [f"{r.col_no} · {r.caption}" for r in cols_.itertuples()], key="lin_c").split(" · ")[0]
            fid = B.field_id(code, ln, co)
            v = stmt.values.get((fid, dim))
            st.markdown(f"**{fid}** = {money(v) if v is not None else 'blank'}  \n"
                        f"Lineage: {stmt.lineage.get(fid, 'not produced in this run')}  \n"
                        f"Meaning: `{fc.at[fid, 'concept_id'] if fid in fc.index else ''}` · {fc.at[fid, 'dimensions'] if fid in fc.index else ''}")
        frame = stmt.frame()
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as xw:
            for p in ["P2", "P3", "P4", "P5", "U1", "U1A", "U1B", "U2", "U2A", "U3", "NII", "H5", "SP1SUM"]:
                E.page_view(stmt, p, "").to_excel(xw, sheet_name=p, index=False)
            E.page_view(stmt, "SP", "Total").to_excel(xw, sheet_name="SP_all_states", index=False)
            ss.fin_edits.to_excel(xw, sheet_name="Edits", index=False)
        c1, c2 = st.columns(2)
        c1.download_button("Download the statement (Excel, main pages)", buf.getvalue(), f"SI2_YellowBook_{B.YEAR}.xlsx")
        c2.download_button("Download every value with lineage (CSV)", frame.to_csv(index=False), f"SI2_YellowBook_{B.YEAR}_values.csv", "text/csv")
        for n in stmt.notes:
            st.caption(n)

# ------------------------------------------------------------------------------------------ 5. Edits
elif step == STEPS[5]:
    st.subheader("Validate (cross-check edits)")
    if ss.fin_edits is None:
        st.info("Generate the statement first (step 4).")
    else:
        e = ss.fin_edits
        bad = e[e.result != "PASS"]
        c = st.columns(3)
        c[0].metric("Edits run", len(e))
        c[1].metric("Pass", int((e.result == "PASS").sum()))
        c[2].metric("Fail", len(bad))

        show = e.assign(result=e.result.map({"PASS": "✅ PASS", "FAIL": "❌ FAIL"}).fillna(e.result))
        for c in ("expected", "actual", "difference"):
            show[c] = show[c].map(lambda v: f"{v:,.0f}")
        st.dataframe(show, hide_index=True, width="stretch", height=560)
        if len(bad):
            st.error("Failing edits must be fixed at the source before the statement can be approved.")
            if {"E20", "E21"} & set(bad.edit_id):
                st.markdown("SI² traced **E20 / E21**: Part 1B direct premium comes from the general ledger, the state page from "
                            "the policy system. The difference is the manual GL entry on homeowners that the policy system does "
                            "not have. Book it in the policy system (or reverse it in the GL) and regenerate.")
        facts = {"edits": e.to_dict("records"), "company": S.COMPANY["name"], "year": B.YEAR}
        st.markdown("**🤖 Ask SI²**")
        st.caption(ai.status())
        q = st.text_input("Question about the edits", "Explain any failing edit and how to fix it", key="fin_q")
        if st.button("Ask", key="fin_ask"):
            with st.spinner("SI² is reading ..."):
                ss.fin_ans = ai.answer(q, facts)
        if ss.get("fin_ans"):
            st.info(ss.fin_ans[0])
            st.caption(f"Answered by {ss.fin_ans[1]} · a suggestion for the preparer, not a decision.")

# ------------------------------------------------------------------------------------------ 6. Schedule P
elif step == STEPS[6]:
    st.subheader("Schedule P")
    if ss.fin_stmt is None:
        st.info("Generate the statement first (step 4).")
    else:
        stmt = ss.fin_stmt
        have = [("SUM", "Summary")] + [(c, n) for c, n in B.SCHED_P_LINES if any(k.startswith(f"SP1{c}.") for k, _ in stmt.values)]
        pick = st.selectbox("Schedule P line", [f"{c} · {n}" for c, n in have], key="sp_line")
        code = pick.split(" · ")[0]
        t1, t2, t3 = st.tabs(["Part 1 · Summary by accident year", "Part 2 · Incurred net losses and DCC", "Part 3 · Paid net losses and DCC"])
        with t1:
            st.dataframe(styled_page(E.page_view(stmt, f"SP1{code}")), hide_index=True, width="stretch", height=460)
        for tab, part in ((t2, "SP2"), (t3, "SP3")):
            with tab:
                v = E.page_view(stmt, f"{part}{code}")
                st.dataframe(styled_page(v), hide_index=True, width="stretch", height=430)
                tri = v.set_index("Line").iloc[1:, 1:11].apply(pd.to_numeric, errors="coerce")
                tri.columns = [str(i) for i in range(1, 11)]
                ata = pd.DataFrame({f"{i}-{i + 1}": [(tri[str(i + 1)] / tri[str(i)]).replace([float("inf")], pd.NA).dropna().mean()]
                                    for i in range(1, 10)}, index=["average age-to-age factor"])
                st.markdown("**Development factors** (simple average, for the actuary's review)")
                st.dataframe(ata.round(3), width="stretch")

# ------------------------------------------------------------------------------------------ 7. Ontology
elif step == STEPS[7]:
    st.subheader("Financial reporting ontology")
    concepts, relations, fcon = _onto()
    c = st.columns(5)
    c[0].metric("Concepts", int(concepts.kind.isin(["class", "measure"]).sum()))
    c[1].metric("Dimensions", int((concepts.kind == "dimension").sum()))
    c[2].metric("Members", int((concepts.kind == "member").sum()))
    c[3].metric("Relations", len(relations))
    c[4].metric("Fields with a meaning", f"{(fcon.concept_id != 'FinancialConcept').mean():.0%}",
                help=f"{int((fcon.concept_id != 'FinancialConcept').sum()):,} of {len(fcon):,} Yellow Book fields")
    st.caption("Kept as plain tables (fin.OntConcept, fin.OntRelation, fin.YbField.concept_id) so it sits next to the "
               "canonical model and engineers can query it with SQL; exported as OWL / RDFS / SKOS Turtle and JSON-LD for "
               "knowledge-graph tools.")
    t1, t2, t3, t4 = st.tabs(["Concept browser", "Fields → concepts", "Canonical gaps", "Download"])
    with t1:
        meas = concepts[concepts.kind.isin(["class", "measure", "dimension"])]
        pick = st.selectbox("Concept", [f"{r.concept_id} · {r.label}" for r in meas.itertuples()],
                            index=int((meas.concept_id == "EarnedPremium").values.argmax()), key="onto_pick")
        cid = pick.split(" · ")[0]
        r = concepts.set_index("concept_id").loc[cid]
        a, b = st.columns([2, 3])
        with a:
            st.markdown(f"**{r.label}** ({r.kind})  \n{r.definition}  \nParent: `{r.parent_id}`  \n"
                        f"SI2Canonical: `{r.canonical_element or '—'}` {('· ' + r.canonical_status) if r.canonical_status else ''}")
            f = relations[(relations.subject_id == cid) & (relations.predicate == "derivedFrom")]
            if len(f):
                st.markdown("**Formula**  \n" + f.note.iloc[0])
            n = int((fcon.concept_id == cid).sum())
            st.markdown(f"**Measured by {n:,} Yellow Book fields**")
            st.dataframe(fcon[fcon.concept_id == cid].merge(F[["field_id", "page_name", "line_caption", "col_caption"]], on="field_id")
                         .head(300), hide_index=True, width="stretch", height=260)
        with b:
            st.graphviz_chart(O.neighbourhood_dot(cid), width="stretch")
            st.caption("Blue: derived from · green: reported on · orange: checked by · purple: rolls up to · red: SI2Canonical element")
    with t2:
        pg = st.selectbox("Page", [f"{p.page_code} · {p.page_name}" for p in PAGES.itertuples()], key="onto_pg").split(" · ")[0]
        st.dataframe(fcon.merge(F[["field_id", "page_code", "line_caption", "col_caption"]], on="field_id").query("page_code == @pg"),
                     hide_index=True, width="stretch", height=460)
    with t3:
        gaps = O.canonical_gaps()
        st.markdown(f"**{len(gaps)} financial concepts need an element SI2Canonical does not have yet.** Propose them in the "
                    "Canonical Master (two-person approval); existing elements are reused, never duplicated.")
        st.dataframe(gaps, hide_index=True, width="stretch")
        st.download_button("Download proposals for the Canonical Master (CSV)", gaps.to_csv(index=False),
                           "SI2_finance_canonical_proposals.csv", "text/csv")
    with t4:
        st.download_button("Ontology: concepts and relations (Turtle)", O.turtle(False), "si2_finrep_ontology.ttl", "text/turtle")
        if st.button("Prepare Turtle with every field (about 4 MB)"):
            ss.fin_ttl_full = O.turtle(True)
        if ss.get("fin_ttl_full"):
            st.download_button("Ontology + 17,000 fields (Turtle)", ss.fin_ttl_full, "si2_finrep_ontology_fields.ttl", "text/turtle")
        st.download_button("Ontology (JSON-LD)", O.jsonld(), "si2_finrep_ontology.jsonld", "application/ld+json")
        st.download_button("Concepts (CSV)", concepts.to_csv(index=False), "si2_finrep_concepts.csv", "text/csv")
        st.download_button("Relations (CSV)", relations.to_csv(index=False), "si2_finrep_relations.csv", "text/csv")
        st.download_button("Field meanings (CSV)", fcon.to_csv(index=False), "si2_finrep_field_concepts.csv", "text/csv")

# ------------------------------------------------------------------------------------------ 8. Approve
elif step == STEPS[8]:
    st.subheader("Approve & file")
    if ss.fin_stmt is None:
        st.info("Generate the statement first (step 4).")
    else:
        e = ss.fin_edits
        bad = int((e.result != "PASS").sum())
        st.write(("✅ " if bad == 0 else "❌ ") + f"Edits: {len(e) - bad} of {len(e)} pass")
        st.write(f"Run **{ss.fin_run}** · source {ss.fin_src_label} · prepared by **{actor or '—'}**")
        if st.button("Save the run to the database and submit for approval", type="primary", disabled=bad > 0):
            try:
                d = database()
                d.create()
                n = fdb.save_run(d, ss.fin_run, ss.fin_stmt, e, {"company": S.COMPANY["name"], "statement_year": B.YEAR,
                                                                  "source": ss.fin_src_label[:60], "created_by": actor or "SME",
                                                                  "created_at": dt.datetime.now().isoformat(timespec="seconds"),
                                                                  "status": "Pending approval"})
                rid = store.request(APP, "Annual statement", ss.fin_run,
                                    f"{B.YEAR} annual statement {ss.fin_run}: surplus {money(ss.fin_stmt.get('P3', '37', '1'))}, "
                                    f"net income {money(ss.fin_stmt.get('P4', '20', '1'))}", {"run_id": ss.fin_run}, actor)
                log("Submitted for approval", f"{ss.fin_run} saved ({n:,} values) to {d.describe()}; request #{rid}")
                st.success(f"Saved {n:,} values to {d.describe()} and submitted request #{rid}. A different person approves it below.")
            except Exception as exc:  # noqa: BLE001
                st.error(str(exc))
        if bad:
            st.caption("Fix the failing edits first (step 5).")

        def decided(req):
            run = req["payload"]["run_id"]
            try:
                fdb.set_status(database(), run, req["status"], req["checker"])
            except Exception:  # noqa: BLE001 - the approval itself is recorded in the SI² store
                pass
            log(f"Statement {req['status'].lower()}", f"{run} by {req['checker']}: {req.get('note', '')}")
            return f"{run} {req['status'].lower()} by {req['checker']}."
        st.markdown("**Approvals**")
        approvals_ui.render(APP, actor, decided, note_label="Approval note", key="fin_appr")
        approved = [r for r in store.approvals(APP, "Approved") if r["payload"] and r["payload"].get("run_id") == ss.fin_run]
        if approved:
            stmt = ss.fin_stmt
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
                z.writestr("statement_values.csv", stmt.frame().to_csv(index=False))
                z.writestr("edits.csv", e.to_csv(index=False))
                z.writestr("ontology_field_meanings.csv", _onto()[2].to_csv(index=False))
                z.writestr("approval.txt", f"Run {ss.fin_run}\nApproved by {approved[0]['checker']} at {approved[0]['checked_at']}\n"
                                           f"Prepared by {approved[0]['maker']}\nNote: {approved[0].get('note', '')}\n")
            st.success(f"Approved by {approved[0]['checker']}. The filing package is ready for your annual statement filing software.")
            st.download_button("Download the filing package (ZIP)", buf.getvalue(), f"SI2_YellowBook_{B.YEAR}_{ss.fin_run}.zip")

# ------------------------------------------------------------------------------------------ audit
elif step == "Audit trail":
    st.subheader("Audit trail")
    a = pd.DataFrame(ss.fin_audit)
    if a.empty:
        st.caption("Nothing yet.")
    else:
        st.dataframe(a.iloc[::-1], hide_index=True, width="stretch")
        st.download_button("Download audit trail (CSV)", a.to_csv(index=False), "SI2_finance_audit.csv", "text/csv")

branding.note_synthetic()
branding.footer()
