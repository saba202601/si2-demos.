# Changelog

SI² demos follow semantic versioning: MAJOR.MINOR.PATCH. Each release is a git tag (`v1.0.0`) so you can always say
exactly which version a client saw, and redeploy it.

## v1.1.0 (in development)

* **SI² Canonical Master on SQL Server** (`sql/si2_canonical/`): 247 data elements, 179 pick lists, 1,092 options,
  860+ synonyms, 788 ISO / NCCI code mappings, 82 rules with 35 test cases; propose → second-person approval;
  GLOBAL / COMPANY / PERSON scopes; extension attributes; system-versioned history; scan another database and
  propose what is missing (alias, synonym, abbreviation and value-fingerprint matching); collector for the RuleEngine, BureauReporting and ISOBureauReporting databases. Installer with self-test.

* **Rule engine and Rule Studio** (`sql/si2_canonical/06_rule_engine.sql`, `07_rule_library.sql`, `app_rule_studio.py`):
  rules scoped by company, line, product, state, channel and program; most-specific override; ordered phases;
  18 role-owned templates; 16 roles with authority limits; decision tables; a 71-rule library for 9 lines with 149
  generated tests; plain-English rule drafting (optional Claude, always checked against the canonical model);
  impact on a synthetic book; Saba proposes, Sabasi approves.

* **Role-Based Super Intelligence** (`app_roles.py`, deploy as `si2-roles`): 15 roles in 5 departments from the
  role workbook, each with an SI² workbench, decisions with reasons, decision boundaries under two-person approval,
  the intelligence it adds, and Ask SI². Claims reserve changes above authority go to a second person; the
  Reinsurance choice drives the Enterprise Risk solvency view; Compliance sees fairness of SI² and of people.

## v1.0.0 (2026-10-12)

First tagged release.

* **Bureau reporting**: ISO (all lines, effective-dated layouts) and NCCI (WCSTAT, WCPOLS, WCIND, WCMED); generate,
  validate, two-person approval, submit, correct and resubmit; AI explanation of rejections.
* **Migration Workbench**: initial load from Excel, CSV, JSON, XML / ACORD, SQL / PL-SQL (read only), PDF and API;
  key and pick-list proposals with evidence; personal-data masking; bureau-style edits; type-2 delta loads;
  hand-off to mapping, canonical gaps, inject, test and two-person sign-off. About 1 million rows in 42 s.
* **Rules, Rating, Claims, Fraud**: Canonical Gaps screens, saved decisions, two-person approvals (rule sets,
  rating factors, routing settings, SIU and payment releases), AI assistance.
* **Company canonical model**: where-used across every app; governed changes published to every app.
* **SI² Command Center**: ROI calculator, NCCI / ISO reporting calendar, demo hub.
* **Platform**: SQLite, SQL Server or PostgreSQL storage; client workspaces; backup / restore; company single sign-on;
  continuous integration on every push.
