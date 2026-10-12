# SI² security and compliance

* **Data stays with the carrier**: SI² stores decisions, approvals and loaded data in the carrier's SQL Server or
  PostgreSQL (`SI2_STATE_BACKEND`, see `.streamlit/secrets.toml.example`). The public demos use synthetic data only.
* **Sign-in**: OpenID Connect single sign-on (Microsoft Entra ID, Okta, Google ...) via Streamlit's `st.login`;
  MFA is enforced by the identity provider. Without SSO configured the demos run in demo mode with typed names.
* **Two-person rule** on rating factors, rule sets, claims routing settings and SIU releases, fraud payment releases,
  initial-load plans, NCCI submissions, company-model changes and migration sign-off (`si2_common/approvals_ui.py`).
* **Personal data** (SSN/TIN, DOB, driver's license, email, phone, names, addresses) is detected and masked unless the
  role is Data steward (`migrate/initial_load.py`: `pii_kind`, `mask`).
* **Audit and history**: every decision is logged; records are versioned with effective dates, never deleted.
* **Uploaded SQL / PL-SQL is parsed, never executed.** Stored state is tagged JSON, never unpickled.
* **AI** (optional, `ANTHROPIC_API_KEY`): only masked profiles, counts and codes are sent; suggestions need SME approval.
* **Regulation**: controls support NAIC Insurance Data Security Model Law #668 (§4 program, §5 investigation,
  §6 72-hour commissioner notice) and NYDFS 23 NYCRR 500 (500.6, 500.7, 500.11, 500.12, 500.15, 500.17).
* **Roadmap**: SOC 2 Type II, independent penetration test, data processing agreement template.

Report a vulnerability: hello@si2insure.com
