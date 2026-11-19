import csv
import json
import os

import guidance


def _work(tmp_path):
    w = tmp_path / "Filings Research" / "_work"
    (w / "readers" / "s01").mkdir(parents=True)
    with open(w / "model_series.csv", "w", newline="") as f:
        x = csv.writer(f)
        x.writerow(["metric", "period", "value", "unit", "source"])
        x.writerow(["INCOME STATEMENT | Revenue", "FY2025", "460", "$M", "Model, MOD!H4"])
        x.writerow(["INCOME STATEMENT | Revenue", "FY2024", "400", "$M", "Model, MOD!B4"])
    json.dump({"config": {"last_year": 2025, "first_year": 2020}}, open(w / "drivers_math.json", "w"))
    json.dump({"ticker": "TEST", "guidance": [{"key": "revenue", "names": ["revenue ($M)"], "basis": ["reported"],
                                               "actual": {"metric": "INCOME STATEMENT | Revenue"}}]},
              open(w / "model_handoff.json", "w"))
    return str(w)


ANS = [{"metric": "revenue ($M)", "fiscal_year": "2026", "action": "raised", "low": 520, "high": 530,
        "date": "2026-10-29", "basis": "reported", "kind": "hard", "source": "rel.md:61"},
       {"metric": "gross margin (%)", "fiscal_year": "2026", "action": "first", "low": 62, "high": 63,
        "date": "2026-10-29", "basis": "reported", "kind": "hard", "source": "rel.md:62"}]


def test_guides_go_into_research_filings_own_guidance_data(tmp_path):
    """The guide path must stay complete print by print, or the habitual-raiser flag goes wrong."""
    w = _work(tmp_path)
    rep = guidance.record(w, ANS, "Q3 26")
    rows = list(csv.DictReader(open(os.path.join(w, "readers", "update_Q3_26", "guidance.csv"))))
    assert rows[0]["metric"] == "revenue ($M)" and rows[0]["low"] == "520" and rows[0]["date"] == "2026-10-29"
    assert rep["no_block"] == ["gross margin (%)"]


def test_q4_adds_the_closed_year_to_the_series_and_bumps_the_last_year(tmp_path):
    w = _work(tmp_path)
    rep = guidance.close_year(w, 2026, {"H": "N"}, {"N4": 520.0})
    rows = list(csv.DictReader(open(os.path.join(w, "model_series.csv"))))
    new = [r for r in rows if r["period"] == "FY2026"]
    assert new == [{"metric": "INCOME STATEMENT | Revenue", "period": "FY2026", "value": "520.0", "unit": "$M",
                    "source": "Model, MOD!N4"}]
    assert json.load(open(os.path.join(w, "drivers_math.json")))["config"]["last_year"] == 2026
    assert rep["added"] == 1
