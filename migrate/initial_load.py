"""Initial load: uploaded files -> proposed tables, keys and pick lists -> SME approval -> create + load -> reconcile.

Readers (nothing uploaded is ever executed):
  CSV, Excel (one table per sheet), JSON (nested lists become child tables), XML / ACORD (repeated
  elements become child tables), SQL / PL-SQL scripts (CREATE TABLE, PRIMARY / FOREIGN KEY and INSERT
  statements are *read*; procedures and other statements are listed as skipped), PDF (best effort:
  simple text tables), and an API reader (JSON over HTTPS, with paging).

Key inference, every proposal with a confidence and its evidence:
  primary key   declared in the DDL; else a column that is never blank and never repeats (key-like names
                first); else key + date (a policy term); else SI² generates one
  foreign key   declared in the DDL; implied by nesting in JSON / XML; found in the data (every child value
                exists in the parent key, and the names agree); for a parent whose key is policy number +
                effective date: the exact pair, or the *term in force* on the child's date (loss date), or
                the latest term when the child has no date

Load: every table gets a surrogate key (<table>_sk) and keeps its natural key as a unique business key;
children reference the parent's surrogate key. Tables load parent-first. Rows that cannot be loaded
(bad date, bad amount, orphan child) are quarantined with a reason, never dropped silently. Each row
carries batch id, load time and effective-from / effective-to (never delete, only expire).
"""
from __future__ import annotations

import datetime as dt
import io
import json
import re
import sqlite3
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from si2_common.gaps import draft_description, similarity, to_title, words

SAMPLES = Path(__file__).resolve().parent / "initial_load_samples"
FAR_FUTURE = "9999-12-31"
GENERIC_KEYS = {"data", "items", "results", "records", "rows", "value", "values"}
KEY_WORDS = {"ID", "NUMBER", "KEY", "CODE"}
DATE_WORDS = {"DATE", "DT", "EFFECTIVE", "EXPIRATION", "DUE"}
MONEY_WORDS = {"AMOUNT", "PREMIUM", "RESERVE", "PAID", "LIMIT", "DEDUCTIBLE", "AMT", "PRICE", "BALANCE"}
TEXT_FORCED = {"ZIP", "POSTAL", "PHONE", "SSN", "FEIN", "NAICS", "SIC", "VIN"}


# ============================================================================== staging
@dataclass
class Staged:
    tables: dict = field(default_factory=dict)          # name -> DataFrame (all text)
    origin: dict = field(default_factory=dict)          # name -> "file / sheet"
    declared_types: dict = field(default_factory=dict)  # name -> {col: TYPE}
    declared_pk: dict = field(default_factory=dict)     # name -> [cols]
    declared_fk: list = field(default_factory=list)     # (child, [cols], parent, [cols], method)
    notes: list = field(default_factory=list)           # (file, message)

    def add(self, name: str, df: pd.DataFrame, origin: str):
        name = table_name(name)
        df = df.fillna("").astype(str)
        df.columns = [column_name(c) for c in df.columns]
        df = df.loc[:, ~df.columns.duplicated()]
        if name in self.tables and len(self.tables[name]):
            self.tables[name] = pd.concat([self.tables[name], df], ignore_index=True).fillna("")
            self.origin[name] += f" + {origin}"
        else:
            self.tables[name] = df.reset_index(drop=True)
            self.origin[name] = origin


def table_name(name: str) -> str:
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", Path(str(name)).stem)
    s = re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_").lower()
    return s or "table"


def column_name(name: str) -> str:
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", str(name))
    s = re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_").lower()
    return s or "column"


def _singular(name: str) -> str:
    n = table_name(name)
    if n.endswith("ies"):
        return n[:-3] + "y"
    if n.endswith("ses") or n.endswith("xes"):
        return n[:-2]
    return n[:-1] if n.endswith("s") and not n.endswith("ss") else n


def _cell(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    if isinstance(v, (pd.Timestamp, dt.datetime)):
        return v.strftime("%Y-%m-%d") if (v.hour, v.minute, v.second) == (0, 0, 0) else v.isoformat(sep=" ")
    if isinstance(v, dt.date):
        return v.isoformat()
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v).strip()


# ============================================================================== readers
def read_csv(data: bytes, name: str, st: Staged):
    text = data.decode("utf-8-sig", errors="replace")
    sep = max([",", "|", "\t", ";"], key=lambda s: text.splitlines()[0].count(s) if text else 0)
    df = pd.read_csv(io.StringIO(text), dtype=str, keep_default_na=False, sep=sep)
    st.add(name, df, name)


def read_excel(data: bytes, name: str, st: Staged):
    for sheet, df in pd.read_excel(io.BytesIO(data), sheet_name=None, dtype=object).items():
        df = df.dropna(how="all").dropna(axis=1, how="all")
        if df.empty:
            st.notes.append((name, f"sheet '{sheet}' is empty; skipped"))
            continue
        st.add(sheet, df.map(_cell), f"{name} / {sheet}")


def _xml_to_obj(root: ET.Element):
    def tag(e):
        return e.tag.split("}")[-1]
    repeated = set()
    for parent in root.iter():
        c = Counter(tag(ch) for ch in parent)
        repeated |= {(tag(parent), t) for t, n in c.items() if n > 1}

    def conv(e):
        kids = list(e)
        if not kids and not e.attrib:
            return (e.text or "").strip()
        d = {k.split("}")[-1]: v for k, v in e.attrib.items()}
        for ch in kids:
            t, v = tag(ch), conv(ch)
            if (tag(e), t) in repeated:
                d.setdefault(t, []).append(v)
            else:
                d[t] = v
        if (e.text or "").strip() and kids == []:
            d["value"] = e.text.strip()
        return d
    return {tag(root): conv(root)}


def _tables_from_tree(obj, source_name: str, st: Staged, origin: str):
    """Unwrap single-key containers, then every list of objects is a table; nested lists are child tables."""
    while isinstance(obj, dict):
        lists = {k: v for k, v in obj.items() if isinstance(v, list) and v and isinstance(v[0], dict)}
        dicts = {k: v for k, v in obj.items() if isinstance(v, dict)}
        if lists:
            for k, v in lists.items():
                tname = table_name(source_name) if k.lower() in GENERIC_KEYS else _singular(k)
                _flatten(v, tname, st, origin)
            return
        def has_rows(o):
            if isinstance(o, list):
                return any(isinstance(x, dict) for x in o)
            return isinstance(o, dict) and any(has_rows(v) for v in o.values())
        holders = [v for v in dicts.values() if has_rows(v)]
        if len(holders) == 1:                       # descend past envelopes (SignonRs, paging metadata ...)
            obj = holders[0]
            continue
        _flatten([obj], table_name(source_name), st, origin)
        return
    if isinstance(obj, list) and obj and isinstance(obj[0], dict):
        _flatten(obj, table_name(source_name), st, origin)


def _flatten(records: list, tname: str, st: Staged, origin: str, parent: tuple | None = None):
    rows, children = [], defaultdict(list)          # child table -> [(parent row no, [records])]
    for i, rec in enumerate(records, 1):
        row = {}

        def walk(d, prefix):
            for k, v in d.items():
                key = f"{prefix}{k}"
                if isinstance(v, dict):
                    walk(v, f"{key}_")
                elif isinstance(v, list) and v and isinstance(v[0], dict):
                    children[_singular(k)].append((i, v))
                elif isinstance(v, list):
                    row[key] = "; ".join(map(_cell, v))
                else:
                    row[key] = _cell(v)
        walk(rec if isinstance(rec, dict) else {"value": rec}, "")
        if parent:
            row[parent[0]] = parent[1][i - 1]
        rows.append(row)
    df = pd.DataFrame(rows).fillna("")
    df.columns = [column_name(c) for c in df.columns]
    # the parent's natural key, if it has one; otherwise a row number SI² generates
    key = next((c for c in df.columns if not c.endswith("_row") and _keyish(c) and df[c].ne("").all()
                and df[c].is_unique), None)
    if key is None and children:
        key = f"{tname}_row"
        df.insert(0, key, [str(i) for i in range(1, len(df) + 1)])
    st.add(tname, df, origin)
    for child, groups in children.items():
        link = key if key.startswith(tname) else f"{tname}_{key}"
        flat, refs = [], []
        for i, recs in groups:
            flat += recs
            refs += [df.iloc[i - 1][key]] * len(recs)
        _flatten(flat, child, st, origin, parent=(link, refs))
        if (child, [link], tname, [key], "Nested in file") not in st.declared_fk:
            st.declared_fk.append((child, [link], tname, [key], "Nested in file"))
        if key.endswith("_row"):
            st.declared_pk.setdefault(tname, [key])


def read_json(data: bytes, name: str, st: Staged):
    _tables_from_tree(json.loads(data.decode("utf-8-sig")), name, st, name)


def read_xml(data: bytes, name: str, st: Staged):
    obj = _xml_to_obj(ET.fromstring(data))
    _tables_from_tree(obj, name, st, name)


# ---------------------------------------------------------------------- SQL / PL-SQL (read, never executed)
def _split_sql(text: str) -> list[str]:
    text = re.sub(r"--[^\n]*", "", text)
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    out, buf, q = [], [], False
    plsql = False
    for line in text.splitlines():
        s = line.strip()
        if not "".join(buf).strip() and re.match(r"(CREATE\s+(OR\s+REPLACE\s+)?(PROCEDURE|FUNCTION|TRIGGER|PACKAGE)|DECLARE|BEGIN)\b", s, re.I):
            plsql = True
        if plsql:
            buf.append(line)
            if s == "/":
                out.append("\n".join(buf[:-1]))
                buf, plsql = [], False
            continue
        for ch in line + "\n":
            if ch == "'":
                q = not q
            if ch == ";" and not q:
                out.append("".join(buf))
                buf = []
            else:
                buf.append(ch)
    if "".join(buf).strip():
        out.append("".join(buf) if not plsql else "\n".join(buf))
    return [s.strip() for s in out if s.strip()]


def _split_top(s: str) -> list[str]:
    parts, depth, q, cur = [], 0, False, ""
    for ch in s:
        if ch == "'":
            q = not q
        if not q and ch == "(":
            depth += 1
        if not q and ch == ")":
            depth -= 1
        if ch == "," and depth == 0 and not q:
            parts.append(cur.strip())
            cur = ""
        else:
            cur += ch
    if cur.strip():
        parts.append(cur.strip())
    return parts


def _sql_type(t: str, col: str) -> str:
    t = t.upper()
    if t.startswith(("VARCHAR", "CHAR", "NVARCHAR", "NCHAR", "CLOB", "TEXT")):
        return "TEXT"
    if t.startswith(("DATE", "TIMESTAMP")):
        return "DATE"
    m = re.match(r"(NUMBER|NUMERIC|DECIMAL)\s*\(\s*\d+\s*,\s*(\d+)\s*\)", t)
    if m and int(m.group(2)) > 0:
        return "MONEY" if set(words(col)) & MONEY_WORDS else "DECIMAL"
    if t.startswith(("NUMBER", "INT", "INTEGER", "SMALLINT", "BIGINT", "NUMERIC")):
        return "INTEGER"
    if t.startswith(("FLOAT", "REAL", "DOUBLE", "BINARY_DOUBLE")):
        return "DECIMAL"
    return "TEXT"


def _cols(s: str) -> list[str]:
    return [column_name(c.strip().strip('"')) for c in s.split(",")]


def _sql_value(tok: str) -> str:
    tok = tok.strip()
    if tok.upper() == "NULL":
        return ""
    m = re.match(r"(?:TO_DATE|TO_TIMESTAMP|DATE)\s*\(?\s*'([^']*)'", tok, re.I)
    if m:
        return m.group(1)
    if tok.startswith("'") and tok.endswith("'"):
        return tok[1:-1].replace("''", "'")
    return tok


def read_sql(data: bytes, name: str, st: Staged):
    text = data.decode("utf-8-sig", errors="replace")
    inserts = defaultdict(list)
    for stmt in _split_sql(text):
        head = " ".join(stmt.split()[:4]).upper()
        if m := re.match(r"CREATE\s+(?:GLOBAL\s+TEMPORARY\s+)?TABLE\s+([\w.\"]+)\s*\((.*)\)", stmt, re.S | re.I):
            t = table_name(m.group(1).split(".")[-1].strip('"'))
            types, cols = {}, []
            for part in _split_top(m.group(2)):
                up = part.upper()
                if mm := re.match(r"(?:CONSTRAINT\s+\w+\s+)?PRIMARY\s+KEY\s*\(([^)]*)\)", part, re.I):
                    st.declared_pk[t] = _cols(mm.group(1))
                elif mm := re.match(r"(?:CONSTRAINT\s+\w+\s+)?FOREIGN\s+KEY\s*\(([^)]*)\)\s*REFERENCES\s+([\w.\"]+)\s*\(([^)]*)\)",
                                    part, re.I):
                    st.declared_fk.append((t, _cols(mm.group(1)), table_name(mm.group(2).split(".")[-1].strip('"')),
                                           _cols(mm.group(3)), "Declared in DDL"))
                elif up.startswith(("CONSTRAINT", "UNIQUE", "CHECK", "INDEX")):
                    continue
                else:
                    bits = part.split(None, 1)
                    c = column_name(bits[0].strip('"'))
                    cols.append(c)
                    types[c] = _sql_type(bits[1] if len(bits) > 1 else "", c)
                    if re.search(r"\bPRIMARY\s+KEY\b", up):
                        st.declared_pk[t] = [c]
                    if mm := re.search(r"REFERENCES\s+([\w.\"]+)\s*\(([^)]*)\)", part, re.I):
                        st.declared_fk.append((t, [c], table_name(mm.group(1).split(".")[-1].strip('"')),
                                               _cols(mm.group(2)), "Declared in DDL"))
            st.declared_types[t] = types
            if t not in st.tables:
                st.tables[t] = pd.DataFrame(columns=cols)
                st.origin[t] = f"{name} (DDL)"
        elif m := re.match(r"ALTER\s+TABLE\s+([\w.\"]+)\s+ADD\s+(?:CONSTRAINT\s+\w+\s+)?(PRIMARY|FOREIGN)\s+KEY\s*\(([^)]*)\)"
                           r"(?:\s*REFERENCES\s+([\w.\"]+)\s*\(([^)]*)\))?", stmt, re.S | re.I):
            t = table_name(m.group(1).split(".")[-1].strip('"'))
            if m.group(2).upper() == "PRIMARY":
                st.declared_pk[t] = _cols(m.group(3))
            else:
                st.declared_fk.append((t, _cols(m.group(3)), table_name(m.group(4).split(".")[-1].strip('"')),
                                       _cols(m.group(5)), "Declared in DDL"))
        elif m := re.match(r"INSERT\s+INTO\s+([\w.\"]+)\s*\(([^)]*)\)\s*VALUES\s*\((.*)\)\s*$", stmt, re.S | re.I):
            t = table_name(m.group(1).split(".")[-1].strip('"'))
            inserts[t].append(dict(zip(_cols(m.group(2)), [_sql_value(v) for v in _split_top(m.group(3))])))
        elif head.startswith(("CREATE INDEX", "CREATE UNIQUE", "CREATE SEQUENCE", "COMMIT", "GRANT")):
            continue
        else:
            first = stmt.split("\n")[0][:70]
            st.notes.append((name, f"not executed (read-only load): {first}"))
    for t, rows in inserts.items():
        df = pd.DataFrame(rows)
        if t in st.tables and not len(st.tables[t]):
            st.tables[t] = df.reindex(columns=list(st.tables[t].columns) or list(df.columns)).fillna("")
            st.origin[t] = f"{name} (DDL + INSERT)"
        else:
            st.add(t, df, f"{name} (INSERT)")


def read_pdf(data: bytes, name: str, st: Staged):
    """Best effort: a simple text table (header row, then rows with the same number of columns)."""
    from pypdf import PdfReader
    lines = []
    for page in PdfReader(io.BytesIO(data)).pages:
        lines += [ln for ln in (page.extract_text() or "").splitlines() if ln.strip()]
    split = (lambda s: [x.strip() for x in s.split("|")]) if any("|" in ln for ln in lines) else \
        (lambda s: [x for x in re.split(r"\s{2,}", s.strip())])
    best, cur = [], []
    for ln in lines:
        parts = split(ln)
        if len(parts) >= 2 and (not cur or len(parts) == len(cur[0])):
            cur.append(parts)
        else:
            best = max(best, cur, key=len)
            cur = [parts] if len(parts) >= 2 else []
    best = max(best, cur, key=len)
    if len(best) < 2:
        st.notes.append((name, "no table found in the PDF text; PDFs are best used for layouts and specs"))
        return
    st.add(name, pd.DataFrame(best[1:], columns=best[0]), f"{name} (PDF text table)")
    st.notes.append((name, "read from PDF text: check the columns before approving"))


SAMPLE_API = "si2://sample-api/drivers"


def read_api(url: str, st: Staged, max_pages: int = 20, timeout: int = 15):
    """GET JSON; follow 'next' links. si2://sample-api/... is the built-in stand-in for a client's API."""
    pages, nxt, n = [], url, 0
    while nxt and n < max_pages:
        if nxt.startswith("si2://"):
            payload = json.loads((SAMPLES / "api" / f"{nxt.rsplit('/', 1)[-1]}.json").read_text())
        else:
            if not nxt.lower().startswith("https://"):
                raise ValueError("Only https:// addresses are read.")
            req = urllib.request.Request(nxt, headers={"Accept": "application/json", "User-Agent": "SI2-initial-load"})
            with urllib.request.urlopen(req, timeout=timeout) as r:   # noqa: S310 (https only, checked above)
                payload = json.loads(r.read().decode("utf-8"))
        pages.append(payload)
        nxt = payload.get("next") if isinstance(payload, dict) else None
        n += 1
    resource = _singular(url.rstrip("/").rsplit("/", 1)[-1].split("?")[0])
    for p in pages:
        _tables_from_tree(p, resource, st, f"API {url}")
    st.notes.append((f"API {url}", f"{n} page(s) read"))


READERS = {".csv": read_csv, ".txt": read_csv, ".xlsx": read_excel, ".xls": read_excel, ".json": read_json,
           ".xml": read_xml, ".sql": read_sql, ".ddl": read_sql, ".pls": read_sql, ".pkb": read_sql, ".pdf": read_pdf}


def stage(files: list[tuple[str, bytes]], api_urls: list[str] = ()) -> Staged:
    st = Staged()
    # DDL first, so data files land in the declared tables
    for fname, data in sorted(files, key=lambda f: Path(f[0]).suffix.lower() not in (".sql", ".ddl", ".pls", ".pkb")):
        reader = READERS.get(Path(fname).suffix.lower())
        if reader is None:
            st.notes.append((fname, "file type not supported; skipped"))
            continue
        try:
            reader(data, fname, st)
        except Exception as exc:                        # one bad file must not stop the others
            st.notes.append((fname, f"could not be read: {exc}"))
    for url in api_urls:
        try:
            read_api(url, st)
        except Exception as exc:
            st.notes.append((f"API {url}", f"could not be read: {exc}"))
    return st


def sample_files() -> list[tuple[str, bytes]]:
    return [(p.name, p.read_bytes()) for p in sorted(SAMPLES.glob("*.*"))]


# ============================================================================== profiling
DATE_FORMATS = [("%Y-%m-%d", r"\d{4}-\d{2}-\d{2}"), ("%m/%d/%Y", r"\d{1,2}/\d{1,2}/\d{4}"), ("%Y%m%d", r"\d{8}"),
                ("%m/%d/%y", r"\d{1,2}/\d{1,2}/\d{2}"), ("%d-%b-%Y", r"\d{1,2}-[A-Za-z]{3}-\d{4}"),
                ("%Y-%m-%d %H:%M:%S", r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}")]


def _keyish(col: str) -> bool:
    w = set(words(col))
    return bool(w & KEY_WORDS) or col.endswith("_row")


def parse_date(v: str) -> str | None:
    v = str(v).strip()
    for fmt, rx in DATE_FORMATS:
        if re.fullmatch(rx, v):
            try:
                return dt.datetime.strptime(v, fmt).date().isoformat()
            except ValueError:
                return None
    return None


def parse_money(v: str) -> float | None:
    s = str(v).strip().replace("$", "").replace(",", "")
    if re.fullmatch(r"\(\d+(\.\d+)?\)", s):
        s = "-" + s[1:-1]
    try:
        return float(s)
    except ValueError:
        return None


def infer_column(col: str, vals: list[str]) -> tuple[str, str]:
    """-> (TYPE, note). Codes with leading zeros stay text."""
    v = [x for x in vals if x != ""]
    w = set(words(col))
    if not v:
        return "TEXT", "always blank"
    if w & TEXT_FORCED:
        return "TEXT", "kept as text (identifier, leading zeros kept)"
    dates = [parse_date(x) for x in v[:500]]
    if sum(d is not None for d in dates) >= 0.95 * len(dates) and (w & DATE_WORDS or not all(x.isdigit() for x in v[:50])):
        fmts = {next((f for f, rx in DATE_FORMATS if re.fullmatch(rx, x)), "?") for x in v[:200]}
        return "DATE", "formats: " + ", ".join(sorted(fmts))
    if any(re.fullmatch(r"0\d+", x) for x in v):
        return "TEXT", "leading zeros kept"
    if all(re.fullmatch(r"-?\d+", x) for x in v) and not (w & KEY_WORDS and max(map(len, v)) >= 9):
        return "INTEGER", ""
    if all(parse_money(x) is not None for x in v):
        if w & MONEY_WORDS or any("$" in x or "," in x for x in v):
            return "MONEY", "$ and commas removed" if any("$" in x or "," in x for x in v) else ""
        return "DECIMAL", ""
    return "TEXT", ""


def profile(st: Staged) -> pd.DataFrame:
    rows = []
    for t, df in st.tables.items():
        declared = st.declared_types.get(t, {})
        for c in df.columns:
            vals = df[c].astype(str).tolist()
            nonblank = [x for x in vals if x != ""]
            typ, note = infer_column(c, vals)
            if c in declared:
                if declared[c] != typ and nonblank:
                    note = f"DDL says {declared[c]}; data looks {typ}" + (f" ({note})" if note else "")
                typ = declared[c]
            distinct = len(set(nonblank))
            pick = (typ == "TEXT" and 1 < distinct <= 15 and len(nonblank) >= 2 * distinct
                    and max(map(len, nonblank)) <= 12 and not _keyish(c))
            rows.append({"table": t, "column": c, "type": typ, "rows": len(vals), "blank": len(vals) - len(nonblank),
                         "distinct": distinct, "unique": distinct == len(vals) and not (len(vals) - len(nonblank)),
                         "max_len": max(map(len, nonblank), default=0), "samples": ", ".join(list(dict.fromkeys(nonblank))[:3]),
                         "pick_list": pick, "note": note,
                         "description": draft_description(c, "CODE" if pick else typ, list(dict.fromkeys(nonblank))[:3], "",
                                                          {}).replace(" (Drafted by SI² - edit if needed.)", "")})
    return pd.DataFrame(rows)


# ============================================================================== key proposals
def _vals(df, c):
    return set(x for x in df[c].astype(str) if x != "")


def _name_score(child_col: str, parent_table: str, parent_col: str) -> float:
    return max(similarity(child_col, parent_col), similarity(child_col, f"{parent_table} {parent_col}"),
               similarity(child_col.replace(f"{parent_table}_", ""), parent_col))


def propose(st: Staged, prof: pd.DataFrame) -> pd.DataFrame:
    props = []
    types = {(r.table, r.column): r.type for r in prof.itertuples()}
    pks = {}
    for t, df in st.tables.items():
        n = len(df)
        if t in st.declared_pk and all(c in df.columns for c in st.declared_pk[t]):
            cols = st.declared_pk[t]
            dup = int(df.duplicated(cols).sum()) if n else 0
            meth = "Generated row number" if cols[0].endswith("_row") else "Declared in DDL"
            props.append(("PK", t, cols, "", [], meth, 100 if not dup else 60,
                          ("declared; " if meth.startswith("Declared") else "") +
                          (f"{dup} duplicate key(s) in the data" if dup else "unique in the data" if n else "no rows yet")))
            pks[t] = cols
            continue
        if not n:
            continue
        full = [c for c in df.columns if df[c].ne("").all()]
        uniq = [c for c in full if _keyish(c) and types.get((t, c)) in ("TEXT", "INTEGER") and df[c].is_unique]
        if uniq:
            c = uniq[0]
            props.append(("PK", t, [c], "", [], "Found in the data", 95,
                          f"never blank and never repeats ({n} rows); key-like name"))
            pks[t] = [c]
            continue
        # two columns together: key + key (vehicle + coverage code) first, then key + date (policy number + term)
        keyish = [c for c in full if _keyish(c) and types.get((t, c)) in ("TEXT", "INTEGER")]
        links = {c for ch, cc, *_ in st.declared_fk if ch == t for c in cc}
        keyish.sort(key=lambda c: c not in links)                 # parent link first: (vehicle, coverage code)
        dates = [c for c in full if types.get((t, c)) == "DATE"]
        pairs = [(a, b) for i, a in enumerate(keyish) for b in keyish[i + 1:]] + [(a, b) for a in keyish for b in dates]
        found = next(([a, b] for a, b in pairs if not df.duplicated([a, b]).any()), None)
        if found:
            reps = int(df[found[0]].duplicated().sum())
            why = "one row per term (renewals)" if found[1] in dates else "one row per combination"
            props.append(("PK", t, found, "", [], "Found in the data", 90,
                          f"{found[0]} repeats {reps} time(s); {found[0]} + {found[1]} is unique: {why}"))
            pks[t] = found
        else:
            props.append(("PK", t, [f"{t}_sk"], "", [], "SI² generates", 60,
                          "no key-like column (or pair) is unique: SI² generates the key; SME may name a natural key"))

    declared = {(c, tuple(cc)) for c, cc, *_ in st.declared_fk}
    for child, ccols, parent, pcols, meth in st.declared_fk:
        if child in st.tables and parent in st.tables:
            orphans = _orphans(st, child, ccols, parent, pcols)
            props.append(("FK", child, ccols, parent, pcols, meth, 100 if not orphans else 85,
                          f"{meth.lower()}" + (f"; {orphans} child row(s) have no parent (quarantined on load)" if orphans else
                                               "; every child row has a parent")))

    for child, cdf in st.tables.items():
        if not len(cdf):
            continue
        for parent, pk in pks.items():
            if parent == child or pk == [f"{parent}_sk"] or not len(st.tables[parent]):
                continue
            pdf = st.tables[parent]
            for c in cdf.columns:
                if (child, (c,)) in declared or [c] == pks.get(child) and len(pk) == 1 and child < parent:
                    continue
                if any(p[0] == "FK" and p[1] == child and p[2][:1] == [c] and p[3] == parent for p in props):
                    continue
                name = _name_score(c, parent, pk[0])
                if name < 0.5:
                    continue
                cv, pv = _vals(cdf, c), _vals(pdf, pk[0])
                if not cv:
                    continue
                hit = len(cv & pv) / len(cv)
                if hit < 0.8:
                    continue
                miss = len(cv - pv)
                if len(pk) == 1:
                    props.append(("FK", child, [c], parent, pk, "Found in the data", int(60 + 30 * hit + 10 * min(name, 1)),
                                  f"{hit:.0%} of {child}.{c} values exist in {parent}.{pk[0]}"
                                  + (f"; {miss} value(s) have no parent (quarantined on load)" if miss else "")
                                  + ("" if (child, (c,)) in declared else "; not declared in any DDL")))
                    continue
                if types.get((parent, pk[1])) == "DATE":            # parent keyed by number + term date
                    props.append(_term_link(st, child, c, parent, pk, types, hit))
    out = pd.DataFrame(props, columns=["kind", "table", "columns", "ref_table", "ref_columns", "method", "confidence", "evidence"])
    out["conflict"] = False
    groups = defaultdict(list)
    for i in out.index[out.kind == "FK"]:
        groups[(out.at[i, "table"], out.at[i, "columns"][0])].append(i)
    for idx in groups.values():
        if len(idx) > 1:
            out.loc[idx, "conflict"] = True
            for i in idx:
                others = ", ".join(out.at[j, "ref_table"] for j in idx if j != i)
                out.at[i, "evidence"] += f". Also matches {others}: SME picks one"

    for r in prof[prof.pick_list].itertuples():
        vals = st.tables[r.table][r.column]
        counts = vals[vals != ""].value_counts()
        out.loc[len(out)] = ["PICKLIST", r.table, [r.column], "pick_list", [to_title(r.column)], "Found in the data", 85,
                             f"{len(counts)} codes: " + ", ".join(f"{k} ({v})" for k, v in counts.head(8).items()), False]
    out["status"] = "Proposed"
    out.insert(0, "id", [f"P{i:03d}" for i in range(1, len(out) + 1)])
    return out


def _term_link(st, child, c, parent, pk, types, hit):
    """Parent key is policy number + a date (one row per term). Exact pair, term in force on a child date, or latest term."""
    cdf, pdf = st.tables[child], st.tables[parent]
    a, b = pk[0], pk[1]
    pairs = set(zip(pdf[a], pdf[b]))
    child_dates = [d for d in cdf.columns if types.get((child, d)) == "DATE"]
    for d in child_dates:
        cp = set(zip(cdf[c], cdf[d].map(lambda x: parse_date(x) or x)))
        if cp and len(cp & {(x, parse_date(y) or y) for x, y in pairs}) / len(cp) >= 0.95:
            return ("FK", child, [c, d], parent, [a, b], "Found in the data", 98,
                    f"{child}.({c}, {d}) matches {parent}.({a}, {b}) exactly: the same policy term")
    exp = next((x for x in pdf.columns if x != b and types.get((parent, x)) == "DATE" and
                {"EXPIRATION", "EXP", "END", "TO"} & set(words(x))), None)
    if exp:
        for d in sorted(child_dates, key=lambda x: (not ({"LOSS", "ACCIDENT", "OCCURRENCE"} & set(words(x))), x)):
            ok = 0
            for no, when in zip(cdf[c], cdf[d]):
                when = parse_date(when)
                terms = pdf[(pdf[a] == no)]
                if when and sum(1 for s, e in zip(terms[b], terms[exp]) if (parse_date(s) or "") <= when < (parse_date(e) or "")) == 1:
                    ok += 1
            share = ok / max(len(cdf), 1)
            if share >= 0.8:
                return ("FK", child, [c, d], parent, [a, b], "Term in force on the date", int(80 + 18 * share),
                        f"{child}.{d} falls inside exactly one {parent} term ({b} ≤ {d} < {exp}) for {share:.0%} of rows; "
                        f"a link on {c} alone would attach renewals to the wrong term")
    return ("FK", child, [c], parent, [a, b], "Latest term", int(50 + 20 * hit),
            f"{hit:.0%} of {child}.{c} values exist in {parent}.{a}, but {child} has no date to pick the term: "
            f"links to the latest term; SME to confirm")


def _orphans(st, child, ccols, parent, pcols) -> int:
    cdf, pdf = st.tables[child], st.tables[parent]
    if not all(c in cdf for c in ccols) or not all(c in pdf for c in pcols) or not len(cdf):
        return 0
    have = set(map(tuple, pdf[pcols].astype(str).values.tolist()))
    keys = [tuple(r) for r in cdf[ccols].astype(str).values.tolist()]
    return sum(1 for k in keys if any(k) and k not in have)


# ============================================================================== build + load
SQLITE_TYPE = {"TEXT": "TEXT", "DATE": "TEXT", "INTEGER": "INTEGER", "DECIMAL": "REAL", "MONEY": "REAL"}
MSSQL_TYPE = {"TEXT": "NVARCHAR({n})", "DATE": "DATE", "INTEGER": "BIGINT", "DECIMAL": "DECIMAL(18,6)", "MONEY": "DECIMAL(18,2)"}


def load_order(tables: list[str], fks: list[tuple]) -> tuple[list[str], list[str]]:
    deps = {t: {p for c, p in fks if c == t and p != t and p in tables} for t in tables}
    order, cyc = [], []
    while deps:
        ready = sorted(t for t, d in deps.items() if not d - set(order))
        if not ready:
            cyc = sorted(deps)
            order += cyc
            break
        order += ready
        for t in ready:
            deps.pop(t)
    return order, cyc


def ddl(st: Staged, prof: pd.DataFrame, props: pd.DataFrame, dialect: str = "sqlite") -> str:
    ok = props[props.status == "Approved"]
    pk = {r.table: r.columns for r in ok[ok.kind == "PK"].itertuples()}
    fks = [(r.table, r.ref_table, r.columns, r.ref_columns) for r in ok[ok.kind == "FK"].itertuples()]
    order, _ = load_order(list(st.tables), [(c, p) for c, p, *_ in fks])
    out = []
    for t in order:
        p = prof[prof.table == t]
        if dialect == "sqlite":
            cols = [f"  {t}_sk INTEGER PRIMARY KEY"]
        else:
            cols = [f"  {t}_sk BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_{t} PRIMARY KEY"]
        for r in p.itertuples():
            typ = SQLITE_TYPE[r.type] if dialect == "sqlite" else MSSQL_TYPE[r.type].format(n=max(10, int(r.max_len * 1.5)))
            nn = " NOT NULL" if t in pk and r.column in pk[t] else ""
            cols.append(f"  {r.column} {typ}{nn}")
        for c, par, cc, pc in fks:
            if c == t:
                ref_type = "INTEGER" if dialect == "sqlite" else "BIGINT"
                cols.append(f"  {par}_sk {ref_type} REFERENCES {par}({par}_sk)" if dialect == "sqlite"
                            else f"  {par}_sk {ref_type} NULL CONSTRAINT FK_{t}_{par} REFERENCES {par}({par}_sk)")
        cols += ["  load_batch_id TEXT NOT NULL", "  loaded_at TEXT NOT NULL", "  effective_from TEXT NOT NULL",
                 f"  effective_to TEXT NOT NULL DEFAULT '{FAR_FUTURE}'"] if dialect == "sqlite" else \
            ["  load_batch_id NVARCHAR(40) NOT NULL", "  loaded_at DATETIME2 NOT NULL", "  effective_from DATE NOT NULL",
             f"  effective_to DATE NOT NULL CONSTRAINT DF_{t}_eff_to DEFAULT '{FAR_FUTURE}'"]
        if t in pk and pk[t] != [f"{t}_sk"]:
            cols.append(f"  CONSTRAINT UQ_{t}_business_key UNIQUE ({', '.join(pk[t])}, effective_from)")
        out.append(f"CREATE TABLE {t} (\n" + ",\n".join(cols) + "\n);")
    if (ok.kind == "PICKLIST").any():
        out.append("CREATE TABLE pick_list (\n  list_name TEXT NOT NULL,\n  code TEXT NOT NULL,\n  description TEXT,\n"
                   "  source_table TEXT, source_column TEXT,\n  effective_from TEXT NOT NULL,\n"
                   f"  effective_to TEXT NOT NULL DEFAULT '{FAR_FUTURE}',\n  PRIMARY KEY (list_name, code, effective_from)\n);"
                   if dialect == "sqlite" else
                   "CREATE TABLE pick_list (\n  list_name NVARCHAR(80) NOT NULL,\n  code NVARCHAR(40) NOT NULL,\n"
                   "  description NVARCHAR(200) NULL,\n  source_table NVARCHAR(80) NULL, source_column NVARCHAR(80) NULL,\n"
                   f"  effective_from DATE NOT NULL,\n  effective_to DATE NOT NULL DEFAULT '{FAR_FUTURE}',\n"
                   "  CONSTRAINT PK_pick_list PRIMARY KEY (list_name, code, effective_from)\n);")
    header = (f"-- SI² initial load: {dialect.upper()} DDL generated {dt.datetime.now():%Y-%m-%d %H:%M}\n"
              "-- Surrogate key <table>_sk; the natural key is kept as a unique business key; children reference <parent>_sk.\n")
    return header + "\n\n".join(out) + "\n"


def _convert(v: str, typ: str):
    if v == "":
        return None, ""
    if typ == "DATE":
        d = parse_date(v)
        return (d, "") if d else (None, f"'{v}' is not a date")
    if typ in ("MONEY", "DECIMAL"):
        m = parse_money(v)
        return (m, "") if m is not None else (None, f"'{v}' is not an amount")
    if typ == "INTEGER":
        try:
            return int(str(v).replace(",", "")), ""
        except ValueError:
            return None, f"'{v}' is not a whole number"
    return v, ""


def build_and_load(st: Staged, prof: pd.DataFrame, props: pd.DataFrame, db_path: str, actor: str) -> dict:
    ok = props[props.status == "Approved"]
    batch = f"IL-{dt.datetime.now():%Y%m%d-%H%M%S}"
    now = dt.datetime.now().isoformat(sep=" ", timespec="seconds")
    today = dt.date.today().isoformat()
    Path(db_path).unlink(missing_ok=True)
    con = sqlite3.connect(db_path)
    con.execute("PRAGMA foreign_keys = ON")
    con.executescript(ddl(st, prof, props, "sqlite"))
    types = {(r.table, r.column): r.type for r in prof.itertuples()}
    fks = [(r.table, r.ref_table, list(r.columns), list(r.ref_columns), r.method) for r in ok[ok.kind == "FK"].itertuples()]
    order, cycles = load_order(list(st.tables), [(c, p) for c, p, *_ in fks])
    keys = {}                    # table -> (business key tuple -> sk), plus term index
    recon, quarantine = [], []
    for t in order:
        df = st.tables[t]
        cols = list(df.columns)
        my_fks = [f for f in fks if f[0] == t]
        rows, sks = [], {}
        for i, rec in enumerate(df.to_dict("records"), 1):
            vals, why = [], []
            for c in cols:
                v, err = _convert(str(rec[c]), types.get((t, c), "TEXT"))
                vals.append(v)
                if err:
                    why.append(f"{c}: {err}")
            refs = []
            for _, par, cc, pc, meth in my_fks:
                sk, err = _resolve(keys.get(par), rec, cc, pc, meth)
                refs.append(sk)
                if err:
                    why.append(f"{par}: {err}")
            if why:
                quarantine.append({"table": t, "row": i, "reason": "; ".join(why),
                                   "record": ", ".join(f"{k}={v}" for k, v in list(rec.items())[:6])})
                continue
            rows.append((i, vals + refs + [batch, now, today]))
        names = cols + [f"{f[1]}_sk" for f in my_fks] + ["load_batch_id", "loaded_at", "effective_from"]
        sql = f"INSERT INTO {t} ({', '.join(names)}) VALUES ({', '.join('?' * len(names))})"
        loaded = 0
        for i, v in rows:
            try:
                cur = con.execute(sql, v)
                sks[i] = cur.lastrowid
                loaded += 1
            except sqlite3.IntegrityError as exc:
                quarantine.append({"table": t, "row": i, "reason": f"database rejected it: {exc}",
                                   "record": ", ".join(f"{k}={x}" for k, x in list(zip(cols, v))[:6])})
        keys[t] = _key_index(df, sks, ok, t, types)
        money = [c for c in cols if types.get((t, c)) in ("MONEY", "DECIMAL")]
        src_tot = {c: round(sum(parse_money(x) or 0 for x in df[c] if x != ""), 2) for c in money}
        db_tot = {c: round(con.execute(f"SELECT COALESCE(SUM({c}),0) FROM {t}").fetchone()[0], 2) for c in money}
        q_rows = [q for q in quarantine if q["table"] == t]
        q_idx = [q["row"] - 1 for q in q_rows]
        q_tot = {c: round(sum(parse_money(x) or 0 for x in df.iloc[q_idx][c] if x != ""), 2) for c in money}
        bal = all(abs(src_tot[c] - db_tot[c] - q_tot[c]) < 0.01 for c in money)
        recon.append({"table": t, "source rows": len(df), "loaded": loaded, "quarantined": len(q_rows),
                      "rows balance": "PASS" if loaded + len(q_rows) == len(df) else "FAIL",
                      "control totals": "; ".join(f"{c}: source {src_tot[c]:,.2f} = loaded {db_tot[c]:,.2f}"
                                                  + (f" + quarantined {q_tot[c]:,.2f}" if q_tot[c] else "") for c in money) or "—",
                      "totals balance": ("PASS" if bal else "FAIL") if money else "—"})
    for r in ok[ok.kind == "PICKLIST"].itertuples():
        t, c = r.table, r.columns[0]
        for code in sorted(set(x for x in st.tables[t][c] if x != "")):
            con.execute("INSERT OR IGNORE INTO pick_list VALUES (?,?,?,?,?,?,?)",
                        (r.ref_columns[0], code, "", t, c, today, FAR_FUTURE))
    con.commit()
    fk_problems = con.execute("PRAGMA foreign_key_check").fetchall()
    con.close()
    return {"batch": batch, "by": actor, "order": order, "cycles": cycles, "recon": pd.DataFrame(recon),
            "quarantine": pd.DataFrame(quarantine, columns=["table", "row", "reason", "record"]),
            "fk_violations": len(fk_problems), "db_path": db_path}


def _key_index(df, sks, ok, t, types):
    pk = next((list(r.columns) for r in ok[(ok.kind == "PK") & (ok.table == t)].itertuples()), None)
    idx = {"exact": {}, "first": defaultdict(list), "pk": pk}
    if not pk or pk == [f"{t}_sk"] or not all(c in df for c in pk):
        return idx
    for i, rec in enumerate(df.to_dict("records"), 1):
        if i not in sks:
            continue
        key = tuple(parse_date(rec[c]) or rec[c] if types.get((t, c)) == "DATE" else str(rec[c]) for c in pk)
        idx["exact"][key] = sks[i]
        exp = next((c for c in df.columns if c not in pk and types.get((t, c)) == "DATE"
                    and {"EXPIRATION", "EXP", "END", "TO"} & set(words(c))), None)
        idx["first"][str(rec[pk[0]])].append((key[1] if len(key) > 1 else "", parse_date(rec[exp]) if exp else None, sks[i]))
    return idx


def _resolve(idx, rec, cc, pc, meth):
    if not idx or idx["pk"] is None:
        return None, ""
    vals = [str(rec[c]) for c in cc]
    if not any(vals):
        return None, ""
    if meth == "Term in force on the date":
        when = parse_date(vals[1])
        hits = [sk for start, end, sk in idx["first"].get(vals[0], []) if when and start <= when < (end or FAR_FUTURE)]
        return (hits[0], "") if len(hits) == 1 else (None, f"no term of {vals[0]} in force on {vals[1]}")
    if meth == "Latest term":
        terms = idx["first"].get(vals[0], [])
        return (max(terms)[2], "") if terms else (None, f"{vals[0]} not found")
    key = tuple(parse_date(v) or v for v in vals) if len(vals) > 1 else (vals[0],)
    sk = idx["exact"].get(key)
    return (sk, "") if sk else (None, f"{'/'.join(vals)} not found (orphan)")
