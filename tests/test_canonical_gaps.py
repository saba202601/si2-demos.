"""Canonical Gaps adapters for NCCI bureau reporting, the Rule Engine and the Rating Engine.

Run from the repo root:  python -m pytest tests -q
(ISO and Migration gaps are covered in iso_bureau/tests/test_gaps.py.)
"""
import sys
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from si2_common import rating_gaps as RT  # noqa: E402
from si2_common import rules_gaps as RG  # noqa: E402


# ------------------------------------------------------------------------------------------ NCCI
@pytest.fixture(scope="module")
def ncci_base():
    from bureau import canonical as cn, catalog, generate as gen, source
    src = source.build()
    smap = cn.auto_map_source(src)
    fmaps = {s: gen.auto_map_fields(s) for s in catalog.SPEC_INFO}
    return src, smap, fmaps


@pytest.fixture
def ncci(ncci_base):
    from bureau import canonical as cn, catalog, generate as gen, source
    src, smap, fmaps = ncci_base
    ss = SimpleNamespace(src=src, smap=smap.copy(), fmaps={k: v.copy() for k, v in fmaps.items()},
                         overrides={}, carrier=source.CARRIER_CODE, audit=[])
    ss.canon = cn.build_canonical(ss.src, ss.smap, ss.carrier, ss.overrides)
    ss.vmaps = {s: gen.auto_value_map(ss.canon, ss.fmaps[s]) for s in catalog.SPEC_INFO}

    def rebuild():
        ss.canon = cn.build_canonical(ss.src, ss.smap, ss.carrier, ss.overrides)

    def log(who, event, detail=""):
        ss.audit.append((who, event, detail))
    return ss, rebuild, log


def test_ncci_scan_finds_destination_and_code_gaps(ncci):
    from bureau import gaps as NG
    ss, rebuild, log = ncci
    gaps = NG.scan(ss)
    kinds = {g.kind for g in gaps}
    assert {"DEST_ELEMENT", "CODE"} <= kinds
    assert all(g.actions == ("map",) for g in gaps if g.kind == "CODE")   # NCCI owns its code lists
    assert len({g.gap_id for g in gaps}) == len(gaps)


def test_ncci_add_attribute_without_source_becomes_unsourced_gap(ncci):
    from bureau import gaps as NG
    ss, rebuild, log = ncci
    h = NG.Handler(ss, "tester", rebuild, log)
    g = next(g for g in NG.scan(ss) if g.kind == "DEST_ELEMENT")
    p = dict(g.proposal, source=NG.NO_SOURCE)
    h.add_new(g, p)
    unsourced = [x for x in NG.scan(ss) if x.kind == "UNSOURCED"]
    assert any(x.name == p["column"] for x in unsourced)
    # it can only be fed from the table at the same grain
    u = next(x for x in unsourced if x.name == p["column"])
    opts = [k for k, _ in h.map_options(u)]
    assert opts and all(k.split(".")[0] in NG.cn.SOURCE_FOR[u.context] for k in opts)
    with pytest.raises(ValueError):
        wrong = next(t for t in ss.src if t not in NG.cn.SOURCE_FOR[u.context])
        h.map_existing(u, f"{wrong}.{ss.src[wrong].columns[0]}")
    h.map_existing(u, opts[0])
    assert not any(x.name == p["column"] for x in NG.scan(ss) if x.kind == "UNSOURCED")


def test_ncci_resolves_every_gap(ncci):
    from bureau import gaps as NG
    ss, rebuild, log = ncci
    h = NG.Handler(ss, "tester", rebuild, log)
    for _ in range(40):
        gaps = NG.scan(ss)
        if not gaps:
            break
        g = gaps[0]
        if g.kind == "CODE":
            h.map_existing(g, h.map_options(g)[0][0])
        else:
            h.not_needed(g, "test")
    assert NG.scan(ss) == []
    assert any("Canonical Gaps" in e for _, e, _ in ss.audit)


def test_ncci_table_follows_record_grain():
    from bureau import gaps as NG
    assert NG._table_for("WCSTAT", "Exposure") == "exposure"
    assert NG._table_for("WCSTAT", "Loss") == "claim"
    assert NG._table_for("WCPOLS", "State Premium") == "policy_state"
    assert NG._table_for("WCMED", "Medical Data Call") == "medical_bill_line"


# ------------------------------------------------------------------------------------------ Rules
FIELDS = {"state": "Two-letter state", "driver_age": "Age of the principal driver", "violations": "Violations",
          "use_type": "Use", "annual_miles": "Annual miles"}
DOMS = {"state": RG.US_STATES, "use_type": ["Pleasure", "Commute", "Business", "Rideshare"]}


def _rules():
    return pd.DataFrame([
        (True, "R01", "a", "state not in ['FL', 'GA']", "DECLINE", 0),
        (True, "R09", "b", "telematics_score < 40 and use_type == 'Delivery'", "SURCHARGE %", 15),
        (True, "R10", "c", "drv_age >= 80 and violations >= 1", "REFER", 0),
        (True, "R11", "d", "state == 'FLA' and annual_miles > 20000", "SURCHARGE %", 5),
    ], columns=["active", "rule_id", "name", "condition", "action", "value"])


def _rss():
    return SimpleNamespace()


def test_rules_scan():
    ss = _rss()
    gaps = RG.scan(_rules(), FIELDS, DOMS, ss)
    got = {(g.kind, g.name) for g in gaps}
    assert got == {("ELEMENT", "telematics_score"), ("ELEMENT", "drv_age"), ("CODE", "Delivery"), ("CODE", "FLA")}
    fla = next(g for g in gaps if g.name == "FLA")
    assert fla.candidates[0][0] == "FL"
    drv = next(g for g in gaps if g.name == "drv_age")
    assert drv.candidates[0][0] == "driver_age"


def test_rules_map_rewrites_conditions_but_not_quoted_text():
    ss = _rss()
    rules = _rules()
    rules.loc[2, "condition"] = "drv_age >= 80 and state != 'drv_age'"
    h = RG.Handler(ss, rules, FIELDS, DOMS, "tester")
    g = next(g for g in RG.scan(rules, FIELDS, DOMS, ss) if g.name == "drv_age")
    h.map_existing(g, "driver_age")
    assert ss.rules.loc[2, "condition"] == "driver_age >= 80 and state != 'drv_age'"
    h = RG.Handler(ss, ss.rules, FIELDS, DOMS, "tester")
    g = next(g for g in RG.scan(ss.rules, FIELDS, DOMS, ss) if g.name == "FLA")
    h.map_existing(g, "FL")
    assert "'FL'" in ss.rules.loc[3, "condition"] and "FLA" not in ss.rules.loc[3, "condition"]
    assert len(ss.rule_audit) == 2


def test_rules_add_field_and_code_extend_vocabulary_and_sample_data():
    ss = _rss()
    h = RG.Handler(ss, _rules(), FIELDS, DOMS, "tester")
    gaps = RG.scan(_rules(), FIELDS, DOMS, ss)
    tel = next(g for g in gaps if g.name == "telematics_score")
    assert tel.proposal["type"] == "number"
    h.add_new(tel, dict(tel.proposal))
    assert "telematics_score" in RG.vocabulary(FIELDS, ss)
    subs = RG.extend_submissions(pd.DataFrame({"submission": ["A", "B", "C"]}), ss)
    assert "telematics_score" in subs and subs.telematics_score.between(0, 100).all()
    dl = next(g for g in gaps if g.name == "Delivery")
    h.add_new(dl, dict(dl.proposal))
    assert "Delivery" in RG.domains(DOMS, ss)["use_type"]
    with pytest.raises(ValueError):
        h.add_new(dl, dict(dl.proposal))                  # already there now
    left = {g.name for g in RG.scan(ss.rules, FIELDS, DOMS, ss)}
    assert left == {"drv_age", "FLA"}


def test_rules_not_needed_switches_rules_off():
    ss = _rss()
    h = RG.Handler(ss, _rules(), FIELDS, DOMS, "tester")
    g = next(g for g in RG.scan(_rules(), FIELDS, DOMS, ss) if g.name == "telematics_score")
    h.not_needed(g, "not filed")
    assert not ss.rules.set_index("rule_id").at["R09", "active"]
    assert "telematics_score" not in {x.name for x in RG.scan(ss.rules, FIELDS, DOMS, ss)}


# ------------------------------------------------------------------------------------------ Rating
def _spec():
    state = {"FL": 1.32, "GA": 1.08, "NC": 0.86, "TX": 1.05}
    use = {"Pleasure": 0.95, "Commute": 1.00, "Business": 1.15}
    bi = {"25/50": 0.80, "50/100": 1.00, "100/300": 1.22, "250/500": 1.45}
    coll = {250: 1.12, 500: 1.00, 1000: 0.82}
    return {"state": ("STATE_REL", "State", state, "state"), "use": ("USE", "Use", use, "use"),
            "bi": ("BI_LIMIT", "BI / UM limit", bi, "limit"), "coll_ded": ("COLL_DED", "Collision deductible", coll, "deductible")}


QUOTES = pd.DataFrame([("Q1", "AL", "Commute", "100/300", 500), ("Q2", "SC", "Rideshare", "500/1000", 2000),
                       ("Q3", "FL", "Pleasure", "50/100", 1000)], columns=["quote", "state", "use", "bi", "coll_ded"])


def test_rating_scan_and_expert_drafts():
    gaps = RT.scan(QUOTES, _spec(), SimpleNamespace())
    by = {g.name: g for g in gaps}
    assert set(by) == {"AL", "SC", "Rideshare", "500/1000", "2000"}
    assert by["AL"].candidates[0][0] == "GA" and by["AL"].proposal["factor"] == "1.080"
    assert by["SC"].proposal["factor"] == "0.860"
    assert by["Rideshare"].proposal["factor"] == "1.380"
    assert 1.45 < float(by["500/1000"].proposal["factor"]) < 2.0          # beyond the top of the ILF curve
    assert 0.5 < float(by["2000"].proposal["factor"]) < 0.82              # beyond the highest deductible
    assert "actuary" in by["AL"].proposal["description"].lower()


def test_rating_handler_map_add_skip():
    ss, spec = SimpleNamespace(), _spec()
    h = RT.Handler(ss, spec, "tester")
    gaps = {g.name: g for g in RT.scan(QUOTES, spec, ss)}
    h.map_existing(gaps["AL"], "GA")
    h.add_new(gaps["2000"], dict(gaps["2000"].proposal))
    with pytest.raises(ValueError):
        h.add_new(gaps["500/1000"], {"factor": "abc"})
    with pytest.raises(ValueError):
        h.add_new(gaps["500/1000"], {"factor": "45"})
    h.not_needed(gaps["Rideshare"], "not filed")
    RT.apply_extensions({k: t for k, _, t, _ in spec.values()}, ss)
    assert spec["state"][2]["AL"] == 1.08 and 2000 in spec["coll_ded"][2]
    assert ss.factor_ext["COLL_DED"][2000]["status"].startswith("Draft")
    assert RT.declined_reason({"use": "Rideshare"}, spec, ss).startswith("Not written")
    assert {g.name for g in RT.scan(QUOTES, spec, ss)} == {"SC", "500/1000"}
    assert RT.missing_reason(QUOTES.iloc[2].to_dict(), spec) == ""
    assert len(ss.rating_audit) == 3
