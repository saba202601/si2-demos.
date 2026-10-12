"""Build the BureauReporting database from the ISO layout workbooks + starter catalog.

    python -m iso_bureau.seed                 # everything PENDING (real SME workflow)
    python -m iso_bureau.seed --demo-approve  # baseline approved by "Demo SME"; 2027 changes stay PENDING

Sample source transactions (Guidewire + Duck Creek style) are generated for every
line, including deliberate defects so validation, holds, ISO rejects and the
correction / resubmission loop can be exercised.
"""
from __future__ import annotations

import argparse
import json
import random
from datetime import date, timedelta
from pathlib import Path

from . import catalog as C
from . import db
from .layouts import LOB_NAMES, parse_all

ROOT = Path(__file__).resolve().parent
LAYOUT_DIR = ROOT / "data" / "iso_layouts"
SEED_ACTOR = "seed: ISO layout import"


def transform_for(element: str, fmt: str, lob: str, picklist: str | None) -> str:
    if element == "FILLER":
        return "TR_BLANK"
    if picklist:
        return "TR_CODE_MAP"
    if fmt == "YYMMDD":
        return "TR_YYMMDD"
    if fmt == "YYMM":
        return "TR_YYMM"
    if fmt == "SIGNED":
        return "TR_SIGNED_OVERPUNCH"
    if element == "LIMIT_AMOUNT":
        return "TR_THOUSANDS"
    if element == "EXPOSURE" and lob in C.AUTO_LOBS:
        return "TR_IMPLIED_1DEC"
    if fmt == "N" and element not in ("RISK_ZIP", "LOSS_ZIP", "CAT_CODE"):
        return "TR_ZEROPAD"
    return "TR_LEFT"


def build(path: Path, demo_approve: bool = False) -> dict:
    if path.exists():
        path.unlink()
    con = db.connect(path)
    stats = {}
    with db.tx(con):
        db.insert(con, "bureau", {"bureau_code": "ISO", "bureau_name": "Insurance Services Office (Verisk) - Statistical Plans",
                                  "code_basis": "POLICY_EFF"})
        for code, name, fam, _iso, _m in C.LOBS:
            db.insert(con, "line_of_business", {"lob_code": code, "lob_name": name, "lob_family": fam})

        # ---------------- canonical elements + source mappings
        def add_element(code, spec, eff):
            name, dtype, pl, desc, gw, dc = spec
            db.add_pending(con, "canonical_element", {"element_code": code, "element_name": name, "business_description": desc,
                                                       "data_type": dtype, "picklist_code": pl, "eff_date": eff}, SEED_ACTOR)
            for sysname, attr, ent in (("Guidewire", gw, "PolicyCenter/ClaimCenter"), ("DuckCreek", dc, "DC Policy/Claims extract")):
                if attr:
                    db.add_pending(con, "source_mapping", {"source_system": sysname, "source_entity": ent, "source_attribute": attr,
                                                            "source_data_type": dtype, "element_code": code, "eff_date": eff}, SEED_ACTOR)
            db.add_pending(con, "element_alias", {"element_code": code, "alias_name": name, "alias_context": "BUSINESS", "eff_date": eff}, SEED_ACTOR)

        for code, spec in C.ELEMENTS.items():
            add_element(code, spec, C.BASE_EFF)
        for code, spec in C.NEW_2027_ELEMENTS.items():
            add_element(code, spec, C.CHANGE_EFF)

        # ---------------- pick lists, options, aliases, bureau code maps
        for code, name in C.PICKLISTS.items():
            eff = C.CHANGE_EFF if code == "YES_NO" else C.BASE_EFF
            db.add_pending(con, "picklist", {"picklist_code": code, "picklist_name": name, "business_description": name, "eff_date": eff}, SEED_ACTOR)
        for pl, alias, ctx in C.PICKLIST_ALIASES:
            db.add_pending(con, "picklist_alias", {"picklist_code": pl, "alias_name": alias, "alias_context": ctx, "eff_date": C.BASE_EFF}, SEED_ACTOR)
        for pl, opts in C.OPTIONS.items():
            for o in opts:
                scope, oc, name, bval = o[:4]
                eff = o[4] if len(o) > 4 else (C.CHANGE_EFF if pl == "YES_NO" else C.BASE_EFF)
                exp = o[5] if len(o) > 5 else db.OPEN_END
                oid = db.add_pending(con, "picklist_option", {"picklist_code": pl, "lob_scope": scope, "option_code": oc,
                                                              "option_name": name, "business_description": name,
                                                              "eff_date": eff, "exp_date": exp}, SEED_ACTOR)
                db.add_pending(con, "bureau_code_map", {"bureau_code": "ISO", "lob_scope": scope, "picklist_code": pl,
                                                        "option_code": oc, "bureau_value": bval, "eff_date": eff, "exp_date": exp}, SEED_ACTOR)
        for pl, oc, sysname, sval in C.OPTION_ALIASES:
            db.add_pending(con, "picklist_option_alias", {"picklist_code": pl, "option_code": oc, "source_system": sysname,
                                                          "source_value": sval, "eff_date": C.BASE_EFF}, SEED_ACTOR)

        # ---------------- business / derivation / transformation rules
        for (code, name, cat, lobs, rts, el, expr, sev, msg, desc, eff) in C.RULES:
            db.add_pending(con, "business_rule", {"rule_code": code, "rule_name": name, "rule_category": cat, "bureau_code": "ISO",
                                                  "lob_scope": lobs, "record_type_scope": rts, "element_code": el,
                                                  "expression_json": json.dumps(expr), "severity": sev, "message": msg,
                                                  "business_description": desc, "eff_date": eff}, SEED_ACTOR)

        # ---------------- layouts from the ISO workbooks
        findings = []
        elements = {**C.ELEMENTS, **C.NEW_2027_ELEMENTS}
        for lay in parse_all(LAYOUT_DIR):
            lid = db.add_pending(con, "layout_version", {"bureau_code": "ISO", "lob_code": lay.lob, "record_type": lay.record_type,
                                                         "version_no": 1, "record_length": 150, "source_file": f"{lay.source_file} [{lay.sheet}]",
                                                         "eff_date": C.BASE_EFF, "notes": " | ".join(lay.findings) or None}, SEED_ACTOR,
                                 f"Imported from {lay.source_file} sheet {lay.sheet}")
            findings += [f"{lay.lob} {lay.record_type}: {x}" for x in lay.findings]
            for f in lay.fields:
                el = C.FIELD_OVERRIDES.get((lay.lob, lay.record_type, f.name)) or C.FIELD_TO_ELEMENT[f.name]
                pl = elements[el][2]
                db.add_pending(con, "layout_field", {
                    "layout_id": lid, "seq": f.seq, "bureau_field_name": f.name, "start_pos": f.start, "length": f.length,
                    "field_format": f.data_type, "required": "N" if el in C.OPTIONAL_ELEMENTS else "Y", "element_code": el,
                    "transform_rule_code": transform_for(el, f.data_type, lay.lob, pl),
                    "bureau_description": f.description, "business_description": elements[el][3], "eff_date": C.BASE_EFF}, SEED_ACTOR)
                db.add_pending(con, "element_alias", {"element_code": el, "alias_name": f.name, "alias_context": f"BUREAU:ISO:{lay.lob}",
                                                      "eff_date": C.BASE_EFF}, SEED_ACTOR) if not db.one(
                    con, "SELECT 1 FROM element_alias WHERE element_code=? AND alias_name=?", (el, f.name)) else None
            if lay.lob == "PA" and lay.record_type == "PREMIUM":
                _pa_2027_version(con, lid, lay)
        stats["layout_findings"] = findings

        # ---------------- future-dated code changes (pending)
        for pl, scope, oc, name, bval, eff in C.PENDING_OPTION_CHANGES:
            db.add_pending(con, "picklist_option", {"picklist_code": pl, "lob_scope": scope, "option_code": oc, "option_name": name,
                                                    "business_description": name, "eff_date": eff}, "SME proposal", "HO water peril split for 2027")
            db.add_pending(con, "bureau_code_map", {"bureau_code": "ISO", "lob_scope": scope, "picklist_code": pl, "option_code": oc,
                                                    "bureau_value": bval, "eff_date": eff}, "SME proposal")
        db.add_pending(con, "picklist_option_alias", {"picklist_code": "CAUSE_OF_LOSS", "option_code": "WATERW", "source_system": "Guidewire",
                                                      "source_value": "water_weather", "eff_date": C.CHANGE_EFF}, "SME proposal")
        db.add_pending(con, "picklist_option_alias", {"picklist_code": "CAUSE_OF_LOSS", "option_code": "WATERN", "source_system": "Guidewire",
                                                      "source_value": "water_plumbing", "eff_date": C.CHANGE_EFF}, "SME proposal")
        # HO WATER option ends when the split starts: proposed as a superseding expiry
        water = db.one(con, "SELECT option_id FROM picklist_option WHERE picklist_code='CAUSE_OF_LOSS' AND option_code='WATER'")
        db.supersede(con, "picklist_option", water["option_id"], {"lob_scope": "CP,BP,BR,IM"}, C.CHANGE_EFF, "SME proposal",
                     "Homeowners water damage splits into WATERW / WATERN from 2027-01-01")

        stats["source_transactions"] = _sample_transactions(con)

    if demo_approve:
        approve_baseline(con, "Demo SME")
    stats["pending"] = db.pending_counts(con)
    con.close()
    return stats


def _pa_2027_version(con, v1_id: int, lay):
    """Proposed PA premium layout v2: telematics + rideshare indicators carved out of the ISO extension area."""
    lid = db.insert(con, "layout_version", {"bureau_code": "ISO", "lob_code": "PA", "record_type": "PREMIUM", "version_no": 2,
                                            "record_length": 150, "source_file": "SME proposal - 2027 PA extensions",
                                            "eff_date": C.CHANGE_EFF, "exp_date": db.OPEN_END, "status": "PENDING",
                                            "created_by": "SME proposal", "supersedes_id": v1_id,
                                            "notes": "Adds Telematics (87) and Rideshare (88) indicators; filler 89-150"})
    db.insert(con, "approval_log", {"object_table": "layout_version", "object_id": lid, "action": "SUBMITTED",
                                    "actor": "SME proposal", "comment": "2027 PA layout change"})
    for f in lay.fields:
        base = {"layout_id": lid, "field_format": f.data_type, "eff_date": C.CHANGE_EFF, "bureau_description": f.description}
        el = C.FIELD_TO_ELEMENT[f.name]
        if el == "FILLER":
            for seq, name, start, ln, e2, fmt in ((18, "Telematics Indicator", 87, 1, "TELEMATICS_IND", "A"),
                                                  (19, "Rideshare Indicator", 88, 1, "RIDESHARE_IND", "A"),
                                                  (20, f.name, 89, 62, "FILLER", "AN")):
                spec = C.NEW_2027_ELEMENTS.get(e2) or C.ELEMENTS[e2]
                db.add_pending(con, "layout_field", {**base, "seq": seq, "bureau_field_name": name, "start_pos": start, "length": ln,
                                                     "field_format": fmt, "required": "N" if e2 == "FILLER" else "Y", "element_code": e2,
                                                     "transform_rule_code": "TR_BLANK" if e2 == "FILLER" else "TR_CODE_MAP",
                                                     "business_description": spec[3],
                                                     "bureau_description": spec[3] if e2 != "FILLER" else "Reserved space (reduced to 62)"},
                               "SME proposal")
        else:
            db.add_pending(con, "layout_field", {**base, "seq": f.seq, "bureau_field_name": f.name, "start_pos": f.start, "length": f.length,
                                                 "required": "N" if el in C.OPTIONAL_ELEMENTS else "Y", "element_code": el,
                                                 "transform_rule_code": transform_for(el, f.data_type, "PA", C.ELEMENTS[el][2]),
                                                 "business_description": C.ELEMENTS[el][3]}, "SME proposal")


def approve_baseline(con, actor: str):
    """Demo helper: approve everything effective before the 2027 change set."""
    with db.tx(con):
        for t, key in db.META_TABLES.items():
            for r in db.rows(con, f"SELECT {key} AS id FROM {t} WHERE status='PENDING' AND eff_date < ?", (C.CHANGE_EFF,)):
                db.set_status(con, t, r["id"], "APPROVED", actor, "Demo baseline approval")


# ============================================================ sample source data
GW_CODES = {"TRANSACTION_TYPE": {"NB": "Submission", "RN": "Renewal", "EN": "PolicyChange", "CN": "Cancellation"},
            "CLAIM_STATUS": {"OP": "open", "CL": "closed", "RO": "reopened"},
            "CONSTRUCTION": {"FR": "Frame", "JM": "JoistedMasonry", "NC": "NonCombustible", "FRS": "FireResistive"},
            "DEDUCTIBLE": {"D500": "500", "D1000": "1000", "D2500": "2500", "D250": "250"},
            "CAUSE_OF_LOSS": {"WATER": "waterdamage", "WIND": "wind", "FIRE": "fire"}}
DC_CODES = {"TRANSACTION_TYPE": {"NB": "N", "RN": "R", "EN": "E", "CN": "C"},
            "CLAIM_STATUS": {"OP": "O", "CL": "C"},
            "CONSTRUCTION": {"FR": "1", "JM": "2"},
            "DEDUCTIBLE": {"D500": "500", "D1000": "1000", "D2500": "2500", "D250": "250"}}

STATE_ZIP = {"NJ": "07", "NY": "10", "PA": "19", "TX": "75", "FL": "33", "IL": "60", "GA": "30", "OH": "44"}


def _opts(pl, lob):
    from .engine import in_scope
    return [o[1] for o in C.OPTIONS.get(pl, []) if in_scope(o[0], lob) and (len(o) < 5 or o[4] <= "2026-09-30")]


def _src_val(sysname, pl, canon_code):
    table = (GW_CODES if sysname == "Guidewire" else DC_CODES).get(pl, {})
    return table.get(canon_code, canon_code)


def _payload(lob, rt, sysname, rng, acct: date, n: int, pa_2027=False):
    elements = {**C.ELEMENTS, **(C.NEW_2027_ELEMENTS if pa_2027 else {})}
    layout_els = {e for (lo, r, _), e in C.FIELD_OVERRIDES.items() if lo == lob and r == rt}
    layout_els |= set(_layout_elements(lob, rt))
    if lob in C.AUTO_LOBS:
        layout_els.add("COVERAGE")
    if pa_2027:
        layout_els |= {"TELEMATICS_IND", "RIDESHARE_IND"}
    col = 4 if sysname == "Guidewire" else 5
    if rt == "PREMIUM":
        eff = (acct - timedelta(days=rng.randint(0, 60))).replace(day=1)
    else:
        eff = (acct - timedelta(days=rng.randint(30, 170) if lob == "PA" else rng.randint(150, 330))).replace(day=1)
    exp = eff + timedelta(days=182) if lob == "PA" else eff.replace(year=eff.year + 1)
    st = rng.choice(list(STATE_ZIP))
    vals = {}
    for el in sorted(layout_els):
        spec = elements[el]
        attr = spec[col]
        if not attr:
            continue
        pl = spec[2]
        if el == "ACCT_DATE":
            v = acct.isoformat()
        elif el == "POLICY_NUMBER":
            v = f"{lob}{'GW' if col == 4 else 'DC'}{100000 + n:06d}"
        elif el == "POLICY_EFF_DATE":
            v = eff.isoformat()
        elif el == "POLICY_EXP_DATE":
            v = exp.isoformat()
        elif el == "STATE":
            v = st
        elif el in ("RISK_ZIP", "LOSS_ZIP"):
            v = f"{STATE_ZIP[st]}{rng.randint(100, 999)}"
        elif el == "TERRITORY":
            v = str(rng.randint(1, 120))
        elif el == "CLASS_CODE":
            v = str(rng.choice([1101, 7398, 91111, 49451, 61217, 10040, 65121, 99999, 5410, 41650]))
        elif el == "LIMIT_AMOUNT":
            v = str(rng.choice([150000, 250000, 400000, 750000, 1200000, 2500000]))
        elif el == "WRITTEN_PREMIUM":
            v = f"{rng.uniform(150, 9500):.2f}"
        elif el == "EXPOSURE":
            v = str(rng.choice([0.5, 1, 1, 2, 3.5])) if lob in C.AUTO_LOBS else str(rng.randint(10, 9000))
        elif el == "EMPLOYEE_COUNT":
            v = str(rng.randint(3, 400))
        elif el == "LOSS_DATE":
            lo = max(eff, acct - timedelta(days=120))
            v = (lo + timedelta(days=rng.randint(0, max(0, (min(exp, acct) - lo).days)))).isoformat()
        elif el == "CLAIM_NUMBER":
            v = f"CL{lob}{200000 + n:07d}"
        elif el == "PAID_LOSS":
            v = f"{rng.uniform(0, 25000):.2f}"
        elif el == "OS_RESERVE":
            v = f"{rng.uniform(0, 40000):.2f}"
        elif el == "ALAE":
            v = f"{rng.uniform(0, 3000):.2f}"
        elif el == "CAT_CODE":
            v = ""
        elif el == "VEHICLE_SYMBOL":
            v = str(rng.randint(10, 27))
        elif el == "DRIVER_POINTS":
            v = str(rng.randint(0, 4))
        elif el == "COMPANY_USE":
            v = f"REF{n:05d}"
        elif el == "VEHICLE_TYPE":
            v = str(rng.choice([11, 21, 31, 41]))
        elif el == "CLAIM_STATUS":
            v = _src_val(("Guidewire" if col == 4 else "DuckCreek"), pl, "OP")
        elif el == "TRANSACTION_TYPE":
            v = _src_val(("Guidewire" if col == 4 else "DuckCreek"), pl, rng.choice(["NB", "RN", "RN", "EN"]))
        elif el == "COVERAGE" and lob in C.AUTO_LOBS:
            v = rng.choice(["BI", "PD", "COLL", "COMP", "PIP"] if lob == "PA" else ["BI", "PD", "COLL", "COMP"])
        elif el == "CAUSE_OF_LOSS" and lob in C.AUTO_LOBS:
            v = None  # filled from coverage below
        elif pl:
            choices = _opts(pl, lob)
            if el == "MAJOR_LINE" or el == "LOB_CODE":
                continue
            v = _src_val(("Guidewire" if col == 4 else "DuckCreek"), pl, rng.choice(choices)) if choices else ""
        else:
            v = ""
        if v is not None:
            vals[attr] = v
    if lob in C.AUTO_LOBS and rt == "LOSS":
        cov_attr = elements["COVERAGE"][col]
        vals[elements["CAUSE_OF_LOSS"][col]] = vals[cov_attr]
    if rt == "LOSS":  # source claims carry the policy term even though ISO loss records do not report it
        vals[elements["POLICY_EFF_DATE"][col]] = eff.isoformat()
        vals[elements["POLICY_EXP_DATE"][col]] = exp.isoformat()
        vals[elements["CLAIM_STATUS"][col]] = _src_val("Guidewire" if col == 4 else "DuckCreek", "CLAIM_STATUS", "OP")
    return vals


_LAYOUT_CACHE = {}


def _layout_elements(lob, rt):
    if not _LAYOUT_CACHE:
        for lay in parse_all(LAYOUT_DIR):
            _LAYOUT_CACHE[(lay.lob, lay.record_type)] = [
                C.FIELD_OVERRIDES.get((lay.lob, lay.record_type, f.name)) or C.FIELD_TO_ELEMENT[f.name] for f in lay.fields]
    return _LAYOUT_CACHE[(lob, rt)]


def _sample_transactions(con) -> int:
    rng = random.Random(150)
    n = 0
    acct_days = [date(2026, 7, 15), date(2026, 8, 14), date(2026, 9, 10), date(2026, 9, 25), date(2026, 9, 30)]

    def add(lob, rt, sysname, payload, acct, key=None):
        nonlocal n
        n += 1
        db.insert(con, "source_transaction", {"source_system": sysname, "source_txn_key": key or f"{sysname[:2].upper()}-{lob}-{rt[0]}-{n:05d}",
                                              "record_type": rt, "lob_code": lob, "accounting_date": acct.isoformat(),
                                              "payload_json": json.dumps(payload)})

    for lob, *_ in C.LOBS:
        for rt in ("PREMIUM", "LOSS"):
            batch = []
            for i in range(14 if rt == "PREMIUM" else 10):
                sysname = "Guidewire" if i % 3 else "DuckCreek"
                acct = rng.choice(acct_days)
                p = _payload(lob, rt, sysname, rng, acct, n + 1)
                batch.append((sysname, p, acct))
            # ---- deliberate defects for SME review (all on Guidewire rows)
            gw = [b for b in batch if b[0] == "Guidewire"]
            if rt == "PREMIUM":
                p = gw[0][1]
                p["PeriodEnd"], p["PeriodStart"] = p["PeriodStart"], p["PeriodEnd"]          # VR002 exp before eff
                gw[1][1]["TransactionType"] = "Rewrite"                                       # PCK001 no alias
                gw[2][1]["PostalCode"] = "1234"                                               # VR003 bad ZIP
                batch.append(gw[3])                                                           # ISO duplicate
            else:
                p = gw[0][1]
                p["ClaimStatus"] = "closed"                                                   # VR006 closed w/ reserve
                p["OutstandingReserve"] = "1500.00"
                gw[1][1]["LossDate"] = "2019-05-05"                                           # VR004 outside policy
                gw[2][1]["PaidLoss"] = "-850.00"                                              # VR007 recovery warning
                if lob in ("HO", "CP", "BP"):
                    gw[3][1]["LossCause"] = "wind"                                            # VR011 cat code warning
            for sysname, p, acct in batch:
                add(lob, rt, sysname, dict(p), acct)
    # ---- January 2027 Personal Auto premium for the pending v2 layout (telematics / rideshare)
    for i in range(6):
        acct = date(2027, 1, 20)
        p = _payload("PA", "PREMIUM", "Guidewire", rng, acct, n + 1, pa_2027=True)
        p["PeriodStart"], p["PeriodEnd"] = "2027-01-01", "2027-07-01"
        p["TelematicsInd"], p["RideshareInd"] = rng.choice("YN"), rng.choice("YN")
        # attributes the new Guidewire release sends that the canonical model does not know yet (Canonical Gaps demo)
        p["AgentComment"] = rng.choice(["Customer asked for paperless", "Garaged at second home in winter", "Referred by existing insured"])
        p["GaragingCounty"] = rng.choice(["Bergen", "Essex", "Morris", "Hudson"])
        p["DiscountCode"] = rng.choice(["MULTIPOL", "GOODSTU", "MULTIPOL", "NONE"])
        add("PA", "PREMIUM", "Guidewire", p, acct)
    # ---- January 2027 HO losses on 2027 policies using the proposed water split
    for i in range(4):
        acct = date(2027, 1, 28)
        p = _payload("HO", "LOSS", "Guidewire", rng, acct, n + 1)
        p["PeriodStart"], p["PeriodEnd"], p["LossDate"] = "2027-01-01", "2028-01-01", "2027-01-1" + str(i)
        p["LossCause"] = "water_weather" if i % 2 else "water_plumbing"
        add("HO", "LOSS", "Guidewire", p, acct)
    return n


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(db.DEFAULT_DB))
    ap.add_argument("--demo-approve", action="store_true")
    a = ap.parse_args()
    s = build(Path(a.db), a.demo_approve)
    print(json.dumps(s, indent=1))
