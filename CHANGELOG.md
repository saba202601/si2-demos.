# Changelog

SI² demos follow semantic versioning: MAJOR.MINOR.PATCH. Each release is a git tag (`v1.0.0`) so you can always say
exactly which version a client saw, and redeploy it.

## v1.1.0 (in development)

* **Financial Reporting: NAIC P&C Annual Statement (Yellow Book)** (`app_finance.py`, `finance/`): every field of the blank
  as data (86 pages and schedules, 17,259 fields), tables on SQL Server (schema `fin` in SI2Canonical) or SQLite,
  nine company feeds (connect synthetic, database or CSV), the generated statement with lineage, 27 cross-check edits,
  Schedule P triangles and development factors, the financial reporting ontology (Turtle / JSON-LD / tables, SI2Canonical
  gaps) and two-person approval with a filing package.

* **SI² Canonical Master on SQL Server** (`sql/si2_canonical/`): 247 data elements, 179 pick lists, 1,092 options,
  860+ synonyms, 788 ISO / NCCI code mappings, 82 rules with 35 test cases; propose → second-person approval;
  GLOBAL / COMPANY / PERSON scopes; extension attributes; system-versioned history; scan another database and
  propose what is missing (alias, synonym, abbreviation and value-fingerprint matching); collector for the RuleEngine, BureauReporting and ISOBureauReporting databases. Installer with self-test.

* **Rule engine and Rule Studio** (`sql/si2_canonical/06_rule_engine.sql`, `07_rule_library.sql`, `app_rule_studio.py`):
  rules scoped by company, line, product, state, channel and program; most-specific override; ordered phases;
  18 role-owned templates; 16 roles with authority limits; decision tables; a 71-rule library for 9 lines with 149
  generated tests; plain-English rule drafting (optional Claude, always checked against the canonical model);
  impact on a synthetic book; Saba proposes, Sabasi approves.

* **Commercial application model, Party first** (`commercial_app_model.py`, `09_commercial_app.sql`,
  `run_commercial_app.bat`): party, roles, addresses, contacts, relationships and additional interests; producer,
  premises, prior insurance, loss history, 56 underwriting questions; general liability and property sections;
  21 entities over 208 elements and 22 pick lists, collected without duplicates and approved by a second person.

* **SI² Studio** (`si2_studio.py`, `run_si2_studio.bat`): every engine in one app on your own PC, one menu:
  Rule Studio and My desk (on SI2Canonical), Command Center, Roles, Canonical, Migration, ISO and NCCI bureau
  reporting, Business Rule Engine, Rating, Claims Triage and Fraud. Each engine keeps its own working data.

* **My desk** (Rule Studio): one page per role with everything waiting for that person (claim alerts, referrals,
  approvals, compliance stops, routed claims and billing), their rules, their authority, what changed, and Ask SI²
  answered from their own rules and authority.

* **Claim coverage check** (`sql/si2_canonical/08_coverage.sql`, `coverage.py`, `check_claims.py`; Rule Studio pages
  *Claim coverage* and *Policy forms*): reads the policy forms (PDF or text) into covered / excluded / given back /
  limits / deductibles; reads loss descriptions; decides coverage with the form wording as evidence; checks limits,
  deductibles, coverage, cause and payments against the policy; routes alerts (adjuster; underwriter with a copy to
  the claims manager; SIU). Synthetic forms, policies and claims.

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
