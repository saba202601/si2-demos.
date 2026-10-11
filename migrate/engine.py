"""SI² Legacy-to-Cloud migration engine.

discover()        every legacy element: type, length, pick list name and values, aliases, samples
build_canonical() canonical model generated from the destination schema + insurance synonyms
match()           source element -> canonical element, with confidence (SME can edit synonyms / overrides)
value_maps()      legacy pick-list value -> destination pick-list code, with confidence
transform()       legacy rows -> canonical tables -> destination tables
load()            inject destination tables into the cloud database (SQLite in the demo)
reconcile()       counts, control totals, integrity, sample record and business-rule tests
"""
from __future__ import annotations

import datetime as dt
import re
import sqlite3

import pandas as pd

from . import legacy

# ------------------------------------------------------------------------------------------ vocabulary
ABBR = {
    "NO": "NUMBER", "NBR": "NUMBER", "NUM": "NUMBER", "CD": "CODE", "EFF": "EFFECTIVE", "EXP": "EXPIRATION",
    "DT": "DATE", "PREM": "PREMIUM", "AGT": "AGENT", "ST": "STATE", "STAT": "STATUS", "COV": "COVERAGE",
    "LMT": "LIMIT", "DED": "DEDUCTIBLE", "AMT": "AMOUNT", "CNT": "COUNT", "PAY": "PAYMENT", "POL": "POLICY",
    "CLM": "CLAIM", "OS": "OUTSTANDING", "LOB": "LINE OF BUSINESS", "PERS": "PERSONAL", "LIAB": "LIABILITY",
    "COMP": "COMPENSATION", "ADDR": "ADDRESS", "TEL": "PHONE", "SEQ": "SEQUENCE", "OCCURRENCE": "SEQUENCE",
}
STOP = {"OF", "THE", "AND", "FROM", "A", "AN", "IN"}

# Standard P&C synonyms seeded into the canonical model (SME can add more in the app)
SEED = {
    "policy_number": ["policy number", "policy id", "contract number"],
    "line_of_business": ["line of business", "lob", "product line"],
    "policy_status": ["policy status", "status"],
    "effective_date": ["effective date", "inception date", "policy effective date"],
    "expiration_date": ["expiration date", "expiry date", "policy expiration date"],
    "base_state": ["state", "base state", "risk state", "primary state"],
    "written_premium": ["written premium", "policy premium", "total premium"],
    "payment_plan": ["payment plan", "billing plan", "pay plan"],
    "producer_code": ["producer code", "agent number", "agent code", "producer number"],
    "full_name": ["full name", "name", "insured full name"],
    "email": ["email", "email address", "insured email"],
    "phone": ["phone", "phone number", "insured phone", "telephone"],
    "mailing_address": ["mailing address", "address", "insured address"],
    "producer_name": ["producer name", "agent name", "agency name"],
    "producer_state": ["producer state", "agent state"],
    "coverage_type": ["coverage type", "coverage code"],
    "limit_amount": ["limit amount", "coverage limit", "limit"],
    "deductible_amount": ["deductible amount", "coverage deductible", "deductible"],
    "coverage_premium": ["coverage premium"],
    "claim_number": ["claim number", "claim id"],
    "loss_date": ["loss date", "date of loss", "accident date"],
    "loss_cause": ["loss cause", "cause of loss", "cause code"],
    "claim_status": ["claim status", "status"],
    "outstanding_reserve": ["outstanding reserve", "case reserve"],
    "repair_estimate": ["repair estimate", "estimate"],
    "attorney_involved": ["attorney involved", "attorney flag", "litigated"],
    "payment_sequence": ["payment sequence", "sequence"],
    "payment_date": ["payment date", "paid date", "check date"],
    "payment_amount": ["payment amount", "paid amount"],
}
# Which canonical entity a legacy entity naturally describes (used to break ties)
CONTEXT = {"POLMAST": "Policy", "CLMMAST": "Claim", "CLMMAST.CL-PAYMENT": "ClaimPayment", "AGENT": "Producer",
           "COVERAGE": "Coverage", "POLICY_CHANGE_FORMS": "Party", "CLAIM_NOTES": "Claim"}
PRIORITY = {"COBOL copybook + VSAM data": 1, "COBOL OCCURS group": 1, "DB2 table": 2, "PDF forms": 3,
            "Free-text notes": 4}
NOT_MIGRATED = "(not migrated · archive only)"


def pascal(s: str) -> str:
    return "".join(w.capitalize() for w in re.split(r"[_\s]+", s) if w)


def tokens(text: str, strip_prefix: str = "") -> list[str]:
    """Business words of a name: split, drop record prefix, expand abbreviations."""
    words = [w for w in re.split(r"[^A-Za-z0-9]+", re.sub(r"([a-z])([A-Z])", r"\1 \2", str(text))) if w]
    words = [w.upper() for w in words]
    if strip_prefix and words and words[0] == strip_prefix:
        words = words[1:]
    out = []
    for w in words:
        out.extend(ABBR.get(w, w).split())
    return [w for w in out if w not in STOP]


WEAK = {"CODE"}          # "PM-LOB-CD" and "line of business" describe the same thing


def similarity(a: list[str], b: list[str]) -> float:
    A, B = set(a) - WEAK or set(a), set(b) - WEAK or set(b)
    if not A or not B:
        return 0.0
    if A == B:
        return 1.0
    return len(A & B) / len(A | B)


# ------------------------------------------------------------------------------------------ discovery
def _infer(series: pd.Series) -> tuple[str, int]:
    s = series.dropna().astype(str).str.strip()
    s = s[s != ""]
    if s.empty:
        return "text", 0
    length = int(s.str.len().max())
    if s.str.fullmatch(r"\d{4}-\d{2}-\d{2}|\d{2}/\d{2}/\d{4}").all():
        return "date", length
    if s.str.fullmatch(r"[^@\s]+@[^@\s]+\.[a-z]+").all():
        return "email", length
    if s.str.fullmatch(r"\(?\d{3}\)?[\s-]?\d{3}-\d{4}").all():
        return "phone", length
    if s.str.fullmatch(r"-?\d+").all():
        return "integer", length
    if s.str.fullmatch(r"-?\d+(\.\d+)?").all():
        return "decimal", length
    if set(s.unique()) <= {"Y", "N"}:
        return "flag", 1
    return "text", length


def _strip_common(names: list[str]) -> list[str]:
    """88-level names PM-STAT-ACTIVE, PM-STAT-CANCELLED -> ACTIVE, CANCELLED."""
    parts = [n.split("-") for n in names]
    k = 0
    while len(parts) > 1 and all(len(p) > k + 1 for p in parts) and len({p[k] for p in parts}) == 1:
        k += 1
    return [" ".join(p[k:]) for p in parts]


def discover(src: dict) -> pd.DataFrame:
    """Inventory every legacy element."""
    code_table = src.get("code_table")
    tables = {}
    if code_table is not None and len(code_table):
        for tid, g in code_table.groupby("TABLE_ID"):
            tables[tid] = dict(zip(g.CODE, g.DESCRIPTION))
    rows = []
    for ent, info in src["entities"].items():
        df, stype = info["df"], info["type"]
        layout = src["layouts"].get(ent.split(".")[0])
        prefix = ""
        if layout is not None:
            heads = layout.name.str.split("-").str[0]
            prefix = heads.mode().iat[0] if len(heads) else ""
        for col in df.columns:
            if col in ("FORM_FILE",):
                continue
            s = df[col]
            pick_name, pick_vals, pic = "", {}, ""
            lay = layout[layout.name == col] if layout is not None else None
            if lay is not None and len(lay):
                r = lay.iloc[0]
                pic = r.pic
                typ = {"text": "text", "number": "integer", "decimal": "decimal"}[r.type]
                length = int(r.length)
                if "DATE" in col and r.type == "number":
                    typ = "date (YYYYMMDD)"
                if r.pick_list:
                    pick_name = f"{col} (88-levels)"
                    pick_vals = dict(zip(r.pick_list.keys(), _strip_common(list(r.pick_list.values()))))
            else:
                typ, length = _infer(s)
                if col == "OCCURRENCE":
                    typ, pic = "integer", "OCCURS index"
            vals = set(s.dropna().astype(str).str.strip()) - {""}
            if not pick_vals and vals and typ == "text":
                for tid, codes in tables.items():
                    if len(vals & set(codes)) / len(vals) >= 0.8:
                        pick_name, pick_vals = f"CODE_TABLE {tid}", dict(codes)
                        break
            if not pick_vals and typ == "flag":
                pick_name, pick_vals = "Y/N flag", {"Y": "YES", "N": "NO"}
            samples = list(dict.fromkeys(s.dropna().astype(str).str.strip()))[:3]
            rows.append({
                "element_id": f"{ent}.{col}", "entity": ent, "source_type": stype, "element": col,
                "data_type": typ, "pic": pic, "length": length,
                "pick_list": pick_name, "pick_values": "; ".join(f"{k}={v}" for k, v in pick_vals.items()),
                "alias": " ".join(tokens(col, prefix)).title(), "tokens": tokens(col, prefix), "prefix": prefix,
                "pick": pick_vals, "distinct": len(vals), "null_pct": round(100 * s.isna().mean(), 1),
                "samples": ", ".join(samples)})
    return pd.DataFrame(rows)


# ------------------------------------------------------------------------------------------ canonical model
def build_canonical(dest_schema: pd.DataFrame, dest_picklists: pd.DataFrame, extra_syn: dict | None = None) -> pd.DataFrame:
    """One canonical element per business concept in the destination; shared keys merge into one element."""
    ds = dest_schema.fillna("")
    if "key" not in ds.columns:
        ds["key"] = ""
        ds.loc[ds.groupby("table").head(1).index, "key"] = "Y"
    pk_owner = {}
    for tbl, g in ds.groupby("table", sort=False):
        k = g[g.key == "Y"]
        if len(k) == 1:
            pk_owner.setdefault(k.field.iat[0], tbl)
    rows = {}
    for r in ds.itertuples():
        owner = pk_owner.get(r.field, r.table)
        cid = f"{pascal(owner)}.{pascal(r.field)}"
        if cid not in rows:
            syn = list(SEED.get(r.field, []))
            base = r.field.replace("_", " ")
            if base not in syn:
                syn.insert(0, base)
            syn += (extra_syn or {}).get(cid, [])
            rows[cid] = {"canonical_id": cid, "entity": pascal(owner), "attribute": pascal(r.field),
                         "data_type": r.type, "length": r.length, "pick_list": r.pick_list,
                         "synonyms": ", ".join(dict.fromkeys(syn)), "description": r.description,
                         "destination_fields": [], "required": False}
        rows[cid]["destination_fields"].append(f"{r.table}.{r.field}")
        rows[cid]["required"] |= r.required == "Y"
    can = pd.DataFrame(rows.values())
    can["destination_fields"] = can.destination_fields.apply(", ".join)
    return can


def dest_field_to_canon(canon: pd.DataFrame) -> dict:
    out = {}
    for r in canon.itertuples():
        for f in r.destination_fields.split(", "):
            out[f] = r.canonical_id
    return out


# ------------------------------------------------------------------------------------------ matching
TYPE_OK = {
    "date": {"date", "date (YYYYMMDD)"}, "decimal": {"decimal", "integer"}, "integer": {"integer"},
    "boolean": {"flag"}, "string": {"text", "email", "phone", "integer"}, "picklist": {"text"},
}


def match(inv: pd.DataFrame, canon: pd.DataFrame, overrides: dict | None = None) -> pd.DataFrame:
    """Source element -> canonical element with confidence. overrides: element_id -> canonical_id/NOT_MIGRATED."""
    overrides = overrides or {}
    syn = {r.canonical_id: [tokens(p) for p in r.synonyms.split(",") if p.strip()] for r in canon.itertuples()}
    ctype = dict(zip(canon.canonical_id, canon.data_type))
    centity = dict(zip(canon.canonical_id, canon.entity))
    out = []
    for e in inv.itertuples():
        scored = []
        for cid, phrases in syn.items():
            s = max((similarity(e.tokens, p) for p in phrases), default=0)
            if e.data_type not in TYPE_OK.get(ctype[cid], {e.data_type}):
                s *= 0.5
            if centity[cid] == CONTEXT.get(e.entity):
                s += 0.001                                    # tie-break toward the entity's own concept
            scored.append((s, cid))
        scored.sort(reverse=True)
        best, cid = scored[0]
        conf = round(min(best, 1) * 100)
        if e.element_id in overrides:
            target, status, how = overrides[e.element_id], "SME approved", "SME"
        elif conf >= 90:
            target, status, how = cid, "Auto-mapped", "Synonym match"
        else:
            target, status, how = (cid if conf >= 60 else ""), "Needs SME review", "Suggested" if conf >= 60 else "No match"
        out.append({"element_id": e.element_id, "entity": e.entity, "element": e.element, "alias": e.alias,
                    "data_type": e.data_type, "suggested": cid if conf >= 30 else "", "confidence": conf, "canonical_id": target,
                    "status": status, "method": how})
    m = pd.DataFrame(out)
    m["destination_fields"] = m.canonical_id.map(dict(zip(canon.canonical_id, canon.destination_fields))).fillna("")
    return m


def coverage(m: pd.DataFrame, canon: pd.DataFrame, vm: pd.DataFrame) -> dict:
    decided = m.status != "Needs SME review"
    mapped_canon = set(m.loc[decided & (m.canonical_id != NOT_MIGRATED), "canonical_id"])
    req = canon[canon.required]
    v_ok = (vm.status != "Needs SME review") if len(vm) else pd.Series(dtype=bool)
    parts = {
        "Source elements decided": (int(decided.sum()), len(m)),
        "Destination fields sourced": (int(canon.canonical_id.isin(mapped_canon).sum()), len(canon)),
        "Required fields sourced": (int(req.canonical_id.isin(mapped_canon).sum()), len(req)),
        "Pick-list values mapped": (int(v_ok.sum()), len(vm)),
    }
    done = sum(a for a, _ in parts.values())
    total = sum(b for _, b in parts.values())
    return {"parts": parts, "pct": round(100 * done / total, 1) if total else 100.0,
            "missing_required": sorted(set(req.canonical_id) - mapped_canon),
            "missing_any": sorted(set(canon.canonical_id) - mapped_canon)}


# ------------------------------------------------------------------------------------------ value maps
def _value_score(desc_tokens, code, desc):
    best = 0.0
    for target in (tokens(code), tokens(desc)):
        if not target:
            continue
        S, T = set(desc_tokens), set(target)
        jac = similarity(desc_tokens, target)
        contain = len(S & T) / len(S) if S else 0
        best = max(best, jac if jac == 1 else 0.5 * jac + 0.5 * contain)
    return best


def value_maps(inv: pd.DataFrame, m: pd.DataFrame, canon: pd.DataFrame, picklists: pd.DataFrame,
               overrides: dict | None = None) -> pd.DataFrame:
    """For every mapped picklist element: each legacy value -> destination code. overrides: (element_id, value) -> code."""
    overrides = overrides or {}
    cpl = dict(zip(canon.canonical_id, canon.pick_list))
    out = []
    for e in m[m.canonical_id.isin([c for c, p in cpl.items() if p])].itertuples():
        pl = cpl[e.canonical_id]
        codes = picklists[picklists.pick_list == pl]
        legacy_vals = inv.set_index("element_id").at[e.element_id, "pick"]
        if not legacy_vals:
            src_df = None
            legacy_vals = {}
        for val, desc in legacy_vals.items():
            dtoks = tokens(desc)
            scored = sorted(((_value_score(dtoks, c.code, c.description), c.code) for c in codes.itertuples()),
                            reverse=True)
            s, code = scored[0] if scored else (0, "")
            conf = round(s * 100)
            key = (e.element_id, val)
            if key in overrides:
                tgt, status = overrides[key], "SME approved"
            elif conf >= 90:
                tgt, status = code, "Auto-mapped"
            else:
                tgt, status = (code if conf >= 50 else ""), "Needs SME review"
            out.append({"element_id": e.element_id, "pick_list": pl, "legacy_value": val, "legacy_meaning": desc,
                        "suggested": code if conf >= 40 else "", "confidence": conf, "destination_code": tgt,
                        "status": status})
    return pd.DataFrame(out, columns=["element_id", "pick_list", "legacy_value", "legacy_meaning", "suggested",
                                      "confidence", "destination_code", "status"])


# ------------------------------------------------------------------------------------------ transform
def _date(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    s = str(v).strip()
    if s in ("", "0", "00000000"):
        return None
    for fmt in ("%Y%m%d", "%Y-%m-%d", "%m/%d/%Y"):
        try:
            return dt.datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            pass
    return s


def _name(v):
    s = str(v).strip()
    if "," in s:
        last, first = [x.strip() for x in s.split(",", 1)]
        s = f"{first} {last}"
    return s.title() if s.isupper() else s


def rule_for(e_type: str, c_type: str, samples: str, pick: bool, description: str = "") -> str:
    if pick:
        return "Value map → pick-list code"
    if c_type == "date":
        return "Date → ISO YYYY-MM-DD" + (" (from YYYYMMDD)" if "YYYYMMDD" in e_type else "")
    if c_type == "boolean":
        return "Y/N → true/false"
    if c_type == "decimal":
        return "Implied decimal (V99) → decimal" if e_type == "decimal" else "Number → decimal"
    if "First Last" in description and re.search(r"[A-Z]+, [A-Z]+", samples or ""):
        return "Name 'LAST, FIRST' → 'First Last'"
    return "Trim / copy"


def convert(v, rule: str, vmap: dict | None = None):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    if rule.startswith("Value map"):
        return (vmap or {}).get(str(v).strip())
    if rule.startswith("Date"):
        return _date(v)
    if rule.startswith("Y/N"):
        return {"Y": 1, "N": 0}.get(str(v).strip().upper())
    if rule.startswith(("Implied", "Number")):
        try:
            return round(float(v), 2)
        except ValueError:
            return None
    if rule.startswith("Name"):
        return _name(v)
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(v).strip()


def mapping_view(inv, m, canon, vm) -> pd.DataFrame:
    """Source → Canonical → Destination with the transformation rule, for the SME."""
    c = canon.set_index("canonical_id")
    iv = inv.set_index("element_id")
    rows = []
    for r in m.itertuples():
        mapped = r.canonical_id and r.canonical_id != NOT_MIGRATED
        rule = ""
        if mapped:
            cr = c.loc[r.canonical_id]
            rule = rule_for(r.data_type, cr.data_type, iv.at[r.element_id, "samples"], bool(cr.pick_list), cr.description)
        rows.append({"Source": r.element_id, "Source type": iv.at[r.element_id, "source_type"],
                     "Alias": r.alias, "Rule": rule, "Canonical": r.canonical_id or "—",
                     "Destination": r.destination_fields or "—", "Confidence": r.confidence, "Status": r.status})
    return pd.DataFrame(rows)


def transform(src, inv, m, canon, vm, dest_schema) -> tuple[dict, dict, pd.DataFrame]:
    """Build canonical tables (one per canonical entity) and destination tables. Returns (canonical, destination, issues)."""
    ds = dest_schema.fillna("")
    if "key" not in ds.columns:
        ds["key"] = ""
        ds.loc[ds.groupby("table").head(1).index, "key"] = "Y"
    f2c = dest_field_to_canon(canon)
    c = canon.set_index("canonical_id")
    iv = inv.set_index("element_id")
    live = m[(m.canonical_id != "") & (m.canonical_id != NOT_MIGRATED) & (m.status != "Needs SME review")]
    vmaps = {}
    for r in vm.itertuples():
        if r.destination_code:
            vmaps.setdefault(r.element_id, {})[r.legacy_value] = r.destination_code
    canonical, dest, issues = {}, {}, []
    for tbl, g in ds.groupby("table", sort=False):
        fields = list(g.field)
        keys = list(g[g.key == "Y"].field)
        cids = {f: f2c[f"{tbl}.{f}"] for f in fields}
        key_c = [cids[k] for k in keys]
        # every legacy entity that carries the full key and at least one other field of this table contributes
        contrib = []
        for ent, em in live.groupby("entity"):
            have = dict(zip(em.canonical_id, em.element))
            if all(k in have for k in key_c) and any(cids[f] in have for f in fields if f not in keys):
                contrib.append((PRIORITY.get(src["entities"][ent]["type"], 9), ent, have))
        contrib.sort()
        frames = []
        for pri, ent, have in contrib:
            df = src["entities"][ent]["df"]
            part = pd.DataFrame(index=df.index)
            for f in fields:
                cid = cids[f]
                if cid not in have:
                    continue
                eid = f"{ent}.{have[cid]}"
                cr = c.loc[cid]
                rule = rule_for(iv.at[eid, "data_type"], cr.data_type, iv.at[eid, "samples"], bool(cr.pick_list),
                                cr.description)
                part[f] = [convert(v, rule, vmaps.get(eid)) for v in df[have[cid]]]
                if cr.pick_list:
                    unmapped = df[have[cid]][part[f].isna() & df[have[cid]].notna()]
                    for v in sorted(set(unmapped.astype(str))):
                        issues.append({"table": tbl, "field": f, "issue": f"Legacy value '{v}' in {eid} has no destination code",
                                       "rows": int((unmapped.astype(str) == v).sum())})
            part = part.drop_duplicates(subset=keys)
            frames.append((ent, part))
        if not frames:
            issues.append({"table": tbl, "field": "*", "issue": "No legacy source mapped to this table", "rows": 0})
            dest[tbl] = pd.DataFrame(columns=fields)
            canonical[pascal(tbl)] = pd.DataFrame(columns=[cids[f].split(".")[1] for f in fields])
            continue
        merged, lineage = None, {}
        for ent, part in frames:                      # highest-priority source first; others fill gaps
            part = part.set_index(keys)
            for k in part.index:
                lineage.setdefault(k, []).append(ent)
            if merged is not None:                    # cross-source check: same fact, different value?
                both = merged.index.intersection(part.index)
                for col in part.columns.intersection(merged.columns):
                    a, b = merged.loc[both, col], part.loc[both, col]
                    diff = a.notna() & b.notna() & (a.astype(str) != b.astype(str))
                    if diff.any():
                        issues.append({"table": tbl, "field": col, "rows": int(diff.sum()),
                                       "issue": f"{ent} disagrees with {frames[0][0]} (primary value kept)"})
            merged = part if merged is None else merged.combine_first(part)
        out = merged.reset_index()
        for f in fields:
            if f not in out.columns:
                out[f] = None
        out = out[fields].sort_values(keys).reset_index(drop=True)
        dest[tbl] = out
        can = out.rename(columns={f: cids[f].split(".")[1] for f in fields})
        kv = [tuple(x) if len(keys) > 1 else x[0] for x in out[keys].itertuples(index=False)]
        can["_lineage"] = [" + ".join(lineage.get(k, [])) for k in kv]
        canonical[pascal(tbl)] = can
    return canonical, dest, pd.DataFrame(issues, columns=["table", "field", "issue", "rows"])


def validate(dest: dict, dest_schema: pd.DataFrame, picklists: pd.DataFrame) -> pd.DataFrame:
    """Destination load rules: required, length, pick-list membership, type."""
    ds = dest_schema.fillna("")
    allowed = picklists.groupby("pick_list").code.apply(set).to_dict()
    errs = []
    for r in ds.itertuples():
        df = dest.get(r.table)
        if df is None or r.field not in df.columns:
            continue
        col = df[r.field]
        if r.required == "Y":
            n = int(col.isna().sum())
            if n:
                errs.append({"table": r.table, "field": r.field, "rule": "Required", "failed_rows": n})
        if r.length and r.type in ("string", "picklist"):
            n = int(col.dropna().astype(str).str.len().gt(int(r.length)).sum())
            if n:
                errs.append({"table": r.table, "field": r.field, "rule": f"Max length {r.length}", "failed_rows": n})
        if r.pick_list:
            n = int((~col.dropna().isin(allowed.get(r.pick_list, set()))).sum())
            if n:
                errs.append({"table": r.table, "field": r.field, "rule": f"Pick list {r.pick_list}", "failed_rows": n})
        if r.type == "date":
            n = int((~col.dropna().astype(str).str.fullmatch(r"\d{4}-\d{2}-\d{2}")).sum())
            if n:
                errs.append({"table": r.table, "field": r.field, "rule": "ISO date", "failed_rows": n})
    return pd.DataFrame(errs, columns=["table", "field", "rule", "failed_rows"])


# ------------------------------------------------------------------------------------------ load
SQLTYPE = {"string": "TEXT", "picklist": "TEXT", "date": "TEXT", "decimal": "NUMERIC", "integer": "INTEGER",
           "boolean": "INTEGER"}


def load(dest: dict, dest_schema: pd.DataFrame, path: str = ":memory:") -> sqlite3.Connection:
    """Inject destination tables into the cloud database (DDL generated from the destination schema)."""
    con = sqlite3.connect(path, check_same_thread=False)
    ds = dest_schema.fillna("")
    for tbl, g in ds.groupby("table", sort=False):
        cols = ", ".join(f"{r.field} {SQLTYPE.get(r.type, 'TEXT')}{' NOT NULL' if r.required == 'Y' else ''}"
                         for r in g.itertuples())
        keys = list(g[g.get("key", pd.Series("", index=g.index)) == "Y"].field) if "key" in g else []
        pk = f", PRIMARY KEY ({', '.join(keys)})" if keys else ""
        con.execute(f"DROP TABLE IF EXISTS {tbl}")
        con.execute(f"CREATE TABLE {tbl} ({cols}{pk})")
        df = dest[tbl][list(g.field)]
        con.executemany(f"INSERT INTO {tbl} VALUES ({', '.join('?' * len(g))})",
                        [tuple(None if pd.isna(v) else v for v in row) for row in df.itertuples(index=False)])
    con.commit()
    return con


def ddl(dest_schema: pd.DataFrame) -> str:
    ds = dest_schema.fillna("")
    out = []
    for tbl, g in ds.groupby("table", sort=False):
        cols = [f"  {r.field:<22} {SQLTYPE.get(r.type, 'TEXT')}{' NOT NULL' if r.required == 'Y' else ''}"
                for r in g.itertuples()]
        if "key" in g and (g.key == "Y").any():
            cols.append(f"  PRIMARY KEY ({', '.join(g[g.key == 'Y'].field)})")
        out.append(f"CREATE TABLE {tbl} (\n" + ",\n".join(cols) + "\n);")
    return "\n\n".join(out)


# ------------------------------------------------------------------------------------------ reconcile
def reconcile(src, m, con) -> dict:
    """Legacy vs destination: row counts, control totals and referential integrity."""
    live = m[(m.canonical_id != "") & (m.canonical_id != NOT_MIGRATED) & (m.status != "Needs SME review")]
    counts, totals = [], []
    dest_counts = {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                   for (t,) in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    # expected rows = distinct legacy keys for each table, using the entity that owns the table's concept
    for ent, info in src["entities"].items():
        tbl = {"Policy": "policy", "Claim": "claim", "ClaimPayment": "claim_payment", "Producer": "producer",
               "Coverage": "coverage"}.get(CONTEXT.get(ent, ""))
        if not tbl or tbl not in dest_counts or info["type"] == "Free-text notes":
            continue
        counts.append({"check": f"{ent} records → {tbl}", "legacy": len(info["df"]), "destination": dest_counts[tbl]})
    if "POLMAST" in src["entities"] and "party" in dest_counts:
        counts.append({"check": "POLMAST insureds → party", "legacy": len(src["entities"]["POLMAST"]["df"]),
                       "destination": dest_counts["party"]})
    if "CLMMAST" in src["entities"] and "claim_payment" in dest_counts:
        df = src["entities"]["CLMMAST"]["df"]
        if "CL-PAY-CNT" in df:
            counts.append({"check": "Σ CL-PAY-CNT → claim_payment", "legacy": int(df["CL-PAY-CNT"].sum()),
                           "destination": dest_counts["claim_payment"]})
    cdf = pd.DataFrame(counts)
    if len(cdf):
        cdf["result"] = (cdf.legacy == cdf.destination).map({True: "PASS", False: "FAIL"})
    # control totals: every numeric amount mapped from a primary (COBOL/DB) source
    for r in live.itertuples():
        stype = src["entities"][r.entity]["type"]
        if r.data_type not in ("decimal",) or not r.destination_fields:
            continue
        legacy_sum = pd.to_numeric(src["entities"][r.entity]["df"][r.element], errors="coerce").sum()
        for f in r.destination_fields.split(", "):
            t, col = f.split(".")
            if t not in dest_counts:
                continue
            d = con.execute(f"SELECT COALESCE(SUM({col}),0) FROM {t}").fetchone()[0]
            totals.append({"control total": f"{r.element_id} → {f}", "legacy": round(float(legacy_sum), 2),
                           "destination": round(float(d), 2), "source": stype})
    tdf = pd.DataFrame(totals)
    if len(tdf):
        tdf["difference"] = (tdf.destination - tdf.legacy).round(2)
        tdf["result"] = tdf.difference.abs().lt(0.005).map({True: "PASS", False: "FAIL"})
        # Notes are sparse (one per claim): the destination should equal the notes sum as well
    integrity = []
    for child, col, parent, pcol in [("policy", "producer_code", "producer", "producer_code"),
                                     ("party", "policy_number", "policy", "policy_number"),
                                     ("coverage", "policy_number", "policy", "policy_number"),
                                     ("claim", "policy_number", "policy", "policy_number"),
                                     ("claim_payment", "claim_number", "claim", "claim_number")]:
        if child in dest_counts and parent in dest_counts:
            n = con.execute(f"SELECT COUNT(*) FROM {child} c LEFT JOIN {parent} p ON c.{col}=p.{pcol} "
                            f"WHERE p.{pcol} IS NULL").fetchone()[0]
            integrity.append({"relationship": f"{child}.{col} → {parent}.{pcol}", "orphans": n,
                              "result": "PASS" if n == 0 else "FAIL"})
    return {"counts": cdf, "totals": tdf, "integrity": pd.DataFrame(integrity)}


def earned_premium_test(src, con, val_date: dt.date) -> pd.DataFrame:
    """Run INSURE/400 PREMCALC on legacy data and the same rule as SQL on the cloud database; compare."""
    pol = src["entities"]["POLMAST"]["df"]
    legacy_rows = []
    for rec in pol.to_dict("records"):
        eff = dt.datetime.strptime(str(int(rec["PM-EFF-DATE"])), "%Y%m%d").date()
        exp = dt.datetime.strptime(str(int(rec["PM-EXP-DATE"])), "%Y%m%d").date()
        legacy_rows.append({"policy_number": rec["PM-POLICY-NO"], "legacy_status": rec["PM-STATUS"],
                            "legacy_earned": legacy.earned_premium(rec["PM-WRITTEN-PREM"], eff, exp, val_date,
                                                                   rec["PM-STATUS"] == "C")})
    lg = pd.DataFrame(legacy_rows)
    v = val_date.isoformat()
    q = f"""
      SELECT policy_number, policy_status,
        CASE WHEN policy_status = 'Cancelled' THEN 0
             ELSE ROUND(written_premium *
                  MIN(MAX(julianday('{v}') - julianday(effective_date), 0),
                      julianday(expiration_date) - julianday(effective_date))
                  / (julianday(expiration_date) - julianday(effective_date)), 2) END AS cloud_earned
      FROM policy"""
    cd = pd.read_sql_query(q, con)
    out = lg.merge(cd, on="policy_number", how="outer")
    out["difference"] = (out.cloud_earned - out.legacy_earned).round(2)
    out["result"] = out.difference.abs().le(0.01).map({True: "MATCH", False: "MISMATCH"})
    return out


KEYCOL = {"policy": "policy_number", "party": "policy_number", "claim": "claim_number", "producer": "producer_code"}


def sample_compare(src, inv, m, canon, vm, con, entity: str, key_value: str) -> tuple[str, pd.DataFrame]:
    """One legacy record, field by field: positions → legacy value → expected (transformed) → destination value."""
    df = src["entities"][entity]["df"]
    key_col = [c for c in df.columns if c != "FORM_FILE"][0]
    hit = df[df[key_col].astype(str) == key_value]
    if hit.empty:
        return "", pd.DataFrame()
    rec = hit.iloc[0]
    raw = src["entities"][entity].get("raw", {}).get(key_value, "")
    lay = src["layouts"].get(entity)
    c = canon.set_index("canonical_id")
    iv = inv.set_index("element_id")
    vmaps = {}
    for r in vm.itertuples():
        if r.destination_code:
            vmaps.setdefault(r.element_id, {})[r.legacy_value] = r.destination_code
    f2c = dest_field_to_canon(canon)
    key_canon = m.loc[m.element_id == f"{entity}.{key_col}", "canonical_id"].iat[0]
    rows = []
    for r in m[m.entity == entity].itertuples():
        lv = rec.get(r.element)
        pos = ""
        if lay is not None:
            lr = lay[lay.name == r.element]
            if len(lr):
                pos = f"{lr.start.iat[0]}-{lr.end.iat[0]}"
        base = {"legacy field": r.element, "positions": pos, "legacy value": lv}
        if not r.canonical_id or r.canonical_id == NOT_MIGRATED or r.status == "Needs SME review":
            rows.append(base | {"canonical": "—", "destination field": "—", "expected": "", "destination value": "",
                                "result": "Not migrated"})
            continue
        cr = c.loc[r.canonical_id]
        rule = rule_for(r.data_type, cr.data_type, iv.at[r.element_id, "samples"], bool(cr.pick_list), cr.description)
        expected = convert(lv, rule, vmaps.get(r.element_id))
        for f in r.destination_fields.split(", "):
            t, col = f.split(".")
            k = KEYCOL.get(t)
            if k is None or f2c.get(f"{t}.{k}") != key_canon:
                continue
            row = con.execute(f"SELECT {col} FROM {t} WHERE {k}=?", (key_value,)).fetchone()
            if row is None:
                continue
            dv = row[0]
            ok = str(expected) == str(dv) or (_num(expected) is not None and _num(expected) == _num(dv))
            rows.append(base | {"canonical": r.canonical_id, "destination field": f, "expected": expected,
                                "destination value": dv, "result": "MATCH" if ok else "MISMATCH"})
    out = pd.DataFrame(rows)
    for col in ("legacy value", "expected", "destination value"):
        if col in out:
            out[col] = out[col].apply(lambda v: "" if v is None or (isinstance(v, float) and pd.isna(v)) else str(v))
    return raw, out


def _num(v):
    try:
        return round(float(v), 2)
    except (TypeError, ValueError):
        return None
