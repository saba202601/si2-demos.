"""Reading fillable insurance forms into master vocabulary (made-up fields; no real form content)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "sql" / "si2_canonical"))
import form_fields as F  # noqa: E402
import collect_si2_databases as K  # noqa: E402


def _form():
    fs = [
        F.Field("FORM 1 (2020/01)", "Vehicle_ModelYear_A", "TEXT", "Enter year: The model year of the vehicle."),
        F.Field("FORM 1 (2020/01)", "Vehicle_ModelYear_B", "TEXT", "Enter year: The model year of the vehicle."),
        F.Field("FORM 1 (2020/01)", "Building_Roof_WoodIndicator_A", "CHECK", "Check if wood."),
        F.Field("FORM 1 (2020/01)", "Building_Roof_MetalIndicator_A", "CHECK", "Check if metal."),
        F.Field("FORM 1 (2020/01)", "Pool_FenceIndicator_A", "CHECK", "Check if fenced."),
        F.Field("FORM 1 (2020/01)", "Insured_State", "CHOICE", "", options=["NY", "NJ"]),
        F.Field("FORM 1 (2020/01)", "Text7", "TEXT", ""),
        F.Field("FORM 2 (2021/02)", "Field12", "TEXT", "Enter amount: The total payroll of the employees."),
    ]
    return {"FORM 1 (2020/01)": fs[:7], "FORM 2 (2021/02)": fs[7:]}


def test_interpret_names_groups_and_unlabeled():
    forms = _form()
    for v in forms.values():
        F.interpret(v)
    f = {x.name: x for v in forms.values() for x in v}
    assert f["Vehicle_ModelYear_A"].base == "Vehicle_ModelYear" and f["Vehicle_ModelYear_A"].source == "NAME"
    assert f["Building_Roof_WoodIndicator_A"].option == "wood" and f["Building_Roof_WoodIndicator_A"].group
    assert f["Text7"].source == "NONE"
    assert f["Field12"].source == "DESCRIPTION" and "payroll" in f["Field12"].attribute


def test_catalog_lists_options_and_where_used():
    forms = _form()
    for v in forms.values():
        F.interpret(v)
    cat, usage = F.catalog(forms)
    codes = {e["code"] for e in cat["elements"].values()}
    assert "MODEL_YEAR" in codes
    roof = next(p for p in cat["picklists"].values() if p["code"] == "BUILDING_ROOF")
    assert {o["code"] for o in roof["options"].values()} == {"WOOD", "METAL"}
    assert cat["elements"]["DE:POOL_FENCE"]["picklist_code"] == "YES_NO"          # a lone check box is yes / no
    assert all(not a.startswith("Text") for e in cat["elements"].values() for a, _ in e["aliases"])
    assert len({u for u in usage if u[0] == "FORM 1 (2020/01)" and u[2] == "Vehicle_ModelYear"}) == 1   # _A and _B are one field
    assert "Name drafted from the form" in next(e for e in cat["elements"].values() if "PAYROLL" in e["code"])["desc"]


def test_catalog_plans_without_duplicates():
    forms = _form()
    for v in forms.values():
        F.interpret(v)
    cat, _ = F.catalog(forms)
    master = {k: [] for k in ("elements", "picklists", "options", "synonyms", "bureau", "rules", "rulesets", "pending")}
    master["elements"].append({"id": 1, "code": "VEHICLE_MODEL_YEAR", "name": "Vehicle Model Year", "pl": None})
    props = K.plan([cat], K.Index(master))
    assert not any(p["object_type"] == "ELEMENT" and p["code"] == "MODEL_YEAR" for p in props)
    assert any(p["object_type"] == "PICKLIST" and p["code"] == "BUILDING_ROOF" for p in props)


def test_form_id_cleanup():
    assert F.form_id("blah ACORD 125 (2016/03) blah", "x") == "ACORD 125 (2016/03)"
    assert F.form_id("", "0d4b65d7-Liability-Notice") == "Liability Notice"
