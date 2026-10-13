"""The rule assistant: a business person says what they want in plain English, SI² turns it into a draft rule.

    "Decline homes in Georgia with a roof older than 20 years"
        -> template UW_DECLINE, condition ROOF_AGE > 20, applies to line HO, state GA,
           and it notices that this is a state version of HO-E01 (same override key), so Georgia gets 20 and everywhere else keeps 25.

The parser works without any AI: canonical element names, synonyms and a business vocabulary, operator words
("older than", "at least", "between ... and ..."), numbers ("1.5 million", "25k", "70%") and pick-list codes.
With an Anthropic API key, Claude reads the sentence first and the parser checks every element and code it returns.
"""
from __future__ import annotations

import json
import re

from rule_engine import Rule, describe_condition

STATES = {"AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California", "CO": "Colorado", "CT": "Connecticut",
          "DE": "Delaware", "DC": "District of Columbia", "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois",
          "IN": "Indiana", "IA": "Iowa", "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
          "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi", "MO": "Missouri", "MT": "Montana", "NE": "Nebraska",
          "NV": "Nevada", "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York", "NC": "North Carolina",
          "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island",
          "SC": "South Carolina", "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah", "VT": "Vermont", "VA": "Virginia",
          "WA": "Washington", "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming"}
AMBIGUOUS_STATE_CODES = {"IN", "OR", "ME", "OK", "PA", "DE", "HI", "AS", "AT"}     # English words or line codes: need "state" nearby or a full name

LOB_WORDS = [  # longest first
    ("commercial general liability", "GL"), ("general liability", "GL"), ("commercial property", "CP"), ("commercial auto", "CA"),
    ("business auto", "CA"), ("commercial umbrella", "UMB"), ("personal umbrella", "UMB"), ("workers compensation", "WC"),
    ("workers comp", "WC"), ("businessowners", "BP"), ("homeowners", "HO"), ("personal auto", "PA"), ("dwelling fire", "HO"),
    ("umbrella", "UMB"), ("excess", "UMB"), ("cyber", "CYB"), ("bop", "BP"), ("homes", "HO"), ("home", "HO"), ("dwellings", "HO"),
    ("dwelling", "HO"), ("house", "HO"), ("condo", "HO"), ("renters", "HO"), ("trucks", "CA"), ("truck", "CA"), ("fleet", "CA"),
    ("auto", "PA"), ("cars", "PA"), ("car", "PA"), ("drivers", "PA"), ("driver", "PA"), ("buildings", "CP"), ("building", "CP"),
]
PRODUCT_WORDS = {"HO-3": "HO3", "HO3": "HO3", "HO-5": "HO5", "HO5": "HO5", "HO-4": "HO4", "HO4": "HO4", "HO-6": "HO6", "HO6": "HO6",
                 "DP-3": "DP3", "DP3": "DP3", "PUP": "PUP", "BOP": "BOP"}
COMPANY_WORDS = {"si² mutual": "SIM", "si2 mutual": "SIM", "sim": "SIM", "mutual": "SIM", "si² specialty": "SIS", "si2 specialty": "SIS",
                 "sis": "SIS", "specialty": "SIS"}

# business words -> element (checked before element names; longest first)
ALIASES = {
    "roof": "ROOF_AGE", "coast": "DISTANCE_TO_COAST", "coastline": "DISTANCE_TO_COAST", "year built": "YEAR_BUILT", "built": "YEAR_BUILT",
    "coverage a": "COVERAGE_A_LIMIT", "dwelling limit": "COVERAGE_A_LIMIT", "coverage c": "COVERAGE_C_LIMIT", "contents": "COVERAGE_C_LIMIT",
    "personal property": "COVERAGE_C_LIMIT", "wildfire": "WILDFIRE_SCORE", "tiv": "TOTAL_INSURED_VALUE", "insured value": "TOTAL_INSURED_VALUE",
    "prior claims": "PRIOR_CLAIMS", "prior losses": "PRIOR_CLAIMS", "claim history": "PRIOR_CLAIMS", "losses": "PRIOR_CLAIMS",
    "driver age": "DRIVER_AGE", "drivers": "DRIVER_AGE", "driver": "DRIVER_AGE", "years old": "DRIVER_AGE", "non-payment": "CANCEL_REASON",
    "nonpayment": "CANCEL_REASON", "non payment": "CANCEL_REASON", "vehicle value": "VEHICLE_VALUE", "vehicle worth": "VEHICLE_VALUE", "car worth": "VEHICLE_VALUE",
    "revenue": "ANNUAL_REVENUE", "sales": "ANNUAL_REVENUE", "square feet": "SQUARE_FEET", "sq ft": "SQUARE_FEET", "sqft": "SQUARE_FEET",
    "payroll": "ANNUAL_PAYROLL", "experience mod": "EXPERIENCE_MODIFICATION_FACTOR", "emod": "EXPERIENCE_MODIFICATION_FACTOR",
    "mod": "EXPERIENCE_MODIFICATION_FACTOR", "records": "RECORDS_HELD", "vehicles": "NUMBER_OF_VEHICLES", "power units": "NUMBER_OF_VEHICLES",
    "years in business": "YEARS_IN_BUSINESS", "violations": "VIOLATIONS", "tickets": "VIOLATIONS", "mfa": "MFA_IND",
    "multi-factor": "MFA_IND", "multifactor": "MFA_IND", "edr": "EDR_IND", "endpoint": "EDR_IND", "offline backups": "BACKUP_OFFLINE_IND",
    "backups": "BACKUP_OFFLINE_IND", "backup": "BACKUP_OFFLINE_IND", "rate change": "RATE_CHANGE_PCT", "rate increase": "RATE_CHANGE_PCT",
    "loss ratio": "LOSS_RATIO", "combined ratio": "COMBINED_RATIO", "expense ratio": "EXPENSE_RATIO", "premium growth": "PREMIUM_GROWTH_PCT",
    "growth": "PREMIUM_GROWTH_PCT", "retention": "RETENTION_RATE", "past due": "DAYS_PAST_DUE", "balance": "ACCOUNT_BALANCE",
    "reported": "DAYS_TO_REPORT", "report lag": "DAYS_TO_REPORT", "attorney": "ATTORNEY_INDICATOR", "lawyer": "ATTORNEY_INDICATOR",
    "represented": "ATTORNEY_INDICATOR", "lawsuit": "LITIGATION_IND", "litigation": "LITIGATION_IND", "litigated": "LITIGATION_IND",
    "in suit": "LITIGATION_IND", "catastrophe": "CATASTROPHE_IND", "cat event": "CATASTROPHE_IND", "payment": "CLAIM_PAYMENT_AMOUNT",
    "payments": "CLAIM_PAYMENT_AMOUNT", "incurred": "INCURRED_LOSS", "claim amount": "INCURRED_LOSS", "loss amount": "INCURRED_LOSS",
    "days notice": "NOTICE_DAYS_GIVEN", "days of notice": "NOTICE_DAYS_GIVEN", "notice": "NOTICE_DAYS_GIVEN", "unlicensed": "PRODUCER_LICENSED_IND",
    "not licensed": "PRODUCER_LICENSED_IND", "producer licensed": "PRODUCER_LICENSED_IND", "credit score": "INSURANCE_SCORE_IND",
    "insurance score": "INSURANCE_SCORE_IND", "underlying": "UNDERLYING_LIABILITY_LIMIT", "flood zone": "FLOOD_ZONE",
    "protection class": "PROTECTION_CLASS", "ppc": "PROTECTION_CLASS", "unsprinklered": "SPRINKLER_TYPE", "sprinklers": "SPRINKLER_TYPE",
    "sprinklered": "SPRINKLER_TYPE", "sprinkler": "SPRINKLER_TYPE", "frame": "CONSTRUCTION", "vacant": "OCCUPANCY", "unoccupied": "OCCUPANCY",
    "tenant": "OCCUPANCY", "alarm": "ALARM_TYPE", "good student": "GOOD_STUDENT_IND", "dui": "VIOLATION_TYPE", "dwi": "VIOLATION_TYPE",
    "suspended": "LICENSE_STATUS", "revoked": "LICENSE_STATUS", "rideshare": "VEHICLE_USE", "uber": "VEHICLE_USE", "delivery": "VEHICLE_USE",
    "heavy trucks": "VEHICLE_TYPE", "tractors": "VEHICLE_TYPE", "wind mitigation": "WIND_MITIGATION", "hurricane straps": "WIND_MITIGATION",
    "shutters": "WIND_MITIGATION", "naics": "NAICS_SECTOR", "anti-theft": "ANTI_THEFT", "tracking device": "ANTI_THEFT",
}
# a word that is itself the value: element -> (operator, value)
VALUE_WORDS = {
    "unsprinklered": ("SPRINKLER_TYPE", "=", "NONE"), "frame": ("CONSTRUCTION", "=", "FR"), "vacant": ("OCCUPANCY", "IN", "VACANT,UNOCCUPIED"),
    "unoccupied": ("OCCUPANCY", "IN", "VACANT,UNOCCUPIED"), "tenant": ("OCCUPANCY", "=", "TENANT"), "dui": ("VIOLATION_TYPE", "=", "DUI"),
    "dwi": ("VIOLATION_TYPE", "=", "DUI"), "suspended": ("LICENSE_STATUS", "IN", "SUSPENDED,REVOKED"), "revoked": ("LICENSE_STATUS", "IN", "SUSPENDED,REVOKED"),
    "rideshare": ("VEHICLE_USE", "=", "RIDESHARE"), "uber": ("VEHICLE_USE", "=", "RIDESHARE"), "delivery": ("VEHICLE_USE", "=", "DELIVERY"),
    "heavy trucks": ("VEHICLE_TYPE", "IN", "HEAVY_TRUCK,TRACTOR"), "tractors": ("VEHICLE_TYPE", "IN", "HEAVY_TRUCK,TRACTOR"),
    "unlicensed": ("PRODUCER_LICENSED_IND", "=", "N"), "not licensed": ("PRODUCER_LICENSED_IND", "=", "N"),
    "hurricane straps": ("WIND_MITIGATION", "=", "HURRICANE_STRAPS"), "shutters": ("WIND_MITIGATION", "=", "SHUTTERS"),
    "litigated": ("LITIGATION_IND", "=", "Y"), "in suit": ("LITIGATION_IND", "=", "Y"), "lawsuit": ("LITIGATION_IND", "=", "Y"),
    "litigation": ("LITIGATION_IND", "=", "Y"), "catastrophe": ("CATASTROPHE_IND", "=", "Y"), "cat event": ("CATASTROPHE_IND", "=", "Y"),
    "good student": ("GOOD_STUDENT_IND", "=", "Y"), "non-payment": ("CANCEL_REASON", "=", "NONPAY"),
    "nonpayment": ("CANCEL_REASON", "=", "NONPAY"), "non payment": ("CANCEL_REASON", "=", "NONPAY"), "tracking device": ("ANTI_THEFT", "=", "TRACKING"),
}
NEGATION = re.compile(r"\b(no|without|not|lacks?|lacking|missing|never|non)\b[\w\s-]{0,12}$", re.I)

TEMPLATE_WORDS = [  # (template, words) checked in order; the first with a hit wins unless the role prefers another hit
    ("SIU_REFER", ["siu", "fraud", "special investigation"]),
    ("REIN_FAC", ["reinsurance", "facultative", "fac "]),
    ("EXEC_ALERT", ["alert", "loss ratio", "combined ratio", "expense ratio", "retention", "premium growth", "notify the ceo", "tell the ceo"]),
    ("CLAIM_AUTHORITY", ["claim payment", "payment above", "payments above", "payments over", "payment over", "reserve above", "reserve change"]),
    ("RATE_CHANGE_CAP", ["rate change", "rate increase"]),
    ("UW_AUTHORITY", ["approval", "approve", "authority", "sign off", "sign-off", "sign-off"]),
    ("RATE_SURCHARGE", ["surcharge", "load ", "loading", "charge more", "debit"]),
    ("RATE_CREDIT", ["credit", "discount", "charge less"]),
    ("FORM_ATTACH", ["attach", "endorsement", "form "]),
    ("COMP_NOTICE", ["notice"]),
    ("COMP_PROHIBIT", ["prohibit", "not allowed", "may not", "cannot use", "can't use", "must not", "illegal"]),
    ("BILL_ACTION", ["past due", "collections", "billing", "non-payment", "nonpayment"]),
    ("CLAIM_ROUTE", ["route", "fast track", "fast-track", "litigation unit", "cat team", "complex unit", "assign the claim", "claim to"]),
    ("DIST_ELIGIBILITY", ["producer", "agent not", "unlicensed", "not licensed", "appointment"]),
    ("DQ_REQUIRED", ["missing", "required", "must be present", "blank"]),
    ("DQ_WARN", ["warn", "warning", "looks wrong", "suspicious value"]),
    ("UW_REFER", ["refer", "review", "look at", "check with", "send to"]),
    ("UW_DECLINE", ["decline", "do not write", "don't write", "not eligible", "ineligible", "reject", "no new business", "outside appetite"]),
]

OPS = [  # phrase -> operator, longest first
    ("greater than or equal to", ">="), ("less than or equal to", "<="), ("no more than", "<="), ("no less than", ">="), ("not more than", "<="),
    ("more than", ">"), ("greater than", ">"), ("higher than", ">"), ("larger than", ">"), ("bigger than", ">"), ("older than", ">"),
    ("longer than", ">"), ("later than", ">"), ("exceeds", ">"), ("exceeding", ">"), ("above", ">"), ("over", ">"), ("after", ">"),
    ("passes", ">"), ("tops", ">"), ("at least", ">="), ("minimum of", ">="), ("less than", "<"), ("fewer than", "<"), ("lower than", "<"),
    ("younger than", "<"), ("newer than", "<"), ("shorter than", "<"), ("smaller than", "<"), ("under", "<"), ("below", "<"), ("before", "<"),
    ("within", "<="), ("at most", "<="), ("up to", "<="), (">=", ">="), ("<=", "<="), ("≥", ">="), ("≤", "<="), (">", ">"), ("<", "<"),
    ("not equal to", "<>"), ("equals", "="), ("equal to", "="), ("=", "="),
]
NUMBER = re.compile(r"(?<![\w.])(-?\$?\d[\d,]*(?:\.\d+)?)\s*(million|mm|m|thousand|k|percent|%|billion|bn)?(?![\w])", re.I)


def _num(text: str, unit: str | None) -> float:
    v = float(text.replace("$", "").replace(",", ""))
    u = (unit or "").lower()
    return v * {"million": 1e6, "mm": 1e6, "m": 1e6, "thousand": 1e3, "k": 1e3, "billion": 1e9, "bn": 1e9}.get(u, 1)


def _fmt(v: float) -> str:
    return str(int(v)) if float(v).is_integer() else f"{v:.4f}".rstrip("0").rstrip(".")


def _vocabulary(catalog) -> list[tuple[str, str]]:
    """(phrase, element) longest first: aliases, element names, readable codes, readable synonyms."""
    vocab = {k: v for k, v in ALIASES.items() if v in catalog.elements}
    skip = {"STATE", "LOB", "COMPANY", "PRODUCT", "STATE_CODE", "LINE_OF_BUSINESS"}
    for code, e in catalog.elements.items():
        if code in skip:
            continue
        for phrase in [e["name"], code.replace("_", " ")] + [s.replace("_", " ") for s in catalog.synonyms.get(code, [])]:
            p = re.sub(r"\s+", " ", str(phrase).lower()).strip()
            if len(p) >= 5 and re.fullmatch(r"[a-z][a-z0-9 /&'-]*", p) and p not in vocab:
                vocab[p] = code
    return sorted(vocab.items(), key=lambda kv: -len(kv[0]))


def find_mentions(text: str, catalog) -> list[dict]:
    low = text.lower()
    taken = [False] * len(low)
    out = []
    for phrase, code in _vocabulary(catalog):
        for m in re.finditer(r"(?<![a-z0-9-])" + re.escape(phrase) + r"(?:s|es)?(?![a-z0-9])", low):
            if any(taken[m.start():m.end()]):
                continue
            for i in range(m.start(), m.end()):
                taken[i] = True
            out.append({"element": code, "start": m.start(), "end": m.end(), "phrase": phrase})
    return sorted(out, key=lambda x: x["start"])


def _option_values(clause: str, catalog, element: str) -> list[str]:
    opts = catalog.element_options(element)
    if not opts:
        return []
    hits = []
    for code, name in opts:
        for probe in sorted({code, name, code.replace("_", " "), name.split(" / ")[0], name.split(" (")[0]}, key=len, reverse=True):
            m = re.search(r"(?<![\w])" + re.escape(probe.lower()) + r"(?![\w])", clause.lower()) if len(probe) > 1 else None
            if m:
                hits.append((m.start(), code))
                break
    found = [c for _, c in sorted(hits)]
    for m in re.finditer(r"(?<![\w.])(\d{1,2})(?![\w.])", clause):    # "class 9 or 10" -> 09, 10
        z = m[1].zfill(2)
        if z in {c for c, _ in opts} and z not in found and m[1] not in found:
            found.append(z)
    return sorted(found) if all(f.isdigit() for f in found) else found


def _condition(element: str, clause: str, before: str, catalog, mention: str) -> tuple | None:
    """Read operator and value(s) for one element from the words after (or before) it."""
    e = catalog.elements.get(element, {})
    if mention in VALUE_WORDS and VALUE_WORDS[mention][0] == element:
        _, op, v = VALUE_WORDS[mention]
        if NEGATION.search(before) and v in ("Y", "N"):
            v = "N" if v == "Y" else "Y"
        return (element, op, v, None)
    if e.get("picklist") == "YES_NO":
        neg = NEGATION.search(before) or re.match(r"\s*(is |are )?(not|missing|absent|off|disabled|n\b|no\b)", clause, re.I)
        return (element, "=", "N" if neg else "Y", None)
    if re.search(r"\b(is missing|is blank|is empty|missing|not provided)\b", clause[:30], re.I):
        return (element, "IS NULL", None, None)
    if e.get("picklist"):
        vals = _option_values(clause[:80], catalog, element) or _option_values(before[-40:], catalog, element)
        if vals:
            neg = re.match(r"\s*(is |are )?(not|other than)\b", clause, re.I)
            if len(vals) == 1:
                return (element, "<>" if neg else "=", vals[0], None)
            return (element, "NOT IN" if neg else "IN", ",".join(vals), None)
    ratio = element.endswith(("_RATIO", "_RATE")) or element in ("LOSS_RATIO", "RETENTION_RATE")

    def value(m):
        v = _num(m[1], m[2])
        if ratio and (m[2] in ("%", "percent") or v > 1.5):
            v = v / 100
        return _fmt(v)

    for window, where in ((clause, "after"), (before, "before")):
        bm = re.search(r"between\s+" + NUMBER.pattern + r"\s+and\s+" + NUMBER.pattern, window, re.I)
        if bm:
            lo, hi = _num(bm[1], bm[2]), _num(bm[3], bm[4])
            if ratio:
                lo, hi = (lo / 100 if lo > 1.5 else lo), (hi / 100 if hi > 1.5 else hi)
            return (element, "BETWEEN", _fmt(lo), _fmt(hi))
        nums = list(NUMBER.finditer(window))
        if not nums:
            continue
        m = nums[0] if where == "after" else nums[-1]
        head = window[:m.start()].lower() if where == "after" else window[max(0, m.start() - 40):m.start()].lower()
        tail = window[m.end():m.end() + 14].lower()
        op = None
        for phrase, o in OPS:
            if re.search(r"(?<![a-z])" + re.escape(phrase) + r"(?![a-z])", head[-28:]):
                op = o
                break
        if re.match(r"\s*(\+|or more|or older|or higher|or greater|plus)", tail):
            op = ">="
        elif re.match(r"\s*(or less|or fewer|or younger|or lower)", tail):
            op = "<="
        if op is None and element == "DAYS_TO_REPORT" and "late" in tail:
            op = ">"
        return (element, op or "=", value(m), None)
    return None


def parse_scope(text: str, catalog=None) -> dict:
    scope: dict = {}
    low = text.lower()
    taken = [False] * len(low)

    def take(m):
        if any(taken[m.start():m.end()]):
            return False
        for i in range(m.start(), m.end()):
            taken[i] = True
        return True

    for name_code in sorted(STATES.items(), key=lambda kv: -len(kv[1])):
        code, name = name_code
        for m in re.finditer(r"(?<![a-z])" + re.escape(name.lower()) + r"(?![a-z])", low):
            if take(m):
                scope.setdefault("STATE", []).append(code)
    for m in re.finditer(r"(?<![A-Za-z])([A-Z]{2})(?![A-Za-z])", text):
        code = m[1]
        if code in STATES and code not in scope.get("STATE", []):
            near = text[max(0, m.start() - 12):m.end() + 8].lower()
            if code in AMBIGUOUS_STATE_CODES and not re.search(r"state|,|\band\b|/", near):
                continue
            if code in AMBIGUOUS_STATE_CODES and code in ("PA",) and re.search(r"\bauto\b", low) and "state" not in near:
                continue
            scope.setdefault("STATE", []).append(code)
    for word, code in PRODUCT_WORDS.items():
        if re.search(r"(?<![A-Za-z0-9])" + re.escape(word) + r"(?![A-Za-z0-9])", text, re.I):
            if code not in scope.get("PRODUCT", []):
                scope.setdefault("PRODUCT", []).append(code)
    for word, code in LOB_WORDS:
        for m in re.finditer(r"(?<![a-z])" + re.escape(word) + r"(?![a-z])", low):
            if take(m) and code not in scope.get("LOB", []):
                scope.setdefault("LOB", []).append(code)
    if "BP" in scope.get("LOB", []) and "BOP" in scope.get("PRODUCT", []):
        pass
    for word, code in COMPANY_WORDS.items():
        if re.search(r"(?<![a-z0-9²])" + re.escape(word) + r"(?![a-z0-9])", low):
            if code not in scope.get("COMPANY", []):
                scope.setdefault("COMPANY", []).append(code)
    return scope


def choose_template(text: str, templates: list[dict], role: str | None = None) -> str:
    low = " " + text.lower() + " "
    hits = [t for t, words in TEMPLATE_WORDS if any(w in low for w in words)]
    known = {t["code"] for t in templates}
    hits = [h for h in hits if h in known]
    if role:
        mine = [h for h in hits if next((t for t in templates if t["code"] == h), {}).get("role") == role]
        if mine:
            return mine[0]
    if hits:
        return hits[0]
    own = [t["code"] for t in templates if t.get("role") == role]
    return own[0] if own else "UW_REFER"


def _action_value(text: str, template: dict) -> tuple[str | None, str]:
    """The template's action value from the sentence, and the sentence with it removed (so a 10% credit is not read as a condition)."""
    action = template.get("action")
    q = next((x for x in template.get("questions", []) if x.get("name") == "action_value"), None)
    if action in ("SURCHARGE_PCT", "CREDIT_PCT"):
        m = re.search(r"(surcharge|credit|discount|load(?:ing)?|debit)\s+(?:of\s+|by\s+)?(\d+(?:\.\d+)?)\s*(%|percent)", text, re.I) or \
            re.search(r"(\d+(?:\.\d+)?)\s*(%|percent)\s+(surcharge|credit|discount|load|debit)", text, re.I)
        if m:
            val = m[2] if m[1][0].isalpha() else m[1]
            return val, text[:m.start()] + " " + text[m.end():]
        return None, text
    if action == "ATTACH_FORM":
        m = re.search(r"attach(?:\s+the)?(?:\s+form)?\s+(.+?)(?:\s+(?:when|if|for|on|to)\s+|$)", text, re.I)
        if m:
            return m[1].strip(" .,"), text[:m.start()] + " " + text[m.end():]
        return None, text
    if q and q.get("choices"):
        best = None
        for c in q["choices"]:
            for probe in {c.lower(), {"Chief Risk Officer": "cro"}.get(c, c).lower()}:
                m = re.search(r"(?<![a-z])" + re.escape(probe) + r"(?![a-z])", text.lower())
                if m and (best is None or len(probe) > len(best[1])):
                    best = (c, probe, m)
        if best:
            m = best[2]
            return best[0], text[:m.start()] + " " + text[m.end():]
        return (q["choices"][0] if action in ("ROUTE", "APPROVE_BY", "ALERT", "REFER") else None), text
    return None, text


def parse(text: str, catalog, templates: list[dict], role: str | None = None) -> dict:
    """Plain English -> draft: template, conditions, scope, action value, name, notes."""
    code = choose_template(text, templates, role)
    t = next(x for x in templates if x["code"] == code)
    action_value, rest = _action_value(text, t)
    scope = parse_scope(text, catalog)
    mentions = find_mentions(rest, catalog)
    conds, notes, seen = [], [], set()
    for i, m in enumerate(mentions):
        nxt = mentions[i + 1]["start"] if i + 1 < len(mentions) else len(rest)
        prev = mentions[i - 1]["end"] if i else 0
        c = _condition(m["element"], rest[m["end"]:nxt], rest[prev:m["start"]], catalog, m["phrase"])
        if c and c[0] not in seen:
            conds.append(c)
            seen.add(c[0])
        elif not c:
            notes.append(f"I saw '{m['phrase']}' ({catalog.name(m['element'])}) but no value for it.")
    joins = [rest[max(mentions[i - 1]["end"], mentions[i]["start"] - 16):mentions[i]["start"]] for i in range(1, len(mentions))]
    logic = "ANY" if len(conds) > 1 and any(re.search(r"\bor\s+(?:[a-z-]+\s+){0,2}$", j) for j in joins) else "ALL"
    if not conds:
        notes.append("I could not find a condition. Add one below: pick the data element, the comparison and the value.")
    return {"template": code, "conditions": conds, "logic": logic, "scope": scope, "action_value": action_value,
            "message": None, "name": draft_name(t, conds, scope, catalog), "notes": notes, "source": "SI² parser", "text": text}


def draft_name(template: dict, conds: list, scope: dict, catalog) -> str:
    what = " and ".join(describe_condition(c, catalog.names()) for c in conds[:2]) if conds else template["name"]
    where = ", ".join(scope.get("STATE", [])[:3])
    name = f"{what}" + (f" ({where})" if where else "")
    return name[:1].upper() + name[1:200]


def with_claude(text: str, catalog, templates: list[dict], role: str | None, ask) -> dict | None:
    """Ask Claude for the draft; keep it only if every element, operator and pick-list code is real."""
    used = sorted({c[0] for t in templates for c in []} | set(ALIASES.values()))
    elements = "\n".join(f"{c}: {catalog.name(c)}" + (f" [codes: {', '.join(o for o, _ in catalog.element_options(c)[:25])}]" if catalog.element_options(c) else "")
                         for c in sorted(set(used) | set(catalog.elements)) if c in catalog.elements)
    tlist = "\n".join(f"{t['code']} ({t['role']}): {t['sentence']}" for t in templates)
    prompt = (f"A {role or 'business user'} at a P&C insurer wants this rule:\n\"{text}\"\n\nTemplates:\n{tlist}\n\nCanonical data elements:\n{elements}\n\n"
              "Return only JSON: {\"template\": code, \"conditions\": [[element, operator, value1, value2 or null]], \"logic\": \"ALL\"|\"ANY\", "
              "\"scope\": {\"COMPANY\": [], \"LOB\": [], \"PRODUCT\": [], \"STATE\": []}, \"action_value\": text or null, \"name\": short name}. "
              "Operators: = <> > >= < <= IN NOT IN BETWEEN IS NULL IS NOT NULL LIKE. Use pick-list codes, comma-separated for IN. "
              "Ratios are decimals (70% = 0.70). Lines: HO PA UMB BP CP GL CA WC CYB. Put states in scope, not in conditions.")
    try:
        raw = ask(prompt)
        data = json.loads(re.search(r"\{.*\}", raw, re.S)[0])
    except Exception:  # noqa: BLE001 - any failure falls back to the parser
        return None
    if data.get("template") not in {t["code"] for t in templates}:
        return None
    conds = []
    for c in data.get("conditions", []):
        c = list(c) + [None] * (4 - len(c))
        el, op = str(c[0]).upper(), str(c[1]).upper()
        if el not in catalog.elements or op not in {"=", "<>", ">", ">=", "<", "<=", "IN", "NOT IN", "BETWEEN", "IS NULL", "IS NOT NULL", "LIKE", "NOT LIKE"}:
            return None
        opts = {o for o, _ in catalog.element_options(el)}
        if opts and c[2] is not None and op in ("=", "<>", "IN", "NOT IN"):
            if any(v.strip() not in opts for v in str(c[2]).split(",")):
                return None
        conds.append((el, op, None if c[2] is None else str(c[2]), None if c[3] is None else str(c[3])))
    scope = {k.upper(): [str(v).upper() for v in vs] for k, vs in (data.get("scope") or {}).items() if vs}
    t = next(x for x in templates if x["code"] == data["template"])
    return {"template": data["template"], "conditions": conds, "logic": "ANY" if data.get("logic") == "ANY" else "ALL", "scope": scope,
            "action_value": data.get("action_value"), "message": None, "name": data.get("name") or draft_name(t, conds, scope, catalog),
            "notes": [], "source": "Claude (checked against the canonical model)", "text": text}


def related(rule: Rule, rules: list[Rule]) -> list[dict]:
    """Existing rules this one overlaps: same action on the same elements where both apply."""
    out = []
    els = {c[0] for c in rule.conditions}
    for r in rules:
        if r.status != "ACTIVE" or r.code == rule.code or not els & {c[0] for c in r.conditions} or r.action != rule.action:
            continue
        broader = all(not r.scope.get(d) or not rule.scope.get(d) or set(rule.scope[d]) <= set(r.scope[d]) for d in r.scope)
        overlap = all(not r.scope.get(d) or not rule.scope.get(d) or set(r.scope[d]) & set(rule.scope[d]) for d in set(r.scope) | set(rule.scope))
        if overlap and _rung(rule) and _rung(r) and _rung(r)[0] == _rung(rule)[0] and \
                (_rung(r)[1] != _rung(rule)[1] or (r.action_value or "") != (rule.action_value or "")):
            out.append({"rule": r, "kind": "ladder"})        # another level of the same approval ladder, never a replacement
        elif broader and rule.specificity() > r.specificity():
            out.append({"rule": r, "kind": "replaces here" if r.override_key else "also applies"})
        elif overlap:
            out.append({"rule": r, "kind": "overlaps"})
    return out


def _rung(rule: Rule):
    """(element, threshold) when the rule is one level of an approval ladder: approval above an amount."""
    if rule.action != "APPROVE_BY" or len(rule.conditions) != 1 or rule.conditions[0][1] not in (">", ">="):
        return None
    try:
        return rule.conditions[0][0], float(rule.conditions[0][2])
    except (TypeError, ValueError):
        return None


def ladder(rule: Rule, rules: list[Rule]) -> list[tuple]:
    """Every level of the approval ladder this rule belongs to, lowest first: [(threshold, approver, code, is_new)]."""
    me = _rung(rule)
    if not me:
        return []
    steps = [(me[1], rule.action_value, rule.code, True)]
    steps += [(_rung(x["rule"])[1], x["rule"].action_value, x["rule"].code, False) for x in related(rule, rules) if x["kind"] == "ladder"]
    return sorted(steps, key=lambda s: s[0]) if len(steps) > 1 else []
