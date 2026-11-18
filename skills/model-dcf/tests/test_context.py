import datetime as dt
import json

import openpyxl
import pytest

import context

ROWS = {  # MOD row -> (section, label); a deliberately non-DXCM shape: units x price + other revenue
    32: ("KEY OPERATING / ALT DATA", "Units shipped"),
    34: (None, "Other revenue"),
    35: (None, "Price per unit"),
    119: ("INCOME STATEMENT", "Revenue:"),
    129: (None, "Gross Profit"),
    139: (None, "(-) R&D"),
    143: (None, "(-) SG&A"),
    150: (None, "Operating Income"),
    161: (None, "Income Tax Rate"),
    171: (None, "Shares, diluted"),
    176: (None, "EPS, diluted"),
    236: ("NON-GAAP METRICS", "Non-GAAP EPS, Diluted"),
    243: ("ASSETS:", "Cash & Equivalents"),
    244: (None, "Short-term marketable securities"),
    271: ("LIABILITIES & EQUITY:", "Current LT Senior Convertible Notes"),
    276: (None, "LT Senior Convertible Debt:"),
    330: ("CASH FLOWS FROM OPERATING ACTIVITIES:", "(+) Depreciation & Amortization"),
    344: (None, "Working Capital Changes, Net"),
    355: ("CASH FLOWS FROM INVESTING ACTIVITIES:", "(-) CapEx (Purchase of PP&E)"),
}
# columns: D=2023 E=2024 F=2025 G=Q3 26 H=Q4 26E I=2026E J=2027E K=2028E
HDR = {"D": 2023, "E": 2024, "F": 2025, "G": "Q3 26", "H": "Q4 26E", "I": "2026E", "J": "2027E", "K": "2028E"}


@pytest.fixture
def model(tmp_path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "MOD"
    for c, v in HDR.items():
        ws[f"{c}2"] = v
    for r, (sec, lab) in ROWS.items():
        if sec:
            ws[f"A{r}"] = sec
        ws[f"B{r}"] = lab
    # revenue = average units x price + other revenue, exactly, in every year the identity is checked
    units = dict(zip("DEFIJK", [2.0, 2.8, 3.5, 4.0, 4.5, 5.0]))
    other = dict(zip("DEFIJK", [100, 100, 100, 100, 120, 140]))
    rev = dict(zip("DEFIJK", [3000, 4000, 4600, 5200, 5800, 6400]))
    prev = {"E": "D", "F": "E", "I": "F", "J": "I", "K": "J"}
    for c in "DEFIJK":
        ws[f"{c}32"], ws[f"{c}34"] = units[c], other[c]
        ws[f"{c}35"] = (rev[c] - other[c]) / ((units[c] + units[prev[c]]) / 2) if c in prev else 1500
    for c, v in zip("DEFIJK", [3000, 4000, 4600, 5200, 5800, 6400]):
        ws[f"{c}119"] = v
    for c, v in zip("DEFIJK", [1800, 2400, 2800, 3300, 3700, 4200]):
        ws[f"{c}129"] = v
        ws[f"{c}139"] = -500
        ws[f"{c}143"] = -1300
        ws[f"{c}161"] = 0.2
        ws[f"{c}330"] = 250
        ws[f"{c}344"] = 10
        ws[f"{c}355"] = -350
    ws["J139"], ws["K139"] = -600, -650
    for c in "DEFIJK":                                   # operating income = gross profit - all operating expenses
        ws[f"{c}150"] = ws[f"{c}129"].value + ws[f"{c}139"].value + ws[f"{c}143"].value
    ws["H171"], ws["I176"], ws["J176"], ws["I236"], ws["J236"] = 380, 2.5, 2.9, 2.7, 3.1
    ws["H243"], ws["H244"], ws["H271"], ws["H276"] = 1100, 800, 50, 1200
    ws["G243"] = 1
    px = wb.create_sheet("Px Data")
    px["A1"] = "title"
    for c, h in zip("AB", ["Date", "DXCM close"]):
        px[f"{c}4"] = h
    series = [(dt.datetime(2020, 1, 2), 500.0), (dt.datetime(2023, 12, 29), 30.0), (dt.datetime(2024, 6, 3), 90.0),
              (dt.datetime(2025, 3, 3), 20.0), (dt.datetime(2026, 11, 6), 60.0)]
    for i, (d, v) in enumerate(series, start=5):
        px[f"A{i}"], px[f"B{i}"] = d, v
    cp = wb.create_sheet("CAPM")
    cp["G20"], cp["H20"] = "WACC:", 0.08
    p = tmp_path / "m.xlsx"
    wb.save(p)
    fp = tmp_path / "_model_work" / "forecast"
    fp.mkdir(parents=True)
    (fp / "forecast_plan.json").write_text(json.dumps({"revenue_identity": IDENTITY}))
    return str(p)


IDENTITY = {"terms": [
    {"factors": [{"key": "KEY OPERATING / ALT DATA | Units shipped", "name": "Units", "average": True, "long_run": 0.03,
                  "long_run_source": "test"},
                 {"key": "KEY OPERATING / ALT DATA | Price per unit", "name": "Price", "average": False,
                  "long_run": -0.01, "long_run_source": "test"}]},
    {"factors": [{"key": "KEY OPERATING / ALT DATA | Other revenue", "name": "Other revenue", "average": False,
                  "long_run": 0.0, "long_run_source": "test"}]}]}


def test_context_values_and_refs(model):
    c = context.build(model)
    assert c["year0"] == "2026E" and c["k"] == 2
    assert c["rev0"] == 5200 and c["refs"]["rev0"] == "MOD!I119"
    assert c["gm0"] == pytest.approx(3300 / 5200)
    assert c["opex0"] == 1800  # R&D + SG&A, positive
    f = {x["name"]: x for x in c["factors"]}
    assert c["terms"] == [[0, 1], [2]] and not c["identity_fallback"]
    assert f["Units"]["level_prev"] == 3.5 and f["Units"]["level0"] == 4.0 and f["Units"]["mod"] == [4.5, 5.0]
    assert f["Units"]["average"] and f["Units"]["long_run"] == 0.03 and f["Units"]["refs"]["year0"] == "MOD!I32"
    assert f["Other revenue"]["mod"] == [120, 140]
    m = c["mod"]
    assert m["rev"] == [5800, 6400] and m["gp"] == [3700, 4200]
    assert m["opex"] == [600 + 1300, 650 + 1300]
    assert m["capex"] == [350, 350] and m["da"] == [250, 250] and m["wc"] == [10, 10]
    assert m["tax_rate"] == [0.2, 0.2]
    assert c["refs"]["mod"]["rev"] == ["MOD!J119", "MOD!K119"]
    assert c["eps"]["gaap"] == {"year0": 2.5, "year1": 2.9} and c["eps"]["non_gaap"]["year1"] == 3.1


def test_cap_table_and_net_debt(model):
    c = context.build(model)
    cap = c["cap"]
    assert cap["cash"] == 1100 and cap["st_securities"] == 800 and cap["debt"] == 1250
    assert cap["shares"] == 380 and cap["column"] == "H"
    assert c["net_debt"] == 1250 - 1900 and c["shares"] == 380


def test_price_high_low_over_three_years(model):
    p = context.build(model)["price"]
    assert p["last"] == {"date": "2026-11-06", "value": 60.0}
    # window starts 2023-11-06: the 2020 high of 500 and 2023-12-29's 30 -> only 2023-12-29 onward counts
    assert p["high3y"] == {"date": "2024-06-03", "value": 90.0}
    assert p["low3y"] == {"date": "2025-03-03", "value": 20.0}


def test_wacc_is_not_read_from_capm_and_history(model):
    """v2: WACC is the user's typed input on the DCF tab, never a CAPM link, so context carries no WACC."""
    c = context.build(model)
    assert "wacc" not in c and "wacc_ref" not in c
    assert [h["year"] for h in c["history"]] == ["2023", "2024", "2025"]
    assert c["history"][-1]["rev"] == 4600 and c["history"][-1]["levels"][0] == 3.5


def test_unknown_row_stops_with_name(model, tmp_path):
    wb = openpyxl.load_workbook(model)
    wb["MOD"]["B355"] = "Something else"
    wb.save(model)
    with pytest.raises(SystemExit) as e:
        context.build(model)
    assert "CapEx" in str(e.value)


def test_without_a_revenue_identity_revenue_is_the_only_driver_and_flagged(model, tmp_path):
    """An old forecast (before revenue identities) still values, but as a growth engine the user is told about."""
    (tmp_path / "_model_work" / "forecast" / "forecast_plan.json").write_text("{}")
    c = context.build(model)
    assert c["identity_fallback"] and [f["name"] for f in c["factors"]] == ["Revenue"]
    assert c["factors"][0]["level0"] == 5200 and c["factors"][0]["long_run"] == 0.0


def test_rows_are_found_by_role_so_template_labels_and_the_users_labels_both_work(model):
    """the DXCM example model says 'Current LT Senior Convertible Notes'; the /model-historicals template says 'Current Portion of
    Debt' / 'Long-Term Debt:'. Every debt-like liability row is summed (a finance lease too), current vs long-term split
    at Total Current Liabilities; a company with no short-term securities values with 0 there."""
    wb = openpyxl.load_workbook(model)
    ws = wb["MOD"]
    ws["B271"], ws["B276"] = "Current Portion of Debt", "Long-Term Debt:"
    ws["B272"], ws["B278"], ws["B280"] = "Total Current Liabilities:", "Finance lease liabilities", "Total Liabilities:"
    ws["H278"] = 30
    ws["B244"] = "Prepaid Assets"                        # no short-term securities row
    ws["B139"], ws["B143"] = "(-) Sales & Marketing", "(-) General & Administrative"     # opex split differently
    wb.save(model)
    c = context.build(model)
    cap = c["cap"]
    assert cap["debt_current"] == 50 and cap["debt_lt"] == 1200 + 30 and cap["st_securities"] == 0.0
    assert cap["debt_lt_labels"] == ["Long-Term Debt:", "Finance lease liabilities"]
    assert c["opex0"] == 1800                            # gross profit - operating income, whatever the split


def test_driver_sections_are_not_read_as_the_statements(model):
    """/model-forecast v2 adds sections like 'INCOME STATEMENT DRIVERS' with their own tax-rate rows."""
    wb = openpyxl.load_workbook(model)
    ws = wb["MOD"]
    ws["A100"], ws["B101"] = "INCOME STATEMENT DRIVERS", "Tax rate from 2027 (assumption)"
    wb.save(model)
    c = context.build(model)
    assert c["refs"]["mod"]["tax_rate"][0] == "MOD!J161"


def _forecast_only_term(model, tmp_path, monkeypatch, blank_price=False):
    """A forecast-only additive term (e.g. 'revenue lost to a contract loss'): /model-forecast writes its row from the
    first forecast column, so the last actual year and year 0 are empty even after a recalculation."""
    import lo
    monkeypatch.setattr(lo, "recalc", lambda path, outdir: path)     # a recalculation cannot fill an empty cell
    wb = openpyxl.load_workbook(model)
    ws = wb["MOD"]
    ws["B37"], ws["J37"], ws["K37"] = "Revenue lost", -50, -60
    if blank_price:
        ws["F35"] = None
    wb.save(model)
    ident = json.loads(json.dumps(IDENTITY))
    ident["terms"].append({"factors": [{"key": "KEY OPERATING / ALT DATA | Revenue lost", "name": "Revenue lost",
                                        "average": False, "long_run": 0.02, "long_run_source": "test"}]})
    (tmp_path / "_model_work" / "forecast" / "forecast_plan.json").write_text(json.dumps({"revenue_identity": ident}))


def test_a_forecast_only_additive_term_is_0_before_the_forecast(model, tmp_path, monkeypatch):
    """Its own term, summed: nothing was there before the forecast, so 0 is the true level and the year-0 identity
    still equals revenue. Stopping here blocked /model-dcf on any model whose plan gained such a term."""
    import tempfile
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(scratch))
    _forecast_only_term(model, tmp_path, monkeypatch)
    c = context.build(model)
    f = c["factors"][3]
    assert f["level_prev"] == 0.0 and f["level0"] == 0.0 and f["mod"] == [-50, -60]
    assert f["refs"]["prev"] == "MOD!F37" and f["refs"]["year0"] == "MOD!I37"
    assert list(scratch.iterdir()) == []      # the recalculation folder (a copy of the user's model) is not kept
    # every blank counted as 0 is listed, so the user is told (a blank the user meant to fill would otherwise vanish)
    assert c["blank_as_0"] == ["MOD!F37 (KEY OPERATING / ALT DATA | Revenue lost, 2025)",
                               "MOD!I37 (KEY OPERATING / ALT DATA | Revenue lost, 2026E)"]


def test_a_model_with_no_blanks_lists_none(model):
    assert context.build(model)["blank_as_0"] == []


def test_a_blank_multiplied_factor_still_stops(model, tmp_path, monkeypatch):
    """A factor inside a product cannot count as 0: it would wipe the whole term, so a gap there is a real error."""
    _forecast_only_term(model, tmp_path, monkeypatch, blank_price=True)
    with pytest.raises(SystemExit) as e:
        context.build(model)
    assert "MOD!F35" in str(e.value)
