"""Collector: reads the other SI² databases and proposes only what the master does not have."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "sql" / "si2_canonical"))
import collect_si2_databases as K  # noqa: E402

MASTER = {
    "elements": [{"id": 1, "code": "STATE", "name": "State"}, {"id": 2, "code": "POLICY_NUMBER", "name": "Policy Number"},
                 {"id": 3, "code": "COVERAGE_A_LIMIT", "name": "Coverage A Dwelling Limit"}],
    "picklists": [{"id": 10, "code": "STATE", "name": "State"}, {"id": 11, "code": "CONSTRUCTION", "name": "Construction Type"},
                  {"id": 12, "code": "YES_NO", "name": "Yes / No"}],
    "options": [{"id": 100, "pl": 10, "code": "TX", "name": "Texas"}, {"id": 101, "pl": 10, "code": "FL", "name": "Florida"},
                {"id": 110, "pl": 11, "code": "FR", "name": "Frame"}],
    "synonyms": [{"ot": "ELEMENT", "id": 1, "text": "Risk State", "src": "*"}, {"ot": "ELEMENT", "id": 2, "text": "POL_NO", "src": "*"}],
    "bureau": [], "rules": [{"code": "R01"}], "rulesets": [{"code": "UW_PERSONAL_AUTO"}], "pending": [],
}


class FakeReader:
    db = "RuleEngine"

    def __init__(self, tables):
        self.tables = tables

    def rows(self, schema, table, want, where_current=None):
        return [{c: r.get(c) for c in want} for r in self.tables.get(table, [])]


RE_TABLES = {
    "PickList": [{"PickListID": "PL01", "PickListName": "State Code"}, {"PickListID": "PL02", "PickListName": "Construction Type"},
                 {"PickListID": "PL03", "PickListName": "Product Code", "Description": "Homeowners forms"}],
    "PickListOption": [{"OptionID": "O1", "PickListID": "PL01", "OptionCode": "TX", "OptionName": "Texas"},
                       {"OptionID": "O2", "PickListID": "PL01", "OptionCode": "GA", "OptionName": "Georgia"},
                       {"OptionID": "O3", "PickListID": "PL02", "OptionCode": "WD", "OptionName": "Frame"},
                       {"OptionID": "O4", "PickListID": "PL03", "OptionCode": "HO3", "OptionName": "Special form"}],
    "PickListOptionAlias": [{"OptionID": "O3", "AliasCode": "1", "AliasName": "Wood frame", "AliasSourceSystem": "Client Legacy"}],
    "DataElement": [{"DataElementID": "DE004", "DataElementName": "Risk State", "DataType": "Pick List", "PickListID": "PL01"},
                    {"DataElementID": "DE010", "DataElementName": "Coverage A Dwelling Limit", "DataType": "Currency"},
                    {"DataElementID": "DE020", "DataElementName": "Roof Age", "BusinessDefinition": "Age of the roof in years", "DataType": "Integer"},
                    {"DataElementID": "DE005", "DataElementName": "Product", "DataType": "Pick List", "PickListID": "PL03"}],
    "DataElementAlias": [{"DataElementID": "DE020", "Alias": "RoofAgeYrs", "AliasSourceSystem": "Guidewire"}],
    "Rule": [{"RuleID": "R-0004", "State": "FL", "Product": "HO3", "Module": "Policy", "SubModule": "Underwriting",
              "BusinessRule": "Refer homes with roof age over 20 years", "Status": "Approved",
              "RuleJSON": '{"when":[{"field":"DE020","op":"gt","value":20}],"then":[{"action":"refer","to":"Underwriting","reason":"Roof age over 20"}]}'}],
}


def proposals():
    cat = K.read_rule_engine(FakeReader(RE_TABLES))
    return K.plan([cat], K.Index(MASTER))


def test_existing_items_are_matched_not_duplicated():
    p = proposals()
    codes = {(x["object_type"], x["code"]) for x in p}
    assert ("PICKLIST", "STATE") not in codes and ("PICKLIST", "CONSTRUCTION") not in codes   # 'State Code' = STATE, by name
    assert ("ELEMENT", "STATE") not in codes and ("ELEMENT", "COVERAGE_A_LIMIT") not in codes    # 'Risk State' synonym; same name
    assert ("OPTION", "CONSTRUCTION.WD") not in codes                                            # WD is Frame (by name)


def test_missing_items_are_proposed_in_order():
    p = proposals()
    codes = [(x["object_type"], x["code"]) for x in p]
    assert ("OPTION", "STATE.GA") in codes
    assert ("PICKLIST", "PRODUCT_CODE") in codes and ("OPTION", "PRODUCT_CODE.HO3") in codes
    assert ("ELEMENT", "ROOF_AGE") in codes and ("RULE", "R-0004") in codes and ("RULESET", "RULEENGINE_POLICY") in codes
    order = [K.ORDER[t] for t, _ in codes]
    assert order == sorted(order)
    roof = next(x for x in p if x["code"] == "ROOF_AGE")["payload"]
    assert roof["data_type"] == "INTEGER" and {"DE020", "RoofAgeYrs"} <= {s["text"] for s in roof["synonyms"]}
    product = next(x for x in p if x["code"] == "PRODUCT")["payload"]
    assert product["picklist"] == "PRODUCT_CODE"


def test_source_names_become_synonyms():
    syn = {(x["payload"]["object_type"], x["code"], x["payload"]["text"]) for x in proposals() if x["object_type"] == "SYNONYM"}
    assert ("ELEMENT", "STATE", "DE004") in syn                 # the rule engine's id, so its rules map
    assert ("OPTION", "CONSTRUCTION.FR", "WD") in syn             # its code for Frame
    assert ("OPTION", "CONSTRUCTION.FR", "Wood frame") in syn     # the legacy alias
    assert ("PICKLIST", "STATE", "State Code") in syn
    assert not any(t == "Risk State" for _, _, t in syn)        # already known


def test_rule_conditions_use_master_elements():
    rule = next(x for x in proposals() if x["object_type"] == "RULE")["payload"]
    assert rule["action_type"] == "REFER" and rule["rule_type"] == "REFERRAL" and rule["state"] == "FL"
    assert rule["conditions"] == [{"element": "ROOF_AGE", "operator": ">", "value1": "20"}]


def test_second_run_proposes_nothing_new_for_pending_items():
    cat = K.read_rule_engine(FakeReader(RE_TABLES))
    ix = K.Index(MASTER)
    first = K.plan([cat], ix)
    again = K.plan([K.read_rule_engine(FakeReader(RE_TABLES))], ix)
    assert first and not again


def test_bureau_and_iso_readers():
    br = FakeReader({
        "PickList": [{"PickListCode": "WC_TRANS", "PickListName": "Transaction Code", "OwnerBureauCode": "NCCI"}],
        "PickListOption": [{"PickListCode": "WC_TRANS", "OptionCode": "01", "OptionName": "New Policy"}],
        "PickListOptionAlias": [{"PickListCode": "WC_TRANS", "OptionCode": "01", "AliasValue": "Submission", "SourceSystemCode": "GW"}],
        "DataElement": [{"ElementCode": "POL_NO", "ElementName": "Policy Number", "DataType": "AN", "LayoutCode": "WCPOLS01"},
                        {"ElementCode": "FILLER1", "ElementName": "Filler", "DataType": "AN", "IsFiller": 1}],
        "BureauRule": [{"RuleCode": "WCPOLS_REQUIRED_POLICY_NUMBER_IDENTIFIER_IN_EVERY_RECORD_OF_THE_UNIT", "ReportTypeCode": "WCPOLS",
                        "ElementCode": "POL_NO", "RuleType": "REQUIRED", "Severity": "Reject", "Message": "Policy number is required"}],
    })
    br.db = "BureauReporting"
    iso = FakeReader({
        "picklist": [{"picklist_code": "STATE", "picklist_name": "State", "status": "APPROVED"}],
        "picklist_option": [{"picklist_code": "STATE", "option_code": "TX", "option_name": "Texas", "status": "APPROVED"}],
        "bureau_code_map": [{"bureau_code": "ISO", "picklist_code": "STATE", "option_code": "TX", "bureau_value": "42", "status": "APPROVED"}],
        "canonical_element": [{"element_code": "ACCT_DATE", "element_name": "Accounting Date", "data_type": "DATE", "status": "REJECTED"}],
    })
    iso.db = "ISOBureauReporting"
    p = K.plan([K.read_bureau_reporting(br), K.read_iso(iso)], K.Index(MASTER))
    codes = {(x["object_type"], x["code"]) for x in p}
    assert ("ELEMENT", "POL_NO") not in codes and not any("FILLER" in c for _, c in codes)      # POL_NO is a synonym of POLICY_NUMBER
    rule = next(x for x in p if x["object_type"] == "RULE")
    assert len(rule["code"]) <= 40 and rule["payload"]["target_element"] == "POLICY_NUMBER" and rule["payload"]["action_type"] == "REJECT"
    assert ("BUREAU_CODE", "STATE.TX.ISO") in codes
    assert ("ELEMENT", "ACCT_DATE") not in codes                                                    # rejected rows are ignored
