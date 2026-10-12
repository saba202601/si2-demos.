"""SME upload templates: download, fill NEW records only, upload.

The template carries only business columns; the system adds keys, status
(PENDING), created_by/at and supersede links. Uploads are checked for required
columns, dates, foreign keys and overlap with records already in force. A row
that overlaps an existing record with a *later* effective date becomes a
supersede (the old row expires when the SME approves the new one).
"""
from __future__ import annotations

import io
import json
from datetime import date

import openpyxl
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

from . import db

# table: (natural key columns, [(column, required, help)])
SPECS = {
    "canonical_element": (["element_code"], [
        ("element_code", True, "UPPER_SNAKE code, e.g. TELEMATICS_IND"), ("element_name", True, "Business name"),
        ("business_description", True, "What it means to the business"),
        ("data_type", True, "CODE | TEXT | DATE | AMOUNT | NUMBER | INTEGER | DECIMAL"),
        ("picklist_code", False, "Pick list for CODE elements"), ("eff_date", True, "YYYY-MM-DD"),
        ("exp_date", False, "YYYY-MM-DD, blank = open"), ("notes", False, "")]),
    "element_alias": (["element_code", "alias_name", "alias_context"], [
        ("element_code", True, "Existing element"), ("alias_name", True, "Synonym / other system's name"),
        ("alias_context", True, "BUSINESS | BUREAU:ISO:<LOB> | SOURCE:<system>"), ("eff_date", True, "YYYY-MM-DD")]),
    "source_mapping": (["source_system", "source_attribute", "element_code"], [
        ("source_system", True, "Guidewire | DuckCreek | <legacy>"), ("source_entity", True, "Table / object / extract"),
        ("source_attribute", True, "Column / field name in source"), ("source_data_type", False, ""),
        ("element_code", True, "Canonical element it feeds"), ("eff_date", True, "YYYY-MM-DD")]),
    "picklist": (["picklist_code"], [
        ("picklist_code", True, "UPPER_SNAKE"), ("picklist_name", True, ""), ("business_description", False, ""),
        ("eff_date", True, "YYYY-MM-DD")]),
    "picklist_alias": (["picklist_code", "alias_name"], [
        ("picklist_code", True, ""), ("alias_name", True, ""), ("alias_context", True, "BUSINESS | BUREAU:ISO | SOURCE:<system>"),
        ("eff_date", True, "YYYY-MM-DD")]),
    "picklist_option": (["picklist_code", "option_code", "lob_scope"], [
        ("picklist_code", True, ""), ("lob_scope", True, "* or comma list e.g. HO,CP"), ("option_code", True, "Canonical code"),
        ("option_name", True, ""), ("business_description", False, ""), ("eff_date", True, "YYYY-MM-DD"),
        ("exp_date", False, "YYYY-MM-DD")]),
    "picklist_option_alias": (["picklist_code", "source_system", "source_value"], [
        ("picklist_code", True, ""), ("option_code", True, "Canonical option"), ("source_system", True, "system or * for all"),
        ("source_value", True, "Value as it arrives from source"), ("eff_date", True, "YYYY-MM-DD")]),
    "bureau_code_map": (["bureau_code", "picklist_code", "option_code", "lob_scope"], [
        ("bureau_code", True, "ISO"), ("lob_scope", True, "* or comma list"), ("picklist_code", True, ""),
        ("option_code", True, "Canonical option"), ("bureau_value", True, "Code ISO expects"), ("eff_date", True, "YYYY-MM-DD"),
        ("exp_date", False, "")]),
    "business_rule": (["rule_code"], [
        ("rule_code", True, "VRnnn / DRnnn / TR_xxx"), ("rule_name", True, ""),
        ("rule_category", True, "VALIDATION | DERIVATION | TRANSFORMATION"), ("lob_scope", True, "* or list"),
        ("record_type_scope", True, "* | PREMIUM | LOSS"), ("state_scope", False, "* or list of state codes"),
        ("element_code", False, "Element the rule is about"), ("expression_json", True, "JSON - see Rules page examples"),
        ("severity", True, "ERROR | WARNING"), ("message", False, "Shown on failure"), ("business_description", True, ""),
        ("eff_date", True, "YYYY-MM-DD")]),
    "layout_field": (["lob_code", "record_type", "version_no", "seq"], [
        ("lob_code", True, "PA HO CA CP GL IM CR BP FI BR"), ("record_type", True, "PREMIUM | LOSS"),
        ("version_no", True, "New version number"), ("eff_date", True, "Version effective date"),
        ("seq", True, "Field #"), ("bureau_field_name", True, ""), ("start_pos", True, ""), ("length", True, ""),
        ("field_format", True, "N | A | AN | YYMM | YYMMDD | SIGNED"), ("required", True, "Y | N"),
        ("element_code", True, "Canonical element"), ("transform_rule_code", True, "TR_xxx"),
        ("bureau_description", False, "")]),
}

HDR = PatternFill("solid", fgColor="1F3A5F")


def build_template(tables: list[str] | None = None) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Instructions"
    lines = ["SI² ISO Bureau Reporting - SME upload template",
             "Enter NEW records only. Do not enter keys, status or audit columns - the system adds them.",
             "Every uploaded row is created as PENDING and must be approved in the app before the engine uses it.",
             "To change an existing record, enter it again with a LATER eff_date: it supersedes the current record,",
             "which expires the day before once you approve the new one. Nothing is ever deleted.",
             "Bold columns are required. Dates are YYYY-MM-DD."]
    for i, l in enumerate(lines, 1):
        ws.cell(i, 1, l).font = Font(bold=i == 1, size=13 if i == 1 else 11)
    ws.column_dimensions["A"].width = 110
    for t in tables or SPECS:
        sh = wb.create_sheet(t[:31])
        for j, (c, req, hlp) in enumerate(SPECS[t][1], 1):
            cell = sh.cell(1, j, c)
            cell.font = Font(bold=req, color="FFFFFF")
            cell.fill = HDR
            sh.cell(2, j, hlp).font = Font(italic=True, color="808080")
            sh.column_dimensions[get_column_letter(j)].width = max(16, len(c) + 4)
        sh.freeze_panes = "A3"
    bio = io.BytesIO()
    wb.save(bio)
    return bio.getvalue()


def _iso(v) -> str | None:
    if v in (None, ""):
        return None
    if hasattr(v, "date"):
        return v.date().isoformat()
    if isinstance(v, date):
        return v.isoformat()
    return date.fromisoformat(str(v).strip()[:10]).isoformat()


def read_upload(data: bytes) -> dict[str, list[dict]]:
    wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True)
    out = {}
    for t in SPECS:
        if t[:31] not in wb.sheetnames:
            continue
        ws = wb[t[:31]]
        rows = list(ws.iter_rows(values_only=True))
        hdr = [str(h).strip() if h else "" for h in rows[0]]
        recs = []
        for r in rows[2:]:  # row 2 = help text
            if not any(c not in (None, "") for c in r):
                continue
            recs.append({hdr[i]: (r[i] if i < len(r) else None) for i in range(len(hdr)) if hdr[i]})
        if recs:
            out[t] = recs
    return out


def check_and_load(con, uploads: dict[str, list[dict]], actor: str, commit: bool = False) -> list[dict]:
    """Return one result per row: ok / error / supersede. Loads only when commit and no errors."""
    results = []
    elements = {r["element_code"] for r in db.rows(con, "SELECT element_code FROM canonical_element WHERE status!='REJECTED'")}
    picklists = {r["picklist_code"] for r in db.rows(con, "SELECT picklist_code FROM picklist WHERE status!='REJECTED'")}
    options = {(r["picklist_code"], r["option_code"]) for r in db.rows(con, "SELECT picklist_code, option_code FROM picklist_option WHERE status!='REJECTED'")}
    trs = {r["rule_code"] for r in db.rows(con, "SELECT rule_code FROM business_rule WHERE rule_category='TRANSFORMATION' AND status!='REJECTED'")}
    lobs = {r["lob_code"] for r in db.rows(con, "SELECT lob_code FROM line_of_business")}
    # elements / picklists / options introduced in the same upload count as known
    for r in uploads.get("canonical_element", []):
        elements.add(str(r.get("element_code") or "").strip())
    for r in uploads.get("picklist", []):
        picklists.add(str(r.get("picklist_code") or "").strip())
    for r in uploads.get("picklist_option", []):
        options.add((str(r.get("picklist_code") or "").strip(), str(r.get("option_code") or "").strip()))

    plan = []
    for table, recs in uploads.items():
        keys, cols = SPECS[table]
        for n, raw in enumerate(recs, 3):
            errs = []
            rec = {}
            for c, req, _ in cols:
                v = raw.get(c)
                v = v.strip() if isinstance(v, str) else v
                if req and v in (None, ""):
                    errs.append(f"{c} is required")
                if c in ("eff_date", "exp_date"):
                    try:
                        v = _iso(v)
                    except ValueError:
                        errs.append(f"{c} '{v}' is not YYYY-MM-DD")
                rec[c] = v if v not in ("",) else None
            if rec.get("exp_date") is None and "exp_date" in rec:
                rec["exp_date"] = db.OPEN_END
            if rec.get("element_code") and rec["element_code"] not in elements and table != "canonical_element":
                errs.append(f"element_code {rec['element_code']} does not exist")
            if rec.get("picklist_code") and rec["picklist_code"] not in picklists and table != "picklist":
                errs.append(f"picklist_code {rec['picklist_code']} does not exist")
            if table in ("picklist_option_alias", "bureau_code_map") and (rec.get("picklist_code"), rec.get("option_code")) not in options:
                errs.append(f"option {rec.get('picklist_code')}/{rec.get('option_code')} does not exist")
            if table == "layout_field":
                if rec.get("lob_code") not in lobs:
                    errs.append(f"lob_code {rec.get('lob_code')} unknown")
                if rec.get("transform_rule_code") not in trs:
                    errs.append(f"transform_rule_code {rec.get('transform_rule_code')} unknown")
            if table == "business_rule" and rec.get("expression_json"):
                try:
                    json.loads(rec["expression_json"])
                except ValueError:
                    errs.append("expression_json is not valid JSON")
            action, sup = "new", None
            if not errs and table != "layout_field":
                where = " AND ".join(f"{k}=?" for k in keys)
                ex = db.rows(con, f"""SELECT * FROM {table} WHERE {where} AND status!='REJECTED'
                                      AND exp_date >= ? AND eff_date <= ?""",
                             [rec.get(k) for k in keys] + [rec["eff_date"], rec.get("exp_date", db.OPEN_END)])
                if ex:
                    cur = max(ex, key=lambda r: r["eff_date"])
                    if rec["eff_date"] > cur["eff_date"]:
                        action, sup = "supersede", cur[db.META_TABLES[table]]
                    else:
                        errs.append(f"overlaps existing {table} id {cur[db.META_TABLES[table]]} "
                                    f"({cur['eff_date']}..{cur['exp_date']}); use a later eff_date")
            results.append({"table": table, "row": n, "key": " / ".join(str(rec.get(k)) for k in keys),
                            "result": "error" if errs else action, "detail": "; ".join(errs)})
            plan.append((table, rec, action, sup, bool(errs)))

    if commit and not any(p[4] for p in plan):
        with db.tx(con):
            layouts = {}
            for table, rec, action, sup, _ in plan:
                rec = {k: v for k, v in rec.items() if v is not None}
                if table == "layout_field":
                    k = (rec["lob_code"], rec["record_type"], int(rec["version_no"]))
                    if k not in layouts:
                        prev = db.one(con, """SELECT * FROM layout_version WHERE lob_code=? AND record_type=? AND status='APPROVED'
                                              ORDER BY version_no DESC""", k[:2])
                        layouts[k] = db.insert(con, "layout_version", {
                            "bureau_code": "ISO", "lob_code": k[0], "record_type": k[1], "version_no": k[2], "record_length": 150,
                            "source_file": "SME upload", "eff_date": rec["eff_date"], "exp_date": db.OPEN_END, "status": "PENDING",
                            "created_by": actor, "supersedes_id": prev["layout_id"] if prev else None})
                        db.insert(con, "approval_log", {"object_table": "layout_version", "object_id": layouts[k],
                                                        "action": "SUBMITTED", "actor": actor, "comment": "SME upload"})
                    data = {c: rec[c] for c in ("seq", "bureau_field_name", "start_pos", "length", "field_format", "required",
                                                "element_code", "transform_rule_code", "bureau_description", "eff_date")}
                    data.update({"layout_id": layouts[k], "seq": int(data["seq"]), "start_pos": int(data["start_pos"]),
                                 "length": int(data["length"])})
                    db.add_pending(con, "layout_field", data, actor, "SME upload")
                elif action == "supersede":
                    db.supersede(con, table, sup, {k: v for k, v in rec.items() if k not in ("eff_date",)}, rec["eff_date"], actor, "SME upload")
                else:
                    db.add_pending(con, table, rec, actor, "SME upload")
    return results
