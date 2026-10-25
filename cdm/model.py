"""SI² Commercial Lines model: ONE governed definition that generates both the CDM and the ontology.

Lines: Commercial Property (CP), Workers' Compensation (WC), General Liability (GL), Commercial Auto (CA).
Everything that varies is scoped by the context key:
    country · state · company · line · lob · product · object · module · effective_from · effective_to
'*' means "all" (countrywide, every company ...). The most specific matching row wins.

All codes, rates and data are illustrative. Bureau class codes and forms belong to their owners (ISO, NCCI, ACORD);
verify against the manuals your company licenses.
"""
from __future__ import annotations

KEY = ["country", "state", "company", "line", "lob", "product", "object", "module", "effective_from", "effective_to"]
KEY_DOC = [
    ("country", "Country of the risk or contract", "US, CA (Canada), GB", "Laws, currency, address format and which lines exist (no private workers' comp in Canada; employers' liability compulsory in Great Britain)."),
    ("state", "State, province or territory", "FL, TX, CA, NY, NJ, PA, OH, WA, ON ...", "Filed rates, forms, mandatory coverages, bureaus. Most variation lives here."),
    ("company", "Writing company / paper", "SI2-ADM (admitted), SI2-ES (excess & surplus)", "Admitted paper follows filed rates and forms; E&S adds surplus lines tax and stamping fees and is not rate-filed in most states."),
    ("line", "Personal or commercial line", "Commercial", "Separates personal from commercial vocabularies."),
    ("lob", "Line of business", "CP, WC, GL, CA", "Which coverages, objects and rating apply."),
    ("product", "Product and form edition", "CP-Std 2025, GL-Contractors 2025 ...", "Products change by edition; old policies keep the edition they were written on."),
    ("object", "Risk object the element describes", "Location, Building, Vehicle, Driver, Class, Coverage, Party", "An element belongs to one object, wherever it is used."),
    ("module", "Where the element is used", "Policy, Billing, Claims, Reinsurance, Finance, Reporting", "Same meaning in every module; applicability and requiredness can differ."),
    ("effective_from / effective_to", "Effective dates", "2025-01-01 .. 9999-12-31", "Nothing is deleted: a change ends one row and starts another."),
]
LOBS = {"CP": "Commercial Property", "WC": "Workers' Compensation", "GL": "General Liability", "CA": "Commercial Auto"}
COMPANIES = {"SI2-ADM": "SI² Insurance Company (admitted)", "SI2-ES": "SI² Specialty Insurance Company (excess & surplus lines)"}

# ------------------------------------------------------------------------------------------ objects (CDM entities / ontology classes)
# code, name, parent object, definition, key attribute
OBJECTS = [
    ("Party", "Party", None, "A person or organization in any role: named insured, additional insured, producer, claimant, employer.", "party_id"),
    ("Producer", "Producer", "Party", "Agency or broker that places the business.", "producer_code"),
    ("Policy", "Policy", None, "The contract: one term of coverage for one or more lines.", "policy_number"),
    ("PolicyTransaction", "Policy transaction", "Policy", "New business, endorsement, cancellation, reinstatement, renewal or audit.", "transaction_id"),
    ("Location", "Location", None, "An insured premises address.", "location_id"),
    ("Building", "Building", "Location", "A structure at a location (Commercial Property).", "building_id"),
    ("Coverage", "Coverage", None, "A coverage on the policy with its limits and deductibles.", "coverage_id"),
    ("Classification", "Rating classification", None, "A rating class with its exposure: WC class payroll, GL class exposure.", "class_id"),
    ("Vehicle", "Vehicle", None, "A covered auto (Commercial Auto).", "vehicle_id"),
    ("Driver", "Driver", "Party", "A person who drives covered autos.", "driver_id"),
    ("StateCoverage", "Workers' comp state", None, "A state covered under Part One (3.A) or Other States (3.C).", "state_coverage_id"),
    ("Premium", "Premium", None, "Premium by coverage, state and transaction.", "premium_id"),
    ("Claim", "Claim", None, "A reported loss.", "claim_number"),
    ("ClaimFinancial", "Claim financial transaction", "Claim", "Payment, recovery or reserve change.", "claim_txn_id"),
    ("BillingAccount", "Billing account", None, "Account that receives invoices and payments.", "billing_account_id"),
    ("Cession", "Reinsurance cession", None, "Premium and loss ceded under a treaty.", "cession_id"),
]
RELATIONS = [  # child, relation, parent, cardinality
    ("Policy", "hasNamedInsured", "Party", "1..*"), ("Policy", "placedBy", "Producer", "1"),
    ("PolicyTransaction", "amends", "Policy", "1"), ("Location", "insuredUnder", "Policy", "1"),
    ("Building", "locatedAt", "Location", "1"), ("Coverage", "partOf", "Policy", "1"),
    ("Coverage", "covers", "Building", "0..1"), ("Coverage", "covers", "Vehicle", "0..1"),
    ("Classification", "ratedUnder", "Coverage", "1"), ("Classification", "atLocation", "Location", "0..1"),
    ("Vehicle", "insuredUnder", "Policy", "1"), ("Driver", "drives", "Vehicle", "0..*"),
    ("StateCoverage", "partOf", "Policy", "1"), ("Premium", "chargedFor", "Coverage", "1"),
    ("Claim", "reportedUnder", "Policy", "1"), ("Claim", "involves", "Coverage", "1..*"),
    ("ClaimFinancial", "postedTo", "Claim", "1"), ("BillingAccount", "bills", "Policy", "1..*"),
    ("Cession", "cedes", "Premium", "0..*"), ("Cession", "cedes", "ClaimFinancial", "0..*"),
]

# ------------------------------------------------------------------------------------------ pick lists
PICKLISTS = {
    "LOB": ("Line of business", [("CP", "Commercial Property"), ("WC", "Workers' Compensation"), ("GL", "General Liability"), ("CA", "Commercial Auto")]),
    "TXN_TYPE": ("Transaction type", [("NB", "New business"), ("EN", "Endorsement"), ("CN", "Cancellation"), ("RI", "Reinstatement"), ("RN", "Renewal"), ("AU", "Premium audit")]),
    "ENTITY_TYPE": ("Legal entity type", [("CORP", "Corporation"), ("LLC", "Limited liability company"), ("PART", "Partnership"), ("IND", "Individual / sole proprietor"), ("NFP", "Not-for-profit")]),
    "CONSTRUCTION": ("Construction class", [("1", "Frame"), ("2", "Joisted masonry"), ("3", "Non-combustible"), ("4", "Masonry non-combustible"), ("5", "Modified fire resistive"), ("6", "Fire resistive")]),
    "PROTECTION_CLASS": ("Public protection class", [(str(i), f"Class {i}") for i in range(1, 11)]),
    "SPRINKLER": ("Sprinkler protection", [("FULL", "Fully sprinklered"), ("PART", "Partially sprinklered"), ("NONE", "None")]),
    "CAUSES_OF_LOSS": ("Causes of loss form", [("BASIC", "Basic"), ("BROAD", "Broad"), ("SPECIAL", "Special")]),
    "VALUATION": ("Valuation", [("RC", "Replacement cost"), ("ACV", "Actual cash value"), ("AGREED", "Agreed value")]),
    "COINSURANCE": ("Coinsurance", [("80", "80%"), ("90", "90%"), ("100", "100%")]),
    "DEDUCTIBLE_TYPE": ("Deductible type", [("FLAT", "Flat amount"), ("WIND_PCT", "Named storm / windstorm % of value"), ("EQ_PCT", "Earthquake % of value"), ("HAIL_PCT", "Wind / hail % of value")]),
    "WC_CLASS": ("Workers' comp classification (illustrative)", [("8810", "Clerical office employees"), ("8742", "Outside salespersons"), ("5645", "Carpentry - residential"), ("7219", "Trucking - local hauling"), ("9015", "Building operations"), ("5183", "Plumbing")]),
    "WC_PART3": ("Workers' comp state coverage", [("3A", "Part One - states listed in Item 3.A"), ("3C", "Other states insurance - Item 3.C")]),
    "WC_BUREAU": ("Workers' comp rating / data bureau", [("NCCI", "NCCI"), ("WCIRB", "WCIRB (California)"), ("NYCIRB", "NYCIRB (New York)"), ("NJCRIB", "NJCRIB (New Jersey)"), ("PCRB", "PCRB (Pennsylvania)"), ("STATE_FUND", "Monopolistic state fund")]),
    "GL_PREMIUM_BASIS": ("General liability premium basis", [("PAYROLL", "Payroll (per $1,000)"), ("SALES", "Gross sales (per $1,000)"), ("AREA", "Area (per 1,000 sq ft)"), ("UNITS", "Units"), ("COST", "Total cost (per $1,000)")]),
    "GL_FORM": ("General liability coverage form", [("OCC", "Occurrence"), ("CM", "Claims-made")]),
    "GL_CLASS": ("General liability classification (illustrative)", [("CONTR-CARP", "Carpentry contractor"), ("CONTR-PLUMB", "Plumbing contractor"), ("RETAIL", "Retail store"), ("RESTAURANT", "Restaurant"), ("OFFICE", "Office building occupancy"), ("MFG-LIGHT", "Light manufacturing")]),
    "VEHICLE_TYPE": ("Commercial vehicle type", [("PPT", "Private passenger type"), ("LT", "Light truck (≤10,000 lbs GVW)"), ("MT", "Medium truck (10,001-20,000)"), ("HT", "Heavy truck (20,001-45,000)"), ("XHT", "Extra-heavy truck (>45,000)"), ("TRAC", "Truck-tractor")]),
    "RADIUS": ("Radius of operation", [("LOCAL", "Local (up to 50 miles)"), ("INTERMEDIATE", "Intermediate (51-200 miles)"), ("LONG", "Long distance (over 200 miles)")]),
    "VEHICLE_USE": ("Vehicle use", [("SERVICE", "Service"), ("RETAIL", "Retail"), ("COMMERCIAL", "Commercial")]),
    "AUTO_SYMBOL": ("Covered auto symbol", [("1", "Any auto"), ("2", "Owned autos only"), ("7", "Specifically described autos"), ("8", "Hired autos only"), ("9", "Non-owned autos only")]),
    "CLAIM_STATUS": ("Claim status", [("OPEN", "Open"), ("CLOSED", "Closed"), ("REOPEN", "Reopened")]),
    "CAUSE_OF_LOSS": ("Cause of loss", [("FIRE", "Fire"), ("WIND", "Windstorm / hurricane"), ("HAIL", "Hail"), ("WATER", "Water damage"), ("THEFT", "Theft"), ("COLL", "Collision"), ("BI", "Bodily injury"), ("PD", "Property damage"), ("INJURY", "Workplace injury"), ("EQ", "Earthquake")]),
    "PAYMENT_PLAN": ("Payment plan", [("PIF", "Paid in full"), ("QTR", "Quarterly"), ("MON", "Monthly"), ("AUDIT", "Reporting / audit basis")]),
    "ADDRESS_FORMAT": ("Postal code format", [("ZIP", "US ZIP / ZIP+4"), ("CA_PC", "Canadian postal code (A1A 1A1)"), ("UK_PC", "UK postcode")]),
}
# option-level applicability (only where an option does not apply everywhere): (picklist, option, scope dict)
OPTION_SCOPES = [
    ("DEDUCTIBLE_TYPE", "WIND_PCT", {"country": "US", "state": "FL"}), ("DEDUCTIBLE_TYPE", "WIND_PCT", {"country": "US", "state": "TX"}),
    ("DEDUCTIBLE_TYPE", "WIND_PCT", {"country": "US", "state": "NC"}), ("DEDUCTIBLE_TYPE", "WIND_PCT", {"country": "US", "state": "SC"}),
    ("DEDUCTIBLE_TYPE", "EQ_PCT", {"country": "US", "state": "CA"}), ("DEDUCTIBLE_TYPE", "HAIL_PCT", {"country": "US", "state": "TX"}),
    ("DEDUCTIBLE_TYPE", "HAIL_PCT", {"country": "US", "state": "CO"}),
    ("WC_BUREAU", "WCIRB", {"country": "US", "state": "CA"}), ("WC_BUREAU", "NYCIRB", {"country": "US", "state": "NY"}),
    ("WC_BUREAU", "NJCRIB", {"country": "US", "state": "NJ"}), ("WC_BUREAU", "PCRB", {"country": "US", "state": "PA"}),
    ("WC_BUREAU", "STATE_FUND", {"country": "US", "state": "OH"}), ("WC_BUREAU", "STATE_FUND", {"country": "US", "state": "WA"}),
    ("WC_BUREAU", "STATE_FUND", {"country": "US", "state": "ND"}), ("WC_BUREAU", "STATE_FUND", {"country": "US", "state": "WY"}),
    ("ADDRESS_FORMAT", "ZIP", {"country": "US"}), ("ADDRESS_FORMAT", "CA_PC", {"country": "CA"}), ("ADDRESS_FORMAT", "UK_PC", {"country": "GB"}),
]

# ------------------------------------------------------------------------------------------ elements
# code, name, object, data type, pick list, definition, synonyms (as seen in source systems), lobs ('*' = all), modules
E = [
    # policy and party
    ("POLICY_NUMBER", "Policy number", "Policy", "TEXT", None, "Identifier of the policy term.", ["POL_NO", "PolicyNumber", "policy_num", "PM-POLICY-NO"], "*", "Policy,Billing,Claims,Reinsurance,Finance,Reporting"),
    ("POLICY_EFFECTIVE_DATE", "Policy effective date", "Policy", "DATE", None, "Date the policy term starts.", ["EFF_DT", "PeriodStart", "inception_date"], "*", "Policy,Billing,Claims,Reporting"),
    ("POLICY_EXPIRATION_DATE", "Policy expiration date", "Policy", "DATE", None, "Date the policy term ends.", ["EXP_DT", "PeriodEnd"], "*", "Policy,Billing,Claims,Reporting"),
    ("LINE_OF_BUSINESS", "Line of business", "Policy", "CODE", "LOB", "Line of business of the coverage part.", ["LOB_CD", "LineCode", "Coverage part"], "*", "Policy,Billing,Claims,Reinsurance,Finance,Reporting"),
    ("WRITING_COMPANY", "Writing company", "Policy", "CODE", None, "Company whose paper the policy is written on (company key).", ["CO_CD", "UnderwritingCompany", "Paper"], "*", "Policy,Billing,Finance,Reporting"),
    ("PRODUCT_CODE", "Product and edition", "Policy", "CODE", None, "Product and form edition (product key).", ["PROD_CD", "ProductCode", "Program"], "*", "Policy,Reporting"),
    ("TRANSACTION_TYPE", "Transaction type", "PolicyTransaction", "CODE", "TXN_TYPE", "Kind of policy transaction.", ["TRANS_CD", "JobType"], "*", "Policy,Billing,Reporting"),
    ("TRANSACTION_EFFECTIVE_DATE", "Transaction effective date", "PolicyTransaction", "DATE", None, "Date the transaction takes effect.", ["TRANS_EFF_DT", "EditEffectiveDate"], "*", "Policy,Billing,Reporting"),
    ("NAMED_INSURED_NAME", "Named insured name", "Party", "TEXT", None, "Legal name of the first named insured.", ["INSD_NAME", "PrimaryNamedInsured", "Applicant name"], "*", "Policy,Billing,Claims"),
    ("FEIN", "Federal employer ID number", "Party", "TEXT", None, "Employer tax identifier (masked outside authorized roles).", ["FEIN", "TaxID", "EIN"], "*", "Policy,Billing,Reporting"),
    ("LEGAL_ENTITY_TYPE", "Legal entity type", "Party", "CODE", "ENTITY_TYPE", "Legal form of the named insured.", ["ENT_TYPE", "OrganizationType"], "*", "Policy"),
    ("NAICS_CODE", "NAICS code", "Party", "CODE", None, "Industry classification of the insured's business.", ["NAICS", "IndustryCode", "SIC"], "*", "Policy,Reporting"),
    ("PRODUCER_CODE", "Producer code", "Producer", "CODE", None, "Agency / broker code.", ["AGT_NO", "ProducerCode", "Agency number"], "*", "Policy,Billing,Finance"),
    ("COMMISSION_RATE", "Commission rate", "Producer", "PERCENT", None, "Commission percentage paid to the producer.", ["COMM_PCT", "CommissionRate"], "*", "Billing,Finance"),
    ("SURPLUS_LINES_TAX", "Surplus lines tax", "Premium", "AMOUNT", None, "Premium tax on excess and surplus lines business.", ["SL_TAX", "SurplusLinesTax"], "*", "Policy,Billing,Finance"),
    ("STAMPING_FEE", "Stamping office fee", "Premium", "AMOUNT", None, "Fee charged by a state surplus lines stamping office.", ["STAMP_FEE"], "*", "Policy,Billing,Finance"),
    ("WRITTEN_PREMIUM", "Written premium", "Premium", "AMOUNT", None, "Premium written by the transaction.", ["WRT_PREM", "TransactionPremium", "PM-WRITTEN-PREM"], "*", "Policy,Billing,Reinsurance,Finance,Reporting"),
    ("PAYMENT_PLAN", "Payment plan", "BillingAccount", "CODE", "PAYMENT_PLAN", "How premium is billed.", ["PAY_PLAN", "BillingPlan"], "*", "Billing"),
    # location and property
    ("LOCATION_ADDRESS", "Location address", "Location", "TEXT", None, "Street address of the premises.", ["LOC_ADDR", "AddressLine1"], "*", "Policy,Claims"),
    ("STATE", "State / province", "Location", "CODE", None, "State or province of the location (state key).", ["ST", "State", "Jurisdiction"], "*", "Policy,Billing,Claims,Reporting"),
    ("POSTAL_CODE", "Postal code", "Location", "TEXT", "ADDRESS_FORMAT", "ZIP or postal code; format by country.", ["ZIP", "PostalCode"], "*", "Policy,Claims,Reporting"),
    ("TERRITORY", "Rating territory", "Location", "CODE", None, "Rating territory derived from the address.", ["TERR", "TerritoryCode"], "CP,GL,CA", "Policy,Reporting"),
    ("CONSTRUCTION_CLASS", "Construction class", "Building", "CODE", "CONSTRUCTION", "Fire-resistance class of the building.", ["CONST_CD", "ConstructionType"], "CP", "Policy,Reporting"),
    ("YEAR_BUILT", "Year built", "Building", "INTEGER", None, "Year the building was constructed.", ["YR_BUILT", "YearBuilt"], "CP", "Policy"),
    ("ROOF_YEAR", "Roof year", "Building", "INTEGER", None, "Year the roof was last replaced.", ["ROOF_YR", "RoofUpdateYear"], "CP", "Policy,Claims"),
    ("SQUARE_FEET", "Square feet", "Building", "INTEGER", None, "Total floor area.", ["SQ_FT", "Area"], "CP,GL", "Policy"),
    ("STORIES", "Number of stories", "Building", "INTEGER", None, "Stories above grade.", ["NUM_STORIES"], "CP", "Policy"),
    ("PROTECTION_CLASS", "Public protection class", "Building", "CODE", "PROTECTION_CLASS", "Fire protection class of the community.", ["PPC", "FireProtectionClass"], "CP", "Policy,Reporting"),
    ("SPRINKLER", "Sprinkler protection", "Building", "CODE", "SPRINKLER", "Automatic sprinkler protection.", ["SPRK_IND", "Sprinklered"], "CP", "Policy"),
    ("BUILDING_LIMIT", "Building limit", "Coverage", "AMOUNT", None, "Limit of insurance for the building.", ["BLDG_LMT", "BuildingLimit"], "CP", "Policy,Claims,Reinsurance"),
    ("BPP_LIMIT", "Business personal property limit", "Coverage", "AMOUNT", None, "Limit for business personal property.", ["BPP_LMT", "ContentsLimit"], "CP", "Policy,Claims,Reinsurance"),
    ("BUSINESS_INCOME_LIMIT", "Business income limit", "Coverage", "AMOUNT", None, "Limit for business income and extra expense.", ["BI_LMT", "TimeElement"], "CP", "Policy,Claims"),
    ("CAUSES_OF_LOSS_FORM", "Causes of loss form", "Coverage", "CODE", "CAUSES_OF_LOSS", "Perils insured.", ["COL_FORM", "PerilForm"], "CP", "Policy,Claims"),
    ("VALUATION", "Valuation", "Coverage", "CODE", "VALUATION", "How a loss is valued.", ["VAL_CD", "ValuationMethod"], "CP", "Policy,Claims"),
    ("COINSURANCE", "Coinsurance", "Coverage", "CODE", "COINSURANCE", "Coinsurance percentage.", ["COINS_PCT"], "CP", "Policy,Claims"),
    ("DEDUCTIBLE_TYPE", "Deductible type", "Coverage", "CODE", "DEDUCTIBLE_TYPE", "Kind of deductible.", ["DED_TYPE"], "CP", "Policy,Claims"),
    ("DEDUCTIBLE_AMOUNT", "Deductible amount", "Coverage", "AMOUNT", None, "Flat deductible.", ["DED_AMT", "Deductible"], "CP,CA,GL", "Policy,Claims"),
    ("WIND_DEDUCTIBLE_PCT", "Named storm / windstorm deductible %", "Coverage", "PERCENT", None, "Percentage deductible for windstorm or named storm.", ["WIND_DED", "HurricaneDeductible"], "CP", "Policy,Claims"),
    ("EQ_DEDUCTIBLE_PCT", "Earthquake deductible %", "Coverage", "PERCENT", None, "Percentage deductible for earthquake.", ["EQ_DED"], "CP", "Policy,Claims"),
    ("FLOOD_ZONE", "Flood zone", "Location", "CODE", None, "FEMA flood zone.", ["FLD_ZONE", "FloodZone"], "CP", "Policy,Reinsurance"),
    # workers comp
    ("WC_CLASS_CODE", "WC classification code", "Classification", "CODE", "WC_CLASS", "Workers' comp class for the payroll.", ["CLASS_CD", "ClassCode", "WCClass"], "WC", "Policy,Reporting"),
    ("ESTIMATED_PAYROLL", "Estimated annual payroll", "Classification", "AMOUNT", None, "Remuneration estimated for the class.", ["EST_PAYROLL", "BasisAmount"], "WC,GL", "Policy,Billing,Reporting"),
    ("AUDITED_PAYROLL", "Audited payroll", "Classification", "AMOUNT", None, "Remuneration found at premium audit.", ["AUD_PAYROLL"], "WC,GL", "Policy,Billing,Reporting"),
    ("EXPERIENCE_MOD", "Experience modification", "StateCoverage", "DECIMAL", None, "Experience rating modification factor.", ["EMOD", "ExpMod", "XMOD"], "WC", "Policy,Reporting"),
    ("WC_PART3_TYPE", "State coverage type", "StateCoverage", "CODE", "WC_PART3", "Whether the state is listed in 3.A or covered under 3.C.", ["ITEM3"], "WC", "Policy"),
    ("WC_BUREAU", "WC rating / data bureau", "StateCoverage", "CODE", "WC_BUREAU", "Bureau that governs the state's classes and statistical reporting.", ["BUREAU"], "WC", "Policy,Reporting"),
    ("EL_LIMIT_EACH_ACCIDENT", "Employers liability - each accident", "Coverage", "AMOUNT", None, "Part Two limit per accident.", ["EL_ACC"], "WC", "Policy,Claims"),
    ("EL_LIMIT_DISEASE_POLICY", "Employers liability - disease policy limit", "Coverage", "AMOUNT", None, "Part Two disease policy limit.", ["EL_DIS_POL"], "WC", "Policy,Claims"),
    ("EL_LIMIT_DISEASE_EMPLOYEE", "Employers liability - disease each employee", "Coverage", "AMOUNT", None, "Part Two disease limit per employee.", ["EL_DIS_EE"], "WC", "Policy,Claims"),
    ("FULL_TIME_EMPLOYEES", "Number of full-time employees", "Classification", "INTEGER", None, "Employees in the class.", ["NUM_EE"], "WC", "Policy"),
    # general liability
    ("GL_CLASS_CODE", "GL classification", "Classification", "CODE", "GL_CLASS", "General liability rating class.", ["GL_CLASS", "ClassCode"], "GL", "Policy,Reporting"),
    ("GL_PREMIUM_BASIS", "Premium basis", "Classification", "CODE", "GL_PREMIUM_BASIS", "Exposure basis for the class.", ["PREM_BASIS"], "GL", "Policy,Billing,Reporting"),
    ("GL_EXPOSURE", "Exposure amount", "Classification", "AMOUNT", None, "Exposure in the premium basis.", ["EXPOSURE", "BasisAmount"], "GL", "Policy,Billing,Reporting"),
    ("GL_COVERAGE_FORM", "Coverage form", "Coverage", "CODE", "GL_FORM", "Occurrence or claims-made.", ["CGL_FORM"], "GL", "Policy,Claims,Reporting"),
    ("RETROACTIVE_DATE", "Retroactive date", "Coverage", "DATE", None, "Earliest date of covered injury on claims-made forms.", ["RETRO_DT"], "GL", "Policy,Claims"),
    ("EACH_OCCURRENCE_LIMIT", "Each occurrence limit", "Coverage", "AMOUNT", None, "Most paid for any one occurrence.", ["OCC_LMT", "PerOccurrence"], "GL", "Policy,Claims,Reinsurance"),
    ("GENERAL_AGGREGATE_LIMIT", "General aggregate limit", "Coverage", "AMOUNT", None, "Most paid in the term other than products-completed operations.", ["GEN_AGG"], "GL", "Policy,Claims,Reinsurance"),
    ("PRODUCTS_AGGREGATE_LIMIT", "Products-completed operations aggregate", "Coverage", "AMOUNT", None, "Aggregate for products and completed work.", ["PCO_AGG"], "GL", "Policy,Claims"),
    ("PERSONAL_ADV_INJURY_LIMIT", "Personal and advertising injury limit", "Coverage", "AMOUNT", None, "Limit for personal and advertising injury.", ["PAI_LMT"], "GL", "Policy,Claims"),
    ("SUBCONTRACTOR_COST", "Subcontracted work cost", "Classification", "AMOUNT", None, "Cost of work let to subcontractors (contractors).", ["SUB_COST"], "GL", "Policy,Billing"),
    ("NY_LABOR_LAW_EXPOSURE", "New York Labor Law exposure", "Classification", "BOOLEAN", None, "Whether operations involve elevation or construction work subject to NY Labor Law sections 240/241.", ["NY_LL_240"], "GL", "Policy,Claims"),
    # commercial auto
    ("VIN", "Vehicle identification number", "Vehicle", "TEXT", None, "17-character VIN.", ["VIN", "VehicleIdNumber"], "CA", "Policy,Claims"),
    ("VEHICLE_YEAR", "Model year", "Vehicle", "INTEGER", None, "Vehicle model year.", ["VEH_YR", "ModelYear"], "CA", "Policy"),
    ("VEHICLE_TYPE", "Vehicle type", "Vehicle", "CODE", "VEHICLE_TYPE", "Size class of the vehicle.", ["VEH_TYPE", "VehicleClass"], "CA", "Policy,Reporting"),
    ("GVW", "Gross vehicle weight", "Vehicle", "INTEGER", None, "Gross vehicle weight in pounds.", ["GVW", "GrossWeight"], "CA", "Policy"),
    ("RADIUS_CLASS", "Radius of operation", "Vehicle", "CODE", "RADIUS", "Farthest regular trip distance.", ["RADIUS"], "CA", "Policy,Reporting"),
    ("VEHICLE_USE", "Vehicle use", "Vehicle", "CODE", "VEHICLE_USE", "Business use class.", ["USE_CD"], "CA", "Policy,Reporting"),
    ("GARAGING_ZIP", "Garaging ZIP", "Vehicle", "TEXT", None, "Where the vehicle is principally garaged.", ["GAR_ZIP", "GaragingLocation"], "CA", "Policy,Reporting"),
    ("COST_NEW", "Cost new", "Vehicle", "AMOUNT", None, "Original cost new for physical damage rating.", ["COST_NEW", "StatedAmount"], "CA", "Policy"),
    ("AUTO_SYMBOL", "Covered auto symbol", "Coverage", "CODE", "AUTO_SYMBOL", "Which autos the coverage applies to.", ["SYMBOL"], "CA", "Policy,Claims"),
    ("CA_LIABILITY_LIMIT", "Auto liability combined single limit", "Coverage", "AMOUNT", None, "Combined single limit for liability.", ["CSL", "LiabLimit"], "CA", "Policy,Claims,Reinsurance"),
    ("PIP_LIMIT", "Personal injury protection limit", "Coverage", "AMOUNT", None, "No-fault personal injury protection.", ["PIP_LMT"], "CA", "Policy,Claims"),
    ("UM_LIMIT", "Uninsured motorists limit", "Coverage", "AMOUNT", None, "Uninsured / underinsured motorists limit.", ["UM_LMT", "UMBI"], "CA", "Policy,Claims"),
    ("DRIVER_LICENSE_STATE", "Driver license state", "Driver", "CODE", None, "Licensing state of the driver.", ["DL_ST"], "CA", "Policy"),
    ("DRIVER_MVR_POINTS", "MVR points", "Driver", "INTEGER", None, "Violation points from the motor vehicle record.", ["MVR_PTS"], "CA", "Policy"),
    ("CDL_IND", "Commercial driver's license", "Driver", "BOOLEAN", None, "Driver holds a commercial driver's license.", ["CDL"], "CA", "Policy"),
    # claims, billing, reinsurance, finance
    ("CLAIM_NUMBER", "Claim number", "Claim", "TEXT", None, "Identifier of the claim.", ["CLM_NO", "ClaimNumber"], "*", "Claims,Reinsurance,Finance,Reporting"),
    ("LOSS_DATE", "Date of loss", "Claim", "DATE", None, "Date the loss occurred.", ["LOSS_DT", "LossDate", "Accident date"], "*", "Claims,Reinsurance,Reporting"),
    ("CAUSE_OF_LOSS", "Cause of loss", "Claim", "CODE", "CAUSE_OF_LOSS", "What caused the loss.", ["COL_CD", "LossCause"], "*", "Claims,Reinsurance,Reporting"),
    ("CLAIM_STATUS", "Claim status", "Claim", "CODE", "CLAIM_STATUS", "Open, closed or reopened.", ["CLM_STAT", "State"], "*", "Claims,Reporting"),
    ("PAID_LOSS", "Paid loss", "ClaimFinancial", "AMOUNT", None, "Loss payment amount.", ["PD_LOSS", "PaymentAmount"], "*", "Claims,Reinsurance,Finance,Reporting"),
    ("CASE_RESERVE", "Case reserve", "ClaimFinancial", "AMOUNT", None, "Outstanding reserve on the claim.", ["OS_RSV", "Reserve"], "*", "Claims,Reinsurance,Finance,Reporting"),
    ("INJURED_WORKER_AWW", "Average weekly wage", "Claim", "AMOUNT", None, "Injured worker's average weekly wage (WC).", ["AWW"], "WC", "Claims,Reporting"),
    ("TREATY_ID", "Treaty", "Cession", "CODE", None, "Reinsurance treaty the cession belongs to.", ["TRTY_ID"], "*", "Reinsurance,Finance"),
    ("CEDED_PREMIUM", "Ceded premium", "Cession", "AMOUNT", None, "Premium ceded to reinsurers.", ["CED_PREM"], "*", "Reinsurance,Finance"),
    ("ANNUAL_STATEMENT_LINE", "Annual statement line", "Premium", "CODE", None, "NAIC annual statement line the premium and losses report on.", ["ASL"], "*", "Finance,Reporting"),
]
# required in the base definition (before any scope); scoped applicability rows can still override
BASE_REQUIRED = set("""POLICY_NUMBER POLICY_EFFECTIVE_DATE POLICY_EXPIRATION_DATE LINE_OF_BUSINESS WRITING_COMPANY PRODUCT_CODE
TRANSACTION_TYPE TRANSACTION_EFFECTIVE_DATE NAMED_INSURED_NAME LEGAL_ENTITY_TYPE PRODUCER_CODE WRITTEN_PREMIUM PAYMENT_PLAN
LOCATION_ADDRESS STATE POSTAL_CODE CONSTRUCTION_CLASS YEAR_BUILT SQUARE_FEET PROTECTION_CLASS BUILDING_LIMIT CAUSES_OF_LOSS_FORM
VALUATION COINSURANCE DEDUCTIBLE_TYPE WC_CLASS_CODE ESTIMATED_PAYROLL WC_PART3_TYPE EL_LIMIT_EACH_ACCIDENT EL_LIMIT_DISEASE_POLICY
EL_LIMIT_DISEASE_EMPLOYEE GL_CLASS_CODE GL_PREMIUM_BASIS GL_EXPOSURE GL_COVERAGE_FORM EACH_OCCURRENCE_LIMIT GENERAL_AGGREGATE_LIMIT
PRODUCTS_AGGREGATE_LIMIT VIN VEHICLE_YEAR VEHICLE_TYPE RADIUS_CLASS VEHICLE_USE GARAGING_ZIP AUTO_SYMBOL CA_LIABILITY_LIMIT
DRIVER_LICENSE_STATE CLAIM_NUMBER LOSS_DATE CAUSE_OF_LOSS CLAIM_STATUS PAID_LOSS CASE_RESERVE""".split())
ELEMENTS = [{"element_code": c, "name": n, "object": o, "data_type": t, "pick_list": p, "definition": d,
             "synonyms": s, "lobs": l, "modules": m, "base_required": "Y" if c in BASE_REQUIRED else "N"} for c, n, o, t, p, d, s, l, m in E]

# ------------------------------------------------------------------------------------------ applicability (the key in action)
# element, scope (key parts not listed = '*'), required (Y/N/NA), default, label override, reason
APPLIC = [
    # company key
    ("SURPLUS_LINES_TAX", {"company": "SI2-ES"}, "Y", None, None, "Excess & surplus lines policies pay surplus lines tax."),
    ("SURPLUS_LINES_TAX", {"company": "SI2-ADM"}, "NA", None, None, "Admitted paper does not pay surplus lines tax."),
    ("STAMPING_FEE", {"company": "SI2-ADM"}, "NA", None, None, "Admitted paper has no stamping fee."),
    ("STAMPING_FEE", {"company": "SI2-ES"}, "N", None, None, "Only some states run a stamping office."),
    ("STAMPING_FEE", {"company": "SI2-ES", "state": "TX"}, "Y", None, None, "Texas surplus lines stamping office fee."),
    ("STAMPING_FEE", {"company": "SI2-ES", "state": "NY"}, "Y", None, None, "New York surplus lines stamping fee."),
    ("STAMPING_FEE", {"company": "SI2-ES", "state": "CA"}, "Y", None, None, "California surplus lines stamping fee."),
    # country key
    ("POSTAL_CODE", {"country": "CA"}, "Y", None, "Postal code", "Canadian address format."),
    ("POSTAL_CODE", {"country": "GB"}, "Y", None, "Postcode", "UK address format."),
    ("STATE", {"country": "CA"}, "Y", None, "Province", "Canada uses provinces."),
    ("STATE", {"country": "GB"}, "N", None, "County", "Great Britain has no states."),
    ("WC_CLASS_CODE", {"country": "CA", "lob": "WC"}, "NA", None, None, "Workers' compensation in Canada is provided by provincial boards, not private insurers."),
    ("FEIN", {"country": "CA"}, "NA", None, "Business number", "Canada uses a CRA business number instead of FEIN."),
    ("EL_LIMIT_EACH_ACCIDENT", {"country": "GB", "lob": "WC"}, "Y", "5000000", "Employers' liability limit", "Employers' liability is compulsory in Great Britain."),
    # state key: property
    ("WIND_DEDUCTIBLE_PCT", {"state": "FL", "lob": "CP"}, "Y", "2", "Hurricane deductible %", "Florida coastal property carries a hurricane percentage deductible."),
    ("WIND_DEDUCTIBLE_PCT", {"state": "TX", "lob": "CP"}, "Y", "2", "Windstorm and hail deductible %", "Texas coastal and hail exposure."),
    ("WIND_DEDUCTIBLE_PCT", {"lob": "CP"}, "N", None, None, "Optional elsewhere."),
    ("EQ_DEDUCTIBLE_PCT", {"state": "CA", "lob": "CP"}, "Y", "10", None, "Earthquake coverage in California carries a percentage deductible."),
    ("EQ_DEDUCTIBLE_PCT", {"lob": "CP"}, "N", None, None, "Optional elsewhere."),
    ("FLOOD_ZONE", {"state": "FL", "lob": "CP"}, "Y", None, None, "Required for Florida property underwriting and catastrophe modeling."),
    ("ROOF_YEAR", {"lob": "CP"}, "Y", None, None, "Roof age drives eligibility and wind / hail rating."),
    # state key: workers comp
    ("WC_CLASS_CODE", {"state": "OH", "lob": "WC"}, "NA", None, None, "Ohio is a monopolistic state fund state: no private workers' comp (stop-gap employers liability only)."),
    ("WC_CLASS_CODE", {"state": "WA", "lob": "WC"}, "NA", None, None, "Washington is a monopolistic state fund state."),
    ("WC_CLASS_CODE", {"state": "ND", "lob": "WC"}, "NA", None, None, "North Dakota is a monopolistic state fund state."),
    ("WC_CLASS_CODE", {"state": "WY", "lob": "WC"}, "NA", None, None, "Wyoming is a monopolistic state fund state."),
    ("WC_BUREAU", {"state": "CA", "lob": "WC"}, "Y", "WCIRB", None, "California classes and statistical reporting follow the WCIRB."),
    ("WC_BUREAU", {"state": "NY", "lob": "WC"}, "Y", "NYCIRB", None, "New York follows the NYCIRB."),
    ("WC_BUREAU", {"state": "NJ", "lob": "WC"}, "Y", "NJCRIB", None, "New Jersey follows the NJCRIB."),
    ("WC_BUREAU", {"state": "PA", "lob": "WC"}, "Y", "PCRB", None, "Pennsylvania follows the PCRB."),
    ("WC_BUREAU", {"state": "OH", "lob": "WC"}, "Y", "STATE_FUND", None, "Ohio Bureau of Workers' Compensation (monopolistic)."),
    ("WC_BUREAU", {"state": "WA", "lob": "WC"}, "Y", "STATE_FUND", None, "Washington Department of Labor & Industries (monopolistic)."),
    ("WC_BUREAU", {"lob": "WC"}, "Y", "NCCI", None, "NCCI states."),
    ("EXPERIENCE_MOD", {"lob": "WC"}, "Y", "1.00", None, "Experience rating applies when the risk qualifies."),
    # state key: GL
    ("NY_LABOR_LAW_EXPOSURE", {"state": "NY", "lob": "GL"}, "Y", None, None, "Contractors in New York must answer the Labor Law 240/241 exposure question."),
    ("NY_LABOR_LAW_EXPOSURE", {"lob": "GL"}, "NA", None, None, "Not applicable outside New York."),
    ("RETROACTIVE_DATE", {"lob": "GL", "product": "GL-ClaimsMade 2025"}, "Y", None, None, "Required on claims-made forms."),
    ("RETROACTIVE_DATE", {"lob": "GL"}, "NA", None, None, "Not used on occurrence forms."),
    # state key: commercial auto
    ("PIP_LIMIT", {"state": "FL", "lob": "CA"}, "Y", "10000", None, "Florida no-fault personal injury protection."),
    ("PIP_LIMIT", {"state": "NY", "lob": "CA"}, "Y", "50000", None, "New York no-fault (basic economic loss)."),
    ("PIP_LIMIT", {"state": "MI", "lob": "CA"}, "Y", None, None, "Michigan no-fault."),
    ("PIP_LIMIT", {"state": "NJ", "lob": "CA"}, "Y", None, None, "New Jersey no-fault."),
    ("PIP_LIMIT", {"lob": "CA"}, "NA", None, None, "Not a no-fault state."),
    ("UM_LIMIT", {"lob": "CA"}, "Y", None, None, "Uninsured motorists is offered in every state; rejection must be documented where allowed."),
    ("CDL_IND", {"lob": "CA", "object": "Driver"}, "Y", None, None, "Needed for heavy and extra-heavy trucks."),
    # module key
    ("FEIN", {"module": "Claims"}, "NA", None, None, "Claims does not need the FEIN (data minimization)."),
    ("INJURED_WORKER_AWW", {"lob": "WC", "module": "Claims"}, "Y", None, None, "Indemnity benefits are computed from the average weekly wage."),
    ("ANNUAL_STATEMENT_LINE", {"module": "Finance"}, "Y", None, None, "Every premium and loss must carry its annual statement line."),
]

# ------------------------------------------------------------------------------------------ business rules
# code, name, scope, phase, condition, action, owner
RULES = [
    ("UW-CP-001", "Roof age limit", {"lob": "CP"}, "Eligibility", "ROOF_YEAR < policy year - 20", "Refer to underwriter", "Underwriting"),
    ("UW-CP-002", "Roof age limit - Florida", {"lob": "CP", "state": "FL"}, "Eligibility", "ROOF_YEAR < policy year - 15", "Decline unless roof inspection", "Underwriting"),
    ("UW-CP-003", "Frame high-rise", {"lob": "CP"}, "Eligibility", "CONSTRUCTION_CLASS = 1 AND STORIES > 4", "Decline", "Underwriting"),
    ("UW-CP-004", "Coastal flood zone", {"lob": "CP", "state": "FL"}, "Eligibility", "FLOOD_ZONE in (V, VE)", "Refer to catastrophe desk", "Underwriting"),
    ("UW-WC-001", "Monopolistic state", {"lob": "WC"}, "Eligibility", "STATE in (OH, WA, ND, WY) AND WC_PART3_TYPE = 3A", "Block: write stop-gap EL only", "Underwriting"),
    ("UW-WC-002", "High experience mod", {"lob": "WC"}, "Eligibility", "EXPERIENCE_MOD > 1.50", "Refer to underwriter", "Underwriting"),
    ("UW-WC-003", "Bureau by state", {"lob": "WC"}, "Validation", "WC_BUREAU must equal the state default (CA WCIRB, NY NYCIRB, NJ NJCRIB, PA PCRB, else NCCI)", "Correct before issue", "Bureau reporting"),
    ("UW-GL-001", "NY Labor Law contractors", {"lob": "GL", "state": "NY"}, "Eligibility", "GL_CLASS_CODE starts CONTR AND NY_LABOR_LAW_EXPOSURE = true", "Refer; require action-over exclusion review", "Underwriting"),
    ("UW-GL-002", "Subcontractor ratio", {"lob": "GL"}, "Rating", "SUBCONTRACTOR_COST / GL_EXPOSURE > 0.5", "Charge for uninsured subcontractors unless certificates on file", "Underwriting"),
    ("UW-CA-001", "Long-haul heavy trucks", {"lob": "CA"}, "Eligibility", "VEHICLE_TYPE in (HT, XHT, TRAC) AND RADIUS_CLASS = LONG", "Refer to transportation unit", "Underwriting"),
    ("UW-CA-002", "Driver MVR", {"lob": "CA"}, "Eligibility", "DRIVER_MVR_POINTS >= 6", "Exclude driver or decline", "Underwriting"),
    ("UW-CA-003", "CDL required", {"lob": "CA"}, "Validation", "VEHICLE_TYPE in (HT, XHT, TRAC) AND CDL_IND = false", "Error: driver needs a CDL", "Underwriting"),
    ("UW-ES-001", "Surplus lines tax", {"company": "SI2-ES"}, "Rating", "always", "Add SURPLUS_LINES_TAX = premium x state SL tax rate; add STAMPING_FEE where the state has one", "Finance"),
    ("CL-WC-001", "AWW required for indemnity", {"lob": "WC", "module": "Claims"}, "Validation", "indemnity payment AND INJURED_WORKER_AWW is null", "Block payment", "Claims"),
    ("FN-001", "Annual statement line", {"module": "Finance"}, "Validation", "ANNUAL_STATEMENT_LINE is null", "Block posting", "Finance"),
]

# ------------------------------------------------------------------------------------------ rating algorithms (illustrative)
# lob, step, description, formula, factor table
RATING = [
    ("CP", 1, "Building base premium", "BUILDING_LIMIT / 100 x base rate[CONSTRUCTION_CLASS, PROTECTION_CLASS]", "CP_BASE_RATE"),
    ("CP", 2, "Contents base premium", "BPP_LIMIT / 100 x contents rate[CONSTRUCTION_CLASS, PROTECTION_CLASS]", "CP_BASE_RATE"),
    ("CP", 3, "Causes of loss", "x factor[CAUSES_OF_LOSS_FORM]", "CP_COL_FACTOR"),
    ("CP", 4, "Sprinkler credit", "x factor[SPRINKLER]", "CP_SPRK_FACTOR"),
    ("CP", 5, "Deductible credit", "x factor[DEDUCTIBLE_TYPE, DEDUCTIBLE_AMOUNT or WIND_DEDUCTIBLE_PCT]", "CP_DED_FACTOR"),
    ("CP", 6, "Territory (state key)", "x factor[STATE, TERRITORY]", "CP_TERR_FACTOR"),
    ("WC", 1, "Manual premium", "sum over classes: ESTIMATED_PAYROLL / 100 x rate[STATE, WC_CLASS_CODE]", "WC_CLASS_RATE"),
    ("WC", 2, "Experience rating", "x EXPERIENCE_MOD", None),
    ("WC", 3, "Schedule rating", "x (1 + schedule credit/debit, capped by state)", "WC_SCHED_CAP"),
    ("WC", 4, "Premium discount and expense constant", "- premium discount[STATE, premium size] + expense constant[STATE]", "WC_EXP_CONST"),
    ("GL", 1, "Premises / operations", "sum over classes: GL_EXPOSURE / basis divisor x rate[STATE, TERRITORY, GL_CLASS_CODE]", "GL_CLASS_RATE"),
    ("GL", 2, "Increased limits", "x ILF[EACH_OCCURRENCE_LIMIT, GENERAL_AGGREGATE_LIMIT]", "GL_ILF"),
    ("GL", 3, "Claims-made step", "x step factor[years since RETROACTIVE_DATE] (claims-made only)", "GL_CM_STEP"),
    ("CA", 1, "Liability base", "base rate[STATE, TERRITORY] x factor[VEHICLE_TYPE, VEHICLE_USE, RADIUS_CLASS]", "CA_BASE_RATE"),
    ("CA", 2, "Increased limits", "x ILF[CA_LIABILITY_LIMIT]", "CA_ILF"),
    ("CA", 3, "Physical damage", "COST_NEW x rate[VEHICLE_TYPE, age] x deductible factor", "CA_PD_RATE"),
    ("CA", 4, "State coverages", "+ PIP[STATE] + UM[STATE, UM_LIMIT]", "CA_STATE_COV"),
]
FACTORS = [  # table, scope, keys, value
    ("CP_BASE_RATE", {"state": "*"}, "construction=1;ppc=1-5", 0.42), ("CP_BASE_RATE", {"state": "*"}, "construction=6;ppc=1-5", 0.18),
    ("CP_BASE_RATE", {"state": "FL"}, "construction=1;ppc=1-5", 0.71), ("CP_BASE_RATE", {"state": "FL"}, "construction=6;ppc=1-5", 0.33),
    ("CP_SPRK_FACTOR", {"state": "*"}, "sprinkler=FULL", 0.70), ("CP_SPRK_FACTOR", {"state": "*"}, "sprinkler=NONE", 1.00),
    ("CP_COL_FACTOR", {"state": "*"}, "form=SPECIAL", 1.12), ("CP_COL_FACTOR", {"state": "*"}, "form=BASIC", 0.85),
    ("WC_CLASS_RATE", {"state": "TX"}, "class=8810", 0.12), ("WC_CLASS_RATE", {"state": "TX"}, "class=5645", 6.85),
    ("WC_CLASS_RATE", {"state": "FL"}, "class=8810", 0.19), ("WC_CLASS_RATE", {"state": "FL"}, "class=5645", 9.40),
    ("WC_CLASS_RATE", {"state": "CA"}, "class=8810", 0.31), ("WC_CLASS_RATE", {"state": "NY"}, "class=5645", 15.20),
    ("WC_EXP_CONST", {"state": "*"}, "constant", 160.0), ("WC_SCHED_CAP", {"state": "*"}, "max credit/debit", 0.25),
    ("GL_CLASS_RATE", {"state": "*"}, "class=CONTR-CARP;basis=PAYROLL", 18.50), ("GL_CLASS_RATE", {"state": "NY"}, "class=CONTR-CARP;basis=PAYROLL", 41.00),
    ("GL_CLASS_RATE", {"state": "*"}, "class=RESTAURANT;basis=SALES", 1.95), ("GL_ILF", {"state": "*"}, "1M/2M", 1.00), ("GL_ILF", {"state": "*"}, "2M/4M", 1.28),
    ("CA_BASE_RATE", {"state": "*"}, "territory=urban", 1450.0), ("CA_BASE_RATE", {"state": "FL"}, "territory=urban", 2150.0),
    ("CA_ILF", {"state": "*"}, "csl=1M", 1.00), ("CA_ILF", {"state": "*"}, "csl=2M", 1.21),
    ("CA_STATE_COV", {"state": "FL"}, "PIP 10k", 210.0), ("CA_STATE_COV", {"state": "NY"}, "PIP 50k", 330.0),
]

# ------------------------------------------------------------------------------------------ source systems (illustrative crosswalk targets)
SOURCES = [
    ("ACORD", "Standard", "ACORD forms and data standards (125, 126, 130, 137, 140): reference vocabulary"),
    ("IBM_IIW", "Standard", "IBM insurance industry data models: reference vocabulary"),
    ("ISO_NCCI", "Standard", "ISO and NCCI statistical plans and class codes"),
    ("GW_PC", "Policy admin (Guidewire-style)", "Policy administration configured entities and typelists"),
    ("DC_POL", "Policy admin (Duck Creek-style)", "Manuscript-based policy and rating data"),
    ("LEGACY", "Legacy", "COBOL / DB2 policy and claims masters"),
    ("HOMEBUILT", "Home-built", "In-house rating and billing applications"),
    ("AMS", "Agency management", "Agency management system exports"),
]
FORM_USE = {  # element -> ACORD forms that collect it (form numbers only)
    "NAMED_INSURED_NAME": "125", "FEIN": "125,130", "LEGAL_ENTITY_TYPE": "125", "NAICS_CODE": "125", "PRODUCER_CODE": "125",
    "CONSTRUCTION_CLASS": "140", "YEAR_BUILT": "140", "ROOF_YEAR": "140", "SPRINKLER": "140", "PROTECTION_CLASS": "140",
    "BUILDING_LIMIT": "140", "BPP_LIMIT": "140", "CAUSES_OF_LOSS_FORM": "140", "COINSURANCE": "140", "VALUATION": "140",
    "WC_CLASS_CODE": "130", "ESTIMATED_PAYROLL": "130", "EXPERIENCE_MOD": "130", "EL_LIMIT_EACH_ACCIDENT": "130",
    "GL_CLASS_CODE": "126", "GL_EXPOSURE": "126", "EACH_OCCURRENCE_LIMIT": "126", "GENERAL_AGGREGATE_LIMIT": "126",
    "VIN": "137", "VEHICLE_YEAR": "137", "VEHICLE_TYPE": "137", "RADIUS_CLASS": "137", "GARAGING_ZIP": "137",
    "COST_NEW": "137", "AUTO_SYMBOL": "137", "CA_LIABILITY_LIMIT": "137",
}
