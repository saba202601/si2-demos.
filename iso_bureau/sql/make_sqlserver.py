"""Generate SQL Server Express scripts from the engine schema and the seeded database.

    python iso_bureau/sql/make_sqlserver.py

Writes:
  sql/01_create_ISOBureauReporting.sql   database + tables (+ indexes)
  sql/02_load_metadata.sql            every metadata row (layouts, canonical, pick lists, rules, approvals)
  sql/03_load_sample_source.sql       sample Guidewire / Duck Creek source transactions
Run them in SSMS against SABAHOME\\SQLEXPRESS02 (Windows Authentication) in order.
"""
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent  # repo root
sys.path.insert(0, str(ROOT))
from iso_bureau import db  # noqa: E402

OUT = Path(__file__).resolve().parent
WIDE = {"business_description", "bureau_description", "expression_json", "payload_json", "canonical_json", "messages_json",
        "file_text", "notes", "comment", "message", "record_text", "source_file"}


def col_type(name, decl):
    d = decl.upper()
    if "INTEGER PRIMARY KEY AUTOINCREMENT" in d:
        return "INT IDENTITY(1,1) PRIMARY KEY"
    if d.startswith("INTEGER"):
        rest = decl[len("INTEGER"):]
        rest = re.sub(r"REFERENCES (\w+)\((\w+)\)", r"REFERENCES dbo.\1(\2)", rest)
        return "INT" + rest
    if d.startswith("REAL"):
        return "DECIMAL(18,2)" + decl[4:]
    if d.startswith("TEXT"):
        rest = decl[4:]
        rest = rest.replace("DEFAULT (datetime('now'))", "DEFAULT SYSDATETIME()")
        if name in ("created_at", "approved_at", "at", "loaded_at", "submitted_at", "response_at", "closed_at", "sme_approved_at"):
            return "DATETIME2(0)" + rest
        if name in ("eff_date", "exp_date", "accounting_date", "period_start", "period_end"):
            return "DATE" + rest
        size = "MAX" if name in WIDE else ("1000" if name.endswith("_name") or name == "alias_name" else "100")
        if "PRIMARY KEY" in rest.upper():
            size = "20"
        return f"NVARCHAR({size})" + rest
    return decl


def ddl():
    out = ["-- SI² ISO Bureau Reporting - SQL Server Express DDL (generated from engine/db.py)",
           "IF DB_ID('ISOBureauReporting') IS NULL CREATE DATABASE ISOBureauReporting;", "GO", "USE ISOBureauReporting;", "GO"]
    for m in re.finditer(r"CREATE TABLE IF NOT EXISTS (\w+) \((.*?)\);", db.SCHEMA, re.S):
        name, body = m.group(1), m.group(2)
        body = "\n".join(re.sub(r"--.*", "", ln) for ln in body.splitlines())
        parts, depth, cur = [], 0, ""
        for ch in body:
            depth += ch == "("
            depth -= ch == ")"
            if ch == "," and depth == 0:
                parts.append(cur); cur = ""
            else:
                cur += ch
        parts.append(cur)
        cols = []
        for part in (" ".join(p.split()) for p in parts):
            if part:
                cn, decl = part.split(None, 1)
                cols.append(f"    {cn} {col_type(cn, decl)}")
        out += [f"IF OBJECT_ID('dbo.{name}') IS NULL", f"CREATE TABLE dbo.{name} (", ",\n".join(cols), ");", "GO"]
    for t in db.META_TABLES:
        out.append(f"CREATE INDEX IX_{t}_status_eff ON dbo.{t}(status, eff_date, exp_date);")
    out += ["CREATE INDEX IX_layout_field_layout ON dbo.layout_field(layout_id, seq);",
            "CREATE INDEX IX_source_txn_period ON dbo.source_transaction(lob_code, record_type, accounting_date);",
            "CREATE INDEX IX_submission_record_batch ON dbo.submission_record(batch_id, status);", "GO"]
    return "\n".join(out) + "\n"


def lit(v):
    if v is None:
        return "NULL"
    if isinstance(v, (int, float)):
        return str(v)
    return "N'" + str(v).replace("'", "''") + "'"


def inserts(con, tables):
    out = ["USE ISOBureauReporting;", "GO", "SET NOCOUNT ON;"]
    for t in tables:
        rows = con.execute(f"SELECT * FROM {t}").fetchall()
        if not rows:
            continue
        cols = rows[0].keys()
        ident = cols[0].endswith("_id") and t not in ("bureau", "line_of_business")
        if ident:
            out.append(f"SET IDENTITY_INSERT dbo.{t} ON;")
        for r in rows:
            out.append(f"INSERT INTO dbo.{t} ({', '.join(cols)}) VALUES ({', '.join(lit(r[c]) for c in cols)});")
        if ident:
            out.append(f"SET IDENTITY_INSERT dbo.{t} OFF;")
        out.append("GO")
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else db.DEFAULT_DB
    con = sqlite3.connect(src)
    con.row_factory = sqlite3.Row
    (OUT / "01_create_ISOBureauReporting.sql").write_text(ddl(), encoding="utf-8")
    meta = ["bureau", "line_of_business"] + list(db.META_TABLES) + ["approval_log"]
    (OUT / "02_load_metadata.sql").write_text(inserts(con, meta), encoding="utf-8")
    (OUT / "03_load_sample_source.sql").write_text(inserts(con, ["source_transaction"]), encoding="utf-8")
    print("written to", OUT)
