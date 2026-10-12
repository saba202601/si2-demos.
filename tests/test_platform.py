"""Platform features: permanent store + two-person rule, personal data, code descriptions, data edits,
delta loads, hand-off to the migration, company canonical model, rating / rules approvals."""
import datetime as dt
import sqlite3
import sys
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from migrate import initial_load as IL  # noqa: E402
from si2_common import store  # noqa: E402


@pytest.fixture(autouse=True)
def state_db(tmp_path, monkeypatch):
    monkeypatch.setenv("SI2_STATE_DB", str(tmp_path / "state.db"))
    store._CON.clear()
    yield
    store._CON.clear()


# ------------------------------------------------------------------------------------------ store
def test_codec_round_trips_app_state():
    st = IL.Staged(tables={"t": pd.DataFrame({"zip": ["07030"], "amt": [1.5]})}, declared_pk={"t": ["zip"]})
    o = {"df": pd.DataFrame({"a": [1, 2], "b": ["x", None]}), "set": {("a", 1), "b"}, "pairs": {(1, "x"): 2, 2000: "y"},
         "date": dt.date(2026, 1, 2), "staged": st, "bytes": b"\x00\x01", "nested": [{"k": (1, 2)}]}
    r = store.loads(store.dumps(o))
    assert r["df"]["a"].tolist() == [1, 2] and r["set"] == {("a", 1), "b"} and r["pairs"][2000] == "y"
    assert r["pairs"][(1, "x")] == 2 and r["date"] == dt.date(2026, 1, 2) and r["bytes"] == b"\x00\x01"
    assert r["staged"].tables["t"].iloc[0]["zip"] == "07030" and r["nested"][0]["k"] == (1, 2)


def test_codec_refuses_foreign_classes():
    with pytest.raises(ValueError):
        store.decode({"__dc__": "os:PathLike", "fields": {}})


def test_save_load_reset():
    store.save("app1", "k", store.dumps({"x": 1}), "Ann")
    assert store.loads(store.load("app1")["k"]) == {"x": 1}
    store.reset("app1")
    assert store.load("app1") == {}


def test_two_person_rule():
    with pytest.raises(ValueError):
        store.request("app1", "K", "r", "s", {}, "")                    # must be named
    rid = store.request("app1", "K", "r", "s", {"v": 1}, "Ann")
    with pytest.raises(ValueError):
        store.decide("app1", rid, "ann", True)                           # maker cannot approve
    done = store.decide("app1", rid, "Bob", True, "ok")
    assert done["status"] == "Approved" and done["payload"] == {"v": 1}
    with pytest.raises(ValueError):
        store.decide("app1", rid, "Cy", True)                            # already decided
    rid2 = store.request("app1", "K", "r", "s", {}, "Ann")
    store.request("app1", "K", "r", "s2", {}, "Ann")                     # resubmitting supersedes
    assert store.approvals("app1", "Pending")[0]["summary"] == "s2"
    assert any(a["id"] == rid2 and a["status"] == "Superseded" for a in store.approvals("app1"))


# ------------------------------------------------------------------------------------------ initial load extras
@pytest.fixture(scope="module")
def plan():
    st = IL.stage(IL.sample_files(), [IL.SAMPLE_API])
    prof = IL.profile(st)
    props = IL.propose(st, prof)
    props.loc[(props.confidence >= 90) & ~props.conflict, "status"] = "Approved"
    props.loc[props.kind == "PICKLIST", "status"] = "Approved"
    return st, prof, props


def test_personal_data_found_and_masked(plan):
    _, prof, _ = plan
    k = prof.set_index(["table", "column"]).pii
    assert k["policy", "insured_tin"] == "SSN / TIN" and k["policy", "insured_email"] == "Email"
    assert k["driver", "birth_date"] == "Date of birth" and k["driver", "license_number"] == "Driver's license"
    assert k["agent", "agent_nm"] == ""                                  # agency names are not personal data
    assert "9" not in prof.set_index(["table", "column"]).samples["policy", "insured_tin"].split("-")[0]
    assert IL.mask("912-34-5678", "SSN / TIN") == "***-**-5678" and IL.mask("1980-05-17", "Date of birth") == "1980-**-**"
    assert IL.mask("maria.lopez@example.com", "Email") == "m***@example.com"


def test_code_descriptions(plan):
    st, _, props = plan
    c = IL.code_descriptions(st, props).set_index(["list_name", "code"])
    assert c.at[("Claim Status", "R"), "description"] == "Reopened"
    assert c.at[("Payment Type", "REC"), "source"] == "Insurance code dictionary"
    assert c.at[("Manufacturer", "FORD"), "source"] == "Drafted"


def test_data_edits_and_blocking(plan):
    st, prof, props = plan
    e = IL.quality_edits(st, prof, props, today=dt.date(2026, 10, 12))
    got = set(zip(e.edit, e.table))
    assert {("Q02", "policy"), ("Q04", "claim"), ("Q07", "claim_payment")} <= got
    assert IL.blocked_rows(e, set()) and not IL.blocked_rows(e, {"Q04"})


def test_initial_then_delta_keeps_history(plan, tmp_path):
    st, prof, props = plan
    db = str(tmp_path / "il.db")
    blocked = IL.blocked_rows(IL.quality_edits(st, prof, props), set())
    r = IL.build_and_load(st, prof, props, db, "Ann", as_of="2026-10-05 09:00:00", blocked=blocked,
                          codes=IL.code_descriptions(st, props))
    assert set(r["quarantine"].table) == {"claim", "claim_payment"} and r["fk_violations"] == 0
    sd = IL.stage([(p.name, p.read_bytes()) for p in sorted((IL.SAMPLES / "delta").glob("*.*"))])
    with pytest.raises(ValueError):
        IL.delta_load(sd, prof, props, db, "Ann", as_of="2026-10-01 00:00:00")      # before the last load
    sd = IL.stage([(p.name, p.read_bytes()) for p in sorted((IL.SAMPLES / "delta").glob("*.*"))])
    d = IL.delta_load(sd, prof, props, db, "Ann", as_of="2026-10-12 09:00:00").get("recon").set_index("table")
    assert d.at["policy", "new"] == 1 and d.at["policy", "changed (new version)"] == 2
    assert d.at["claim", "changed (new version)"] == 1 and d.at["claim_payment", "new"] == 2
    con = sqlite3.connect(db)
    v = con.execute("select written_prem, effective_to from policy where pol_no='PA1000101' and eff_dt='2025-01-01' "
                    "order by effective_from").fetchall()
    assert len(v) == 2 and v[0][1] == "2026-10-12 09:00:00" and v[1][1] == "9999-12-31" and v[1][0] == v[0][0] + 125
    assert con.execute("select claim_status from claim_current where claim_no='CL-0001'").fetchone()[0] == "C"
    assert con.execute("select count(*) from claim where claim_no='CL-0001'").fetchone()[0] == 2     # history kept
    assert con.execute("select description from pick_list where list_name='Claim Status' and code='O'").fetchone()[0] == "Open"


def test_hand_off_to_migration(plan):
    from migrate import engine as E, legacy
    st, _, props = plan
    base = {"dest_schema": pd.read_csv(legacy.SAMPLES / "destination_schema.csv", dtype=str).fillna(""),
            "dest_picklists": pd.read_csv(legacy.SAMPLES / "destination_picklists.csv", dtype=str)}
    src = IL.to_legacy_source(st, IL.code_descriptions(st, props), base)
    inv = E.discover(src)
    assert "POLICY" in src["entities"] and len(inv) > 50
    status = inv.set_index("element_id").pick_list["CLAIM.claim_status"]
    assert status.startswith("CODE_TABLE")                                # the approved codes travel along


# ------------------------------------------------------------------------------------------ company model
def test_company_model_unifies_names():
    from si2_common import registry as R
    where = R.harvest()
    assert set(R.APPS) == set(where.app)
    pn = where[where.term == "POLICY_NUMBER"]
    assert {"ISO bureau", "NCCI bureau", "Migration (cloud)", "Core canonical"} <= set(pn.app)
    t = R.terms(where).set_index("term")
    assert t.at["STATE", "apps"] == len(R.APPS)
    assert R.concept_of("POL_EFF_DT") == "POLICY_EFFECTIVE_DATE" and R.concept_of("AccidentDate") == "LOSS_DATE"


# ------------------------------------------------------------------------------------------ approvals in the apps
def test_rating_factor_needs_actuary():
    from si2_common import rating_gaps as RT
    spec = {"state": ("STATE_REL", "State", {"GA": 1.08}, "state")}
    ss, calls = SimpleNamespace(), []
    h = RT.Handler(ss, spec, "Ann", lambda *a: calls.append(a))
    g = RT.scan(pd.DataFrame([("Q1", "AL")], columns=["quote", "state"]), spec, ss)[0]
    h.add_new(g, dict(g.proposal))
    assert ss.factor_ext["STATE_REL"]["AL"]["status"] == RT.PENDING and calls[0][0] == "New rating factor"
    msg = RT.decide_factor(ss, {"status": "Rejected", "checker": "Bob", "payload": calls[0][3]})
    assert "rejected" in msg and "AL" not in ss.factor_ext["STATE_REL"]


def test_rules_vocabulary_is_shared():
    from si2_common.rules_gaps import BASE_DOMAINS, FIELDS
    assert "driver_age" in FIELDS and "Rideshare" in BASE_DOMAINS["use_type"]
