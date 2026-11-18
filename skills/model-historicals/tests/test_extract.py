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


# ---- Abbott (ABT): "Earnings" wording, mixed units, a balance sheet split over two pages, unlabeled totals
from mdtables import find_tables

ABT_10Q_IS = """Condensed Consolidated Statement of Earnings

(dollars in millions except per share data; shares in thousands)

|  | Three Months Ended |
| --- | --- |
| Net sales | $ | 10,377 |  |
| Cost of products sold | 4,603 |  |
| Research and development | 698 |  |
| Selling, general and administrative | 2,936 |  |
| Total operating cost and expenses | 8,237 |  |
| Operating earnings | 2,140 |  |
| Interest expense | 140 |  |
| Earnings before taxes | 2,000 |  |
| Taxes on earnings | 305 |  |
| Net Earnings | 1,695 |  |
| Basic Earnings Per Common Share | $ | 0.97 |  |
| Average Number of Common Shares Outstanding Used for Basic Earnings Per Common Share | 1,743,040 |  |
| Average Number of Common Shares Outstanding Plus Dilutive Common Stock Options | 1,751,153 |  |
"""


def test_dollars_in_millions_with_shares_in_thousands():
    # ABT 10-Qs: "(dollars in millions except per share data; shares in thousands)". Reading the shares unit for the whole
    # table divided every dollar figure by 1,000; EPS ("Per Common Share") was scaled too.
    t = find_tables(ABT_10Q_IS, min_rows=5)
    rows = dict(t["IS"])
    assert rows["Net sales"] == [10377.0] and rows["Basic Earnings Per Common Share"] == [0.97]
    assert rows["Average Number of Common Shares Outstanding Used for Basic Earnings Per Common Share"] == [1743.04]  # millions
    out, chk = map_is(t["IS"], [], 0.45)
    assert chk["OI"] == 2140 and chk["SB"] == 1743.04 and chk["SD"] == 1751.153   # 'Operating earnings' is operating income
    assert abs(tot(out, *IS_SUM) - 2140) < 0.01        # 'Total operating cost and expenses' is a total, not one more cost


ABT_10K_BS = """Consolidated Balance Sheet

(dollars in millions)

|  | December 31 |
| --- | --- |
| ​ | 2024 |  | 2023 |
| Assets |  |  |  |
| Current assets: |  |  |  |
| Cash and cash equivalents | $ | 7,616 |  |  | $ | 6,896 |  |
| Trade receivables | 6,925 |  |  | 6,565 |  |
| Inventories: |  |  |  |
| Finished products | 3,700 |  |  | 3,946 |  |
| Materials | 1,654 |  |  | 1,817 |  |
| Total inventories | 5,354 |  |  | 5,763 |  |
| Total current assets | 19,895 |  |  | 19,224 |  |
| Property and equipment, at cost: |  |  |  |
| Land | 528 |  |  | 529 |  |
| Equipment | 22,212 |  |  | 21,404 |  |
|  | 22,740 |  |  | 21,933 |  |
| Less: accumulated depreciation and amortization | 12,082 |  |  | 11,779 |  |
| Net property and equipment | 10,658 |  |  | 10,154 |  |
| Goodwill | 23,108 |  |  | 23,679 |  |
|  | $ | 53,661 |  |  | $ | 53,057 |  |

44

Consolidated Balance Sheet

(dollars in millions)

|  | December 31 |
| --- | --- |
|  | 2024 |  | 2023 |
| Liabilities and Shareholders’ Investment |  |  |  |
| Current liabilities: |  |  |  |
| Trade accounts payable | $ | 4,195 |  |  | $ | 4,295 |  |
| Total current liabilities | 4,195 |  |  | 4,295 |  |
| Long-term debt | 12,625 |  |  | 13,599 |  |
| Shareholders’ Investment: |  |  |  |
| Common shares | 24,858 |  |  | 24,869 |  |
| Earnings employed in the business | 11,741 |  |  | 10,070 |  |
| Total Abbott Shareholders’ Investment | 36,599 |  |  | 34,939 |  |
| Noncontrolling Interests in Subsidiaries | 242 |  |  | 224 |  |
| Total Shareholders’ Investment | 36,841 |  |  | 35,163 |  |
|  | $ | 53,661 |  |  | $ | 53,057 |  |
"""


def test_balance_sheet_split_over_two_pages_with_unlabeled_totals():
    # ABT 10-K: liabilities sit under a second "Consolidated Balance Sheet" heading; total assets has no label; a year
    # header row with an invisible label must not become a line item (it put 2019 into current assets).
    t = find_tables(ABT_10K_BS, min_rows=5)
    out, chk = map_bs(t["BS"], [])
    assert chk["TA"] == 53661 and chk["TCL"] == 4195                       # the unlabeled row before liabilities
    assert tot(out, "INV") == 5354 and tot(out, "OCA") == 0                # inventory parts are inventory
    assert tot(out, "PPE") == 10658 and tot(out, "OTHA") == 0              # gross parts (land...) are detail of net PP&E
    assert tot(out, "EQ") == 36599 and tot(out, "NCTL") == 242             # "Shareholders' Investment" is equity
    assert tot(out, "OTHLTL") == 0


def test_discontinued_operations_subtotal_and_before_tax_wording():
    # ABT 2016-2019: discontinued operations shown as parts plus their own 'Net earnings from discontinued operations'
    # subtotal (counted twice before), and 'before tax' (singular) as the pre-tax label
    rows = [("Net sales", [100.0]), ("Cost of products sold", [40.0]), ("Operating earnings", [60.0]),
            ("Interest expense", [10.0]), ("Earnings from continuing operations before tax", [50.0]),
            ("Tax expense (benefit) on earnings from continuing operations", [10.0]),
            ("Earnings from Continuing Operations", [40.0]),
            ("Earnings from Discontinued Operations, net of taxes", [21.0]),
            ("Gain on sale of Discontinued Operations, net of taxes", [16.0]),
            ("Net Earnings from Discontinued Operations, net of taxes", [37.0]), ("Net Earnings", [77.0])]
    out, chk = map_is(rows, [], 0.45)
    assert chk["PRETAX"] == 50 and tot(out, "DISCOPS") == 37 and chk["NI"] == 77


def test_page_break_line_with_only_an_invisible_character_does_not_end_the_table():
    # ABT 10-Qs (2020-22): the balance sheet continues after a line holding only a zero-width space
    md = ABT_10K_BS.replace("\n\n44\n\nConsolidated Balance Sheet\n\n(dollars in millions)\n\n", "\n\n​\n\n")
    out, chk = map_bs(find_tables(md, min_rows=5)["BS"], [])
    assert chk["TA"] == 53661 and chk["TCL"] == 4195 and tot(out, "EQ") == 36599


def test_working_capital_lines_without_a_heading_buybacks_and_dispositions():
    # ABT lists receivables, inventories... straight after the non-cash items, with no 'Changes in operating assets' heading
    rows = [("Net earnings", [100.0]), ("Depreciation", [10.0]), ("Share-based compensation", [5.0]),
            ("Trade receivables", [-7.0]), ("Inventories", [-1.0]), ("Prepaid expenses and other assets", [-8.0]),
            ("Trade accounts payable and other liabilities", [4.0]), ("Income taxes", [-3.0]),
            ("Net Cash From Operating Activities", [100.0]), ("Acquisitions of property and equipment", [-20.0]),
            ("Proceeds from business dispositions", [2.0]), ("Net Cash From (Used in) Investing Activities", [-18.0]),
            ("Purchases of common shares", [-13.0]), ("Proceeds from stock options exercised", [3.0]),
            ("Net Cash From (Used in) Financing Activities", [-10.0])]
    out, _ = map_cf(rows, [])
    assert tot(out, "W_AR") == -7 and tot(out, "W_INV") == -1 and tot(out, "W_PRE") == -8
    assert tot(out, "W_AP") == 4 and tot(out, "W_TAX") == -3 and tot(out, "OTHNC") == 0
    assert tot(out, "DIVEST") == 2 and tot(out, "BUYBACK") == -13 and tot(out, "STOCK") == 3


# ---- two-class EPS (ABT): EPS uses net earnings allocated to common shares, not net earnings
from extract import allocated_to_common, two_class


def test_allocated_to_common_only_when_printed_to_the_million():
    # 10-K and 10-Q wording; the first figure is the filing's own period. '$1.3 billion' is too coarse to fix EPS to the
    # cent (it is ~$50M either way), so it is refused rather than used.
    assert allocated_to_common("Net earnings allocated to common shares in 2024, 2023 and 2022 were $13.351 billion, "
                               "$5.701 billion and $6.905 billion, respectively.") == 13351
    assert allocated_to_common("Net earnings allocated to common shares for the three months ended June 30, 2021 and 2020 "
                               "were $1.184 billion and $534 million, respectively") == 1184
    assert allocated_to_common("Net earnings allocated to common shares in 2017, 2016 and 2015 were $468 million") == 468
    assert allocated_to_common("Net earnings allocated to common shares for the three months ended March 31, 2025 and "
                               "2024 were $1.3 billion and $1.2 billion") is None
    assert allocated_to_common("no such sentence") is None


def test_two_class_fills_a_whole_year_or_none_of_it():
    # Q4 = FY - Q1 - Q2 - Q3 in the model, so one missing quarter would put its allocation into Q4: skip the year instead
    mk = lambda ni, al: {"IS": {}, "IS_chk": {"NI": ni, "ALLOC_COMMON": al}}
    p = {"Q1 24": mk(1225, 1220), "Q2 24": mk(1302, 1297), "Q3 24": mk(1646, 1640), "FY 24": mk(13402, 13351),
         "Q1 19": mk(672, 668), "Q2 19": mk(1005, None), "Q3 19": mk(959, 954), "FY 19": mk(3687, 3666)}
    skipped = two_class(p)
    assert p["FY 24"]["IS"]["PARTSEC"] == [["Net earnings allocated to common shares (EPS note)", 13351, "two-class"],
                                          ["Less: net earnings", -13402, "two-class"]]
    assert "PARTSEC" not in p["Q1 19"]["IS"] and "19" in skipped
    p["Q1 25"] = mk(1325, None); p["FY 25"] = mk(6500, None)    # printed only as '$1.3 billion': must still be reported
    assert "25" in two_class(p)
    assert two_class({"Q1 24": mk(10, None), "FY 24": mk(40, None)}) == {}   # never printed: not a two-class company
