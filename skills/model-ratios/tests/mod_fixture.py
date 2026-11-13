"""A synthetic MOD tab laid out exactly like model-historicals's output (same labels, same rows, same header style),
with simple typed numbers, so tests don't depend on real filings."""
import openpyxl

# (row, column A text, column B text) - model-historicals core template, rows 1-114
LABELS = [
    (1, "TEST - Model", None), (2, "INCOME STATEMENT", None),
    (4, None, "Revenue:"), (5, None, "(-) Cost of Sales"), (6, None, "Gross Profit"),
    (8, None, "(-) Operating Expenses (break up if possible):"), (9, None, "        (-) R&D"), (10, None, "        (-) SG&A"),
    (11, None, "(-) Total Operating Expenses"), (12, None, "(-) Depreciation & Amortization"),
    (14, None, "Operating Income"), (15, None, "Other Income"), (16, None, "EBIT:"), (18, None, "EBITDA:"),
    (20, None, "(+) Interest Income"), (21, None, "(-) Interest Expense"), (22, None, "Pre-Tax Income:"),
    (23, None, "(-) Income Taxes"), (24, None, "Income Tax Rate"), (25, None, "Net Income"),
    (26, None, "Shares, basic"), (27, None, "Shares, diluted"), (28, None, "EPS, basic"), (29, None, "EPS, diluted"),
    (31, "BALANCE SHEET", None), (32, "ASSETS:", None),
    (33, None, "Cash & Equivalents"), (34, None, "Short-term marketable securities"), (35, None, "Accounts Receivable"),
    (36, None, "Inventory"), (37, None, "Prepaid Assets"), (38, None, "Total Current Assets:"),
    (40, None, "Net PP&E"), (41, None, "Operating Lease ROUs"), (42, None, "Goodwill & Intangibles"), (43, None, "DTAs"),
    (44, None, "Other Assets"), (45, None, "Total Non-Current Assets"), (47, None, "TOTAL ASSETS:"),
    (49, "LIABILITIES & EQUITY:", None),
    (50, None, "Accounts Payable & Accrued Liabilities"), (51, None, "Accrued payroll & related expenses"),
    (52, None, "Current LT Senior Convertible Notes"), (53, None, "Operating Lease Liabilities"),
    (54, None, "Deferred Revenue / Other"), (55, None, "Total Current Liabilities:"),
    (57, None, "LT Senior Convertible Debt:"), (58, None, "LT Operating lease liabilities"),
    (59, None, "Other LT Liabilities"), (60, None, "Total LT Liabilities:"), (62, None, "Total Liabilities:"),
    (63, None, "Total Stockholders Equity:"), (64, None, "TOTAL LIABILITIES & EQUITY:"), (66, None, "Balance Check:"),
    (69, "CASH FLOW STATEMENT", None), (70, "CASH FLOWS FROM OPERATING ACTIVITIES:", None),
    (71, None, "Net Income:"), (72, None, "(+) Depreciation & Amortization"), (73, None, "(+) SBC"),
    (74, None, "(+/-) Non-cash Interest"), (75, None, "(+/-) Deferred Income taxes"),
    (76, None, "(+/-) Gain / Loss on Equity Investments"), (77, None, "(+/-) Other non-cash expense"),
    (78, None, "Working Capital Changes"), (79, None, "     (+/-)  Accounts Receivable"),
    (80, None, "     (+/-)  Inventory"), (81, None, "     (+/-)  Prepaid Assets"),
    (82, None, "     (+/-)  Operating Lease ROU Assets / Liabilities"),
    (83, None, "     (+/-)  Accounts Payable & Accured Liabilities"), (84, None, "     (+/-)  Accrued payroll"),
    (85, None, "     (+/-)  Deferred Revenue & Other Liabilities"), (86, None, "Working Capital Changes, Net"),
    (88, None, "Net Cash Provided by Operating Activities:"), (90, "CASH FLOWS FROM INVESTING ACTIVITIES:", None),
    (91, None, "(-)  Purchase Marketable Securities"), (92, None, "(+) Sale Marketable Securities"),
    (93, None, "(-) CapEx (Purchase of PP&E)"), (94, None, "(-) Acquisitions"), (95, None, "(+/-) Other"),
    (96, None, "Net Cash Provided by Investing Activities:"), (98, "CASH FLOWS FROM FINANCING ACTIVITIES:", None),
    (99, None, "(+/-) Stock Issuance / Repurchase"), (100, None, "(+/-) Debt Issued / Repaid"), (101, None, "(+/-) Other"),
    (102, None, "Net Cash Provided by Financing Activities:"), (104, None, "Exchange Rate Effects:"),
    (105, None, "Beginning Cash:"), (106, None, "Net Change in Cash:"), (107, None, "Ending Cash:"),
    (109, None, "Reconciliation for cash equivalents & restricted cash:"), (110, None, "      Cash & Equivalents (BS):"),
    (111, None, "      Restricted Cash:"), (112, None, "Total Cash, end of period:"), (114, None, "Cash Check:"),
]
NO_DATA = {1, 2, 8, 31, 32, 49, 69, 70, 78, 90, 98, 109}
NEGATIVE = {5, 9, 10, 11, 12, 21, 23, 91, 93}       # costs / outflows are stored negative (model-historicals convention)

# header row 2 from column D: (label, reported?)
HEADER = []
for y in (2021, 2022, 2023):
    HEADER += [(f"Q{q} {y % 100}", True) for q in (1, 2, 3, 4)] + [(y, True), (None, None)]
HEADER += [("Q1 24", True), ("Q2 24", True), ("Q3 24E", False), ("Q4 24E", False), ("2024E", False), (None, None), ("2025E", False)]


def make_mod(path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "MOD"
    for r, a, b in LABELS:
        if a: ws.cell(r, 1, a)
        if b: ws.cell(r, 2, b)
    ws.cell(2, 3, "Units")
    for i, (h, reported) in enumerate(HEADER):
        c = 4 + i
        ws.cell(2, c, h)
        if not reported: continue
        for r, _, b in LABELS:
            if r in NO_DATA: continue
            v = round(r * 10 + c * 0.5, 4)
            if r == 24: v = -1.19 if h == 2022 else 0.21        # tax rate (FY 2022 distorted, for outlier tests)
            ws.cell(r, c, -v if r in NEGATIVE else v)
    wb.save(path)
