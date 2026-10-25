"""SI² Financial Reporting ontology (P&C statutory reporting).

Three layers, all plain tables so engineers can query them like the canonical model:

    concepts   what a number means: Earned Premium, Case Reserve, Policyholder Surplus ... (class hierarchy)
    relations  how meanings connect: is-a, derived-from (with the formula), reported-on (page), checked-by (edit),
               rolls-up-to (annual statement line -> Schedule P line / five-year group), maps-to (SI2Canonical element)
    fields     every Yellow Book cell -> one concept + its dimensions (reinsurance basis, line, state, accident year ...)

Exports: Turtle (OWL / RDFS / SKOS), JSON-LD and CSV, plus the fin.OntConcept / fin.OntRelation tables.
"""
from __future__ import annotations

import json
import re

import pandas as pd

from . import blank as B

NS = "https://si2insure.com/ontology/finrep#"
CANON_EXISTING = {"WRITTEN_PREMIUM", "CEDED_PREMIUM", "CEDED_LOSS", "PAID_LOSS", "INCURRED_LOSS", "PAID_ALAE", "ALAE_RESERVE",
                  "OUTSTANDING_RESERVE", "LOSS_RATIO", "EXPENSE_RATIO", "COMBINED_RATIO", "LINE_OF_BUSINESS", "STATE",
                  "ACCOUNTING_DATE", "LOSS_DATE", "REINSURER_NAME", "REINSURANCE_TYPE", "TREATY_ID", "RECOVERY_AMOUNT",
                  "COMMISSION_RATE", "SOLVENCY_RATIO", "COMPANY_CODE", "CLAIM_STATUS", "ACCOUNT_BALANCE"}

# id, label, parent, kind, definition, SI2Canonical element (existing code, or a proposed new one)
C = [
    ("Thing", "Financial reporting", None, "class", "Root of the SI² financial reporting ontology.", None),
    # structure
    ("ReportStructure", "Report structure", "Thing", "class", "The shape of a regulatory report.", None),
    ("StatutoryAnnualStatement", "NAIC P&C Annual Statement (Yellow Book)", "ReportStructure", "class",
     "Statutory financial statement every U.S. property and casualty insurer files with the NAIC and its domiciliary state.", None),
    ("Page", "Page / exhibit / schedule", "ReportStructure", "class", "A page, exhibit, schedule or part of the statement.", None),
    ("Line", "Line", "ReportStructure", "class", "A numbered row on a page.", None),
    ("Column", "Column", "ReportStructure", "class", "A numbered column on a page.", None),
    ("ReportingField", "Reporting field", "ReportStructure", "class",
     "One cell: page x line x column (x dimensions such as state or accident year). Measures exactly one concept.", None),
    ("CrossCheck", "Cross-check edit", "ReportStructure", "class", "A rule that two or more fields must agree.", None),
    # measures
    ("FinancialConcept", "Financial concept", "Thing", "class", "What a reported number means.", None),
    ("Asset", "Asset", "FinancialConcept", "class", "Resources the insurer owns; only admitted assets count toward surplus.", None),
    ("InvestedAsset", "Invested asset", "Asset", "class", "Bonds, stocks, mortgage loans, real estate, cash and other investments.", None),
    ("Bonds", "Bonds", "InvestedAsset", "measure", "Fixed-income securities, usually at amortized cost.", "BOND_CARRYING_VALUE"),
    ("PreferredStock", "Preferred stocks", "InvestedAsset", "measure", "Preferred equity holdings.", "PREFERRED_STOCK_VALUE"),
    ("CommonStock", "Common stocks", "InvestedAsset", "measure", "Common equity holdings at fair value.", "COMMON_STOCK_VALUE"),
    ("MortgageLoan", "Mortgage loans", "InvestedAsset", "measure", "Mortgage loans on real estate.", "MORTGAGE_LOAN_VALUE"),
    ("RealEstate", "Real estate", "InvestedAsset", "measure", "Real estate occupied, held for income or for sale.", "REAL_ESTATE_VALUE"),
    ("CashAndShortTerm", "Cash, cash equivalents and short-term investments", "InvestedAsset", "measure", "Cash and near-cash.", "CASH_BALANCE"),
    ("OtherInvestedAsset", "Other invested assets", "InvestedAsset", "measure", "Partnerships, derivatives, receivables for securities and write-ins.", None),
    ("Receivable", "Receivable", "Asset", "class", "Amounts owed to the insurer.", None),
    ("InvestmentIncomeDue", "Investment income due and accrued", "Receivable", "measure", "Earned investment income not yet received.", None),
    ("PremiumReceivable", "Premium receivable", "Receivable", "measure", "Uncollected, deferred and accrued retrospective premium.", "ACCOUNT_BALANCE"),
    ("ReinsuranceRecoverable", "Reinsurance recoverable", "Receivable", "measure", "Amounts due from reinsurers on paid losses and LAE.", "RECOVERY_AMOUNT"),
    ("AffiliateReceivable", "Receivable from affiliates", "Receivable", "measure", "Amounts due from the parent, subsidiaries and affiliates.", None),
    ("DeferredTaxAsset", "Net deferred tax asset", "Asset", "measure", "Admitted net deferred tax asset.", None),
    ("OtherAsset", "Other assets", "Asset", "measure", "Equipment, guaranty funds, write-ins and other non-invested assets.", None),
    ("NonadmittedAsset", "Nonadmitted asset", "Asset", "measure", "Assets excluded from statutory surplus under SSAP rules.", None),
    ("Liability", "Liability", "FinancialConcept", "class", "Obligations of the insurer.", None),
    ("LossReserve", "Loss reserve (unpaid losses)", "Liability", "measure", "Estimated unpaid losses: case + bulk + IBNR.", "OUTSTANDING_RESERVE"),
    ("CaseReserve", "Case reserve", "LossReserve", "measure", "Reserve on reported claims set by adjusters.", "OUTSTANDING_RESERVE"),
    ("IBNR", "Bulk and IBNR reserve", "LossReserve", "measure", "Actuarial reserve for incurred but not reported claims and case development.", "IBNR_RESERVE"),
    ("LAEReserve", "Loss adjustment expense reserve", "Liability", "measure", "Unpaid defense and cost containment and adjusting and other expense.", "ALAE_RESERVE"),
    ("DCCReserve", "Defense and cost containment reserve", "LAEReserve", "measure", "Unpaid DCC (allocated LAE).", "ALAE_RESERVE"),
    ("AOReserve", "Adjusting and other reserve", "LAEReserve", "measure", "Unpaid adjusting and other (unallocated) LAE.", "ULAE_RESERVE"),
    ("UnearnedPremium", "Unearned premium reserve", "Liability", "measure", "Premium for the unexpired part of policy terms.", "UNEARNED_PREMIUM"),
    ("EarnedButUnbilled", "Earned but unbilled premium", "UnearnedPremium", "measure", "Premium earned but not yet billed (e.g. workers' compensation audit).", "EBUB_PREMIUM"),
    ("RetroReserve", "Reserve for rate credits and retrospective adjustments", "UnearnedPremium", "measure", "Experience-based premium adjustments.", None),
    ("ReinsurancePayable", "Reinsurance balances payable", "Liability", "measure", "Ceded premiums payable, payable on paid losses and funds held.", None),
    ("ExpensePayable", "Expenses and commissions payable", "Liability", "measure", "Accrued commissions, other expenses, taxes, licenses and fees.", None),
    ("TaxPayable", "Federal income taxes payable", "Liability", "measure", "Current and deferred federal and foreign income taxes.", None),
    ("ProvisionForReinsurance", "Provision for reinsurance", "Liability", "measure", "Statutory charge for unsecured or slow-paying reinsurance.", None),
    ("OtherLiability", "Other liabilities", "Liability", "measure", "Advance premium, dividends, drafts, borrowed money and write-ins.", None),
    ("Surplus", "Capital and surplus", "FinancialConcept", "class", "Statutory net worth.", None),
    ("CapitalStock", "Capital stock", "Surplus", "measure", "Common and preferred capital stock.", None),
    ("SurplusNotes", "Surplus notes", "Surplus", "measure", "Subordinated debt counted as surplus with regulator approval.", None),
    ("PaidInSurplus", "Gross paid in and contributed surplus", "Surplus", "measure", "Capital contributed above par.", None),
    ("UnassignedFunds", "Unassigned funds (surplus)", "Surplus", "measure", "Accumulated earnings and adjustments.", None),
    ("PolicyholderSurplus", "Surplus as regards policyholders", "Surplus", "measure", "Admitted assets minus liabilities.", "POLICYHOLDER_SURPLUS"),
    ("SurplusChange", "Change in surplus", "Surplus", "measure", "Movements in surplus other than net income.", None),
    ("Premium", "Premium", "FinancialConcept", "class", "Premium measures.", None),
    ("WrittenPremium", "Written premium", "Premium", "measure", "Premium on policies written or endorsed in the period.", "WRITTEN_PREMIUM"),
    ("EarnedPremium", "Earned premium", "Premium", "measure", "Written premium plus prior unearned minus current unearned.", "EARNED_PREMIUM"),
    ("Loss", "Loss", "FinancialConcept", "class", "Loss measures.", None),
    ("PaidLoss", "Paid loss", "Loss", "measure", "Loss payments, net of salvage and subrogation received.", "PAID_LOSS"),
    ("IncurredLoss", "Incurred loss", "Loss", "measure", "Paid loss plus change in unpaid loss.", "INCURRED_LOSS"),
    ("SalvageSubrogation", "Salvage and subrogation", "Loss", "measure", "Recoveries from salvage and subrogation.", "RECOVERY_AMOUNT"),
    ("LAE", "Loss adjustment expense", "FinancialConcept", "class", "Cost of settling claims.", None),
    ("PaidLAE", "Paid loss adjustment expense", "LAE", "measure", "DCC and A&O payments.", "PAID_ALAE"),
    ("IncurredLAE", "Incurred loss adjustment expense", "LAE", "measure", "Paid LAE plus change in unpaid LAE.", "INCURRED_LAE"),
    ("UnderwritingExpense", "Underwriting expense", "FinancialConcept", "class", "Cost of acquiring and servicing business.", None),
    ("Commission", "Commission and brokerage", "UnderwritingExpense", "measure", "Commissions, contingent commissions and brokerage.", "COMMISSION_AMOUNT"),
    ("TaxesLicensesFees", "Taxes, licenses and fees", "UnderwritingExpense", "measure", "Premium taxes, licenses, fees and assessments.", None),
    ("OperatingExpense", "General operating expense", "UnderwritingExpense", "measure", "Salaries, rent, equipment, advertising and other expenses.", None),
    ("ExpenseIncurred", "Expenses incurred (all)", "UnderwritingExpense", "measure", "Total expenses incurred before allocation.", None),
    ("ExpensePaid", "Expenses paid", "UnderwritingExpense", "measure", "Expenses incurred less change in unpaid.", None),
    ("InvestmentResult", "Investment result", "FinancialConcept", "class", "Income from investments.", None),
    ("InvestmentIncome", "Investment income", "InvestmentResult", "measure", "Interest, dividends and rents.", "INVESTMENT_INCOME"),
    ("InvestmentExpense", "Investment expense", "InvestmentResult", "measure", "Expenses, taxes, interest and depreciation charged to investment income.", None),
    ("RealizedGain", "Realized capital gain (loss)", "InvestmentResult", "measure", "Gains on investments sold or impaired, net of tax.", None),
    ("UnrealizedGain", "Unrealized capital gain (loss)", "InvestmentResult", "measure", "Change in fair value recognized in surplus.", None),
    ("Result", "Income result", "FinancialConcept", "class", "Income statement results.", None),
    ("UnderwritingGain", "Net underwriting gain (loss)", "Result", "measure", "Earned premium minus losses, LAE and underwriting expenses.", None),
    ("OtherIncome", "Other income", "Result", "measure", "Charge-offs, finance and service charges, write-ins.", None),
    ("PolicyholderDividend", "Dividends to policyholders", "Result", "measure", "Dividends declared to policyholders.", None),
    ("IncomeTax", "Federal and foreign income tax", "Result", "measure", "Income tax incurred.", None),
    ("NetIncome", "Net income", "Result", "measure", "Bottom-line statutory net income.", None),
    ("CashFlow", "Cash flow", "FinancialConcept", "class", "Cash movements.", None),
    ("OperatingCashFlow", "Cash from operations", "CashFlow", "measure", "Premiums collected less losses, expenses, dividends and taxes paid.", None),
    ("InvestingCashFlow", "Cash from investments", "CashFlow", "measure", "Proceeds less investments acquired.", None),
    ("FinancingCashFlow", "Cash from financing", "CashFlow", "measure", "Capital, borrowed funds, dividends and other.", None),
    ("Ratio", "Ratio", "FinancialConcept", "class", "Percentages derived from other concepts.", None),
    ("LossRatio", "Loss ratio", "Ratio", "measure", "Incurred loss / earned premium.", "LOSS_RATIO"),
    ("LAERatio", "LAE ratio", "Ratio", "measure", "Incurred LAE / earned premium.", None),
    ("ExpenseRatio", "Expense ratio", "Ratio", "measure", "Underwriting expense / written (or earned) premium.", "EXPENSE_RATIO"),
    ("CombinedRatio", "Combined ratio", "Ratio", "measure", "Loss + LAE + expense ratio.", "COMBINED_RATIO"),
    ("PremiumToSurplus", "Net premiums written to surplus", "Ratio", "measure", "Leverage ratio.", None),
    ("RBC", "Risk-based capital", "FinancialConcept", "measure", "Total adjusted capital and authorized control level RBC.", "SOLVENCY_RATIO"),
    ("ClaimCount", "Claim count", "FinancialConcept", "measure", "Number of claims reported, outstanding or closed.", "CLAIM_COUNT"),
    ("ReserveDevelopment", "Reserve development", "FinancialConcept", "measure", "Change in incurred losses and DCC between valuations.", None),
    # dimensions
    ("Dimension", "Dimension", "Thing", "class", "A way a measure is broken down.", None),
    ("ReinsuranceBasis", "Reinsurance basis", "Dimension", "dimension", "Direct, assumed, ceded or net.", "REINSURANCE_TYPE"),
    ("LineOfBusiness", "Annual statement line of business", "Dimension", "dimension", "Annual statement lines 1 through 35.", "ANNUAL_STATEMENT_LINE"),
    ("SchedulePLine", "Schedule P line", "Dimension", "dimension", "Schedule P reserving lines A through U.", "SCHEDULE_P_LINE"),
    ("Jurisdiction", "State / jurisdiction", "Dimension", "dimension", "U.S. state, territory, Canada or aggregate other alien.", "STATE"),
    ("AccidentYear", "Accident year", "Dimension", "dimension", "Year in which the loss occurred.", "ACCIDENT_YEAR"),
    ("ValuationDate", "Valuation date", "Dimension", "dimension", "December 31 of a development year.", "ACCOUNTING_DATE"),
    ("ReportingPeriod", "Reporting period", "Dimension", "dimension", "Current year or prior year.", "ACCOUNTING_DATE"),
    ("Reinsurer", "Reinsurer", "Dimension", "dimension", "Counterparty on Schedule F.", "REINSURER_NAME"),
    ("AdmissionStatus", "Admission status", "Dimension", "dimension", "Gross, nonadmitted or net admitted.", None),
    ("ExpenseAllocation", "Expense allocation", "Dimension", "dimension", "Loss adjustment, other underwriting or investment.", None),
]
BASIS = [("Direct", "Direct business"), ("AssumedAffiliate", "Reinsurance assumed from affiliates"),
         ("AssumedNonAffiliate", "Reinsurance assumed from non-affiliates"), ("Assumed", "Reinsurance assumed"),
         ("CededAffiliate", "Reinsurance ceded to affiliates"), ("CededNonAffiliate", "Reinsurance ceded to non-affiliates"),
         ("Ceded", "Reinsurance ceded"), ("DirectAndAssumed", "Direct and assumed"), ("Net", "Net of reinsurance")]
FORMULAS = [  # derived concept, formula, inputs
    ("EarnedPremium", "Earned = Written + Unearned(prior) - Unearned(current)", ["WrittenPremium", "UnearnedPremium"]),
    ("WrittenPremium", "Net = Direct + Assumed - Ceded (by reinsurance basis)", []),
    ("IncurredLoss", "Incurred = Paid + Unpaid(current) - Unpaid(prior)", ["PaidLoss", "LossReserve"]),
    ("LossReserve", "Unpaid = Case + Bulk and IBNR", ["CaseReserve", "IBNR"]),
    ("LAEReserve", "Unpaid LAE = DCC unpaid + A&O unpaid", ["DCCReserve", "AOReserve"]),
    ("IncurredLAE", "Incurred LAE = Paid LAE + LAE unpaid(current) - LAE unpaid(prior)", ["PaidLAE", "LAEReserve"]),
    ("UnderwritingGain", "Underwriting gain = Earned premium - Incurred loss - Incurred LAE - Underwriting expense",
     ["EarnedPremium", "IncurredLoss", "IncurredLAE", "UnderwritingExpense"]),
    ("NetIncome", "Net income = Underwriting gain + Investment gain + Other income - Policyholder dividends - Income tax",
     ["UnderwritingGain", "InvestmentIncome", "RealizedGain", "OtherIncome", "PolicyholderDividend", "IncomeTax"]),
    ("PolicyholderSurplus", "Surplus = Admitted assets - Liabilities; Surplus(current) = Surplus(prior) + Net income + Surplus changes",
     ["Asset", "Liability", "NetIncome", "SurplusChange"]),
    ("LossRatio", "Loss ratio = Incurred loss / Earned premium", ["IncurredLoss", "EarnedPremium"]),
    ("LAERatio", "LAE ratio = Incurred LAE / Earned premium", ["IncurredLAE", "EarnedPremium"]),
    ("ExpenseRatio", "Expense ratio = Underwriting expense / Written premium", ["UnderwritingExpense", "WrittenPremium"]),
    ("CombinedRatio", "Combined = Loss ratio + LAE ratio + Expense ratio", ["LossRatio", "LAERatio", "ExpenseRatio"]),
    ("PremiumToSurplus", "Net written premium / Policyholder surplus", ["WrittenPremium", "PolicyholderSurplus"]),
    ("ReserveDevelopment", "Incurred(valued now) - Incurred(valued one or two years ago)", ["IncurredLoss"]),
    ("OperatingCashFlow", "Premiums collected + investment income + other - losses, expenses, dividends and taxes paid",
     ["EarnedPremium", "PaidLoss", "ExpensePaid", "InvestmentIncome"]),
    ("ExpensePaid", "Paid = Incurred - Unpaid(current) + Unpaid(prior)", ["ExpenseIncurred", "ExpensePayable"]),
]
REPORTED_ON = {"WrittenPremium": ["U1B", "U1", "SP", "H5", "SF3"], "EarnedPremium": ["P4", "U1", "SP", "SP1SUM"],
               "UnearnedPremium": ["P3", "U1", "U1A", "SP"], "PaidLoss": ["U2", "SP", "SP1SUM", "SP3SUM"],
               "IncurredLoss": ["P4", "U2", "SP", "SP1SUM", "SP2SUM"], "LossReserve": ["P3", "U2A", "SP1SUM"],
               "CaseReserve": ["U2A", "SP1SUM"], "IBNR": ["U2A", "SP1SUM"], "LAEReserve": ["P3", "U2A", "SP1SUM"],
               "IncurredLAE": ["P4", "U3"], "PolicyholderSurplus": ["P3", "P4", "H5"], "NetIncome": ["P4", "H5"],
               "InvestmentIncome": ["P4", "NII"], "ReinsuranceRecoverable": ["P2", "SF3"], "ReserveDevelopment": ["SP2SUM", "H5"],
               "ClaimCount": ["SP1SUM", "SP3SUM"], "CashAndShortTerm": ["P2", "P5"]}
EDIT_CONCEPTS = {"E01": ["Asset", "Liability", "PolicyholderSurplus"], "E02": ["Asset", "Liability", "PolicyholderSurplus"],
                 "E03": ["EarnedPremium"], "E04": ["IncurredLoss"], "E05": ["IncurredLAE"], "E06": ["UnderwritingExpense"],
                 "E07": ["LossReserve"], "E08": ["LAEReserve"], "E09": ["UnearnedPremium"], "E10": ["PolicyholderSurplus"],
                 "E11": ["PolicyholderSurplus"], "E12": ["InvestmentIncome"], "E13": ["CashAndShortTerm"], "E14": ["WrittenPremium"],
                 "E15": ["UnearnedPremium"], "E16": ["LossReserve"], "E17": ["ExpenseIncurred"], "E18": ["WrittenPremium"],
                 "E19": ["IncurredLoss"], "E20": ["WrittenPremium"], "E21": ["WrittenPremium"], "E22": ["LossReserve"],
                 "E23": ["LAEReserve"], "E24": ["EarnedPremium"], "E25": ["WrittenPremium", "Reinsurer"],
                 "E26": ["PolicyholderSurplus"], "E27": ["CashFlow"]}


def concepts() -> pd.DataFrame:
    rows = [{"concept_id": c, "label": l, "parent_id": p, "kind": k, "definition": d,
             "canonical_element": e} for c, l, p, k, d, e in C]
    rows += [{"concept_id": f"Basis.{b}", "label": l, "parent_id": "ReinsuranceBasis", "kind": "member", "definition": l,
              "canonical_element": None} for b, l in BASIS]
    rows += [{"concept_id": f"ASL.{c}", "label": f"{c} {n}", "parent_id": "LineOfBusiness", "kind": "member",
              "definition": f"Annual statement line {c}", "canonical_element": None} for c, n, _ in B.ASL]
    rows += [{"concept_id": f"SchP.{c}", "label": f"{c} {n}", "parent_id": "SchedulePLine", "kind": "member",
              "definition": f"Schedule P line {c}", "canonical_element": None} for c, n in B.SCHED_P_LINES]
    rows += [{"concept_id": f"Page.{p[0]}", "label": p[1], "parent_id": "Page", "kind": "member", "definition": p[2],
              "canonical_element": None} for p in B.PAGES]
    from .engine import edits as _e  # noqa: F401 - edit ids come from the engine
    for eid in EDIT_CONCEPTS:
        rows.append({"concept_id": f"Edit.{eid}", "label": f"Edit {eid}", "parent_id": "CrossCheck", "kind": "member",
                     "definition": "Cross-check run on every generated statement (finance/engine.py)", "canonical_element": None})
    df = pd.DataFrame(rows)
    df = df.astype(object).where(df.notna(), None)
    df["canonical_status"] = df.canonical_element.map(lambda e: "" if not isinstance(e, str) else ("in SI2Canonical" if e in CANON_EXISTING
                                                                                  else "proposed new element"))
    return df


def relations() -> pd.DataFrame:
    rows = []
    for c, _l, p, _k, _d, e in C:
        if p:
            rows.append((c, "isA", p, ""))
        if e:
            rows.append((c, "mapsToCanonical", f"canon:{e}", "existing element" if e in CANON_EXISTING else "proposed element"))
    for b, _l in BASIS:
        rows.append((f"Basis.{b}", "isA", "ReinsuranceBasis", ""))
    for code, _n, sp in B.ASL:
        rows.append((f"ASL.{code}", "isA", "LineOfBusiness", ""))
        if sp:
            rows.append((f"ASL.{code}", "rollsUpTo", f"SchP.{sp}", "Schedule P line"))
    from .engine import FIVE_YEAR_GROUPS
    names = {"1": "Liability lines", "2": "Property lines", "3": "Property and liability combined lines", "4": "All other lines",
             "5": "Nonproportional reinsurance lines"}
    for g, lns in FIVE_YEAR_GROUPS.items():
        for ln in lns:
            rows.append((f"ASL.{ln}", "rollsUpTo", f"FiveYear.{names[g]}", "Five-Year Historical Data group"))
    for d, f, ins in FORMULAS:
        for i in ins:
            rows.append((d, "derivedFrom", i, f))
        if not ins:
            rows.append((d, "derivedFrom", "ReinsuranceBasis", f))
    for c, pages in REPORTED_ON.items():
        for p in pages:
            rows.append((c, "reportedOn", f"Page.{p}", ""))
    for eid, cs in EDIT_CONCEPTS.items():
        for c in cs:
            rows.append((f"Edit.{eid}", "checks", c, ""))
    for p in B.PAGES:
        rows.append((f"Page.{p[0]}", "partOf", "StatutoryAnnualStatement", p[2]))
    return pd.DataFrame(rows, columns=["subject_id", "predicate", "object_id", "note"])


# ------------------------------------------------------------------------------------------ field -> concept
LINE_RULES = [  # (page, regex on caption, concept) - first match wins
    ("P2", r"^Bonds", "Bonds"), ("P2", r"Preferred stocks", "PreferredStock"), ("P2", r"Common stocks", "CommonStock"),
    ("P2", r"liens", "MortgageLoan"), ("P2", r"^Properties", "RealEstate"), ("P2", r"^Cash", "CashAndShortTerm"),
    ("P2", r"Investment income due", "InvestmentIncomeDue"), ("P2", r"premiums|Premiums|retrospective", "PremiumReceivable"),
    ("P2", r"reinsur", "ReinsuranceRecoverable"), ("P2", r"deferred tax", "DeferredTaxAsset"),
    ("P2", r"affiliates", "AffiliateReceivable"), ("P2", r"^(Subtotals|Total)", "Asset"),
    ("P2", r"Contract loans|Derivatives|Other invested|Receivables for securities|Securities lending|invested assets", "OtherInvestedAsset"),
    ("P2", r".", "OtherAsset"),
    ("P3", r"^Losses$", "LossReserve"), ("P3", r"^Loss adjustment expenses$", "LAEReserve"), ("P3", r"^Unearned premiums", "UnearnedPremium"),
    ("P3", r"[Rr]einsurance|Funds held", "ReinsurancePayable"), ("P3", r"Provision for reinsurance", "ProvisionForReinsurance"),
    ("P3", r"Commissions|Other expenses|Taxes, licenses", "ExpensePayable"), ("P3", r"income taxes|deferred tax", "TaxPayable"),
    ("P3", r"capital stock", "CapitalStock"), ("P3", r"Surplus notes", "SurplusNotes"), ("P3", r"paid in", "PaidInSurplus"),
    ("P3", r"Unassigned", "UnassignedFunds"), ("P3", r"Surplus as regards|^Totals", "PolicyholderSurplus"),
    ("P3", r"special surplus|other-than-special|treasury|Shares", "SurplusChange"), ("P3", r"^Total liabilities", "Liability"),
    ("P3", r".", "OtherLiability"),
    ("P4", r"^Premiums earned", "EarnedPremium"), ("P4", r"^Losses incurred", "IncurredLoss"),
    ("P4", r"^Loss adjustment", "IncurredLAE"), ("P4", r"underwriting expenses|underwriting deductions", "UnderwritingExpense"),
    ("P4", r"underwriting gain", "UnderwritingGain"), ("P4", r"investment income", "InvestmentIncome"),
    ("P4", r"realized capital", "RealizedGain"), ("P4", r"unrealized", "UnrealizedGain"), ("P4", r"investment gain", "InvestmentResult"),
    ("P4", r"Dividends to policyholders", "PolicyholderDividend"), ("P4", r"income taxes", "IncomeTax"),
    ("P4", r"^Net income", "NetIncome"), ("P4", r"Surplus as regards", "PolicyholderSurplus"),
    ("P4", r"charged off|Finance and service|miscellaneous income|other income", "OtherIncome"), ("P4", r".", "SurplusChange"),
    ("P5", r"^(Premiums|Net investment|Miscellaneous|Benefit|Commissions|Dividends paid|Federal|Net transfers|Total \(Lines [15])|Net cash from operations",
     "OperatingCashFlow"), ("P5", r"^Cash, cash|Beginning|End of year|Net change", "CashAndShortTerm"),
    ("P5", r"Surplus notes|Capital and paid|Borrowed|deposits|Dividends to stock|Other cash|financing", "FinancingCashFlow"),
    ("P5", r".", "InvestingCashFlow"),
    ("U3", r"Claim adjustment|Net claim", "IncurredLAE"), ("U3", r"[Cc]ommission|Contingent|Allowances|Policy and membership", "Commission"),
    ("U3", r"[Tt]axes, licenses|insurance taxes|licenses and fees|guaranty", "TaxesLicensesFees"),
    ("U3", r"unpaid expenses|receivable relating", "ExpensePayable"), ("U3", r"Total expenses paid", "ExpensePaid"),
    ("U3", r"Total expenses incurred", "ExpenseIncurred"), ("U3", r".", "OperatingExpense"),
    ("NII", r"Investment expenses|taxes|Interest expense|Depreciation|deductions", "InvestmentExpense"), ("NII", r".", "InvestmentIncome"),
    ("H5", r"premiums written|Liability lines|Property|All other|Nonproportional|^Total$", "WrittenPremium"),
    ("H5", r"underwriting gain", "UnderwritingGain"), ("H5", r"investment gain", "InvestmentResult"), ("H5", r"other income", "OtherIncome"),
    ("H5", r"Dividends", "PolicyholderDividend"), ("H5", r"income taxes", "IncomeTax"), ("H5", r"^Net income", "NetIncome"),
    ("H5", r"admitted assets", "Asset"), ("H5", r"Premiums and considerations", "PremiumReceivable"), ("H5", r"Total liabilities", "Liability"),
    ("H5", r"^Losses$", "LossReserve"), ("H5", r"Loss adjustment", "LAEReserve"), ("H5", r"Unearned", "UnearnedPremium"),
    ("H5", r"Capital paid", "CapitalStock"), ("H5", r"Surplus as regards", "PolicyholderSurplus"), ("H5", r"Net cash", "OperatingCashFlow"),
    ("H5", r"adjusted capital|risk-based", "RBC"), ("H5", r"development", "ReserveDevelopment"),
    ("H5", r"Losses and loss expenses|Losses incurred", "LossRatio"), ("H5", r"Loss expenses incurred", "LAERatio"),
    ("H5", r"underwriting expenses", "ExpenseRatio"), ("H5", r"to policyholders' surplus|to surplus", "PremiumToSurplus"),
    ("H5", r".", "Ratio"),
]
COL_RULES = {  # page -> {col: (concept, basis)}
    "U1B": {"1": ("WrittenPremium", "Direct"), "2": ("WrittenPremium", "AssumedAffiliate"), "3": ("WrittenPremium", "AssumedNonAffiliate"),
            "4": ("WrittenPremium", "CededAffiliate"), "5": ("WrittenPremium", "CededNonAffiliate"), "6": ("WrittenPremium", "Net")},
    "U1": {"1": ("WrittenPremium", "Net"), "2": ("UnearnedPremium", "Net"), "3": ("UnearnedPremium", "Net"), "4": ("EarnedPremium", "Net")},
    "U1A": {"1": ("UnearnedPremium", "Net"), "2": ("UnearnedPremium", "Net"), "3": ("EarnedButUnbilled", "Net"),
            "4": ("RetroReserve", "Net"), "5": ("UnearnedPremium", "Net")},
    "U2": {"1": ("PaidLoss", "Direct"), "2": ("PaidLoss", "Assumed"), "3": ("PaidLoss", "Ceded"), "4": ("PaidLoss", "Net"),
           "5": ("LossReserve", "Net"), "6": ("LossReserve", "Net"), "7": ("IncurredLoss", "Net"), "8": ("LossRatio", "Net")},
    "U2A": {"1": ("CaseReserve", "Direct"), "2": ("CaseReserve", "Assumed"), "3": ("CaseReserve", "Ceded"), "4": ("CaseReserve", "Net"),
            "5": ("IBNR", "Direct"), "6": ("IBNR", "Assumed"), "7": ("IBNR", "Ceded"), "8": ("LossReserve", "Net"), "9": ("LAEReserve", "Net")},
    "SP": {"1": ("WrittenPremium", "Direct"), "2": ("EarnedPremium", "Direct"), "3": ("PolicyholderDividend", "Direct"),
           "4": ("UnearnedPremium", "Direct"), "5": ("PaidLoss", "Direct"), "6": ("IncurredLoss", "Direct"), "7": ("LossReserve", "Direct"),
           "8": ("PaidLAE", "Direct"), "9": ("IncurredLAE", "Direct"), "10": ("DCCReserve", "Direct"), "11": ("Commission", "Direct"),
           "12": ("TaxesLicensesFees", "Direct")},
}
SP1_COLS = {"1": ("EarnedPremium", "DirectAndAssumed"), "2": ("EarnedPremium", "Ceded"), "3": ("EarnedPremium", "Net"),
            "4": ("PaidLoss", "DirectAndAssumed"), "5": ("PaidLoss", "Ceded"), "6": ("PaidLAE", "DirectAndAssumed"), "7": ("PaidLAE", "Ceded"),
            "8": ("PaidLAE", "Net"), "9": ("SalvageSubrogation", "DirectAndAssumed"), "10": ("PaidLoss", "Net"),
            "11": ("ClaimCount", "DirectAndAssumed"), "13": ("CaseReserve", "DirectAndAssumed"), "14": ("CaseReserve", "Ceded"),
            "15": ("IBNR", "DirectAndAssumed"), "16": ("IBNR", "Ceded"), "17": ("DCCReserve", "DirectAndAssumed"),
            "18": ("DCCReserve", "Ceded"), "19": ("DCCReserve", "DirectAndAssumed"), "20": ("DCCReserve", "Ceded"),
            "21": ("AOReserve", "Net"), "22": ("SalvageSubrogation", "DirectAndAssumed"), "23": ("LossReserve", "Net"),
            "24": ("ClaimCount", "DirectAndAssumed"), "25": ("IncurredLoss", "DirectAndAssumed"), "26": ("IncurredLoss", "Ceded"),
            "27": ("IncurredLoss", "Net"), "28": ("LossRatio", "DirectAndAssumed"), "29": ("LossRatio", "Ceded"),
            "30": ("LossRatio", "Net"), "31": ("LossReserve", "Net"), "32": ("LAEReserve", "Net"), "33": ("Ratio", "Net"),
            "34": ("LossReserve", "Net"), "35": ("LAEReserve", "Net")}


def field_concepts() -> pd.DataFrame:
    f = B.fields()
    rules = [(p, re.compile(rx), c) for p, rx, c in LINE_RULES]
    out = []
    for r in f.itertuples():
        dims = []
        page = r.page_code
        if page in COL_RULES:
            concept, basis = COL_RULES[page].get(r.col_no, ("FinancialConcept", ""))
            dims += [f"basis={basis}", f"line={r.line_no}"] + (["state=*"] if page == "SP" else [])
            if page == "U1" and r.col_no == "2" or page == "U2" and r.col_no == "6":
                dims.append("period=PriorYear")
        elif page.startswith("SP1"):
            concept, basis = SP1_COLS.get(r.col_no, ("FinancialConcept", ""))
            dims += [f"basis={basis}", f"accident_year={r.line_no}", f"schedP={page[3:]}"]
        elif page.startswith("SP2"):
            concept = "ReserveDevelopment" if r.col_no in ("11", "12") else "IncurredLoss"
            dims += ["basis=Net", f"accident_year={r.line_no}", f"valuation={r.col_caption}", f"schedP={page[3:]}"]
        elif page.startswith("SP3"):
            concept = "ClaimCount" if r.col_no in ("11", "12") else "PaidLoss"
            dims += ["basis=Net", f"accident_year={r.line_no}", f"valuation={r.col_caption}", f"schedP={page[3:]}"]
        elif page == "SF3":
            concept = {"6": "WrittenPremium", "7": "ReinsuranceRecoverable", "8": "ReinsuranceRecoverable", "9": "CaseReserve",
                       "10": "DCCReserve", "11": "IBNR", "12": "LAEReserve", "13": "UnearnedPremium", "14": "Commission",
                       "15": "ReinsuranceRecoverable", "16": "ReinsurancePayable", "17": "ReinsurancePayable",
                       "18": "ReinsuranceRecoverable", "19": "ReinsurancePayable"}.get(r.col_no, "Reinsurer")
            dims += ["basis=Ceded", "reinsurer=*"]
        else:
            concept = next((c for p, rx, c in rules if p == page and rx.search(r.line_caption)), "FinancialConcept")
            if page == "P2":
                dims.append({"1": "admission=Gross", "2": "admission=Nonadmitted", "3": "admission=NetAdmitted",
                             "4": "admission=NetAdmitted;period=PriorYear"}[r.col_no])
            elif page in ("P3", "P4", "P5"):
                dims.append("period=" + ("CurrentYear" if r.col_no == "1" else "PriorYear"))
            elif page == "U3":
                dims.append("allocation=" + {"1": "LAE", "2": "OtherUnderwriting", "3": "Investment", "4": "Total"}[r.col_no])
            elif page == "H5":
                dims.append(f"year={r.col_caption}")
        out.append({"field_id": r.field_id, "concept_id": concept, "dimensions": ";".join(dims)})
    return pd.DataFrame(out)


# ------------------------------------------------------------------------------------------ exports
def _iri(x: str) -> str:
    if x.startswith("canon:"):
        return f"canon:{x[6:]}"
    return "fr:" + re.sub(r"[^A-Za-z0-9_]", "_", x)


def _lit(s) -> str:
    return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"') + '"'


def turtle(include_fields: bool = False) -> str:
    cs, rs = concepts(), relations()
    out = ["@prefix fr: <" + NS + "> .", "@prefix canon: <https://si2insure.com/canonical#> .",
           "@prefix owl: <http://www.w3.org/2002/07/owl#> .", "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .",
           "@prefix skos: <http://www.w3.org/2004/02/skos/core#> .", "@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .", "",
           "<" + NS[:-1] + "> a owl:Ontology ; rdfs:label \"SI² P&C financial reporting ontology\" .", ""]
    for p in ("derivedFrom", "reportedOn", "checks", "rollsUpTo", "mapsToCanonical", "partOf", "measures", "hasDimension"):
        out.append(f"fr:{p} a owl:ObjectProperty ; rdfs:label {_lit(p)} .")
    out.append("fr:formula a owl:AnnotationProperty .")
    out.append("")
    for r in cs.itertuples():
        typ = "owl:Class" if r.kind in ("class", "measure", "dimension") else "owl:NamedIndividual"
        line = f"{_iri(r.concept_id)} a {typ} ; rdfs:label {_lit(r.label)}"
        if isinstance(r.parent_id, str):
            line += f" ; {'rdfs:subClassOf' if typ == 'owl:Class' else 'a'} {_iri(r.parent_id)}"
        if isinstance(r.definition, str):
            line += f" ; skos:definition {_lit(r.definition)}"
        out.append(line + " .")
    for r in rs.itertuples():
        if r.predicate == "isA":
            continue
        t = f"{_iri(r.subject_id)} fr:{r.predicate} {_iri(r.object_id)} ."
        if r.predicate == "derivedFrom" and r.note:
            t = f"{_iri(r.subject_id)} fr:formula {_lit(r.note)} .\n" + t
        out.append(t)
    if include_fields:
        fc = field_concepts().merge(B.fields()[["field_id", "page_code", "line_caption", "col_caption"]], on="field_id")
        for r in fc.itertuples():
            out.append(f"{_iri('F.' + r.field_id)} a fr:ReportingField ; rdfs:label {_lit(r.field_id + ' ' + r.line_caption + ' | ' + r.col_caption)}"
                       f" ; fr:partOf {_iri('Page.' + r.page_code)} ; fr:measures {_iri(r.concept_id)} ; fr:hasDimension {_lit(r.dimensions)} .")
    return "\n".join(dict.fromkeys(out)) + "\n"


def jsonld() -> str:
    cs, rs = concepts(), relations()
    graph = []
    for r in cs.itertuples():
        node = {"@id": "fr:" + r.concept_id, "@type": "owl:Class" if r.kind in ("class", "measure", "dimension") else "owl:NamedIndividual",
                "rdfs:label": r.label, "skos:definition": r.definition}
        if isinstance(r.parent_id, str):
            node["rdfs:subClassOf"] = {"@id": "fr:" + r.parent_id}
        if isinstance(r.canonical_element, str):
            node["fr:mapsToCanonical"] = {"@id": "canon:" + r.canonical_element}
        for x in rs[(rs.subject_id == r.concept_id) & (rs.predicate.isin(["derivedFrom", "reportedOn", "checks", "rollsUpTo"]))].itertuples():
            node.setdefault("fr:" + x.predicate, []).append({"@id": "fr:" + x.object_id})
        graph.append(node)
    return json.dumps({"@context": {"fr": NS, "canon": "https://si2insure.com/canonical#",
                                    "owl": "http://www.w3.org/2002/07/owl#", "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
                                    "skos": "http://www.w3.org/2004/02/skos/core#"}, "@graph": graph}, indent=1)


def canonical_gaps() -> pd.DataFrame:
    """Concepts whose SI2Canonical element does not exist yet: proposals for the Canonical Master (two-person approval)."""
    cs = concepts()
    g = cs[cs.canonical_status == "proposed new element"]
    return g[["canonical_element", "label", "definition", "concept_id"]].rename(
        columns={"canonical_element": "proposed_element_code", "label": "name", "definition": "business_description"}
    ).assign(subject_area="FINANCIAL_REPORTING", data_type=lambda d: d.proposed_element_code.map(
        lambda x: "TEXT" if x in ("ANNUAL_STATEMENT_LINE", "SCHEDULE_P_LINE") else ("INTEGER" if x in ("ACCIDENT_YEAR", "CLAIM_COUNT") else "AMOUNT")))


def neighbourhood_dot(concept: str, depth: int = 1) -> str:
    rs = relations()
    keep = {concept}
    for _ in range(depth):
        nxt = set(rs[rs.subject_id.isin(keep)].object_id) | set(rs[rs.object_id.isin(keep)].subject_id)
        keep |= nxt
    sub = rs[rs.subject_id.isin(keep) & rs.object_id.isin(keep)]
    if len(sub) > 70:
        sub = sub[(sub.subject_id == concept) | (sub.object_id == concept)]
    colors = {"isA": "#9AA5B1", "derivedFrom": "#2B4CF2", "reportedOn": "#0A7A3D", "checks": "#B54708", "rollsUpTo": "#6941C6",
              "mapsToCanonical": "#B42318", "partOf": "#9AA5B1"}
    lines = ['digraph O { rankdir=LR; bgcolor="transparent"; node [shape=box, style="rounded,filled", fillcolor="#FFFFFF", '
             'fontname="Helvetica", fontsize=10]; edge [fontname="Helvetica", fontsize=8];',
             f'"{concept}" [fillcolor="#E7ECFE", penwidth=2];']
    for r in sub.itertuples():
        lines.append(f'"{r.subject_id}" -> "{r.object_id}" [label="{r.predicate}", color="{colors.get(r.predicate, "#666")}"];')
    return "\n".join(lines) + "\n}"
