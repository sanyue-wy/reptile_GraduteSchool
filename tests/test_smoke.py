"""Offline import, CLI help and Flask smoke checks; no collection starts."""
import importlib
import runpy
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize("module", ["services.crawler_service", "services.merge_service", "services.export_service",
    "storage", "spiders.engine", "security.plugin_validator", "utils.http"])
def test_core_module_imports(module):
    assert importlib.import_module(module).__name__ == module


def test_cli_help_exits_before_collection(monkeypatch, capsys, isolated_workspace):
    main_path = Path(__file__).resolve().parents[1] / "main.py"
    monkeypatch.setattr(sys, "argv", [str(main_path), "--help"])
    with pytest.raises(SystemExit) as result:
        runpy.run_path(str(main_path), run_name="__main__")
    assert result.value.code == 0
    text = capsys.readouterr().out
    assert all(flag in text for flag in ("--school", "--source", "--resume", "--retry-failed", "--workers"))
    assert not list((isolated_workspace / "data/output").glob("*.jsonl"))


def test_flask_overview_and_empty_tutors(monkeypatch):
    from api.server import app
    monkeypatch.setitem(app.config, "TESTING", True)
    with app.test_client() as client:
        overview = client.get("/api/overview")
        assert overview.status_code == 200
        assert overview.get_json()["code"] == 0
        tutors = client.get("/api/tutors").get_json()
        assert tutors["code"] == 0 and tutors["data"]["total"] == 0
