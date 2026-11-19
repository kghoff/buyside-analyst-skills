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


RF = os.path.join(os.path.dirname(__file__), "..", "..", "research-filings", "scripts")


def _closed_q4(model, tmp_path):
    """The fixture with FY2026 closed: Q3 26 and Q4 26 reported and the year header without its E (as actuals.py
    leaves a Q4 copy). An openpyxl test copy, never a user's model."""
    import openpyxl
    wb = openpyxl.load_workbook(model)
    ws = wb["MOD"]
    ws["L2"], ws["M2"], ws["N2"] = "Q3 26", "Q4 26", "2026"
    for r, v in ((4, 140), (6, 52), (8, 36), (11, 30), (27, 1500)):
        ws[f"L{r}"] = v
    for r, v in ((4, 150), (6, 55), (8, 37), (11, 32), (27, 1600)):
        ws[f"M{r}"] = v
    out = str(tmp_path / "closed.xlsx")
    wb.save(out)
    return out


def _stale_series(w):
    """model_series.csv as research-filings wrote it before a MOD row was inserted above Revenue: every source is one
    row up, so 'Revenue' points at the row above it and 'Cost of sales' at the '% yoy' row."""
    with open(os.path.join(w, "model_series.csv"), "w", newline="") as f:
        x = csv.writer(f)
        x.writerow(["metric", "period", "value", "unit", "source"])
        x.writerow(["INCOME STATEMENT | Revenue", "FY2025", "460", "$m", "Model, MOD!H3"])
        x.writerow(["INCOME STATEMENT | Cost of sales", "FY2025", "184", "$m", "Model, MOD!H5"])


def test_q4_rebuilds_the_series_from_the_model_so_stale_rows_cannot_point_the_closed_year_at_another_line(model, tmp_path):
    """model_series.csv's MOD rows go stale when rows move (on the real DXCM data 8,084 of 8,106 were: Revenue pointed
    at a '% yoy' row). Remapping them would write the wrong lines into the closed year and handoff.py's check_rows
    would stop the run; rebuilding from the finished copy with research-filings' own extractor cannot."""
    import openpyxl
    w = _work(tmp_path)
    _stale_series(w)
    closed = _closed_q4(model, tmp_path)
    rep = guidance.close_year(w, 2026, closed, RF)
    rows = list(csv.DictReader(open(os.path.join(w, "model_series.csv"))))
    ws = openpyxl.load_workbook(closed)["MOD"]
    for r in rows:                                    # every source sits on its own line
        row = int(r["source"].rsplit("MOD!", 1)[1].lstrip("ABCDEFGHIJKLMNOPQRSTUVWXYZ"))
        assert ws[f"B{row}"].value == r["metric"].split(" | ")[-1], r
    rev = {r["period"]: r for r in rows if r["metric"] == "INCOME STATEMENT | Revenue"}
    assert rev["FY2026"]["source"] == "Model, MOD!N4" and float(rev["FY2026"]["value"]) == 115 + 125 + 140 + 150
    assert rev["FY2025"]["source"] == "Model, MOD!H4"
    assert "FY2027" not in rev                        # the forecast year (header 2027E) is not history
    assert json.load(open(os.path.join(w, "drivers_math.json")))["config"]["last_year"] == 2026
    assert rep["closed_year_values"] > 0


def test_close_year_does_not_need_an_existing_series(model, tmp_path):
    """An empty model_series.csv (research-filings stopped early, or a header-only file) must not crash the Q4 step."""
    w = _work(tmp_path)
    open(os.path.join(w, "model_series.csv"), "w").close()
    guidance.close_year(w, 2026, _closed_q4(model, tmp_path), RF)
    assert any(r["period"] == "FY2026" for r in csv.DictReader(open(os.path.join(w, "model_series.csv"))))
