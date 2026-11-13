"""compare() must catch cells ADDED to an old tab and unexpected new tabs, not only changed ones (no false pass)."""
import xlverify


def test_added_cell_in_existing_tab_is_reported():
    d = xlverify.compare({"MOD": {(1, 1): 5}}, {"MOD": {(1, 1): 5, (2, 2): 7}})
    assert d and "added" in d[0][1]


def test_added_cell_allowed_when_written_or_allow_callback():
    b, a = {"MOD": {(1, 1): 5}}, {"MOD": {(1, 1): 5, (2, 2): 7}}
    assert xlverify.compare(b, a, written={"MOD": {(2, 2)}}) == []
    assert xlverify.compare(b, a, allow=lambda t, r, c: (r, c) == (2, 2)) == []


def test_added_cell_respects_row_inserts():
    b = {"MOD": {(5, 1): 1}}
    a = {"MOD": {(7, 1): 1}}
    assert xlverify.compare(b, a, inserts=[("MOD", 3, 2)]) == []


def test_unexpected_new_tab_reported_unless_listed():
    b, a = {"MOD": {(1, 1): 5}}, {"MOD": {(1, 1): 5}, "DCF": {(1, 1): 1}}
    assert xlverify.compare(b, a)
    assert xlverify.compare(b, a, new_tabs={"DCF"}) == []
