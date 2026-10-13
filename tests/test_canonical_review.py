"""Duplicate review: finds same-meaning elements, keeps the standard one, merges by synonyms and expiry."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "sql" / "si2_canonical"))
import review_duplicates as R  # noqa: E402

E = [
    {"id": 1, "code": "LOSS_DESCRIPTION", "name": "Loss Description", "desc": "Free-text description of the loss.", "dtype": "TEXT", "created_by": "SI2 seed"},
    {"id": 2, "code": "DESCRIPTION_OF_LOSS", "name": "Description of Loss", "desc": "Narrative of what happened.", "dtype": "TEXT", "created_by": "Saba"},
    {"id": 3, "code": "REVIEWED_BY", "name": "Reviewed By", "desc": "Person who reviewed.", "dtype": "TEXT", "created_by": "Saba"},
    {"id": 4, "code": "REVIEWED_ON", "name": "Reviewed On", "desc": "Date reviewed.", "dtype": "DATE", "created_by": "Saba"},
    {"id": 5, "code": "CLAIM_STATUS", "name": "Claim Status", "desc": "Status of the claim.", "dtype": "CODE", "picklist": "CLAIM_STATUS", "created_by": "SI2 seed"},
    {"id": 6, "code": "CLAIM_STATUS_OPTIONS", "name": "ClaimStatusOptions", "desc": "Options.", "dtype": "CODE", "created_by": "Saba"},
    {"id": 7, "code": "CLAIM_NUMBER", "name": "Claim Number", "desc": "Claim identifier.", "dtype": "TEXT", "created_by": "SI2 seed"},
    {"id": 8, "code": "NUMBER_CLAIMS", "name": "Number Claims", "desc": "How many claims.", "dtype": "TEXT", "created_by": "Saba"},
    {"id": 9, "code": "WIND_DED_PCT", "name": "Wind Deductible Percent", "desc": "x", "dtype": "PERCENT", "created_by": "Saba"},
]
S = [{"id": 5, "text": "ClaimStatusOptions", "source": "SemanticMappingHub"}, {"id": 2, "text": "LossNarrative", "source": "Guidewire"}]


def test_finds_real_duplicates_only():
    rows, shared = R.find_duplicates(E, S, {})
    pairs = {(r["Keep"], r["Merge"]): r for r in rows}
    assert pairs[("LOSS_DESCRIPTION", "DESCRIPTION_OF_LOSS")]["Confidence"] == "High"        # standard element is kept
    assert pairs[("CLAIM_STATUS", "CLAIM_STATUS_OPTIONS")]["Decision"] == "MERGE"
    assert not any({r["Keep"], r["Merge"]} == {"REVIEWED_BY", "REVIEWED_ON"} for r in rows)      # 'by' and 'on' matter
    cn = pairs.get(("CLAIM_NUMBER", "NUMBER_CLAIMS"))
    assert cn is None or cn["Confidence"] == "Medium"                                          # an id is not a count


def test_apply_moves_names_and_expires():
    rows, _ = R.find_duplicates(E, S, {})
    ch = R.plan_apply(rows, [{"id": 42, "picklist": "CONSTRUCTION", "option": "FR", "bureau": "ISO", "code": "ISO_CT1", "Decision": "EXPIRE"}], E, S)
    syn = {(c["code"], c["payload"]["text"]) for c in ch if c["object_type"] == "SYNONYM"}
    assert ("LOSS_DESCRIPTION", "DESCRIPTION_OF_LOSS") in syn and ("LOSS_DESCRIPTION", "LossNarrative") in syn
    assert ("ELEMENT", "EXPIRE", "DESCRIPTION_OF_LOSS") in {(c["object_type"], c["change"], c["code"]) for c in ch}
    assert not any(c["payload"].get("text") == "ClaimStatusOptions" for c in ch)                # already a synonym of the keeper
    assert any(c["object_type"] == "BUREAU_CODE" and c["payload"]["id"] == 42 for c in ch)
    order = [c["object_type"] for c in ch if c["code"] in ("LOSS_DESCRIPTION", "DESCRIPTION_OF_LOSS")]
    assert order.index("SYNONYM") < order.index("ELEMENT")                                     # names move before the expiry


def test_workbook_round_trip(tmp_path):
    rows, shared = R.find_duplicates(E, S, {})
    p = R.write_review(tmp_path / "review.xlsx", rows, [{"id": 42, "code": "ISO_CT1", "Decision": "EXPIRE"}], shared)
    merges, bureau = R.read_review(p)
    assert len(merges) == len(rows) and bureau[0]["Decision"] == "EXPIRE"
