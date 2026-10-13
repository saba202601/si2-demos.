"""Role-Based Super Intelligence: engines find what was planted, and every role's workbench renders."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from roles import book as B, si as S  # noqa: E402

CATALOG = json.loads((ROOT / "roles" / "data" / "roles.json").read_text())


@pytest.fixture(scope="module")
def b():
    return B.build()


def test_catalog_has_fifteen_roles_in_five_departments():
    assert len(CATALOG) == 15
    assert len({r["department"] for r in CATALOG}) == 5
    assert all(r["today"] and r["tomorrow"] and r["tasks"] and r["si"] for r in CATALOG)


def test_all_planted_fraud_rings_are_found(b):
    net, members = S.fraud_network(b["claims"])
    found = {g.fraud_truth.mode()[0] for g in members.values() if (g.fraud_truth != "").mean() > 0.5}
    planted = set(b["claims"].fraud_truth) - {""}
    assert planted and planted <= found


def test_texas_homeowners_rate_inadequacy_is_flagged(b):
    ra = S.rate_adequacy(b["policies"], b["claims"])
    tx = ra[(ra["product"] == "Homeowners") & (ra.state == "TX")].iloc[0]
    assert tx.si_flag == "Rate inadequate" and tx.indicated_change > 0.05


def test_reinsurance_improves_solvency(b):
    ev = S.cat_event_set(b["policies"])
    cl = S.chain_ladder(S.triangle(b["payments"]), boot=200)
    opt, _ = S.optimize_cat_xol(ev, S.DEFAULT_ERM)
    best = opt[opt.si_choice != ""].iloc[0]
    gross = S.capital(b["policies"], b["claims"], ev, cl, lambda x: x, S.DEFAULT_ERM)
    net = S.capital(b["policies"], b["claims"], ev, cl, S.xol(best.retention, best.limit), S.DEFAULT_ERM)
    assert net["solvency_ratio"] > gross["solvency_ratio"]
    assert net["solvency_ratio"] >= S.DEFAULT_ERM["min_solvency"]


def test_chain_ladder_reconciles(b):
    cl = S.chain_ladder(S.triangle(b["payments"]), boot=200)
    t = cl["table"]
    assert abs(t.ibnr.sum() - cl["ibnr_total"]) < 1
    assert (t.ultimate >= t.paid_to_date - 1e-6).all()
    assert cl["p50"] <= cl["p75"] <= cl["p995"]


def test_underwriting_respects_boundaries(b):
    uw = S.underwrite(b["submissions"], S.DEFAULT_UW)
    assert len(uw) == len(b["submissions"])
    assert uw.si_recommendation.nunique() >= 2


def test_every_role_renders(tmp_path, monkeypatch):
    from streamlit.testing.v1 import AppTest
    from si2_common import store
    monkeypatch.setenv("SI2_STATE_DB", str(tmp_path / "state.db"))
    monkeypatch.chdir(ROOT)
    store._CON.clear()
    at = AppTest.from_file(str(ROOT / "app_roles.py"), default_timeout=300)
    at.run()
    assert not at.exception, at.exception[0].message
    for r in CATALOG:
        at.selectbox(key="dept").set_value(r["department"]).run()
        at.radio(key="role_" + r["department"][:12]).set_value(r["role"]).run()
        assert not at.exception, f"{r['role']}: {at.exception[0].message}"
