"""Build bureau submission files from canonical data, driven entirely by the spec catalog.

For every record, each spec field gets its value from (in order): the spec constant (e.g. Record
Type Code "5"), the SME-approved field map (canonical column or SI²-derived value), or blank/zero
fill. Values then pass through the approved pick-list map, NCCI state codes, date formats and
implied decimals before being written at the exact positions in the spec.
"""
from __future__ import annotations

import datetime as dt
import io
import uuid

import pandas as pd

from . import catalog, canonical

# Which canonical / derived tables can feed each record.
RECORD_SOURCES = {
    ("WCSTAT", "0"): ["policy", "policy_state", "unit"],
    ("WCSTAT", "1"): ["policy", "policy_state", "unit"],
    ("WCSTAT", "2"): ["policy"], ("WCSTAT", "3"): ["policy"],
    ("WCSTAT", "4"): ["exposure", "policy_state", "unit"],
    ("WCSTAT", "5"): ["claim", "unit"], ("WCSTAT", "6"): ["unit"], ("WCSTAT", "9"): ["file"],
    ("WCPOLS", "00"): ["policy", "txn"], ("WCPOLS", "01"): ["policy", "txn"], ("WCPOLS", "02"): ["policy", "txn"],
    ("WCPOLS", "03"): ["policy", "txn"], ("WCPOLS", "04"): ["policy_state", "policy", "txn"],
    ("WCPOLS", "05"): ["exposure", "txn"],
    ("WCIND", "FILE CONTROL RECORD"): ["file"],
    ("WCIND", "TRANSACTIONAL RECORD"): ["indemnity_payment", "claim", "policy", "txn"],
    ("WCIND", "QUARTERLY RECORD"): ["claim", "policy", "txn", "qtr"],
    ("WCMED", "FILE CONTROL RECORD"): ["file"],
    ("WCMED", "MEDICAL DATA CALL RECORD"): ["medical_bill_line", "claim", "policy", "txn"],
}
OUTPUT_RECORDS = {
    "WCSTAT": ["1", "2", "3", "4", "5", "6", "9"],
    "WCPOLS": ["01", "02", "03", "04", "05"],
    "WCIND": ["FILE CONTROL RECORD", "TRANSACTIONAL RECORD", "QUARTERLY RECORD"],
    "WCMED": ["FILE CONTROL RECORD", "MEDICAL DATA CALL RECORD"],
}
LINK_RECORD = {"WCSTAT": "0", "WCPOLS": "00"}

# Values SI² derives at generation time (column -> (type, the spec field names it feeds)).
DERIVED_COLS = {
    "unit": {
        "report_level_code": ("text", ["REPORT LEVEL CODE/REPORT NUMBER"]),
        "correction_sequence_number": ("text", ["CORRECTION SEQUENCE NUMBER"]),
        "correction_type_code": ("text", ["CORRECTION TYPE CODE"]),
        "state_effective_date": ("date", ["STATE EFFECTIVE DATE"]),
        "experience_modification_effective_date": ("date", ["EXPERIENCE MODIFICATION/MERIT RATING FACTOR EFFECTIVE DATE"]),
        "estimated_audit_code": ("text", ["ESTIMATED AUDIT CODE"]),
        "interstate_rated_policy_indicator": ("text", ["INTERSTATE RATED POLICY INDICATOR"]),
        "type_of_non_standard_id_code": ("text", ["TYPE OF NON-STANDARD ID CODE"]),
        "experience_modification_effective_date": ("date", ["EXPERIENCE MODIFICATION/MERIT RATING FACTOR EFFECTIVE DATE"]),
        "basis_of_deductible_calculation_code": ("text", ["BASIS OF DEDUCTIBLE CALCULATION CODE"]),
        "split_period_code": ("text", ["SPLIT PERIOD CODE"]),
        "three_year_fixed_rate_policy_indicator": ("text", ["THREE-YEAR FIXED RATE POLICY INDICATOR"]),
        "managed_care_organization_policy_indicator": ("text", ["MANAGED CARE ORGANIZATION (MCO) POLICY INDICATOR"]),
        "certified_health_care_network_policy_indicator": ("text", ["CERTIFIED HEALTH CARE NETWORK POLICY INDICATOR"]),
        "exposure_payroll_total": ("money", ["EXPOSURE - PAYROLL TOTAL"]),
        "subject_premium_total": ("money", ["SUBJECT PREMIUM TOTAL"]),
        "standard_premium_total": ("money", ["STANDARD PREMIUM TOTAL"]),
        "claim_count_total": ("int", ["CLAIM COUNT TOTAL"]),
        "incurred_indemnity_amount_total": ("money", ["INCURRED INDEMNITY AMOUNT TOTAL"]),
        "incurred_medical_amount_total": ("money", ["INCURRED MEDICAL AMOUNT TOTAL"]),
        "records_in_unit_report_total": ("int", ["RECORDS IN UNIT REPORT TOTAL"]),
        "paid_indemnity_amount_total": ("money", ["PAID INDEMNITY AMOUNT TOTAL"]),
        "paid_medical_amount_total": ("money", ["PAID MEDICAL AMOUNT TOTAL"]),
        "paid_alae_total": ("money", ["PAID ALLOCATED LOSS ADJUSTMENT EXPENSE (ALAE) TOTAL"]),
        "incurred_alae_total": ("money", ["INCURRED ALLOCATED LOSS ADJUSTMENT EXPENSE (ALAE) TOTAL"]),
    },
    "file": {
        "detail_record_count_total": ("int", ["DETAIL RECORD COUNT TOTAL"]),
        "unit_reports_submitted_total": ("int", ["UNIT REPORTS SUBMITTED TOTAL"]),
        "primary_effective_year": ("int", ["PRIMARY EFFECTIVE YEAR"]),
        "primary_effective_month": ("int", ["PRIMARY EFFECTIVE MONTH"]),
        "record_total": ("int", ["RECORD TOTAL"]),
        "carrier_group_code": ("text", ["CARRIER GROUP CODE"]),
        "reporting_quarter_code": ("text", ["REPORTING QUARTER CODE"]),
        "reporting_year": ("int", ["REPORTING YEAR"]),
        "submission_file_identifier": ("text", ["SUBMISSION FILE IDENTIFIER"]),
        "submission_date": ("date", ["SUBMISSION DATE"]),
        "submission_time": ("text", ["SUBMISSION TIME"]),
        "submission_file_type_code": ("text", ["SUBMISSION FILE TYPE CODE"]),
        "file_record_type_code": ("text", ["RECORD TYPE CODE"]),
    },
    "qtr": {"quarterly_transaction_date": ("date", ["TRANSACTION DATE"])},
    "txn": {
        "transaction_code": ("text", ["TRANSACTION CODE"]),
        "record_type_code": ("text", ["RECORD TYPE CODE"]),
        "name_type_code": ("text", ["NAME TYPE CODE"]),
        "address_type_code": ("text", ["ADDRESS TYPE CODE"]),
        "address_structure_code": ("text", ["ADDRESS STRUCTURE CODE"]),
        "foreign_address_indicator": ("text", ["FOREIGN ADDRESS INDICATOR"]),
        "policy_term_code": ("text", ["POLICY TERM CODE"]),
        "experience_rating_code": ("text", ["EXPERIENCE RATING CODE"]),
        "classification_use_code": ("text", ["CLASSIFICATION USE CODE"]),
        "type_of_non_standard_id_code": ("text", ["TYPE OF NON-STANDARD ID CODE"]),
        "experience_modification_effective_date": ("date", ["EXPERIENCE MODIFICATION/MERIT RATING FACTOR EFFECTIVE DATE"]),
        "exposure_period_code": ("text", ["EXPOSURE PERIOD CODE"]),
        "exposure_period_effective_date": ("date", ["EXPOSURE PERIOD EFFECTIVE DATE"]),
        "experience_modification_status_code": ("text", ["EXPERIENCE MODIFICATION/MERIT RATING STATUS CODE"]),
        "claimant_birth_year": ("int", ["BIRTH YEAR"]),
        "employment_status_code": ("text", ["EMPLOYMENT STATUS CODE"]),
    },
}
PENALTY = {"PREVIOUS", "ORIGINAL", "PRIOR", "SEPARATED", "REPLACEMENT", "CONTINUATION", "OTHER", "SECONDARY",
           "TOTAL", "MINIMUM", "DEPOSIT", "CHANGE", "ANNIVERSARY", "COUNTER", "LINK", "FROM", "TO", "SUFFIX",
           "AGGREGATE", "PERCENTAGE", "OFFSET", "ADMINISTRATOR", "LEASING", "PHONE"}
DERIVED_ALIASES = {"loss_coverage_act": ["LOSS COVERAGE ACT CODE", "ACT—LOSS CONDITION CODE"],
                   "incurred_alae": ["INCURRED ALLOCATED LOSS ADJUSTMENT EXPENSE (ALAE)",
                                     "INCURRED ALLOCATED LOSS ADJUSTMENT EXPENSE"]}


def _candidates(tables):
    out = []
    for t in tables:
        if t in canonical.SCHEMA:
            for c, (typ, desc, aliases) in canonical.SCHEMA[t].items():
                out.append((t, c, typ, [c.replace("_", " ")] + aliases))
            for c, desc in canonical.DERIVED.get(t, {}).items():
                out.append((t, c, "derived", [c.replace("_", " ")] + DERIVED_ALIASES.get(c, [])))
        for c, (typ, names) in DERIVED_COLS.get(t, {}).items():
            out.append((t, c, typ, names))
    return out


def _score(field_name: str, names: list[str], typ: str = "") -> float:
    ftoks = set(canonical._tokens(field_name))
    date_mismatch = field_name.endswith("DATE") and typ not in ("date", "derived")
    best = 0.0
    for n in names:
        s = canonical.similarity(field_name, n)
        ntoks = set(canonical._tokens(n))
        if (ftoks & PENALTY) - ntoks:
            s *= 0.4
        if n.upper() == field_name.upper():
            s = 1.0
        elif date_mismatch:
            s *= 0.4
        best = max(best, s)
    return best


def auto_map_fields(spec: str) -> pd.DataFrame:
    """Canonical -> bureau field map for every field of the records this workbench produces."""
    rows = []
    keys = ([LINK_RECORD[spec]] if spec in LINK_RECORD else []) + OUTPUT_RECORDS[spec]
    for key in keys:
        cands = _candidates(RECORD_SOURCES[(spec, key)])
        for _, f in catalog.record_fields(spec, key).iterrows():
            base = {"field_id": f.field_id, "spec": spec, "record_key": key, "record_name": f.record_name,
                    "field_no": f.field_no, "field_name": f["name"], "start": f.start, "end": f.end,
                    "class": f["class"], "pick_list": "Yes" if f.codes else ""}
            n = f["name"]
            if n.startswith(("RESERVED", "FILLER")):
                rows.append({**base, "source": "Reserved", "canonical": "", "confidence": 1.0, "status": "Auto-approved"})
                continue
            if n == "LINK DATA":
                rows.append({**base, "source": "Link data", "canonical": f"record {LINK_RECORD.get(spec)}",
                             "confidence": 1.0, "status": "Auto-approved"})
                continue
            if f.constant:
                rows.append({**base, "source": "Spec constant", "canonical": f'"{f.constant}"', "confidence": 1.0,
                             "status": "Auto-approved"})
                continue
            scored = sorted(((_score(n, names, typ), t, c) for t, c, typ, names in cands), reverse=True)
            s, t, c = scored[0] if scored else (0, "", "")
            if s >= 0.72:
                rows.append({**base, "source": "SI² derived" if t in DERIVED_COLS else "Canonical",
                             "canonical": f"{t}.{c}", "confidence": round(s, 2),
                             "status": "Auto-approved" if s >= 0.85 else "Needs SME review"})
            else:
                rows.append({**base, "source": "Not reported", "canonical": "", "confidence": round(s, 2),
                             "status": "Blank/zero fill" if (f.not_applicable or f.optional or s < 0.5) else "Needs SME review"})
    return pd.DataFrame(rows)


# ----------------------------------------------------------------------------------- encoding
def _date_fmt(field) -> str:
    fmt = field.get("format", "") if isinstance(field, dict) else field.format
    length = field["length"]
    if fmt in ("YYMMDD", "YYYYMMDD", "YYDDD", "MMDDYY", "MMDDYYYY"):
        return fmt
    return {8: "YYYYMMDD", 6: "YYMMDD", 5: "YYDDD", 4: "YYYY"}.get(length, "YYYYMMDD")


def encode(field, value, typ: str = "") -> str:
    L, cls = int(field["length"]), field["class"]
    if value is None or (isinstance(value, float) and pd.isna(value)) or (isinstance(value, str) and value == ""):
        return "0" * L if cls == "N" else " " * L
    if isinstance(value, (dt.date, dt.datetime)):
        f = _date_fmt(field)
        s = {"YYMMDD": value.strftime("%y%m%d"), "YYYYMMDD": value.strftime("%Y%m%d"),
             "YYDDD": value.strftime("%y") + f"{value.timetuple().tm_yday:03d}", "YYYY": value.strftime("%Y"),
             "MMDDYY": value.strftime("%m%d%y"), "MMDDYYYY": value.strftime("%m%d%Y")}[f]
        return s[:L].rjust(L, "0")
    if isinstance(value, (int, float)) and not isinstance(value, bool) and cls == "N":
        d = int(field["implied_decimals"] or 0)
        n = int(round(float(value) * (10 ** d)))
        s = str(abs(n))
        if n < 0:
            return ("-" + s.zfill(L - 1))[-L:] if len(s) < L else "-" + s[-(L - 1):]
        return s.zfill(L)[-L:]
    s = str(value).upper()
    if isinstance(value, float) and value.is_integer():
        s = str(int(value))
    if cls == "N":
        return s.zfill(L)[-L:] if s.isdigit() else s.ljust(L)[:L]
    return s.ljust(L)[:L]


def _is_state_field(f) -> bool:
    n = f["name"]
    return ("STATE CODE" in n or n.endswith("STATE")) and f["class"] == "N" and int(f["length"]) == 2


# ----------------------------------------------------------------------------------- value maps
def derived_domains(canon: dict[str, pd.DataFrame], spec: str = "") -> dict:
    """Possible values of SI²-derived columns that feed pick-list fields."""
    txn = sorted(set(canon["policy"].transaction_type.dropna().astype(str))) if spec == "WCPOLS" else ["01"]
    return {"transaction_code": txn,
            "name_type_code": ["2"], "address_type_code": ["1"], "address_structure_code": ["2"],
            "foreign_address_indicator": ["N"], "policy_term_code": ["1"], "experience_rating_code": ["3", "5"],
            "classification_use_code": ["B"], "exposure_period_code": ["1"],
            "experience_modification_status_code": ["1", "3"], "type_of_non_standard_id_code": ["01"],
            "employment_status_code": ["1"], "submission_file_type_code": ["O", "R"],
            "reporting_quarter_code": ["1", "2", "3", "4"], "estimated_audit_code": ["N"],
            "interstate_rated_policy_indicator": ["N"], "basis_of_deductible_calculation_code": ["00", "01"],
            "split_period_code": ["0"], "three_year_fixed_rate_policy_indicator": ["N"],
            "managed_care_organization_policy_indicator": ["N"], "certified_health_care_network_policy_indicator": ["N"],
            "correction_type_code": ["E", "H", "L", "M"], "report_level_code": list("123456789A")}


def auto_value_map(canon: dict[str, pd.DataFrame], fmap: pd.DataFrame, derived_values: dict | None = None) -> pd.DataFrame:
    cat = catalog.load().set_index("field_id")
    spec = fmap.spec.iloc[0] if len(fmap) else ""
    derived_values = derived_values or derived_domains(canon, spec)
    rows = []
    for _, m in fmap[(fmap.pick_list == "Yes") & fmap.source.isin(["Canonical", "SI² derived"])].iterrows():
        f = cat.loc[m.field_id]
        t, c = m.canonical.split(".")
        if t in canon and c in canon[t]:
            values = sorted({str(v) for v in canon[t][c].dropna().unique() if str(v) != ""})
        else:
            values = sorted(derived_values.get(c, []))
        for v in values:
            code, conf, how = canonical.map_value(f["name"], v, f.codes)
            rows.append({"field_id": m.field_id, "spec": m.spec, "record": m.record_name, "field_name": f["name"],
                         "canonical": m.canonical, "source_value": v, "bureau_code": code,
                         "code_description": catalog.pick_list(f).get(code, ""), "confidence": conf, "method": how,
                         "status": "Auto-approved" if conf >= 0.85 else "Needs SME review"})
    return pd.DataFrame(rows, columns=["field_id", "spec", "record", "field_name", "canonical", "source_value",
                                       "bureau_code", "code_description", "confidence", "method", "status"])


# ----------------------------------------------------------------------------------- record builders
def _months_between(a: dt.date, b: dt.date) -> int:
    return (b.year - a.year) * 12 + (b.month - a.month)


def _month_end(ym: str) -> dt.date:
    y, m = map(int, ym.split("-"))
    nxt = dt.date(y + (m == 12), m % 12 + 1, 1)
    return nxt - dt.timedelta(days=1)


LEVEL_CODES = "123456789A"


class Builder:
    def __init__(self, spec, canon, fmap, vmap, settings, corrections=None, revision=0, only_units=None):
        self.spec, self.canon, self.settings = spec, canon, settings
        self.fmap = {r["field_id"]: r for r in fmap.to_dict("records")}
        self._fields = {}
        self.vmap = {(r.field_id, r.source_value): r.bureau_code for r in vmap.itertuples() if r.bureau_code}
        self.cat = catalog.load()
        self.corrections = corrections or {}      # unit key -> correction type code
        self.revision = revision
        self.only_units = only_units
        self.records = []

    # one record = dict(record_key, ctx, ref)
    def _emit(self, key, ctx, ref):
        self.records.append({"record_key": key, "ctx": ctx, "ref": ref})

    def fields(self, key):
        if key not in self._fields:
            self._fields[key] = catalog.record_fields(self.spec, key).to_dict("records")
        return self._fields[key]

    def _value(self, f, ctx):
        m = self.fmap.get(f["field_id"])
        if f["constant"]:
            return f["constant"], "text"
        if m is None or m["source"] in ("Reserved", "Not reported", "Link data") or not m["canonical"]:
            return None, ""
        t, c = m["canonical"].split(".")
        row = ctx.get(t) or {}
        v = row.get(c)
        typ = canonical.SCHEMA.get(t, {}).get(c, (DERIVED_COLS.get(t, {}).get(c, ("text",))[0],))[0]
        if f["codes"] and v not in (None, ""):
            v = self.vmap.get((f["field_id"], str(v)), v)
        elif _is_state_field(f) and isinstance(v, str) and v in catalog.NCCI_STATE:
            v = catalog.NCCI_STATE[v]
        if typ == "derived" and isinstance(v, str):
            typ = "text"
        return v, typ

    def render(self, rec) -> str:
        key, ctx = rec["record_key"], rec["ctx"]
        length = catalog.SPEC_INFO[self.spec]["record_length"]
        buf = [" "] * length
        link = None
        if self.spec in LINK_RECORD and key != "9":
            link = "".join(encode(f, *self._value(f, ctx)) for f in self.fields(LINK_RECORD[self.spec]))
        values = {}
        for f in self.fields(key):
            if f["name"] == "LINK DATA" and link is not None:
                s = link.ljust(int(f["length"]))[: int(f["length"])]
            else:
                v, typ = self._value(f, ctx)
                s = encode(f, v, typ)
                values[f["field_id"]] = s
            buf[f["start"] - 1: f["end"]] = list(s)
        rec["values"] = values
        return "".join(buf)[:length]

    # ------------------------------------------------------------------ WCSTAT
    def build_wcstat(self, months):
        c = self.canon
        pol = c["policy"].set_index("policy_number", drop=False)
        units = []
        for ps in c["policy_state"].to_dict("records"):
            if ps["policy_number"] not in pol.index:
                continue
            p = pol.loc[ps["policy_number"]].to_dict()
            eff = p["policy_effective_date"]
            if not eff:
                continue
            for ym in months:
                val = _month_end(ym)
                diff = _months_between(eff, val)
                if diff >= 18 and (diff - 18) % 12 == 0 and (diff - 18) // 12 < 10:
                    units.append((p, ps, LEVEL_CODES[(diff - 18) // 12], val))
        exp_by = c["exposure"].groupby(["policy_number", "state"])
        clm = c["claim"]
        unit_count, detail = 0, 0
        min_eff = None
        for p, ps, level, val in sorted(units, key=lambda u: (u[0]["policy_number"], u[1]["state"])):
            ukey = f'{p["policy_number"]}|{ps["state"]}|{level}'
            if self.only_units is not None and ukey not in self.only_units:
                continue
            corr = self.corrections.get(ukey)
            exps = exp_by.get_group((p["policy_number"], ps["state"])).to_dict("records") \
                if (p["policy_number"], ps["state"]) in exp_by.groups else []
            losses = clm[(clm.policy_number == p["policy_number"]) & (clm.jurisdiction_state == ps["state"])]
            losses = [r for r in losses.to_dict("records") if r["accident_date"] and r["accident_date"] <= val]
            unit = {
                "report_level_code": level, "correction_sequence_number": str(min(self.revision, 9)) if corr else "0",
                "correction_type_code": corr or "", "state_effective_date": p["policy_effective_date"],
                "experience_modification_effective_date": p["policy_effective_date"],
                "estimated_audit_code": "N", "interstate_rated_policy_indicator": "N",
                "type_of_non_standard_id_code": "01",
                "basis_of_deductible_calculation_code": "01" if p.get("deductible_amount") else "00",
                "split_period_code": "0", "three_year_fixed_rate_policy_indicator": "N",
                "managed_care_organization_policy_indicator": "N", "certified_health_care_network_policy_indicator": "N",
                "exposure_payroll_total": sum(e["exposure_amount"] for e in exps),
                "subject_premium_total": round(sum(e["premium_amount"] for e in exps), 0),
                "standard_premium_total": round(ps["estimated_state_standard_premium"], 0),
                "claim_count_total": len(losses),
                "incurred_indemnity_amount_total": round(sum(r["incurred_indemnity_amount"] for r in losses), 0),
                "incurred_medical_amount_total": round(sum(r["incurred_medical_amount"] for r in losses), 0),
                "records_in_unit_report_total": 4 + len(exps) + len(losses),
                "paid_indemnity_amount_total": round(sum(r["paid_indemnity_amount"] for r in losses), 0),
                "paid_medical_amount_total": round(sum(r["paid_medical_amount"] for r in losses), 0),
                "paid_alae_total": round(sum(r["paid_alae"] for r in losses), 0),
                "incurred_alae_total": round(sum(r["incurred_alae"] for r in losses), 0),
            }
            base = {"policy": p, "policy_state": ps, "unit": unit}
            ref = {"unit": ukey, "policy": p["policy_number"], "state": ps["state"], "valuation": val.isoformat()}
            self._emit("1", base, {**ref, "table": "policy", "row": p["_row"]})
            self._emit("2", base, {**ref, "table": "policy", "row": p["_row"]})
            self._emit("3", base, {**ref, "table": "policy", "row": p["_row"]})
            for e in exps:
                self._emit("4", {**base, "exposure": e}, {**ref, "table": "exposure", "row": e["_row"]})
            for r in losses:
                r = {**r, "incurred_indemnity_amount": round(r["incurred_indemnity_amount"], 0),
                     "incurred_medical_amount": round(r["incurred_medical_amount"], 0)}
                self._emit("5", {**base, "claim": r}, {**ref, "table": "claim", "row": r["_row"], "claim": r["claim_number"]})
            self._emit("6", base, {**ref, "table": "policy_state", "row": ps["_row"]})
            unit_count += 1
            detail += 4 + len(exps) + len(losses)
            min_eff = min(min_eff or p["policy_effective_date"], p["policy_effective_date"])
        fc = {"detail_record_count_total": detail, "unit_reports_submitted_total": unit_count,
              "primary_effective_year": (min_eff or dt.date.today()).year,
              "primary_effective_month": (min_eff or dt.date.today()).month}
        self._emit("9", {"file": fc}, {"table": "file"})

    # ------------------------------------------------------------------ WCPOLS
    def build_wcpols(self, months):
        c = self.canon
        ps_by = c["policy_state"].groupby("policy_number")
        ex_by = c["exposure"].groupby("policy_number")
        for p in c["policy"].sort_values("policy_number").to_dict("records"):
            d = p["transaction_issue_date"]
            if not d or d.strftime("%Y-%m") not in months:
                continue
            if self.only_units is not None and p["policy_number"] not in self.only_units:
                continue
            states = ps_by.get_group(p["policy_number"]).to_dict("records") if p["policy_number"] in ps_by.groups else []
            rated = any(s["experience_modification_factor"] not in (0, 1, 1.0) for s in states)
            txn = {"transaction_code": p["transaction_type"], "name_type_code": "2", "address_type_code": "1",
                   "address_structure_code": "2", "foreign_address_indicator": "N", "policy_term_code": "1",
                   "experience_rating_code": "3" if rated else "5", "classification_use_code": "B",
                   "exposure_period_code": "1", "exposure_period_effective_date": p["policy_effective_date"],
                   "experience_modification_status_code": "1" if rated else "3",
                   "type_of_non_standard_id_code": "01",
                   "experience_modification_effective_date": p["policy_effective_date"]}
            base = {"policy": p, "txn": txn}
            ref = {"policy": p["policy_number"], "table": "policy", "row": p["_row"], "unit": p["policy_number"]}
            for k in ("01", "02", "03"):
                self._emit(k, base, ref)
            for s in states:
                self._emit("04", {**base, "policy_state": s}, {**ref, "table": "policy_state", "row": s["_row"]})
            for e in (ex_by.get_group(p["policy_number"]).to_dict("records") if p["policy_number"] in ex_by.groups else []):
                self._emit("05", {**base, "exposure": e}, {**ref, "table": "exposure", "row": e["_row"]})

    def _file(self, months, count):
        last = max(months)
        y, m = map(int, last.split("-"))
        now = dt.datetime.now()
        return {"record_total": count, "carrier_group_code": self.settings["carrier_group_code"],
                "reporting_quarter_code": str((m - 1) // 3 + 1), "reporting_year": y,
                "submission_file_identifier": f"SI2{self.spec}{y}Q{(m - 1) // 3 + 1}R{self.revision}",
                "submission_date": now.date(), "submission_time": now.strftime("%H%M%S"),
                "submission_file_type_code": "R" if self.revision else "O"}

    # ------------------------------------------------------------------ WCIND
    def build_wcind(self, months):
        c = self.canon
        clm = c["claim"].set_index("claim_number", drop=False)
        pol = c["policy"].set_index("policy_number", drop=False)
        pays = c["indemnity_payment"]
        sel = pays[[bool(d) and d.strftime("%Y-%m") in months for d in pays.transaction_date]]
        body = []
        for pmt in sel.sort_values(["claim_number", "transaction_date"]).to_dict("records"):
            if pmt["claim_number"] not in clm.index:
                continue
            cl = clm.loc[pmt["claim_number"]].to_dict()
            p = pol.loc[cl["policy_number"]].to_dict() if cl["policy_number"] in pol.index else {}
            body.append(("TRANSACTIONAL RECORD", {"indemnity_payment": pmt, "claim": cl, "policy": p,
                                                  "txn": {"transaction_code": "01", "record_type_code": "01"}},
                         {"table": "indemnity_payment", "row": pmt["_row"], "claim": cl["claim_number"],
                          "policy": cl["policy_number"], "unit": cl["claim_number"]}))
        q_end = _month_end(max(months))
        for cl in c["claim"].to_dict("records"):
            if cl["paid_indemnity_amount"] <= 0 or not cl["accident_date"] or cl["accident_date"] > q_end:
                continue
            if cl["closing_date"] and cl["closing_date"] < q_end - dt.timedelta(days=92):
                continue
            p = pol.loc[cl["policy_number"]].to_dict() if cl["policy_number"] in pol.index else {}
            body.append(("QUARTERLY RECORD", {"claim": cl, "policy": p, "txn": {
                "record_type_code": "02", "claimant_birth_year": cl["birth_year"], "employment_status_code": "1",
                }, "qtr": {"quarterly_transaction_date": q_end}},
                {"table": "claim", "row": cl["_row"], "claim": cl["claim_number"], "policy": cl["policy_number"],
                 "unit": cl["claim_number"]}))
        self._emit("FILE CONTROL RECORD", {"file": {**self._file(months, len(body) + 1), "file_record_type_code": "03"}},
                   {"table": "file"})
        for k, ctx, ref in body:
            self._emit(k, ctx, ref)

    # ------------------------------------------------------------------ WCMED
    def build_wcmed(self, months):
        c = self.canon
        clm = c["claim"].set_index("claim_number", drop=False)
        pol = c["policy"].set_index("policy_number", drop=False)
        bills = c["medical_bill_line"]
        sel = bills[[bool(d) and d.strftime("%Y-%m") in months for d in bills.transaction_date]]
        body = []
        for b in sel.sort_values(["claim_number", "bill_identification_number", "line_identification_number"]).to_dict("records"):
            if b["claim_number"] not in clm.index:
                continue
            cl = clm.loc[b["claim_number"]].to_dict()
            p = pol.loc[cl["policy_number"]].to_dict() if cl["policy_number"] in pol.index else {}
            b = {**b, "provider_postal_code": str(b["provider_postal_code"])[:3]}
            body.append(("MEDICAL DATA CALL RECORD", {"medical_bill_line": b, "claim": cl, "policy": p, "txn": {
                "transaction_code": "01", "claimant_birth_year": cl["birth_year"]}},
                {"table": "medical_bill_line", "row": b["_row"], "claim": cl["claim_number"],
                 "policy": cl["policy_number"], "unit": b["bill_identification_number"]}))
        self._emit("FILE CONTROL RECORD", {"file": {**self._file(months, len(body) + 1), "file_record_type_code": "SUBCTRLREC"}},
                   {"table": "file"})
        for k, ctx, ref in body:
            self._emit(k, ctx, ref)


def generate(spec: str, months: list[str], canon, fmap, vmap, settings, corrections=None, revision=0,
             only_units=None, excluded=None) -> dict:
    if excluded:
        canon = {t: (df[~df._row.isin({r for tt, r in excluded if tt == t})] if "_row" in df else df)
                 for t, df in canon.items()}
    b = Builder(spec, canon, fmap, vmap, settings, corrections, revision, only_units)
    {"WCSTAT": b.build_wcstat, "WCPOLS": b.build_wcpols, "WCIND": b.build_wcind, "WCMED": b.build_wcmed}[spec](sorted(months))
    lines, recs = [], []
    for i, r in enumerate(b.records, start=1):
        line = b.render(r)
        lines.append(line)
        recs.append({"seq": i, "record_key": r["record_key"],
                     "record_name": catalog.RECORD_NAMES[spec].get(r["record_key"], r["record_key"]),
                     "policy": r["ref"].get("policy", ""), "claim": r["ref"].get("claim", ""),
                     "unit": r["ref"].get("unit", ""), "ref_table": r["ref"].get("table", ""),
                     "ref_row": r["ref"].get("row", -1), "line": line})
    df = pd.DataFrame(recs, columns=["seq", "record_key", "record_name", "policy", "claim", "unit", "ref_table",
                                     "ref_row", "line"])
    return {"id": uuid.uuid4().hex[:8].upper(), "spec": spec, "months": sorted(months), "revision": revision,
            "created": dt.datetime.now().strftime("%Y-%m-%d %H:%M"), "records": df,
            "fixed_width": "\n".join(lines) + "\n", "flat_csv": flat_csv(spec, df)}


def flat_csv(spec: str, recs: pd.DataFrame) -> str:
    """One row per record, every spec field as its own column (record type prefix keeps names unique)."""
    rows, cache = [], {}
    for r in recs.itertuples():
        if r.record_key not in cache:
            cache[r.record_key] = [f for f in catalog.record_fields(spec, r.record_key).to_dict("records")
                                   if not f["name"].startswith(("RESERVED", "FILLER"))]
        row = {"record_seq": r.seq, "record_type": r.record_name}
        for f in cache[r.record_key]:
            row[f"{r.record_name}.{f['name']}"] = r.line[f["start"] - 1:f["end"]].strip()
        rows.append(row)
    buf = io.StringIO()
    pd.DataFrame(rows).to_csv(buf, index=False)
    return buf.getvalue()


def accounting_months(start="2025-01", end="2026-09") -> list[str]:
    out, y, m = [], *map(int, start.split("-"))
    ey, em = map(int, end.split("-"))
    while (y, m) <= (ey, em):
        out.append(f"{y}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out
