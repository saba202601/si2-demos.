"""SI² AI assistance with Claude, behind the same SME approvals as everything else.

Claude explains bureau rejections, drafts business descriptions, turns a plain-English rule into a condition the
rule engine can check, and answers questions about the data on screen. Nothing it says changes data by itself:
every suggestion is shown to the SME, and rule changes still go through the two-person approval.

Configuration (Streamlit secrets or environment):
    ANTHROPIC_API_KEY   enables Claude
    SI2_AI_MODEL        default "claude-sonnet-5-5"
Without a key every function answers from SI²'s built-in rules (offline mode), so the demos always work.

Privacy: callers pass masked profiles, counts and codes only. Personal data is never sent.
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request

API_URL = "https://api.anthropic.com/v1/messages"
SYSTEM = ("You are SI², an assistant for US property & casualty insurance data: bureau statistical reporting (NCCI, ISO), "
          "policy, claims, rating, underwriting rules and data migration. Be precise and brief, write for a business "
          "SME, and say when something must be confirmed against the bureau manual, the filed rates or the source system. "
          "Never invent official codes or edit numbers.")


def _secret(name: str) -> str:
    v = os.environ.get(name, "")
    if v:
        return v
    try:
        import streamlit as st
        return str(st.secrets.get(name, "")) if hasattr(st, "secrets") else ""
    except Exception:
        return ""


def model() -> str:
    return _secret("SI2_AI_MODEL") or "claude-sonnet-5-5"


def available() -> bool:
    return bool(_secret("ANTHROPIC_API_KEY"))


def status() -> str:
    return (f"🤖 Claude connected ({model()})" if available()
            else "🤖 Offline mode: SI²'s built-in rules answer. Add ANTHROPIC_API_KEY to the app's secrets to use Claude.")


def ask(prompt: str, max_tokens: int = 700, system: str = SYSTEM, timeout: int = 45) -> str:
    """Claude's answer, or raise RuntimeError (callers fall back to the built-in rules)."""
    key = _secret("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError("no API key")
    body = json.dumps({"model": model(), "max_tokens": max_tokens, "system": system,
                       "messages": [{"role": "user", "content": prompt}]}).encode()
    req = urllib.request.Request(API_URL, data=body, method="POST", headers={
        "x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:      # noqa: S310 (fixed https endpoint)
            out = json.loads(r.read().decode())
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Claude API error {exc.code}") from None
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError(f"Claude API unreachable: {exc}") from None
    return "".join(b.get("text", "") for b in out.get("content", []) if b.get("type") == "text").strip()


def _with_fallback(prompt: str, fallback, max_tokens: int = 700) -> tuple[str, str]:
    if available():
        try:
            return ask(prompt, max_tokens), "Claude"
        except RuntimeError as exc:
            return fallback() + f"\n\n_(Claude unavailable: {exc}; answered by SI²'s built-in rules.)_", "SI² rules"
    return fallback(), "SI² rules"


# ------------------------------------------------------------------------------------------ explain rejections
def explain_rejections(bureau: str, errors: list[dict], context: str = "") -> tuple[str, str]:
    """errors: [{"edit": code/message, "field": ..., "count": n, "example": ...}] (no personal data)."""
    def fallback():
        lines = [f"**{len(errors)} kind(s) of {bureau} edit failure**, largest first:"]
        for e in sorted(errors, key=lambda x: -x.get("count", 0))[:8]:
            fld = e.get("field") or "the record"
            msg = str(e.get("edit", ""))
            fix = ("map the source value to a valid bureau code (Step 3, pick-list values)" if "code" in msg.lower() or "invalid" in msg.lower()
                   else "fill it from the source system or the canonical default" if "blank" in msg.lower() or "missing" in msg.lower() or "required" in msg.lower()
                   else "check the date order and the policy term" if "date" in msg.lower()
                   else "correct the value in the source, or override it in the revision")
            lines.append(f"- **{msg}** on *{fld}* ({e.get('count', 1)}×{', e.g. ' + str(e['example']) if e.get('example') else ''}): {fix}.")
        lines.append("Fix the mapping once and every future file inherits it; then create the revision and resubmit.")
        return "\n".join(lines)
    prompt = (f"These are {bureau} edit failures from a statistical submission (no personal data):\n"
              f"{json.dumps(errors[:40], default=str)}\n{context}\n\nFor each kind: what it means in plain English, the "
              "most likely root cause in the source or mapping, and the fix. Then one line on what to fix first.")
    return _with_fallback(prompt, fallback, 900)


# ------------------------------------------------------------------------------------------ descriptions
def describe_columns(table: str, columns: list[dict]) -> tuple[dict, str]:
    """columns: [{"column", "type", "samples" (masked)}] -> {column: description}."""
    from .gaps import draft_description
    def fallback():
        return {c["column"]: draft_description(c["column"], c.get("type", "TEXT"),
                                               [s.strip() for s in str(c.get("samples", "")).split(",") if s.strip()][:3])
                .replace(" (Drafted by SI² - edit if needed.)", "") for c in columns}
    if not available():
        return fallback(), "SI² rules"
    prompt = (f"Write a one-sentence business description for each column of the insurance table '{table}'. "
              f"Columns (masked samples): {json.dumps(columns[:60], default=str)}\n"
              "Answer only with a JSON object {column: description}.")
    try:
        txt = ask(prompt, 1500)
        m = re.search(r"\{.*\}", txt, re.S)
        data = json.loads(m.group(0)) if m else {}
        out = fallback()
        out.update({k: str(v) for k, v in data.items() if k in out})
        return out, "Claude"
    except (RuntimeError, ValueError):
        return fallback(), "SI² rules"


# ------------------------------------------------------------------------------------------ rule from English
STATE_NAMES = {"alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR", "california": "CA", "colorado": "CO",
               "connecticut": "CT", "delaware": "DE", "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID",
               "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS", "kentucky": "KY", "louisiana": "LA",
               "maine": "ME", "maryland": "MD", "massachusetts": "MA", "michigan": "MI", "minnesota": "MN",
               "mississippi": "MS", "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV",
               "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM", "new york": "NY", "north carolina": "NC",
               "north dakota": "ND", "ohio": "OH", "oklahoma": "OK", "oregon": "OR", "pennsylvania": "PA",
               "rhode island": "RI", "south carolina": "SC", "south dakota": "SD", "tennessee": "TN", "texas": "TX",
               "utah": "UT", "vermont": "VT", "virginia": "VA", "washington": "WA", "west virginia": "WV",
               "wisconsin": "WI", "wyoming": "WY"}
_PHRASES = [  # (regex, field, op) - the built-in parser for common underwriting phrases
    (r"\b(?:drivers?|age[ds]?|insureds?)\s*(?:under|younger than|below|less than)\s*(\d+)", "driver_age", "<"),
    (r"\b(?:drivers?|age[ds]?)\s*(?:over|older than|above|more than)\s*(\d+)", "driver_age", ">"),
    (r"(?:more than|over)\s*(\d+)\s*(?:moving\s*)?violations?", "violations", ">"),
    (r"(\d+)\s*or more\s*(?:moving\s*)?violations?", "violations", ">="),
    (r"(?:more than|over)\s*(\d+)\s*(?:at[- ]fault\s*)?claims?", "prior_claims", ">"),
    (r"(\d+)\s*or more\s*(?:at[- ]fault\s*)?claims?", "prior_claims", ">="),
    (r"(?:mileage|miles)\s*(?:over|above|more than)\s*([\d,]+)", "annual_miles", ">"),
    (r"(?:vehicles?|cars?)\s*(?:worth|valued?)\s*(?:over|above|more than)\s*\$?([\d,]+)k?", "vehicle_value", ">"),
    (r"(?:lapse|without (?:insurance|coverage))\s*(?:of\s*)?(?:over|more than)\s*(\d+)\s*days?", "coverage_lapse_days", ">"),
    (r"(?:licensed|license)\s*(?:less than|under)\s*(\d+)\s*years?", "years_licensed", "<"),
    (r"(?:model year|built|vehicles?)\s*(?:before|older than|prior to)\s*(\d{4})", "model_year", "<"),
]


def _parse_rule(text: str, fields: dict, domains: dict) -> dict:
    t = text.lower()
    conds = []
    for rx, f, op in _PHRASES:
        if f in fields and (m := re.search(rx, t)):
            n = int(m.group(1).replace(",", ""))
            if f == "vehicle_value" and re.search(rx.replace(r"k?", "k"), t):
                n *= 1000
            conds.append(f"{f} {op} {n}")
    states = [code for name, code in STATE_NAMES.items() if re.search(rf"\b{name}\b", t)]
    states += [s for s in re.findall(r"\b([A-Z]{2})\b", text) if s in domains.get("state", [])]
    states = list(dict.fromkeys(states))
    if states and "state" in fields:
        conds.append(f"state == '{states[0]}'" if len(states) == 1 else f"state in {states}")
    for u in domains.get("use_type", []):
        if re.search(rf"\b{u.lower()}\b", t):
            conds.append(f"use_type == '{u}'")
    action, value = "REFER", 0
    if re.search(r"\bdecline|reject|ineligible|not eligible|do not write\b", t):
        action = "DECLINE"
    elif m := re.search(r"surcharge\s*(?:of\s*)?(\d+)\s*%?|(\d+)\s*%\s*surcharge", t):
        action, value = "SURCHARGE %", int(m.group(1) or m.group(2))
    elif m := re.search(r"(?:credit|discount)\s*(?:of\s*)?(\d+)\s*%?|(\d+)\s*%\s*(?:credit|discount)", t):
        action, value = "CREDIT %", int(m.group(1) or m.group(2))
    name = re.sub(r"\s+", " ", text.strip().rstrip("."))[:60]
    return {"name": name[:1].upper() + name[1:], "condition": " and ".join(conds), "action": action, "value": value}


def rule_from_english(text: str, fields: dict, domains: dict) -> tuple[dict, str]:
    """-> ({"name", "condition", "action", "value", "note"}, source). The condition is checked by the rule compiler."""
    from .rules import RuleError, compile_rule, fields_used
    def check(r):
        try:
            unknown = fields_used(compile_rule(r["condition"])) - set(fields)
            r["note"] = f"Uses fields that do not exist: {', '.join(sorted(unknown))}" if unknown else "Checked by the rule compiler."
        except RuleError as exc:
            r["note"] = f"Not a valid condition: {exc}"
        return r
    if available():
        prompt = (f"Turn this underwriting rule into the SI² rule format.\nRule: {text}\n"
                  f"Fields: {json.dumps(fields)}\nCoded values: {json.dumps({k: v[:60] for k, v in domains.items()})}\n"
                  "Condition syntax: Python-like comparisons on the fields (<, <=, >, >=, ==, !=, in [...], and/or/not); "
                  "text in single quotes. Actions: DECLINE, REFER, SURCHARGE %, CREDIT % (value = percent, else 0).\n"
                  'Answer only with JSON: {"name": short name, "condition": "...", "action": "...", "value": number}')
        try:
            m = re.search(r"\{.*\}", ask(prompt, 400), re.S)
            r = json.loads(m.group(0))
            r = {"name": str(r.get("name", text))[:60], "condition": str(r.get("condition", "")),
                 "action": r.get("action") if r.get("action") in ("DECLINE", "REFER", "SURCHARGE %", "CREDIT %") else "REFER",
                 "value": int(float(r.get("value") or 0))}
            return check(r), "Claude"
        except (RuntimeError, ValueError, AttributeError, TypeError):
            pass
    r = _parse_rule(text, fields, domains)
    if not r["condition"]:
        r["note"] = "SI²'s built-in parser did not recognise a condition; write it in the Condition column."
        return r, "SI² rules"
    return check(r), "SI² rules"


# ------------------------------------------------------------------------------------------ ask about the data
def answer(question: str, facts: dict) -> tuple[str, str]:
    """facts: a small dictionary of counts, keys, edits ... from the screen (masked, no personal data)."""
    def fallback():
        q = question.lower()
        hits = [(k, v) for k, v in facts.items() if any(w in k.lower() for w in re.findall(r"[a-z]{4,}", q))]
        body = hits or list(facts.items())[:8]
        return "Here is what SI² knows about that:\n" + "\n".join(f"- **{k}**: {v}" for k, v in body)
    prompt = (f"Facts from the SI² screen (masked, no personal data):\n{json.dumps(facts, default=str)[:12000]}\n\n"
              f"Question from the SME: {question}\nAnswer from the facts only; say if they do not cover it.")
    return _with_fallback(prompt, fallback, 700)


# ------------------------------------------------------------------------------------------ explain a premium
def explain_premium(sheet_rows: list[dict], total: float) -> tuple[str, str]:
    def fallback():
        drivers = {}
        for r in sheet_rows:
            for k, v in r.items():
                if isinstance(v, (int, float)) and k not in ("Base rate", "Premium") and v != 1:
                    drivers.setdefault(k, []).append(v)
        ranked = sorted(((k, sum(v) / len(v)) for k, v in drivers.items()), key=lambda x: -abs(x[1] - 1))
        up = [f"{k} ×{f:.2f}" for k, f in ranked if f > 1][:3]
        down = [f"{k} ×{f:.2f}" for k, f in ranked if f < 1][:3]
        big = max(sheet_rows, key=lambda r: r["Premium"])
        return (f"Annual premium **${total:,.0f}**. The largest coverage is **{big['Coverage']}** (${big['Premium']:,.0f}). "
                f"Raising it: {', '.join(up) or 'nothing above 1.0'}. Lowering it: {', '.join(down) or 'nothing below 1.0'}.")
    prompt = (f"Explain this personal auto premium to an underwriter in 4 short bullet points (what drives it up, down, "
              f"and one lever the customer controls). Total ${total:,.0f}. Worksheet: {json.dumps(sheet_rows, default=str)}")
    return _with_fallback(prompt, fallback, 500)
