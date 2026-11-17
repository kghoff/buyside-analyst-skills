import datetime as dt
import re

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
    qs, _ = subject.quarters(REFERENCE, REFERENCE)
    q4 = next(q for q in qs if q["label"] == "Q4 24")
    fy = subject.num(subject.grid(REFERENCE, max(subject.find_rows(mm)["rev"], 1)), subject.find_rows(mm)["rev"],
                     mm.col("2024"))
    assert q4["rev"][0] == pytest.approx(fy)
    assert len(set(re.findall(r"MOD!\$[A-Z]+\$\d+", q4["rev"][1]))) == 4                       # a live formula over four MOD cells


def test_quarter_known_only_after_release(mm):
    qs, _ = subject.quarters(REFERENCE, REFERENCE)
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


def test_formulas_reproduce_the_values(mm):
    # Intent: the live Excel formula build.py writes must give the same number (or NM) as the value we checked.
    import re
    qs, _ = subject.quarters(REFERENCE, REFERENCE)
    g = subject.grid(REFERENCE, 400)

    term = re.compile(r"([+-]?)MOD!\$([A-Z]+)\$(\d+)")

    def terms(text):
        return [(s or "+", subject.num(g, int(r), c)) for s, c, r in term.findall(text)]

    def ev(f):
        if not f.startswith("IF("):                                 # a bare reference
            return terms(f)[0][1]
        guard, rest = f[3:].split(")", 1)
        body = rest.split(",", 1)[1] if guard.startswith("COUNT(") else rest[1:]
        body = body.rsplit(",NA())", 1)[0]
        if guard.startswith("COUNT("):
            n = int(rest.split(",")[0].lstrip("="))
            if sum(v is not None for _, v in terms(guard)) != n:
                return None
        elif guard.startswith("ISNUMBER(") and terms(guard)[0][1] is None:
            return None
        return sum((-1 if s == "-" else 1) * (v or 0) for s, v in terms(body))

    n = 0
    for q in qs:
        for k in ("rev", "gp", "ebitda", "eps", "eps_gaap", "fcf", "shares", "net_debt"):
            val, f = q[k]
            got = ev(f)
            assert (got is None and val is None) or got == pytest.approx(val), (q["label"], k)
            n += 1
    assert n > 100


def test_skipped_quarter_stops_loudly(monkeypatch):
    real = ModMap.__init__

    def init(self, *a, **k):
        real(self, *a, **k)
        self.order.remove("Q2 20")
    monkeypatch.setattr(ModMap, "__init__", init)
    with pytest.raises(SystemExit, match="no column for Q2 20 between Q1 20 and Q3 20"):
        subject.quarters(REFERENCE, REFERENCE)


def test_ng_basis_without_ng_eps_row_stops(monkeypatch):
    real = subject.find_rows
    monkeypatch.setattr(subject, "eps_basis", lambda m: "ng")
    monkeypatch.setattr(subject, "find_rows", lambda mm: {k: v for k, v in real(mm).items() if k != "eps_ng"})
    with pytest.raises(SystemExit, match="non-GAAP EPS"):
        subject.quarters(REFERENCE, REFERENCE)


def test_ng_without_adjusted_ebitda_falls_back_and_says_so(monkeypatch):
    real = subject.find_rows
    monkeypatch.setattr(subject, "eps_basis", lambda m: "ng")
    monkeypatch.setattr(subject, "find_rows", lambda mm: {k: v for k, v in real(mm).items() if k != "ebitda_ng"})
    _, notes = subject.quarters(REFERENCE, REFERENCE)
    assert any("operating income + D&A" in n for n in notes)


def test_ng_basis_still_carries_gaap_eps_for_the_relative_rows(monkeypatch, mm):
    # The relative rows compare with GAAP figures (multpl, XBRL), so a non-GAAP subject must also carry GAAP TTM EPS,
    # as a live formula over the GAAP EPS row, not the non-GAAP one.
    monkeypatch.setattr(subject, "eps_basis", lambda m: "ng")
    R = subject.find_rows(mm)
    qs, _ = subject.quarters(REFERENCE, REFERENCE)
    q = qs[-1]
    assert f"${R['eps_ng']}" in q["eps"][1] and f"${R['eps_gaap']}" in q["eps_gaap"][1]
    assert q["eps"][0] != pytest.approx(q["eps_gaap"][0])
    assert "COUNT(" in q["eps_gaap"][1]


def test_unit_column_not_millions_is_a_warning(mm):
    # The multiples assume MOD's revenue and shares are in millions; a model kept in thousands must not pass silently.
    R = subject.find_rows(mm)
    assert subject.unit_notes(mm, R) == []                       # the reference model: '$ M' and 'M'
    fake = type("MM", (), {"lines": [(R["rev"], "k", "$ K"), (R["shares"], "k", "M")]})()
    notes = subject.unit_notes(fake, R)
    assert len(notes) == 1 and "'$ K'" in notes[0] and "revenue" in notes[0]


def test_unit_check_matches_only_real_millions_labels():
    # "Number" contains an m but is not millions; a units slip must warn, a real millions label must not.
    mk = lambda u: type("MM", (), {"lines": [(1, "k", u), (2, "k", "M")]})()
    R = {"rev": 1, "shares": 2}
    assert len(subject.unit_notes(mk("Number"), R)) == 1
    for ok in ("$M", "$ millions", "MM", "$ M", "Mil"):
        assert subject.unit_notes(mk(ok), R) == [], ok
