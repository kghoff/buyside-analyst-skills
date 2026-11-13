"""Rebuild assets/core_template.xlsx as the superset template (2026-11-06): the DXCM example rows plus the line items other
companies report (Regulation S-X Art. 5 captions, the Morningstar 43-company line-item count, common 3-statement
models). build.py deletes the optional rows a company never reports, so every model shows only its own lines.

usage: python3 make_template.py <old core_template.xlsx> <new core_template.xlsx>
Rows are cloned from the old template's styles; every subtotal formula is rewritten from SUBTOTALS below."""
import sys
from copy import copy

import openpyxl
from openpyxl.utils import get_column_letter as L

O = "        "          # opex label indent, as in the house template
W = "     (+/-)  "      # working-capital label indent
# (role or None, label, units, style source = old template row). None role = header / blank / copied as is.
LAYOUT = [
    ("old", 1), ("old", 2), ("old", 3), ("old", 4),
    ("REV", "Revenue:", "$ M", 5), ("COGS", "(-) Cost of Sales", "$ M", 6), ("GP", "Gross Profit", "$ M", 7), ("old", 8),
    ("old", 9), ("RD", O + "(-) R&D", "$ M", 10), ("SGA", O + "(-) SG&A", "$ M", 11),
    ("SM", O + "(-) Sales & Marketing", "$ M", 10), ("GA", O + "(-) General & Administrative", "$ M", 10),
    ("AMORT", O + "(-) Amortization of Intangibles", "$ M", 10), ("RESTR", O + "(-) Restructuring", "$ M", 10),
    ("IMPAIR", O + "(-) Impairment", "$ M", 10), ("ACQEXP", O + "(-) Acquisition & Integration Costs", "$ M", 10),
    ("LITIG", O + "(-) Litigation", "$ M", 10), ("GAINOP", O + "(+/-) Gain / Loss on Sale of Assets", "$ M", 10),
    ("OTHOPEX", O + "(-) Other Operating Expense / (Income)", "$ M", 10),
    ("TOPEX", "(-) Total Operating Expenses", "$ M", 12), ("ISDA", "(-) Depreciation & Amortization", "$ M", 13), ("old", 14),
    ("OI", "Operating Income", "$ M", 15), ("OTHINC", "Other Income", "$ M", 16),
    ("GAININV", "(+/-) Gain / Loss on Investments", "$ M", 16), ("DEBTEXT", "(+/-) Loss on Debt Extinguishment", "$ M", 16),
    ("EQAFF", "(+/-) Equity Method Income", "$ M", 16),
    ("EBIT", "EBIT:", "$ M", 17), ("old", 18), ("EBITDA", "EBITDA:", "$ M", 19), ("old", 20),
    ("INTINC", "(+) Interest Income", "$ M", 21), ("INTEXP", "(-) Interest Expense", "$ M", 22),
    ("PRETAX", "Pre-Tax Income:", "$ M", 23), ("TAX", "(-) Income Taxes", "$ M", 24), ("TAXRATE", "Income Tax Rate", "%", 25),
    ("EQAFF_AT", "(+/-) Equity Method Income, after tax", "$ M", 24),
    ("DISCOPS", "(+/-) Discontinued Operations, net of tax", "$ M", 24),
    ("NI", "Net Income", "$ M", 26), ("NCI_IS", "(-) Net Income to Noncontrolling Interests", "$ M", 24),
    ("PREFDIV", "(-) Preferred Dividends", "$ M", 24), ("NI_COMMON", "Net Income to Common", "$ M", 26),
    ("SB", "Shares, basic", "M", 27), ("SD", "Shares, diluted", "M", 28),
    ("EPSB", "EPS, basic", "$", 29), ("EPSD", "EPS, diluted", "$", 30), ("old", 31),
    ("old", 32), ("old", 33),
    ("CASH", "Cash & Equivalents", "$ M", 34), ("STSEC", "Short-term marketable securities", "$ M", 35),
    ("AR", "Accounts Receivable", "$ M", 36), ("INV", "Inventory", "$ M", 37), ("PRE", "Prepaid Assets", "$ M", 38),
    ("OCA", "Other Current Assets", "$ M", 38), ("TCA", "Total Current Assets:", "$ M", 39), ("old", 40),
    ("PPE", "Net PP&E", "$ M", 41), ("ROU", "Operating Lease ROUs", "$ M", 42), ("GWI", "Goodwill & Intangibles", "$ M", 43),
    ("LTINV", "Long-term Investments", "$ M", 45), ("DTA", "DTAs", "$ M", 44), ("OTHA", "Other Assets", "$ M", 45),
    ("TNCA", "Total Non-Current Assets", "$ M", 46), ("old", 47), ("TA", "TOTAL ASSETS:", "$ M", 48), ("old", 49),
    ("old", 50), ("AP", "Accounts Payable", "$ M", 51), ("PAY", "Accrued payroll & related expenses", "$ M", 52),
    ("ACCR", "Accrued Expenses & Other", "$ M", 52), ("TAXPAY", "Income Taxes Payable", "$ M", 52),
    ("CURDEBT", "Current Portion of Debt", "$ M", 53), ("OPLLC", "Operating Lease Liabilities", "$ M", 54),
    ("CLOTH", "Deferred Revenue", "$ M", 55), ("OCL", "Other Current Liabilities", "$ M", 55),
    ("TCL", "Total Current Liabilities:", "$ M", 56), ("old", 57),
    ("LTDEBT", "Long-Term Debt:", "$ M", 58), ("OPLLLT", "LT Operating lease liabilities", "$ M", 59),
    ("DEFREVLT", "LT Deferred Revenue", "$ M", 60), ("DTL", "Deferred Tax Liabilities", "$ M", 60),
    ("PENSION", "Pension & Retirement Benefits", "$ M", 60), ("OTHLTL", "Other LT Liabilities", "$ M", 60),
    ("TLTL", "Total LT Liabilities:", "$ M", 61), ("old", 62), ("TL", "Total Liabilities:", "$ M", 63),
    ("MEZZ", "Redeemable / Mezzanine Equity", "$ M", 64), ("EQ", "Total Stockholders Equity:", "$ M", 64),
    ("NCTL", "Noncontrolling Interests", "$ M", 64), ("TLE", "TOTAL LIABILITIES & EQUITY:", "$ M", 65), ("old", 66),
    ("BALCHK", "Balance Check:", None, 67), ("old", 68), ("old", 69),
    ("old", 70), ("old", 71), ("NI_LINK", "Net Income:", "$ M", 72), ("DA", "(+) Depreciation & Amortization", "$ M", 73),
    ("SBC", "(+) SBC", "$ M", 74), ("NCI", "(+/-) Non-cash Interest", "$ M", 75), ("DT", "(+/-) Deferred Income taxes", "$ M", 76),
    ("EQI", "(+/-) Gain / Loss on Equity Investments", "$ M", 77), ("IMPAIR_CF", "(+) Impairment & Write-downs", "$ M", 78),
    ("GAIN_CF", "(+/-) Gain / Loss on Sale of Assets", "$ M", 78), ("OTHNC", "(+/-) Other non-cash expense", "$ M", 78),
    ("old", 79), ("W_AR", W + "Accounts Receivable", "$ M", 80), ("W_INV", W + "Inventory", "$ M", 81),
    ("W_PRE", W + "Prepaid Assets", "$ M", 82), ("W_ROU", W + "Operating Lease ROU Assets / Liabilities, Net", "$ M", 83),
    ("W_AP", W + "Accounts Payable & Accured Liabilities", "$ M", 84), ("W_PAY", W + "Accrued payroll", "$ M", 85),
    ("W_OTH", W + "Deferred Revenue & Other Liabilities", "$ M", 86), ("W_TAX", W + "Income Taxes", "$ M", 86),
    ("W_OTHAL", W + "Other Operating Assets & Liabilities", "$ M", 86),
    ("WCNET", "Working Capital Changes, Net", "$ M", 87), ("old", 88),
    ("CFO", "Net Cash Provided by Operating Activities:", "$ M", 89), ("old", 90), ("old", 91),
    ("PURSEC", "(-)  Purchase Marketable Securities", "$ M", 92), ("SALESEC", "(+) Sale Marketable Securities", "$ M", 93),
    ("CAPEX", "(-) CapEx (Purchase of PP&E)", "$ M", 94), ("CAPSW", "(-) Capitalized Software", "$ M", 95),
    ("ACQ", "(-) Acquisitions", "$ M", 95), ("DIVEST", "(+) Proceeds from Divestitures & Asset Sales", "$ M", 95),
    ("OTHINV", "(+/-) Other", "$ M", 96), ("CFI", "Net Cash Provided by Investing Activities:", "$ M", 97), ("old", 98),
    ("old", 99), ("STOCK", "(+) Stock Issuance / Employee Plans", "$ M", 100), ("BUYBACK", "(-) Share Repurchases", "$ M", 100),
    ("DIV", "(-) Dividends Paid", "$ M", 100), ("DEBT", "(+/-) Debt Issued / Repaid", "$ M", 101),
    ("OTHFIN", "(+/-) Other", "$ M", 102), ("CFF", "Net Cash Provided by Financing Activities:", "$ M", 103), ("old", 104),
    ("FX", "Exchange Rate Effects:", "$ M", 105), ("BEG", "Beginning Cash:", "$ M", 106), ("CHG", "Net Change in Cash:", "$ M", 107),
    ("END", "Ending Cash:", "$ M", 108), ("old", 109), ("old", 110),
    ("CASHBS", "      Cash & Equivalents (BS):", "$ M", 111), ("RC", "      Restricted Cash:", "$ M", 112),
    ("TOTCASH", "Total Cash, end of period:", "$ M", 113), ("old", 114), ("CASHCHK", "Cash Check:", None, 115),
]
WC = ["W_AR", "W_INV", "W_PRE", "W_ROU", "W_AP", "W_PAY", "W_OTH", "W_TAX", "W_OTHAL"]
SUBTOTALS = {           # role: [(sign, role)]; build.py drops the terms of rows a company doesn't report
    "GP": "REV COGS", "TOPEX": "RD SGA SM GA AMORT RESTR IMPAIR ACQEXP LITIG GAINOP OTHOPEX", "OI": "GP TOPEX ISDA",
    "EBIT": "OI OTHINC GAININV DEBTEXT EQAFF", "EBITDA": "EBIT -ISDA", "PRETAX": "EBIT INTINC INTEXP",
    "NI": "PRETAX TAX EQAFF_AT DISCOPS", "NI_COMMON": "NI NCI_IS PREFDIV",
    "TCA": "CASH STSEC AR INV PRE OCA", "TNCA": "PPE ROU GWI LTINV DTA OTHA", "TA": "TNCA TCA",
    "TCL": "AP PAY ACCR TAXPAY CURDEBT OPLLC CLOTH OCL", "TLTL": "LTDEBT OPLLLT DEFREVLT DTL PENSION OTHLTL",
    "TL": "TLTL TCL", "TLE": "TL MEZZ EQ NCTL", "BALCHK": "TA -TLE", "NI_LINK": "NI", "WCNET": " ".join(WC),
    "CFO": "NI_LINK DA SBC NCI DT EQI IMPAIR_CF GAIN_CF OTHNC " + " ".join(WC),
    "CFI": "PURSEC SALESEC CAPEX CAPSW ACQ DIVEST OTHINV", "CFF": "STOCK BUYBACK DIV DEBT OTHFIN",
    "CHG": "CFF CFI CFO FX", "END": "BEG CHG", "CASHBS": "CASH", "TOTCASH": "CASHBS RC", "CASHCHK": "END -TOTCASH",
}
RATIOS = {"TAXRATE": "=-{TAX}/{PRETAX}", "EPSB": "={NI_COMMON}/{SB}", "EPSD": "={NI_COMMON}/{SD}"}


def main(src, out):
    wb = openpyxl.load_workbook(src); ws = wb.worksheets[0]
    maxc = ws.max_column
    snap = {r: [(copy(ws.cell(r, c)._style), ws.cell(r, c).value) for c in range(1, maxc + 1)] for r in range(1, ws.max_row + 1)}
    dims = {r: copy(d) for r, d in ws.row_dimensions.items()}
    data = [c for c in range(4, maxc + 1) if ws.cell(2, c).value]
    reported = [c for c in data if not str(ws.cell(2, c).value).rstrip().endswith("E")]
    for r in list(range(3, ws.max_row + 1)):
        for c in range(1, maxc + 1): ws.cell(r, c).value = None
    ws.row_dimensions.clear()
    rowof = {}
    for i, spec in enumerate(LAYOUT, 1):
        if spec[0] == "old": continue
        rowof[spec[0]] = i
    for i, spec in enumerate(LAYOUT, 1):
        src_row = spec[1] if spec[0] == "old" else spec[3]
        for c in range(1, maxc + 1):
            ws.cell(i, c)._style = copy(snap[src_row][c - 1][0])
        if src_row in dims: ws.row_dimensions[i].height = dims[src_row].height
        if spec[0] == "old":
            for c in range(1, maxc + 1): ws.cell(i, c).value = snap[src_row][c - 1][1]
            continue
        role, label, units = spec[0], spec[1], spec[2]
        ws.cell(i, 2).value, ws.cell(i, 3).value = label, units
        for c in data:
            col = L(c)
            if role in SUBTOTALS:
                terms = SUBTOTALS[role].split()
                f = "".join(("-" if t.startswith("-") else "+") + f"{col}{rowof[t.lstrip('-')]}" for t in terms)
                ws.cell(i, c).value = "=" + f.lstrip("+")
            elif role in RATIOS:
                ws.cell(i, c).value = RATIOS[role].format(**{k: f"{col}{v}" for k, v in rowof.items()})
            elif role != "BEG":
                ws.cell(i, c).value = 0 if c in reported else None
    if ws.freeze_panes:                                  # keep the user's pane on the same line (CF investing) as before
        ws.freeze_panes = f"{ws.freeze_panes.rstrip('0123456789')}{rowof['PURSEC']}"
    wb.save(out)
    print(f"{out}: {len(LAYOUT)} rows, {len(rowof)} roles")


if __name__ == "__main__":
    main(*sys.argv[1:3])
