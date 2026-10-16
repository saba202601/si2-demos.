"""Print the Party / commercial application model as it is in SI2Canonical, and save it to a CSV for review.

    python show_entity_model.py [--server ...] [--database SI2Canonical]
"""
import argparse
import csv
import datetime as dt
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import check_claims as K  # noqa: E402  (connect / rows helpers)

ap = argparse.ArgumentParser()
ap.add_argument("--server", default=os.environ.get("SI2_MSSQL_SERVER", "SABAHOME\\SQLEXPRESS02"))
ap.add_argument("--database", default="SI2Canonical")
a = ap.parse_args()
cn = K.connect(a.server, a.database)
rows = K.rows(cn, "SELECT * FROM canon.vw_EntityModel ORDER BY SortOrder, Seq")
by = {}
for r in rows:
    by.setdefault((r["SortOrder"], r["Entity"], r["EntityName"], r["ParentEntity"]), []).append(r)
print(f"Commercial application model in {a.database}: {len(by)} entities, {len(rows)} entity elements")
for (_, ent, name, parent), rs in sorted(by.items()):
    missing = [r["ModelCode"] for r in rs if r["InMaster"] == "NOT YET"]
    reused = [f"{r['ModelCode']}={r['ElementCode']}" for r in rs if r["InMaster"].startswith("IN MODEL AS")]
    print(f"  {ent:<22} {name:<30} {len(rs):>3} elements" + (f"  under {parent}" if parent else "")
          + (f"  NOT YET: {', '.join(missing)}" if missing else "") + (f"  (already in the master as {', '.join(reused)})" if reused else ""))
out = HERE / f"party_model_{dt.datetime.now():%Y%m%d_%H%M}.csv"
with open(out, "w", newline="", encoding="utf-8-sig") as fh:
    w = csv.writer(fh)
    w.writerow(["Entity", "Entity name", "Parent", "Seq", "Element", "Element name", "Data type", "Pick list", "Subject area", "Personal data", "In master"])
    for r in rows:
        w.writerow([r["Entity"], r["EntityName"], r["ParentEntity"], r["Seq"], r["ElementCode"] or r["ModelCode"], r["ElementName"], r["DataType"],
                    r["PickList"], r["SubjectArea"], "Y" if r["IsPII"] else "", r["InMaster"]])
print(f"Saved: {out}")
