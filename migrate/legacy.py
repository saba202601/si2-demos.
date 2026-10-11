"""Read every kind of legacy source: COBOL copybooks + fixed-width data, DB tables, code tables,
PDF forms, free-text notes and COBOL program logic."""
from __future__ import annotations

import io
import re
from pathlib import Path

import pandas as pd

_HERE = Path(__file__).parent
SAMPLES = _HERE / "samples" if (_HERE / "samples" / "POLMAST.cpy").exists() else _HERE

PIC_LINE = re.compile(r"^\s*(\d{2})\s+([A-Z0-9-]+)(?:\s+PIC\s+([^\s.]+(?:\s+COMP-3)?))?(?:\s+OCCURS\s+(\d+)\s+TIMES)?\s*\.?\s*$", re.I)
VAL88 = re.compile(r"^\s*88\s+([A-Z0-9-]+)\s+VALUE\s+'?([^'.]*)'?\s*\.\s*$", re.I)


def _pic_len(pic: str) -> tuple[str, int, int, bool]:
    """Return (type, byte length, decimals, signed) for a PIC clause."""
    comp3 = "COMP-3" in pic.upper()
    p = pic.upper().replace("COMP-3", "").strip()
    signed = p.startswith("S")
    p = p.lstrip("S")
    expand = re.sub(r"([X9A])\((\d+)\)", lambda m: m.group(1) * int(m.group(2)), p)
    if "V" in expand:
        whole, dec = expand.split("V")
    else:
        whole, dec = expand, ""
    digits = len(whole) + len(dec)
    typ = "text" if "X" in expand or "A" in expand else ("decimal" if dec else "number")
    length = (digits // 2 + 1) if comp3 else digits
    return typ, length, len(dec), signed


def parse_copybook(text: str, name: str) -> pd.DataFrame:
    """Copybook -> one row per elementary field (OCCURS expanded), with 88-level values as pick lists."""
    nodes = []                                    # flat list: level, name, pic, occurs, pick_list
    for raw in text.splitlines():
        if len(raw) > 6 and raw[6:7] == "*":
            continue
        line = raw[6:72] if len(raw) > 6 else raw
        if not line.strip() or line.lstrip().startswith("*"):
            continue
        m88 = VAL88.match(line)
        if m88:
            if nodes:
                nodes[-1]["pick_list"][m88.group(2).strip()] = m88.group(1).upper()
            continue
        m = PIC_LINE.match(line)
        if m:
            nodes.append({"level": int(m.group(1)), "name": m.group(2).upper(), "pic": m.group(3),
                          "occurs": int(m.group(4) or 1), "pick_list": {}})

    rows, pos = [], 1

    def emit(i, occ_group="", occurrence=0):
        """Lay out node i (and its children); return index of next sibling."""
        nonlocal pos
        n = nodes[i]
        j = i + 1
        if n["pic"]:
            typ, length, dec, signed = _pic_len(n["pic"])
            rows.append({"record": name, "name": n["name"], "pic": n["pic"], "type": typ, "length": length,
                         "decimals": dec, "signed": signed, "start": pos, "end": pos + length - 1,
                         "occurrence": occurrence, "occurs_group": occ_group, "pick_list": n["pick_list"]})
            pos += length
            return j
        kids_end = j
        while kids_end < len(nodes) and nodes[kids_end]["level"] > n["level"]:
            kids_end += 1
        for k in range(1, n["occurs"] + 1):
            c = j
            while c < kids_end:
                c = emit(c, n["name"] if n["occurs"] > 1 else occ_group, k if n["occurs"] > 1 else occurrence)
        return kids_end

    i = 0
    while i < len(nodes):
        i = emit(i)
    return pd.DataFrame(rows)


def decode(layout: pd.DataFrame, data: str) -> tuple[pd.DataFrame, pd.DataFrame | None]:
    """Fixed-width data -> main table, plus a child table for OCCURS groups."""
    main_rows, child_rows = [], []
    scalar = layout[layout.occurrence == 0]
    occ = layout[layout.occurrence > 0]
    key_field = scalar.iloc[0]["name"]
    for line in data.splitlines():
        if not line.strip():
            continue
        rec = {}
        for f in scalar.itertuples():
            if f.name == "FILLER":
                continue
            rec[f.name] = _val(line[f.start - 1:f.end], f)
        main_rows.append(rec)
        if len(occ):
            count_field = next((c for c in rec if c.endswith("-CNT")), None)
            n = int(rec.get(count_field) or 0) if count_field else occ.occurrence.max()
            for i in range(1, int(n) + 1):
                child = {key_field: rec[key_field], "OCCURRENCE": i}
                for f in occ[occ.occurrence == i].itertuples():
                    child[f.name] = _val(line[f.start - 1:f.end], f)
                child_rows.append(child)
    child = pd.DataFrame(child_rows) if len(occ) else None
    return pd.DataFrame(main_rows), child


def _val(s, f):
    if f.type == "text":
        return s.strip()
    s = s.strip() or "0"
    try:
        n = int(s)
    except ValueError:
        return s
    return n / (10 ** f.decimals) if f.decimals else n


def read_pdf_forms(files: dict[str, bytes]) -> pd.DataFrame:
    """'Label: value' pairs from each form PDF -> one row per form."""
    import pypdf
    rows = []
    for name, data in files.items():
        text = "\n".join(p.extract_text() or "" for p in pypdf.PdfReader(io.BytesIO(data)).pages)
        row = {"FORM_FILE": name}
        for m in re.finditer(r"^([A-Z][A-Za-z ]{2,30}):\s*(.+?)\s*$", text, re.M):
            label, val = m.group(1).strip(), m.group(2).strip()
            if set(val) <= set("_ "):
                continue
            row[label] = val
        rows.append(row)
    return pd.DataFrame(rows)


AMT = re.compile(r"(?:estimate(?: of)?)\s*\$?([\d,]+)", re.I)


def read_notes(text: str) -> pd.DataFrame:
    """Claim notes -> structured elements: claim number, note date, author, estimate, attorney flag."""
    rows = []
    for line in text.splitlines():
        if not line.strip():
            continue
        parts = line.split("|", 3)
        if len(parts) < 4:
            continue
        clm, d, who, txt = parts
        m = AMT.search(txt)
        rows.append({"CLAIM NO": clm.strip(), "NOTE DATE": d.strip(), "AUTHOR": who.strip(), "NOTE TEXT": txt.strip(),
                     "REPAIR ESTIMATE": float(m.group(1).replace(",", "")) if m else None,
                     "ATTORNEY INVOLVED": "Y" if re.search(r"\battorney\b", txt, re.I) else "N"})
    return pd.DataFrame(rows)


def cobol_rules(text: str) -> list[dict]:
    """Find COMPUTE / IF rules in a COBOL program so the SME can see the business logic being tested."""
    rules = []
    para = ""
    for line in text.splitlines():
        body = line[6:72] if len(line) > 6 else line
        if re.match(r"^\s{0,4}[A-Z0-9-]+\.\s*$", body) and "DIVISION" not in body and "SECTION" not in body:
            para = body.strip(" .")
        if re.search(r"\b(COMPUTE|IF|MOVE)\b", body):
            rules.append({"paragraph": para, "statement": body.strip()})
    return rules


def earned_premium(written: float, eff, exp, val, cancelled: bool) -> float:
    """Python translation of INSURE/400 PREMCALC paragraph CALC-EARNED-PREM."""
    term = (exp - eff).days
    elapsed = min(max((val - eff).days, 0), term)
    if cancelled or term <= 0:
        return 0.0
    return round(written * elapsed / term, 2)


def raw_index(data: str, key_len: int = 10) -> dict:
    """Raw fixed-width line keyed by the record key in its first field."""
    return {line[:key_len].strip(): line for line in data.splitlines() if line.strip()}


def load_uploads(files: dict[str, bytes], fallback: dict | None = None) -> tuple[dict, list[str]]:
    """Classify uploaded files and read them like the demo system. Returns (sources, messages)."""
    msgs, ents, layouts = [], {}, {}
    by_stem = {}
    for name, data in files.items():
        by_stem.setdefault(Path(name).stem.upper(), {})[Path(name).suffix.lower()] = (name, data)
    code_table = program = dest_schema = dest_pl = None
    pdfs = {}
    used = set()
    for name, data in files.items():
        ext, stem = Path(name).suffix.lower(), Path(name).stem.upper()
        text = data.decode("utf-8", errors="replace") if ext != ".pdf" else ""
        if ext == ".pdf":
            pdfs[name] = data
        elif ext in (".cbl", ".cob") or "PROCEDURE DIVISION" in text.upper():
            program = text
            msgs.append(f"{name}: COBOL program ({len(cobol_rules(text))} business-rule statements)")
        elif ext == ".cpy":
            lay = parse_copybook(text, stem)
            data_file = next((by_stem[stem][e] for e in (".dat", ".txt") if e in by_stem.get(stem, {})), None)
            if data_file is None:
                msgs.append(f"{name}: copybook read ({len(lay)} fields) but no {stem}.dat data file was uploaded")
                continue
            used.add(data_file[0])
            raw = data_file[1].decode("utf-8", errors="replace")
            main, child = decode(lay, raw)
            layouts[stem] = lay
            key_len = int(lay.iloc[0].length)
            ents[stem] = {"type": "COBOL copybook + VSAM data", "df": main, "raw": raw_index(raw, key_len)}
            if child is not None:
                grp = lay[lay.occurrence > 0].occurs_group.iat[0]
                ents[f"{stem}.{grp}"] = {"type": "COBOL OCCURS group", "df": child}
            msgs.append(f"{name} + {data_file[0]}: {len(main)} records, {int(lay.end.max())}-byte layout")
        elif ext == ".csv":
            df = pd.read_csv(io.BytesIO(data), dtype=str)
            cols = {c.lower() for c in df.columns}
            if {"table_id", "code", "description"} <= cols:
                code_table = df.rename(columns=str.upper)
                msgs.append(f"{name}: code table ({df.iloc[:, 0].nunique()} lists)")
            elif {"table", "field", "type"} <= cols:
                dest_schema = df.fillna("")
                msgs.append(f"{name}: destination schema ({len(df)} fields)")
            elif {"pick_list", "code"} <= cols:
                dest_pl = df
                msgs.append(f"{name}: destination pick lists ({df.pick_list.nunique()} lists)")
            else:
                ents[stem] = {"type": "DB2 table", "df": df}
                msgs.append(f"{name}: database table, {len(df)} rows")
    for name, data in files.items():
        ext, stem = Path(name).suffix.lower(), Path(name).stem.upper()
        if ext == ".txt" and name not in used:
            text = data.decode("utf-8", errors="replace")
            notes = read_notes(text)
            if len(notes):
                ents[stem] = {"type": "Free-text notes", "df": notes}
                msgs.append(f"{name}: {len(notes)} notes")
    if pdfs:
        ents["POLICY_CHANGE_FORMS"] = {"type": "PDF forms", "df": read_pdf_forms(pdfs)}
        msgs.append(f"{len(pdfs)} PDF form(s) read")
    fb = fallback or {}
    if dest_schema is None and fb:
        dest_schema, dest_pl = fb["dest_schema"], fb["dest_picklists"]
        msgs.append("No destination schema uploaded: using the SI² demo cloud destination")
    return {"layouts": layouts, "entities": ents,
            "code_table": code_table if code_table is not None else pd.DataFrame(columns=["TABLE_ID", "CODE", "DESCRIPTION"]),
            "program": program or "", "dest_schema": dest_schema,
            "dest_picklists": dest_pl if dest_pl is not None else pd.DataFrame(columns=["pick_list", "code", "description"])}, msgs


def load_samples() -> dict:
    """The demo legacy system INSURE/400."""
    s = SAMPLES
    pol_lay = parse_copybook((s / "POLMAST.cpy").read_text(), "POLMAST")
    clm_lay = parse_copybook((s / "CLMMAST.cpy").read_text(), "CLMMAST")
    pol_raw, clm_raw = (s / "POLMAST.dat").read_text(), (s / "CLMMAST.dat").read_text()
    pol, _ = decode(pol_lay, pol_raw)
    clm, pay = decode(clm_lay, clm_raw)
    forms = read_pdf_forms({p.name: p.read_bytes() for p in sorted(((s / "forms") if (s / "forms").is_dir() else s).glob("*.pdf"))})
    return {
        "layouts": {"POLMAST": pol_lay, "CLMMAST": clm_lay},
        "entities": {
            "POLMAST": {"type": "COBOL copybook + VSAM data", "df": pol, "raw": raw_index(pol_raw)},
            "CLMMAST": {"type": "COBOL copybook + VSAM data", "df": clm, "raw": raw_index(clm_raw)},
            "CLMMAST.CL-PAYMENT": {"type": "COBOL OCCURS group", "df": pay},
            "AGENT": {"type": "DB2 table", "df": pd.read_csv(s / "AGENT.csv", dtype=str)},
            "COVERAGE": {"type": "DB2 table", "df": pd.read_csv(s / "COVERAGE.csv", dtype=str)},
            "POLICY_CHANGE_FORMS": {"type": "PDF forms", "df": forms},
            "CLAIM_NOTES": {"type": "Free-text notes", "df": read_notes((s / "CLAIM_NOTES.txt").read_text())},
        },
        "code_table": pd.read_csv(s / "CODE_TABLE.csv", dtype=str),
        "program": (s / "PREMCALC.cbl").read_text(),
        "dest_schema": pd.read_csv(s / "destination_schema.csv", dtype=str).fillna(""),
        "dest_picklists": pd.read_csv(s / "destination_picklists.csv", dtype=str),
    }
