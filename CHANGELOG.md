# Changelog

SI² demos follow semantic versioning: MAJOR.MINOR.PATCH. Each release is a git tag (`v1.0.0`) so you can always say
exactly which version a client saw, and redeploy it.

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
