"""model_reads.py: the deck's model data, found by label or header in grids laid out like the real tabs."""
import datetime as dt

from openpyxl.utils.cell import coordinate_from_string
from openpyxl.utils.cell import column_index_from_string

import model_reads as M


def grid(cells, rows=60, cols=30):
    """A 0-based grid of rows from {"E3": value}."""
    g = [[None] * cols for _ in range(rows)]
    for ref, v in cells.items():
        col, row = coordinate_from_string(ref)
        g[row - 1][column_index_from_string(col) - 1] = v
    return g


def sum_like():
    """model-summary layout.py's positions: estimates grid E3:J (years in row 4), and on the same header row the
    probability tree (P:U) and the tactical R/R ladder (W:AA)."""
    c = {"E3": "Internal estimates (our model; multiples at today's price and EV)",
         "F4": "2025A", "G4": "2026E", "H4": "2027E", "I4": "2028E",
         "E5": "Revenue", "F5": 1100, "G5": 1250, "H5": 1420, "I5": 1600,
         "E6": "EPS (GAAP, the Street's basis)", "F6": 2.45, "G6": 2.85, "H6": 3.30, "I6": 3.80,
         "E7": "Street EPS", "F7": "n/a", "G7": 2.90, "H7": 3.05, "I7": 3.40,
         "E8": "Expected Delta (ours vs Street)", "F8": "n/a", "G8": -0.017, "H8": 0.082, "I8": 0.118,
         "P3": "1-year return scenarios (Valuation's probability tree)",
         "W3": "Tactical R/R (Valuation's blended ladder)"}
    for col, h in zip("PQRSTU", ("Scenario", "EPS", "P/E", "Target", "% return", "Probability")):
        c[f"{col}4"] = h
    for col, h in zip(("W", "X", "Y", "Z", "AA"), ("% move", "Entry price", "Reward", "Risk", "R/R")):
        c[f"{col}4"] = h
    c.update({"B6": "Cap table ($M except per share)", "B7": "Price (date beside it)", "C7": 72.40,
              "B19": "Buy price", "B20": "No-brainer price", "C20": 55.0,
              "B29": "3-year target price", "C29": 120.0, "B33": "IRR", "C33": 0.1834,
              "B39": "12-month target", "C39": 94.84, "B40": "% return", "C40": 0.31,
              "B46": "Risk price", "C46": 61.54, "B47": "% return", "C47": -0.15})
    return grid(c)


def test_estimates_grid_stops_at_its_own_years():
    # SUM's header row also holds the probability tree and the R/R ladder: those are not estimate years
    hd, rows, colours = M.estimates_grid(sum_like())
    assert hd == ["$M except per share", "2025A", "2026E", "2027E", "2028E"]
    assert all(len(r) == 5 for r in rows)
    assert rows[-1] == ["Expected Delta (ours vs Street)", "n/a", "-1.7%", "+8.2%", "+11.8%"]
    assert colours[(3, 2)] == "bad" and colours[(3, 3)] == "good"


def test_year_headers_typed_as_numbers_count():
    g = sum_like()
    g[3][5:9] = [2025, 2026, 2027, 2028]
    assert M.estimates_grid(g)[0][1:] == ["2025", "2026", "2027", "2028"]


def test_cap_table_scopes_repeated_labels_and_reports_fallbacks():
    numbers = {"buy_price": {"shown": "$69.44"}, "price": {"shown": "$1.00"}}
    rows, fell_back = M.cap_table(sum_like(), numbers)
    got = {a: b for a, b, _ in rows}
    assert got["Price"] == "$72.40"                       # SUM wins when it has the number
    assert got["12-month base return"] == "+31.0%" and got["12-month risk return"] == "-15.0%"
    assert got["Buy price"] == "$69.44" and fell_back == ["buy_price"]   # empty SUM cell: the plan's anchored number


def weekly(gaap):
    c = {"A1": "XYZ multiples", "A2": "Trailing (TTM) multiples as known on each date", "A40": "WEEKLY DATA"}
    heads = ["Week", "Price", "P/E"] + (["P/E (GAAP)"] if gaap else []) + ["S&P 500 P/E", "Core-peer median P/E"]
    for j, h in enumerate(heads):
        c[f"{'ABCDEF'[j]}41"] = h
    for k in range(5):
        vals = [dt.date(2026, 1, 2) + dt.timedelta(weeks=k), 50.0, 30.0 + k] + ([40.0 + k] if gaap else []) + \
               [21.0, 24.0]
        for j, v in enumerate(vals):
            c[f"{'ABCDEF'[j]}{42 + k}"] = v
    return grid(c, rows=50)


def test_pe_history_plots_gaap_against_gaap_on_a_non_gaap_model():
    # the S&P 500 and core-peer P/Es are GAAP; a non-GAAP subject line beside them would flatter the stock
    weeks, cols, basis = M.pe_history(weekly(gaap=True))
    assert cols["pe"] == [40.0, 41.0, 42.0, 43.0, 44.0] and "GAAP" in basis and "TTM" in basis
    assert cols["S&P 500 P/E"] == [21.0] * 5 and len(weeks) == 5


def test_pe_history_without_a_gaap_column_names_its_basis():
    _, cols, basis = M.pe_history(weekly(gaap=False))
    assert cols["pe"][0] == 30.0 and basis == "TTM"


def test_ladder_ignores_reasoning_text_that_mentions_it():
    # agent reasoning in column H can name the ladder; only the block's own column-A header counts
    c = {"A10": "4b. Blended", "H10": "Reward / risk ladder below is wide", "B10": "Entry", "C10": "Reward",
         "D10": "Risk", "E10": "R/R", "A11": 9.0,
         "A50": "4c. Reward / risk ladder (blended)", "B50": "Entry", "C50": "Reward", "D50": "Risk", "E50": "R/R",
         "A51": -0.05, "B51": 68.78, "C51": 0.379, "D51": 0.105, "E51": 3.6,
         "A52": 0.0, "B52": 72.40, "C52": 0.31, "D52": 0.15, "E52": 2.07}
    lad = M.ladder(grid(c))
    assert [r[0] for r in lad] == [-0.05, 0.0] and lad[1][1] == 72.40


def test_price_history_without_px_events_still_gives_prices():
    px = grid({"A4": "Date", "B4": "XYZ close", "C4": "SPY close", "A5": dt.date(2026, 1, 2), "B5": 70.0,
               "A6": dt.date(2026, 1, 5), "B6": 71.0}, rows=10)
    pts, rel = M.price_history(px, None, "XYZ")
    assert pts == [(dt.date(2026, 1, 2), 70.0), (dt.date(2026, 1, 5), 71.0)] and rel is None


def test_missing_blocks_give_none():
    empty = grid({})
    assert M.cap_table(empty, {}) is None and M.estimates_grid(empty) is None and M.ladder(empty) is None
    assert M.pe_history(empty) is None and M.price_history(None, None, "XYZ") is None
