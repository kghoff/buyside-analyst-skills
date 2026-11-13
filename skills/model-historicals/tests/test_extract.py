"""Statement shapes DXCM never had (house default: cover companies whose statements look different). Each test is
a real pattern from a filing; a wrong mapping here means a wrong model row with no error anywhere."""
from extract import map_is, map_bs, map_cf, tot, unit_of, plug_rounding, financial_kind, CA, IS_SUM


def test_costs_and_expenses_layout_without_gross_profit(  ):
    # Medtronic: one "Costs and expenses" list, no gross-profit line. The old reader took R&D and SG&A for revenue.
    rows = [("Net sales", [36364.0]), ("Costs and expenses:", []),
            ("Cost of products sold, excluding amortization of intangible assets", [12721.0]),
            ("Research and development expense", [2873.0]), ("Selling, general, and administrative expense", [11784.0]),
            ("Amortization of intangible assets", [1772.0]), ("Restructuring charges, net", [249.0]),
            ("Certain litigation charges, net", [113.0]), ("Other operating expense (income), net", [386.0]),
            ("Operating profit", [6467.0]), ("Other non-operating expense (income), net", [-384.0]),
            ("Interest expense, net", [715.0]), ("Income before income taxes", [6136.0]), ("Income tax provision", [1299.0]),
            ("Net income", [4837.0]), ("Net income attributable to noncontrolling interests", [-37.0]),
            ("Net income attributable to Medtronic", [4801.0]),
            ("Basic weighted average shares outstanding", [1281.8]), ("Diluted weighted average shares outstanding", [1288.1])]
    out, chk = map_is(rows, [], 3.15)
    assert tot(out, "REV") == 36364 and tot(out, "COGS") == -12721
    assert tot(out, "RD") == -2873 and tot(out, "RESTR") == -249 and tot(out, "LITIG") == -113 and tot(out, "AMORT") == -1772
    assert tot(out, "OTHINC") == 384 and tot(out, "INTEXP") == -715          # 'expense (income)': a negative is income
    assert chk["NI"] == 4837 and tot(out, "NCI_IS") == -37                   # consolidated NI; minority share subtracted
    assert abs(tot(out, *IS_SUM) - 6467) <= 1          # MDT's own rounding; main() plugs the 1 into Other Operating


def test_interest_net_subtotal_is_not_counted_twice():
    rows = [("Net sales", [100.0]), ("Cost of products sold", [40.0]), ("Research and development expense", [10.0]),
            ("Operating profit", [50.0]), ("Interest income", [-6.0]), ("Interest expense", [16.0]),
            ("Interest expense, net", [10.0]), ("Income from operations before income taxes", [40.0]),
            ("Provision for income taxes", [8.0]), ("Net income", [32.0]), ("Shares used basic", [1.0])]
    out, chk = map_is(rows, [], 0.45)
    assert chk["PRETAX"] == 40 and chk["OI"] == 50                         # 'income from operations before taxes' is pre-tax
    assert tot(out, "INTINC") + tot(out, "INTEXP") == -10 and len(out["INTEXP"]) == 1


def test_product_and_service_lines_under_headings():
    # Apple-style: 'Net sales:' and 'Cost of sales:' headings with Products / Services under each
    rows = [("Net sales:", []), ("Products", [300.0]), ("Services", [100.0]), ("Total net sales", [400.0]),
            ("Cost of sales:", []), ("Products", [200.0]), ("Services", [30.0]), ("Total cost of sales", [230.0]),
            ("Gross margin", [170.0]), ("Operating expenses:", []), ("Research and development", [30.0]),
            ("Selling, general and administrative", [25.0]), ("Total operating expenses", [55.0]), ("Operating income", [115.0]),
            ("Other income/(expense), net", [5.0]), ("Income before provision for income taxes", [120.0]),
            ("Provision for income taxes", [20.0]), ("Net income", [100.0])]
    out, chk = map_is(rows, [], 0.45)
    assert tot(out, "REV") == 400 and tot(out, "COGS") == -230 and tot(out, "OTHINC") == 5


def test_dxcm_style_expenses_shown_negative_keep_their_meaning():
    # DXCM prints non-operating expenses as negatives; both readings tie, the label decides
    rows = [("Revenue", [137.3]), ("Cost of sales", [51.8]), ("Gross profit", [85.5]), ("Research and development", [36.3]),
            ("Selling, general and administrative", [69.3]), ("Operating loss", [-20.1]), ("Interest income", [0.1]),
            ("Interest expense", [-0.1]), ("Loss before income taxes", [-20.1]), ("Income tax expense", [0.1]), ("Net loss", [-20.2])]
    out, _ = map_is(rows, [], 0.45)
    assert tot(out, "INTINC") == 0.1 and tot(out, "INTEXP") == -0.1


def test_balance_sheet_gross_and_net_ppe_minority_and_held_for_sale():
    rows = [("Cash and cash equivalents", [10.0]), ("Investments", [5.0]), ("Current assets held for sale", [2.0]),
            ("Total current assets", [17.0]), ("Property, plant, and equipment", [100.0]), ("Accumulated depreciation", [-60.0]),
            ("Property, plant, and equipment, net", [40.0]), ("Other intangible assets, net", [8.0]), ("Total assets", [65.0]),
            ("Accounts payable", [5.0]), ("Accrued income taxes", [1.0]), ("Other accrued expenses", [4.0]),
            ("Total current liabilities", [10.0]), ("Long-term debt", [20.0]), ("Accrued compensation and retirement benefits", [3.0]),
            ("Total liabilities", [33.0]), ("Redeemable noncontrolling interests", [2.0]), ("Shareholders' equity:", []),
            ("Retained earnings", [29.0]), ("Total shareholders' equity", [29.0]), ("Noncontrolling interests", [1.0]),
            ("Total equity", [30.0]), ("Total liabilities and equity", [65.0])]
    out, chk = map_bs(rows, [])
    assert tot(out, "PPE") == 40 and tot(out, "STSEC") == 5 and tot(out, "OCA") == 2      # net PP&E only; no double count
    assert tot(out, "TAXPAY") == 1 and tot(out, "ACCR") == 4 and tot(out, "PENSION") == 3
    assert tot(out, "MEZZ") == 2 and tot(out, "EQ") == 29 and tot(out, "NCTL") == 1


def test_cash_flow_note_repurchase_is_debt_and_asset_sale_is_not_capex():
    rows = [("Net income", [10.0]), ("Depreciation and amortization", [5.0]), ("Net cash provided by operating activities", [15.0]),
            ("Purchases of property and equipment", [-4.0]), ("Proceeds from sale of property and equipment", [1.0]),
            ("Net cash used in investing activities", [-3.0]), ("Repurchase of convertible notes", [-50.0]),
            ("Repurchase of common stock", [-20.0]), ("Dividends paid", [-6.0]), ("Proceeds from issuance of common stock", [2.0]),
            ("Net cash used in financing activities", [-74.0])]
    out, _ = map_cf(rows, [])
    assert tot(out, "CAPEX") == -4 and tot(out, "DIVEST") == 1
    assert tot(out, "DEBT") == -50 and tot(out, "BUYBACK") == -20 and tot(out, "DIV") == -6 and tot(out, "STOCK") == 2


def test_rounding_plug_only_for_whole_number_reporters():
    # MDT reports whole $ millions: its own total can be 1 off the sum of its lines -> plugged (logged), not a failure
    out = {"CASH": [["c", 10.0, "primary"]], "AR": [["a", 6.0, "primary"]]}
    plug_rounding(out, CA, "OCA", 17.0, unit_of([("Cash", [10.0]), ("AR", [6.0])]), "current assets")
    assert out["OCA"] == [["Rounding to the reported current assets", 1.0, "rounding"]]
    out = {"CASH": [["c", 10.1, "primary"]]}
    plug_rounding(out, CA, "OCA", 11.6, unit_of([("Cash", [10.1])]), "current assets")   # 1.5 off at 0.1 precision: a real gap
    assert "OCA" not in out


def test_banks_insurers_and_reits_are_detected():
    bank = {"BS": [("Loans, net", [1.0]), ("Total deposits", [2.0])], "IS": [("Net interest income", [1.0])]}
    reit = {"BS": [("Investments in real estate, net", [1.0])], "IS": []}
    tech = {"BS": [("Customer deposits", [1.0])], "IS": [("Interest income", [1.0])]}
    assert financial_kind(bank) == "bank" and financial_kind(reit) == "REIT" and financial_kind(tech) is None
