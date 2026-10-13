"""SI² rule library: roles, companies, products, templates, rules, decision tables and authority for every major line.

    python sql/si2_canonical/rule_library.py      writes 07_rule_library.sql (idempotent: only what is missing is added)

Everything here is synthetic and illustrative: two synthetic companies (SI² Mutual for personal lines and small
commercial in the Southeast, SI² Specialty for commercial and E&S countrywide). Regulated values (notice days,
monopolistic states, credit-score restrictions) are marked illustrative and must be confirmed by compliance.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from rule_engine import Rule, generate_tests  # noqa: E402

BY = "SI2 library"
SE = ["FL", "GA", "AL", "SC", "NC", "TX"]          # SI² Mutual footprint

ROLES = [  # code, name, department, description
    ("CEO", "Chief Executive Officer", "Executive", "Company results, appetite and guardrails."),
    ("CFO", "Chief Financial Officer", "Executive", "Profitability, expenses, capital and reserves."),
    ("CUO", "Chief Underwriting Officer", "Underwriting", "Underwriting appetite, authority and rate adequacy."),
    ("UNDERWRITER", "Underwriter", "Underwriting", "Eligibility, referral and pricing decisions on individual risks."),
    ("SR_UNDERWRITER", "Senior Underwriter", "Underwriting", "Referrals above an underwriter's authority."),
    ("PRICING", "Pricing Actuary", "Actuarial", "Rating factors, credits, surcharges and rate changes."),
    ("PRODUCT", "Product Manager", "Product", "Products, coverages, forms and availability by state."),
    ("COMPLIANCE", "Compliance Officer", "Legal & Compliance", "State requirements, notices and prohibited practices."),
    ("BILLING", "Billing Specialist", "Operations", "Payment plans, past-due handling and cancellations for non-payment."),
    ("CLAIMS_ADJUSTER", "Claims Adjuster", "Claims", "Triage, coverage, reserves and payments within authority."),
    ("CLAIMS_MANAGER", "Claims Manager", "Claims", "Large losses, litigation and approvals above adjuster authority."),
    ("SIU", "SIU Investigator", "Claims", "Suspected fraud referrals and investigations."),
    ("DISTRIBUTION", "Distribution Manager", "Distribution", "Producer eligibility, appointments and commissions."),
    ("REINSURANCE", "Reinsurance Manager", "Finance", "Facultative referrals and treaty limits."),
    ("ERM", "Chief Risk Officer", "Risk", "Capital, catastrophe exposure and solvency."),
    ("DATA_STEWARD", "Data Steward", "Data", "Data quality checks on every load."),
]

COMPANIES = [("SIM", "SI² Mutual Insurance Company (synthetic)", "Personal lines and small commercial in the Southeast.", "99901"),
             ("SIS", "SI² Specialty Insurance Company (synthetic)", "Commercial lines and E&S, countrywide.", "99902")]

PRODUCTS = [  # code, line, name, company, states
    ("PA_STD", "PA", "Personal Auto - Standard", "SIM", SE), ("HO3", "HO", "Homeowners Special Form (HO-3)", "SIM", SE),
    ("HO5", "HO", "Homeowners Comprehensive (HO-5)", "SIM", SE), ("HO4", "HO", "Renters (HO-4)", "SIM", SE),
    ("HO6", "HO", "Condominium Unit Owners (HO-6)", "SIM", SE), ("DP3", "HO", "Dwelling Fire Special (DP-3)", "SIM", SE),
    ("PUP", "UMB", "Personal Umbrella", "SIM", SE), ("BOP", "BP", "Businessowners", "SIM", SE),
    ("BA", "CA", "Business Auto", "SIS", []), ("CP", "CP", "Commercial Property", "SIS", []), ("CGL", "GL", "Commercial General Liability", "SIS", []),
    ("WC", "WC", "Workers Compensation", "SIS", []), ("CUMB", "UMB", "Commercial Umbrella", "SIS", []), ("CYB", "CYB", "Cyber Liability", "SIS", []),
]

# Templates: the questions SI² asks. Every template also asks where (company, line, product, state) and from when.
Q_WHEN = {"name": "conditions", "kind": "CONDITIONS", "question": "When should this happen? Describe the risk, e.g. 'roof older than 20 years'."}
Q_WHERE = {"name": "applies_to", "kind": "SCOPE", "question": "Where does it apply? Company, line, product and states (leave empty for everywhere)."}
Q_FROM = {"name": "effective_from", "kind": "DATE", "question": "From which date?"}


def q(name, kind, question, **kw):
    return {"name": name, "kind": kind, "question": question, **kw}


TEMPLATES = [  # code, name, role, phase, rule type, action, sentence, questions, example
    ("UW_DECLINE", "Decline a risk", "UNDERWRITER", "ELIGIBILITY", "ELIGIBILITY", "DECLINE", "Decline when {conditions}",
     [Q_WHEN, q("message", "TEXT", "What reason should the agent see?"), Q_WHERE, Q_FROM], "Decline homes with a roof older than 25 years"),
    ("UW_REFER", "Refer a risk", "UNDERWRITER", "REFERRAL", "REFERRAL", "REFER", "Refer to {action_value} when {conditions}",
     [Q_WHEN, q("action_value", "CHOICE", "Who should review it?", choices=["Underwriter", "Senior Underwriter", "CUO", "Reinsurance"]), Q_WHERE, Q_FROM],
     "Refer coastal homes within 1 mile of the coast to a senior underwriter"),
    ("UW_AUTHORITY", "Underwriting authority", "CUO", "AUTHORITY", "AUTHORITY", "APPROVE_BY", "Needs approval by {action_value} when {conditions}",
     [q("conditions", "CONDITIONS", "Above what amount? e.g. 'total insured value above 5,000,000'"),
      q("action_value", "CHOICE", "Who approves above it?", choices=["Senior Underwriter", "CUO", "CEO"]), Q_WHERE, Q_FROM],
     "TIV above 25 million needs CUO approval"),
    ("RATE_SURCHARGE", "Surcharge", "PRICING", "RATING", "PRICING", "SURCHARGE_PCT", "Surcharge {action_value}% when {conditions}",
     [Q_WHEN, q("action_value", "PERCENT", "How much, in percent?"), Q_WHERE, Q_FROM], "Surcharge 10% when there are 2 or more prior claims"),
    ("RATE_CREDIT", "Credit / discount", "PRICING", "RATING", "PRICING", "CREDIT_PCT", "Credit {action_value}% when {conditions}",
     [Q_WHEN, q("action_value", "PERCENT", "How much, in percent?"), Q_WHERE, Q_FROM], "Credit 5% for a central-station alarm"),
    ("RATE_CHANGE_CAP", "Rate change guardrail", "CUO", "AUTHORITY", "AUTHORITY", "APPROVE_BY", "Rate changes above the cap need {action_value}",
     [q("conditions", "CONDITIONS", "What is the cap? e.g. 'rate change above 15%'"), q("action_value", "CHOICE", "Who approves?", choices=["CUO", "CEO"]),
      Q_WHERE, Q_FROM], "Rate changes above 15% need CUO approval"),
    ("FORM_ATTACH", "Attach a form", "PRODUCT", "FORMS", "FORMS", "ATTACH_FORM", "Attach {action_value} when {conditions}",
     [q("action_value", "TEXT", "Which form (number and title)?"), Q_WHEN, Q_WHERE, Q_FROM], "Attach the windstorm percentage deductible form near the coast"),
    ("COMP_PROHIBIT", "Prohibited practice", "COMPLIANCE", "COMPLIANCE", "COMPLIANCE", "REJECT", "Not allowed: {message} when {conditions}",
     [Q_WHEN, q("message", "TEXT", "What is not allowed and why?"), Q_WHERE, Q_FROM], "Credit-based insurance scores may not be used in CA, HI and MA auto"),
    ("COMP_NOTICE", "Notice requirement", "COMPLIANCE", "COMPLIANCE", "COMPLIANCE", "REJECT", "Reject the notice when {conditions}",
     [Q_WHEN, q("message", "TEXT", "What does the rule protect?"), Q_WHERE, Q_FROM], "Non-payment notice must give at least 10 days"),
    ("BILL_ACTION", "Billing action", "BILLING", "BILLING", "BILLING", "ROUTE", "Route to {action_value} when {conditions}",
     [Q_WHEN, q("action_value", "CHOICE", "What should happen?", choices=["Notice of cancellation", "Collections", "Payment reminder", "Billing review"]),
      Q_WHERE, Q_FROM], "Send a notice of cancellation when 10 days past due"),
    ("CLAIM_ROUTE", "Route a claim", "CLAIMS_ADJUSTER", "ROUTING", "ROUTING", "ROUTE", "Route the claim to {action_value} when {conditions}",
     [Q_WHEN, q("action_value", "CHOICE", "Where should it go?", choices=["Fast track", "Standard", "Complex", "SIU", "CAT team", "Litigation unit"]),
      Q_WHERE, Q_FROM], "Route claims with an attorney to the complex unit"),
    ("CLAIM_AUTHORITY", "Claims authority", "CLAIMS_MANAGER", "AUTHORITY", "AUTHORITY", "APPROVE_BY", "Needs approval by {action_value} when {conditions}",
     [q("conditions", "CONDITIONS", "Above what amount? e.g. 'payment above 25,000'"),
      q("action_value", "CHOICE", "Who approves?", choices=["Claims Manager", "Claims VP", "CFO"]), Q_WHERE, Q_FROM], "Payments above 25,000 need a claims manager"),
    ("SIU_REFER", "Refer to SIU", "SIU", "ROUTING", "ROUTING", "ROUTE", "Refer to SIU when {conditions}",
     [Q_WHEN, Q_WHERE, Q_FROM], "Refer to SIU when the claim is reported more than 30 days late"),
    ("DIST_ELIGIBILITY", "Producer eligibility", "DISTRIBUTION", "ELIGIBILITY", "ELIGIBILITY", "DECLINE", "Decline the submission when {conditions}",
     [Q_WHEN, q("message", "TEXT", "What should the agent see?"), Q_WHERE, Q_FROM], "Decline when the agent is not licensed in the state"),
    ("REIN_FAC", "Facultative referral", "REINSURANCE", "REFERRAL", "REFERRAL", "REFER", "Refer to reinsurance when {conditions}",
     [Q_WHEN, Q_WHERE, Q_FROM], "Refer to reinsurance for facultative when TIV above 50 million"),
    ("EXEC_ALERT", "Executive guardrail", "CEO", "ALERT", "ALERT", "ALERT", "Alert {action_value} when {conditions}",
     [q("conditions", "CONDITIONS", "Which measure and threshold? e.g. 'loss ratio above 0.70'"),
      q("action_value", "CHOICE", "Who should be alerted?", choices=["CEO", "CFO", "CUO", "Chief Risk Officer", "Board"]), Q_WHERE, Q_FROM],
     "Alert the CEO when the homeowners loss ratio passes 70%"),
    ("DQ_REQUIRED", "Required data", "DATA_STEWARD", "DATA", "VALIDATION", "REJECT", "Reject the record when {conditions}",
     [Q_WHEN, q("message", "TEXT", "What should the error say?"), Q_WHERE, Q_FROM], "Reject when the policy number is missing"),
    ("DQ_WARN", "Data warning", "DATA_STEWARD", "DATA", "VALIDATION", "WARN", "Warn when {conditions}",
     [Q_WHEN, q("message", "TEXT", "What should the warning say?"), Q_WHERE, Q_FROM], "Warn when the model year is before 1981"),
]

RULESETS = [  # code, name, purpose, description
    ("UW_ELIGIBILITY", "Underwriting eligibility", "UNDERWRITING", "Declines by line, product and state."),
    ("UW_REFERRAL", "Underwriting referrals", "UNDERWRITING", "Referrals to senior underwriters, the CUO and reinsurance."),
    ("UW_AUTHORITY", "Underwriting authority", "UNDERWRITING", "Approvals above each role's authority."),
    ("RATING_ADJUSTMENTS", "Rating credits and surcharges", "RATING", "Schedule credits and surcharges."),
    ("FORMS", "Forms and endorsements", "PRODUCT", "Forms attached by line, product and state."),
    ("COMPLIANCE_STATE", "State compliance", "COMPLIANCE", "Prohibited practices and notice requirements (illustrative)."),
    ("BILLING", "Billing", "BILLING", "Past-due handling and cancellation for non-payment."),
    ("CLAIMS_ROUTING", "Claims routing", "CLAIMS", "Triage and routing of claims."),
    ("CLAIMS_AUTHORITY", "Claims authority", "CLAIMS", "Reserve and payment approvals."),
    ("SIU_REFERRALS", "SIU referrals", "FRAUD", "Suspected fraud indicators."),
    ("DISTRIBUTION", "Distribution", "DISTRIBUTION", "Producer eligibility."),
    ("REINSURANCE", "Reinsurance", "REINSURANCE", "Facultative referrals."),
    ("EXECUTIVE_GUARDRAILS", "Executive guardrails", "EXECUTIVE", "Alerts on results, growth, retention and capital."),
]


def R(code, name, template, action, conds, scope=None, value=None, okey=None, logic="ALL", ruleset=None, message=None, severity=None, eff="2026-01-01"):
    t = next(t for t in TEMPLATES if t[0] == template)
    return Rule(code=code, name=name, action=action, conditions=[tuple(c) + (None,) * (4 - len(c)) for c in conds], phase=t[3], logic=logic,
                action_value=None if value is None else str(value), scope={k: list(v) for k, v in (scope or {}).items()}, override_key=okey,
                role=t[2], template=template, ruleset=ruleset, severity=severity or ("ERROR" if action in ("DECLINE", "REJECT") else "INFO"),
                message=message or name, effective_from=eff)


HO = {"COMPANY": ["SIM"], "LOB": ["HO"]}
PA = {"COMPANY": ["SIM"], "LOB": ["PA"]}
RULES = [
    # ---------------- Homeowners (SI² Mutual) ----------------
    R("HO-E01", "Roof older than 25 years", "UW_DECLINE", "DECLINE", [("ROOF_AGE", ">", "25")], HO, okey="HO_ROOF_AGE_LIMIT", ruleset="UW_ELIGIBILITY"),
    R("HO-E01-FL", "Roof older than 15 years (Florida)", "UW_DECLINE", "DECLINE", [("ROOF_AGE", ">", "15")], {**HO, "STATE": ["FL"]},
      okey="HO_ROOF_AGE_LIMIT", ruleset="UW_ELIGIBILITY", message="Florida: roof older than 15 years is outside appetite"),
    R("HO-E02", "Vacant or unoccupied dwelling", "UW_DECLINE", "DECLINE", [("OCCUPANCY", "IN", "VACANT,UNOCCUPIED")], HO, ruleset="UW_ELIGIBILITY"),
    R("HO-E03", "Tenant-occupied home on an HO-3", "UW_DECLINE", "DECLINE", [("OCCUPANCY", "=", "TENANT")], {**HO, "PRODUCT": ["HO3", "HO5"]},
      ruleset="UW_ELIGIBILITY", message="Tenant-occupied dwellings belong on a DP-3"),
    R("HO-E04", "Protection class 10", "UW_DECLINE", "DECLINE", [("PROTECTION_CLASS", "=", "10")], HO, ruleset="UW_ELIGIBILITY"),
    R("HO-E05", "Coastal high-hazard flood zone", "UW_DECLINE", "DECLINE", [("FLOOD_ZONE", "IN", "V,VE")], {**HO, "PRODUCT": ["HO3", "HO5", "DP3"]},
      ruleset="UW_ELIGIBILITY"),
    R("HO-R01", "Within 1 mile of the coast", "UW_REFER", "REFER", [("DISTANCE_TO_COAST", "<", "1")], HO, "Senior Underwriter", ruleset="UW_REFERRAL"),
    R("HO-R02", "Home built before 1950", "UW_REFER", "REFER", [("YEAR_BUILT", "<", "1950")], HO, "Underwriter", ruleset="UW_REFERRAL"),
    R("HO-R03", "Coverage A above 1,000,000", "UW_AUTHORITY", "APPROVE_BY", [("COVERAGE_A_LIMIT", ">", "1000000")], HO, "Senior Underwriter",
      okey="HO_COV_A_AUTHORITY", ruleset="UW_AUTHORITY"),
    R("HO-R04", "High wildfire score", "UW_REFER", "REFER", [("WILDFIRE_SCORE", ">", "80")], {**HO, "STATE": ["TX"]}, "Senior Underwriter",
      ruleset="UW_REFERRAL"),
    R("HO-P01", "Wind mitigation credit", "RATE_CREDIT", "CREDIT_PCT", [("WIND_MITIGATION", "IN", "HURRICANE_STRAPS,SHUTTERS,FORTIFIED")],
      {**HO, "STATE": ["FL", "AL", "SC", "NC", "TX"]}, 10, ruleset="RATING_ADJUSTMENTS"),
    R("HO-P02", "Central-station alarm credit", "RATE_CREDIT", "CREDIT_PCT", [("ALARM_TYPE", "IN", "CENTRAL,POLICE_FIRE")], HO, 5, ruleset="RATING_ADJUSTMENTS"),
    R("HO-P03", "Older roof surcharge", "RATE_SURCHARGE", "SURCHARGE_PCT", [("ROOF_AGE", "BETWEEN", "15", "25")], HO, 10, ruleset="RATING_ADJUSTMENTS"),
    R("HO-P04", "Prior claims surcharge", "RATE_SURCHARGE", "SURCHARGE_PCT", [("PRIOR_CLAIMS", ">=", "2")], HO, 15, ruleset="RATING_ADJUSTMENTS"),
    R("HO-F01", "Windstorm percentage deductible near the coast", "FORM_ATTACH", "ATTACH_FORM", [("DISTANCE_TO_COAST", "<", "5")],
      {**HO, "STATE": ["FL", "AL", "SC", "NC", "TX"]}, "HO 03 12 Windstorm or Hail Percentage Deductible", ruleset="FORMS"),
    R("HO-F02", "Sinkhole loss coverage offer (Florida)", "FORM_ATTACH", "ATTACH_FORM", [("STATE", "=", "FL")], {**HO, "STATE": ["FL"]},
      "HO 23 FL Sinkhole Loss Coverage - Florida", ruleset="FORMS"),
    R("HO-F03", "Scheduled personal property", "FORM_ATTACH", "ATTACH_FORM", [("COVERAGE_C_LIMIT", ">", "250000")], HO,
      "HO 04 61 Scheduled Personal Property Endorsement", ruleset="FORMS"),
    # ---------------- Personal auto (SI² Mutual) ----------------
    R("PA-E01", "Driver with a suspended or revoked license", "UW_DECLINE", "DECLINE", [("LICENSE_STATUS", "IN", "SUSPENDED,REVOKED,EXPIRED")], PA,
      ruleset="UW_ELIGIBILITY"),
    R("PA-E02", "DUI violation", "UW_DECLINE", "DECLINE", [("VIOLATION_TYPE", "=", "DUI")], PA, ruleset="UW_ELIGIBILITY"),
    R("PA-R01", "High-value vehicle", "UW_REFER", "REFER", [("VEHICLE_VALUE", ">", "100000")], PA, "Senior Underwriter", ruleset="UW_REFERRAL"),
    R("PA-P01", "Good student credit", "RATE_CREDIT", "CREDIT_PCT", [("GOOD_STUDENT_IND", "=", "Y"), ("DRIVER_AGE", "<", "25")], PA, 10,
      ruleset="RATING_ADJUSTMENTS"),
    R("PA-P02", "Anti-theft credit", "RATE_CREDIT", "CREDIT_PCT", [("ANTI_THEFT", "IN", "ACTIVE,TRACKING")], PA, 5, ruleset="RATING_ADJUSTMENTS"),
    R("PA-P03", "Rideshare surcharge", "RATE_SURCHARGE", "SURCHARGE_PCT", [("VEHICLE_USE", "=", "RIDESHARE")], {**PA, "STATE": ["FL", "TX", "GA"]}, 20,
      ruleset="RATING_ADJUSTMENTS"),
    R("PA-F01", "Florida PIP notice", "FORM_ATTACH", "ATTACH_FORM", [("STATE", "=", "FL")], {**PA, "STATE": ["FL"]},
      "PP FL PIP Personal Injury Protection Notice", ruleset="FORMS"),
    # ---------------- Personal umbrella ----------------
    R("UMB-E01", "Underlying liability below 250,000", "UW_DECLINE", "DECLINE", [("UNDERLYING_LIABILITY_LIMIT", "<", "250000")],
      {"COMPANY": ["SIM"], "LOB": ["UMB"], "PRODUCT": ["PUP"]}, ruleset="UW_ELIGIBILITY", message="Underlying auto and home liability must be at least 250,000"),
    R("UMB-R01", "Young driver in the household", "UW_REFER", "REFER", [("DRIVER_AGE", "<", "21")], {"LOB": ["UMB"], "PRODUCT": ["PUP"]}, "Underwriter",
      ruleset="UW_REFERRAL"),
    # ---------------- Businessowners ----------------
    R("BOP-E01", "Revenue too large for a BOP", "UW_DECLINE", "DECLINE", [("ANNUAL_REVENUE", ">", "5000000")], {"LOB": ["BP"], "PRODUCT": ["BOP"]},
      ruleset="UW_ELIGIBILITY", message="Above 5 million revenue: write on a commercial package"),
    R("BOP-E02", "Building too large for a BOP", "UW_DECLINE", "DECLINE", [("SQUARE_FEET", ">", "35000")], {"LOB": ["BP"], "PRODUCT": ["BOP"]},
      ruleset="UW_ELIGIBILITY"),
    R("BOP-E03", "Ineligible industry for a BOP", "UW_DECLINE", "DECLINE", [("NAICS_SECTOR", "IN", "21,22,23")], {"LOB": ["BP"]}, ruleset="UW_ELIGIBILITY",
      message="Mining, utilities and construction are not eligible for a BOP"),
    # ---------------- Commercial property (SI² Specialty) ----------------
    R("CP-E01", "Large frame building", "UW_DECLINE", "DECLINE", [("CONSTRUCTION", "=", "FR"), ("TOTAL_INSURED_VALUE", ">", "10000000")],
      {"COMPANY": ["SIS"], "LOB": ["CP"]}, ruleset="UW_ELIGIBILITY"),
    R("CP-R01", "Unsprinklered large building", "UW_REFER", "REFER", [("SPRINKLER_TYPE", "=", "NONE"), ("SQUARE_FEET", ">", "50000")],
      {"LOB": ["CP"]}, "Senior Underwriter", ruleset="UW_REFERRAL"),
    R("CP-R02", "Poor fire protection", "UW_REFER", "REFER", [("PROTECTION_CLASS", "IN", "09,10")], {"LOB": ["CP"]}, "Underwriter", ruleset="UW_REFERRAL"),
    R("CP-R03", "Special flood hazard area", "UW_REFER", "REFER", [("FLOOD_ZONE", "IN", "A,AE,AH,AO,V,VE")], {"LOB": ["CP"]}, "Senior Underwriter",
      ruleset="UW_REFERRAL"),
    R("CP-A01", "TIV above underwriter authority", "UW_AUTHORITY", "APPROVE_BY", [("TOTAL_INSURED_VALUE", ">", "25000000")], {"LOB": ["CP"]}, "CUO",
      okey="CP_TIV_AUTHORITY", ruleset="UW_AUTHORITY"),
    R("CP-P01", "Sprinkler credit", "RATE_CREDIT", "CREDIT_PCT", [("SPRINKLER_TYPE", "IN", "FULL,DRY,ESFR")], {"LOB": ["CP"]}, 15, ruleset="RATING_ADJUSTMENTS"),
    R("RE-F01", "Facultative reinsurance", "REIN_FAC", "REFER", [("TOTAL_INSURED_VALUE", ">", "50000000")], {"LOB": ["CP"]}, "Reinsurance",
      ruleset="REINSURANCE"),
    # ---------------- General liability ----------------
    R("GL-E01", "Mining operations", "UW_DECLINE", "DECLINE", [("NAICS_SECTOR", "=", "21")], {"LOB": ["GL"]}, ruleset="UW_ELIGIBILITY"),
    R("GL-R01", "Revenue above 50 million", "UW_REFER", "REFER", [("ANNUAL_REVENUE", ">", "50000000")], {"LOB": ["GL"]}, "Senior Underwriter",
      ruleset="UW_REFERRAL"),
    R("GL-R02", "New venture", "UW_REFER", "REFER", [("YEARS_IN_BUSINESS", "<", "3")], {"LOB": ["GL"]}, "Underwriter", ruleset="UW_REFERRAL"),
    R("GL-P01", "Loss history surcharge", "RATE_SURCHARGE", "SURCHARGE_PCT", [("PRIOR_CLAIMS", ">=", "2")], {"LOB": ["GL"]}, 10, ruleset="RATING_ADJUSTMENTS"),
    # ---------------- Commercial auto ----------------
    R("CA-R01", "Heavy trucks and tractors", "UW_REFER", "REFER", [("VEHICLE_TYPE", "IN", "HEAVY_TRUCK,TRACTOR")], {"LOB": ["CA"]}, "Senior Underwriter",
      ruleset="UW_REFERRAL"),
    R("CA-R02", "Large fleet", "UW_REFER", "REFER", [("NUMBER_OF_VEHICLES", ">", "50")], {"LOB": ["CA"]}, "Senior Underwriter", ruleset="UW_REFERRAL"),
    R("CA-R03", "Young commercial driver", "UW_REFER", "REFER", [("DRIVER_AGE", "<", "23")], {"LOB": ["CA"]}, "Underwriter", ruleset="UW_REFERRAL"),
    R("CA-P01", "Driver record surcharge", "RATE_SURCHARGE", "SURCHARGE_PCT", [("VIOLATIONS", ">=", "3")], {"LOB": ["CA"]}, 15, ruleset="RATING_ADJUSTMENTS"),
    # ---------------- Workers compensation ----------------
    R("WC-E01", "Monopolistic state fund state", "COMP_PROHIBIT", "REJECT", [("STATE", "IN", "ND,OH,WA,WY")], {"LOB": ["WC"]}, ruleset="COMPLIANCE_STATE",
      message="Workers compensation in ND, OH, WA and WY is written by the state fund (illustrative; confirm)"),
    R("WC-R01", "Experience mod above 1.25", "UW_REFER", "REFER", [("EXPERIENCE_MODIFICATION_FACTOR", ">", "1.25")], {"LOB": ["WC"]}, "Senior Underwriter",
      ruleset="UW_REFERRAL"),
    R("WC-R02", "Payroll above 10 million", "UW_REFER", "REFER", [("ANNUAL_PAYROLL", ">", "10000000")], {"LOB": ["WC"]}, "Senior Underwriter",
      ruleset="UW_REFERRAL"),
    # ---------------- Cyber ----------------
    R("CY-E01", "No multi-factor authentication", "UW_DECLINE", "DECLINE", [("MFA_IND", "=", "N")], {"LOB": ["CYB"]}, ruleset="UW_ELIGIBILITY",
      message="Multi-factor authentication is required"),
    R("CY-R01", "More than 1 million records", "UW_REFER", "REFER", [("RECORDS_HELD", ">", "1000000")], {"LOB": ["CYB"]}, "Senior Underwriter",
      ruleset="UW_REFERRAL"),
    R("CY-P01", "No endpoint detection surcharge", "RATE_SURCHARGE", "SURCHARGE_PCT", [("EDR_IND", "=", "N")], {"LOB": ["CYB"]}, 20,
      ruleset="RATING_ADJUSTMENTS"),
    R("CY-P02", "No offline backups surcharge", "RATE_SURCHARGE", "SURCHARGE_PCT", [("BACKUP_OFFLINE_IND", "=", "N")], {"LOB": ["CYB"]}, 15,
      ruleset="RATING_ADJUSTMENTS"),
    # ---------------- Pricing guardrails ----------------
    R("PR-A01", "Rate change above 15%", "RATE_CHANGE_CAP", "APPROVE_BY", [("RATE_CHANGE_PCT", ">", "15")], None, "CUO", okey="RATE_CHANGE_CAP",
      ruleset="UW_AUTHORITY"),
    R("PR-A02", "Rate change above 25%", "RATE_CHANGE_CAP", "APPROVE_BY", [("RATE_CHANGE_PCT", ">", "25")], None, "CEO", ruleset="UW_AUTHORITY"),
    # ---------------- Compliance (illustrative; confirm with compliance) ----------------
    R("CO-01", "Credit-based insurance score in auto", "COMP_PROHIBIT", "REJECT", [("INSURANCE_SCORE_IND", "=", "Y")],
      {"LOB": ["PA"], "STATE": ["CA", "HI", "MA"]}, ruleset="COMPLIANCE_STATE",
      message="Credit-based insurance scores may not be used for auto in CA, HI and MA (illustrative; confirm)"),
    R("CO-02", "Non-payment notice shorter than 10 days", "COMP_NOTICE", "REJECT", [("CANCEL_REASON", "=", "NONPAY"), ("NOTICE_DAYS_GIVEN", "<", "10")],
      None, ruleset="COMPLIANCE_STATE", message="Notice of cancellation for non-payment must give at least the state minimum (see CANCEL_NOTICE_DAYS)"),
    # ---------------- Billing ----------------
    R("BI-01", "Ten days past due", "BILL_ACTION", "ROUTE", [("DAYS_PAST_DUE", ">=", "10")], None, "Notice of cancellation", ruleset="BILLING"),
    R("BI-02", "Large balance long past due", "BILL_ACTION", "ROUTE", [("DAYS_PAST_DUE", ">", "30"), ("ACCOUNT_BALANCE", ">", "500")], None, "Collections",
      ruleset="BILLING"),
    # ---------------- Claims ----------------
    R("CL-01", "Litigated claim", "CLAIM_ROUTE", "ROUTE", [("LITIGATION_IND", "=", "Y")], None, "Litigation unit", ruleset="CLAIMS_ROUTING"),
    R("CL-02", "Catastrophe claim", "CLAIM_ROUTE", "ROUTE", [("CATASTROPHE_IND", "=", "Y")], None, "CAT team", ruleset="CLAIMS_ROUTING"),
    R("CL-03", "Small property claim", "CLAIM_ROUTE", "ROUTE", [("INCURRED_LOSS", "<", "2500"), ("ATTORNEY_INDICATOR", "=", "N")], {"LOB": ["HO", "CP", "BP"]},
      "Fast track", ruleset="CLAIMS_ROUTING"),
    R("CL-04", "Payment above adjuster authority", "CLAIM_AUTHORITY", "APPROVE_BY", [("CLAIM_PAYMENT_AMOUNT", ">", "25000")], None, "Claims Manager",
      okey="CLAIM_PAYMENT_AUTHORITY", ruleset="CLAIMS_AUTHORITY"),
    R("CL-05", "Payment above manager authority", "CLAIM_AUTHORITY", "APPROVE_BY", [("CLAIM_PAYMENT_AMOUNT", ">", "250000")], None, "Claims VP",
      ruleset="CLAIMS_AUTHORITY"),
    R("SIU-01", "Reported more than 30 days late", "SIU_REFER", "ROUTE", [("DAYS_TO_REPORT", ">", "30")], None, "SIU", ruleset="SIU_REFERRALS"),
    R("SIU-02", "Frequent claimant reporting late", "SIU_REFER", "ROUTE", [("PRIOR_CLAIMS", ">=", "3"), ("DAYS_TO_REPORT", ">", "14")], None, "SIU",
      ruleset="SIU_REFERRALS"),
    # ---------------- Distribution ----------------
    R("DI-01", "Producer not licensed in the state", "DIST_ELIGIBILITY", "DECLINE", [("PRODUCER_LICENSED_IND", "=", "N")], None, ruleset="DISTRIBUTION",
      message="The producer must be licensed and appointed in the risk state"),
    # ---------------- Executive guardrails ----------------
    R("EX-01", "Homeowners loss ratio above 70%", "EXEC_ALERT", "ALERT", [("LOSS_RATIO", ">", "0.70")], {"LOB": ["HO"]}, "CEO", ruleset="EXECUTIVE_GUARDRAILS"),
    R("EX-02", "Combined ratio above 100%", "EXEC_ALERT", "ALERT", [("COMBINED_RATIO", ">", "1.00")], None, "CFO", ruleset="EXECUTIVE_GUARDRAILS"),
    R("EX-03", "Premium growth above 25%", "EXEC_ALERT", "ALERT", [("PREMIUM_GROWTH_PCT", ">", "25")], None, "CUO", ruleset="EXECUTIVE_GUARDRAILS",
      message="Fast growth: check rate adequacy and underwriting discipline"),
    R("EX-04", "Premium shrinking more than 10%", "EXEC_ALERT", "ALERT", [("PREMIUM_GROWTH_PCT", "<", "-10")], None, "CEO", ruleset="EXECUTIVE_GUARDRAILS"),
    R("EX-05", "Retention below 80%", "EXEC_ALERT", "ALERT", [("RETENTION_RATE", "<", "0.80")], None, "CEO", ruleset="EXECUTIVE_GUARDRAILS"),
    R("EX-06", "Expense ratio above 35%", "EXEC_ALERT", "ALERT", [("EXPENSE_RATIO", ">", "0.35")], None, "CFO", ruleset="EXECUTIVE_GUARDRAILS"),
]

TABLES = [
    {"code": "CANCEL_NOTICE_DAYS", "name": "Cancellation notice days by state and reason", "role": "COMPLIANCE", "illustrative": True,
     "description": "Minimum days of notice before a cancellation takes effect. Illustrative values: confirm each state with compliance.",
     "inputs": ["STATE", "CANCEL_REASON"], "outputs": ["NOTICE_DAYS"],
     "rows": [({"STATE": "*", "CANCEL_REASON": "NONPAY"}, {"NOTICE_DAYS": 10}), ({"STATE": "*", "CANCEL_REASON": "UW"}, {"NOTICE_DAYS": 30}),
              ({"STATE": "*", "CANCEL_REASON": "FRAUD"}, {"NOTICE_DAYS": 10}), ({"STATE": "FL", "CANCEL_REASON": "UW"}, {"NOTICE_DAYS": 45}),
              ({"STATE": "TX", "CANCEL_REASON": "UW"}, {"NOTICE_DAYS": 30}), ({"STATE": "NC", "CANCEL_REASON": "NONPAY"}, {"NOTICE_DAYS": 15}),
              ({"STATE": "SC", "CANCEL_REASON": "NONPAY"}, {"NOTICE_DAYS": 10}), ({"STATE": "GA", "CANCEL_REASON": "UW"}, {"NOTICE_DAYS": 45})]},
    {"code": "MIN_PREMIUM", "name": "Minimum premium by line and product", "role": "PRICING", "illustrative": True,
     "description": "The lowest premium written for a policy term.", "inputs": ["LOB", "PRODUCT"], "outputs": ["MIN_PREMIUM"],
     "rows": [({"LOB": "HO", "PRODUCT": "*"}, {"MIN_PREMIUM": 300}), ({"LOB": "HO", "PRODUCT": "HO4"}, {"MIN_PREMIUM": 100}),
              ({"LOB": "HO", "PRODUCT": "HO6"}, {"MIN_PREMIUM": 150}), ({"LOB": "PA", "PRODUCT": "*"}, {"MIN_PREMIUM": 250}),
              ({"LOB": "BP", "PRODUCT": "*"}, {"MIN_PREMIUM": 500}), ({"LOB": "CP", "PRODUCT": "*"}, {"MIN_PREMIUM": 1000}),
              ({"LOB": "GL", "PRODUCT": "*"}, {"MIN_PREMIUM": 750}), ({"LOB": "CA", "PRODUCT": "*"}, {"MIN_PREMIUM": 1500}),
              ({"LOB": "WC", "PRODUCT": "*"}, {"MIN_PREMIUM": 750}), ({"LOB": "UMB", "PRODUCT": "*"}, {"MIN_PREMIUM": 250}),
              ({"LOB": "CYB", "PRODUCT": "*"}, {"MIN_PREMIUM": 1000})]},
    {"code": "COMMISSION_RATE", "name": "Agent commission by line and transaction", "role": "DISTRIBUTION", "illustrative": True,
     "description": "Commission paid to the producer as a share of premium.", "inputs": ["LOB", "TRANSACTION_TYPE"], "outputs": ["COMMISSION_RATE"],
     "rows": [({"LOB": "*", "TRANSACTION_TYPE": "NB"}, {"COMMISSION_RATE": 0.15}), ({"LOB": "*", "TRANSACTION_TYPE": "RN"}, {"COMMISSION_RATE": 0.12}),
              ({"LOB": "PA", "TRANSACTION_TYPE": "NB"}, {"COMMISSION_RATE": 0.10}), ({"LOB": "PA", "TRANSACTION_TYPE": "RN"}, {"COMMISSION_RATE": 0.08}),
              ({"LOB": "WC", "TRANSACTION_TYPE": "*"}, {"COMMISSION_RATE": 0.08}), ({"LOB": "CYB", "TRANSACTION_TYPE": "*"}, {"COMMISSION_RATE": 0.17})]},
]

AUTHORITY = [  # role, type, line, limit, note
    ("UNDERWRITER", "BIND_TIV", "*", 2_000_000, "Total insured value an underwriter may bind"),
    ("SR_UNDERWRITER", "BIND_TIV", "*", 10_000_000, None), ("CUO", "BIND_TIV", "*", 50_000_000, None),
    ("UNDERWRITER", "BIND_TIV", "HO", 1_000_000, "Coverage A"), ("SR_UNDERWRITER", "BIND_TIV", "HO", 3_000_000, "Coverage A"),
    ("UNDERWRITER", "RATE_DEVIATION_PCT", "*", 10, "Schedule rating up or down"), ("SR_UNDERWRITER", "RATE_DEVIATION_PCT", "*", 25, None),
    ("CLAIMS_ADJUSTER", "RESERVE_CHANGE", "*", 25_000, None), ("CLAIMS_MANAGER", "RESERVE_CHANGE", "*", 250_000, None),
    ("CLAIMS_ADJUSTER", "CLAIM_PAYMENT", "*", 25_000, None), ("CLAIMS_MANAGER", "CLAIM_PAYMENT", "*", 250_000, None),
    ("CFO", "CLAIM_PAYMENT", "*", 5_000_000, None), ("BILLING", "REFUND", "*", 5_000, None),
]

# The seed rules (written before the engine had phases and roles) get both now.
SEED_RULESETS = {"UW_PERSONAL_AUTO": ("UNDERWRITER", None), "ROLE_AUTHORITY": ("CUO", "AUTHORITY"), "CLAIMS_TRIAGE": ("CLAIMS_ADJUSTER", "ROUTING"),
                 "DATA_QUALITY": ("DATA_STEWARD", "DATA"), "ISO_BUREAU": ("DATA_STEWARD", "DATA"), "NCCI_EDITS": ("DATA_STEWARD", "DATA")}
PHASE_OF_ACTION = {"DECLINE": "ELIGIBILITY", "REFER": "REFERRAL", "SURCHARGE_PCT": "RATING", "CREDIT_PCT": "RATING", "ROUTE": "ROUTING",
                   "WARN": "ALERT", "ACCEPT": "ELIGIBILITY"}


# ------------------------------------------------------------------------------------------ SQL
def sq(v) -> str:
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, (int, float)):
        return repr(v)
    return "N'" + str(v).replace("'", "''") + "'"


def values(rows, cols, head, tail) -> str:
    first = "    (" + ", ".join("CAST(NULL AS nvarchar(4000))" if v is None else sq(v) for v in rows[0]) + ")"
    body = ",\n".join([first] + ["    (" + ", ".join(sq(v) for v in r) + ")" for r in rows[1:]])
    return f"{head}\nFROM (VALUES\n{body}\n) v ({', '.join(cols)})\n{tail};\n"


def element_codes_used() -> set:
    return {c[0] for r in RULES for c in r.conditions}


def build_sql() -> str:
    out = ["/* SI² rule library (generated by rule_library.py). Synthetic companies; regulated values are illustrative.\n"
           "   Idempotent: only missing rows are added. */", "USE SI2Canonical;\nSET NOCOUNT ON;\nGO\n"]
    w = out.append
    w(values(ROLES, ["c", "n", "d", "x"], f"INSERT rules.Role (RoleCode, Name, Department, Description, CreatedBy)\nSELECT v.c, v.n, v.d, v.x, {sq(BY)}",
             "WHERE NOT EXISTS (SELECT 1 FROM rules.Role r WHERE r.RoleCode = v.c)"))
    w(values([(c, n, d, k, True) for c, n, d, k in COMPANIES], ["c", "n", "d", "k", "s"],
             f"INSERT rules.Company (CompanyCode, Name, Description, NaicCode, IsSynthetic, CreatedBy)\nSELECT v.c, v.n, v.d, v.k, v.s, {sq(BY)}",
             "WHERE NOT EXISTS (SELECT 1 FROM rules.Company x WHERE x.CompanyCode = v.c)"))
    w(values([(c, l, n, co, ",".join(st) or None) for c, l, n, co, st in PRODUCTS], ["c", "l", "n", "co", "st"],
             f"INSERT rules.Product (ProductCode, LobCode, Name, CompanyCode, States, CreatedBy)\nSELECT v.c, v.l, v.n, v.co, v.st, {sq(BY)}",
             "WHERE NOT EXISTS (SELECT 1 FROM rules.Product x WHERE x.ProductCode = v.c)"))
    w(values([(c, n, role, ph, rt, act, sen, json.dumps(qs), ex) for c, n, role, ph, rt, act, sen, qs, ex in TEMPLATES],
             ["c", "n", "r", "ph", "rt", "a", "s", "q", "ex"],
             "INSERT rules.RuleTemplate (TemplateCode, Name, OwnerRole, Phase, RuleType, ActionType, Sentence, QuestionsJson, ExampleText, CreatedBy)\n"
             f"SELECT v.c, v.n, v.r, v.ph, v.rt, v.a, v.s, v.q, v.ex, {sq(BY)}",
             "WHERE NOT EXISTS (SELECT 1 FROM rules.RuleTemplate x WHERE x.TemplateCode = v.c)"))
    w(values(RULESETS, ["c", "n", "p", "d"], f"INSERT rules.RuleSet (RuleSetCode, Name, Purpose, Description, CreatedBy)\nSELECT v.c, v.n, v.p, v.d, {sq(BY)}",
             "WHERE NOT EXISTS (SELECT 1 FROM rules.RuleSet x WHERE x.RuleSetCode = v.c AND x.ScopeId = 1)"))
    tmpl = {t[0]: t for t in TEMPLATES}
    rows = []
    for r in RULES:
        t = tmpl[r.template]
        from rule_engine import describe
        rows.append((r.ruleset, r.code, r.name, describe(r), t[4], r.logic, " and ".join(f"{c[0]} {c[1]} {c[2] or ''}".strip() for c in r.conditions),
                     r.action, r.action_value, r.severity, r.message, r.effective_from, r.template, r.phase, r.role, r.override_key,
                     ",".join(r.scope.get("LOB", [])) or "*", ",".join(r.scope.get("STATE", [])) or "*"))
    w(values(rows, ["rs", "c", "n", "d", "t", "lg", "ct", "a", "av", "sev", "m", "ef", "tp", "ph", "ro", "ok", "lob", "st"],
             "INSERT rules.BusinessRule (RuleSetId, RuleCode, Name, Description, RuleType, ConditionLogic, ConditionText, ActionType, ActionValue,\n"
             "    Severity, Message, EffectiveFrom, TemplateCode, Phase, OwnerRole, OverrideKey, LobScope, StateScope, CreatedBy)\n"
             f"SELECT rs.RuleSetId, v.c, v.n, v.d, v.t, v.lg, v.ct, v.a, v.av, v.sev, v.m, v.ef, v.tp, v.ph, v.ro, v.ok, LEFT(v.lob, 60), LEFT(v.st, 200), {sq(BY)}",
             "JOIN rules.RuleSet rs ON rs.RuleSetCode = v.rs AND rs.ScopeId = 1\n"
             "WHERE NOT EXISTS (SELECT 1 FROM rules.BusinessRule x WHERE x.RuleCode = v.c AND x.ScopeId = 1)"))
    conds = [(r.code, i, c[0], c[1], c[2], c[3]) for r in RULES for i, c in enumerate(r.conditions, 1)]
    w(values(conds, ["r", "s", "e", "o", "v1", "v2"],
             f"INSERT rules.RuleCondition (RuleId, Seq, ElementId, Operator, Value1, Value2, CreatedBy)\nSELECT r.RuleId, v.s, e.ElementId, v.o, v.v1, v.v2, {sq(BY)}",
             "JOIN rules.BusinessRule r ON r.RuleCode = v.r AND r.ScopeId = 1\n"
             "CROSS APPLY (SELECT TOP (1) ElementId FROM canon.DataElement d WHERE d.ElementCode = v.e AND d.ScopeId = 1\n"
             "             ORDER BY CASE d.Status WHEN 'ACTIVE' THEN 0 ELSE 1 END) e\n"
             "WHERE NOT EXISTS (SELECT 1 FROM rules.RuleCondition x WHERE x.RuleId = r.RuleId AND x.Seq = v.s)"))
    scopes = [(r.code, d, v) for r in RULES for d, vs in r.scope.items() for v in vs]
    w(values(scopes, ["r", "d", "sv"], f"INSERT rules.RuleScope (RuleId, Dimension, ScopeValue, CreatedBy)\nSELECT r.RuleId, v.d, v.sv, {sq(BY)}",
             "JOIN rules.BusinessRule r ON r.RuleCode = v.r AND r.ScopeId = 1\n"
             "WHERE NOT EXISTS (SELECT 1 FROM rules.RuleScope x WHERE x.RuleId = r.RuleId AND x.Dimension = v.d AND x.ScopeValue = v.sv)"))
    tests = [(r.code, t["name"][:200], json.dumps(t["input"]), t["fires"]) for r in RULES for t in generate_tests(r)]
    w(values(tests, ["r", "n", "j", "x"], f"INSERT rules.RuleTestCase (RuleId, Name, InputJson, ExpectedFires, CreatedBy)\nSELECT r.RuleId, v.n, v.j, v.x, {sq(BY)}",
             "JOIN rules.BusinessRule r ON r.RuleCode = v.r AND r.ScopeId = 1\n"
             "WHERE NOT EXISTS (SELECT 1 FROM rules.RuleTestCase x WHERE x.RuleId = r.RuleId AND x.Name = v.n)"))
    w(values([(t["code"], t["name"], t["role"], t["description"], json.dumps(t["inputs"]), json.dumps(t["outputs"]), t["illustrative"]) for t in TABLES],
             ["c", "n", "r", "d", "i", "o", "il"],
             "INSERT rules.DecisionTable (TableCode, Name, OwnerRole, Description, InputsJson, OutputsJson, IsIllustrative, CreatedBy)\n"
             f"SELECT v.c, v.n, v.r, v.d, v.i, v.o, v.il, {sq(BY)}", "WHERE NOT EXISTS (SELECT 1 FROM rules.DecisionTable x WHERE x.TableCode = v.c)"))
    trows = [(t["code"], json.dumps(i, sort_keys=True), json.dumps(o)) for t in TABLES for i, o in t["rows"]]
    w(values(trows, ["t", "i", "o"], f"INSERT rules.DecisionTableRow (TableCode, InputsJson, OutputsJson, CreatedBy)\nSELECT v.t, v.i, v.o, {sq(BY)}",
             "WHERE NOT EXISTS (SELECT 1 FROM rules.DecisionTableRow x WHERE x.TableCode = v.t AND x.InputsJson = v.i AND x.Status = 'ACTIVE')"))
    w(values([(r, t, l, lim, n) for r, t, l, lim, n in AUTHORITY], ["r", "t", "l", "lim", "n"],
             f"INSERT rules.RoleAuthority (RoleCode, AuthorityType, LobScope, LimitAmount, Notes, CreatedBy)\nSELECT v.r, v.t, v.l, v.lim, v.n, {sq(BY)}",
             "WHERE NOT EXISTS (SELECT 1 FROM rules.RoleAuthority x WHERE x.RoleCode = v.r AND x.AuthorityType = v.t AND x.LobScope = v.l)"))
    w("-- Seed rules written before the engine: give them an owner role, a phase and a scope from their line / state columns")
    for rs, (role, phase) in SEED_RULESETS.items():
        ph = f"N'{phase}'" if phase else ("CASE r.ActionType " + " ".join(f"WHEN '{a}' THEN N'{p}'" for a, p in PHASE_OF_ACTION.items()) + " ELSE N'REFERRAL' END")
        w(f"UPDATE r SET OwnerRole = N'{role}', Phase = {ph} FROM rules.BusinessRule r JOIN rules.RuleSet s ON s.RuleSetId = r.RuleSetId\n"
          f"WHERE s.RuleSetCode = N'{rs}' AND r.Phase IS NULL;")
    w("INSERT rules.RuleScope (RuleId, Dimension, ScopeValue, CreatedBy)\n"
      f"SELECT r.RuleId, 'LOB', LTRIM(RTRIM(x.value)), {sq(BY)} FROM rules.BusinessRule r CROSS APPLY STRING_SPLIT(r.LobScope, ',') x\n"
      "WHERE r.LobScope <> '*' AND LTRIM(RTRIM(x.value)) <> '' AND NOT EXISTS (SELECT 1 FROM rules.RuleScope s WHERE s.RuleId = r.RuleId AND s.Dimension = 'LOB');")
    w("INSERT rules.RuleScope (RuleId, Dimension, ScopeValue, CreatedBy)\n"
      f"SELECT r.RuleId, 'STATE', LTRIM(RTRIM(x.value)), {sq(BY)} FROM rules.BusinessRule r CROSS APPLY STRING_SPLIT(r.StateScope, ',') x\n"
      "WHERE r.StateScope <> '*' AND LTRIM(RTRIM(x.value)) <> '' AND NOT EXISTS (SELECT 1 FROM rules.RuleScope s WHERE s.RuleId = r.RuleId AND s.Dimension = 'STATE');")
    w("GO\nSELECT (SELECT COUNT(*) FROM rules.Role) AS Roles, (SELECT COUNT(*) FROM rules.RuleTemplate) AS Templates,\n"
      "       (SELECT COUNT(*) FROM rules.BusinessRule WHERE Status = 'ACTIVE') AS Rules, (SELECT COUNT(*) FROM rules.RuleScope) AS ScopeRows,\n"
      "       (SELECT COUNT(*) FROM rules.DecisionTableRow) AS TableRows, (SELECT COUNT(*) FROM rules.RoleAuthority) AS AuthorityRows;\nGO\n")
    return "\n".join(out)


def check(seed_sql: str) -> list[str]:
    """Every element a rule uses must exist in the seed; every code must be a real pick-list code where the element has a list."""
    block = seed_sql.split("INSERT canon.DataElement")[1].split("INSERT canon.Synonym")[0]
    known = set(re.findall(r"^    \(N'([A-Z0-9_]+)', N'", block, re.M))
    problems = sorted(element_codes_used() - known)
    picklist = dict(re.findall(r"^    \(N'([A-Z0-9_]+)', .*?, N'(?:CODE|TEXT)', N'([A-Z0-9_]+)', \d", block, re.M))
    options: dict[str, set] = {}
    for pl, oc in re.findall(r"^    \(N'([A-Z0-9_]+)', N'((?:[^']|'')*)', N'", seed_sql, re.M):
        options.setdefault(pl, set()).add(oc)
    for r in RULES:
        for element, op, v1, _ in r.conditions:
            pl = picklist.get(element)
            if pl and v1:
                for v in (str(v1).split(",") if op == "IN" else [str(v1)]):
                    if v.strip() not in options.get(pl, set()):
                        problems.append(f"{r.code}: {element}={v.strip()} is not a {pl} option")
    return problems


if __name__ == "__main__":
    missing = check((HERE / "03_seed.sql").read_text(encoding="utf-8"))
    if missing:
        sys.exit(f"Rules use elements the seed does not have: {missing}")
    (HERE / "07_rule_library.sql").write_text(build_sql(), encoding="utf-8")
    n_tests = sum(len(generate_tests(r)) for r in RULES)
    print(f"{len(ROLES)} roles, {len(COMPANIES)} companies, {len(PRODUCTS)} products, {len(TEMPLATES)} templates, {len(RULESETS)} rule sets, "
          f"{len(RULES)} rules, {n_tests} tests, {len(TABLES)} decision tables, {len(AUTHORITY)} authority rows")
