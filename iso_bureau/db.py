"""Storage for the SI² ISO Bureau Reporting module.

Runs on SQLite for the demo / Streamlit Cloud; the same tables are created on
SQL Server Express by sql/sqlserver_ddl.sql (database BureauReporting).

Audit principle (AGI-INS rule): business content is never updated or deleted.
To change something, the old row is expired (exp_date set to the day before the
new row's eff_date) and a new row is inserted. The only column the engine
updates in place is the workflow `status` (PENDING -> APPROVED / REJECTED),
and every such change is written to approval_log.
"""
from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parent / "data" / "bureau_reporting.db"
OPEN_END = "9999-12-31"

# Common effective-dated / approval columns appended to every metadata table.
_META = """
    eff_date      TEXT NOT NULL,
    exp_date      TEXT NOT NULL DEFAULT '9999-12-31',
    status        TEXT NOT NULL DEFAULT 'PENDING',   -- PENDING | APPROVED | REJECTED
    created_by    TEXT NOT NULL DEFAULT 'system',
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    approved_by   TEXT,
    approved_at   TEXT,
    supersedes_id INTEGER,                           -- row this one replaces (expired on approval)
    notes         TEXT
"""

SCHEMA = f"""
CREATE TABLE IF NOT EXISTS bureau (
    bureau_code TEXT PRIMARY KEY, bureau_name TEXT NOT NULL, code_basis TEXT NOT NULL DEFAULT 'POLICY_EFF');
CREATE TABLE IF NOT EXISTS line_of_business (
    lob_code TEXT PRIMARY KEY, lob_name TEXT NOT NULL, lob_family TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS canonical_element (
    element_id INTEGER PRIMARY KEY AUTOINCREMENT,
    element_code TEXT NOT NULL, element_name TEXT NOT NULL,
    business_description TEXT NOT NULL, data_type TEXT NOT NULL,
    picklist_code TEXT, {_META});
CREATE TABLE IF NOT EXISTS element_alias (
    alias_id INTEGER PRIMARY KEY AUTOINCREMENT,
    element_code TEXT NOT NULL, alias_name TEXT NOT NULL, alias_context TEXT NOT NULL, {_META});
CREATE TABLE IF NOT EXISTS source_mapping (
    source_map_id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_system TEXT NOT NULL, source_entity TEXT NOT NULL, source_attribute TEXT NOT NULL,
    source_data_type TEXT, element_code TEXT NOT NULL, {_META});

CREATE TABLE IF NOT EXISTS picklist (
    picklist_id INTEGER PRIMARY KEY AUTOINCREMENT,
    picklist_code TEXT NOT NULL, picklist_name TEXT NOT NULL, business_description TEXT, {_META});
CREATE TABLE IF NOT EXISTS picklist_alias (
    alias_id INTEGER PRIMARY KEY AUTOINCREMENT,
    picklist_code TEXT NOT NULL, alias_name TEXT NOT NULL, alias_context TEXT NOT NULL, {_META});
CREATE TABLE IF NOT EXISTS picklist_option (
    option_id INTEGER PRIMARY KEY AUTOINCREMENT,
    picklist_code TEXT NOT NULL, lob_scope TEXT NOT NULL DEFAULT '*',
    option_code TEXT NOT NULL, option_name TEXT NOT NULL, business_description TEXT, {_META});
CREATE TABLE IF NOT EXISTS picklist_option_alias (
    alias_id INTEGER PRIMARY KEY AUTOINCREMENT,
    picklist_code TEXT NOT NULL, option_code TEXT NOT NULL,
    source_system TEXT NOT NULL, source_value TEXT NOT NULL, {_META});
CREATE TABLE IF NOT EXISTS bureau_code_map (
    code_map_id INTEGER PRIMARY KEY AUTOINCREMENT,
    bureau_code TEXT NOT NULL, lob_scope TEXT NOT NULL DEFAULT '*',
    picklist_code TEXT NOT NULL, option_code TEXT NOT NULL, bureau_value TEXT NOT NULL, {_META});

CREATE TABLE IF NOT EXISTS layout_version (
    layout_id INTEGER PRIMARY KEY AUTOINCREMENT,
    bureau_code TEXT NOT NULL, lob_code TEXT NOT NULL, record_type TEXT NOT NULL,
    version_no INTEGER NOT NULL, record_length INTEGER NOT NULL DEFAULT 150,
    source_file TEXT, {_META});
CREATE TABLE IF NOT EXISTS layout_field (
    field_id INTEGER PRIMARY KEY AUTOINCREMENT,
    layout_id INTEGER NOT NULL REFERENCES layout_version(layout_id),
    seq INTEGER NOT NULL, bureau_field_name TEXT NOT NULL,
    start_pos INTEGER NOT NULL, length INTEGER NOT NULL, field_format TEXT NOT NULL,
    required TEXT NOT NULL DEFAULT 'Y', element_code TEXT NOT NULL,
    transform_rule_code TEXT NOT NULL, bureau_description TEXT, business_description TEXT, {_META});

CREATE TABLE IF NOT EXISTS business_rule (
    rule_id INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_code TEXT NOT NULL, rule_name TEXT NOT NULL,
    rule_category TEXT NOT NULL,            -- VALIDATION | DERIVATION | TRANSFORMATION
    bureau_code TEXT NOT NULL DEFAULT 'ISO', lob_scope TEXT NOT NULL DEFAULT '*',
    record_type_scope TEXT NOT NULL DEFAULT '*', state_scope TEXT NOT NULL DEFAULT '*',
    element_code TEXT, expression_json TEXT NOT NULL,
    severity TEXT NOT NULL DEFAULT 'ERROR', message TEXT, business_description TEXT, {_META});

CREATE TABLE IF NOT EXISTS approval_log (
    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
    object_table TEXT NOT NULL, object_id INTEGER NOT NULL, action TEXT NOT NULL,
    actor TEXT NOT NULL, comment TEXT, at TEXT NOT NULL DEFAULT (datetime('now')));

CREATE TABLE IF NOT EXISTS source_transaction (
    txn_id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_system TEXT NOT NULL, source_txn_key TEXT NOT NULL, record_type TEXT NOT NULL,
    lob_code TEXT NOT NULL, accounting_date TEXT NOT NULL, payload_json TEXT NOT NULL,
    corrects_txn_id INTEGER, corrected_by TEXT, correction_note TEXT,
    loaded_at TEXT NOT NULL DEFAULT (datetime('now')));

CREATE TABLE IF NOT EXISTS submission_batch (
    batch_id INTEGER PRIMARY KEY AUTOINCREMENT,
    bureau_code TEXT NOT NULL, lob_code TEXT NOT NULL, record_type TEXT NOT NULL,
    period_type TEXT NOT NULL, period_start TEXT NOT NULL, period_end TEXT NOT NULL,
    layout_id INTEGER, status TEXT NOT NULL,
    record_count INTEGER DEFAULT 0, valid_count INTEGER DEFAULT 0,
    error_count INTEGER DEFAULT 0, warning_count INTEGER DEFAULT 0,
    total_premium REAL DEFAULT 0, total_paid REAL DEFAULT 0,
    total_outstanding REAL DEFAULT 0, total_alae REAL DEFAULT 0,
    file_name TEXT, file_text TEXT, parent_batch_id INTEGER,
    created_by TEXT, created_at TEXT NOT NULL DEFAULT (datetime('now')),
    sme_approved_by TEXT, sme_approved_at TEXT, submitted_at TEXT, response_at TEXT, closed_at TEXT);
CREATE TABLE IF NOT EXISTS submission_record (
    rec_id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id INTEGER NOT NULL REFERENCES submission_batch(batch_id),
    txn_id INTEGER NOT NULL, line_no INTEGER, record_text TEXT,
    canonical_json TEXT, status TEXT NOT NULL, messages_json TEXT);
CREATE TABLE IF NOT EXISTS batch_event (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id INTEGER NOT NULL, status_from TEXT, status_to TEXT NOT NULL,
    actor TEXT, comment TEXT, at TEXT NOT NULL DEFAULT (datetime('now')));
"""

# Tables that follow the effective-dated + approval pattern, with their key column.
META_TABLES = {
    "canonical_element": "element_id",
    "element_alias": "alias_id",
    "source_mapping": "source_map_id",
    "picklist": "picklist_id",
    "picklist_alias": "alias_id",
    "picklist_option": "option_id",
    "picklist_option_alias": "alias_id",
    "bureau_code_map": "code_map_id",
    "layout_version": "layout_id",
    "layout_field": "field_id",
    "business_rule": "rule_id",
}


# ------------------------------------------------------------------ backends
# SQLite (default, used by the online demo) or SQL Server Express on the desktop:
#   set SI2_BUREAU_BACKEND=mssql
#   optional: SI2_MSSQL_SERVER (default SABAHOME\\SQLEXPRESS02), SI2_MSSQL_DATABASE (default ISOBureauReporting)
# SQL Server uses Windows Authentication (Trusted_Connection), like the AGI-INS rule engine.
DEFAULT_SERVER = "SABAHOME\\SQLEXPRESS02"
DEFAULT_DATABASE = "ISOBureauReporting"
DRIVER_PREFERENCE = (
    "ODBC Driver 18 for SQL Server",
    "ODBC Driver 17 for SQL Server",
    "ODBC Driver 13 for SQL Server",
    "SQL Server Native Client 11.0",
    "SQL Server",
)
# identity column of every table (used to return the new key after an INSERT on SQL Server)
IDENTITY = {**META_TABLES, "approval_log": "log_id", "source_transaction": "txn_id",
            "submission_batch": "batch_id", "submission_record": "rec_id", "batch_event": "event_id"}


def backend() -> str:
    return os.environ.get("SI2_BUREAU_BACKEND", "sqlite").strip().lower()


class _Row(dict):
    """dict row that also supports row[0] like sqlite3.Row / pyodbc.Row."""

    def __getitem__(self, k):
        if isinstance(k, int):
            return list(self.values())[k]
        return dict.__getitem__(self, k)


def _py(v):
    # keep values identical to the SQLite backend: ISO strings for dates, floats for money
    if isinstance(v, datetime):
        return v.isoformat(sep=" ", timespec="seconds")
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, Decimal):
        return float(v)
    return v


class _Cursor:
    def __init__(self, cur):
        self._cur = cur
        self.lastrowid = None

    def _cols(self):
        return [d[0] for d in self._cur.description] if self._cur.description else []

    def fetchone(self):
        r = self._cur.fetchone()
        return None if r is None else _Row(zip(self._cols(), (_py(v) for v in r)))

    def fetchall(self):
        cols = self._cols()
        return [_Row(zip(cols, (_py(v) for v in r))) for r in self._cur.fetchall()]


class MssqlConnection:
    """Minimal sqlite3-like wrapper over pyodbc so the engine runs unchanged on SQL Server."""

    def __init__(self, server: str, database: str):
        import pyodbc  # imported only when SQL Server is used
        installed = set(pyodbc.drivers())
        driver = next((d for d in DRIVER_PREFERENCE if d in installed), None)
        if driver is None:
            raise RuntimeError("No SQL Server ODBC driver found. Install 'ODBC Driver 18 for SQL Server'. "
                               f"Installed drivers: {sorted(installed)}")
        self.driver, self.server, self.database = driver, server, database
        self._cn = pyodbc.connect(f"DRIVER={{{driver}}};SERVER={server};DATABASE={database};"
                                  "Trusted_Connection=yes;TrustServerCertificate=yes;", autocommit=False)

    def execute(self, sql: str, params=()):
        cur = self._cn.cursor()
        if params:
            cur.execute(sql, tuple(params))
        else:
            cur.execute(sql)
        return _Cursor(cur)

    def commit(self):
        self._cn.commit()

    def rollback(self):
        self._cn.rollback()

    def close(self):
        self._cn.close()


def connect(path: Path | str = DEFAULT_DB):
    if backend() == "mssql":
        return MssqlConnection(os.environ.get("SI2_MSSQL_SERVER", DEFAULT_SERVER),
                               os.environ.get("SI2_MSSQL_DATABASE", DEFAULT_DATABASE))
    con = sqlite3.connect(str(path), check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.executescript(SCHEMA)
    return con


def describe(con) -> str:
    if isinstance(con, MssqlConnection):
        return f"SQL Server {con.server} / {con.database}"
    return "SQLite demo database"


@contextmanager
def tx(con):
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise


def rows(con, sql, params=()) -> list[dict]:
    return [dict(r) for r in con.execute(sql, params).fetchall()]


def one(con, sql, params=()) -> dict | None:
    r = con.execute(sql, params).fetchone()
    return dict(r) if r else None


def insert(con, table: str, data: dict):
    cols = ", ".join(data)
    qs = ", ".join("?" for _ in data)
    if isinstance(con, MssqlConnection):
        key = IDENTITY.get(table)
        out = f" OUTPUT INSERTED.{key}" if key and key not in data else ""
        cur = con.execute(f"INSERT INTO {table} ({cols}){out} VALUES ({qs})", tuple(data.values()))
        if out:
            return int(cur.fetchone()[0])
        return None
    cur = con.execute(f"INSERT INTO {table} ({cols}) VALUES ({qs})", tuple(data.values()))
    return cur.lastrowid


def as_of_clause(alias: str = "") -> str:
    p = f"{alias}." if alias else ""
    return f"{p}eff_date <= ? AND {p}exp_date >= ?"


def status_clause(include_pending: bool, alias: str = "") -> str:
    p = f"{alias}." if alias else ""
    return f"{p}status IN ('APPROVED','PENDING')" if include_pending else f"{p}status = 'APPROVED'"


# ---------------------------------------------------------------- approvals
def set_status(con, table: str, obj_id: int, new_status: str, actor: str, comment: str = ""):
    """Workflow transition. Approving a row that supersedes another expires the
    predecessor the day before the new row's effective date (never deletes it)."""
    key = META_TABLES[table]
    now = datetime.now().isoformat(timespec="seconds")
    row = one(con, f"SELECT * FROM {table} WHERE {key}=?", (obj_id,))
    if row is None:
        raise KeyError(f"{table} {obj_id} not found")
    if new_status == "APPROVED":
        con.execute(f"UPDATE {table} SET status='APPROVED', approved_by=?, approved_at=? WHERE {key}=?",
                    (actor, now, obj_id))
        if row.get("supersedes_id"):
            day_before = (date.fromisoformat(row["eff_date"]) - timedelta(days=1)).isoformat()
            con.execute(f"UPDATE {table} SET exp_date=? WHERE {key}=?", (day_before, row["supersedes_id"]))
            insert(con, "approval_log", {"object_table": table, "object_id": row["supersedes_id"],
                                         "action": "EXPIRED", "actor": actor, "at": now,
                                         "comment": f"Expired {day_before}; superseded by {table} {obj_id}"})
    else:
        con.execute(f"UPDATE {table} SET status=? WHERE {key}=?", (new_status, obj_id))
    insert(con, "approval_log", {"object_table": table, "object_id": obj_id, "action": new_status,
                                 "actor": actor, "comment": comment, "at": now})


def supersede(con, table: str, obj_id: int, new_values: dict, new_eff: str, actor: str,
              comment: str = "") -> int:
    """Create a PENDING replacement for row obj_id effective new_eff.

    The current row keeps serving production until the SME approves the
    replacement; approval then expires it (see set_status). Rejection leaves
    the current row untouched, so there is never a coverage gap."""
    key = META_TABLES[table]
    old = one(con, f"SELECT * FROM {table} WHERE {key}=?", (obj_id,))
    if old is None:
        raise KeyError(f"{table} {obj_id} not found")
    if new_eff <= old["eff_date"]:
        raise ValueError("New effective date must be after the current row's effective date")
    data = {k: v for k, v in old.items() if k != key}
    data.update(new_values)
    data.update({"eff_date": new_eff, "exp_date": old["exp_date"], "status": "PENDING",
                 "created_by": actor, "created_at": datetime.now().isoformat(timespec="seconds"),
                 "approved_by": None, "approved_at": None, "supersedes_id": obj_id})
    new_id = insert(con, table, data)
    insert(con, "approval_log", {"object_table": table, "object_id": new_id, "action": "SUBMITTED",
                                 "actor": actor, "comment": comment or f"Supersedes {table} {obj_id}"})
    return new_id


def add_pending(con, table: str, data: dict, actor: str, comment: str = "") -> int:
    """Insert a brand-new metadata row awaiting SME approval."""
    data = dict(data)
    data.setdefault("exp_date", OPEN_END)
    data.update({"status": "PENDING", "created_by": actor})
    new_id = insert(con, table, data)
    insert(con, "approval_log", {"object_table": table, "object_id": new_id, "action": "SUBMITTED",
                                 "actor": actor, "comment": comment})
    return new_id


def pending_counts(con) -> dict[str, int]:
    return {t: con.execute(f"SELECT COUNT(*) FROM {t} WHERE status='PENDING'").fetchone()[0]
            for t in META_TABLES}


def jdump(o) -> str:
    return json.dumps(o, default=str)
