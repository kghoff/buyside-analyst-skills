import tieout


def _res():
    return {"matched": [{"row": 4, "key": "INCOME STATEMENT | Revenue", "label": "Revenue", "cur": 140.0, "tol": 0.05,
                         "file": "r.md", "lineno": 14},
                        {"row": 7, "key": "INCOME STATEMENT | Gross profit", "label": "Gross profit", "cur": 88.0,
                         "tol": 0.05, "file": "r.md", "lineno": 16}], "combined": []}


def test_a_subtotal_that_does_not_tie_stops_the_run():
    """A formula skeleton that disagrees with the release means a line is on the wrong row."""
    miss = tieout.check(_res(), {"L4": 140.0, "L7": 87.0}, "L")
    assert miss == [{"ref": "L7", "label": "Gross profit", "release": 88.0, "model": 87.0, "file": "r.md", "lineno": 16}]


def test_rounding_inside_the_printed_precision_ties():
    assert tieout.check(_res(), {"L4": 140.04, "L7": 88.0}, "L") == []


def test_a_q4_print_ties_the_full_year_column_too():
    """The release prints the year; if the FY cell drifted from it, the Q4 plug or the year structure is wrong."""
    res = _res()
    res["matched"][0]["fy_cur"] = 500.0
    assert tieout.check(res, {"L4": 140.0, "L7": 88.0, "N4": 500.0}, "L", "N") == []
    miss = tieout.check(res, {"L4": 140.0, "L7": 88.0, "N4": 499.0}, "L", "N")
    assert [(x["ref"], x["release"], x["model"]) for x in miss] == [("N4", 500.0, 499.0)]


def test_without_a_fy_column_the_year_is_not_checked():
    res = _res()
    res["matched"][0]["fy_cur"] = 500.0
    assert tieout.check(res, {"L4": 140.0, "L7": 88.0}, "L") == []


def test_a_cell_that_waits_for_the_10q_is_not_a_miss():
    """Awaiting cells are blank on purpose; flagging them would stop every print-night run."""
    res = _res()
    res["matched"][0]["fy_cur"] = 500.0
    assert tieout.check(res, {"L7": 88.0}, "L", "N", waiting={"L4", "N4"}) == []
