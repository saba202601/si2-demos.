"""Client workspaces, backup / restore, scheduled backup, version and disclaimer."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from si2_common import store  # noqa: E402


@pytest.fixture(autouse=True)
def state_db(tmp_path, monkeypatch):
    monkeypatch.setenv("SI2_STATE_DB", str(tmp_path / "state.db"))
    monkeypatch.delenv("SI2_WORKSPACE", raising=False)
    monkeypatch.delenv("SI2_WORKSPACES", raising=False)
    store._CON.clear()
    yield
    store._CON.clear()


def test_workspaces_are_separate(monkeypatch):
    store.save("rating", "k", store.dumps({"a": 1}), "Ann")
    monkeypatch.setenv("SI2_WORKSPACE", "acme")
    assert store.load("rating") == {}
    store.save("rating", "k", store.dumps({"a": 2}), "Ann")
    store.request("rating", "K", "r", "s", {}, "Ann")
    assert store.workspaces() == ["acme", "demo"]
    monkeypatch.setenv("SI2_WORKSPACES", "acme")
    assert store.workspaces() == ["acme"]


def test_backup_restore_round_trip(monkeypatch):
    store.save("rules", "rules", store.dumps({"r": [1, 2]}), "Ann")
    rid = store.request("rules", "Rule set change", "rules", "s", {"x": 1}, "Ann")
    store.decide("rules", rid, "Bob", True, "ok")
    text = store.export_workspace("demo")
    assert json.loads(text)["format"] == store.BACKUP_FORMAT
    res = store.import_workspace(text, "copy")
    assert res == {"workspace": "copy", "state": 1, "approvals": 1}
    monkeypatch.setenv("SI2_WORKSPACE", "copy")
    assert store.loads(store.load("rules")["rules"]) == {"r": [1, 2]}
    assert store.approvals("rules")[0]["checker"] == "Bob"
    with pytest.raises(ValueError):
        store.import_workspace(json.dumps({"format": "other"}))


def test_scheduled_backup_keeps_newest(tmp_path):
    from tools.backup_state import run
    store.save("x", "k", store.dumps(1), "me")
    out = tmp_path / "bk"
    for _ in range(3):
        files = run(str(out), keep=2)
    assert any(f.name == "si2_state.db" for f in files) and len([d for d in out.iterdir()]) <= 2


def test_version_and_disclaimer():
    from si2_common import branding
    assert branding.VERSION.count(".") == 2
    assert "not affiliated" in branding.DISCLAIMER and "NCCI" in branding.DISCLAIMER
