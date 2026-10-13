"""Collect data elements, pick lists, options, synonyms and rules from the other databases on the server and
propose what SI2Canonical does not have yet (single entry, single meaning).

    python collect_si2_databases.py --dry-run                 show what would be proposed, write nothing
    python collect_si2_databases.py                           propose (change requests from 'SI2 collector')
    python collect_si2_databases.py --approve-as "Saba"       propose and approve as the second person

Sources (each read only if it exists on the server; nothing in them is changed):
    RuleEngine           dbo.DataElement / DataElementAlias / PickList / PickListOption / PickListAlias / PickListOptionAlias / Rule
    BureauReporting      ref.DataElement / DataElementAlias / PickList / PickListOption / PickListAlias / PickListOptionAlias, rul.BureauRule
    ISOBureauReporting   dbo.canonical_element / element_alias / picklist / picklist_option / picklist_alias / picklist_option_alias /
                         bureau_code_map / business_rule
Every database on the server can also be scanned column by column with intake.usp_ScanDatabase (--scan-all).
Options: --server (default SABAHOME\\SQLEXPRESS02 or SI2_MSSQL_SERVER)  --database SI2Canonical  --only RuleEngine,...
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
COLLECTOR = "SI2 collector"
ORDER = {"PICKLIST": 1, "OPTION": 2, "ELEMENT": 3, "SYNONYM": 4, "BUREAU_CODE": 5, "RULESET": 6, "RULE": 7}


# ------------------------------------------------------------------------------------------ text helpers
def norm(s) -> str:
    return re.sub(r"[ _\-./]", "", str(s or "")).upper()


def snake(s) -> str:
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", str(s or ""))
    s = re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_").upper()
    return re.sub(r"_+", "_", s)


def short_code(s: str, n: int) -> str:
    s = str(s)
    return s if len(s) <= n else s[: n - 7] + "~" + hashlib.md5(s.encode()).hexdigest()[:6].upper()


def clean(v):
    if v is None:
        return None
    v = str(v).strip()
    return v or None


PREFIXES = re.compile(r"^(GLOBAL[._]|DE_|CDM[._]|CN_|GW_)", re.I)
LIST_SUFFIX = re.compile(r"(?i)[ _]?(options?|picklist|pick list|list|codes?|values|lov)$")


def variants(*texts, picklist: bool = False) -> list[str]:
    """Ways a name may appear: as is, without a GLOBAL. / DE_ prefix, its last dotted part, and for lists without 'Options' / 'Code'."""
    out = []
    for t in texts:
        t = clean(t)
        if not t:
            continue
        cands = [t, PREFIXES.sub("", t)]
        if "." in t:
            cands.append(t.split(".")[-1])
        if picklist:
            cands += [LIST_SUFFIX.sub("", c) for c in list(cands)]
        for c in cands:
            if c and c not in out:
                out.append(c)
    return out


def good_text(s, name=None, n: int = 12) -> bool:
    s = clean(s)
    return bool(s) and len(s) >= n and norm(s) != norm(name) and s.lower() not in ("none", "nan", "tbd", "null")


CLEAN_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9 _./&()#%'-]{1,119}$")


def clean_name(s) -> bool:
    return bool(s) and bool(CLEAN_NAME.match(str(s).strip())) and "(e.g" not in str(s)


DTYPES = {"text": "TEXT", "string": "TEXT", "an": "TEXT", "integer": "INTEGER", "int": "INTEGER", "number": "DECIMAL", "n": "DECIMAL",
          "decimal": "DECIMAL", "currency": "AMOUNT", "amount": "AMOUNT", "amt": "AMOUNT", "money": "AMOUNT", "percent": "PERCENT",
          "date": "DATE", "d": "DATE", "datetime": "DATETIME", "pick list": "CODE", "picklist": "CODE", "code": "CODE", "boolean": "BOOLEAN"}


def dtype(v, has_picklist: bool) -> str:
    return "CODE" if has_picklist else DTYPES.get(str(v or "").strip().lower(), "TEXT")


# ------------------------------------------------------------------------------------------ catalog model
def new_catalog(source: str) -> dict:
    return {"source": source, "picklists": {}, "elements": {}, "rules": [], "bureau_codes": []}


def add_picklist(cat, key, code=None, name=None, desc=None, library="COMPANY", element=None):
    pl = cat["picklists"].setdefault(key, {"code": clean(code), "name": clean(name), "desc": clean(desc), "library": library,
                                           "aliases": [], "options": {}, "element": clean(element)})
    return pl


def add_option(pl, code, name=None, desc=None):
    code = clean(code)
    if code is None:
        return None
    return pl["options"].setdefault(code.upper(), {"code": code, "name": clean(name) or code, "desc": clean(desc), "aliases": []})


# ------------------------------------------------------------------------------------------ database readers
class Reader:
    def __init__(self, con, db: str, label: str | None = None):
        self.con, self.db, self.label = con, db, label or db

    def exists(self) -> bool:
        return self.one("SELECT DB_ID(?) AS x", self.db) is not None

    def one(self, sql, *p):
        cur = self.con.cursor()
        cur.execute(sql, *p)
        r = cur.fetchone()
        return r[0] if r else None

    def cols(self, schema, table) -> set:
        cur = self.con.cursor()
        cur.execute(f"SELECT COLUMN_NAME FROM [{self.db}].INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = ? AND TABLE_NAME = ?", schema, table)
        return {r[0].lower() for r in cur.fetchall()}

    def rows(self, schema, table, want: list[str], where_current: str | None = None) -> list[dict]:
        """SELECT the wanted columns that exist (missing ones come back as None); current rows only when the date column exists."""
        have = self.cols(schema, table)
        if not have:
            return []
        sel = [f"[{c}]" if c.lower() in have else f"NULL AS [{c}]" for c in want]
        sql = f"SELECT {', '.join(sel)} FROM [{self.db}].[{schema}].[{table}]"
        if where_current and where_current.lower() in have:
            sql += f" WHERE [{where_current}] IS NULL OR [{where_current}] >= CAST(GETDATE() AS date)"
        cur = self.con.cursor()
        cur.execute(sql)
        return [dict(zip(want, r)) for r in cur.fetchall()]


def read_rule_engine(r: Reader) -> dict:
    cat = new_catalog(r.label)
    pls = {}
    for p in r.rows("dbo", "PickList", ["PickListID", "PickListName", "Description"], "ExpirationDate"):
        pls[p["PickListID"]] = add_picklist(cat, f"RE:{p['PickListID']}", snake(p["PickListName"]), p["PickListName"], p["Description"])
    opts = {}
    for o in r.rows("dbo", "PickListOption", ["OptionID", "PickListID", "OptionCode", "OptionName"], "ExpirationDate"):
        pl = pls.get(o["PickListID"])
        if pl:
            opts[o["OptionID"]] = add_option(pl, o["OptionCode"], o["OptionName"])
    for a in r.rows("dbo", "PickListAlias", ["PickListID", "Alias", "AliasSourceSystem"], "ExpirationDate"):
        if a["PickListID"] in pls and clean(a["Alias"]):
            pls[a["PickListID"]]["aliases"].append((clean(a["Alias"]), clean(a["AliasSourceSystem"]) or r.label))
    for a in r.rows("dbo", "PickListOptionAlias", ["OptionID", "AliasCode", "AliasName", "AliasSourceSystem"], "ExpirationDate"):
        o = opts.get(a["OptionID"])
        if o:
            for v in (a["AliasCode"], a["AliasName"]):
                if clean(v):
                    o["aliases"].append((clean(v), clean(a["AliasSourceSystem"]) or r.label))
    for d in r.rows("dbo", "DataElement", ["DataElementID", "DataElementName", "BusinessDefinition", "Module", "DataType", "PickListID", "Mandatory"],
                    "ExpirationDate"):
        pl = pls.get(d["PickListID"])
        cat["elements"][f"RE:{d['DataElementID']}"] = {
            "code": snake(d["DataElementName"]), "name": clean(d["DataElementName"]), "desc": clean(d["BusinessDefinition"]),
            "dtype": dtype(d["DataType"], pl is not None), "picklist_key": f"RE:{d['PickListID']}" if pl else None,
            "aliases": [(str(d["DataElementID"]), r.label)], "module": clean(d["Module"]), "curated": True}
    for a in r.rows("dbo", "DataElementAlias", ["DataElementID", "Alias", "AliasSourceSystem"], "ExpirationDate"):
        e = cat["elements"].get(f"RE:{a['DataElementID']}")
        if e and clean(a["Alias"]):
            e["aliases"].append((clean(a["Alias"]), clean(a["AliasSourceSystem"]) or r.label))
    for x in r.rows("dbo", "Rule", ["RuleID", "State", "Product", "Module", "SubModule", "BusinessRule", "RuleJSON", "EffectiveDate", "Status"],
                    "ExpirationDate"):
        if "reject" in str(x["Status"] or "").lower():
            continue
        try:
            spec = json.loads(x["RuleJSON"]) if x["RuleJSON"] else {}
        except ValueError:
            spec = {}
        cat["rules"].append({"kind": "RE", "code": clean(x["RuleID"]), "name": (clean(x["BusinessRule"]) or x["RuleID"])[:200],
                             "desc": clean(x["BusinessRule"]), "module": clean(x["Module"]) or "Other", "sub": clean(x["SubModule"]),
                             "state": clean(x["State"]) or "*", "lob": clean(x["Product"]) or "*", "spec": spec,
                             "effective": str(x["EffectiveDate"])[:10] if x["EffectiveDate"] else None})
    return cat


def read_bureau_reporting(r: Reader) -> dict:
    cat = new_catalog(r.label)
    for p in r.rows("ref", "PickList", ["PickListCode", "PickListName", "Description", "OwnerBureauCode"], "ExpirationDate"):
        add_picklist(cat, f"BR:{p['PickListCode']}", p["PickListCode"], p["PickListName"], p["Description"],
                     clean(p["OwnerBureauCode"]) or "BUREAU")
    for o in r.rows("ref", "PickListOption", ["PickListCode", "OptionCode", "OptionName"], "ExpirationDate"):
        pl = cat["picklists"].get(f"BR:{o['PickListCode']}")
        if pl:
            add_option(pl, o["OptionCode"], o["OptionName"])
    for a in r.rows("ref", "PickListAlias", ["PickListCode", "AliasName", "SourceSystemCode"], "ExpirationDate"):
        pl = cat["picklists"].get(f"BR:{a['PickListCode']}")
        if pl and clean(a["AliasName"]):
            pl["aliases"].append((clean(a["AliasName"]), clean(a["SourceSystemCode"]) or r.label))
    for a in r.rows("ref", "PickListOptionAlias", ["PickListCode", "OptionCode", "AliasValue", "SourceSystemCode"], "ExpirationDate"):
        pl = cat["picklists"].get(f"BR:{a['PickListCode']}")
        o = pl["options"].get(str(a["OptionCode"]).upper()) if pl and a["OptionCode"] else None
        if o and clean(a["AliasValue"]):
            o["aliases"].append((clean(a["AliasValue"]), clean(a["SourceSystemCode"]) or r.label))
    for d in r.rows("ref", "DataElement", ["ElementCode", "ElementName", "BusinessDefinition", "DataType", "PickListCode", "CanonicalElementName",
                                           "BureauFieldRef", "LayoutCode", "IsFiller"], "ExpirationDate"):
        if d["IsFiller"] in (1, True):
            continue
        key = f"BR:{d['ElementCode']}"
        e = cat["elements"].setdefault(key, {
            "code": snake(d["ElementCode"]), "name": clean(d["ElementName"]), "desc": clean(d["BusinessDefinition"]),
            "dtype": dtype(d["DataType"], bool(d["PickListCode"])), "picklist_key": f"BR:{d['PickListCode']}" if d["PickListCode"] else None,
            "aliases": [], "bureau": True, "curated": True})
        for v in (d["CanonicalElementName"], d["BureauFieldRef"]):
            if clean(v) and not re.fullmatch(r"\d+", str(v).strip()):
                e["aliases"].append((clean(v), r.label))
    for a in r.rows("ref", "DataElementAlias", ["ElementCode", "AliasName", "SourceSystemCode"], "ExpirationDate"):
        e = cat["elements"].get(f"BR:{a['ElementCode']}")
        if e and clean(a["AliasName"]):
            e["aliases"].append((clean(a["AliasName"]), clean(a["SourceSystemCode"]) or r.label))
    for x in r.rows("rul", "BureauRule", ["RuleCode", "ReportTypeCode", "LayoutCode", "ElementCode", "RuleType", "Severity", "BureauEditCode",
                                          "RuleParamsJson", "SqlPredicate", "Message", "EffectiveDate"], "ExpirationDate"):
        cat["rules"].append({"kind": "BR", "code": clean(x["RuleCode"]), "name": (clean(x["Message"]) or x["RuleCode"])[:200],
                             "desc": clean(x["Message"]), "element_key": f"BR:{x['ElementCode']}" if x["ElementCode"] else None,
                             "severity": "WARNING" if str(x["Severity"]).lower().startswith("warn") else "ERROR",
                             "condition_text": clean(x["SqlPredicate"]) or f"{x['RuleType']} {x['RuleParamsJson'] or ''}".strip(),
                             "spec": {"report": x["ReportTypeCode"], "layout": x["LayoutCode"], "element": x["ElementCode"], "rule_type": x["RuleType"],
                                      "params": json.loads(x["RuleParamsJson"]) if x["RuleParamsJson"] else None, "sql": x["SqlPredicate"],
                                      "bureau_edit": x["BureauEditCode"]},
                             "effective": str(x["EffectiveDate"])[:10] if x["EffectiveDate"] else None})
    return cat


def read_iso(r: Reader) -> dict:
    cat = new_catalog(r.label)
    keep = lambda row: "reject" not in str(row.get("status") or "").lower()  # noqa: E731
    for p in r.rows("dbo", "picklist", ["picklist_code", "picklist_name", "business_description", "status"], "exp_date"):
        if keep(p):
            add_picklist(cat, f"ISO:{p['picklist_code']}", p["picklist_code"], p["picklist_name"], p["business_description"], "ISO")
    for o in r.rows("dbo", "picklist_option", ["picklist_code", "option_code", "option_name", "business_description", "status"], "exp_date"):
        pl = cat["picklists"].get(f"ISO:{o['picklist_code']}")
        if pl and keep(o):
            add_option(pl, o["option_code"], o["option_name"], o["business_description"])
    for a in r.rows("dbo", "picklist_alias", ["picklist_code", "alias_name", "alias_context", "status"], "exp_date"):
        pl = cat["picklists"].get(f"ISO:{a['picklist_code']}")
        if pl and keep(a) and clean(a["alias_name"]):
            pl["aliases"].append((clean(a["alias_name"]), (clean(a["alias_context"]) or r.label).split(":")[-1]))
    for a in r.rows("dbo", "picklist_option_alias", ["picklist_code", "option_code", "source_system", "source_value", "status"], "exp_date"):
        pl = cat["picklists"].get(f"ISO:{a['picklist_code']}")
        o = pl["options"].get(str(a["option_code"]).upper()) if pl and a["option_code"] else None
        if o and keep(a) and clean(a["source_value"]):
            o["aliases"].append((clean(a["source_value"]), clean(a["source_system"]) or r.label))
    for b in r.rows("dbo", "bureau_code_map", ["bureau_code", "picklist_code", "option_code", "bureau_value", "status"], "exp_date"):
        if keep(b) and clean(b["bureau_value"]):
            cat["bureau_codes"].append((f"ISO:{b['picklist_code']}", clean(b["option_code"]), clean(b["bureau_code"]) or "ISO", clean(b["bureau_value"])))
    for d in r.rows("dbo", "canonical_element", ["element_code", "element_name", "business_description", "data_type", "picklist_code", "status"],
                    "exp_date"):
        if keep(d):
            cat["elements"][f"ISO:{d['element_code']}"] = {
                "code": snake(d["element_code"]), "name": clean(d["element_name"]), "desc": clean(d["business_description"]),
                "dtype": dtype(d["data_type"], bool(d["picklist_code"])), "picklist_key": f"ISO:{d['picklist_code']}" if d["picklist_code"] else None,
                "aliases": [], "bureau": True, "curated": True}
    for a in r.rows("dbo", "element_alias", ["element_code", "alias_name", "alias_context", "status"], "exp_date"):
        e = cat["elements"].get(f"ISO:{a['element_code']}")
        if e and keep(a) and clean(a["alias_name"]):
            e["aliases"].append((clean(a["alias_name"]), (clean(a["alias_context"]) or r.label).split(":")[-1]))
    for x in r.rows("dbo", "business_rule", ["rule_code", "rule_name", "rule_category", "lob_scope", "state_scope", "element_code", "expression_json",
                                             "severity", "message", "business_description", "eff_date", "status"], "exp_date"):
        if keep(x):
            try:
                spec = json.loads(x["expression_json"]) if x["expression_json"] else {}
            except ValueError:
                spec = {}
            cat["rules"].append({"kind": "ISO", "code": clean(x["rule_code"]), "name": clean(x["rule_name"]) or x["rule_code"],
                                 "desc": clean(x["business_description"]), "category": clean(x["rule_category"]), "lob": clean(x["lob_scope"]) or "*",
                                 "state": clean(x["state_scope"]) or "*", "element_key": f"ISO:{x['element_code']}" if x["element_code"] else None,
                                 "severity": (clean(x["severity"]) or "ERROR").upper(), "message": clean(x["message"]), "spec": spec,
                                 "effective": str(x["eff_date"])[:10] if x["eff_date"] else None})
    return cat


# ------------------------------------------------------------------------------------------ prior-version knowledge stores
def split_list(v) -> list[str]:
    """'a, b' or '["a","b"]' -> ['a', 'b']."""
    v = clean(v)
    if not v:
        return []
    if v.startswith("["):
        try:
            return [clean(x) for x in json.loads(v) if clean(x)]
        except ValueError:
            pass
    return [clean(x) for x in re.split(r"[,;|]", v) if clean(x)]


def active(row, col="IsActive") -> bool:
    return row.get(col) not in (0, False)


def read_cdm_model(r: Reader) -> dict:
    """cdm.DataElement / DataElementSynonym / PickList / PickListOption / PickListSynonym / PickListOptionSynonym + rules (NeurologyInsurance)."""
    cat = new_catalog(r.label)
    pls = {}
    for p in r.rows("cdm", "PickList", ["PickListID", "PickListName", "Description", "PickListCode"]):
        pls[p["PickListID"]] = add_picklist(cat, f"PL:{p['PickListID']}", p["PickListCode"], p["PickListName"], p["Description"])
        pls[p["PickListID"]]["aliases"].append((p["PickListName"], r.label))
    for a in r.rows("cdm", "PickListSynonym", ["PickListID", "Synonym", "SourceSystem", "IsActive"]):
        if a["PickListID"] in pls and active(a) and clean(a["Synonym"]):
            pls[a["PickListID"]]["aliases"].append((clean(a["Synonym"]), clean(a["SourceSystem"]) or r.label))
    opts = {}
    for o in r.rows("cdm", "PickListOption", ["PickListOptionID", "PickListID", "OptionCode", "OptionLabel", "IsActive"]):
        if o["PickListID"] in pls and active(o):
            opts[o["PickListOptionID"]] = add_option(pls[o["PickListID"]], o["OptionCode"], o["OptionLabel"])
    for a in r.rows("cdm", "PickListOptionSynonym", ["PickListOptionID", "Synonym", "SourceSystem", "IsActive"]):
        o = opts.get(a["PickListOptionID"])
        if o and active(a) and clean(a["Synonym"]):
            o["aliases"].append((clean(a["Synonym"]), clean(a["SourceSystem"]) or r.label))
    by_name = {norm(p["name"]): k for k, p in cat["picklists"].items()}
    for d in r.rows("cdm", "DataElement", ["DataElementID", "CanonicalName", "BusinessDefinition", "DataType", "DomainName", "IsPicklist",
                                           "IsSensitive", "DataElementCode", "SubjectArea", "IsActive"]):
        if not active(d) or not clean_name(d["CanonicalName"]):
            continue
        name = d["CanonicalName"]
        pk = by_name.get(norm(d["DomainName"])) if d["DomainName"] else None
        cat["elements"][f"DE:{d['DataElementID']}"] = {
            "code": snake(name.replace(".", "_")), "name": name.split(".")[-1] if name.count(".") == 1 else name,
            "desc": clean(d["BusinessDefinition"]), "dtype": dtype(d["DataType"], pk is not None), "picklist_key": pk,
            "aliases": [(name, r.label)] + ([(d["DataElementCode"], r.label)] if clean(d["DataElementCode"]) and d["DataElementCode"] != name else []),
            "pii": bool(d["IsSensitive"]), "curated": True}
    for a in r.rows("cdm", "DataElementSynonym", ["DataElementID", "Synonym", "SourceSystem", "IsActive"]):
        e = cat["elements"].get(f"DE:{a['DataElementID']}")
        if e and active(a) and clean(a["Synonym"]):
            e["aliases"].append((clean(a["Synonym"]), clean(a["SourceSystem"]) or r.label))
    for x in r.rows("cdm", "Rule_Master", ["RuleID", "RuleName", "RuleDescription", "RuleCategory", "Severity", "IsActive", "EffectiveDate"],
                    "ExpirationDate"):
        if active(x) and clean(x["RuleName"]):
            cat["rules"].append({"kind": "GEN", "code": f"RM-{x['RuleID']}", "name": clean(x["RuleName"])[:200], "desc": clean(x["RuleDescription"]),
                                 "category": clean(x["RuleCategory"]) or "Other", "severity": clean(x["Severity"]), "spec": {"source_rule_id": x["RuleID"]},
                                 "effective": str(x["EffectiveDate"])[:10] if x["EffectiveDate"] else None})
    conds = defaultdict(list)
    for c in r.rows("cdm", "Rule_Condition", ["RuleID", "ConditionJSON"]):
        conds[c["RuleID"]].append(c["ConditionJSON"])
    acts = defaultdict(list)
    for c in r.rows("cdm", "Rule_Action", ["RuleID", "ActionJSON"]):
        acts[c["RuleID"]].append(c["ActionJSON"])
    for x in cat["rules"]:
        rid = x["spec"]["source_rule_id"]
        x["spec"].update({"conditions": [_json(c) for c in conds.get(rid, [])], "actions": [_json(a) for a in acts.get(rid, [])]})
    for x in r.rows("cdm", "BusinessRule", ["BusinessRuleID", "RuleName", "RuleType", "Severity", "RuleExpression", "IsActive", "EffectiveDate",
                                            "Comments"], "ExpirationDate"):
        if active(x) and clean(x["RuleName"]):
            cat["rules"].append({"kind": "GEN", "code": f"BR-{x['BusinessRuleID']}", "name": clean(x["RuleName"])[:200],
                                 "desc": clean(x["Comments"]), "category": clean(x["RuleType"]) or "Rating", "severity": clean(x["Severity"]),
                                 "condition_text": clean(x["RuleExpression"]), "spec": {"expression": x["RuleExpression"]},
                                 "effective": str(x["EffectiveDate"])[:10] if x["EffectiveDate"] else None})
    return cat


def _json(v):
    try:
        return json.loads(v) if v else None
    except ValueError:
        return v


def read_canonical_hub(r: Reader) -> dict:
    """PnC_CanonicalHub: cdm.DataElement (5,600), cdm.PickListOptions (3,800) with ISO / NCCI codes, syn.* synonyms, cdm.Peril."""
    cat = new_catalog(r.label)
    els = {}
    for d in r.rows("cdm", "DataElement", ["DataElementID", "GlobalName", "DataElementName", "BusinessDefinition", "Description", "DataType",
                                           "IsPickListApplicable", "PickListName", "BusinessName", "Status", "IsAnonymizationSensitive"], "ExpirationDate"):
        name = clean(d["BusinessName"]) or clean(d["DataElementName"]) or clean(d["GlobalName"])
        if not clean_name(d["GlobalName"]) or not clean_name(name) or str(d["Status"] or "").upper() in ("REJECTED", "RETIRED", "DEPRECATED"):
            continue
        desc = d["BusinessDefinition"] if good_text(d["BusinessDefinition"], name) else d["Description"]
        e = {"code": snake(d["GlobalName"]), "name": name, "desc": clean(desc), "dtype": dtype(d["DataType"], False), "picklist_key": None,
             "aliases": [(d["GlobalName"], r.label)] + ([(d["DataElementName"], r.label)] if clean(d["DataElementName"]) else []),
             "pii": bool(d["IsAnonymizationSensitive"])}
        els[d["DataElementID"]] = e
        cat["elements"][f"DE:{d['DataElementID']}"] = e
        if d["IsPickListApplicable"] in (1, True):
            pl = add_picklist(cat, f"PL:{d['DataElementID']}", clean(d["PickListName"]) or d["GlobalName"], clean(d["PickListName"]) or name,
                              element=name)
            e["picklist_key"] = f"PL:{d['DataElementID']}"
            e["dtype"] = "CODE"
    opts = {}
    for o in r.rows("cdm", "PickListOptions", ["PickListOptionID", "DataElementID", "PickListOptionCode", "PickListOptionName", "DisplayLabel",
                                               "OptionDefinition", "ISOCode", "NCCICode", "IsActive"], "ExpirationDate"):
        pl = cat["picklists"].get(f"PL:{o['DataElementID']}")
        if not pl:
            e = els.get(o["DataElementID"])
            if not e:
                continue
            pl = add_picklist(cat, f"PL:{o['DataElementID']}", e["code"], e["name"], element=e["name"])
            e["picklist_key"] = f"PL:{o['DataElementID']}"
        if not active(o):
            continue
        opt = add_option(pl, o["PickListOptionCode"], clean(o["PickListOptionName"]) or clean(o["DisplayLabel"]), o["OptionDefinition"])
        if opt:
            opts[o["PickListOptionID"]] = (pl, opt)
            if clean(o["DisplayLabel"]) and norm(o["DisplayLabel"]) != norm(opt["name"]):
                opt["aliases"].append((clean(o["DisplayLabel"]), r.label))
            for bureau, code in (("ISO", o["ISOCode"]), ("NCCI", o["NCCICode"])):
                if clean(code):
                    cat["bureau_codes"].append((f"PL:{o['DataElementID']}", opt["code"], bureau, clean(code)[:30]))
    auto = lambda a: str(a.get("Source") or "").upper() == "RULE" or "auto" in str(a.get("Comments") or "").lower()  # noqa: E731
    for a in r.rows("syn", "DataElementSynonyms", ["DataElementID", "Synonym", "Source", "IsActive", "Comments", "Status"], "ExpirationDate"):
        e = els.get(a["DataElementID"])
        if e and active(a) and not auto(a) and clean(a["Synonym"]):
            e["aliases"].append((clean(a["Synonym"]), clean(a["Source"]) or r.label))
    for a in r.rows("cdm", "DataElement_Synonym", ["DataElementID", "SynonymLabel", "IsActive"], "ExpirationDate"):
        e = els.get(a["DataElementID"])
        if e and active(a) and clean(a["SynonymLabel"]):
            e["aliases"].append((clean(a["SynonymLabel"]), r.label))
    for a in r.rows("syn", "PickListSynonyms", ["PickListOptionID", "Synonym", "Source", "IsActive", "Comments", "Status"], "ExpirationDate"):
        po = opts.get(a["PickListOptionID"])
        if po and active(a) and not auto(a) and clean(a["Synonym"]):
            po[1]["aliases"].append((clean(a["Synonym"]), clean(a["Source"]) or r.label))
    for tbl, col in (("PickList_Option_Synonym", "SynonymLabel"), ("PickList_Synonym", "Synonym")):
        for a in r.rows("cdm", tbl, ["PickListOptionID", col]):
            po = opts.get(a["PickListOptionID"])
            if po and clean(a[col]) and "sample" not in str(a[col]).lower():
                po[1]["aliases"].append((clean(a[col]), r.label))
    peril = add_picklist(cat, "PERIL", "PERIL", "Peril", "Perils (causes of loss) used in coverage definitions.")
    for p in r.rows("cdm", "Peril", ["PerilCode", "PerilName", "IsActive"]):
        if active(p):
            add_option(peril, p["PerilCode"], p["PerilName"])
    return cat


def read_semantic_hub(r: Reader) -> dict:
    """SemanticMappingHub: GlobalDataElementRegistry (5,200) and GlobalPickListInsurance (4,400) with ISO / NCCI codes and synonyms."""
    cat = new_catalog(r.label)
    for d in r.rows("dbo", "GlobalDataElementRegistry", ["Data_Element_Name", "Synonyms", "Business_Definition", "Business_Description",
                                                         "Data_Type", "Pick_List_Is_Applicable", "Pick_List_Name", "SuggestedSynonyms"], "ExpirationDate"):
        name = clean(d["Data_Element_Name"])
        if not clean_name(name):
            continue
        key = f"DE:{norm(name)}"
        e = cat["elements"].setdefault(key, {"code": snake(name), "name": name, "desc": None, "dtype": dtype(d["Data_Type"], False),
                                             "picklist_key": None, "aliases": []})
        for t in (d["Business_Definition"], d["Business_Description"]):
            if not e["desc"] and good_text(t, name):
                e["desc"] = clean(t)
        e["aliases"] += [(a, r.label) for a in split_list(d["Synonyms"])]
        if d["Pick_List_Is_Applicable"] in (1, True) and clean(d["Pick_List_Name"]):
            e["picklist_key"] = f"PL:{norm(d['Pick_List_Name'])}"
            e["dtype"] = "CODE"
    for o in r.rows("dbo", "GlobalPickListInsurance", ["Data_Element_Name", "PickOptionCode", "PickListOption_Name", "DisplayLabel_EN",
                                                       "Option_Definition", "ISO_Code", "NCCI_Code", "Synonyms", "IsDeprecated"], "ExpirationDate"):
        if o["IsDeprecated"] in (1, True) or not clean(o["Data_Element_Name"]):
            continue
        key = f"PL:{norm(o['Data_Element_Name'])}"
        pl = add_picklist(cat, key, o["Data_Element_Name"], o["Data_Element_Name"], element=LIST_SUFFIX.sub("", o["Data_Element_Name"]))
        label = clean(o["DisplayLabel_EN"]) or clean(o["PickListOption_Name"])
        if label and "." in label and " " not in label:          # 'CoverageType.BI' style names carry no label
            label = None
        opt = add_option(pl, o["PickOptionCode"], label or o["PickOptionCode"], o["Option_Definition"])
        if not opt:
            continue
        opt["aliases"] += [(a, r.label) for a in split_list(o["Synonyms"])]
        for bureau, code in (("ISO", o["ISO_Code"]), ("NCCI", o["NCCI_Code"])):
            if clean(code):
                cat["bureau_codes"].append((key, opt["code"], bureau, clean(code)[:30]))
    st = add_picklist(cat, "STATE", "STATE", "State")
    for j in r.rows("dbo", "GlobalJurisdictionRegistry", ["JurisdictionCodeAlpha", "JurisdictionCodeNumeric", "JurisdictionName", "IsActive"]):
        if active(j) and clean(j["JurisdictionCodeAlpha"]):
            o = add_option(st, j["JurisdictionCodeAlpha"], j["JurisdictionName"])
            if clean(j["JurisdictionCodeNumeric"]):
                o["aliases"].append((clean(j["JurisdictionCodeNumeric"]), r.label))
    return cat


def read_ai_mapping(r: Reader) -> dict:
    """AIMapping: CanonicalDataElements_Staging and CanonicalPicklistOptions_Staging (curated), DataElements (definitions only)."""
    cat = new_catalog(r.label)
    for d in r.rows("dbo", "CanonicalDataElements_Staging", ["Data_Element_Name", "Business_Definition", "Data_Type", "IsPII",
                                                              "Pick_List_Is_Applicable", "Pick_List_Name", "Comments"]):
        name = clean(d["Data_Element_Name"])
        if clean_name(name):
            pk = f"PL:{norm(d['Pick_List_Name'])}" if str(d["Pick_List_Is_Applicable"]) in ("1", "True", "Y") and clean(d["Pick_List_Name"]) else None
            cat["elements"][f"DE:{norm(name)}"] = {"code": snake(name), "name": name, "desc": clean(d["Business_Definition"]),
                                                   "dtype": dtype(d["Data_Type"], pk is not None), "picklist_key": pk, "aliases": [],
                                                   "pii": str(d["IsPII"]) in ("1", "True"), "curated": True}
    for o in r.rows("dbo", "CanonicalPicklistOptions_Staging", ["Pick_List_Name", "Option_Code", "Option_Label", "Option_Definition",
                                                                "StandardName_From_CSV", "Alias_Labels", "Is_Active"]):
        if o["Is_Active"] in (0, False) or not clean(o["Pick_List_Name"]):
            continue
        pl = add_picklist(cat, f"PL:{norm(o['Pick_List_Name'])}", o["Pick_List_Name"], clean(o["StandardName_From_CSV"]) or o["Pick_List_Name"],
                          element=o["StandardName_From_CSV"])
        if clean(o["StandardName_From_CSV"]):
            pl["aliases"].append((o["Pick_List_Name"], r.label))
        opt = add_option(pl, o["Option_Code"] if not re.fullmatch(r"\d+", str(o["Option_Code"] or "")) else snake(o["Option_Label"]),
                         o["Option_Label"], o["Option_Definition"])
        if opt:
            if re.fullmatch(r"\d+", str(o["Option_Code"] or "")):
                opt["aliases"].append((str(o["Option_Code"]), r.label))
            opt["aliases"] += [(a, r.label) for a in split_list(o["Alias_Labels"])]
    for d in r.rows("dbo", "DataElements", ["Data Element Name", "Business_Definition", "Business_Description", "Data_Type"]):
        name = clean(d["Data Element Name"])
        if clean_name(name) and f"DE:{norm(name)}" not in cat["elements"]:
            desc = next((clean(t) for t in (d["Business_Definition"], d["Business_Description"]) if good_text(t, name)), None)
            cat["elements"][f"DE:{norm(name)}"] = {"code": snake(name), "name": name, "desc": desc, "dtype": dtype(d["Data_Type"], False),
                                                   "picklist_key": None, "aliases": []}
    return cat


def read_master_picklist(r: Reader) -> dict:
    """SabaAIModel: dbo.MasterPickList with Guidewire / Duck Creek / Majesco / Insurity mappings, and field definitions."""
    cat = new_catalog(r.label)
    for o in r.rows("dbo", "MasterPickList", ["FieldName", "PickListOptionCode", "PickListOptionName", "BusinessName", "BusinessRules",
                                              "PickListSource", "IsActive", "VendorMappingGuidewire", "VendorMappingDuckCreek",
                                              "VendorMappingMajesco", "VendorMappingInsurity"], "ExpirationDate"):
        if not active(o) or not clean(o["FieldName"]):
            continue
        pl = add_picklist(cat, f"PL:{norm(o['FieldName'])}", o["FieldName"], o["FieldName"], element=o["FieldName"],
                          library=str(o["PickListSource"] or "COMPANY")[:30])
        opt = add_option(pl, o["PickListOptionCode"], o["PickListOptionName"], o["BusinessRules"])
        if opt:
            if clean(o["BusinessName"]) and norm(o["BusinessName"]) != norm(opt["name"]):
                opt["aliases"].append((clean(o["BusinessName"]), r.label))
            for vendor, col in (("Guidewire", "VendorMappingGuidewire"), ("DuckCreek", "VendorMappingDuckCreek"),
                                ("Majesco", "VendorMappingMajesco"), ("Insurity", "VendorMappingInsurity")):
                if clean(o[col]):
                    opt["aliases"].append((clean(o[col]), vendor))
    for d in r.rows("SabaAImodel", "FieldDefinitions", ["System", "FieldName", "DataType", "BusinessDefinition", "Description"], "ExpirationDate"):
        name = clean(d["BusinessDefinition"]) if clean_name(d["BusinessDefinition"]) and len(str(d["BusinessDefinition"])) <= 60 else clean(d["FieldName"])
        if not clean_name(name):
            continue
        e = cat["elements"].setdefault(f"DE:{norm(name)}", {"code": snake(name), "name": name, "desc": clean(d["Description"]),
                                                            "dtype": dtype(d["DataType"], False), "picklist_key": None, "aliases": []})
        if clean(d["FieldName"]) and norm(d["FieldName"]) != norm(name):
            e["aliases"].append((clean(d["FieldName"]), clean(d["System"]) or r.label))
    return cat


def read_features(r: Reader) -> dict:
    """Governance: GovernanceData.PandCFeatures (field name + business definition by line and module)."""
    cat = new_catalog(r.label)
    for d in r.rows("GovernanceData", "PandCFeatures", ["FieldName", "BusinessDefinition", "SystemName"]):
        name = clean(d["FieldName"])
        if clean_name(name):
            e = cat["elements"].setdefault(f"DE:{norm(name)}", {"code": snake(name), "name": name, "desc": None, "dtype": "TEXT",
                                                                "picklist_key": None, "aliases": []})
            if not e["desc"] and good_text(d["BusinessDefinition"], name):
                e["desc"] = clean(d["BusinessDefinition"])
    return cat


READERS = {"RuleEngine": read_rule_engine, "BureauReporting": read_bureau_reporting, "ISOBureauReporting": read_iso}
SIGNATURES = [  # how a database is recognized, whatever its name; one database can hold several of these
    (read_iso, [("dbo", "canonical_element"), ("dbo", "picklist_option")]),
    (read_bureau_reporting, [("ref", "DataElement"), ("ref", "PickListOption")]),
    (read_rule_engine, [("dbo", "DataElement"), ("dbo", "PickListOption")]),
    (read_cdm_model, [("cdm", "DataElementSynonym"), ("cdm", "PickListOption")]),
    (read_canonical_hub, [("cdm", "DataElement"), ("cdm", "PickListOptions")]),
    (read_semantic_hub, [("dbo", "GlobalDataElementRegistry"), ("dbo", "GlobalPickListInsurance")]),
    (read_ai_mapping, [("dbo", "CanonicalDataElements_Staging"), ("dbo", "CanonicalPicklistOptions_Staging")]),
    (read_master_picklist, [("dbo", "MasterPickList")]),
    (read_features, [("GovernanceData", "PandCFeatures")]),
]
KEYWORDS = re.compile(r"element|pick|option|alias|synonym|rule|code|lookup|list|canonical|dictionar|glossar|term|domain|layout|field|"
                      r"mapping|reference|ref_|enum|valid|value", re.I)


def detect(r: Reader) -> list:
    return [fn for fn, tables in SIGNATURES if all(r.cols(sch, t) for sch, t in tables)]


def user_databases(con) -> list[str]:
    cur = con.cursor()
    cur.execute("SELECT name FROM sys.databases WHERE database_id > 4 AND state_desc = 'ONLINE' AND name NOT LIKE 'SI2%' ORDER BY name")
    return [r[0] for r in cur.fetchall()]


def discover(con, server: str, path: Path) -> None:
    """Every user database: tables, row counts, columns; a few sample rows of tables that look like reference data."""
    cur = con.cursor()
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(f"Discovery of {server} at {dt.datetime.now():%Y-%m-%d %H:%M}\n")
        for db in user_databases(con):
            r = Reader(con, db)
            kind = detect(r)
            fh.write(f"\n=== DATABASE {db}  ({', '.join(k.__name__ for k in kind) if kind else 'not a known SI2 structure'})\n")
            try:
                cur.execute(f"SELECT s.name, t.name, SUM(p.rows) FROM [{db}].sys.tables t JOIN [{db}].sys.schemas s ON s.schema_id = t.schema_id "
                            f"JOIN [{db}].sys.partitions p ON p.object_id = t.object_id AND p.index_id IN (0, 1) GROUP BY s.name, t.name ORDER BY s.name, t.name")
                tables = cur.fetchall()
            except Exception as ex:  # noqa: BLE001
                fh.write(f"  could not list tables: {ex}\n")
                continue
            for sch, t, n in tables:
                cur.execute(f"SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH FROM [{db}].INFORMATION_SCHEMA.COLUMNS "
                            "WHERE TABLE_SCHEMA = ? AND TABLE_NAME = ? ORDER BY ORDINAL_POSITION", sch, t)
                cols = cur.fetchall()
                fh.write(f"  {sch}.{t}  ({n} rows): " + ", ".join(f"{c}:{ty}{'' if ln is None else f'({ln})'}" for c, ty, ln in cols) + "\n")
                if KEYWORDS.search(t) and n and n < 200000:
                    try:
                        cur.execute(f"SELECT TOP (5) * FROM [{db}].[{sch}].[{t}]")
                        for row in cur.fetchall():
                            fh.write("      | " + " | ".join(str(v)[:60] for v in row) + "\n")
                    except Exception as ex:  # noqa: BLE001
                        fh.write(f"      (sample failed: {ex})\n")


# ------------------------------------------------------------------------------------------ the master model
def load_master(con) -> dict:
    cur = con.cursor()

    def q(sql):
        cur.execute(sql)
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]
    return {
        "elements": q("SELECT e.ElementId AS id, e.ElementCode AS code, e.Name AS name, p.PickListCode AS pl FROM canon.DataElement e "
                      "LEFT JOIN canon.PickList p ON p.PickListId = e.PickListId WHERE e.ScopeId = 1 AND e.Status <> 'EXPIRED'"),
        "picklists": q("SELECT PickListId AS id, PickListCode AS code, Name AS name FROM canon.PickList WHERE ScopeId = 1 AND Status <> 'EXPIRED'"),
        "options": q("SELECT OptionId AS id, PickListId AS pl, OptionCode AS code, OptionName AS name FROM canon.PickListOption "
                     "WHERE ScopeId = 1 AND Status <> 'EXPIRED'"),
        "synonyms": q("SELECT ObjectType AS ot, ObjectId AS id, SynonymText AS text, SourceSystem AS src FROM canon.Synonym "
                      "WHERE ScopeId = 1 AND Status <> 'EXPIRED'"),
        "bureau": q("SELECT OptionId AS id, Bureau AS bureau, BureauCode AS code FROM canon.BureauCodeMap WHERE Status <> 'EXPIRED'"),
        "rules": q("SELECT RuleCode AS code FROM rules.BusinessRule WHERE ScopeId = 1"),
        "rulesets": q("SELECT RuleSetCode AS code FROM rules.RuleSet WHERE ScopeId = 1"),
        "pending": q("SELECT ObjectType AS ot, ObjectCode AS code, PayloadJson AS payload FROM gov.ChangeRequest WHERE Status = 'PENDING'"),
    }


class Index:
    """Everything the master already knows, by normalized text; grows as the plan adds new items."""

    def __init__(self, m: dict):
        self.el_code = {e["code"]: e for e in m["elements"]}
        self.el_pl = {e["code"]: e.get("pl") for e in m["elements"] if e.get("pl")}
        self.skipped = []
        self.pl_code = {p["code"]: p for p in m["picklists"]}
        pl_by_id = {p["id"]: p["code"] for p in m["picklists"]}
        el_by_id = {e["id"]: e["code"] for e in m["elements"]}
        self.el_key, self.pl_key = {}, {}
        self.opt = defaultdict(dict)          # pick list code -> normalized key -> option code
        self.syn = set()                      # (object type, object key, normalized text, source)
        opt_by_id = {}
        for e in m["elements"]:
            self.el_key.setdefault(norm(e["code"]), e["code"])
            self.el_key.setdefault(norm(e["name"]), e["code"])
            self._own("ELEMENT", e["code"], e["code"], e["name"])
        for p in m["picklists"]:
            self.pl_key.setdefault(norm(p["code"]), p["code"])
            self.pl_key.setdefault(norm(p["name"]), p["code"])
            self._own("PICKLIST", p["code"], p["code"], p["name"])
        for o in m["options"]:
            plc = pl_by_id.get(o["pl"])
            if plc:
                opt_by_id[o["id"]] = (plc, o["code"])
                self.opt[plc].setdefault(norm(o["code"]), o["code"])
                self.opt[plc].setdefault(norm(o["name"]), o["code"])
                self._own("OPTION", f"{plc}.{o['code']}", o["code"], o["name"])
        for s in m["synonyms"]:
            if s["ot"] == "ELEMENT" and s["id"] in el_by_id:
                c = el_by_id[s["id"]]
                self.el_key.setdefault(norm(s["text"]), c)
                self.syn.add(("ELEMENT", c, norm(s["text"]), "*"))
                self.syn.add(("ELEMENT", c, norm(s["text"]), s["src"]))
            elif s["ot"] == "PICKLIST" and s["id"] in pl_by_id:
                c = pl_by_id[s["id"]]
                self.pl_key.setdefault(norm(s["text"]), c)
                self.syn.add(("PICKLIST", c, norm(s["text"]), "*"))
            elif s["ot"] == "OPTION" and s["id"] in opt_by_id:
                plc, oc = opt_by_id[s["id"]]
                self.opt[plc].setdefault(norm(s["text"]), oc)
                self.syn.add(("OPTION", f"{plc}.{oc}", norm(s["text"]), "*"))
        self.bureau = {(opt_by_id[b["id"]][0], opt_by_id[b["id"]][1], b["bureau"]) for b in m["bureau"] if b["id"] in opt_by_id}
        self.rules = {r["code"] for r in m["rules"]}
        self.rulesets = {r["code"] for r in m["rulesets"]}
        self.pending = {(p["ot"], p["code"]) for p in m["pending"]}
        for p in m["pending"]:
            if p["ot"] == "SYNONYM":
                try:
                    j = json.loads(p["payload"])
                    oc = j.get("object_code") if j.get("object_type") != "OPTION" else f"{j.get('picklist')}.{j.get('object_code')}"
                    self.syn.add((j.get("object_type"), oc, norm(j.get("text")), "*"))
                except (ValueError, AttributeError):
                    pass

    def _own(self, ot, key, *texts):
        for t in texts:
            self.syn.add((ot, key, norm(t), "*"))

    def known_synonym(self, ot, key, text) -> bool:
        return (ot, key, norm(text), "*") in self.syn

    def find_picklist(self, code, name, aliases=(), element=None):
        for t in variants(code, name, *[a for a, _ in aliases], picklist=True):
            if norm(t) in self.pl_key:
                return self.pl_key[norm(t)]
        if element:                                   # the list of the element it belongs to (CoverageTypeOptions -> COVERAGE)
            el = self.find_element(None, element)
            if el and el in self.el_pl:
                return self.el_pl[el]
        return None

    def find_element(self, code, name, aliases=()):
        for t in variants(code, name, *[a for a, _ in aliases]):
            if norm(t) in self.el_key:
                return self.el_key[norm(t)]
        return None

    def find_option(self, plc, code, name, aliases=()):
        keys = self.opt.get(plc, {})
        for t in (code, name, *[a for a, _ in aliases]):
            if t and norm(t) in keys:
                return keys[norm(t)]
        return None


# ------------------------------------------------------------------------------------------ the plan
def plan(cats: list[dict], ix: Index) -> list[dict]:
    """Proposals (change requests) that bring what the sources know into the master, without duplicates."""
    out = []

    def propose(ot, ct, code, summary, payload, source):
        if (ot, code) in ix.pending and ot != "SYNONYM":
            return
        ix.pending.add((ot, code))
        out.append({"object_type": ot, "change": ct, "code": code, "summary": summary[:1000], "payload": payload, "source": source})

    def synonym(ot, key, text, src, source, picklist=None, code=None, typ="SOURCE"):
        text = clean(text)
        if not text or len(text) > 300 or ix.known_synonym(ot, key, text):
            return
        ix.syn.add((ot, key, norm(text), "*"))
        payload = {"object_type": ot, "object_code": code or key, "text": text, "type": typ, "source": (src or source)[:60]}
        if picklist:
            payload["picklist"] = picklist
        out.append({"object_type": "SYNONYM", "change": "ADD", "code": key, "summary": f"{source}: '{text}' = {ot} {key}",
                    "payload": payload, "source": source})

    for cat in cats:
        src = cat["source"]
        pl_map = {}
        # pick lists and their options
        for key, p in cat["picklists"].items():
            master = ix.find_picklist(p["code"], p["name"], p["aliases"], p.get("element"))
            if master:
                pl_map[key] = master
            elif not p["options"]:
                continue
            else:
                base = p["name"] or p["code"]
                code = short_code(snake(PREFIXES.sub("", base.split(".")[-1] if "." in base else base)), 60)
                while code in ix.pl_code:
                    code = short_code(code + "_" + snake(src)[:10], 60)
                ix.pl_code[code] = {"code": code}
                ix.pl_key[norm(code)] = code
                ix.pl_key.setdefault(norm(p["name"]), code)
                pl_map[key] = code
                propose("PICKLIST", "ADD", code, f"{src}: new pick list {code} ({p['name']}, {len(p['options'])} options)",
                        {"code": code, "name": (p["name"] or code)[:200], "description": (p["desc"] or f"Collected from {src}.")[:2000],
                         "library": str(p["library"] or "COMPANY")[:30]}, src)
                ix._own("PICKLIST", code, code, p["name"])
            plc = pl_map[key]
            for t in (p["name"], p["code"]):
                synonym("PICKLIST", plc, t, src, src, typ="SOURCE")
            for a, s in p["aliases"]:
                synonym("PICKLIST", plc, a, s, src)
            for o in p["options"].values():
                oc = ix.find_option(plc, o["code"], o["name"], o["aliases"])
                if not oc and (len(o["code"]) > 60 or not re.match(r"^[\w .,/&()+#%'-]+$", o["code"])):
                    ix.skipped.append((src, "OPTION", f"{plc}.{o['code']}", "code is not a clean code"))
                    continue
                if not oc:
                    oc = o["code"][:60]
                    ix.opt[plc][norm(oc)] = oc
                    ix.opt[plc].setdefault(norm(o["name"]), oc)
                    ix._own("OPTION", f"{plc}.{oc}", oc, o["name"])
                    propose("OPTION", "ADD", f"{plc}.{oc}", f"{src}: new option {plc}.{oc} ({o['name']})",
                            {"picklist": plc, "code": oc, "name": (o["name"] or oc)[:300], "description": (o["desc"] or "")[:2000] or None, "sort": 500}, src)
                for t in (o["code"], o["name"]):
                    synonym("OPTION", f"{plc}.{oc}", t, src, src, picklist=plc, code=oc, typ="VALUE")
                for a, s in o["aliases"]:
                    synonym("OPTION", f"{plc}.{oc}", a, s, src, picklist=plc, code=oc)
        # bureau codes
        for pkey, ocode, bureau, value in cat["bureau_codes"]:
            plc = pl_map.get(pkey)
            oc = ix.find_option(plc, ocode, None) if plc else None
            if plc and oc and (plc, oc, bureau) not in ix.bureau:
                ix.bureau.add((plc, oc, bureau))
                propose("BUREAU_CODE", "ADD", f"{plc}.{oc}.{bureau}", f"{src}: {bureau} code {value} for {plc}.{oc}",
                        {"picklist": plc, "option": oc, "bureau": bureau, "bureau_code": value, "bureau_field": None}, src)
        # data elements
        el_map = {}
        for key, e in cat["elements"].items():
            master = ix.find_element(e["code"], e["name"], e["aliases"])
            if master:
                el_map[key] = master
                for t in (e["name"], e["code"]):
                    synonym("ELEMENT", master, t, src, src)
                for a, s in e["aliases"]:
                    synonym("ELEMENT", master, a, s, src)
                continue
            if not (e.get("curated") or good_text(e.get("desc"), e["name"]) or e.get("picklist_key") in pl_map):
                ix.skipped.append((src, "ELEMENT", e["name"], "no business definition"))
                continue
            code = short_code(e["code"] or snake(e["name"]), 80)
            while code in ix.el_code:
                code = short_code(code + "_" + snake(src)[:10], 80)
            ix.el_code[code] = {"code": code}
            ix.el_key[norm(code)] = code
            ix.el_key.setdefault(norm(e["name"]), code)
            el_map[key] = code
            syns, seen = [], {norm(code), norm(e["name"])}
            for a, s in [(e["code"], src)] + e["aliases"]:
                if clean(a) and norm(a) not in seen and len(str(a)) <= 300:
                    seen.add(norm(a))
                    syns.append({"text": clean(a), "type": "SOURCE", "source": (s or src)[:60]})
                    ix.syn.add(("ELEMENT", code, norm(a), "*"))
            plc = pl_map.get(e.get("picklist_key"))
            propose("ELEMENT", "ADD", code, f"{src}: new data element {code} ({e['name']})",
                    {"code": code, "name": (e["name"] or code)[:200], "description": (e["desc"] or f"Collected from {src}; SME to describe.")[:2000],
                     "data_type": e["dtype"] if plc or e["dtype"] != "CODE" else "TEXT", "picklist": plc, "is_bureau": bool(e.get("bureau")), "is_pii": bool(e.get("pii")),
                     "synonyms": syns}, src)
            ix._own("ELEMENT", code, code, e["name"])
        # rules
        for x in cat["rules"]:
            x["source"] = src
            if x["kind"] == "GEN" and x["code"]:
                x["code"] = f"{snake(src.split('@')[0])[:14]}-{x['code']}"
            code = short_code(x["code"], 40) if x["code"] else None
            if not code or code in ix.rules:
                continue
            ix.rules.add(code)
            rs, purpose = ruleset_for(x)
            if rs not in ix.rulesets:
                ix.rulesets.add(rs)
                propose("RULESET", "ADD", rs, f"{src}: rule set {rs}",
                        {"code": rs, "name": rs.replace("_", " ").title(), "purpose": purpose, "description": f"Rules collected from {src}."}, src)
            payload = rule_payload(x, code, rs, el_map)
            propose("RULE", "ADD", code, f"{src}: rule {code} - {x['name'][:120]}", payload, src)
    out.sort(key=lambda p: ORDER.get(p["object_type"], 9))
    return out


PURPOSE = {"policy": "UNDERWRITING", "underwriting": "UNDERWRITING", "rating": "RATING", "claims": "CLAIMS", "claim": "CLAIMS",
           "billing": "BILLING", "fraud": "FRAUD", "compliance": "COMPLIANCE", "distribution": "DISTRIBUTION"}
ACTION = {"refer": ("REFER", "REFERRAL"), "decline": ("DECLINE", "ELIGIBILITY"), "accept": ("ACCEPT", "ELIGIBILITY"),
          "attachform": ("FLAG", "ALERT"), "surcharge": ("SURCHARGE_PCT", "PRICING"), "credit": ("CREDIT_PCT", "PRICING"),
          "set": ("SET_VALUE", "DERIVATION"), "setvalue": ("SET_VALUE", "DERIVATION"), "calculate": ("CALCULATE", "CALCULATION"),
          "algorithm": ("CALCULATE", "CALCULATION"), "applyalgorithm": ("CALCULATE", "CALCULATION"), "route": ("ROUTE", "ROUTING"),
          "reject": ("REJECT", "VALIDATION"), "warn": ("WARN", "VALIDATION"), "rate": ("CALCULATE", "PRICING"), "factor": ("CALCULATE", "PRICING")}
OPS = {"gt": ">", "ge": ">=", "gte": ">=", "lt": "<", "le": "<=", "lte": "<=", "eq": "=", "ne": "<>", "neq": "<>", "in": "IN", "nin": "NOT IN",
       "notin": "NOT IN", "between": "BETWEEN", ">": ">", ">=": ">=", "<": "<", "<=": "<=", "=": "=", "==": "=", "!=": "<>", "<>": "<>"}


def ruleset_for(x) -> tuple[str, str]:
    if x["kind"] == "RE":
        return short_code("RULEENGINE_" + snake(x["module"]), 60), PURPOSE.get(str(x["module"]).lower(), "OTHER")
    if x["kind"] == "BR":
        return "BUREAU_REPORTING", "BUREAU"
    if x["kind"] == "GEN":
        cat = str(x.get("category") or "Other")
        purpose = PURPOSE.get(cat.lower()) or ("BUREAU" if "bureau" in cat.lower() else "DATA_QUALITY" if cat.lower() in ("etl", "dq", "data quality")
                                               else "RATING" if cat.upper() in ("CREDIT_PCT", "SURCHARGE_PCT") else "OTHER")
        return short_code(snake(x["source"].split("@")[0])[:24] + "_" + snake(cat)[:30], 60), purpose
    return "ISO_BUREAU", "BUREAU"


def rule_payload(x, code, rs, el_map) -> dict:
    p = {"ruleset": rs, "code": code, "name": x["name"][:200], "description": (x.get("desc") or "")[:2000] or None, "lob": str(x.get("lob") or "*")[:60],
         "state": str(x.get("state") or "*").replace("ALL", "*")[:200], "expression": x.get("spec") or None, "effective_from": x.get("effective")}
    if x["kind"] == "RE":
        then = (x["spec"].get("then") or [{}]) if isinstance(x["spec"], dict) else [{}]
        act = str((then[0] or {}).get("action", "")).replace("_", "").lower()
        a, t = ACTION.get(act, ("FLAG", "VALIDATION"))
        p.update({"action_type": a, "rule_type": t, "message": (then[0] or {}).get("reason"), "condition_text": x.get("desc")})
        val = (then[0] or {}).get("value") or (then[0] or {}).get("to") or (then[0] or {}).get("form")
        p["action_value"] = str(val)[:400] if val is not None else None
        conds = []
        for w in (x["spec"].get("when") or []) if isinstance(x["spec"], dict) else []:
            if not isinstance(w, dict):
                conds = None
                break
            el = el_map.get(f"RE:{w.get('field')}")
            op = OPS.get(str(w.get("op", "")).lower())
            v = w.get("value")
            if not el or not op:
                conds = None
                break
            if isinstance(v, list):
                if op == "BETWEEN" and len(v) == 2:
                    conds.append({"element": el, "operator": op, "value1": str(v[0]), "value2": str(v[1])})
                    continue
                op = "IN" if op in ("=", "IN") else ("NOT IN" if op in ("<>", "NOT IN") else op)
                v = ",".join(str(i) for i in v)
            elif isinstance(v, dict):
                conds = None
                break
            conds.append({"element": el, "operator": op, "value1": None if v is None else str(v)})
        if conds:
            p["conditions"] = conds
            p["logic"] = "ANY" if str(x["spec"].get("match", "")).lower() == "any" else "ALL"
    elif x["kind"] == "BR":
        p.update({"rule_type": "VALIDATION", "action_type": "WARN" if x["severity"] == "WARNING" else "REJECT", "severity": x["severity"],
                  "message": x.get("desc"), "condition_text": (x.get("condition_text") or "")[:2000], "target_element": el_map.get(x.get("element_key"))})
    elif x["kind"] == "GEN":
        cat = str(x.get("category") or "").upper()
        rt = {"RATING": "PRICING", "CREDIT_PCT": "PRICING", "SURCHARGE_PCT": "PRICING", "ETL": "TRANSFORMATION", "ELIGIBILITY": "ELIGIBILITY",
              "UNDERWRITING": "REFERRAL", "CLAIMS": "ROUTING", "FRAUD": "ALERT"}.get(cat, "VALIDATION")
        sev = str(x.get("severity") or "").upper()
        p.update({"rule_type": rt, "action_type": cat if cat in ("CREDIT_PCT", "SURCHARGE_PCT") else "FLAG",
                  "severity": "ERROR" if sev in ("HIGH", "CRITICAL", "ERROR") else "WARNING" if sev in ("MEDIUM", "WARNING") else "INFO",
                  "message": (x.get("desc") or "")[:500] or None, "condition_text": (x.get("condition_text") or x.get("desc") or "")[:2000] or None})
    else:
        cat = str(x.get("category") or "VALIDATION").upper()
        p.update({"rule_type": cat if cat in ("VALIDATION", "DERIVATION", "TRANSFORMATION") else "VALIDATION",
                  "action_type": {"DERIVATION": "SET_VALUE", "TRANSFORMATION": "CALCULATE"}.get(cat, "REJECT" if x["severity"] == "ERROR" else "WARN"),
                  "severity": x["severity"] if x["severity"] in ("INFO", "WARNING", "ERROR") else "ERROR", "message": x.get("message"),
                  "target_element": el_map.get(x.get("element_key"))})
    for k, n in (("message", 500), ("condition_text", 2000), ("action_value", 400), ("name", 200), ("description", 2000)):
        if isinstance(p.get(k), str):
            p[k] = p[k][:n]
    return {k: v for k, v in p.items() if v not in (None, "")}


# ------------------------------------------------------------------------------------------ run
def connect(server, database):
    import pyodbc
    drivers = ["ODBC Driver 18 for SQL Server", "ODBC Driver 17 for SQL Server", "SQL Server Native Client 11.0", "SQL Server"]
    driver = next((d for d in drivers if d in pyodbc.drivers()), None)
    if not driver:
        sys.exit("No SQL Server ODBC driver found.")
    return pyodbc.connect(f"DRIVER={{{driver}}};SERVER={server};DATABASE={database};Trusted_Connection=yes;TrustServerCertificate=yes;",
                          autocommit=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--server", default=os.environ.get("SI2_MSSQL_SERVER", "SABAHOME\\SQLEXPRESS02"))
    ap.add_argument("--database", default="SI2Canonical")
    ap.add_argument("--only", default="auto", help="comma-separated source databases, or 'auto' (every database with a known structure)")
    ap.add_argument("--source-server", default=None, help="read the sources from another server (default: --server)")
    ap.add_argument("--discover", action="store_true", help="write a list of every database, table and column on the source server")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--approve-as", default=None, help="second person who approves the proposals")
    ap.add_argument("--approve-seed", action="store_true", help="first approve the seed's pending changes (as --approve-as)")
    ap.add_argument("--scan-all", action="store_true", help="also scan every other user database column by column")
    a = ap.parse_args()

    con = connect(a.server, a.database)
    if a.approve_seed and a.approve_as:
        c0 = con.cursor()
        c0.execute("SELECT RequestId FROM gov.ChangeRequest WHERE Status = 'PENDING' AND Source = 'SEED' ORDER BY RequestId")
        for (rid,) in c0.fetchall():
            c0.execute("EXEC gov.usp_Decide @RequestId = ?, @DecidedBy = ?, @Approve = 1, @Note = N'Seeded ISO change', @Quiet = 1", rid, a.approve_as)
        c0.execute("SELECT COUNT(*) FROM gov.ChangeRequest WHERE Source = 'SEED' AND Status = 'APPROVED'")
        print(f"Seed changes approved: {c0.fetchone()[0]}")
    src_server = a.source_server or a.server
    scon = con if src_server == a.server else connect(src_server, "master")
    suffix = "" if src_server == a.server else "@" + src_server.split("\\")[-1]
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M")
    if a.discover:
        path = HERE / f"discover_{src_server.replace(chr(92), '_')}_{stamp}.txt"
        discover(scon, src_server, path)
        print(f"Discovery written: {path}")
    cats = []
    names = user_databases(scon) if a.only == "auto" else [d.strip() for d in a.only.split(",") if d.strip()]
    print(f"Sources on {src_server}:")
    for db in names:
        r = Reader(scon, db, (db + suffix)[:60])
        if not r.exists():
            print(f"  {db:<24} not on this server, skipped")
            continue
        fns = detect(r)
        if not fns:
            print(f"  {db:<24} not a known structure (see --discover)")
            continue
        for fn in fns:
            try:
                cat = fn(r)
            except Exception as ex:  # noqa: BLE001
                print(f"  {db:<24} {fn.__name__} could not be read: {ex}")
                continue
            n_opt = sum(len(p["options"]) for p in cat["picklists"].values())
            print(f"  {db:<24} {len(cat['elements'])} elements, {len(cat['picklists'])} pick lists, {n_opt} options, {len(cat['rules'])} rules"
                  f"  ({fn.__name__})")
            cats.append(cat)
    ix = Index(load_master(con))
    proposals = plan(cats, ix)
    report = HERE / f"collect_report_{stamp}.csv"
    with open(report, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["Source", "Object", "Change", "Code", "Summary", "Payload"])
        for p in proposals:
            w.writerow([p["source"], p["object_type"], p["change"], p["code"], p["summary"], json.dumps(p["payload"], ensure_ascii=False)])
    counts = defaultdict(int)
    for p in proposals:
        counts[(p["source"], p["object_type"])] += 1
    print(f"\n{len(proposals)} proposal(s):")
    for (s, ot), n in sorted(counts.items()):
        print(f"  {s:<20} {ot:<12} {n}")
    if ix.skipped:
        skip = HERE / f"collect_skipped_{stamp}.csv"
        with open(skip, "w", newline="", encoding="utf-8-sig") as fh:
            w = csv.writer(fh)
            w.writerow(["Source", "Object", "Name", "Why not proposed"])
            w.writerows(ix.skipped)
        print(f"Not proposed (kept out of the master until an SME adds them): {len(ix.skipped)} -> {skip}")
    print(f"Report: {report}")
    if a.dry_run or not proposals:
        print("Dry run: nothing written." if a.dry_run else "Nothing missing: the master already has everything.")
        return 0

    cur = con.cursor()
    runs = {}
    for src in sorted({p["source"] for p in proposals}):
        cur.execute("IF NOT EXISTS (SELECT 1 FROM intake.SourceSystem WHERE SourceSystemCode = ?) "
                    "INSERT intake.SourceSystem (SourceSystemCode, Name, Kind, DatabaseName) VALUES (?, ?, 'DATABASE', ?)", src, src, src,
                    src.split("@")[0])
        cur.execute("SET NOCOUNT ON; INSERT intake.ScanRun (SourceSystemCode, DatabaseName, StartedBy, Message) "
                    "VALUES (?, ?, ?, N'Catalog collection'); SELECT CAST(SCOPE_IDENTITY() AS int);", src, src.split("@")[0], COLLECTOR)
        runs[src] = cur.fetchone()[0]
    for p in proposals:
        cur.execute("EXEC gov.usp_RequestChange @ObjectType = ?, @ChangeType = ?, @ObjectCode = ?, @PayloadJson = ?, @RequestedBy = ?, "
                    "@Summary = ?, @Source = 'INTAKE', @ScanRunId = ?",
                    p["object_type"], p["change"], p["code"][:300], json.dumps(p["payload"], ensure_ascii=False), COLLECTOR, p["summary"], runs[p["source"]])
    for src, run in runs.items():
        cur.execute("UPDATE intake.ScanRun SET FinishedAt = SYSUTCDATETIME(), Message = ? WHERE ScanRunId = ?",
                    f"Catalog collection: {sum(1 for p in proposals if p['source'] == src)} proposals", run)
    print("Proposed. Review: SELECT * FROM gov.vw_PendingChange WHERE RequestedBy = N'SI2 collector';")
    if a.approve_as:
        for src, run in runs.items():
            cur.execute("EXEC gov.usp_DecideAll @DecidedBy = ?, @Approve = 1, @Note = N'Collected from existing databases', @ScanRunId = ?",
                        a.approve_as, run)
            sets = []
            while True:
                if cur.description:
                    sets.append(cur.fetchall())
                if not cur.nextset():
                    break
            summary = ", ".join(f"{r[0]} {r[1]}" for r in (sets[0] if sets else []))
            print(f"  {src}: {summary}")
            for r in (sets[1] if len(sets) > 1 else [])[:20]:
                print(f"    FAILED {r[1]} {r[3]}: {r[5]}")
    if a.scan_all and src_server == a.server:
        cur.execute("SELECT name FROM sys.databases WHERE database_id > 4 AND name NOT LIKE 'SI2%' AND state_desc = 'ONLINE'")
        for (db,) in cur.fetchall():
            cur.execute("EXEC intake.usp_ScanDatabase @SourceDatabase = ?, @StartedBy = ?", db, COLLECTOR)
            r = cur.fetchone()
            print(f"  scanned {db}: {r[2]} columns, {r[3]} matched, {r[4]} new  ->  EXEC intake.usp_ProposeMissing {r[0]};")
            while cur.nextset():
                pass
    c2 = con.cursor()
    c2.execute("SELECT * FROM canon.vw_Summary")
    row = c2.fetchone()
    print("Master now:", ", ".join(f"{d[0]} {v}" for d, v in zip(c2.description, row)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
