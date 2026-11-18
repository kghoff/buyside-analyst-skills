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


def test_price_fetch_copies_match_model_price_history():
    # House rule: shared helpers are copies; a drifted copy would fetch peers differently from the subject.
    import filecmp
    here = os.path.join(os.path.dirname(__file__), "..", "scripts")
    there = os.path.join(os.path.dirname(__file__), "..", "..", "model-price-history", "scripts")
    for f in ("pricecsv.mjs", "fetch_prices.mjs"):
        assert filecmp.cmp(os.path.join(here, f), os.path.join(there, f), shallow=False), f
