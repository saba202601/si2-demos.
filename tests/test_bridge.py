"""SI² Data Bridge: legacy -> canonical -> destinations, from mappings in memory and from database tables."""
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "sql" / "si2_canonical"))
import bridge as B  # noqa: E402
import bridge_systems as S  # noqa: E402


def _run(d=None, n=120):
    rows = S.legacy_extract(n)
    return rows, B.run(rows, S.LEGACY_PAS, S.DESTINATIONS, d or B.MemoryDictionary())


def test_good_records_reach_every_destination_and_bad_ones_are_held():
    rows, r = _run()
    st = r.stats()
    assert st["held"] == 4 and st["passed"] == len(rows) - 4
    assert st["to POLICYCLOUD"] == st["to ISO_STAT"] == st["passed"]
    probs = {x["Field"]: x["Problem"] for x in r.issues if x["Severity"] == "ERROR"}
    assert set(probs) == {"CONST_CD", "EFF_DT", "RSK_ST", "DED_AMT"}
    assert any(x["Field"] == "AGT_CD" and x["Severity"] == "INFO" for x in r.issues)        # unmapped: reported, never guessed


def test_values_translate_through_the_canonical_option():
    rows, r = _run()
    first = r.outputs["POLICYCLOUD"][0]
    src = rows[0]
    assert first["constructionType"] == {"F": "frame", "J": "joistedMasonry", "N": "nonCombustible", "M": "masonry",
                                         "R": "fireResistive", "V": "masonryVeneer"}[src["CONST_CD"]]
    assert first["effectiveDate"] == f"{src['EFF_DT'][:4]}-{src['EFF_DT'][4:6]}-{src['EFF_DT'][6:]}"
    last, first_name = src["INS_NM"].split(", ")
    assert first["insuredName"] == f"{first_name.capitalize()} {last.capitalize()}"
    assert float(first["writtenPremium"]) == int(src["WRT_PREM"]) / 100


def test_iso_record_is_fixed_width_with_bureau_codes():
    rows, r = _run()
    width = sum(f.width for f in S.ISO_STAT.fields)
    assert all(len(line) == width for line in r.outputs["ISO_STAT"])
    line, src = r.outputs["ISO_STAT"][0], rows[0]
    assert line[:2] == S.ISO_CODES["LOB"][S.LOB_LEGACY[src["LOB_CD"]]]
    assert line[2:4] == S.STATE_ISO[src["RSK_ST"]]
    assert line[8:10] == S.ISO_CODES["CONSTRUCTION"][S.CONST_LEGACY[src["CONST_CD"]]]
    cancel = next(i for i, x in enumerate(rows) if x["TRN_CD"] == "X" and x["POL_NO"] not in r.held)
    passed = [x for x in rows if x["POL_NO"] not in r.held]
    iso_line = r.outputs["ISO_STAT"][passed.index(rows[cancel])]
    assert iso_line[4:6] == "13" and "-" in iso_line                                      # cancellation, negative premium


def test_every_value_has_lineage():
    _, r = _run()
    per_record = len(S.POLICYCLOUD.fields) + len(S.ISO_STAT.fields)
    assert len(r.lineage) == r.stats()["passed"] * per_record
    assert all(x["Source field"] and x["Element"] for x in r.lineage)


def test_proposals_are_unique_and_skip_unmapped_fields():
    props = S.proposals()
    keys = [(p["payload"]["object_type"], p["code"], p["payload"]["text"], p["payload"]["source"]) for p in props]
    assert len(keys) == len(set(keys))
    assert not any(p["payload"]["text"] == "AGT_CD" for p in props)
    assert {p["payload"]["type"] for p in props} == {"LEGACY", "APP", "BUREAU", "VALUE"}


def test_crosswalk_and_matrix():
    d = B.MemoryDictionary()
    cw = {r["Canonical option"]: r for r in B.value_crosswalk(d, "CONSTRUCTION")}
    assert cw["FR"] == {"Canonical option": "FR", "LEGACY_PAS": "F", "POLICYCLOUD": "frame", "ISO_STAT": "01"}
    m = {r["Element"]: r for r in B.mapping_matrix(d)}
    assert m["POLICY_EFFECTIVE_DATE"]["LEGACY_PAS"] == "EFF_DT" and m["POLICY_EFFECTIVE_DATE"]["POLICYCLOUD"] == "effectiveDate"


def _sqlite_master():
    """SI2Canonical's tables for the bridge, in SQLite, with the system mappings applied as approved aliases."""
    con = sqlite3.connect(":memory:")
    con.execute("ATTACH ':memory:' AS canon")
    con.executescript("""
        CREATE TABLE canon.PickList (PickListId INTEGER PRIMARY KEY, PickListCode TEXT, ScopeId INT DEFAULT 1, Status TEXT DEFAULT 'ACTIVE');
        CREATE TABLE canon.PickListOption (OptionId INTEGER PRIMARY KEY, PickListId INT, OptionCode TEXT, Status TEXT DEFAULT 'ACTIVE');
        CREATE TABLE canon.DataElement (ElementId INTEGER PRIMARY KEY, ElementCode TEXT, Name TEXT, DataType TEXT, PickListId INT,
                                        ScopeId INT DEFAULT 1, Status TEXT DEFAULT 'ACTIVE');
        CREATE TABLE canon.Synonym (ObjectType TEXT, ObjectId INT, SynonymText TEXT, SourceSystem TEXT, Status TEXT DEFAULT 'ACTIVE');
        CREATE TABLE canon.BureauCodeMap (OptionId INT, Bureau TEXT, BureauCode TEXT, LobScope TEXT DEFAULT '*', Status TEXT DEFAULT 'ACTIVE');
    """)
    pl_id, opt_id, el_id = {}, {}, {}
    for pl, opts in S.OPTIONS.items():
        pl_id[pl] = con.execute("INSERT INTO canon.PickList (PickListCode) VALUES (?)", (pl,)).lastrowid
        for o in sorted(opts):
            opt_id[(pl, o)] = con.execute("INSERT INTO canon.PickListOption (PickListId, OptionCode) VALUES (?, ?)", (pl_id[pl], o)).lastrowid
    for code, (name, typ, pl) in S.ELEMENTS.items():
        el_id[code] = con.execute("INSERT INTO canon.DataElement (ElementCode, Name, DataType, PickListId) VALUES (?, ?, ?, ?)",
                                  (code, name, typ, pl_id.get(pl))).lastrowid
    for pl, codes in S.ISO_CODES.items():
        for o, c in codes.items():
            con.execute("INSERT INTO canon.BureauCodeMap (OptionId, Bureau, BureauCode) VALUES (?, 'ISO', ?)", (opt_id[(pl, o)], c))
    for p in S.proposals():                                  # what usp_Apply does with each approved alias
        j = p["payload"]
        oid = el_id[j["object_code"]] if j["object_type"] == "ELEMENT" else opt_id[(j["picklist"], j["object_code"])]
        con.execute("INSERT INTO canon.Synonym (ObjectType, ObjectId, SynonymText, SourceSystem) VALUES (?, ?, ?, ?)",
                    (j["object_type"], oid, j["text"], j["source"]))
    return con


def test_database_dictionary_gives_the_same_result_as_memory():
    d = B.SqlDictionary(_sqlite_master())
    assert d.kind == "sql" and d.fields("LEGACY_PAS")["EFF_DT"] == "POLICY_EFFECTIVE_DATE"
    _, r_sql = _run(d)
    _, r_mem = _run()
    assert r_sql.outputs == r_mem.outputs and r_sql.stats() == r_mem.stats()


def test_formats():
    assert B.emit(-1234.4, "dollars", 9) == "-00001234"
    assert B.emit("HO3", "text", 5) == "HO3  "
    assert B.parse("000012345", "implied2") == 123.45
    assert B.parse("SMITH, MARY ANN", "name_last_first") == "Mary Ann Smith"
    assert B.parse("7", "pad2") == "07"
