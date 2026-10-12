# SI² Demo Apps

Streamlit demos for **SI² · Super Intelligence for Insurance** (https://si2insure.com).
All data is synthetic. Codes, record layouts and rating factors are illustrative.

| App file | Demo | Planned address |
|---|---|---|
| `app_canonical.py` | Canonical Data Model | https://si2-canonical.streamlit.app |
| `app_bureau.py` | Bureau Reporting Workbench (WCSTAT, WCPOLS, WCIND, WCMED) | https://si2-bureau.streamlit.app |
| `app_rules.py` | Business Rule Engine | https://si2-rules.streamlit.app |
| `app_rating.py` | Rating Engine | https://si2-rating.streamlit.app |
| `app_claims.py` | Claims Triage | https://si2-claims.streamlit.app |
| `app_migration.py` | Legacy-to-Cloud Migration Workbench | https://si2-migrate.streamlit.app |
| `app_fraud.py` | Fraud Engine | https://si2-fraud.streamlit.app |
| `app_iso_bureau.py` | ISO Bureau Reporting, all lines (PA, HO, CA, CP, GL, IM, CR, BP, FI, BR); see `iso_bureau/README.md` | https://si2-iso-bureau.streamlit.app |

Shared code lives in `si2_common/` (branding, access code, synthetic data, rule evaluator, and the Canonical Gaps engine and screen).

### Canonical Gaps

One shared screen (`si2_common/gaps_ui.py`) lists everything a source, destination, rule or quote uses that the
canonical model does not have yet, with three pre-filled actions: **Map to existing**, **Add new** (SI² drafts the
name, type, description or factor) and **Not needed**. Each app adds only a small adapter:

| App | Where | Adapter | Gaps it finds |
|---|---|---|---|
| ISO bureau reporting | 🧩 Canonical Gaps page | `iso_bureau/gaps.py` | source elements, pick lists and codes; ISO destination codes |
| NCCI bureau reporting | Step 3 · 🧩 Canonical gaps tab | `bureau/gaps.py` | unused source columns, unsourced canonical attributes, WCIO fields with no canonical attribute, values with no WCIO code (NCCI codes are mapped, never added) |
| Legacy migration | Step 5 · 🧩 Canonical gaps tab | `migrate/gaps.py` | legacy elements and codes; required cloud fields nothing feeds |
| Business Rule Engine | 🧩 Rule gaps tab | `si2_common/rules_gaps.py` | fields and codes a rule uses that the rule vocabulary lacks (rules R09-R11 are the demo) |
| Rating Engine | 🧩 Rating gaps tab | `si2_common/rating_gaps.py` | values on incoming quotes with no factor: new state, Rideshare use, 500/1000 limit, $2,000 deductible; drafted factors are flagged until an actuary confirms them |

### Initial load (Migration Workbench, Step 0)

Upload Excel, CSV, JSON, XML / ACORD, SQL / PL-SQL scripts (read, never executed), PDF (simple text tables) or an API
returning JSON. SI² profiles every column (codes with leading zeros stay text; dates and amounts in any format),
proposes primary keys, foreign keys and pick lists with a confidence and the evidence (declared in the DDL, nested in
the file, found in the data, or the policy term in force on the loss date), the SME approves, and SI² creates the
tables (surrogate key + business key, effective dating), loads them parent-first, quarantines rows it cannot load and
reconciles row counts and money totals. SQLite DDL and SQL Server DDL are generated. Engine: `migrate/initial_load.py`;
sample upload set: `migrate/initial_load_samples/`.

### Platform features

* **Decisions are saved** (`si2_common/store.py`, `persist.py`): NCCI, Rules, Rating and Migration restore every SME
  decision in a new session. SQLite by default (`data/si2_state.db`); SQL Server with `SI2_STATE_BACKEND=mssql`
  (`run_si2_sqlserver.bat app_migration.py`). On Streamlit Community Cloud the file resets when the app is rebooted
  or redeployed; use SQL Server or a hosted database for permanent storage. *Reset demo data* in each sidebar.
* **Two-person rule** (`approvals_ui.py`): the person who proposes cannot approve. Rating: new factors are indications
  only until an actuary approves them with a filing reference. Rules: SME edits are a draft; submissions are decided by
  the approved production rules. NCCI: the person who generated a submission cannot approve it. Migration: the
  initial-load plan and the final sign-off need a second person. Names come from the sidebar (SSO in production).
* **Initial load extras**: personal data (SSN/TIN, date of birth, driver's license, email, phone, names, addresses) is
  detected and masked unless the role is Data steward; pick-list codes get descriptions from the destination pick
  lists or the SI² insurance code dictionary; bureau-style data edits (Q01-Q10) run before the load and Error rows are
  quarantined unless accepted; **delta loads** add new rows, version changed rows (old version expired) and never
  delete; *Use in migration* sends the loaded tables into Steps 1-9 with the approved codes.
* **Company canonical model** (`si2_common/registry.py`, Canonical app → 🏢 Company model): every app's model
  harvested into business terms with every name in use and where-used.
* **Demo hub**: every app's sidebar links all eight demos in walk-through order, and each app has a two-minute
  guided tour.

### Round 3: production readiness

* **Company sign-in** (`si2_common/identity.py`): OpenID Connect single sign-on via `st.login` when `[auth]` is in
  the secrets; approvals then use the signed-in email. **PostgreSQL** store backend (`SI2_STATE_BACKEND=postgres`,
  `SI2_DATABASE_URL`). Template: `.streamlit/secrets.toml.example`.
* **AI with Claude** (`si2_common/ai.py`, `ai_ui.py`; `ANTHROPIC_API_KEY`, model `SI2_AI_MODEL`): explain NCCI / ISO
  rejections, draft column descriptions, write a rule from plain English, explain a premium or a claim routing,
  summarise an SIU case, Ask SI² about loaded data. Masked facts only; offline built-in rules when no key is set.
* **Scale**: set-based initial load, about 1 million rows in 42 s (`benchmarks/RESULTS.md`).
* **SI² Command Center** (`app_hub.py`, deploy as `si2-command`): ROI calculator, NCCI / ISO reporting calendar,
  all demos.
* **Claims and Fraud** at the same standard: saved decisions, two-person approval (routing settings, SIU releases,
  payment releases), Canonical Gaps (new FNOL causes; data the remaining fraud types need).
* **Company model governance** (Canonical app): propose → impact → second-person approval → published; published
  synonyms and definitions feed initial-load profiling and migration matching.
* Security summary: `SECURITY.md`.

### Operations

* **Continuous integration** (`.github/workflows/tests.yml`): every push runs the unit and engine tests, a
  PostgreSQL test, every app and every step (`tests/test_apps_smoke.py`) and a smaller load benchmark.
* **Client workspaces**: the sidebar's *Client workspace* keeps each client's decisions and approvals apart;
  `SI2_WORKSPACES=acme,beta` in secrets limits the list (e.g. one deployment per client).
* **Backup / restore**: sidebar → *Backup / restore* downloads or restores one workspace; scheduled backups with
  `python -m tools.backup_state` (`run_si2_backup.bat` + Windows Task Scheduler on your PC).
* **Versions**: `VERSION` (shown in every footer), `CHANGELOG.md`, git tags (`v1.0.0`).

SI² is independent and not affiliated with or endorsed by NCCI, ISO / Verisk, ACORD, Guidewire or Duck Creek; their
names describe the formats SI² works with, and all trademarks belong to their owners.

Tests: `python -m pytest tests iso_bureau/tests -q` (set `SI2_TEST_PG_URL` to include the PostgreSQL test).

## Bureau Reporting Workbench (`bureau/`)

| File | What it does |
|---|---|
| `specparse.py` | Reads WCIO spec PDFs (layout text) into fields: record, positions, class, formats, constants, pick lists, N/A states |
| `data/catalog.json` | Field catalog parsed from WCPOLS, WCSTAT, WCIND and WCMED (2,548 fields) |
| `catalog.py` | Record keys, aliases, implied decimals, NCCI state codes, pick-list confidence, layout QA |
| `source.py` | Demo legacy source system (policy admin, claims, bill review) with seeded data problems |
| `canonical.py` | SI² canonical bureau model, source → canonical auto mapping, value → code mapping |
| `generate.py` | Canonical → bureau field map and fixed-width / flat CSV generation per spec positions |
| `edits.py` | Simulated bureau intake: parses the file by positions and runs edits; returns an error file |
| `revise.py` | Turns errors into revision proposals (rules, or Claude with `ANTHROPIC_API_KEY`) and applies approved ones |

Optional secrets for the workbench (Streamlit Cloud → app → Settings → Secrets):

```toml
ANTHROPIC_API_KEY = "sk-ant-..."
ANTHROPIC_MODEL = "claude-sonnet-5-5"
```

## Legacy-to-Cloud Migration Workbench (`migrate/`)

| File | What it does |
|---|---|
| `legacy.py` | Reads COBOL copybooks (PIC, COMP-3, OCCURS, 88-levels) and fixed-width data, DB tables, code tables, PDF forms, notes and COBOL programs; classifies uploaded files |
| `engine.py` | Discovery inventory, canonical model with synonyms, source → canonical → destination matching, pick-list value maps, transform, load (SQLite), reconciliation and the PREMCALC business-rule test |
| `samples/` | INSURE/400 demo legacy system and the cloud destination schema and pick lists |

## Fraud Engine (`fraud/`)

| File | What it does |
|---|---|
| `catalog.py` | 50 P&C fraud types (policy, billing, claims, reinsurance, internal, vendor, insurer conduct) by country, line, LOB, product, module, object and perpetrator, with red flags, detection rule, prevention control, trigger action and monitoring KPI |
| `data.py` | Synthetic book (US, Canada, UK, India): policies, objects, parties, employees, agents, vendors, billing, claims, payments, invoices, reinsurance, with 92 planted scenarios and an answer key |
| `engine.py` | 34 live rules (rules, anomaly, network rings, external data), risk scoring, gate actions, evaluation against the answer key, monthly monitoring |

## Run on your computer

```bash
pip install -r requirements.txt
streamlit run app_canonical.py
```

## Deploy on Streamlit Community Cloud

1. Put this folder in a GitHub repository (for example `si2-demos`).
2. Sign in at https://share.streamlit.io with GitHub and choose **Create app**.
3. Pick the repository, branch `main`, and set **Main file path** to one of the app files above.
4. Under **App URL**, type the planned address (for example `si2-canonical`).
5. Click **Deploy**. Repeat for each app file.

## Optional access code

To require a code before visitors see a demo, open the app's **Settings → Secrets** in Streamlit Cloud and add:

```toml
APP_ACCESS_CODE = "your-code-here"
```

Without this secret the demo is open to anyone with the link.
