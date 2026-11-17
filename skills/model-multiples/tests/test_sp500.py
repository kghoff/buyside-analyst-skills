import datetime as dt
import os

import pytest

import sp500
from conftest import FIX


def test_parse_saved_page():
    rows = sp500.parse(open(os.path.join(FIX, "multpl.html"), encoding="utf-8").read())
    assert len(rows) > 1500                                       # monthly back to the 1870s
    assert [r["date"] for r in rows] == sorted(r["date"] for r in rows)
    assert all(3 < r["pe"] < 150 for r in rows)
    assert rows[-1]["estimate"] is True                           # the latest months are marked † Estimate


def test_parse_refuses_a_page_it_does_not_understand():
    with pytest.raises(SystemExit, match="multpl"):
        sp500.parse("<html>maintenance</html>")


def test_cache_reused_same_day(tmp_path):
    rows = [{"date": dt.date(2020, 1, 1), "pe": 20.0, "estimate": False}] * 200
    sp500.save(str(tmp_path / "sp500.json"), rows, "2026-11-17")
    assert sp500.load_cached(str(tmp_path / "sp500.json"), "2026-11-17") == rows
    assert sp500.load_cached(str(tmp_path / "sp500.json"), "2026-11-18") is None
