"""The settings file is the only place a user's email, folders and keys live; defaults must work without one."""
import json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lib"))
import settings


def test_defaults_without_a_file(tmp_path, monkeypatch):
    monkeypatch.setenv("BUYSIDE_SETTINGS", str(tmp_path / "none.json"))
    monkeypatch.setenv("HOME", str(tmp_path))
    assert settings.research_dir() == str(tmp_path / "Desktop" / "Research")
    assert settings.load()["alpha_vantage_keys"] == []


def test_file_overrides_defaults_and_expands_home(tmp_path, monkeypatch):
    f = tmp_path / "s.json"
    f.write_text(json.dumps({"research_dir": "~/Work/Research"}))
    monkeypatch.setenv("BUYSIDE_SETTINGS", str(f))
    monkeypatch.setenv("HOME", str(tmp_path))
    assert settings.research_dir() == str(tmp_path / "Work" / "Research")


def test_xbrl_cli_default_and_file_override(tmp_path, monkeypatch):
    monkeypatch.setenv("BUYSIDE_SETTINGS", str(tmp_path / "none.json"))
    monkeypatch.setenv("HOME", str(tmp_path))
    assert settings.xbrl_cli() == str(tmp_path / "Desktop" / "edgar-xbrl-financials" / "bin" / "cli.js")
    f = tmp_path / "s.json"
    f.write_text(json.dumps({"xbrl_cli": "~/tools/xbrl/bin/cli.js"}))
    monkeypatch.setenv("BUYSIDE_SETTINGS", str(f))
    assert settings.xbrl_cli() == str(tmp_path / "tools" / "xbrl" / "bin" / "cli.js")
