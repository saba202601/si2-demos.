"""SI² Bureau Reporting Workbench.

Spec PDFs -> field catalog -> source connection -> canonical model -> auto mapping (fields, aliases,
pick lists) -> SME approval queue -> submission files (fixed width + flat CSV) -> bureau edits ->
error file -> SI² revisions -> SME approval -> resubmission.
"""
import datetime as dt
import io
import json

import pandas as pd
import streamlit as st

from bureau import canonical as cn
from bureau import catalog, edits, generate as gen, revise, source, specparse
from bureau import gaps as NG
from si2_common import branding, gate, gaps_ui

branding.page("Bureau Reporting Workbench",
              "NCCI / WCIO statistical, policy and data call reporting: from spec PDF to accepted submission.")
gate.require_access()

SPEC_LABEL = {s: f"{s} · {i['title']}" for s, i in catalog.SPEC_INFO.items()}
STEPS = ["Overview", "1 · Spec library", "2 · Source connection", "3 · Canonical model & mapping",
         "4 · SME approval queue", "5 · Generate submission", "6 · Submit & bureau response",
         "7 · Revise & resubmit", "Audit trail"]


# ------------------------------------------------------------------------------------------ state
@st.cache_data(show_spinner=False)
def _initial():
    src = source.build()
    smap = cn.auto_map_source(src)
    fmaps = {s: gen.auto_map_fields(s) for s in catalog.SPEC_INFO}
    return src, smap, fmaps


def init():
    if "ready" in st.session_state:
        return
    src, smap, fmaps = _initial()
    ss = st.session_state
    ss.src, ss.smap, ss.fmaps = src, smap.copy(), {k: v.copy() for k, v in fmaps.items()}
    ss.overrides, ss.excluded, ss.subs, ss.audit = {}, set(), [], []
    ss.carrier = source.CARRIER_CODE
    rebuild_canonical()
    ss.vmaps = {s: gen.auto_value_map(ss.canon, ss.fmaps[s]) for s in catalog.SPEC_INFO}
    log("System", "Workbench initialised", f"{len(catalog.load()):,} spec fields loaded; demo source connected")
    ss.ready = True


def rebuild_canonical():
    ss = st.session_state
    ss.canon = cn.build_canonical(ss.src, ss.smap, ss.carrier, ss.overrides)


def log(who, event, detail=""):
    st.session_state.audit.append({"time": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "by": who,
                                   "event": event, "detail": detail})


def sme():
    return st.session_state.get("sme_name") or "SME"


def queue_counts():
    ss = st.session_state
    s = int((ss.smap.status == "Needs SME review").sum())
    f = sum(int((m.status == "Needs SME review").sum()) for m in ss.fmaps.values())
    v = sum(int((m.status == "Needs SME review").sum()) for m in ss.vmaps.values())
    subs = sum(1 for x in ss.subs if x["status"] == "Pending SME approval")
    return s, f, v, subs


def sub_label(x):
    return f'{x["id"]} · {x["spec"]} rev {x["revision"]} · {x["status"]}'


def pick_sub(label, subs, key):
    labels = [sub_label(x) for x in subs][::-1]
    chosen = st.selectbox(label, labels, key=key)
    return next(x for x in subs if sub_label(x) == chosen)


def pick_spec(key, label="Specification"):
    chosen = st.selectbox(label, list(SPEC_LABEL.values()), key=key)
    return chosen.split(" · ")[0]


def fw_ruler(width):
    tens = "".join(f"{i // 10 % 10}" if i % 10 == 0 else " " for i in range(1, width + 1))
    ones = "".join(str(i % 10) for i in range(1, width + 1))
    return tens + "\n" + ones


init()
ss = st.session_state

with st.sidebar:
    st.markdown("**Workflow**")
    step = st.radio("Step", STEPS, label_visibility="collapsed", key="step")
    st.divider()
    st.text_input("SME name", key="sme_name", placeholder="Your name for approvals")
    st.text_input("Carrier code", value=ss.carrier, key="carrier_input", max_chars=5,
                  help="NCCI-assigned carrier code reported in positions 1-5.")
    if ss.carrier_input != ss.carrier and ss.carrier_input.isdigit() and len(ss.carrier_input) == 5:
        ss.carrier = ss.carrier_input
        rebuild_canonical()
        log(sme(), "Carrier code changed", ss.carrier)
    s, f, v, subs = queue_counts()
    st.caption(f"Queue: {s + f + v} mapping items · {subs} submissions awaiting approval")


# ------------------------------------------------------------------------------------------ Overview
if step == "Overview":
    s, f, v, subs = queue_counts()
    cat = catalog.load()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Spec fields catalogued", f"{len(cat):,}")
    c2.metric("Pick-list values", f"{int(cat.codes.str.len().sum()):,}")
    c3.metric("Mapping items for SME", s + f + v)
    c4.metric("Submissions", len(ss.subs))
    st.subheader("How it works")
    st.graphviz_chart("""
digraph G { rankdir=LR; bgcolor="transparent";
 node [shape=box, style="rounded,filled", fillcolor="#FFFFFF", color="#0B1B2B", fontname="Helvetica", fontsize=10];
 edge [color="#2B4CF2"];
 pdf [label="WCIO spec PDFs\\nWCSTAT · WCPOLS\\nWCIND · WCMED"]; lib [label="Spec library\\nfields · aliases\\npick lists · formats"];
 src [label="Source system\\npolicy · claims\\nbill review"]; can [label="SI² canonical\\nbureau model"];
 map [label="Auto mapping\\nwith confidence"]; q [label="SME approval\\nqueue", fillcolor="#E7ECFE"];
 gen [label="Submission files\\nfixed width + CSV"]; dco [label="Bureau edits\\nerror file"]; rev [label="SI² revisions\\n(rules or Claude)"];
 pdf -> lib -> map; src -> can -> map -> q -> gen -> dco -> rev -> q; }""", width="stretch")
    st.markdown(
        "Start in **Spec library** to see what was read from your PDFs, connect a **source**, review the "
        "**auto mapping**, approve it in the **SME queue**, then **generate** WCSTAT, WCPOLS, WCIND or WCMED files "
        "for one or more accounting dates. Each submission needs SME approval before it goes to the bureau; errors "
        "come back as an error file that SI² turns into proposed revisions for you to approve and resubmit.")

# ------------------------------------------------------------------------------------------ 1. Spec library
elif step == STEPS[1]:
    st.subheader("Spec library")
    st.dataframe(catalog.summary(), hide_index=True, width="stretch")
    tab_browse, tab_lists, tab_qa, tab_up = st.tabs(["Browse fields", "Pick lists", "Layout QA", "Upload a spec PDF"])
    with tab_browse:
        c1, c2 = st.columns([1, 2])
        with c1:
            spec = pick_spec("lib_spec")
        recs = catalog.records_for(spec)
        rec_labels = [f"{k} · {n}" for k, n in zip(recs.record_key, recs.record_name)]
        key = recs.record_key.iloc[rec_labels.index(c2.selectbox("Record", rec_labels, key="lib_rec"))]
        fields = catalog.record_fields(spec, key)
        show = fields.assign(pick_list=fields.codes.str.len(), aliases=fields.aliases.str.join(", "),
                             positions=fields.start.astype(str) + "-" + fields.end.astype(str))
        st.dataframe(show[["field_no", "name", "class", "positions", "length", "format", "implied_decimals",
                           "constant", "pick_list", "not_applicable", "aliases"]], hide_index=True, width="stretch",
                     column_config={"pick_list": st.column_config.NumberColumn("pick list values"),
                                    "implied_decimals": st.column_config.NumberColumn("decimals")})
        pick = st.selectbox("Field detail", fields.name, key="lib_field")
        fr = fields[fields.name == pick].iloc[0]
        st.caption(fr.description[:600] or "No description captured.")
    with tab_lists:
        spec = pick_spec("pl_spec")
        cat = catalog.load()
        d = cat[(cat.spec == spec) & (cat.codes.str.len() > 0)]
        opt = (d.record_name + " · " + d.name).tolist()
        sel = st.selectbox("Pick list", opt, key="pl_field")
        r = d.iloc[opt.index(sel)]
        st.caption(f"Source: {r.pick_list_source} · parse confidence {r.pick_list_confidence:.0%}")
        st.dataframe(pd.DataFrame(r.codes).rename(columns={"na_states": "not applicable in"}), hide_index=True, width="stretch")
    with tab_qa:
        spec = pick_spec("qa_spec")
        qa = catalog.layout_qa(spec)
        st.write(f"{(qa.status == 'Complete').sum()} of {len(qa)} record layouts cover every position with no gaps.")
        st.dataframe(qa, hide_index=True, width="stretch")
    with tab_up:
        st.write("Upload a WCIO spec PDF to read its layouts with the same parser that built this library.")
        up = st.file_uploader("Spec PDF", type="pdf", key="spec_pdf")
        if up is not None:
            with st.spinner("Reading the PDF…"):
                text = specparse.pdf_to_text(up.getvalue())
                spec = specparse.detect_spec(text) or "WCSTAT"
                parsed = pd.DataFrame(specparse.parse_text(text, spec))
            lib = catalog.load()
            lib = lib[lib.spec == spec]
            keys = set(zip(lib.start, lib.end, lib.name.str[:20]))
            matched = sum((r.start, r.end, str(r["name"]).upper()[:20]) in keys for _, r in parsed.iterrows())
            st.success(f"Detected {spec}: {len(parsed):,} fields, {int((parsed.codes.str.len() > 0).sum())} pick lists. "
                       f"{matched:,} fields match the library exactly.")
            st.dataframe(parsed[["page_record", "record_title", "field_no", "name", "class", "start", "end", "length", "format"]].head(300),
                         hide_index=True, width="stretch")
            log(sme(), "Spec PDF read", f"{up.name}: {spec}, {len(parsed)} fields")

# ------------------------------------------------------------------------------------------ 2. Source
elif step == STEPS[2]:
    st.subheader("Source connection")
    conn = st.radio("Connection", ["SI² demo: policy admin, claims and bill review (connected)",
                                   "Upload CSV extracts", "Database (ODBC / JDBC)"], key="conn")
    if conn.startswith("Database"):
        st.info("Direct database connections are set up during onboarding with your IT team. "
                "Use CSV extracts or the demo source here.")
    elif conn.startswith("Upload"):
        st.write("Upload extracts that use the same table names; each file replaces that table and the mapping re-runs.")
        tbl = st.selectbox("Replace table", list(ss.src), key="up_tbl")
        f = st.file_uploader("CSV extract", type="csv", key="up_csv")
        if f is not None and st.button("Load extract", type="primary"):
            ss.src[tbl] = pd.read_csv(f, dtype=str).fillna("")
            ss.smap = cn.auto_map_source(ss.src)
            rebuild_canonical()
            ss.vmaps = {s: gen.auto_value_map(ss.canon, ss.fmaps[s]) for s in catalog.SPEC_INFO}
            log(sme(), "Source extract loaded", f"{tbl}: {len(ss.src[tbl])} rows")
            st.success(f"{tbl} replaced with {len(ss.src[tbl]):,} rows. Mapping re-run.")
    st.dataframe(source.describe(ss.src), hide_index=True, width="stretch")
    t = st.selectbox("Preview table", list(ss.src), key="prev_tbl")
    df = ss.src[t]
    prof = pd.DataFrame({"column": df.columns, "blank": [(df[c].astype(str).str.strip() == "").sum() for c in df],
                         "distinct": [df[c].nunique() for c in df], "example": [str(df[c].iloc[0]) for c in df]})
    c1, c2 = st.columns([3, 2])
    c1.dataframe(df.head(50), hide_index=True, width="stretch")
    c2.dataframe(prof, hide_index=True, width="stretch")
    st.download_button("Download this table (CSV)", df.to_csv(index=False), f"{t}.csv", "text/csv")

# ------------------------------------------------------------------------------------------ 3. Mapping
elif step == STEPS[3]:
    st.subheader("Canonical model & mapping")
    t1, t2, t3, t4, t5 = st.tabs(["Source → canonical", "Canonical → bureau fields", "Pick-list values", "Canonical tables",
                                  "🧩 Canonical gaps"])
    with t1:
        st.caption("SI² matched each canonical attribute to a source column using names, abbreviations and synonyms.")
        m = ss.smap
        st.write(f"{(m.band == 'High').sum()} high confidence · {(m.band == 'Medium').sum()} medium · "
                 f"{(m.source_column == '').sum()} unmapped")
        opts = [""] + sorted({c for t in ss.src.values() for c in t.columns})
        ed = st.data_editor(m[["canonical_table", "canonical_column", "description", "source_table", "source_column",
                               "confidence", "band", "status"]], hide_index=True, width="stretch", key="ed_smap",
                            disabled=["canonical_table", "canonical_column", "description", "source_table", "confidence", "band"],
                            column_config={"source_column": st.column_config.SelectboxColumn(options=opts),
                                           "status": st.column_config.SelectboxColumn(options=["Auto-approved", "Needs SME review", "SME approved", "Unmapped"]),
                                           "confidence": st.column_config.ProgressColumn(min_value=0, max_value=1, format="%.2f")})
        if st.button("Save source mapping", type="primary"):
            changed = (ed.source_column != m.source_column) | (ed.status != m.status)
            ss.smap.loc[changed.values, ["source_column", "status"]] = ed.loc[changed, ["source_column", "status"]].values
            ss.smap.loc[changed.values & (ss.smap.status == "Needs SME review"), "status"] = "SME approved"
            rebuild_canonical()
            log(sme(), "Source mapping saved", f"{int(changed.sum())} rows changed")
            st.success("Saved. Canonical tables rebuilt.")
    with t2:
        spec = pick_spec("fm_spec")
        fm = ss.fmaps[spec]
        flt = st.radio("Show", ["Needs SME review", "Mapped", "All"], horizontal=True, key="fm_flt")
        view = fm[fm.status == "Needs SME review"] if flt.startswith("Needs") else fm[fm.source.isin(["Canonical", "SI² derived"])] if flt == "Mapped" else fm
        cols = [""] + sorted({f"{t}.{c}" for t, cs in cn.SCHEMA.items() for c in cs} |
                             {f"{r.canonical_table}.{r.canonical_column}" for r in ss.smap.itertuples()}) + \
            sorted(f"{t}.{c}" for t, cs in cn.DERIVED.items() for c in cs) + \
            sorted(f"{t}.{c}" for t, cs in gen.DERIVED_COLS.items() for c in cs)
        ed = st.data_editor(view[["field_id", "record_name", "field_no", "field_name", "start", "end", "source", "canonical",
                                  "confidence", "status"]], hide_index=True, width="stretch", key=f"ed_fm_{spec}_{flt}",
                            disabled=["field_id", "record_name", "field_no", "field_name", "start", "end", "source", "confidence"],
                            column_config={"field_id": None, "canonical": st.column_config.SelectboxColumn(options=cols),
                                           "status": st.column_config.SelectboxColumn(options=["Auto-approved", "Needs SME review", "SME approved", "Blank/zero fill"]),
                                           "confidence": st.column_config.ProgressColumn(min_value=0, max_value=1, format="%.2f")})
        if st.button("Save field mapping", type="primary", key="save_fm"):
            n = 0
            for r in ed.itertuples():
                i = fm.index[fm.field_id == r.field_id][0]
                if fm.at[i, "canonical"] != r.canonical or fm.at[i, "status"] != r.status:
                    fm.at[i, "canonical"] = r.canonical
                    fm.at[i, "source"] = ("SI² derived" if r.canonical.split(".")[0] in gen.DERIVED_COLS else "Canonical") if r.canonical else "Not reported"
                    fm.at[i, "status"] = "SME approved" if r.status == "Needs SME review" else r.status
                    n += 1
            ss.vmaps[spec] = gen.auto_value_map(ss.canon, fm).pipe(
                lambda new: pd.concat([ss.vmaps[spec][ss.vmaps[spec].status == "SME approved"], new]).drop_duplicates(
                    ["field_id", "source_value"], keep="first"))
            log(sme(), f"{spec} field mapping saved", f"{n} fields changed")
            st.success(f"Saved {n} changes.")
    with t3:
        spec = pick_spec("vm_spec")
        vm = ss.vmaps[spec]
        st.caption("Each distinct source value is mapped to a code from the spec pick list.")
        cat = catalog.load().set_index("field_id")
        field_opts = sorted(vm.field_name.unique())
        fsel = st.selectbox("Field", field_opts, key="vm_field") if field_opts else None
        if fsel:
            sub = vm[vm.field_name == fsel]
            codes = cat.loc[sub.field_id.iloc[0]].codes
            ed = st.data_editor(sub[["source_value", "bureau_code", "code_description", "confidence", "method", "status"]],
                                hide_index=True, width="stretch", key=f"ed_vm_{spec}_{fsel}",
                                disabled=["source_value", "code_description", "confidence", "method"],
                                column_config={"bureau_code": st.column_config.SelectboxColumn(options=[""] + [c["code"] for c in codes]),
                                               "status": st.column_config.SelectboxColumn(options=["Auto-approved", "Needs SME review", "SME approved"]),
                                               "confidence": st.column_config.ProgressColumn(min_value=0, max_value=1, format="%.2f")})
            st.dataframe(pd.DataFrame(codes)[["code", "description", "na_states"]], hide_index=True, width="stretch", height=200)
            if st.button("Save value mapping", type="primary"):
                for idx, r in zip(sub.index, ed.itertuples()):
                    if vm.at[idx, "bureau_code"] != r.bureau_code or vm.at[idx, "status"] != r.status:
                        vm.at[idx, "bureau_code"] = r.bureau_code
                        vm.at[idx, "code_description"] = catalog.pick_list(cat.loc[vm.at[idx, "field_id"]]).get(r.bureau_code, "")
                        vm.at[idx, "status"] = "SME approved"
                log(sme(), f"{spec} value mapping saved", fsel)
                st.success("Saved.")
    with t4:
        t = st.selectbox("Canonical table", list(ss.canon), key="can_tbl")
        st.dataframe(ss.canon[t].drop(columns=["_row"]).head(200), hide_index=True, width="stretch")
        st.dataframe(cn.canonical_columns().query("table == @t"), hide_index=True, width="stretch")
    with t5:
        gaps_ui.render(NG.scan(ss), NG.Handler(ss, sme(), rebuild_canonical, log), key="ncci_gaps",
                       intro="Source columns no canonical attribute uses, canonical attributes nothing feeds, WCIO fields with no "
                             "canonical source, and source values with no WCIO code. NCCI owns its code lists, so values are "
                             "mapped, never added.")

# ------------------------------------------------------------------------------------------ 4. Queue
elif step == STEPS[4]:
    st.subheader("SME approval queue")
    s, f, v, subs = queue_counts()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Source mappings", s)
    c2.metric("Bureau field mappings", f)
    c3.metric("Pick-list values", v)
    c4.metric("Submissions", subs)
    st.markdown("**Mapping items needing review**")
    items = []
    for r in ss.smap[ss.smap.status == "Needs SME review"].itertuples():
        items.append({"approve": False, "layer": "Source → canonical", "item": f"{r.canonical_table}.{r.canonical_column}",
                      "proposal": f"{r.source_table}.{r.source_column}", "confidence": r.confidence, "key": f"s|{r.Index}"})
    for spec, fm in ss.fmaps.items():
        for r in fm[fm.status == "Needs SME review"].itertuples():
            items.append({"approve": False, "layer": f"{spec} field", "item": f"{r.record_name} · {r.field_name} ({r.start}-{r.end})",
                          "proposal": r.canonical or "Leave blank / zero fill", "confidence": r.confidence, "key": f"f|{spec}|{r.Index}"})
    for spec, vm in ss.vmaps.items():
        for r in vm[vm.status == "Needs SME review"].itertuples():
            items.append({"approve": False, "layer": f"{spec} pick list", "item": f"{r.field_name}: {r.source_value}",
                          "proposal": f"{r.bureau_code} {r.code_description[:50]}" if r.bureau_code else "No match: choose a code in step 3",
                          "confidence": r.confidence, "key": f"v|{spec}|{r.Index}"})
    if items:
        q = pd.DataFrame(items)
        ed = st.data_editor(q, hide_index=True, width="stretch", key="ed_queue", disabled=["layer", "item", "proposal", "confidence"],
                            column_config={"key": None, "confidence": st.column_config.ProgressColumn(min_value=0, max_value=1, format="%.2f")})
        b1, b2 = st.columns(2)
        sel_clicked = b1.button("Approve selected", type="primary")
        all_clicked = b2.button("Approve all with a proposal")
        if sel_clicked or all_clicked:
            sel = ed if all_clicked else ed[ed.approve]
            n = 0
            for r in sel.itertuples():
                parts = r.key.split("|")
                if parts[0] == "s":
                    ss.smap.at[int(parts[1]), "status"] = "SME approved"
                elif parts[0] == "f":
                    ss.fmaps[parts[1]].at[int(parts[2]), "status"] = "SME approved"
                elif parts[0] == "v" and ss.vmaps[parts[1]].at[int(parts[2]), "bureau_code"]:
                    ss.vmaps[parts[1]].at[int(parts[2]), "status"] = "SME approved"
                else:
                    continue
                n += 1
            log(sme(), "Mapping items approved", f"{n} items")
            st.success(f"Approved {n} items. Items with no proposed code stay in the queue until you pick a code in step 3.")
            st.rerun()
    else:
        st.success("All mapping items are approved.")
    st.markdown("**Submissions awaiting approval**")
    pend = [x for x in ss.subs if x["status"] == "Pending SME approval"]
    if pend:
        st.dataframe(pd.DataFrame([{"id": x["id"], "file": x["spec"], "revision": x["revision"], "accounting dates": ", ".join(x["months"]),
                                    "records": len(x["records"]), "created": x["created"]} for x in pend]), hide_index=True, width="stretch")
        st.caption("Review and approve them in step 6.")
    else:
        st.caption("None.")

# ------------------------------------------------------------------------------------------ 5. Generate
elif step == STEPS[5]:
    st.subheader("Generate submission")
    c1, c2, c3 = st.columns([1, 1.4, 1.6])
    lob = c1.selectbox("Line of business", list(catalog.LINES_OF_BUSINESS), key="lob")
    types = catalog.LINES_OF_BUSINESS[lob]
    if not types:
        st.info(f"No bureau specs are loaded for {lob} yet. Upload its spec PDFs in the spec library to enable it.")
        st.stop()
    blabels = c2.multiselect("Type of bureau report", [SPEC_LABEL[t] for t in types], default=[SPEC_LABEL["WCSTAT"]], key="btypes")
    bureau = [b.split(" · ")[0] for b in blabels]
    months = gen.accounting_months()
    acct = c3.multiselect("Accounting date(s)", months, default=months[-3:], key="acct",
                          help="WCSTAT: valuation month of the unit report level. WCPOLS: transaction issue month. "
                               "WCIND / WCMED: payment month; the quarter of the latest month is the reporting quarter.")
    s, f, v, _ = queue_counts()
    if s + f + v:
        st.warning(f"{s + f + v} mapping items are still waiting for SME review. Files will use the current proposals.")
    if st.button("Generate submission files", type="primary", disabled=not (bureau and acct)):
        for spec in bureau:
            sub = gen.generate(spec, acct, ss.canon, ss.fmaps[spec], ss.vmaps[spec], {"carrier_group_code": ss.carrier},
                               excluded=ss.excluded)
            sub.update({"status": "Pending SME approval", "lob": lob, "parent": "", "history": [], "errors": None,
                        "response": None, "proposals": None})
            ss.subs.append(sub)
            log("SI²", f"{spec} submission generated", f"{sub['id']}: {len(sub['records'])} records, {', '.join(acct)}")
        st.success(f"Created {len(bureau)} submission(s). They are in the SME approval queue.")
    if ss.subs:
        st.divider()
        x = pick_sub("Preview submission", ss.subs, "prev_sub")
        recs = x["records"]
        st.write(f'{len(recs):,} records · {recs.unit.replace("", pd.NA).nunique()} units/claims · accounting dates {", ".join(x["months"])}')
        st.dataframe(recs.record_name.value_counts().rename_axis("record").reset_index(name="records"), hide_index=True)
        width = catalog.SPEC_INFO[x["spec"]]["record_length"]
        st.code(fw_ruler(width) + "\n" + "\n".join(recs.line.head(25)), language=None)
        seq = st.number_input("Decode record #", 1, max(1, len(recs)), 1, key="decode")
        r = recs[recs.seq == seq].iloc[0]
        flds = catalog.record_fields(x["spec"], r.record_key)
        if x["spec"] in gen.LINK_RECORD and r.record_key != "9":
            flds = pd.concat([catalog.record_fields(x["spec"], gen.LINK_RECORD[x["spec"]]), flds[flds.name != "LINK DATA"]])
        st.dataframe(pd.DataFrame([{"field": f["name"], "positions": f"{f.start}-{f.end}", "value": r.line[f.start - 1:f.end],
                                    "meaning": catalog.pick_list(f).get(r.line[f.start - 1:f.end].strip(), "")}
                                   for _, f in flds.iterrows() if not f["name"].startswith(("RESERVED", "FILLER"))]),
                     hide_index=True, width="stretch")
        d1, d2 = st.columns(2)
        d1.download_button("Download fixed-width file", x["fixed_width"], f'{x["spec"]}_{x["id"]}.txt', key="dl_fw")
        d2.download_button("Download flat CSV", x["flat_csv"], f'{x["spec"]}_{x["id"]}.csv', "text/csv", key="dl_csv")

# ------------------------------------------------------------------------------------------ 6. Submit
elif step == STEPS[6]:
    st.subheader("Submit & bureau response")
    if not ss.subs:
        st.info("Generate a submission in step 5 first.")
        st.stop()
    st.dataframe(pd.DataFrame([{"id": x["id"], "file": x["spec"], "revision": x["revision"], "parent": x["parent"],
                                "accounting dates": ", ".join(x["months"]), "records": len(x["records"]),
                                "status": x["status"],
                                "bureau": x["response"]["status"] if x["response"] else ""} for x in ss.subs]),
                 hide_index=True, width="stretch")
    x = pick_sub("Submission", ss.subs, "sub_sel")
    sel = x["id"]
    if x["status"] == "Pending SME approval":
        st.markdown("**SME review**")
        c1, c2, c3 = st.columns(3)
        c1.metric("Records", len(x["records"]))
        c2.metric("Units / claims", x["records"].unit.replace("", pd.NA).nunique())
        c3.metric("Revision", x["revision"])
        comment = st.text_area("Approval comment", key=f"cm_{sel}", placeholder="e.g. Reviewed record counts and premium totals")
        b1, b2 = st.columns(2)
        if b1.button("Approve and submit to bureau", type="primary"):
            x["history"].append(("Approved", sme(), comment))
            log(sme(), f"{x['spec']} submission approved", f"{x['id']}: {comment}")
            err, resp = edits.run(x["spec"], x["fixed_width"], x["records"])
            x["errors"], x["response"], x["status"] = err, resp, f"Bureau: {resp['status']}"
            x["proposals"] = revise.propose(x["spec"], err, x["records"], ss.canon, ss.fmaps[x["spec"]])
            log("Bureau (simulated)", f"{x['spec']} response", f"{x['id']}: {resp['status']}, {len(err)} edit results")
            st.rerun()
        if b2.button("Reject"):
            x["status"] = "Rejected by SME"
            x["history"].append(("Rejected", sme(), comment))
            log(sme(), f"{x['spec']} submission rejected", f"{x['id']}: {comment}")
            st.rerun()
    elif x["response"]:
        r = x["response"]
        tone = {"Accepted": st.success, "Accepted with errors": st.warning}.get(r["status"], st.error)
        tone(f"Bureau response: **{r['status']}** · {r['records']} records · {r['units_rejected']} of {r['units']} "
             f"units/claims rejected · {r['critical']} critical · {r['errors']} errors · {r['warnings']} warnings")
        err = x["errors"]
        if len(err):
            st.bar_chart(err.groupby("edit_id").size(), color="#2B4CF2", height=200)
            st.dataframe(err, hide_index=True, width="stretch")
            st.download_button("Download error file (CSV)", err.to_csv(index=False), f'{x["spec"]}_{x["id"]}_errors.csv', "text/csv")
            st.info("Go to step 7 to review SI²'s proposed revisions and resubmit.")
        else:
            st.balloons()
    else:
        st.write(f"Status: {x['status']}")

# ------------------------------------------------------------------------------------------ 7. Revise
elif step == STEPS[7]:
    st.subheader("Revise & resubmit")
    cands = [x for x in ss.subs if x["errors"] is not None and len(x["errors"])]
    if not cands:
        st.info("No bureau errors to revise yet.")
        st.stop()
    x = pick_sub("Submission with errors", cands, "rev_sel")
    sel = x["id"]
    props = x["proposals"]
    st.write(f'{len(x["errors"])} edit results → {len(props)} proposed revisions. Tick the ones you approve; '
             "fill in values SI² could not know (for example a missing FEIN).")
    with st.expander("Ask SI² to revise (Claude)"):
        key, model = "", "claude-sonnet-5-5"
        try:
            key = st.secrets.get("ANTHROPIC_API_KEY", "")
            model = st.secrets.get("ANTHROPIC_MODEL", model)
        except Exception:
            pass
        ask = st.text_area("Instruction", placeholder="e.g. Map PPD codes to 09, hold any claim with date conflicts, cap paid at charges",
                           key=f"ask_{sel}")
        if not key:
            st.caption("Add ANTHROPIC_API_KEY to this app's Streamlit secrets to have Claude draft revisions from your instruction. "
                       "The rule-based proposals below work without it.")
        if st.button("Ask SI²", disabled=not (key and ask)):
            with st.spinner("Claude is reviewing the error file…"):
                try:
                    x["proposals"] = revise.ask_claude(key, model, ask, x["spec"], x["errors"], props)
                    log(sme(), "Asked Claude to revise", ask)
                    st.rerun()
                except Exception as exc:  # noqa: BLE001
                    st.error(f"Claude request failed: {exc}")
    ed = st.data_editor(props, hide_index=True, width="stretch", key=f"ed_props_{sel}",
                        disabled=["edit_id", "action", "field", "current", "proposed", "rationale", "records", "confidence", "needs_input"],
                        column_config={"target": None, "approve": st.column_config.CheckboxColumn("Approve"),
                                       "value": st.column_config.TextColumn("Value to apply"),
                                       "confidence": st.column_config.ProgressColumn(min_value=0, max_value=1, format="%.2f")})
    if st.button("Apply approved revisions and create resubmission", type="primary"):
        spec = x["spec"]
        ss.vmaps[spec], ss.overrides, ss.excluded, audit = revise.apply(ed, ss.vmaps[spec], ss.overrides, ss.excluded)
        rebuild_canonical()
        err = x["errors"]
        bad = set(err.unit) - {""}
        crit = set(err[err.severity == "Critical"].unit)
        corr = {}
        if spec == "WCSTAT":
            for u in bad - crit:
                types = set(err[err.unit == u].record_type)
                corr[u] = "L" if types == {"Loss"} else "E" if types == {"Exposure"} else \
                    "H" if types <= {"Header", "Name", "Address"} else "M"
        only = bad if spec in ("WCSTAT", "WCPOLS") and bad else None
        new = gen.generate(spec, x["months"], ss.canon, ss.fmaps[spec], ss.vmaps[spec], {"carrier_group_code": ss.carrier},
                           corrections=corr, revision=x["revision"] + 1, only_units=only, excluded=ss.excluded)
        new.update({"status": "Pending SME approval", "lob": x.get("lob", ""), "parent": x["id"], "history": [],
                    "errors": None, "response": None, "proposals": None})
        ss.subs.append(new)
        x["status"] = f"Revised → {new['id']}"
        for a in audit:
            log(sme(), f"Revision approved ({a['action']})", f"{a['field']}: {a['change']}")
        log("SI²", f"{spec} resubmission generated", f"{new['id']} (rev {new['revision']}): {len(new['records'])} records")
        kind = {"WCSTAT": "corrected and resubmitted units (correction sequence and correction type codes set)",
                "WCPOLS": "resubmitted policy transactions", "WCIND": "replacement file (submission file type R)",
                "WCMED": "replacement file (submission file type R)"}[spec]
        st.success(f"Created {new['id']}: {kind}. Approve and submit it in step 6.")

# ------------------------------------------------------------------------------------------ Audit
elif step == "Audit trail":
    st.subheader("Audit trail")
    a = pd.DataFrame(ss.audit)[::-1]
    st.dataframe(a, hide_index=True, width="stretch")
    st.download_button("Download audit trail (CSV)", a.to_csv(index=False), "si2_bureau_audit.csv", "text/csv")

branding.note_synthetic()
st.caption("Field layouts and code lists are read from the WCIO specification PDFs you provided. "
           "Bureau responses are simulated with SI² edits; edit IDs are not official NCCI edit numbers.")
branding.footer()
