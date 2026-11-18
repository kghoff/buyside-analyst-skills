# tests/test_verify.py
"""verify is the gate before the user's file is replaced: it must pass a good build and catch each kind of damage."""
import json
import os

import openpyxl
import pytest

import build
import verify

pytestmark = pytest.mark.slow   # starts LibreOffice (run-tests.sh --full)


@pytest.fixture
def built(model, work, tmp_path):  # noqa: F811
    out = str(tmp_path / "out.xlsx")
    build.build(model, work, "TEST", out)
    return model, out, work


def test_good_build_passes(built):
    r = verify.run(*built)
    assert r["ok"], r
    assert set(r) == {"checked", "failed", "errors", "changed_parts", "colours", "pairing", "dcf", "anchors", "png",
                      "recalculated", "ok"}
    assert r["png"].endswith("valuation.png") and os.path.exists(r["png"])


def test_dcf_retype_catches_wrong_scenario_value(built):
    model, out, work = built
    p = json.load(open(os.path.join(work, "valuation_plan.json")))
    p["scenarios"]["final"]["base"]["value_per_share"] += 1.0
    json.dump(p, open(os.path.join(work, "valuation_plan.json"), "w"))
    assert any("base" in x for x in verify.run(model, out, work)["dcf"])


def test_colour_check_catches_a_black_input(built, tmp_path):
    model, out, work = built
    lay = json.load(open(os.path.join(work, "layout.json")))
    ref = lay["inputs"]["hurdle"]
    bad = str(tmp_path / "bad.xlsx")
    wb = openpyxl.load_workbook(out)
    from openpyxl.styles import PatternFill
    wb["Valuation"][ref].fill = PatternFill()
    wb.save(bad)
    assert any(ref in x for x in verify.colours(bad, work))


def test_expected_none_means_na_not_blank():
    """An empty cell where the math says #N/A means the formula is missing, not that it returned NA()."""
    assert verify.close("#N/A", None)
    assert not verify.close(None, None)


def test_compare_checks_real_numbers(built):
    """A compare that only matched #N/A against None would pass a broken tab; most checked cells must hold a value."""
    model, out, work = built
    r = verify.compare(out, work)
    assert r["failed"] == [] and r["valued"] > 60, r


def test_inherited_na_is_not_an_error(model, work, tmp_path):  # noqa: F811
    """A long whose risk price is above today's price has no downside, so R/R is #N/A and so are the cells built on it
    (verdict and the like). That is a valid model: #N/A is fine wherever the math says None."""
    p = json.load(open(os.path.join(work, "valuation_plan.json")))
    p["inputs"]["risk_multiple.pe"]["value"] = 60.0          # 60 x ~$2.75 = ~$165, well above the ~$88 price
    json.dump(p, open(os.path.join(work, "valuation_plan.json"), "w"))
    out = str(tmp_path / "out.xlsx")
    build.build(model, work, "TEST", out)
    lay = json.load(open(os.path.join(work, "layout.json")))
    assert sum(v is None for v in lay["expected"].values()) >= 2      # R/R and the verdict, at least
    r = verify.compare(out, work)
    assert r["failed"] == [] and r["errors"] == [], r
