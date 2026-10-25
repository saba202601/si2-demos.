"""Tables for Financial Reporting, on SQLite (online demo) or SQL Server (SI² Studio on your PC).

One table definition produces both dialects:

    SQLite      tables fin_<name> in data/finance.db
    SQL Server  schema [fin] in SI2Canonical (SI2_SQL_SERVER / SI2_SQL_DATABASE, Windows authentication)

Set SI2_FIN_BACKEND=sqlite to force SQLite on the desktop.

    python -m finance.db --ddl mssql > finance/sql/01_create_fin.sql      # regenerate the SQL Server script
    python -m finance.install                                            # create, load the Yellow Book and the demo source
"""
from __future__ import annotations

import os
import sqlite3
import sys
from datetime import date, datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SQLITE_PATH = Path(os.environ.get("SI2_FIN_DB", ROOT / "data" / "finance.db"))
DRIVERS = ["ODBC Driver 18 for SQL Server", "ODBC Driver 17 for SQL Server", "ODBC Driver 13 for SQL Server",
           "SQL Server Native Client 11.0", "SQL Server"]

# name: (columns [(column, type, nullable)], primary key)
#   types: code(n) short text, text long text, int, money, num, date, ts
TABLES = {
    # ---- the Yellow Book (metadata)
    "YbPage": ([("page_code", "code(12)", 0), ("page_name", "code(200)", 0), ("page_ref", "code(40)", 0),
                ("page_group", "code(60)", 0), ("line_count", "int", 1), ("col_count", "int", 1), ("field_count", "int", 1),
                ("source", "code(40)", 0)], ["page_code"]),
    "YbLine": ([("page_code", "code(12)", 0), ("line_no", "code(12)", 0), ("seq", "int", 0), ("caption", "code(400)", 0),
                ("line_kind", "code(1)", 0)], ["page_code", "line_no"]),
    "YbColumn": ([("page_code", "code(12)", 0), ("col_no", "code(4)", 0), ("seq", "int", 0), ("caption", "code(200)", 0)],
                 ["page_code", "col_no"]),
    "YbField": ([("field_id", "code(40)", 0), ("page_code", "code(12)", 0), ("line_no", "code(12)", 0), ("col_no", "code(4)", 0),
                 ("data_type", "code(10)", 0), ("source", "code(40)", 0), ("concept_id", "code(60)", 1),
                 ("dimensions", "code(200)", 1)], ["field_id"]),
    "YbAslLine": ([("asl_code", "code(6)", 0), ("asl_name", "code(120)", 0), ("sched_p_line", "code(4)", 1)], ["asl_code"]),
    # ---- the ontology
    "OntConcept": ([("concept_id", "code(60)", 0), ("label", "code(200)", 0), ("parent_id", "code(60)", 1),
                    ("kind", "code(20)", 0), ("definition", "text", 1), ("canonical_element", "code(60)", 1)], ["concept_id"]),
    "OntRelation": ([("subject_id", "code(60)", 0), ("predicate", "code(40)", 0), ("object_id", "code(60)", 0),
                     ("note", "code(400)", 1)], ["subject_id", "predicate", "object_id"]),
    # ---- the connected source (one table per feed)
    "SrcPremiumTxn": ([("policy_id", "code(30)", 0), ("asl_code", "code(6)", 0), ("state", "code(4)", 0), ("eff_date", "date", 0),
                       ("exp_date", "date", 0), ("written_year", "int", 0), ("basis", "code(1)", 0), ("affiliate", "int", 0),
                       ("written", "money", 0)], []),
    "SrcGlPremium": ([("asl_code", "code(6)", 0), ("basis", "code(1)", 0), ("affiliate", "int", 0), ("written", "money", 0),
                      ("gl_account", "code(10)", 0)], []),
    "SrcClaimTxn": ([("claim_id", "code(30)", 1), ("asl_code", "code(6)", 0), ("state", "code(4)", 0), ("accident_year", "int", 0),
                     ("calendar_year", "int", 0), ("pay_type", "code(8)", 0), ("amount", "money", 0), ("ceded_pct", "num", 0)], []),
    "SrcClaimReserve": ([("claim_id", "code(30)", 0), ("asl_code", "code(6)", 0), ("state", "code(4)", 0), ("accident_year", "int", 0),
                         ("valuation_year", "int", 0), ("case_loss", "money", 0), ("case_dcc", "money", 0), ("ceded_pct", "num", 0),
                         ("closed", "int", 0), ("closed_without_payment", "int", 0)], []),
    "SrcIbnr": ([("asl_code", "code(6)", 0), ("accident_year", "int", 0), ("valuation_year", "int", 0), ("ibnr_loss", "money", 0),
                 ("ibnr_dcc", "money", 0), ("ao_unpaid", "money", 0), ("ceded_pct", "num", 0)], []),
    "SrcExpense": ([("part3_line", "code(6)", 0), ("amount", "money", 0), ("lae_share", "num", 0), ("uw_share", "num", 0),
                    ("inv_share", "num", 0)], ["part3_line"]),
    "SrcGlBalance": ([("account", "code(10)", 0), ("account_name", "code(120)", 0), ("statement_line", "code(12)", 0),
                      ("balance_cy", "money", 0), ("balance_py", "money", 0), ("nonadmitted_cy", "money", 0)], ["account"]),
    "SrcInvestment": ([("nii_line", "code(6)", 0), ("collected", "money", 0), ("earned", "money", 0)], ["nii_line"]),
    "SrcReinsurer": ([("reinsurer_id", "code(12)", 0), ("naic_code", "code(10)", 0), ("name", "code(120)", 0),
                      ("domicile", "code(6)", 0), ("program", "code(6)", 0), ("share", "num", 0)], ["reinsurer_id"]),
    # ---- generated statements
    "StatementRun": ([("run_id", "code(20)", 0), ("company", "code(120)", 0), ("statement_year", "int", 0), ("source", "code(60)", 0),
                      ("created_by", "code(60)", 0), ("created_at", "ts", 0), ("status", "code(20)", 0), ("approved_by", "code(60)", 1),
                      ("approved_at", "ts", 1), ("edits_failed", "int", 0), ("values_count", "int", 0)], ["run_id"]),
    "StatementValue": ([("run_id", "code(20)", 0), ("field_id", "code(40)", 0), ("dim", "code(20)", 0), ("value_num", "money", 1),
                        ("value_text", "code(200)", 1)], ["run_id", "field_id", "dim"]),
    "EditResult": ([("run_id", "code(20)", 0), ("edit_id", "code(8)", 0), ("edit_name", "code(200)", 0), ("expected", "money", 1),
                    ("actual", "money", 1), ("difference", "money", 1), ("result", "code(6)", 0)], ["run_id", "edit_id"]),
}
FEED_TABLE = {"premium_txn": "SrcPremiumTxn", "gl_premium": "SrcGlPremium", "claim_txn": "SrcClaimTxn",
              "claim_reserve": "SrcClaimReserve", "ibnr": "SrcIbnr", "expense_ledger": "SrcExpense", "gl_balance": "SrcGlBalance",
              "investment": "SrcInvestment", "reinsurer": "SrcReinsurer"}
SQLITE_T = {"int": "INTEGER", "money": "REAL", "num": "REAL", "date": "TEXT", "ts": "TEXT", "text": "TEXT"}
MSSQL_T = {"int": "INT", "money": "DECIMAL(19,2)", "num": "DECIMAL(9,6)", "date": "DATE", "ts": "DATETIME2(0)", "text": "NVARCHAR(MAX)"}


def _type(t: str, dialect: str) -> str:
    if t.startswith("code("):
        n = t[5:-1]
        return "TEXT" if dialect == "sqlite" else f"NVARCHAR({n})"
    return (SQLITE_T if dialect == "sqlite" else MSSQL_T)[t]


def tname(name: str, dialect: str) -> str:
    return f"fin_{name}" if dialect == "sqlite" else f"fin.{name}"


def ddl(dialect: str = "sqlite") -> str:
    out = []
    if dialect == "mssql":
        out.append("-- SI² Financial Reporting (NAIC P&C Annual Statement) on SQL Server: schema [fin] in SI2Canonical.\n"
                   "-- Generated by finance/db.py. Safe to run again: existing tables are kept.\n"
                   "IF SCHEMA_ID(N'fin') IS NULL EXEC(N'CREATE SCHEMA fin');\nGO")
    for name, (cols, pk) in TABLES.items():
        body = [f"    {c} {_type(t, dialect)}{'' if nul else ' NOT NULL'}" for c, t, nul in cols]
        if pk:
            body.append(f"    CONSTRAINT PK_fin_{name} PRIMARY KEY ({', '.join(pk)})")
        create = f"CREATE TABLE {tname(name, dialect)} (\n" + ",\n".join(body) + "\n)"
        if dialect == "mssql":
            out.append(f"IF OBJECT_ID(N'fin.{name}', N'U') IS NULL\n{create};\nGO")
        else:
            out.append(create.replace("CREATE TABLE", "CREATE TABLE IF NOT EXISTS", 1) + ";")
    if dialect == "mssql":
        out.append("""IF OBJECT_ID(N'fin.vw_YellowBook', N'V') IS NOT NULL DROP VIEW fin.vw_YellowBook;
GO
CREATE VIEW fin.vw_YellowBook AS
SELECT r.run_id, r.company, r.statement_year, p.page_ref, p.page_name, l.line_no, l.caption AS line_caption,
       c.col_no, c.caption AS col_caption, v.dim, v.value_num, v.value_text, f.concept_id, f.source
FROM fin.StatementValue v
JOIN fin.StatementRun r ON r.run_id = v.run_id
JOIN fin.YbField f ON f.field_id = v.field_id
JOIN fin.YbPage p ON p.page_code = f.page_code
JOIN fin.YbLine l ON l.page_code = f.page_code AND l.line_no = f.line_no
JOIN fin.YbColumn c ON c.page_code = f.page_code AND c.col_no = f.col_no;
GO""")
    return "\n\n".join(out) + "\n"


# ------------------------------------------------------------------------------------------ connections
def backend() -> str:
    forced = os.environ.get("SI2_FIN_BACKEND", "").strip().lower()
    if forced in ("sqlite", "mssql"):
        return forced
    return "mssql" if os.environ.get("SI2_SQL_SERVER", "").strip() else "sqlite"


class Db:
    """Small wrapper: same calls on SQLite and SQL Server."""

    def __init__(self, dialect: str | None = None):
        self.dialect = dialect or backend()
        if self.dialect == "mssql":
            import pyodbc
            driver = next((d for d in DRIVERS if d in pyodbc.drivers()), None)
            if not driver:
                raise RuntimeError("No SQL Server ODBC driver on this PC (install ODBC Driver 18 for SQL Server).")
            self.server = os.environ.get("SI2_SQL_SERVER", "").strip()
            self.database = os.environ.get("SI2_SQL_DATABASE", "SI2Canonical").strip()
            self.cn = pyodbc.connect(f"DRIVER={{{driver}}};SERVER={self.server};DATABASE={self.database};"
                                     "Trusted_Connection=yes;TrustServerCertificate=yes;", autocommit=False)
        else:
            SQLITE_PATH.parent.mkdir(parents=True, exist_ok=True)
            self.server, self.database = "", str(SQLITE_PATH)
            self.cn = sqlite3.connect(str(SQLITE_PATH), check_same_thread=False)

    def describe(self) -> str:
        return f"SQL Server {self.server} / {self.database} (schema fin)" if self.dialect == "mssql" else "SQLite (data/finance.db)"

    def t(self, name: str) -> str:
        return tname(name, self.dialect)

    def create(self) -> None:
        cur = self.cn.cursor()
        for stmt in ddl(self.dialect).split("\nGO" if self.dialect == "mssql" else ";\n"):
            sql = stmt.strip().rstrip(";").strip()
            if sql:
                cur.execute(sql)
        self.cn.commit()

    def exists(self) -> bool:
        try:
            self.q(f"SELECT COUNT(*) AS n FROM {self.t('YbField')}")
            return True
        except Exception:
            self.cn.rollback()
            return False

    def q(self, sql: str, params=()) -> pd.DataFrame:
        cur = self.cn.cursor()
        cur.execute(sql, tuple(params))
        cols = [d[0] for d in cur.description]
        return pd.DataFrame.from_records([tuple(r) for r in cur.fetchall()], columns=cols)

    def replace(self, name: str, df: pd.DataFrame, where: str = "", params=()) -> int:
        """Delete (all rows, or those matching `where`) and insert the frame. Columns follow the table definition."""
        cols = [c for c, _t, _n in TABLES[name][0]]
        cur = self.cn.cursor()
        cur.execute(f"DELETE FROM {self.t(name)}" + (f" WHERE {where}" if where else ""), tuple(params))
        data = df.reindex(columns=cols)
        rows = [tuple(_py(v) for v in r) for r in data.itertuples(index=False)]
        if rows:
            sql = f"INSERT INTO {self.t(name)} ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})"
            if self.dialect == "mssql":
                cur.fast_executemany = True
                for i in range(0, len(rows), 20000):
                    cur.executemany(sql, rows[i:i + 20000])
            else:
                cur.executemany(sql, rows)
        self.cn.commit()
        return len(rows)

    def counts(self) -> pd.DataFrame:
        out = []
        for name in TABLES:
            try:
                n = int(self.q(f"SELECT COUNT(*) AS n FROM {self.t(name)}").iloc[0, 0])
            except Exception:
                self.cn.rollback()
                n = None
            out.append({"table": self.t(name), "rows": n})
        return pd.DataFrame(out)


def _py(v):
    if v is None:
        return None
    if isinstance(v, float) and pd.isna(v):
        return None
    if hasattr(v, "item"):
        v = v.item()
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    return v


# ------------------------------------------------------------------------------------------ load and read
def load_catalog(db: Db, concepts: pd.DataFrame | None = None, relations: pd.DataFrame | None = None,
                 field_concepts: pd.DataFrame | None = None) -> dict:
    from . import blank as B
    f = B.fields()
    if field_concepts is not None:
        f = f.merge(field_concepts, on="field_id", how="left")
    n = {"YbPage": db.replace("YbPage", B.pages()), "YbLine": db.replace("YbLine", B.lines()),
         "YbColumn": db.replace("YbColumn", B.columns()), "YbField": db.replace("YbField", f),
         "YbAslLine": db.replace("YbAslLine", B.asl())}
    if concepts is not None:
        n["OntConcept"] = db.replace("OntConcept", concepts)
    if relations is not None:
        n["OntRelation"] = db.replace("OntRelation", relations.drop_duplicates(["subject_id", "predicate", "object_id"]))
    return n


def load_source(db: Db, src: dict) -> dict:
    return {FEED_TABLE[k]: db.replace(FEED_TABLE[k], src[k]) for k in FEED_TABLE}


def read_source(db: Db, base: dict) -> dict:
    """Connect: read every feed from the database (fin.Src* tables, or your own views with the same columns)."""
    src = dict(base)
    for feed, name in FEED_TABLE.items():
        df = db.q(f"SELECT * FROM {db.t(name)}")
        for c in ("eff_date", "exp_date"):
            if c in df:
                df[c] = pd.to_datetime(df[c]).dt.date
        for c in df.columns:
            if df[c].dtype == object and c not in ("eff_date", "exp_date"):
                try:
                    df[c] = pd.to_numeric(df[c]) if c in ("written", "amount", "ceded_pct", "case_loss", "case_dcc", "ibnr_loss",
                                                         "ibnr_dcc", "ao_unpaid", "balance_cy", "balance_py", "nonadmitted_cy",
                                                         "collected", "earned", "share", "lae_share", "uw_share", "inv_share") else df[c]
                except (TypeError, ValueError):
                    pass
        if df.empty:
            raise ValueError(f"{db.t(name)} is empty: load the source first")
        src[feed] = df
    return src


def save_run(db: Db, run_id: str, stmt, edits: pd.DataFrame, meta: dict) -> int:
    vals = pd.DataFrame([{"run_id": run_id, "field_id": k, "dim": d,
                          "value_num": round(v, 2) if isinstance(v, (int, float)) else None,
                          "value_text": v if isinstance(v, str) else None} for (k, d), v in stmt.values.items()])
    db.replace("StatementValue", vals, "run_id = ?", (run_id,))
    db.replace("EditResult", edits.assign(run_id=run_id).rename(columns={"edit": "edit_name"}), "run_id = ?", (run_id,))
    run = pd.DataFrame([{**meta, "run_id": run_id, "edits_failed": int((edits.result != "PASS").sum()), "values_count": len(vals)}])
    db.replace("StatementRun", run, "run_id = ?", (run_id,))
    return len(vals)


def set_status(db: Db, run_id: str, status: str, actor: str) -> None:
    cur = db.cn.cursor()
    cur.execute(f"UPDATE {db.t('StatementRun')} SET status = ?, approved_by = ?, approved_at = ? WHERE run_id = ?",
                (status, actor, datetime.now().isoformat(timespec="seconds"), run_id))
    db.cn.commit()


if __name__ == "__main__":
    if "--ddl" in sys.argv:
        print(ddl(sys.argv[sys.argv.index("--ddl") + 1]))
