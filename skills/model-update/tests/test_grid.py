import grid


def test_dump_reads_cached_values_of_every_sheet(model):
    """match.py and verify.py read values, never formulas: a formula cell with no cached value is None, not a string."""
    g = grid.dump(model)
    assert g["MOD"]["F4"] == 120 and g["MOD"].get("L4") is None and g["MOD"]["L2"] == "Q3 26E"
    assert "Earnings" in g


def test_errors_lists_error_cells():
    assert grid.errors({"MOD": {"A1": 1, "B2": "#REF!"}, "X": {"C3": "#DIV/0!"}}) == ["MOD!B2", "X!C3"]
