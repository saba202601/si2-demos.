"""Commercial application vocabulary for the SI² Canonical Master: Party first, then everything a commercial
application collects (the data asked for on the industry-standard commercial application, general liability and
property sections: ACORD 125, 126 and 140).

Names and definitions are SI²'s own. The form field labels are kept only as synonyms (source "ACORD 125" etc.) so
every element shows where it appears on the forms; no form text or ACORD codes are copied. Elements that already exist
in the master (FEIN, STATE, YEAR_BUILT ...) are reused: the collector matches them and only adds the new labels.

Entities describe how the elements group: a PARTY has many ROLES, ADDRESSES, CONTACTS and RELATIONSHIPS; an
ADDITIONAL INTEREST is a party with an interest in a location, building, vehicle or item; and so on.
"""
from __future__ import annotations

SOURCE = "Commercial application"

# ------------------------------------------------------------------------------------------ pick lists
# (code, name, description, [(option, name)]): new lists, or new options on lists the master already has
PICKLISTS = [
    ("PARTY_ROLE", "Party Role", "The part a person or organization plays on a policy, submission or claim.", [
        ("FIRST_NAMED_INSURED", "First named insured"), ("OTHER_NAMED_INSURED", "Other named insured"), ("APPLICANT", "Applicant"),
        ("CONTACT", "Contact"), ("ADDITIONAL_INTEREST", "Additional interest"), ("CERTIFICATE_HOLDER", "Certificate holder"),
        ("LOSS_PAYEE", "Loss payee"), ("LENDERS_LOSS_PAYABLE", "Lender's loss payable"), ("CO_OWNER", "Co-owner"), ("OWNER", "Owner"),
        ("EMPLOYEE_AS_LESSOR", "Employee as lessor"), ("LEASEBACK_OWNER", "Leaseback owner"), ("BREACH_OF_WARRANTY", "Breach of warranty interest"),
        ("REGISTRANT", "Registrant"), ("TRUSTEE", "Trustee"), ("PRODUCER", "Producer / agent"), ("AGENCY", "Agency / broker"),
        ("CARRIER", "Insurance carrier"), ("PRIOR_CARRIER", "Prior carrier"), ("PARENT_COMPANY", "Parent company"), ("SUBSIDIARY", "Subsidiary"),
        ("SUBCONTRACTOR", "Subcontractor"), ("ALARM_COMPANY", "Alarm installer / servicer")]),
    ("ADDRESS_TYPE", "Address Type", "What an address is used for.", [
        ("MAILING", "Mailing"), ("PREMISES", "Premises / risk location"), ("BILLING", "Billing"), ("GARAGING", "Garaging"), ("LEGAL", "Legal / registered"),
        ("HOME", "Home"), ("BUSINESS", "Business")]),
    ("PHONE_TYPE", "Phone Type", "Kind of phone number.", [("HOME", "Home"), ("BUSINESS", "Business"), ("CELL", "Cell / mobile"), ("FAX", "Fax")]),
    ("CONTACT_TYPE", "Contact Type", "Why a contact person is listed on an account.", [
        ("PRIMARY", "Primary contact"), ("ACCOUNTING", "Accounting / billing"), ("INSPECTION", "Inspection / loss control"), ("CLAIMS", "Claims"),
        ("SAFETY", "Safety"), ("OWNER_OFFICER", "Owner / officer"), ("OTHER", "Other")]),
    ("PARTY_RELATIONSHIP_TYPE", "Party Relationship Type", "How two parties are related.", [
        ("PARENT", "Parent company"), ("SUBSIDIARY", "Subsidiary"), ("AFFILIATE", "Affiliate / common ownership"), ("TRUST", "Placed in a trust"),
        ("DBA", "Doing business as"), ("SUCCESSOR", "Successor / acquired")]),
    ("INTEREST_ITEM_TYPE", "Interest Item Type", "What an additional interest has an interest in.", [
        ("LOCATION", "Location"), ("BUILDING", "Building"), ("VEHICLE", "Vehicle"), ("BOAT", "Boat / watercraft"), ("AIRPORT", "Airport"),
        ("AIRCRAFT", "Aircraft"), ("ITEM", "Scheduled item"), ("POLICY", "Whole policy")]),
    ("PREMISES_INTEREST", "Premises Interest", "The applicant's interest in a premises.", [("OWNER", "Owner"), ("TENANT", "Tenant"), ("LANDLORD", "Owner, leased to others")]),
    ("NATURE_OF_BUSINESS", "Nature of Business", "Broad kind of business operated by the applicant.", [
        ("APARTMENTS", "Apartments"), ("CONDOMINIUMS", "Condominiums"), ("CONTRACTOR", "Contractor"), ("INSTITUTIONAL", "Institutional"),
        ("MANUFACTURING", "Manufacturing"), ("OFFICE", "Office"), ("RESTAURANT", "Restaurant"), ("RETAIL", "Retail"), ("SERVICE", "Service"),
        ("WHOLESALE", "Wholesale"), ("OTHER", "Other")]),
    ("PRIOR_CANCEL_REASON", "Prior Cancellation Reason", "Why a prior policy was declined, cancelled or not renewed.", [
        ("NON_PAYMENT", "Non-payment"), ("NON_RENEWAL", "Non-renewal"), ("AGENT_LEFT_CARRIER", "Agent no longer represents the carrier"),
        ("UNDERWRITING", "Underwriting reasons"), ("CONDITION_CORRECTED", "Condition since corrected"), ("OTHER", "Other")]),
    ("UW_QUESTION", "Underwriting Question", "Yes / no questions asked on a commercial application; each answer is kept with its explanation.", [
        # applicant (general information)
        ("SUBSIDIARY_OF_ANOTHER", "Applicant is a subsidiary of another entity"), ("HAS_SUBSIDIARIES", "Applicant has subsidiaries"),
        ("FORMAL_SAFETY_PROGRAM", "Formal safety program in operation"), ("FLAMMABLES_EXPOSURE", "Exposure to flammables, explosives or chemicals"),
        ("OTHER_INSURANCE_WITH_CARRIER", "Other insurance with this carrier"),
        ("PRIOR_DECLINED_CANCELLED", "Coverage declined, cancelled or non-renewed in the prior three years"),
        ("ABUSE_DISCRIMINATION_CLAIMS", "Past claims for abuse, discrimination or negligent hiring"),
        ("FRAUD_ARSON_CONVICTION", "Applicant indicted or convicted of fraud, bribery or arson in the last five years"),
        ("CODE_VIOLATIONS", "Uncorrected fire or safety code violations"), ("BANKRUPTCY_FORECLOSURE", "Foreclosure, repossession or bankruptcy in the last five years"),
        ("JUDGEMENT_LIEN", "Judgement or lien in the last five years"), ("PLACED_IN_TRUST", "Business placed in a trust"),
        ("FOREIGN_OPERATIONS", "Foreign operations or products sold abroad"), ("OTHER_VENTURES_NOT_COVERED", "Other business ventures not to be insured"),
        ("OPERATES_DRONES", "Owns, leases or operates drones"), ("HIRES_DRONE_OPERATORS", "Hires others to operate drones"),
        # general liability
        ("MEDICAL_FACILITIES", "Medical facilities provided or medical professionals employed"), ("RADIOACTIVE_EXPOSURE", "Exposure to radioactive or nuclear materials"),
        ("HAZARDOUS_MATERIALS", "Stores, treats, disposes or transports hazardous material"), ("OPERATIONS_SOLD_ACQUIRED", "Operations sold, acquired or discontinued in five years"),
        ("RENTS_EQUIPMENT_TO_OTHERS", "Rents or loans equipment to others"), ("WATERCRAFT_DOCKS", "Watercraft, docks or floats owned, hired or leased"),
        ("PARKING_FACILITIES", "Parking facilities owned or rented"), ("RECREATION_FACILITIES", "Recreation facilities provided"),
        ("SWIMMING_POOL", "Swimming pool on premises"), ("SPORTS_SPONSORSHIP", "Sponsors sporting or social events"), ("STRUCTURAL_ALTERATIONS", "Structural alterations planned"),
        ("DEMOLITION_EXPOSURE", "Demolition exposure"), ("ACTIVE_JOINT_VENTURES", "Active in joint ventures"), ("LEASES_EMPLOYEES", "Leases employees to or from others"),
        ("LABOR_INTERCHANGE", "Labor interchange with other businesses"), ("DAY_CARE", "Day care facilities operated"), ("CRIMES_ON_PREMISES", "Crimes occurred on premises"),
        ("SAFETY_POLICY_WRITTEN", "Formal written safety and security policy"), ("PROMOTES_WITH_ENDORSEMENT", "Promotional literature makes safety claims"),
        # contractors
        ("DRAWS_PLANS_FOR_OTHERS", "Draws plans, designs or specifications for others"), ("BLASTING_EXPLOSIVES", "Blasting or stores explosive material"),
        ("EXCAVATION_UNDERGROUND", "Excavation, tunneling, underground work or earth moving"),
        ("SUBS_LOWER_LIMITS", "Subcontractors carry lower coverage or limits"), ("SUBS_WITHOUT_CERTIFICATE", "Subcontractors work without certificates of insurance"),
        ("LEASES_EQUIPMENT_WITH_OPERATOR", "Leases equipment to others with or without operators"),
        # products / completed operations
        ("INSTALLS_SERVICES_PRODUCTS", "Installs, services or demonstrates products"), ("FOREIGN_PRODUCTS", "Foreign products sold, distributed or used as components"),
        ("RESEARCH_NEW_PRODUCTS", "Research and development or new products planned"), ("WARRANTIES_HOLD_HARMLESS", "Guarantees, warranties or hold-harmless agreements"),
        ("AIRCRAFT_SPACE_PRODUCTS", "Products related to the aircraft or space industry"), ("PRODUCTS_RECALLED", "Products recalled, discontinued or changed"),
        ("OTHERS_PRODUCTS_OWN_LABEL", "Products of others sold under the applicant's label"), ("PRODUCTS_UNDER_OTHERS_LABEL", "Products sold under the label of others"),
        ("VENDORS_COVERAGE_REQUIRED", "Vendors coverage required"), ("SELLS_TO_OTHER_NAMED_INSUREDS", "A named insured sells to other named insureds"),
        # claims-made
        ("PRIOR_EXCLUDED_OR_SELF_INSURED", "A product, work, accident or location was excluded, uninsured or self-insured before"),
        ("TAIL_PURCHASED", "Tail coverage bought under a previous policy"),
        # crime controls
        ("CRIME_AUDIT_INDEPENDENT", "Audited by an independent CPA or public accountant"), ("CRIME_AUDIT_ALL_LOCATIONS", "All locations are audited"),
        ("CRIME_AUDIT_STANDARDS", "Audit follows generally accepted auditing standards"), ("CRIME_AUDIT_TO_OWNERS", "Audit report goes directly to the owners or board"),
        ("CRIME_AUDIT_DISCREPANCIES", "The auditor commented on discrepancies or loose practices"), ("CRIME_INTERNAL_AUDIT", "Internal audit by an internal audit department"),
        ("CRIME_AUDIT_INCLUDES_INVENTORY", "The audit includes inventory"), ("CRIME_BANK_RECONCILED_INDEPENDENTLY", "Bank accounts reconciled by someone who cannot deposit or withdraw"),
        ("CRIME_CHECK_COUNTERSIGNATURE", "Checks need a countersignature"), ("CRIME_SECURITIES_JOINT_CONTROL", "Securities under joint control of two employees"),
        ("CRIME_MANDATORY_VACATION", "Officers and money handlers take five consecutive days of vacation"),
        ("CRIME_LICENSED_INVESTMENT_FIRM", "A licensed securities firm invests the plan's funds"), ("CRIME_DOUBLE_CYLINDER_LOCKS", "Premises doors have double-cylinder locks")]),
    ("CGL_COVERAGE_FORM", "CGL Coverage Form", "Trigger of the general liability policy.", [("OCCURRENCE", "Occurrence"), ("CLAIMS_MADE", "Claims made")]),
    ("AGGREGATE_APPLIES_PER", "Aggregate Applies Per", "What the general aggregate limit applies to.", [
        ("POLICY", "Policy"), ("LOCATION", "Location"), ("PROJECT", "Project"), ("OTHER", "Other")]),
    ("DEDUCTIBLE_BASIS", "Deductible Basis", "How a liability deductible applies.", [("PER_CLAIM", "Per claim"), ("PER_OCCURRENCE", "Per occurrence")]),
    ("EXPOSURE_BASE", "Exposure Base", "Premium basis for a general liability classification.", [
        ("COST", "Total cost (per $1,000)"), ("OTHER", "Other")]),                      # PAY, SALES, AREA, UNITS, ADM are already in the master
    ("SUBJECT_OF_INSURANCE", "Subject of Insurance", "What a property limit insures.", [
        ("BUILDING", "Building"), ("BPP", "Business personal property"), ("BUSINESS_INCOME", "Business income"), ("EXTRA_EXPENSE", "Extra expense"),
        ("BI_EXTRA_EXPENSE", "Business income with extra expense"), ("TENANT_IMPROVEMENTS", "Tenant improvements and betterments"), ("STOCK", "Stock"),
        ("PROPERTY_OF_OTHERS", "Personal property of others"), ("RENTAL_VALUE", "Rental value"), ("SIGNS", "Signs"), ("EDP", "Electronic data processing")]),
    ("VALUATION", "Valuation", "How a property loss is valued.", [
        ("RC", "Replacement cost"), ("ACV", "Actual cash value"), ("AGREED_VALUE", "Agreed value"), ("FUNCTIONAL", "Functional replacement cost"),
        ("MARKET", "Market value"), ("STATED", "Stated amount")]),
    ("CAUSES_OF_LOSS_FORM", "Causes of Loss Form", "Which causes of loss a property limit covers.", [
        ("BASIC", "Basic"), ("BROAD", "Broad"), ("SPECIAL", "Special (open perils)"), ("EARTHQUAKE", "Earthquake"), ("FLOOD", "Flood")]),
    ("WIND_CLASS", "Wind Class", "Wind resistance of a building.", [("RESISTIVE", "Wind resistive"), ("SEMI_RESISTIVE", "Semi-wind resistive"), ("NONE", "Not wind resistive")]),
    ("HEAT_SOURCE", "Heat Source", "How a building is heated.", [
        ("BOILER", "Boiler"), ("SOLID_FUEL", "Solid fuel / wood burning"), ("FORCED_AIR", "Forced air furnace"), ("ELECTRIC", "Electric"),
        ("HEAT_PUMP", "Heat pump"), ("NONE", "No heat"), ("OTHER", "Other")]),
    ("ALARM_SIGNAL", "Alarm Signal", "Where an alarm reports.", [("CENTRAL_STATION", "Central station"), ("CENTRAL_STATION_KEYS", "Central station with keys"),
                                                               ("LOCAL_GONG", "Local gong"), ("POLICE_CONNECT", "Police connected")]),
    ("COVERAGE_ELECTION", "Coverage Election", "Whether an offered coverage was accepted.", [("ACCEPT", "Accepted"), ("REJECT", "Rejected")]),
    ("CRIME_COVERAGE_BASIS", "Crime Coverage Basis", "Whether crime coverage pays losses discovered in the period or sustained in it.", [
        ("DISCOVERY", "Discovery"), ("LOSS_SUSTAINED", "Loss sustained")]),
    ("CRIME_COVERAGE_FORM", "Crime Coverage Form", "The crime coverage applied for.", [
        ("A", "Employee dishonesty"), ("A_ERISA", "Employee dishonesty - ERISA"), ("B", "Forgery or alteration"),
        ("C", "Theft, disappearance and destruction"), ("D", "Robbery and safe burglary"), ("E", "Premises burglary"), ("F", "Computer fraud"),
        ("G", "Extortion"), ("H", "Premises theft and robbery outside the premises"), ("Q", "Robbery and safe burglary - money and securities")]),
    ("CRIME_SCHEDULE_BASIS", "Crime Schedule Basis", "Whether a crime limit is blanket or scheduled.", [("BLANKET", "Blanket"), ("SCHEDULE", "Schedule")]),
    ("CRIME_PREMISES_SECTION", "Crime Premises Section", "Whether a crime limit applies inside or outside the premises.", [("INSIDE", "Inside the premises"), ("OUTSIDE", "Outside the premises")]),
    ("CRIME_EMPLOYEE_CLASS", "Crime Employee Class", "Position of employees who handle or have custody of money, securities or other property.", [
        (c.upper().replace(" ", "_").replace("'", "").replace("/", "_").replace("-", "_").replace(",", ""), c) for c in (
            "Accountants and assistants", "Adjusters", "Administrators and assistants", "Appraisers", "Attorneys", "Auditors and assistants", "Bookkeepers",
            "Bus drivers", "Buyers and assistants", "Canvassers", "Cashiers and assistants", "Chairpersons", "Chefs who order food", "Collectors",
            "Computer programmers", "Comptrollers and assistants", "Credit clerks and managers", "Custodians", "Delivery persons", "Demonstrators",
            "Dietitians who order food", "Drivers and drivers helpers", "Food inspectors", "Head pharmacists", "Instructors handling money",
            "Janitors", "Locker room attendants", "Maitre d and assistants", "Managers and assistants", "Medical directors", "Messengers outside",
            "Payroll distributors", "Purchasing agents and assistants", "Receiving clerks", "Refinery gaugers", "Salespeople", "Security personnel",
            "Service station attendants", "Shipping clerks", "Stock clerks", "Storekeepers", "Storeroom personnel", "Superintendents and assistants",
            "Supervisors and assistants", "Taxi drivers", "Teachers handling money", "Timekeepers and assistants", "Truck drivers", "Warehouse personnel",
            "Wine cellar personnel", "Wine stewards", "Other officers and employees")]),
    ("AUDITOR_TYPE", "Auditor Type", "Who audits the books.", [("CPA", "Certified public accountant"), ("PUBLIC_ACCOUNTANT", "Public accountant"),
                                                             ("STAFF", "Staff"), ("INTERNAL_AUDIT", "Internal audit department"), ("OTHER", "Other")]),
    ("AUDIT_REPORT_RECIPIENT", "Audit Report Recipient", "Who the audit report goes to.", [("BOARD", "Board of directors"), ("OWNER", "Owner"),
                                                                                         ("PARTNERS", "Partners"), ("OTHER", "Other")]),
    ("CRIME_EXPOSURE_CATEGORY", "Crime Exposure Category", "Where money and securities are exposed.", [("INSIDE", "Inside the premises"),
                                                                                                    ("MESSENGER", "With a messenger")]),
    ("SAFE_LABEL", "Safe Label", "Rating label of a safe or vault.", [("UL", "Underwriters Laboratories"), ("SMNA", "Safe Manufacturers National Association")]),
    ("SAFE_DOOR_TYPE", "Safe Door Type", "Shape of a safe door.", [("ROUND", "Round"), ("SQUARE", "Square")]),
    ("ALARM_PROTECTED_AREA", "Alarm Protected Area", "What an alarm protects.", [("HOLDUP", "Hold-up"), ("PREMISES", "Premises"), ("SAFE", "Safe")]),
    ("ALARM_EXTENT_LEVEL", "Alarm Extent Level", "How completely an alarm covers what it protects.", [("PARTIAL", "Partial"), ("COMPLETE", "Complete"),
                                                                                                    ("LEVEL_1", "Level 1"), ("LEVEL_2", "Level 2"), ("LEVEL_3", "Level 3")]),
    ("WATCHPERSON_SIGNAL", "Watchperson Signal", "How a watchperson reports.", [("CENTRAL_STATION", "Reports to a central station"),
                                                                              ("CLOCK_HOURLY", "Clocks hourly"), ("NO_SIGNAL", "Does not signal")]),
    ("SPOILAGE_OPTION", "Spoilage Option", "Causes covered by spoilage coverage.", [
        ("BREAKDOWN_CONTAMINATION", "Breakdown or contamination"), ("POWER_OUTAGE", "Power outage"), ("SELLING_PRICE", "Selling price valuation")]),
]

# ------------------------------------------------------------------------------------------ data elements
# (code, name, subject, type, description, pick list, pii, form labels)
P, L, U, C, R, PR, PO, CL, LI, CR = "PARTY", "LOCATION", "UNDERWRITING", "COVERAGE", "RATING", "PROPERTY", "PRODUCER", "CLAIM", "LIABILITY", "CRIME"
ELEMENTS = [
    # ---- party
    ("PARTY_ID", "Party ID", P, "TEXT", "Identifier of a person or organization, the same on every policy, submission and claim.", None, False, []),
    ("PARTY_TYPE", "Party Type", P, "CODE", "Whether the party is a person or an organization.", "PARTY_TYPE", False, []),
    ("PARTY_ROLE", "Party Role", P, "CODE", "The part the party plays on this policy, submission or claim.", "PARTY_ROLE", False, ["Interest"]),
    ("PARTY_ROLE_SEQUENCE", "Party Role Sequence", P, "INTEGER", "Order of parties with the same role; 1 is the first named insured.", None, False, ["Rank"]),
    ("INSURED_NAME", "Insured Name", P, "TEXT", "Full legal name of the person or organization.", None, True,
     ["Name (First Named Insured)", "Name (Other Named Insured)", "Applicant / First Named Insured", "Named Insured(s)"]),
    ("FIRST_NAME", "First Name", P, "TEXT", "Given name of a person.", None, True, []),
    ("MIDDLE_NAME", "Middle Name", P, "TEXT", "Middle name or initial of a person.", None, True, []),
    ("LAST_NAME", "Last Name", P, "TEXT", "Family name of a person.", None, True, []),
    ("DBA_NAME", "Doing Business As Name", P, "TEXT", "Trade name the organization operates under.", None, False, ["DBA"]),
    ("LEGAL_ENTITY_TYPE", "Legal Entity Type", P, "CODE", "Legal form of the organization (corporation, LLC, partnership ...).", "LEGAL_ENTITY_TYPE", False, []),
    ("LLC_MEMBER_MANAGER_COUNT", "LLC Members and Managers", P, "INTEGER", "Number of members and managers of a limited liability company.", None, False,
     ["No. of Members and Managers"]),
    ("FEIN", "FEIN", P, "TEXT", "Federal employer identification number of an organization.", None, True, []),
    ("SSN", "Social Security Number", P, "TEXT", "Social security number of a person, when used instead of a FEIN.", None, True, []),
    ("DATE_OF_BIRTH", "Date of Birth", P, "DATE", "Birth date of a person.", None, True, []),
    ("BUSINESS_PHONE", "Business Phone", P, "TEXT", "Main business phone number of the organization.", None, True, ["Business Phone #"]),
    ("WEBSITE_ADDRESS", "Website Address", P, "TEXT", "Web address of the organization.", None, False, ["Website Address"]),
    ("SIC_CODE", "SIC Code", U, "TEXT", "Standard Industrial Classification code of the business.", None, False, ["SIC"]),
    ("NAICS_CODE", "NAICS Code", U, "TEXT", "North American Industry Classification System code of the business.", None, False, ["NAICS"]),
    ("GL_CLASS_CODE", "GL Class Code", R, "TEXT", "General liability classification code that best describes the business.", None, False, ["GL Code", "Class Code"]),
    ("NATURE_OF_BUSINESS", "Nature of Business", U, "CODE", "Broad kind of business the applicant runs.", "NATURE_OF_BUSINESS", False, ["Nature of Business"]),
    ("DATE_BUSINESS_STARTED", "Date Business Started", U, "DATE", "Date the applicant's business began operating.", None, False, ["Date Business Started"]),
    ("BUSINESS_DESCRIPTION", "Business Description", U, "TEXT", "What the business does, in the applicant's words.", None, False,
     ["Description of Primary Operations"]),
    ("OTHER_NAMED_INSURED_OPERATIONS", "Other Named Insureds' Operations", U, "TEXT", "What the other named insureds do.", None, False,
     ["Description of Operations of Other Named Insureds"]),
    ("RETAIL_SALES_PCT", "Retail Sales Percent", U, "PERCENT", "Share of total sales from retail stores or service operations.", None, False,
     ["Retail Stores or Service Operations % of Total Sales"]),
    ("ON_PREMISES_INSTALL_PCT", "Installation On Premises Percent", U, "PERCENT", "Share of sales from installation, service or repair work.", None, False,
     ["Installation, Service or Repair Work %"]),
    ("OFF_PREMISES_INSTALL_PCT", "Installation Off Premises Percent", U, "PERCENT", "Share of sales from installation, service or repair work away from the premises.",
     None, False, ["Off Premises Installation, Service or Repair Work %"]),
    # ---- address and contact
    ("ADDRESS_TYPE", "Address Type", L, "CODE", "What the address is used for: mailing, premises, billing ...", "ADDRESS_TYPE", False, []),
    ("ADDRESS_STREET", "Street Address", L, "TEXT", "House number and street.", None, True, ["Street", "Street Address", "Mailing Address"]),
    ("ADDRESS_LINE_2", "Address Line 2", L, "TEXT", "Suite, unit, floor or building of an address.", None, True, []),
    ("ADDRESS_CITY", "City", L, "TEXT", "City of an address.", None, False, ["City"]),
    ("COUNTY", "County", L, "TEXT", "County of an address.", None, False, ["County"]),
    ("ZIP_CODE", "ZIP Code", L, "TEXT", "Postal code, five digits or ZIP+4.", None, False, ["ZIP", "Including ZIP+4"]),
    ("COUNTRY_CODE", "Country Code", L, "TEXT", "Country of an address (ISO 3166 two-letter code).", None, False, []),
    ("INSIDE_CITY_LIMITS_IND", "Inside City Limits", L, "CODE", "The premises is inside city limits.", "YES_NO", False, ["City Limits Inside / Outside"]),
    ("CONTACT_TYPE", "Contact Type", P, "CODE", "Why the contact person is listed: primary, accounting, inspection, claims ...", "CONTACT_TYPE", False, ["Contact Type"]),
    ("CONTACT_NAME", "Contact Name", P, "TEXT", "Name of the person to contact.", None, True, ["Contact Name"]),
    ("PHONE", "Phone Number", P, "TEXT", "Phone number of a party or contact.", None, True, ["Primary Phone #", "Phone (A/C, No, Ext)"]),
    ("PHONE_TYPE", "Phone Type", P, "CODE", "Home, business, cell or fax.", "PHONE_TYPE", False, ["Home / Bus / Cell"]),
    ("PHONE_EXTENSION", "Phone Extension", P, "TEXT", "Extension of a phone number.", None, False, []),
    ("SECONDARY_PHONE", "Secondary Phone", P, "TEXT", "Second phone number of a contact.", None, True, ["Secondary Phone #"]),
    ("FAX_NUMBER", "Fax Number", P, "TEXT", "Fax number of a party.", None, True, ["Fax (A/C, No)"]),
    ("EMAIL", "Email", P, "TEXT", "Primary email address of a party or contact.", None, True, ["Primary E-Mail Address", "E-Mail Address"]),
    ("SECONDARY_EMAIL", "Secondary Email", P, "TEXT", "Second email address of a contact.", None, True, ["Secondary E-Mail Address"]),
    # ---- relationships
    ("RELATED_PARTY_ID", "Related Party ID", P, "TEXT", "The other party in a relationship (parent, subsidiary, trust ...).", None, False, []),
    ("PARTY_RELATIONSHIP_TYPE", "Party Relationship Type", P, "CODE", "How two parties are related.", "PARTY_RELATIONSHIP_TYPE", False, []),
    ("RELATIONSHIP_DESCRIPTION", "Relationship Description", P, "TEXT", "The relationship in words.", None, False, ["Relationship Description"]),
    ("OWNERSHIP_PCT", "Ownership Percent", P, "PERCENT", "Share of the related party that is owned.", None, False, ["% Owned"]),
    # ---- additional interest
    ("INTEREST_RANK", "Interest Rank", P, "INTEGER", "Order of an additional interest (first mortgagee, second ...).", None, False, ["Rank"]),
    ("EVIDENCE_REQUIRED_IND", "Evidence Required", P, "CODE", "The interest is to receive evidence of insurance.", "YES_NO", False, ["Evidence"]),
    ("CERTIFICATE_REQUIRED_IND", "Certificate Required", P, "CODE", "The interest is to receive a certificate of insurance.", "YES_NO", False, ["Certificate"]),
    ("POLICY_COPY_REQUIRED_IND", "Policy Copy Required", P, "CODE", "The interest is to receive a copy of the policy.", "YES_NO", False, ["Policy"]),
    ("SEND_BILL_IND", "Send Bill to Interest", P, "CODE", "Bills go to the additional interest (for example a mortgagee).", "YES_NO", False, ["Send Bill"]),
    ("LOAN_NUMBER", "Loan / Reference Number", P, "TEXT", "Loan or reference number the interest uses for this risk.", None, False, ["Reference / Loan #"]),
    ("LIEN_AMOUNT", "Lien Amount", P, "AMOUNT", "Amount of the lien held by the interest.", None, False, ["Lien Amount"]),
    ("INTEREST_END_DATE", "Interest End Date", P, "DATE", "Date the additional interest ends.", None, False, ["Interest End Date"]),
    ("INTEREST_REASON", "Reason for Interest", P, "TEXT", "Why the party has an interest.", None, False, ["Reason for Interest"]),
    ("INTEREST_ITEM_TYPE", "Interest Item Type", P, "CODE", "What the interest applies to: location, building, vehicle, boat, aircraft or item.", "INTEREST_ITEM_TYPE", False,
     ["Interest in Item Number"]),
    ("ITEM_NUMBER", "Item Number", P, "TEXT", "Number of the scheduled item, vehicle, boat or aircraft the interest applies to.", None, False, ["Item"]),
    ("ITEM_CLASS", "Item Class", P, "TEXT", "Class of the scheduled item.", None, False, ["Item Class"]),
    ("ITEM_DESCRIPTION", "Item Description", P, "TEXT", "Description of the item the interest applies to.", None, False, ["Item Description"]),
    # ---- producer and carrier
    ("AGENCY_NAME", "Agency Name", PO, "TEXT", "Name of the agency or broker that submitted the application.", None, False, ["Agency Name"]),
    ("AGENCY_CUSTOMER_ID", "Agency Customer ID", PO, "TEXT", "The agency's own identifier for the customer.", None, False, ["Agency Customer ID"]),
    ("PRODUCER_NAME", "Producer Name", PO, "TEXT", "Name of the individual producer.", None, False, ["Producer's Name"]),
    ("STATE_PRODUCER_LICENSE_NUMBER", "State Producer License Number", PO, "TEXT", "Producer's license number in the risk state.", None, False,
     ["State Producer License No"]),
    ("NATIONAL_PRODUCER_NUMBER", "National Producer Number", PO, "TEXT", "Producer's national producer number (NPN).", None, False, ["National Producer Number"]),
    ("CARRIER_NAME", "Carrier Name", "POLICY", "TEXT", "Name of the insurance company.", None, False, ["Carrier"]),
    ("NAIC_CODE", "NAIC Company Code", "POLICY", "TEXT", "NAIC code of the insurance company.", None, False, ["NAIC Code"]),
    # ---- application
    ("APPLICATION_DATE", "Application Date", U, "DATE", "Date the application was completed.", None, False, ["Date"]),
    ("APPLICANT_SIGNED_DATE", "Applicant Signed Date", U, "DATE", "Date the applicant signed the application.", None, False, ["Applicant's Signature Date"]),
    ("PRIVACY_NOTICE_GIVEN_IND", "Privacy Notice Given", U, "CODE", "The applicant received the notice of information practices.", "YES_NO", False,
     ["Copy of the Notice of Information Practices"]),
    ("APPLICATION_REMARKS", "Application Remarks", U, "TEXT", "Remarks and processing instructions on the application.", None, False,
     ["Remarks / Processing Instructions"]),
    ("UW_QUESTION", "Underwriting Question", U, "CODE", "Which yes / no underwriting question this answer is for.", "UW_QUESTION", False, ["Explain all Yes responses"]),
    ("UW_ANSWER_IND", "Underwriting Answer", U, "CODE", "Answer to an underwriting question.", "YES_NO", False, ["Y / N"]),
    ("UW_ANSWER_EXPLANATION", "Answer Explanation", U, "TEXT", "Explanation the applicant gave for a yes answer.", None, False, ["Explanation"]),
    ("UW_EVENT_DATE", "Event Date", U, "DATE", "When the event behind an answer happened (violation, bankruptcy, lien ...).", None, False, ["Occur Date"]),
    ("UW_EVENT_RESOLUTION", "Event Resolution", U, "TEXT", "How the event was resolved.", None, False, ["Resolution"]),
    ("UW_EVENT_RESOLVED_DATE", "Event Resolved Date", U, "DATE", "When the event was resolved.", None, False, ["Resolve Date"]),
    ("SAFETY_PROGRAM_ELEMENTS", "Safety Program Elements", U, "TEXT", "Parts of the safety program in place (manual, safety position, meetings, OSHA).", None, False,
     ["Safety Manual", "Safety Position", "Monthly Meetings", "OSHA"]),
    ("PRIOR_CANCEL_REASON", "Prior Cancellation Reason", U, "CODE", "Why a prior policy was declined, cancelled or not renewed.", "PRIOR_CANCEL_REASON", False, []),
    ("TRUST_NAME", "Name of Trust", P, "TEXT", "Name of the trust the business was placed in.", None, False, ["Name of Trust"]),
    # ---- premises
    ("LOCATION_NUMBER", "Location Number", L, "INTEGER", "Number of the premises on the application or policy.", None, False, ["Loc #", "Premises #"]),
    ("BUILDING_NUMBER", "Building Number", L, "INTEGER", "Number of the building at a location.", None, False, ["Bld #", "Building #"]),
    ("BUILDING_DESCRIPTION", "Building Description", PR, "TEXT", "Description of the building.", None, False, ["Bldg Description"]),
    ("PREMISES_INTEREST", "Premises Interest", L, "CODE", "Whether the applicant owns or rents the premises.", "PREMISES_INTEREST", False, ["Interest Owner / Tenant"]),
    ("FULL_TIME_EMPLOYEES", "Full-Time Employees", U, "INTEGER", "Number of full-time employees at the premises.", None, False, ["# Full Time Empl"]),
    ("PART_TIME_EMPLOYEES", "Part-Time Employees", U, "INTEGER", "Number of part-time employees at the premises.", None, False, ["# Part Time Empl"]),
    ("ANNUAL_REVENUE", "Annual Revenue", U, "AMOUNT", "Annual revenue of the business or premises.", None, False, ["Annual Revenues"]),
    ("OCCUPIED_AREA_SQFT", "Occupied Area", PR, "INTEGER", "Square feet occupied by the applicant.", None, False, ["Occupied Area"]),
    ("PUBLIC_AREA_SQFT", "Area Open to the Public", PR, "INTEGER", "Square feet open to the public.", None, False, ["Open to Public Area"]),
    ("SQUARE_FEET", "Total Building Area", PR, "INTEGER", "Total square feet of the building.", None, False, ["Total Building Area", "Total Area"]),
    ("AREA_LEASED_TO_OTHERS_IND", "Area Leased to Others", PR, "CODE", "Part of the premises is leased to others.", "YES_NO", False, ["Any Area Leased to Others"]),
    ("OPERATIONS_DESCRIPTION", "Operations at Premises", U, "TEXT", "What is done at this premises.", None, False, ["Description of Operations"]),
    # ---- prior insurance and losses
    ("PRIOR_POLICY_YEAR", "Prior Policy Year", U, "INTEGER", "Policy year of the prior insurance.", None, False, ["Year"]),
    ("PRIOR_CARRIER", "Prior Carrier", U, "TEXT", "Insurance company that wrote the prior policy.", None, False, ["Carrier (prior)"]),
    ("PRIOR_POLICY_NUMBER", "Prior Policy Number", U, "TEXT", "Number of the prior policy.", None, False, ["Policy Number (prior)"]),
    ("PRIOR_PREMIUM", "Prior Premium", U, "AMOUNT", "Premium of the prior policy.", None, False, ["Premium (prior)"]),
    ("PRIOR_EFFECTIVE_DATE", "Prior Effective Date", U, "DATE", "Start of the prior policy.", None, False, ["Effective Date (prior)"]),
    ("PRIOR_EXPIRATION_DATE", "Prior Expiration Date", U, "DATE", "End of the prior policy.", None, False, ["Expiration Date (prior)"]),
    ("LOSS_HISTORY_YEARS", "Loss History Years", U, "INTEGER", "Number of years of losses reported on the application.", None, False, ["For the last ___ years"]),
    ("NO_PRIOR_LOSSES_IND", "No Prior Losses", U, "CODE", "The applicant reports no losses in the period.", "YES_NO", False, ["Check if none"]),
    ("TOTAL_PRIOR_LOSSES", "Total Prior Losses", U, "AMOUNT", "Total of the losses reported on the application.", None, False, ["Total Losses"]),
    ("PRIOR_LOSS_PAID", "Prior Loss Amount Paid", U, "AMOUNT", "Amount paid on a prior loss.", None, False, ["Amount Paid"]),
    ("PRIOR_LOSS_RESERVED", "Prior Loss Amount Reserved", U, "AMOUNT", "Amount still reserved on a prior loss.", None, False, ["Amount Reserved"]),
    ("PRIOR_CLAIM_OPEN_IND", "Prior Claim Open", U, "CODE", "The prior claim is still open.", "YES_NO", False, ["Claim Open Y/N"]),
    ("SUBROGATION_IND", "Subrogation", CL, "CODE", "Recovery from a third party is being pursued.", "YES_NO", False, ["Subrogation Y/N"]),
    # ---- general liability coverage
    ("CGL_COVERAGE_FORM", "CGL Coverage Form", LI, "CODE", "Whether the general liability policy is occurrence or claims made.", "CGL_COVERAGE_FORM", False,
     ["Claims Made / Occurrence"]),
    ("OCP_IND", "Owners and Contractors Protective", LI, "CODE", "Owner's and contractor's protective coverage is requested.", "YES_NO", False,
     ["Owner's & Contractor's Protective"]),
    ("GENERAL_AGGREGATE_LIMIT", "General Aggregate Limit", LI, "AMOUNT", "Most paid in the policy period for all claims other than products and completed operations.",
     None, False, ["General Aggregate"]),
    ("AGGREGATE_APPLIES_PER", "Aggregate Applies Per", LI, "CODE", "Whether the general aggregate applies per policy, location or project.", "AGGREGATE_APPLIES_PER", False,
     ["Limit Applies Per"]),
    ("PRODUCTS_COMPLETED_OPS_AGGREGATE", "Products-Completed Operations Aggregate", LI, "AMOUNT", "Most paid in the policy period for products and completed operations.",
     None, False, ["Products & Completed Operations Aggregate"]),
    ("PERSONAL_ADVERTISING_INJURY_LIMIT", "Personal and Advertising Injury Limit", LI, "AMOUNT", "Most paid for personal and advertising injury to one person or organization.",
     None, False, ["Personal & Advertising Injury"]),
    ("EACH_OCCURRENCE_LIMIT", "Each Occurrence Limit", LI, "AMOUNT", "Most paid for one occurrence.", None, False, ["Each Occurrence"]),
    ("DAMAGE_TO_RENTED_PREMISES_LIMIT", "Damage to Rented Premises Limit", LI, "AMOUNT", "Most paid for damage to premises rented to the insured.", None, False,
     ["Damage to Rented Premises"]),
    ("MEDICAL_EXPENSE_LIMIT", "Medical Expense Limit", LI, "AMOUNT", "Most paid for medical expenses of one person.", None, False, ["Medical Expense (Any one person)"]),
    ("EMPLOYEE_BENEFITS_LIMIT", "Employee Benefits Limit", LI, "AMOUNT", "Limit for employee benefits liability.", None, False, ["Employee Benefits"]),
    ("PD_DEDUCTIBLE", "Property Damage Deductible", LI, "AMOUNT", "Liability deductible for property damage.", None, False, ["Property Damage"]),
    ("BI_DEDUCTIBLE", "Bodily Injury Deductible", LI, "AMOUNT", "Liability deductible for bodily injury.", None, False, ["Bodily Injury"]),
    ("DEDUCTIBLE_BASIS", "Deductible Basis", LI, "CODE", "Whether a liability deductible applies per claim or per occurrence.", "DEDUCTIBLE_BASIS", False,
     ["Per Claim / Per Occurrence"]),
    ("PREMISES_OPS_PREMIUM", "Premises-Operations Premium", LI, "AMOUNT", "Premium for premises and operations.", None, False, ["Premises/Operations"]),
    ("PRODUCTS_PREMIUM", "Products Premium", LI, "AMOUNT", "Premium for products and completed operations.", None, False, ["Products"]),
    ("RETROACTIVE_DATE", "Retroactive Date", LI, "DATE", "Claims-made: injury before this date is not covered.", None, False, ["Proposed Retroactive Date", "Retroactive Date"]),
    ("CLAIMS_MADE_ENTRY_DATE", "Claims-Made Entry Date", LI, "DATE", "Date the insured entered uninterrupted claims-made coverage.", None, False,
     ["Entry Date into Uninterrupted Claims Made Coverage"]),
    ("EBL_DEDUCTIBLE", "Employee Benefits Deductible", LI, "AMOUNT", "Employee benefits liability deductible per claim.", None, False, ["Deductible per Claim"]),
    ("EBL_EMPLOYEE_COUNT", "Employees for Employee Benefits", LI, "INTEGER", "Number of employees, for employee benefits liability.", None, False, ["Number of Employees"]),
    ("EBL_COVERED_EMPLOYEES", "Employees in Benefit Plans", LI, "INTEGER", "Employees covered by employee benefit plans.", None, False,
     ["Number of Employees Covered by Employee Benefits Plans"]),
    # ---- schedule of hazards
    ("HAZARD_NUMBER", "Hazard Number", R, "INTEGER", "Number of the classification at a location.", None, False, ["Haz #"]),
    ("CLASS_CODE", "Class Code", R, "TEXT", "Rating classification code.", None, False, ["Class Code"]),
    ("EXPOSURE_BASE", "Premium Basis", R, "CODE", "What the classification is rated on: payroll, sales, area, cost, admissions, units.", "EXPOSURE_BASE", False,
     ["Premium Basis", "Rating and Premium Basis"]),
    ("EXPOSURE", "Exposure", R, "AMOUNT", "Amount of the premium basis (payroll, sales, square feet ...).", None, False, ["Exposure"]),
    ("TERRITORY", "Territory", R, "DECIMAL", "Rating territory.", None, False, ["Terr"]),
    ("PREM_OPS_RATE", "Premises-Operations Rate", R, "DECIMAL", "Rate for premises and operations.", None, False, ["Rate Prem / Ops"]),
    ("PRODUCTS_RATE", "Products Rate", R, "DECIMAL", "Rate for products and completed operations.", None, False, ["Rate Products"]),
    ("CLASSIFICATION_DESCRIPTION", "Classification Description", R, "TEXT", "The classification in words.", None, False, ["Classification Description"]),
    # ---- products and contractors
    ("PRODUCT_NAME", "Product", LI, "TEXT", "Product made, sold or distributed.", None, False, ["Products"]),
    ("PRODUCT_ANNUAL_GROSS_SALES", "Product Annual Gross Sales", LI, "AMOUNT", "Yearly gross sales of the product.", None, False, ["Annual Gross Sales"]),
    ("PRODUCT_UNITS", "Product Units Sold", LI, "INTEGER", "Number of units sold.", None, False, ["# of Units"]),
    ("PRODUCT_TIME_IN_MARKET", "Product Time in Market", LI, "TEXT", "How long the product has been on the market.", None, False, ["Time in Market"]),
    ("PRODUCT_EXPECTED_LIFE", "Product Expected Life", LI, "TEXT", "Expected life of the product.", None, False, ["Expected Life"]),
    ("PRODUCT_INTENDED_USE", "Product Intended Use", LI, "TEXT", "What the product is meant to be used for.", None, False, ["Intended Use"]),
    ("PRODUCT_PRINCIPAL_COMPONENTS", "Product Principal Components", LI, "TEXT", "Main components of the product.", None, False, ["Principal Components"]),
    ("SUBCONTRACTED_WORK_DESCRIPTION", "Subcontracted Work", LI, "TEXT", "Kind of work given to subcontractors.", None, False, ["Describe the type of work subcontracted"]),
    ("SUBCONTRACTOR_COST", "Paid to Subcontractors", LI, "AMOUNT", "Amount paid to subcontractors.", None, False, ["$ Paid to Sub-Contractors"]),
    ("SUBCONTRACTED_WORK_PCT", "Work Subcontracted Percent", LI, "PERCENT", "Share of the work done by subcontractors.", None, False, ["% of Work Subcontracted"]),
    ("RENTED_EQUIPMENT_DESCRIPTION", "Equipment Rented to Others", LI, "TEXT", "Equipment rented or loaned to others, and whether instruction is given.", None, False,
     ["Equipment", "Type of Equipment", "Instruction Given"]),
    # ---- property: what is insured
    ("BLANKET_NUMBER", "Blanket Number", PR, "INTEGER", "Number of a blanket limit covering several items.", None, False, ["Blkt #"]),
    ("BLANKET_AMOUNT", "Blanket Amount", PR, "AMOUNT", "Amount of a blanket limit.", None, False, ["Amount (blanket)"]),
    ("BLANKET_TYPE", "Blanket Type", PR, "TEXT", "What a blanket limit covers.", None, False, ["Type (blanket)"]),
    ("SUBJECT_OF_INSURANCE", "Subject of Insurance", PR, "CODE", "What a property limit insures: building, business personal property, business income ...",
     "SUBJECT_OF_INSURANCE", False, ["Subject of Insurance"]),
    ("INSURANCE_AMOUNT", "Amount of Insurance", PR, "AMOUNT", "Limit for the subject of insurance.", None, False, ["Amount"]),
    ("COINSURANCE", "Coinsurance", PR, "CODE", "Coinsurance percentage that applies to the limit.", "COINSURANCE", False, ["Coins %"]),
    ("VALUATION", "Valuation", PR, "CODE", "How a loss is valued: replacement cost, actual cash value, agreed value ...", "VALUATION", False, ["Valuation"]),
    ("CAUSES_OF_LOSS_FORM", "Causes of Loss Form", PR, "CODE", "Which causes of loss the limit covers: basic, broad, special ...", "CAUSES_OF_LOSS_FORM", False,
     ["Causes of Loss"]),
    ("INFLATION_GUARD_PCT", "Inflation Guard Percent", PR, "PERCENT", "Yearly automatic increase of the limit.", None, False, ["Inflation Guard %"]),
    ("DEDUCTIBLE", "Deductible", C, "CODE", "Amount the insured pays before the policy pays.", "DEDUCTIBLE", False, ["Ded"]),
    ("DEDUCTIBLE_TYPE", "Deductible Type", C, "CODE", "Flat amount, percent, franchise or aggregate.", "DEDUCTIBLE_TYPE", False, ["Ded Type"]),
    ("FORMS_AND_CONDITIONS", "Forms and Conditions", PR, "TEXT", "Forms and conditions that apply to the limit.", None, False, ["Forms and Conditions to Apply"]),
    ("SPOILAGE_COVERAGE_IND", "Spoilage Coverage", PR, "CODE", "Spoilage coverage is requested.", "YES_NO", False, ["Spoilage Coverage"]),
    ("SPOILAGE_PROPERTY_DESCRIPTION", "Spoilage Property", PR, "TEXT", "Perishable property covered for spoilage.", None, False, ["Description of Property Covered"]),
    ("SPOILAGE_LIMIT", "Spoilage Limit", PR, "AMOUNT", "Limit for spoilage.", None, False, ["Limit (spoilage)"]),
    ("SPOILAGE_DEDUCTIBLE", "Spoilage Deductible", PR, "AMOUNT", "Deductible for spoilage.", None, False, ["Deductible (spoilage)"]),
    ("REFRIGERATION_MAINT_AGREEMENT_IND", "Refrigeration Maintenance Agreement", PR, "CODE", "A refrigeration maintenance agreement is in place.", "YES_NO", False,
     ["Refrig Maint Agreement"]),
    ("SPOILAGE_OPTION", "Spoilage Option", PR, "CODE", "Spoilage causes covered.", "SPOILAGE_OPTION", False, ["Breakdown or Contamination", "Power Outage", "Selling Price"]),
    ("SINKHOLE_ELECTION", "Sinkhole Coverage Election", PR, "CODE", "Whether offered sinkhole coverage was accepted (required offer in Florida).", "COVERAGE_ELECTION", False,
     ["Sinkhole Coverage"]),
    ("SINKHOLE_LIMIT", "Sinkhole Limit", PR, "AMOUNT", "Limit for sinkhole loss.", None, False, []),
    ("MINE_SUBSIDENCE_ELECTION", "Mine Subsidence Election", PR, "CODE", "Whether offered mine subsidence coverage was accepted.", "COVERAGE_ELECTION", False,
     ["Mine Subsidence Coverage"]),
    ("MINE_SUBSIDENCE_LIMIT", "Mine Subsidence Limit", PR, "AMOUNT", "Limit for mine subsidence.", None, False, []),
    ("HISTORIC_LANDMARK_IND", "Historic Landmark", PR, "CODE", "The property is designated a historical landmark.", "YES_NO", False,
     ["Property has been designated an historical landmark"]),
    ("OPEN_SIDES_COUNT", "Open Sides", PR, "INTEGER", "Number of open sides of the structure.", None, False, ["# of Open Sides on Structure"]),
    # ---- property: the building
    ("CONSTRUCTION", "Construction", PR, "CODE", "Building construction class.", "CONSTRUCTION", False, ["Construction Type"]),
    ("DISTANCE_TO_HYDRANT", "Distance to Hydrant", PR, "INTEGER", "Feet to the nearest fire hydrant.", None, False, ["Distance to Hydrant"]),
    ("DISTANCE_TO_FIRE_STATION", "Distance to Fire Station", PR, "DECIMAL", "Miles to the responding fire station.", None, False, ["Distance to Fire Stat"]),
    ("FIRE_DISTRICT", "Fire District", PR, "TEXT", "Fire district that protects the building.", None, False, ["Fire District"]),
    ("FIRE_DISTRICT_CODE", "Fire District Code", PR, "TEXT", "Code number of the fire district.", None, False, ["Code Number"]),
    ("PROTECTION_CLASS", "Protection Class", PR, "CODE", "Public protection class of the location.", "PROTECTION_CLASS", False, ["Prot Cl"]),
    ("NUMBER_OF_STORIES", "Stories", PR, "INTEGER", "Number of stories above ground.", None, False, ["# Stories"]),
    ("NUMBER_OF_BASEMENTS", "Basements", PR, "INTEGER", "Number of basement levels.", None, False, ["# Basm'ts"]),
    ("YEAR_BUILT", "Year Built", PR, "INTEGER", "Year the building was built.", None, False, ["Yr Built"]),
    ("WIRING_UPDATE_YEAR", "Wiring Updated", PR, "INTEGER", "Year the electrical wiring was last updated.", None, False, ["Wiring, Yr"]),
    ("PLUMBING_UPDATE_YEAR", "Plumbing Updated", PR, "INTEGER", "Year the plumbing was last updated.", None, False, ["Plumbing, Yr"]),
    ("ROOF_YEAR", "Roof Updated", PR, "INTEGER", "Year the roof was last replaced.", None, False, ["Roofing, Yr"]),
    ("HEATING_UPDATE_YEAR", "Heating Updated", PR, "INTEGER", "Year the heating was last updated.", None, False, ["Heating, Yr"]),
    ("OTHER_UPDATE_DESCRIPTION", "Other Building Improvement", PR, "TEXT", "Other building improvement and its year.", None, False, ["Other (improvement)"]),
    ("BUILDING_CODE_GRADE", "Building Code Grade", PR, "TEXT", "Building code effectiveness grade of the community.", None, False, ["Bldg Code Grade"]),
    ("TAX_CODE", "Tax Code", PR, "TEXT", "Tax code of the location.", None, False, ["Tax Code"]),
    ("ROOF_TYPE", "Roof Type", PR, "CODE", "Roof covering.", "ROOF_TYPE", False, ["Roof Type"]),
    ("WIND_CLASS", "Wind Class", PR, "CODE", "Wind resistance of the building.", "WIND_CLASS", False, ["Wind Class"]),
    ("OTHER_OCCUPANCIES", "Other Occupancies", PR, "TEXT", "Other businesses in the building.", None, False, ["Other Occupancies"]),
    ("PRIMARY_HEAT_SOURCE", "Primary Heat", PR, "CODE", "Main way the building is heated.", "HEAT_SOURCE", False, ["Primary Heat"]),
    ("SECONDARY_HEAT_SOURCE", "Secondary Heat", PR, "CODE", "Secondary way the building is heated.", "HEAT_SOURCE", False, ["Secondary Heat"]),
    ("BOILER_INSURED_ELSEWHERE_IND", "Boiler Insured Elsewhere", PR, "CODE", "A boiler is insured under another policy.", "YES_NO", False,
     ["If boiler, is insurance placed elsewhere"]),
    ("SOLID_FUEL_HEATER_DESCRIPTION", "Wood-Burning Heater", PR, "TEXT", "Wood-burning stove or fireplace insert: manufacturer and date installed.", None, False,
     ["Heating source incl woodburning stove or fireplace insert", "Manufacturer", "Date Installed"]),
    ("EXPOSURE_RIGHT", "Right Exposure and Distance", PR, "TEXT", "What is to the right of the building and how far.", None, False, ["Right Exposure & Distance"]),
    ("EXPOSURE_LEFT", "Left Exposure and Distance", PR, "TEXT", "What is to the left of the building and how far.", None, False, ["Left Exposure & Distance"]),
    ("EXPOSURE_FRONT", "Front Exposure and Distance", PR, "TEXT", "What is in front of the building and how far.", None, False, ["Front Exposure & Distance"]),
    ("EXPOSURE_REAR", "Rear Exposure and Distance", PR, "TEXT", "What is behind the building and how far.", None, False, ["Rear Exposure & Distance"]),
    # ---- property: protection
    ("ALARM_TYPE", "Burglar Alarm Type", PR, "CODE", "Kind of burglar alarm.", "ALARM_TYPE", False, ["Burglar Alarm Type"]),
    ("BURGLAR_ALARM_SIGNAL", "Burglar Alarm Signal", PR, "CODE", "Where the burglar alarm reports.", "ALARM_SIGNAL", False, ["Central Station", "With Keys", "Local Gong"]),
    ("ALARM_CERTIFICATE_NUMBER", "Alarm Certificate Number", PR, "TEXT", "Certificate number of the alarm system.", None, False, ["Certificate #"]),
    ("ALARM_CERTIFICATE_EXPIRATION", "Alarm Certificate Expiration", PR, "DATE", "Expiration of the alarm certificate.", None, False, ["Alarm Certificate Expiration Date"]),
    ("ALARM_INSTALLER", "Alarm Installed and Serviced By", PR, "TEXT", "Company that installed and services the alarm.", None, False, ["Burglar Alarm Installed and Serviced By"]),
    ("ALARM_EXTENT", "Alarm Extent", PR, "TEXT", "Extent of the alarm protection.", None, False, ["Extent"]),
    ("ALARM_GRADE", "Alarm Grade", PR, "TEXT", "Grade of the alarm system.", None, False, ["Grade"]),
    ("GUARD_COUNT", "Guards / Watchmen", PR, "INTEGER", "Number of guards or watchmen.", None, False, ["# Guards / Watchmen"]),
    ("GUARD_CLOCK_HOURLY_IND", "Guards Clock Hourly", PR, "CODE", "Guards make hourly clock rounds.", "YES_NO", False, ["Clock Hourly"]),
    ("FIRE_PROTECTION_DESCRIPTION", "Premises Fire Protection", PR, "TEXT", "Sprinklers, standpipes, CO2 or chemical systems.", None, False,
     ["Premises Fire Protection (Sprinklers, Standpipes, CO2 / Chemical Systems)"]),
    ("SPRINKLER_PCT", "Sprinklered Percent", PR, "PERCENT", "Share of the building protected by sprinklers.", None, False, ["% Sprnk"]),
    ("FIRE_ALARM_MANUFACTURER", "Fire Alarm Manufacturer", PR, "TEXT", "Maker of the fire alarm.", None, False, ["Fire Alarm Manufacturer"]),
    ("FIRE_ALARM_SIGNAL", "Fire Alarm Signal", PR, "CODE", "Where the fire alarm reports.", "ALARM_SIGNAL", False, ["Central Station", "Local Gong"]),
    # ---- crime (commercial crime section)
    ("CRIME_COVERAGE_BASIS", "Crime Coverage Basis", CR, "CODE", "Discovery or loss sustained.", "CRIME_COVERAGE_BASIS", False, ["Basis for Coverage"]),
    ("CRIME_COVERAGE_FORM", "Crime Coverage Form", CR, "CODE", "The crime coverage a limit is for.", "CRIME_COVERAGE_FORM", False, ["Form Ltr"]),
    ("CRIME_SCHEDULE_BASIS", "Crime Blanket or Schedule", CR, "CODE", "Whether the crime limit is blanket or scheduled.", "CRIME_SCHEDULE_BASIS", False, []),
    ("CRIME_PREMISES_SECTION", "Crime Premises Section", CR, "CODE", "Inside or outside the premises.", "CRIME_PREMISES_SECTION", False, []),
    ("CRIME_LIMIT", "Crime Limit", CR, "AMOUNT", "Limit for a crime coverage.", None, False, []),
    ("CRIME_DEDUCTIBLE", "Crime Deductible", CR, "AMOUNT", "Deductible for a crime coverage.", None, False, []),
    ("EXTORTION_PARTICIPATION_PCT", "Extortion Insured Participation", CR, "PERCENT", "Share of an extortion loss the insured keeps.", None, False, ["Ins Loss Participation"]),
    ("ERISA_PLAN_NAME", "ERISA Plan Name", CR, "TEXT", "Name of the employee benefit plan covered for employee dishonesty.", None, False, ["Name of Plan"]),
    ("ERISA_PLAN_ADDRESS", "ERISA Plan Address", CR, "TEXT", "Principal address of the plan.", None, False, ["Principal Address"]),
    ("ERISA_TOTAL_ASSET_VALUE", "ERISA Total Asset Value", CR, "AMOUNT", "Total value of the plan's assets.", None, False, ["Total Asset Value"]),
    ("ERISA_HANDLER_COUNT", "Plan Asset Handlers", CR, "INTEGER", "Trustees, employees and others who handle plan assets.", None, False, []),
    ("ERISA_PARTICIPANT_COUNT", "Plan Participants", CR, "INTEGER", "Number of plan participants.", None, False, ["Number of Plan Participants"]),
    ("CRIME_EMPLOYEE_CLASS", "Crime Employee Class", CR, "CODE", "Position of employees who handle money, securities or property.", "CRIME_EMPLOYEE_CLASS", False, []),
    ("CRIME_EMPLOYEE_CLASS_COUNT", "Employees in Class", CR, "INTEGER", "Number of employees in the position.", None, False, []),
    ("OFFICER_COUNT", "Officers", CR, "INTEGER", "Number of officers.", None, False, ["Number of Officers"]),
    ("OTHER_EMPLOYEE_COUNT", "Other Employees", CR, "INTEGER", "Total number of other employees.", None, False, ["Total Number of Other Employees"]),
    ("AGENT_DISTRIBUTOR_COUNT", "Agents and Distributors", CR, "INTEGER", "Manufacturers, processors, wholesalers or distributors acting for the insured.", None, False, []),
    ("CRIME_LOCATION_COUNT", "Locations other than Home and Head Offices", CR, "INTEGER", "Number of retail or other locations.", None, False, []),
    ("AUDITOR_TYPE", "Auditor Type", CR, "CODE", "Who audits the books.", "AUDITOR_TYPE", False, ["Is there an audit by"]),
    ("BOOKS_AUDIT_FREQUENCY", "Books Audit Frequency", CR, "TEXT", "How often the books are audited (not the premium audit).", None, False, ["Audit Frequency"]),
    ("AUDIT_REPORT_RECIPIENT", "Audit Report Recipient", CR, "CODE", "Who the audit report is rendered to.", "AUDIT_REPORT_RECIPIENT", False, ["Audit Report is Rendered To"]),
    ("AUDITOR_NAME_ADDRESS", "Auditor", CR, "TEXT", "Person or firm performing the audit.", None, False, ["Name and Address of Person or Firm Performing Audit"]),
    ("LAST_AUDIT_DATE_CASH", "Last Audit - Cash and Accounts", CR, "DATE", "Date the last audit of cash and accounts was completed.", None, False, ["Cash & Accounts"]),
    ("LAST_AUDIT_DATE_INVENTORY", "Last Audit - Inventory", CR, "DATE", "Date the last inventory audit was completed.", None, False, ["Inventory"]),
    ("CRIME_EXPOSURE_CATEGORY", "Crime Exposure Category", CR, "CODE", "Inside the premises or with a messenger.", "CRIME_EXPOSURE_CATEGORY", False, []),
    ("MONEY_EXPOSURE", "Money", CR, "AMOUNT", "Most money exposed.", None, False, []),
    ("CHECKS_FOR_DEPOSIT_EXPOSURE", "Checks for Deposit", CR, "AMOUNT", "Most checks held for deposit.", None, False, ["Checks for Deposit"]),
    ("CHECKS_ACCOUNTS_PAYABLE_EXPOSURE", "Checks for Accounts Payable", CR, "AMOUNT", "Most checks held for accounts payable.", None, False, ["Checks for Accounts Payable"]),
    ("PAYROLL_CHECKS_EXPOSURE", "Payroll Checks", CR, "AMOUNT", "Most payroll checks held.", None, False, ["Payroll Checks"]),
    ("MONEY_OVERNIGHT_EXPOSURE", "Money Overnight", CR, "AMOUNT", "Most money kept overnight.", None, False, ["Money Overnight"]),
    ("SECURITIES_EXPOSURE", "Securities", CR, "AMOUNT", "Most securities held (in bank or safe deposit).", None, False, []),
    ("CRIME_PROPERTY_DESCRIPTION", "Crime Property", CR, "TEXT", "Property, merchandise or stock covered for theft.", None, False, ["Description of Property, Merchandise, Stock"]),
    ("CRIME_PROPERTY_MAX_VALUE", "Crime Property Maximum Value", CR, "AMOUNT", "Most value of that property at one time.", None, False, ["Maximum Value"]),
    ("BUSINESS_HOURS", "Business Hours", CR, "TEXT", "Hours the business is open.", None, False, ["Business Hours"]),
    ("EMPLOYEES_ON_DUTY_AVG", "Employees on Duty", CR, "INTEGER", "Average number of employees on duty.", None, False, ["Avg # Employees on Duty"]),
    ("CHECKS_STAMPED_DEPOSIT_ONLY_IND", "Checks Stamped for Deposit Only", CR, "CODE", "Checks are stamped for deposit only.", "YES_NO", False, ["Checks Stamped for Deposit Only"]),
    ("DEPOSIT_FREQUENCY", "Deposit Frequency", CR, "TEXT", "How often money is deposited.", None, False, ["Frequency of Deposits"]),
    ("NIGHT_DEPOSITORY_IND", "Night Depository Used", CR, "CODE", "A night depository is used.", "YES_NO", False, ["Night Depository Used"]),
    ("SAFE_MANUFACTURER", "Safe Manufacturer", CR, "TEXT", "Maker of the safe or vault.", None, False, []),
    ("SAFE_LABEL", "Safe Label", CR, "CODE", "UL or SMNA rating label.", "SAFE_LABEL", False, []),
    ("SAFE_CLASS", "Safe Class", CR, "TEXT", "Class of the safe or vault.", None, False, []),
    ("SAFE_DOOR_TYPE", "Safe Door Type", CR, "CODE", "Round or square door.", "SAFE_DOOR_TYPE", False, ["Door Type"]),
    ("SAFE_COMBINATION_LOCKS", "Combination Locks", CR, "TEXT", "Combination locks on the outer door, inner door and chest.", None, False, ["Combination Locks"]),
    ("SAFE_DOOR_THICKNESS", "Safe Door Thickness", CR, "TEXT", "Thickness of the door, without the bolt work.", None, False, []),
    ("SAFE_WALL_THICKNESS", "Safe Wall Thickness", CR, "TEXT", "Thickness of the wall.", None, False, []),
    ("MESSENGER_NUMBER", "Messenger Number", CR, "INTEGER", "Number of the messenger.", None, False, []),
    ("GUARDS_PER_MESSENGER", "Guards per Messenger", CR, "INTEGER", "Guards with each messenger.", None, False, ["# of Guards per Messenger"]),
    ("PRIVATE_CONVEYANCE_IND", "Private Conveyance Used", CR, "CODE", "The messenger uses a private conveyance.", "YES_NO", False, ["Private Conveyance Used"]),
    ("SAFETY_SATCHEL_IND", "Safety Satchel Used", CR, "CODE", "The messenger uses a safety satchel.", "YES_NO", False, ["Safety Satchel Used"]),
    ("ALARM_PROTECTED_AREA", "Alarm Protected Area", CR, "CODE", "Hold-up, premises or safe alarm.", "ALARM_PROTECTED_AREA", False, []),
    ("ALARM_EXTENT_LEVEL", "Alarm Extent Level", CR, "CODE", "Partial or complete; premises level 1 to 3.", "ALARM_EXTENT_LEVEL", False, ["Extent of Protection"]),
    ("WATCHPERSON_COUNT", "Watchpersons", CR, "INTEGER", "Number of watchpersons.", None, False, ["# Watch Persons"]),
    ("WATCHPERSON_SIGNAL", "Watchperson Signal", CR, "CODE", "How watchpersons report.", "WATCHPERSON_SIGNAL", False, []),
    ("ACCESSIBLE_OPENINGS_PROTECTION", "Accessible Openings Protection", CR, "TEXT", "Protection of accessible openings.", None, False, ["Accessible Openings & Protection"]),
    ("OTHER_PROTECTION_DESCRIPTION", "Other Protection", CR, "TEXT", "Fences, floodlights and other protection.", None, False, ["Other Protection"]),
]

# ------------------------------------------------------------------------------------------ entities (how the elements group)
# (code, name, description, parent, [element codes])
ENTITIES = [
    ("PARTY", "Party", "A person or organization, once, whatever roles it plays.", None,
     ["PARTY_ID", "PARTY_TYPE", "INSURED_NAME", "FIRST_NAME", "MIDDLE_NAME", "LAST_NAME", "DBA_NAME", "LEGAL_ENTITY_TYPE", "LLC_MEMBER_MANAGER_COUNT",
      "FEIN", "SSN", "DATE_OF_BIRTH", "BUSINESS_PHONE", "WEBSITE_ADDRESS", "SIC_CODE", "NAICS_CODE", "GL_CLASS_CODE", "NATURE_OF_BUSINESS",
      "DATE_BUSINESS_STARTED", "BUSINESS_DESCRIPTION"]),
    ("PARTY_ROLE", "Party Role", "A party on a policy, submission or claim: first named insured, other named insured, contact, producer ...", "PARTY",
     ["PARTY_ID", "PARTY_ROLE", "PARTY_ROLE_SEQUENCE", "AGENCY_CUSTOMER_ID"]),
    ("PARTY_ADDRESS", "Party Address", "Addresses of a party: mailing, premises, billing ...", "PARTY",
     ["PARTY_ID", "ADDRESS_TYPE", "ADDRESS_STREET", "ADDRESS_LINE_2", "ADDRESS_CITY", "COUNTY", "STATE", "ZIP_CODE", "COUNTRY_CODE"]),
    ("PARTY_CONTACT", "Party Contact", "People and ways to reach a party.", "PARTY",
     ["PARTY_ID", "CONTACT_TYPE", "CONTACT_NAME", "PHONE", "PHONE_TYPE", "PHONE_EXTENSION", "SECONDARY_PHONE", "FAX_NUMBER", "EMAIL", "SECONDARY_EMAIL",
      "CONTACT_METHOD"]),
    ("PARTY_RELATIONSHIP", "Party Relationship", "Parent, subsidiary, affiliate or trust relationships between parties.", "PARTY",
     ["PARTY_ID", "RELATED_PARTY_ID", "PARTY_RELATIONSHIP_TYPE", "RELATIONSHIP_DESCRIPTION", "OWNERSHIP_PCT", "TRUST_NAME"]),
    ("ADDITIONAL_INTEREST", "Additional Interest", "A party with an interest in a location, building, vehicle or item: mortgagee, loss payee, certificate holder ...",
     "PARTY_ROLE",
     ["PARTY_ID", "PARTY_ROLE", "INTEREST_RANK", "EVIDENCE_REQUIRED_IND", "CERTIFICATE_REQUIRED_IND", "POLICY_COPY_REQUIRED_IND", "SEND_BILL_IND",
      "LOAN_NUMBER", "LIEN_AMOUNT", "INTEREST_END_DATE", "INTEREST_REASON", "INTEREST_ITEM_TYPE", "LOCATION_NUMBER", "BUILDING_NUMBER", "ITEM_NUMBER",
      "ITEM_CLASS", "ITEM_DESCRIPTION"]),
    ("PRODUCER", "Producer", "The agency and producer who submit the business.", "PARTY",
     ["AGENCY_NAME", "AGENCY_CUSTOMER_ID", "PRODUCER_CODE", "PRODUCER_NAME", "STATE_PRODUCER_LICENSE_NUMBER", "NATIONAL_PRODUCER_NUMBER"]),
    ("APPLICATION", "Commercial Application", "The submission as a whole.", None,
     ["SUBMISSION_ID", "APPLICATION_DATE", "POLICY_NUMBER", "POLICY_EFFECTIVE_DATE", "CARRIER_NAME", "NAIC_CODE", "LINE_OF_BUSINESS", "NATURE_OF_BUSINESS",
      "RETAIL_SALES_PCT", "ON_PREMISES_INSTALL_PCT", "OFF_PREMISES_INSTALL_PCT", "OTHER_NAMED_INSURED_OPERATIONS", "SAFETY_PROGRAM_ELEMENTS",
      "PRIVACY_NOTICE_GIVEN_IND", "APPLICANT_SIGNED_DATE", "APPLICATION_REMARKS"]),
    ("UW_ANSWER", "Underwriting Answer", "One answer to one underwriting question, with its explanation and any event dates.", "APPLICATION",
     ["UW_QUESTION", "UW_ANSWER_IND", "UW_ANSWER_EXPLANATION", "UW_EVENT_DATE", "UW_EVENT_RESOLUTION", "UW_EVENT_RESOLVED_DATE", "PRIOR_CANCEL_REASON"]),
    ("PREMISES", "Premises", "A location the applicant occupies and what happens there.", "APPLICATION",
     ["LOCATION_NUMBER", "BUILDING_NUMBER", "ADDRESS_STREET", "ADDRESS_CITY", "COUNTY", "STATE", "ZIP_CODE", "INSIDE_CITY_LIMITS_IND", "PREMISES_INTEREST",
      "FULL_TIME_EMPLOYEES", "PART_TIME_EMPLOYEES", "ANNUAL_REVENUE", "OCCUPIED_AREA_SQFT", "PUBLIC_AREA_SQFT", "SQUARE_FEET", "AREA_LEASED_TO_OTHERS_IND",
      "OPERATIONS_DESCRIPTION"]),
    ("PRIOR_INSURANCE", "Prior Insurance", "Prior policies by year and line.", "APPLICATION",
     ["PRIOR_POLICY_YEAR", "LINE_OF_BUSINESS", "PRIOR_CARRIER", "PRIOR_POLICY_NUMBER", "PRIOR_PREMIUM", "PRIOR_EFFECTIVE_DATE", "PRIOR_EXPIRATION_DATE"]),
    ("LOSS_HISTORY", "Loss History", "Losses the applicant reports, insured or not.", "APPLICATION",
     ["LOSS_HISTORY_YEARS", "NO_PRIOR_LOSSES_IND", "LOSS_DATE", "LINE_OF_BUSINESS", "LOSS_DESCRIPTION", "REPORT_DATE", "PRIOR_LOSS_PAID",
      "PRIOR_LOSS_RESERVED", "SUBROGATION_IND", "PRIOR_CLAIM_OPEN_IND", "TOTAL_PRIOR_LOSSES"]),
    ("CGL_COVERAGE", "General Liability Coverage", "Limits, deductibles and premiums of a general liability policy.", "APPLICATION",
     ["CGL_COVERAGE_FORM", "OCP_IND", "GENERAL_AGGREGATE_LIMIT", "AGGREGATE_APPLIES_PER", "PRODUCTS_COMPLETED_OPS_AGGREGATE",
      "PERSONAL_ADVERTISING_INJURY_LIMIT", "EACH_OCCURRENCE_LIMIT", "DAMAGE_TO_RENTED_PREMISES_LIMIT", "MEDICAL_EXPENSE_LIMIT", "EMPLOYEE_BENEFITS_LIMIT",
      "PD_DEDUCTIBLE", "BI_DEDUCTIBLE", "DEDUCTIBLE_BASIS", "PREMISES_OPS_PREMIUM", "PRODUCTS_PREMIUM", "RETROACTIVE_DATE", "CLAIMS_MADE_ENTRY_DATE",
      "EBL_DEDUCTIBLE", "EBL_EMPLOYEE_COUNT", "EBL_COVERED_EMPLOYEES"]),
    ("CGL_HAZARD", "General Liability Hazard", "One classification at one location: exposure, rates and premiums.", "CGL_COVERAGE",
     ["LOCATION_NUMBER", "HAZARD_NUMBER", "CLASS_CODE", "EXPOSURE_BASE", "EXPOSURE", "TERRITORY", "PREM_OPS_RATE", "PRODUCTS_RATE", "PREMISES_OPS_PREMIUM",
      "PRODUCTS_PREMIUM", "CLASSIFICATION_DESCRIPTION"]),
    ("PRODUCT", "Product", "A product made, sold or distributed by the applicant.", "CGL_COVERAGE",
     ["PRODUCT_NAME", "PRODUCT_ANNUAL_GROSS_SALES", "PRODUCT_UNITS", "PRODUCT_TIME_IN_MARKET", "PRODUCT_EXPECTED_LIFE", "PRODUCT_INTENDED_USE",
      "PRODUCT_PRINCIPAL_COMPONENTS"]),
    ("CONTRACTOR_OPERATIONS", "Contractor Operations", "Work given to subcontractors and equipment leased to others.", "CGL_COVERAGE",
     ["SUBCONTRACTED_WORK_DESCRIPTION", "SUBCONTRACTOR_COST", "SUBCONTRACTED_WORK_PCT", "FULL_TIME_EMPLOYEES", "PART_TIME_EMPLOYEES", "RENTED_EQUIPMENT_DESCRIPTION"]),
    ("PROPERTY_COVERAGE", "Property Coverage", "One subject of insurance at one building, with its limit and terms.", "APPLICATION",
     ["LOCATION_NUMBER", "BUILDING_NUMBER", "SUBJECT_OF_INSURANCE", "INSURANCE_AMOUNT", "COINSURANCE", "VALUATION", "CAUSES_OF_LOSS_FORM", "INFLATION_GUARD_PCT",
      "DEDUCTIBLE", "DEDUCTIBLE_TYPE", "BLANKET_NUMBER", "FORMS_AND_CONDITIONS"]),
    ("BLANKET", "Blanket", "A blanket limit shared by several items.", "PROPERTY_COVERAGE", ["BLANKET_NUMBER", "BLANKET_AMOUNT", "BLANKET_TYPE"]),
    ("PROPERTY_OPTIONS", "Property Options", "Additional property coverages, options and elections.", "PROPERTY_COVERAGE",
     ["SPOILAGE_COVERAGE_IND", "SPOILAGE_PROPERTY_DESCRIPTION", "SPOILAGE_LIMIT", "SPOILAGE_DEDUCTIBLE", "REFRIGERATION_MAINT_AGREEMENT_IND", "SPOILAGE_OPTION",
      "SINKHOLE_ELECTION", "SINKHOLE_LIMIT", "MINE_SUBSIDENCE_ELECTION", "MINE_SUBSIDENCE_LIMIT", "HISTORIC_LANDMARK_IND", "OPEN_SIDES_COUNT"]),
    ("BUILDING", "Building", "Construction, age, updates and surroundings of a building.", "PREMISES",
     ["LOCATION_NUMBER", "BUILDING_NUMBER", "BUILDING_DESCRIPTION", "CONSTRUCTION", "DISTANCE_TO_HYDRANT", "DISTANCE_TO_FIRE_STATION", "FIRE_DISTRICT",
      "FIRE_DISTRICT_CODE", "PROTECTION_CLASS", "NUMBER_OF_STORIES", "NUMBER_OF_BASEMENTS", "YEAR_BUILT", "SQUARE_FEET", "WIRING_UPDATE_YEAR",
      "PLUMBING_UPDATE_YEAR", "ROOF_YEAR", "HEATING_UPDATE_YEAR", "OTHER_UPDATE_DESCRIPTION", "BUILDING_CODE_GRADE", "TAX_CODE", "ROOF_TYPE", "WIND_CLASS",
      "OTHER_OCCUPANCIES", "PRIMARY_HEAT_SOURCE", "SECONDARY_HEAT_SOURCE", "BOILER_INSURED_ELSEWHERE_IND", "SOLID_FUEL_HEATER_DESCRIPTION",
      "EXPOSURE_RIGHT", "EXPOSURE_LEFT", "EXPOSURE_FRONT", "EXPOSURE_REAR"]),
    ("CRIME_COVERAGE", "Crime Coverage", "Crime coverages applied for, with limits and deductibles.", "APPLICATION",
     ["CRIME_COVERAGE_BASIS", "CRIME_COVERAGE_FORM", "CRIME_SCHEDULE_BASIS", "CRIME_PREMISES_SECTION", "CRIME_LIMIT", "CRIME_DEDUCTIBLE", "EXTORTION_PARTICIPATION_PCT"]),
    ("CRIME_ERISA_PLAN", "ERISA Plan", "Employee benefit plan covered for employee dishonesty.", "CRIME_COVERAGE",
     ["ERISA_PLAN_NAME", "ERISA_PLAN_ADDRESS", "ERISA_TOTAL_ASSET_VALUE", "ERISA_HANDLER_COUNT", "ERISA_PARTICIPANT_COUNT"]),
    ("CRIME_EMPLOYEES", "Crime Employee Classification", "Employees who handle or have custody of money, securities or property.", "CRIME_COVERAGE",
     ["CRIME_EMPLOYEE_CLASS", "CRIME_EMPLOYEE_CLASS_COUNT", "OFFICER_COUNT", "OTHER_EMPLOYEE_COUNT", "AGENT_DISTRIBUTOR_COUNT", "CRIME_LOCATION_COUNT"]),
    ("CRIME_CONTROLS", "Crime Controls", "Audit and internal controls (yes / no answers are UW_ANSWER rows).", "CRIME_COVERAGE",
     ["AUDITOR_TYPE", "BOOKS_AUDIT_FREQUENCY", "AUDIT_REPORT_RECIPIENT", "AUDITOR_NAME_ADDRESS", "LAST_AUDIT_DATE_CASH", "LAST_AUDIT_DATE_INVENTORY"]),
    ("CRIME_EXPOSURES", "Money and Securities Exposures", "Most money, checks and securities exposed inside or with a messenger.", "CRIME_COVERAGE",
     ["LOCATION_NUMBER", "CRIME_EXPOSURE_CATEGORY", "MESSENGER_NUMBER", "MONEY_EXPOSURE", "CHECKS_FOR_DEPOSIT_EXPOSURE", "CHECKS_ACCOUNTS_PAYABLE_EXPOSURE",
      "PAYROLL_CHECKS_EXPOSURE", "MONEY_OVERNIGHT_EXPOSURE", "SECURITIES_EXPOSURE", "CRIME_PROPERTY_DESCRIPTION", "CRIME_PROPERTY_MAX_VALUE",
      "BUSINESS_HOURS", "EMPLOYEES_ON_DUTY_AVG", "CHECKS_STAMPED_DEPOSIT_ONLY_IND", "DEPOSIT_FREQUENCY", "NIGHT_DEPOSITORY_IND"]),
    ("SAFE_VAULT", "Safe or Vault", "A safe or vault at a crime location.", "CRIME_COVERAGE",
     ["SAFE_MANUFACTURER", "SAFE_LABEL", "SAFE_CLASS", "SAFE_DOOR_TYPE", "SAFE_COMBINATION_LOCKS", "SAFE_DOOR_THICKNESS", "SAFE_WALL_THICKNESS"]),
    ("MESSENGER", "Messenger Protection", "Messengers carrying money or securities.", "CRIME_COVERAGE",
     ["MESSENGER_NUMBER", "GUARDS_PER_MESSENGER", "PRIVATE_CONVEYANCE_IND", "SAFETY_SATCHEL_IND"]),
    ("CRIME_PROTECTION", "Premises and Safe Protection", "Alarms, guards and watchpersons for crime.", "CRIME_COVERAGE",
     ["ALARM_PROTECTED_AREA", "BURGLAR_ALARM_SIGNAL", "ALARM_GRADE", "ALARM_EXTENT_LEVEL", "ALARM_INSTALLER", "ALARM_CERTIFICATE_NUMBER",
      "ALARM_CERTIFICATE_EXPIRATION", "GUARD_COUNT", "WATCHPERSON_COUNT", "WATCHPERSON_SIGNAL", "ACCESSIBLE_OPENINGS_PROTECTION", "OTHER_PROTECTION_DESCRIPTION"]),
    ("BUILDING_PROTECTION", "Building Protection", "Alarms, guards, sprinklers and fire protection of a building.", "BUILDING",
     ["ALARM_TYPE", "BURGLAR_ALARM_SIGNAL", "ALARM_CERTIFICATE_NUMBER", "ALARM_CERTIFICATE_EXPIRATION", "ALARM_INSTALLER", "ALARM_EXTENT", "ALARM_GRADE",
      "GUARD_COUNT", "GUARD_CLOCK_HOURLY_IND", "FIRE_PROTECTION_DESCRIPTION", "SPRINKLER_TYPE", "SPRINKLER_PCT", "FIRE_ALARM_MANUFACTURER", "FIRE_ALARM_SIGNAL"]),
]

# Which form each element appears on (for the synonym source, i.e. where-used)
FORM_OF = {}
for _code, *_rest in ELEMENTS:
    FORM_OF[_code] = "ACORD 125"
for _ent, _forms in (("CGL_COVERAGE", "ACORD 126"), ("CGL_HAZARD", "ACORD 126"), ("PRODUCT", "ACORD 126"), ("CONTRACTOR_OPERATIONS", "ACORD 126"),
                     ("PROPERTY_COVERAGE", "ACORD 140"), ("BLANKET", "ACORD 140"), ("PROPERTY_OPTIONS", "ACORD 140"), ("BUILDING", "ACORD 140"),
                     ("BUILDING_PROTECTION", "ACORD 140"), ("CRIME_COVERAGE", "ACORD 141"), ("CRIME_ERISA_PLAN", "ACORD 141"), ("CRIME_EMPLOYEES", "ACORD 141"),
                     ("CRIME_CONTROLS", "ACORD 141"), ("CRIME_EXPOSURES", "ACORD 141"), ("SAFE_VAULT", "ACORD 141"), ("MESSENGER", "ACORD 141"),
                     ("CRIME_PROTECTION", "ACORD 141")):
    for _el in next(e for e in ENTITIES if e[0] == _ent)[4]:
        if _el not in ("LOCATION_NUMBER", "BUILDING_NUMBER", "FULL_TIME_EMPLOYEES", "PART_TIME_EMPLOYEES", "SQUARE_FEET"):
            FORM_OF[_el] = _forms


GENERIC_LABELS = {"rank", "date", "amount", "products", "item", "year", "certificate", "policy", "evidence", "interest", "extent", "grade",
                  "exposure", "equipment", "explanation", "resolution", "central station", "local gong", "with keys", "ded", "ded type", "terr",
                  "y / n", "carrier", "city", "county", "zip", "street", "type of equipment", "instruction given", "manufacturer", "date installed"}


def catalog() -> dict:
    """The model as a collector catalog: pick lists with options, elements with their form labels as synonyms."""
    import collect_si2_databases as K
    cat = K.new_catalog(SOURCE)
    for code, name, desc, opts in PICKLISTS:
        pl = K.add_picklist(cat, f"PL:{code}", code, name, desc, library="SI2")
        for oc, on in opts:
            K.add_option(pl, oc, on, None)
    pls = {code for code, *_ in PICKLISTS}
    for pl in cat["picklists"].values():
        pl["keep_code"] = True
    uses = {}
    for e in ELEMENTS:
        for lab in e[7]:
            uses[lab.lower()] = uses.get(lab.lower(), 0) + 1
    for code, name, subject, dtype, desc, picklist, pii, labels in ELEMENTS:
        labels = [x for x in labels if x.lower() not in GENERIC_LABELS and uses[x.lower()] == 1]   # a label on several fields says nothing
        cat["elements"][f"DE:{code}"] = {
            "code": code, "name": name, "desc": desc, "dtype": dtype, "subject": subject, "pii": pii, "curated": True,
            "picklist_key": f"PL:{picklist}" if picklist in pls else None, "picklist_code": picklist,
            "aliases": [(lab, FORM_OF.get(code, "ACORD 125")) for lab in labels]}
    return cat


def check(seed_elements: set, seed_picklists: set) -> list[str]:
    """Every entity attribute is an element here or in the seed; every pick list exists; codes are unique."""
    codes = [e[0] for e in ELEMENTS]
    problems = [f"duplicate element {c}" for c in set(codes) if codes.count(c) > 1]
    known = set(codes) | seed_elements
    for ent in ENTITIES:
        problems += [f"{ent[0]}: unknown element {c}" for c in ent[4] if c not in known]
        if ent[3] and ent[3] not in {x[0] for x in ENTITIES}:
            problems.append(f"{ent[0]}: unknown parent {ent[3]}")
    pls = {p[0] for p in PICKLISTS} | seed_picklists
    problems += [f"{e[0]}: unknown pick list {e[5]}" for e in ELEMENTS if e[5] and e[5] not in pls]
    return problems


# ------------------------------------------------------------------------------------------ SQL: entities
def _q(v) -> str:
    return "CAST(NULL AS nvarchar(4000))" if v is None else "N'" + str(v).replace("'", "''") + "'"


def build_sql() -> str:
    """09_commercial_app.sql: the LIABILITY subject area, the entity layer (canon.Entity, canon.EntityAttribute, canon.vw_EntityModel)."""
    names = {e[0]: e[1] for e in ELEMENTS}
    ents = ",\n".join(f"    ({_q(c)}, {_q(n)}, {_q(d)}, {_q(p)}, {i * 10})" for i, (c, n, d, p, _) in enumerate(ENTITIES, 1))
    attrs = ",\n".join(f"    ({_q(c)}, {j}, {_q(el)}, {_q(names.get(el))})" for c, _, _, _, els in ENTITIES for j, el in enumerate(els, 1))
    return f"""/* =====================================================================================================
   SI² Canonical Master · commercial application model: Party first
   -----------------------------------------------------------------------------------------------------
   canon.Entity            how the data elements group: PARTY, PARTY_ROLE, PARTY_ADDRESS, PARTY_CONTACT, PARTY_RELATIONSHIP,
                           ADDITIONAL_INTEREST, PRODUCER, APPLICATION, UW_ANSWER, PREMISES, PRIOR_INSURANCE, LOSS_HISTORY,
                           CGL_COVERAGE, CGL_HAZARD, PRODUCT, CONTRACTOR_OPERATIONS, PROPERTY_COVERAGE, BLANKET, PROPERTY_OPTIONS,
                           BUILDING, BUILDING_PROTECTION
   canon.EntityAttribute   the elements of each entity; an element is found by its code, or by a synonym when the master
                           already had it under another name
   canon.vw_EntityModel    each entity with its elements as they are in the master today
   The elements and pick lists themselves are proposed by: collect_si2_databases.py --commercial-app (Saba approves).
   Safe to re-run.
   ===================================================================================================== */
USE SI2Canonical;
GO
INSERT canon.SubjectArea (SubjectAreaCode, Name, Description, SortOrder, CreatedBy)
SELECT N'LIABILITY', N'General Liability', N'Liability coverages, limits, hazards, products and contractors.', 75, N'SI2 commercial app'
WHERE NOT EXISTS (SELECT 1 FROM canon.SubjectArea WHERE SubjectAreaCode = N'LIABILITY');
GO
INSERT canon.SubjectArea (SubjectAreaCode, Name, Description, SortOrder, CreatedBy)
SELECT N'CRIME', N'Crime', N'Crime coverages, employee classes, controls, money and securities exposures, safes and messengers.', 76, N'SI2 commercial app'
WHERE NOT EXISTS (SELECT 1 FROM canon.SubjectArea WHERE SubjectAreaCode = N'CRIME');
GO
IF OBJECT_ID(N'canon.Entity') IS NULL
CREATE TABLE canon.Entity (
    EntityCode   varchar(60)    NOT NULL CONSTRAINT PK_Entity PRIMARY KEY,
    Name         nvarchar(200)  NOT NULL,
    Description  nvarchar(1000) NULL,
    ParentEntity varchar(60)    NULL,
    SortOrder    int            NOT NULL CONSTRAINT DF_Entity_Sort DEFAULT (100),
    Status       varchar(10)    NOT NULL CONSTRAINT DF_Entity_Status DEFAULT ('ACTIVE'),
    CreatedBy    nvarchar(100)  NOT NULL CONSTRAINT DF_Entity_By DEFAULT (SUSER_SNAME()),
    CreatedAt    datetime2(0)   NOT NULL CONSTRAINT DF_Entity_At DEFAULT (SYSUTCDATETIME())
);
GO
IF OBJECT_ID(N'canon.EntityAttribute') IS NULL
CREATE TABLE canon.EntityAttribute (
    EntityCode   varchar(60)   NOT NULL CONSTRAINT FK_EntityAttr_Entity REFERENCES canon.Entity (EntityCode),
    Seq          int           NOT NULL,
    ElementCode  varchar(80)   NOT NULL,
    ElementName  nvarchar(200) NULL,
    CreatedBy    nvarchar(100) NOT NULL CONSTRAINT DF_EntityAttr_By DEFAULT (SUSER_SNAME()),
    CONSTRAINT PK_EntityAttribute PRIMARY KEY (EntityCode, ElementCode)
);
GO
IF COL_LENGTH(N'canon.EntityAttribute', N'MasterElementCode') IS NULL
    ALTER TABLE canon.EntityAttribute ADD MasterElementCode varchar(80) NULL;   -- the master element it was matched to (set by the collector)
GO
CREATE OR ALTER VIEW canon.vw_EntityModel
AS
SELECT en.EntityCode AS Entity, en.Name AS EntityName, en.ParentEntity, a.Seq, a.ElementCode AS ModelCode,
       el.ElementCode, el.Name AS ElementName, el.DataType, p.PickListCode AS PickList, el.SubjectAreaCode AS SubjectArea, el.IsPII,
       CASE WHEN el.ElementId IS NULL THEN 'NOT YET' WHEN el.ElementCode = a.ElementCode THEN 'IN MODEL' ELSE 'IN MODEL AS ' + el.ElementCode END AS InMaster,
       en.SortOrder
FROM canon.Entity en
JOIN canon.EntityAttribute a ON a.EntityCode = en.EntityCode
OUTER APPLY (SELECT TOP (1) e.* FROM canon.DataElement e
             WHERE e.ScopeId = 1 AND e.Status <> 'EXPIRED'
               AND (e.ElementCode = a.ElementCode OR e.ElementCode = a.MasterElementCode
                    OR EXISTS (SELECT 1 FROM canon.Synonym s WHERE s.ObjectType = 'ELEMENT' AND s.ObjectId = e.ElementId AND s.Status <> 'EXPIRED'
                               AND s.SynonymText IN (a.ElementCode, a.ElementName))
                    OR e.Name = a.ElementName)
             ORDER BY CASE WHEN e.ElementCode = a.MasterElementCode THEN 0 WHEN e.ElementCode = a.ElementCode THEN 1 ELSE 2 END) el
LEFT JOIN canon.PickList p ON p.PickListId = el.PickListId
WHERE en.Status = 'ACTIVE';
GO
INSERT canon.Entity (EntityCode, Name, Description, ParentEntity, SortOrder, CreatedBy)
SELECT v.c, v.n, v.d, v.p, v.s, N'SI2 commercial app'
FROM (VALUES
{ents}
) v (c, n, d, p, s)
WHERE NOT EXISTS (SELECT 1 FROM canon.Entity x WHERE x.EntityCode = v.c);
GO
INSERT canon.EntityAttribute (EntityCode, Seq, ElementCode, ElementName, CreatedBy)
SELECT v.e, v.s, v.c, v.n, N'SI2 commercial app'
FROM (VALUES
{attrs}
) v (e, s, c, n)
WHERE NOT EXISTS (SELECT 1 FROM canon.EntityAttribute x WHERE x.EntityCode = v.e AND x.ElementCode = v.c);
GO
SELECT (SELECT COUNT(*) FROM canon.Entity) AS Entities, (SELECT COUNT(*) FROM canon.EntityAttribute) AS Attributes;
GO
"""


if __name__ == "__main__":
    import sys
    from pathlib import Path
    here = Path(__file__).resolve().parent
    sys.path.insert(0, str(here))
    import rule_repo as R
    cat = R.seed_catalog()
    problems = check(set(cat.elements), set(cat.options))
    if problems:
        sys.exit("\n".join(problems))
    (here / "09_commercial_app.sql").write_text(build_sql(), encoding="utf-8")
    print(f"09_commercial_app.sql written: {len(ENTITIES)} entities, {sum(len(e[4]) for e in ENTITIES)} attributes; "
          f"{len(ELEMENTS)} elements and {len(PICKLISTS)} pick lists go through the collector (--commercial-app)")
