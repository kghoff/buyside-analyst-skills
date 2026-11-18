"""prices.py tells Yahoo files (Close + Adj Close) from stooq ones, checks the adjustment runs the right way, and
refuses a run that mixes sources: one regression must never mix a total-return SPY with a price-only stock."""
import pandas as pd

import prices


def _csv(path, adj=None, closes=(10.0, 11.0, 12.0)):
    df = pd.DataFrame({"Date": ["2025-01-02", "2025-01-03", "2025-01-06"], "Open": closes, "High": closes,
                       "Low": closes, "Close": closes, "Volume": [1, 1, 1]})
    if adj is not None:
        df["Adj Close"] = adj
    df.to_csv(path, index=False)
    return str(path)


def test_yahoo_file_is_recognised(tmp_path):
    r = prices.check("abt", _csv(tmp_path / "a.csv", adj=[9.8, 10.8, 12.0]))
    assert r["ok"] and r["source"] == "yahoo" and r["adj_problems"] == []


def test_stooq_file_is_recognised(tmp_path):
    r = prices.check("abt", _csv(tmp_path / "a.csv"))
    assert r["ok"] and r["source"] == "stooq"


def test_adj_above_close_is_a_problem(tmp_path):
    # Dividends only ever lower past adjusted prices; an Adj Close above Close means a wrong or swapped column.
    r = prices.check("abt", _csv(tmp_path / "a.csv", adj=[10.5, 11.0, 12.0]))
    assert any("above" in p for p in r["adj_problems"])


def test_adj_not_anchored_today_is_a_problem(tmp_path):
    r = prices.check("abt", _csv(tmp_path / "a.csv", adj=[9.8, 10.8, 11.9]))
    assert any("last day" in p for p in r["adj_problems"])


def test_mixed_sources_are_named():
    assert prices.mixed({"stock": {"source": "yahoo"}, "spy": {"source": "stooq"}}) == ["spy"]
    assert prices.mixed({"stock": {"source": "yahoo"}, "spy": {"source": "yahoo"}}) == []
