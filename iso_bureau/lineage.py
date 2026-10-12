"""Source -> Canonical -> Bureau lineage for the SME validation workbench.

One row per bureau field, carrying every object the engine will touch to fill
that field, with each object's approval status. Approving a lineage row
approves all of its PENDING objects in one action (logged per object).
"""
from __future__ import annotations

from . import db
from .engine import in_scope


def _st(rows):
    s = {r["status"] for r in rows}
    if not rows:
        return "MISSING"
    if "REJECTED" in s:
        return "REJECTED"
    if "PENDING" in s:
        return "PENDING"
    return "APPROVED"


def _eff(sql_alias=""):
    return db.as_of_clause(sql_alias)


def lineage(con, bureau: str, lob: str, record_type: str, as_of: str, include_pending: bool = True) -> list[dict]:
    st = "status IN ('APPROVED','PENDING','REJECTED')" if include_pending else "status='APPROVED'"
    lays = db.rows(con, f"""SELECT * FROM layout_version WHERE bureau_code=? AND lob_code=? AND record_type=?
                            AND {_eff()} AND {st} ORDER BY version_no DESC""", (bureau, lob, record_type, as_of, as_of))
    if not lays:
        return []
    lay = lays[0]
    fields = db.rows(con, f"SELECT * FROM layout_field WHERE layout_id=? AND {_eff()} AND {st} ORDER BY seq",
                     (lay["layout_id"], as_of, as_of))
    out = []
    for f in fields:
        el = f["element_code"]
        objs: dict[str, list[dict]] = {"layout_version": [lay], "layout_field": [f]}
        objs["canonical_element"] = db.rows(con, f"SELECT * FROM canonical_element WHERE element_code=? AND {_eff()} AND {st}", (el, as_of, as_of))
        objs["source_mapping"] = db.rows(con, f"SELECT * FROM source_mapping WHERE element_code=? AND {_eff()} AND {st}", (el, as_of, as_of))
        objs["element_alias"] = db.rows(con, f"SELECT * FROM element_alias WHERE element_code=? AND {_eff()} AND {st}", (el, as_of, as_of))
        pl = objs["canonical_element"][0]["picklist_code"] if objs["canonical_element"] else None
        if pl:
            objs["picklist"] = db.rows(con, f"SELECT * FROM picklist WHERE picklist_code=? AND {_eff()} AND {st}", (pl, as_of, as_of))
            opts = [o for o in db.rows(con, f"SELECT * FROM picklist_option WHERE picklist_code=? AND {_eff()} AND {st}", (pl, as_of, as_of))
                    if in_scope(o["lob_scope"], lob)]
            objs["picklist_option"] = opts
            codes = {o["option_code"] for o in opts}
            objs["bureau_code_map"] = [m for m in db.rows(con, f"""SELECT * FROM bureau_code_map WHERE bureau_code=? AND picklist_code=?
                                                               AND {_eff()} AND {st}""", (bureau, pl, as_of, as_of))
                                       if in_scope(m["lob_scope"], lob) and m["option_code"] in codes]
            objs["picklist_option_alias"] = [a for a in db.rows(con, f"""SELECT * FROM picklist_option_alias WHERE picklist_code=?
                                                                        AND {_eff()} AND {st}""", (pl, as_of, as_of)) if a["option_code"] in codes]
        tr = db.rows(con, f"SELECT * FROM business_rule WHERE rule_code=? AND {_eff()} AND {st}", (f["transform_rule_code"], as_of, as_of))
        rules = [r for r in db.rows(con, f"""SELECT * FROM business_rule WHERE element_code=? AND bureau_code=? AND {_eff()} AND {st}""",
                                    (el, bureau, as_of, as_of))
                 if in_scope(r["lob_scope"], lob) and in_scope(r["record_type_scope"], record_type)]
        objs["business_rule"] = tr + rules
        gw = next((m["source_attribute"] for m in objs["source_mapping"] if m["source_system"] == "Guidewire"), "")
        dc = next((m["source_attribute"] for m in objs["source_mapping"] if m["source_system"] == "DuckCreek"), "")
        derived = [r["rule_code"] for r in rules if r["rule_category"] == "DERIVATION"]
        status = {k: _st(v) for k, v in objs.items() if k not in ("layout_version",)}
        for optional in ("picklist_option_alias", "element_alias"):  # aliases are optional
            if status.get(optional) == "MISSING":
                status[optional] = "NONE"
        if not objs["source_mapping"] and (derived or el == "FILLER"):
            status["source_mapping"] = "DERIVED"
        overall = ("REJECTED" if "REJECTED" in status.values() else
                   "MISSING" if "MISSING" in status.values() else
                   "PENDING" if "PENDING" in status.values() else "APPROVED")
        out.append({
            "seq": f["seq"], "position": f"{f['start_pos']}-{f['start_pos'] + f['length'] - 1}", "length": f["length"],
            "bureau_field": f["bureau_field_name"], "format": f["field_format"], "required": f["required"],
            "bureau_description": f["bureau_description"],
            "canonical_element": el,
            "element_name": objs["canonical_element"][0]["element_name"] if objs["canonical_element"] else "",
            "business_description": objs["canonical_element"][0]["business_description"] if objs["canonical_element"] else f["business_description"],
            "data_type": objs["canonical_element"][0]["data_type"] if objs["canonical_element"] else "",
            "source_guidewire": gw, "source_duckcreek": dc,
            "derivation": ", ".join(derived),
            "picklist": pl or "", "options": len(objs.get("picklist_option", [])),
            "transform_rule": f["transform_rule_code"],
            "validation_rules": ", ".join(r["rule_code"] for r in rules if r["rule_category"] == "VALIDATION"),
            "aliases": ", ".join(sorted({a["alias_name"] for a in objs["element_alias"]})),
            "status_detail": status, "overall": overall,
            "_objects": {k: [r[db.META_TABLES[k]] for r in v] for k, v in objs.items()},
            "_pending": {k: [r[db.META_TABLES[k]] for r in v if r["status"] == "PENDING"] for k, v in objs.items()},
            "layout_id": lay["layout_id"], "layout_version": lay["version_no"],
        })
    return out


def approve_lineage_rows(con, rows: list[dict], actor: str, comment: str, action: str = "APPROVED") -> int:
    n = 0
    done = set()
    with db.tx(con):
        for r in rows:
            for table, ids in r["_pending"].items():
                if table == "layout_version":
                    continue
                for i in ids:
                    if (table, i) not in done:
                        db.set_status(con, table, i, action, actor, comment)
                        done.add((table, i))
                        n += 1
        # the layout version itself is approved once every field in it is approved
        if action == "APPROVED":
            for lid in {r["layout_id"] for r in rows}:
                lay = db.one(con, "SELECT * FROM layout_version WHERE layout_id=?", (lid,))
                left = db.one(con, "SELECT COUNT(*) n FROM layout_field WHERE layout_id=? AND status!='APPROVED'", (lid,))["n"]
                if lay["status"] == "PENDING" and left == 0:
                    db.set_status(con, "layout_version", lid, "APPROVED", actor, "All fields approved")
                    n += 1
    return n
