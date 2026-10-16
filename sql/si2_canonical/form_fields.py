"""Read fillable insurance forms (PDF) into canonical concepts: elements, pick lists, options, where-used.

    python form_fields.py <folder>          print what each form contains and how it maps (no database needed)

Works on any fillable PDF form. For each field it finds the meaning from, in order:
  1. a structured field name     Producer_MailingAddress_LineOne_A   -> entity Producer, attribute Mailing Address Line One
  2. the same field on another form that has a structured name (learned from the descriptions both share)
  3. the field's description     "Enter date: The effective date of the policy."  -> attribute Effective Date, entity Policy
  4. a label-like field name     "NAIC CODE", "PhoneACNoExt"
Fields with none of these (Text_1, Check Box_7) are reported, not guessed.

Check boxes that share a prefix become a pick list (Policy_LineOfBusiness_BusinessAutoIndicator ... -> LINE_OF_BUSINESS:
BUSINESS_AUTO, ...); a lone check box is a yes / no element; radio groups and choice lists keep their own values.
Only short names and identifiers are kept (as synonyms, with the form as the source); descriptions are SI²'s own,
built from the structure, never the form's text.
"""
from __future__ import annotations

import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

STOP = {"the", "a", "an", "of", "for", "to", "is", "be", "being", "on", "in", "or", "and", "by", "which", "that", "this", "with", "as", "at", "if"}
GENERIC = {"description", "amount", "code", "name", "full name", "identifier", "indicator", "count", "date", "remark", "remarks", "text", "type",
           "value", "percent", "limit", "year", "explanation", "number", "other", "other description", "premium amount", "status", "comment",
           "title", "rate", "deductible amount", "limit amount", "premium", "location", "phone number", "address", "total"}

# attribute words (optionally with the entity) -> element already in the canonical master
CANON = {
    "mailing address line one": "ADDRESS_STREET", "physical address line one": "ADDRESS_STREET", "address line one": "ADDRESS_STREET",
    "mailing address line two": "ADDRESS_LINE_2", "physical address line two": "ADDRESS_LINE_2", "address line two": "ADDRESS_LINE_2",
    "mailing address city name": "ADDRESS_CITY", "physical address city name": "ADDRESS_CITY", "city name": "ADDRESS_CITY",
    "mailing address state or province code": "STATE", "physical address state or province code": "STATE", "state or province code": "STATE",
    "mailing address postal code": "ZIP_CODE", "physical address postal code": "ZIP_CODE", "postal code": "ZIP_CODE",
    "mailing address country code": "COUNTRY_CODE", "physical address country code": "COUNTRY_CODE", "country code": "COUNTRY_CODE",
    "physical address county name": "COUNTY", "county name": "COUNTY",
    "phone number": "PHONE", "primary phone number": "PHONE", "secondary phone number": "SECONDARY_PHONE", "fax number": "FAX_NUMBER",
    "email address": "EMAIL", "primary email address": "EMAIL", "secondary email address": "SECONDARY_EMAIL", "website address": "WEBSITE_ADDRESS",
    "contact person full name": "CONTACT_NAME", "contact person phone number": "PHONE", "contact person email address": "EMAIL",
    "tax identifier": "FEIN", "form completion date": "APPLICATION_DATE", "completion date": "APPLICATION_DATE", "birth date": "DATE_OF_BIRTH", "gl code": "GL_CLASS_CODE", "sic code": "SIC_CODE", "naics code": "NAICS_CODE",
    "policy number identifier": "POLICY_NUMBER", "naic code": "NAIC_CODE", "customer identifier": "AGENCY_CUSTOMER_ID",
    "effective date": "POLICY_EFFECTIVE_DATE", "expiration date": "POLICY_EXPIRATION_DATE",
    "legal entity": "LEGAL_ENTITY_TYPE", "business start date": "DATE_BUSINESS_STARTED", "producer identifier": "PRODUCER_CODE",
    "national identifier": "NATIONAL_PRODUCER_NUMBER", "state license identifier": "STATE_PRODUCER_LICENSE_NUMBER",
    "construction code": "CONSTRUCTION", "year built": "YEAR_BUILT", "protection class code": "PROTECTION_CLASS", "storey count": "NUMBER_OF_STORIES",
    "story count": "NUMBER_OF_STORIES", "roof material code": "ROOF_TYPE", "square feet count": "SQUARE_FEET", "total area": "SQUARE_FEET",
    "vehicle identification number": "VIN", "model year": "MODEL_YEAR", "license number identifier": "LICENSE_NUMBER",
}
ENTITY_NAME = {"full name": {"producer": "AGENCY_NAME", "insurer": "CARRIER_NAME", "named insured": "INSURED_NAME", "applicant": "INSURED_NAME",
                             "co applicant": "INSURED_NAME", "additional interest": "INSURED_NAME", "contact": "CONTACT_NAME", "form": None}}
SUBJECT = [  # entity words -> subject area
    (r"producer|agency|agent", "PRODUCER"), (r"insurer|policy|binder|form|program|line of business|commercial policy|personal policy|billing", "POLICY"),
    (r"personal property|inland marine|jewel|furs|fine arts|golf|silverware|camera|musical", "PROPERTY"),
    (r"named insured|applicant|\binsured\b|contact|employer|subsidiary|additional interest|party|\bperson\b|household|spouse", "PARTY"),
    (r"vehicle|auto|garage|truck", "VEHICLE"), (r"driver", "DRIVER"), (r"claim|loss|occurrence|accident|injur|witness|claimant", "CLAIM"),
    (r"general liability|products|contractor|liability|premises operation|athletic", "LIABILITY"),
    (r"workers|employee|payroll|wc|rating classification|officer", "WORKERS_COMP"),
    (r"building|structure|construction|residen|dwelling|alarm|fire|protection|swimming|pool|safe|vault|property|roof|heating|wiring|plumbing|exposure|occupancy|inland marine|animal",
     "PROPERTY"),
    (r"coverage|limit|deductible|endorsement", "COVERAGE"), (r"location|premises|address", "LOCATION"), (r"premium", "PREMIUM"),
    (r"prior|cancel|non ?renew|underwrit|business information|general information|crime", "UNDERWRITING"),
]


def words(token: str) -> str:
    """Producer_MailingAddress_LineOne -> 'producer mailing address line one'."""
    t = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", token.replace("_", " "))
    t = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", t)
    return re.sub(r"\s+", " ", t).strip().lower()


def snake(text: str, n: int = 80) -> str:
    s = re.sub(r"[^A-Z0-9]+", "_", text.upper()).strip("_")
    return s[:n].rstrip("_")


def title(text: str) -> str:
    small = {"of", "and", "or", "the", "a", "to", "for", "in", "on", "per"}
    out = [w if (i and w in small) else (w.upper() if w in {"naic", "gl", "sic", "naics", "id", "vin", "fein", "bop", "ul", "osha", "cpa"} else w.capitalize())
           for i, w in enumerate(text.split())]
    return " ".join(out)


@dataclass
class Field:
    form: str
    name: str                    # field name without the [0] suffixes
    kind: str                    # TEXT, CHECK, RADIO, CHOICE
    tooltip: str = ""
    states: list = field(default_factory=list)
    options: list = field(default_factory=list)
    base: str = ""               # name without the _A / _B repeat index
    entity: str = ""             # words
    attribute: str = ""          # words
    group: str = ""              # check box group key
    option: str = ""             # check box option words
    source: str = ""             # how the meaning was found: NAME, LEARNED, DESCRIPTION, LABEL, NONE


STRUCTURED = re.compile(r"^(?:[A-Z][A-Za-z0-9]*)(?:_[A-Z][A-Za-z0-9]*)+$")
UNLABELED = re.compile(r"^(text|check ?box|button|radio( button)?|group|field|undefined|untitled|\d+)[ _]?\d*$", re.I)


def form_id(text: str, fallback: str) -> str:
    m = re.search(r"ACORD\s+(\d{2,4}[A-Z]?)(?:\s+[A-Z]{2})?\s*\((\d{4}/\d{2})\)", text)
    if m:
        return f"ACORD {m[1]} ({m[2]})"
    fb = re.sub(r"^[0-9a-f]{6,}[-_ ]+", "", fallback, flags=re.I)        # drop a download hash in front of the file name
    return re.sub(r"[-_]+", " ", fb).strip()[:60] or fallback[:60]


def read_pdf(path: Path) -> tuple[str, list[Field]]:
    from pypdf import PdfReader
    r = PdfReader(str(path))
    head = " ".join((p.extract_text() or "") for p in r.pages[:2])
    fid = form_id(head, path.stem)
    out = []
    for full, v in (r.get_fields() or {}).items():
        ft = v.get("/FT")
        if ft is None:
            continue
        name = re.sub(r"\[\d+\]", "", str(full).split(".")[-1]).strip()
        if re.match(r"^(clear|reset|print|submit|save|email|e-mail)\b", name, re.I):
            continue                                              # form buttons, not data
        states = [str(s).lstrip("/") for s in (v.get("/_States_") or []) if str(s) not in ("/Off", "Off")]
        states = [x for x in states if not re.fullmatch(r"(Type|BBox|Resources|Subtype|FormType|Matrix|Filter|Length|N|D|R)", x)]
        opts = []
        for o in (v.get("/Opt") or []):
            o = o[-1] if isinstance(o, (list, tuple)) else o
            opts.append(str(o))
        kind = "TEXT" if ft == "/Tx" else "CHOICE" if ft == "/Ch" else ("CHECK" if set(states) <= {"1", "Yes", "On", "X", "True"} else "RADIO")
        tip = re.sub(r"\s+", " ", str(v.get("/TU") or "")).strip()
        out.append(Field(fid, name, kind, tip, states, opts))
    return fid, out


def _tip_phrase(tip: str) -> tuple[str, str]:
    """Description -> (attribute words, entity words) in SI²'s own short form; only used to name and match, never stored."""
    t = re.sub(r"^[^:]{0,60}:\s*", "", tip)                        # drop "Enter text:" / "Check the box (if applicable):"
    t = re.split(r"(?<=[a-z0-9)])\.\s|\(e\.g\.|\(MM/|;\s", t + " ")[0]
    t = re.sub(r"^(the|a|an)\s+", "", t.strip(), flags=re.I)
    t = re.sub(r"^indicates( that)?( whether)?( the)?\s+", "", t, flags=re.I)
    for _ in range(3):                                            # "Indicate whether there is a ..." -> "..."
        t = re.sub(r"^(enter|indicate|describe|explain|identify|list|provide|check|specify|state|show|select|give)\b(\s+(whether|if|the|any|all|a|an|there|is|are|has|have|was|were|applicant|insured))*\s+",
                   "", t, flags=re.I)
    t = re.sub(r"^(month/day/year|mm/dd/yyyy)\s+(on\s+)?which\s+(the\s+)?form\s+is\s+completed.*", "form completion date", t, flags=re.I)
    ent = ""
    m = re.search(r"\s+(?:of|for)\s+(?:the|a|an|this)\s+([a-z /&'-]{3,40})$", t, re.I)
    if m:
        ent, t = m[1], t[:m.start()]
    t = re.sub(r"\be-?\s?mail\b", "email", t, flags=re.I).replace("'s ", " ")
    w = [x for x in re.sub(r"[^a-z0-9 ]", " ", t.lower()).split() if x not in STOP][:5]
    return " ".join(w), " ".join(x for x in re.sub(r"[^a-z0-9 ]", " ", ent.lower()).split() if x not in STOP)


def interpret(fields: list[Field], learned: dict | None = None) -> None:
    """Fill base / entity / attribute / group / option / source on each field."""
    learned = learned or {}
    for f in fields:
        f.base = re.sub(r"(?<=[A-Za-z])\d+$", "", re.sub(r"_[A-Z]{1,2}$", "", f.name))     # CertificateRequired4 -> CertificateRequired
        tipkey = re.sub(r"[^a-z0-9]", "", f.tooltip.lower())
        name = f.base
        if STRUCTURED.match(name) and not UNLABELED.match(name):
            f.source = "NAME"
        elif tipkey and tipkey in learned:
            name, f.source = learned[tipkey], "LEARNED"
        if f.source in ("NAME", "LEARNED"):
            toks = [re.sub(r"(?<=[A-Za-z])\d+$", "", t) for t in name.split("_") if t and not t.isdigit()]   # Location1 -> Location
            if toks and toks[0] == "ACORD" and len(toks) > 2:
                toks = toks[1:]
            elif toks and toks[0] == "ACORD":
                toks = ["Form"] + toks[1:]
            f.entity = words(toks[0]) if len(toks) > 1 else ""
            attr = toks[1:] if len(toks) > 1 else toks
            if f.kind == "CHECK" and attr and attr[-1].endswith("Indicator") and len(attr[-1]) > len("Indicator"):
                f.option = words(attr[-1][:-len("Indicator")])
                f.group = "_".join(toks[:-1])
                f.attribute = words("_".join(attr[:-1])) if len(attr) > 1 else ""
            else:
                f.attribute = words("_".join(attr))
            continue
        if f.tooltip and len(f.tooltip) > 12:
            a, e = _tip_phrase(f.tooltip)
            if a:
                f.attribute, f.entity, f.source = a, e, "DESCRIPTION"
                continue
        if not UNLABELED.match(f.base) and re.search(r"[A-Za-z]{3}", f.base):
            f.attribute, f.source = words(re.sub(r"[^A-Za-z0-9 _]", " ", f.base)), "LABEL"
            continue
        f.source = "NONE"


def learn(fields: list[Field]) -> dict:
    """Description -> structured name, from forms that have both."""
    out = {}
    for f in fields:
        if f.tooltip and STRUCTURED.match(f.name) and not UNLABELED.match(f.name):
            out.setdefault(re.sub(r"[^a-z0-9]", "", f.tooltip.lower()), re.sub(r"_[A-Z]{1,2}$", "", f.name))
    return out


def dtype(f: Field) -> str:
    t, a = f.tooltip.lower()[:30], f.attribute
    if f.kind in ("CHECK", "RADIO", "CHOICE"):
        return "CODE"
    if re.search(r"\b(description|name|code|identifier|explanation|remarks?|comment)\b", a):
        return "TEXT"
    if "enter date" in t or re.search(r"\bdate\b", a):
        return "DATE"
    if "amount" in t or re.search(r"\b(amount|premium|limit|deductible|value|cost|payroll|sales|receipts)\b", a) and "code" not in a:
        return "AMOUNT"
    if "percent" in t or re.search(r"\b(percent|percentage|pct)\b", a):
        return "PERCENT"
    if re.search(r"enter (rate|factor)", t) or re.search(r"\b(rate|factor|modifier)\b", a):
        return "DECIMAL"
    if "enter year" in t or re.search(r"\b(year|count|number of)\b", a) and "identifier" not in a:
        return "INTEGER"
    return "TEXT"


def concept_name(f: Field) -> tuple[str, str]:
    """(element code, element name): the attribute, prefixed by the entity when the attribute alone says nothing."""
    a, e = f.attribute or f.option, f.entity
    if not a:
        return "", ""
    known = ENTITY_NAME.get(a, {}).get(e) if e else None
    if known:
        return known, title(a if not e else f"{e} {a}")
    if a in CANON and not (a in ("effective date", "expiration date") and e not in ("policy", "")):
        return CANON[a], title(a)
    full = f"{e} {a}".strip() if (a in GENERIC or len(a.split()) == 1) and e else a
    return snake(full), title(full)


def subject(f: Field) -> str:
    text = f"{f.entity} {f.attribute}"
    return next((sa for rx, sa in SUBJECT if re.search(rx, text)), "UNDERWRITING")


def catalog(forms: dict, source: str = "Insurance forms") -> tuple[dict, list]:
    """Collector catalog for every form, and where-used rows (form, entity, field name, element code)."""
    import collect_si2_databases as K
    cat = K.new_catalog(source)
    usage, groups = [], defaultdict(list)
    for fid, fields in forms.items():
        for f in fields:
            if f.source == "NONE":
                continue
            if f.group and f.option:
                groups[(fid, f.group)].append(f)
                continue
            code, name = concept_name(f)
            if not code:
                continue
            pl = None
            if f.kind == "RADIO" and f.states and not set(s.upper() for s in f.states) <= {"Y", "N", "YES", "NO"}:
                pl = _list(K, cat, code, name, [(s, s) for s in f.states], fid)
            elif f.kind == "CHOICE" and f.options:
                pl = _list(K, cat, code, name, [(o, o) for o in f.options], fid)
            elif f.kind in ("CHECK", "RADIO"):
                pl = "YES_NO"
            _element(cat, code, name, f, pl, fid)
            usage.append((fid, f.entity, f.base, code))
    for (fid, gkey), members in groups.items():
        if len(members) == 1:                                   # a lone check box: yes / no
            f = members[0]
            f.attribute = f"{f.attribute} {f.option}".strip()
            code, name = concept_name(f)
            _element(cat, code, name, f, "YES_NO", fid)
            usage.append((fid, f.entity, f.base, code))
            continue
        f0 = members[0]
        a = f0.attribute or "type"
        e = f0.entity
        full = f"{e} {a}".strip() if (a in GENERIC or len(a.split()) == 1) and e else a
        code, name = (CANON.get(a) or snake(full)), title(full)
        _list(K, cat, code, name, [(snake(m.option, 60), title(m.option)) for m in members], fid)
        f0c = Field(fid, f0.base, "CHOICE", entity=e, attribute=a)
        _element(cat, code, name, f0c, code, fid)
        for m in members:
            usage.append((fid, m.entity, m.base, code))
    return cat, usage


def _list(K, cat, code, name, opts, fid):
    pl = K.add_picklist(cat, f"PL:{code}", code, name, f"Values of {name.lower()} on insurance forms.", library="FORMS")
    pl["keep_code"] = True
    for oc, on in opts:
        oc = snake(str(oc), 60) or str(oc)
        o = K.add_option(pl, oc, on, None)
        if o is not None and (on, fid) not in o["aliases"]:
            o["aliases"].append((on, fid))
    return code


def _element(cat, code, name, f: Field, picklist, fid):
    e = cat["elements"].setdefault(f"DE:{code}", {
        "code": code, "name": name, "dtype": "CODE" if picklist else dtype(f), "subject": subject(f), "curated": True,
        "desc": f"{name}{' of the ' + f.entity if f.entity and f.entity not in name.lower() else ''}, as collected on insurance application and notice forms."
                + (" Name drafted from the form; SME to confirm." if f.source == "DESCRIPTION" else ""),
        "picklist_key": f"PL:{picklist}" if picklist and f"PL:{picklist}" in cat["picklists"] else None, "picklist_code": picklist,
        "pii": bool(re.search(r"name|address|phone|email|birth|tax identifier|license number|social security", name.lower())), "aliases": []})
    alias = (f.base, fid)
    useful = f.source in ("NAME", "LABEL") or (f.source == "LEARNED" and STRUCTURED.match(f.base))
    if useful and alias not in e["aliases"] and len(f.base) <= 300 and not UNLABELED.match(f.base) and len(re.sub(r"[^A-Za-z]", "", f.base)) >= 4:
        e["aliases"].append(alias)


def read_folder(folder: Path) -> dict:
    forms, all_fields = {}, []
    for p in sorted(folder.glob("*.pdf")):
        try:
            fid, fields = read_pdf(p)
        except Exception as ex:  # noqa: BLE001 - a broken PDF is reported, the rest go on
            print(f"  {p.name}: could not be read ({ex})")
            continue
        if fid in forms:                                   # the same form inside a combined file: name it after the file
            fid = f"{fid} in {form_id('', p.stem)}"[:60]
        while fid in forms:
            fid += "*"
        forms[fid] = fields
        all_fields += fields
    known = learn(all_fields)
    for fields in forms.values():
        interpret(fields, known)
    return forms


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    forms = read_folder(Path(sys.argv[1] if len(sys.argv) > 1 else "."))
    for fid, fields in forms.items():
        by = defaultdict(int)
        for f in fields:
            by[f.source] += 1
        print(f"{fid:<24} {len(fields):>4} fields  " + "  ".join(f"{k} {v}" for k, v in sorted(by.items())))
    cat, usage = catalog(forms)
    print(f"{len(cat['elements'])} elements, {len(cat['picklists'])} pick lists, {sum(len(p['options']) for p in cat['picklists'].values())} options, "
          f"{len(usage)} where-used rows")
