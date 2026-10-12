"""Canonical Gaps for Claims Triage: causes of loss on new FNOL feeds that the triage model has no score for.

Map to existing ("score as"), Add new (line + base severity points, drafted from the most similar cause), or
Not needed (those claims go to a standard adjuster for manual review).
"""
from __future__ import annotations

import datetime as dt

import pandas as pd

from .gaps import Gap, rank, words

LINE_HINTS = {"Homeowners": {"WATER", "SEWER", "ROOF", "LIGHTNING", "FIRE", "WIND", "HAIL", "THEFT", "BURGLARY", "FREEZE",
                             "PIPE", "MOLD", "TREE", "SMOKE", "DWELLING", "HOME", "KITCHEN"},
              "Personal Auto": {"COLLISION", "VEHICLE", "GLASS", "WINDSHIELD", "ANIMAL", "DEER", "PARKED", "HIT", "RUN",
                                "ROLLOVER", "TOW", "CAR", "AUTO"}}


EXPERT = {  # keyword -> (line, base points, closest existing cause): an adjuster's first draft
    "ANIMAL": ("Personal Auto", 25, "Single-vehicle collision"), "DEER": ("Personal Auto", 25, "Single-vehicle collision"),
    "GLASS": ("Personal Auto", 8, None), "WINDSHIELD": ("Personal Auto", 8, None),
    "SEWER": ("Homeowners", 20, "Water damage"), "PIPE": ("Homeowners", 20, "Water damage"),
    "LIGHTNING": ("Homeowners", 30, "Kitchen fire"), "SMOKE": ("Homeowners", 30, "Kitchen fire"),
    "BURGLARY": ("Homeowners", 20, None), "TREE": ("Homeowners", 20, "Wind"), "FREEZE": ("Homeowners", 20, "Water damage"),
}


def scan(incoming: pd.DataFrame, causes: dict, ss) -> list[Gap]:
    ignored = getattr(ss, "claims_gap_ignored", set())
    gaps = []
    cands = [(c, f"{c} · {ln}, {pts} pts", []) for c, (ln, pts) in causes.items()]
    for cause, g in incoming[~incoming.cause.isin(list(causes))].groupby("cause"):
        if cause in ignored:
            continue
        best = rank(cause, cands)
        w = set(words(cause))
        hint = next((EXPERT[k] for k in EXPERT if k in w), None)
        if hint and hint[2] in causes:
            best = [(hint[2], f"{hint[2]} · {causes[hint[2]][0]}, {causes[hint[2]][1]} pts", 0.6)] + \
                [b for b in best if b[0] != hint[2]]
        line = max(LINE_HINTS, key=lambda k: len(LINE_HINTS[k] & w)) if any(LINE_HINTS[k] & w for k in LINE_HINTS) else \
            (causes[best[0][0]][0] if best else "Personal Auto")
        same_line = [p for c, (ln, p) in causes.items() if ln == line]
        pts = hint[1] if hint else causes[best[0][0]][1] if best else (round(sum(same_line) / len(same_line)) if same_line else 20)
        if hint:
            line = hint[0]
        gaps.append(Gap(gap_id="", kind="CODE", side="SOURCE", system="FNOL feed", ref=", ".join(g.claim.head(4)),
                        name=cause, context="cause of loss", meaning=f"{len(g)} new claim(s) cannot be scored",
                        occurrences=len(g), risk="High", candidates=best,
                        samples=[f"${x:,.0f}" for x in g.estimate.head(3)],
                        proposal={"code": cause, "line": line, "points": str(pts),
                                  "description": f"{cause} ({line}); base severity {pts} points drafted by SI² from "
                                                 + ("SI²'s claims guide" if hint else f"'{best[0][0]}'" if best else f"the {line} average")
                                                 + ". Claims manager to confirm."}))
    for i, g in enumerate(gaps, 1):
        g.gap_id = f"C{i:03d}"
    return gaps


class Handler:
    def __init__(self, ss, causes: dict, actor: str):
        self.ss, self.causes, self.actor = ss, causes, actor
        for a, d in (("cause_ext", {}), ("claims_gap_ignored", set()), ("claims_audit", [])):
            if not hasattr(ss, a):
                setattr(ss, a, d)

    def _log(self, event, detail):
        self.ss.claims_audit.append({"time": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "by": self.actor,
                                     "event": event, "detail": detail})

    def map_options(self, g):
        first = [(k, f"{l}  ({int(s * 100)}% match)") for k, l, s in g.candidates]
        keys = {k for k, _ in first}
        return first + [(c, f"{c} · {ln}, {p} pts") for c, (ln, p) in self.causes.items() if c not in keys]

    def proposal_fields(self, g):
        return [("code", "Cause of loss", None), ("line", "Line", ["Personal Auto", "Homeowners"]),
                ("points", "Base severity points (0-60)", None), ("description", "Note", None)]

    def map_existing(self, g, key):
        ln, pts = self.causes[key]
        self.ss.cause_ext[g.name] = (ln, pts, f"scored as {key}")
        self._log("Cause mapped (Canonical Gaps)", f"{g.name} → {key}")
        return f"'{g.name}' is now scored as {key} ({pts} points); {g.occurrences} claim(s) can be routed."

    def add_new(self, g, p):
        try:
            pts = int(float(p["points"]))
        except (TypeError, ValueError):
            raise ValueError(f"'{p.get('points')}' is not a number of points.") from None
        if not 0 <= pts <= 60:
            raise ValueError("Base points must be between 0 and 60.")
        self.ss.cause_ext[p["code"].strip()] = (p["line"], pts, p.get("description", ""))
        self._log("Cause added (Canonical Gaps)", f"{p['code']} · {p['line']} · {pts} points")
        return f"New cause '{p['code']}' ({p['line']}, {pts} points) added; {g.occurrences} claim(s) can be routed."

    def not_needed(self, g, reason):
        self.ss.claims_gap_ignored.add(g.name)
        self._log("Cause left unscored (Canonical Gaps)", f"{g.name}: {reason}")
        return f"'{g.name}' claims go to a standard adjuster for manual review ({reason})."
