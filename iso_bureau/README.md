# SI² ISO Bureau Reporting: all lines

The SME selects the **line of business**, the **bureau** and the **accounting period**. The system then generates, validates and submits the ISO 150-byte statistical file. Every object the engine uses has an effective date and an expiration date, and the SME must approve it first. That covers layouts, fields, canonical elements, business descriptions, source mappings, aliases, pick lists, options, ISO codes, and derivation, validation and transformation rules.

Lines loaded from the three ISO workbooks: 10 lines, each with a Premium and a Loss layout (20 layouts).

| Code | Line | Code | Line |
|---|---|---|---|
| PA | Personal Auto (AL / AN / AP) | GL | Commercial General Liability |
| HO | Homeowners | IM | Inland Marine |
| CA | Commercial Auto (AL / AN / AP) | CR | Commercial Crime |
| CP | Commercial Property | BP | Businessowners (BOP) |
| FI | Fidelity & Forgery | BR | Builders Risk |

## Run it

```bash
pip install -r requirements.txt                    # from the repo root
streamlit run app_iso_bureau.py
python -m iso_bureau.seed --demo-approve           # optional: rebuild iso_bureau/data/bureau_reporting.db
python -m pytest -q iso_bureau/tests               # 35 end-to-end tests
```

* `python -m iso_bureau.seed` without the flag loads **everything as PENDING**. Use it for real SME onboarding.
* `--demo-approve` approves the 2020 baseline as "Demo SME". The proposed **2027 changes stay PENDING** so the SME can see the approval workflow.
* The app builds the demo database on first start if it is missing. Set `SI2_BUREAU_DB` to point it at another file.

## How a run works

```
Source (Guidewire / Duck Creek / legacy)
   │  source_mapping           attribute  → canonical element
   │  picklist_option_alias    source code → canonical option
   ▼
Canonical record ── DERIVATION rules (LOB, AL/AN/AP from coverage, filler …)
   │             ── VALIDATION rules (term, ZIP, loss in period, closed = 0 reserve …)
   ▼
ISO layout (effective-dated) ── TRANSFORMATION rule per field
   │  bureau_code_map   canonical option → ISO code
   ▼
150-byte record → flat file → ISO acknowledgment → corrections → resubmission → close
```

| Step | Status | What happens |
|---|---|---|
| 1 Generate | GENERATED | Readiness check (everything approved?), source → canonical → 150 bytes |
| 2 Validate | VALIDATED | Approved validation rules run; records become VALID / WARNING / ERROR |
| 3 SME approve | SME_APPROVED | SME signs off the control totals; ERROR records are **held** for correction |
| 4 Submit | SUBMITTED → ACCEPTED / PARTIALLY_ACCEPTED | Flat file built; ISO response (simulated: duplicates rejected) |
| Corrections | | SME fixes the source value (a new linked row, so the original is kept) or adds a missing alias, then creates a resubmission batch |
| 5 Close | CLOSED | Allowed when all items are resolved, or with an SME reason |

**Sandbox:** the SME can preview a run with PENDING metadata, for example a 2027 layout that is not yet approved. Sandbox batches can never be submitted.

## Effective dating

| Object | Resolved on |
|---|---|
| Layout version and its fields | accounting **period end** date |
| Canonical elements, source mappings | accounting period end date |
| Pick-list options, aliases, ISO code maps, business rules | each transaction's **code date** (policy effective date for ISO; otherwise loss date) |

To change anything, add a new record with a later effective date ("supersede"). The current record stays in force until the SME **approves** the new one. Approval then sets the old record's expiration to the day before. A rejected change leaves the current record untouched, so there is never a gap. Nothing is ever deleted or overwritten. The only in-place updates are workflow status and the expiration date set on approval, and both are logged in `approval_log`.

The demo database includes two proposed 2027 changes that are waiting for SME approval:

1. **Personal Auto premium layout v2** (effective 2027-01-01). It adds a Telematics indicator (position 87) and a Rideshare indicator (position 88), cut out of the ISO extension area. It comes with the new elements, the YES_NO pick list, source mappings and ISO codes.
2. **Homeowners water split.** WATER expires for HO, and WATERW (13) and WATERN (14) start on 2027-01-01, with Guidewire aliases.

Open the **SME Validation Workbench** with *As of = 2027-01-15*. Approve the lineage, then run January 2027.

## App pages

| Page | Purpose |
|---|---|
| Dashboard | Pending approvals, batches, layout import findings |
| Bureau Run | Select line, bureau and period. Generate, validate, SME approve, submit, close. Record inspector (bureau ↔ canonical ↔ source, field by field) and a flat-file viewer with a position ruler |
| Corrections & Resubmit | Held and rejected records: edit source values, map unknown codes, build the resubmission batch, close |
| **SME Validation Workbench** | One row per bureau field: position, bureau field and description, canonical element and business description, Guidewire and Duck Creek attributes, derivation, pick list, transformation and validation rules, aliases, and approval status of every piece. Approve or reject the whole lineage in one action |
| Layouts | Versions by effective and expiration date, field list with position check, version compare, new version editor, import of an ISO layout workbook |
| Canonical Model / Pick Lists / Business Rules | Effective-dated lists with history, add new, change (supersede), and a rule tester |
| Approval Queue | Everything pending, by table, with bulk approve or reject |
| SME Templates | Download the template, fill in new records only, upload. The system adds keys, status and audit columns, then checks keys and overlaps |
| Audit Trail | Approvals, expirations, batch lifecycle, source corrections |
| Canonical Gaps | Every source attribute, source code, layout field and ISO code the canonical model lacks, each with a complete draft. Three buttons: Map to existing, Add new, Not needed, plus bulk add. Shared with the Migration app (`si2_common/gaps.py`, `gaps_ui.py`) |
| Data | Browse any table, download it as CSV, export every table to one Excel workbook, or download the SQLite database file |

## Findings from the supplied layouts (for the SME)

* All 20 layouts add up to exactly 150 bytes.
* **Commercial Auto workbook:** Excel converted the Position column for fields 1 to 4 into dates (`1-2` became 2026-01-02). The import recomputes positions from the field lengths and flags the problem on the layout version.
* Eighty-eight different bureau field names (for example "Accounting Date" and "Accounting / Transaction Date") map to 42 canonical elements. The bureau names are stored as element aliases.

## Important: codes are placeholders

The ISO line codes, transaction, cause-of-loss, deductible, limit and other code values come from the descriptions in the supplied layouts or are placeholders. They must be confirmed against the carrier's licensed ISO statistical plan manuals before production use, and that is exactly what the SME approval step is for. The ISO acknowledgment is simulated: it rejects duplicate records only.

## SQL Server Express

`python iso_bureau/sql/make_sqlserver.py` regenerates:

* `iso_bureau/sql/01_create_ISOBureauReporting.sql`: the database and all tables
* `iso_bureau/sql/02_load_metadata.sql`: layouts, canonical model, pick lists, rules, approvals
* `iso_bureau/sql/03_load_sample_source.sql`: sample source transactions

Run them in SSMS against `SABAHOME\SQLEXPRESS02`. They create a separate database, **ISOBureauReporting**, so your Workers Comp `BureauReporting` database is untouched. Loaded and verified on SQLEXPRESS02 on 2026-10-12.

### Run the app on SQL Server (desktop)

Double-click **`run_iso_bureau_sqlserver.bat`** in the repo root. It installs the Python packages (including `pyodbc`), checks the connection, then opens the app on `ISOBureauReporting` with Windows Authentication. Or by hand:

```bat
set SI2_BUREAU_BACKEND=mssql
set SI2_MSSQL_SERVER=SABAHOME\SQLEXPRESS02
set SI2_MSSQL_DATABASE=ISOBureauReporting
python -m iso_bureau.check_sqlserver
python -m streamlit run app_iso_bureau.py
```

The driver is picked automatically from: ODBC Driver 18, 17, 13, SQL Server Native Client 11.0, SQL Server. Without `SI2_BUREAU_BACKEND` the app uses its built-in SQLite demo database (that is what Streamlit Cloud runs). The sidebar shows which database is in use.

## Files

```
app_iso_bureau.py            Streamlit app (repo root, uses si2_common branding + access code)
iso_bureau/layouts.py        ISO workbook parser + position audit
iso_bureau/catalog.py        starter canonical model, pick lists, ISO codes, aliases, rules (JSON)
iso_bureau/seed.py           builds the database + sample Guidewire / Duck Creek transactions
iso_bureau/engine.py         resolve -> canonical -> derive -> validate -> format -> batch lifecycle
iso_bureau/lineage.py        SME workbench lineage + one-click approval
iso_bureau/templates.py      SME upload templates
iso_bureau/db.py             schema, effective dating, supersede / approve, audit
iso_bureau/gaps.py           Canonical Gaps adapter for bureau reporting
si2_common/gaps.py           shared gap logic: naming standard, matching, drafted proposals
si2_common/gaps_ui.py        shared Canonical Gaps screen (also used by app_migration.py)
migrate/gaps.py              Canonical Gaps adapter for the migration workbench
iso_bureau/tests/            35 tests (engine + Canonical Gaps for ISO and Migration)
iso_bureau/sql/              SQL Server Express scripts
iso_bureau/templates/        blank SME upload template
iso_bureau/data/iso_layouts/ the three ISO layout workbooks
```
