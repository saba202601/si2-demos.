"""Install (or self-test) the SI² Canonical Master database on SQL Server with Windows Authentication.

    python install_si2_canonical.py --selftest      build a throw-away copy, run every flow, report PASS / FAIL, drop it
    python install_si2_canonical.py                 install or update SI2Canonical (re-running only adds what is missing)
    python install_si2_canonical.py --demo          also create SI2_SourceDemo, a small database to try the scan on

Options: --server SABAHOME\\SQLEXPRESS02 (default, or env SI2_MSSQL_SERVER)   --database SI2Canonical   --keep (self-test)
Needs: pip install pyodbc, and "ODBC Driver 17 or 18 for SQL Server". No passwords: Windows sign-in only.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
DRIVERS = ["ODBC Driver 18 for SQL Server", "ODBC Driver 17 for SQL Server", "ODBC Driver 13 for SQL Server",
           "SQL Server Native Client 11.0", "SQL Server"]


def connect(server: str, database: str = "master"):
    import pyodbc
    have = set(pyodbc.drivers())
    driver = next((d for d in DRIVERS if d in have), None)
    if not driver:
        sys.exit("No SQL Server ODBC driver found. Install 'ODBC Driver 18 for SQL Server'.")
    return pyodbc.connect(f"DRIVER={{{driver}}};SERVER={server};DATABASE={database};Trusted_Connection=yes;TrustServerCertificate=yes;",
                          autocommit=True)


def batches(sql: str) -> list[str]:
    return [b.strip() for b in re.split(r"^\s*GO\s*;?\s*$", sql, flags=re.M | re.I) if b.strip()]


def run_file(con, path: Path, db: str, demo_db: str = "SI2_SourceDemo") -> None:
    sql = path.read_text(encoding="utf-8").replace("SI2_SourceDemo", demo_db).replace("SI2Canonical", db)
    cur = con.cursor()
    for i, b in enumerate(batches(sql), 1):
        try:
            cur.execute(b)
            while cur.nextset():
                pass
        except Exception as ex:  # noqa: BLE001
            first = b.splitlines()[0][:120]
            raise SystemExit(f"\nFAILED in {path.name}, batch {i} ({first} ...):\n{ex}\n") from None


def query(con, sql: str, *params) -> list[list[dict]]:
    """All result sets of a statement as lists of dicts."""
    cur = con.cursor()
    cur.execute(sql, *params)
    sets = []
    while True:
        if cur.description:
            cols = [c[0] for c in cur.description]
            sets.append([dict(zip(cols, r)) for r in cur.fetchall()])
        if not cur.nextset():
            break
    return sets


def install(server: str, db: str, demo: bool, demo_db: str = "SI2_SourceDemo", quiet: bool = False) -> None:
    con = connect(server)
    say = (lambda *a: None) if quiet else print
    say(f"Server {server}: database {db}")
    con.cursor().execute(f"IF DB_ID(N'{db}') IS NULL CREATE DATABASE [{db}];")
    exists = query(con, f"SELECT OBJECT_ID(N'[{db}].canon.DataElement') AS x")[0][0]["x"]
    steps = ([] if exists else ["01_schema.sql"]) + ["02_procedures.sql", "03_seed.sql", "06_rule_engine.sql",
                                                       "07_rule_library.sql", "08_coverage.sql"] + (["04_demo_source.sql"] if demo else [])
    if exists:
        say("  schema already there: keeping it (procedures refreshed, missing seed rows added)")
    for f in steps:
        t = time.time()
        run_file(con, HERE / f, db, demo_db)
        say(f"  {f:<22} ok ({time.time() - t:.1f}s)")
    con2 = connect(server, db)
    s = query(con2, "SELECT * FROM canon.vw_Summary")[0][0]
    say("  " + " · ".join(f"{k} {v}" for k, v in s.items()))
    con.close()
    con2.close()


# ------------------------------------------------------------------------------------------- self-test
def coverage_checks(server, db, check, one) -> None:
    """Claim coverage: forms read, claims checked from SQL Server give the same findings as in Python, alerts routed, closing rules."""
    sys.path.insert(0, str(HERE))
    import check_claims as K
    import coverage as C
    cn = K.connect(server, db)
    n = K.rows(cn, "SELECT (SELECT COUNT(*) FROM cov.Form) f, (SELECT COUNT(*) FROM cov.FormSection) s, (SELECT COUNT(*) FROM cov.Claim) c, "
                   "(SELECT COUNT(*) FROM canon.vw_PickListOption WHERE PickList = 'CAUSE_OF_LOSS' AND OptionCode IN ('FLOOD', 'SEWER', 'MOLD')) o, "
                   "(SELECT COUNT(*) FROM canon.vw_Synonym WHERE ObjectCode = 'CAUSE_OF_LOSS.FLOOD') w")[0]
    check("coverage: forms, sections, claims, causes and loss words loaded", n["f"] >= 16 and n["s"] >= 40 and n["c"] >= 90 and n["o"] == 3 and n["w"] >= 15,
          f"{n['f']} forms, {n['s']} sections, {n['c']} claims, FLOOD has {n['w']} loss words")
    lib, pols, claims = K.load(cn)
    alerts = C.check_all(claims, pols, lib)
    plib = C.FormLibrary.synthetic()
    ppols = C.synthetic_policies()
    expect = C.check_all(C.synthetic_claims(ppols, lib=plib), ppols, plib)
    key = lambda xs: sorted((a["claim"], a["type"]) for a in xs)  # noqa: E731
    check("claims checked from SQL Server match the engine", key(alerts) == key(expect), f"{len(alerts)} findings")
    first, again = K.save_alerts(cn, alerts), K.save_alerts(cn, alerts)
    check("alerts saved once (re-running adds none)", first == len(alerts) and again == 0, f"{first} added, then {again}")
    surge = K.rows(cn, "SELECT AlertType, SendTo, CopyTo FROM cov.CoverageAlert WHERE ClaimNumber = 'CLM-69901' ORDER BY AlertType")
    check("storm surge recorded as wind: cause mismatch, not covered, paid on an exclusion",
          {r["AlertType"] for r in surge} >= {"CAUSE_MISMATCH", "NOT_COVERED", "PAID_NOT_COVERED"}, str([tuple(r.values()) for r in surge]))
    lim = K.rows(cn, "SELECT TOP (1) AlertId, AdjusterName, SendTo, CopyTo FROM cov.CoverageAlert WHERE AlertType = 'LIMIT_MISMATCH'")[0]
    check("limit changed on a claim goes to the underwriter, copy to the claims manager", (lim["SendTo"], lim["CopyTo"]) == ("UNDERWRITER", "CLAIMS_MANAGER"))
    try:
        cn.cursor().execute("EXEC cov.usp_CloseAlert ?, ?, N'fine'", lim["AlertId"], lim["AdjusterName"])
        check("the adjuster cannot close an alert on their own claim", False)
    except Exception as ex:  # noqa: BLE001
        check("the adjuster cannot close an alert on their own claim", "cannot close" in str(ex))
    cn.cursor().execute("EXEC cov.usp_CloseAlert ?, N'Sabasi', N'Limit corrected to the policy limit'", lim["AlertId"])
    check("the claims manager closes it with a note", K.rows(cn, "SELECT Status FROM cov.CoverageAlert WHERE AlertId = ?", lim["AlertId"])[0]["Status"] == "CLOSED")
    cn.close()


def rule_engine_checks(server, db, con, check, one) -> None:
    """Rule engine: library loaded, a Georgia rule proposed by Saba from Python and approved by Sabasi, read back by the Rule Studio."""
    sys.path.insert(0, str(HERE))
    import rule_engine as E
    import rule_repo as R
    n = one("SELECT (SELECT COUNT(*) FROM rules.Role) r, (SELECT COUNT(*) FROM rules.RuleTemplate) t, (SELECT COUNT(*) FROM rules.RuleScope) s, "
            "(SELECT COUNT(*) FROM rules.DecisionTableRow) d, (SELECT COUNT(*) FROM rules.RoleAuthority) a, "
            "(SELECT COUNT(*) FROM rules.BusinessRule WHERE OwnerRole IS NOT NULL) o")
    check("rule library: roles, templates, scopes, tables, authority", n["r"] >= 16 and n["t"] >= 18 and n["s"] > 100 and n["d"] >= 25 and n["a"] >= 13
          and n["o"] >= 140, f"{n['r']} roles, {n['t']} templates, {n['s']} scope rows, {n['d']} table rows, {n['a']} authority rows, {n['o']} rules with an owner")
    cat = one("SELECT States, Lines, Companies FROM rules.vw_RuleCatalog WHERE RuleCode = 'HO-E01-FL'")
    check("catalog shows where a rule applies", (cat["States"], cat["Lines"], cat["Companies"]) == ("FL", "HO", "SIM"), str(cat))
    repo = R.SqlRepo(server, db)
    rule = E.Rule("HO-E01-GA", "Roof older than 20 years (Georgia)", "DECLINE", [("ROOF_AGE", ">", "20", None)], phase="ELIGIBILITY",
                  scope={"COMPANY": ["SIM"], "LOB": ["HO"], "STATE": ["GA"]}, override_key="HO_ROOF_AGE_LIMIT", role="UNDERWRITER",
                  template="UW_DECLINE", severity="ERROR", effective_from="2026-01-01")
    rid = repo.propose("RULE", "ADD", rule.code, R.rule_payload(rule, "UW_ELIGIBILITY", "ELIGIBILITY", E.generate_tests(rule)), "Saba", "Georgia roof limit")
    try:
        repo.decide(rid, "Saba")
        check("Rule Studio: two-person rule", False)
    except ValueError as ex:
        check("Rule Studio: two-person rule", "Two-person" in str(ex), str(ex)[:80])
    status, result = repo.decide(rid, "Sabasi")
    check("Rule Studio: Sabasi approves Saba's rule", status == "APPROVED", result)
    live = repo.rule("HO-E01-GA")
    ga = E.evaluate(repo.rules, {"COMPANY": "SIM", "LOB": "HO", "STATE": "GA"}, {"ROOF_AGE": 22}, "2026-10-13")
    fl = E.evaluate(repo.rules, {"COMPANY": "SIM", "LOB": "HO", "STATE": "FL"}, {"ROOF_AGE": 22}, "2026-10-13")
    check("Georgia rule overrides countrywide, Florida keeps its own", live is not None and live.scope == rule.scope
          and [r.code for r, _ in ga.fired if r.override_key] == ["HO-E01-GA"] and [r.code for r, _ in fl.fired if r.override_key] == ["HO-E01-FL"])
    t = query(con, "EXEC rules.usp_RunTests")
    check("generated tests pass in SQL Server too", t[0][0]["Failed"] == 0 and one("SELECT COUNT(*) n FROM rules.RuleTestCase t JOIN rules.BusinessRule r "
          "ON r.RuleId = t.RuleId WHERE r.RuleCode = 'HO-E01-GA'")["n"] == 2, f"{t[0][0]['Passed']} passed, {t[0][0]['Failed']} failed")
    rid = repo.propose("AUTHORITY", "ADD", "UNDERWRITER.BIND_TIV.*", {"role": "UNDERWRITER", "authority": "BIND_TIV", "lob": "*", "limit": 3000000,
                                                                    "effective_from": "2026-11-01"}, "Saba", "raise")
    repo.decide(rid, "Sabasi")
    rows = sorted((a["status"], a["effective_to"] or "") for a in repo.authority if (a["role"], a["authority"], a["lob"]) == ("UNDERWRITER", "BIND_TIV", "*"))
    check("new authority limit closes the old one", rows == [("ACTIVE", ""), ("EXPIRED", "2026-10-31")], str(rows))
    rid = repo.propose("DTABLE_ROW", "ADD", "CANCEL_NOTICE_DAYS", {"table": "CANCEL_NOTICE_DAYS", "inputs": {"STATE": "AL", "CANCEL_REASON": "UW"},
                                                                  "outputs": {"NOTICE_DAYS": 20}}, "Saba", "AL")
    repo.decide(rid, "Sabasi")
    hit = E.lookup(repo.engine_tables()["CANCEL_NOTICE_DAYS"], {"STATE": "AL", "CANCEL_REASON": "UW"})
    check("decision table row added and used", hit == {"NOTICE_DAYS": 20}, str(hit))
    rid = repo.propose("TEMPLATE", "ADD", "UW_REFER_TEST", {"code": "UW_REFER_TEST", "name": "Test template", "owner_role": "UNDERWRITER",
                                                           "sentence": "Refer when {conditions}", "questions": [{"name": "conditions"}]}, "Saba", "t")
    check("new template", repo.decide(rid, "Sabasi")[0] == "APPROVED" and repo.template("UW_REFER_TEST") is not None)
    repo.cn.close()



def selftest(server: str, keep: bool) -> int:
    db, demo_db = "SI2Canonical_SelfTest", "SI2_SourceDemo_SelfTest"
    master = connect(server)
    for d in (db, demo_db):
        master.cursor().execute(f"IF DB_ID(N'{d}') IS NOT NULL BEGIN ALTER DATABASE [{d}] SET SINGLE_USER WITH ROLLBACK IMMEDIATE; DROP DATABASE [{d}]; END")
    print(f"Self-test on {server} (temporary databases {db}, {demo_db})")
    install(server, db, demo=True, demo_db=demo_db, quiet=True)
    install(server, db, demo=False, demo_db=demo_db, quiet=True)          # re-run must be harmless
    con = connect(server, db)
    results = []

    def check(name, ok, detail=""):
        results.append(ok)
        print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  ({detail})" if detail else ""))

    def one(sql, *p):
        return query(con, sql, *p)[0][0]

    s = one("SELECT * FROM canon.vw_Summary")
    check("seed loaded (elements, pick lists, options, synonyms, rules)",
          s["DataElements"] > 150 and s["PickLists"] > 100 and s["PickListOptions"] > 800 and s["Synonyms"] > 600 and s["Rules"] > 70,
          f"{s['DataElements']} elements, {s['PickLists']} pick lists, {s['PickListOptions']} options, {s['Synonyms']} synonyms, {s['Rules']} rules")
    check("re-running the installer adds no duplicates", one("SELECT * FROM canon.vw_Summary") == s)
    t = query(con, "EXEC rules.usp_RunTests")
    check("rule test cases", t[0][0]["Failed"] == 0, f"{t[0][0]['Passed']} passed, {t[0][0]['Failed']} failed "
          + ", ".join(r["RuleCode"] for r in t[1] if r["Outcome"] == "FAIL"))

    rid = query(con, "EXEC canon.usp_ProposeElement @Code='ROOF_AGE_BAND', @Name=N'Roof Age Band', @Description=N'Roof age band.', "
                     "@SubjectArea='PROPERTY', @Synonyms=N'RoofAgeBand,roof_age_grp', @RequestedBy=N'Tester A'")[0][0]["RequestId"]
    try:
        query(con, "EXEC gov.usp_Decide ?, N'Tester A', 1", rid)
        check("two-person rule blocks self-approval", False)
    except Exception as ex:  # noqa: BLE001
        check("two-person rule blocks self-approval", "Two-person" in str(ex))
    r = query(con, "EXEC gov.usp_Decide ?, N'Tester B', 1", rid)[0][0]
    check("second person approves a new element", r["Status"] == "APPROVED", r["Result"])
    check("element and its synonyms are in the model",
          one("SELECT COUNT(*) n FROM canon.vw_Synonym WHERE ObjectCode='ROOF_AGE_BAND'")["n"] == 2)

    query(con, "EXEC canon.usp_ProposePickList 'ROOF_SHAPE', N'Roof Shape', N'Shape of the roof.', N'GABLE=Gable;HIP=Hip;FLAT=Flat', 'COMPANY', N'GLOBAL', N'Tester A'")
    out = query(con, "EXEC gov.usp_DecideAll N'Tester B', 1, NULL, NULL, NULL, N'ROOF_SHAPE%'")
    check("new pick list with options", one("SELECT ActiveOptions FROM canon.vw_PickList WHERE PickListCode='ROOF_SHAPE'")["ActiveOptions"] == 3,
          "; ".join(f"{x['Status']} {x['Requests']}" for x in out[0]))

    query(con, "EXEC canon.usp_ProposeSynonym 'OPTION', 'OP', N'Pending', N'Majesco', 'CLAIM_STATUS', NULL, N'GLOBAL', N'Tester A'")
    query(con, "EXEC gov.usp_DecideAll N'Tester B', 1, NULL, NULL, 'SYNONYM'")
    check("synonym on a pick-list option", one("SELECT COUNT(*) n FROM canon.vw_Synonym WHERE ObjectCode='CLAIM_STATUS.OP' AND SynonymText=N'Pending'")["n"] == 1)

    query(con, "EXEC rules.usp_ProposeRule @RuleSet='UW_PERSONAL_AUTO', @Code='R12', @Name=N'Young driver, high symbol', @RuleType='REFERRAL', "
               "@ActionType='REFER', @ConditionsJson=N'[[\"DRIVER_AGE\",\"<\",\"25\"],[\"VEHICLE_SYMBOL\",\">=\",\"20\"]]', @RequestedBy=N'Tester A'")
    query(con, "EXEC gov.usp_DecideAll N'Tester B', 1, NULL, NULL, 'RULE'")
    fire = query(con, "EXEC rules.usp_TestRule 'R12', N'{\"DRIVER_AGE\":22,\"VEHICLE_SYMBOL\":24}'")[0][0]["Fires"]
    nofire = query(con, "EXEC rules.usp_TestRule 'R12', N'{\"DRIVER_AGE\":40,\"VEHICLE_SYMBOL\":24}'")[0][0]["Fires"]
    check("new rule approved and evaluated", fire and not nofire)

    query(con, "EXEC canon.usp_EnsureScope N'COMPANY:ACME', N'Acme Mutual'")
    query(con, "EXEC canon.usp_ProposeElement @Code='LOYALTY_TIER', @Name=N'Loyalty Tier', @Scope=N'COMPANY:ACME', @RequestedBy=N'Tester A'")
    query(con, "EXEC gov.usp_DecideAll N'Tester B', 1, NULL, NULL, NULL, N'LOYALTY_TIER'")
    check("company-specific element", one("SELECT COUNT(*) n FROM canon.vw_DataElement WHERE ElementCode='LOYALTY_TIER' AND Scope=N'COMPANY:ACME'")["n"] == 1)

    query(con, "EXEC gov.usp_RequestChange 'EXTENSION', 'ADD', N'POLICY_NUMBER', "
               "N'{\"object_type\":\"ELEMENT\",\"object_code\":\"POLICY_NUMBER\",\"name\":\"Data steward\",\"value\":\"UW operations\"}', N'Tester A'")
    query(con, "EXEC gov.usp_DecideAll N'Tester B', 1, NULL, NULL, 'EXTENSION'")
    check("extension attribute", one("SELECT COUNT(*) n FROM canon.ExtensionAttribute WHERE AttributeName=N'Data steward'")["n"] == 1)

    pend = query(con, "EXEC gov.usp_DecideAll N'Tester B', 1, NULL, NULL, 'OPTION', N'CAUSE_OF_LOSS.%'")
    check("seeded ISO 2027 cause-of-loss codes approved", one("SELECT COUNT(*) n FROM canon.vw_PickListOption WHERE PickList='CAUSE_OF_LOSS' "
                                                            "AND OptionCode IN ('WATERW','WATERN') AND BureauCodes IS NOT NULL")["n"] == 2,
          "; ".join(f"{x['Status']} {x['Requests']}" for x in pend[0]))

    scan = query(con, f"EXEC intake.usp_ScanDatabase @SourceDatabase='{demo_db}', @SourceSystem=N'Guidewire', @StartedBy=N'Tester A'")
    sr = scan[0][0]
    check("scan another database", sr["ColumnsScanned"] == 26 and sr["ElementsMatched"] >= 18,
          f"{sr['ColumnsScanned']} columns: {sr['ElementsMatched']} matched, {sr['ElementsNew']} new; values {sr['ValuesMatched']} matched, {sr['ValuesNew']} new")
    news = query(con, "SELECT SourceTable + '.' + SourceColumn AS c FROM intake.Candidate WHERE ScanRunId=? AND CandidateType='ELEMENT' AND Status='NEW'",
                 sr["ScanRunId"])[0]
    print("        new columns: " + ", ".join(sorted(x["c"] for x in news)))
    prop = query(con, "EXEC intake.usp_ProposeMissing ?, N'Tester A'", sr["ScanRunId"])
    print("        proposals: " + ", ".join(f"{x['ObjectType']} {x['ChangeType']} {x['Requests']}" for x in prop[0]))
    dec = query(con, "EXEC gov.usp_DecideAll @DecidedBy=N'Tester B', @ScanRunId=?", sr["ScanRunId"])
    failed = dec[1] if len(dec) > 1 else []
    check("approve everything the scan proposed", not failed, "; ".join(f"{x['ObjectCode']}: {x['Result']}" for x in failed[:5]))
    check("Y/N column reuses YES_NO (value fingerprint)",
          one("SELECT PickList FROM canon.vw_DataElement WHERE ElementCode='PETINJURYIND'")["PickList"] == "YES_NO")
    check("new value added to an existing pick list",
          one("SELECT COUNT(*) n FROM canon.vw_PickListOption WHERE PickList='PAYMENT_METHOD' AND OptionCode='CRYPTO'")["n"] == 1)
    scan2 = query(con, f"EXEC intake.usp_ScanDatabase @SourceDatabase='{demo_db}', @SourceSystem=N'Guidewire', @StartedBy=N'Tester A'")[0][0]
    check("second scan recognizes everything approved", scan2["ElementsNew"] == 0 and scan2["ValuesNew"] == 0,
          f"{scan2['ElementsMatched']} matched, {scan2['ElementsNew']} new elements, {scan2['ValuesNew']} new values")

    query(con, "EXEC gov.usp_RequestChange 'OPTION', 'EXPIRE', N'ROOF_SHAPE.FLAT', N'{\"picklist\":\"ROOF_SHAPE\",\"code\":\"FLAT\",\"effective_to\":\"2027-12-31\"}', N'Tester A'")
    query(con, "EXEC gov.usp_DecideAll N'Tester B', 1, NULL, NULL, 'OPTION', N'ROOF_SHAPE.FLAT'")
    hist = one("SELECT COUNT(*) n FROM canon.PickListOption FOR SYSTEM_TIME ALL o JOIN canon.PickList p ON p.PickListId=o.PickListId "
               "WHERE p.PickListCode='ROOF_SHAPE' AND o.OptionCode='FLAT'")["n"]
    check("expire, never delete, history kept", hist == 2 and one("SELECT Status FROM canon.vw_PickListOption WHERE PickList='ROOF_SHAPE' AND OptionCode='FLAT'")["Status"] == "EXPIRED")
    rule_engine_checks(server, db, con, check, one)
    coverage_checks(server, db, check, one)
    check("no requests left failed", one("SELECT COUNT(*) n FROM gov.ChangeRequest WHERE Status='FAILED'")["n"] == 0)
    con.close()
    if not keep:
        for d in (db, demo_db):
            master.cursor().execute(f"ALTER DATABASE [{d}] SET SINGLE_USER WITH ROLLBACK IMMEDIATE; DROP DATABASE [{d}];")
    master.close()
    n_ok = sum(results)
    print(f"\n{n_ok} of {len(results)} checks passed." + ("" if n_ok == len(results) else "  Please send this output to Claude."))
    return 0 if n_ok == len(results) else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--server", default=os.environ.get("SI2_MSSQL_SERVER", "SABAHOME\\SQLEXPRESS02"))
    ap.add_argument("--database", default="SI2Canonical")
    ap.add_argument("--demo", action="store_true", help="also create SI2_SourceDemo")
    ap.add_argument("--selftest", action="store_true", help="test everything on temporary databases")
    ap.add_argument("--keep", action="store_true", help="keep the self-test databases")
    a = ap.parse_args()
    if a.selftest:
        sys.exit(selftest(a.server, a.keep))
    install(a.server, a.database, a.demo)
    print("Done. Open 05_how_to.sql in SSMS to try it.")
