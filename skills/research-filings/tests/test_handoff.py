import csv, os

import handoff
from handoff import _auto_axis, guide_paths, _table_rows


def _guides(tmp_path, rows):
    d = tmp_path / "readers" / "s01"
    d.mkdir(parents=True)
    with open(d / "guidance.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["fiscal_year", "metric", "basis", "kind", "date", "low", "high", "actual", "source"])
        w.writerows(rows)
    return str(tmp_path)


def test_guide_path_keeps_each_change_and_drops_actuals(tmp_path):
    # the user wants every revision of a guide; a "guide" dated after the year ended is the actual, not a guide
    work = _guides(tmp_path, [
        ["2025", "revenue ($M)", "reported", "hard", "2025-01-13", "4600", "4600", "", "rel A"],
        ["2025", "revenue ($M)", "reported", "soft", "2025-02-13", "4600", "4600", "", "deck B"],     # repeat: dropped
        ["2025", "Revenue ($B)", "reported", "hard", "2025-07-30", "4.600", "4.625", "", "rel C"],   # $B scaled
        ["FY2025", "revenue ($M)", "reported", "hard", "2025-10-30", "4630", "4650", "", "rel D"],
        ["2025", "revenue ($M)", "reported", "hard", "2026-01-12", "4662", "", "", "prelim"],        # after year end
        ["2025", "revenue ($M) long-range target", "reported", "hard", "2023-06-23", "4000", "4500", "", "LRP"]])
    spec = {"names": ["revenue ($M)", "Revenue ($B)"], "scale": {"Revenue ($B)": 1000}, "basis": ["reported"]}
    p = guide_paths(work, spec, 2025)[2025]
    assert [(d, lo, hi) for d, lo, hi, _ in p] == [("2025-01-13", 4600, 4600), ("2025-07-30", 4600, 4625),
                                                  ("2025-10-30", 4630, 4650)]


def test_alpha_axis_matches_excels_automatic_range():
    # annotation arrows are placed by value: the axis bounds must be the ones Excel draws (-100% to 150% for DXCM)
    assert _auto_axis(-0.7105, 1.2854) == (-1.0, 1.5)


def test_an_annotation_table_ends_at_its_first_undated_row():
    # the Idio Chart has an up-days table and, below it, a down-days table: each header owns only its own rows
    cells = {"W7": 43000.0, "W8": 43001.0, "V30": "Top 20 DOWN days", "W32": 43100.0}
    assert list(_table_rows(cells, "W", 6)) == [7, 8]


def test_alpha_points_come_from_the_charts_own_cache():
    """A fresh /model-price-history build (its refresh) has formulas with no cached results yet; the chart's own cache
    holds exactly what it plots, so the research notes can be placed without Excel opening the file first."""
    xml = ('<c:chart><c:ser><c:cat><c:numRef><c:f>\'Px Data\'!$A$5:$A$6</c:f><c:numCache>'
           '<c:pt idx="0"><c:v>45658</c:v></c:pt><c:pt idx="1"><c:v>45665</c:v></c:pt></c:numCache></c:numRef></c:cat>'
           '<c:val><c:numRef><c:f>\'Px Data\'!$B$5:$B$6</c:f><c:numCache>'
           '<c:pt idx="0"><c:v>0.1</c:v></c:pt><c:pt idx="1"><c:v>0.4</c:v></c:pt></c:numCache></c:numRef></c:val></c:ser></c:chart>')
    (dates, vals), axis = handoff.alpha_series("no-such-workbook.xlsx", xml)
    assert [d.isoformat() for d in dates] == ["2025-01-01", "2025-01-08"] and vals == [0.1, 0.4]
    assert axis == handoff._auto_axis(0.1, 0.4)


def test_event_moves_read_the_stocks_own_move_under_a_ticker_neutral_key():
    # the handoff JSON is written for any company; a key named after one ticker leaves every other company's
    # typed move ignored (it fell back to a Px Events lookup that misses events not in that tab)
    from handoff import _event_moves
    assert _event_moves({"stock": -0.065, "spy": -0.007, "idio": -0.058}) == {"B": -0.065, "C": -0.007, "D": -0.058}
    assert _event_moves({"date": "2025-11-19"}) == {"B": None, "C": None, "D": None}


def test_sector_header_matches_old_and_new_wording():
    # Old models say 'XHE close (stooq adj.)', models built after the Yahoo switch 'XHE close (dividends in)'.
    import re
    import handoff
    for h in ("XHE close (stooq adj.)", "XHE close (dividends in)"):
        assert re.match(handoff.SECTOR_HDR, h).group(1) == "XHE"
