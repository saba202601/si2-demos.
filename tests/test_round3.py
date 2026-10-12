"""Scale engine, AI layer (offline + mocked API), identity, PostgreSQL store, claims / fraud gaps, governance, hub."""
import io
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from si2_common import ai, store  # noqa: E402
from si2_common.rules_gaps import BASE_DOMAINS, FIELDS  # noqa: E402


@pytest.fixture(autouse=True)
def state_db(tmp_path, monkeypatch):
    monkeypatch.setenv("SI2_STATE_DB", str(tmp_path / "state.db"))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    store._CON.clear()
    yield
    store._CON.clear()


def test_benchmark_small_book_reconciles():
    from benchmarks.initial_load_benchmark import run
    times, r = run(1500)
    rec = r["recon"]
    assert (rec["rows balance"] == "PASS").all() and (rec["totals balance"] != "FAIL").all() and r["fk_violations"] == 0


@pytest.mark.parametrize("text,cond,action", [
    ("Decline drivers under 18 in Florida", "driver_age < 18 and state == 'FL'", "DECLINE"),
    ("Refer mileage over 30,000", "annual_miles > 30000", "REFER"),
    ("Surcharge 10% for rideshare in Texas", "state == 'TX' and use_type == 'Rideshare'", "SURCHARGE %"),
])
def test_rule_from_english_offline(text, cond, action):
    r, src = ai.rule_from_english(text, FIELDS, BASE_DOMAINS)
    assert src == "SI² rules" and r["condition"] == cond and r["action"] == action and r["note"].startswith("Checked")


def test_ai_uses_claude_when_key_set(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    seen = {}

    class Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout=0):
        seen["headers"] = dict(req.header_items())
        seen["body"] = json.loads(req.data)
        out = {"content": [{"type": "text", "text": '{"name":"Young drivers","condition":"driver_age < 21","action":"REFER","value":0}'}]}
        return Resp(json.dumps(out).encode())
    monkeypatch.setattr(ai.urllib.request, "urlopen", fake_urlopen)
    r, src = ai.rule_from_english("refer young drivers", FIELDS, BASE_DOMAINS)
    assert src == "Claude" and r["condition"] == "driver_age < 21"
    assert seen["body"]["model"] == ai.model() and seen["headers"]["X-api-key"] == "test-key"
    assert "anthropic-version" in {k.lower() for k in seen["headers"]}


def test_ai_falls_back_when_api_fails(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    def boom(*a, **k):
        raise ai.urllib.error.URLError("no route")
    monkeypatch.setattr(ai.urllib.request, "urlopen", boom)
    text, src = ai.explain_rejections("WCSTAT", [{"edit": "Invalid code", "field": "X", "count": 2}])
    assert src == "SI² rules" and "Claude unavailable" in text


def test_postgres_store_when_available(monkeypatch):
    url = os.environ.get("SI2_TEST_PG_URL")
    if not url:
        pytest.skip("set SI2_TEST_PG_URL to test against PostgreSQL")
    monkeypatch.setenv("SI2_STATE_BACKEND", "postgres")
    monkeypatch.setenv("SI2_DATABASE_URL", url)
    store._CON.clear()
    store.reset("t3")
    store.save("t3", "k", store.dumps({"x": {1, 2}}), "me")
    assert store.loads(store.load("t3")["k"]) == {"x": {1, 2}}
    i = store.request("t3", "K", "r", "s", {}, "Ann")
    with pytest.raises(ValueError):
        store.decide("t3", i, "ANN", True)
    assert store.decide("t3", i, "Bob", True)["status"] == "Approved" and store.describe().startswith("PostgreSQL")
    store.reset("t3")


def test_claims_gaps_draft_like_an_adjuster():
    from si2_common import claims_gaps as CG
    causes = {"Single-vehicle collision": ("Personal Auto", 25), "Water damage": ("Homeowners", 20),
              "Kitchen fire": ("Homeowners", 35)}
    inc = pd.DataFrame({"claim": ["A", "B", "C"], "cause": ["Animal collision", "Glass breakage", "Sewer backup"],
                        "estimate": [3000.0, 500.0, 9000.0]})
    ss = SimpleNamespace()
    g = {x.name: x for x in CG.scan(inc, causes, ss)}
    assert g["Animal collision"].candidates[0][0] == "Single-vehicle collision"
    assert g["Glass breakage"].proposal["points"] == "8" and g["Sewer backup"].proposal["line"] == "Homeowners"
    h = CG.Handler(ss, causes, "Ann")
    with pytest.raises(ValueError):
        h.add_new(g["Glass breakage"], {**g["Glass breakage"].proposal, "points": "90"})
    h.add_new(g["Glass breakage"], dict(g["Glass breakage"].proposal))
    h.map_existing(g["Animal collision"], "Single-vehicle collision")
    assert {"Glass breakage", "Animal collision"} <= set(ss.cause_ext)


def test_fraud_gaps_list_data_for_rules_not_yet_live():
    from fraud import catalog, data, gaps as FG
    cat, d, ss = catalog.load(), data.build(), SimpleNamespace()
    gaps = FG.scan(cat, d, ss)
    names = {g.name for g in gaps}
    assert {"VIN history", "Medical bills", "Access logs"} <= names and "Limits" not in names
    h = FG.Handler(ss, d, "Ann", lambda *a: None)
    vin = next(g for g in gaps if g.name == "VIN history")
    h.add_new(vin, dict(vin.proposal))
    assert ss.fraud_requests["VIN history"]["table"] == "objects"
    assert "VIN history" not in {g.name for g in FG.scan(cat, d, ss)}


def test_company_model_governance_publishes_to_apps():
    from si2_common import registry as R
    R.publish("POLICY_NUMBER", {"standard_name": "policy_number", "definition": "Carrier policy contract number.",
                                "synonyms": ["contract no"]}, "Ann", "Bob")
    assert R.concept_of("CONTRACT_NO") == "POLICY_NUMBER"
    assert R.definition_for("pol_no") == ("POLICY_NUMBER", "Carrier policy contract number.")
    t = R.terms(R.harvest()).set_index("term")
    assert t.at["POLICY_NUMBER", "status"] == "Published v1"
    from migrate import initial_load as IL
    st = IL.Staged()
    st.add("pol", pd.DataFrame({"CONTRACT_NO": ["A1", "A2"], "AMT": ["1", "2"]}), "x")
    prof = IL.profile(st).set_index("column")
    assert prof.at["contract_no", "company_term"] == "POLICY_NUMBER"
    assert prof.at["contract_no", "description"].endswith("(company definition)")
    assert R.history()[-1]["approved_by"] == "Bob"
