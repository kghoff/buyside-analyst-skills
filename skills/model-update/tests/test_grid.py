import grid


def test_dump_reads_cached_values_of_every_sheet(model):
    """match.py and verify.py read values, never formulas: a formula cell with no cached value is None, not a string."""
    g = grid.dump(model)
    assert g["MOD"]["F4"] == 120 and g["MOD"].get("L4") is None and g["MOD"]["L2"] == "Q3 26E"
    assert "Earnings" in g


def test_errors_lists_error_cells():
    assert grid.errors({"MOD": {"A1": 1, "B2": "#REF!"}, "X": {"C3": "#DIV/0!"}}) == ["MOD!B2", "X!C3"]


def test_recalc_into_the_models_own_folder_is_refused(model, tmp_path):
    """LibreOffice writes <recalc dir>/<same file name>: recalculating into the model's folder would overwrite the
    user's workbook, which the user owns. Refuse before LibreOffice starts."""
    import os
    import pytest
    before = open(model, "rb").read()
    with pytest.raises(SystemExit):
        grid.dump(model, os.path.dirname(model))
    with pytest.raises(SystemExit):
        grid.dump(model, os.path.dirname(model) + "/.")
    assert open(model, "rb").read() == before
