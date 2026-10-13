"""SI² claim check on SQL Server: read the forms on each policy, check every open claim, raise alerts.

    python check_claims.py                          check all claims in SI2Canonical (cov schema), add new alerts
    python check_claims.py --load-forms "C:\\Forms" read every PDF / TXT form in the folder into cov.Form and cov.FormSection
    python check_claims.py --server ... --database ...

The file name is the form number (e.g. "HO 00 03 05 11.pdf"); add the form to a policy in cov.PolicyForm. Windows sign-in only.
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import coverage as C  # noqa: E402

DRIVERS = ["ODBC Driver 18 for SQL Server", "ODBC Driver 17 for SQL Server", "ODBC Driver 13 for SQL Server", "SQL Server Native Client 11.0", "SQL Server"]


def connect(server: str, database: str):
    import pyodbc
    driver = next((d for d in DRIVERS if d in pyodbc.drivers()), None)
    if not driver:
        sys.exit("No SQL Server ODBC driver found.")
    return pyodbc.connect(f"DRIVER={{{driver}}};SERVER={server};DATABASE={database};Trusted_Connection=yes;TrustServerCertificate=yes;", autocommit=True)


def rows(cn, sql: str, *p) -> list[dict]:
    cur = cn.cursor()
    cur.execute(sql, *p)
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def _d(v):
    return v.isoformat() if hasattr(v, "isoformat") else (str(v) if v is not None else None)


def load(cn) -> tuple[C.FormLibrary, dict, list[dict]]:
    """Forms, policies and claims from the cov tables, in the shapes coverage.py uses."""
    lib = C.FormLibrary()
    for f in rows(cn, "SELECT FormNumber, Edition, Title, LobCode, Products, States, FormKind, FormText FROM cov.Form WHERE Status = 'ACTIVE' ORDER BY FormId"):
        lib.add({"number": f["FormNumber"], "edition": f["Edition"], "title": f["Title"], "lob": f["LobCode"], "products": (f["Products"] or "").split(","),
                 "states": [s for s in (f["States"] or "").split(",") if s], "kind": f["FormKind"], "text": f["FormText"]})
    pols = {}
    for p in rows(cn, "SELECT * FROM cov.Policy"):
        pols[p["PolicyNumber"]] = {"policy_number": p["PolicyNumber"], "product": p["ProductCode"], "lob": p["LobCode"], "state": p["StateCode"],
                                   "insured": p["InsuredName"], "effective": _d(p["EffectiveDate"]), "expiration": _d(p["ExpirationDate"]),
                                   "coverages": {}, "forms": []}
    for r in rows(cn, "SELECT * FROM cov.PolicyCoverage"):
        if r["PolicyNumber"] in pols:
            pols[r["PolicyNumber"]]["coverages"][r["CoverageCode"]] = {"limit": float(r["LimitAmount"]), "deductible": float(r["DeductibleAmount"])}
    for r in rows(cn, "SELECT * FROM cov.PolicyForm ORDER BY PolicyNumber, Seq"):
        if r["PolicyNumber"] in pols:
            pols[r["PolicyNumber"]]["forms"].append(r["FormNumber"])
    pays = {}
    for r in rows(cn, "SELECT * FROM cov.ClaimPayment ORDER BY PaymentId"):
        pays.setdefault(r["ClaimNumber"], []).append({"amount": float(r["Amount"]), "payee": r["Payee"], "payee_type": r["PayeeType"], "date": _d(r["PaymentDate"])})
    claims = []
    for c in rows(cn, "SELECT * FROM cov.Claim ORDER BY ClaimNumber"):
        f = lambda v: None if v is None else float(v)  # noqa: E731
        claims.append({"claim_number": c["ClaimNumber"], "policy_number": c["PolicyNumber"], "loss_date": _d(c["LossDate"]), "reported_date": _d(c["ReportedDate"]),
                       "cause": c["CauseCode"], "coverage": c["CoverageCode"], "description": c["LossDescription"] or "", "notes": c["Notes"] or "",
                       "adjuster": c["AdjusterName"], "recorded_limit": f(c["RecordedLimit"]), "recorded_deductible": f(c["RecordedDeductible"]),
                       "gross_loss": f(c["GrossLoss"]) or 0.0, "paid": f(c["PaidAmount"]) or 0.0, "reserve": f(c["ReserveAmount"]) or 0.0,
                       "payments": pays.get(c["ClaimNumber"], [])})
    return lib, pols, claims


def save_alerts(cn, alerts: list[dict]) -> int:
    """Add alerts that are not already open for the same claim, type and message."""
    cur = cn.cursor()
    n = 0
    for a in alerts:
        cur.execute("""INSERT cov.CoverageAlert (ClaimNumber, PolicyNumber, AlertType, Title, Severity, SendTo, CopyTo, Message, Evidence, AdjusterName)
                       SELECT ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                       WHERE NOT EXISTS (SELECT 1 FROM cov.CoverageAlert x WHERE x.ClaimNumber = ? AND x.AlertType = ? AND x.Message = ? )""",
                    a["claim"], a["policy"], a["type"], a["title"][:200], a["severity"], a["to"], a["cc"], a["message"][:1000], (a["evidence"] or "")[:2000] or None,
                    a["adjuster"], a["claim"], a["type"], a["message"][:1000])
        n += cur.rowcount
    return n


def pdf_text(path: Path) -> str:
    if path.suffix.lower() == ".pdf":
        from pypdf import PdfReader
        return "\n".join((p.extract_text() or "") for p in PdfReader(str(path)).pages)
    return path.read_text(encoding="utf-8", errors="replace")


def load_forms(cn, folder: Path, by: str) -> list[str]:
    """Read every form in the folder into cov.Form / cov.FormSection (new or changed forms only)."""
    cur = cn.cursor()
    report = []
    for path in sorted(list(folder.glob("*.pdf")) + list(folder.glob("*.txt"))):
        text = pdf_text(path).strip()
        if not text:
            report.append(f"{path.name}: no text (scanned image?) - skipped")
            continue
        number = path.stem.strip()
        first = next((ln.strip() for ln in text.splitlines() if ln.strip()), number)
        kind = "ENDORSEMENT" if "endorsement" in text[:600].lower() or "this endorsement changes" in text.lower() else "BASE"
        cur.execute("SELECT FormId FROM cov.Form WHERE FormNumber = ? AND Edition = ''", number)
        row = cur.fetchone()
        if row:
            cur.execute("UPDATE cov.Form SET FormText = ?, Title = ?, FormKind = ?, Source = ? WHERE FormId = ?", text, first[:300], kind,
                        path.suffix.upper().strip("."), row[0])
            cur.execute("DELETE FROM cov.FormSection WHERE FormId = ? AND ReviewedBy IS NULL", row[0])
            fid = row[0]
        else:
            cur.execute("INSERT cov.Form (FormNumber, Edition, Title, FormKind, Source, FormText, LoadedBy) OUTPUT inserted.FormId VALUES (?, '', ?, ?, ?, ?, ?)",
                        number, first[:300], kind, path.suffix.upper().strip("."), text, by)
            fid = cur.fetchone()[0]
        sections = C.read_form(number, text)
        for s in sections:
            cur.execute("""INSERT cov.FormSection (FormId, Seq, Heading, SectionType, Coverages, OpenPerils, CauseCodes, SectionText)
                           SELECT ?, ?, ?, ?, ?, ?, ?, ? WHERE NOT EXISTS (SELECT 1 FROM cov.FormSection z WHERE z.FormId = ? AND z.Seq = ?)""",
                        fid, s["seq"], s["heading"][:300], s["type"], ",".join(s["coverages"]) or None, 1 if s["open_perils"] else 0,
                        ",".join(sorted({c for cl in s["clauses"] for c in cl["causes"]})) or None, " ".join(c["text"] for c in s["clauses"]) or s["heading"],
                        fid, s["seq"])
        kinds = {}
        for s in sections:
            kinds[s["type"]] = kinds.get(s["type"], 0) + 1
        report.append(f"{path.name}: {kind.lower()}, {len(sections)} sections (" + ", ".join(f"{v} {k.lower()}" for k, v in sorted(kinds.items())) + ")")
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--server", default=os.environ.get("SI2_MSSQL_SERVER", "SABAHOME\\SQLEXPRESS02"))
    ap.add_argument("--database", default="SI2Canonical")
    ap.add_argument("--load-forms", help="folder with policy forms (PDF or TXT) to read")
    ap.add_argument("--by", default="SI2 claim check")
    a = ap.parse_args()
    cn = connect(a.server, a.database)
    if a.load_forms:
        for line in load_forms(cn, Path(a.load_forms), a.by):
            print("  " + line)
    lib, pols, claims = load(cn)
    alerts = C.check_all(claims, pols, lib)
    added = save_alerts(cn, alerts)
    print(f"Checked {len(claims)} claims on {len(pols)} policies with {len(lib.forms)} forms ({dt.datetime.now():%Y-%m-%d %H:%M}).")
    print(f"  {len(alerts)} findings, {added} new alerts added.")
    by_role = {}
    for x in alerts:
        by_role.setdefault(x["to"], []).append(x)
    for role, xs in sorted(by_role.items()):
        print(f"  to {role}: {len(xs)}  (" + ", ".join(sorted({x['type'] for x in xs})) + ")")
    for r in rows(cn, "SELECT TOP (8) ClaimNumber, SendTo, CopyTo, Title, Message FROM cov.vw_AlertInbox WHERE Status = 'OPEN' AND Severity = 'HIGH' ORDER BY AlertId"):
        print(f"    {r['ClaimNumber']} -> {r['SendTo']}" + (f" cc {r['CopyTo']}" if r["CopyTo"] else "") + f": {r['Title']}. {r['Message'][:140]}")
    cn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
