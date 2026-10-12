"""Permanent store for SME decisions and two-person approvals, shared by every SI² app.

Backends
  SQLite (default)  file at $SI2_STATE_DB, default <repo>/data/si2_state.db
  SQL Server        SI2_STATE_BACKEND=mssql, using SI2_MSSQL_SERVER / SI2_MSSQL_DATABASE (same as the ISO app)
  PostgreSQL        SI2_STATE_BACKEND=postgres, SI2_DATABASE_URL=postgresql://user:password@host:5432/db
                    (Azure Database for PostgreSQL, Amazon RDS, Supabase, Neon ...); set it in Streamlit secrets

Tables
  si2_state     one row per (workspace, app, key): the app's decision state, as tagged JSON
  si2_approval  maker-checker requests: who proposed, who decided, when, with a note (e.g. a filing reference)

Values are stored as tagged JSON (DataFrames, sets, tuples, dates, non-text dict keys, bytes and dataclasses
round-trip exactly); nothing is ever unpickled.
"""
from __future__ import annotations

import base64
import dataclasses
import datetime as dt
import hashlib
import importlib
import json
import os
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DDL = [
    """CREATE TABLE si2_state (workspace VARCHAR(40) NOT NULL, app VARCHAR(40) NOT NULL, k VARCHAR(80) NOT NULL,
       v {big} NOT NULL, updated_by VARCHAR(80), updated_at VARCHAR(30), PRIMARY KEY (workspace, app, k))""",
    """CREATE TABLE si2_approval (id {ident}, workspace VARCHAR(40) NOT NULL, app VARCHAR(40) NOT NULL,
       kind VARCHAR(60) NOT NULL, ref VARCHAR(200), summary {big}, payload {big},
       maker VARCHAR(80) NOT NULL, made_at VARCHAR(30) NOT NULL, status VARCHAR(20) NOT NULL,
       checker VARCHAR(80), checked_at VARCHAR(30), note {big})""",
]


class PgConnection:
    """sqlite3-like wrapper over psycopg 3: '?' placeholders, rows as dicts."""

    def __init__(self, url: str):
        import psycopg
        from psycopg.rows import dict_row
        self._cn = psycopg.connect(url, row_factory=dict_row, connect_timeout=15)

    def execute(self, sql: str, params=()):
        return self._cn.execute(sql.replace("?", "%s"), tuple(params) if params else None)

    def commit(self):
        self._cn.commit()

    def rollback(self):
        self._cn.rollback()

    def close(self):
        self._cn.close()


def _setting(name: str, default: str = "") -> str:
    v = os.environ.get(name, "")
    if v:
        return v
    try:
        import streamlit as st
        return str(st.secrets.get(name, default))
    except Exception:
        return default


def workspace() -> str:
    """The client workspace: chosen in the sidebar (session), else SI2_WORKSPACE, else 'demo'."""
    try:
        import streamlit as st
        w = st.session_state.get("si2_workspace")
        if w:
            return str(w)
    except Exception:
        pass
    return _setting("SI2_WORKSPACE", "demo") or "demo"


def allowed_workspaces() -> list[str]:
    """SI2_WORKSPACES (comma separated) limits who sees which client; empty = any."""
    return [w.strip() for w in _setting("SI2_WORKSPACES", "").split(",") if w.strip()]


def workspaces() -> list[str]:
    con = connect()
    found = {r["workspace"] for r in con.execute("SELECT DISTINCT workspace FROM si2_state").fetchall()}
    found |= {r["workspace"] for r in con.execute("SELECT DISTINCT workspace FROM si2_approval").fetchall()}
    allow = allowed_workspaces()
    out = sorted((found | {"demo"} | set(allow)) if not allow else set(allow))
    return out


def backend() -> str:
    return _setting("SI2_STATE_BACKEND", "sqlite").strip().lower()


_CON = {}


def connect():
    key = (backend(), os.environ.get("SI2_STATE_DB", ""))
    if key in _CON:
        return _CON[key]
    if backend() == "postgres":
        url = _setting("SI2_DATABASE_URL")
        if not url:
            raise RuntimeError("SI2_STATE_BACKEND=postgres needs SI2_DATABASE_URL")
        con = PgConnection(url)
        _ensure(con, big="TEXT", ident="SERIAL PRIMARY KEY")
    elif backend() == "mssql":
        from iso_bureau.db import DEFAULT_DATABASE, DEFAULT_SERVER, MssqlConnection
        con = MssqlConnection(os.environ.get("SI2_MSSQL_SERVER", DEFAULT_SERVER),
                              os.environ.get("SI2_MSSQL_DATABASE", DEFAULT_DATABASE))
        _ensure(con, big="NVARCHAR(MAX)", ident="INT IDENTITY(1,1) PRIMARY KEY")
    else:
        path = Path(os.environ.get("SI2_STATE_DB", ROOT / "data" / "si2_state.db"))
        path.parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(str(path), check_same_thread=False)
        con.row_factory = sqlite3.Row
        _ensure(con, big="TEXT", ident="INTEGER PRIMARY KEY AUTOINCREMENT")
    _CON[key] = con
    return con


def _ensure(con, **types):
    for d, t in zip(DDL, ("si2_state", "si2_approval")):
        try:
            con.execute(f"SELECT COUNT(*) AS n FROM {t} WHERE 1 = 0").fetchall()
        except Exception:
            try:
                con.rollback()
            except Exception:
                pass
            con.execute(d.format(**types))
            con.commit()
    con.commit()


def describe() -> str:
    if backend() == "postgres":
        from urllib.parse import urlparse
        u = urlparse(_setting("SI2_DATABASE_URL"))
        return f"PostgreSQL {u.hostname or ''}/{(u.path or '/').lstrip('/')}"
    if backend() == "mssql":
        from iso_bureau.db import DEFAULT_DATABASE, DEFAULT_SERVER
        return (f"SQL Server {os.environ.get('SI2_MSSQL_SERVER', DEFAULT_SERVER)} / "
                f"{os.environ.get('SI2_MSSQL_DATABASE', DEFAULT_DATABASE)}")
    return "SQLite " + Path(os.environ.get("SI2_STATE_DB", ROOT / "data" / "si2_state.db")).name


def _now() -> str:
    return dt.datetime.now().isoformat(sep=" ", timespec="seconds")


# ------------------------------------------------------------------------------------------ codec
def encode(o):
    if isinstance(o, pd.DataFrame):
        cols = [str(c) for c in o.columns]
        return {"__df__": {"columns": cols, "dtypes": [str(t) for t in o.dtypes],
                           "data": [[encode(v) for v in row] for row in o.itertuples(index=False, name=None)],
                           "index": [encode(i) for i in o.index]}}
    if isinstance(o, pd.Series):
        return {"__series__": {"name": encode(o.name), "data": [encode(v) for v in o.tolist()],
                               "index": [encode(i) for i in o.index]}}
    if dataclasses.is_dataclass(o) and not isinstance(o, type):
        return {"__dc__": f"{type(o).__module__}:{type(o).__qualname__}",
                "fields": {f.name: encode(getattr(o, f.name)) for f in dataclasses.fields(o)}}
    if isinstance(o, dict):
        if all(isinstance(k, str) for k in o):
            return {"__dict__": {k: encode(v) for k, v in o.items()}}
        return {"__pairs__": [[encode(k), encode(v)] for k, v in o.items()]}
    if isinstance(o, (set, frozenset)):
        return {"__set__": [encode(v) for v in o]}
    if isinstance(o, tuple):
        return {"__tuple__": [encode(v) for v in o]}
    if isinstance(o, list):
        return [encode(v) for v in o]
    if isinstance(o, (bytes, bytearray)):
        return {"__bytes__": base64.b64encode(bytes(o)).decode()}
    if isinstance(o, pd.Timestamp):
        return {"__ts__": o.isoformat()}
    if isinstance(o, dt.datetime):
        return {"__dt__": o.isoformat()}
    if isinstance(o, dt.date):
        return {"__date__": o.isoformat()}
    if isinstance(o, np.generic):
        return encode(o.item())
    if isinstance(o, float) and (o != o):
        return {"__nan__": 1}
    if o is pd.NaT:
        return None
    if isinstance(o, (str, int, float, bool)) or o is None:
        return o
    return str(o)


_ALLOWED_DC = ("migrate.", "si2_common.", "bureau.", "iso_bureau.")


def decode(o):
    if isinstance(o, list):
        return [decode(v) for v in o]
    if not isinstance(o, dict):
        return o
    if "__df__" in o:
        d = o["__df__"]
        df = pd.DataFrame([[decode(v) for v in row] for row in d["data"]], columns=d["columns"])
        for c, t in zip(d["columns"], d["dtypes"]):
            if t in ("bool", "int64", "float64") and len(df):
                try:
                    df[c] = df[c].astype(t)
                except (ValueError, TypeError):
                    pass
        if d.get("index") is not None and len(d["index"]) == len(df):
            df.index = [decode(i) for i in d["index"]]
        return df
    if "__series__" in o:
        d = o["__series__"]
        return pd.Series([decode(v) for v in d["data"]], index=[decode(i) for i in d["index"]], name=decode(d["name"]))
    if "__dc__" in o:
        mod, name = o["__dc__"].split(":")
        if not mod.startswith(_ALLOWED_DC):
            raise ValueError(f"refusing to rebuild {mod}")
        cls = getattr(importlib.import_module(mod), name)
        return cls(**{k: decode(v) for k, v in o["fields"].items()})
    if "__dict__" in o:
        return {k: decode(v) for k, v in o["__dict__"].items()}
    if "__pairs__" in o:
        return {_hashable(decode(k)): decode(v) for k, v in o["__pairs__"]}
    if "__set__" in o:
        return {_hashable(decode(v)) for v in o["__set__"]}
    if "__tuple__" in o:
        return tuple(decode(v) for v in o["__tuple__"])
    if "__bytes__" in o:
        return base64.b64decode(o["__bytes__"])
    if "__ts__" in o:
        return pd.Timestamp(o["__ts__"])
    if "__dt__" in o:
        return dt.datetime.fromisoformat(o["__dt__"])
    if "__date__" in o:
        return dt.date.fromisoformat(o["__date__"])
    if "__nan__" in o:
        return float("nan")
    return {k: decode(v) for k, v in o.items()}


def _hashable(v):
    return tuple(_hashable(x) for x in v) if isinstance(v, list) else v


def dumps(o) -> str:
    return json.dumps(encode(o), separators=(",", ":"), default=str)


def loads(s: str):
    return decode(json.loads(s))


def digest(s: str) -> str:
    return hashlib.sha1(s.encode()).hexdigest()


# ------------------------------------------------------------------------------------------ state
def load(app: str) -> dict:
    con = connect()
    out = {}
    for r in con.execute("SELECT k, v FROM si2_state WHERE workspace = ? AND app = ?", (workspace(), app)).fetchall():
        out[r["k"]] = r["v"]
    return out


def save(app: str, key: str, text: str, actor: str = ""):
    con = connect()
    con.execute("DELETE FROM si2_state WHERE workspace = ? AND app = ? AND k = ?", (workspace(), app, key))
    con.execute("INSERT INTO si2_state (workspace, app, k, v, updated_by, updated_at) VALUES (?,?,?,?,?,?)",
                (workspace(), app, key, text, actor, _now()))
    con.commit()


def last_saved(app: str) -> str:
    r = connect().execute("SELECT MAX(updated_at) AS t FROM si2_state WHERE workspace = ? AND app = ?",
                          (workspace(), app)).fetchone()
    return (r["t"] if r else "") or ""


def reset(app: str):
    con = connect()
    con.execute("DELETE FROM si2_state WHERE workspace = ? AND app = ?", (workspace(), app))
    con.execute("DELETE FROM si2_approval WHERE workspace = ? AND app = ?", (workspace(), app))
    con.commit()


# ------------------------------------------------------------------------------------------ two-person approval
def request(app: str, kind: str, ref: str, summary: str, payload, maker: str) -> int:
    maker = (maker or "").strip()
    if not maker or maker.upper() == "SME":
        raise ValueError("Enter your name in the sidebar first: approvals record who proposed and who approved.")
    con = connect()
    con.execute("UPDATE si2_approval SET status = 'Superseded', checked_at = ? "
                "WHERE workspace = ? AND app = ? AND kind = ? AND ref = ? AND status = 'Pending'",
                (_now(), workspace(), app, kind, ref))
    con.execute("INSERT INTO si2_approval (workspace, app, kind, ref, summary, payload, maker, made_at, status) "
                "VALUES (?,?,?,?,?,?,?,?, 'Pending')", (workspace(), app, kind, ref, summary, dumps(payload), maker, _now()))
    con.commit()
    r = con.execute("SELECT MAX(id) AS id FROM si2_approval WHERE workspace = ? AND app = ?", (workspace(), app)).fetchone()
    return int(r["id"])


def approvals(app: str, status: str | None = None) -> list[dict]:
    sql = "SELECT * FROM si2_approval WHERE workspace = ? AND app = ?"
    params = [workspace(), app]
    if status:
        sql += " AND status = ?"
        params.append(status)
    rows = [dict(r) for r in connect().execute(sql + " ORDER BY id DESC", tuple(params)).fetchall()]
    for r in rows:
        r["payload"] = loads(r["payload"]) if r.get("payload") else None
    return rows


def decide(app: str, req_id: int, checker: str, approve: bool, note: str = "") -> dict:
    con = connect()
    r = con.execute("SELECT * FROM si2_approval WHERE id = ? AND workspace = ? AND app = ?",
                    (req_id, workspace(), app)).fetchone()
    if r is None or r["status"] != "Pending":
        raise ValueError("This request is no longer pending.")
    checker = (checker or "").strip()
    if not checker or checker.upper() == "SME":
        raise ValueError("Enter your name in the sidebar first.")
    if checker.lower() == (r["maker"] or "").lower():
        raise ValueError(f"Two-person rule: {checker} proposed this change, so someone else must approve it.")
    con.execute("UPDATE si2_approval SET status = ?, checker = ?, checked_at = ?, note = ? WHERE id = ?",
                ("Approved" if approve else "Rejected", checker, _now(), note, req_id))
    con.commit()
    out = dict(r)
    out.update(status="Approved" if approve else "Rejected", checker=checker, note=note,
               payload=loads(r["payload"]) if r["payload"] else None)
    return out



# ------------------------------------------------------------------------------------------ backup / restore
BACKUP_FORMAT = "si2-backup-1"


def export_workspace(ws: str | None = None) -> str:
    """Everything SI² saved for one client workspace (all apps, approvals) as one JSON document."""
    ws = ws or workspace()
    con = connect()
    state = [dict(r) for r in con.execute("SELECT * FROM si2_state WHERE workspace = ?", (ws,)).fetchall()]
    appr = [dict(r) for r in con.execute("SELECT * FROM si2_approval WHERE workspace = ? ORDER BY id", (ws,)).fetchall()]
    return json.dumps({"format": BACKUP_FORMAT, "workspace": ws, "exported_at": _now(), "backend": describe(),
                       "state": state, "approvals": appr}, default=str)


def import_workspace(text: str, ws: str | None = None, actor: str = "") -> dict:
    """Replace one workspace with a backup (to the same or another workspace name)."""
    data = json.loads(text)
    if data.get("format") != BACKUP_FORMAT:
        raise ValueError("This is not an SI² backup file.")
    ws = ws or data["workspace"]
    con = connect()
    con.execute("DELETE FROM si2_state WHERE workspace = ?", (ws,))
    con.execute("DELETE FROM si2_approval WHERE workspace = ?", (ws,))
    for r in data["state"]:
        con.execute("INSERT INTO si2_state (workspace, app, k, v, updated_by, updated_at) VALUES (?,?,?,?,?,?)",
                    (ws, r["app"], r["k"], r["v"], r.get("updated_by") or actor, r.get("updated_at") or _now()))
    for r in data["approvals"]:
        con.execute("INSERT INTO si2_approval (workspace, app, kind, ref, summary, payload, maker, made_at, status, checker, "
                    "checked_at, note) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (ws, r["app"], r["kind"], r.get("ref"), r.get("summary"), r.get("payload"), r["maker"], r["made_at"],
                     r["status"], r.get("checker"), r.get("checked_at"), r.get("note")))
    con.commit()
    return {"workspace": ws, "state": len(data["state"]), "approvals": len(data["approvals"])}
