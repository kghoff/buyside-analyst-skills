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


def _fixture():
    return open(os.path.join(FIX, "multpl.html"), encoding="utf-8").read()


def test_corrupt_cache_is_a_miss(tmp_path):
    p = tmp_path / "sp500.json"
    p.write_text("{not json")
    assert sp500.load_cached(str(p), "2026-11-17") is None
    p.write_text('{"asof": "2026-11-17"}')                      # missing rows key
    assert sp500.load_cached(str(p), "2026-11-17") is None


def test_get_fetches_once_then_uses_cache(tmp_path, monkeypatch):
    calls = []

    class Resp:
        def read(self):
            return _fixture().encode("utf-8")

    monkeypatch.setattr(sp500.urllib.request, "urlopen", lambda *a, **k: calls.append(1) or Resp())
    first = sp500.get(str(tmp_path), "2026-11-17")
    second = sp500.get(str(tmp_path), "2026-11-17")
    assert len(calls) == 1 and first == second


def test_get_wraps_fetch_failure(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise sp500.urllib.error.URLError("down")
    monkeypatch.setattr(sp500.urllib.request, "urlopen", boom)
    with pytest.raises(SystemExit, match="multpl.*rerun later"):
        sp500.get(str(tmp_path), "2026-11-17")


def test_unparseable_row_is_not_dropped_silently():
    html = _fixture().replace("</abbr>\n25.30", "</abbr>\nn/a", 1)
    assert "n/a" in html
    with pytest.raises(SystemExit, match="multpl: parsed"):
        sp500.parse(html)


def test_extra_whitespace_and_nbsp_still_parse():
    html = _fixture().replace("&#x2002;", " &nbsp;\n  ", 1)
    assert len(sp500.parse(html)) == len(sp500.parse(_fixture()))
