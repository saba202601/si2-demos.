"""SI² claim coverage check: the forms attached to the policy decide what is covered, and the policy decides the limits.

1. Read the forms.  Every policy form has sections: what is covered (insuring agreement, perils insured against),
   what is not covered and the exclusions, limits, deductibles, conditions. `read_form` splits any form text (a PDF
   the company already has, or the synthetic SI² forms below) into those sections and finds the causes of loss each
   section talks about.
2. Read the claim.  `causes_in` finds the causes of loss in the loss description and notes ("storm surge",
   "sewer backed up", "dry rot") with the canonical CAUSE_OF_LOSS codes; negations ("no flooding") are ignored.
3. Decide.  For each cause and the coverage the claim is under, the base form decides (open perils or named perils,
   exclusions) and endorsements change it (an exclusion added, coverage given back with a sublimit).
   Result: COVERED, NOT COVERED or REVIEW, with the form, the section and the sentence as evidence.
4. Check the money.  The limit and deductible recorded on the claim are compared with the policy; payments with the
   limit, the deductible and the adjuster's authority.
5. Alert.  Coverage questions go to the claims adjuster. Anything that looks like the claim was changed in the
   insured's favour (limit, deductible, coverage, cause) goes to the underwriter with a copy to the claims manager,
   so no adjuster can quietly change a claim. SI² never denies a claim: people decide.

All forms, policies and claims here are synthetic. The form wording is SI²'s own, written in the style of a standard
policy; it is not any bureau's or company's form.
"""
from __future__ import annotations

import datetime as dt
import random
import re
from dataclasses import dataclass, field

# ------------------------------------------------------------------------------------------ causes of loss
NEW_CAUSES = [  # canonical CAUSE_OF_LOSS codes this module adds (the others are already in the master)
    ("FLOOD", "Flood / surface water / storm surge"), ("EARTHMV", "Earth movement / earthquake"), ("SINKHOLE", "Sinkhole collapse"),
    ("MOLD", "Mold / fungi / rot"), ("WEAR", "Wear and tear / deterioration"), ("SEWER", "Water backup through sewer or drain"),
    ("FREEZE", "Freezing"), ("COLLAPSE", "Collapse"), ("SMOKE", "Smoke"), ("EXPLOS", "Explosion"), ("NEGLECT", "Neglect"),
    ("INTENT", "Intentional loss"), ("POWER", "Power failure off premises"), ("VERMIN", "Insects / rodents / vermin"),
    ("ICESNOW", "Weight of ice, snow or sleet"), ("FALLOBJ", "Falling objects"), ("RACING", "Racing / speed contest"),
    ("RIDESHARE", "Used for hire / ride-sharing"), ("ANIMAL", "Contact with an animal"), ("GLASS", "Glass breakage"),
]

CAUSE_WORDS = {
    "FLOOD": ["flood", "flooding", "flooded", "storm surge", "surge", "rising water", "surface water", "tidal water", "high water",
              "overflow of the river", "river overflowed", "creek overflowed", "water came in under the door", "water came under the door",
              "water came in from outside", "standing water in the yard", "waves", "mudflow", "inundation"],
    "EARTHMV": ["earthquake", "earth movement", "landslide", "mudslide", "tremor", "ground shifted", "earth sinking", "foundation shifted"],
    "SINKHOLE": ["sinkhole", "sink hole", "ground collapsed under", "cavity under the foundation"],
    "MOLD": ["mold", "mould", "fungus", "fungi", "mildew", "wet rot", "dry rot", "rot"],
    "WEAR": ["wear and tear", "worn out", "deterioration", "deteriorated", "old age", "rust", "corrosion", "settling", "cracking over time",
             "gradual leak", "leaking for months", "long-term leak", "slow leak", "seepage", "marring", "latent defect"],
    "SEWER": ["backs up through sewers", "back up through sewers", "backing up through sewers", "backs up through sewers or drains",
              "water backing up", "sewer or drain backup", "overflows from a sump pump", "overflow from a sump pump", "sewers or drains", "sump pump", "sewer", "sewer backup", "sewer backed up", "backed up sewer", "drain backed up", "drain backup", "sump pump failed", "sump pump overflow",
              "sump overflow", "toilet backed up", "backup through the drain", "septic backed up"],
    "FREEZE": ["freezing", "frozen pipe", "frozen pipes", "pipe froze", "pipes froze", "pipes burst in the cold", "ice in the pipes"],
    "COLLAPSE": ["collapse", "collapsed", "caved in", "roof caved"],
    "SMOKE": ["smoke damage", "smoke", "soot"],
    "EXPLOS": ["explosion", "exploded", "blast"],
    "NEGLECT": ["neglect", "neglected", "failed to protect the property", "left the window open for weeks", "did not repair"],
    "INTENT": ["intentional", "on purpose", "deliberately", "set the fire himself", "set the fire herself", "staged"],
    "POWER": ["power outage", "power failure", "blackout", "utility outage", "power went out"],
    "VERMIN": ["termites", "termite", "rodents", "rats", "mice", "squirrels", "insects", "vermin", "raccoons", "bats"],
    "ICESNOW": ["weight of snow", "weight of ice", "snow load", "heavy snow on the roof", "ice dam", "sleet"],
    "FALLOBJ": ["falling object", "fell on", "tree fell", "fallen tree", "branch fell", "limb fell"],
    "RACING": ["racing", "drag race", "speed contest", "street race", "track day"],
    "RIDESHARE": ["uber", "lyft", "rideshare", "ride-share", "ride sharing", "ride-sharing", "for a fee", "carry persons or property for a fee", "driving for doordash", "delivering food", "delivery driver",
                  "carrying passengers for a fee", "for hire"],
    "ANIMAL": ["hit a deer", "struck a deer", "deer", "animal", "hit a cow", "hit an elk", "moose"],
    "GLASS": ["windshield", "glass breakage", "broken glass", "cracked windshield", "window shattered"],
    "FIRE": ["fire", "burned", "burnt", "flames", "kitchen fire", "grease fire", "wildfire", "caught fire"],
    "LTNG": ["lightning", "lightning strike", "struck by lightning"],
    "WIND": ["wind", "windstorm", "hurricane", "tropical storm", "tornado", "high winds", "blew off", "shingles blown", "wind-driven"],
    "HAIL": ["hail", "hailstorm", "hail stones"],
    "VMM": ["vandalism", "vandalized", "graffiti", "malicious mischief", "keyed the car", "smashed"],
    "WATER": ["burst pipe", "pipe burst", "water heater burst", "water heater leaked", "washing machine hose", "supply line", "dishwasher leaked",
              "accidental discharge", "sudden leak", "plumbing leak", "ac line leaked", "overflowed tub"],
    "SPRK": ["sprinkler leakage", "sprinkler head", "fire sprinkler discharged"],
    "THEFT": ["theft", "stolen", "stole", "burglary", "break-in", "broke in", "missing jewelry", "robbed", "taken from"],
    "COLL": ["collision", "rear-ended", "rear ended", "hit another car", "hit a pole", "ran into", "crashed", "accident with", "t-boned",
             "sideswiped", "rolled over", "single car accident"],
    "BRKDN": ["mechanical breakdown", "engine failure", "transmission failed", "electrical breakdown", "boiler broke down", "compressor failed"],
    "EMPDIS": ["employee theft", "employee stole", "embezzlement", "embezzled", "cashier took money"],
    "SLIP": ["slipped", "slip and fall", "tripped", "fell on the floor", "fell on the stairs"],
}
NEGATION = re.compile(r"\b(no|not|without|never|nor|denies|denied|ruled out|wasn't|was not|isn't|no sign of|no evidence of)\b[\w\s,'-]{0,25}$", re.I)
_ORDERED = sorted(((w, c) for c, ws in CAUSE_WORDS.items() for w in ws), key=lambda x: -len(x[0]))


def causes_in(text: str, negations: bool = True) -> list[tuple[str, str]]:
    """[(cause code, phrase)] found in the text, longest phrases first, each place counted once; 'no flooding' is ignored."""
    low = (text or "").lower()
    taken = [False] * len(low)
    hits = []
    for phrase, code in _ORDERED:
        for m in re.finditer(r"(?<![a-z])" + re.escape(phrase) + r"(?![a-z])", low):
            if any(taken[m.start():m.end()]):
                continue
            for i in range(m.start(), m.end()):
                taken[i] = True
            sentence_start = max(low.rfind(".", 0, m.start()), low.rfind(";", 0, m.start())) + 1
            if negations and NEGATION.search(low[sentence_start:m.start()]):
                continue
            hits.append((m.start(), code, phrase))
    out, seen = [], set()
    for _, code, phrase in sorted(hits):
        if code not in seen:
            out.append((code, phrase))
            seen.add(code)
    return out


# ------------------------------------------------------------------------------------------ forms
COVERAGE_WORDS = [  # (regex, canonical COVERAGE code)
    (r"coverage a\b|dwelling", "DWELL"), (r"coverage b\b|other structures", "OTHSTR"), (r"coverage c\b|personal property", "PERSPROP"),
    (r"coverage d\b|loss of use", "LOU"), (r"coverage e\b|personal liability", "PERSLIAB"), (r"coverage f\b|medical payments to others", "MEDPAY"),
    (r"other than collision|comprehensive", "COMP"), (r"(?<!other than )collision", "COLL"), (r"business personal property", "BPP"),
    (r"\bbuilding\b", "BLDG"), (r"business income", "TE"),
]
SECTION_TYPES = [  # checked in order on the heading
    ("EXCLUSION", r"exclusion|we do not (insure|cover)|not covered|is excluded|does not apply"),
    ("ADDS", r"additional coverage|coverage (is )?added|the following (coverage )?is added|we will (also )?pay|coverage given back|exception"),
    ("DEDUCTIBLE", r"deductible"),
    ("LIMIT", r"limit"),
    ("CONDITION", r"condition|duties|what you must do"),
    ("DEFINITION", r"definition"),
    ("COVERED", r"peril|insuring agreement|coverage|we cover|we insure|property covered|what is covered|covered causes?|causes of loss"),
]
QUALIFIER = re.compile(r"\b(unless|except|whether or not|regardless of|resulting from|that results from|caused by a covered|if the|other than)\b", re.I)
EXCEPTION = re.compile(r"\b(unless|except|however we (do )?(cover|pay|insure)|but we (do )?(cover|pay|insure)|this exclusion does not apply)\b", re.I)
OPEN_PERILS = re.compile(r"risks? of direct physical loss|direct physical loss .{0,60}unless .{0,40}excluded|all risks?", re.I)


def _is_heading(line: str) -> bool:
    s = line.strip()
    letters = re.sub(r"[^A-Za-z]", "", s)
    return 3 <= len(s) <= 90 and len(letters) >= 3 and s.upper() == s and not s.endswith(",")


def coverages_named(text: str) -> list[str]:
    low = text.lower()
    out = []
    for rx, code in COVERAGE_WORDS:
        if re.search(rx, low) and code not in out:
            out.append(code)
    return out


def read_form(number: str, text: str) -> list[dict]:
    """Split a form into sections: {seq, heading, type, coverages, open_perils, clauses: [{text, causes, exception, amount}]}."""
    sections, cur = [], None
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        if _is_heading(line):
            cur = {"seq": len(sections) + 1, "heading": line, "lines": []}
            sections.append(cur)
        else:
            if cur is None:
                cur = {"seq": 1, "heading": "GENERAL", "lines": []}
                sections.append(cur)
            cur["lines"].append(line)
    out = []
    parent_cov: list = []
    for s in sections:
        h = s["heading"].lower()
        kind = next((k for k, rx in SECTION_TYPES if re.search(rx, h)), "OTHER")
        body = " ".join(s["lines"])
        covs = coverages_named(s["heading"]) or (coverages_named(body) if kind in ("COVERED", "LIMIT") else [])
        if kind == "COVERED" and covs:
            parent_cov = covs
        elif kind in ("EXCLUSION", "ADDS") and not covs:
            covs = []                                   # applies to every coverage the form gives
        clauses = []
        for ln in s["lines"]:
            for part in re.split(r"(?<=[.])\s+(?=[A-Z(0-9])|;\s+", ln):
                part = part.strip()
                if not part:
                    continue
                amt = re.search(r"\$\s?([\d,]{3,})", part)
                pct = re.search(r"(\d+(?:\.\d+)?)\s?% of (?:the )?coverage a", part, re.I)
                subject = part
                if kind == "EXCLUSION":                     # an exclusion excludes its subject, not what its exceptions mention
                    q = QUALIFIER.search(part)
                    subject = part[:q.start()] if q else part
                exc = EXCEPTION.search(part)
                clauses.append({"text": part, "causes": [c for c, _ in causes_in(subject, negations=False)],
                                "exception": bool(exc) and not re.search(r"endorsement", part[exc.start():], re.I),
                                "amount": float(amt[1].replace(",", "")) if amt else None, "pct_cov_a": float(pct[1]) if pct else None})
        out.append({"form": number, "seq": s["seq"], "heading": s["heading"], "type": kind, "coverages": covs,
                    "open_perils": bool(kind == "COVERED" and OPEN_PERILS.search(body)), "clauses": clauses, "parent": parent_cov})
    return out


# The synthetic SI² forms: SI²'s own wording, laid out like a policy (headings in capitals, one clause per line).
FORMS = [
    {"number": "SIM HO 3", "edition": "01 26", "title": "Homeowners Special Form (synthetic)", "lob": "HO", "products": ["HO3", "HO5"], "kind": "BASE", "text": """
SECTION I - PROPERTY COVERAGES
Coverage A - Dwelling: the dwelling on the residence premises, including attached structures.
Coverage B - Other Structures: structures set apart from the dwelling by clear space.
Coverage C - Personal Property: property owned or used by an insured anywhere in the world.
Coverage D - Loss Of Use: additional living expense while the residence premises is not fit to live in.
PERILS INSURED AGAINST - COVERAGE A AND COVERAGE B
We insure against risk of direct physical loss to property described in Coverages A and B unless the loss is excluded in this policy.
PERILS INSURED AGAINST - COVERAGE C
We insure for direct physical loss to property described in Coverage C caused by the following perils only, unless the loss is excluded.
Fire or lightning.
Windstorm or hail; interior damage only if the wind or hail first makes an opening in the roof or a wall.
Explosion. Smoke, meaning sudden and accidental damage from smoke.
Vandalism or malicious mischief. Theft, including attempted theft.
Falling objects. Weight of ice, snow or sleet.
Accidental discharge or overflow of water from a plumbing, heating or air conditioning system or household appliance, such as a burst pipe or a washing machine hose.
Freezing of a plumbing system, if you maintained heat in the building.
SECTION I - EXCLUSIONS
We do not insure for loss caused directly or indirectly by any of the following, regardless of any other cause contributing to the loss.
Flood, surface water, waves, tidal water, storm surge, overflow of a body of water, or spray from any of these, whether or not driven by wind.
Water which backs up through sewers or drains or overflows from a sump pump.
Earth movement, including earthquake, landslide, mudflow, earth sinking, rising or shifting, and sinkhole.
Wear and tear, marring, deterioration, mechanical breakdown, latent defect, rust, corrosion, settling, cracking or seepage of water over a period of weeks or months.
Mold, fungus or wet or dry rot, unless hidden within the walls or ceilings and resulting from an accidental discharge of water covered by this policy.
Birds, rodents, insects, termites or other vermin.
Neglect, meaning failure to use all reasonable means to protect covered property at and after the time of loss.
Intentional loss, meaning any loss arising out of an act committed by or at the direction of an insured with the intent to cause a loss.
Power failure, meaning the failure of power or other utility service if the failure takes place off the residence premises.
War, nuclear hazard, and ordinance or law.
SECTION I - DEDUCTIBLE
Unless otherwise noted in this policy, we pay only the part of the loss over the deductible stated in the Declarations.
SECTION I - LIMITS OF LIABILITY
We will not pay more than the limit of liability shown in the Declarations for each coverage.
SECTION I - CONDITIONS
Duties after loss: give prompt notice to us, protect the property from further damage, and show the damaged property.
"""},
    {"number": "SIM HO 4", "edition": "01 26", "title": "Renters Broad Form (synthetic)", "lob": "HO", "products": ["HO4"], "kind": "BASE", "text": """
SECTION I - PROPERTY COVERAGES
Coverage C - Personal Property: property owned or used by an insured anywhere in the world.
Coverage D - Loss Of Use: additional living expense while the rented premises is not fit to live in.
PERILS INSURED AGAINST - COVERAGE C
We insure for direct physical loss to property described in Coverage C caused by the following perils only.
Fire or lightning. Windstorm or hail. Explosion. Smoke. Vandalism or malicious mischief. Theft. Falling objects.
Weight of ice, snow or sleet. Accidental discharge or overflow of water from a plumbing system or household appliance, such as a burst pipe.
SECTION I - EXCLUSIONS
We do not insure for loss caused by flood, surface water, storm surge or waves; water backing up through sewers or drains; earth movement including earthquake and sinkhole; wear and tear or deterioration; mold, fungus or rot; vermin; neglect; intentional loss; or power failure off the premises.
SECTION I - DEDUCTIBLE
We pay only the part of the loss over the deductible stated in the Declarations.
"""},
    {"number": "SIM HO 6", "edition": "01 26", "title": "Unit-Owners Form (synthetic)", "lob": "HO", "products": ["HO6"], "kind": "BASE", "text": """
SECTION I - PROPERTY COVERAGES
Coverage A - Dwelling: the alterations, fixtures and improvements that are part of the unit.
Coverage C - Personal Property: property owned or used by an insured.
PERILS INSURED AGAINST - COVERAGE A
We insure against risk of direct physical loss to property described in Coverage A unless the loss is excluded.
PERILS INSURED AGAINST - COVERAGE C
We insure for direct physical loss to Coverage C property caused by fire or lightning, windstorm or hail, explosion, smoke, vandalism, theft, falling objects, weight of ice or snow, and accidental discharge of water such as a burst pipe or appliance leak.
SECTION I - EXCLUSIONS
We do not insure for loss caused by flood, storm surge or surface water; sewer or drain backup; earthquake or other earth movement; sinkhole; wear and tear, deterioration or seepage over weeks or months; mold or rot; vermin; neglect; intentional loss; or power failure.
SECTION I - DEDUCTIBLE
We pay only the part of the loss over the deductible stated in the Declarations.
"""},
    {"number": "SIM DP 3", "edition": "01 26", "title": "Dwelling Property Special Form (synthetic)", "lob": "HO", "products": ["DP3"], "kind": "BASE", "text": """
COVERAGES
Coverage A - Dwelling: the dwelling at the described location, rented to others.
Coverage C - Personal Property: landlord's household property at the dwelling.
PERILS INSURED AGAINST - COVERAGE A
We insure against risk of direct physical loss to Coverage A property unless the loss is excluded.
PERILS INSURED AGAINST - COVERAGE C
We insure Coverage C property for fire or lightning, windstorm or hail, explosion, smoke, vandalism, theft and burst pipe or accidental discharge of water.
GENERAL EXCLUSIONS
We do not insure for loss caused by flood or storm surge; sewer backup; earth movement or earthquake; sinkhole; wear and tear, deterioration or settling; mold or rot; vermin; neglect; intentional loss; or vandalism and theft if the dwelling was vacant for more than 60 days.
DEDUCTIBLE
We pay only the part of the loss over the deductible stated in the Declarations.
"""},
    {"number": "SIM HO 04 95", "edition": "01 26", "title": "Water Back-Up and Sump Discharge (synthetic)", "lob": "HO", "products": ["HO3", "HO5", "HO6", "HO4"], "kind": "ENDORSEMENT", "text": """
ADDITIONAL COVERAGE - WATER BACK-UP
We will pay for direct physical loss caused by water which backs up through sewers or drains or overflows from a sump pump, up to $10,000 per loss.
The Water Back-Up exclusion in Section I Exclusions does not apply to the coverage given by this endorsement.
"""},
    {"number": "SIM HO 23 FL", "edition": "01 26", "title": "Sinkhole Loss Coverage - Florida (synthetic)", "lob": "HO", "products": ["HO3", "HO5", "DP3"], "states": ["FL"], "kind": "ENDORSEMENT", "text": """
ADDITIONAL COVERAGE - SINKHOLE LOSS
We will pay for direct physical loss to Coverage A property caused by sinkhole activity, when a sinkhole is verified by a professional engineer.
"""},
    {"number": "SIM HO 32 FL", "edition": "01 26", "title": "Hurricane Percentage Deductible (synthetic)", "lob": "HO", "products": ["HO3", "HO5", "HO6", "DP3"], "kind": "ENDORSEMENT", "text": """
HURRICANE DEDUCTIBLE
For loss caused by windstorm during a hurricane, the deductible is 2% of the Coverage A limit shown in the Declarations.
"""},
    {"number": "SIM HO 04 26", "edition": "01 26", "title": "Limited Fungi, Wet or Dry Rot Coverage (synthetic)", "lob": "HO", "products": ["HO3", "HO5", "HO6"], "kind": "ENDORSEMENT", "text": """
ADDITIONAL COVERAGE - FUNGI, WET OR DRY ROT
We will pay for loss caused by mold, fungi, wet rot or dry rot that results from a covered peril, up to $10,000 per policy term.
"""},
    {"number": "SIM HO 04 54", "edition": "01 26", "title": "Earthquake (synthetic)", "lob": "HO", "products": ["HO3", "HO5", "HO6"], "kind": "ENDORSEMENT", "text": """
ADDITIONAL COVERAGE - EARTHQUAKE
We will pay for direct physical loss caused by earthquake, including land shock waves or tremors.
"""},
    {"number": "SIM HO 04 94", "edition": "01 26", "title": "Windstorm or Hail Exclusion (synthetic)", "lob": "HO", "products": ["HO3", "HO5", "HO6", "DP3"], "kind": "ENDORSEMENT", "text": """
WINDSTORM OR HAIL EXCLUSION
We do not insure for loss caused by windstorm or hail, including hurricane and tornado; this risk is insured by the state wind pool.
"""},
    {"number": "SIM PP 00 01", "edition": "01 26", "title": "Personal Auto Policy (synthetic)", "lob": "PA", "products": ["PA_STD"], "kind": "BASE", "text": """
PART D - COVERAGE FOR DAMAGE TO YOUR AUTO
INSURING AGREEMENT - COLLISION COVERAGE
We will pay for direct and accidental loss to your covered auto caused by collision with another object or by overturn, if Collision Coverage is shown in the Declarations.
INSURING AGREEMENT - OTHER THAN COLLISION COVERAGE
We will pay for direct and accidental loss to your covered auto not caused by collision, if Other Than Collision Coverage is shown in the Declarations.
Loss caused by the following is Other Than Collision: missiles or falling objects; fire; theft; explosion or earthquake; windstorm; hail, water or flood; malicious mischief or vandalism; riot; contact with a bird or animal; glass breakage.
PART D - EXCLUSIONS
We will not pay for loss to your covered auto while it is being used to carry persons or property for a fee, including ride-sharing and delivery, unless the ride-share endorsement is attached.
We will not pay for loss due to and confined to wear and tear, freezing, mechanical or electrical breakdown or failure, or road damage to tires.
We will not pay for loss to your covered auto while it is used in any race or speed contest.
We will not pay for loss caused intentionally by or at the direction of an insured.
PART D - LIMIT OF LIABILITY
Our limit is the lesser of the actual cash value of the stolen or damaged property or the amount necessary to repair or replace it, minus the deductible shown in the Declarations.
PART E - DUTIES AFTER AN ACCIDENT OR LOSS
We must be notified promptly of how, when and where the accident or loss happened.
"""},
    {"number": "SIM PP 03 RS", "edition": "01 26", "title": "Ride-Share Coverage (synthetic)", "lob": "PA", "products": ["PA_STD"], "kind": "ENDORSEMENT", "text": """
ADDITIONAL COVERAGE - RIDE-SHARE
The exclusion for carrying persons for a fee does not apply while you are logged in to a ride-sharing or delivery platform and waiting for or carrying a passenger or delivery.
"""},
    {"number": "SIM BP 00 03", "edition": "01 26", "title": "Businessowners Coverage Form (synthetic)", "lob": "BP", "products": ["BOP"], "kind": "BASE", "text": """
SECTION I - PROPERTY - COVERAGE
We will pay for direct physical loss of or damage to Building and Business Personal Property at the premises caused by or resulting from any Covered Cause of Loss.
COVERED CAUSES OF LOSS
Risks of direct physical loss unless the loss is excluded or limited in this policy.
SECTION I - EXCLUSIONS
We will not pay for loss caused by flood, surface water, storm surge or waves; earth movement or earthquake; sinkhole; wear and tear, rust, corrosion or deterioration; mold or fungi; insects, rodents or vermin; power failure off the premises; mechanical breakdown; dishonest acts by you or your employees, including employee theft and embezzlement; or neglect.
SECTION I - LIMITS OF INSURANCE
The most we will pay for loss in any one occurrence is the applicable Limit of Insurance shown in the Declarations.
SECTION I - DEDUCTIBLES
We will not pay for loss in any one occurrence until the amount of loss exceeds the Deductible shown in the Declarations.
"""},
    {"number": "SIM BP 04 ED", "edition": "01 26", "title": "Employee Dishonesty (synthetic)", "lob": "BP", "products": ["BOP"], "kind": "ENDORSEMENT", "text": """
ADDITIONAL COVERAGE - EMPLOYEE DISHONESTY
We will pay for loss of Business Personal Property and money resulting from employee theft or embezzlement by an employee, up to $25,000 per occurrence.
"""},
    {"number": "SIS CP 10 30", "edition": "01 26", "title": "Commercial Property Special Causes of Loss (synthetic)", "lob": "CP", "products": ["CP"], "kind": "BASE", "text": """
COVERED CAUSES OF LOSS - BUILDING AND BUSINESS PERSONAL PROPERTY
Covered Causes of Loss means risks of direct physical loss unless the loss is excluded or limited in this form.
EXCLUSIONS
We will not pay for loss caused by flood, surface water, storm surge or waves; earth movement or earthquake; water that backs up through sewers or drains; wear and tear, rust, corrosion, deterioration or settling; mold or fungi; vermin; mechanical breakdown; power failure off the premises; neglect; intentional loss; or collapse, except as provided in the Additional Coverage for Collapse.
ADDITIONAL COVERAGE - COLLAPSE
We will pay for direct physical loss caused by abrupt collapse of a building caused by decay hidden from view or the weight of ice, snow or rain.
DEDUCTIBLE
We will not pay for loss in any one occurrence until the amount of loss exceeds the Deductible shown in the Declarations.
"""},
    {"number": "SIS CP 10 65", "edition": "01 26", "title": "Flood Coverage Endorsement (synthetic)", "lob": "CP", "products": ["CP"], "kind": "ENDORSEMENT", "text": """
ADDITIONAL COVERAGE - FLOOD
We will pay for direct physical loss caused by flood, surface water or storm surge, up to $1,000,000 per occurrence.
"""},
]
FORM_BY_NUMBER = {f["number"]: f for f in FORMS}


@dataclass
class FormLibrary:
    forms: dict = field(default_factory=dict)        # number -> form dict
    sections: dict = field(default_factory=dict)     # number -> [sections]

    @classmethod
    def synthetic(cls) -> "FormLibrary":
        lib = cls()
        for f in FORMS:
            lib.add(f)
        return lib

    def add(self, form: dict) -> None:
        self.forms[form["number"]] = form
        self.sections[form["number"]] = read_form(form["number"], form["text"])


# ------------------------------------------------------------------------------------------ decide coverage
def _applies(section: dict, coverage: str, form_covs: list) -> bool:
    covs = section["coverages"]
    return not covs or coverage in covs


def decide(cause: str, coverage: str, form_numbers: list[str], lib: FormLibrary) -> dict:
    """COVERED / NOT COVERED / REVIEW for one cause under one coverage, from the forms attached to the policy (base first)."""
    ordered = sorted(form_numbers, key=lambda n: 0 if lib.forms.get(n, {}).get("kind") == "BASE" else 1)
    covered, excluded, exception, added, sublimit, named_only = None, None, False, None, None, False
    evidence = []
    for n in ordered:
        form = lib.forms.get(n)
        if not form:
            continue
        base = form.get("kind") == "BASE"
        for s in lib.sections.get(n, []):
            if s["type"] == "COVERED" and base and _applies(s, coverage, []):
                hit = next((c for c in s["clauses"] if cause in c["causes"]), None)
                if s["open_perils"]:
                    covered = covered or (n, s, {"text": next((c["text"] for c in s["clauses"] if OPEN_PERILS.search(c["text"])), s["clauses"][0]["text"] if s["clauses"] else "")})
                elif hit:
                    covered = (n, s, hit)
                elif s["coverages"] and coverage in s["coverages"] and any(c["causes"] for c in s["clauses"]):
                    named_only = named_only or (n, s)
            elif s["type"] == "EXCLUSION":
                hit = next((c for c in s["clauses"] if cause in c["causes"]), None)
                if hit and _applies(s, coverage, []):
                    excluded, exception = (n, s, hit), hit["exception"]
                    added = None if not base else added
            elif s["type"] == "ADDS":
                hit = next((c for c in s["clauses"] if cause in c["causes"]), None)
                if hit and (not s["coverages"] or coverage in s["coverages"] or coverage in ("DWELL", "PERSPROP", "OTHSTR", "BLDG", "BPP", "COMP")):
                    added, sublimit = (n, s, hit), next((c["amount"] for c in s["clauses"] if c["amount"]), None)
    if covered and not excluded and named_only and covered[1].get("open_perils") is False:
        named_only = False
    if added and (excluded or not covered):
        status, why = "COVERED", added
        note = f"Given back by {added[0]}" + (f", up to ${sublimit:,.0f}" if sublimit else "")
    elif excluded and exception:
        status, why, note = "REVIEW", excluded, "Excluded, but the exclusion has an exception: check the facts"
    elif excluded:
        status, why, note = "NOT COVERED", excluded, f"Excluded by {excluded[0]}"
    elif covered:
        status, why, note = "COVERED", covered, f"Covered by {covered[0]}"
    elif named_only:
        status, why, note = "NOT COVERED", (named_only[0], named_only[1], {"text": "Not one of the named perils for this coverage."}), \
            f"Not a named peril for this coverage in {named_only[0]}"
    else:
        status, why, note = "REVIEW", None, "The attached forms do not mention this cause: an adjuster must decide"
    if why:
        evidence.append({"form": why[0], "section": why[1]["heading"], "text": why[2]["text"]})
    return {"cause": cause, "coverage": coverage, "status": status, "note": note, "evidence": evidence, "sublimit": sublimit}


# ------------------------------------------------------------------------------------------ claim checks
USE_EXCLUSIONS = {"RIDESHARE", "RACING", "INTENT", "NEGLECT"}
AUTHORITY = {"CLAIMS_ADJUSTER": 25_000, "CLAIMS_MANAGER": 250_000}
PA_COVERAGE_OF = {"COLL": "COLL"}       # every other auto cause is Other Than Collision
CAUSE_NAMES = dict(NEW_CAUSES) | {"FIRE": "Fire", "LTNG": "Lightning", "WIND": "Windstorm", "HAIL": "Hail", "VMM": "Vandalism", "WATER": "Water damage (accidental discharge)",
                                  "SPRK": "Sprinkler leakage", "THEFT": "Theft", "COLL": "Collision", "BRKDN": "Mechanical breakdown",
                                  "EMPDIS": "Employee dishonesty", "SLIP": "Slip / fall", "COMP": "Comprehensive"}
ROUTE = {  # alert type -> (to, copy, severity)
    "NOT_COVERED": ("CLAIMS_ADJUSTER", "CLAIMS_MANAGER", "HIGH"), "COVERAGE_REVIEW": ("CLAIMS_ADJUSTER", None, "MEDIUM"),
    "PAID_NOT_COVERED": ("CLAIMS_MANAGER", "SIU", "HIGH"), "OUTSIDE_POLICY_PERIOD": ("CLAIMS_ADJUSTER", "CLAIMS_MANAGER", "HIGH"),
    "LIMIT_MISMATCH": ("UNDERWRITER", "CLAIMS_MANAGER", "HIGH"), "DEDUCTIBLE_MISMATCH": ("UNDERWRITER", "CLAIMS_MANAGER", "HIGH"),
    "COVERAGE_NOT_ON_POLICY": ("UNDERWRITER", "CLAIMS_MANAGER", "HIGH"), "OVER_LIMIT": ("UNDERWRITER", "CLAIMS_MANAGER", "HIGH"),
    "DEDUCTIBLE_NOT_APPLIED": ("UNDERWRITER", "CLAIMS_MANAGER", "HIGH"), "WRONG_COVERAGE": ("UNDERWRITER", "CLAIMS_MANAGER", "HIGH"),
    "CAUSE_MISMATCH": ("CLAIMS_MANAGER", "UNDERWRITER", "HIGH"), "SPLIT_PAYMENTS": ("CLAIMS_MANAGER", "SIU", "HIGH"),
    "SHARED_PAYEE": ("SIU", "CLAIMS_MANAGER", "HIGH"), "EARLY_LOSS": ("SIU", "CLAIMS_MANAGER", "MEDIUM"), "LATE_REPORT": ("CLAIMS_ADJUSTER", None, "MEDIUM"),
    "SUBLIMIT": ("CLAIMS_ADJUSTER", None, "MEDIUM"),
}
TITLES = {"NOT_COVERED": "Not covered under the attached forms", "COVERAGE_REVIEW": "Coverage needs review", "PAID_NOT_COVERED": "Paid on a cause the forms exclude",
          "OUTSIDE_POLICY_PERIOD": "Loss date outside the policy period", "LIMIT_MISMATCH": "Limit on the claim differs from the policy",
          "DEDUCTIBLE_MISMATCH": "Deductible on the claim lower than the policy", "COVERAGE_NOT_ON_POLICY": "Coverage not on the policy",
          "OVER_LIMIT": "Paid plus reserve above the limit", "DEDUCTIBLE_NOT_APPLIED": "Payment ignores the deductible",
          "WRONG_COVERAGE": "Collision paid under Other Than Collision", "CAUSE_MISMATCH": "Recorded cause does not match the loss description",
          "SPLIT_PAYMENTS": "Payments split just under the adjuster's authority", "SHARED_PAYEE": "Same payee on unrelated insureds' claims",
          "EARLY_LOSS": "Loss soon after the policy started", "LATE_REPORT": "Reported late", "SUBLIMIT": "A sublimit applies"}


def _alert(claim: dict, kind: str, message: str, evidence: str = "") -> dict:
    to, cc, sev = ROUTE[kind]
    return {"claim": claim["claim_number"], "policy": claim["policy_number"], "type": kind, "title": TITLES[kind], "severity": sev, "to": to, "cc": cc,
            "message": message, "evidence": evidence, "adjuster": claim.get("adjuster")}


def expected_deductible(policy: dict, coverage: str, causes: list[str], text: str, lib: FormLibrary) -> tuple[float, str]:
    row = policy["coverages"].get(coverage, {})
    ded, why = float(row.get("deductible") or 0), "policy deductible"
    if "WIND" in causes and re.search(r"hurricane|tropical storm", text or "", re.I):
        for n in policy["forms"]:
            for s in lib.sections.get(n, []):
                for c in s["clauses"]:
                    if c.get("pct_cov_a") and "WIND" in c["causes"]:
                        cov_a = float(policy["coverages"].get("DWELL", {}).get("limit") or 0)
                        if cov_a:
                            return round(cov_a * c["pct_cov_a"] / 100, 2), f"hurricane deductible {c['pct_cov_a']:g}% of Coverage A ({n})"
    return ded, why


def check_claim(claim: dict, policy: dict | None, lib: FormLibrary) -> dict:
    """Everything SI² sees on one claim: causes, coverage decisions, money checks and alerts (with who gets them)."""
    alerts, decisions = [], []
    text = " ".join(str(claim.get(k) or "") for k in ("description", "notes"))
    found = causes_in(text)
    causes = [c for c, _ in found]
    rec = claim.get("cause")
    if not policy:
        return {"causes": found, "decisions": [], "alerts": [_alert(claim, "COVERAGE_NOT_ON_POLICY", "No policy found for this claim.")], "money": {}}
    lob = policy["lob"]
    coverage = claim.get("coverage")
    # recorded cause vs the words
    if rec and causes and rec not in causes and not (lob == "PA" and rec == "COMP" and set(causes) - {"COLL"}):
        alerts.append(_alert(claim, "CAUSE_MISMATCH", f"Recorded as {CAUSE_NAMES.get(rec, rec)}, but the description says "
                             + ", ".join(f"'{p}' ({CAUSE_NAMES.get(c, c)})" for c, p in found) + ".", text[:300]))
    check_causes = causes or ([rec] if rec else [])
    if rec and rec in causes and len(causes) > 1 and lob != "PA":
        other = [(c, p) for c, p in found if c != rec and decide(c, coverage or "", policy["forms"], lib)["status"] == "NOT COVERED"]
        if other and decide(rec, coverage or "", policy["forms"], lib)["status"] == "COVERED":
            alerts.append(_alert(claim, "CAUSE_MISMATCH", f"Recorded only as {CAUSE_NAMES.get(rec, rec)} (covered), but the description also says "
                                 + ", ".join(f"'{p}' ({CAUSE_NAMES.get(c, c)}, excluded)" for c, p in other) + ".", text[:300]))
    if lob == "PA":
        want = "COLL" if "COLL" in check_causes else "COMP"
        if coverage and coverage != want and coverage in ("COLL", "COMP"):
            alerts.append(_alert(claim, "WRONG_COVERAGE" if want == "COLL" else "COVERAGE_REVIEW",
                                 f"The loss is {CAUSE_NAMES.get(want, want)} but it is recorded under {coverage}. "
                                 f"Deductibles: COLL {policy['coverages'].get('COLL', {}).get('deductible', '—')}, COMP {policy['coverages'].get('COMP', {}).get('deductible', '—')}."))
        coverage = want if coverage in (None, "COLL", "COMP") else coverage
        if want not in policy["coverages"]:
            alerts.append(_alert(claim, "NOT_COVERED", f"{'Collision' if want == 'COLL' else 'Other Than Collision'} coverage was not bought on policy "
                                 f"{policy['policy_number']} (it has {', '.join(policy['coverages'])}). Review before any payment; a denial needs the claims manager."))
            return {"causes": found, "coverage": coverage, "decisions": [{"cause": c, "coverage": want, "status": "NOT COVERED",
                                                                           "note": "Coverage not bought", "evidence": [], "sublimit": None}
                                                                          for c in check_causes], "alerts": alerts, "money": {}}
    if coverage and coverage not in policy["coverages"]:
        alerts.append(_alert(claim, "COVERAGE_NOT_ON_POLICY", f"The claim is under {coverage}, which is not on policy {policy['policy_number']} "
                             f"(policy has {', '.join(policy['coverages'])})."))
    # coverage from the forms
    sublimit = None
    for c in check_causes:
        d = decide("COLL" if (lob == "PA" and c == "COLL") else c, coverage or "", policy["forms"], lib)
        decisions.append(d)
        if d["sublimit"] and d["status"] == "COVERED":
            sublimit = min(sublimit or d["sublimit"], d["sublimit"])
    statuses = {d["status"] for d in decisions}
    use_excl = [d for d in decisions if d["cause"] in USE_EXCLUSIONS and d["status"] == "NOT COVERED"]
    if use_excl:                                          # how the property was used excludes the whole loss
        statuses = {"NOT COVERED"}
        decisions = use_excl + [dict(d, status="NOT COVERED", note=f"Excluded because of {CAUSE_NAMES.get(use_excl[0]['cause'])}")
                                for d in decisions if d not in use_excl]
    if "NOT COVERED" in statuses and "COVERED" in statuses:
        alerts.append(_alert(claim, "COVERAGE_REVIEW", "Concurrent causes: " + "; ".join(f"{CAUSE_NAMES.get(d['cause'], d['cause'])} {d['status'].lower()}"
                                                                                       for d in decisions) + ". Separate the damage by cause before paying.",
                             " | ".join(e["text"] for d in decisions for e in d["evidence"])[:400]))
    elif "NOT COVERED" in statuses:
        d = next(x for x in decisions if x["status"] == "NOT COVERED")
        alerts.append(_alert(claim, "NOT_COVERED", f"{CAUSE_NAMES.get(d['cause'], d['cause'])}: {d['note']}. Review before any payment; a denial needs the claims manager.",
                             " | ".join(f"{e['form']} · {e['section']}: {e['text']}" for e in d["evidence"])))
    elif "REVIEW" in statuses or not decisions:
        d = next((x for x in decisions if x["status"] == "REVIEW"), None)
        alerts.append(_alert(claim, "COVERAGE_REVIEW", (f"{CAUSE_NAMES.get(d['cause'], d['cause'])}: {d['note']}." if d else
                                                        "No cause of loss found in the description; record the cause and describe the loss."),
                             " | ".join(f"{e['form']} · {e['section']}: {e['text']}" for e in (d["evidence"] if d else []))))
    # dates
    loss, eff, exp = claim.get("loss_date"), policy["effective"], policy["expiration"]
    if loss and (loss < eff or loss > exp):
        alerts.append(_alert(claim, "OUTSIDE_POLICY_PERIOD", f"Loss on {loss}; the policy runs {eff} to {exp}."))
    elif loss and (dt.date.fromisoformat(loss) - dt.date.fromisoformat(eff)).days <= 15:
        alerts.append(_alert(claim, "EARLY_LOSS", f"Loss on {loss}, {(dt.date.fromisoformat(loss) - dt.date.fromisoformat(eff)).days} days after the policy started on {eff}."))
    if loss and claim.get("reported_date") and (dt.date.fromisoformat(claim["reported_date"]) - dt.date.fromisoformat(loss)).days > 60:
        alerts.append(_alert(claim, "LATE_REPORT", f"Reported {(dt.date.fromisoformat(claim['reported_date']) - dt.date.fromisoformat(loss)).days} days after the loss; "
                             "the policy asks for prompt notice."))
    # money
    row = policy["coverages"].get(coverage or "", {})
    limit = float(row.get("limit") or 0)
    applicable = min(limit, sublimit) if sublimit and limit else (sublimit or limit)
    ded, ded_why = expected_deductible(policy, coverage or "", check_causes, text, lib)
    paid, reserve, gross = float(claim.get("paid") or 0), float(claim.get("reserve") or 0), float(claim.get("gross_loss") or 0)
    rl, rd = claim.get("recorded_limit"), claim.get("recorded_deductible")
    if rl is not None and limit and abs(float(rl) - limit) > 0.5:
        alerts.append(_alert(claim, "LIMIT_MISMATCH", f"Limit on the claim {float(rl):,.0f}; policy {policy['policy_number']} {coverage} limit {limit:,.0f}."))
    if rd is not None and float(rd) + 0.5 < ded:
        alerts.append(_alert(claim, "DEDUCTIBLE_MISMATCH", f"Deductible on the claim {float(rd):,.0f}; the policy's is {ded:,.0f} ({ded_why})."))
    if sublimit and applicable < limit:
        alerts.append(_alert(claim, "SUBLIMIT", f"This cause is covered only up to {sublimit:,.0f} (endorsement), not the {limit:,.0f} {coverage} limit."))
    if applicable and paid + reserve > applicable + 0.5:
        alerts.append(_alert(claim, "OVER_LIMIT", f"Paid {paid:,.0f} + reserve {reserve:,.0f} = {paid + reserve:,.0f}, above the {applicable:,.0f} that applies."))
    if gross and paid > max(gross - ded, 0) + 0.5:
        alerts.append(_alert(claim, "DEDUCTIBLE_NOT_APPLIED", f"Paid {paid:,.0f} on a {gross:,.0f} loss; with the {ded:,.0f} deductible at most {max(gross - ded, 0):,.0f} is due."))
    if paid > 0 and "NOT COVERED" in statuses and "COVERED" not in statuses:
        alerts.append(_alert(claim, "PAID_NOT_COVERED", f"{paid:,.0f} already paid although the forms exclude this loss."))
    auth = AUTHORITY["CLAIMS_ADJUSTER"]
    near = [p for p in claim.get("payments", []) if 0.9 * auth <= float(p["amount"]) < auth]
    if len(near) >= 2:
        alerts.append(_alert(claim, "SPLIT_PAYMENTS", f"{len(near)} payments between {0.9 * auth:,.0f} and {auth:,.0f} by {claim.get('adjuster')}: "
                             + ", ".join(f"{float(p['amount']):,.0f} to {p['payee']} on {p['date']}" for p in near)
                             + f" (total {sum(float(p['amount']) for p in near):,.0f})."))
    return {"causes": found, "coverage": coverage, "decisions": decisions, "alerts": alerts,
            "money": {"coverage": coverage, "policy limit": limit, "sublimit": sublimit, "limit that applies": applicable, "deductible": ded,
                      "deductible basis": ded_why, "claim limit": rl, "claim deductible": rd, "gross loss": gross, "paid": paid, "reserve": reserve}}


def book_checks(claims: list[dict], policies: dict) -> list[dict]:
    """Checks across claims: a vendor paid on claims of 3+ different insureds, (almost) only ever through one adjuster."""
    by, per_payee = {}, {}
    for c in claims:
        insured = policies.get(c["policy_number"], {}).get("insured")
        for p in c.get("payments", []):
            if p.get("payee_type") == "VENDOR":
                by.setdefault((c.get("adjuster"), p["payee"]), {}).setdefault(insured, []).append(c)
                per_payee.setdefault(p["payee"], set()).add(c["claim_number"])
    out = []
    for (adj, payee), insureds in by.items():
        mine = {x["claim_number"] for cs in insureds.values() for x in cs}
        if len(insureds) >= 3 and len(mine) >= 0.9 * len(per_payee[payee]):
            for cl in {x["claim_number"]: x for cs in insureds.values() for x in cs}.values():
                out.append(_alert(cl, "SHARED_PAYEE", f"{payee} was paid on claims of {len(insureds)} different insureds, all handled by {adj}: "
                                  + ", ".join(sorted({x['claim_number'] for cs in insureds.values() for x in cs})) + "."))
    return out


def check_all(claims: list[dict], policies: dict, lib: FormLibrary) -> list[dict]:
    alerts = []
    for c in claims:
        alerts += check_claim(c, policies.get(c["policy_number"]), lib)["alerts"]
    return alerts + book_checks(claims, policies)


# ------------------------------------------------------------------------------------------ synthetic policies and claims
FIRST = ["Maria", "James", "Linda", "Robert", "Aisha", "Wei", "Carlos", "Priya", "David", "Grace", "Omar", "Elena", "Kevin", "Fatima", "Brian", "Sofia"]
LAST = ["Lopez", "Smith", "Nguyen", "Patel", "Johnson", "Kim", "Garcia", "Brown", "Davis", "Okafor", "Martin", "Rossi", "Chen", "Haddad", "Wilson", "Silva"]
ADJUSTERS = ["Ana Torres", "Ben Clarke", "Chloe Park", "Dev Shah", "Tom Reed"]
VENDORS = ["BlueSky Roofing", "AquaDry Restoration", "Metro Auto Body", "Coastal Builders", "Rapid Restore LLC", "SafeGlass Inc", "City Plumbing Co"]
STORY = {
    "FIRE": "A grease fire started on the stove and burned the kitchen cabinets; smoke damage through the first floor.",
    "WIND": "High winds during the storm blew off shingles; rain came through the opening in the roof into the bedroom.",
    "HURR": "Hurricane winds tore off part of the roof and broke windows; wind-driven rain damaged ceilings.",
    "SURGE": "Storm surge pushed seawater into the house; water came in under the door, about two feet of water on the first floor.",
    "HAIL": "Hailstorm damaged the roof shingles and gutters.",
    "WATER": "The washing machine hose burst while the family was at work; water spread across the laundry room and hallway.",
    "SEWER": "After heavy rain the sewer backed up through the basement floor drain; carpet and drywall ruined.",
    "MOLD": "Insured found mold behind the bathroom vanity; plumber says it was a slow leak for months.",
    "WEAR": "Roof leaking because the shingles are worn out; deterioration over many years, ceiling stained.",
    "THEFT": "Break-in while the insured was on vacation; jewelry and a laptop stolen.",
    "SINKHOLE": "Cracks in the walls and floor; engineer confirmed a sinkhole under the foundation.",
    "EARTHMV": "Earthquake shook the house; chimney cracked and foundation shifted.",
    "FREEZE": "Pipes froze during the cold snap and burst in the attic; heat was on.",
    "TREE": "A tree fell on the garage during a windstorm.",
    "COLL": "Insured rear-ended another car at a red light; front bumper and radiator damaged.",
    "DEER": "Insured hit a deer on the highway at night; hood and headlight damaged.",
    "GLASS": "Rock hit the windshield on the interstate; cracked windshield.",
    "RIDESHARE": "Insured was driving for Uber with a passenger when another car sideswiped the vehicle.",
    "AUTOTHEFT": "Vehicle stolen from the driveway overnight; recovered stripped.",
    "EMPDIS": "Bookkeeper embezzled cash over three months; police report filed.",
    "SLIP": "Customer slipped on a wet floor in the store and broke a wrist.",
    "BLDGWATER": "Supply line to the restroom sink burst overnight; water damage to the shop floor and stock.",
    "CPFLOOD": "River overflowed after the storm; flood water two feet deep in the warehouse.",
    "VANDAL": "Vandals broke in and spray-painted graffiti on the walls; vandalism to fixtures.",
}
CAUSE_OF_STORY = {"FIRE": "FIRE", "WIND": "WIND", "HURR": "WIND", "SURGE": "FLOOD", "HAIL": "HAIL", "WATER": "WATER", "SEWER": "SEWER", "MOLD": "MOLD",
                  "WEAR": "WEAR", "THEFT": "THEFT", "SINKHOLE": "SINKHOLE", "EARTHMV": "EARTHMV", "FREEZE": "FREEZE", "TREE": "FALLOBJ", "COLL": "COLL",
                  "DEER": "COMP", "GLASS": "COMP", "RIDESHARE": "COLL", "AUTOTHEFT": "COMP", "EMPDIS": "EMPDIS", "SLIP": "SLIP", "BLDGWATER": "WATER",
                  "CPFLOOD": "FLOOD", "VANDAL": "VMM"}
HO_STORIES = ["FIRE", "WIND", "HURR", "SURGE", "HAIL", "WATER", "SEWER", "MOLD", "WEAR", "THEFT", "SINKHOLE", "EARTHMV", "FREEZE", "TREE"]
PRODUCT_LOB = {"HO3": "HO", "HO5": "HO", "HO4": "HO", "HO6": "HO", "DP3": "HO", "PA_STD": "PA", "BOP": "BP", "CP": "CP"}
BASE_FORM = {"HO3": "SIM HO 3", "HO5": "SIM HO 3", "HO4": "SIM HO 4", "HO6": "SIM HO 6", "DP3": "SIM DP 3", "PA_STD": "SIM PP 00 01", "BOP": "SIM BP 00 03",
             "CP": "SIS CP 10 30"}


def synthetic_policies(n: int = 48, seed: int = 31) -> dict:
    rng = random.Random(seed)
    out = {}
    products = ["HO3", "HO3", "HO5", "HO4", "HO6", "DP3", "PA_STD", "PA_STD", "BOP", "CP"]
    for i in range(n):
        prod = products[i % len(products)]
        lob = PRODUCT_LOB[prod]
        state = rng.choice(["FL", "GA", "SC", "NC", "AL", "TX"])
        eff = dt.date(2025, 1, 1) + dt.timedelta(days=rng.randrange(0, 540))
        forms = [BASE_FORM[prod]]
        cov = {}
        if lob == "HO":
            a = rng.randrange(200_000, 900_000, 10_000) if prod not in ("HO4",) else 0
            ded = rng.choice([500, 1000, 2500])
            if prod in ("HO3", "HO5", "DP3"):
                cov = {"DWELL": {"limit": a, "deductible": ded}, "OTHSTR": {"limit": round(a * 0.1), "deductible": ded},
                       "PERSPROP": {"limit": round(a * (0.5 if prod != "DP3" else 0.1)), "deductible": ded}, "LOU": {"limit": round(a * 0.2), "deductible": 0}}
            elif prod == "HO6":
                cov = {"DWELL": {"limit": 50_000, "deductible": ded}, "PERSPROP": {"limit": 60_000, "deductible": ded}, "LOU": {"limit": 20_000, "deductible": 0}}
            else:
                cov = {"PERSPROP": {"limit": rng.choice([25_000, 40_000, 60_000]), "deductible": ded}, "LOU": {"limit": 10_000, "deductible": 0}}
            if rng.random() < 0.45:
                forms.append("SIM HO 04 95")
            if state == "FL" and prod in ("HO3", "HO5", "DP3") and rng.random() < 0.6:
                forms.append("SIM HO 23 FL")
            if state in ("FL", "SC", "NC", "AL", "TX") and prod != "HO4":
                forms.append("SIM HO 32 FL")
            if prod in ("HO3", "HO5", "HO6") and rng.random() < 0.35:
                forms.append("SIM HO 04 26")
            if prod in ("HO3", "HO5") and rng.random() < 0.15:
                forms.append("SIM HO 04 54")
        elif lob == "PA":
            cov = {"BI": {"limit": 100_000, "deductible": 0}, "PD": {"limit": 50_000, "deductible": 0},
                   "COMP": {"limit": rng.randrange(8_000, 60_000, 1_000), "deductible": rng.choice([100, 250, 500])}}
            if rng.random() < 0.85:
                cov["COLL"] = {"limit": cov["COMP"]["limit"], "deductible": rng.choice([500, 1000])}
            if rng.random() < 0.2:
                forms.append("SIM PP 03 RS")
        elif lob == "BP":
            b = rng.randrange(300_000, 2_000_000, 50_000)
            cov = {"BLDG": {"limit": b, "deductible": 1000}, "BPP": {"limit": round(b * 0.4), "deductible": 1000}, "LIAB": {"limit": 1_000_000, "deductible": 0}}
            if rng.random() < 0.5:
                forms.append("SIM BP 04 ED")
        else:
            b = rng.randrange(1_000_000, 15_000_000, 100_000)
            cov = {"BLDG": {"limit": b, "deductible": 5000}, "BPP": {"limit": round(b * 0.5), "deductible": 5000}}
            if rng.random() < 0.3:
                forms.append("SIS CP 10 65")
        pn = f"{'SIM' if lob != 'CP' else 'SIS'}-{prod.replace('_STD', '')}-{24001 + i}"
        out[pn] = {"policy_number": pn, "product": prod, "lob": lob, "state": state, "insured": f"{rng.choice(FIRST)} {rng.choice(LAST)}",
                   "effective": eff.isoformat(), "expiration": (eff + dt.timedelta(days=365)).isoformat(), "coverages": cov, "forms": forms}
    return out


def synthetic_claims(policies: dict, n: int = 90, seed: int = 41, lib: FormLibrary | None = None) -> list[dict]:
    """Claims with loss descriptions; about a third carry something an adjuster, underwriter or manager must see."""
    rng = random.Random(seed)
    lib = lib or FormLibrary.synthetic()
    pols = list(policies.values())
    out = []
    honest_vendors = [v for v in VENDORS if v != "Rapid Restore LLC"]
    for i in range(n):
        p = pols[rng.randrange(len(pols))]
        lob = p["lob"]
        if lob == "HO":
            story = rng.choice(HO_STORIES if p["product"] != "HO4" else ["FIRE", "THEFT", "WATER", "SEWER", "WIND", "MOLD"])
            coverage = "PERSPROP" if story in ("THEFT",) or p["product"] == "HO4" else "DWELL"
        elif lob == "PA":
            story = rng.choice(["COLL", "COLL", "DEER", "GLASS", "RIDESHARE", "AUTOTHEFT"])
            coverage = "COLL" if story in ("COLL", "RIDESHARE") else "COMP"
        elif lob == "BP":
            story, coverage = rng.choice([("EMPDIS", "BPP"), ("BLDGWATER", "BLDG"), ("THEFT", "BPP"), ("VANDAL", "BLDG"), ("FIRE", "BLDG")])
        else:
            story, coverage = rng.choice([("FIRE", "BLDG"), ("CPFLOOD", "BLDG"), ("WIND", "BLDG"), ("BLDGWATER", "BPP"), ("VANDAL", "BLDG")])
        if coverage not in p["coverages"] and lob != "PA":
            coverage = next(iter(p["coverages"]))
        eff = dt.date.fromisoformat(p["effective"])
        loss = eff + dt.timedelta(days=rng.randrange(20, 360))
        reported = loss + dt.timedelta(days=int(rng.expovariate(1 / 5)))
        row = p["coverages"].get(coverage) or {"limit": 0, "deductible": 0}
        cause = CAUSE_OF_STORY[story]
        c = {"claim_number": f"CLM-{70001 + i}", "policy_number": p["policy_number"], "loss_date": loss.isoformat(), "reported_date": reported.isoformat(),
             "cause": cause, "coverage": coverage, "description": STORY[story], "notes": "", "adjuster": rng.choice(ADJUSTERS[:4]),
             "recorded_limit": float(row["limit"]), "recorded_deductible": 0.0, "gross_loss": 0.0, "paid": 0.0, "reserve": 0.0, "payments": []}
        # an honest adjuster: the policy's deductible (hurricane % included), the limit or sublimit, nothing paid on an exclusion
        first = check_claim(c, p, lib)
        m = first["money"] or {"deductible": 0, "limit that applies": 0}
        ded = float(m["deductible"])
        c["recorded_deductible"] = ded
        applicable = float(m["limit that applies"] or row["limit"] or 5000)
        gross = round(min(applicable * rng.uniform(0.05, 0.6), rng.lognormvariate(9.3, 0.9)), 0) + ded
        c["gross_loss"] = gross
        statuses = {d["status"] for d in first["decisions"]} | ({"NOT COVERED"} if any(a["type"] == "NOT_COVERED" for a in first["alerts"]) else set())
        if "NOT COVERED" in statuses or "REVIEW" in statuses:
            net = 0.0
            c["reserve"] = 0.0
        else:
            net = max(min(gross - ded, applicable), 0)
        paid = round(net * rng.choice([0, 0.5, 1.0]), 0)
        c["paid"], c["reserve"] = paid, round(net - paid, 0) if net else 0.0
        if paid:
            vendor = rng.random() < 0.6
            c["payments"] = [{"amount": paid, "payee": rng.choice(honest_vendors) if vendor else p["insured"],
                              "payee_type": "VENDOR" if vendor else "INSURED", "date": (reported + dt.timedelta(days=10)).isoformat()}]
        # planted findings (synthetic), so every alert type shows up
        twist = rng.random()
        if twist < 0.07:
            c["recorded_limit"] = round(float(row["limit"]) * 1.5, -3)
            c["notes"] = "Limit updated on the claim by the adjuster."
        elif twist < 0.14 and ded > 0 and not statuses & {"NOT COVERED", "REVIEW"}:
            c["recorded_deductible"] = 0.0
            c["paid"] = round(gross, 0)
            c["reserve"] = 0.0
            c["payments"] = [{"amount": c["paid"], "payee": rng.choice(honest_vendors), "payee_type": "VENDOR", "date": (reported + dt.timedelta(days=7)).isoformat()}]
        elif twist < 0.19 and story == "SURGE":
            c["cause"] = "WIND"
        elif twist < 0.24:
            c["loss_date"] = (eff - dt.timedelta(days=rng.randrange(3, 40))).isoformat()
            c["reported_date"] = (dt.date.fromisoformat(c["loss_date"]) + dt.timedelta(days=20)).isoformat()
        elif twist < 0.28 and lob == "PA" and story == "COLL":
            c["coverage"] = "COMP"
            c["recorded_deductible"] = float(p["coverages"]["COMP"]["deductible"])
            c["recorded_limit"] = float(p["coverages"]["COMP"]["limit"])
        elif twist < 0.32:
            c["adjuster"] = "Tom Reed"
            c["payments"] = [{"amount": a, "payee": "Rapid Restore LLC", "payee_type": "VENDOR", "date": (reported + dt.timedelta(days=d)).isoformat()}
                             for a, d in ((24_600.0, 6), (24_850.0, 9))]
            c["paid"] = 49_450.0
            c["gross_loss"] = max(c["gross_loss"], 49_450.0 + ded)
            c["reserve"] = 0.0
        elif twist < 0.36:
            c["reported_date"] = (loss + dt.timedelta(days=rng.randrange(75, 160))).isoformat()
        elif twist < 0.40 and c["paid"] == 0 and "NOT COVERED" in statuses:
            c["paid"] = round(max(gross - ded, 0), 0)
            c["payments"] = [{"amount": c["paid"], "payee": p["insured"], "payee_type": "INSURED", "date": (reported + dt.timedelta(days=5)).isoformat()}]
        out.append(c)
    return showcase_claims(policies) + out


def showcase_claims(policies: dict) -> list[dict]:
    """Six claims that show each kind of finding clearly (synthetic)."""
    def pick(prod, need=(), state=None):
        for p in policies.values():
            if p["product"] == prod and all(f in p["forms"] for f in need) and (state is None or p["state"] == state):
                return p
        return next(p for p in policies.values() if p["product"] == prod)
    out = []

    def add(n, p, cov, cause, desc, gross, paid, rec_ded=None, rec_limit=None, payments=None, notes=""):
        eff = dt.date.fromisoformat(p["effective"])
        loss = eff + dt.timedelta(days=120)
        row = p["coverages"].get(cov, {"limit": 0, "deductible": 0})
        out.append({"claim_number": f"CLM-{n}", "policy_number": p["policy_number"], "loss_date": loss.isoformat(),
                    "reported_date": (loss + dt.timedelta(days=2)).isoformat(), "cause": cause, "coverage": cov, "description": desc, "notes": notes,
                    "adjuster": "Ben Clarke", "recorded_limit": float(rec_limit if rec_limit is not None else row["limit"]),
                    "recorded_deductible": float(rec_ded if rec_ded is not None else row["deductible"]), "gross_loss": float(gross), "paid": float(paid),
                    "reserve": 0.0, "payments": payments or ([{"amount": float(paid), "payee": p["insured"], "payee_type": "INSURED",
                                                              "date": (loss + dt.timedelta(days=12)).isoformat()}] if paid else [])})
    ho = pick("HO3", ("SIM HO 32 FL",))
    add(69901, ho, "DWELL", "WIND", STORY["SURGE"], 48_000, 46_000, notes="Cause code entered by the adjuster on the first call.")
    add(69902, ho, "DWELL", "WIND", STORY["HURR"], 30_000, 0, rec_ded=ho["coverages"]["DWELL"]["deductible"])
    add(69903, ho, "DWELL", "WATER", STORY["WATER"], 12_500, 12_500 - ho["coverages"]["DWELL"]["deductible"])
    add(69904, ho, "DWELL", "WIND", "Hurricane winds tore shingles off the roof, and the storm surge then pushed seawater through the front door.", 60_000, 0)
    wb = pick("HO3", ("SIM HO 04 95",))
    add(69905, wb, "DWELL", "SEWER", STORY["SEWER"], 19_000, 18_000)
    pa = next(p for p in policies.values() if p["product"] == "PA_STD" and "COLL" in p["coverages"])
    add(69906, pa, "COMP", "COMP", STORY["COLL"], 6_200, 6_200 - pa["coverages"]["COMP"]["deductible"],
        rec_ded=pa["coverages"]["COMP"]["deductible"], rec_limit=pa["coverages"]["COMP"]["limit"])
    return out
