"""End-to-end tests: python -m pytest -q"""
import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent          # iso_bureau package
sys.path.insert(0, str(ROOT.parent))                    # repo root

from iso_bureau import db, engine as E, seed  # noqa: E402
from iso_bureau.layouts import parse_all  # noqa: E402

LOBS = ["PA", "HO", "CA", "CP", "GL", "IM", "CR", "BP", "FI", "BR"]


@pytest.fixture(scope="session")
def template_db(tmp_path_factory):
    p = tmp_path_factory.mktemp("db") / "template.db"
    seed.build(p, demo_approve=True)
    return p


@pytest.fixture
def con(template_db, tmp_path):
    p = tmp_path / "t.db"
    shutil.copy(template_db, p)
    c = db.connect(p)
    yield c
    c.close()


Q3 = E.period_bounds("QUARTERLY", 2026, 3)


# ---------------------------------------------------------------- formatting
def test_overpunch_roundtrip():
    assert E.overpunch("292.66", 10) == "000002926F"
    assert E.overpunch("-850.00", 10) == "000008500}"
    assert E.overpunch("0", 10) == "000000000{"
    for v in ("1234.56", "-0.01", "99.99", "-12345678.90"):
        assert float(E.un_overpunch(E.overpunch(v, 10))) == float(v)
    with pytest.raises(ValueError):
        E.overpunch("123456789012.00", 10)


def test_period_bounds():
    assert E.period_bounds("MONTHLY", 2026, 2) == ("2026-02-01", "2026-02-28")
    assert E.period_bounds("MONTHLY", 2026, 12) == ("2026-12-01", "2026-12-31")
    assert E.period_bounds("QUARTERLY", 2026, 4) == ("2026-10-01", "2026-12-31")


# ------------------------------------------------------------------- layouts
def test_all_layouts_are_150_bytes():
    lays = parse_all(ROOT / "data" / "iso_layouts")
    assert len(lays) == 20
    for lay in lays:
        assert lay.fields[-1].end == 150, (lay.lob, lay.record_type)


def test_commercial_auto_excel_date_positions_flagged():
    ca = [l for l in parse_all(ROOT / "data" / "iso_layouts") if l.lob == "CA"]
    assert all(len(l.findings) == 4 for l in ca)
    assert ca[0].fields[3].start == 9 and ca[0].fields[3].length == 14


# ----------------------------------------------------------- full pipeline
@pytest.mark.parametrize("lob", LOBS)
@pytest.mark.parametrize("rt", ["PREMIUM", "LOSS"])
def test_generate_validate_every_line(con, lob, rt):
    assert E.readiness(con, "ISO", lob, rt, Q3[1]) == []
    bid = E.generate_batch(con, "ISO", lob, rt, "QUARTERLY", *Q3, "pytest")
    b = E.validate_batch(con, bid, "pytest")
    assert b["status"] == "VALIDATED"
    assert b["record_count"] >= 10 and b["valid_count"] >= 7
    recs = db.rows(con, "SELECT * FROM submission_record WHERE batch_id=?", (bid,))
    assert all(len(r["record_text"]) == 150 for r in recs)
    codes = {m["code"] for r in recs for m in json.loads(r["messages_json"])}
    expected = {"VR002", "PCK001"} if rt == "PREMIUM" else {"VR006", "VR004"}
    assert expected <= codes


def test_submit_reject_correct_resubmit_close(con):
    bid = E.generate_batch(con, "ISO", "HO", "PREMIUM", "QUARTERLY", *Q3, "pytest")
    E.validate_batch(con, bid, "pytest")
    with pytest.raises(ValueError):
        E.submit_batch(con, bid, "pytest")  # SME approval required first
    E.sme_approve_batch(con, bid, "SME")
    res = E.submit_batch(con, bid, "pytest")
    assert res["held"] == 3 and res["rejected"] == 1 and res["status"] == "PARTIALLY_ACCEPTED"
    b = db.one(con, "SELECT * FROM submission_batch WHERE batch_id=?", (bid,))
    assert all(len(l) == 150 for l in b["file_text"].splitlines())
    with pytest.raises(ValueError):
        E.close_batch(con, bid, "SME")  # open items, no reason

    # SME corrects every open item at the source (new rows, originals untouched)
    for r in E.open_corrections(con, bid):
        p = json.loads(r["payload_json"])
        if p.get("PeriodEnd", "9") < p.get("PeriodStart", "0"):
            p["PeriodStart"], p["PeriodEnd"] = p["PeriodEnd"], p["PeriodStart"]
        if p.get("TransactionType") == "Rewrite":
            p["TransactionType"] = "Renewal"
        if len(p.get("PostalCode", "00000")) != 5:
            p["PostalCode"] = "07001"
        if r["status"] == "REJECTED":
            p["WrittenPremium"] = str(round(float(p["WrittenPremium"]) + 1, 2))
        E.correct_transaction(con, r["txn_id"], p, "SME", "fixed in test")
    before = db.one(con, "SELECT COUNT(*) n FROM source_transaction")["n"]
    child = E.resubmission_batch(con, bid, "pytest")
    E.validate_batch(con, child, "pytest")
    cb = db.one(con, "SELECT * FROM submission_batch WHERE batch_id=?", (child,))
    assert cb["error_count"] == 0 and cb["parent_batch_id"] == bid
    E.sme_approve_batch(con, child, "SME")
    assert E.submit_batch(con, child, "pytest")["status"] == "ACCEPTED"
    E.close_batch(con, bid, "SME")
    E.close_batch(con, child, "SME")
    assert db.one(con, "SELECT status FROM submission_batch WHERE batch_id=?", (bid,))["status"] == "CLOSED"
    assert db.one(con, "SELECT COUNT(*) n FROM source_transaction")["n"] == before  # no deletes


def test_accepted_transactions_not_reported_twice(con):
    bid = E.generate_batch(con, "ISO", "GL", "LOSS", "QUARTERLY", *Q3, "pytest")
    E.validate_batch(con, bid, "pytest")
    E.sme_approve_batch(con, bid, "SME")
    E.submit_batch(con, bid, "pytest")
    again = E.generate_batch(con, "ISO", "GL", "LOSS", "QUARTERLY", *Q3, "pytest")
    n = db.one(con, "SELECT record_count FROM submission_batch WHERE batch_id=?", (again,))["record_count"]
    assert n == 2  # only the two held error records remain unreported


# ------------------------------------------------------- effective dating
def test_pending_2027_layout_not_used_until_approved(con):
    jan = E.period_bounds("MONTHLY", 2027, 1)
    lay, fields = E.resolve_layout(con, "ISO", "PA", "PREMIUM", jan[1])
    assert lay["version_no"] == 1  # v2 still pending
    lay2, f2 = E.resolve_layout(con, "ISO", "PA", "PREMIUM", jan[1], sandbox=True)
    assert lay2["version_no"] == 2 and len(f2) == 20 and E.layout_problems(f2) == []

    # sandbox preview uses pending metadata and can never be submitted
    sb = E.generate_batch(con, "ISO", "PA", "PREMIUM", "MONTHLY", *jan, "SME", sandbox=True)
    E.validate_batch(con, sb, "SME")
    recs = db.rows(con, "SELECT * FROM submission_record WHERE batch_id=?", (sb,))
    assert recs and all(r["record_text"][86] in "YN" for r in recs if r["status"] != "ERROR")
    with pytest.raises(ValueError):
        E.sme_approve_batch(con, sb, "SME")

    # SME approves everything pending -> v1 expires 2026-12-31, v2 serves 2027
    for t, key in db.META_TABLES.items():
        for r in db.rows(con, f"SELECT {key} id FROM {t} WHERE status='PENDING'"):
            db.set_status(con, t, r["id"], "APPROVED", "SME")
    con.commit()
    v1 = db.one(con, "SELECT * FROM layout_version WHERE lob_code='PA' AND record_type='PREMIUM' AND version_no=1")
    assert v1["exp_date"] == "2026-12-31"
    assert E.resolve_layout(con, "ISO", "PA", "PREMIUM", "2026-12-31")[0]["version_no"] == 1
    assert E.resolve_layout(con, "ISO", "PA", "PREMIUM", jan[1])[0]["version_no"] == 2
    bid = E.generate_batch(con, "ISO", "PA", "PREMIUM", "MONTHLY", *jan, "pytest")
    b = E.validate_batch(con, bid, "pytest")
    assert b["error_count"] == 0 and b["record_count"] == 6


def test_option_effective_by_policy_date(con):
    """HO water split: 2027 policies use WATERW/WATERN only after approval; 2026 policies keep WATER."""
    jan = E.period_bounds("MONTHLY", 2027, 1)
    bid = E.generate_batch(con, "ISO", "HO", "LOSS", "MONTHLY", *jan, "pytest")
    recs = db.rows(con, "SELECT * FROM submission_record WHERE batch_id=?", (bid,))
    assert all(r["status"] == "ERROR" for r in recs)  # aliases still pending
    for t, key in db.META_TABLES.items():
        for r in db.rows(con, f"SELECT {key} id FROM {t} WHERE status='PENDING'"):
            db.set_status(con, t, r["id"], "APPROVED", "SME")
    con.commit()
    bid = E.generate_batch(con, "ISO", "HO", "LOSS", "MONTHLY", *jan, "pytest")
    recs = db.rows(con, "SELECT * FROM submission_record WHERE batch_id=?", (bid,))
    assert {r["record_text"][51:53] for r in recs} == {"13", "14"}
    water = db.rows(con, "SELECT * FROM picklist_option WHERE option_code='WATER' ORDER BY option_id")
    assert water[0]["exp_date"] == "2026-12-31" and water[1]["lob_scope"] == "CP,BP,BR,IM"


def test_supersede_rejected_keeps_current(con):
    r = db.one(con, "SELECT * FROM business_rule WHERE rule_code='VR008' AND status='APPROVED'")
    new = db.supersede(con, "business_rule", r["rule_id"], {"severity": "ERROR"}, "2026-11-01", "SME")
    db.set_status(con, "business_rule", new, "REJECTED", "SME", "keep as warning")
    con.commit()
    assert db.one(con, "SELECT exp_date FROM business_rule WHERE rule_id=?", (r["rule_id"],))["exp_date"] == db.OPEN_END


def test_unapproved_metadata_blocks_run(con):
    lay = db.one(con, "SELECT layout_id FROM layout_version WHERE lob_code='CR' AND record_type='LOSS'")
    con.execute("UPDATE layout_version SET status='PENDING' WHERE layout_id=?", (lay["layout_id"],))
    issues = E.readiness(con, "ISO", "CR", "LOSS", Q3[1])
    assert issues and "PENDING" in issues[0]["issue"]
    with pytest.raises(ValueError):
        E.generate_batch(con, "ISO", "CR", "LOSS", "QUARTERLY", *Q3, "pytest")


# ----------------------------------------------------------- SME templates
def test_template_roundtrip(con):
    import io
    import openpyxl
    from iso_bureau import templates as T
    wb = openpyxl.load_workbook(io.BytesIO(T.build_template(["picklist_option", "bureau_code_map", "business_rule"])))
    wb["picklist_option"].append(["TRANSACTION_TYPE", "*", "RW", "Rewrite", "Policy rewrite", "2026-01-01", None])
    wb["bureau_code_map"].append(["ISO", "*", "TRANSACTION_TYPE", "RW", "16", "2026-01-01", None])
    # change to an existing rule: later eff date -> supersede
    wb["business_rule"].append(["VR008", "Zero premium transaction", "VALIDATION", "*", "PREMIUM", None, "WRITTEN_PREMIUM",
                                '{"op":"compare","left":"WRITTEN_PREMIUM","cmp":"!=","value":0}', "ERROR", "Zero premium",
                                "Now an error", "2026-11-01"])
    wb["business_rule"].append(["VR999", "bad", "VALIDATION", "*", "*", None, "NOPE", "{bad json", "ERROR", None, "x", "2026-01-01"])
    bio = io.BytesIO(); wb.save(bio)
    data = T.read_upload(bio.getvalue())
    res = T.check_and_load(con, data, "SME", commit=False)
    assert [r["result"] for r in res] == ["new", "new", "supersede", "error"]
    assert "NOPE" in res[3]["detail"] and "JSON" in res[3]["detail"]
    data["business_rule"] = data["business_rule"][:1]
    res = T.check_and_load(con, data, "SME", commit=True)
    assert all(r["result"] != "error" for r in res)
    rw = db.one(con, "SELECT * FROM picklist_option WHERE option_code='RW'")
    assert rw["status"] == "PENDING"
    new_rule = db.one(con, "SELECT * FROM business_rule WHERE rule_code='VR008' AND status='PENDING'")
    assert new_rule["supersedes_id"] and new_rule["severity"] == "ERROR"
