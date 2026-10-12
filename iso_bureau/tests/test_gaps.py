"""Canonical Gaps: ISO bureau and migration adapters (python -m pytest -q iso_bureau/tests)."""
import json
import shutil
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT.parent))

from iso_bureau import db, engine as E, gaps as G, seed  # noqa: E402
from migrate import engine as ME, gaps as MG, legacy  # noqa: E402
from si2_common.gaps import draft_description, infer_type, to_code, words  # noqa: E402


def test_naming_helpers():
    assert words("TelematicsInd") == ["TELEMATICS", "INDICATOR"]
    assert to_code("CL-OS-RSV") == "CLAIM_OUTSTANDING_RESERVE"
    assert infer_type(["Y", "N", "Y", "N"]) == "CODE"
    assert infer_type(["2026-01-01", "2026-02-01"]) == "DATE"
    assert "Drafted by SI²" in draft_description("AgentComment", "TEXT", ["x"])


@pytest.fixture
def con(tmp_path_factory, tmp_path):
    p = tmp_path / "g.db"
    seed.build(p, demo_approve=True)
    c = db.connect(p)
    yield c
    c.close()


def test_iso_gap_lifecycle(con):
    gaps = {g.name: g for g in G.scan(con)}
    assert {"AgentComment", "GaragingCounty", "DiscountCode", "Rewrite"} <= set(gaps)
    assert gaps["Rewrite"].kind == "CODE" and gaps["DiscountCode"].data_type == "CODE"
    h = G.Handler(con, "SME")
    h.not_needed(gaps["AgentComment"], "free text")
    h.add_new(gaps["DiscountCode"], dict(gaps["DiscountCode"].proposal))
    h.add_new(gaps["GaragingCounty"], dict(gaps["GaragingCounty"].proposal))
    h.add_new(gaps["Rewrite"], dict(gaps["Rewrite"].proposal, code="RW"))
    left = G.scan(con)
    assert [g.kind for g in left] == ["DEST_CODE"] and left[0].name == "RW"   # new code needs its ISO code
    h.add_new(left[0], dict(left[0].proposal, bureau_value="16"))
    assert G.scan(con) == []
    # the held 'Rewrite' record now reports, and nothing was deleted
    s, e = E.period_bounds("QUARTERLY", 2026, 3)
    bid = E.generate_batch(con, "ISO", "HO", "PREMIUM", "QUARTERLY", s, e, "t")
    codes = {m["code"] for r in db.rows(con, "SELECT messages_json FROM submission_record WHERE batch_id=?", (bid,))
             for m in json.loads(r["messages_json"])}
    assert "PCK001" not in codes
    jan = E.period_bounds("MONTHLY", 2027, 1)
    sb = E.generate_batch(con, "ISO", "PA", "PREMIUM", "MONTHLY", *jan, "t", sandbox=True)
    codes = {m["code"] for r in db.rows(con, "SELECT messages_json FROM submission_record WHERE batch_id=?", (sb,))
             for m in json.loads(r["messages_json"])}
    assert "MAP001" not in codes   # every source attribute is now mapped or marked not needed


def test_iso_pending_mode_and_destination_field(con):
    h = G.Handler(con, "SME", approve_now=False)
    g = next(x for x in G.scan(con) if x.name == "DiscountCode")
    h.add_new(g, dict(g.proposal))
    assert db.one(con, "SELECT status FROM canonical_element WHERE element_code='DISCOUNT_CODE'")["status"] == "PENDING"
    lay = db.one(con, "SELECT layout_id FROM layout_version WHERE lob_code='HO' AND record_type='PREMIUM'")
    with db.tx(con):
        db.add_pending(con, "layout_field", {"layout_id": lay["layout_id"], "seq": 99, "bureau_field_name": "Roof Age",
                                             "start_pos": 151, "length": 2, "field_format": "N", "element_code": "UNMAPPED",
                                             "transform_rule_code": "TR_ZEROPAD", "eff_date": "2027-01-01"}, "t")
    d = next(x for x in G.scan(con) if x.kind == "DEST_ELEMENT")
    G.Handler(con, "SME").add_new(d, dict(d.proposal, data_type="NUMBER"))
    rows = db.rows(con, "SELECT element_code, status FROM layout_field WHERE bureau_field_name='Roof Age' ORDER BY field_id")
    assert [(r["element_code"], r["status"]) for r in rows] == [("UNMAPPED", "REJECTED"), ("ROOF_AGE", "APPROVED")]


def test_migration_gap_lifecycle():
    ss = types.SimpleNamespace(src=legacy.load_samples(), syn_edits={}, map_ov={}, rejected=set(), val_ov={})
    ss.inv = ME.discover(ss.src)

    def recompute():
        canon = ME.build_canonical(ss.src["dest_schema"], ss.src["dest_picklists"])
        m = ME.match(ss.inv, canon, ss.map_ov)
        vm = ME.value_maps(ss.inv, m, canon, ss.src["dest_picklists"], ss.val_ov)
        ss.canon, ss.m, ss.vm, ss.cov = canon, m, vm, ME.coverage(m, canon, vm)

    recompute()
    h = MG.Handler(ss, "SME", recompute, lambda *a: None, lambda r: None)
    gaps = MG.scan(ss)
    kinds = {g.kind for g in gaps}
    assert kinds == {"ELEMENT", "CODE", "DEST_ELEMENT"}
    for g in gaps:
        if g.ref == "CLAIM_NOTES.AUTHOR":
            h.add_new(g, dict(g.proposal))
        elif g.kind == "ELEMENT" and g.candidates and g.candidates[0][2] >= 0.99:
            h.map_existing(g, g.candidates[0][0])
        elif g.kind == "ELEMENT":
            h.not_needed(g, "archive")
        elif g.kind == "CODE" and g.name == "S":
            h.add_new(g, dict(g.proposal))
        elif g.kind == "CODE":
            h.map_existing(g, g.candidates[0][0])
    for g in MG.scan(ss):
        h.map_existing(g, g.candidates[0][0])
    assert MG.scan(ss) == []
    _, dest, issues = ME.transform(ss.src, ss.inv, ss.m, ss.canon, ss.vm, ss.src["dest_schema"])
    assert issues.empty and ME.validate(dest, ss.src["dest_schema"], ss.src["dest_picklists"]).empty
    con = ME.load(dest, ss.src["dest_schema"])
    assert con.execute("SELECT COUNT(*) FROM claim WHERE author IS NOT NULL").fetchone()[0] > 0
    assert con.execute("SELECT COUNT(*) FROM policy WHERE policy_status='Suspended'").fetchone()[0] == 2
