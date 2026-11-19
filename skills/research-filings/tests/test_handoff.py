import csv, os, re

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


def _px_model(tmp_path, headers):
    # a throwaway workbook with only the Px Data header row (row 4), as /model-price-history writes it
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Px Data"
    for i, h in enumerate(headers):
        ws.cell(row=4, column=i + 1, value=h)
    p = str(tmp_path / "m.xlsx")
    wb.save(p)
    return p


def test_stock_returns_read_the_total_return_column_when_px_data_has_one(tmp_path):
    # Yahoo-era Px Data: B is the traded price (no dividends), D the total return. The yearly returns and the big
    # moves must read D, or a dividend payer's return vs SPY (a total return) is understated every year. The weekly
    # block repeats the header further right; its rows are weeks, so the daily (leftmost) one is the right column.
    from xlsx import Package
    p = _px_model(tmp_path, ["Date", "ABT close", "SPY close", "ABT total return (dividends in)", "ABT daily return",
                             None, None, "ABT total return (dividends in)"])
    pkg = Package(p)
    assert handoff._stock_col(pkg, handoff._strings(pkg)) == "D"


def test_stock_returns_read_column_b_on_models_without_a_total_return_column(tmp_path):
    # Models built before the Yahoo switch (stooq): B is already dividend-adjusted and D is the daily return.
    from xlsx import Package
    p = _px_model(tmp_path, ["Date", "DXCM close", "SPY close", "DXCM daily return"])
    pkg = Package(p)
    assert handoff._stock_col(pkg, handoff._strings(pkg)) == "B"


def test_stock_col_ignores_stray_spaces_in_the_header(tmp_path):
    from xlsx import Package
    p = _px_model(tmp_path, ["Date", "ABT close", "SPY close", " ABT total return (dividends in) "])
    pkg = Package(p)
    assert handoff._stock_col(pkg, handoff._strings(pkg)) == "D"


def test_stock_blocks_read_the_stock_from_the_column_they_are_given(tmp_path):
    # _stock_col picks D on Yahoo-era models; every stock lookup in the blocks (yearly returns, Total, the moves with
    # no company event) must then read D, never the traded price in B. SPY stays C.
    import openpyxl
    from xlsx import Package, Styles
    wb = openpyxl.Workbook()
    wb.active.title = "Idio Chart"
    wb.active["A1"] = handoff.MARK              # the block starts at its marker (no drawing needed)
    wb.create_sheet("Px Data")
    p = str(tmp_path / "m.xlsx")
    wb.save(p)
    pkg = Package(p)
    st = Styles(pkg.text("xl/styles.xml"))
    part = handoff._sheet_part(pkg, "Idio Chart")
    H = {"returns_years": [2023, 2024], "stock_col": "D",
         "no_event_moves": [{"from": "2024-03-01", "to": "2024-03-08", "what": "no news"}]}
    handoff.stock_blocks(pkg, st, part, H, "ABT", None)
    fs = dict(re.findall(r'<c r="([A-Z]+\d+)"[^>]*><f>(.*?)</f>', pkg.text(part)))
    stock = [f for r, f in fs.items() if r.startswith("B") and "LOOKUP" in f]          # 2 years + Total
    stock += [f for r, f in fs.items() if r.startswith("C") and "LOOKUP(B" in f]       # the move with no event
    assert len(stock) == 4, fs
    for f in stock:
        assert "$D$5:$D$20000" in f and "$B$5" not in f, f
    assert any(r.startswith("C") and "$C$5:$C$20000" in f for r, f in fs.items())     # SPY still reads C


def test_charts_only_leaves_idio_chart_alone_so_a_q4_refresh_cannot_touch_price_history(tmp_path, monkeypatch, capsys):
    # /model-update refreshes Filings Charts after a Q4; the user's Idio Chart and Px Events must not be looked at
    import json, sys
    TAB = handoff.TAB
    work = tmp_path / "_work"
    work.mkdir()
    json.dump({"config": {"revenue": 1, "cogs": 2, "operating_income": 3}}, open(work / "drivers_math.json", "w"))
    json.dump({"ticker": "TEST"}, open(work / "model_handoff.json", "w"))
    asked = []

    class FakePkg:
        def __init__(self, p): pass
        def text(self, n): return ""
        def put(self, *a): pass
        def finish(self): pass
        def save(self, p): pass

    class FakeStyles:
        def __init__(self, x): pass
        def render(self): return ""

    class FakeTab:
        def __init__(self, st):
            self.s = {"title": 0}
            self.sh = type("S", (), {"set": lambda *a: None, "heights": {}})()
        def note(self, t): pass

    monkeypatch.setattr(handoff, "_work", lambda src: str(work))
    monkeypatch.setattr(handoff, "load_mod", lambda w: {})
    monkeypatch.setattr(handoff, "check_rows", lambda *a: None)
    monkeypatch.setattr(handoff, "Package", FakePkg)
    monkeypatch.setattr(handoff, "Styles", FakeStyles)
    monkeypatch.setattr(handoff, "Tab", FakeTab)
    wrote = []
    monkeypatch.setattr(handoff, "write_tab", lambda *a: wrote.append(TAB))
    monkeypatch.setattr(handoff, "block_fixed_variable", lambda *a: False)
    monkeypatch.setattr(handoff, "block_profit_bridge", lambda *a: False)
    monkeypatch.setattr(handoff, "block_price_volume", lambda *a: False)
    monkeypatch.setattr(handoff, "_sheet_part", lambda pkg, name: asked.append(name) or "xl/worksheets/sheet9.xml")
    import notebox
    monkeypatch.setattr(notebox, "fix", lambda *a, **k: None)
    monkeypatch.setattr(sys, "argv", ["handoff.py", "--src", str(tmp_path), "--model", "m.xlsx", "--out", "o.xlsx",
                                      "--charts-only"])
    handoff.main()
    assert "Idio Chart" not in asked
    assert "idio" not in json.loads(capsys.readouterr().out)
    assert wrote == [TAB]                         # the point of the Q4 refresh: Filings Charts is still rebuilt
