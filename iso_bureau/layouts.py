"""Parse ISO 150-byte bureau layouts supplied as Excel workbooks.

Every sheet becomes one (line of business, record type) layout.  Start
positions are recomputed from lengths so a mangled "Position" column (Excel
turned "1-2" into a date in the Commercial Auto file) never breaks the build;
any disagreement between the supplied and computed position is returned as an
audit finding for the SME.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import openpyxl

RECORD_LENGTH = 150

# sheet name -> (LOB code, record type)
SHEET_MAP = {
    "Premium": ("PA", "PREMIUM"), "Loss": ("PA", "LOSS"),
    "Record 150 - Premium": ("CA", "PREMIUM"), "Record 150 - Loss": ("CA", "LOSS"),
    "CP Premium": ("CP", "PREMIUM"), "CP Loss": ("CP", "LOSS"),
    "CGL Prem": ("GL", "PREMIUM"), "CGL Loss": ("GL", "LOSS"),
    "IM Prem": ("IM", "PREMIUM"), "IM Loss": ("IM", "LOSS"),
    "CR Prem": ("CR", "PREMIUM"), "CR Loss": ("CR", "LOSS"),
    "HO Prem": ("HO", "PREMIUM"), "HO Loss": ("HO", "LOSS"),
    "BOP Prem": ("BP", "PREMIUM"), "BOP Loss": ("BP", "LOSS"),
    "FD Prem": ("FI", "PREMIUM"), "FD Loss": ("FI", "LOSS"),
    "BR Prem": ("BR", "PREMIUM"), "BR Loss": ("BR", "LOSS"),
}

LOB_NAMES = {
    "PA": "Personal Auto", "CA": "Commercial Auto", "CP": "Commercial Property",
    "GL": "Commercial General Liability", "IM": "Inland Marine", "CR": "Commercial Crime",
    "HO": "Homeowners", "BP": "Businessowners (BOP)", "FI": "Fidelity & Forgery",
    "BR": "Builders Risk",
}


@dataclass
class LayoutField:
    seq: int
    name: str
    start: int
    length: int
    data_type: str
    description: str
    applicability: str = ""
    supplied_position: str = ""

    @property
    def end(self) -> int:
        return self.start + self.length - 1


@dataclass
class Layout:
    lob: str
    record_type: str
    source_file: str
    sheet: str
    fields: list[LayoutField] = field(default_factory=list)
    findings: list[str] = field(default_factory=list)


def _norm_type(t: str) -> str:
    """Collapse the supplied 'Data Type'/'Format' text to an engine format code."""
    t = (t or "").strip().lower()
    if "yymmdd" in t:
        return "YYMMDD"
    if "yymm" in t:
        return "YYMM"
    if "signed" in t:
        return "SIGNED"
    if t.startswith("numeric/alpha") or t.startswith("alpha/numeric") or "alphanumeric" in t:
        return "AN"
    if t.startswith("alpha"):
        return "A"
    return "N"


def _supplied_start(raw) -> int | None:
    if raw is None:
        return None
    if isinstance(raw, datetime):  # Excel turned "1-2" into 2026-01-02
        return raw.month
    if isinstance(raw, (int, float)):
        return int(raw)
    m = re.match(r"\s*(\d+)", str(raw))
    return int(m.group(1)) if m else None


def parse_workbook(path: Path) -> list[Layout]:
    wb = openpyxl.load_workbook(path, data_only=True)
    out = []
    for ws in wb.worksheets:
        if ws.title not in SHEET_MAP:
            continue
        lob, rt = SHEET_MAP[ws.title]
        lay = Layout(lob, rt, path.name, ws.title)
        rows = [r for r in ws.iter_rows(values_only=True) if any(c is not None for c in r)]
        hdr = [str(c or "").lower() for c in rows[0]]

        def col(*keys):
            for i, h in enumerate(hdr):
                if any(k in h for k in keys):
                    return i
            return None

        c_name = col("field name")
        c_pos = col("start pos", "position")
        c_len = col("length")
        c_type = col("data type", "format", "data format")
        c_app = col("applicab")
        c_desc = col("description")
        pos = 1
        for r in rows[1:]:
            if r[0] is None:
                continue
            length = int(float(r[c_len]))
            sup = _supplied_start(r[c_pos]) if c_pos is not None else None
            f = LayoutField(
                seq=int(float(r[0])), name=str(r[c_name]).strip(), start=pos, length=length,
                data_type=_norm_type(str(r[c_type] or "")),
                description=str(r[c_desc] or "").strip(),
                applicability=str(r[c_app] or "") if c_app is not None else "",
                supplied_position=str(r[c_pos]) if c_pos is not None else "",
            )
            if isinstance(r[c_pos], datetime):
                lay.findings.append(
                    f"Field {f.seq} '{f.name}': supplied position was converted to a date by Excel "
                    f"({r[c_pos]:%Y-%m-%d}); recomputed as {f.start}-{f.end}.")
            elif sup is not None and sup != pos:
                lay.findings.append(
                    f"Field {f.seq} '{f.name}': supplied start {sup} but lengths imply {pos}.")
            lay.fields.append(f)
            pos += length
        if pos - 1 != RECORD_LENGTH:
            lay.findings.append(f"Total record length is {pos-1}, expected {RECORD_LENGTH}.")
        out.append(lay)
    return out


def parse_all(folder: Path) -> list[Layout]:
    layouts = []
    for p in sorted(folder.glob("*.xlsx")):
        layouts.extend(parse_workbook(p))
    return layouts


if __name__ == "__main__":
    import sys
    for lay in parse_all(Path(sys.argv[1])):
        print(lay.lob, lay.record_type, len(lay.fields), "fields", lay.fields[-1].end)
        for f in lay.findings:
            print("   !", f)
