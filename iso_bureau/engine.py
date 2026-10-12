"""Bureau reporting engine: source -> canonical -> rules -> ISO 150-byte record.

Everything the engine uses is read from the metadata tables and must be
APPROVED by the SME and in force on the right date:

* layout version and layout fields   -> in force on the accounting period end date
* pick-list options, aliases, bureau code maps, business rules
                                     -> in force on the transaction's *code date*
                                        (policy effective date for ISO; falls back
                                        to loss date, then accounting date)

A "sandbox" flag lets the SME preview PENDING metadata before approving it;
sandbox batches can never be submitted.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from . import db

BATCH_FLOW = ["GENERATED", "VALIDATED", "SME_APPROVED", "SUBMITTED", "ACCEPTED", "CLOSED"]
OVERPUNCH_POS = "{ABCDEFGHI"
OVERPUNCH_NEG = "}JKLMNOPQR"


def in_scope(scope: str, value: str) -> bool:
    return scope in ("*", "", None) or value in [s.strip() for s in scope.split(",")]


def active(row: dict, as_of: str) -> bool:
    return row["eff_date"] <= as_of <= row["exp_date"]


# ======================================================================= cache
@dataclass
class Meta:
    """All metadata a batch needs, loaded once (approved, or approved+pending in sandbox)."""
    bureau: dict
    lob: str
    lob_row: dict
    major_line: str | None
    elements: list[dict]
    source_maps: list[dict]
    options: list[dict]
    option_aliases: list[dict]
    code_maps: list[dict]
    rules: list[dict]
    sandbox: bool = False

    @classmethod
    def load(cls, con, bureau_code: str, lob: str, sandbox: bool = False) -> "Meta":
        st = db.status_clause(sandbox)
        q = lambda sql, p=(): db.rows(con, sql, p)
        maj = q(f"SELECT option_code, lob_scope FROM picklist_option WHERE picklist_code='MAJOR_LINE' AND {st}")
        major = next((m["option_code"] for m in maj if m["lob_scope"] == lob), None)
        return cls(
            bureau=db.one(con, "SELECT * FROM bureau WHERE bureau_code=?", (bureau_code,)),
            lob=lob,
            lob_row=db.one(con, "SELECT * FROM line_of_business WHERE lob_code=?", (lob,)),
            major_line=major,
            elements=q(f"SELECT * FROM canonical_element WHERE {st}"),
            source_maps=q(f"SELECT * FROM source_mapping WHERE {st}"),
            options=[o for o in q(f"SELECT * FROM picklist_option WHERE {st}") if in_scope(o["lob_scope"], lob)],
            option_aliases=q(f"SELECT * FROM picklist_option_alias WHERE {st}"),
            code_maps=[m for m in q(f"SELECT * FROM bureau_code_map WHERE bureau_code=? AND {st}", (bureau_code,))
                       if in_scope(m["lob_scope"], lob)],
            rules=[r for r in q(f"SELECT * FROM business_rule WHERE bureau_code=? AND {st}", (bureau_code,))
                   if in_scope(r["lob_scope"], lob)],
            sandbox=sandbox,
        )

    def element(self, code: str, as_of: str) -> dict | None:
        c = [e for e in self.elements if e["element_code"] == code and active(e, as_of)]
        return max(c, key=lambda e: e["eff_date"]) if c else None

    def option(self, picklist: str, code: str, as_of: str) -> dict | None:
        return next((o for o in self.options if o["picklist_code"] == picklist and o["option_code"] == code
                     and active(o, as_of)), None)

    def rules_for(self, category: str, record_type: str, state: str | None, as_of: str) -> list[dict]:
        out = [r for r in self.rules if r["rule_category"] == category and in_scope(r["record_type_scope"], record_type)
               and (state is None or in_scope(r["state_scope"], state)) and active(r, as_of)]
        # newest version of each rule code wins
        best: dict[str, dict] = {}
        for r in out:
            if r["rule_code"] not in best or r["eff_date"] > best[r["rule_code"]]["eff_date"]:
                best[r["rule_code"]] = r
        return sorted(best.values(), key=lambda r: r["rule_code"])

    def transform(self, code: str, as_of: str) -> dict | None:
        c = [r for r in self.rules if r["rule_code"] == code and r["rule_category"] == "TRANSFORMATION" and active(r, as_of)]
        return max(c, key=lambda r: r["eff_date"]) if c else None


# ===================================================================== layouts
def resolve_layout(con, bureau: str, lob: str, record_type: str, as_of: str, sandbox: bool = False):
    st = db.status_clause(sandbox)
    versions = db.rows(con, f"""SELECT * FROM layout_version WHERE bureau_code=? AND lob_code=? AND record_type=?
                                 AND {db.as_of_clause()} AND {st} ORDER BY version_no DESC""",
                       (bureau, lob, record_type, as_of, as_of))
    if not versions:
        return None, []
    lay = versions[0]
    fields = db.rows(con, f"""SELECT * FROM layout_field WHERE layout_id=? AND {db.as_of_clause()} AND {st}
                              ORDER BY seq, eff_date DESC""", (lay["layout_id"], as_of, as_of))
    seen, out = set(), []
    for f in fields:
        if f["seq"] not in seen:
            seen.add(f["seq"])
            out.append(f)
    return lay, out


def layout_problems(fields: list[dict], record_length: int = 150) -> list[str]:
    probs, pos = [], 1
    for f in fields:
        if f["start_pos"] != pos:
            probs.append(f"Field {f['seq']} {f['bureau_field_name']} starts at {f['start_pos']}, expected {pos}")
        pos = f["start_pos"] + f["length"]
    if pos - 1 != record_length:
        probs.append(f"Layout covers {pos-1} bytes, expected {record_length}")
    return probs


# ================================================================== formatting
def _dec(v) -> Decimal:
    try:
        return Decimal(str(v).replace(",", "").strip())
    except (InvalidOperation, AttributeError):
        raise ValueError(f"'{v}' is not a number")


def overpunch(amount, length: int, scale: int = 2) -> str:
    cents = int((_dec(amount) * (10 ** scale)).quantize(Decimal(1), rounding=ROUND_HALF_UP))
    digits = str(abs(cents)).rjust(length, "0")
    if len(digits) > length:
        raise ValueError(f"amount {amount} overflows {length} positions")
    last = int(digits[-1])
    return digits[:-1] + (OVERPUNCH_NEG if cents < 0 else OVERPUNCH_POS)[last]


def un_overpunch(text: str, scale: int = 2) -> Decimal:
    last = text[-1]
    if last in OVERPUNCH_NEG:
        sign, d = -1, OVERPUNCH_NEG.index(last)
    else:
        sign, d = 1, OVERPUNCH_POS.index(last)
    return sign * Decimal(int(text[:-1] + str(d))) / (10 ** scale)


def apply_transform(expr: dict, value, length: int, field_format: str, bureau_value: str | None = None) -> str:
    op = expr["op"]
    if op == "blank":
        return " " * length
    if value in (None, ""):
        return ("0" * length) if field_format in ("N", "SIGNED", "YYMM", "YYMMDD") and op != "text" else " " * length
    if op == "date":
        out = datetime.strptime(str(value)[:10], "%Y-%m-%d").strftime(expr["fmt"])
    elif op == "overpunch":
        return overpunch(value, length, expr.get("scale", 2))
    elif op == "number":
        n = _dec(value)
        if "divide" in expr:
            n = n / Decimal(expr["divide"])
        if "multiply" in expr:
            n = n * Decimal(expr["multiply"])
        n = int(n.quantize(Decimal(1), rounding=ROUND_HALF_UP))
        if n < 0:
            raise ValueError(f"negative value {value} in unsigned numeric field")
        out = str(n).rjust(length, "0")
    elif op == "code_map":
        v = bureau_value if bureau_value is not None else str(value)
        out = v.rjust(length, "0") if field_format == "N" and v.isdigit() else v.ljust(length)
    elif op == "text":
        v = str(value)
        v = v.upper() if expr.get("case") == "upper" else v
        out = v.ljust(length) if expr.get("justify", "left") == "left" else v.rjust(length)
    else:
        raise ValueError(f"unknown transform op {op}")
    if len(out) > length:
        raise ValueError(f"value '{value}' -> '{out}' exceeds {length} positions")
    return out


# =================================================================== canonical
def code_date(canon: dict, bureau: dict) -> str:
    if bureau.get("code_basis") == "POLICY_EFF" and canon.get("POLICY_EFF_DATE"):
        return str(canon["POLICY_EFF_DATE"])[:10]
    return str(canon.get("LOSS_DATE") or canon.get("ACCT_DATE"))[:10]


def to_canonical(txn: dict, meta: Meta, meta_date: str) -> tuple[dict, list[dict]]:
    """Source attributes -> canonical elements (names via source_mapping, codes via option aliases)."""
    payload = json.loads(txn["payload_json"])
    msgs: list[dict] = []
    canon: dict = {}
    sysname = txn["source_system"]
    maps = [m for m in meta.source_maps if m["source_system"] == sysname]
    attr_to_el = {}
    for m in maps:
        attr_to_el.setdefault(m["source_attribute"], []).append(m)
    for attr, val in payload.items():
        cands = attr_to_el.get(attr)
        if not cands:
            msgs.append({"sev": "WARNING", "code": "MAP001", "element": None,
                         "msg": f"Source attribute {sysname}.{attr} has no approved canonical mapping (ignored)"})
            continue
        if cands[0]["element_code"] == "NOT_REPORTED":  # SME marked this attribute not needed
            continue
        canon[cands[0]["element_code"]] = val
    # resolve code dates after dates are known; then translate pick-list values
    cdate = code_date(canon, meta.bureau)
    for el_code, val in list(canon.items()):
        el = meta.element(el_code, meta_date)
        if el is None:
            msgs.append({"sev": "ERROR", "code": "MAP002", "element": el_code,
                         "msg": f"Canonical element {el_code} is not approved / not in force on {meta_date}"})
            continue
        if el["picklist_code"] and val not in (None, ""):
            canon[el_code] = _resolve_option(el["picklist_code"], str(val), sysname, cdate, meta, msgs, el_code)
    canon["_code_date"] = cdate
    return canon, msgs


def _resolve_option(picklist, val, sysname, cdate, meta: Meta, msgs, el_code):
    for a in meta.option_aliases:
        if a["picklist_code"] == picklist and a["source_system"] in (sysname, "*") \
                and a["source_value"].lower() == val.lower() and active(a, cdate):
            if meta.option(picklist, a["option_code"], cdate):
                return a["option_code"]
    if meta.option(picklist, val.upper(), cdate):
        return val.upper()
    if meta.option(picklist, val, cdate):
        return val
    msgs.append({"sev": "ERROR", "code": "PCK001", "element": el_code, "source_value": val, "picklist": picklist,
                 "msg": f"{sysname} value '{val}' is not an approved {picklist} option or alias in force on {cdate}"})
    return None


# ================================================================ rule runtime
def _ref(token, canon, ctx):
    if isinstance(token, str) and token.startswith("$"):
        return ctx.get(token[1:])
    return canon.get(token)


def _cmp(a, op, b) -> bool:
    try:
        a, b = float(a), float(b)
    except (TypeError, ValueError):
        a, b = str(a)[:10], str(b)[:10]
    return {"==": a == b, "!=": a != b, ">": a > b, ">=": a >= b, "<": a < b, "<=": a <= b}[op]


def eval_check(expr: dict, element: str | None, canon: dict, ctx: dict) -> bool | None:
    """True = pass, False = fail, None = not applicable (missing inputs)."""
    op = expr["op"]
    if op == "required":
        return canon.get(element) not in (None, "")
    if op == "regex":
        v = canon.get(element)
        return None if v in (None, "") else re.match(expr["pattern"], str(v)) is not None
    if op == "compare":
        a = _ref(expr["left"], canon, ctx)
        b = expr["value"] if "value" in expr else _ref(expr["right"], canon, ctx)
        if a in (None, "") or b in (None, ""):
            return None
        return _cmp(a, expr["cmp"], b)
    if op == "between":
        v, lo, hi = (_ref(expr[k], canon, ctx) for k in ("field", "from", "to"))
        if v in (None, "") or lo in (None, "") or hi in (None, ""):
            return None
        return _cmp(v, ">=", lo) and _cmp(v, "<=", hi)
    if op == "when":
        cond = expr["if"]
        if canon.get(cond["field"]) not in cond["in"]:
            return None
        return eval_check(expr["then"], element, canon, ctx)
    raise ValueError(f"unknown validation op {op}")


def run_derivations(canon: dict, meta: Meta, record_type: str, ctx: dict, msgs: list):
    cdate = canon["_code_date"]
    for r in meta.rules_for("DERIVATION", record_type, canon.get("STATE"), cdate):
        e = json.loads(r["expression_json"])
        el = r["element_code"]
        if e["op"] == "set":
            canon[el] = _ref(e["value"], canon, ctx) if str(e["value"]).startswith("$") else e["value"]
        elif e["op"] == "lookup":
            src = canon.get(e["from"])
            if src in e["map"]:
                canon[el] = e["map"][src]
            elif canon.get(el) in (None, ""):
                msgs.append({"sev": r["severity"], "code": r["rule_code"], "element": el,
                             "msg": f"{r['message']} ({e['from']}={src})"})
        elif e["op"] == "coalesce":
            if canon.get(el) in (None, ""):
                canon[el] = next((canon.get(f) for f in e["from"] if canon.get(f) not in (None, "")), None)


def run_validations(canon: dict, meta: Meta, record_type: str, ctx: dict,
                    reported: set[str] | None = None) -> list[dict]:
    """Rules on elements the layout does not report are skipped (they are not the bureau's concern)."""
    out = []
    cdate = canon["_code_date"]
    for r in meta.rules_for("VALIDATION", record_type, canon.get("STATE"), cdate):
        if reported is not None and r["element_code"] and r["element_code"] not in reported:
            continue
        ok = eval_check(json.loads(r["expression_json"]), r["element_code"], canon, ctx)
        if ok is False:
            out.append({"sev": r["severity"], "code": r["rule_code"], "element": r["element_code"], "msg": r["message"]})
    return out


# ================================================================= bureau out
def to_bureau(canon: dict, fields: list[dict], meta: Meta, record_length: int,
              prior: list[dict] = ()) -> tuple[str, list[dict]]:
    msgs, parts = [], []
    cdate = canon["_code_date"]
    for f in fields:
        el = f["element_code"]
        val = canon.get(el)
        if f["required"] == "Y" and val in (None, "") and el != "FILLER" \
                and not any(m.get("element") == el for m in prior):
            msgs.append({"sev": "ERROR", "code": "REQ001", "element": el,
                         "msg": f"Required field {f['seq']} '{f['bureau_field_name']}' ({el}) is blank"})
        tr = meta.transform(f["transform_rule_code"], cdate)
        if tr is None:
            msgs.append({"sev": "ERROR", "code": "TRN001", "element": el,
                         "msg": f"Transformation rule {f['transform_rule_code']} is not approved / in force"})
            parts.append(" " * f["length"])
            continue
        expr = json.loads(tr["expression_json"])
        bval = None
        if expr["op"] == "code_map" and val not in (None, ""):
            el_row = meta.element(el, canon.get("_meta_date", cdate))
            pl = el_row["picklist_code"] if el_row else None
            hits = [m for m in meta.code_maps if m["picklist_code"] == pl and m["option_code"] == val and active(m, cdate)]
            if not hits:
                msgs.append({"sev": "ERROR", "code": "MAP003", "element": el,
                             "msg": f"No approved ISO code for {pl} option '{val}' in force on {cdate}"})
                parts.append(" " * f["length"])
                continue
            bval = max(hits, key=lambda m: m["eff_date"])["bureau_value"]
        try:
            parts.append(apply_transform(expr, val, f["length"], f["field_format"], bval))
        except ValueError as ex:
            msgs.append({"sev": "ERROR", "code": "FMT001", "element": el,
                         "msg": f"Field {f['seq']} '{f['bureau_field_name']}': {ex}"})
            parts.append(("?" * f["length"]))
    rec = "".join(parts)
    if len(rec) != record_length:
        msgs.append({"sev": "ERROR", "code": "LEN001", "element": None,
                     "msg": f"Record is {len(rec)} bytes, expected {record_length}"})
    return rec, msgs


# ================================================================= batch flow
def period_bounds(period_type: str, year: int, n: int) -> tuple[str, str]:
    if period_type == "MONTHLY":
        start = date(year, n, 1)
        end = date(year + (n == 12), n % 12 + 1, 1)
    else:
        start = date(year, 3 * (n - 1) + 1, 1)
        end = date(year + (n == 4), (3 * n) % 12 + 1, 1)
    from datetime import timedelta
    return start.isoformat(), (end - timedelta(days=1)).isoformat()


def _event(con, batch_id, frm, to, actor, comment=""):
    db.insert(con, "batch_event", {"batch_id": batch_id, "status_from": frm, "status_to": to,
                                   "actor": actor, "comment": comment})


def current_txns(con, lob, record_type, start, end, txn_ids: list[int] | None = None):
    sql = """SELECT t.* FROM source_transaction t
             WHERE t.lob_code=? AND t.record_type=?
               AND NOT EXISTS (SELECT 1 FROM source_transaction c WHERE c.corrects_txn_id=t.txn_id)"""
    p = [lob, record_type]
    if txn_ids is None:
        sql += " AND t.accounting_date BETWEEN ? AND ?"
        p += [start, end]
        # skip transactions already accepted by the bureau
        sql += """ AND NOT EXISTS (SELECT 1 FROM submission_record r JOIN submission_batch b ON b.batch_id=r.batch_id
                                   WHERE r.txn_id=t.txn_id AND r.status='ACCEPTED')"""
    else:
        sql += f" AND t.txn_id IN ({','.join('?'*len(txn_ids))})"
        p += txn_ids
    return db.rows(con, sql + " ORDER BY t.txn_id", p)


def readiness(con, bureau, lob, record_type, period_end) -> list[dict]:
    """Everything this run depends on that is not yet SME-approved."""
    issues = []
    lay, fields = resolve_layout(con, bureau, lob, record_type, period_end, sandbox=False)
    if lay is None:
        lay_p, _ = resolve_layout(con, bureau, lob, record_type, period_end, sandbox=True)
        issues.append({"object": "layout_version", "id": lay_p["layout_id"] if lay_p else None,
                       "issue": f"No APPROVED {bureau} {lob} {record_type} layout in force on {period_end}"
                                + (" (a PENDING version exists)" if lay_p else "")})
        return issues
    for p in layout_problems(fields, lay["record_length"]):
        issues.append({"object": "layout_field", "id": None, "issue": p})
    pend_fields = db.rows(con, f"""SELECT * FROM layout_field WHERE layout_id=? AND status='PENDING'
                                    AND {db.as_of_clause()}""", (lay["layout_id"], period_end, period_end))
    for f in pend_fields:
        issues.append({"object": "layout_field", "id": f["field_id"], "issue": f"Field {f['seq']} {f['bureau_field_name']} pending SME approval"})
    els = {f["element_code"] for f in fields}
    for el in sorted(els):
        e = db.one(con, f"SELECT * FROM canonical_element WHERE element_code=? AND status='APPROVED' AND {db.as_of_clause()}",
                   (el, period_end, period_end))
        if not e:
            issues.append({"object": "canonical_element", "id": None, "issue": f"Canonical element {el} not approved"})
            continue
        if e["picklist_code"]:
            n = db.one(con, "SELECT COUNT(*) n FROM bureau_code_map WHERE picklist_code=? AND bureau_code=? AND status='APPROVED'",
                       (e["picklist_code"], bureau))["n"]
            if n == 0:
                issues.append({"object": "bureau_code_map", "id": None, "issue": f"Pick list {e['picklist_code']} has no approved ISO codes"})
    trs = {f["transform_rule_code"] for f in fields}
    for t in sorted(trs):
        if not db.one(con, "SELECT 1 FROM business_rule WHERE rule_code=? AND status='APPROVED'", (t,)):
            issues.append({"object": "business_rule", "id": None, "issue": f"Transformation rule {t} not approved"})
    return issues


def generate_batch(con, bureau: str, lob: str, record_type: str, period_type: str, period_start: str,
                   period_end: str, actor: str, sandbox: bool = False, txn_ids: list[int] | None = None,
                   parent_batch_id: int | None = None) -> int:
    """Step 1 - map source to canonical and build the fixed-width records."""
    lay, fields = resolve_layout(con, bureau, lob, record_type, period_end, sandbox)
    if lay is None:
        raise ValueError(f"No {'approved ' if not sandbox else ''}{bureau} {lob} {record_type} layout in force on {period_end}")
    meta = Meta.load(con, bureau, lob, sandbox)
    status = "SANDBOX" if sandbox else "GENERATED"
    with db.tx(con):
        if txn_ids is None and not sandbox:
            for old in db.rows(con, """SELECT batch_id, status FROM submission_batch WHERE bureau_code=? AND lob_code=? AND record_type=?
                                        AND period_start=? AND period_end=? AND status IN ('GENERATED','VALIDATED')
                                        AND parent_batch_id IS NULL""",
                               (bureau, lob, record_type, period_start, period_end)):
                con.execute("UPDATE submission_batch SET status='SUPERSEDED' WHERE batch_id=?", (old["batch_id"],))
                _event(con, old["batch_id"], old["status"], "SUPERSEDED", actor, "Regenerated")
        bid = db.insert(con, "submission_batch", {
            "bureau_code": bureau, "lob_code": lob, "record_type": record_type, "period_type": period_type,
            "period_start": period_start, "period_end": period_end, "layout_id": lay["layout_id"],
            "status": status, "created_by": actor, "parent_batch_id": parent_batch_id})
        ctx = {"batch.lob": lob, "batch.period_start": period_start, "batch.period_end": period_end,
               "lob.major_line": meta.major_line}
        txns = current_txns(con, lob, record_type, period_start, period_end, txn_ids)
        for i, t in enumerate(txns, 1):
            canon, msgs = to_canonical(t, meta, period_end)
            canon["_meta_date"] = period_end
            run_derivations(canon, meta, record_type, ctx, msgs)
            rec, m2 = to_bureau(canon, fields, meta, lay["record_length"], msgs)
            msgs += m2
            db.insert(con, "submission_record", {
                "batch_id": bid, "txn_id": t["txn_id"], "line_no": i, "record_text": rec,
                "canonical_json": db.jdump(canon), "status": _rec_status(msgs), "messages_json": db.jdump(msgs)})
        _event(con, bid, None, status, actor, f"{len(txns)} source transactions; layout v{lay['version_no']}")
        _refresh_counts(con, bid)
    return bid


def _rec_status(msgs):
    if any(m["sev"] == "ERROR" for m in msgs):
        return "ERROR"
    return "WARNING" if msgs else "VALID"


def validate_batch(con, batch_id: int, actor: str) -> dict:
    """Step 2 - run the approved validation rules over each canonical record."""
    b = db.one(con, "SELECT * FROM submission_batch WHERE batch_id=?", (batch_id,))
    sandbox = b["status"] == "SANDBOX"
    if not sandbox and b["status"] not in ("GENERATED", "VALIDATED"):
        raise ValueError(f"Batch {batch_id} is {b['status']}; only GENERATED batches can be validated")
    meta = Meta.load(con, b["bureau_code"], b["lob_code"], sandbox)
    ctx = {"batch.lob": b["lob_code"], "batch.period_start": b["period_start"], "batch.period_end": b["period_end"],
           "lob.major_line": meta.major_line}
    reported = {f["element_code"] for f in db.rows(con, "SELECT element_code FROM layout_field WHERE layout_id=?", (b["layout_id"],))}
    with db.tx(con):
        for r in db.rows(con, "SELECT * FROM submission_record WHERE batch_id=?", (batch_id,)):
            canon = json.loads(r["canonical_json"])
            msgs = [m for m in json.loads(r["messages_json"]) if not str(m["code"]).startswith("VR")]
            msgs += run_validations(canon, meta, b["record_type"], ctx, reported)
            con.execute("UPDATE submission_record SET status=?, messages_json=? WHERE rec_id=?",
                        (_rec_status(msgs), db.jdump(msgs), r["rec_id"]))
        if not sandbox:
            con.execute("UPDATE submission_batch SET status='VALIDATED' WHERE batch_id=?", (batch_id,))
            _event(con, batch_id, b["status"], "VALIDATED", actor)
        _refresh_counts(con, batch_id)
    return db.one(con, "SELECT * FROM submission_batch WHERE batch_id=?", (batch_id,))


def _refresh_counts(con, batch_id):
    recs = db.rows(con, "SELECT status, canonical_json FROM submission_record WHERE batch_id=?", (batch_id,))
    good = [r for r in recs if r["status"] in ("VALID", "WARNING", "ACCEPTED")]
    tot = {"WRITTEN_PREMIUM": 0.0, "PAID_LOSS": 0.0, "OS_RESERVE": 0.0, "ALAE": 0.0}
    for r in good:
        c = json.loads(r["canonical_json"])
        for k in tot:
            try:
                tot[k] += float(c.get(k) or 0)
            except ValueError:
                pass
    con.execute("""UPDATE submission_batch SET record_count=?, valid_count=?, error_count=?, warning_count=?,
                   total_premium=?, total_paid=?, total_outstanding=?, total_alae=? WHERE batch_id=?""",
                (len(recs), len(good), sum(r["status"] == "ERROR" for r in recs),
                 sum(r["status"] == "WARNING" for r in recs),
                 round(tot["WRITTEN_PREMIUM"], 2), round(tot["PAID_LOSS"], 2), round(tot["OS_RESERVE"], 2),
                 round(tot["ALAE"], 2), batch_id))


def sme_approve_batch(con, batch_id: int, actor: str, comment: str = "") -> None:
    """Step 3 - SME signs off control totals; ERROR records are held for correction."""
    b = db.one(con, "SELECT * FROM submission_batch WHERE batch_id=?", (batch_id,))
    if b["status"] != "VALIDATED":
        raise ValueError(f"Batch {batch_id} must be VALIDATED before SME approval (is {b['status']})")
    if b["valid_count"] == 0:
        raise ValueError("No valid records to submit")
    with db.tx(con):
        con.execute("UPDATE submission_record SET status='HELD' WHERE batch_id=? AND status='ERROR'", (batch_id,))
        con.execute("UPDATE submission_batch SET status='SME_APPROVED', sme_approved_by=?, sme_approved_at=? WHERE batch_id=?",
                    (actor, datetime.now().isoformat(timespec="seconds"), batch_id))
        _event(con, batch_id, "VALIDATED", "SME_APPROVED", actor, comment or f"{b['error_count']} record(s) held for correction")


def build_file(con, batch_id: int) -> tuple[str, str]:
    b = db.one(con, "SELECT * FROM submission_batch WHERE batch_id=?", (batch_id,))
    recs = db.rows(con, """SELECT record_text FROM submission_record WHERE batch_id=? AND status IN ('VALID','WARNING','SUBMITTED','ACCEPTED','REJECTED')
                           ORDER BY line_no""", (batch_id,))
    name = f"{b['bureau_code']}_{b['lob_code']}_{b['record_type']}_{b['period_end'][:7].replace('-', '')}_B{batch_id:05d}.txt"
    return name, "\n".join(r["record_text"] for r in recs) + ("\n" if recs else "")


def submit_batch(con, batch_id: int, actor: str) -> dict:
    """Step 4 - build the flat file and transmit (simulated ISO acknowledgment)."""
    b = db.one(con, "SELECT * FROM submission_batch WHERE batch_id=?", (batch_id,))
    if b["status"] != "SME_APPROVED":
        raise ValueError(f"Batch {batch_id} must be SME_APPROVED before submission (is {b['status']})")
    now = datetime.now().isoformat(timespec="seconds")
    with db.tx(con):
        con.execute("UPDATE submission_record SET status='SUBMITTED' WHERE batch_id=? AND status IN ('VALID','WARNING')", (batch_id,))
        name, text = build_file(con, batch_id)
        con.execute("UPDATE submission_batch SET status='SUBMITTED', file_name=?, file_text=?, submitted_at=? WHERE batch_id=?",
                    (name, text, now, batch_id))
        _event(con, batch_id, "SME_APPROVED", "SUBMITTED", actor, name)
        # ---- simulated bureau edit: duplicates within the file or of an accepted record are rejected
        seen = {r["record_text"] for r in db.rows(con, """SELECT r.record_text FROM submission_record r
                    JOIN submission_batch b ON b.batch_id=r.batch_id WHERE r.status='ACCEPTED' AND b.lob_code=?""", (b["lob_code"],))}
        acc = rej = 0
        for r in db.rows(con, "SELECT * FROM submission_record WHERE batch_id=? AND status='SUBMITTED' ORDER BY line_no", (batch_id,)):
            if r["record_text"] in seen:
                msgs = json.loads(r["messages_json"]) + [{"sev": "ERROR", "code": "ISO-DUP", "element": None,
                                                          "msg": "ISO edit: duplicate of a record already received"}]
                con.execute("UPDATE submission_record SET status='REJECTED', messages_json=? WHERE rec_id=?", (db.jdump(msgs), r["rec_id"]))
                rej += 1
            else:
                seen.add(r["record_text"])
                con.execute("UPDATE submission_record SET status='ACCEPTED' WHERE rec_id=?", (r["rec_id"],))
                acc += 1
        held = db.one(con, "SELECT COUNT(*) n FROM submission_record WHERE batch_id=? AND status='HELD'", (batch_id,))["n"]
        new = "ACCEPTED" if rej == 0 and held == 0 else "PARTIALLY_ACCEPTED"
        con.execute("UPDATE submission_batch SET status=?, response_at=? WHERE batch_id=?", (new, now, batch_id))
        _event(con, batch_id, "SUBMITTED", new, "ISO (simulated)", f"{acc} accepted, {rej} rejected, {held} held")
    return {"file_name": name, "accepted": acc, "rejected": rej, "held": held, "status": new}


def correct_transaction(con, txn_id: int, new_payload: dict, actor: str, note: str) -> int:
    """Corrections never overwrite source: a new transaction row points at the one it corrects."""
    old = db.one(con, "SELECT * FROM source_transaction WHERE txn_id=?", (txn_id,))
    with db.tx(con):
        new_id = db.insert(con, "source_transaction", {
            "source_system": old["source_system"], "source_txn_key": old["source_txn_key"],
            "record_type": old["record_type"], "lob_code": old["lob_code"],
            "accounting_date": new_payload.get("AccountingDate") or new_payload.get("acct_dt") or old["accounting_date"],
            "payload_json": db.jdump(new_payload), "corrects_txn_id": txn_id, "corrected_by": actor,
            "correction_note": note})
    return new_id


def open_corrections(con, batch_id: int) -> list[dict]:
    return db.rows(con, """SELECT r.*, t.source_system, t.source_txn_key, t.payload_json FROM submission_record r
                           JOIN source_transaction t ON t.txn_id=r.txn_id
                           WHERE r.batch_id=? AND r.status IN ('HELD','REJECTED')""", (batch_id,))


def resubmission_batch(con, parent_id: int, actor: str) -> int:
    """Build a correction batch from the latest version of every held / rejected transaction."""
    p = db.one(con, "SELECT * FROM submission_batch WHERE batch_id=?", (parent_id,))
    ids = []
    for r in open_corrections(con, parent_id):
        cur = r["txn_id"]
        while True:
            nxt = db.one(con, "SELECT txn_id FROM source_transaction WHERE corrects_txn_id=?", (cur,))
            if not nxt:
                break
            cur = nxt["txn_id"]
        if cur == r["txn_id"]:
            continue  # not corrected yet
        ids.append(cur)
    if not ids:
        raise ValueError("No corrected transactions to resubmit yet")
    bid = generate_batch(con, p["bureau_code"], p["lob_code"], p["record_type"], p["period_type"],
                         p["period_start"], p["period_end"], actor, txn_ids=ids, parent_batch_id=parent_id)
    with db.tx(con):
        _event(con, parent_id, p["status"], p["status"], actor, f"Resubmission batch {bid} created with {len(ids)} corrected records")
    return bid


def close_batch(con, batch_id: int, actor: str, comment: str = "") -> None:
    b = db.one(con, "SELECT * FROM submission_batch WHERE batch_id=?", (batch_id,))
    if b["status"] not in ("ACCEPTED", "PARTIALLY_ACCEPTED"):
        raise ValueError("Only acknowledged batches can be closed")
    openn = len(open_corrections(con, batch_id))
    # an open item is resolved once a child batch accepted its correction
    resolved = db.one(con, """SELECT COUNT(*) n FROM submission_record r JOIN submission_batch c ON c.batch_id=r.batch_id
                               WHERE c.parent_batch_id=? AND r.status='ACCEPTED'""", (batch_id,))["n"]
    if openn > resolved and not comment:
        raise ValueError(f"{openn - resolved} record(s) still open - correct and resubmit, or give the SME reason to close")
    with db.tx(con):
        con.execute("UPDATE submission_batch SET status='CLOSED', closed_at=? WHERE batch_id=?",
                    (datetime.now().isoformat(timespec="seconds"), batch_id))
        _event(con, batch_id, b["status"], "CLOSED", actor, comment)


def parse_record(record: str, fields: list[dict]) -> list[dict]:
    """Split a fixed-width record back into fields (used by the SME record inspector)."""
    return [{"seq": f["seq"], "field": f["bureau_field_name"], "pos": f"{f['start_pos']}-{f['start_pos']+f['length']-1}",
             "value": record[f["start_pos"]-1:f["start_pos"]-1+f["length"]], "element": f["element_code"]} for f in fields]
