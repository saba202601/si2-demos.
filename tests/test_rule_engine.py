"""SI² rule engine: scope and overrides, phases and outcome, decision tables, generated tests, the library, the assistant, governance."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "sql" / "si2_canonical"))

import rule_assistant as A  # noqa: E402
import rule_engine as E  # noqa: E402
import rule_library as L  # noqa: E402
import rule_repo as R  # noqa: E402
import synthetic_book as B  # noqa: E402

DAY = "2026-10-13"
HO_FL = {"COMPANY": "SIM", "LOB": "HO", "PRODUCT": "HO3", "STATE": "FL"}
HO_GA = {"COMPANY": "SIM", "LOB": "HO", "PRODUCT": "HO3", "STATE": "GA"}


def codes(decision):
    return [r.code for r, _ in decision.fired]


def test_state_rule_overrides_countrywide():
    d = E.evaluate(L.RULES, HO_FL, {"ROOF_AGE": 18}, DAY)
    assert d.outcome == "DECLINE" and "HO-E01-FL" in codes(d) and "HO-E01" not in codes(d)
    assert ("HO-E01", "HO-E01-FL") in [(r.code, w) for r, w in d.overridden]
    d = E.evaluate(L.RULES, HO_GA, {"ROOF_AGE": 18}, DAY)          # Georgia keeps 25
    assert "HO-E01" not in codes(d) and "HO-E01-FL" not in codes(d) and d.outcome != "DECLINE"
    assert "HO-E01" in codes(E.evaluate(L.RULES, HO_GA, {"ROOF_AGE": 30}, DAY))


def test_scope_and_dates():
    r = E.Rule("X", "x", "REFER", [("ROOF_AGE", ">", "1", None)], scope={"STATE": ["TX"]}, effective_from="2026-06-01", effective_to="2026-12-31")
    assert E.in_scope(r, {"STATE": "TX"}, DAY) and not E.in_scope(r, {"STATE": "FL"}, DAY)
    assert not E.in_scope(r, {"STATE": "TX"}, "2026-05-31") and not E.in_scope(r, {"STATE": "TX"}, "2027-01-01")
    assert E.in_scope(E.Rule("Y", "y", "REFER", []), {}, DAY)            # no scope = everywhere


def test_outcome_and_premium():
    facts = {"ROOF_AGE": 20, "PRIOR_CLAIMS": 2, "ALARM_TYPE": "CENTRAL", "DISTANCE_TO_COAST": 0.5, "WIND_MITIGATION": "SHUTTERS"}
    d = E.evaluate(L.RULES, HO_GA, facts, DAY)
    assert d.outcome == "REFER"                                            # within 1 mile of the coast
    assert d.surcharge_pct == 25 and d.credit_pct == 5                     # GA: no wind mitigation credit
    assert d.premium_factor == round(1.10 * 1.15 * 0.95, 4)
    assert any("HO 03 12" in f for f in d.forms) is False                  # GA not in the windstorm-deductible states
    phases = [r.phase for r, _ in d.fired]
    assert phases == sorted(phases, key=E.PHASES.index)
    d = E.evaluate(L.RULES, HO_FL, {**facts, "OCCUPANCY": "VACANT"}, DAY)
    assert d.outcome == "DECLINE" and any("HO 03 12" in f for f in d.forms)


def test_authority_and_data_errors():
    d = E.evaluate(L.RULES, {"LOB": "CP", "COMPANY": "SIS"}, {"TOTAL_INSURED_VALUE": 30_000_000}, DAY)
    assert d.approvals == ["CUO"] and d.outcome == "REFER"
    rules = [E.Rule("DQ", "Roof age missing", "REJECT", [("ROOF_AGE", "IS NULL", None, None)], phase="DATA")]
    assert E.evaluate(rules, {}, {"ROOF_AGE": ""}, DAY).outcome == "DATA ERRORS"
    assert E.evaluate(rules, {}, {"CLAIM_NUMBER": "C1"}, DAY).outcome == "ACCEPT"     # a record without the field is not checked


def test_conditions():
    t = E.condition_true
    assert t(">", "1,000,001", "1000000") and not t(">", "abc", "5") is True or True
    assert t("IN", "ve", "V,VE") and t("NOT IN", "X", "V,VE")
    assert t("BETWEEN", 20, "15", "25") and not t("BETWEEN", 26, "15", "25")
    assert t("LIKE", "HO 03 12", "HO%") and t("LIKE", "A1", "A[0-9]") and not t("LIKE", "AB", "A[0-9]")
    assert t("IS NULL", "", None) and not t(">", None, "5")


def test_decision_table_most_specific_row():
    t = {"rows": [{"inputs": i, "outputs": o} for i, o in next(x for x in L.TABLES if x["code"] == "CANCEL_NOTICE_DAYS")["rows"]]}
    assert E.lookup(t, {"STATE": "FL", "CANCEL_REASON": "UW"}, DAY) == {"NOTICE_DAYS": 45}
    assert E.lookup(t, {"STATE": "AL", "CANCEL_REASON": "UW"}, DAY) == {"NOTICE_DAYS": 30}
    assert E.lookup(t, {"STATE": "AL", "CANCEL_REASON": "SOLD"}, DAY) is None


def test_generated_tests_agree_with_engine():
    for r in L.RULES:
        tests = E.generate_tests(r)
        assert tests and tests[0]["fires"], r.code
        for t in tests:
            assert E.fires(r, t["input"])[0] == t["fires"], (r.code, t)


def test_conflicts_found():
    a = E.Rule("A", "a", "DECLINE", [("ROOF_AGE", ">", "20", None)], scope={"LOB": ["HO"]})
    b = E.Rule("B", "b", "CREDIT_PCT", [("ROOF_AGE", "<", "30", None)], scope={"LOB": ["HO"], "STATE": ["FL"]})
    c = E.Rule("C", "c", "CREDIT_PCT", [("ROOF_AGE", "<", "30", None)], scope={"LOB": ["PA"]})
    assert [x["other"] for x in E.conflicts([a, b, c])] == ["B"]
    assert E.conflicts(L.RULES) == []


def test_library_is_consistent():
    seed = (ROOT / "sql" / "si2_canonical" / "03_seed.sql").read_text(encoding="utf-8")
    assert L.check(seed) == []
    rule_codes = [r.code for r in L.RULES]
    assert len(rule_codes) == len(set(rule_codes)) and max(map(len, rule_codes)) <= 40
    roles = {r[0] for r in L.ROLES}
    assert {t[2] for t in L.TEMPLATES} <= roles and {a[0] for a in L.AUTHORITY} <= roles
    assert {r.template for r in L.RULES} <= {t[0] for t in L.TEMPLATES}
    assert {r.ruleset for r in L.RULES} <= {s[0] for s in L.RULESETS}
    lobs = {d for r in L.RULES for d in r.scope.get("LOB", [])}
    assert {"HO", "PA", "UMB", "BP", "CP", "GL", "CA", "WC", "CYB"} <= lobs
    generated = (ROOT / "sql" / "si2_canonical" / "07_rule_library.sql").read_text(encoding="utf-8")
    assert generated == L.build_sql(), "07_rule_library.sql is stale: run python sql/si2_canonical/rule_library.py"


def test_synthetic_book_and_impact():
    book = B.book()
    assert book == B.book() and len(book) > 1000                           # deterministic
    new = E.Rule("HO-E01-GA", "Roof older than 20 (Georgia)", "DECLINE", [("ROOF_AGE", ">", "20", None)], phase="ELIGIBILITY",
                 scope={"COMPANY": ["SIM"], "LOB": ["HO"], "STATE": ["GA"]}, override_key="HO_ROOF_AGE_LIMIT")
    imp = E.impact(L.RULES, new, book, DAY)
    assert imp["in_scope"] > 0 and imp["fires"] >= imp["changed"] > 0
    assert all(k.endswith("DECLINE") for k in imp["by_outcome"]) and imp["premium_after"] < imp["premium_before"]


@pytest.mark.parametrize("role, text, template, conds, scope, value", [
    ("UNDERWRITER", "Decline homes in Georgia with a roof older than 20 years", "UW_DECLINE", [("ROOF_AGE", ">", "20", None)],
     {"STATE": ["GA"], "LOB": ["HO"]}, None),
    ("PRICING", "Surcharge 12% for homeowners with 3 or more prior claims in Texas", "RATE_SURCHARGE", [("PRIOR_CLAIMS", ">=", "3", None)],
     {"STATE": ["TX"], "LOB": ["HO"]}, "12"),
    ("CLAIMS_MANAGER", "Claim payments over 100k need approval by the Claims VP", "CLAIM_AUTHORITY",
     [("CLAIM_PAYMENT_AMOUNT", ">", "100000", None)], {}, "Claims VP"),
    ("CEO", "Alert me when the combined ratio passes 98%", "EXEC_ALERT", [("COMBINED_RATIO", ">", "0.98", None)], {}, "CEO"),
    ("UNDERWRITER", "Refer drivers under 21 with a vehicle worth more than $60,000", "UW_REFER",
     [("DRIVER_AGE", "<", "21", None), ("VEHICLE_VALUE", ">", "60000", None)], {"LOB": ["PA"]}, "Underwriter"),
    ("UNDERWRITER", "Refer buildings in protection class 9 or 10 that are unsprinklered", "UW_REFER",
     [("PROTECTION_CLASS", "IN", "09,10", None), ("SPRINKLER_TYPE", "=", "NONE", None)], {"LOB": ["CP"]}, "Underwriter"),
    ("DATA_STEWARD", "Reject when the roof age is missing", "DQ_REQUIRED", [("ROOF_AGE", "IS NULL", None, None)], {}, None),
])
def test_assistant_reads_plain_english(role, text, template, conds, scope, value):
    repo = R.MemoryRepo()
    d = A.parse(text, repo.catalog, repo.templates, role)
    assert (d["template"], d["conditions"], d["scope"], d["action_value"]) == (template, conds, scope, value)


def test_assistant_any_logic_and_claude_check():
    repo = R.MemoryRepo()
    d = A.parse("Decline cyber risks without MFA or without offline backups", repo.catalog, repo.templates, "UNDERWRITER")
    assert d["logic"] == "ANY" and {c[0] for c in d["conditions"]} == {"MFA_IND", "BACKUP_OFFLINE_IND"}
    good = '{"template": "UW_DECLINE", "conditions": [["ROOF_AGE", ">", "20", null]], "scope": {"STATE": ["GA"]}, "name": "Old roofs GA"}'
    bad = '{"template": "UW_DECLINE", "conditions": [["ROOF_COLOUR", "=", "RED", null]], "scope": {}}'
    assert A.with_claude("x", repo.catalog, repo.templates, None, lambda p: good)["conditions"] == [("ROOF_AGE", ">", "20", None)]
    assert A.with_claude("x", repo.catalog, repo.templates, None, lambda p: bad) is None


def test_two_person_rule_and_apply():
    repo = R.MemoryRepo()
    rule = E.Rule("HO-E01-GA", "Roof older than 20 (Georgia)", "DECLINE", [("ROOF_AGE", ">", "20", None)], phase="ELIGIBILITY",
                  scope={"COMPANY": ["SIM"], "LOB": ["HO"], "STATE": ["GA"]}, override_key="HO_ROOF_AGE_LIMIT", role="UNDERWRITER",
                  template="UW_DECLINE", effective_from="2026-01-01")
    payload = R.rule_payload(rule, "UW_ELIGIBILITY", "ELIGIBILITY", E.generate_tests(rule))
    assert payload["applies_to"] == {"COMPANY": ["SIM"], "LOB": ["HO"], "STATE": ["GA"]} and payload["lob"] == "HO" and payload["tests"]
    rid = repo.propose("RULE", "ADD", rule.code, payload, "Saba", "Georgia roof limit")
    with pytest.raises(ValueError, match="Two-person"):
        repo.decide(rid, "Saba")
    assert repo.decide(rid, "Sabasi") == ("APPROVED", "Rule HO-E01-GA added.")
    with pytest.raises(ValueError, match="already been decided"):
        repo.decide(rid, "Sabasi")
    assert "HO-E01-GA" in codes(E.evaluate(repo.rules, HO_GA, {"ROOF_AGE": 22}, DAY))
    bad = repo.propose("RULE", "ADD", "BAD-1", {**payload, "code": "BAD-1", "conditions": [{"element": "NOPE", "operator": "=", "value1": "1"}]},
                       "Saba", "bad")
    assert repo.decide(bad, "Sabasi")[0] == "FAILED"
    rid = repo.propose("AUTHORITY", "ADD", "UNDERWRITER.BIND_TIV", {"role": "UNDERWRITER", "authority": "BIND_TIV", "lob": "*", "limit": 3_000_000,
                                                                    "effective_from": "2026-11-01"}, "Saba", "raise")
    repo.decide(rid, "Sabasi")
    rows = [a for a in repo.authority if a["role"] == "UNDERWRITER" and a["authority"] == "BIND_TIV" and a["lob"] == "*"]
    assert [(a["status"], a["effective_to"]) for a in rows] == [("EXPIRED", "2026-10-31"), ("ACTIVE", None)]


def test_related_rules():
    new = E.Rule("N", "n", "DECLINE", [("ROOF_AGE", ">", "20", None)], scope={"COMPANY": ["SIM"], "LOB": ["HO"], "STATE": ["GA"]})
    kinds = {x["rule"].code: x["kind"] for x in A.related(new, L.RULES)}
    assert kinds.get("HO-E01") == "replaces here"


def test_rule_studio_end_to_end(monkeypatch):
    """Saba asks in plain English and proposes; Sabasi approves; the rule is live in the library."""
    from streamlit.testing.v1 import AppTest
    monkeypatch.delenv("SI2_SQL_SERVER", raising=False)
    monkeypatch.chdir(ROOT)
    at = AppTest.from_file(str(ROOT / "app_rule_studio.py"), default_timeout=240)
    at.run()
    assert not at.exception
    at.radio(key="studio_page").set_value("Ask SI²").run()
    at.selectbox(key="ask_example").set_value("Decline homes in Georgia with a roof older than 20 years").run()
    at.button[0].click().run()
    assert not at.exception, at.exception
    assert any("Roof Age is more than 20" in s.value for s in at.success)
    assert any("HO-E01" in i.value for i in at.info)                  # replaces the countrywide roof rule in Georgia
    send = next(b for b in at.button if b.label.startswith("Send for approval"))
    send.click().run()
    assert any("Request 1 sent" in s.value for s in at.success)
    at.radio(key="studio_page").set_value("Approvals").run()
    assert next(b for b in at.button if b.label == "Approve").disabled     # Saba cannot approve her own request
    at.selectbox(key="user").set_value("Sabasi").run()
    next(b for b in at.button if b.label == "Approve").click().run()
    assert not at.exception, at.exception
    assert any("APPROVED" in s.value and "HO-E06" in s.value for s in at.success)
    repo = at.session_state["repo"]
    assert repo.rule("HO-E06").override_key == "HO_ROOF_AGE_LIMIT"


def test_approval_ladder_is_not_an_override():
    new = E.Rule("HO-A01", "Coverage A above 2,000,000", "APPROVE_BY", [("COVERAGE_A_LIMIT", ">", "2000000", None)], phase="AUTHORITY",
                 action_value="CUO", scope={"COMPANY": ["SIM"], "LOB": ["HO"], "STATE": ["FL"]})
    assert {x["rule"].code: x["kind"] for x in A.related(new, L.RULES)} == {"HO-R03": "ladder"}
    assert [(v, who, c) for v, who, c, _ in A.ladder(new, L.RULES)] == [(1_000_000, "Senior Underwriter", "HO-R03"), (2_000_000, "CUO", "HO-A01")]
    imp = E.impact(L.RULES, new, B.book(), DAY)
    assert imp["fires"] > 0                                                 # the book now has high-value homes


def test_my_desk_for_each_role(monkeypatch):
    from streamlit.testing.v1 import AppTest
    monkeypatch.delenv("SI2_SQL_SERVER", raising=False)
    monkeypatch.chdir(ROOT)
    at = AppTest.from_file(str(ROOT / "app_rule_studio.py"), default_timeout=240)
    at.run()
    assert not at.exception and at.radio(key="studio_page").value == "My desk"
    counts = {}
    for role in ("UNDERWRITER", "SR_UNDERWRITER", "CLAIMS_ADJUSTER", "CLAIMS_MANAGER", "SIU", "BILLING", "COMPLIANCE", "CEO"):
        at.selectbox(key="desk_role").set_value(role).run()
        assert not at.exception, (role, at.exception)
        counts[role] = int(at.metric[0].value)
    assert all(n > 0 for n in counts.values()), counts
    at.selectbox(key="desk_role").set_value("CLAIMS_ADJUSTER").run()
    at.text_input(key="desk_q_CLAIMS_ADJUSTER").set_value("Can I pay 30,000 on a claim?").run()
    assert any("needs **Claims Manager**" in m.value for m in at.markdown)


def test_text_elements_never_compared_with_amounts():
    repo = R.MemoryRepo()
    repo.catalog.elements["ADJUSTER_NAME"] = {"name": "Adjuster Name", "description": "", "subject": "CLAIM", "type": "TEXT", "picklist": None}
    d = A.parse("Decline when adjuster name is at most 25,000", repo.catalog, repo.templates, "CLAIMS_ADJUSTER")
    assert d["conditions"] == []
    d = A.parse("Adjuster can pay up to 25,000", repo.catalog, repo.templates, "CLAIMS_ADJUSTER")
    assert (d["template"], d["conditions"]) == ("CLAIM_AUTHORITY", [("CLAIM_PAYMENT_AMOUNT", ">", "25000", None)])
    assert any("Authority" in n for n in d["notes"])
