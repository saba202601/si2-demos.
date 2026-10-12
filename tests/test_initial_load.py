"""Initial load: readers, profiling, key proposals, create + load, reconciliation."""
import io
import sqlite3
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from migrate import initial_load as IL  # noqa: E402


@pytest.fixture(scope="module")
def sample():
    st = IL.stage(IL.sample_files(), [IL.SAMPLE_API])
    prof = IL.profile(st)
    return st, prof, IL.propose(st, prof)


def _prop(props, kind, table, ref=None):
    p = props[(props.kind == kind) & (props.table == table)]
    if ref:
        p = p[p.ref_table == ref]
    return p.iloc[0]


def test_every_format_becomes_tables(sample):
    st, _, _ = sample
    assert {"agent", "policy", "claim", "claim_payment", "pers_policy", "pers_veh", "coverage", "invoice",
            "installment", "driver", "violation"} <= set(st.tables)
    assert len(st.tables["agent"]) == 3                               # INSERTs read from the Oracle script
    assert any("not executed" in n and "PURGE_OLD_CLAIMS" in n for _, n in st.notes)   # PL/SQL is never run
    assert len(st.tables["driver"]) == 9                              # both API pages


def test_profiling_keeps_codes_as_text_and_reads_dates_and_money(sample):
    _, prof, _ = sample
    t = prof.set_index(["table", "column"]).type
    assert t["policy", "zip_cd"] == "TEXT"                            # 07030 keeps its zero
    assert t["claim_payment", "pmt_id"] == "TEXT"
    assert t["claim_payment", "pmt_dt"] == "DATE"                     # MM/DD/YYYY
    assert t["policy", "written_prem"] == "MONEY"                     # "$1,234.00"
    assert prof.set_index(["table", "column"]).pick_list["claim", "claim_status"]


def test_keys_declared_nested_found_and_term_in_force(sample):
    _, _, props = sample
    assert _prop(props, "PK", "policy").columns == ["pol_no", "eff_dt"]
    assert _prop(props, "PK", "coverage").columns == ["pers_veh_veh_identification_number", "coverage_cd"]
    assert _prop(props, "FK", "pers_veh").method == "Nested in file"
    # the FK the DDL forgot
    fk = _prop(props, "FK", "claim_payment", "claim")
    assert fk.method == "Found in the data" and "not declared" in fk.evidence and "1 value(s) have no parent" in fk.evidence
    # claims attach to the policy term in force on the loss date, not just the policy number
    t = _prop(props, "FK", "claim", "policy")
    assert t.method == "Term in force on the date" and t.columns == ["pol_no", "loss_dt"]
    # XML and JSON carry the term date: exact pair
    assert _prop(props, "FK", "pers_policy", "policy").columns == ["policy_number", "contract_term_effective_dt"]
    # one column, two possible parents -> conflict for the SME
    assert props[(props.table == "driver") & (props.kind == "FK")].conflict.all()
    # a child never links to a table keyed by its own child rows (vehicle -> coverage)
    assert not ((props.kind == "FK") & (props.table == "pers_veh") & (props.ref_table == "coverage")).any()


def test_create_and_load_reconciles(sample, tmp_path):
    st, prof, props = sample
    props = props.copy()
    props.loc[(props.confidence >= 90) & ~props.conflict, "status"] = "Approved"
    props.loc[props.kind == "PICKLIST", "status"] = "Approved"
    r = IL.build_and_load(st, prof, props, str(tmp_path / "il.db"), "tester")
    rec = r["recon"].set_index("table")
    assert (rec["rows balance"] == "PASS").all() and (rec["totals balance"] != "FAIL").all()
    assert r["fk_violations"] == 0
    assert r["order"].index("policy") < r["order"].index("claim") < r["order"].index("claim_payment")
    assert list(r["quarantine"].table) == ["claim_payment"]           # the orphan payment CL-0999
    con = sqlite3.connect(tmp_path / "il.db")
    # every claim points at the right term: loss date between that term's dates
    bad = con.execute("""select count(*) from claim c join policy p on p.policy_sk = c.policy_sk
                         where not (p.eff_dt <= c.loss_dt and c.loss_dt < p.exp_dt) or p.pol_no <> c.pol_no""").fetchone()[0]
    assert bad == 0 and con.execute("select count(*) from claim where policy_sk is null").fetchone()[0] == 0
    assert con.execute("select zip_cd from policy where pol_no='PA1000102'").fetchone()[0] == "07030"
    assert con.execute("select count(distinct list_name) from pick_list").fetchone()[0] >= 5
    assert con.execute("select min(effective_to) from claim").fetchone()[0] == "9999-12-31"
    con.close()
    assert "IDENTITY" in IL.ddl(st, prof, props, "mssql") and "UQ_policy_business_key" in IL.ddl(st, prof, props, "mssql")


def test_bad_values_are_quarantined_not_dropped(tmp_path):
    csv = b"POLICY_NO,EFF_DATE,PREMIUM_AMT\nP1,2025-01-01,100.00\nP2,not a date,200.00\nP3,2025-03-01,abc\n"
    st = IL.stage([("pol.csv", csv)])
    prof = IL.profile(st)
    prof.loc[prof.column == "eff_date", "type"] = "DATE"            # SME confirms the types
    prof.loc[prof.column == "premium_amt", "type"] = "MONEY"
    props = IL.propose(st, prof)
    props["status"] = "Approved"
    r = IL.build_and_load(st, prof, props, str(tmp_path / "q.db"), "t")
    assert r["recon"].iloc[0]["loaded"] == 1 and len(r["quarantine"]) == 2
    assert r["recon"].iloc[0]["rows balance"] == "PASS"


def test_pdf_text_table_and_unreadable_sources(tmp_path):
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    for i, line in enumerate(["Agent list", "AGENT_NO | AGENT_NM | STATE", "AG201 | North Agency | NY",
                              "AG202 | South Agency | FL"]):
        c.drawString(72, 720 - 16 * i, line)
    c.save()
    st = IL.stage([("agents.pdf", buf.getvalue()), ("notes.docx", b"x"), ("broken.json", b"{not json")],
                  ["http://example.com/api"])
    assert len(st.tables["agents"]) == 2 and list(st.tables["agents"].columns) == ["agent_no", "agent_nm", "state"]
    notes = " ".join(n for _, n in st.notes)
    assert "not supported" in notes and "could not be read" in notes and "https" in notes


def test_sql_reader_handles_alter_and_inline_keys():
    sql = b"""CREATE TABLE A (ID NUMBER PRIMARY KEY, NM VARCHAR2(10));
CREATE TABLE B (BID NUMBER, AID NUMBER REFERENCES A(ID), AMT NUMBER(10,2));
ALTER TABLE B ADD CONSTRAINT PK_B PRIMARY KEY (BID);
INSERT INTO A (ID, NM) VALUES (1, 'it''s');
INSERT INTO B (BID, AID, AMT) VALUES (10, 1, 5.5);"""
    st = IL.stage([("x.sql", sql)])
    assert st.declared_pk == {"a": ["id"], "b": ["bid"]}
    assert ("b", ["aid"], "a", ["id"], "Declared in DDL") in st.declared_fk
    assert st.tables["a"].iloc[0]["nm"] == "it's" and st.declared_types["b"]["amt"] == "MONEY"
