"""SI² ISO Bureau Reporting - all lines (PA, HO, CA, CP, GL, IM, CR, BP, FI, BR).

    streamlit run app_iso_bureau.py

Select line, bureau and accounting period -> generate -> validate -> SME approve -> submit ->
correct -> resubmit -> close. Layouts, fields, canonical model, pick lists, aliases and rules are
effective-dated and SME-approved. Engine and docs: iso_bureau/.
"""
from __future__ import annotations

import io
import json
import os
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

from iso_bureau import db, engine as E, lineage as L, seed, templates as T
from iso_bureau.catalog import LOBS
from si2_common import branding, gate

branding.page("ISO Bureau Reporting", "ISO statistical plans, all lines: effective-dated layouts, canonical model, "
              "pick lists and rules, every object SME-approved.")
gate.require_access()

DB_PATH = Path(os.environ.get("SI2_BUREAU_DB", db.DEFAULT_DB))
LOB_NAME = {c: n for c, n, *_ in LOBS}
LOB_CODES = list(LOB_NAME)
BADGE = {"APPROVED": "🟢 APPROVED", "PENDING": "🟡 PENDING", "REJECTED": "🔴 REJECTED", "MISSING": "⛔ MISSING",
         "DERIVED": "🔷 DERIVED", "NONE": "▫️ none", "EXPIRED": "⚪ EXPIRED"}
REC_BADGE = {"VALID": "✅ VALID", "WARNING": "⚠️ WARNING", "ERROR": "❌ ERROR", "HELD": "⏸ HELD",
             "SUBMITTED": "📤 SUBMITTED", "ACCEPTED": "✅ ACCEPTED", "REJECTED": "❌ REJECTED"}

st.markdown("""<style>
.iso-title{font-size:1.3rem;font-weight:700;margin:0}
.iso-sub{color:#6b7280;margin:0 0 .6rem 0}
.step{display:inline-block;padding:.25rem .7rem;border-radius:1rem;margin:0 .2rem .3rem 0;font-size:.85rem;border:1px solid #d1d5db}
.step.done{background:#dcfce7;border-color:#16a34a}
.step.now{background:#fef9c3;border-color:#ca8a04;font-weight:600}
.ruler{font-family:monospace;font-size:12px;white-space:pre;color:#6b7280}
.rec{font-family:monospace;font-size:12px;white-space:pre}
</style>""", unsafe_allow_html=True)


@st.cache_resource
def get_con():
    if db.backend() == "mssql":
        return db.connect()
    if not DB_PATH.exists():
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        seed.build(DB_PATH, demo_approve=True)
    return db.connect(DB_PATH)


con = get_con()


def status_of(r: dict) -> str:
    if r.get("status") == "APPROVED" and r.get("exp_date", "9999") < date.today().isoformat():
        return BADGE["EXPIRED"]
    return BADGE.get(r.get("status"), r.get("status"))


def table(rows, cols=None, height=None, key=None):
    d = pd.DataFrame(rows)
    if cols and not d.empty:
        d = d[[c for c in cols if c in d.columns]]
    if "status" in d.columns and rows and "eff_date" in rows[0]:
        d["status"] = [status_of(r) for r in rows]
    st.dataframe(d, width="stretch", hide_index=True, height=height or "auto", key=key)
    return d


def toast(msg):
    st.session_state["_flash"] = msg


def lob_label(c):
    return f"{c} - {LOB_NAME[c]}"


# ======================================================================= sidebar
with st.sidebar:
    st.markdown("### 🛡️ SI² Bureau Reporting")
    st.caption("ISO statistical reporting - all lines")
    PAGES = ["🏠 Dashboard", "▶️ Bureau Run", "🛠 Corrections & Resubmit", "✅ SME Validation Workbench",
             "📐 Layouts", "🧬 Canonical Model", "📋 Pick Lists", "⚙️ Business Rules",
             "🗳 Approval Queue", "⬇⬆ SME Templates", "📜 Audit Trail", "🗄 Data"]
    page = st.radio("Menu", PAGES, label_visibility="collapsed", key="page")
    st.divider()
    actor = st.text_input("SME / approver name", value=st.session_state.get("actor", "SME"), key="actor")
    pc = db.pending_counts(con)
    st.metric("Items awaiting SME approval", sum(pc.values()))
    st.caption(f"Database: {db.describe(con)}")
    if db.backend() != "mssql":
        with st.expander("Demo data"):
            st.caption("Rebuild the demo database (baseline approved, 2027 changes pending).")
            if st.button("Reset demo database"):
                st.cache_resource.clear()
                con.close()
                seed.build(DB_PATH, demo_approve=True)
                st.rerun()

if "_flash" in st.session_state:
    st.success(st.session_state.pop("_flash"))


def header(title, sub):
    st.markdown(f'<p class="iso-title">{title}</p><p class="iso-sub">{sub}</p>', unsafe_allow_html=True)


# ===================================================================== dashboard
def page_dashboard():
    header("Dashboard", "Select line, bureau and accounting period → generate → validate → SME approve → submit → correct → close")
    c = st.columns(4)
    c[0].metric("Lines of business", len(LOB_CODES))
    c[1].metric("Approved layouts", db.one(con, "SELECT COUNT(*) n FROM layout_version WHERE status='APPROVED'")["n"])
    c[2].metric("Pending SME approvals", sum(pc.values()))
    c[3].metric("Batches", db.one(con, "SELECT COUNT(*) n FROM submission_batch WHERE status!='SANDBOX'")["n"])
    st.graphviz_chart("""digraph{rankdir=LR; node[shape=box,style="rounded,filled",fillcolor="#eef2ff",fontname=Helvetica,fontsize=11]; edge[color="#64748b"]
      src[label="Source systems\\nGuidewire / Duck Creek / legacy"]; can[label="Canonical model\\nelements · aliases · pick lists"];
      bre[label="Business Rule Engine\\nderive · validate · transform"]; lay[label="ISO layout\\n(effective-dated)"];
      file[label="150-byte flat file"]; iso[label="ISO\\nacknowledgment"]; fix[label="Corrections\\n& resubmission"];
      sme[label="SME approves every object\\n(eff / exp dated)",fillcolor="#fef9c3"];
      src->can->bre->file->iso->fix->can; lay->file; sme->can; sme->bre; sme->lay; sme->file[label=" batch sign-off",fontsize=9]}""")
    l, r = st.columns(2)
    with l:
        st.subheader("Pending approvals by object")
        table([{"object": k, "pending": v} for k, v in pc.items() if v])
    with r:
        st.subheader("Batches by line and status")
        b = db.rows(con, "SELECT lob_code, record_type, status, COUNT(*) n FROM submission_batch WHERE status!='SANDBOX' GROUP BY lob_code, record_type, status")
        if b:
            table(b)
        else:
            st.info("No batches yet - go to ▶️ Bureau Run.")
    st.subheader("Layout import findings for SME review")
    f = db.rows(con, "SELECT lob_code, record_type, version_no, source_file, notes FROM layout_version WHERE notes IS NOT NULL")
    table(f)


# ===================================================================== run page
def run_selector(prefix="run"):
    c = st.columns([1, 2, 1.2, 1.2, 1, 1])
    bureau = c[0].selectbox("Bureau", ["ISO"], key=f"{prefix}_b",
                            help="NCCI / WCIRB / NYCIRB are handled by the Workers Comp module")
    lob = c[1].selectbox("Line of business", LOB_CODES, format_func=lob_label, key=f"{prefix}_lob")
    rt = c[2].selectbox("Record type", ["PREMIUM", "LOSS"], key=f"{prefix}_rt")
    ptype = c[3].selectbox("Accounting period", ["MONTHLY", "QUARTERLY"], index=1, key=f"{prefix}_pt")
    year = c[4].selectbox("Year", [2025, 2026, 2027], index=1, key=f"{prefix}_y")
    n = c[5].selectbox("Month" if ptype == "MONTHLY" else "Quarter", list(range(1, 13 if ptype == "MONTHLY" else 5)),
                       index=8 if ptype == "MONTHLY" else 2, key=f"{prefix}_n_{ptype}")
    ps, pe = E.period_bounds(ptype, year, n)
    return bureau, lob, rt, ptype, ps, pe


def stepper(status):
    flow = ["GENERATED", "VALIDATED", "SME_APPROVED", "SUBMITTED", "ACCEPTED", "CLOSED"]
    s = "ACCEPTED" if status == "PARTIALLY_ACCEPTED" else status
    idx = flow.index(s) if s in flow else -1
    html = "".join(f'<span class="step {"done" if i < idx or (i == idx and s == "CLOSED") else "now" if i == idx else ""}">'
                   f'{i+1}. {x.replace("_", " ").title().replace("Sme", "SME")}</span>' for i, x in enumerate(flow))
    st.markdown(html, unsafe_allow_html=True)


def record_inspector(batch, rec):
    lay = db.one(con, "SELECT * FROM layout_version WHERE layout_id=?", (batch["layout_id"],))
    fields = db.rows(con, "SELECT * FROM layout_field WHERE layout_id=? ORDER BY seq, eff_date DESC", (lay["layout_id"],))
    seen, fl = set(), []
    for f in fields:
        if f["seq"] not in seen and f["eff_date"] <= batch["period_end"] <= f["exp_date"]:
            seen.add(f["seq"]); fl.append(f)
    canon = json.loads(rec["canonical_json"])
    txn = db.one(con, "SELECT * FROM source_transaction WHERE txn_id=?", (rec["txn_id"],))
    payload = json.loads(txn["payload_json"])
    maps = {m["element_code"]: m["source_attribute"] for m in db.rows(con, "SELECT * FROM source_mapping WHERE source_system=?",
                                                                       (txn["source_system"],))}
    msgs = json.loads(rec["messages_json"])
    bad = {m.get("element") for m in msgs}
    out = []
    for p in E.parse_record(rec["record_text"], fl):
        attr = maps.get(p["element"], "")
        out.append({"#": p["seq"], "pos": p["pos"], "bureau field": p["field"], "bureau value": f"[{p['value']}]",
                    "canonical element": p["element"], "canonical value": canon.get(p["element"], ""),
                    f"{txn['source_system']} attribute": attr or "(derived)", "source value": payload.get(attr, ""),
                    "issue": "❗" if p["element"] in bad else ""})
    st.caption(f"Source {txn['source_system']} key {txn['source_txn_key']} · code date {canon.get('_code_date')} · "
               f"layout v{lay['version_no']}" + (f" · corrects txn {txn['corrects_txn_id']}" if txn["corrects_txn_id"] else ""))
    st.dataframe(pd.DataFrame(out), width="stretch", hide_index=True)
    if msgs:
        st.dataframe(pd.DataFrame(msgs), width="stretch", hide_index=True)


def page_run():
    header("Bureau Run", "Generate → Validate → SME approve → Submit for the selected line, bureau and accounting period")
    bureau, lob, rt, ptype, ps, pe = run_selector()
    sandbox = st.toggle("Sandbox preview with PENDING metadata (SME test - can never be submitted)", key="sandbox")
    st.caption(f"Period **{ps} → {pe}** · layout and fields resolved on {pe} · pick-list codes and rules resolved on each "
               f"transaction's policy effective date")
    issues = E.readiness(con, bureau, lob, rt, pe)
    lay, fields = E.resolve_layout(con, bureau, lob, rt, pe, sandbox)
    if issues and not sandbox:
        st.error("Not ready - these items need SME approval first:")
        table(issues)
    elif lay:
        st.success(f"Ready · {bureau} {lob} {rt} layout v{lay['version_no']} ({lay['eff_date']} → {lay['exp_date']}, "
                   f"{lay['status']}) · {len(fields)} fields")
    n_src = len(E.current_txns(con, lob, rt, ps, pe))
    c = st.columns([1, 1, 1, 1, 3])
    if c[0].button("1 · Generate", type="primary", disabled=bool(issues) and not sandbox or lay is None):
        try:
            bid = E.generate_batch(con, bureau, lob, rt, ptype, ps, pe, actor, sandbox=sandbox)
            st.session_state["batch_id"] = bid
            toast(f"Batch {bid} generated from {n_src} source transactions")
            st.rerun()
        except ValueError as ex:
            st.error(str(ex))
    c[4].caption(f"{n_src} unreported source transactions in period")

    batches = db.rows(con, """SELECT * FROM submission_batch WHERE bureau_code=? AND lob_code=? AND record_type=? AND period_start=?
                              AND period_end=? ORDER BY batch_id DESC""", (bureau, lob, rt, ps, pe))
    if not batches:
        st.info("No batch for this selection yet.")
        return
    ids = [b["batch_id"] for b in batches]
    default = st.session_state.get("batch_id") if st.session_state.get("batch_id") in ids else ids[0]
    bid = st.selectbox("Batch", ids, index=ids.index(default),
                       format_func=lambda i: next(f"#{b['batch_id']} · {b['status']} · {b['created_at']}"
                                                  + (f" · resubmission of #{b['parent_batch_id']}" if b["parent_batch_id"] else "")
                                                  for b in batches if b["batch_id"] == i))
    b = db.one(con, "SELECT * FROM submission_batch WHERE batch_id=?", (bid,))
    if b["status"] == "SANDBOX":
        st.warning("Sandbox batch - built with pending metadata for SME testing; it cannot be approved or submitted.")
    else:
        stepper(b["status"])
    act = st.columns(5)
    try:
        if act[0].button("2 · Validate", disabled=b["status"] not in ("GENERATED", "SANDBOX")):
            E.validate_batch(con, bid, actor); toast("Validation complete"); st.rerun()
        if act[1].button("3 · SME approve", disabled=b["status"] != "VALIDATED",
                         help="SME signs off the control totals; records with errors are held for correction"):
            E.sme_approve_batch(con, bid, actor); toast("Batch approved by SME"); st.rerun()
        if act[2].button("4 · Submit to ISO", disabled=b["status"] != "SME_APPROVED"):
            r = E.submit_batch(con, bid, actor)
            toast(f"Submitted {r['file_name']} - ISO: {r['accepted']} accepted, {r['rejected']} rejected, {r['held']} held")
            st.rerun()
        if act[3].button("5 · Close", disabled=b["status"] not in ("ACCEPTED", "PARTIALLY_ACCEPTED")):
            E.close_batch(con, bid, actor); toast("Batch closed"); st.rerun()
    except ValueError as ex:
        st.error(str(ex))
    if b["status"] == "PARTIALLY_ACCEPTED":
        act[4].warning("Open items → 🛠 Corrections")

    m = st.columns([1, 1, 1, 1, 1.8, 1.8, 1.6])
    for col, (lbl, k) in zip(m, [("Records", "record_count"), ("Reportable", "valid_count"), ("Warnings", "warning_count"),
                                 ("Errors", "error_count")]):
        col.metric(lbl, b[k])
    if rt == "PREMIUM":
        m[4].metric("Written premium", f"${b['total_premium']:,.2f}")
    else:
        m[4].metric("Paid loss", f"${b['total_paid']:,.2f}")
        m[5].metric("Outstanding", f"${b['total_outstanding']:,.2f}")
        m[6].metric("ALAE", f"${b['total_alae']:,.2f}")

    recs = db.rows(con, "SELECT * FROM submission_record WHERE batch_id=? ORDER BY line_no", (bid,))
    tabs = st.tabs(["Records", "Record inspector", "Flat file", "Batch history"])
    with tabs[0]:
        f = st.multiselect("Status", sorted({r["status"] for r in recs}), key="recfilter")
        rows = []
        for r in recs:
            if f and r["status"] not in f:
                continue
            cn = json.loads(r["canonical_json"])
            rows.append({"line": r["line_no"], "status": REC_BADGE.get(r["status"], r["status"]),
                         "policy": cn.get("POLICY_NUMBER"), "claim": cn.get("CLAIM_NUMBER", ""), "state": cn.get("STATE"),
                         "amount": cn.get("WRITTEN_PREMIUM") or cn.get("PAID_LOSS"),
                         "messages": " | ".join(f"{m['code']}: {m['msg']}" for m in json.loads(r["messages_json"]))})
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True, height=380)
    with tabs[1]:
        ln = st.selectbox("Record line", [r["line_no"] for r in recs],
                          format_func=lambda n: next(f"{n} · {r['status']}" for r in recs if r["line_no"] == n))
        record_inspector(b, next(r for r in recs if r["line_no"] == ln))
    with tabs[2]:
        name, text = (b["file_name"], b["file_text"]) if b["file_text"] else E.build_file(con, bid)
        st.caption(f"{name} · {len(text.splitlines())} records × 150 bytes" + ("" if b["file_text"] else " · preview (not yet submitted)"))
        ruler = "".join(str(i // 10 % 10) if i % 10 == 0 else " " for i in range(1, 151)) + "\n" + "".join(str(i % 10) for i in range(1, 151))
        st.markdown(f'<div class="ruler">{ruler}</div><div class="rec">{text[:150*40]}</div>', unsafe_allow_html=True)
        st.download_button("Download flat file", text, file_name=name, disabled=not text)
    with tabs[3]:
        table(db.rows(con, "SELECT at, status_from, status_to, actor, comment FROM batch_event WHERE batch_id=? ORDER BY event_id", (bid,)))


# ============================================================ corrections page
def page_corrections():
    header("Corrections & Resubmission", "Fix held (validation) and rejected (ISO) records at the source, resubmit, then close the period")
    batches = db.rows(con, """SELECT b.*, (SELECT COUNT(*) FROM submission_record r WHERE r.batch_id=b.batch_id AND r.status IN ('HELD','REJECTED')) open_items
                              FROM submission_batch b WHERE b.status IN ('PARTIALLY_ACCEPTED','ACCEPTED') ORDER BY batch_id DESC""")
    if not batches:
        st.info("No acknowledged batches yet. Submit a batch on ▶️ Bureau Run first.")
        return
    bid = st.selectbox("Acknowledged batch", [b["batch_id"] for b in batches],
                       format_func=lambda i: next(f"#{b['batch_id']} · {b['lob_code']} {b['record_type']} {b['period_start']}→{b['period_end']} · "
                                                  f"{b['status']} · {b['open_items']} open" for b in batches if b["batch_id"] == i))
    b = db.one(con, "SELECT * FROM submission_batch WHERE batch_id=?", (bid,))
    items = E.open_corrections(con, bid)
    corrected = {r["txn_id"] for r in items if db.one(con, "SELECT 1 FROM source_transaction WHERE corrects_txn_id=?", (r["txn_id"],))}
    children = db.rows(con, "SELECT batch_id, status, record_count, error_count FROM submission_batch WHERE parent_batch_id=?", (bid,))
    c = st.columns(3)
    c[0].metric("Open items", len(items))
    c[1].metric("Corrected, awaiting resubmission", len(corrected))
    c[2].metric("Resubmission batches", len(children))
    if children:
        table(children)
    if not items:
        st.success("No open items.")
    else:
        rows = [{"line": r["line_no"], "status": REC_BADGE.get(r["status"]), "txn": r["txn_id"], "source": r["source_system"],
                 "corrected": "✔" if r["txn_id"] in corrected else "",
                 "errors": " | ".join(m["msg"] for m in json.loads(r["messages_json"]) if m["sev"] == "ERROR")} for r in items]
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
        pick = st.selectbox("Correct record", [r["txn_id"] for r in items],
                            format_func=lambda t: next(f"line {r['line_no']} · txn {t} · {r['status']}" for r in items if r["txn_id"] == t))
        r = next(x for x in items if x["txn_id"] == pick)
        msgs = json.loads(r["messages_json"])
        for m in msgs:
            (st.error if m["sev"] == "ERROR" else st.warning)(f"{m['code']} · {m['msg']}")
        pck = [m for m in msgs if m["code"] == "PCK001"]
        if pck:
            m = pck[0]
            with st.expander(f"➕ Map '{m['source_value']}' to a {m['picklist']} option (adds an approved-on-save alias)"):
                opts = [o["option_code"] for o in db.rows(con, "SELECT DISTINCT option_code FROM picklist_option WHERE picklist_code=? AND status='APPROVED'", (m["picklist"],))]
                oc = st.selectbox("Canonical option", opts, key="alias_opt")
                eff = st.date_input("Alias effective", date(2020, 1, 1), key="alias_eff")
                if st.button("Save alias and approve as SME"):
                    with db.tx(con):
                        aid = db.add_pending(con, "picklist_option_alias", {"picklist_code": m["picklist"], "option_code": oc,
                                                                            "source_system": r["source_system"], "source_value": m["source_value"],
                                                                            "eff_date": eff.isoformat()}, actor, "Added from correction")
                        db.set_status(con, "picklist_option_alias", aid, "APPROVED", actor, "Approved from correction screen")
                    toast("Alias saved. Regenerate the period on ▶️ Bureau Run (or correct the source value) to pick it up.")
                    st.rerun()
        payload = json.loads(r["payload_json"])
        st.markdown("**Source values** (edit and save - the original transaction is kept; the correction is a new linked row)")
        ed = st.data_editor(pd.DataFrame({"attribute": list(payload), "value": [str(v) for v in payload.values()]}),
                            width="stretch", hide_index=True, disabled=["attribute"], key=f"ed_{pick}")
        note = st.text_input("Correction note", key=f"note_{pick}")
        if st.button("Save correction", type="primary", disabled=pick in corrected):
            newp = dict(zip(ed["attribute"], ed["value"]))
            E.correct_transaction(con, pick, newp, actor, note or "SME correction")
            toast(f"Correction saved for txn {pick}")
            st.rerun()
    st.divider()
    c = st.columns(2)
    if c[0].button("Create resubmission batch", disabled=not corrected):
        try:
            nb = E.resubmission_batch(con, bid, actor)
            st.session_state["batch_id"] = nb
            toast(f"Resubmission batch #{nb} created - validate / approve / submit it on ▶️ Bureau Run "
                  f"({b['lob_code']} {b['record_type']} {b['period_start']}).")
            st.rerun()
        except ValueError as ex:
            st.error(str(ex))
    with c[1]:
        reason = st.text_input("Reason to close with open items (optional)")
        if st.button("Close batch", disabled=b["status"] == "CLOSED"):
            try:
                E.close_batch(con, bid, actor, reason); toast("Batch closed"); st.rerun()
            except ValueError as ex:
                st.error(str(ex))


# ========================================================== SME workbench
def page_workbench():
    header("SME Validation Workbench", "Source → Canonical → Rules → Bureau, field by field. Approve the whole lineage or reject with a reason.")
    c = st.columns([2, 1, 1, 1.4])
    lob = c[0].selectbox("Line of business", LOB_CODES, format_func=lob_label, key="wb_lob")
    rt = c[1].selectbox("Record type", ["PREMIUM", "LOSS"], key="wb_rt")
    as_of = c[2].date_input("As of", date(2026, 9, 30), key="wb_asof",
                            help="Layouts, fields, codes and rules shown as they are in force on this date. Try 2027-01-01 for proposed changes.")
    only = c[3].selectbox("Show", ["All fields", "Needs approval", "Approved"], key="wb_show")
    rows = L.lineage(con, "ISO", lob, rt, as_of.isoformat())
    if not rows:
        st.warning("No layout in force on this date.")
        return
    st.caption(f"Layout version {rows[0]['layout_version']} · {len(rows)} fields · "
               f"{sum(r['overall'] == 'APPROVED' for r in rows)} fully approved")
    vis = [r for r in rows if only == "All fields" or (only == "Approved") == (r["overall"] == "APPROVED")]
    d = pd.DataFrame([{"select": False, "status": BADGE.get(r["overall"]), **{k: r[k] for k in (
        "seq", "position", "bureau_field", "format", "required", "canonical_element", "business_description",
        "source_guidewire", "source_duckcreek", "derivation", "picklist", "options", "transform_rule", "validation_rules",
        "aliases", "bureau_description")}} for r in vis])
    ed = st.data_editor(d, width="stretch", hide_index=True, height=440, key=f"wb_{lob}_{rt}_{as_of}_{only}",
                        disabled=[c for c in d.columns if c != "select"],
                        column_config={"select": st.column_config.CheckboxColumn("✓", width="small"),
                                       "business_description": st.column_config.TextColumn(width="large")})
    chosen = [vis[i] for i, v in enumerate(ed["select"]) if v] if not d.empty else []
    c = st.columns([3, 1, 1, 1.4])
    comment = c[0].text_input("SME comment", key="wb_comment")
    if c[1].button("Approve selected", type="primary", disabled=not chosen):
        n = L.approve_lineage_rows(con, chosen, actor, comment or "SME validated lineage")
        toast(f"{n} object(s) approved across source, canonical, pick list, rules and layout"); st.rerun()
    if c[2].button("Reject selected", disabled=not chosen or not comment, help="A comment is required to reject"):
        n = L.approve_lineage_rows(con, chosen, actor, comment, action="REJECTED")
        toast(f"{n} object(s) rejected"); st.rerun()
    pend = [r for r in rows if r["overall"] == "PENDING"]
    if c[3].button(f"Approve all pending ({len(pend)})", disabled=not pend):
        n = L.approve_lineage_rows(con, pend, actor, comment or "SME approved layout lineage")
        toast(f"{n} object(s) approved"); st.rerun()

    st.subheader("Field detail")
    seq = st.selectbox("Field", [r["seq"] for r in rows], format_func=lambda s: next(f"{s} · {r['bureau_field']} → {r['canonical_element']}"
                                                                                      for r in rows if r["seq"] == s))
    r = next(x for x in rows if x["seq"] == seq)
    st.dataframe(pd.DataFrame([{"object": k, "status": BADGE.get(v, v), "ids": ", ".join(map(str, r["_objects"].get(k, [])))}
                               for k, v in r["status_detail"].items()]), hide_index=True, width="stretch")
    t = st.tabs(["Canonical & aliases", "Source mapping", "Pick list → ISO codes", "Rules"])
    ids = r["_objects"]
    q = lambda tbl, key: db.rows(con, f"SELECT * FROM {tbl} WHERE {key} IN ({','.join(map(str, ids.get(tbl, []) or [0]))})")
    with t[0]:
        table(q("canonical_element", "element_id"), ["element_code", "element_name", "business_description", "data_type", "picklist_code",
                                                    "eff_date", "exp_date", "status", "approved_by"])
        table(q("element_alias", "alias_id"), ["alias_name", "alias_context", "eff_date", "exp_date", "status"])
    with t[1]:
        sm = q("source_mapping", "source_map_id")
        if sm:
            table(sm, ["source_system", "source_entity", "source_attribute", "source_data_type", "eff_date", "exp_date", "status"])
        else:
            st.info(f"Derived by rule {r['derivation'] or 'n/a'} - no source attribute.")
    with t[2]:
        if r["picklist"]:
            opts = q("picklist_option", "option_id")
            maps = {m["option_code"]: m for m in q("bureau_code_map", "code_map_id")}
            als = q("picklist_option_alias", "alias_id")
            table([{**o, "iso_code": maps.get(o["option_code"], {}).get("bureau_value", "⛔ none"),
                    "map_status": maps.get(o["option_code"], {}).get("status", ""),
                    "source_aliases": ", ".join(f"{a['source_system']}:{a['source_value']}" for a in als if a["option_code"] == o["option_code"])}
                   for o in opts], ["option_code", "option_name", "lob_scope", "iso_code", "source_aliases", "eff_date", "exp_date", "status", "map_status"])
        else:
            st.info("Not a pick-list field.")
    with t[3]:
        rr = q("business_rule", "rule_id")
        table(rr, ["rule_code", "rule_category", "rule_name", "business_description", "lob_scope", "record_type_scope", "severity",
                   "expression_json", "eff_date", "exp_date", "status"])


# ================================================================= generic editor
def meta_editor(tbl: str, cols: list[str], key_cols: list[str], where: str = "1=1", params=(), show_cols=None, label=""):
    """Effective-dated list + add new + change (supersede) for any metadata table."""
    k = db.META_TABLES[tbl]
    c = st.columns([1, 1, 2])
    hist = c[0].toggle("Show history", key=f"h_{tbl}_{label}")
    as_of = c[1].date_input("As of", date.today(), key=f"a_{tbl}_{label}", disabled=hist)
    rows = db.rows(con, f"SELECT * FROM {tbl} WHERE {where} ORDER BY {', '.join(key_cols)}, eff_date", params)
    if not hist:
        rows = [r for r in rows if r["eff_date"] <= as_of.isoformat() <= r["exp_date"] or r["status"] == "PENDING"]
    table(rows, [k] + (show_cols or cols) + ["eff_date", "exp_date", "status", "created_by", "approved_by", "supersedes_id"], height=320)
    a, b = st.columns(2)
    with a.expander(f"➕ Add new {tbl.replace('_', ' ')}"):
        with st.form(f"add_{tbl}_{label}"):
            vals = {col: st.text_input(col, key=f"n_{tbl}_{col}_{label}") for col in cols}
            eff = st.date_input("Effective date", date.today(), key=f"ne_{tbl}_{label}")
            if st.form_submit_button("Submit for SME approval"):
                missing = [kc for kc in key_cols if not vals.get(kc)]
                if missing:
                    st.error(f"Required: {', '.join(missing)}")
                else:
                    with db.tx(con):
                        db.add_pending(con, tbl, {**{x: (v or None) for x, v in vals.items()}, "eff_date": eff.isoformat()}, actor, "Added in app")
                    toast(f"New {tbl} submitted - approve it in 🗳 Approval Queue"); st.rerun()
    with b.expander(f"✏️ Change (supersede) an existing {tbl.replace('_', ' ')}"):
        if rows:
            rid = st.selectbox("Record id", [r[k] for r in rows], key=f"s_{tbl}_{label}")
            cur = next(r for r in rows if r[k] == rid)
            with st.form(f"sup_{tbl}_{label}"):
                vals = {col: st.text_input(col, value=str(cur.get(col) or ""), key=f"u_{tbl}_{col}_{rid}_{label}") for col in cols}
                eff = st.date_input("New version effective", date.today(), key=f"ue_{tbl}_{rid}_{label}")
                why = st.text_input("Reason")
                if st.form_submit_button("Submit change for SME approval"):
                    try:
                        with db.tx(con):
                            db.supersede(con, tbl, rid, {x: (v or None) for x, v in vals.items()}, eff.isoformat(), actor, why)
                        toast("Change submitted. Current record stays in force until the SME approves the new one."); st.rerun()
                    except ValueError as ex:
                        st.error(str(ex))


# ================================================================ layouts page
def page_layouts():
    header("Layouts", "Effective-dated ISO record layouts per line and record type - versions, field positions, compare, create")
    c = st.columns([2, 1])
    lob = c[0].selectbox("Line of business", LOB_CODES, format_func=lob_label, key="ly_lob")
    rt = c[1].selectbox("Record type", ["PREMIUM", "LOSS"], key="ly_rt")
    vers = db.rows(con, "SELECT * FROM layout_version WHERE lob_code=? AND record_type=? ORDER BY version_no", (lob, rt))
    table(vers, ["layout_id", "version_no", "eff_date", "exp_date", "status", "source_file", "approved_by", "notes"])
    t = st.tabs(["Fields", "Compare versions", "Create new version", "Import ISO layout workbook"])
    with t[0]:
        v = st.selectbox("Version", [x["layout_id"] for x in vers], index=len(vers) - 1,
                         format_func=lambda i: next(f"v{x['version_no']} ({x['eff_date']} → {x['exp_date']}, {x['status']})" for x in vers if x["layout_id"] == i))
        fl = db.rows(con, "SELECT * FROM layout_field WHERE layout_id=? ORDER BY seq", (v,))
        probs = E.layout_problems(fl)
        if not probs:
            st.success("Positions contiguous, 150 bytes")
        for p in probs:
            st.error(p)
        table(fl, ["seq", "bureau_field_name", "start_pos", "length", "field_format", "required", "element_code", "transform_rule_code",
                   "bureau_description", "eff_date", "exp_date", "status"], height=420)
    with t[1]:
        if len(vers) < 2:
            st.info("Only one version exists for this layout.")
        else:
            a, b = st.columns(2)
            va = a.selectbox("From", [x["version_no"] for x in vers], key="cmp_a")
            vb = b.selectbox("To", [x["version_no"] for x in vers], index=len(vers) - 1, key="cmp_b")
            fa = {f["seq"]: f for f in db.rows(con, "SELECT f.* FROM layout_field f JOIN layout_version v ON v.layout_id=f.layout_id WHERE v.lob_code=? AND v.record_type=? AND v.version_no=?", (lob, rt, va))}
            fb = {f["seq"]: f for f in db.rows(con, "SELECT f.* FROM layout_field f JOIN layout_version v ON v.layout_id=f.layout_id WHERE v.lob_code=? AND v.record_type=? AND v.version_no=?", (lob, rt, vb))}
            diff = []
            for s in sorted(set(fa) | set(fb)):
                x, y = fa.get(s), fb.get(s)
                key = ("bureau_field_name", "start_pos", "length", "field_format", "element_code", "transform_rule_code")
                if not x or not y or any(x[k] != y[k] for k in key):
                    diff.append({"seq": s, "change": "added" if not x else "removed" if not y else "changed",
                                 f"v{va}": f"{x['bureau_field_name']} {x['start_pos']}/{x['length']} {x['element_code']}" if x else "",
                                 f"v{vb}": f"{y['bureau_field_name']} {y['start_pos']}/{y['length']} {y['element_code']}" if y else ""})
            if diff:
                table(diff)
            else:
                st.info("No differences.")
    with t[2]:
        base = st.selectbox("Start from version", [x["layout_id"] for x in vers], index=len(vers) - 1, key="nv_base",
                            format_func=lambda i: next(f"v{x['version_no']}" for x in vers if x["layout_id"] == i))
        eff = st.date_input("New version effective date", date(2027, 7, 1), key="nv_eff")
        fl = db.rows(con, "SELECT seq, bureau_field_name, start_pos, length, field_format, required, element_code, transform_rule_code, bureau_description FROM layout_field WHERE layout_id=? ORDER BY seq", (base,))
        ed = st.data_editor(pd.DataFrame(fl), num_rows="dynamic", width="stretch", hide_index=True, key=f"nv_{base}")
        recs = ed.to_dict("records")
        for r in recs:
            for k in ("seq", "start_pos", "length"):
                r[k] = int(r[k]) if pd.notna(r[k]) else 0
        probs = E.layout_problems(sorted(recs, key=lambda r: r["seq"]))
        for p in probs:
            st.error(p)
        if st.button("Submit new version for SME approval", disabled=bool(probs), type="primary"):
            bv = next(x for x in vers if x["layout_id"] == base)
            with db.tx(con):
                lid = db.insert(con, "layout_version", {"bureau_code": "ISO", "lob_code": lob, "record_type": rt,
                                                        "version_no": max(x["version_no"] for x in vers) + 1, "record_length": 150,
                                                        "source_file": "Edited in app", "eff_date": eff.isoformat(), "exp_date": db.OPEN_END,
                                                        "status": "PENDING", "created_by": actor, "supersedes_id": bv["layout_id"]})
                db.insert(con, "approval_log", {"object_table": "layout_version", "object_id": lid, "action": "SUBMITTED", "actor": actor,
                                                "comment": f"New version from v{bv['version_no']}"})
                for r in recs:
                    db.add_pending(con, "layout_field", {**r, "layout_id": lid, "eff_date": eff.isoformat()}, actor)
            toast("New layout version submitted - approve it in ✅ SME Validation Workbench (As of = its effective date)"); st.rerun()
    with t[3]:
        st.caption("Upload an ISO layout workbook in the same format as the supplied files (Field #, Field Name, Position, Length, Data Type, "
                   "Description). Each sheet becomes a PENDING new version; field names are matched to canonical elements through aliases.")
        up = st.file_uploader("ISO layout workbook (.xlsx)", type=["xlsx"], key="lay_up")
        eff = st.date_input("Effective date of imported layouts", date(2027, 1, 1), key="imp_eff")
        if up and st.button("Import as pending versions"):
            import tempfile
            from iso_bureau.layouts import parse_workbook
            with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as fh:
                fh.write(up.getvalue())
            lays = parse_workbook(Path(fh.name))
            alias = {a["alias_name"]: a["element_code"] for a in db.rows(con, "SELECT alias_name, element_code FROM element_alias WHERE status='APPROVED'")}
            msgs = []
            with db.tx(con):
                for lay in lays:
                    prev = db.one(con, "SELECT * FROM layout_version WHERE lob_code=? AND record_type=? ORDER BY version_no DESC", (lay.lob, lay.record_type))
                    lid = db.add_pending(con, "layout_version", {"bureau_code": "ISO", "lob_code": lay.lob, "record_type": lay.record_type,
                                                                 "version_no": (prev["version_no"] + 1) if prev else 1, "record_length": 150,
                                                                 "source_file": up.name, "eff_date": eff.isoformat(),
                                                                 "supersedes_id": prev["layout_id"] if prev else None,
                                                                 "notes": " | ".join(lay.findings) or None}, actor, "Imported")
                    for f in lay.fields:
                        el = alias.get(f.name, "UNMAPPED")
                        if el == "UNMAPPED":
                            msgs.append(f"{lay.lob} {lay.record_type} field {f.seq} '{f.name}' has no canonical alias - map it before approval")
                        pl = db.one(con, "SELECT picklist_code FROM canonical_element WHERE element_code=?", (el,))
                        db.add_pending(con, "layout_field", {"layout_id": lid, "seq": f.seq, "bureau_field_name": f.name, "start_pos": f.start,
                                                             "length": f.length, "field_format": f.data_type, "required": "Y", "element_code": el,
                                                             "transform_rule_code": seed.transform_for(el, f.data_type, lay.lob, pl and pl["picklist_code"]),
                                                             "bureau_description": f.description, "eff_date": eff.isoformat()}, actor)
            toast(f"Imported {len(lays)} layout(s) as pending. " + (" ".join(msgs[:5]) if msgs else "All fields mapped."))
            st.rerun()


# ============================================================ canonical page
def page_canonical():
    header("Canonical Model", "Data elements, business descriptions, aliases and source-system mappings - all effective-dated and SME-approved")
    t = st.tabs(["Data elements", "Element aliases", "Source mappings"])
    with t[0]:
        meta_editor("canonical_element", ["element_code", "element_name", "business_description", "data_type", "picklist_code", "notes"],
                    ["element_code"], label="ce")
    with t[1]:
        meta_editor("element_alias", ["element_code", "alias_name", "alias_context"], ["element_code", "alias_name"], label="ea")
    with t[2]:
        meta_editor("source_mapping", ["source_system", "source_entity", "source_attribute", "source_data_type", "element_code"],
                    ["source_system", "source_attribute"], label="sm")


def page_picklists():
    header("Pick Lists", "Lists, options (canonical codes), source aliases and ISO bureau codes - by line, effective and expiration date")
    pls = db.rows(con, "SELECT DISTINCT picklist_code FROM picklist ORDER BY 1")
    pl = st.selectbox("Pick list", [p["picklist_code"] for p in pls], key="pl_sel")
    t = st.tabs(["Options", "ISO code map", "Source value aliases", "Pick list & aliases"])
    with t[0]:
        meta_editor("picklist_option", ["picklist_code", "lob_scope", "option_code", "option_name", "business_description"],
                    ["picklist_code", "option_code"], "picklist_code=?", (pl,), label="po")
    with t[1]:
        meta_editor("bureau_code_map", ["bureau_code", "lob_scope", "picklist_code", "option_code", "bureau_value"],
                    ["picklist_code", "option_code"], "picklist_code=?", (pl,), label="bm")
    with t[2]:
        meta_editor("picklist_option_alias", ["picklist_code", "option_code", "source_system", "source_value"],
                    ["picklist_code", "source_value"], "picklist_code=?", (pl,), label="oa")
    with t[3]:
        meta_editor("picklist", ["picklist_code", "picklist_name", "business_description"], ["picklist_code"], "picklist_code=?", (pl,), label="pl")
        meta_editor("picklist_alias", ["picklist_code", "alias_name", "alias_context"], ["picklist_code", "alias_name"], "picklist_code=?", (pl,), label="pa")


def page_rules():
    header("Business Rules", "Derivation, validation and transformation rules as JSON - read by the engine and by AI - effective-dated and SME-approved")
    c = st.columns(3)
    cat = c[0].selectbox("Category", ["VALIDATION", "DERIVATION", "TRANSFORMATION"], key="r_cat")
    meta_editor("business_rule", ["rule_code", "rule_name", "rule_category", "lob_scope", "record_type_scope", "state_scope", "element_code",
                                  "expression_json", "severity", "message", "business_description"], ["rule_code"],
                "rule_category=?", (cat,), show_cols=["rule_code", "rule_name", "lob_scope", "record_type_scope", "element_code", "severity",
                                                     "business_description", "expression_json"], label=cat)
    st.subheader("Try a validation rule")
    rules = db.rows(con, "SELECT * FROM business_rule WHERE rule_category='VALIDATION' ORDER BY rule_code, eff_date DESC")
    rc = st.selectbox("Rule", [r["rule_id"] for r in rules], format_func=lambda i: next(f"{r['rule_code']} · {r['rule_name']} ({r['status']})" for r in rules if r["rule_id"] == i))
    r = next(x for x in rules if x["rule_id"] == rc)
    st.code(json.dumps(json.loads(r["expression_json"]), indent=2), language="json")
    sample = st.text_area("Canonical record (JSON)", json.dumps({"POLICY_NUMBER": "HOGW100123", "POLICY_EFF_DATE": "2026-07-01", "POLICY_EXP_DATE": "2027-07-01",
                                                                 "LOSS_DATE": "2026-08-12", "ACCT_DATE": "2026-09-30", "CLAIM_STATUS": "CL",
                                                                 "OS_RESERVE": 0, "WRITTEN_PREMIUM": 125.5, "TRANSACTION_TYPE": "NB",
                                                                 "RISK_ZIP": "07001", "EXPOSURE": 1}, indent=1), height=200)
    try:
        res = E.eval_check(json.loads(r["expression_json"]), r["element_code"], json.loads(sample),
                           {"batch.period_start": "2026-07-01", "batch.period_end": "2026-09-30", "batch.lob": "HO"})
        {True: st.success, False: st.error, None: st.info}[res]({True: "PASS", False: f"FAIL - {r['message']}", None: "Not applicable to this record"}[res])
    except Exception as ex:  # noqa: BLE001
        st.error(f"Could not evaluate: {ex}")


# ============================================================ approval queue
def page_queue():
    header("Approval Queue", "Everything awaiting the SME. Approving a change expires the record it replaces on the day before it takes effect.")
    counts = db.pending_counts(con)
    opts = [t for t, n in counts.items() if n] or list(counts)
    tbl = st.selectbox("Object", opts, format_func=lambda t: f"{t} ({counts[t]} pending)")
    k = db.META_TABLES[tbl]
    rows = db.rows(con, f"SELECT * FROM {tbl} WHERE status='PENDING' ORDER BY {k}")
    if not rows:
        st.success("Nothing pending.")
        return
    d = pd.DataFrame(rows)
    d.insert(0, "select", False)
    drop = [c for c in ("created_at", "approved_by", "approved_at", "status") if c in d.columns]
    ed = st.data_editor(d.drop(columns=drop), width="stretch", hide_index=True, height=420,
                        disabled=[c for c in d.columns if c != "select"], key=f"q_{tbl}")
    sel = [int(x) for x in ed.loc[ed["select"], k]]
    c = st.columns([3, 1, 1, 1])
    com = c[0].text_input("Comment")
    if c[1].button("Approve selected", type="primary", disabled=not sel):
        with db.tx(con):
            for i in sel:
                db.set_status(con, tbl, i, "APPROVED", actor, com)
        toast(f"{len(sel)} approved"); st.rerun()
    if c[2].button("Reject selected", disabled=not sel or not com):
        with db.tx(con):
            for i in sel:
                db.set_status(con, tbl, i, "REJECTED", actor, com)
        toast(f"{len(sel)} rejected"); st.rerun()
    if c[3].button(f"Approve all {len(rows)}"):
        with db.tx(con):
            for r in rows:
                db.set_status(con, tbl, r[k], "APPROVED", actor, com or "Bulk approval")
        toast(f"{len(rows)} approved"); st.rerun()


def page_templates():
    header("SME Templates", "Download a template, enter NEW records only, upload. Keys, status and audit columns are added by the system.")
    tabs = st.multiselect("Tables", list(T.SPECS), default=list(T.SPECS))
    st.download_button("⬇ Download template", T.build_template(tabs), file_name="SI2_ISO_Bureau_SME_Template.xlsx")
    up = st.file_uploader("⬆ Upload completed template", type=["xlsx"])
    if up:
        data = T.read_upload(up.getvalue())
        res = T.check_and_load(con, data, actor, commit=False)
        if not res:
            st.info("No records found in the upload.")
            return
        table(res)
        errs = sum(r["result"] == "error" for r in res)
        if errs:
            st.error(f"{errs} row(s) have errors - fix and re-upload. Nothing was loaded.")
        elif st.button(f"Load {len(res)} record(s) as PENDING", type="primary"):
            T.check_and_load(con, data, actor, commit=True)
            toast(f"{len(res)} record(s) loaded - approve them in 🗳 Approval Queue"); st.rerun()


def page_audit():
    header("Audit Trail", "Every submission, approval, rejection and expiry - nothing is ever deleted or overwritten")
    t = st.tabs(["Metadata approvals", "Batch lifecycle", "Source corrections"])
    with t[0]:
        tb = st.selectbox("Object", ["(all)"] + list(db.META_TABLES), key="au_t")
        q = "SELECT * FROM approval_log" + ("" if tb == "(all)" else " WHERE object_table=?") + " ORDER BY log_id DESC"
        table(db.rows(con, q, () if tb == "(all)" else (tb,)), height=460)
    with t[1]:
        table(db.rows(con, """SELECT e.at, e.batch_id, b.lob_code, b.record_type, b.period_start, e.status_from, e.status_to, e.actor, e.comment
                              FROM batch_event e JOIN submission_batch b ON b.batch_id=e.batch_id ORDER BY e.event_id DESC"""), height=460)
    with t[2]:
        table(db.rows(con, """SELECT n.txn_id, n.corrects_txn_id, n.source_system, n.source_txn_key, n.lob_code, n.record_type,
                                     n.corrected_by, n.correction_note, n.loaded_at FROM source_transaction n WHERE n.corrects_txn_id IS NOT NULL
                              ORDER BY n.txn_id DESC"""))


# ============================================================ data access
ALL_TABLES = ["bureau", "line_of_business", *db.META_TABLES, "approval_log", "source_transaction",
              "submission_batch", "submission_record", "batch_event"]
EXCEL_CELL_LIMIT = 32000  # Excel holds at most 32,767 characters per cell


def _table_df(tbl: str) -> pd.DataFrame:
    return pd.DataFrame(db.rows(con, f"SELECT * FROM {tbl}"))


def _excel_export() -> bytes:
    bio = io.BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as xw:
        pd.DataFrame([{"table": t, "rows": db.one(con, f"SELECT COUNT(*) n FROM {t}")["n"]} for t in ALL_TABLES]) \
            .to_excel(xw, sheet_name="Tables", index=False)
        for t in ALL_TABLES:
            d = _table_df(t)
            for c in d.columns:
                if d[c].dtype == object:
                    d[c] = d[c].map(lambda v: v[:EXCEL_CELL_LIMIT] if isinstance(v, str) else v)
            d.to_excel(xw, sheet_name=t[:31], index=False)
    return bio.getvalue()


def _sqlite_copy() -> bytes:
    """Consistent copy of the live SQLite file (safe while the app is running)."""
    import sqlite3
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "bureau_reporting.db"
        dst = sqlite3.connect(target)
        con.backup(dst)
        dst.close()
        return target.read_bytes()


def page_data():
    header("Data", "See every table, export everything to Excel, or download the database itself")
    st.caption(f"Database: {db.describe(con)}")
    counts = [{"table": t, "rows": db.one(con, f"SELECT COUNT(*) n FROM {t}")["n"]} for t in ALL_TABLES]
    t = st.tabs(["Table viewer", "Export / download"])
    with t[0]:
        c = st.columns([2, 3])
        tbl = c[0].selectbox("Table", ALL_TABLES, format_func=lambda x: f"{x} ({next(r['rows'] for r in counts if r['table'] == x)} rows)")
        find = c[1].text_input("Filter rows containing (optional)")
        d = _table_df(tbl)
        if find and not d.empty:
            d = d[d.astype(str).apply(lambda col: col.str.contains(find, case=False, regex=False)).any(axis=1)]
        st.caption(f"{len(d)} row(s)" + (" - showing the first 5,000" if len(d) > 5000 else ""))
        st.dataframe(d.head(5000), width="stretch", hide_index=True, height=480)
        st.download_button(f"Download {tbl} as CSV", d.to_csv(index=False).encode("utf-8"), file_name=f"{tbl}.csv", mime="text/csv")
    with t[1]:
        table(counts)
        a, b = st.columns(2)
        with a:
            st.markdown("**Excel workbook**: one sheet per table, ready to share.")
            if st.button("Prepare Excel export"):
                st.session_state["_xlsx"] = _excel_export()
            if st.session_state.get("_xlsx"):
                st.download_button("Download SI2_ISO_Bureau_Data.xlsx", st.session_state["_xlsx"], file_name="SI2_ISO_Bureau_Data.xlsx",
                                   mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        with b:
            if db.backend() == "mssql":
                st.markdown("**Database**: this app is running on SQL Server. Open it directly in SSMS.")
            else:
                st.markdown("**SQLite database file**: open it with the free *DB Browser for SQLite* (sqlitebrowser.org) "
                            "or any SQLite tool.")
                st.download_button("Download bureau_reporting.db", _sqlite_copy(), file_name="bureau_reporting.db",
                                   mime="application/x-sqlite3")
        st.caption("The online demo database is rebuilt when Streamlit restarts the app, so download anything you want to keep.")



ROUTES = {"🏠 Dashboard": page_dashboard, "▶️ Bureau Run": page_run, "🛠 Corrections & Resubmit": page_corrections,
 "✅ SME Validation Workbench": page_workbench, "📐 Layouts": page_layouts, "🧬 Canonical Model": page_canonical,
 "📋 Pick Lists": page_picklists, "⚙️ Business Rules": page_rules, "🗳 Approval Queue": page_queue,
 "⬇⬆ SME Templates": page_templates, "📜 Audit Trail": page_audit,
 "🗄 Data": page_data}
_ = ROUTES[page]()
branding.note_synthetic()
branding.footer()
