"""Turn a bureau error file into revision proposals the SME can approve.

Each proposal is one of:
  value_map   change how a source value maps to a bureau code (fixes every record with that value)
  override    correct one canonical value for one record (kept as an SME-approved override)
  exclude     hold a record out of the resubmission until the source system is corrected
  acknowledge accept a warning without change
Optionally, the SME can ask Claude (Anthropic API key in Streamlit secrets) to draft proposals from
a plain-language instruction; those come back in the same structure and still need SME approval.
"""
from __future__ import annotations

import difflib
import json
import urllib.request

import pandas as pd

from . import catalog
from .source import CLASSES

# SI² domain knowledge for remapping values the bureau rejected.
HINTS = {
    ("INJURY CODE (INJURY TYPE)", "PPD-MINOR"): ("09", "NCCI does not accept codes 03/04; permanent partial disability is reported as 09."),
    ("INJURY CODE (INJURY TYPE)", "PPD-MAJOR"): ("09", "NCCI does not accept codes 03/04; permanent partial disability is reported as 09."),
    ("INJURY CODE (INJURY TYPE)", "TTD/TPD"): ("05", "Temporary total and temporary partial disability share code 05."),
    ("CLAIM/STATUS CODE", "PENDING"): ("0", "A pending claim is still open for statistical reporting (code 0)."),
    ("BENEFIT TYPE CODE", "MISC"): ("99", "Miscellaneous indemnity with no specific benefit type is reported as 99."),
}


def _field(spec, record_name, field_name):
    df = catalog.load()
    keys = {v: k for k, v in catalog.RECORD_NAMES[spec].items()}
    key = keys.get(record_name, record_name)
    m = df[(df.spec == spec) & (df.record_key == key) & (df.name == field_name)]
    if not len(m) and spec in ("WCSTAT", "WCPOLS"):
        link = "0" if spec == "WCSTAT" else "00"
        m = df[(df.spec == spec) & (df.record_key == link) & (df.name == field_name)]
    return m.iloc[0] if len(m) else None


def _canon_row(canon, table, meta_row):
    """Find the canonical row behind an error record."""
    t = canon.get(table)
    if t is None:
        return None
    if meta_row["ref_table"] == table and meta_row["ref_row"] >= 0:
        r = t[t._row == meta_row["ref_row"]]
        return r.iloc[0] if len(r) else None
    if table == "claim" and meta_row["claim"]:
        r = t[t.claim_number == meta_row["claim"]]
        return r.iloc[0] if len(r) else None
    if table in ("policy", "policy_state") and meta_row["policy"]:
        r = t[t.policy_number == meta_row["policy"]]
        return r.iloc[0] if len(r) else None
    return None


def best_code(field_name, value, codes):
    hint = HINTS.get((field_name, value))
    if hint and hint[0] in {c["code"] for c in codes}:
        return hint[0], hint[1], 0.95
    ok = [c for c in codes if not c["reserved"] and "NCCI" not in c["na_states"]]
    best, score = "", 0.0
    for c in ok:
        s = difflib.SequenceMatcher(None, str(value).lower(), c["description"].lower()[:40]).ratio()
        if s > score:
            best, score = c["code"], s
    return best, "Closest active code that applies to NCCI by description.", round(score, 2)


def propose(spec: str, err: pd.DataFrame, meta: pd.DataFrame, canon: dict, fmap: pd.DataFrame) -> pd.DataFrame:
    meta_i = meta.set_index("seq")
    fm = {}
    for r in fmap.to_dict("records"):
        fm.setdefault((r["record_name"], r["field_name"]), r)
    props, seen = [], set()

    def add(**p):
        key = (p["action"], p["target"])
        if key in seen:
            for q in props:
                if (q["action"], q["target"]) == key:
                    q["records"] += 1
            return
        seen.add(key)
        props.append({"records": 1, "approve": p.get("confidence", 0) >= 0.8 and not p.get("needs_input"), **p})

    for e in err.itertuples():
        m = meta_i.loc[e.record_seq] if e.record_seq in meta_i.index else None
        if m is None:
            continue
        f = _field(spec, e.record_type, e.field)
        fmrow = fm.get((e.record_type, e.field))
        canon_ref = fmrow["canonical"] if fmrow is not None and "." in str(fmrow["canonical"]) else ""

        if e.edit_id in ("G02", "G03", "G04") and f is not None and canon_ref:
            table, col = canon_ref.split(".")
            row = _canon_row(canon, table, m)
            src_val = str(row[col]) if row is not None and col in row else e.value
            code, why, conf = best_code(e.field, src_val, f["codes"])
            add(edit_id=e.edit_id, action="value_map", target=f"{f.field_id}|{src_val}", field=e.field,
                current=f"{src_val} → {e.value}", proposed=f"{src_val} → {code} ({catalog.pick_list(f).get(code, '')[:50]})",
                rationale=why, confidence=conf, needs_input=False, value=code)
        elif e.edit_id in ("G08", "S12") and spec == "WCSTAT":
            row = _canon_row(canon, "claim", m)
            if row is not None:
                kind = "indemnity" if "INDEMNITY" in e.field else "medical"
                res_col = f"{kind}_reserve"
                add(edit_id=e.edit_id, action="override", target=f"claim|{row._row}|{res_col}", field=e.field,
                    current=f"{row.claim_number}: {kind} reserve {row[res_col]:,.2f}",
                    proposed=f"{kind} reserve 0.00 (incurred = paid {row[f'paid_{kind}_amount']:,.2f})",
                    rationale="A negative reserve makes paid exceed incurred. Set the reserve to zero so incurred equals paid.",
                    confidence=0.85, needs_input=False, value="0")
        elif e.edit_id == "S13":
            row = _canon_row(canon, "claim", m)
            if row is not None:
                add(edit_id=e.edit_id, action="override", target=f"claim|{row._row}|injury_type", field=e.field,
                    current=f"{row.claim_number}: {row.injury_type} with indemnity paid {row.paid_indemnity_amount:,.2f}",
                    proposed="TTD (code 05)",
                    rationale="Indemnity was paid, so the claim is not medical-only; temporary disability is the likely type. Confirm with the adjuster.",
                    confidence=0.7, needs_input=False, value="TTD")
        elif e.edit_id == "S10":
            table = "exposure" if m["ref_table"] == "exposure" else "claim"
            row = _canon_row(canon, table, m)
            if row is None:
                continue
            if table == "exposure":
                wording = str(row.classification_wording).upper()
                match = next((k for k, (d, _) in CLASSES.items() if d == wording), "")
                why = f'Class wording "{wording.title()}" belongs to class {match}.' if match else "Class wording did not match a known class."
                conf = 0.9 if match else 0.3
            else:
                ex = canon["exposure"]
                ex = ex[(ex.policy_number == row.policy_number) & (ex.classification_code != "9999")]
                match = ex.sort_values("exposure_amount", ascending=False).classification_code.iloc[0] if len(ex) else ""
                why, conf = "Governing class (largest payroll) on the same policy.", 0.6
            add(edit_id=e.edit_id, action="override", target=f"{table}|{row._row}|classification_code", field=e.field,
                current=f"{row.policy_number}: class {e.value}", proposed=f"class {match}" if match else "Enter class code",
                rationale=why, confidence=conf, needs_input=not match, value=match)
        elif e.edit_id in ("S11", "I11", "I10", "M11"):
            table = m["ref_table"]
            row = _canon_row(canon, table if table in canon else "claim", m)
            if row is None:
                continue
            tbl = table if table in canon else "claim"
            add(edit_id=e.edit_id, action="exclude", target=f"{tbl}|{row._row}|", field=e.field,
                current=f"{m['claim'] or m['policy']}: {e.field} {e.value}",
                proposed="Hold out of the resubmission and send to the claims team",
                rationale="The dates conflict with the policy or payment; this needs the source system corrected, not a guess.",
                confidence=0.8, needs_input=False, value="")
        elif e.edit_id in ("P10",) or (e.edit_id == "G07" and "FEIN" in e.field):
            row = _canon_row(canon, "policy", m)
            if row is not None:
                add(edit_id=e.edit_id, action="override", target=f"policy|{row._row}|fein", field=e.field,
                    current=f"{row.policy_number}: FEIN blank", proposed="Enter the 9-digit FEIN",
                    rationale="FEIN is missing in the policy system. Get it from the application or underwriting file.",
                    confidence=0.0, needs_input=True, value="")
        elif e.edit_id == "M10":
            row = _canon_row(canon, "medical_bill_line", m)
            if row is not None:
                add(edit_id=e.edit_id, action="override", target=f"medical_bill_line|{row._row}|paid_amount", field=e.field,
                    current=f"Bill {row.bill_identification_number} line {row.line_identification_number}: paid {row.paid_amount:,.2f}",
                    proposed=f"paid {row.amount_charged_by_provider:,.2f} (capped at charges)",
                    rationale="Paid cannot exceed the provider charge; the bill review system likely double-applied an adjustment.",
                    confidence=0.75, needs_input=False, value=f"{row.amount_charged_by_provider:.2f}")
        elif e.edit_id == "M12":
            row = _canon_row(canon, "medical_bill_line", m)
            if row is not None:
                add(edit_id=e.edit_id, action="override", target=f"medical_bill_line|{row._row}|paid_procedure_code",
                    field=e.field, current=f"Bill {row.bill_identification_number}: procedure code blank",
                    proposed="Enter the CPT/HCPCS code from the bill", rationale="The procedure code is missing on the bill line.",
                    confidence=0.0, needs_input=True, value="")
        elif e.severity == "Warning":
            add(edit_id=e.edit_id, action="acknowledge", target=f"{e.edit_id}|{e.field}", field=e.field,
                current=e.message, proposed="Accept warning", rationale="Warning only; no change required.",
                confidence=0.9, needs_input=False, value="")
    cols = ["approve", "edit_id", "action", "field", "current", "proposed", "rationale", "records", "confidence",
            "needs_input", "value", "target"]
    return pd.DataFrame(props, columns=cols)


def ask_claude(api_key: str, model: str, instruction: str, spec: str, err: pd.DataFrame, props: pd.DataFrame) -> pd.DataFrame:
    """Ask Claude to draft revisions from the SME's instruction. Returns proposals for SME approval."""
    sample = err.head(60).to_dict("records")
    prompt = (
        "You are SI², a workers compensation bureau reporting expert (NCCI / WCIO specifications).\n"
        f"Bureau file type: {spec}. The bureau returned these errors (JSON):\n{json.dumps(sample, default=str)}\n\n"
        f"Current proposals (JSON):\n{props.drop(columns=['approve']).to_json(orient='records')}\n\n"
        f"SME instruction: {instruction}\n\n"
        "Reply with ONLY a JSON array of revisions. Each item: {\"action\": \"value_map\"|\"override\"|\"exclude\"|"
        "\"acknowledge\", \"target\": exactly a target string from the current proposals, \"value\": new value, "
        "\"rationale\": one sentence}. Only use targets that appear in the current proposals.")
    body = json.dumps({"model": model, "max_tokens": 2000, "messages": [{"role": "user", "content": prompt}]}).encode()
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=body, headers={
        "x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=90) as r:
        text = json.loads(r.read())["content"][0]["text"]
    start, end = text.find("["), text.rfind("]")
    items = json.loads(text[start:end + 1]) if start >= 0 else []
    out = props.copy()
    for it in items:
        hit = out.target == it.get("target")
        if hit.any():
            out.loc[hit, ["action", "value", "rationale"]] = [it.get("action"), str(it.get("value", "")),
                                                              "Claude: " + it.get("rationale", "")]
            out.loc[hit, "proposed"] = f'{it.get("action")}: {it.get("value", "")}'
            out.loc[hit, "approve"] = True
            out.loc[hit, "needs_input"] = False
    return out


def apply(props: pd.DataFrame, vmap: pd.DataFrame, overrides: dict, excluded: set) -> tuple[pd.DataFrame, dict, set, list]:
    """Apply approved proposals. Returns updated value map, overrides, exclusions and an audit list."""
    vmap = vmap.copy()
    audit = []
    for p in props[props.approve].itertuples():
        if p.action == "value_map":
            fid, src = p.target.rsplit("|", 1)
            hit = (vmap.field_id == fid) & (vmap.source_value == src)
            if hit.any():
                vmap.loc[hit, ["bureau_code", "status", "method"]] = [p.value, "SME approved", "SME revision"]
            else:
                vmap.loc[len(vmap)] = {"field_id": fid, "spec": "", "record": "", "field_name": p.field, "canonical": "",
                                       "source_value": src, "bureau_code": p.value, "code_description": "",
                                       "confidence": 1.0, "method": "SME revision", "status": "SME approved"}
        elif p.action == "override":
            if p.needs_input and not str(p.value).strip():
                continue
            table, row, col = p.target.split("|")
            overrides[(table, int(row), col)] = p.value
        elif p.action == "exclude":
            table, row, _ = p.target.split("|")
            excluded.add((table, int(row)))
        audit.append({"action": p.action, "field": p.field, "change": p.proposed, "rationale": p.rationale})
    return vmap, overrides, excluded, audit
