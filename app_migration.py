"""SI² Legacy-to-Cloud Migration Workbench.

Legacy sources (COBOL copybooks + data, DB tables, code tables, PDF forms, notes, COBOL programs)
-> discovery inventory -> canonical model (fields, synonyms, pick lists) -> Source → Canonical → Destination
mapping with SME queue -> pick-list value maps -> transform -> inject into the cloud database
-> legacy vs cloud tests (counts, control totals, integrity, sample records, COBOL business rule) -> SME approval.
"""
import datetime as dt
import io
import sqlite3
import tempfile
import uuid
import zipfile
from pathlib import Path

import pandas as pd
import streamlit as st

from migrate import engine as E
from migrate import gaps as MG
from migrate import initial_load as IL
from si2_common import registry as R
from migrate import legacy
from si2_common import identity, ai, ai_ui, approvals_ui, branding, gate, gaps_ui, persist, store

branding.page("Legacy-to-Cloud Migration Workbench",
              "Discover every legacy data element, build the canonical model, map, migrate, test and approve.")
gate.require_access()

STEPS = ["Overview", "0 · Initial load", "1 · Legacy sources", "2 · Destination", "3 · Discovery inventory",
         "4 · Canonical model & synonyms", "5 · Source → Canonical → Destination", "6 · Pick-list values",
         "7 · Transform & inject", "8 · Test legacy vs cloud", "9 · SME approval", "Audit trail"]
CHOICE_NONE = ""


# ------------------------------------------------------------------------------------------ state
@st.cache_data(show_spinner=False)
def _demo():
    return legacy.load_samples()


def log(who, event, detail=""):
    st.session_state.audit.append({"time": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "by": who,
                                   "event": event, "detail": detail})


def sme():
    return st.session_state.get("sme_name") or "SME"


def set_source(src, label):
    ss = st.session_state
    ss.src, ss.src_label = src, label
    ss.syn_edits, ss.map_ov, ss.rejected, ss.val_ov = {}, {}, set(), {}
    ss.loaded, ss.tests_signed, ss.approved = None, {}, None
    ss.inv = E.discover(src)
    recompute()
    log("SI²", "Legacy sources connected", f"{label}: {len(src['entities'])} entities, {len(ss.inv)} elements")


def recompute():
    """Canonical model -> matching -> value maps, applying every SME decision so far."""
    ss = st.session_state
    canon = E.build_canonical(ss.src["dest_schema"], ss.src["dest_picklists"])
    pub = R.published()                       # company synonyms approved in the company model
    if pub:
        idx = R._synonym_index()
        for i, cid in canon.canonical_id.items():
            t = R.concept_of(cid.split(".")[-1], idx)
            extra = [x for x in pub.get(t, {}).get("synonyms", []) if x not in canon.at[i, "synonyms"]]
            if extra:
                canon.at[i, "synonyms"] += ", " + ", ".join(extra)
    for cid, syn in ss.syn_edits.items():
        canon.loc[canon.canonical_id == cid, "synonyms"] = syn
    m = E.match(ss.inv, canon, ss.map_ov)
    rej = m.element_id.isin(ss.rejected) & ~m.element_id.isin(ss.map_ov)
    m.loc[rej, ["canonical_id", "status", "method", "destination_fields"]] = ["", "Needs SME review", "SME rejected", ""]
    vm = E.value_maps(ss.inv, m, canon, ss.src["dest_picklists"], ss.val_ov)
    ss.canon, ss.m, ss.vm = canon, m, vm
    ss.cov = E.coverage(m, canon, vm)


APP = "migration"
KEYS = ["src", "src_label", "syn_edits", "map_ov", "rejected", "val_ov", "audit", "il", "approved"]
# the injected cloud database (and the tests run on it) is rebuilt in Step 7 after a restart
IL_DIR = Path(__file__).resolve().parent / "data" / "initial_load"
IL_DIR.mkdir(parents=True, exist_ok=True)


def init():
    if "ready" in st.session_state:
        return
    if persist.restore(APP, KEYS) and "src" in st.session_state:
        for ent in st.session_state.src["entities"]:
            E.CONTEXT.setdefault(ent, context_for(ent))
        st.session_state.inv = E.discover(st.session_state.src)
        for k, v in (("syn_edits", {}), ("map_ov", {}), ("rejected", set()), ("val_ov", {}), ("audit", []),
                     ("approved", None)):
            st.session_state.setdefault(k, v)
        st.session_state.loaded, st.session_state.tests_signed = None, {}
        recompute()
        st.session_state.ready = True
        return
    st.session_state.audit = []
    set_source(_demo(), "SI² demo legacy system INSURE/400")
    st.session_state.ready = True


def context_for(entity: str) -> str:
    """Destination context of an initial-load table, by its name."""
    w = set(entity.upper().replace("-", "_").split("_"))
    for words_, ctx in ((("PAYMENT", "PMT"), "ClaimPayment"), (("CLAIM",), "Claim"), (("AGENT", "PRODUCER", "AGENCY"), "Producer"),
                        (("COVERAGE", "COV"), "Coverage"), (("DRIVER", "PARTY", "INSURED"), "Party"), (("POLICY", "POL"), "Policy")):
        if w & set(words_):
            return ctx
    return "Policy"


@st.cache_data(show_spinner=False)
def il_sample_zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(IL.SAMPLES.rglob("*")):
            if p.is_file():
                z.write(p, p.relative_to(IL.SAMPLES))
    return buf.getvalue()


def load_plan_digest(il: dict) -> str:
    ok = il["props"][il["props"].status == "Approved"]
    plan = [(r.kind, r.table, list(r.columns), r.ref_table, list(r.ref_columns), r.method) for r in ok.itertuples()]
    types = il["prof"][["table", "column", "type"]].values.tolist()
    return store.digest(store.dumps([plan, types, sorted(il["accepted_edits"])]))


def decide_request(req: dict) -> str:
    ss = st.session_state
    if req["kind"] == "Initial load plan":
        if req["status"] == "Approved":
            ss.il["approved_plan"], ss.il["plan_checker"] = req["payload"]["plan"], req["checker"]
            log(req["checker"], "Initial load plan approved", req["summary"])
            return f"Load plan approved by {req['checker']}. Create tables and load is now enabled."
        log(req["checker"], "Initial load plan rejected", req.get("note", ""))
        return f"Load plan rejected by {req['checker']}."
    if req["kind"] == "Migration sign-off":
        if req["status"] == "Approved":
            ss.approved = {"by": req["checker"], "at": req["checked_at"], "comment": req.get("note", ""),
                           "requested_by": req["maker"]}
            log(req["checker"], "Migration approved (second signature)", req.get("note", ""))
            return f"Migration signed off by {req['maker']} and approved by {req['checker']}."
        log(req["checker"], "Migration sign-off rejected", req.get("note", ""))
        return f"Sign-off rejected by {req['checker']}."
    return ""


def show_load_result(r: dict, steward: bool):
    rec = r["recon"]
    k = st.columns(4)
    k[0].metric("Rows loaded" if r["mode"] == "Initial" else "New + changed rows", f"{int(rec.loaded.sum()):,}")
    k[1].metric("Quarantined", len(r["quarantine"]))
    k[2].metric("Foreign-key violations", r["fk_violations"])
    k[3].metric("Reconciliation", "PASS" if (rec["rows balance"] == "PASS").all()
                and (rec["totals balance"] != "FAIL").all() else "FAIL")
    st.caption(f"{r['mode']} batch {r['batch']} · as of {r['as_of']} · by {r['by']} · load order (parents first): "
               f"{' → '.join(r['order'])}" + (f" · circular references: {', '.join(r['cycles'])}" if r["cycles"] else ""))
    st.dataframe(styled(rec, ["rows balance", "totals balance"]), hide_index=True, width="stretch")
    if len(r["quarantine"]):
        st.markdown("**Quarantined rows** (not loaded; personal data in them is always masked)")
        st.dataframe(r["quarantine"], hide_index=True, width="stretch")


def invalidate_load(reason):
    ss = st.session_state
    if ss.loaded is not None:
        ss.loaded, ss.tests_signed, ss.approved = None, {}, None
        st.info(f"Mapping changed ({reason}). Transform & inject again before testing.")


def sample_pack() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(legacy.SAMPLES.rglob("*")):
            if p.is_file():
                z.write(p, p.relative_to(legacy.SAMPLES))
    return buf.getvalue()


def fw_ruler(width):
    tens = "".join(f"{i // 10 % 10}" if i % 10 == 0 else " " for i in range(1, width + 1))
    ones = "".join(str(i % 10) for i in range(1, width + 1))
    return tens + "\n" + ones


def pass_badge(df, col="result", ok=("PASS", "MATCH")):
    if df is None or df.empty:
        return "—"
    bad = int((~df[col].isin(ok)).sum())
    return "✅ all pass" if bad == 0 else f"❌ {bad} failing"


def styled(df, col="result"):
    def color(v):
        if v in ("PASS", "MATCH", "Auto-mapped", "SME approved"):
            return "color:#0A7A3D;font-weight:600"
        if v in ("FAIL", "MISMATCH", "Needs SME review"):
            return "color:#B42318;font-weight:600"
        return ""
    cols = [c for c in ([col] if isinstance(col, str) else col) if c in df.columns]
    return df.style.map(color, subset=cols) if cols else df


init()
ss = st.session_state

with st.sidebar:
    st.markdown("**Workflow**")
    step = st.radio("Step", STEPS, label_visibility="collapsed", key="step")
    st.divider()
    identity.name_input("SME name", "sme_name")
    st.selectbox("Role", ["SME", "Data steward"], key="role",
                 help="Data stewards see personal data unmasked and can download the loaded database.")
    persist.sidebar(APP)
    st.caption(f"Source: {ss.src_label}")
    st.metric("Mapping complete", f"{ss.cov['pct']}%")
    q = int((ss.m.status == "Needs SME review").sum()) + int((ss.vm.status == "Needs SME review").sum())
    st.caption(f"SME queue: {q} item(s)")

# ------------------------------------------------------------------------------------------ Overview
if step == "Overview":
    src = ss.src
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Legacy entities", len(src["entities"]))
    c2.metric("Data elements found", len(ss.inv))
    c3.metric("Canonical elements", len(ss.canon))
    c4.metric("Mapping complete", f"{ss.cov['pct']}%")
    st.subheader("How it works")
    st.graphviz_chart("""
digraph G { rankdir=LR; bgcolor="transparent";
 node [shape=box, style="rounded,filled", fillcolor="#FFFFFF", color="#0B1B2B", fontname="Helvetica", fontsize=10];
 edge [color="#2B4CF2"];
 src [label="Legacy system\\nCOBOL copybooks + VSAM\\nDB2 tables · code tables\\nPDF forms · notes\\nCOBOL programs"];
 inv [label="Discovery\\nelements · types\\npick lists · aliases"];
 dst [label="Cloud destination\\nschema + pick lists"];
 can [label="SI² canonical\\nmodel + synonyms", fillcolor="#E7ECFE"];
 map [label="Source → Canonical\\n→ Destination\\nwith confidence"];
 q [label="SME validates\\nfields · synonyms\\nvalues → 100%", fillcolor="#E7ECFE"];
 load [label="Transform &\\ninject to cloud"]; test [label="Test legacy vs cloud\\ncounts · totals\\nsamples · COBOL rule"];
 ok [label="SME approval\\n+ audit", fillcolor="#E7ECFE"];
 src -> inv -> map; dst -> can -> map -> q -> load -> test -> ok; q -> can [style=dashed, label=" synonyms"]; }""",
                      width="stretch")
    st.markdown(
        "The demo starts connected to **INSURE/400**, a fictional legacy policy and claims system: two COBOL "
        "copybooks with fixed-width VSAM extracts (one with an `OCCURS` payment group), DB2 agent and coverage "
        "tables, a code table, 12 scanned policy-change **PDF forms**, adjuster **notes** and the **PREMCALC** COBOL "
        "program. The destination is a cloud policy and claims platform with six tables and six pick lists.\n\n"
        "Walk the steps on the left. SI² finds every element and pick list, generates the canonical model from the "
        "destination, and maps everything it can. **You** settle the queue (edit synonyms, confirm fields and values) "
        "until mapping reaches 100%. Then SI² transforms and injects the data, tests legacy against cloud, and you approve.\n\n"
        "**Step 0 · Initial load** is the fast path for a first load from files: upload Excel, CSV, JSON, XML / ACORD, "
        "SQL / PL-SQL scripts, PDFs or an API; SI² proposes the tables, primary and foreign keys and pick lists with "
        "evidence, you approve, and SI² creates the tables, loads them parent-first and reconciles.")
    st.download_button("Download the INSURE/400 sample files", sample_pack(), "SI2_INSURE400_samples.zip",
                       help="Upload these in step 1 to try the upload path, or replace them with your own files.")

# ------------------------------------------------------------------------------------------ 0. Initial load
elif step == STEPS[1]:
    st.subheader("Initial load: upload files, SI² proposes tables and keys, you approve, SI² loads")
    st.caption("Excel (one table per sheet) · CSV · JSON and XML / ACORD (nested records become child tables) · "
               "SQL / PL-SQL scripts (CREATE TABLE, keys and INSERTs are read, nothing is executed) · PDF (simple text "
               "tables, best effort) · an API returning JSON.")
    il = ss.setdefault("il", {})
    steward = ss.get("role", "SME") == "Data steward"
    up = st.file_uploader("Files", accept_multiple_files=True, key="il_files",
                          type=["csv", "txt", "xlsx", "xls", "json", "xml", "sql", "ddl", "pls", "pkb", "pdf"])
    c1, c2 = st.columns([3, 1])
    api = c1.text_input("API address (optional)", IL.SAMPLE_API, key="il_api",
                        help="An https:// address that returns JSON (paging via a 'next' link is followed). "
                             f"{IL.SAMPLE_API} is a built-in stand-in for a client's driver API.")
    use_api = c2.checkbox("Read the API", True, key="il_use_api")
    b1, b2, b3 = st.columns(3)
    go_sample = b1.button("Use the sample upload set", type="primary", key="il_sample")
    go_files = b2.button("Read my files", disabled=not up, key="il_read")
    b3.download_button("Download the sample set", il_sample_zip(), "SI2_initial_load_samples.zip", key="il_dl_samples")
    if go_sample or go_files:
        files = IL.sample_files() if go_sample else [(f.name, f.getvalue()) for f in up]
        with st.spinner("Reading and profiling ..."):
            staged = IL.stage(files, [api] if use_api and api.strip() else [])
            prof = IL.profile(staged)
            props = IL.propose(staged, prof)
            codes = IL.code_descriptions(staged, props, ss.src.get("dest_picklists"))
            edits_df = IL.quality_edits(staged, prof, props)
        ss.il = il = {"staged": staged, "prof": prof, "props": props, "codes": codes, "edits": edits_df,
                      "accepted_edits": set(), "files": [f for f, _ in files], "result": None, "batches": [],
                      "approved_plan": "", "db": str(IL_DIR / f"si2_initial_load_{uuid.uuid4().hex[:8]}.db")}
        for k in [k for k in ss if str(k).startswith("il_ed_")]:
            del ss[k]
        log("SI²", "Initial load: files read", f"{len(files)} file(s), {len(staged.tables)} tables, {len(props)} proposals")
    if not il:
        st.info("Start with the sample set (policy and claim Excel, payment CSV, Oracle DDL, ACORD XML, billing JSON and "
                "a driver API) or upload your own files.")
    else:
        staged, prof, props, codes, edits_df = il["staged"], il["prof"], il["props"], il["codes"], il["edits"]
        m = st.columns(6)
        m[0].metric("Sources", len(il["files"]) + sum(1 for src_, note in staged.notes if src_.startswith("API") and "page" in note))
        m[1].metric("Tables", len(staged.tables))
        m[2].metric("Rows", f"{sum(len(d) for d in staged.tables.values()):,}")
        m[3].metric("Personal-data columns", int((prof.pii != "").sum()))
        m[4].metric("Edit errors", int((edits_df.severity == "Error").sum()))
        m[5].metric("Need a decision", int((props.status == "Proposed").sum()))
        if staged.notes:
            with st.expander(f"Reader notes ({len(staged.notes)})"):
                st.dataframe(pd.DataFrame(staged.notes, columns=["file", "note"]), hide_index=True, width="stretch")
        tabs = st.tabs(["Tables & columns", "Data quality", "Keys & pick lists", "Pick-list codes", "Relationships",
                        "Approve & load", "Delta loads", "Use in migration", "🤖 Ask SI²"])
        with tabs[0]:
            tsel = st.selectbox("Table", list(staged.tables), key="il_table",
                                format_func=lambda t: f"{t}  ·  {len(staged.tables[t])} rows  ·  from {staged.origin[t]}")
            cols = prof[prof.table == tsel].drop(columns=["table"]).reset_index()
            ed = st.data_editor(cols, hide_index=True, width="stretch", key=f"il_ed_{tsel}",
                                disabled=[c for c in cols.columns if c not in ("type", "description")],
                                column_order=["column", "type", "company_term", "pii", "description", "rows", "blank", "distinct", "unique",
                                              "samples", "note"],
                                column_config={"type": st.column_config.SelectboxColumn("type", options=list(IL.SQLITE_TYPE)),
                                               "pii": st.column_config.TextColumn("personal data"),
                                               "description": st.column_config.TextColumn("business description", width="large")})
            if st.button("🤖 Draft business descriptions for this table", key=f"il_ai_desc_{tsel}"):
                desc, src_ = ai.describe_columns(tsel, cols[["column", "type", "samples"]].to_dict("records"))
                for i in cols.index:
                    prof.loc[cols.at[i, "index"], "description"] = desc.get(cols.at[i, "column"], cols.at[i, "description"])
                log(sme() if src_ == "SI² rules" else "Claude", "Initial load: descriptions drafted", f"{tsel} by {src_}")
                for k in [k for k in ss if str(k).startswith("il_ed_")]:
                    del ss[k]
                st.rerun()
            changed = (ed[["type", "description"]].values != cols[["type", "description"]].values).any(axis=1)
            if changed.any():
                for r in ed[changed].itertuples():
                    prof.loc[r.index, ["type", "description"]] = [r.type, r.description]
                    log(sme(), "Initial load: column approved", f"{tsel}.{r.column} {r.type}: {r.description[:60]}")
            st.caption("Types are inferred from the data (or taken from the DDL). Codes with leading zeros (ZIP, class "
                       "codes) stay text; dates in any format load as dates; $ and commas are removed from amounts. "
                       "Personal data is masked everywhere unless your role is Data steward (sidebar).")
            prev = staged.tables[tsel].head(20)
            st.markdown("Preview" + ("" if steward else " (personal data masked)"))
            st.dataframe(prev if steward else IL.mask_frame(prev, tsel, prof), hide_index=True, width="stretch")
        with tabs[1]:
            st.caption("SI² data edits in the style of NCCI / ISO statistical-plan edits, run before anything is loaded. "
                       "Rows with an **Error** are quarantined at load unless you accept that edit; **Warnings** load "
                       "and stay on this report.")
            if edits_df.empty:
                st.success("No edit failures.")
            else:
                summ = edits_df.groupby(["edit", "severity", "message"]).size().reset_index(name="rows")
                summ.insert(0, "accept", summ.edit.isin(il["accepted_edits"]))
                es = st.data_editor(summ, hide_index=True, width="stretch", key=f"il_ed_edits_{len(il['accepted_edits'])}",
                                    disabled=["edit", "severity", "message", "rows"],
                                    column_config={"accept": st.column_config.CheckboxColumn(
                                        "load anyway", help="Errors only: the SME accepts the rows as they are.")})
                acc = set(es[es.accept & (es.severity == "Error")].edit)
                if acc != il["accepted_edits"]:
                    il["accepted_edits"] = acc
                    log(sme(), "Initial load: edit acceptance changed", ", ".join(sorted(acc)) or "none accepted")
                    st.rerun()
                shown = edits_df if steward else edits_df.assign(
                    value=[IL.mask(v, prof.set_index(["table", "column"]).pii.get((t, c), "")) for t, c, v in
                           zip(edits_df.table, edits_df.column, edits_df.value)])
                st.dataframe(styled(shown, "severity"), hide_index=True, width="stretch")
        with tabs[2]:
            st.caption("Every primary key, foreign key and pick list SI² proposes, with its evidence. Declared keys come from "
                       "the DDL; nested keys from the JSON / XML structure; the rest are found in the data. Where one column "
                       "matches two parents, you pick one.")
            a1, a2, _ = st.columns([1.6, 1.2, 2])
            if a1.button("Approve all ≥ 90% without a conflict", key="il_approve_hi"):
                hit = (props.confidence >= 90) & ~props.conflict & (props.status == "Proposed")
                props.loc[hit, "status"] = "Approved"
                log(sme(), "Initial load: proposals approved", f"{int(hit.sum())} at ≥ 90% confidence")
                st.rerun()
            if a2.button("Reset decisions", key="il_reset"):
                props["status"] = "Proposed"
                st.rerun()
            view = props.assign(columns=props["columns"].map(", ".join), ref_columns=props["ref_columns"].map(", ".join))
            ed = st.data_editor(view, hide_index=True, width="stretch", key=f"il_ed_props_{(props.status != 'Proposed').sum()}",
                                disabled=[c for c in view.columns if c != "status"],
                                column_order=["status", "id", "kind", "table", "columns", "ref_table", "ref_columns",
                                              "method", "confidence", "evidence"],
                                column_config={"status": st.column_config.SelectboxColumn(
                                    "decision", options=["Proposed", "Approved", "Rejected"], width="small"),
                                    "confidence": st.column_config.ProgressColumn("confidence", min_value=0, max_value=100,
                                                                                  format="%d%%"),
                                    "evidence": st.column_config.TextColumn("evidence", width="large")})
            diff = ed.status != props.status
            if diff.any():
                for i in ed[diff].index:
                    props.at[i, "status"] = ed.at[i, "status"]
                    log(sme(), f"Initial load: {ed.at[i, 'kind']} {ed.at[i, 'status'].lower()}",
                        f"{ed.at[i, 'id']} {ed.at[i, 'table']}({ed.at[i, 'columns']}) {ed.at[i, 'ref_table']}")
                st.rerun()
            pk_ok = set(props[(props.kind == "PK") & (props.status == "Approved")].table)
            missing = [t for t in staged.tables if t not in pk_ok]
            if missing:
                st.warning("Tables without an approved key (SI² will still give them a generated key): " + ", ".join(missing))
        with tabs[3]:
            st.caption("Each pick list's codes with a drafted description: from the destination pick lists, the SI² insurance "
                       "code dictionary (ACORD-style LOB, claim status, payment type, cause of loss ...), or a draft. Edit "
                       "any description; they load into the pick_list table and travel with the codes into the migration.")
            ced = st.data_editor(codes, hide_index=True, width="stretch", key=f"il_ed_codes_{len(codes)}",
                                 disabled=[c for c in codes.columns if c != "description"],
                                 column_config={"description": st.column_config.TextColumn("description", width="large")})
            if not ced.description.equals(codes.description):
                il["codes"] = ced
                log(sme(), "Initial load: code descriptions approved", f"{int((ced.description != codes.description).sum())} edited")
                st.rerun()
        with tabs[4]:
            g = ['digraph G { rankdir=LR; bgcolor="transparent"; node [shape=box, style="rounded,filled", '
                 'fillcolor="#FFFFFF", color="#0B1B2B", fontname="Helvetica", fontsize=10]; edge [fontname="Helvetica", fontsize=8];']
            for t, df in staged.tables.items():
                pk = props[(props.kind == "PK") & (props.table == t)]
                key = ", ".join(pk.iloc[0]["columns"]) if len(pk) else "?"
                g.append(f'"{t}" [label="{t}\\n{len(df)} rows\\nkey: {key}"];')
            for r in props[props.kind == "FK"].itertuples():
                col = {"Approved": "#0A7A3D", "Rejected": "#C8CDD3"}.get(r.status, "#E8590C" if r.conflict else "#2B4CF2")
                style = "solid" if r.status == "Approved" else "dashed"
                g.append(f'"{r.table}" -> "{r.ref_table}" [color="{col}", style={style}, '
                         f'label=" {", ".join(r.columns)}\\n{r.method.lower()}"];')
            st.graphviz_chart("\n".join(g) + "}", width="stretch")
            st.caption("Arrows point from child to parent. Green = approved, blue dashed = proposed, orange = one column "
                       "matching two parents (SME picks), grey = rejected.")
        with tabs[5]:
            plan = load_plan_digest(il)
            sql = IL.ddl(staged, prof, props, "mssql")
            with st.expander("Generated DDL: SQLite (this demo) and SQL Server"):
                d1, d2 = st.tabs(["SQLite", "SQL Server"])
                with d1:
                    st.code(IL.ddl(staged, prof, props, "sqlite"), language="sql")
                with d2:
                    st.code(sql, language="sql")
            st.download_button("Download SQL Server DDL", sql, "SI2_initial_load_sqlserver.sql", key="il_dl_mssql")
            open_items = int((props.status == "Proposed").sum())
            if open_items:
                st.info(f"{open_items} proposal(s) still need a decision; only approved keys and pick lists are created.")
            st.markdown("**Two-person approval of the load plan** (keys, pick lists, accepted edits)")
            if il.get("approved_plan") == plan:
                st.success(f"Load plan approved by {il.get('plan_checker', '')}.")
            else:
                if il.get("approved_plan"):
                    st.warning("The plan changed after it was approved: submit it again.")
                if st.button("Submit the load plan for approval", key="il_submit_plan"):
                    ok = props[props.status == "Approved"]
                    try:
                        store.request(APP, "Initial load plan", "initial_load",
                                      f"{int((ok.kind == 'PK').sum())} keys, {int((ok.kind == 'FK').sum())} relationships, "
                                      f"{int((ok.kind == 'PICKLIST').sum())} pick lists, accepted edits: "
                                      f"{', '.join(sorted(il['accepted_edits'])) or 'none'}", {"plan": plan}, sme())
                        log(sme(), "Initial load plan submitted for approval", plan[:10])
                        st.rerun()
                    except ValueError as exc:
                        st.error(str(exc))
                approvals_ui.render(APP, sme(), decide_request, note_label="Note", key="il_appr", kinds=["Initial load plan"])
            if st.button("Create tables and load", type="primary", key="il_load", disabled=il.get("approved_plan") != plan,
                         help=None if il.get("approved_plan") == plan else "A second person must approve the load plan first."):
                blocked = IL.blocked_rows(edits_df, il["accepted_edits"])
                with st.spinner("Creating tables and loading parent-first ..."):
                    il["result"] = IL.build_and_load(staged, prof, props, il["db"], sme(), blocked=blocked, codes=il["codes"])
                r = il["result"]
                il["batches"] = [{"batch": r["batch"], "type": "Initial", "as of": r["as_of"], "by": r["by"],
                                  "loaded": int(r["recon"].loaded.sum()), "quarantined": len(r["quarantine"])}]
                log(sme(), "Initial load: tables created and loaded",
                    f"batch {r['batch']}: {int(r['recon'].loaded.sum())} rows loaded, {len(r['quarantine'])} quarantined")
            r = il.get("result")
            if r and Path(r["db_path"]).exists():
                show_load_result(r, steward)
                con = sqlite3.connect(r["db_path"])
                names = [x[0] for x in con.execute("select name from sqlite_master where type in ('table','view') order by name")]
                qt = st.selectbox("Look at a loaded table (…_current views show only current versions)", names, key="il_peek")
                peek = pd.read_sql_query(f'select * from "{qt}" limit 50', con)
                con.close()
                base_t = qt.removesuffix("_current")
                st.dataframe(peek if steward else IL.mask_frame(peek, base_t, prof), hide_index=True, width="stretch")
                if steward:
                    st.download_button("Download the loaded database (SQLite)", Path(r["db_path"]).read_bytes(),
                                       "SI2_initial_load.db", key="il_dl_db")
                else:
                    st.caption("The database download (unmasked personal data) is for the Data steward role.")
            elif r:
                st.warning("The loaded database is no longer on this server (the app was restarted). Load again.")
        with tabs[6]:
            r = il.get("result")
            if not r or not Path(r["db_path"]).exists():
                st.info("Run the initial load first.")
            else:
                st.caption("Weekly or nightly extracts after the first load. New rows are added; a changed row gets a new "
                           "version and the old one is expired (effective_to); unchanged rows are skipped; rows missing from "
                           "the extract are kept, never deleted. Keys and types come from the approved plan.")
                dup = st.file_uploader("Delta files", accept_multiple_files=True, key="il_delta_files",
                                       type=["csv", "txt", "xlsx", "xls", "json", "xml"])
                as_of = st.text_input("As of (blank = now)", "", key="il_delta_asof", placeholder="YYYY-MM-DD HH:MM:SS")
                e1, e2 = st.columns(2)
                go_d_sample = e1.button("Load the sample delta", type="primary", key="il_delta_sample")
                go_d_files = e2.button("Load my delta files", disabled=not dup, key="il_delta_go")
                if go_d_sample or go_d_files:
                    dfiles = ([(p.name, p.read_bytes()) for p in sorted((IL.SAMPLES / "delta").glob("*.*"))] if go_d_sample
                              else [(f.name, f.getvalue()) for f in dup])
                    sd = IL.stage(dfiles)
                    d_edits = IL.quality_edits(sd, prof, props)
                    try:
                        res = IL.delta_load(sd, prof, props, r["db_path"], sme(), as_of=as_of.strip() or None,
                                            blocked=IL.blocked_rows(d_edits, il["accepted_edits"]))
                    except ValueError as exc:
                        st.error(str(exc))
                        st.stop()
                    il["delta"] = res
                    il["batches"].append({"batch": res["batch"], "type": "Delta", "as of": res["as_of"], "by": res["by"],
                                          "loaded": int(res["recon"].loaded.sum()), "quarantined": len(res["quarantine"])})
                    log(sme(), "Delta load", f"batch {res['batch']}: {int(res['recon'].loaded.sum())} new / changed rows")
                if il.get("delta"):
                    res = il["delta"]
                    if res.get("unknown_tables"):
                        st.warning("Not in the approved plan (run a full load to add them): " + ", ".join(res["unknown_tables"]))
                    show_load_result(res, steward)
                st.markdown("**Load history**")
                st.dataframe(pd.DataFrame(il["batches"]), hide_index=True, width="stretch")
        with tabs[8]:
            def _facts():
                ok = props[props.status == "Approved"]
                q = il["result"]["quarantine"] if il.get("result") else pd.DataFrame()
                return {"tables": {t: f"{len(d)} rows from {staged.origin[t]}" for t, d in staged.tables.items()},
                        "approved keys": [f"{r.kind} {r.table}({', '.join(r.columns)})" + (f" -> {r.ref_table}" if r.ref_table else "")
                                          for r in ok.itertuples()],
                        "keys needing a decision": [f"{r.id} {r.kind} {r.table}({', '.join(r.columns)}) -> {r.ref_table}: {r.evidence}"
                                                    for r in props[props.status == "Proposed"].itertuples()],
                        "data edits": edits_df.groupby(["edit", "severity", "message"]).size().reset_index(name="rows").to_dict("records"),
                        "personal data columns": prof[prof.pii != ""][["table", "column", "pii"]].to_dict("records"),
                        "quarantined rows": q[["table", "reason"]].to_dict("records") if len(q) else [],
                        "load batches": il.get("batches", []),
                        "column types": prof[["table", "column", "type"]].to_dict("records")[:120]}
            ai_ui.ask_box("il_ask", _facts, ["Which keys still need my decision?", "Why were rows quarantined?",
                                             "Which columns hold personal data?"])
        with tabs[7]:
            st.caption("Send the loaded tables into Steps 1-9: SI² discovers every column, maps it to the canonical model "
                       "and the cloud destination, and anything missing appears on the Canonical gaps tab in Step 5. The "
                       "approved pick-list codes and descriptions go along as the code table.")
            if st.button("Use these tables as the legacy source", type="primary", key="il_to_mig"):
                src = IL.to_legacy_source(staged, il["codes"], ss.src)
                for ent in src["entities"]:
                    E.CONTEXT.setdefault(ent, context_for(ent))
                set_source(src, f"Initial load: {len(src['entities'])} tables")
                st.success(f"{len(src['entities'])} tables are now the legacy source. Mapping is {ss.cov['pct']}%: "
                           "continue with Step 3 (discovery) and Step 5 (mapping and canonical gaps).")
            if ss.src_label.startswith("Initial load"):
                st.info(f"Current legacy source: {ss.src_label}.")

# ------------------------------------------------------------------------------------------ 1. Legacy sources
elif step == STEPS[2]:
    st.subheader("Legacy sources")
    mode = st.radio("Connection", ["SI² demo legacy system INSURE/400 (connected)", "Upload legacy files"],
                    horizontal=True, key="conn_mode")
    if mode.startswith("Upload"):
        st.markdown("Upload any mix of: COBOL copybooks (`.cpy`) with their data files (same name, `.dat`), database "
                    "tables (`.csv`), a code table (`TABLE_ID, CODE, DESCRIPTION`), PDF forms (`Label: value`), notes "
                    "(`.txt`, `claim|date|author|text`) and COBOL programs (`.cbl`). You can include the destination "
                    "schema and pick-list CSVs too.")
        up = st.file_uploader("Legacy files", accept_multiple_files=True, key="uploads",
                              type=["cpy", "dat", "txt", "csv", "pdf", "cbl", "cob"])
        if up and st.button("Read uploaded files", type="primary"):
            src, msgs = legacy.load_uploads({f.name: f.getvalue() for f in up}, fallback=_demo())
            if not src["entities"]:
                st.error("No legacy data could be read from those files.")
            else:
                set_source(src, f"Uploaded files ({len(up)})")
                for x in msgs:
                    st.write("• " + x)
                st.success("Sources read. Continue to Discovery inventory.")
    elif not ss.src_label.startswith("SI² demo") and st.button("Reconnect the demo system"):
        set_source(_demo(), "SI² demo legacy system INSURE/400")
        st.rerun()

    src = ss.src
    summary = pd.DataFrame([{"entity": k, "source type": v["type"], "records": len(v["df"]),
                             "elements": len([c for c in v["df"].columns if c != "FORM_FILE"])}
                            for k, v in src["entities"].items()])
    st.dataframe(summary, hide_index=True, width="stretch")
    tabs = st.tabs(["COBOL copybooks & data", "Database tables", "PDF forms", "Notes", "COBOL programs"])
    with tabs[0]:
        if not src["layouts"]:
            st.caption("No copybooks connected.")
        for name, lay in src["layouts"].items():
            st.markdown(f"**{name}** · {int(lay.end.max())}-byte record")
            show = lay.assign(pick_list=lay.pick_list.apply(lambda d: ", ".join(f"{k}={v}" for k, v in d.items())))
            st.dataframe(show[["name", "pic", "type", "length", "decimals", "start", "end", "occurrence",
                               "occurs_group", "pick_list"]], hide_index=True, width="stretch")
            raw = src["entities"][name].get("raw", {})
            if raw:
                width = int(lay.end.max())
                st.code(fw_ruler(width) + "\n" + "\n".join(list(raw.values())[:8]), language=None)
            st.dataframe(src["entities"][name]["df"].head(20), hide_index=True, width="stretch")
            for ent in [e for e in src["entities"] if e.startswith(name + ".")]:
                st.markdown(f"`OCCURS` group **{ent}** → child rows")
                st.dataframe(src["entities"][ent]["df"].head(12), hide_index=True, width="stretch")
    with tabs[1]:
        for ent, v in src["entities"].items():
            if v["type"] == "DB2 table":
                st.markdown(f"**{ent}** · {len(v['df'])} rows")
                st.dataframe(v["df"].head(15), hide_index=True, width="stretch")
        if len(src["code_table"]):
            st.markdown("**CODE_TABLE** (legacy pick lists)")
            st.dataframe(src["code_table"], hide_index=True, width="stretch")
    with tabs[2]:
        f = src["entities"].get("POLICY_CHANGE_FORMS")
        if f is None:
            st.caption("No PDF forms connected.")
        else:
            st.caption("Fields read from each scanned policy-change request. Email, phone and mailing address exist only here.")
            st.dataframe(f["df"], hide_index=True, width="stretch")
    with tabs[3]:
        notes = [k for k, v in src["entities"].items() if v["type"] == "Free-text notes"]
        for k in notes:
            st.caption("Repair estimate and attorney involvement are extracted from the free text.")
            st.dataframe(src["entities"][k]["df"], hide_index=True, width="stretch")
        if not notes:
            st.caption("No notes connected.")
    with tabs[4]:
        if src["program"]:
            st.code(src["program"], language="cobol")
            st.markdown("**Business-rule statements found**")
            st.dataframe(pd.DataFrame(legacy.cobol_rules(src["program"])), hide_index=True, width="stretch")
            st.caption("SI² translates PREMCALC into Python for the legacy side and SQL for the cloud side, and "
                       "runs both in step 8 to prove the migrated data gives the same business result.")
        else:
            st.caption("No COBOL programs connected.")

# ------------------------------------------------------------------------------------------ 2. Destination
elif step == STEPS[3]:
    st.subheader("Cloud destination")
    st.markdown("The destination schema and pick lists come from the target platform. Upload them in step 1 "
                "(`table, field, type, length, required, key, pick_list, description` and `pick_list, code, description`) "
                "or use the demo cloud platform.")
    ds = ss.src["dest_schema"]
    c1, c2, c3 = st.columns(3)
    c1.metric("Tables", ds.table.nunique())
    c2.metric("Fields", len(ds))
    c3.metric("Pick lists", ss.src["dest_picklists"].pick_list.nunique())
    t1, t2, t3 = st.tabs(["Data elements", "Pick lists and values", "Generated DDL"])
    with t1:
        st.dataframe(ds, hide_index=True, width="stretch")
    with t2:
        for pl, g in ss.src["dest_picklists"].groupby("pick_list", sort=False):
            used = ", ".join(ds[ds.pick_list == pl].apply(lambda r: f"{r.table}.{r.field}", axis=1))
            st.markdown(f"**{pl}** · used by `{used}`")
            st.dataframe(g[["code", "description"]], hide_index=True, width="stretch")
    with t3:
        st.code(E.ddl(ds), language="sql")

# ------------------------------------------------------------------------------------------ 3. Discovery
elif step == STEPS[4]:
    st.subheader("Discovery inventory")
    inv = ss.inv
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Elements", len(inv))
    c2.metric("With pick lists", int((inv.pick_list != "").sum()))
    c3.metric("Pick-list values", int(inv.pick.apply(len).sum()))
    c4.metric("Source types", inv.source_type.nunique())
    st.caption("Every element SI² found: data type and length (from the copybook PIC or inferred from the data), "
               "pick list (from 88-levels, the code table or the values), business alias (abbreviations expanded) and samples.")
    ents = ["All"] + list(inv.entity.unique())
    pick = st.selectbox("Entity", ents, key="inv_ent")
    view = inv if pick == "All" else inv[inv.entity == pick]
    st.dataframe(view[["entity", "source_type", "element", "alias", "data_type", "pic", "length", "pick_list",
                       "pick_values", "distinct", "null_pct", "samples"]], hide_index=True, width="stretch")
    st.download_button("Download inventory (CSV)", view.drop(columns=["tokens", "prefix", "pick"]).to_csv(index=False),
                       "legacy_inventory.csv", "text/csv")

# ------------------------------------------------------------------------------------------ 4. Canonical
elif step == STEPS[5]:
    st.subheader("Canonical model & synonyms")
    st.markdown("Generated from the destination: one canonical element per business concept (keys shared across "
                "tables become one element), with its pick list and synonyms. **Edit the synonyms** to teach SI² your "
                "legacy vocabulary, then re-run matching. Abbreviations in synonyms are expanded the same way as "
                "legacy names (e.g. `OS RSV` = outstanding reserve).")
    can = ss.canon
    ed = st.data_editor(
        can[["canonical_id", "entity", "attribute", "data_type", "pick_list", "required", "synonyms",
             "destination_fields"]],
        disabled=["canonical_id", "entity", "attribute", "data_type", "pick_list", "required", "destination_fields"],
        column_config={"synonyms": st.column_config.TextColumn("synonyms (comma separated)", width="large")},
        hide_index=True, width="stretch", key="canon_editor")
    if st.button("Save synonyms and re-run matching", type="primary"):
        changed = 0
        for r in ed.itertuples():
            orig = can.loc[can.canonical_id == r.canonical_id, "synonyms"].iat[0]
            if r.synonyms != orig:
                ss.syn_edits[r.canonical_id] = r.synonyms
                changed += 1
                log(sme(), "Synonyms updated", f"{r.canonical_id}: {r.synonyms}")
        before = ss.cov["pct"]
        recompute()
        invalidate_load("synonyms edited")
        st.success(f"{changed} canonical element(s) updated. Mapping {before}% → {ss.cov['pct']}%.")
    with st.expander("Canonical pick lists"):
        st.dataframe(ss.src["dest_picklists"], hide_index=True, width="stretch")
    with st.expander("Abbreviation dictionary SI² uses on legacy names"):
        st.dataframe(pd.DataFrame(sorted(E.ABBR.items()), columns=["abbreviation", "expands to"]),
                     hide_index=True, width="stretch")

# ------------------------------------------------------------------------------------------ 5. Mapping
elif step == STEPS[6]:
    st.subheader("Source → Canonical → Destination")
    cov = ss.cov
    cols = st.columns(len(cov["parts"]) + 1)
    cols[0].metric("Overall", f"{cov['pct']}%")
    for c, (k, (a, b)) in zip(cols[1:], cov["parts"].items()):
        c.metric(k, f"{a}/{b}")
    if cov["missing_required"]:
        st.warning("Required destination fields with no legacy source yet: " + ", ".join(cov["missing_required"]))
    t1, t2, t3 = st.tabs(["SME mapping queue", "Lineage view", "🧩 Canonical gaps"])
    with t1:
        flt = st.radio("Show", ["Needs SME review", "All"], horizontal=True, key="map_flt")
        m = ss.m if flt == "All" else ss.m[ss.m.status == "Needs SME review"]
        if m.empty:
            st.success("Nothing waiting. Every legacy element is mapped or marked not migrated.")
        else:
            options = [CHOICE_NONE, E.NOT_MIGRATED] + list(ss.canon.canonical_id)
            samples = ss.inv.set_index("element_id").samples
            view = m.assign(samples=m.element_id.map(samples), approve=m.status != "Needs SME review",
                            canonical_id=m.canonical_id.where(m.canonical_id != "", ""))
            ed = st.data_editor(
                view[["element_id", "canonical_id", "approve", "suggested", "confidence", "status", "alias",
                      "samples", "data_type"]],
                column_config={
                    "canonical_id": st.column_config.SelectboxColumn("canonical element", options=options, width="medium"),
                    "approve": st.column_config.CheckboxColumn("approve"),
                    "confidence": st.column_config.ProgressColumn("confidence", min_value=0, max_value=100, format="%d%%"),
                },
                disabled=["element_id", "suggested", "alias", "data_type", "samples", "confidence", "status"],
                hide_index=True, width="stretch", key=f"map_editor_{flt}")
            c1, c2 = st.columns(2)
            if c1.button("Save SME decisions", type="primary"):
                n = 0
                for r, o in zip(ed.itertuples(), view.itertuples()):
                    if r.approve and r.canonical_id:
                        if r.canonical_id != o.canonical_id or o.status == "Needs SME review" or o.element_id in ss.rejected:
                            ss.map_ov[r.element_id] = r.canonical_id
                            ss.rejected.discard(r.element_id)
                            n += 1
                            log(sme(), "Mapping approved", f"{r.element_id} → {r.canonical_id}")
                    elif not r.approve and o.status != "Needs SME review":
                        ss.map_ov.pop(r.element_id, None)
                        ss.rejected.add(r.element_id)
                        n += 1
                        log(sme(), "Mapping rejected", r.element_id)
                recompute()
                invalidate_load("field mapping")
                st.success(f"{n} decision(s) saved. Mapping is {ss.cov['pct']}%.")
                st.rerun()
            if c2.button("Approve every suggestion ≥ 60%"):
                pend = ss.m[(ss.m.status == "Needs SME review") & (ss.m.confidence >= 60) & (ss.m.suggested != "")]
                for r in pend.itertuples():
                    ss.map_ov[r.element_id] = r.suggested
                    log(sme(), "Mapping approved (bulk)", f"{r.element_id} → {r.suggested}")
                recompute()
                invalidate_load("field mapping")
                st.rerun()
        st.caption("Tick **approve** to accept the canonical element shown (change it from the list first if needed). "
                   f"Choose **{E.NOT_MIGRATED}** for data that stays in the archive. Untick an auto-mapped row to reject it.")
    with t2:
        mv = E.mapping_view(ss.inv, ss.m, ss.canon, ss.vm)
        st.dataframe(styled(mv, "Status"), hide_index=True, width="stretch")
        ent = st.selectbox("Draw lineage for", list(ss.src["entities"]), key="lin_ent")
        sub = ss.m[(ss.m.entity == ent)]
        dot = ['digraph L { rankdir=LR; bgcolor="transparent"; node [shape=box, style="rounded,filled", '
               'fontname="Helvetica", fontsize=9]; edge [color="#2B4CF2"];']
        for r in sub.itertuples():
            s_id = f'"s:{r.element}"'
            dot.append(f'{s_id} [label="{r.element}", fillcolor="#FFFFFF"];')
            if r.canonical_id and r.canonical_id != E.NOT_MIGRATED:
                dot.append(f'"c:{r.canonical_id}" [label="{r.canonical_id}", fillcolor="#E7ECFE"];')
                style = "" if r.status != "Needs SME review" else ', style=dashed, color="#B42318"'
                dot.append(f'{s_id} -> "c:{r.canonical_id}" [label="{r.confidence}%"{style}];')
                for f in r.destination_fields.split(", "):
                    dot.append(f'"d:{f}" [label="{f}", fillcolor="#EAF7EF"];')
                    dot.append(f'"c:{r.canonical_id}" -> "d:{f}";')
            else:
                dot.append(f'{s_id} -> "x" [color="#9AA5B1"]; "x" [label="not migrated / pending", fillcolor="#F2F4F7"];')
        dot.append("}")
        st.graphviz_chart("\n".join(dot), width="stretch")
        st.caption("Legacy element → canonical element → destination field(s). Dashed red = waiting for the SME.")
    with t3:
        gaps_ui.render(MG.scan(ss), MG.Handler(ss, sme(), recompute, log, invalidate_load), key="mig_gaps",
                       intro="Legacy elements and values the canonical model cannot place, plus required cloud fields nothing "
                             "feeds yet. Add new extends the cloud destination (new column or new pick-list code).")

# ------------------------------------------------------------------------------------------ 6. Values
elif step == STEPS[7]:
    st.subheader("Pick-list values")
    vm = ss.vm
    if vm.empty:
        st.info("No mapped pick-list elements yet.")
    else:
        pend = int((vm.status == "Needs SME review").sum())
        st.metric("Values waiting for the SME", pend)
        st.caption("Legacy values come from COBOL 88-levels and the code table; destination codes come from the "
                   "cloud pick lists. Pick the destination code and tick approve.")
        pls = ss.src["dest_picklists"]
        decisions = []
        for eid, g in vm.groupby("element_id", sort=False):
            pl = g.pick_list.iat[0]
            label = f"{eid} → {pl}" + (f"  ·  {int((g.status == 'Needs SME review').sum())} to review"
                                       if (g.status == "Needs SME review").any() else "  ·  ✓")
            with st.expander(label, expanded=(g.status == "Needs SME review").any()):
                v = g.assign(approve=g.status != "Needs SME review",
                             destination_code=g.destination_code.where(g.destination_code != "", g.suggested))
                ed = st.data_editor(
                    v[["legacy_value", "legacy_meaning", "suggested", "confidence", "destination_code", "approve", "status"]],
                    column_config={"destination_code": st.column_config.SelectboxColumn(
                        "destination code", options=[""] + list(pls[pls.pick_list == pl].code)),
                        "confidence": st.column_config.ProgressColumn("confidence", min_value=0, max_value=100, format="%d%%")},
                    disabled=["legacy_value", "legacy_meaning", "suggested", "confidence", "status"],
                    hide_index=True, width="stretch", key=f"vm_{eid}")
                decisions.append((eid, v, ed))
        if st.button("Save value decisions", type="primary"):
            n = 0
            for eid, v, ed in decisions:
                for r, o in zip(ed.itertuples(), v.itertuples()):
                    key = (eid, r.legacy_value)
                    if r.approve and r.destination_code and (o.status == "Needs SME review" or r.destination_code != o.destination_code):
                        ss.val_ov[key] = r.destination_code
                        n += 1
                        log(sme(), "Value mapping approved", f"{eid} '{r.legacy_value}' ({r.legacy_meaning}) → {r.destination_code}")
            recompute()
            invalidate_load("value mapping")
            st.success(f"{n} value decision(s) saved. Mapping is {ss.cov['pct']}%.")
            st.rerun()

# ------------------------------------------------------------------------------------------ 7. Transform & inject
elif step == STEPS[8]:
    st.subheader("Transform & inject into the cloud")
    ready = ss.cov["pct"] >= 100
    if not ready:
        st.warning(f"Mapping is {ss.cov['pct']}%. Finish the SME queue (steps 4–6) to reach 100% before injecting.")
    if st.button("Transform and inject", type="primary", disabled=not ready):
        canonical, dest, issues = E.transform(ss.src, ss.inv, ss.m, ss.canon, ss.vm, ss.src["dest_schema"])
        errs = E.validate(dest, ss.src["dest_schema"], ss.src["dest_picklists"])
        if len(errs):
            ss.loaded = {"canonical": canonical, "dest": dest, "issues": issues, "errors": errs, "con": None}
            log("SI²", "Load blocked by validation", f"{int(errs.failed_rows.sum())} failing values")
        else:
            con = E.load(dest, ss.src["dest_schema"])
            ss.loaded = {"canonical": canonical, "dest": dest, "issues": issues, "errors": errs, "con": con,
                         "at": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
            ss.tests_signed, ss.approved = {}, None
            log(sme(), "Data injected into cloud database",
                ", ".join(f"{t} {len(d)}" for t, d in dest.items()))
    L = ss.loaded
    if L:
        if len(L["errors"]):
            st.error("Destination validation failed, nothing was injected. Fix the mapping and try again.")
            st.dataframe(L["errors"], hide_index=True, width="stretch")
        else:
            st.success(f"Injected at {L['at']}: " + " · ".join(f"{t} {len(d)} rows" for t, d in L["dest"].items()))
        if len(L["issues"]):
            st.markdown("**Transformation notes**")
            st.dataframe(L["issues"], hide_index=True, width="stretch")
        t1, t2, t3 = st.tabs(["Canonical database", "Cloud destination tables", "Downloads"])
        with t1:
            st.caption("`_lineage` shows which legacy sources contributed to each canonical record.")
            for name, df in L["canonical"].items():
                st.markdown(f"**{name}** · {len(df)} rows")
                st.dataframe(df.head(50), hide_index=True, width="stretch")
        with t2:
            for t, df in L["dest"].items():
                st.markdown(f"**{t}** · {len(df)} rows")
                st.dataframe(df.head(50), hide_index=True, width="stretch")
        with t3:
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
                for t, df in L["dest"].items():
                    z.writestr(f"destination/{t}.csv", df.to_csv(index=False))
                for t, df in L["canonical"].items():
                    z.writestr(f"canonical/{t}.csv", df.to_csv(index=False))
                z.writestr("mapping.csv", E.mapping_view(ss.inv, ss.m, ss.canon, ss.vm).to_csv(index=False))
                z.writestr("value_maps.csv", ss.vm.to_csv(index=False))
            st.download_button("Canonical + destination tables and mapping (ZIP)", buf.getvalue(),
                               "SI2_migration_output.zip")
            if L["con"] is not None:
                st.download_button("Cloud database load script (SQL)", "\n".join(L["con"].iterdump()),
                                   "SI2_cloud_load.sql", "text/plain")
    else:
        st.info("Nothing injected yet.")

# ------------------------------------------------------------------------------------------ 8. Test
elif step == STEPS[9]:
    st.subheader("Test legacy vs cloud")
    L = ss.loaded
    if not L or L.get("con") is None:
        st.info("Inject the data first (step 7).")
    else:
        con = L["con"]
        rec = E.reconcile(ss.src, ss.m, con)
        t1, t2, t3, t4 = st.tabs(["Counts & control totals", "Referential integrity", "Sample record",
                                  "COBOL business rule"])
        with t1:
            st.markdown(f"**Record counts** {pass_badge(rec['counts'])}")
            st.dataframe(styled(rec["counts"]), hide_index=True, width="stretch")
            st.markdown(f"**Control totals** {pass_badge(rec['totals'])}")
            st.dataframe(styled(rec["totals"]), hide_index=True, width="stretch")
        with t2:
            st.markdown(f"**Foreign keys in the cloud database** {pass_badge(rec['integrity'])}")
            st.dataframe(styled(rec["integrity"]), hide_index=True, width="stretch")
        with t3:
            ents = [e for e, v in ss.src["entities"].items() if not e.count(".")]
            ent = st.selectbox("Legacy entity", ents, key="smp_ent")
            df = ss.src["entities"][ent]["df"]
            kc = [c for c in df.columns if c != "FORM_FILE"][0]
            key = st.selectbox(f"Record ({kc})", list(df[kc].astype(str)), key=f"smp_key_{ent}")
            raw, cmp_ = E.sample_compare(ss.src, ss.inv, ss.m, ss.canon, ss.vm, con, ent, key)
            if raw:
                lay = ss.src["layouts"].get(ent)
                st.markdown("**Legacy record as stored (fixed width)**")
                st.code(fw_ruler(int(lay.end.max())) + "\n" + raw, language=None)
            if cmp_.empty:
                st.caption("This entity does not feed a table keyed by its first field. Pick another entity.")
            else:
                st.markdown(f"**Legacy → expected → cloud** {pass_badge(cmp_[cmp_.result != 'Not migrated'])}")
                st.dataframe(styled(cmp_), hide_index=True, width="stretch")
        with t4:
            if not ss.src["program"] or "POLMAST" not in ss.src["entities"]:
                st.caption("Needs the PREMCALC program and the POLMAST policy master.")
                ep = None
            else:
                st.markdown("PREMCALC `CALC-EARNED-PREM` runs on the **legacy** record (Python translation of the COBOL, "
                            "cancelled = 88-level `PM-STAT-CANCELLED`) and as **SQL on the cloud database** (cancelled = "
                            "`policy_status = 'Cancelled'`). Same answer for every policy proves the data *and* the "
                            "pick-list decisions keep the business meaning.")
                val = st.date_input("Valuation date", dt.date(2026, 6, 30), key="val_date")
                ep = E.earned_premium_test(ss.src, con, val)
                c1, c2, c3 = st.columns(3)
                c1.metric("Policies tested", len(ep))
                c2.metric("Matches", int((ep.result == "MATCH").sum()))
                c3.metric("Legacy vs cloud earned", f"${ep.legacy_earned.sum():,.2f}",
                          f"{ep.cloud_earned.sum() - ep.legacy_earned.sum():+,.2f}")
                bad = ep[ep.result != "MATCH"]
                if len(bad):
                    st.error(f"{len(bad)} policies give a different earned premium in the cloud. Look at the legacy "
                             "status: the value mapping changed the business meaning.")
                    st.dataframe(styled(bad), hide_index=True, width="stretch")
                with st.expander("All policies"):
                    st.dataframe(styled(ep), hide_index=True, width="stretch")
        st.divider()
        st.markdown("**SME test sign-off**")
        checks = {"Counts & control totals": pass_badge(rec["counts"]) + " / " + pass_badge(rec["totals"]),
                  "Referential integrity": pass_badge(rec["integrity"]),
                  "Sample records reviewed": "SME review",
                  "COBOL business rule": pass_badge(ep) if ep is not None else "—"}
        for name, status in checks.items():
            c1, c2, c3 = st.columns([3, 2, 2])
            c1.write(name)
            c2.write(status)
            signed = ss.tests_signed.get(name)
            if signed:
                c3.write(f"✅ {signed}")
            elif "❌" in status:
                c3.write("Fix before signing")
            elif c3.button("Sign off", key=f"sign_{name}"):
                ss.tests_signed[name] = f"{sme()} · {dt.datetime.now():%Y-%m-%d %H:%M}"
                log(sme(), "Test signed off", f"{name}: {status}")
                st.rerun()

# ------------------------------------------------------------------------------------------ 9. Approval
elif step == STEPS[10]:
    st.subheader("SME approval")
    L = ss.loaded
    items = [("Mapping 100% (fields, synonyms, pick-list values)", ss.cov["pct"] >= 100),
             ("Data injected with zero validation errors", bool(L and L.get("con") is not None)),
             ("All four tests signed off", len(ss.tests_signed) >= 4)]
    for label, ok in items:
        st.write(("✅ " if ok else "⬜ ") + label)
    if ss.approved:
        st.success(f"Migration approved by {ss.approved['by']} on {ss.approved['at']}.")
        st.json(ss.approved)
    elif all(ok for _, ok in items):
        note = st.text_area("Sign-off note", "Legacy and cloud results match. Recommended for production cut-over.")
        if st.button("Sign off and request the second approval", type="primary"):
            try:
                store.request(APP, "Migration sign-off", "migration",
                              f"{ss.src_label}: {sum(len(d) for d in L['dest'].values()):,} rows, 4 tests signed. {note}",
                              {"rows": {t: len(d) for t, d in L["dest"].items()}, "tests": ss.tests_signed}, sme())
                log(sme(), "Migration signed off (first signature)", note)
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))
        approvals_ui.render(APP, sme(), decide_request, note_label="Approval note",
                            note_default="Approved for production cut-over.", key="mig_appr", kinds=["Migration sign-off"])
    else:
        st.info("Complete the items above to enable approval.")

# ------------------------------------------------------------------------------------------ Audit
elif step == "Audit trail":
    st.subheader("Audit trail")
    a = pd.DataFrame(ss.audit)
    st.dataframe(a.iloc[::-1], hide_index=True, width="stretch")
    st.download_button("Download audit trail (CSV)", a.to_csv(index=False), "SI2_migration_audit.csv", "text/csv")

persist.checkpoint(APP, KEYS, sme())
branding.note_synthetic()
branding.footer()
