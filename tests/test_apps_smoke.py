"""Every app starts and every step / tab renders without an error (Streamlit AppTest)."""
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
APPS = ["app_hub", "app_canonical", "app_migration", "app_iso_bureau", "app_bureau", "app_rules", "app_rating",
        "app_claims", "app_fraud", "app_roles"]


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("SI2_STATE_DB", str(tmp_path / "state.db"))
    monkeypatch.setenv("SI2_BUREAU_DB", str(tmp_path / "iso.db"))
    monkeypatch.chdir(ROOT)
    from si2_common import store
    store._CON.clear()


@pytest.mark.parametrize("app", APPS)
def test_app_renders(app):
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(str(ROOT / f"{app}.py"), default_timeout=240)
    at.run()
    assert not at.exception, at.exception[0].message
    nav = [r for r in at.radio if r.key in ("step", "page")]
    for value in (nav[0].options if nav else []):
        nav[0].set_value(value).run()
        assert not at.exception, f"{app} · {value}: {at.exception[0].message}"
