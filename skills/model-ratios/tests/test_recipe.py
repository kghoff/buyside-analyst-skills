import openpyxl
from openpyxl.utils import column_index_from_string as CI
from periods import Periods
from recipe import build_layout, Ctx
from roles import find_roles


def layout(mod_path, adj=()):
    ws = openpyxl.load_workbook(mod_path)["MOD"]
    roles, starts, opex = find_roles(ws)
    rows = build_layout(ws, roles, starts, opex, adj)
    keys = {R.key: i for i, R in enumerate(rows, 1) if R.key}
    return rows, keys, Ctx(keys, Periods(ws))


def test_analysis_rows_sit_under_their_line(mod_path):
    rows, keys, _ = layout(mod_path)
    labels = [R.label for R in rows[keys["REV"]:keys["REV"] + 3]]
    assert labels == ["% yoy", "% 2 year", "% qoq"]
    gp = [R.label for R in rows[keys["GP"]:keys["GP"] + 6]]
    assert gp == ["% margin", "bps yoy", "% yoy", "incremental margin", "% 2 year", "% qoq"]   # no duplicate % yoy
    rd = [R.label for R in rows[keys["RD"]:keys["RD"] + 5]]
    assert rd == ["% yoy", "% 2 year", "% qoq", "% of sales", "bps yoy"]                         # Part-2 addition
    assert rows[keys["GP"] + 1].pct == "GP:margin"                                                # bps uses the margin row
    assert [R.label for R in rows[keys["EPSD"]:keys["EPSD"] + 3]] == ["% yoy", "% 2 year", "% qoq"]


def test_sections_are_placed_like_the_dxcm_example_model(mod_path):
    rows, keys, _ = layout(mod_path)
    sections = [(i, R.label) for i, R in enumerate(rows, 1) if R.kind == "section"]
    assert [s for _, s in sections] == ["ROIC, ROE, ROA", "LEVERAGE & CASH CONVERSION", "FREE CASH FLOW"]
    cf_header = next(i for i, R in enumerate(rows, 1) if R.kind == "keep" and R.mod_row == 69)
    assert keys["BALCHK"] < sections[0][0] < sections[1][0] < cf_header   # returns + leverage: after the balance sheet
    assert sections[2][0] > keys["CASHCHK"]                               # FCF after the cash flow statement
    assert [R.mod_row for R in rows if R.kind == "keep"] == list(range(1, 115))   # every MOD row once, in order


def test_operating_cash_flow_gets_growth_rows_and_capex_its_share_of_sales(mod_path):
    rows, keys, _ = layout(mod_path)
    assert [R.label for R in rows[keys["CFO"]:keys["CFO"] + 3]] == ["% yoy", "% 2 year", "% qoq"]
    assert rows[keys["FCF_CAPEX"]].label == "% of sales"


def test_kpi_formulas(mod_path):
    rows, keys, x = layout(mod_path, adj=["(-) Capitalized software"])
    calc = {R.key: R.calc for R in rows if R.kind == "kpi"}
    r = keys
    assert calc["NOPAT"](x, CI("P")) == f"=P{r['ROIC_TAXES']}+P{r['ROIC_OI']}"
    assert calc["ROIC_TAX"](x, CI("P")) == f"=$T${r['TAXRATE']}"                    # quarter uses its FY rate
    assert calc["ICAVG_A"](x, CI("P")) == f"=(P{r['IC_A']}+J{r['IC_A']})/2"         # TTM basis: year-ago quarter-end
    # Invested capital (house definition): operating assets - non-interest-bearing current liabilities; "minus cash" drops cash + securities
    ops = "+".join(f"P{r[k]}" for k in ("AR", "INV", "PRE", "PPE", "ROU", "GWI"))
    nib = "+".join(f"P{r[k]}" for k in ("AP", "PAY", "OPLLC", "CLOTH"))
    assert calc["IC_A"](x, CI("P")) == f"=(P{r['CASH']}+P{r['STSEC']}+{ops})-({nib})"
    assert calc["IC_M"](x, CI("P")) == f"=({ops})-({nib})"
    assert calc["ICAVG_A"](x, CI("F")) is None                                     # no year-ago balance yet
    assert calc["DSO"](x, CI("P")) == f"=((P{r['AR']}+M{r['AR']})/2)/P{r['REV']}*P{r['DAYS']}"   # prior quarter-end
    assert calc["FCF"](x, CI("P")) == f"=P{r['FCF_CFO']}+P{r['FCF_CAPEX']}+P{r['ADJ0']}"
    assert calc["INTCOV"](x, CI("T")) == f'=IFERROR((T{r["OI"]})/-(T{r["INTEXP"]}),"n.a.")'
    assert calc["EBITDA"](x, CI("P")) == f"=P{r['KM_OP']}+P{r['DA']}"


def test_current_year_quarters_fall_back_to_latest_reported_tax_rate(mod_path):
    rows, keys, x = layout(mod_path)
    calc = {R.key: R.calc for R in rows if R.kind == "kpi"}
    assert calc["ROIC_TAX"](x, CI("V")) == f"=$T${keys['TAXRATE']}"     # Q1 24: no FY 2024 yet -> FY 2023 rate
    assert x.notes and "FY 2023" in x.notes[0][2]
    assert calc["ROIC_TAX"](x, CI("X")) == f"=$Z${keys['TAXRATE']}"     # Q3 24E: its own FY-estimate rate


def test_net_leverage_without_a_short_term_securities_row(mod_path):
    # SFM holds no short-term securities, so model-historicals drops the row; net leverage is then debt less cash,
    # not "n.a." (a company with no securities still has a net leverage ratio)
    rows, keys, x = layout(mod_path)
    calc = {R.key: R.calc for R in rows if R.kind == "kpi"}
    r = dict(keys)
    del x.rows["STSEC"]
    assert calc["NETLEV"](x, CI("P")) == f"=(P{r['LTDEBT']}+P{r['CURDEBT']}-P{r['CASH']})/P{r['EBITDA_TTM']}"
