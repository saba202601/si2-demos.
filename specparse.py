"""Read WCIO data specification PDFs into a field catalog.

Works on layout-preserving text (pypdf `extraction_mode="layout"` or `pdftotext -layout`).
For every field it captures: record, field number, name, class (N / AN / A), start, end, length,
code list (pick list) with per-code N/A states, NOT APPLICABLE / OPTIONAL states,
report format (YYMMDD, YYDDD, YYYYMMDD, implied decimals) and constants ("Report "1"").
"""
from __future__ import annotations

import io
import re

FIELD = re.compile(
    r"^\s{0,50}(\d{1,3}[A-Z]?)\s{2,}(.+?)\s{2,}(?:\(?(N|AN|A)\)?\s+)?(\d{1,4})(?:\s*-\s*(\d{1,4}))?\s+(\d{1,4})\s*$")
WRAP = re.compile(
    r"^\s{0,48}(\d{1,3}[A-Z]?\s{2,})?([A-Z][A-Za-z ()/'’&—–-]+?)\s{2,}\(?(N|AN|A)\)?\s+(\d{1,4})-\s+(\d{1,4})\s*$")
NUM = re.compile(r"^\s*(\d{1,4})\s*$")
PAGE_REC = re.compile(r"^Page\s+\d+\s{2,}(?:Record\s+)?(.+?)\s*$")
TITLE = re.compile(
    r"^\s*(?:[IVX]+\.\s*)?([A-Z][A-Z0-9 /&()'’,.-]*RECORD(?:\s*[-–]\s*[A-Z0-9 ()/'-]+)?|LINK DATA COMMON TO ALL RECORDS)\s*$")
CODE = re.compile(r"^\s{8,}([A-Z0-9]{1,6})\s{3,}(\S.{2,})$")
NA = re.compile(r"NOT APPLICABLE:\s*(.+)")
OPT = re.compile(r"OPTIONAL:\s*(.+)")
FOOT = re.compile(r"©|WCIO Workers Compensation Data|^\s*Effective|Field No\.|WCIO WORKERS COMPENSATION")
FMT = re.compile(r"Format\s+(YYYYMMDD|YYMMDD|YYDDD|MMDDYYYY|MMDDYY|HHMMSS|\$\d+\.\d+)")
CONST = re.compile(r"Report\s+[“\"]([A-Z0-9]{1,10})[”\"]\s*(?:for|\.|$)")
CODE_NA = re.compile(r"\s*N/A:\s*([A-Z]{2,4}(?:,\s*[A-Z]{2,4})*)")

SPECS = {
    "WCSTAT": "Unit Statistical Reporting",
    "WCPOLS": "Policy Reporting",
    "WCIND": "Indemnity Data Call",
    "WCMED": "Medical Data Call",
}


def pdf_to_text(data: bytes) -> str:
    """Layout text from a PDF using pypdf (pure Python, works on Streamlit Cloud)."""
    import pypdf
    reader = pypdf.PdfReader(io.BytesIO(data))
    return "\n".join(p.extract_text(extraction_mode="layout") or "" for p in reader.pages)


def detect_spec(text: str) -> str | None:
    head = text[:4000].upper()
    for key in ("WCPOLS", "WCSTAT", "WCMED", "WCIND"):
        if f"({key})" in head or key in head[:1500]:
            return key
    return None


def _new(spec, title, page_rec, no, name, cls, s, e, b):
    return {"spec": spec, "record_title": title or page_rec, "page_record": page_rec, "field_no": no,
            "name": name, "class": cls or "AN", "start": s, "end": e, "length": b,
            "not_applicable": "", "optional": "", "description": [], "codes": []}


def parse_text(text: str, spec: str) -> list[dict]:
    fields, cur, page_rec, title, in_codes, pending = [], None, "", "", False, None
    for ln in text.splitlines():
        stripped = ln.strip()
        m = PAGE_REC.match(stripped)
        if stripped.startswith("Page ") and m:
            page_rec = m.group(1)
            continue
        if FOOT.search(ln):
            continue
        t = TITLE.match(ln)
        if t and not FIELD.match(ln):
            title = re.sub(r"\s+", " ", t.group(1)).strip()
            continue
        f = FIELD.match(ln)
        if f:
            no, name, cls, s, e, b = f.groups()
            name = re.sub(r"\s+", " ", name).strip()
            s, e, b = int(s), int(e or s), int(b)
            if e >= s and e - s + 1 == b and not name.startswith(("Format", "Code")):
                cur = _new(spec, title, page_rec, no, name, cls, s, e, b)
                fields.append(cur)
                in_codes, pending = False, None
                continue
        w = WRAP.match(ln)
        if w:
            pending = {"no": (w.group(1) or "").strip(), "name": re.sub(r"\s+", " ", w.group(2)).strip(),
                       "cls": w.group(3), "start": int(w.group(4)), "bytes": int(w.group(5))}
            if pending["no"]:
                p = pending
                cur = _new(spec, title, page_rec, p["no"], p["name"], p["cls"], p["start"],
                           p["start"] + p["bytes"] - 1, p["bytes"])
                fields.append(cur)
                in_codes, pending = False, None
            continue
        if pending is not None:
            nm = NUM.match(ln)
            if nm:
                p = pending
                cur = _new(spec, title, page_rec, nm.group(1), p["name"], p["cls"], p["start"],
                           p["start"] + p["bytes"] - 1, p["bytes"])
                fields.append(cur)
                in_codes, pending = False, None
                continue
        if cur is None or not stripped:
            continue
        if stripped.startswith("Code") and "Description" in stripped:
            in_codes = True
            continue
        n = NA.search(stripped)
        if n:
            cur["not_applicable"] = n.group(1).strip()
            continue
        o = OPT.search(stripped)
        if o:
            cur["optional"] = o.group(1).strip()
            continue
        c = CODE.match(ln)
        if in_codes and c and len(c.group(1)) <= max(cur["length"], 2):
            cur["codes"].append([c.group(1), re.sub(r"\s+", " ", c.group(2)).strip()])
            continue
        if in_codes and cur["codes"] and ln.startswith(" " * 20) and not c:
            cur["codes"][-1][1] += " " + stripped
            continue
        if len(cur["description"]) < 40:
            cur["description"].append(stripped)

    seen, out = set(), []
    for f in fields:
        key = f["page_record"] if spec in ("WCSTAT", "WCPOLS") else f["record_title"]
        k = (key, f["start"], f["end"])
        if k in seen:
            continue
        seen.add(k)
        out.append(_finish(f))
    return out


def _finish(f: dict) -> dict:
    desc = " ".join(f["description"])
    fm = FMT.search(desc)
    f["format"] = fm.group(1) if fm else ""
    if f["format"].startswith("$"):
        f["implied_decimals"] = int(f["format"].split(".")[1])
    elif "assumed decimal" in desc.lower():
        f["implied_decimals"] = 2
    else:
        f["implied_decimals"] = 0
    cm = CONST.search(desc)
    f["constant"] = cm.group(1) if cm and "RECORD TYPE" in f["name"].upper() else ""
    codes = []
    for code, text in f["codes"]:
        na = ""
        m = CODE_NA.search(text)
        if m:
            na = m.group(1)
            text = CODE_NA.sub("", text).strip()
        codes.append({"code": code, "description": text[:240], "na_states": na,
                      "reserved": "reserved for future use" in text.lower()})
    f["codes"] = codes
    f["description"] = desc[:900]
    f["signed"] = "negative" in desc.lower() and f["class"] == "N"
    return f
