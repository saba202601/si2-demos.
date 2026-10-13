"""Build 03_seed.sql for the SI² Canonical Master database from every SI² app plus P&C domain lists.

    python sql/si2_canonical/build_seed.py          (run from the repository root)

Sources: the company-model harvest (core canonical, ISO bureau, NCCI bureau, migration cloud model, rule
engine, rating engine), the ISO element and pick-list catalog with source aliases, the NCCI WCIO code
lists, legacy and cloud code tables, the rule engine, the ISO bureau rules, the NCCI edits and the
role-based decision boundaries. The script is idempotent SQL: re-running the seed only adds what is missing.
"""
from __future__ import annotations

import collections
import csv
import difflib
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))

import logging  # noqa: E402
logging.disable(logging.WARNING)

from bureau import canonical as NC  # noqa: E402
from bureau import edits as NE  # noqa: E402
from iso_bureau import catalog as C  # noqa: E402
from si2_common import registry as R  # noqa: E402

sys.path.insert(0, str(HERE))
import domain_extra as X  # noqa: E402

BY = "SI2 seed"
BASE = "2020-01-01"


# ------------------------------------------------------------------------------------------ helpers
def q(v) -> str:
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, (int, float)):
        return repr(v)
    return "N'" + str(v).replace("'", "''") + "'"


def snake(s: str) -> str:
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", str(s))
    s = re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_").upper()
    return re.sub(r"_+", "_", s)


def norm(s: str) -> str:
    return re.sub(r"[ _\-./]", "", str(s)).upper()


def title(code: str) -> str:
    small = {"OF", "AND", "OR", "TO", "BY", "THE", "A", "IN", "ON"}
    keep = {"ID", "VIN", "FEIN", "ZIP", "ALAE", "ICD", "LOB", "UW", "SIU", "TIV", "XOL", "NCCI", "ISO", "EL", "PIP", "UM", "BI", "PD", "DCO", "WC", "PEO", "MCO"}
    out = []
    for i, w in enumerate(code.split("_")):
        out.append(w if w in keep else (w.lower() if (w in small and i) else w.capitalize()))
    return " ".join(out)


def values_insert(lines: list, head: str, cols: list[str], rows: list[tuple], tail: str, chunk: int = 400) -> None:
    """INSERT ... SELECT from a VALUES list, chunked (SQL Server allows 1000 rows per VALUES)."""
    for i in range(0, len(rows), chunk):
        part = rows[i:i + chunk]
        # a typed NULL in the first row keeps an all-NULL column from being typed as int
        first = "    (" + ", ".join("CAST(NULL AS nvarchar(4000))" if v is None else q(v) for v in part[0]) + ")"
        body = ",\n".join([first] + ["    (" + ", ".join(q(v) for v in r) + ")" for r in part[1:]])
        lines.append(f"{head}\nFROM (VALUES\n{body}\n) v ({', '.join(cols)})\n{tail};\n")


# ------------------------------------------------------------------------------------ subject areas
SUBJECTS = [
    ("POLICY", "Policy", "The contract: policy term, status, transactions, forms.", 10),
    ("PARTY", "Party / Insured", "People and organizations: insureds, drivers, claimants, employers.", 20),
    ("LOCATION", "Location / Address", "Addresses, risk locations, territories, catastrophe zones.", 30),
    ("VEHICLE", "Vehicle", "Vehicles and their use.", 40),
    ("DRIVER", "Driver", "Drivers, licensing, violations and loss history.", 50),
    ("PROPERTY", "Property / Building", "Buildings and property characteristics.", 60),
    ("COVERAGE", "Coverage", "Coverages, limits, deductibles.", 70),
    ("RATING", "Rating", "Rating variables, classes, factors and rates.", 80),
    ("PREMIUM", "Premium", "Premium transactions and amounts.", 90),
    ("UNDERWRITING", "Underwriting", "Submissions, risk scores, decisions and authority.", 100),
    ("CLAIM", "Claim", "Claims, claimants and claim characteristics.", 110),
    ("CLAIM_FINANCIAL", "Claim Financials", "Payments, reserves, recoveries and expenses.", 120),
    ("WORKERS_COMP", "Workers Compensation", "WC policy, injury, benefit and medical data (WCIO / NCCI).", 130),
    ("MEDICAL", "Medical Billing", "Medical bills, providers and procedures.", 140),
    ("FRAUD", "Fraud / SIU", "Fraud scores, referrals and investigations.", 150),
    ("PRODUCER", "Producer / Distribution", "Agents, brokers, channels and commissions.", 160),
    ("BILLING", "Billing", "Invoices, payment plans and payments.", 170),
    ("REINSURANCE", "Reinsurance", "Treaties, layers, cessions and reinsurers.", 180),
    ("CAPITAL", "Risk & Capital", "Capital, solvency and risk appetite measures.", 190),
    ("BUREAU", "Bureau Reporting", "Bureau-only technical fields (record control, filler, company use).", 200),
]


def subject_of(code: str, app_entities: set) -> str:
    c = code
    rules = [
        ("REINSURANCE", ["TREATY", "REINSUR", "CEDED", "RETENTION", "LAYER", "AM_BEST"]),
        ("CAPITAL", ["SOLVENCY", "CAPITAL", "APPETITE"]),
        ("BILLING", ["INVOICE", "BILL", "DUE_DATE", "BALANCE", "PAYMENT_METHOD", "PAYMENT_PLAN", "INSTALLMENT"]),
        ("FRAUD", ["FRAUD", "SIU"]),
        ("MEDICAL", ["PROVIDER", "PROCEDURE", "ICD", "PLACE_SERVICE", "SERVICE_DATE", "AMOUNT_CHARGED", "BILL_IDENTIFICATION", "LINE_IDENTIFICATION", "NETWORK_SERVICE"]),
        ("WORKERS_COMP", ["INJURY", "BENEFIT", "WEEKLY", "HIRE_DATE", "EL_LIMIT", "EMPLOYEE", "EXPERIENCE_MOD", "INTERSTATE", "PART_BODY",
                          "OCCUPATION", "LUMP_SUM", "RETROSPECTIVE", "LEGAL_NATURE", "TYPE_PLAN", "ESTIMATED_STATE", "EXPENSE_CONSTANT", "AUDIT_FREQ",
                          "BILLING_FREQ", "MANUAL_CHARGED", "CLASSIFICATION_WORDING", "JURISDICTION"]),
        ("CLAIM_FINANCIAL", ["PAID", "RESERVE", "ALAE", "RECOVERY", "SETTLEMENT", "INCURRED", "PAYMENT", "REPAIR_ESTIMATE", "TRANSACTION_AMOUNT"]),
        ("CLAIM", ["CLAIM", "LOSS", "CAT_CODE", "ATTORNEY", "REPORT_DATE", "CLOSING", "CAUSE", "CATASTROPHE", "LITIGATION", "ADJUSTER",
                   "DAYS_TO_REPORT"]),
        ("UNDERWRITING", ["SUBMISSION", "UW_", "RISK_SCORE", "TOTAL_INSURED", "DECISION", "QUOTE", "CYBER", "RECORDS_HELD", "NAICS", "SIC_CODE",
                          "LEGAL_ENTITY", "ANNUAL_REVENUE", "YEARS_IN_BUSINESS", "BUSINESS_DESCRIPTION", "PRIOR_CARRIER"]),
        ("DRIVER", ["DRIVER", "VIOLATION", "PRIOR_CLAIMS", "YEARS_LICENSED", "LICENSE", "GOOD_STUDENT"]),
        ("VEHICLE", ["VEHICLE", "VIN", "MAKE", "SYMBOL", "ANNUAL_MILES", "TELEMATICS", "RIDESHARE", "MODEL_YEAR", "BODY_STYLE", "FUEL",
                     "ANTI_THEFT", "GARAGING", "ODOMETER"]),
        ("PROPERTY", ["CONSTRUCTION", "PROTECTION_CLASS", "ROOF", "OCCUPANCY", "YEAR_BUILT", "SQUARE", "COINSURANCE", "WIND_HAIL", "COAST",
                      "DWELLING", "STORIES", "UNITS", "FOUNDATION", "ALARM", "SPRINKLER", "WIND_MITIGATION", "FLOOD", "FIRE_STATION",
                      "HYDRANT", "WILDFIRE", "REPLACEMENT_COST"]),
        ("COVERAGE", ["COVERAGE", "LIMIT", "DEDUCTIBLE", "INSURING_AGREEMENT", "SUBLINE", "PROJECT_CATEGORY"]),
        ("RATING", ["RATE", "TERRITORY", "CLASS", "EXPOSURE", "UNITS", "FACTOR", "SYMBOL"]),
        ("PREMIUM", ["PREMIUM", "ACCOUNTING", "TRANSACTION", "POLICY_FEE"]),
        ("PRODUCER", ["PRODUCER", "AGENT", "CHANNEL", "COMMISSION"]),
        ("LOCATION", ["ZIP", "ADDRESS", "LOCATION", "STATE", "CITY", "COUNTY"]),
        ("PARTY", ["PARTY", "INSURED", "NAME", "EMAIL", "PHONE", "FEIN", "BIRTH", "MARITAL", "GENDER", "CUSTOMER", "LANGUAGE", "CONTACT",
                   "LAPSE_RISK"]),
        ("BUREAU", ["FILLER", "COMPANY_USE", "MAJOR_LINE", "FILED_FORM"]),
        ("POLICY", ["POLICY", "CANCELLATION", "LINE_OF_BUSINESS", "FORM", "STATUS", "SEQUENCE", "RISK_ITEM", "RISK_TYPE"]),
    ]
    for subj, keys in rules:
        if any(k in c for k in keys):
            return subj
    return "POLICY"


# ---------------------------------------------------------------------------------------- pick lists
# (code, name, description, library, [(code, name, description)])
DOMAIN_LISTS = [
    ("POLICY_STATUS", "Policy Status", "Life-cycle status of a policy term.", "SI2", [
        ("QUOTED", "Quoted", None), ("BOUND", "Bound, not yet issued", None), ("INFORCE", "In force", None),
        ("PENDING_CANCEL", "Pending cancellation", "Notice of cancellation issued."), ("CANCELLED", "Cancelled", None),
        ("EXPIRED", "Expired", None), ("NONRENEWED", "Non-renewed", None), ("LAPSED", "Lapsed for non-payment", None),
        ("REINSTATED", "Reinstated", None)]),
    ("PAYMENT_PLAN", "Payment Plan", "How the premium is billed.", "SI2", [
        ("PIF", "Paid in full", None), ("2PAY", "Two payments (semi-annual)", None), ("4PAY", "Quarterly", None),
        ("10PAY", "Ten installments", None), ("12PAY", "Monthly", None), ("EFT12", "Monthly electronic funds transfer", None)]),
    ("PAYMENT_METHOD", "Payment Method", "How a payment was made.", "SI2", [
        ("CHECK", "Check", None), ("ACH", "ACH / bank transfer", None), ("CARD", "Credit or debit card", None),
        ("WIRE", "Wire transfer", None), ("AGENCY", "Paid through the agency", None)]),
    ("BILLING_TYPE", "Billing Type", "Who bills the insured.", "SI2", [("DIRECT", "Direct bill", None), ("AGENCY", "Agency bill", None),
                                                                       ("LIST", "List bill", None)]),
    ("PARTY_TYPE", "Party Type", "Kind of party.", "SI2", [("PERSON", "Person", None), ("ORGANIZATION", "Organization", None)]),
    ("PARTY_ROLE", "Party Role", "Role a party plays on a policy or claim.", "SI2", [
        ("NAMED_INSURED", "Named insured", None), ("ADDITIONAL_INSURED", "Additional insured", None), ("DRIVER", "Driver", None),
        ("CLAIMANT", "Claimant", None), ("MORTGAGEE", "Mortgagee", None), ("LIENHOLDER", "Lienholder", None),
        ("WITNESS", "Witness", None), ("ATTORNEY", "Attorney", None), ("VENDOR", "Vendor / repair shop", None)]),
    ("MARITAL_STATUS", "Marital Status", "Marital status of a person (where permitted for rating).", "SI2", [
        ("S", "Single", None), ("M", "Married", None), ("D", "Divorced", None), ("W", "Widowed", None), ("P", "Domestic partner", None)]),
    ("VEHICLE_USE", "Vehicle Use", "Principal use of the vehicle.", "SI2", [
        ("PLEASURE", "Pleasure", None), ("COMMUTE", "Commute", None), ("BUSINESS", "Business", None), ("FARM", "Farm", None),
        ("RIDESHARE", "Rideshare (transportation network)", None), ("DELIVERY", "Delivery", None)]),
    ("VEHICLE_TYPE", "Vehicle Type", "Body / vehicle type.", "SI2", [
        ("PPA", "Private passenger auto", None), ("SUV", "Sport utility vehicle", None), ("PICKUP", "Pickup truck", None),
        ("VAN", "Van / minivan", None), ("MOTORCYCLE", "Motorcycle", None), ("TRAILER", "Trailer", None),
        ("LIGHT_TRUCK", "Light truck (commercial)", None), ("MEDIUM_TRUCK", "Medium truck", None), ("HEAVY_TRUCK", "Heavy truck", None),
        ("TRACTOR", "Truck-tractor", None), ("BUS", "Bus", None)]),
    ("RISK_TYPE", "Risk Type", "Kind of insured risk item.", "SI2", [
        ("VEHICLE", "Vehicle", None), ("DWELLING", "Dwelling", None), ("BUILDING", "Building", None), ("LOCATION", "Location", None),
        ("CLASS_EXPOSURE", "Class exposure (payroll, sales, area)", None), ("EQUIPMENT", "Equipment", None)]),
    ("OCCUPANCY", "Occupancy", "How a dwelling is occupied.", "SI2", [
        ("OWNER", "Owner occupied", None), ("TENANT", "Tenant occupied", None), ("SEASONAL", "Seasonal / secondary", None),
        ("VACANT", "Vacant", None), ("UNOCCUPIED", "Unoccupied", None)]),
    ("ROOF_TYPE", "Roof Type", "Roof covering material.", "SI2", [
        ("ASPHALT", "Asphalt shingle", None), ("METAL", "Metal", None), ("TILE", "Clay or concrete tile", None),
        ("SLATE", "Slate", None), ("WOOD", "Wood shake", None), ("FLAT", "Flat / built-up / membrane", None)]),
    ("CLAIM_TYPE", "Claim Type", "Broad kind of claim.", "SI2", [
        ("PROPERTY", "Property", None), ("AUTO_PD", "Auto physical damage", None), ("AUTO_BI", "Auto bodily injury", None),
        ("LIABILITY", "General liability", None), ("WC_MED", "Workers comp medical only", None), ("WC_IND", "Workers comp indemnity", None)]),
    ("CLAIMANT_TYPE", "Claimant Type", "Relationship of the claimant to the policy.", "SI2", [
        ("INSURED", "First party (insured)", None), ("THIRD_PARTY", "Third party", None), ("EMPLOYEE", "Injured employee", None)]),
    ("CLAIM_TIER", "Claim Handling Tier", "Triage tier assigned to a claim.", "SI2", [
        ("FAST_TRACK", "Fast track", None), ("STANDARD", "Standard", None), ("COMPLEX", "Complex", None),
        ("SIU", "Special investigation", None)]),
    ("UW_DECISION", "Underwriting Decision", "Outcome of underwriting review.", "SI2", [
        ("ACCEPT", "Accept", None), ("REFER", "Refer to a senior underwriter", None), ("DECLINE", "Decline", None),
        ("COUNTER", "Counter-offer (different terms)", None)]),
    ("CHANNEL", "Distribution Channel", "How the business was sold.", "SI2", [
        ("INDEPENDENT_AGENT", "Independent agent", None), ("CAPTIVE_AGENT", "Captive agent", None), ("BROKER", "Broker", None),
        ("DIRECT_ONLINE", "Direct online", None), ("CALL_CENTER", "Call center", None), ("MGA", "Managing general agent", None)]),
    ("REINSURANCE_TYPE", "Reinsurance Type", "Kind of reinsurance contract.", "SI2", [
        ("QS", "Quota share", None), ("SURPLUS", "Surplus share", None), ("PER_RISK_XOL", "Per-risk excess of loss", None),
        ("CAT_XOL", "Catastrophe excess of loss", None), ("AGG_STOP", "Aggregate stop loss", None), ("FAC", "Facultative", None)]),
    ("DEDUCTIBLE_TYPE", "Deductible Type", "How a deductible applies.", "SI2", [
        ("FLAT", "Flat amount", None), ("PERCENT", "Percent of the insured value", None), ("FRANCHISE", "Franchise", None),
        ("AGGREGATE", "Annual aggregate", None)]),
    ("FRAUD_INDICATOR", "Fraud Indicator", "Red flag observed on a claim.", "SI2", [
        ("LATE_REPORT", "Reported late", None), ("NEW_POLICY", "Loss soon after inception", None),
        ("SHARED_CONTACT", "Phone / address shared with other claims", None), ("SAME_VENDOR_ATTORNEY", "Same repair vendor and attorney pattern", None),
        ("PRIOR_SIU", "Prior SIU history", None), ("INCONSISTENT_STORY", "Inconsistent statements", None),
        ("SOFT_TISSUE", "Soft-tissue injury only", None), ("PHOTO_MISMATCH", "Photos do not match the damage described", None)]),
    ("RULE_ACTION", "Rule Action", "What a business rule does when it fires.", "SI2", [
        ("ACCEPT", "Accept", None), ("DECLINE", "Decline", None), ("REFER", "Refer", None), ("SURCHARGE_PCT", "Surcharge %", None),
        ("CREDIT_PCT", "Credit %", None), ("SET_VALUE", "Set a value", None), ("REJECT", "Reject the record", None), ("WARN", "Warn", None),
        ("ROUTE", "Route to a queue", None), ("FLAG", "Flag", None)]),
]

ELEMENT_RENAME = {"STATUS": "CLAIM_STATUS", "SEQUENCE": "RISK_ITEM_SEQUENCE", "MAKE": "VEHICLE_MAKE", "SYMBOL": "VEHICLE_SYMBOL",
                  "RATING_SYMBOL": "VEHICLE_SYMBOL", "ACCOUNT_DATE": "ACCOUNTING_DATE", "ATTORNEY_INVOLVED": "ATTORNEY_INDICATOR",
                  "NUMBER_EMPLOYEES": "EMPLOYEE_COUNT", "TYPE_CLAIM": "CLAIM_TYPE_CODE", "TYPE_LOSS": "LOSS_TYPE_CODE",
                  "TYPE_RECOVERY": "RECOVERY_TYPE", "TYPE_SETTLEMENT": "SETTLEMENT_TYPE", "TYPE_PLAN": "PLAN_TYPE",
                  "CLOSING_DATE": "CLAIM_CLOSE_DATE", "ADDRESS_ZIP": "ZIP_CODE", "ADDRESS_STATE": "STATE", "PRODUCER_STATE": "STATE",
                  "TELEMATICS_INDICATOR": "TELEMATICS_IND", "RIDESHARE_INDICATOR": "RIDESHARE_IND", "LOSS_ZIP": "LOSS_ZIP_CODE"}
SKIP_ELEMENTS = {"FILLER", "COMPANY_USE"}

ELEMENT_PICKLIST = {  # element -> pick list (ISO lists first; NCCI lists are recorded as an extension attribute)
    "STATE": "STATE", "JURISDICTION_STATE": "STATE", "LINE_OF_BUSINESS": "LOB", "MAJOR_LINE": "MAJOR_LINE", "COVERAGE_CODE": "COVERAGE",
    "TRANSACTION_TYPE": "TRANSACTION_TYPE", "CLAIM_STATUS": "CLAIM_STATUS", "CONSTRUCTION": "CONSTRUCTION",
    "PROTECTION_CLASS": "PROTECTION_CLASS", "COINSURANCE": "COINSURANCE", "LIMIT_CODE": "LIMIT_CODE", "DEDUCTIBLE": "DEDUCTIBLE",
    "WIND_HAIL_DEDUCTIBLE": "WIND_HAIL_DED", "EXPOSURE_BASE": "EXPOSURE_BASE", "SUBLINE": "GL_SUBLINE", "POLICY_FORM": "POLICY_FORM",
    "FILED_FORM": "FILED_FORM", "INSURING_AGREEMENT": "INSURING_AGREEMENT", "PROJECT_CATEGORY": "PROJECT_CATEGORY",
    "CAUSE_OF_LOSS": "CAUSE_OF_LOSS", "POLICY_STATUS": "POLICY_STATUS", "PAYMENT_PLAN": "PAYMENT_PLAN", "PARTY_TYPE": "PARTY_TYPE",
    "VEHICLE_USE": "VEHICLE_USE", "VEHICLE_TYPE": "VEHICLE_TYPE", "RISK_TYPE": "RISK_TYPE", "DEDUCTIBLE_TYPE": "DEDUCTIBLE_TYPE",
    "TELEMATICS_IND": "YES_NO", "RIDESHARE_IND": "YES_NO", "ATTORNEY_INDICATOR": "YES_NO", "LUMP_SUM_INDICATOR": "YES_NO",
    "RETROSPECTIVE_RATED": "YES_NO", "OCCUPANCY": "OCCUPANCY", "ROOF_TYPE": "ROOF_TYPE", "UW_DECISION": "UW_DECISION",
    "CHANNEL": "CHANNEL", "REINSURANCE_TYPE": "REINSURANCE_TYPE", "PAYMENT_METHOD": "PAYMENT_METHOD", "BILLING_TYPE": "BILLING_TYPE",
    "MARITAL_STATUS": "MARITAL_STATUS", "CLAIM_TYPE": "CLAIM_TYPE", "CLAIMANT_TYPE": "CLAIMANT_TYPE", "CLAIM_TIER": "CLAIM_TIER",
    "PARTY_ROLE": "PARTY_ROLE", "SIU_REFERRAL_IND": "YES_NO", "SUBROGATION_IND": "YES_NO", "FRAUD_INDICATOR": "FRAUD_INDICATOR",
}

# Elements the apps do not have yet but every carrier needs (code, name, description, type, picklist, pii)
EXTRA_ELEMENTS = [
    ("SUBMISSION_ID", "Submission ID", "Identifier of a new-business submission or quote request.", "TEXT", None, False),
    ("UW_DECISION", "Underwriting Decision", "Accept, refer, decline or counter-offer, decided by the underwriter.", "CODE", "UW_DECISION", False),
    ("DECISION_REASON", "Decision Reason", "Reason the person gave, required when the decision differs from SI²'s recommendation.", "TEXT", None, False),
    ("RISK_SCORE", "Risk Score", "SI² risk score 0-100 for a submission or policy (higher = riskier).", "DECIMAL", None, False),
    ("TOTAL_INSURED_VALUE", "Total Insured Value", "Sum of insured values for a risk or account (TIV).", "AMOUNT", None, False),
    ("YEAR_BUILT", "Year Built", "Year the building was constructed.", "INTEGER", None, False),
    ("ROOF_TYPE", "Roof Type", "Roof covering material.", "CODE", "ROOF_TYPE", False),
    ("ROOF_AGE", "Roof Age", "Age of the roof covering in years.", "INTEGER", None, False),
    ("OCCUPANCY", "Occupancy", "How the dwelling is occupied.", "CODE", "OCCUPANCY", False),
    ("SQUARE_FEET", "Square Feet", "Finished living or building area in square feet.", "INTEGER", None, False),
    ("DISTANCE_TO_COAST", "Distance to Coast", "Distance from the risk to the coast in miles.", "DECIMAL", None, False),
    ("TELEMATICS_SCORE", "Telematics Score", "Usage-based driving score 0-100 (higher = safer).", "DECIMAL", None, False),
    ("VEHICLE_VALUE", "Vehicle Value", "Current market value of the vehicle.", "AMOUNT", None, False),
    ("COVERAGE_LAPSE_DAYS", "Coverage Lapse Days", "Days without insurance before this policy.", "INTEGER", None, False),
    ("YEARS_LICENSED", "Years Licensed", "Years the driver has been licensed.", "INTEGER", None, False),
    ("MARITAL_STATUS", "Marital Status", "Marital status of a person (where permitted for rating).", "CODE", "MARITAL_STATUS", True),
    ("PARTY_ROLE", "Party Role", "Role the party plays on the policy or claim.", "CODE", "PARTY_ROLE", False),
    ("CLAIM_TYPE", "Claim Type", "Broad kind of claim (property, auto PD, auto BI, liability, WC).", "CODE", "CLAIM_TYPE", False),
    ("CLAIMANT_TYPE", "Claimant Type", "First party, third party or injured employee.", "CODE", "CLAIMANT_TYPE", False),
    ("CLAIM_TIER", "Claim Handling Tier", "Fast track, standard, complex or special investigation.", "CODE", "CLAIM_TIER", False),
    ("INCURRED_LOSS", "Incurred Loss", "Paid loss plus outstanding reserve.", "AMOUNT", None, False),
    ("RESERVE_CHANGE_AMOUNT", "Reserve Change Amount", "Proposed change to the case reserve; above the adjuster's authority it needs a second person.", "AMOUNT", None, False),
    ("FRAUD_SCORE", "Fraud Score", "SI² fraud score 0-100 for a claim or network.", "DECIMAL", None, False),
    ("FRAUD_INDICATOR", "Fraud Indicator", "Red flag observed on a claim.", "CODE", "FRAUD_INDICATOR", False),
    ("SIU_REFERRAL_IND", "SIU Referral Indicator", "Claim referred to the Special Investigations Unit.", "CODE", "YES_NO", False),
    ("SUBROGATION_IND", "Subrogation Indicator", "Recovery from a responsible third party is being pursued.", "CODE", "YES_NO", False),
    ("CHANNEL", "Distribution Channel", "How the business was sold.", "CODE", "CHANNEL", False),
    ("COMMISSION_RATE", "Commission Rate", "Commission paid to the producer as a share of premium.", "PERCENT", None, False),
    ("INVOICE_NUMBER", "Invoice Number", "Identifier of a billing invoice.", "TEXT", None, False),
    ("INVOICE_DATE", "Invoice Date", "Date the invoice was issued.", "DATE", None, False),
    ("DUE_DATE", "Due Date", "Date a payment is due.", "DATE", None, False),
    ("AMOUNT_DUE", "Amount Due", "Amount the insured owes on an invoice.", "AMOUNT", None, False),
    ("PAYMENT_AMOUNT", "Payment Amount", "Amount received from the insured.", "AMOUNT", None, False),
    ("PAYMENT_METHOD", "Payment Method", "How the payment was made.", "CODE", "PAYMENT_METHOD", False),
    ("BILLING_TYPE", "Billing Type", "Direct, agency or list bill.", "CODE", "BILLING_TYPE", False),
    ("ACCOUNT_BALANCE", "Account Balance", "Billing account balance (positive = owed by the insured).", "AMOUNT", None, False),
    ("TREATY_ID", "Treaty ID", "Identifier of a reinsurance treaty.", "TEXT", None, False),
    ("REINSURANCE_TYPE", "Reinsurance Type", "Quota share, surplus, per-risk or catastrophe excess of loss, stop loss, facultative.", "CODE", "REINSURANCE_TYPE", False),
    ("RETENTION_AMOUNT", "Retention Amount", "Amount the company keeps before reinsurance pays.", "AMOUNT", None, False),
    ("LAYER_LIMIT", "Layer Limit", "Limit of a reinsurance layer.", "AMOUNT", None, False),
    ("CEDED_PREMIUM", "Ceded Premium", "Premium paid to reinsurers.", "AMOUNT", None, False),
    ("CEDED_LOSS", "Ceded Loss", "Loss recovered from reinsurers.", "AMOUNT", None, False),
    ("REINSURER_NAME", "Reinsurer Name", "Name of the reinsurer.", "TEXT", None, False),
    ("REINSURER_RATING", "Reinsurer Financial Strength Rating", "Financial strength rating of the reinsurer (e.g. A+).", "TEXT", None, False),
    ("SOLVENCY_RATIO", "Solvency Ratio", "Available capital divided by required capital.", "DECIMAL", None, False),
    ("NET_CAT_1_IN_200", "Net 1-in-200 Catastrophe Loss", "Catastrophe loss at the 1-in-200 return period after reinsurance.", "AMOUNT", None, False),
    ("COUNTY", "County", "County of the risk location.", "TEXT", None, False),
    ("LATITUDE", "Latitude", "Latitude of the risk location.", "DECIMAL", None, False),
    ("LONGITUDE", "Longitude", "Longitude of the risk location.", "DECIMAL", None, False),
    ("POLICY_STATUS", "Policy Status", "Life-cycle status of the policy term.", "CODE", "POLICY_STATUS", False),
    ("VEHICLE_TYPE", "Vehicle Type", "Body / vehicle type.", "CODE", "VEHICLE_TYPE", False),
    ("DEDUCTIBLE_TYPE", "Deductible Type", "Flat, percent, franchise or aggregate.", "CODE", "DEDUCTIBLE_TYPE", False),
]

COMMON_ABBREVIATIONS = {
    "POLICY_NUMBER": ["POL_NO", "POL_NBR", "POLICY_NO", "POLNUM", "PolicyNumber"], "CLAIM_NUMBER": ["CLM_NO", "CLM_NBR", "CLAIM_NO", "ClaimNumber"],
    "LOSS_DATE": ["DOL", "LOSS_DT", "ACCIDENT_DT", "DATE_OF_LOSS"], "POLICY_EFFECTIVE_DATE": ["EFF_DT", "POL_EFF_DT", "INCEPTION_DATE"],
    "POLICY_EXPIRATION_DATE": ["EXP_DT", "POL_EXP_DT"], "WRITTEN_PREMIUM": ["WP", "WRTN_PREM", "PREM_AMT"],
    "PAID_LOSS": ["PD_LOSS", "LOSS_PD", "PAID_AMT"], "OUTSTANDING_RESERVE": ["OS_RSV", "OS_RESERVE", "CASE_RESERVE", "RSV_AMT"],
    "ZIP_CODE": ["ZIP", "POSTAL_CD", "ZIP5"], "STATE": ["ST", "ST_CD", "STATE_CD"], "INSURED_NAME": ["INSD_NM", "NAMED_INSURED"],
    "PRODUCER_CODE": ["AGT_CD", "AGENT_NO", "PRODUCER_NO"], "CAUSE_OF_LOSS": ["COL", "LOSS_CAUSE", "CAUSE_CD"],
    "LINE_OF_BUSINESS": ["LOB", "LOB_CD"], "COVERAGE_CODE": ["COV_CD", "COV_TYPE"], "CLAIM_STATUS": ["CLM_STAT", "CLM_STS"],
    "VEHICLE_MODEL_YEAR": ["VEH_YR", "MODEL_YR"], "DRIVER_BIRTH_DATE": ["DOB", "BIRTH_DT"], "TOTAL_INSURED_VALUE": ["TIV"],
    "ALAE": ["DCC", "DEFENSE_COST"], "FEIN": ["Federal Employer Identification Number", "FED_TAX_ID"],
    "VIN": ["Vehicle Identification Number"], "REPORT_DATE": ["RPT_DT", "REPORTED_DT"], "INCURRED_LOSS": ["INCURRED", "INC_LOSS"],
}

PII = {"INSURED_NAME", "MAILING_ADDRESS", "ADDRESS_STREET", "EMAIL", "PHONE", "FEIN", "DRIVER_BIRTH_DATE", "PRIMARY_ICD_DIAGNOSTIC_CODE",
       "SECONDARY_ICD_DIAGNOSTIC_CODE", "MARITAL_STATUS", "CLAIMANT_GENDER", "LATITUDE", "LONGITUDE", "WEEKLY_WAGE_AMOUNT"}

TYPE_MAP = {"money": "AMOUNT", "amount": "AMOUNT", "date": "DATE", "number": "DECIMAL", "integer": "INTEGER", "int": "INTEGER",
            "decimal": "DECIMAL", "factor": "DECIMAL", "rate": "DECIMAL", "code": "CODE", "picklist": "CODE", "state": "CODE",
            "text": "TEXT", "string": "TEXT", "boolean": "BOOLEAN"}
APP_SOURCE = {"Core canonical": "SI2 Core", "ISO bureau": "ISO", "NCCI bureau": "NCCI", "Migration (cloud)": "SI2 Cloud",
              "Rule engine": "SI2 Rules", "Rating engine": "SI2 Rating"}


def merge_ext(ext):
    """One row per (object, attribute): several values are joined, so the unique key holds."""
    vals = collections.OrderedDict()
    for ot, pl, oc, n, v in sorted(set(ext)):
        vals.setdefault((ot, pl, oc, n), [])
        if v not in vals[(ot, pl, oc, n)]:
            vals[(ot, pl, oc, n)].append(v)
    return [(*k, "; ".join(v)) for k, v in vals.items()]


def build() -> str:
    out: list[str] = []
    w = out.append
    w("/* SI² Canonical Master · seed (generated by build_seed.py; do not edit by hand).\n"
      "   Idempotent: every insert adds only what is missing, so it can be re-run after the model grows. */")
    w("USE SI2Canonical;\nSET NOCOUNT ON;\nGO\n")

    # ---- subject areas
    w("-- Subject areas")
    values_insert(out, "INSERT canon.SubjectArea (SubjectAreaCode, Name, Description, SortOrder, CreatedBy)\nSELECT v.c, v.n, v.d, v.s, " + q(BY),
                  ["c", "n", "d", "s"], SUBJECTS,
                  "WHERE NOT EXISTS (SELECT 1 FROM canon.SubjectArea x WHERE x.SubjectAreaCode = v.c)")

    # ---- pick lists and options ------------------------------------------------------------------
    picklists: dict[str, tuple] = {}            # code -> (name, desc, library, release)
    options: list[tuple] = []                   # (picklist, code, name, desc, lob, state, sort, eff)
    bureau: list[tuple] = []                    # (picklist, option, lob, bureau, field, code, eff)
    syn: list[tuple] = []                       # (object_type, picklist, object_code, text, type, source)
    ext: list[tuple] = []                       # (object_type, picklist, object_code, name, value)
    pending: list[tuple] = []                   # (object_type, change, object_code, summary, payload)

    iso_desc = {"LOB": "ISO statistical line of business.", "STATE": "US state, with the ISO / NCCI numeric state code.",
                "YES_NO": "Yes / No indicator."}
    for code, name in C.PICKLISTS.items():
        picklists[code] = (name, iso_desc.get(code, f"{name} codes used in ISO statistical reporting."),
                           "USPS" if code == "STATE" else ("STANDARD" if code == "YES_NO" else "ISO"), "ISO Statistical Plans (SI² catalog)")
    for pl, rows in C.OPTIONS.items():
        for i, r in enumerate(rows):
            lob, oc, on, iso = (r + (None,) * 4)[:4]
            options.append((pl, oc, on, None, lob or "*", "*", (i + 1) * 10, BASE))
            if iso not in (None, ""):
                bureau.append((pl, oc, lob or "*", "ISO", C.PICKLISTS.get(pl), str(iso), BASE))
    for pl, lob, oc, on, iso, eff in C.PENDING_OPTION_CHANGES:
        payload = {"picklist": pl, "code": oc, "name": on, "lob": lob, "effective_from": eff, "bureau": "ISO", "bureau_code": iso,
                   "bureau_field": C.PICKLISTS.get(pl)}
        pending.append(("OPTION", "ADD", f"{pl}.{oc}", f"ISO circular: new {pl} code {oc} ({on}) for {lob} effective {eff}", payload))
    for pl, text, src in C.PICKLIST_ALIASES:
        b, _, s = src.partition(":")
        syn.append(("PICKLIST", None, pl, text, "BUREAU" if b == "BUREAU" else ("SOURCE" if b == "SOURCE" else "BUSINESS"), s or "*"))
    for pl, oc, src, val in C.OPTION_ALIASES:
        syn.append(("OPTION", pl, oc, val, "SOURCE" if src != "*" else "VALUE", src))
    # STATE options also answer to their full names and numeric codes
    for s, n, c in C.STATES:
        syn.append(("OPTION", "STATE", s, n, "BUSINESS", "*"))
    syn.append(("OPTION", "STATE", "FL", "FLA", "ABBREVIATION", "*"))

    # NCCI WCIO code lists
    cat = json.load(open(ROOT / "bureau" / "catalog.json"))
    ncci: dict[str, dict] = collections.OrderedDict()
    specs: dict[str, set] = collections.defaultdict(set)
    for f in cat:
        if f["codes"]:
            specs[f["name"]].add(f["spec"])
            for k in f["codes"]:
                ncci.setdefault(f["name"], {}).setdefault(k["code"], k)
    ncci_code_of = {}
    for fname, codes in ncci.items():
        pl = ("NCCI_" + snake(fname))[:60]
        ncci_code_of[fname] = pl
        picklists[pl] = (title(snake(fname)), f"NCCI / WCIO code list for '{fname}' ({', '.join(sorted(specs[fname]))}).", "NCCI",
                         "WCIO specifications (SI² catalog)")
        syn.append(("PICKLIST", None, pl, fname, "BUREAU", "NCCI"))
        for i, (cd, k) in enumerate(codes.items()):
            if k.get("reserved"):
                continue
            nm = k["description"].split(". ")[0].strip()
            if len(nm) > 120:
                nm = nm[:120].rsplit(" ", 1)[0] + " ..."
            nm = nm or cd
            desc = k["description"][:2000]
            if k.get("na_states"):
                desc = (desc + f" Not applicable in: {k['na_states']}.")[:2000]
            options.append((pl, cd[:60], nm, desc if desc != nm else None, "WC", "*", (i + 1) * 10, BASE))
            bureau.append((pl, cd[:60], "WC", "NCCI", fname, cd, BASE))
    # NCCI value synonyms (source words -> option name)
    for val, desc in NC.VALUE_SYNONYMS.items():
        for pl_field, codes in ncci.items():
            for cd, k in codes.items():
                if not k.get("reserved") and k["description"].strip().lower().startswith(desc.lower()):
                    syn.append(("OPTION", ncci_code_of[pl_field], cd[:60], val, "VALUE", "*"))
    for (fname, val), desc in NC.CONTEXT_SYNONYMS.items():
        if fname in ncci:
            for cd, k in ncci[fname].items():
                if k["description"].lower().startswith(desc.lower()):
                    syn.append(("OPTION", ncci_code_of[fname], cd[:60], val, "VALUE", "*"))

    # Company additions to standard lists (not ISO-reported)
    for pl, oc, on, lob in [("LOB", "WC", "Workers Compensation", "*"),
                            ("COVERAGE", "DWELL", "Coverage A - Dwelling", "HO"), ("COVERAGE", "OTHSTR", "Coverage B - Other Structures", "HO"),
                            ("COVERAGE", "PERSPROP", "Coverage C - Personal Property", "HO"), ("COVERAGE", "LOU", "Coverage D - Loss of Use", "HO"),
                            ("COVERAGE", "PERSLIAB", "Coverage E - Personal Liability", "HO"), ("COVERAGE", "MEDPAY", "Coverage F - Medical Payments", "HO"),
                            ("COVERAGE", "WCEL", "Workers Compensation and Employers Liability", "WC")]:
        options.append((pl, oc, on, "Company option (no ISO code)", lob, "*", 500, BASE))

    # Domain lists
    for code, name, desc, lib, opts in DOMAIN_LISTS + [(c, n, d, lb, [(oc, on, None) for oc, on in o]) for c, n, d, lb, o in X.LISTS]:
        picklists[code] = (name, desc, lib, None)
        for i, (oc, on, od) in enumerate(opts):
            options.append((code, oc, on, od, "*", "*", (i + 1) * 10, BASE))

    # Cloud (migration) and legacy code tables -> synonyms on the matching option
    opt_by_list = collections.defaultdict(list)
    for o in options:
        opt_by_list[o[0]].append(o)
    target = {"ClaimStatus": "CLAIM_STATUS", "CoverageType": "COVERAGE", "LineOfBusiness": "LOB", "LossCause": "CAUSE_OF_LOSS",
              "PaymentPlan": "PAYMENT_PLAN", "PolicyStatus": "POLICY_STATUS", "COVTYPE": "COVERAGE", "LOSSCAUSE": "CAUSE_OF_LOSS"}

    def best_option(pl, code, desc):
        best, score = None, 0.0
        for o in opt_by_list[pl]:
            for cand in (o[1], o[2]):
                s = max(difflib.SequenceMatcher(None, str(desc).lower(), str(cand).lower()).ratio(),
                        difflib.SequenceMatcher(None, str(code).lower(), str(cand).lower()).ratio())
                if str(code).upper() == str(o[1]).upper():
                    s = 1.0
                elif len(str(desc)) >= 4 and (str(desc).lower() in str(cand).lower() or str(cand).lower() in str(desc).lower()):
                    s = max(s, 0.8)
                if s > score:
                    best, score = o, s
        return best if score >= 0.6 else None

    unmatched = []
    for fn, src in (("destination_picklists.csv", "SI2 Cloud"), ("CODE_TABLE.csv", "Legacy")):
        with open(ROOT / "migrate" / "samples" / fn) as fh:
            for r in csv.reader(fh):
                if r[0] in ("pick_list", "TABLE_ID"):
                    continue
                pl = target.get(r[0])
                if not pl:
                    continue
                syn.append(("PICKLIST", None, pl, r[0], "SOURCE", src))
                o = best_option(pl, r[1], r[2])
                if o:
                    syn.append(("OPTION", pl, o[1], r[1], "SOURCE", src))
                    if r[2].strip().upper() != str(o[2]).upper():
                        syn.append(("OPTION", pl, o[1], r[2], "SOURCE", src))
                else:
                    unmatched.append((src, r[0], r[1], r[2], pl))

    # ---- data elements ----------------------------------------------------------------------------
    h = R.harvest()
    h["code"] = [ELEMENT_RENAME.get(t, t) for t in h.term]
    h = h[~h.code.isin(SKIP_ELEMENTS)]
    iso_spec = {**C.ELEMENTS, **C.NEW_2027_ELEMENTS}
    iso_to_code = {}
    for r in h[h.app == "ISO bureau"].itertuples():
        iso_to_code[r.element] = r.code
    elements: dict[str, dict] = {}
    usage: list[tuple] = []
    for code, g in h.groupby("code"):
        descs = [d for d in g.description if d and len(d) > 3 and d.lower() != code.replace("_", " ").lower()]
        types = [TYPE_MAP.get(t) for t in g.type if TYPE_MAP.get(t)]
        pl = ELEMENT_PICKLIST.get(code)
        iso_rows = g[g.app == "ISO bureau"]
        for r in iso_rows.itertuples():
            spec = iso_spec.get(r.element)
            if spec and spec[2] and not pl:
                pl = spec[2]
        dtype = "CODE" if pl else (collections.Counter(types).most_common(1)[0][0] if types else "TEXT")
        if code.endswith(("_DATE", "_DT")) and not pl:
            dtype = "DATE"
        if code.endswith("_ID") or code.endswith("_NUMBER"):
            dtype = "TEXT" if dtype in ("DECIMAL", "INTEGER") and code.endswith("_NUMBER") else dtype
        bureau_used = bool(set(g.app) & {"ISO bureau", "NCCI bureau"})
        elements[code] = {"name": title(code), "desc": max(descs, key=len) if descs else title(code) + ".",
                          "subject": subject_of(code, set(g.entity)), "type": dtype, "pl": pl, "pii": code in PII,
                          "bureau": bureau_used,
                          "risk": "HIGH" if bureau_used and dtype in ("AMOUNT", "CODE", "DATE") else ("LOW" if dtype == "TEXT" else "MEDIUM")}
        for r in g.itertuples():
            src = APP_SOURCE[r.app]
            last = r.element.split(".")[-1]
            usage.append((code, r.app, r.entity if r.entity else None, r.element))
            if norm(last) != norm(code):
                syn.append(("ELEMENT", None, code, last, "APP", src))
        # concept word sets -> business synonyms
        last_words = ("AMOUNT", "NUMBER", "DATE", "CODE", "IDENTIFIER", "TYPE", "NAME", "LIMIT", "DEDUCTIBLE", "STATUS")
        for ws in R.CONCEPTS.get(code, []):
            cw = code.split("_")
            if len(ws) > 2 or set(ws) <= set(cw) or "REL" in ws:
                continue
            first_words = ("NAMED", "FULL", "PRIOR", "BASE", "RISK", "PRIMARY", "AT", "BI", "PD", "COLL", "COMP", "VEHICLE", "POSTAL", "BILL", "RATING", "VIOLATION")
            phrase = " ".join(sorted(ws, key=lambda x: (0 if x in first_words else (2 if x in last_words else 1),
                                                        cw.index(x) if x in cw else 9, x)))
            if norm(phrase) != norm(code):
                syn.append(("ELEMENT", None, code, title(phrase.replace(" ", "_")), "BUSINESS", "*"))
    # ISO field names, Guidewire and DuckCreek names
    for fld, el in C.FIELD_TO_ELEMENT.items():
        code = iso_to_code.get(el)
        if code in elements:
            syn.append(("ELEMENT", None, code, fld, "BUREAU", "ISO"))
    for el, spec in iso_spec.items():
        code = iso_to_code.get(el)
        if code in elements:
            if spec[4]:
                syn.append(("ELEMENT", None, code, spec[4], "SOURCE", "Guidewire"))
            if spec[5]:
                syn.append(("ELEMENT", None, code, spec[5], "SOURCE", "DuckCreek"))
    # NCCI bureau field names (aliases) and the NCCI code list each element reports with
    for table, cols in NC.SCHEMA.items():
        for col, (_t, _d, aliases) in cols.items():
            row = h[(h.app == "NCCI bureau") & (h.element == f"{table}.{col}")]
            if row.empty:
                continue
            code = row.code.iloc[0]
            for a in aliases:
                syn.append(("ELEMENT", None, code, a, "BUREAU" if a.isupper() else "BUSINESS", "NCCI" if a.isupper() else "*"))
                if a in ncci_code_of:
                    if not elements[code]["pl"]:
                        elements[code]["pl"] = ncci_code_of[a]
                        elements[code]["type"] = "CODE"
                    elif elements[code]["pl"] != ncci_code_of[a]:
                        ext.append(("ELEMENT", None, code, "NCCI pick list", ncci_code_of[a]))
    for code, name, desc, dtype, pl, pii in EXTRA_ELEMENTS + X.ELEMENTS:
        if code in elements:
            elements[code].update({"pl": elements[code]["pl"] or pl})
            continue
        elements[code] = {"name": name, "desc": desc, "subject": subject_of(code, set()), "type": dtype, "pl": pl, "pii": pii,
                          "bureau": False, "risk": "MEDIUM"}
    # The rule engine's own words (driver_age, use_type ...) and the rating variables
    rule_field_map = {"state": "STATE", "driver_age": "DRIVER_AGE", "years_licensed": "YEARS_LICENSED", "prior_claims": "PRIOR_CLAIMS",
                      "violations": "VIOLATIONS", "vehicle_value": "VEHICLE_VALUE", "model_year": "VEHICLE_MODEL_YEAR",
                      "use_type": "VEHICLE_USE", "annual_miles": "ANNUAL_MILES", "coverage_lapse_days": "COVERAGE_LAPSE_DAYS",
                      "telematics_score": "TELEMATICS_SCORE", "drv_age": "DRIVER_AGE"}
    for f, code in rule_field_map.items():
        syn.append(("ELEMENT", None, code, f, "APP", "SI2 Rules"))
    for code, abbrs in COMMON_ABBREVIATIONS.items():
        for a in abbrs:
            syn.append(("ELEMENT", None, code, a, "ABBREVIATION", "*"))
    for code in list(elements):
        if elements[code]["pl"] and elements[code]["pl"] not in picklists:
            elements[code]["pl"] = None
            elements[code]["type"] = "TEXT"
        if elements[code]["subject"] is None:
            elements[code]["subject"] = "POLICY"
    for el, spec in C.NEW_2027_ELEMENTS.items():
        code = iso_to_code.get(el) or ELEMENT_RENAME.get(el, el)
        if code not in elements:
            payload = {"code": code, "name": spec[0], "description": spec[3], "data_type": "CODE", "picklist": spec[2],
                       "subject_area": "VEHICLE", "is_bureau": True, "risk": "HIGH",
                       "synonyms": [{"text": spec[4], "type": "SOURCE", "source": "Guidewire"}, {"text": spec[5], "type": "SOURCE", "source": "DuckCreek"},
                                    {"text": el, "type": "BUREAU", "source": "ISO"}]}
            pending.append(("ELEMENT", "ADD", code, f"ISO 2027 layout adds {spec[0]} ({el})", payload))

    # ---- write pick lists, options, bureau codes, elements, synonyms, usage ------------------------
    w("-- Pick lists")
    values_insert(out, "INSERT canon.PickList (PickListCode, Name, Description, LibrarySource, LibraryRelease, EffectiveFrom, CreatedBy)\n"
                       f"SELECT v.c, v.n, v.d, v.l, v.r, '{BASE}', {q(BY)}",
                  ["c", "n", "d", "l", "r"], [(k, *v) for k, v in picklists.items()],
                  "WHERE NOT EXISTS (SELECT 1 FROM canon.PickList x WHERE x.PickListCode = v.c AND x.ScopeId = 1)")
    seen = set()
    opts = []
    for o in options:
        key = (o[0], o[1].upper(), o[4])
        if key not in seen:
            seen.add(key)
            opts.append(o)
    w("-- Pick-list options")
    values_insert(out, "INSERT canon.PickListOption (PickListId, OptionCode, OptionName, Description, LobScope, StateScope, SortOrder, EffectiveFrom, CreatedBy)\n"
                       f"SELECT p.PickListId, v.oc, v.n, v.d, v.lob, v.st, v.s, v.ef, {q(BY)}",
                  ["pl", "oc", "n", "d", "lob", "st", "s", "ef"], opts,
                  "JOIN canon.PickList p ON p.PickListCode = v.pl AND p.ScopeId = 1\n"
                  "WHERE NOT EXISTS (SELECT 1 FROM canon.PickListOption x WHERE x.PickListId = p.PickListId AND x.OptionCode = v.oc "
                  "AND x.LobScope = v.lob AND x.ScopeId = 1)")
    w("-- Bureau codes")
    bseen, brows = set(), []
    for b in bureau:
        k = (b[0], b[1].upper(), b[2], b[3])
        if k not in bseen:
            bseen.add(k)
            brows.append(b)
    values_insert(out, "INSERT canon.BureauCodeMap (OptionId, Bureau, BureauField, BureauCode, LobScope, LibraryRelease, EffectiveFrom, CreatedBy)\n"
                       f"SELECT o.OptionId, v.b, v.f, v.bc, v.lob, p.LibraryRelease, v.ef, {q(BY)}",
                  ["pl", "oc", "lob", "b", "f", "bc", "ef"], brows,
                  "JOIN canon.PickList p ON p.PickListCode = v.pl AND p.ScopeId = 1\n"
                  "JOIN canon.PickListOption o ON o.PickListId = p.PickListId AND o.OptionCode = v.oc AND o.LobScope = v.lob AND o.ScopeId = 1\n"
                  "WHERE NOT EXISTS (SELECT 1 FROM canon.BureauCodeMap x WHERE x.OptionId = o.OptionId AND x.Bureau = v.b AND x.LobScope = v.lob)")

    w("-- Data elements")
    erows = [(c, e["name"], e["desc"][:2000], e["subject"], e["type"], e["pl"], e["pii"], e["bureau"], e["risk"]) for c, e in sorted(elements.items())]
    values_insert(out, "INSERT canon.DataElement (ElementCode, Name, BusinessDescription, SubjectAreaCode, DataType, PickListId, IsPII, IsBureauReported, RiskClass, EffectiveFrom, CreatedBy)\n"
                       f"SELECT v.c, v.n, v.d, v.sa, v.t, p.PickListId, v.pii, v.b, v.r, '{BASE}', {q(BY)}",
                  ["c", "n", "d", "sa", "t", "pl", "pii", "b", "r"], erows,
                  "LEFT JOIN canon.PickList p ON p.PickListCode = v.pl AND p.ScopeId = 1\n"
                  "WHERE NOT EXISTS (SELECT 1 FROM canon.DataElement x WHERE x.ElementCode = v.c AND x.ScopeId = 1)")

    w("-- Synonyms (elements, pick lists, options)")
    sseen, srows = set(), []
    for s in syn:
        ot, pl, oc, text, typ, src = s
        if ot == "ELEMENT" and oc not in elements:
            continue
        if not text or not str(text).strip():
            continue
        text = str(text).strip()[:300]
        k = (ot, pl, str(oc).upper(), text.upper(), src)
        if k in sseen:
            continue
        sseen.add(k)
        srows.append((ot, pl, oc, text, typ, src))
    values_insert(out, "INSERT canon.Synonym (ObjectType, ObjectId, SynonymText, SynonymType, SourceSystem, CreatedBy)\n"
                       f"SELECT v.ot, x.Id, v.t, v.ty, v.src, {q(BY)}",
                  ["ot", "pl", "oc", "t", "ty", "src"], srows,
                  "CROSS APPLY (SELECT CASE v.ot\n"
                  "    WHEN 'ELEMENT' THEN (SELECT ElementId FROM canon.DataElement WHERE ElementCode = v.oc AND ScopeId = 1)\n"
                  "    WHEN 'PICKLIST' THEN (SELECT PickListId FROM canon.PickList WHERE PickListCode = v.oc AND ScopeId = 1)\n"
                  "    WHEN 'OPTION' THEN (SELECT TOP (1) o.OptionId FROM canon.PickListOption o JOIN canon.PickList p ON p.PickListId = o.PickListId\n"
                  "                        WHERE p.PickListCode = v.pl AND p.ScopeId = 1 AND o.OptionCode = v.oc AND o.ScopeId = 1 ORDER BY o.OptionId) END AS Id) x\n"
                  "WHERE x.Id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM canon.Synonym s WHERE s.ObjectType = v.ot AND s.ObjectId = x.Id "
                  "AND s.SynonymText = v.t AND s.SourceSystem = v.src AND s.ScopeId = 1)")

    w("-- Where-used")
    useen, urows = set(), []
    for u in usage:
        uk = (u[0], u[1].upper(), str(u[2] or "").upper(), u[3].upper())
        if u[0] in elements and uk not in useen:
            useen.add(uk)
            urows.append(u)
    values_insert(out, f"INSERT canon.ElementUsage (ElementId, UsedIn, ObjectName, FieldName, CreatedBy)\nSELECT e.ElementId, v.u, v.o, v.f, {q(BY)}",
                  ["c", "u", "o", "f"], urows,
                  "JOIN canon.DataElement e ON e.ElementCode = v.c AND e.ScopeId = 1\n"
                  "WHERE NOT EXISTS (SELECT 1 FROM canon.ElementUsage x WHERE x.ElementId = e.ElementId AND x.UsedIn = v.u "
                  "AND ISNULL(x.ObjectName, N'') = ISNULL(v.o, N'') AND x.FieldName = v.f)")

    if ext:
        w("-- Extension attributes")
        values_insert(out, f"INSERT canon.ExtensionAttribute (ObjectType, ObjectId, AttributeName, AttributeValue, CreatedBy)\nSELECT v.ot, e.ElementId, v.n, v.val, {q(BY)}",
                      ["ot", "pl", "oc", "n", "val"], merge_ext(ext),
                      "JOIN canon.DataElement e ON e.ElementCode = v.oc AND e.ScopeId = 1\n"
                      "WHERE NOT EXISTS (SELECT 1 FROM canon.ExtensionAttribute x WHERE x.ObjectType = v.ot AND x.ObjectId = e.ElementId AND x.AttributeName = v.n AND x.ScopeId = 1)")

    # ---- rules -------------------------------------------------------------------------------------
    rulesets = [
        ("ISO_BUREAU", "ISO statistical reporting", "BUREAU", "Derivations, transformations and validations for ISO statistical plans (all lines)."),
        ("NCCI_EDITS", "NCCI / WCIO data edits", "BUREAU", "Edits a DCO applies to WCSTAT, WCPOLS, WCIND and WCMED submissions (SI² edit IDs)."),
        ("UW_PERSONAL_AUTO", "Personal auto underwriting", "UNDERWRITING", "Eligibility, referral and pricing rules for personal auto."),
        ("ROLE_AUTHORITY", "Role decision boundaries", "UNDERWRITING", "Authority and appetite boundaries each role works within; changes need a second person."),
        ("CLAIMS_TRIAGE", "Claims triage and routing", "CLAIMS", "Routing of new and open claims to fast track, complex handling or SIU."),
        ("DATA_QUALITY", "Data quality", "DATA_QUALITY", "Checks applied to every load before data reaches the company model."),
    ]
    w("-- Rule sets")
    values_insert(out, f"INSERT rules.RuleSet (RuleSetCode, Name, Purpose, Description, CreatedBy)\nSELECT v.c, v.n, v.p, v.d, {q(BY)}",
                  ["c", "n", "p", "d"], rulesets, "WHERE NOT EXISTS (SELECT 1 FROM rules.RuleSet x WHERE x.RuleSetCode = v.c AND x.ScopeId = 1)")

    rules: list[tuple] = []        # (ruleset, code, name, desc, type, lob, state, target, logic, cond_text, action, action_value, severity, message, priority, expr_json, eff)
    conds: list[tuple] = []        # (rule, seq, element, operator, v1, v2)
    tests: list[tuple] = []        # (rule, name, input_json, expected)
    for r in C.RULES:
        code, name, catg, lob, _rt, el, expr, sev, msg, desc, eff = r
        op = expr.get("op")
        action = {"DERIVATION": "LOOKUP" if op == "lookup" else "SET_VALUE", "TRANSFORMATION": "CALCULATE"}.get(catg, "REJECT" if sev == "ERROR" else "WARN")
        rules.append(("ISO_BUREAU", code, name, desc, catg if catg in ("VALIDATION", "DERIVATION", "TRANSFORMATION") else "VALIDATION",
                      lob or "*", "*", iso_to_code.get(el) if el else None, "ALL", None, action, None, sev, msg, 100, json.dumps(expr), eff))
    for code, (sev, text, fix) in NE.EDITS.items():
        rules.append(("NCCI_EDITS", code, text, text + ". " + fix, "VALIDATION", "WC", "*", None, "ALL", text, "REJECT" if sev != "Warning" else "WARN",
                      None, "WARNING" if sev == "Warning" else "ERROR", fix, 10 if sev == "Critical" else 50, None, BASE))

    # UW rules from the rule engine, written as conditions on data elements
    uw = [("R01", "Ineligible state", "DECLINE", None, [("STATE", "NOT IN", "FL,GA,NC,NY,OH,TX")]),
          ("R02", "Frequent claims", "DECLINE", None, [("PRIOR_CLAIMS", ">=", "3")]),
          ("R03", "Rideshare use", "DECLINE", None, [("VEHICLE_USE", "=", "RIDESHARE")]),
          ("R04", "Young driver, high-value vehicle", "REFER", None, [("DRIVER_AGE", "<", "21"), ("VEHICLE_VALUE", ">", "40000")]),
          ("R05", "Multiple violations", "REFER", None, [("VIOLATIONS", ">=", "2")]),
          ("R06", "Lapse in coverage", "SURCHARGE_PCT", "10", [("COVERAGE_LAPSE_DAYS", ">", "30")]),
          ("R07", "High annual mileage", "SURCHARGE_PCT", "5", [("ANNUAL_MILES", ">", "25000")]),
          ("R08", "Experienced clean driver", "CREDIT_PCT", "5", [("YEARS_LICENSED", ">=", "10"), ("PRIOR_CLAIMS", "=", "0"), ("VIOLATIONS", "=", "0")]),
          ("R09", "Low telematics score on delivery use", "SURCHARGE_PCT", "15", [("TELEMATICS_SCORE", "<", "40"), ("VEHICLE_USE", "=", "DELIVERY")]),
          ("R10", "Senior driver with a violation", "REFER", None, [("DRIVER_AGE", ">=", "80"), ("VIOLATIONS", ">=", "1")]),
          ("R11", "Florida high mileage", "SURCHARGE_PCT", "5", [("STATE", "=", "FL"), ("ANNUAL_MILES", ">", "20000")])]
    uw_tests = {"R01": ({"STATE": "CA"}, {"STATE": "TX"}), "R02": ({"PRIOR_CLAIMS": 3}, {"PRIOR_CLAIMS": 1}),
                "R03": ({"VEHICLE_USE": "RIDESHARE"}, {"VEHICLE_USE": "COMMUTE"}),
                "R04": ({"DRIVER_AGE": 19, "VEHICLE_VALUE": 45000}, {"DRIVER_AGE": 19, "VEHICLE_VALUE": 18000}),
                "R05": ({"VIOLATIONS": 2}, {"VIOLATIONS": 1}), "R06": ({"COVERAGE_LAPSE_DAYS": 45}, {"COVERAGE_LAPSE_DAYS": 10}),
                "R07": ({"ANNUAL_MILES": 30000}, {"ANNUAL_MILES": 12000}),
                "R08": ({"YEARS_LICENSED": 15, "PRIOR_CLAIMS": 0, "VIOLATIONS": 0}, {"YEARS_LICENSED": 15, "PRIOR_CLAIMS": 1, "VIOLATIONS": 0}),
                "R09": ({"TELEMATICS_SCORE": 32, "VEHICLE_USE": "DELIVERY"}, {"TELEMATICS_SCORE": 32, "VEHICLE_USE": "PLEASURE"}),
                "R10": ({"DRIVER_AGE": 82, "VIOLATIONS": 1}, {"DRIVER_AGE": 82, "VIOLATIONS": 0}),
                "R11": ({"STATE": "FL", "ANNUAL_MILES": 22000}, {"STATE": "GA", "ANNUAL_MILES": 22000})}
    rtype = {"DECLINE": "ELIGIBILITY", "REFER": "REFERRAL", "SURCHARGE_PCT": "PRICING", "CREDIT_PCT": "PRICING"}

    def add_rule(rs, code, name, action, value, cl, desc=None, rule_type=None, severity="INFO", message=None, lob="*", priority=100):
        text = " and ".join(f"{e} {o} {v}" for e, o, v, *_ in cl)
        rules.append((rs, code, name, desc or name + ".", rule_type or rtype.get(action, "ROUTING"), lob, "*", None, "ALL", text, action, value,
                      severity, message or name, priority, None, BASE))
        for i, c in enumerate(cl, 1):
            conds.append((code, i, c[0], c[1], c[2], c[3] if len(c) > 3 else None))

    for code, name, action, value, cl in uw:
        add_rule("UW_PERSONAL_AUTO", code, name, action, value, cl, lob="PA")
        fire, nofire = uw_tests[code]
        tests.append((code, f"{name}: fires", json.dumps(fire), True))
        tests.append((code, f"{name}: does not fire", json.dumps(nofire), False))
    role_rules = [
        ("UW_AUTH_TIV", "Above underwriting authority", "REFER", "Senior underwriter", [("TOTAL_INSURED_VALUE", ">", "2000000")],
         "Submissions above the underwriter's TIV authority go to a senior underwriter (Underwriter boundary)."),
        ("UW_ACCEPT", "Within appetite: accept", "ACCEPT", None, [("RISK_SCORE", "<=", "55")], "SI² recommends accept at or below risk score 55."),
        ("UW_DECLINE", "Outside appetite: decline", "DECLINE", None, [("RISK_SCORE", ">=", "85")], "SI² recommends decline at or above risk score 85."),
        ("UW_REFER_BAND", "Between accept and decline: refer", "REFER", None, [("RISK_SCORE", "BETWEEN", "55.01", "84.99")],
         "Scores between the boundaries are referred for a person to decide."),
        ("CL_RESERVE_AUTH", "Reserve change above authority", "ROUTE", "Claims manager approval", [("RESERVE_CHANGE_AMOUNT", ">", "25000")],
         "A reserve change above the adjuster's authority needs a second person (Claims boundary)."),
        ("ERM_MIN_SOLVENCY", "Solvency below the minimum", "WARN", "Board risk committee", [("SOLVENCY_RATIO", "<", "1.5")],
         "Early warning when the solvency ratio falls below the risk appetite minimum."),
        ("ERM_NET_CAT", "Net catastrophe exposure above appetite", "WARN", "Reinsurance review", [("NET_CAT_1_IN_200", ">", "225000000")],
         "Net 1-in-200 catastrophe loss above 25% of available capital ($900M)."),
    ]
    for code, name, action, value, cl, desc in role_rules:
        add_rule("ROLE_AUTHORITY", code, name, action, value, cl, desc=desc, rule_type="REFERRAL" if action in ("REFER", "ROUTE") else
                 ("ALERT" if action == "WARN" else "ELIGIBILITY"))
    tests += [("UW_AUTH_TIV", "TIV $3M: refer", json.dumps({"TOTAL_INSURED_VALUE": 3000000}), True),
              ("UW_AUTH_TIV", "TIV $1M: within authority", json.dumps({"TOTAL_INSURED_VALUE": 1000000}), False),
              ("CL_RESERVE_AUTH", "Change $40,000: route", json.dumps({"RESERVE_CHANGE_AMOUNT": 40000}), True),
              ("CL_RESERVE_AUTH", "Change $8,000: adjuster decides", json.dumps({"RESERVE_CHANGE_AMOUNT": 8000}), False),
              ("UW_REFER_BAND", "Score 70: refer", json.dumps({"RISK_SCORE": 70}), True),
              ("ERM_MIN_SOLVENCY", "Gross 0.74: warn", json.dumps({"SOLVENCY_RATIO": 0.74}), True)]
    triage = [
        ("CT_SIU", "Fraud score at or above 80", "ROUTE", "SIU", [("FRAUD_SCORE", ">=", "80")], "Claims with a high fraud score go to SIU before payment."),
        ("CT_COMPLEX_ATTY", "Attorney involved", "ROUTE", "Complex", [("ATTORNEY_INDICATOR", "=", "Y")], "Represented claims go to a complex handler."),
        ("CT_COMPLEX_SIZE", "Large expected loss", "ROUTE", "Complex", [("INCURRED_LOSS", ">", "60000")], "Expected ultimate above $60,000."),
        ("CT_FAST", "Small, unrepresented claim", "ROUTE", "Fast track", [("INCURRED_LOSS", "<", "5000"), ("ATTORNEY_INDICATOR", "=", "N")],
         "Small claims without an attorney are paid on the fast track."),
    ]
    for code, name, action, value, cl, desc in triage:
        add_rule("CLAIMS_TRIAGE", code, name, action, value, cl, desc=desc, rule_type="ROUTING")
    tests += [("CT_FAST", "$2,500, no attorney: fast track", json.dumps({"INCURRED_LOSS": 2500, "ATTORNEY_INDICATOR": "N"}), True),
              ("CT_FAST", "$2,500 with attorney: not fast track", json.dumps({"INCURRED_LOSS": 2500, "ATTORNEY_INDICATOR": "Y"}), False),
              ("CT_SIU", "Fraud score 91: SIU", json.dumps({"FRAUD_SCORE": 91}), True)]
    dq = [
        ("DQ_POLICY_NUMBER", "Policy number is required", "REJECT", [("POLICY_NUMBER", "IS NULL", None)], "ERROR"),
        ("DQ_EXP_DATE", "Expiration date is required", "REJECT", [("POLICY_EXPIRATION_DATE", "IS NULL", None)], "ERROR"),
        ("DQ_ZIP", "ZIP code must start with five digits", "REJECT", [("ZIP_CODE", "NOT LIKE", "[0-9][0-9][0-9][0-9][0-9]%")], "ERROR"),
        ("DQ_VIN", "VIN must be 17 characters", "WARN", [("VIN", "NOT LIKE", "_" * 17)], "WARNING"),
        ("DQ_MODEL_YEAR", "Model year before 1981 (pre-VIN standard)", "WARN", [("VEHICLE_MODEL_YEAR", "<", "1981")], "WARNING"),
        ("DQ_NEG_PAID", "Paid loss is negative", "WARN", [("PAID_LOSS", "<", "0")], "WARNING"),
        ("DQ_LOSS_DATE", "Loss date is required", "REJECT", [("LOSS_DATE", "IS NULL", None)], "ERROR"),
    ]
    for code, name, action, cl, sev in dq:
        add_rule("DATA_QUALITY", code, name, action, None, cl, rule_type="VALIDATION", severity=sev)
    tests += [("DQ_ZIP", "ZIP 3021: rejected", json.dumps({"ZIP_CODE": "3021"}), True),
              ("DQ_ZIP", "ZIP 30214: passes", json.dumps({"ZIP_CODE": "30214"}), False),
              ("DQ_VIN", "16-character VIN: warn", json.dumps({"VIN": "1HGCM82633A00435"}), True),
              ("DQ_VIN", "17-character VIN: passes", json.dumps({"VIN": "1HGCM82633A004352"}), False)]
    missing = sorted({c[2] for c in conds} - set(elements))
    assert not missing, f"rule conditions use unknown elements: {missing}"

    w("-- Rules")
    values_insert(out, "INSERT rules.BusinessRule (RuleSetId, RuleCode, Name, Description, RuleType, LobScope, StateScope, TargetElementId, ConditionLogic,\n"
                       "    ConditionText, ActionType, ActionValue, Severity, Message, Priority, ExpressionJson, EffectiveFrom, CreatedBy)\n"
                       f"SELECT rs.RuleSetId, v.c, v.n, v.d, v.t, v.lob, v.st, e.ElementId, v.lg, v.ct, v.a, v.av, v.sev, v.m, v.p, v.x, v.ef, {q(BY)}",
                  ["rs", "c", "n", "d", "t", "lob", "st", "te", "lg", "ct", "a", "av", "sev", "m", "p", "x", "ef"], rules,
                  "JOIN rules.RuleSet rs ON rs.RuleSetCode = v.rs AND rs.ScopeId = 1\n"
                  "LEFT JOIN canon.DataElement e ON e.ElementCode = v.te AND e.ScopeId = 1\n"
                  "WHERE NOT EXISTS (SELECT 1 FROM rules.BusinessRule x WHERE x.RuleCode = v.c AND x.ScopeId = 1)")
    w("-- Rule conditions")
    values_insert(out, f"INSERT rules.RuleCondition (RuleId, Seq, ElementId, Operator, Value1, Value2, CreatedBy)\nSELECT r.RuleId, v.s, e.ElementId, v.o, v.v1, v.v2, {q(BY)}",
                  ["r", "s", "e", "o", "v1", "v2"], conds,
                  "JOIN rules.BusinessRule r ON r.RuleCode = v.r AND r.ScopeId = 1\n"
                  "JOIN canon.DataElement e ON e.ElementCode = v.e AND e.ScopeId = 1\n"
                  "WHERE NOT EXISTS (SELECT 1 FROM rules.RuleCondition x WHERE x.RuleId = r.RuleId AND x.Seq = v.s)")
    w("-- Rule test cases")
    values_insert(out, f"INSERT rules.RuleTestCase (RuleId, Name, InputJson, ExpectedFires, CreatedBy)\nSELECT r.RuleId, v.n, v.j, v.x, {q(BY)}",
                  ["r", "n", "j", "x"], tests,
                  "JOIN rules.BusinessRule r ON r.RuleCode = v.r AND r.ScopeId = 1\n"
                  "WHERE NOT EXISTS (SELECT 1 FROM rules.RuleTestCase x WHERE x.RuleId = r.RuleId AND x.Name = v.n)")

    # ---- source systems and pending changes ---------------------------------------------------------
    w("-- Source systems")
    values_insert(out, f"INSERT intake.SourceSystem (SourceSystemCode, Name, Kind, Notes, CreatedBy)\nSELECT v.c, v.n, v.k, v.d, {q(BY)}",
                  ["c", "n", "k", "d"], [("Guidewire", "Guidewire PolicyCenter / ClaimCenter", "APP", "Source names captured from mapping work."),
                                         ("DuckCreek", "Duck Creek Policy / Claims", "APP", "Source names captured from mapping work."),
                                         ("Legacy", "Legacy mainframe (COBOL copybooks, code tables)", "FILE", None),
                                         ("SI2 Cloud", "SI² cloud canonical model (migration target)", "APP", None),
                                         ("ISO", "ISO statistical plans", "BUREAU", None), ("NCCI", "NCCI / WCIO specifications", "BUREAU", None)],
                  "WHERE NOT EXISTS (SELECT 1 FROM intake.SourceSystem x WHERE x.SourceSystemCode = v.c)")
    w("-- Pending changes waiting for a second person (the effective-dated ISO changes)")
    for ot, ct, oc, summary, payload in pending:
        w(f"IF NOT EXISTS (SELECT 1 FROM gov.ChangeRequest WHERE ObjectType = {q(ot)} AND ChangeType = {q(ct)} AND ObjectCode = {q(oc)})\n"
          f"    INSERT gov.ChangeRequest (ObjectType, ChangeType, ObjectCode, Summary, PayloadJson, Source, RequestedBy)\n"
          f"    VALUES ({q(ot)}, {q(ct)}, {q(oc)}, {q(summary)}, {q(json.dumps(payload))}, 'SEED', {q(BY)});")
    w("GO\nSELECT * FROM canon.vw_Summary;\nGO\n")

    stats = {"subject areas": len(SUBJECTS), "pick lists": len(picklists), "options": len(opts), "bureau codes": len(brows),
             "elements": len(elements), "synonyms": len(srows), "where-used": len(urows), "rules": len(rules), "conditions": len(conds),
             "tests": len(tests), "pending": len(pending), "unmatched code-table values": len(unmatched)}
    print(stats)
    for u in unmatched:
        print("  unmatched:", u)
    return "\n".join(out)


if __name__ == "__main__":
    (HERE / "03_seed.sql").write_text(build(), encoding="utf-8")
    print("wrote", HERE / "03_seed.sql")
