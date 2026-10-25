"""The NAIC Property & Casualty Annual Statement ("Yellow Book") as data: pages, lines, columns and every field.

A field is one cell of the blank: page × line × column (Schedule P: × accident year). Each page records where its
captions came from:

* "NAIC 2026 blank": line and column captions read from the NAIC 2026 Property/Casualty Annual Statement Blank
  (content.naic.org, publication-asb-prop.pdf): Assets, Liabilities, Income, Cash Flow, Underwriting and Investment
  Exhibit Parts 1, 1A, 1B, 2, 2A, 3 and the Exhibit of Net Investment Income.
* "SI² outline – verify": structure SI² knows from the blank but has not yet read line by line from the PDF
  (Schedule P, the state page, Schedule F Part 3, Five-Year Historical Data, cash-flow sub-lines). Verify these
  against the blank for the filing year before production use.

Captions are short business captions (cross-references such as "(Part 1, Line 35, Column 4)" are kept as edits in
finance/engine.py instead of in the caption).
"""
from __future__ import annotations

import pandas as pd

YEAR = 2025                              # statement year of the demo filing (blank edition 2026 instructions)
NAIC = "NAIC 2026 blank"
OUTLINE = "SI² outline – verify"

# ------------------------------------------------------------------------------------------ annual statement lines
# Annual statement line of business rows used by UIE Parts 1, 1A, 1B, 2, 2A and the state page. (code, name, Schedule P line)
ASL = [
    ("1", "Fire", "I"), ("2.1", "Allied lines", "I"), ("2.2", "Multiple peril crop", "I"), ("2.3", "Federal flood", "I"),
    ("2.4", "Private crop", "I"), ("2.5", "Private flood", "I"), ("3", "Farmowners multiple peril", "A"),
    ("4", "Homeowners multiple peril", "A"), ("5.1", "Commercial multiple peril (non-liability portion)", "E"),
    ("5.2", "Commercial multiple peril (liability portion)", "E"), ("6", "Mortgage guaranty", "S"), ("8", "Ocean marine", "G"),
    ("9.1", "Inland marine", "I"), ("9.2", "Pet insurance plans", "U"), ("10", "Financial guaranty", "S"),
    ("11.1", "Medical professional liability - occurrence", "F1"), ("11.2", "Medical professional liability - claims-made", "F2"),
    ("12", "Earthquake", "I"), ("13.1", "Comprehensive (hospital and medical) individual", "L"),
    ("13.2", "Comprehensive (hospital and medical) group", "L"), ("14", "Credit accident and health", "L"),
    ("15.1", "Vision only", "L"), ("15.2", "Dental only", "L"), ("15.3", "Disability income", "L"),
    ("15.4", "Medicare supplement", "L"), ("15.5", "Medicaid Title XIX", "L"), ("15.6", "Medicare Title XVIII", "L"),
    ("15.7", "Long-term care", "L"), ("15.8", "Federal employees health benefits plan", "L"), ("15.9", "Other health", "L"),
    ("16", "Workers' compensation", "D"), ("17.1", "Other liability - occurrence", "H1"),
    ("17.2", "Other liability - claims-made", "H2"), ("17.3", "Excess workers' compensation", "H1"),
    ("18.1", "Products liability - occurrence", "R1"), ("18.2", "Products liability - claims-made", "R2"),
    ("19.1", "Private passenger auto no-fault (personal injury protection)", "B"),
    ("19.2", "Other private passenger auto liability", "B"), ("19.3", "Commercial auto no-fault (personal injury protection)", "C"),
    ("19.4", "Other commercial auto liability", "C"), ("21.1", "Private passenger auto physical damage", "J"),
    ("21.2", "Commercial auto physical damage", "J"), ("22", "Aircraft (all perils)", "G"), ("23", "Fidelity", "K"),
    ("24", "Surety", "K"), ("26", "Burglary and theft", "I"), ("27", "Boiler and machinery", "G"), ("28", "Credit", "L"),
    ("29", "International", "M"), ("30", "Warranty", "T"), ("31", "Reinsurance - nonproportional assumed property", "N"),
    ("32", "Reinsurance - nonproportional assumed liability", "O"),
    ("33", "Reinsurance - nonproportional assumed financial lines", "P"), ("34", "Aggregate write-ins for other lines", "L"),
    ("35", "Totals", ""),
]
ASL_CODES = [a[0] for a in ASL]

SCHED_P_LINES = [
    ("A", "Homeowners / farmowners"), ("B", "Private passenger auto liability / medical"),
    ("C", "Commercial auto / truck liability / medical"), ("D", "Workers' compensation (excluding excess workers' compensation)"),
    ("E", "Commercial multiple peril"), ("F1", "Medical professional liability - occurrence"),
    ("F2", "Medical professional liability - claims-made"), ("G", "Special liability (ocean marine, aircraft, boiler and machinery)"),
    ("H1", "Other liability - occurrence"), ("H2", "Other liability - claims-made"),
    ("I", "Special property (fire, allied lines, inland marine, earthquake, burglary and theft)"), ("J", "Auto physical damage"),
    ("K", "Fidelity / surety"), ("L", "Other (including credit, accident and health)"), ("M", "International"),
    ("N", "Reinsurance - nonproportional assumed property"), ("O", "Reinsurance - nonproportional assumed liability"),
    ("P", "Reinsurance - nonproportional assumed financial lines"), ("R1", "Products liability - occurrence"),
    ("R2", "Products liability - claims-made"), ("S", "Financial guaranty / mortgage guaranty"), ("T", "Warranty"),
    ("U", "Pet insurance plans"),
]

STATES = ["AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "DC", "FL", "GA", "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA",
          "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK", "OR",
          "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY", "AS", "GU", "PR", "VI", "MP", "CAN",
          "AGG"]

# ------------------------------------------------------------------------------------------ page definitions
# line kinds: D detail (a value), T total (computed from other lines), H heading (no value)


def L(no, caption, kind="D"):
    return (str(no), caption, kind)


ASSETS = [
    L(1, "Bonds"), L("2", "Stocks", "H"), L(2.1, "Preferred stocks"), L(2.2, "Common stocks"),
    L("3", "Mortgage loans on real estate", "H"), L(3.1, "First liens"), L(3.2, "Other than first liens"),
    L("4", "Real estate", "H"), L(4.1, "Properties occupied by the company (less encumbrances)"),
    L(4.2, "Properties held for the production of income (less encumbrances)"),
    L(4.3, "Properties held for sale (less encumbrances)"), L(5, "Cash, cash equivalents and short-term investments"),
    L(6, "Contract loans (including premium notes)"), L(7, "Derivatives"), L(8, "Other invested assets"),
    L(9, "Receivables for securities"), L(10, "Securities lending reinvested collateral assets"),
    L(11, "Aggregate write-ins for invested assets"), L(12, "Subtotals, cash and invested assets (Lines 1 to 11)", "T"),
    L(13, "Title plants less charged off (for Title insurers only)"), L(14, "Investment income due and accrued"),
    L("15", "Premiums and considerations", "H"),
    L(15.1, "Uncollected premiums and agents' balances in the course of collection"),
    L(15.2, "Deferred premiums, agents' balances and installments booked but deferred and not yet due"),
    L(15.3, "Accrued retrospective premiums and contracts subject to redetermination"),
    L("16", "Reinsurance", "H"), L(16.1, "Amounts recoverable from reinsurers"),
    L(16.2, "Funds held by or deposited with reinsured companies"), L(16.3, "Other amounts receivable under reinsurance contracts"),
    L(17, "Amounts receivable relating to uninsured plans"),
    L(18.1, "Current federal and foreign income tax recoverable and interest thereon"), L(18.2, "Net deferred tax asset"),
    L(19, "Guaranty funds receivable or on deposit"), L(20, "Electronic data processing equipment and software"),
    L(21, "Furniture and equipment, including health care delivery assets"),
    L(22, "Net adjustment in assets and liabilities due to foreign exchange rates"),
    L(23, "Receivables from parent, subsidiaries and affiliates"), L(24, "Health care and other amounts receivable"),
    L(25, "Aggregate write-ins for other-than-invested assets"),
    L(26, "Total assets excluding Separate Accounts, Segregated Accounts and Protected Cell Accounts (Lines 12 to 25)", "T"),
    L(27, "From Separate Accounts, Segregated Accounts and Protected Cell Accounts"), L(28, "Total (Lines 26 and 27)", "T"),
]
LIABILITIES = [
    L(1, "Losses"), L(2, "Reinsurance payable on paid losses and loss adjustment expenses"), L(3, "Loss adjustment expenses"),
    L(4, "Commissions payable, contingent commissions and other similar charges"),
    L(5, "Other expenses (excluding taxes, licenses and fees)"),
    L(6, "Taxes, licenses and fees (excluding federal and foreign income taxes)"),
    L(7.1, "Current federal and foreign income taxes (including on realized capital gains (losses))"),
    L(7.2, "Net deferred tax liability"), L(8, "Borrowed money and interest thereon"),
    L(9, "Unearned premiums (after deducting unearned premiums for ceded reinsurance)"), L(10, "Advance premium"),
    L("11", "Dividends declared and unpaid", "H"), L(11.1, "Stockholders"), L(11.2, "Policyholders"),
    L(12, "Ceded reinsurance premiums payable (net of ceding commissions)"),
    L(13, "Funds held by company under reinsurance treaties"), L(14, "Amounts withheld or retained by company for account of others"),
    L(15, "Remittances and items not allocated"), L(16, "Provision for reinsurance (including certified)"),
    L(17, "Net adjustments in assets and liabilities due to foreign exchange rates"), L(18, "Drafts outstanding"),
    L(19, "Payable to parent, subsidiaries and affiliates"), L(20, "Derivatives"), L(21, "Payable for securities"),
    L(22, "Payable for securities lending"), L(23, "Liability for amounts held under uninsured plans"),
    L(24, "Capital notes and interest thereon"), L(25, "Aggregate write-ins for liabilities"),
    L(26, "Total liabilities excluding protected cell liabilities (Lines 1 through 25)", "T"), L(27, "Protected cell liabilities"),
    L(28, "Total liabilities (Lines 26 and 27)", "T"), L(29, "Aggregate write-ins for special surplus funds"),
    L(30, "Common capital stock"), L(31, "Preferred capital stock"), L(32, "Aggregate write-ins for other-than-special surplus funds"),
    L(33, "Surplus notes"), L(34, "Gross paid in and contributed surplus"), L(35, "Unassigned funds (surplus)"),
    L("36", "Less treasury stock, at cost", "H"), L(36.1, "Shares common"), L(36.2, "Shares preferred"),
    L(37, "Surplus as regards policyholders (Lines 29 to 35, less 36)", "T"), L(38, "Totals (Page 2, Line 28, Col. 3)", "T"),
]
INCOME = [
    L("UW", "Underwriting income", "H"), L(1, "Premiums earned"), L(2, "Losses incurred"), L(3, "Loss adjustment expenses incurred"),
    L(4, "Other underwriting expenses incurred"), L(5, "Aggregate write-ins for underwriting deductions"),
    L(6, "Total underwriting deductions (Lines 2 through 5)", "T"), L(7, "Net income of protected cells"),
    L(8, "Net underwriting gain (loss) (Line 1 minus Line 6 plus Line 7)", "T"),
    L("INV", "Investment income", "H"), L(9, "Net investment income earned"),
    L(10, "Net realized capital gains (losses) less capital gains tax"), L(11, "Net investment gain (loss) (Lines 9 + 10)", "T"),
    L("OTH", "Other income", "H"), L(12, "Net gain or (loss) from agents' or premium balances charged off"),
    L(13, "Finance and service charges not included in premiums"), L(14, "Aggregate write-ins for miscellaneous income"),
    L(15, "Total other income (Lines 12 through 14)", "T"),
    L(16, "Net income before dividends to policyholders, after capital gains tax and before federal and foreign income taxes", "T"),
    L(17, "Dividends to policyholders"),
    L(18, "Net income after dividends to policyholders, after capital gains tax and before federal and foreign income taxes", "T"),
    L(19, "Federal and foreign income taxes incurred"), L(20, "Net income (Line 18 minus Line 19)", "T"),
    L("CS", "Capital and surplus account", "H"), L(21, "Surplus as regards policyholders, December 31 prior year"),
    L(22, "Net income (from Line 20)", "T"), L(23, "Net transfers (to) from Protected Cell accounts"),
    L(24, "Change in net unrealized capital gains or (losses) less capital gains tax"),
    L(25, "Change in net unrealized foreign exchange capital gain (loss)"), L(26, "Change in net deferred income tax"),
    L(27, "Change in nonadmitted assets"), L(28, "Change in provision for reinsurance"), L(29, "Change in surplus notes"),
    L(30, "Surplus (contributed to) withdrawn from protected cells"), L(31, "Cumulative effect of changes in accounting principles"),
    L("32", "Capital changes", "H"), L(32.1, "Paid in"), L(32.2, "Transferred from surplus (Stock Dividend)"),
    L(32.3, "Transferred to surplus"), L("33", "Surplus adjustments", "H"), L(33.1, "Paid in"),
    L(33.2, "Transferred to capital (Stock Dividend)"), L(33.3, "Transferred from capital"),
    L(34, "Net remittances from or (to) Home Office"), L(35, "Dividends to stockholders"), L(36, "Change in treasury stock"),
    L(37, "Aggregate write-ins for gains and losses in surplus"),
    L(38, "Change in surplus as regards policyholders for the year (Lines 22 through 37)", "T"),
    L(39, "Surplus as regards policyholders, December 31 current year (Lines 21 plus 38)", "T"),
]
CASH_FLOW = [
    L("OPS", "Cash from operations", "H"), L(1, "Premiums collected net of reinsurance"), L(2, "Net investment income"),
    L(3, "Miscellaneous income"), L(4, "Total (Lines 1 through 3)", "T"), L(5, "Benefit and loss related payments"),
    L(6, "Net transfers to Separate Accounts, Segregated Accounts and Protected Cell Accounts"),
    L(7, "Commissions, expenses paid and aggregate write-ins for deductions"), L(8, "Dividends paid to policyholders"),
    L(9, "Federal and foreign income taxes paid (recovered)"), L(10, "Total (Lines 5 through 9)", "T"),
    L(11, "Net cash from operations (Line 4 minus Line 10)", "T"),
    L("INVS", "Cash from investments", "H"), L("12", "Proceeds from investments sold, matured or repaid", "H"),
    L(12.1, "Bonds"), L(12.2, "Stocks"), L(12.3, "Mortgage loans"), L(12.4, "Real estate"), L(12.5, "Other invested assets"),
    L(12.6, "Net gains or (losses) on cash, cash equivalents and short-term investments"), L(12.7, "Miscellaneous proceeds"),
    L(12.8, "Total investment proceeds (Lines 12.1 to 12.7)", "T"), L("13", "Cost of investments acquired", "H"),
    L(13.1, "Bonds"), L(13.2, "Stocks"), L(13.3, "Mortgage loans"), L(13.4, "Real estate"), L(13.5, "Other invested assets"),
    L(13.6, "Miscellaneous applications"), L(13.7, "Total investments acquired (Lines 13.1 to 13.6)", "T"),
    L(14, "Net increase (or decrease) in contract loans and premium notes"),
    L(15, "Net cash from investments (Line 12.8 minus Line 13.7 minus Line 14)", "T"),
    L("FIN", "Cash from financing and miscellaneous sources", "H"), L("16", "Cash provided (applied)", "H"),
    L(16.1, "Surplus notes, capital notes"), L(16.2, "Capital and paid in surplus, less treasury stock"),
    L(16.3, "Borrowed funds"), L(16.4, "Net deposits on deposit-type contracts and other insurance liabilities"),
    L(16.5, "Dividends to stockholders"), L(16.6, "Other cash provided (applied)"),
    L(17, "Net cash from financing and miscellaneous sources", "T"),
    L(18, "Net change in cash, cash equivalents and short-term investments (Lines 11 + 15 + 17)", "T"),
    L("19", "Cash, cash equivalents and short-term investments", "H"), L(19.1, "Beginning of year"),
    L(19.2, "End of year (Line 18 plus Line 19.1)", "T"),
]
EXPENSES = [
    L("1", "Claim adjustment services", "H"), L(1.1, "Direct"), L(1.2, "Reinsurance assumed"), L(1.3, "Reinsurance ceded"),
    L(1.4, "Net claim adjustment services (1.1 + 1.2 - 1.3)", "T"), L("2", "Commission and brokerage", "H"),
    L(2.1, "Direct, excluding contingent"), L(2.2, "Reinsurance assumed, excluding contingent"),
    L(2.3, "Reinsurance ceded, excluding contingent"), L(2.4, "Contingent - direct"), L(2.5, "Contingent - reinsurance assumed"),
    L(2.6, "Contingent - reinsurance ceded"), L(2.7, "Policy and membership fees"),
    L(2.8, "Net commission and brokerage (2.1 + 2.2 - 2.3 + 2.4 + 2.5 - 2.6 + 2.7)", "T"),
    L(3, "Allowances to manager and agents"), L(4, "Advertising"), L(5, "Boards, bureaus and associations"),
    L(6, "Surveys and underwriting reports"), L(7, "Audit of assureds' records"), L("8", "Salary and related items", "H"),
    L(8.1, "Salaries"), L(8.2, "Payroll taxes"), L(9, "Employee relations and welfare"), L(10, "Insurance"),
    L(11, "Directors' fees"), L(12, "Travel and travel items"), L(13, "Rent and rent items"), L(14, "Equipment"),
    L(15, "Cost or depreciation of EDP equipment and software"), L(16, "Printing and stationery"),
    L(17, "Postage, telephone and telegraph, exchange and express"), L(18, "Legal and auditing"),
    L(19, "Totals (Lines 3 to 18)", "T"), L("20", "Taxes, licenses and fees", "H"), L(20.1, "State and local insurance taxes"),
    L(20.2, "Insurance department licenses and fees"), L(20.3, "Gross guaranty association assessments"),
    L(20.4, "All other (excluding federal and foreign income and real estate)"),
    L(20.5, "Total taxes, licenses and fees (20.1 + 20.2 + 20.3 + 20.4)", "T"), L(21, "Real estate expenses"),
    L(22, "Real estate taxes"), L(23, "Reimbursements by uninsured plans"), L(24, "Aggregate write-ins for miscellaneous expenses"),
    L(25, "Total expenses incurred", "T"), L(26, "Less unpaid expenses - current year"), L(27, "Add unpaid expenses - prior year"),
    L(28, "Amounts receivable relating to uninsured plans, prior year"),
    L(29, "Amounts receivable relating to uninsured plans, current year"), L(30, "Total expenses paid (Lines 25 - 26 + 27 - 28 + 29)", "T"),
]
NII = [
    L(1, "U.S. Government bonds"), L(1.1, "Bonds exempt from U.S. tax"), L(1.2, "Other bonds (unaffiliated)"),
    L(1.3, "Bonds of affiliates"), L(2.1, "Preferred stocks (unaffiliated)"), L(2.11, "Preferred stocks of affiliates"),
    L(2.2, "Common stocks (unaffiliated)"), L(2.21, "Common stocks of affiliates"), L(3, "Mortgage loans"), L(4, "Real estate"),
    L(5, "Contract loans"), L(6, "Cash, cash equivalents and short-term investments"), L(7, "Derivative instruments"),
    L(8, "Other invested assets"), L(9, "Aggregate write-ins for investment income"),
    L(10, "Total gross investment income", "T"), L(11, "Investment expenses"),
    L(12, "Investment taxes, licenses and fees, excluding federal income taxes"), L(13, "Interest expense"),
    L(14, "Depreciation on real estate and other invested assets"), L(15, "Aggregate write-ins for deductions from investment income"),
    L(16, "Total deductions (Lines 11 through 15)", "T"), L(17, "Net investment income (Line 10 minus Line 16)", "T"),
]
FIVE_YEAR = [
    L("GPW", "Gross premiums written (Page 8, Part 1B, Cols. 1, 2 & 3)", "H"),
    L(1, "Liability lines"), L(2, "Property lines"), L(3, "Property and liability combined lines"), L(4, "All other lines"),
    L(5, "Nonproportional reinsurance lines"), L(6, "Total", "T"),
    L("NPW", "Net premiums written (Page 8, Part 1B, Col. 6)", "H"),
    L(7, "Liability lines"), L(8, "Property lines"), L(9, "Property and liability combined lines"), L(10, "All other lines"),
    L(11, "Nonproportional reinsurance lines"), L(12, "Total", "T"),
    L("SOI", "Statement of income (Page 4)", "H"), L(13, "Net underwriting gain (loss)"), L(14, "Net investment gain (loss)"),
    L(15, "Total other income"), L(16, "Dividends to policyholders"), L(17, "Federal and foreign income taxes incurred"),
    L(18, "Net income"), L("BS", "Balance sheet (Pages 2 and 3)", "H"), L(19, "Total admitted assets"),
    L(20.1, "Premiums and considerations: in course of collection"), L(20.2, "Premiums and considerations: deferred and not yet due"),
    L(20.3, "Premiums and considerations: accrued retrospective premiums"), L(21, "Total liabilities"),
    L(22, "Losses"), L(23, "Loss adjustment expenses"), L(24, "Unearned premiums"), L(25, "Capital paid up"),
    L(26, "Surplus as regards policyholders"), L(27, "Net cash from operations"),
    L("RBC", "Risk-based capital analysis", "H"), L(28, "Total adjusted capital"), L(29, "Authorized control level risk-based capital"),
    L("OP", "Operating percentages (Page 4 lines as % of Line 1)", "H"), L(37, "Premiums earned"), L(38, "Losses incurred"),
    L(39, "Loss expenses incurred"), L(40, "Other underwriting expenses incurred"), L(41, "Net underwriting gain (loss)"),
    L("OPC", "Other percentages", "H"), L(42, "Other underwriting expenses to net premiums written"),
    L(43, "Losses and loss expenses incurred to premiums earned"), L(44, "Net premiums written to policyholders' surplus"),
    L("DEV", "Loss development", "H"), L(45, "One-year development of losses and LAE (Schedule P Part 2 Summary)"),
    L(46, "Percent of one-year development to policyholders' surplus of prior year"),
    L(47, "Two-year development of losses and LAE"), L(48, "Percent of two-year development to policyholders' surplus"),
]

COLS_BS_ASSETS = [("1", "Assets"), ("2", "Nonadmitted assets"), ("3", "Net admitted assets (Cols. 1 - 2)"),
                  ("4", "December 31 prior year net admitted assets")]
CY_PY = [("1", "Current year"), ("2", "Prior year")]
FIVE_COLS = [("1", f"{YEAR}"), ("2", f"{YEAR - 1}"), ("3", f"{YEAR - 2}"), ("4", f"{YEAR - 3}"), ("5", f"{YEAR - 4}")]

PART1B_COLS = [("1", "Direct business"), ("2", "Reinsurance assumed from affiliates"),
               ("3", "Reinsurance assumed from non-affiliates"), ("4", "Reinsurance ceded to affiliates"),
               ("5", "Reinsurance ceded to non-affiliates"), ("6", "Net premiums written (Cols. 1 + 2 + 3 - 4 - 5)")]
PART1_COLS = [("1", "Net premiums written per Column 6, Part 1B"), ("2", "Unearned premiums Dec. 31 prior year"),
              ("3", "Unearned premiums Dec. 31 current year"), ("4", "Premiums earned during year (Cols. 1 + 2 - 3)")]
PART1A_COLS = [("1", "Amount unearned (running one year or less from date of policy)"),
               ("2", "Amount unearned (running more than one year from date of policy)"), ("3", "Earned but unbilled premium"),
               ("4", "Reserve for rate credits and retrospective adjustments based on experience"),
               ("5", "Total reserve for unearned premiums (Cols. 1 + 2 + 3 + 4)")]
PART2_COLS = [("1", "Direct business"), ("2", "Reinsurance assumed"), ("3", "Reinsurance recovered"),
              ("4", "Net payments (Cols. 1 + 2 - 3)"), ("5", "Net losses unpaid current year (Part 2A, Col. 8)"),
              ("6", "Net losses unpaid prior year"), ("7", "Losses incurred current year (Cols. 4 + 5 - 6)"),
              ("8", "Percentage of losses incurred to premiums earned")]
PART2A_COLS = [("1", "Reported losses: direct"), ("2", "Reported losses: reinsurance assumed"),
               ("3", "Reported losses: deduct reinsurance recoverable"), ("4", "Net losses excluding IBNR (Cols. 1 + 2 - 3)"),
               ("5", "IBNR: direct"), ("6", "IBNR: reinsurance assumed"), ("7", "IBNR: reinsurance ceded"),
               ("8", "Net losses unpaid (Cols. 4 + 5 + 6 - 7)"), ("9", "Net unpaid loss adjustment expenses")]
PART3_COLS = [("1", "Loss adjustment expenses"), ("2", "Other underwriting expenses"), ("3", "Investment expenses"), ("4", "Total")]
NII_COLS = [("1", "Collected during year"), ("2", "Earned during year")]
STATE_COLS = [("1", "Direct premiums written"), ("2", "Direct premiums earned"),
              ("3", "Dividends paid or credited to policyholders on direct business"), ("4", "Direct unearned premium reserves"),
              ("5", "Direct losses paid (deducting salvage)"), ("6", "Direct losses incurred"), ("7", "Direct losses unpaid"),
              ("8", "Direct defense and cost containment expense paid"), ("9", "Direct defense and cost containment expense incurred"),
              ("10", "Direct defense and cost containment expense unpaid"), ("11", "Commissions and brokerage expenses"),
              ("12", "Taxes, licenses and fees")]
SCHF3_COLS = [("1", "ID number"), ("2", "NAIC company code"), ("3", "Name of reinsurer"), ("4", "Domiciliary jurisdiction"),
              ("5", "Special code"), ("6", "Reinsurance premiums ceded"), ("7", "Recoverable on paid losses"),
              ("8", "Recoverable on paid LAE"), ("9", "Known case loss reserves"), ("10", "Known case LAE reserves"),
              ("11", "IBNR loss reserves"), ("12", "IBNR LAE reserves"), ("13", "Unearned premiums"), ("14", "Contingent commissions"),
              ("15", "Total recoverable (Cols. 7 through 14)"), ("16", "Ceded balances payable"),
              ("17", "Other amounts due to reinsurers"), ("18", "Net amount recoverable from reinsurers (Cols. 15 - [16 + 17])"),
              ("19", "Funds held by company under reinsurance treaties")]
SCHP1_COLS = [
    ("1", "Premiums earned: direct and assumed"), ("2", "Premiums earned: ceded"), ("3", "Premiums earned: net (1 - 2)"),
    ("4", "Loss payments: direct and assumed"), ("5", "Loss payments: ceded"),
    ("6", "Defense and cost containment payments: direct and assumed"), ("7", "Defense and cost containment payments: ceded"),
    ("8", "Adjusting and other payments"), ("9", "Salvage and subrogation received"),
    ("10", "Total net paid (Cols. 4 - 5 + 6 - 7 + 8)"), ("11", "Number of claims reported: direct and assumed"),
    ("13", "Losses unpaid: case basis direct and assumed"), ("14", "Losses unpaid: case basis ceded"),
    ("15", "Losses unpaid: bulk + IBNR direct and assumed"), ("16", "Losses unpaid: bulk + IBNR ceded"),
    ("17", "Defense and cost containment unpaid: case basis direct and assumed"), ("18", "Defense and cost containment unpaid: case basis ceded"),
    ("19", "Defense and cost containment unpaid: bulk + IBNR direct and assumed"), ("20", "Defense and cost containment unpaid: bulk + IBNR ceded"),
    ("21", "Adjusting and other unpaid"), ("22", "Salvage and subrogation anticipated"),
    ("23", "Total net losses and expenses unpaid"), ("24", "Number of claims outstanding: direct and assumed"),
    ("25", "Total losses and loss expenses incurred: direct and assumed"), ("26", "Total losses and loss expenses incurred: ceded"),
    ("27", "Total losses and loss expenses incurred: net"), ("28", "Loss and LAE percentage: direct and assumed"),
    ("29", "Loss and LAE percentage: ceded"), ("30", "Loss and LAE percentage: net"), ("31", "Nontabular discount: loss"),
    ("32", "Nontabular discount: loss expense"), ("33", "Inter-company pooling participation percentage"),
    ("34", "Net balance sheet reserves after discount: losses unpaid"), ("35", "Net balance sheet reserves after discount: loss expenses unpaid"),
]
AY_ROWS = ["Prior"] + [str(y) for y in range(YEAR - 9, YEAR + 1)] + ["Totals"]
DEV_COLS = [(str(i + 1), f"Valued 12/31/{YEAR - 9 + i}") for i in range(10)]
SCHP2_COLS = DEV_COLS + [("11", "One-year development"), ("12", "Two-year development")]
SCHP3_COLS = DEV_COLS + [("11", "Number of claims closed with loss payment"), ("12", "Number of claims closed without loss payment")]

PAGES = [
    # code, name, page ref, group, lines, columns, source
    ("P2", "Assets", "Page 2", "Financial statements", ASSETS, COLS_BS_ASSETS, NAIC),
    ("P3", "Liabilities, surplus and other funds", "Page 3", "Financial statements", LIABILITIES, CY_PY, NAIC),
    ("P4", "Statement of income", "Page 4", "Financial statements", INCOME, CY_PY, NAIC),
    ("P5", "Cash flow", "Page 5", "Financial statements", CASH_FLOW, CY_PY, NAIC),
    ("U1", "UIE Part 1 - Premiums earned", "Page 6", "Underwriting and investment exhibit", "ASL", PART1_COLS, NAIC),
    ("U1A", "UIE Part 1A - Recapitulation of all premiums", "Page 7", "Underwriting and investment exhibit", "ASL", PART1A_COLS, NAIC),
    ("U1B", "UIE Part 1B - Premiums written", "Page 8", "Underwriting and investment exhibit", "ASL", PART1B_COLS, NAIC),
    ("U2", "UIE Part 2 - Losses paid and incurred", "Page 9", "Underwriting and investment exhibit", "ASL", PART2_COLS, NAIC),
    ("U2A", "UIE Part 2A - Unpaid losses and loss adjustment expenses", "Page 10", "Underwriting and investment exhibit", "ASL", PART2A_COLS, NAIC),
    ("U3", "UIE Part 3 - Expenses", "Page 11", "Underwriting and investment exhibit", EXPENSES, PART3_COLS, NAIC),
    ("NII", "Exhibit of net investment income", "Page 12", "Underwriting and investment exhibit", NII, NII_COLS, NAIC),
    ("H5", "Five-year historical data", "Page 17", "Exhibits", FIVE_YEAR, FIVE_COLS, OUTLINE),
    ("SP", "Exhibit of premiums and losses (statutory page 14, by state)", "Page 19", "Exhibits", "ASL", STATE_COLS, OUTLINE),
    ("SF3", "Schedule F Part 3 - Ceded reinsurance", "Schedule F", "Schedule F", "REINSURER", SCHF3_COLS, OUTLINE),
]
for _code, _name in [("SUM", "Summary")] + SCHED_P_LINES:
    PAGES.append((f"SP1{_code}", f"Schedule P Part 1{_code if _code != 'SUM' else ''} - {_name}", "Schedule P", "Schedule P",
                  "AY", SCHP1_COLS, OUTLINE))
    PAGES.append((f"SP2{_code}", f"Schedule P Part 2{_code if _code != 'SUM' else ''} - {_name}: incurred net losses and DCC",
                  "Schedule P", "Schedule P", "AYDEV", SCHP2_COLS, OUTLINE))
    PAGES.append((f"SP3{_code}", f"Schedule P Part 3{_code if _code != 'SUM' else ''} - {_name}: cumulative paid net losses and DCC",
                  "Schedule P", "Schedule P", "AYDEV", SCHP3_COLS, OUTLINE))


def _cell_exists(spec, line_no: str, col: str, col_caption: str) -> bool:
    """Development triangles have no cell for a valuation before the accident year (shaded in the blank)."""
    if spec != "AYDEV" or not line_no.isdigit() or not col_caption.startswith("Valued"):
        return True
    return int(col_caption[-4:]) >= int(line_no)


def _lines_for(spec):
    if spec == "ASL":
        return [(c, n, "T" if c == "35" else "D") for c, n, _ in ASL]
    if spec == "AYDEV":
        return [(r, "Prior years" if r == "Prior" else f"Accident year {r}", "D") for r in AY_ROWS[:-1]]
    if spec == "AY":
        return [(r, "Prior years" if r == "Prior" else ("Totals" if r == "Totals" else f"Accident year {r}"),
                 "T" if r == "Totals" else "D") for r in AY_ROWS]
    if spec == "REINSURER":
        return [("R", "One row per reinsurer (affiliates, U.S. non-affiliates, pools, other non-U.S.)", "D"),
                ("T", "Totals", "T")]
    return spec


def pages() -> pd.DataFrame:
    rows = []
    for code, name, ref, group, lines, cols, src in PAGES:
        ln = _lines_for(lines)
        n = sum(1 for x in ln if x[2] != "H" for c, cap in cols if _cell_exists(lines, x[0], c, cap))
        rows.append({"page_code": code, "page_name": name, "page_ref": ref, "page_group": group, "line_count": len(ln),
                     "col_count": len(cols), "field_count": n, "source": src})
    return pd.DataFrame(rows)


def lines() -> pd.DataFrame:
    rows = []
    for code, _n, _r, _g, spec, _c, _s in PAGES:
        for seq, (no, cap, kind) in enumerate(_lines_for(spec), 1):
            rows.append({"page_code": code, "line_no": no, "seq": seq, "caption": cap, "line_kind": kind})
    return pd.DataFrame(rows)


def columns() -> pd.DataFrame:
    return pd.DataFrame([{"page_code": code, "col_no": c, "seq": i, "caption": cap}
                         for code, _n, _r, _g, _l, cols, _s in PAGES for i, (c, cap) in enumerate(cols, 1)])


def field_id(page: str, line: str, col: str) -> str:
    return f"{page}.L{line}.C{col}"


def fields() -> pd.DataFrame:
    """Every reportable cell of the Yellow Book: page × line × column (heading lines carry no value)."""
    out = []
    for code, pname, ref, group, spec, cols, src in PAGES:
        for no, cap, kind in _lines_for(spec):
            if kind == "H":
                continue
            for c, ccap in cols:
                if not _cell_exists(spec, no, c, ccap):
                    continue
                dtype = "percent" if ("percentage" in ccap.lower() or code == "H5" and no in {"37", "38", "39", "40", "41", "42", "43", "44", "46", "48"}) \
                    else ("count" if "number of" in ccap.lower() else
                          ("text" if code == "SF3" and c in {"1", "2", "3", "4", "5"} else "amount"))
                out.append({"field_id": field_id(code, no, c), "page_code": code, "page_name": pname, "page_ref": ref,
                            "page_group": group, "line_no": no, "line_caption": cap, "col_no": c, "col_caption": ccap,
                            "line_kind": kind, "data_type": dtype, "source": src})
    return pd.DataFrame(out)


def asl() -> pd.DataFrame:
    return pd.DataFrame(ASL, columns=["asl_code", "asl_name", "sched_p_line"])


def summary() -> dict:
    f = fields()
    return {"pages": len(PAGES), "lines": len(lines()), "columns": len(columns()), "fields": len(f),
            "verified_fields": int((f.source == NAIC).sum()), "asl_lines": len(ASL) - 1, "sched_p_lines": len(SCHED_P_LINES)}
