"""SI² decision engine: runs every rule that applies to a case and explains the decision.

A rule applies when its scope matches the case (company, line, product, state, channel, program; an empty
dimension means everywhere) and the date is inside its effective period. Rules with the same override key compete:
the most specific one wins (state beats product beats company beats line), so a Florida rule replaces the
countrywide one. Phases run in a fixed order and the outcome combines predictably: DECLINE beats REFER beats ACCEPT.

The same condition semantics as rules.usp_TestRule in SQL Server: numbers compare as numbers, text as text,
IN / NOT IN take comma-separated codes, LIKE uses SQL patterns (% _ [0-9]).
"""
from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field

PHASES = ["DATA", "ELIGIBILITY", "REFERRAL", "RATING", "FORMS", "COMPLIANCE", "BILLING", "ROUTING", "AUTHORITY", "ALERT"]
DIMENSIONS = ["COMPANY", "LOB", "PRODUCT", "STATE", "CHANNEL", "PROGRAM"]
WEIGHT = {"STATE": 8, "PRODUCT": 4, "COMPANY": 2, "LOB": 1, "CHANNEL": 1, "PROGRAM": 3}
OPERATORS = ["=", "<>", ">", ">=", "<", "<=", "IN", "NOT IN", "BETWEEN", "IS NULL", "IS NOT NULL", "LIKE", "NOT LIKE"]
OP_WORDS = {"=": "is", "<>": "is not", ">": "is more than", ">=": "is at least", "<": "is less than", "<=": "is at most", "IN": "is one of",
            "NOT IN": "is not one of", "BETWEEN": "is between", "IS NULL": "is missing", "IS NOT NULL": "is present", "LIKE": "matches",
            "NOT LIKE": "does not match"}
ACTION_WORDS = {"DECLINE": "Decline", "REFER": "Refer", "ACCEPT": "Accept", "SURCHARGE_PCT": "Surcharge", "CREDIT_PCT": "Credit",
                "ATTACH_FORM": "Attach form", "ROUTE": "Route to", "APPROVE_BY": "Needs approval by", "ALERT": "Alert", "REJECT": "Reject the record",
                "WARN": "Warn", "SET_VALUE": "Set", "REQUIRE": "Require", "NOTIFY": "Notify", "FLAG": "Flag", "LOOKUP": "Look up", "CALCULATE": "Calculate"}


@dataclass
class Rule:
    code: str
    name: str
    action: str
    conditions: list                     # [(element, operator, value1, value2)]
    phase: str = "REFERRAL"
    logic: str = "ALL"
    action_value: str | None = None
    scope: dict = field(default_factory=dict)      # {"STATE": ["FL"], "LOB": ["HO"]}
    override_key: str | None = None
    role: str | None = None
    template: str | None = None
    ruleset: str | None = None
    severity: str = "INFO"
    message: str | None = None
    effective_from: str = "2020-01-01"
    effective_to: str | None = None
    status: str = "ACTIVE"
    description: str | None = None

    def specificity(self) -> int:
        return sum(WEIGHT.get(d, 1) for d, v in self.scope.items() if v)


def _num(v):
    try:
        return float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return None


def _like(value: str, pattern: str) -> bool:
    rx = ""
    i = 0
    while i < len(pattern):
        ch = pattern[i]
        if ch == "%":
            rx += ".*"
        elif ch == "_":
            rx += "."
        elif ch == "[":
            j = pattern.find("]", i)
            rx += pattern[i:j + 1] if j > i else re.escape(ch)
            i = j if j > i else i
        else:
            rx += re.escape(ch)
        i += 1
    return re.fullmatch(rx, value, flags=re.I | re.S) is not None


def condition_true(op: str, value, v1, v2=None) -> bool:
    op = op.upper()
    empty = value is None or str(value).strip() == ""
    if op == "IS NULL":
        return empty
    if op == "IS NOT NULL":
        return not empty
    if empty:
        return False
    s = str(value).strip()
    if op in ("IN", "NOT IN"):
        hit = s.upper() in {x.strip().upper() for x in str(v1 or "").split(",")}
        return hit if op == "IN" else not hit
    if op in ("LIKE", "NOT LIKE"):
        hit = _like(s, str(v1 or ""))
        return hit if op == "LIKE" else not hit
    a, b = _num(s), _num(v1)
    if a is not None and b is not None:
        if op == "BETWEEN":
            c = _num(v2)
            return c is not None and b <= a <= c
        return {"=": a == b, "<>": a != b, ">": a > b, ">=": a >= b, "<": a < b, "<=": a <= b}.get(op, False)
    x, y = s.upper(), str(v1 or "").strip().upper()
    if op == "BETWEEN":
        return y <= x <= str(v2 or "").upper()
    return {"=": x == y, "<>": x != y, ">": x > y, ">=": x >= y, "<": x < y, "<=": x <= y}.get(op, False)


def fires(rule: Rule, facts: dict) -> tuple[bool, list]:
    """Whether the rule fires on the facts, and each condition's result."""
    f = {str(k).upper(): v for k, v in facts.items()}
    results = []
    for c in rule.conditions:
        v = f.get(str(c[0]).upper())
        results.append((c, condition_true(c[1], v, c[2], c[3] if len(c) > 3 else None), v))
    if not results:
        return False, []
    ok = any(r for _, r, _ in results) if rule.logic == "ANY" else all(r for _, r, _ in results)
    return ok, results


def in_scope(rule: Rule, case: dict, as_of: str) -> bool:
    if rule.status != "ACTIVE":
        return False
    if as_of < (rule.effective_from or "0000") or (rule.effective_to and as_of > rule.effective_to):
        return False
    for d, values in rule.scope.items():
        if values and "*" not in values:
            v = case.get(d)
            if v is None or str(v).upper() not in {str(x).upper() for x in values}:
                return False
    return True


def describe_condition(c, names: dict | None = None) -> str:
    el = (names or {}).get(c[0], c[0].replace("_", " ").title())
    if c[1] in ("IS NULL", "IS NOT NULL"):
        return f"{el} {OP_WORDS[c[1]]}"
    if c[1] == "BETWEEN":
        return f"{el} is between {_show(c[2])} and {_show(c[3])}"
    if c[1] in ("=", "<>") and str(c[2]).upper() in ("Y", "N"):
        return f"{el} is {'' if (c[1] == '=') == (str(c[2]).upper() == 'Y') else 'not '}yes".replace("is not yes", "is no")
    return f"{el} {OP_WORDS.get(c[1], c[1])} {', '.join(_show(v) for v in str(c[2]).split(',')) if c[1] in ('IN', 'NOT IN') else _show(c[2])}"


def _show(v) -> str:
    """1000000 -> 1,000,000 for reading; codes and small numbers unchanged."""
    n = _num(v)
    if n is None or not re.fullmatch(r"-?\d+(\.\d+)?", str(v).strip()) or abs(n) < 10000:
        return str(v)
    return f"{n:,.0f}" if float(n).is_integer() else f"{n:,.2f}"


def describe(rule: Rule, names: dict | None = None) -> str:
    """The rule in plain English."""
    joiner = " or " if rule.logic == "ANY" else " and "
    when = joiner.join(describe_condition(c, names) for c in rule.conditions) or "always"
    act = ACTION_WORDS.get(rule.action, rule.action.title())
    if rule.action in ("SURCHARGE_PCT", "CREDIT_PCT"):
        act += f" {rule.action_value}%"
    elif rule.action_value and rule.action not in ("DECLINE", "ACCEPT"):
        act += f" {rule.action_value}"
    where = []
    for d in DIMENSIONS:
        if rule.scope.get(d):
            where.append(f"{d.lower() if d != 'LOB' else 'line'} {', '.join(rule.scope[d])}")
    return f"{act} when {when}" + (f" ({'; '.join(where)})" if where else " (everywhere)")


@dataclass
class Decision:
    outcome: str = "ACCEPT"
    fired: list = field(default_factory=list)          # [(rule, condition results)]
    overridden: list = field(default_factory=list)     # [(rule, winner code)]
    surcharge_pct: float = 0.0
    credit_pct: float = 0.0
    premium_factor: float = 1.0
    forms: list = field(default_factory=list)
    routes: list = field(default_factory=list)
    approvals: list = field(default_factory=list)
    alerts: list = field(default_factory=list)
    data_errors: list = field(default_factory=list)
    lookups: dict = field(default_factory=dict)

    def explain(self, names: dict | None = None) -> list[str]:
        out = []
        for r, res in self.fired:
            why = "; ".join(describe_condition(c, names) + f" (value {v})" for c, ok, v in res if ok)
            out.append(f"[{r.phase}] {r.code} {r.name}: {ACTION_WORDS.get(r.action, r.action)}"
                       + (f" {r.action_value}" if r.action_value else "") + (f" because {why}" if why else ""))
        for r, w in self.overridden:
            out.append(f"{r.code} did not apply: replaced by the more specific rule {w}")
        return out


def evaluate(rules: list[Rule], case: dict, facts: dict, as_of: str | None = None, tables: dict | None = None) -> Decision:
    """case: {"COMPANY": "SIM", "LOB": "HO", "PRODUCT": "HO3", "STATE": "FL", "CHANNEL": ...}; facts: {element code: value}."""
    as_of = as_of or dt.date.today().isoformat()
    applicable = [r for r in rules if in_scope(r, case, as_of)]
    best = {}
    for r in applicable:
        if r.override_key:
            cur = best.get(r.override_key)
            if cur is None or r.specificity() > cur.specificity():
                best[r.override_key] = r
    d = Decision()
    for r in applicable:
        if r.override_key and best[r.override_key] is not r:
            d.overridden.append((r, best[r.override_key].code))
    applicable = [r for r in applicable if not r.override_key or best[r.override_key] is r]
    applicable.sort(key=lambda r: (PHASES.index(r.phase) if r.phase in PHASES else 99, r.code))
    present = {str(k).upper() for k in facts}
    for r in applicable:
        if r.phase == "DATA" and not any(str(c[0]).upper() in present for c in r.conditions):
            continue                                   # a data check runs on records that carry its fields
        ok, res = fires(r, facts)
        if not ok:
            continue
        d.fired.append((r, res))
        a, v = r.action, r.action_value
        if a in ("DECLINE", "REJECT") and r.phase != "DATA":
            d.outcome = "DECLINE"
        elif a in ("REJECT",) and r.phase == "DATA":
            d.data_errors.append(r.message or r.name)
        elif a == "REFER" and d.outcome != "DECLINE":
            d.outcome = "REFER"
        elif a == "SURCHARGE_PCT":
            d.surcharge_pct += float(v or 0)
            d.premium_factor *= 1 + float(v or 0) / 100
        elif a == "CREDIT_PCT":
            d.credit_pct += float(v or 0)
            d.premium_factor *= 1 - float(v or 0) / 100
        elif a == "ATTACH_FORM":
            d.forms.append(v)
        elif a == "ROUTE":
            d.routes.append(v)
        elif a == "APPROVE_BY":
            d.approvals.append(v)
            if d.outcome == "ACCEPT":
                d.outcome = "REFER"
        elif a in ("ALERT", "NOTIFY", "WARN"):
            d.alerts.append(f"{v or ''}: {r.message or r.name}".strip(": "))
    if d.data_errors and d.outcome == "ACCEPT":
        d.outcome = "DATA ERRORS"
    d.premium_factor = round(d.premium_factor, 4)
    for code, t in (tables or {}).items():
        hit = lookup(t, {**case, **{str(k).upper(): v for k, v in facts.items()}}, as_of)
        if hit:
            d.lookups[code] = hit
    return d


def lookup(table: dict, values: dict, as_of: str | None = None) -> dict | None:
    """Most specific active row whose inputs all match ('*' matches anything)."""
    as_of = as_of or dt.date.today().isoformat()
    best, score = None, -1
    for row in table.get("rows", []):
        if row.get("status", "ACTIVE") != "ACTIVE" or as_of < row.get("effective_from", "0000") or \
                (row.get("effective_to") and as_of > row["effective_to"]):
            continue
        ok, s = True, 0
        for k, v in row["inputs"].items():
            if v == "*":
                continue
            if str(values.get(k, "")).upper() != str(v).upper():
                ok = False
                break
            s += 1
        if ok and s > score:
            best, score = row, s
    return dict(best["outputs"]) if best else None


# ------------------------------------------------------------------------------------------ tests
def _value_for(op, v1, v2, want: bool):
    """A value that makes the condition true (want=True) or false."""
    n = _num(v1)
    if op in ("IS NULL", "IS NOT NULL"):
        return ("" if op == "IS NULL" else "X") if want else ("X" if op == "IS NULL" else "")
    if op in ("IN", "NOT IN"):
        first = str(v1).split(",")[0].strip()
        hit = first if (op == "IN") == want else "ZZ_OTHER"
        return hit
    if op in ("LIKE", "NOT LIKE"):
        sample = re.sub(r"\[0-9\]", "1", str(v1)).replace("%", "").replace("_", "A")
        return sample if (op == "LIKE") == want else "~nomatch~"
    if op == "BETWEEN" and n is not None and _num(v2) is not None:
        return (n + _num(v2)) / 2 if want else _num(v2) + 1
    if n is not None:
        step = 1 if float(n).is_integer() else 0.01
        val = {"=": n, "<>": n + step, ">": n + step, ">=": n, "<": n - step, "<=": n}[op] if want else \
              {"=": n + step, "<>": n, ">": n, ">=": n - step, "<": n, "<=": n + step}[op]
        return int(val) if float(val).is_integer() else round(val, 4)
    return v1 if (op in ("=", ">=", "<=")) == want else f"NOT_{v1}"


def generate_tests(rule: Rule) -> list[dict]:
    """One case where the rule fires and, for each condition, one where only that condition fails."""
    if not rule.conditions:
        return []
    base = {c[0]: _value_for(c[1], c[2], c[3] if len(c) > 3 else None, True) for c in rule.conditions}
    tests = [{"name": f"{rule.name}: fires", "input": dict(base), "fires": True}]
    if rule.logic == "ANY":
        none = {c[0]: _value_for(c[1], c[2], c[3] if len(c) > 3 else None, False) for c in rule.conditions}
        tests.append({"name": f"{rule.name}: does not fire", "input": none, "fires": False})
    else:
        for c in rule.conditions:
            t = dict(base)
            t[c[0]] = _value_for(c[1], c[2], c[3] if len(c) > 3 else None, False)
            tests.append({"name": f"{rule.name}: not when {c[0].replace('_', ' ').lower()} differs", "input": t, "fires": False})
    for t in tests:                                    # keep only tests the engine agrees with (guards odd value types)
        t["ok"] = fires(rule, t["input"])[0] == t["fires"]
    return [t for t in tests if t.pop("ok")]


def impact(rules: list[Rule], new_rule: Rule, book: list[dict], as_of: str | None = None, replaces: str | None = None) -> dict:
    """What changes on the book if new_rule goes live (optionally replacing the rule with code `replaces`).

    book: [{id, case, facts, premium}]. Returns how many cases it applies to and fires on, decisions that change, premium effect, examples.
    """
    as_of = as_of or dt.date.today().isoformat()
    before_rules = list(rules)
    after_rules = [r for r in rules if r.code not in {replaces, new_rule.code}] + [new_rule]
    out = {"cases": len(book), "in_scope": 0, "fires": 0, "changed": 0, "premium_before": 0.0, "premium_after": 0.0,
           "by_outcome": {}, "examples": []}
    for item in book:
        if not in_scope(new_rule, item["case"], as_of):
            continue
        out["in_scope"] += 1
        if fires(new_rule, item["facts"])[0]:
            out["fires"] += 1
        b = evaluate(before_rules, item["case"], item["facts"], as_of)
        a = evaluate(after_rules, item["case"], item["facts"], as_of)
        prem = float(item.get("premium") or 0)
        out["premium_before"] += prem * b.premium_factor if b.outcome != "DECLINE" else 0
        out["premium_after"] += prem * a.premium_factor if a.outcome != "DECLINE" else 0
        key = f"{b.outcome} → {a.outcome}"
        if b.outcome == a.outcome:
            def more(after, before):
                rest = list(before)
                return [x for x in after if not (x in rest and not rest.remove(x))]
            extra = [f"needs {x}" for x in more(a.approvals, b.approvals)] + [f"routed to {x}" for x in more(a.routes, b.routes)] + \
                    [f"form {x}" for x in more(a.forms, b.forms)] + [f"alert {x}" for x in more(a.alerts, b.alerts)]
            if a.premium_factor != b.premium_factor:
                extra.append(f"premium factor {b.premium_factor} → {a.premium_factor}")
            key = f"still {a.outcome}, " + (", ".join(extra) or "other change")
        if (b.outcome, b.premium_factor, b.routes, b.forms, b.approvals, b.alerts) != (a.outcome, a.premium_factor, a.routes, a.forms, a.approvals, a.alerts):
            out["changed"] += 1
            out["by_outcome"][key] = out["by_outcome"].get(key, 0) + 1
            if len(out["examples"]) < 10:
                out["examples"].append({"id": item["id"], **item["case"], "before": b.outcome, "after": a.outcome,
                                        "premium factor": f"{b.premium_factor} → {a.premium_factor}"})
    out["premium_before"], out["premium_after"] = round(out["premium_before"], 0), round(out["premium_after"], 0)
    return out


def conflicts(rules: list[Rule]) -> list[dict]:
    """Rules that can both apply to the same risk with opposite actions on the same element."""
    out = []
    opposite = {("DECLINE", "CREDIT_PCT"), ("DECLINE", "ACCEPT"), ("SURCHARGE_PCT", "CREDIT_PCT")}
    active = [r for r in rules if r.status == "ACTIVE" and r.conditions]
    for i, a in enumerate(active):
        for b in active[i + 1:]:
            if (a.action, b.action) not in opposite and (b.action, a.action) not in opposite:
                continue
            if a.override_key and a.override_key == b.override_key:
                continue
            overlap = all(not a.scope.get(d) or not b.scope.get(d) or set(a.scope[d]) & set(b.scope[d]) for d in DIMENSIONS)
            same = {c[0] for c in a.conditions} & {c[0] for c in b.conditions}
            if overlap and same:
                out.append({"rule": a.code, "other": b.code, "elements": ", ".join(sorted(same)), "actions": f"{a.action} vs {b.action}"})
    return out
