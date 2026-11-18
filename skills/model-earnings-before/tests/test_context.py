# skills/model-earnings-before/tests/test_context.py
"""context.json is the single source build.py, plan.py and note.py read. It must say whether the report date came
from Yahoo or was estimated (an implied move only means something with the print still ahead), carry code's own
answers (set-up row, blow-up flags) so the agent can't restate them, freeze the forecast per MOD row, and stop with
the skill to run when a required tab is missing."""
import json
import os

import openpyxl
import pytest

import context
import earnmath as em
import make_fixture as mf
from conftest import FPLAN, RESEARCH, TODAY


def _ctx(work):
    return json.load(open(os.path.join(work, "context.json")))


def test_quarter_date_and_code_answers(work):
    c = _ctx(work)
    assert c["quarter"] == "Q4 26E" and c["fy"] == "2026E"
    assert c["report_date"] == {"value": "2027-02-01", "estimated": True,
                                "source": "estimated: last year's release (2026-02-02, 'Px Events'!$B$11) + 52 weeks"}
    assert c["days_to_print"] == 75
    assert c["yahoo"]["implied_move"] is None
    assert c["price"]["value"] == 51.0
    assert c["code"]["blowups"] == {"margins": False, "peak_pe": True, "cash": False}
    assert c["code"]["setup"]["value_perf"] == em.setup_code(0.85, c["rates"]["rel"]["value"])
    assert c["last_print"] == "2026-11-02"                    # the reaction day: where the price moved
    assert c["last_release"] == "2026-10-30"                  # released after the close the trading day before
    # the reading list starts on the release day, so the print's own release (dated the day before the reaction)
    # is on it
    assert [d["date"] for d in c["new_docs"]] == ["2026-10-30", "2026-11-02", "2026-11-10", "2026-11-12"]
    assert [m["name"] for m in c["checks"]["metrics"]][-1] == "Units"
    assert c["mod"]["periods"] == {"q": "Q4 26E", "q_ly": "Q4 25", "fy": "2026E", "fy_ly": "2025", "fy1": "2027E"}
    assert c["mod"]["vals"]["3"]["q"] == pytest.approx(mf.series()["Q4 26E"]["rev"])
    assert c["mod"]["drivers"] == [{"name": "Units", "row": 13}]


def test_frozen_forecast_and_files(work):
    c = _ctx(work)
    s = mf.series()
    fr = {x["label"]: x for x in c["frozen"]}
    assert fr["INCOME STATEMENT | Revenue"]["q"] == pytest.approx(s["Q4 26E"]["rev"])
    assert fr["INCOME STATEMENT | Revenue"]["fy"] == pytest.approx(sum(s[p]["rev"] for p in ("Q1 26", "Q2 26", "Q3 26", "Q4 26E")))
    md = open(os.path.join(work, "context.md")).read()
    assert "Q4 26E" in md and "estimated" in md and "Investor Events/_md/TEST 2026-11-10 conference.md" in md
    assert os.path.exists(os.path.join(work, "rowmap.md"))


def test_yahoo_date_ahead_keeps_the_implied_move(fixture_model, tmp_path):
    w = tmp_path / "w"
    w.mkdir()
    (w / "earnings.json").write_text(json.dumps({**mf.EARN, "earnings_date": "2027-02-10", "implied_move": 0.06}))
    c = context.run(fixture_model, str(w), "TEST", values=fixture_model, research=RESEARCH, forecast_plan=FPLAN,
                    today=TODAY)
    assert c["report_date"]["estimated"] is False and c["report_date"]["value"] == "2027-02-10"
    assert c["yahoo"]["implied_move"] == 0.06


def test_yahoo_failure_falls_back_to_the_last_close(fixture_model, tmp_path):
    w = tmp_path / "w"
    w.mkdir()
    (w / "earnings.json").write_text(json.dumps({"ticker": "TEST", "asof": TODAY, "error": "boom"}))
    c = context.run(fixture_model, str(w), "TEST", values=fixture_model, research=RESEARCH, forecast_plan=FPLAN,
                    today=TODAY)
    assert c["price"]["value"] == pytest.approx(mf.closes()[0][-1]) and "Px Data" in c["price"]["source"]
    assert c["yahoo"]["surprises"] == [] and any("Yahoo" in x for x in c["warnings"])


def test_missing_required_tab_names_the_skill(tmp_path):
    p = mf.build(str(tmp_path / "x.xlsx"))
    wb = openpyxl.load_workbook(p)
    del wb["Px Events"]
    wb.save(p)
    with pytest.raises(SystemExit, match="model-price-history"):
        context.run(p, str(tmp_path / "w"), "TEST", values=p, research=RESEARCH, forecast_plan=FPLAN, today=TODAY)


def test_no_forecast_plan_leaves_drivers_out_and_says_so(fixture_model, tmp_path):
    w = tmp_path / "w"
    w.mkdir()
    (w / "earnings.json").write_text(json.dumps(mf.EARN))
    c = context.run(fixture_model, str(w), "TEST", values=fixture_model, research=RESEARCH,
                    forecast_plan=str(tmp_path / "none.json"), today=TODAY)
    assert "Units" not in [m["name"] for m in c["checks"]["metrics"]]
    assert any("forecast plan" in x for x in c["warnings"])
