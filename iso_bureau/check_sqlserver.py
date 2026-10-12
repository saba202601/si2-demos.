"""Check the SQL Server connection used by the ISO Bureau app.

    set SI2_BUREAU_BACKEND=mssql
    python -m iso_bureau.check_sqlserver
"""
import os
import sys

os.environ.setdefault("SI2_BUREAU_BACKEND", "mssql")

from iso_bureau import db, engine as E  # noqa: E402


def main() -> int:
    try:
        con = db.connect()
    except Exception as ex:  # noqa: BLE001
        print("Could not connect:", ex)
        return 1
    print("Connected:", db.describe(con), "| driver:", getattr(con, "driver", "sqlite"))
    for t in ("layout_version", "layout_field", "canonical_element", "picklist_option",
              "bureau_code_map", "business_rule", "source_transaction", "submission_batch"):
        print(f"  {t:<20} {db.one(con, f'SELECT COUNT(*) n FROM {t}')['n']:>6} rows")
    start, end = E.period_bounds("QUARTERLY", 2026, 3)
    issues = E.readiness(con, "ISO", "HO", "PREMIUM", end)
    print("Readiness HO premium Q3 2026:", "OK" if not issues else issues)
    lay, fields = E.resolve_layout(con, "ISO", "HO", "PREMIUM", end)
    print(f"Layout v{lay['version_no']} with {len(fields)} fields; positions OK: {not E.layout_problems(fields)}")
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
