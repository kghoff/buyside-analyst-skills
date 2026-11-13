# tests/test_estimates.py
import json
import os
from datetime import date

import estimates


def test_report_file_names_parse_into_date_firm_type():
    p = estimates.parse_name("2026-10-29 JPM earnings recap - Overall Good 3Q.md")
    assert p == (date(2026, 10, 29), "JPM", "earnings recap")
    assert estimates.parse_name("notes.md") is None


MD = """# Note
Some prose about EPS that is not a table.

### Estimates (FYE Dec)
| | 2025A | 2026E | 2027E |
|---|---|---|---|
| Revenue ($ mn) | 4,662 | 5,237 | 5,771 |
| Adj. EPS ($) | 2.08 | 2.71 | 3.20 |

| Valuation | x |
|---|---|
| EV/EBITDA | 20 |
"""


def test_cut_keeps_only_tables_with_estimates_and_their_heading(tmp_path):
    f = tmp_path / "r.md"; f.write_text(MD)
    idx = estimates.cut_lines(str(f))
    lines = MD.splitlines()
    kept = [lines[i] for i in idx]
    assert "### Estimates (FYE Dec)" in kept and "| Adj. EPS ($) | 2.08 | 2.71 | 3.20 |" in kept
    assert "| EV/EBITDA | 20 |" not in kept


def entry(**k):
    base = {"metric": "eps", "period": "FY 27", "value": 3.20, "raw": "3.20", "scale": 1, "line_no": 8, "basis": "non-GAAP"}
    base.update(k)
    return base


def test_check_accepts_only_numbers_printed_on_the_cited_line(tmp_path):
    f = tmp_path / "r.md"; f.write_text(MD)
    labels = {"FY 26", "FY 27", "Q4 26"}
    ok, why = estimates.check_entry(entry(file=str(f)), labels)
    assert ok, why
    assert not estimates.check_entry(entry(file=str(f), raw="3.25", value=3.25), labels)[0]       # not printed
    assert not estimates.check_entry(entry(file=str(f), line_no=7), labels)[0]                    # wrong line
    assert not estimates.check_entry(entry(file=str(f), value=3.0), labels)[0]                    # value ≠ raw × scale
    assert not estimates.check_entry(entry(file=str(f), period="FY 30"), labels)[0]               # not a table period
    rev = entry(file=str(f), metric="revenue", raw="5,771", value=5771, line_no=7)
    assert estimates.check_entry(rev, labels)[0]
    neg = estimates.num("(1.5)")
    assert neg == -1.5


def test_choose_marks_old_reports_stale():
    acc = [entry(file="/x/2026-10-29 JPM earnings recap - a.md", firm="J.P. Morgan"),
           entry(file="/x/2026-05-01 Citi preview - b.md", firm="Citi")]
    last = {"J.P. Morgan": date(2026, 10, 30), "Citi": date(2026, 9, 1)}
    out = estimates.choose(acc, last, date(2026, 11, 12))
    assert out["J.P. Morgan"]["stale"] is False       # report one day before its rating action is the same event
    assert out["Citi"]["stale"] is True               # older than the firm's last action and than 90 days
    assert out["J.P. Morgan"]["values"]["eps"]["FY 27"]["value"] == 3.20


def test_choose_prefers_the_newest_report_for_the_same_period():
    acc = [entry(file="/x/2026-07-30 JPM earnings recap - a.md", firm="J.P. Morgan", value=3.29, raw="3.29"),
           entry(file="/x/2026-10-29 JPM earnings recap - b.md", firm="J.P. Morgan")]
    out = estimates.choose(acc, {"J.P. Morgan": date(2026, 10, 30)}, date(2026, 11, 12))
    assert out["J.P. Morgan"]["values"]["eps"]["FY 27"]["value"] == 3.20
    assert out["J.P. Morgan"]["date"] == "2026-10-29"


def test_check_matches_numbers_on_boundaries_not_substrings(tmp_path):
    f = tmp_path / "r.md"
    f.write_text("| Adj. EPS | 2.08 | 2.71 | 32.71 |\n| Revenue | 5,771 |\n")
    labels = {"FY 27"}
    base = dict(file=str(f), line_no=1, period="FY 27")
    assert estimates.check_entry(entry(raw="2.71", value=2.71, **base), labels)[0]
    assert not estimates.check_entry(entry(raw="2.7", value=2.7, **base), labels)[0]     # prefix of 2.71
    assert not estimates.check_entry(entry(raw="71", value=71, **base), labels)[0]       # tail of 32.71
    rev = entry(raw="771", value=771, metric="revenue", **{**base, "line_no": 2})
    assert not estimates.check_entry(rev, labels)[0]                                       # tail of 5,771


def test_check_unescapes_markdown_pipes(tmp_path):
    f = tmp_path / "r.md"
    f.write_text("| Rating | Buy \\| Overweight |\n")
    e = {"metric": "rating", "value": "Buy | Overweight", "raw": "Buy | Overweight", "line_no": 1, "file": str(f)}
    assert estimates.check_entry(e, set())[0]


def test_check_rejects_line_zero_and_bad_values_without_crashing(tmp_path):
    f = tmp_path / "r.md"; f.write_text(MD)
    labels = {"FY 26", "FY 27"}
    assert not estimates.check_entry(entry(file=str(f), line_no=0), labels)[0]
    for bad in (dict(value=None), dict(value="abc"), dict(scale=None), dict(scale="x")):
        ok, why = estimates.check_entry(entry(file=str(f), **bad), labels)
        assert not ok and why


def test_num_strips_currency_dashes_and_markers():
    assert estimates.num("$(0.12)") == -0.12
    assert estimates.num("(€1.5)") == -1.5
    assert estimates.num("−2.5") == -2.5
    assert estimates.num("–2.5") == -2.5
    assert estimates.num("2.71E") == 2.71
    assert estimates.num("2.08a") == 2.08
    assert estimates.num("3.20*") == 3.20
    assert estimates.num("3.20[a]") == 3.20
    assert estimates.num("3.20(b)") == 3.20
    assert estimates.num("3.20²") == 3.20
    assert estimates.num("1,234") == 1234.0


def test_cut_reports_what_it_skipped(tmp_path, monkeypatch):
    import ratings, snapshots
    snap = {"asof": "2026-11-12"}
    monkeypatch.setattr(snapshots, "load_all", lambda w: [snap])
    monkeypatch.setattr(snapshots, "consensus", lambda s, m: {"labels": {}})
    monkeypatch.setattr(estimates.periods, "fye_month", lambda s: 12)
    monkeypatch.setattr(ratings, "actions", lambda s, F: [])
    monkeypatch.setattr(ratings, "latest_by_firm", lambda a, d: ([], []))
    monkeypatch.setattr(ratings, "split_types", lambda rows: ([{"firm": "J.P. Morgan"}, {"firm": "Barclays"}], [], []))
    monkeypatch.setattr(ratings, "nasdaq_covering", lambda s, F, rows: [])
    sell = tmp_path / "ss" / "1 Broker Research" / "_md"; sell.mkdir(parents=True)
    (sell / "2026-10-29 JPM earnings recap - x.md").write_text("no tables here\n")
    (sell / "2026-10-30 Barclays earnings recap - y.md").write_text("### E\n| EPS | 1.0 |\n")
    (sell / "notes.md").write_text("x")
    (sell / "2026-10-30 Zzzz Unknown earnings recap - y.md").write_text("x")
    plan = estimates.cut(str(tmp_path), str(tmp_path / "ss"))
    assert [e["firm"] for e in plan["firms"]] == ["Barclays"]
    sk = plan["skipped"]
    assert any(s.get("firm") == "J.P. Morgan" and s["why"] == "no EPS/revenue table" for s in sk)
    assert any(s["file"].endswith("notes.md") for s in sk)
    assert any("Zzzz" in s["file"] for s in sk)


# ---- final review -------------------------------------------------------------------------------------------------
def _work_with(tmp_path, snapshot):
    w = tmp_path / "w"; os.makedirs(w / "snapshots")
    json.dump(snapshot, open(w / "snapshots" / f"{snapshot['asof']}.json", "w"))
    return w


# 3. the plan carries each label's period end, so the reader maps a broker's "FY27" by end month, not by name
def test_cut_writes_each_labels_period_end(tmp_path):
    from conftest import snap
    w = _work_with(tmp_path, snap("DXCM"))
    (tmp_path / "ss" / "_md").mkdir(parents=True)
    plan = estimates.cut(str(w), str(tmp_path / "ss"))
    assert plan["periods"] == {"Q4 26": "2026-12-31", "FY 26": "2026-12-31", "FY 27": "2027-12-31"}
    assert json.load(open(w / "estimates_plan.json"))["periods"] == plan["periods"]


ENDS = {"FY 26": "2026-12-31", "FY 27": "2027-12-31", "Q4 26": "2026-12-31"}


def test_check_rejects_a_value_whose_stated_period_end_is_another_year(tmp_path):
    f = tmp_path / "r.md"; f.write_text(MD)
    labels = set(ENDS)
    assert estimates.check_entry(entry(file=str(f), period_end="2027-12"), labels, ENDS)[0]
    assert estimates.check_entry(entry(file=str(f), period_end="2028-01"), labels, ENDS)[0]       # 53-week year: 1 month off
    ok, why = estimates.check_entry(entry(file=str(f), period_end="2028-06"), labels, ENDS)       # a June-FY broker "FY27"?
    assert not ok and "period end" in why
    assert not estimates.check_entry(entry(file=str(f), period_end="2026-12"), labels, ENDS)[0]   # that is FY 26, not FY 27
    assert not estimates.check_entry(entry(file=str(f), period_end="Dec 27"), labels, ENDS)[0]    # not YYYY-MM


def test_check_accepts_a_missing_period_end_but_notes_it(tmp_path):
    f = tmp_path / "r.md"; f.write_text(MD)
    v = entry(file=str(f), note="adj.")
    ok, _ = estimates.check_entry(v, set(ENDS), ENDS)
    assert ok and "period end not stated" in v["note"] and "adj." in v["note"]
    r = entry(file=str(f), metric="rating", raw="3.20", value="3.20", period=None)                # ratings have no period
    estimates.check_entry(r, set(ENDS), ENDS)
    assert "period end not stated" not in (r.get("note") or "")


# 8. a period end that isn't a quarter end: labels unknown and a printed warning, not a crash
def test_cut_survives_unreadable_periods(tmp_path, capsys):
    from conftest import snap
    s = snap("DXCM")
    for t in s["yahoo"]["trend"]:
        if t["period"] == "0q":
            t["endDate"] = "2026-11-15T00:00:00.000Z"
    w = _work_with(tmp_path, s)
    (tmp_path / "ss" / "_md").mkdir(parents=True)
    plan = estimates.cut(str(w), str(tmp_path / "ss"))
    assert plan["labels"] == {"q": None, "fy": None, "fy1": None} and plan["periods"] == {}
    assert any("not a quarter end" in x for x in plan["warnings"])
    assert "not a quarter end" in capsys.readouterr().err


# 10. a covering broker's report filed under Independent Research is still read for estimates
def test_cut_reads_analyst_reports_filed_under_independent_research(tmp_path, monkeypatch):
    import ratings, snapshots
    monkeypatch.setattr(snapshots, "load_all", lambda w: [{"asof": "2026-11-12"}])
    monkeypatch.setattr(snapshots, "consensus", lambda s, m: {"labels": {}})
    monkeypatch.setattr(estimates.periods, "fye_month", lambda s: 12)
    monkeypatch.setattr(ratings, "actions", lambda s, F: [])
    monkeypatch.setattr(ratings, "latest_by_firm", lambda a, d: ([], []))
    monkeypatch.setattr(ratings, "split_types", lambda rows: ([{"firm": "Barclays"}], [], []))
    monkeypatch.setattr(ratings, "nasdaq_covering", lambda s, F, rows: [])
    ind = tmp_path / "ss" / "2 Independent Research" / "_md"; ind.mkdir(parents=True)
    (tmp_path / "ss" / "1 Broker Research" / "_md").mkdir(parents=True)
    (ind / "2026-10-30 Barclays earnings recap - y.md").write_text("### E\n| EPS | 1.0 |\n")
    plan = estimates.cut(str(tmp_path), str(tmp_path / "ss"))
    assert [(e["firm"], e["kind"]) for e in plan["firms"]] == [("Barclays", "broker")]
    assert "Independent Research" in plan["firms"][0]["file"]
