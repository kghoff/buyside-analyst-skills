import json
import os

import frozen
import make_fixture as mf


def test_band_7_for_this_quarter_is_used_and_left_alone(model, tmp_path):
    r = frozen.ensure(model, "Q3 26E", {}, str(tmp_path))
    assert r["source"] == "band7" and not os.path.exists(tmp_path / "preprint.json")


def test_without_band_7_for_this_quarter_the_forecast_is_saved_first(tmp_path):
    """Entering actuals overwrites the forecast; 'what we expected' must survive somewhere."""
    p = mf.model(str(tmp_path / "m.xlsx"), frozen_quarter="Q2 26E")
    g = {"L4": 132.0, "N4": 500.0, "L7": 79.2, "N7": 300.0}
    r = frozen.ensure(p, "Q3 26E", g, str(tmp_path))
    pre = json.load(open(tmp_path / "preprint.json"))
    assert r["source"] == "preprint" and pre["rows"]["INCOME STATEMENT | Revenue"] == {"q": 132.0, "fy": 500.0}


def test_actual_vs_frozen_table_lines_up_by_label(model):
    rows = frozen.table(frozen.read(model, "Q3 26E", {}, None), {"L4": 140.0, "L7": 88.0, "L12": 1.2}, model, "L")
    assert rows[0] == {"label": "Revenue", "frozen": 132.0, "actual": 140.0, "diff": 8.0}


def test_a_placeholder_is_not_shown_as_the_actual(model):
    """A placeholder equals the forecast, so 'actual vs frozen' would show a zero surprise that never happened."""
    rows = frozen.table(frozen.read(model, "Q3 26E", {}, None), {"L4": 132.0, "L7": 88.0}, model, "L", {"L4"})
    assert rows[0] == {"label": "Revenue", "frozen": 132.0, "actual": None, "diff": None}


def test_a_band_7_line_with_no_mod_row_says_so_instead_of_a_blank(model):
    """A blank actual reads as 'not reported yet'; a band-7 label MOD no longer has (renamed since the preview) is a
    different thing the user should see, so the table names it."""
    rows = frozen.table([{"label": "Billings", "q": 150.0}], {"L4": 140.0}, model, "L")
    assert rows == [{"label": "Billings", "frozen": 150.0, "actual": "no MOD row", "diff": None}]
