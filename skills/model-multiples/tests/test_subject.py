import datetime as dt

import pytest

import subject
from conftest import REFERENCE
from modmap import ModMap


@pytest.fixture(scope="module")
def mm():
    return ModMap(REFERENCE)


def test_rows_found_and_net_debt_excludes_operating_leases(mm):
    rows = subject.find_rows(mm)
    labels = {r: k.split(" | ", 1)[1] for k, r in mm.keys.items()}
    assert labels[rows["rev"]].startswith("Revenue")
    debt_labels = [labels[r] for r in rows["debt"]]
    assert any("Convertible" in l for l in debt_labels)
    assert not any("Lease" in l for l in debt_labels)            # leases are not debt (model-dcf's rule)
    assert "free cash flow" in labels[rows["fcf"]].lower()


def test_eps_basis_read_from_px_data_header():
    assert subject.eps_basis(REFERENCE) == "gaap"                # header 'P/E (TTM GAAP)'


def test_ttm_equals_the_fiscal_year_at_q4(mm):
    # Intent: TTM at a Q4 must be the fiscal year the company reported (four quarters = the annual column).
    qs = subject.quarters(REFERENCE, REFERENCE)
    q4 = next(q for q in qs if q["label"] == "Q4 24")
    fy = subject.num(subject.grid(REFERENCE, max(subject.find_rows(mm)["rev"], 1)), subject.find_rows(mm)["rev"],
                     mm.col("2024"))
    assert q4["rev"][0] == pytest.approx(fy)
    assert q4["rev"][1].count("MOD!") == 4                       # a live formula over four MOD cells


def test_quarter_known_only_after_release(mm):
    qs = subject.quarters(REFERENCE, REFERENCE)
    assert all(isinstance(q["date"], dt.date) for q in qs)
    assert [q["date"] for q in qs] == sorted(q["date"] for q in qs)
    d = qs[5]["date"]
    assert subject.asof([q["date"] for q in qs], d) == 4          # release day itself: still the previous quarter
    assert subject.asof([q["date"] for q in qs], d + dt.timedelta(days=1)) == 5


def test_weekly_takes_last_trading_day_of_each_week():
    w = subject.weekly(REFERENCE)
    days = [x[0] for x in w]
    assert days == sorted(days)
    assert len({d.isocalendar()[:2] for d in days}) == len(days)   # one row per ISO week
    assert all(x[1] > 0 and x[2] >= 5 for x in w)                  # close, Px Data row
