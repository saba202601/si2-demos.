"""Where the Rule Studio reads and writes: the SI2Canonical database, or an in-memory copy of the library for demos and tests.

Both work the same way: every change is a request (maker) that a second person approves (checker), and only an
approved request changes the rules. In SQL Server that is gov.usp_RequestChange / gov.usp_Decide; in memory the same
two-person rule is enforced here.
"""
from __future__ import annotations

import copy
import datetime as dt
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import rule_library as L  # noqa: E402
from rule_engine import PHASES, Rule  # noqa: E402

ACTION_PHASE = {"DECLINE": "ELIGIBILITY", "REFER": "REFERRAL", "SURCHARGE_PCT": "RATING", "CREDIT_PCT": "RATING", "ROUTE": "ROUTING",
                "WARN": "ALERT", "ACCEPT": "ELIGIBILITY", "REJECT": "DATA", "ATTACH_FORM": "FORMS", "APPROVE_BY": "AUTHORITY", "ALERT": "ALERT"}
SCOPE_ELEMENTS = {"STATE", "LOB", "COMPANY", "PRODUCT", "LINE_OF_BUSINESS", "STATE_CODE"}


# ----------------------------------------------------------------------------------------------- catalog
@dataclass
class Catalog:
    """Canonical data elements and pick lists, for writing conditions."""
    elements: dict = field(default_factory=dict)     # code -> {name, description, subject, type, picklist}
    options: dict = field(default_factory=dict)      # picklist -> [(code, name)]
    synonyms: dict = field(default_factory=dict)     # element code -> [text]

    def name(self, code: str) -> str:
        return self.elements.get(code, {}).get("name") or code.replace("_", " ").title()

    def names(self) -> dict:
        return {c: e["name"] for c, e in self.elements.items()}

    def element_options(self, code: str) -> list:
        pl = self.elements.get(code, {}).get("picklist")
        return self.options.get(pl, []) if pl else []


def _block(sql: str, start: str) -> str:
    out = []
    for part in sql.split(start)[1:]:
        out.append(re.split(r"\nINSERT |\nGO\b", part, maxsplit=1)[0])
    return "\n".join(out)


def seed_catalog(path: Path = HERE / "03_seed.sql") -> Catalog:
    sql = path.read_text(encoding="utf-8")
    cat = Catalog()
    lit = r"(?:N'((?:[^']|'')*)'|NULL|CAST\(NULL AS nvarchar\(4000\)\))"
    for m in re.finditer(rf"^    \(N'([A-Z0-9_]+)', N'((?:[^']|'')*)', {lit}, N'([A-Z_]+)', N'([A-Z]+)', {lit}", _block(sql, "INSERT canon.DataElement"), re.M):
        cat.elements[m[1]] = {"name": m[2].replace("''", "'"), "description": (m[3] or "").replace("''", "'"), "subject": m[4], "type": m[5],
                              "picklist": m[6]}
    for m in re.finditer(rf"^    \(N'([A-Z0-9_]+)', N'((?:[^']|'')*)', N'((?:[^']|'')*)'", _block(sql, "INSERT canon.PickListOption"), re.M):
        opts = cat.options.setdefault(m[1], [])
        if m[2] not in {o[0] for o in opts}:
            opts.append((m[2].replace("''", "'"), m[3].replace("''", "'")))
    for m in re.finditer(r"^    \(N'ELEMENT', (?:NULL|CAST\(NULL AS nvarchar\(4000\)\)), N'([A-Z0-9_]+)', N'((?:[^']|'')*)'", sql, re.M):
        cat.synonyms.setdefault(m[1], []).append(m[2].replace("''", "'"))
    return cat


# ----------------------------------------------------------------------------------------------- payloads
def rule_payload(rule: Rule, ruleset: str, rule_type: str, tests: list | None = None, description: str | None = None) -> dict:
    """The change-request payload gov.usp_Apply expects for RULE ADD."""
    lob = ",".join(rule.scope.get("LOB", [])) or "*"
    state = ",".join(rule.scope.get("STATE", [])) or "*"
    joiner = " OR " if rule.logic == "ANY" else " AND "
    text = joiner.join(f"{c[0]} {c[1]}" + ("" if c[1] in ("IS NULL", "IS NOT NULL") else f" {c[2]}") + (f" AND {c[3]}" if c[1] == "BETWEEN" else "")
                       for c in rule.conditions)
    return {"code": rule.code, "name": rule.name, "description": description or rule.description, "ruleset": ruleset, "rule_type": rule_type,
            "logic": rule.logic, "condition_text": text, "action_type": rule.action, "action_value": rule.action_value,
            "severity": rule.severity, "message": rule.message, "effective_from": rule.effective_from, "lob": lob[:60], "state": state[:200],
            "conditions": [{"element": c[0], "operator": c[1], "value1": c[2], "value2": c[3]} for c in rule.conditions],
            "template": rule.template, "phase": rule.phase, "owner_role": rule.role, "override_key": rule.override_key,
            "applies_to": {d: v for d, v in rule.scope.items() if v}, "tests": tests or [], "scope": "GLOBAL"}


def payload_rule(p: dict) -> Rule:
    return Rule(code=p["code"], name=p.get("name") or p["code"], action=p.get("action_type", "WARN"),
                conditions=[(c["element"], c["operator"], c.get("value1"), c.get("value2")) for c in p.get("conditions", [])],
                phase=p.get("phase") or ACTION_PHASE.get(p.get("action_type"), "REFERRAL"), logic=p.get("logic", "ALL"),
                action_value=p.get("action_value"), scope={k.upper(): list(v) for k, v in (p.get("applies_to") or {}).items() if v},
                override_key=p.get("override_key"), role=p.get("owner_role"), template=p.get("template"), ruleset=p.get("ruleset"),
                severity=p.get("severity", "INFO"), message=p.get("message"), effective_from=p.get("effective_from") or "2020-01-01",
                description=p.get("description"))


def next_code(existing: set, prefix: str) -> str:
    n = 1
    while f"{prefix}{n:02d}" in existing:
        n += 1
    return f"{prefix}{n:02d}"


# ----------------------------------------------------------------------------------------------- memory repo
class MemoryRepo:
    """The rule library in memory: for the online demo, for tests, and when SQL Server is not reachable."""
    kind = "memory"

    def __init__(self):
        self.catalog = seed_catalog()
        self.rules: list[Rule] = copy.deepcopy(L.RULES)
        self.templates = [{"code": t[0], "name": t[1], "role": t[2], "phase": t[3], "rule_type": t[4], "action": t[5], "sentence": t[6],
                           "questions": t[7], "example": t[8]} for t in L.TEMPLATES]
        self.roles = [{"code": r[0], "name": r[1], "department": r[2], "description": r[3]} for r in L.ROLES]
        self.companies = [{"code": c[0], "name": c[1], "description": c[2]} for c in L.COMPANIES]
        self.products = [{"code": p[0], "lob": p[1], "name": p[2], "company": p[3], "states": ", ".join(p[4])} for p in L.PRODUCTS]
        self.rulesets = [{"code": r[0], "name": r[1], "purpose": r[2]} for r in L.RULESETS]
        self.tables = {t["code"]: {**{k: v for k, v in t.items() if k != "rows"},
                                   "rows": [{"id": i + 1, "inputs": a, "outputs": b, "status": "ACTIVE", "effective_from": "2020-01-01"}
                                            for i, (a, b) in enumerate(t["rows"])]} for t in L.TABLES}
        self.authority = [{"role": a[0], "authority": a[1], "lob": a[2], "limit": a[3], "note": a[4], "status": "ACTIVE",
                           "effective_from": "2020-01-01", "effective_to": None} for a in L.AUTHORITY]
        self.requests: list[dict] = []

    # -- reading
    def rule(self, code: str) -> Rule | None:
        return next((r for r in self.rules if r.code == code and r.status == "ACTIVE"), None)

    def template(self, code: str) -> dict | None:
        return next((t for t in self.templates if t["code"] == code), None)

    def pending(self) -> list[dict]:
        return [r for r in self.requests if r["status"] == "PENDING"]

    def history(self) -> list[dict]:
        return list(reversed(self.requests))

    # -- maker / checker
    def propose(self, object_type: str, change_type: str, code: str, payload: dict, by: str, summary: str) -> int:
        rid = len(self.requests) + 1
        self.requests.append({"id": rid, "object_type": object_type, "change_type": change_type, "code": code, "summary": summary,
                              "payload": json.loads(json.dumps(payload)), "requested_by": by, "requested_at": dt.datetime.now().isoformat(timespec="seconds"),
                              "status": "PENDING", "decided_by": None, "note": None, "result": None})
        return rid

    def decide(self, request_id: int, by: str, approve: bool = True, note: str | None = None) -> tuple[str, str]:
        req = next((r for r in self.requests if r["id"] == request_id), None)
        if req is None:
            raise ValueError("Change request not found.")
        if req["status"] != "PENDING":
            raise ValueError("This change request has already been decided.")
        if req["requested_by"] == by:
            raise ValueError("Two-person rule: the person who requested a change cannot approve it.")
        if not approve:
            status, result = "REJECTED", "Rejected."
        else:
            try:
                status, result = "APPROVED", self._apply(req)
            except Exception as e:  # noqa: BLE001 - recorded like gov.usp_Decide does
                status, result = "FAILED", str(e)
        req.update(status=status, decided_by=by, note=note, result=result)
        return status, result

    def _apply(self, req: dict) -> str:
        ot, ct, p = req["object_type"], req["change_type"], req["payload"]
        if ot == "RULE" and ct == "ADD":
            unknown = [c["element"] for c in p.get("conditions", []) if c["element"] not in self.catalog.elements]
            if unknown:
                raise ValueError(f"Unknown data element in the conditions: {', '.join(unknown)}. Add the element first.")
            if self.rule(p["code"]):
                raise ValueError(f"Rule {p['code']} already exists.")
            self.rules.append(payload_rule(p))
            return f"Rule {p['code']} added."
        if ot == "RULE" and ct == "EXPIRE":
            r = self.rule(p["code"])
            if r is None:
                raise ValueError("Rule not found.")
            r.status, r.effective_to = "EXPIRED", p.get("effective_to") or dt.date.today().isoformat()
            return f"Rule {p['code']} expired."
        if ot == "TEMPLATE" and ct == "ADD":
            self.templates.append({"code": p["code"], "name": p.get("name", p["code"]), "role": p.get("owner_role"), "phase": p.get("phase", "REFERRAL"),
                                   "rule_type": p.get("rule_type", "REFERRAL"), "action": p.get("action_type", "REFER"),
                                   "sentence": p.get("sentence", p["code"]), "questions": p.get("questions", []), "example": p.get("example")})
            return f"Template {p['code']} added."
        if ot == "DTABLE_ROW" and ct == "ADD":
            t = self.tables[p["table"]]
            t["rows"].append({"id": max([r["id"] for r in t["rows"]] or [0]) + 1, "inputs": p["inputs"], "outputs": p["outputs"],
                              "status": "ACTIVE", "effective_from": p.get("effective_from") or dt.date.today().isoformat(), "note": p.get("note")})
            return f"Row added to {p['table']}."
        if ot == "DTABLE_ROW" and ct == "EXPIRE":
            for t in self.tables.values():
                for r in t["rows"]:
                    if r["id"] == int(p["row_id"]) and t["code"] == p.get("table", t["code"]):
                        r["status"], r["effective_to"] = "EXPIRED", p.get("effective_to") or dt.date.today().isoformat()
            return "Row expired."
        if ot == "AUTHORITY" and ct == "ADD":
            start = p.get("effective_from") or dt.date.today().isoformat()
            for a in self.authority:
                if (a["role"], a["authority"], a["lob"]) == (p["role"], p["authority"], p.get("lob") or "*") and a["status"] == "ACTIVE":
                    a["status"] = "EXPIRED"
                    a["effective_to"] = (dt.date.fromisoformat(start) - dt.timedelta(days=1)).isoformat()
            self.authority.append({"role": p["role"], "authority": p["authority"], "lob": p.get("lob") or "*", "limit": float(p["limit"]),
                                   "note": p.get("note"), "status": "ACTIVE", "effective_from": start, "effective_to": None})
            return f"Authority for {p['role']} set."
        raise ValueError(f"Unsupported change: {ot} {ct}.")

    def engine_tables(self) -> dict:
        return {c: {"rows": t["rows"]} for c, t in self.tables.items()}


# ----------------------------------------------------------------------------------------------- SQL Server repo
class SqlRepo(MemoryRepo):
    """The same, read from and written to SI2Canonical. Windows authentication only."""
    kind = "sql"
    DRIVERS = ["ODBC Driver 18 for SQL Server", "ODBC Driver 17 for SQL Server", "ODBC Driver 13 for SQL Server", "SQL Server Native Client 11.0",
               "SQL Server"]

    def __init__(self, server: str, database: str = "SI2Canonical"):  # noqa: D107 - no super().__init__: everything comes from SQL
        import pyodbc
        driver = next((d for d in self.DRIVERS if d in pyodbc.drivers()), None)
        if driver is None:
            raise RuntimeError("No SQL Server ODBC driver is installed.")
        self.server, self.database = server, database
        self.cn = pyodbc.connect(f"DRIVER={{{driver}}};SERVER={server};DATABASE={database};Trusted_Connection=yes;TrustServerCertificate=yes;",
                                 autocommit=True, timeout=15)
        self.reload()

    def _q(self, sql: str, *params) -> list[dict]:
        cur = self.cn.cursor()
        cur.execute(sql, *params)
        while cur.description is None and cur.nextset():
            pass
        if cur.description is None:
            return []
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

    def reload(self) -> None:
        q = self._q
        cat = Catalog()
        for r in q("SELECT ElementCode, Name, BusinessDescription, SubjectArea, DataType, PickList FROM canon.vw_DataElement WHERE Status = 'ACTIVE'"):
            cat.elements[r["ElementCode"]] = {"name": r["Name"], "description": r["BusinessDescription"] or "", "subject": r["SubjectArea"],
                                              "type": r["DataType"], "picklist": r["PickList"]}
        for r in q("SELECT PickList, OptionCode, OptionName FROM canon.vw_PickListOption WHERE Status = 'ACTIVE' ORDER BY PickList, SortOrder"):
            cat.options.setdefault(r["PickList"], []).append((r["OptionCode"], r["OptionName"]))
        for r in q("SELECT e.ElementCode, s.SynonymText FROM canon.Synonym s JOIN canon.DataElement e ON s.ObjectType = 'ELEMENT' AND e.ElementId = s.ObjectId "
                   "WHERE s.Status = 'ACTIVE'"):
            cat.synonyms.setdefault(r["ElementCode"], []).append(r["SynonymText"])
        self.catalog = cat
        conds, scopes = {}, {}
        for r in q("SELECT c.RuleId, c.Seq, e.ElementCode, c.Operator, c.Value1, c.Value2 FROM rules.RuleCondition c "
                   "JOIN canon.DataElement e ON e.ElementId = c.ElementId ORDER BY c.RuleId, c.Seq"):
            conds.setdefault(r["RuleId"], []).append((r["ElementCode"], r["Operator"], r["Value1"], r["Value2"]))
        for r in q("SELECT RuleId, Dimension, ScopeValue FROM rules.RuleScope"):
            scopes.setdefault(r["RuleId"], {}).setdefault(r["Dimension"], []).append(r["ScopeValue"])
        self.rules = []
        for r in q("SELECT r.RuleId, r.RuleCode, r.Name, r.Description, r.ActionType, r.ActionValue, r.ConditionLogic, r.Phase, r.OwnerRole, "
                   "r.TemplateCode, r.OverrideKey, r.Severity, r.Message, CONVERT(char(10), r.EffectiveFrom, 23) AS EffFrom, "
                   "CONVERT(char(10), r.EffectiveTo, 23) AS EffTo, r.Status, rs.RuleSetCode, r.LobScope, r.StateScope "
                   "FROM rules.BusinessRule r JOIN rules.RuleSet rs ON rs.RuleSetId = r.RuleSetId"):
            scope = scopes.get(r["RuleId"], {})
            if not scope:
                for dim, col in (("LOB", "LobScope"), ("STATE", "StateScope")):
                    vals = [v.strip() for v in (r[col] or "*").split(",") if v.strip() not in ("", "*")]
                    if vals:
                        scope[dim] = vals
            self.rules.append(Rule(code=r["RuleCode"], name=r["Name"], action=r["ActionType"], conditions=conds.get(r["RuleId"], []),
                                   phase=r["Phase"] if r["Phase"] in PHASES else ACTION_PHASE.get(r["ActionType"], "REFERRAL"),
                                   logic=r["ConditionLogic"], action_value=r["ActionValue"], scope=scope, override_key=r["OverrideKey"],
                                   role=r["OwnerRole"], template=r["TemplateCode"], ruleset=r["RuleSetCode"], severity=r["Severity"],
                                   message=r["Message"], effective_from=r["EffFrom"], effective_to=r["EffTo"], status=r["Status"],
                                   description=r["Description"]))
        self.templates = [{"code": t["TemplateCode"], "name": t["Name"], "role": t["OwnerRole"], "phase": t["Phase"], "rule_type": t["RuleType"],
                           "action": t["ActionType"], "sentence": t["Sentence"], "questions": json.loads(t["QuestionsJson"] or "[]"), "example": t["ExampleText"]}
                          for t in q("SELECT * FROM rules.RuleTemplate WHERE Status = 'ACTIVE' ORDER BY TemplateCode")]
        self.roles = [{"code": r["RoleCode"], "name": r["Name"], "department": r["Department"], "description": r["Description"]}
                      for r in q("SELECT * FROM rules.Role ORDER BY SortOrder, RoleCode")]
        self.companies = [{"code": r["CompanyCode"], "name": r["Name"], "description": r["Description"]} for r in q("SELECT * FROM rules.Company")]
        self.products = [{"code": r["ProductCode"], "lob": r["LobCode"], "name": r["Name"], "company": r["CompanyCode"], "states": r["States"] or ""}
                         for r in q("SELECT * FROM rules.Product ORDER BY LobCode, ProductCode")]
        self.rulesets = [{"code": r["RuleSetCode"], "name": r["Name"], "purpose": r["Purpose"]}
                         for r in q("SELECT RuleSetCode, Name, Purpose FROM rules.RuleSet WHERE Status = 'ACTIVE' ORDER BY RuleSetCode")]
        self.tables = {}
        for t in q("SELECT * FROM rules.DecisionTable WHERE Status = 'ACTIVE'"):
            self.tables[t["TableCode"]] = {"code": t["TableCode"], "name": t["Name"], "role": t["OwnerRole"], "description": t["Description"],
                                           "inputs": json.loads(t["InputsJson"]), "outputs": json.loads(t["OutputsJson"]),
                                           "illustrative": bool(t["IsIllustrative"]), "rows": []}
        for r in q("SELECT RowId, TableCode, InputsJson, OutputsJson, Note, Status, CONVERT(char(10), EffectiveFrom, 23) AS EffFrom, "
                   "CONVERT(char(10), EffectiveTo, 23) AS EffTo FROM rules.DecisionTableRow ORDER BY RowId"):
            if r["TableCode"] in self.tables:
                self.tables[r["TableCode"]]["rows"].append({"id": r["RowId"], "inputs": json.loads(r["InputsJson"]), "outputs": json.loads(r["OutputsJson"]),
                                                            "note": r["Note"], "status": r["Status"], "effective_from": r["EffFrom"],
                                                            "effective_to": r["EffTo"]})
        self.authority = [{"role": a["RoleCode"], "authority": a["AuthorityType"], "lob": a["LobScope"], "limit": float(a["LimitAmount"]),
                           "note": a["Notes"], "status": a["Status"], "effective_from": a["EffFrom"], "effective_to": a["EffTo"]}
                          for a in q("SELECT RoleCode, AuthorityType, LobScope, LimitAmount, Notes, Status, CONVERT(char(10), EffectiveFrom, 23) AS EffFrom, "
                                     "CONVERT(char(10), EffectiveTo, 23) AS EffTo FROM rules.RoleAuthority ORDER BY RoleCode, AuthorityType")]
        self.requests = [{"id": r["RequestId"], "object_type": r["ObjectType"], "change_type": r["ChangeType"], "code": r["ObjectCode"],
                          "summary": r["Summary"], "payload": json.loads(r["PayloadJson"] or "{}"), "requested_by": r["RequestedBy"],
                          "requested_at": str(r["RequestedAt"])[:19], "status": r["Status"], "decided_by": r["DecidedBy"], "note": r["DecisionNote"],
                          "result": r["ResultMessage"]}
                         for r in q("SELECT TOP (300) * FROM gov.ChangeRequest WHERE ObjectType IN ('RULE', 'TEMPLATE', 'DTABLE_ROW', 'AUTHORITY', 'RULESET') "
                                    "ORDER BY RequestId")]

    def history(self) -> list[dict]:
        return list(reversed(self.requests))

    def propose(self, object_type, change_type, code, payload, by, summary) -> int:
        rows = self._q("SET NOCOUNT ON; DECLARE @id int; EXEC gov.usp_RequestChange ?, ?, ?, ?, ?, ?, 'MANUAL', NULL, @id OUTPUT; SELECT @id AS RequestId;",
                       object_type, change_type, code, json.dumps(payload), by, summary[:1000])
        self.reload()
        return int(rows[0]["RequestId"])

    def decide(self, request_id, by, approve=True, note=None) -> tuple[str, str]:
        try:
            rows = self._q("SET NOCOUNT ON; DECLARE @s varchar(10), @r nvarchar(2000); "
                           "EXEC gov.usp_Decide ?, ?, ?, ?, 1, @s OUTPUT, @r OUTPUT; SELECT @s AS Status, @r AS Result;",
                           int(request_id), by, 1 if approve else 0, note)
        except Exception as e:  # the procedure's own messages (two-person rule, already decided)
            msg = str(e)
            m = re.search(r"\]([^\[\]]+?)\s*\(\d+\)", msg)
            raise ValueError(m[1].strip() if m else msg) from e
        self.reload()
        return rows[0]["Status"], rows[0]["Result"]
