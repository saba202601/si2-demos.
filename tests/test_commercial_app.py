"""Commercial application model (Party first): consistent, collected without duplicates, entities complete, SQL current."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "sql" / "si2_canonical"))

import collect_si2_databases as K  # noqa: E402
import commercial_app_model as M  # noqa: E402
import rule_repo as R  # noqa: E402

CAT = R.seed_catalog()


def seed_master() -> dict:
    els = [{"id": i, "code": k, "name": e["name"], "pl": e["picklist"]} for i, (k, e) in enumerate(CAT.elements.items(), 1)]
    pls = [{"id": 10000 + i, "code": k, "name": k.replace("_", " ").title()} for i, k in enumerate(CAT.options)]
    plid = {p["code"]: p["id"] for p in pls}
    opts = [{"id": 50000 + n, "pl": plid[k], "code": o, "name": nm} for n, (k, o, nm) in
            enumerate((k, o, nm) for k, v in CAT.options.items() for o, nm in v)]
    eid = {e["code"]: e["id"] for e in els}
    syns = [{"ot": "ELEMENT", "id": eid[k], "text": t, "src": "*"} for k, ts in CAT.synonyms.items() if k in eid for t in ts]
    return {"elements": els, "picklists": pls, "options": opts, "synonyms": syns, "bureau": [], "rules": [], "rulesets": [], "pending": []}


def test_model_is_consistent():
    assert M.check(set(CAT.elements), set(CAT.options)) == []
    roles = dict(next(p for p in M.PICKLISTS if p[0] == "PARTY_ROLE")[3])
    assert {"FIRST_NAMED_INSURED", "OTHER_NAMED_INSURED", "LOSS_PAYEE", "LENDERS_LOSS_PAYABLE", "CERTIFICATE_HOLDER", "PRODUCER"} <= set(roles)
    assert {e[0] for e in M.ENTITIES} >= {"PARTY", "PARTY_ROLE", "PARTY_ADDRESS", "PARTY_CONTACT", "PARTY_RELATIONSHIP", "ADDITIONAL_INTEREST"}
    assert all(e[6] for e in M.ELEMENTS if e[0] in ("FEIN", "SSN", "DATE_OF_BIRTH", "EMAIL", "PHONE", "ADDRESS_STREET", "CONTACT_NAME"))   # personal data flagged


def test_collected_without_wrong_matches_or_duplicates():
    props = K.plan([M.catalog()], K.Index(seed_master()))
    new = {p["code"]: p["payload"] for p in props if p["object_type"] == "ELEMENT"}
    assert {"FIRST_NAME", "DBA_NAME", "EACH_OCCURRENCE_LIMIT", "SUBJECT_OF_INSURANCE", "INTEREST_RANK"} <= set(new)
    assert new["EACH_OCCURRENCE_LIMIT"]["subject_area"] == "LIABILITY" and new["PHONE_TYPE"]["picklist"] == "PHONE_TYPE"
    assert new["SPRINKLER_PCT"]["picklist"] is None and new["HISTORIC_LANDMARK_IND"]["picklist"] == "YES_NO"     # linked to the master's YES_NO
    syn = [(p["code"], p["payload"]["text"]) for p in props if p["object_type"] == "SYNONYM" and p["payload"]["object_type"] == "ELEMENT"]
    assert ("POLICY_EXPIRATION_DATE", "Alarm Certificate Expiration") not in syn and not any(c == "POLICY_EXPIRATION_DATE" for c, _ in syn)
    assert ("YEAR_BUILT", "Yr Built") in syn and "FEIN" not in new and "YEAR_BUILT" not in new                   # reused, labels added
    texts = [t.lower() for _, t in syn] + [s["text"].lower() for p in new.values() for s in p["synonyms"]]
    assert not {"date", "amount", "rank", "interest", "products"} & set(texts)                                      # no generic labels
    pls = {p["code"] for p in props if p["object_type"] == "PICKLIST"}
    assert {"UW_QUESTION", "PRIOR_CANCEL_REASON", "SUBJECT_OF_INSURANCE", "VALUATION"} <= pls and "PARTY_ROLE" not in pls
    opts = {p["code"] for p in props if p["object_type"] == "OPTION"}
    assert {"PARTY_ROLE.FIRST_NAMED_INSURED", "EXPOSURE_BASE.COST"} <= opts and "PARTY_ROLE.MORTGAGEE" not in opts and "EXPOSURE_BASE.PAY" not in opts


def test_09_sql_is_current():
    assert (ROOT / "sql" / "si2_canonical" / "09_commercial_app.sql").read_text(encoding="utf-8") == M.build_sql(), \
        "09_commercial_app.sql is stale: run python sql/si2_canonical/commercial_app_model.py"


def test_reused_elements_only_have_their_gaps_filled():
    master = {"FIRST_NAME": {"subject": None, "pii": False, "picklist": None, "dtype": "TEXT"},
              "NATURE_OF_BUSINESS": {"subject": "UNDERWRITING", "pii": False, "picklist": None, "dtype": "TEXT"},
              "GLOBAL_PHONE_TYPE": {"subject": None, "pii": False, "picklist": None, "dtype": "TEXT"},
              "FEIN": {"subject": "PARTY", "pii": True, "picklist": None, "dtype": "TEXT"},
              "LEGAL_ENTITY_TYPE": {"subject": "UNDERWRITING", "pii": False, "picklist": "LEGAL_ENTITY_TYPE", "dtype": "CODE"},
              "__picklists__": {"NATURE_OF_BUSINESS", "PHONE_TYPE", "LEGAL_ENTITY_TYPE"}}
    matches = {"FIRST_NAME": "FIRST_NAME", "NATURE_OF_BUSINESS": "NATURE_OF_BUSINESS", "PHONE_TYPE": "GLOBAL_PHONE_TYPE", "FEIN": "FEIN",
               "LEGAL_ENTITY_TYPE": "LEGAL_ENTITY_TYPE"}
    ups = {u["code"]: u["payload"] for u in K.enrichment(M.ELEMENTS, master, matches)}
    assert ups["FIRST_NAME"] == {"code": "FIRST_NAME", "subject_area": "PARTY", "is_pii": 1}
    assert ups["NATURE_OF_BUSINESS"] == {"code": "NATURE_OF_BUSINESS", "picklist": "NATURE_OF_BUSINESS", "data_type": "CODE"}   # subject kept
    assert ups["GLOBAL_PHONE_TYPE"] == {"code": "GLOBAL_PHONE_TYPE", "subject_area": "PARTY"}     # other name: no pick list forced on it
    assert "FEIN" not in ups and "LEGAL_ENTITY_TYPE" not in ups                                    # nothing missing: nothing proposed
