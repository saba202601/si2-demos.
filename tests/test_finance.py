"""Financial Reporting: Yellow Book catalog, generation, edits, ontology, database round trip and the app flow."""
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


@pytest.fixture(scope="module")
def built():
    from finance import engine as E
    from finance import source as S
    src = S.build()
    stmt = E.generate(src)
    return src, stmt, E.edits(stmt)


def test_catalog_has_every_page_and_unique_fields():
    from finance import blank as B
    f = B.fields()
    assert f.field_id.is_unique
    assert len(f) > 15000
    assert {"P2", "P3", "P4", "P5", "U1", "U1A", "U1B", "U2", "U2A", "U3", "NII", "SP", "SF3", "H5", "SP1SUM"} <= set(f.page_code)
    assert (f.query("page_code == 'P4' and line_no == '1'").line_caption == "Premiums earned").all()
    assert len(B.ASL) == 55 and B.ASL[-1][0] == "35"


def test_statement_balances_and_every_edit_passes(built):
    _src, stmt, edits = built
    assert (edits.result == "PASS").all(), edits[edits.result != "PASS"].to_dict("records")
    assert abs(stmt.get("P2", "28", "3") - stmt.get("P3", "38", "1")) < 1
    assert stmt.get("P2", "5", "3") > 0, "cash must not be negative in the synthetic book"


def test_late_gl_entry_is_caught_by_the_state_page_reconciliation():
    from finance import engine as E
    from finance import source as S
    bad = E.edits(E.generate(S.build(late_gl_entry=1_250_000)))
    failing = set(bad[bad.result == "FAIL"].edit_id)
    assert {"E20", "E21"} <= failing
    assert abs(bad.set_index("edit_id").at["E20", "difference"] + 1_250_000) < 1


def test_ontology_is_valid_and_every_field_has_a_meaning():
    from finance import ontology as O
    fc = O.field_concepts()
    assert (fc.concept_id != "FinancialConcept").all()
    rel = O.relations()
    assert {"isA", "derivedFrom", "reportedOn", "checks", "rollsUpTo", "mapsToCanonical"} <= set(rel.predicate)
    try:
        import rdflib
    except ImportError:
        return
    g = rdflib.Graph()
    g.parse(data=O.turtle(), format="turtle")
    assert len(g) > 1000


def test_database_round_trip_on_sqlite(tmp_path, monkeypatch, built):
    monkeypatch.setenv("SI2_FIN_BACKEND", "sqlite")
    from finance import db
    monkeypatch.setattr(db, "SQLITE_PATH", tmp_path / "fin.db")
    from finance import engine as E
    from finance import ontology as O
    src, stmt, edits = built
    d = db.Db("sqlite")
    d.create()
    db.load_catalog(d, O.concepts(), O.relations(), O.field_concepts())
    db.load_source(d, src)
    back = db.read_source(d, src)
    again = E.edits(E.generate(back))
    assert (again.result == "PASS").all()
    n = db.save_run(d, "T1", stmt, edits, {"company": "x", "statement_year": 2025, "source": "t", "created_by": "Saba",
                                            "created_at": "2026-10-25T10:00:00", "status": "Pending approval"})
    assert n == len(stmt.values)
    assert "fin.YbField" in db.ddl("mssql") and "CREATE SCHEMA fin" in db.ddl("mssql")


def test_app_end_to_end(tmp_path, monkeypatch):
    monkeypatch.setenv("SI2_STATE_DB", str(tmp_path / "state.db"))
    monkeypatch.setenv("SI2_FIN_BACKEND", "sqlite")
    monkeypatch.setenv("SI2_FIN_DB", str(tmp_path / "finance.db"))
    monkeypatch.chdir(ROOT)
    from finance import db
    monkeypatch.setattr(db, "SQLITE_PATH", tmp_path / "finance.db")
    from si2_common import store
    store._CON.clear()
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(str(ROOT / "app_finance.py"), default_timeout=300).run()
    assert not at.exception, at.exception[0].message
    for step in at.radio(key="step").options:
        at.radio(key="step").set_value(step).run()
        assert not at.exception, f"{step}: {at.exception[0].message}"
    at.radio(key="step").set_value("2 · Tables").run()
    at.button[0].click().run()
    assert not at.exception and any("Loaded" in s.value for s in at.success)
    at.radio(key="step").set_value("4 · Generate statement").run()
    at.button[0].click().run()
    assert not at.exception
    at.radio(key="step").set_value("8 · Approve & file").run()
    at.button[0].click().run()
    assert any("submitted request" in s.value for s in at.success), [e.value for e in at.error]
    at.sidebar.text_input(key="fin_actor").set_value("Sabasi").run()
    approve = [b for b in at.button if b.label == "Approve"]
    approve[0].click().run()
    assert not at.exception
    assert any("Approved by Sabasi" in s.value for s in at.success)
