import datetime as dt
import json
import os

import pytest

import peers
from conftest import FIX


@pytest.fixture(scope="module")
def x():
    return json.load(open(os.path.join(FIX, "abt_xbrl.json")))


def test_our_ttm_matches_the_tools_ttm(x):
    # Intent: quarter stitching is right only if the latest four quarters sum to the tool's own TTM figure.
    q = peers.eps_quarters(x)
    t = peers.ttm(q)
    assert t[-1]["ttm"] == pytest.approx(x["ttm"]["income"]["diluted_earnings_per_share"], rel=1e-9)
    assert t[-1]["consecutive"] is True


def test_quarter_known_after_filing_deadline_never_at_quarter_end(x):
    q = peers.eps_quarters(x)
    for r in q:
        lag = (r["known"] - r["end"]).days
        assert lag == (60 if r["q"] == 4 else 40)
    assert q[-1]["end"] == dt.date.fromisoformat(x["ttm"]["endDate"])


def test_gap_in_quarters_breaks_ttm(x):
    q = peers.eps_quarters(x)
    del q[-2]                                          # a missing quarter: no TTM until four consecutive again
    t = peers.ttm(q)
    assert t[-1]["ttm"] is None and t[-1]["consecutive"] is False


def test_missing_eps_is_kept_visible_and_breaks_ttm(x):
    # Intent: a quarter with no EPS must not vanish silently; it stays as a row and breaks every TTM that spans it,
    # so build can write NA() exactly where Python says None.
    y = json.loads(json.dumps(x))
    y["quarterly"]["2026"]["Q2"]["income"].pop("diluted_earnings_per_share")
    q = peers.eps_quarters(y)
    assert len(q) == len(peers.eps_quarters(x))
    assert [r["eps"] for r in q if (r["fy"], r["q"]) == (2026, 2)] == [None]
    t = peers.ttm(q)
    assert [r["consecutive"] for r in t[-3:]] == [False, False, False]
    assert all(r["ttm"] is None for r in t[-3:])


def test_weekly_close_is_last_close_on_or_before_the_week(tmp_path):
    p = tmp_path / "abt_us_d.csv"
    p.write_text("Date,Open,High,Low,Close,Volume\n2026-01-05,1,1,1,100,1\n2026-01-07,1,1,1,102,1\n")
    closes = peers.load_closes(str(p))
    assert peers.close_on(closes, dt.date(2026, 1, 9)) == 102
    assert peers.close_on(closes, dt.date(2026, 1, 4)) is None
