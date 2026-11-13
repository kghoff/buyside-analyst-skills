import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import pytest
import fetch


def test_missing_xbrl_tool_stops_with_setup_instructions(tmp_path, monkeypatch):
    # Without this message the user would see a bare "node: file not found" halfway through a fetch.
    monkeypatch.delenv("IPNL_XBRL_CLI", raising=False)
    monkeypatch.setenv("BUYSIDE_SETTINGS", str(tmp_path / "s.json"))
    (tmp_path / "s.json").write_text('{"xbrl_cli": "%s"}' % (tmp_path / "nope" / "cli.js"))
    with pytest.raises(SystemExit) as e:
        fetch.xbrl_cli()
    assert "clone github.com/kghoff/edgar-xbrl-financials" in str(e.value) and "xbrl_cli" in str(e.value)


def test_environment_variable_overrides_the_setting(tmp_path, monkeypatch):
    cli = tmp_path / "cli.js"
    cli.write_text("")
    monkeypatch.setenv("IPNL_XBRL_CLI", str(cli))
    assert fetch.xbrl_cli() == str(cli)
