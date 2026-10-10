# SI² Demo Apps

Five Streamlit demos for **SI² · Super Intelligence for Insurance** (https://si2insure.com).
All data is synthetic. Codes, record layouts and rating factors are illustrative.

| App file | Demo | Planned address |
|---|---|---|
| `app_canonical.py` | Canonical Data Model | https://si2-canonical.streamlit.app |
| `app_bureau.py` | Bureau Statistical Reporting | https://si2-bureau.streamlit.app |
| `app_rules.py` | Business Rule Engine | https://si2-rules.streamlit.app |
| `app_rating.py` | Rating Engine | https://si2-rating.streamlit.app |
| `app_claims.py` | Claims Triage | https://si2-claims.streamlit.app |

Shared code lives in `si2_common/` (branding, access code, synthetic data, rule evaluator).

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
