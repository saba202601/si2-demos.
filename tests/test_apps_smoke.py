"""Every app starts and every step / tab renders without an error (Streamlit AppTest)."""
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
APPS = ["app_hub", "app_canonical", "app_migration", "app_iso_bureau", "app_bureau", "app_rules", "app_rating",
        "app_claims", "app_fraud", "app_roles", "app_rule_studio", "app_canonical_master", "app_bridge", "app_finance"]


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("SI2_STATE_DB", str(tmp_path / "state.db"))
    monkeypatch.setenv("SI2_BUREAU_DB", str(tmp_path / "iso.db"))
    monkeypatch.setenv("SI2_FIN_DB", str(tmp_path / "finance.db"))
    monkeypatch.setenv("SI2_FIN_BACKEND", "sqlite")
    monkeypatch.chdir(ROOT)
    from si2_common import store
    store._CON.clear()


@pytest.mark.parametrize("app", APPS)
def test_app_renders(app):
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(str(ROOT / f"{app}.py"), default_timeout=240)
    at.run()
    assert not at.exception, at.exception[0].message
    nav = [r for r in at.radio if r.key in ("step", "step_bureau", "step_fraud", "step_mig", "page", "studio_page", "cm_page", "bridge_page")]
    for value in (nav[0].options if nav else []):
        at.radio(key=nav[0].key).set_value(value).run()     # fresh element: pages drop their own widgets
        assert not at.exception, f"{app} · {value}: {at.exception[0].message}"


def test_si2_studio_runs_every_engine_in_one_app():
    """One SI² Studio: every engine opens from its menu, and moving between engines keeps each one's own state."""
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(str(ROOT / "si2_studio.py"), default_timeout=300)
    at.run()
    assert not at.exception, at.exception[0].message
    order = ["app_hub.py", "app_roles.py", "app_canonical.py", "app_migration.py", "app_iso_bureau.py", "app_bureau.py", "app_rules.py",
             "app_rating.py", "app_claims.py", "app_fraud.py", "app_rule_studio.py", "app_canonical_master.py", "app_bridge.py", "app_finance.py"]
    for page in order + list(reversed(order)):                # there and back: no engine may trip over another's state
        at.switch_page(page).run()
        assert not at.exception, f"{page}: {at.exception[0].message}"
