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
