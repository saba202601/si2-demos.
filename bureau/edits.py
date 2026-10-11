"""Simulated bureau (DCO) intake: read the fixed-width file back by spec positions and run edits.

The edit catalog follows the rules written in the WCIO specifications (field class, code lists,
codes not applicable to NCCI, reserved codes, date formats, record totals) plus the cross-field
logic a DCO applies (accident inside the policy period, paid within incurred, medical-only claims
without indemnity, unit totals). Edit IDs are SI² identifiers, not official NCCI edit numbers.
"""
from __future__ import annotations

import datetime as dt

import pandas as pd

from . import catalog
from .generate import LINK_RECORD

VALID_CLASSES = {"8810", "8742", "5403", "5183", "5190", "7380", "9082", "8017", "8832", "9014", "8380", "7219",
                 "8868", "5645", "5022", "5221", "8018", "8829", "9015", "9052", "8601", "8835", "2003", "3632"}

EDITS = {
    "G01": ("Error", "Numeric field contains non-numeric characters", "Correct the value or its mapping so only digits are reported."),
    "G02": ("Error", "Value is not a valid code for this field", "Map the source value to a valid code from the spec pick list."),
    "G03": ("Error", "Code is reserved for future use", "Use an active code from the spec pick list."),
    "G04": ("Error", "Code is not applicable for NCCI", "Choose a code that applies to NCCI states."),
    "G05": ("Critical", "Date is not a valid date in the spec format", "Correct the source date."),
    "G06": ("Critical", "State code is not a valid NCCI state code", "Correct the state."),
    "G07": ("Error", "Required field is blank", "Populate the field from the source system."),
    "G08": ("Error", "Negative amount is not allowed in this field", "Correct the reserve or payment that makes the amount negative."),
    "S10": ("Error", "Classification code is not in the classification table", "Report the correct class code for the operation."),
    "S11": ("Critical", "Accident date is outside the policy period", "Verify the accident date or the policy the claim is attached to."),
    "S12": ("Error", "Paid amount exceeds incurred amount", "Incurred must include paid; correct the reserve."),
    "S13": ("Error", "Medical-only injury code (06) reported with indemnity", "Change the injury code or remove the indemnity amount."),
    "S14": ("Warning", "Closed claim still carries an outstanding reserve", "Close out the reserve or reopen the claim."),
    "S15": ("Critical", "Unit total does not equal the sum of the detail records", "Regenerate the unit so totals agree."),
    "S17": ("Error", "Exposure amount must be greater than zero", "Report the audited exposure."),
    "S18": ("Critical", "File control totals do not match the file", "Regenerate the file control record."),
    "S19": ("Warning", "Premium differs from exposure × rate by more than 2%", "Check the rate or premium."),
    "S20": ("Critical", "Policy expiration date is not after the effective date", "Correct the policy dates."),
    "P10": ("Error", "FEIN must be 9 digits and not all zeros", "Obtain the FEIN from the underwriting file."),
    "I10": ("Error", "Transaction To Date is before Transaction From Date", "Correct the payment period."),
    "I11": ("Error", "Payment date is before the accident date", "Verify the payment and accident dates."),
    "I13": ("Warning", "Transaction amount is zero", "Remove zero payments."),
    "M10": ("Error", "Paid amount exceeds the amount charged by provider", "Paid cannot exceed charges; correct the paid amount."),
    "M11": ("Error", "Service date is before the accident date", "Verify the date of service."),
    "M12": ("Error", "Paid procedure code is blank", "Report the procedure code from the bill."),
}

REQUIRED = {
    ("WCSTAT", "0"): ["CARRIER CODE", "POLICY NUMBER IDENTIFIER", "EXPOSURE STATE CODE", "POLICY EFFECTIVE DATE"],
    ("WCSTAT", "1"): ["POLICY EXPIRATION OR CANCELLATION DATE", "FEDERAL EMPLOYER IDENTIFICATION NUMBER (FEIN)"],
    ("WCSTAT", "4"): ["CLASSIFICATION CODE"],
    ("WCSTAT", "5"): ["CLASSIFICATION CODE", "ACCIDENT DATE", "CLAIM NUMBER", "INJURY CODE (INJURY TYPE)", "CLAIM/STATUS CODE"],
    ("WCPOLS", "02"): ["NAME OF INSURED"],
    ("WCPOLS", "05"): ["CLASSIFICATION CODE"],
    ("WCIND", "TRANSACTIONAL RECORD"): ["BENEFIT TYPE CODE", "CLAIM NUMBER IDENTIFIER", "TRANSACTION DATE"],
    ("WCMED", "MEDICAL DATA CALL RECORD"): ["PAID PROCEDURE CODE", "CLAIM NUMBER IDENTIFIER", "SERVICE DATE"],
}


def record_key_of(spec: str, line: str) -> str:
    if spec == "WCSTAT":
        return line[40:41]
    if spec == "WCPOLS":
        return line[45:47]
    if spec == "WCIND":
        return {"03": "FILE CONTROL RECORD", "01": "TRANSACTIONAL RECORD", "02": "QUARTERLY RECORD",
                "04": "KEY FIELD CHANGE RECORD"}.get(line[0:2], "UNKNOWN")
    return "FILE CONTROL RECORD" if line.startswith("SUBCTRLREC") else "MEDICAL DATA CALL RECORD"


def parse(spec: str, text: str) -> list[dict]:
    """Read the submitted file purely from spec positions (what the bureau sees)."""
    cache, out = {}, []
    for i, line in enumerate(text.rstrip("\n").split("\n"), start=1):
        key = record_key_of(spec, line)
        if key not in cache:
            fs = catalog.record_fields(spec, key).to_dict("records")
            if spec in LINK_RECORD and key != "9":
                fs = catalog.record_fields(spec, LINK_RECORD[spec]).to_dict("records") + [f for f in fs if f["name"] != "LINK DATA"]
            cache[key] = fs
        vals = {f["name"]: line[f["start"] - 1:f["end"]] for f in cache[key]}
        out.append({"seq": i, "record_key": key, "fields": cache[key], "values": vals, "line": line})
    return out


def _date(raw: str, field) -> dt.date | None:
    s = raw.strip()
    if not s or set(s) == {"0"}:
        return None
    fmt = field.get("format") or {8: "YYYYMMDD", 6: "YYMMDD", 5: "YYDDD"}.get(int(field["length"]), "")
    try:
        if fmt == "YYMMDD":
            return dt.datetime.strptime(s, "%y%m%d").date()
        if fmt == "YYYYMMDD":
            return dt.datetime.strptime(s, "%Y%m%d").date()
        if fmt == "YYDDD":
            return dt.datetime.strptime(s, "%y%j").date()
    except ValueError:
        return dt.date.min
    return None


def _num(raw: str, field) -> float:
    s = raw.strip()
    try:
        return int(s) / (10 ** int(field.get("implied_decimals") or 0))
    except ValueError:
        return 0.0


def _is_date_field(f) -> bool:
    n = f["name"]
    return f["class"] == "N" and ("DATE" in n) and int(f["length"]) in (5, 6, 8)


def run(spec: str, text: str, meta: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    recs = parse(spec, text)
    errs = []
    meta_by_seq = meta.set_index("seq") if len(meta) else pd.DataFrame()

    def add(rec, edit, field="", value="", positions="", extra=""):
        sev, msg, fix = EDITS[edit]
        m = meta_by_seq.loc[rec["seq"]] if rec["seq"] in meta_by_seq.index else None
        errs.append({"record_seq": rec["seq"], "record_type": catalog.RECORD_NAMES[spec].get(rec["record_key"], rec["record_key"]),
                     "policy": m["policy"] if m is not None else "", "claim": m["claim"] if m is not None else "",
                     "unit": m["unit"] if m is not None else "", "field": field, "positions": positions,
                     "value": str(value).strip(), "edit_id": edit, "severity": sev,
                     "message": msg + (f" ({extra})" if extra else ""), "suggested_fix": fix})

    def val(rec, name):
        return rec["values"].get(name, "")

    def fld(rec, name):
        return next((f for f in rec["fields"] if f["name"] == name), None)

    units = {}
    for rec in recs:
        key = rec["record_key"]
        state = catalog.STATE_FROM_CODE.get(val(rec, "EXPOSURE STATE CODE") or val(rec, "JURISDICTION STATE CODE"), "")
        for f in rec["fields"]:
            name, raw = f["name"], rec["values"][f["name"]]
            if name.startswith(("RESERVED", "FILLER")) or name == "LINK DATA":
                continue
            pos = f'{f["start"]}-{f["end"]}'
            s = raw.strip()
            if f["class"] == "N" and s and not f["codes"] and not (s.isdigit() or (s.startswith("-") and s[1:].isdigit() and f.get("signed"))):
                add(rec, "G08" if s.startswith("-") and s[1:].isdigit() else "G01", name, raw, pos)
                continue
            if f["codes"] and s and not (f["class"] == "N" and set(s) == {"0"} and s not in {c["code"] for c in f["codes"]}):
                codes = {c["code"]: c for c in f["codes"]}
                if s not in codes:
                    add(rec, "G02", name, raw, pos)
                elif codes[s]["reserved"]:
                    add(rec, "G03", name, raw, pos)
                elif "NCCI" in codes[s]["na_states"] or (state and state in codes[s]["na_states"]):
                    add(rec, "G04", name, raw, pos, f'code {s} N/A: {codes[s]["na_states"]}')
            if _is_date_field(f) and s and set(s) != {"0"} and _date(raw, f) == dt.date.min:
                add(rec, "G05", name, raw, pos)
            if "STATE CODE" in name and f["class"] == "N" and int(f["length"]) == 2 and s and set(s) != {"0"} \
                    and s not in catalog.STATE_FROM_CODE and "LINK" not in name and "UNEMPLOYMENT" not in name:
                add(rec, "G06", name, raw, pos)
        for name in REQUIRED.get((spec, key), []) + (REQUIRED.get((spec, LINK_RECORD.get(spec, "")), []) if key in ("1",) else []):
            f = fld(rec, name)
            if f is not None:
                s = rec["values"][name].strip()
                if not s or (set(s) == {"0"} and s not in {c["code"] for c in f["codes"]}):
                    add(rec, "P10" if "FEIN" in name else "G07", name, rec["values"][name], f'{f["start"]}-{f["end"]}')

        # ------------------------------------------------ cross-field edits
        if spec == "WCSTAT":
            ukey = (val(rec, "POLICY NUMBER IDENTIFIER"), val(rec, "EXPOSURE STATE CODE"), val(rec, "REPORT LEVEL CODE/REPORT NUMBER"))
            u = units.setdefault(ukey, {"exp": 0.0, "claims": 0, "ind": 0.0, "med": 0.0, "recs": 0, "total": None})
            if key in "123456":
                u["recs"] += 1
            eff = _date(val(rec, "POLICY EFFECTIVE DATE"), fld(rec, "POLICY EFFECTIVE DATE"))
            if key == "1":
                exp = _date(val(rec, "POLICY EXPIRATION OR CANCELLATION DATE"), fld(rec, "POLICY EXPIRATION OR CANCELLATION DATE"))
                u["eff"], u["expd"] = eff, exp
                if eff and exp and exp <= eff:
                    add(rec, "S20", "POLICY EXPIRATION OR CANCELLATION DATE", val(rec, "POLICY EXPIRATION OR CANCELLATION DATE"), "55-60")
            if key == "4":
                cls = val(rec, "CLASSIFICATION CODE").strip()
                if cls not in VALID_CLASSES:
                    add(rec, "S10", "CLASSIFICATION CODE", cls, "43-46")
                f = fld(rec, "EXPOSURE AMOUNT")
                amt = _num(val(rec, "EXPOSURE AMOUNT"), f)
                u["exp"] += amt
                if amt <= 0:
                    add(rec, "S17", "EXPOSURE AMOUNT", val(rec, "EXPOSURE AMOUNT"), "67-76")
                rate = _num(val(rec, "MANUAL/CHARGED RATE"), fld(rec, "MANUAL/CHARGED RATE"))
                prem = _num(val(rec, "PREMIUM AMOUNT"), fld(rec, "PREMIUM AMOUNT"))
                if amt > 0 and rate > 0 and abs(prem - amt * rate / 100) > max(2, 0.02 * prem):
                    add(rec, "S19", "PREMIUM AMOUNT", val(rec, "PREMIUM AMOUNT"), "77-85")
            if key == "5":
                u["claims"] += 1
                acc = _date(val(rec, "ACCIDENT DATE"), fld(rec, "ACCIDENT DATE"))
                u_exp = u.get("expd")
                if acc and acc != dt.date.min and eff and (acc < eff or (isinstance(u_exp, dt.date) and acc > u_exp)):
                    add(rec, "S11", "ACCIDENT DATE", val(rec, "ACCIDENT DATE"), "55-60", f"policy effective {eff:%m/%d/%Y}")
                cls = val(rec, "CLASSIFICATION CODE").strip()
                if cls not in VALID_CLASSES:
                    add(rec, "S10", "CLASSIFICATION CODE", cls, "43-46")
                inc_i = _num(val(rec, "INCURRED INDEMNITY AMOUNT"), fld(rec, "INCURRED INDEMNITY AMOUNT"))
                inc_m = _num(val(rec, "INCURRED MEDICAL AMOUNT"), fld(rec, "INCURRED MEDICAL AMOUNT"))
                pd_i = _num(val(rec, "PAID INDEMNITY AMOUNT"), fld(rec, "PAID INDEMNITY AMOUNT"))
                pd_m = _num(val(rec, "PAID MEDICAL AMOUNT"), fld(rec, "PAID MEDICAL AMOUNT"))
                u["ind"] += inc_i
                u["med"] += inc_m
                if pd_i > inc_i + 1:
                    add(rec, "S12", "PAID INDEMNITY AMOUNT", val(rec, "PAID INDEMNITY AMOUNT"), "174-182", f"incurred {inc_i:,.0f}")
                if pd_m > inc_m + 1:
                    add(rec, "S12", "PAID MEDICAL AMOUNT", val(rec, "PAID MEDICAL AMOUNT"), "183-191", f"incurred {inc_m:,.0f}")
                if val(rec, "INJURY CODE (INJURY TYPE)") == "06" and (inc_i > 0 or pd_i > 0):
                    add(rec, "S13", "INJURY CODE (INJURY TYPE)", "06", "79-80", f"indemnity {max(inc_i, pd_i):,.0f}")
                if val(rec, "CLAIM/STATUS CODE") == "1" and (inc_i + inc_m) - (pd_i + pd_m) > 1:
                    add(rec, "S14", "CLAIM/STATUS CODE", "1", "73-73")
            if key == "6":
                checks = [("EXPOSURE - PAYROLL TOTAL", u["exp"]), ("CLAIM COUNT TOTAL", u["claims"]),
                          ("INCURRED INDEMNITY AMOUNT TOTAL", u["ind"]), ("INCURRED MEDICAL AMOUNT TOTAL", u["med"]),
                          ("RECORDS IN UNIT REPORT TOTAL", u["recs"])]
                for name, expected in checks:
                    f = fld(rec, name)
                    got = _num(val(rec, name), f)
                    if abs(got - expected) > 1:
                        add(rec, "S15", name, val(rec, name), f'{f["start"]}-{f["end"]}', f"detail records sum to {expected:,.0f}")
            if key == "9":
                detail = sum(1 for r in recs if r["record_key"] in "123456")
                n_units = sum(1 for r in recs if r["record_key"] == "1")
                if _num(val(rec, "DETAIL RECORD COUNT TOTAL"), fld(rec, "DETAIL RECORD COUNT TOTAL")) != detail:
                    add(rec, "S18", "DETAIL RECORD COUNT TOTAL", val(rec, "DETAIL RECORD COUNT TOTAL"), "42-49", f"file has {detail}")
                if _num(val(rec, "UNIT REPORTS SUBMITTED TOTAL"), fld(rec, "UNIT REPORTS SUBMITTED TOTAL")) != n_units:
                    add(rec, "S18", "UNIT REPORTS SUBMITTED TOTAL", val(rec, "UNIT REPORTS SUBMITTED TOTAL"), "50-56", f"file has {n_units}")

        elif spec == "WCPOLS":
            if key == "02":
                fein = val(rec, "FEDERAL EMPLOYER IDENTIFICATION NUMBER (FEIN)").strip()
                if not fein.isdigit() or set(fein) == {"0"} or len(fein) != 9:
                    add(rec, "P10", "FEDERAL EMPLOYER IDENTIFICATION NUMBER (FEIN)", fein, "149-157")
            if key == "05":
                cls = val(rec, "CLASSIFICATION CODE").strip()
                if cls not in VALID_CLASSES:
                    add(rec, "S10", "CLASSIFICATION CODE", cls, "51-54")
                amt = _num(val(rec, "ESTIMATED EXPOSURE AMOUNT"), fld(rec, "ESTIMATED EXPOSURE AMOUNT"))
                if amt <= 0:
                    add(rec, "S17", "ESTIMATED EXPOSURE AMOUNT", val(rec, "ESTIMATED EXPOSURE AMOUNT"), "95-106")

        elif spec == "WCIND":
            if key == "TRANSACTIONAL RECORD":
                fd, td = (_date(val(rec, n), fld(rec, n)) for n in ("TRANSACTION FROM DATE", "TRANSACTION TO DATE"))
                tx, acc = (_date(val(rec, n), fld(rec, n)) for n in ("TRANSACTION DATE", "ACCIDENT DATE"))
                eff = _date(val(rec, "POLICY EFFECTIVE DATE"), fld(rec, "POLICY EFFECTIVE DATE"))
                if fd and td and td < fd:
                    add(rec, "I10", "TRANSACTION TO DATE", val(rec, "TRANSACTION TO DATE"), "94-101")
                if tx and acc and tx < acc:
                    add(rec, "I11", "TRANSACTION DATE", val(rec, "TRANSACTION DATE"), "5-12")
                if acc and eff and acc < eff:
                    add(rec, "S11", "ACCIDENT DATE", val(rec, "ACCIDENT DATE"), "76-83", f"policy effective {eff:%m/%d/%Y}")
                if _num(val(rec, "TRANSACTION AMOUNT"), fld(rec, "TRANSACTION AMOUNT")) == 0:
                    add(rec, "I13", "TRANSACTION AMOUNT", val(rec, "TRANSACTION AMOUNT"), "102-113")
            if key == "FILE CONTROL RECORD":
                if _num(val(rec, "RECORD TOTAL"), fld(rec, "RECORD TOTAL")) != len(recs):
                    add(rec, "S18", "RECORD TOTAL", val(rec, "RECORD TOTAL"), "58-68", f"file has {len(recs)}")

        elif spec == "WCMED":
            if key == "MEDICAL DATA CALL RECORD":
                chg = _num(val(rec, "AMOUNT CHARGED BY PROVIDER"), fld(rec, "AMOUNT CHARGED BY PROVIDER"))
                paid = _num(val(rec, "PAID AMOUNT"), fld(rec, "PAID AMOUNT"))
                if paid > chg + 0.01:
                    add(rec, "M10", "PAID AMOUNT", val(rec, "PAID AMOUNT"), "197-207", f"charged {chg:,.2f}")
                svc, acc = (_date(val(rec, n), fld(rec, n)) for n in ("SERVICE DATE", "ACCIDENT DATE"))
                if svc and acc and svc < acc:
                    add(rec, "M11", "SERVICE DATE", val(rec, "SERVICE DATE"), "129-136")
                if not val(rec, "PAID PROCEDURE CODE").strip():
                    errs[:] = [e for e in errs if not (e["record_seq"] == rec["seq"] and e["edit_id"] == "G07")]
                    add(rec, "M12", "PAID PROCEDURE CODE", "", "153-177")
            if key == "FILE CONTROL RECORD":
                if _num(val(rec, "RECORD TOTAL"), fld(rec, "RECORD TOTAL")) != len(recs):
                    add(rec, "S18", "RECORD TOTAL", val(rec, "RECORD TOTAL"), "66-76", f"file has {len(recs)}")

    err = pd.DataFrame(errs, columns=["record_seq", "record_type", "policy", "claim", "unit", "field", "positions",
                                      "value", "edit_id", "severity", "message", "suggested_fix"])
    crit_units = set(err[err.severity == "Critical"].unit) - {""}
    file_crit = bool(((err.severity == "Critical") & (err.unit == "")).any())
    all_units = set(meta.unit) - {""} if len(meta) else set()
    if file_crit:
        status = "Rejected"
    elif crit_units:
        status = "Partially accepted"
    elif len(err[err.severity == "Error"]):
        status = "Accepted with errors"
    else:
        status = "Accepted"
    resp = {"status": status, "records": len(recs), "units": len(all_units),
            "units_rejected": len(crit_units), "critical": int((err.severity == "Critical").sum()),
            "errors": int((err.severity == "Error").sum()), "warnings": int((err.severity == "Warning").sum()),
            "received": dt.datetime.now().strftime("%Y-%m-%d %H:%M")}
    return err, resp
