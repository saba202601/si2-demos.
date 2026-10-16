"""SI² Data Bridge on SI2Canonical: register each system's mappings (two-person approval), then move a legacy
extract to every destination through the canonical model.

    python run_bridge.py --register --approve-as Saba      # teach SI2Canonical the three demo systems
    python run_bridge.py --rows 200                         # run the bridge from the approved mappings
    python run_bridge.py --memory                           # no SQL Server: the mappings in memory

Output in bridge_out\\: the legacy input, the canonical records, one file per destination, lineage and issues.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import bridge as B  # noqa: E402
import bridge_systems as S  # noqa: E402

REQUESTER = "SI2 bridge"
USAGE_NOTE = "Field in a connected system (Data Bridge)"


def connect(server, database):
    import pyodbc
    drivers = ["ODBC Driver 18 for SQL Server", "ODBC Driver 17 for SQL Server", "ODBC Driver 13 for SQL Server",
               "SQL Server Native Client 11.0", "SQL Server"]
    driver = next((d for d in drivers if d in pyodbc.drivers()), None)
    if not driver:
        raise SystemExit("No SQL Server ODBC driver on this PC.")
    return pyodbc.connect(f"DRIVER={{{driver}}};SERVER={server};DATABASE={database};Trusted_Connection=yes;TrustServerCertificate=yes;",
                          autocommit=True)


def _k(*parts) -> tuple:
    return tuple(str(p).strip().upper() for p in parts)


def register(con, approve_as: str | None) -> None:
    """Propose the systems' field and value aliases that SI2Canonical does not have yet; a second person approves."""
    cur = con.cursor()
    codes = list(S.SYSTEMS)
    marks = ",".join("?" * len(codes))
    cur.execute("SELECT s.ObjectType, CASE s.ObjectType WHEN 'ELEMENT' THEN e.ElementCode ELSE p.PickListCode + '.' + o.OptionCode END, "
                "s.SynonymText, s.SourceSystem FROM canon.Synonym s LEFT JOIN canon.DataElement e ON s.ObjectType = 'ELEMENT' AND e.ElementId = s.ObjectId "
                "LEFT JOIN canon.PickListOption o ON s.ObjectType = 'OPTION' AND o.OptionId = s.ObjectId LEFT JOIN canon.PickList p ON p.PickListId = o.PickListId "
                "WHERE s.Status <> 'EXPIRED' AND s.SourceSystem IN (" + marks + ")", *codes)
    have = {_k(*r) for r in cur.fetchall()}
    cur.execute("SELECT PayloadJson FROM gov.ChangeRequest WHERE Status = 'PENDING' AND ObjectType = 'SYNONYM'")
    for (pj,) in cur.fetchall():
        try:
            j = json.loads(pj)
        except (TypeError, ValueError):
            continue
        key = j.get("object_code") if j.get("object_type") == "ELEMENT" else f"{j.get('picklist')}.{j.get('object_code')}"
        have.add(_k(j.get("object_type"), key, j.get("text"), j.get("source")))
    todo = [p for p in S.proposals() if _k(p["payload"]["object_type"], p["code"], p["payload"]["text"], p["payload"]["source"]) not in have]
    ids = []
    for p in todo:
        cur.execute("SET NOCOUNT ON; DECLARE @id int; EXEC gov.usp_RequestChange 'SYNONYM', 'ADD', ?, ?, ?, ?, 'INTAKE', NULL, @id OUTPUT; SELECT @id;",
                    p["code"][:300], json.dumps(p["payload"]), REQUESTER, p["summary"][:1000])
        ids.append(cur.fetchone()[0])
    print(f"Mappings: {len(S.proposals())} for {len(S.SYSTEMS)} systems; {len(todo)} new proposed by '{REQUESTER}'")
    if approve_as and ids:
        done, failed = 0, []
        for rid in ids:
            cur.execute("SET NOCOUNT ON; DECLARE @s varchar(10), @r nvarchar(2000); EXEC gov.usp_Decide ?, ?, 1, N'Data Bridge system mapping', 1, "
                        "@s OUTPUT, @r OUTPUT; SELECT @s, @r;", rid, approve_as)
            s, r = cur.fetchone()
            if s == "APPROVED":
                done += 1
            else:
                failed.append((rid, r))
        print(f"  approved by {approve_as}: {done}" + (f", not applied: {len(failed)}" if failed else ""))
        for rid, r in failed[:10]:
            print(f"    request {rid}: {r}")
    elif ids:
        print("  waiting for a second person: SELECT * FROM gov.vw_PendingChange WHERE RequestedBy = N'SI2 bridge';")
    # where-used: each system field is recorded against its element (the Canonical Master shows it)
    d = B.SqlDictionary(con)
    added = 0
    for s in S.SYSTEMS.values():
        for fname, el in d.fields(s.code).items():
            cur.execute("SET NOCOUNT ON; INSERT canon.ElementUsage (ElementId, UsedIn, ObjectName, FieldName, Notes, CreatedBy) "
                        "SELECT e.ElementId, ?, ?, ?, ?, ? FROM canon.DataElement e WHERE e.ElementCode = ? AND e.ScopeId = 1 AND NOT EXISTS "
                        "(SELECT 1 FROM canon.ElementUsage u WHERE u.ElementId = e.ElementId AND u.UsedIn = ? AND u.FieldName = ?); SELECT @@ROWCOUNT;",
                        s.code, s.name, fname, USAGE_NOTE, REQUESTER, el, s.code, fname)
            added += cur.fetchone()[0]
    print(f"  where-used rows added: {added}")


def write(res: B.Result, rows: list[dict], out: Path) -> None:
    out.mkdir(exist_ok=True)
    (out / "1_legacy_input.csv").write_text(B.to_csv(rows), encoding="utf-8")
    (out / "2_canonical_records.csv").write_text(B.to_csv(B.canonical_rows(res)), encoding="utf-8")
    for i, code in enumerate(res.destinations, 3):
        ext = "txt" if S.SYSTEMS[code].kind == "FIXED" else "csv"
        (out / f"{i}_{code.lower()}.{ext}").write_text(B.output_text(res, code), encoding="utf-8")
    with open(out / "lineage.csv", "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(res.lineage[0]) if res.lineage else ["Record"])
        w.writeheader()
        w.writerows(res.lineage)
    with open(out / "issues.csv", "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=["Record", "Severity", "System", "Field", "Element", "Value", "Problem"])
        w.writeheader()
        w.writerows(res.issues)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--server", default=os.environ.get("SI2_SQL_SERVER", "SABAHOME\\SQLEXPRESS02"))
    ap.add_argument("--database", default="SI2Canonical")
    ap.add_argument("--register", action="store_true", help="propose the systems' mappings in SI2Canonical")
    ap.add_argument("--approve-as", default=None, help="second person who approves the mappings")
    ap.add_argument("--rows", type=int, default=200)
    ap.add_argument("--memory", action="store_true", help="use the mappings in memory, no SQL Server")
    ap.add_argument("--out", default=str(HERE / "bridge_out"))
    a = ap.parse_args()

    if a.memory:
        d = B.MemoryDictionary()
        print("Mappings: in memory (synthetic, as if approved)")
    else:
        con = connect(a.server, a.database)
        if a.register:
            register(con, a.approve_as)
        d = B.SqlDictionary(con)
        print(f"Mappings read from {a.database} on {a.server}: " +
              ", ".join(f"{c} {len(d.fields(c))} fields" for c in S.SYSTEMS))
    rows = S.legacy_extract(a.rows)
    res = B.run(rows, S.LEGACY_PAS, S.DESTINATIONS, d)
    write(res, rows, Path(a.out))
    st = res.stats()
    print(f"\nBridge run: {S.LEGACY_PAS.name} -> canonical -> {', '.join(x.name for x in S.DESTINATIONS)}")
    for k, v in st.items():
        print(f"  {k:<16} {v:,}")
    print("  held records and why:")
    for x in res.issues:
        print(f"    {x['Severity']:<5} {x['Record']:<11} {x['System']:<11} {x['Field']:<9} {x['Problem']}")
    if res.lineage:
        r = next(x for x in res.lineage if x["Element"] == "CONSTRUCTION")
        print(f"\nOne value end to end ({r['Record']}): {r['Source field']}='{r['Source value']}' -> {r['Element']} {r['Canonical value']} "
              f"-> {r['Destination']}.{r['Destination field']}='{r['Destination value']}'  ({r['Source to canonical']}; {r['Canonical to destination']})")
    print(f"\nFiles: {a.out}")
    ok = st["passed"] > 0 and all(st[f"to {c}"] == st["passed"] for c in res.destinations)
    print("Bridge OK" if ok else "Bridge: some records did not reach every destination (see issues.csv)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
