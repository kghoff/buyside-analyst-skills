import json
import os

from conftest import FIX


def test_fixtures_present():
    # The build tests need a real model, real XBRL output and a real multpl page; fail loudly if any is missing.
    for f in ("reference_model.xlsx", "abt_xbrl.json", "multpl.html", "brett_pull.csv"):
        assert os.path.getsize(os.path.join(FIX, f)) > 0, f
    assert len(json.load(open(os.path.join(FIX, "abt_xbrl.json")))["quarterly"]) >= 4


def test_helpers_import():
    import lo, modmap, notebox, prices, xlsx  # noqa: F401
