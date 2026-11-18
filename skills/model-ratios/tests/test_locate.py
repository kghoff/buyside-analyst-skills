import json
import os
from locate_model import find_model


def test_finds_model_and_gather_folder(tmp_path, mod_path):
    d = tmp_path / "Desktop" / "Research" / "TEST"
    d.mkdir(parents=True)
    os.rename(mod_path, d / "TEST_model.xlsx")
    (d / "_manifest.json").write_text(json.dumps({"ticker": "TEST", "items": {}}))
    res = find_model("TEST", home=str(tmp_path))
    assert res["status"] == "found" and res["model"] == str(d / "TEST_model.xlsx")
    assert res["src"] == str(d) and res["work"] == str(d / "_model_work")


def test_source_subfolder_layout(tmp_path, mod_path):
    d = tmp_path / "Downloads" / "Models" / "TEST"
    (d / "Source Data : Reading").mkdir(parents=True)
    os.rename(mod_path, d / "TEST_model.xlsx")
    (d / "Source Data : Reading" / "_manifest.json").write_text(json.dumps({"ticker": "TEST", "items": {}}))
    res = find_model("TEST", home=str(tmp_path))
    assert res["src"] == str(d / "Source Data : Reading")


def test_no_model_means_build_first(tmp_path):
    assert find_model("TEST", home=str(tmp_path)) == {"status": "build"}


def _copy(src, dest, mtime):
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(open(src, "rb").read())
    os.utime(dest, (mtime, mtime))
    return str(dest)


def test_newest_model_wins_outside_research(tmp_path, mod_path, monkeypatch):
    # An old copy on the Desktop (e.g. a repo example) must not shadow the model the user saved most recently,
    # even when that one sits in Downloads under a personal file name.
    import locate_model
    monkeypatch.setattr(locate_model.settings, "research_dir", lambda: str(tmp_path / "home" / "Research"))
    _copy(mod_path, tmp_path / "home" / "Desktop" / "repo" / "examples" / "TEST" / "TEST_model.xlsx", 1_000_000)
    new = _copy(mod_path, tmp_path / "home" / "Downloads" / "Models" / "TEST" / "test_model_v2.xlsx", 2_000_000)
    assert find_model("TEST", home=str(tmp_path / "home"))["model"] == new


def test_research_folder_wins_even_if_older(tmp_path, mod_path, monkeypatch):
    # Every model lives in <research_dir>/<TICKER>; a stray newer copy elsewhere must not take over.
    import locate_model
    monkeypatch.setattr(locate_model.settings, "research_dir", lambda: str(tmp_path / "home" / "Research"))
    kept = _copy(mod_path, tmp_path / "home" / "Research" / "TEST" / "TEST_model.xlsx", 1_000_000)
    _copy(mod_path, tmp_path / "home" / "Downloads" / "TEST_model.xlsx", 2_000_000)
    assert find_model("TEST", home=str(tmp_path / "home"))["model"] == kept


def test_other_tickers_models_ignored(tmp_path, mod_path, monkeypatch):
    # TESTX_model.xlsx belongs to another ticker, not TEST.
    import locate_model
    monkeypatch.setattr(locate_model.settings, "research_dir", lambda: str(tmp_path / "home" / "Research"))
    _copy(mod_path, tmp_path / "home" / "Desktop" / "TESTX_model.xlsx", 2_000_000)
    assert find_model("TEST", home=str(tmp_path / "home")) == {"status": "build"}
