"""More P&C data elements and pick lists for the SI² Canonical Master (common industry vocabulary).

Codes are SI² company codes; where a public standard exists (USPS, NAICS sectors, NHTSA body styles) the code
follows it. Bureau codes are added only where the SI² catalogs already know them.
"""

# (code, name, description, library, [(code, name)])
LISTS = [
    ("US_TERRITORY", "US Territory", "US territories and the District of Columbia (USPS).", "USPS", [
        ("DC", "District of Columbia"), ("PR", "Puerto Rico"), ("VI", "U.S. Virgin Islands"), ("GU", "Guam"),
        ("AS", "American Samoa"), ("MP", "Northern Mariana Islands")]),
    ("NAICS_SECTOR", "NAICS Sector", "Two-digit North American Industry Classification System sector.", "NAICS", [
        ("11", "Agriculture, Forestry, Fishing and Hunting"), ("21", "Mining, Quarrying, and Oil and Gas Extraction"),
        ("22", "Utilities"), ("23", "Construction"), ("31-33", "Manufacturing"), ("42", "Wholesale Trade"),
        ("44-45", "Retail Trade"), ("48-49", "Transportation and Warehousing"), ("51", "Information"),
        ("52", "Finance and Insurance"), ("53", "Real Estate and Rental and Leasing"),
        ("54", "Professional, Scientific, and Technical Services"), ("55", "Management of Companies and Enterprises"),
        ("56", "Administrative and Support and Waste Management"), ("61", "Educational Services"),
        ("62", "Health Care and Social Assistance"), ("71", "Arts, Entertainment, and Recreation"),
        ("72", "Accommodation and Food Services"), ("81", "Other Services (except Public Administration)"),
        ("92", "Public Administration")]),
    ("LEGAL_ENTITY_TYPE", "Legal Entity Type", "Legal form of an organization.", "SI2", [
        ("INDIVIDUAL", "Individual / sole proprietor"), ("PARTNERSHIP", "Partnership"), ("LLC", "Limited liability company"),
        ("CORPORATION", "Corporation"), ("S_CORP", "S corporation"), ("NONPROFIT", "Non-profit organization"),
        ("TRUST", "Trust or estate"), ("GOVERNMENT", "Government entity"), ("JOINT_VENTURE", "Joint venture")]),
    ("SPRINKLER_TYPE", "Sprinkler Protection", "Automatic sprinkler protection of a building.", "SI2", [
        ("NONE", "None"), ("PARTIAL", "Partial"), ("FULL", "Full, wet system"), ("DRY", "Full, dry system"),
        ("ESFR", "Early suppression fast response")]),
    ("ALARM_TYPE", "Alarm Type", "Fire or burglar alarm on a dwelling or building.", "SI2", [
        ("NONE", "None"), ("LOCAL", "Local alarm"), ("CENTRAL", "Central station"), ("POLICE_FIRE", "Direct to police / fire")]),
    ("FOUNDATION_TYPE", "Foundation Type", "Foundation of a dwelling.", "SI2", [
        ("SLAB", "Slab"), ("BASEMENT", "Basement"), ("CRAWL", "Crawl space"), ("PIER", "Pier / piling"), ("ELEVATED", "Elevated")]),
    ("DWELLING_TYPE", "Dwelling Type", "Kind of residence.", "SI2", [
        ("SINGLE_FAMILY", "Single family"), ("TOWNHOUSE", "Townhouse / row house"), ("CONDO", "Condominium unit"),
        ("DUPLEX", "Two family"), ("TRIPLEX_FOURPLEX", "Three or four family"), ("MOBILE", "Manufactured / mobile home"),
        ("APARTMENT", "Apartment unit (renter)")]),
    ("WIND_MITIGATION", "Wind Mitigation Feature", "Wind-resistive construction features (credit eligible).", "SI2", [
        ("HURRICANE_STRAPS", "Roof-to-wall straps / clips"), ("SHUTTERS", "Opening protection / shutters"),
        ("SECONDARY_WATER", "Secondary water resistance"), ("ROOF_DECK", "Enhanced roof-deck attachment"),
        ("FORTIFIED", "IBHS FORTIFIED designation")]),
    ("FLOOD_ZONE", "Flood Zone", "FEMA flood zone designation.", "FEMA", [
        ("A", "Zone A (1% annual chance, no BFE)"), ("AE", "Zone AE (1% annual chance, with BFE)"), ("AH", "Zone AH (shallow ponding)"),
        ("AO", "Zone AO (sheet flow)"), ("V", "Zone V (coastal high hazard)"), ("VE", "Zone VE (coastal high hazard, with BFE)"),
        ("X500", "Zone X shaded (0.2% annual chance)"), ("X", "Zone X unshaded (minimal hazard)"), ("D", "Zone D (undetermined)")]),
    ("BODY_STYLE", "Vehicle Body Style", "Body style of a vehicle.", "SI2", [
        ("SEDAN", "Sedan"), ("COUPE", "Coupe"), ("CONVERTIBLE", "Convertible"), ("HATCHBACK", "Hatchback"), ("WAGON", "Station wagon"),
        ("SUV", "Sport utility"), ("PICKUP", "Pickup"), ("VAN", "Van / minivan"), ("MOTORCYCLE", "Motorcycle")]),
    ("FUEL_TYPE", "Fuel Type", "Vehicle fuel or power source.", "SI2", [
        ("GAS", "Gasoline"), ("DIESEL", "Diesel"), ("HYBRID", "Hybrid"), ("PHEV", "Plug-in hybrid"), ("EV", "Battery electric"),
        ("FLEX", "Flex fuel"), ("CNG", "Compressed natural gas")]),
    ("ANTI_THEFT", "Anti-Theft Device", "Anti-theft equipment on a vehicle.", "SI2", [
        ("NONE", "None"), ("PASSIVE", "Passive disabling device"), ("ACTIVE", "Active disabling device"), ("ALARM", "Alarm only"),
        ("TRACKING", "Vehicle recovery / tracking system")]),
    ("GARAGING_TYPE", "Garaging Type", "Where the vehicle is kept overnight.", "SI2", [
        ("GARAGE", "Private garage"), ("CARPORT", "Carport"), ("DRIVEWAY", "Driveway"), ("STREET", "Street"), ("LOT", "Parking lot / structure")]),
    ("LICENSE_STATUS", "Driver License Status", "Status of a driver's license.", "SI2", [
        ("VALID", "Valid"), ("PERMIT", "Learner's permit"), ("SUSPENDED", "Suspended"), ("REVOKED", "Revoked"), ("EXPIRED", "Expired"),
        ("FOREIGN", "Foreign / international")]),
    ("VIOLATION_TYPE", "Violation Type", "Kind of motor vehicle violation.", "SI2", [
        ("SPEED_MINOR", "Speeding, minor"), ("SPEED_MAJOR", "Speeding, major"), ("DUI", "Driving under the influence"),
        ("RECKLESS", "Reckless driving"), ("AT_FAULT_ACC", "At-fault accident"), ("DWS", "Driving while suspended"),
        ("LEAVING_SCENE", "Leaving the scene"), ("DISTRACTED", "Distracted driving"), ("EQUIPMENT", "Equipment / minor violation")]),
    ("LOSS_SEVERITY", "Claim Severity Band", "Severity band of a claim by incurred amount.", "SI2", [
        ("LOW", "Under $5,000"), ("MEDIUM", "$5,000 - $25,000"), ("HIGH", "$25,000 - $100,000"), ("LARGE", "$100,000 - $1,000,000"),
        ("SHOCK", "Over $1,000,000")]),
    ("RECOVERY_SOURCE", "Recovery Source", "Where a recovery comes from.", "SI2", [
        ("SUBROGATION", "Subrogation"), ("SALVAGE", "Salvage"), ("REINSURANCE", "Reinsurance"), ("DEDUCTIBLE", "Deductible reimbursement"),
        ("CONTRIBUTION", "Contribution from another insurer")]),
    ("PAYMENT_TYPE", "Claim Payment Type", "Kind of claim payment.", "SI2", [
        ("INDEMNITY", "Indemnity / loss"), ("MEDICAL", "Medical"), ("EXPENSE_DCC", "Defense and cost containment"),
        ("EXPENSE_AO", "Adjusting and other"), ("RECOVERY", "Recovery (negative payment)")]),
    ("CLAIM_CLOSE_REASON", "Claim Close Reason", "Why a claim was closed.", "SI2", [
        ("PAID", "Paid"), ("DENIED", "Denied - no coverage"), ("WITHDRAWN", "Withdrawn by claimant"), ("BELOW_DED", "Below deductible"),
        ("SETTLED", "Settled"), ("JUDGMENT", "Judgment"), ("DUPLICATE", "Duplicate claim")]),
    ("CANCEL_REASON", "Cancellation Reason", "Why a policy was cancelled.", "SI2", [
        ("NONPAY", "Non-payment of premium"), ("INSURED_REQ", "Insured request"), ("UW", "Underwriting reasons"),
        ("FRAUD", "Fraud / misrepresentation"), ("SOLD", "Property sold / vehicle sold"), ("REWRITE", "Rewritten")]),
    ("POLICY_TERM", "Policy Term", "Length of the policy term.", "SI2", [
        ("6M", "Six months"), ("12M", "Twelve months"), ("36M", "Three years"), ("SHORT", "Short term"), ("CONT", "Continuous until cancelled")]),
    ("CYBER_CONTROL", "Cyber Security Control", "Security control considered in cyber underwriting.", "SI2", [
        ("MFA", "Multi-factor authentication"), ("EDR", "Endpoint detection and response"), ("BACKUP_OFFLINE", "Offline / immutable backups"),
        ("PATCHING", "Timely patching"), ("TRAINING", "Phishing training"), ("IR_PLAN", "Incident response plan"), ("ENCRYPTION", "Encryption at rest")]),
    ("SUBMISSION_STATUS", "Submission Status", "Status of a new-business submission.", "SI2", [
        ("RECEIVED", "Received"), ("IN_REVIEW", "In review"), ("QUOTED", "Quoted"), ("BOUND", "Bound"), ("DECLINED", "Declined"),
        ("LOST", "Not taken / lost"), ("WITHDRAWN", "Withdrawn")]),
    ("LANGUAGE", "Preferred Language", "Customer's preferred language for communication.", "ISO639", [
        ("en", "English"), ("es", "Spanish"), ("zh", "Chinese"), ("vi", "Vietnamese"), ("ko", "Korean"), ("fr", "French"), ("ar", "Arabic"),
        ("ta", "Tamil"), ("hi", "Hindi")]),
    ("CONTACT_METHOD", "Contact Method", "Preferred way to contact the customer.", "SI2", [
        ("EMAIL", "Email"), ("PHONE", "Phone"), ("SMS", "Text message"), ("MAIL", "Postal mail"), ("PORTAL", "Online portal")]),
]

# (code, name, description, type, pick list, PII)
ELEMENTS = [
    ("COVERAGE_A_LIMIT", "Coverage A Dwelling Limit", "Limit for the dwelling (homeowners Coverage A).", "AMOUNT", None, False),
    ("COVERAGE_C_LIMIT", "Coverage C Personal Property Limit", "Limit for personal property (homeowners Coverage C).", "AMOUNT", None, False),
    ("REPLACEMENT_COST", "Replacement Cost", "Estimated cost to rebuild the structure.", "AMOUNT", None, False),
    ("DWELLING_TYPE", "Dwelling Type", "Kind of residence.", "CODE", "DWELLING_TYPE", False),
    ("NUMBER_OF_STORIES", "Number of Stories", "Stories above grade.", "INTEGER", None, False),
    ("NUMBER_OF_UNITS", "Number of Units", "Dwelling or building units.", "INTEGER", None, False),
    ("FOUNDATION_TYPE", "Foundation Type", "Foundation of the dwelling.", "CODE", "FOUNDATION_TYPE", False),
    ("ALARM_TYPE", "Alarm Type", "Fire or burglar alarm.", "CODE", "ALARM_TYPE", False),
    ("SPRINKLER_TYPE", "Sprinkler Protection", "Automatic sprinkler protection.", "CODE", "SPRINKLER_TYPE", False),
    ("WIND_MITIGATION", "Wind Mitigation Feature", "Wind-resistive feature present (credit eligible).", "CODE", "WIND_MITIGATION", False),
    ("FLOOD_ZONE", "Flood Zone", "FEMA flood zone of the location.", "CODE", "FLOOD_ZONE", False),
    ("DISTANCE_TO_FIRE_STATION", "Distance to Fire Station", "Road miles to the responding fire station.", "DECIMAL", None, False),
    ("DISTANCE_TO_HYDRANT", "Distance to Hydrant", "Feet to the nearest fire hydrant.", "INTEGER", None, False),
    ("WILDFIRE_SCORE", "Wildfire Risk Score", "Wildfire hazard score for the location.", "DECIMAL", None, False),
    ("ROOF_YEAR", "Roof Year", "Year the roof covering was installed or replaced.", "INTEGER", None, False),
    ("NAICS_CODE", "NAICS Code", "North American Industry Classification System code of the insured's business.", "TEXT", None, False),
    ("NAICS_SECTOR", "NAICS Sector", "Two-digit NAICS sector.", "CODE", "NAICS_SECTOR", False),
    ("SIC_CODE", "SIC Code", "Standard Industrial Classification code (legacy).", "TEXT", None, False),
    ("LEGAL_ENTITY_TYPE", "Legal Entity Type", "Legal form of the insured organization.", "CODE", "LEGAL_ENTITY_TYPE", False),
    ("ANNUAL_REVENUE", "Annual Revenue", "Insured's annual gross revenue / sales.", "AMOUNT", None, False),
    ("ANNUAL_PAYROLL", "Annual Payroll", "Insured's annual payroll.", "AMOUNT", None, False),
    ("YEARS_IN_BUSINESS", "Years in Business", "Years the insured has operated.", "INTEGER", None, False),
    ("BUSINESS_DESCRIPTION", "Business Description", "Description of the insured's operations.", "TEXT", None, False),
    ("BODY_STYLE", "Vehicle Body Style", "Body style of the vehicle.", "CODE", "BODY_STYLE", False),
    ("FUEL_TYPE", "Fuel Type", "Fuel or power source of the vehicle.", "CODE", "FUEL_TYPE", False),
    ("ANTI_THEFT", "Anti-Theft Device", "Anti-theft equipment.", "CODE", "ANTI_THEFT", False),
    ("GARAGING_TYPE", "Garaging Type", "Where the vehicle is kept overnight.", "CODE", "GARAGING_TYPE", False),
    ("GARAGING_ZIP", "Garaging ZIP Code", "ZIP code where the vehicle is principally garaged.", "TEXT", None, False),
    ("ODOMETER_READING", "Odometer Reading", "Odometer miles at inception.", "INTEGER", None, False),
    ("VEHICLE_COST_NEW", "Vehicle Cost New", "Manufacturer's suggested retail price when new.", "AMOUNT", None, False),
    ("LICENSE_STATUS", "Driver License Status", "Status of the driver's license.", "CODE", "LICENSE_STATUS", False),
    ("LICENSE_STATE", "License State", "State that issued the driver's license.", "CODE", "STATE", False),
    ("LICENSE_NUMBER", "Driver License Number", "Driver's license number (personal data).", "TEXT", None, True),
    ("VIOLATION_TYPE", "Violation Type", "Kind of motor vehicle violation.", "CODE", "VIOLATION_TYPE", False),
    ("VIOLATION_DATE", "Violation Date", "Date of the violation.", "DATE", None, False),
    ("GOOD_STUDENT_IND", "Good Student Indicator", "Student driver qualifies for a good-student discount.", "CODE", "YES_NO", False),
    ("LOSS_LOCATION_ZIP", "Loss Location ZIP", "ZIP code where the loss occurred.", "TEXT", None, False),
    ("LOSS_DESCRIPTION", "Loss Description", "Free-text description of the loss.", "TEXT", None, False),
    ("CATASTROPHE_IND", "Catastrophe Indicator", "Loss is part of a declared catastrophe event.", "CODE", "YES_NO", False),
    ("LOSS_SEVERITY", "Claim Severity Band", "Severity band of the claim.", "CODE", "LOSS_SEVERITY", False),
    ("LITIGATION_IND", "Litigation Indicator", "A lawsuit has been filed on the claim.", "CODE", "YES_NO", False),
    ("RECOVERY_SOURCE", "Recovery Source", "Where a recovery comes from.", "CODE", "RECOVERY_SOURCE", False),
    ("RECOVERY_AMOUNT", "Recovery Amount", "Amount recovered (salvage, subrogation, reinsurance).", "AMOUNT", None, False),
    ("PAYMENT_TYPE", "Claim Payment Type", "Kind of claim payment.", "CODE", "PAYMENT_TYPE", False),
    ("CLAIM_CLOSE_REASON", "Claim Close Reason", "Why the claim was closed.", "CODE", "CLAIM_CLOSE_REASON", False),
    ("ADJUSTER_ID", "Adjuster ID", "Identifier of the assigned adjuster.", "TEXT", None, False),
    ("DAYS_TO_REPORT", "Days to Report", "Days between the loss and the report.", "INTEGER", None, False),
    ("CANCEL_REASON", "Cancellation Reason", "Why the policy was cancelled.", "CODE", "CANCEL_REASON", False),
    ("POLICY_TERM", "Policy Term", "Length of the policy term.", "CODE", "POLICY_TERM", False),
    ("RENEWAL_COUNT", "Renewal Count", "Number of times the policy has renewed.", "INTEGER", None, False),
    ("PRIOR_CARRIER", "Prior Carrier", "Insurer that covered the risk before this policy.", "TEXT", None, False),
    ("ANNUAL_PREMIUM", "Annual Premium", "Full-term premium annualized.", "AMOUNT", None, False),
    ("SUBMISSION_STATUS", "Submission Status", "Status of the submission.", "CODE", "SUBMISSION_STATUS", False),
    ("QUOTE_NUMBER", "Quote Number", "Identifier of a quote.", "TEXT", None, False),
    ("CYBER_CONTROL", "Cyber Security Control", "Security control in place (cyber underwriting).", "CODE", "CYBER_CONTROL", False),
    ("RECORDS_HELD", "Personal Records Held", "Number of personal records the insured stores (cyber).", "INTEGER", None, False),
    ("PREFERRED_LANGUAGE", "Preferred Language", "Customer's preferred language.", "CODE", "LANGUAGE", False),
    ("CONTACT_METHOD", "Contact Method", "Preferred way to contact the customer.", "CODE", "CONTACT_METHOD", False),
    ("CUSTOMER_ID", "Customer ID", "Identifier of the customer across policies.", "TEXT", None, False),
    ("CUSTOMER_TENURE_YEARS", "Customer Tenure", "Years the customer has been with the company.", "INTEGER", None, False),
    ("LAPSE_RISK_SCORE", "Lapse Risk Score", "SI² probability that the policy will not renew (0-100).", "DECIMAL", None, False),
    ("LOSS_RATIO", "Loss Ratio", "Incurred losses divided by earned premium for the segment being monitored.", "DECIMAL", None, False),
    ("COMBINED_RATIO", "Combined Ratio", "Loss ratio plus expense ratio for the segment being monitored.", "DECIMAL", None, False),
    ("EXPENSE_RATIO", "Expense Ratio", "Underwriting expenses divided by written premium.", "DECIMAL", None, False),
    ("PREMIUM_GROWTH_PCT", "Premium Growth Percent", "Change in written premium against the same period last year, in percent.", "DECIMAL", None, False),
    ("RETENTION_RATE", "Retention Rate", "Share of policies up for renewal that renewed.", "DECIMAL", None, False),
    ("RATE_CHANGE_PCT", "Rate Change Percent", "Proposed rate change for a segment, in percent.", "DECIMAL", None, False),
    ("DAYS_PAST_DUE", "Days Past Due", "Days since the unpaid installment was due.", "INTEGER", None, False),
    ("CLAIM_PAYMENT_AMOUNT", "Claim Payment Amount", "Amount of a single claim payment being issued.", "AMOUNT", None, False),
    ("MFA_IND", "Multi-Factor Authentication", "The insured enforces multi-factor authentication for remote and email access (cyber).", "CODE", "YES_NO", False),
    ("EDR_IND", "Endpoint Detection and Response", "The insured runs endpoint detection and response on all endpoints (cyber).", "CODE", "YES_NO", False),
    ("BACKUP_OFFLINE_IND", "Offline Backups", "The insured keeps offline or immutable backups (cyber).", "CODE", "YES_NO", False),
    ("INSURANCE_SCORE_IND", "Insurance Score Used", "A credit-based insurance score is used in underwriting or rating.", "CODE", "YES_NO", False),
    ("PRODUCER_LICENSED_IND", "Producer Licensed in State", "The producing agent is licensed and appointed in the risk state.", "CODE", "YES_NO", False),
    ("NUMBER_OF_VEHICLES", "Number of Vehicles", "Power units on the policy (fleet size).", "INTEGER", None, False),
    ("UNDERLYING_LIABILITY_LIMIT", "Underlying Liability Limit", "Liability limit of the underlying policy an umbrella sits above.", "AMOUNT", None, False),
    ("NOTICE_DAYS_GIVEN", "Notice Days Given", "Days between the cancellation notice and the cancellation effective date.", "INTEGER", None, False),
    ("COMPANY_CODE", "Writing Company Code", "Legal entity within the group that writes the policy (NAIC code).", "TEXT", None, False),
]
