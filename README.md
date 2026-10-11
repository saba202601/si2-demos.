# SI² Demo Apps

Five Streamlit demos for **SI² · Super Intelligence for Insurance** (https://si2insure.com).
All data is synthetic. Codes, record layouts and rating factors are illustrative.

| App file | Demo | Planned address |
|---|---|---|
| `app_canonical.py` | Canonical Data Model | https://si2-canonical.streamlit.app |
| `app_bureau.py` | Bureau Reporting Workbench (WCSTAT, WCPOLS, WCIND, WCMED) | https://si2-bureau.streamlit.app |
| `app_rules.py` | Business Rule Engine | https://si2-rules.streamlit.app |
| `app_rating.py` | Rating Engine | https://si2-rating.streamlit.app |
| `app_claims.py` | Claims Triage | https://si2-claims.streamlit.app |

Shared code lives in `si2_common/` (branding, access code, synthetic data, rule evaluator).

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
