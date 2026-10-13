"""SI² claim coverage: reading forms, finding causes in loss descriptions, deciding coverage, checking money, routing alerts."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "sql" / "si2_canonical"))

import coverage as C  # noqa: E402
import coverage_build as CB  # noqa: E402

LIB = C.FormLibrary.synthetic()


def test_causes_in_words_and_negations():
    assert C.causes_in("Storm surge pushed water in under the door") == [("FLOOD", "storm surge")]
    assert [c for c, _ in C.causes_in("The sewer backed up; mold on the drywall")] == ["SEWER", "MOLD"]
    assert C.causes_in("Pipe burst in the wall. No flooding outside.") == [("WATER", "pipe burst")]
    assert C.causes_in("Insured hit a deer at night")[0][0] == "ANIMAL"


def test_form_is_read_into_sections():
    kinds = {s["heading"]: s["type"] for s in LIB.sections["SIM HO 3"]}
    assert kinds["SECTION I - EXCLUSIONS"] == "EXCLUSION" and kinds["SECTION I - DEDUCTIBLE"] == "DEDUCTIBLE"
    open_perils = next(s for s in LIB.sections["SIM HO 3"] if s["heading"].endswith("COVERAGE A AND COVERAGE B"))
    assert open_perils["open_perils"] and open_perils["coverages"] == ["DWELL", "OTHSTR"]
    excl = {c for s in LIB.sections["SIM HO 3"] if s["type"] == "EXCLUSION" for cl in s["clauses"] for c in cl["causes"]}
    assert {"FLOOD", "SEWER", "EARTHMV", "WEAR", "MOLD"} <= excl and not {"WIND", "WATER"} & excl   # "whether or not driven by wind" is not a wind exclusion
    hur = [cl for s in LIB.sections["SIM HO 32 FL"] for cl in s["clauses"] if cl["pct_cov_a"]]
    assert hur and hur[0]["pct_cov_a"] == 2


@pytest.mark.parametrize("cause, cov, forms, status", [
    ("FLOOD", "DWELL", ["SIM HO 3"], "NOT COVERED"),
    ("WIND", "DWELL", ["SIM HO 3"], "COVERED"),
    ("WIND", "DWELL", ["SIM HO 3", "SIM HO 04 94"], "NOT COVERED"),                 # endorsement excludes wind
    ("SEWER", "DWELL", ["SIM HO 3"], "NOT COVERED"),
    ("SEWER", "DWELL", ["SIM HO 3", "SIM HO 04 95"], "COVERED"),                    # given back, with a sublimit
    ("MOLD", "DWELL", ["SIM HO 3"], "REVIEW"),                                      # exclusion with an exception
    ("SINKHOLE", "DWELL", ["SIM HO 3", "SIM HO 23 FL"], "COVERED"),
    ("EARTHMV", "PERSPROP", ["SIM HO 3"], "NOT COVERED"),
    ("THEFT", "PERSPROP", ["SIM HO 3"], "COVERED"),                                 # named peril
    ("RIDESHARE", "COLL", ["SIM PP 00 01"], "NOT COVERED"),
    ("RIDESHARE", "COLL", ["SIM PP 00 01", "SIM PP 03 RS"], "COVERED"),
    ("EMPDIS", "BPP", ["SIM BP 00 03"], "NOT COVERED"),
    ("FIRE", "BLDG", ["SIS CP 10 30"], "COVERED"),
    ("FLOOD", "BLDG", ["SIS CP 10 30", "SIS CP 10 65"], "COVERED"),
])
def test_decide(cause, cov, forms, status):
    d = C.decide(cause, cov, forms, LIB)
    assert d["status"] == status, d
    assert d["evidence"] or status == "REVIEW"


def test_showcase_claims_and_routing():
    pols = C.synthetic_policies()
    claims = C.synthetic_claims(pols, lib=LIB)
    by = {c["claim_number"]: c for c in claims}

    def types(n):
        return {a["type"]: a for a in C.check_claim(by[n], pols[by[n]["policy_number"]], LIB)["alerts"]}
    surge = types("CLM-69901")
    assert {"CAUSE_MISMATCH", "NOT_COVERED", "PAID_NOT_COVERED"} <= set(surge)
    assert (surge["NOT_COVERED"]["to"], surge["NOT_COVERED"]["cc"]) == ("CLAIMS_ADJUSTER", "CLAIMS_MANAGER")
    assert "DEDUCTIBLE_MISMATCH" in types("CLM-69902")                              # hurricane % deductible
    assert types("CLM-69903") == {}                                                 # a clean covered claim
    assert {"SUBLIMIT", "OVER_LIMIT"} <= set(types("CLM-69905"))
    auto = types("CLM-69906")
    assert {"WRONG_COVERAGE", "DEDUCTIBLE_MISMATCH", "DEDUCTIBLE_NOT_APPLIED"} <= set(auto)
    assert all((auto[t]["to"], auto[t]["cc"]) == ("UNDERWRITER", "CLAIMS_MANAGER") for t in ("WRONG_COVERAGE", "DEDUCTIBLE_MISMATCH"))
    alerts = C.check_all(claims, pols, LIB)
    kinds = {a["type"] for a in alerts}
    assert {"LIMIT_MISMATCH", "SPLIT_PAYMENTS", "SHARED_PAYEE", "OUTSIDE_POLICY_PERIOD"} <= kinds
    shared = [a for a in alerts if a["type"] == "SHARED_PAYEE"]
    assert {a["adjuster"] for a in shared} == {"Tom Reed"} and len({a["claim"] for a in shared}) == len(shared)
    assert all(a["to"] in {"CLAIMS_ADJUSTER", "UNDERWRITER", "CLAIMS_MANAGER", "SIU"} for a in alerts)


def test_any_form_text_is_read():
    text = """BROADENED WATER COVERAGE
We will pay for loss caused by water which backs up through sewers or drains, up to $5,000.
EXCLUSIONS
We do not cover loss caused by flood or storm surge, unless the flood endorsement is attached.
"""
    s = C.read_form("TEST 1", text)
    assert [x["type"] for x in s] == ["COVERED", "EXCLUSION"]
    assert s[0]["clauses"][0]["amount"] == 5000 and "SEWER" in s[0]["clauses"][0]["causes"]
    assert s[1]["clauses"][0]["causes"] == ["FLOOD"] and not s[1]["clauses"][0]["exception"]   # "unless ... endorsement" is a plain exclusion


def test_08_coverage_sql_is_current():
    assert (ROOT / "sql" / "si2_canonical" / "08_coverage.sql").read_text(encoding="utf-8") == CB.build_sql(), \
        "08_coverage.sql is stale: run python sql/si2_canonical/coverage_build.py"
