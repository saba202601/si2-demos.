"""SI² bureau-reporting canonical model and automatic mapping.

Three mapping layers, each with a confidence score and an SME status:
1. Source column  -> canonical attribute   (fuzzy match on names, abbreviations and synonyms)
2. Canonical attr -> bureau spec field     (the canonical model is built from the spec field names)
3. Source value   -> bureau pick-list code (exact code, domain synonyms, then description similarity)
"""
from __future__ import annotations

import datetime as dt
import difflib
import re

import numpy as np
import pandas as pd

from . import catalog

# ----------------------------------------------------------------------------------------------- schema
# table: {column: (type, description, aliases incl. the bureau field names the column feeds)}
SCHEMA: dict[str, dict[str, tuple[str, str, list[str]]]] = {
    "policy": {
        "policy_number": ("text", "Policy number", ["POLICY NUMBER IDENTIFIER", "policy no"]),
        "insured_name": ("text", "Named insured", ["NAME OF INSURED"]),
        "fein": ("text", "Federal employer identification number", ["FEDERAL EMPLOYER IDENTIFICATION NUMBER (FEIN)", "federal tax id"]),
        "policy_effective_date": ("date", "Policy effective date", ["POLICY EFFECTIVE DATE", "effective date"]),
        "policy_expiration_date": ("date", "Policy expiration date", ["POLICY EXPIRATION DATE", "expiration date"]),
        "cancellation_date": ("date", "Cancellation date", ["cancel date"]),
        "transaction_issue_date": ("date", "Date the transaction was processed", ["TRANSACTION ISSUE DATE", "issue date"]),
        "transaction_type": ("code", "New or renewal", ["TRANSACTION CODE", "transaction type"]),
        "type_of_plan": ("code", "Voluntary or assigned risk", ["TYPE OF PLAN ID CODE", "plan code"]),
        "legal_nature_of_insured": ("code", "Legal entity type", ["LEGAL NATURE OF INSURED CODE", "LEGAL NATURE OF ENTITY CODE", "entity type"]),
        "producer_name": ("text", "Producer or agency", ["NAME OF PRODUCER", "agency name"]),
        "address_street": ("text", "Mailing street", ["ADDRESS - STREET", "mail address line 1"]),
        "address_city": ("text", "Mailing city", ["ADDRESS - CITY", "mail city"]),
        "address_state": ("text", "Mailing state", ["ADDRESS - STATE", "mail state"]),
        "address_zip": ("text", "Mailing ZIP", ["ADDRESS - ZIP CODE", "mail zip"]),
        "number_of_employees": ("int", "Employee count", ["NUMBER OF EMPLOYEES", "employee count"]),
        "deductible_type": ("code", "Deductible type", ["LOSSES SUBJECT TO DEDUCTIBLE CODE", "deductible type"]),
        "deductible_amount": ("money", "Deductible per claim", ["DEDUCTIBLE AMOUNT PER CLAIM/ACCIDENT", "deductible amount"]),
        "el_limit_each_accident": ("money", "EL bodily injury by accident, each accident", ["EMPLOYER LIABILITY LIMIT AMOUNT - BODILY INJURY BY ACCIDENT EACH ACCIDENT", "el each accident"]),
        "el_limit_disease_policy": ("money", "EL bodily injury by disease, policy limit", ["EMPLOYER LIABILITY LIMIT AMOUNT - BODILY INJURY BY DISEASE POLICY LIMIT", "el policy"]),
        "el_limit_disease_each_employee": ("money", "EL bodily injury by disease, each employee", ["EMPLOYER LIABILITY LIMIT AMOUNT - BODILY INJURY BY DISEASE EACH EMPLOYEE", "el each employee"]),
        "billing_frequency": ("code", "Billing plan", ["BILLING FREQUENCY CODE", "bill plan"]),
        "audit_frequency": ("code", "Audit frequency", ["AUDIT FREQUENCY CODE"]),
        "retrospective_rated": ("code", "Retro rated Y/N", ["RETROSPECTIVE RATED POLICY INDICATOR", "RETROSPECTIVE RATING CODE", "retro indicator"]),
        "interstate_risk_id": ("text", "Interstate risk ID", ["INTERSTATE RISK ID NUMBER", "RISK ID NUMBER"]),
    },
    "policy_state": {
        "policy_number": ("text", "Policy number", ["POLICY NUMBER IDENTIFIER", "policy no"]),
        "state": ("state", "Exposure state (USPS)", ["EXPOSURE STATE CODE", "STATE CODE", "risk state"]),
        "experience_modification_factor": ("factor", "Experience modification factor", ["EXPERIENCE MODIFICATION FACTOR", "EXPERIENCE MODIFICATION FACTOR/MERIT RATING FACTOR", "xmod factor"]),
        "estimated_state_standard_premium": ("money", "State standard premium", ["ESTIMATED STATE STANDARD PREMIUM TOTAL", "standard premium"]),
        "expense_constant_amount": ("money", "Expense constant", ["EXPENSE CONSTANT AMOUNT", "expense constant"]),
        "premium_discount_amount": ("money", "Premium discount", ["PREMIUM DISCOUNT AMOUNT", "premium discount"]),
    },
    "exposure": {
        "policy_number": ("text", "Policy number", ["POLICY NUMBER IDENTIFIER", "policy no"]),
        "state": ("state", "Exposure state (USPS)", ["EXPOSURE STATE CODE", "STATE CODE", "risk state"]),
        "classification_code": ("text", "Class code", ["CLASSIFICATION CODE", "class code"]),
        "classification_wording": ("text", "Class description", ["CLASSIFICATION WORDING", "class description"]),
        "manual_charged_rate": ("rate", "Rate per $100", ["MANUAL/CHARGED RATE", "rate"]),
        "estimated_exposure_amount": ("money", "Estimated payroll", ["ESTIMATED EXPOSURE AMOUNT", "estimated payroll"]),
        "exposure_amount": ("money", "Audited payroll", ["EXPOSURE AMOUNT", "audited payroll"]),
        "premium_amount": ("money", "Class premium", ["PREMIUM AMOUNT", "manual premium"]),
    },
    "claim": {
        "claim_number": ("text", "Claim number", ["CLAIM NUMBER", "CLAIM NUMBER IDENTIFIER", "claim no"]),
        "policy_number": ("text", "Policy number", ["POLICY NUMBER IDENTIFIER", "policy no"]),
        "jurisdiction_state": ("state", "Jurisdiction state (USPS)", ["JURISDICTION STATE CODE", "jurisdiction state"]),
        "classification_code": ("text", "Class code of the injured worker", ["CLASSIFICATION CODE", "class code"]),
        "accident_date": ("date", "Date of accident", ["ACCIDENT DATE", "date of loss", "loss date"]),
        "reported_to_insurer_date": ("date", "Date reported", ["REPORTED TO INSURER DATE", "report date"]),
        "closing_date": ("date", "Date closed", ["CLOSING DATE", "close date"]),
        "claim_status": ("code", "Claim status", ["CLAIM/STATUS CODE", "claim status"]),
        "injury_type": ("code", "Injury type / severity", ["INJURY CODE (INJURY TYPE)", "injury severity"]),
        "type_of_loss": ("code", "Type of loss", ["TYPE OF LOSS CODE", "loss type"]),
        "type_of_recovery": ("code", "Type of recovery", ["TYPE OF RECOVERY CODE", "recovery type"]),
        "type_of_claim": ("code", "Type of claim", ["TYPE OF CLAIM CODE", "claim type"]),
        "type_of_settlement": ("code", "Type of settlement", ["TYPE OF SETTLEMENT CODE", "settlement type"]),
        "part_of_body_code": ("text", "WCIO part of body", ["PART OF BODY CODE", "body part"]),
        "nature_of_injury_code": ("text", "WCIO nature of injury", ["NATURE OF INJURY CODE", "nature injury"]),
        "cause_of_injury_code": ("text", "WCIO cause of injury", ["CAUSE OF INJURY CODE", "cause injury"]),
        "weekly_wage_amount": ("money", "Average weekly wage", ["WEEKLY WAGE AMOUNT", "PRE-INJURY/AVERAGE WEEKLY WAGE", "weekly wage"]),
        "claimant_gender": ("code", "Claimant gender", ["CLAIMANT GENDER CODE", "claimant sex"]),
        "birth_date": ("date", "Claimant birth date", ["BIRTH DATE", "claimant date of birth"]),
        "hire_date": ("date", "Hire date", ["HIRE DATE"]),
        "occupation_description": ("text", "Occupation", ["OCCUPATION DESCRIPTION", "occupation"]),
        "lump_sum_indicator": ("code", "Lump sum Y/N", ["LUMP SUM INDICATOR", "lump sum ind"]),
        "attorney_indicator": ("code", "Attorney involved Y/N", ["ATTORNEY OR AUTHORIZED REPRESENTATIVE INDICATOR", "attorney ind"]),
        "paid_indemnity_amount": ("money", "Indemnity paid to date", ["PAID INDEMNITY AMOUNT", "INDEMNITY PAID-TO-DATE", "indemnity paid"]),
        "indemnity_reserve": ("money", "Indemnity outstanding reserve", ["indemnity reserve"]),
        "paid_medical_amount": ("money", "Medical paid to date", ["PAID MEDICAL AMOUNT", "MEDICAL PAID-TO-DATE", "medical paid"]),
        "medical_reserve": ("money", "Medical outstanding reserve", ["medical reserve"]),
        "paid_alae": ("money", "Paid allocated loss adjustment expense", ["PAID ALLOCATED LOSS ADJUSTMENT EXPENSE (ALAE)", "expense paid"]),
        "alae_reserve": ("money", "ALAE outstanding reserve", ["expense reserve"]),
    },
    "indemnity_payment": {
        "claim_number": ("text", "Claim number", ["CLAIM NUMBER IDENTIFIER", "claim no"]),
        "transaction_identifier": ("text", "Payment identifier", ["TRANSACTION IDENTIFIER", "payment id"]),
        "transaction_date": ("date", "Check date", ["TRANSACTION DATE", "check date"]),
        "transaction_from_date": ("date", "Period from", ["TRANSACTION FROM DATE", "service from"]),
        "transaction_to_date": ("date", "Period to", ["TRANSACTION TO DATE", "service through"]),
        "transaction_amount": ("money", "Payment amount", ["TRANSACTION AMOUNT", "payment amount"]),
        "benefit_type": ("code", "Benefit type", ["BENEFIT TYPE CODE", "benefit code"]),
        "weekly_benefit_amount": ("money", "Weekly benefit", ["WEEKLY BENEFIT AMOUNT", "week benefit amount"]),
    },
    "medical_bill_line": {
        "bill_identification_number": ("text", "Bill ID", ["BILL IDENTIFICATION NUMBER", "bill id"]),
        "line_identification_number": ("text", "Line number", ["LINE IDENTIFICATION NUMBER", "line no"]),
        "claim_number": ("text", "Claim number", ["CLAIM NUMBER IDENTIFIER", "claim no"]),
        "service_date": ("date", "Date of service", ["SERVICE DATE", "date of service"]),
        "transaction_date": ("date", "Paid date", ["TRANSACTION DATE", "paid date"]),
        "paid_procedure_code": ("text", "Procedure code", ["PAID PROCEDURE CODE", "cpt code"]),
        "paid_procedure_code_modifier": ("text", "Modifier", ["PAID PROCEDURE CODE MODIFIER", "cpt modifier"]),
        "amount_charged_by_provider": ("money", "Billed amount", ["AMOUNT CHARGED BY PROVIDER", "billed amount"]),
        "paid_amount": ("money", "Paid amount", ["PAID AMOUNT", "allowed paid"]),
        "primary_icd_diagnostic_code": ("text", "Primary ICD", ["PRIMARY ICD DIAGNOSTIC CODE", "diagnosis 1"]),
        "secondary_icd_diagnostic_code": ("text", "Secondary ICD", ["SECONDARY ICD DIAGNOSTIC CODE", "diagnosis 2"]),
        "provider_taxonomy_code": ("text", "Provider taxonomy", ["PROVIDER TAXONOMY CODE", "provider taxonomy"]),
        "provider_identification_number": ("text", "Provider NPI", ["PROVIDER IDENTIFICATION NUMBER", "provider npi"]),
        "provider_postal_code": ("text", "Provider ZIP", ["PROVIDER POSTAL (ZIP) CODE", "provider zip"]),
        "network_service_code": ("code", "Network", ["NETWORK SERVICE CODE", "network indicator"]),
        "place_of_service_code": ("code", "Place of service", ["PLACE OF SERVICE CODE", "pos code"]),
        "units": ("int", "Units", ["QUANTITY/NUMBER OF UNITS PER PROCEDURE CODE", "units"]),
    },
}

SOURCE_FOR = {"policy": ["PC_POLICY"], "policy_state": ["PC_POLICY_STATE"], "exposure": ["PC_CLASS_EXPOSURE"],
              "claim": ["CC_CLAIM"], "indemnity_payment": ["CC_INDEMNITY_PAYMENT"],
              "medical_bill_line": ["BR_MEDICAL_BILL_LINE"]}

# Columns SI² derives (not mapped from source) — shown in the model so the SME sees every input.
DERIVED = {
    "policy": {"carrier_code": "Carrier code from SI² settings", "address_of_insured": "Street, city, state ZIP",
               "multistate_policy_indicator": "Y when more than one state", "cancelled_mid_term_policy_indicator": "Y when cancelled before expiration",
               "policy_expiration_or_cancellation_date": "Cancellation date if cancelled, else expiration",
               "policy_estimated_standard_premium_total": "Sum of state standard premium",
               "type_of_coverage_id_code": "Standard policy (01) unless configured"},
    "exposure": {"estimated_premium_amount": "Estimated payroll × rate / 100",
                 "exposure_act_coverage": "STATE ACT unless USL&HW / federal act"},
    "claim": {"incurred_indemnity_amount": "Paid + indemnity reserve", "incurred_medical_amount": "Paid + medical reserve",
              "incurred_alae": "Paid + ALAE reserve", "birth_year": "Year of birth", "loss_coverage_act": "STATE ACT",
              "claim_count": "1 per loss record", "fraudulent_claim": "NONE", "vocational_rehabilitation_indicator": "N"},
}

# Source-side abbreviations (what a legacy system writes) -> words.
SRC_ABBR = {
    "POL": "POLICY", "NO": "NUMBER", "NBR": "NUMBER", "INSD": "INSURED", "NM": "NAME", "FED": "FEDERAL",
    "DT": "DATE", "EFF": "EFFECTIVE", "EXP": "EXPIRATION", "CANC": "CANCEL", "TRANS": "TRANSACTION",
    "TYP": "TYPE", "CD": "CODE", "ADDR1": "ADDRESS STREET", "ST": "STATE", "CNT": "COUNT", "EMP": "EMPLOYEE",
    "DED": "DEDUCTIBLE", "AMT": "AMOUNT", "EL": "EL", "ACC": "ACCIDENT", "AUD": "AUDITED", "CLS": "CLASS",
    "DESC": "DESCRIPTION", "PREM": "PREMIUM", "XMOD": "EXPERIENCE MODIFICATION", "FCTR": "FACTOR",
    "STD": "STANDARD", "CONST": "CONSTANT", "DISC": "DISCOUNT", "JURIS": "JURISDICTION", "RPT": "REPORT",
    "CLM": "CLAIM", "STAT": "STATUS", "INJ": "INJURY", "SVRTY": "SEVERITY", "RECOV": "RECOVERY",
    "SETTLE": "SETTLEMENT", "WKLY": "WEEKLY", "WG": "WAGE", "CLMT": "CLAIMANT", "SEX": "GENDER", "DOB": "BIRTH DATE",
    "ATTY": "ATTORNEY", "IND": "INDEMNITY", "RSV": "RESERVE", "MED": "MEDICAL", "PMT": "PAYMENT", "ID": "ID",
    "SVC": "SERVICE", "THRU": "THROUGH", "BEN": "BENEFIT", "WK": "WEEK", "DOS": "DATE OF SERVICE",
    "CPT": "CPT", "MOD": "MODIFIER", "DX1": "DIAGNOSIS 1", "DX2": "DIAGNOSIS 2", "PROV": "PROVIDER",
    "POS": "POS", "ISSUE": "ISSUE", "AGENCY": "AGENCY", "MAIL": "MAIL", "PLAN": "PLAN", "ENTITY": "ENTITY",
    "RETRO": "RETRO", "FREQ": "FREQUENCY", "CHECK": "CHECK", "LN": "LINE",
}
STOP = {"OF", "THE", "AND", "OR", "TO", "BY", "CODE", "ID", "IDENTIFIER", "NUMBER", "AMOUNT", "DATE", "INDICATOR"}


def _tokens(text: str, source: bool = False) -> list[str]:
    toks = re.sub(r"[^A-Z0-9]+", " ", text.upper()).split()
    if source:
        toks = " ".join(SRC_ABBR.get(t, t) for t in toks).split()
    return toks


def similarity(a: str, b: str, source_a: bool = False) -> float:
    ta, tb = _tokens(a, source_a), _tokens(b)
    if not ta or not tb:
        return 0.0
    sa, sb = set(ta), set(tb)
    inter = sa & sb
    core = len([t for t in inter if t not in STOP])
    dice = 2 * len(inter) / (len(sa) + len(sb))
    seq = difflib.SequenceMatcher(None, " ".join(ta), " ".join(tb)).ratio()
    score = 0.6 * dice + 0.4 * seq
    if core == 0:
        score *= 0.5
    return round(min(1.0, score), 3)


def band(score: float) -> str:
    return "High" if score >= 0.8 else "Medium" if score >= 0.55 else "Low"


# --------------------------------------------------------------------------- 1. source -> canonical
def auto_map_source(src: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for table, cols in SCHEMA.items():
        candidates = [(t, c) for t in SOURCE_FOR[table] if t in src for c in src[t].columns]
        scored = []
        for col, (typ, desc, aliases) in cols.items():
            names = [col.replace("_", " "), desc] + aliases
            for t, c in candidates:
                s = max(similarity(c, n, source_a=True) for n in names)
                scored.append((s, col, t, c))
        scored.sort(reverse=True)
        used_src, done = set(), {}
        for s, col, t, c in scored:
            if col in done or (t, c) in used_src:
                continue
            if s < 0.45:
                continue
            done[col] = (t, c, s)
            used_src.add((t, c))
        for col, (typ, desc, aliases) in cols.items():
            t, c, s = done.get(col, ("", "", 0.0))
            rows.append({"canonical_table": table, "canonical_column": col, "type": typ, "description": desc,
                         "source_table": t, "source_column": c, "confidence": s, "band": band(s) if c else "Unmapped",
                         "status": "Auto-approved" if s >= 0.8 else ("Needs SME review" if c else "Unmapped")})
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- build canonical tables
def _to_date(v):
    if v is None or (isinstance(v, float) and np.isnan(v)) or str(v).strip() == "":
        return None
    if isinstance(v, (dt.date, dt.datetime)):
        return v if isinstance(v, dt.date) else v.date()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%Y%m%d", "%m/%d/%y"):
        try:
            return dt.datetime.strptime(str(v).strip(), fmt).date()
        except ValueError:
            continue
    return None


def _to_num(v):
    try:
        f = float(v)
        return 0.0 if np.isnan(f) else f
    except (TypeError, ValueError):
        return 0.0


def build_canonical(src: dict[str, pd.DataFrame], smap: pd.DataFrame, carrier_code: str,
                    overrides: dict | None = None) -> dict[str, pd.DataFrame]:
    out = {}
    for table, cols in SCHEMA.items():
        m = smap[smap.canonical_table == table]
        base_t = SOURCE_FOR[table][0]
        n = len(src[base_t])
        data = {}
        for _, r in m.iterrows():
            col, typ = r.canonical_column, r.type
            if r.source_column and r.source_table in src and r.source_column in src[r.source_table]:
                s = src[r.source_table][r.source_column]
            else:
                s = pd.Series([None] * n)
            if typ == "date":
                data[col] = [_to_date(v) for v in s]
            elif typ in ("money", "factor", "rate"):
                data[col] = [_to_num(v) for v in s]
            elif typ == "int":
                data[col] = [int(_to_num(v)) for v in s]
            else:
                data[col] = ["" if v is None or (isinstance(v, float) and np.isnan(v)) else str(v).strip() for v in s]
        out[table] = pd.DataFrame(data)
        out[table]["_row"] = range(len(out[table]))

    p, ps, ex, c = out["policy"], out["policy_state"], out["exposure"], out["claim"]
    p["carrier_code"] = carrier_code
    p["address_of_insured"] = p.address_street + " " + p.address_city + " " + p.address_state + " " + p.address_zip
    st_count = ps.groupby("policy_number").state.nunique()
    p["multistate_policy_indicator"] = p.policy_number.map(st_count).fillna(1).gt(1).map({True: "Y", False: "N"})
    p["cancelled_mid_term_policy_indicator"] = [
        "Y" if (cd and xd and cd < xd) else "N" for cd, xd in zip(p.cancellation_date, p.policy_expiration_date)]
    p["policy_expiration_or_cancellation_date"] = [cd or xd for cd, xd in zip(p.cancellation_date, p.policy_expiration_date)]
    p["policy_estimated_standard_premium_total"] = p.policy_number.map(
        ps.groupby("policy_number").estimated_state_standard_premium.sum()).fillna(0)
    p["type_of_coverage_id_code"] = "STANDARD"
    ex["estimated_premium_amount"] = (ex.estimated_exposure_amount * ex.manual_charged_rate / 100).round(0)
    ex["exposure_act_coverage"] = "STATE ACT"
    c["incurred_indemnity_amount"] = c.paid_indemnity_amount + c.indemnity_reserve
    c["incurred_medical_amount"] = c.paid_medical_amount + c.medical_reserve
    c["incurred_alae"] = c.paid_alae + c.alae_reserve
    c["birth_year"] = [d.year if d else 0 for d in c.birth_date]
    c["loss_coverage_act"] = "STATE ACT"
    c["claim_count"] = 1
    c["fraudulent_claim"] = "NONE"
    c["vocational_rehabilitation_indicator"] = "N"

    for (table, row, col), val in (overrides or {}).items():   # SME-approved record-level corrections
        if table in out and row < len(out[table]) and col in out[table]:
            typ = SCHEMA.get(table, {}).get(col, ("text",))[0]
            out[table].at[row, col] = _to_date(val) if typ == "date" else (_to_num(val) if typ in ("money", "factor", "rate") else val)
            if table == "claim" and col in ("indemnity_reserve", "paid_indemnity_amount"):
                out[table].at[row, "incurred_indemnity_amount"] = out[table].at[row, "paid_indemnity_amount"] + out[table].at[row, "indemnity_reserve"]
    return out


def canonical_columns() -> pd.DataFrame:
    rows = []
    for t, cols in SCHEMA.items():
        for c, (typ, desc, aliases) in cols.items():
            rows.append({"table": t, "column": c, "type": typ, "description": desc, "origin": "Mapped from source"})
        for c, desc in DERIVED.get(t, {}).items():
            rows.append({"table": t, "column": c, "type": "derived", "description": desc, "origin": "Derived by SI²"})
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- 3. value -> pick list
VALUE_SYNONYMS = {
    "OPEN": "Open Claim", "CLOSED": "Closed Claim", "REOPENED": "Reopened Claim",
    "MED ONLY": "Medical Claims Only", "TTD": "Temporary Total or Temporary Partial Disability",
    "PPD-MINOR": "Minor Permanent Partial Disability", "PPD-MAJOR": "Major Permanent Partial Disability",
    "PTD": "Permanent Total Disability", "FATAL": "Death", "TRAUMA": "Trauma", "OCC DISEASE": "Occupational Disease",
    "CUMULATIVE": "Cumulative Injury Other Than Disease", "SUBRO": "Subrogation Only (Third Party)",
    "WC ONLY": "Workers Compensation Only", "COMPROMISE": "Compromise Settlement", "M": "Male", "F": "Female",
    "NEW": "New Policy", "RENEWAL": "Renewal Policy", "VOLUNTARY": "Voluntary Policy", "AR": "Normal Assigned Risk Policy",
    "CORP": "Corporation", "LLC": "Limited Liability Company", "PARTNERSHIP": "Partnership", "INDIVIDUAL": "Individual",
    "S-CORP": "Corporation", "PPD-S": "Scheduled Permanent Partial Disability Benefits",
    "PPD-U": "Unscheduled Permanent Partial Disability Benefits", "DEATH": "Death Benefits",
    "PPO": "PPO Agreement", "HMO": "HMO", "STATE ACT": "State Act or Federal Act Excluding USL&HW",
    "STANDARD": "Standard Workers Compensation Policy", "MED": "Medical Losses Only",
    "ANNUAL": "Annual", "QUARTERLY": "Quarterly", "MONTHLY": "Monthly", "SEMIANNUAL": "Semiannual",
}
CONTEXT_SYNONYMS = {  # same source value means different things in different bureau fields
    ("TYPE OF RECOVERY CODE", "NONE"): "No Recovery",
    ("TYPE OF SETTLEMENT CODE", "NONE"): "Claim Not Subject to Settlement",
    ("NETWORK SERVICE CODE", "NONE"): "No Agreement",
    ("LOSSES SUBJECT TO DEDUCTIBLE CODE", "NONE"): "No Deductible",
    ("FRAUDULENT CLAIM CODE", "NONE"): "Not Fraudulent",
    ("BENEFIT TYPE CODE", "TTD"): "Temporary Total Disability Benefits",
    ("BENEFIT TYPE CODE", "PTD"): "Permanent Total Disability Benefits",
    ("RETROSPECTIVE RATING CODE", "N"): "Not Retrospective Rated",
    ("RETROSPECTIVE RATING CODE", "Y"): "Retrospective Rated",
    ("LEGAL NATURE OF INSURED CODE", "LLC"): "Limited Liability Company (LLC)",
    ("LEGAL NATURE OF ENTITY CODE", "LLC"): "Limited Liability Company (LLC)",
}


def map_value(field_name: str, value: str, codes: list[dict]) -> tuple[str, float, str]:
    """Return (bureau code, confidence, how) for one source value."""
    v = str(value).strip().upper()
    valid = {c["code"]: c for c in codes}
    if v == "":
        return "", 1.0, "blank"
    if v in valid:
        return v, 1.0, "exact code"
    phrase = CONTEXT_SYNONYMS.get((field_name, v)) or VALUE_SYNONYMS.get(v)
    best, best_s = "", 0.0
    for c in codes:
        if c["reserved"]:
            continue
        s = difflib.SequenceMatcher(None, (phrase or v).lower(), c["description"].lower()[:len((phrase or v)) + 25]).ratio()
        if phrase and c["description"].lower().startswith(phrase.lower()):
            s = 1.0
        if s > best_s:
            best, best_s = c["code"], s
    how = "synonym" if phrase else "description similarity"
    conf = round(best_s if phrase else best_s * 0.8, 2)
    return (best, conf, how) if conf >= 0.5 else ("", conf, "no match")
