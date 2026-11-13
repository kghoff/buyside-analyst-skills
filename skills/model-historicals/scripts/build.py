"""Step 3 - write the core-financials model from the template.

usage: python3 build.py --work <work_dir> --template <core_template.xlsx> --ticker DXCM --out <model.xlsx>
                        [--decisions decisions.json] [--years 10]

Layout (house layout): for each fiscal year  Q1 | Q2 | Q3 | Q4 | FY | spacer, then the current partial
year (reported quarters + remaining quarters as estimates), then annual estimate columns (as many as the template has).
Everything is driven by the row LABELS in the template's column B, so rows can move without editing this script
(if a label is renamed, update ROLE_PATTERNS). Writes <work>/JUDGMENT_CALLS.md alongside the model."""
import argparse, json, os, re
from copy import copy
import openpyxl
from openpyxl.formula.translate import Translator
from openpyxl.styles import Color, Font, PatternFill
from openpyxl.utils import get_column_letter as L, column_index_from_string as CI
from openpyxl.worksheet.dimensions import ColumnDimension

BLUE, GREEN, BLACK = "FF0000FF", "FF008000", "FF000000"
# the house convention: FY columns are grey ("Background 2", darker 10%) so years stand out from quarters
FY_FILL = PatternFill("solid", fgColor=Color(theme=2, tint=-0.0999786370433668))
DATA_WIDTH, SPACER_WIDTH = 11.0, 2.0       # 11.0 = 66 px in Mac Excel (Aptos Narrow 12): The user's standard

# (section, role, regex on the normalised column-B label). First match wins, in order, within its section.
# The template is a superset (2026-11-06); rows a company never reports are deleted by build.py (see OPTIONAL).
ROLE_PATTERNS = [
    ("IS", "REV", r"^revenue"), ("IS", "COGS", r"cost of sales|cost of revenue"), ("IS", "GP", r"^gross profit"),
    ("IS", "RD", r"r&d|research"), ("IS", "SGA", r"sg&a|selling"), ("IS", "SM", r"sales & marketing"),
    ("IS", "GA", r"general & administrative"), ("IS", "AMORT", r"amortization of intangibles"),
    ("IS", "RESTR", r"restructuring"), ("IS", "IMPAIR", r"impairment"), ("IS", "ACQEXP", r"acquisition & integration"),
    ("IS", "LITIG", r"litigation"), ("IS", "GAINOP", r"sale of assets"), ("IS", "OTHOPEX", r"other operating"),
    ("IS", "TOPEX", r"total operating expenses"),
    ("IS", "ISDA", r"depreciation"), ("IS", "OI", r"^operating income"), ("IS", "OTHINC", r"^other income"),
    ("IS", "GAININV", r"gain / loss on investments"), ("IS", "DEBTEXT", r"debt extinguishment"),
    ("IS", "EQAFF_AT", r"equity method income, after tax"), ("IS", "EQAFF", r"equity method income"),
    ("IS", "EBITDA", r"^ebitda"), ("IS", "EBIT", r"^ebit\b"), ("IS", "INTINC", r"interest income"),
    ("IS", "INTEXP", r"interest expense"), ("IS", "PRETAX", r"pre-tax"), ("IS", "TAXRATE", r"tax rate"),
    ("IS", "TAX", r"income taxes"), ("IS", "DISCOPS", r"discontinued operations"),
    ("IS", "NCI_IS", r"noncontrolling"), ("IS", "PREFDIV", r"preferred dividends"),
    ("IS", "NI_COMMON", r"^net income to common"), ("IS", "NI", r"^net income"), ("IS", "SB", r"shares, basic"),
    ("IS", "SD", r"shares, diluted"), ("IS", "EPSB", r"eps, basic"), ("IS", "EPSD", r"eps, diluted"),
    ("BS", "CASH", r"^cash"), ("BS", "STSEC", r"short-term"), ("BS", "AR", r"receivable"), ("BS", "INV", r"^inventory"),
    ("BS", "PRE", r"prepaid"), ("BS", "OCA", r"^other current assets"), ("BS", "TCA", r"total current assets"),
    ("BS", "PPE", r"pp&e|property"), ("BS", "ROU", r"lease rou"), ("BS", "GWI", r"goodwill"),
    ("BS", "LTINV", r"long-term investments"), ("BS", "DTA", r"^dta|deferred tax assets"), ("BS", "OTHA", r"^other assets"),
    ("BS", "TNCA", r"total non-current assets"), ("BS", "TA", r"^total assets"), ("BS", "AP", r"accounts payable"),
    ("BS", "PAY", r"accrued payroll"), ("BS", "ACCR", r"^accrued expenses"), ("BS", "TAXPAY", r"income taxes payable"),
    ("BS", "CURDEBT", r"^current"), ("BS", "OPLLC", r"^operating lease liab"),
    ("BS", "CLOTH", r"^deferred revenue"), ("BS", "OCL", r"^other current liabilities"),
    ("BS", "TCL", r"total current liabilities"), ("BS", "LTDEBT", r"^long-term debt|^lt .*(debt|notes)"),
    ("BS", "OPLLLT", r"^lt operating lease"), ("BS", "DEFREVLT", r"^lt deferred revenue"),
    ("BS", "DTL", r"deferred tax liab"), ("BS", "PENSION", r"pension"), ("BS", "OTHLTL", r"other lt liab"),
    ("BS", "TLTL", r"total lt liab"), ("BS", "TLE", r"total liabilities & equity"), ("BS", "TL", r"^total liabilities"),
    ("BS", "MEZZ", r"mezzanine"), ("BS", "EQ", r"stockholders equity|shareholders equity"), ("BS", "NCTL", r"^noncontrolling"),
    ("BS", "BALCHK", r"balance check"),
    ("CF", "NI_LINK", r"^net income"), ("CF", "DA", r"depreciation"), ("CF", "SBC", r"sbc|stock-based|share-based"),
    ("CF", "NCI", r"non-cash interest"), ("CF", "DT", r"deferred income tax"), ("CF", "EQI", r"equity investments"),
    ("CF", "IMPAIR_CF", r"impairment"), ("CF", "GAIN_CF", r"sale of assets"),
    ("CF", "OTHNC", r"other non-cash"), ("CF", "W_AR", r"accounts receivable"), ("CF", "W_INV", r"inventory"),
    ("CF", "W_PRE", r"prepaid"), ("CF", "W_ROU", r"lease rou"), ("CF", "W_AP", r"accounts payable"), ("CF", "W_PAY", r"accrued payroll"),
    ("CF", "W_OTH", r"deferred revenue"), ("CF", "W_TAX", r"^\(\+/-\) income taxes"), ("CF", "W_OTHAL", r"other operating assets"),
    ("CF", "WCNET", r"working capital changes, net"), ("CF", "CFO", r"operating activities"),
    ("CF", "PURSEC", r"purchase marketable"), ("CF", "SALESEC", r"sale marketable"), ("CF", "CAPEX", r"capex"),
    ("CF", "CAPSW", r"capitalized software"), ("CF", "ACQ", r"acquisitions"), ("CF", "DIVEST", r"divestitures"),
    ("CF", "OTHINV", r"^\(\+/-\) other"), ("CF", "CFI", r"investing activities"),
    ("CF", "STOCK", r"stock issuance"), ("CF", "BUYBACK", r"share repurchases"), ("CF", "DIV", r"dividends paid"),
    ("CF", "DEBT", r"debt issued"), ("CF", "OTHFIN", r"^\(\+/-\) other"),
    ("CF", "CFF", r"financing activities"), ("CF", "FX", r"exchange rate"), ("CF", "BEG", r"beginning cash"),
    ("CF", "CHG", r"net change in cash"), ("CF", "END", r"^ending cash"), ("CF", "CASHBS", r"cash & equivalents \(bs\)"),
    ("CF", "RC", r"^restricted cash"), ("CF", "TOTCASH", r"total cash"), ("CF", "CASHCHK", r"cash check"),
]
IS_IN = ["REV", "COGS", "RD", "SGA", "SM", "GA", "AMORT", "RESTR", "IMPAIR", "ACQEXP", "LITIG", "GAINOP", "OTHOPEX",
         "ISDA", "OTHINC", "GAININV", "DEBTEXT", "EQAFF", "INTINC", "INTEXP", "TAX", "EQAFF_AT", "DISCOPS", "NCI_IS", "PREFDIV"]
BS_IN = ["CASH", "STSEC", "AR", "INV", "PRE", "OCA", "PPE", "ROU", "GWI", "LTINV", "DTA", "OTHA", "AP", "PAY", "ACCR", "TAXPAY",
         "CURDEBT", "OPLLC", "CLOTH", "OCL", "LTDEBT", "OPLLLT", "DEFREVLT", "DTL", "PENSION", "OTHLTL", "MEZZ", "EQ", "NCTL"]
CF_IN = ["DA", "SBC", "NCI", "DT", "EQI", "IMPAIR_CF", "GAIN_CF", "OTHNC", "W_AR", "W_INV", "W_PRE", "W_ROU", "W_AP", "W_PAY",
         "W_OTH", "W_TAX", "W_OTHAL", "PURSEC", "SALESEC", "CAPEX", "CAPSW", "ACQ", "DIVEST", "OTHINV", "STOCK", "BUYBACK", "DIV",
         "DEBT", "OTHFIN", "FX"]
# input rows every model keeps even when zero (downstream skills read them: leverage, interest cover, EBITDA, FCF)
ALWAYS = {"REV", "COGS", "TAX", "CASH", "EQ", "CURDEBT", "LTDEBT", "DA", "CAPEX", "INTEXP"}
OPTIONAL = [r for r in IS_IN + BS_IN + CF_IN if r not in ALWAYS]
SUBTOTAL_FALLBACK = {"NI_COMMON": "NI"}          # deleted optional subtotal -> the row formulas use instead
REQUIRED = ["REV", "COGS", "GP", "OI", "PRETAX", "TAX", "NI", "SB", "SD", "EPSB", "EPSD", "CASH", "TCA", "TA", "TCL", "TL", "EQ",
            "TLE", "NI_LINK", "CFO", "CFI", "CFF", "BEG", "CHG", "END"] + OPTIONAL


def norm(s):
    return re.sub(r"\s+", " ", str(s or "").replace("\t", " ").replace(":", "")).strip().lower()


def fmt(v):
    s = f"{round(v, 3):.3f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def expr(comps):
    comps = [round(c, 3) for c in comps if abs(c) > 1e-9]
    if not comps: return "0"
    return fmt(comps[0]) + "".join(("+" if c > 0 else "-") + fmt(abs(c)) for c in comps[1:])


def typed(comps):
    e = expr(comps)
    return float(e) if re.fullmatch(r"-?[\d.]+", e) else "=" + e


def order(key):                     # "Q1 22" -> (22, 1); "FY 22" -> (22, 4)
    return (int(key[3:]), 4 if key.startswith("FY") else int(key[1]))


# the house convention: every core-financial number is blue in every column - typed values, YTD differences, Q4 plugs
# and balance-sheet Q4 (=FY) alike - because they are all reported facts. Only subtotals / ratios are black and
# links between sections (CF net income, beginning cash) are green.
INPUT_ROLES = IS_IN + ["SB", "SD"] + BS_IN + CF_IN + ["RC"]


def color_for(v, input_row=False):
    if v is None: return None
    if input_row: return BLUE
    if v is None: return None
    if not isinstance(v, str) or not v.startswith("="): return BLUE                   # typed input
    body = v[1:].replace("$", "")
    if re.fullmatch(r"[\d.+\-*/() ]+", body): return BLUE                              # number-only formula (=25.3+144.5)
    if re.fullmatch(r"[A-Z]{1,3}\d+", body): return GREEN                              # link to another cell
    if re.search(r"(?<![A-Z\d.])\d+\.?\d*(?![\d:])", re.sub(r"[A-Z]{1,3}\d+", "", body)) and re.search(r"[A-Z]{1,3}\d+", body):
        return BLUE                                                                    # hard-coded YTD number - prior quarters
    return BLACK


def find_rows(ws, hdr=2):
    """{role: row} by column-B label (ROLE_PATTERNS, first match per section) + section start rows"""
    sect_start = {"IS": hdr}
    for r in range(1, ws.max_row + 1):
        t = norm(ws.cell(r, 1).value)
        if t.startswith("balance sheet"): sect_start.setdefault("BS", r)
        if t.startswith("cash flow"): sect_start.setdefault("CF", r)
    bounds = {"IS": (sect_start["IS"], sect_start["BS"]), "BS": (sect_start["BS"], sect_start["CF"]), "CF": (sect_start["CF"], ws.max_row + 1)}
    row = {}
    for sect, (r0, r1) in bounds.items():
        taken = set()
        for s, role, pat in ROLE_PATTERNS:
            if s != sect or role in row: continue
            for r in range(r0, r1):
                if r in taken: continue
                if norm(ws.cell(r, 2).value) and re.search(pat, norm(ws.cell(r, 2).value)):
                    if role == "OTHFIN" and r < row.get("CFI", 0): continue
                    if role == "OTHINV" and r < row.get("CFO", 0): continue
                    row[role] = r; taken.add(r); break
    return row


def used_roles(per, years, splits_fx=True):
    """optional roles with a non-zero value in any period that will be built"""
    used = set()
    for key, p in per.items():
        if 2000 + int(key[3:]) not in years: continue
        for st in ("IS", "BS", "CF"):
            for role, items in p[st].items():
                if any(abs(v) > 0.0005 for _, v, _ in items): used.add(role)
        if abs(p["CF_chk"].get("FX") or 0) > 0.0005: used.add("FX")
    if used & {"NCI_IS", "PREFDIV"}: used.add("NI_COMMON")
    return used


def prune(ws, row, used, log):
    """delete the optional rows this company never reports; sums lose the term, EPS falls back to Net Income"""
    from rows import delete_rows             # here, not at the top: /model-ratios loads this file for ROLE_PATTERNS
    drop = [r for role, r in row.items() if (role in OPTIONAL or role in SUBTOTAL_FALLBACK) and role not in used]
    fb = {row[k]: row[v] for k, v in SUBTOTAL_FALLBACK.items() if k in row and k not in used}
    delete_rows(ws, drop, fb)
    gone = sorted(role for role, r in row.items() if r in drop)
    log.append(("Template rows", f"{len(gone)} optional rows not reported by this company were left out",
                ", ".join(gone)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True); ap.add_argument("--template", required=True)
    ap.add_argument("--ticker", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--decisions", default=None); ap.add_argument("--years", type=int, default=10)
    a = ap.parse_args()
    P = json.load(open(os.path.join(a.work, "periods.json")))
    per, q4 = P["periods"], P["q4"]
    dec = json.load(open(a.decisions)) if a.decisions and os.path.exists(a.decisions) else {}
    log = []

    # value overrides from decisions.json
    for o in dec.get("value_overrides", []):
        st = next(s for s in ("IS", "BS", "CF") if o["role"] in [*map_roles(s)])
        per[o["period"]][st][o["role"]] = [[o.get("label", "decisions.json override"), c, "override"] for c in o["components"]]
        log.append(("Value override", f"{o['period']} {o['role']} = {expr(o['components'])}", o.get("note", "")))

    wb = openpyxl.load_workbook(a.template); ws = wb[wb.sheetnames[0]]
    HDR = 2
    _fys = sorted(2000 + int(k[3:]) for k in per if k.startswith("FY"))
    _years = set(range(_fys[-1] - a.years + 1, _fys[-1] + 2))
    _row = find_rows(ws, HDR)
    _missing = [r for r in REQUIRED if r not in _row]
    if _missing:
        raise SystemExit(f"Template rows not found for roles {_missing}. Update ROLE_PATTERNS in build.py to match the template labels.")
    prune(ws, _row, used_roles(per, _years), log)
    # ---------------------------------------------------------------- template column types
    tcols = {}
    for c in range(4, ws.max_column + 1):
        h = str(ws.cell(HDR, c).value or "").strip()
        m = re.fullmatch(r"Q([1-4]) Y(\d+)(-?E)?", h)
        if m:
            kind = "QE" if m.group(3) else "Q"
            tcols.setdefault(f"{kind}{m.group(1)}", c)
        elif re.fullmatch(r"YEAR \d+", h): tcols.setdefault("FY", c)
        elif re.fullmatch(r"YEAR \d+E", h):
            tcols.setdefault("FYE", c) if "QE4" in tcols and "FYE" not in tcols else tcols.setdefault("AE", c)
    tcols["SP"] = tcols["FY"] + 1
    tcols["AESP"] = tcols["AE"] - 1
    n_annual = sum(1 for c in range(4, ws.max_column + 1) if re.fullmatch(r"YEAR \d+E", str(ws.cell(HDR, c).value or "").strip())) - 1
    for q in range(1, 5): tcols.setdefault(f"QE{q}", tcols[f"Q{q}"])
    tcols.setdefault("FYE", tcols["FY"])
    maxr = ws.max_row
    style = {k: {r: copy(ws.cell(r, c)._style) for r in range(1, maxr + 1)} for k, c in tcols.items()}
    tform = {k: {r: ws.cell(r, c).value for r in range(1, maxr + 1)} for k, c in tcols.items()}
    def find_dim(c):
        for k, d in ws.column_dimensions.items():
            lo, hi = d.min or CI(k), d.max or CI(k)
            if lo <= c <= hi: return (d.hidden, d.outlineLevel)
        return (False, 0)
    dims = {k: find_dim(c) for k, c in tcols.items()}

    # ---------------------------------------------------------------- template row roles (by label), after pruning
    row = find_rows(ws, HDR)

    # template fixes: net income must come from pre-tax (template may use EBIT, which skips interest rows)
    fq = tform["Q1"][row["NI"]] or ""
    if f"{L(tcols['Q1'])}{row['PRETAX']}" not in fq:
        for k in tform: tform[k][row["NI"]] = f"={L(tcols[k])}{row['PRETAX']}+{L(tcols[k])}{row['TAX']}"
        log.append(("Template formula fix", "Net Income = Pre-Tax Income + Taxes", "template formula skipped the interest income/expense rows"))
    if "TAXRATE" in row and f"{L(tcols['Q1'])}{row['PRETAX']}" not in (tform["Q1"][row["TAXRATE"]] or ""):
        for k in tform: tform[k][row["TAXRATE"]] = f"=-{L(tcols[k])}{row['TAX']}/{L(tcols[k])}{row['PRETAX']}"
        log.append(("Template formula fix", "Income Tax Rate = -Taxes / Pre-Tax Income", "template divided by EBIT"))
    # EBITDA adds back the cash-flow D&A (all depreciation + amortization, wherever it sits in the income statement).
    # The template subtracted the income-statement D&A row, which most companies don't report, leaving EBITDA = EBIT.
    # Same definition as /model-ratios (house default).
    if "EBITDA" in row and "EBIT" in row and "DA" in row:
        for k in tform: tform[k][row["EBITDA"]] = f"={L(tcols[k])}{row['EBIT']}+{L(tcols[k])}{row['DA']}"
        log.append(("Template formula fix", "EBITDA = EBIT + D&A from the cash flow statement",
                    "template subtracted the income-statement D&A row; without one, EBITDA equalled EBIT"))

    # ---------------------------------------------------------------- periods to build
    fys = sorted(2000 + int(k[3:]) for k in per if k.startswith("FY"))
    last_fy = fys[-1]; first_fy = last_fy - a.years + 1
    partial = sorted(int(k[1]) for k in per if not k.startswith("FY") and 2000 + int(k[3:]) == last_fy + 1)
    need = [f"Q{q} {y % 100:02d}" for y in range(first_fy, last_fy + 1) for q in (1, 2, 3)] + [f"FY {y % 100:02d}" for y in range(first_fy, last_fy + 1)]
    gaps = [k for k in need if k not in per]
    if gaps: raise SystemExit(f"Missing filings for {gaps} - run /collect-documents first.")
    layout = []          # (col, kind, fy, q)
    c = 4
    for y in range(first_fy, last_fy + 1):
        for q in range(1, 5): layout.append((c, f"Q{q}", y, q)); c += 1
        layout.append((c, "FY", y, 5)); c += 1; layout.append((c, "SP", y, 6)); c += 1
    est_y = last_fy + 1
    for q in range(1, 5):
        layout.append((c, f"Q{q}" if q in partial else f"QE{q}", est_y, q)); c += 1
    layout.append((c, "FYE", est_y, 5)); c += 1; layout.append((c, "AESP", est_y, 6)); c += 1
    for k in range(1, n_annual + 1):
        layout.append((c, "AE", est_y + k, 5)); c += 1
        if k < n_annual: layout.append((c, "AESP", est_y + k, 6)); c += 1
    colof = {(y, q): cc for cc, kind, y, q in layout}

    # ---------------------------------------------------------------- clear template data columns
    for r in range(1, maxr + 1):
        for cc in range(4, max(ws.max_column, c) + 1):
            ws.cell(r, cc).value = None
    for k in list(ws.column_dimensions.keys()):
        if CI(k) >= 4: del ws.column_dimensions[k]

    splits = dec.get("share_splits", [])
    for s in splits: log.append(("Stock split", f"share counts through {s['through_period']} x{s['factor']}", s.get("note", "")))

    def split_factor(source_period):
        f = 1
        for s in splits:
            if order(source_period) <= order(s["through_period"]): f *= s["factor"]
        return f

    def comps(key, st, role):
        return [v for _, v, _ in per[key][st].get(role, [])]

    def translate(kind, r, cc):
        v = tform[kind][r]
        if not (isinstance(v, str) and v.startswith("=")): return None
        try:
            f = Translator(v, origin=f"{L(tcols[kind])}{r}").translate_formula(f"{L(cc)}{r}")
        except Exception:
            return None
        return f

    for cc, kind, y, q in layout:
        yy = f"{y % 100:02d}"
        reported = kind in ("Q1", "Q2", "Q3", "Q4", "FY")
        is_est = kind in ("QE1", "QE2", "QE3", "QE4", "FYE", "AE")
        # header
        if kind in ("SP", "AESP"): label = None
        elif kind == "FY": label = y
        elif kind in ("FYE", "AE"): label = f"{y}E"
        else: label = f"Q{q} {yy}" + ("E" if kind.startswith("QE") else "")
        for r in range(1, maxr + 1):
            ws.cell(r, cc)._style = copy(style[kind][r])
            if kind in ("FY", "FYE", "AE") and r > HDR and not ws.cell(r, cc).fill.fill_type:
                ws.cell(r, cc).fill = FY_FILL
        ws.cell(HDR, cc).value = label
        hid, lvl = dims[kind]
        ws.column_dimensions[L(cc)] = ColumnDimension(ws, index=L(cc), width=SPACER_WIDTH if kind in ("SP", "AESP") else DATA_WIDTH,
                                                      hidden=hid, outlineLevel=lvl)
        if not reported: continue
        key = f"FY {yy}" if q == 5 else f"Q{q} {yy}"
        col = lambda qq: L(colof[(y, qq)])
        vals = {}
        # income statement
        for role in IS_IN:
            if role not in row: continue
            if q == 4: vals[role] = f"={col(5)}{row[role]}-{col(3)}{row[role]}-{col(2)}{row[role]}-{col(1)}{row[role]}"
            else:
                cs = comps(key, "IS", role)
                vals[role] = typed(cs) if cs else 0
        # shares
        for role in ("SB", "SD"):
            if q == 4:
                d = q4.get(f"Q4 {yy}", {})
                if d.get("missing"):
                    vals[role] = None; log.append(("MISSING", f"Q4 {yy} share counts", "no Q4 press release with share counts - typed value needed")); continue
                val, src = d[role], d["source_period"]
            else:
                val, src = per[key]["IS_chk"][role], key
            f = split_factor(src)
            vals[role] = f"={fmt(val)}*{f}" if f != 1 else val
        # balance sheet
        for role in BS_IN:
            if role not in row: continue
            vals[role] = f"={col(5)}{row[role]}" if q == 4 else typed(comps(key, "BS", role))
        # cash flow (filings report year-to-date; quarters are differences)
        for role in CF_IN:
            if role not in row: continue
            if q == 4:
                vals[role] = f"={col(5)}{row[role]}-SUM({col(1)}{row[role]}:{col(3)}{row[role]})"; continue
            cs = [per[key]["CF_chk"].get("FX") or 0] if role == "FX" else comps(key, "CF", role)
            if q in (1, 5): vals[role] = typed(cs)
            else:
                e = expr(cs)
                e = e if re.fullmatch(r"-?[\d.]+", e) else f"({e})"
                vals[role] = f"={e}-" + "-".join(f"{col(k)}{row[role]}" for k in range(q - 1, 0, -1))
        if "RC" in row:
            vals["RC"] = f"={col(5)}{row['RC']}" if q == 4 else typed([per[key]["CF_chk"].get("RC") or 0])
        # beginning cash: first period typed, then links to the prior period's ending cash
        if y == first_fy and q in (1, 5):
            vals["BEG"] = per[f"Q1 {yy}"]["CF_chk"]["BEG"]
        elif q == 1: vals["BEG"] = f"={L(colof[(y - 1, 4)])}{row['END']}"
        elif q == 5: vals["BEG"] = f"={L(colof[(y - 1, 5)])}{row['END']}"
        else: vals["BEG"] = f"={col(q - 1)}{row['END']}"
        inputs = {row[k]: v for k, v in vals.items() if k in row}
        blue_rows = {row[k] for k in INPUT_ROLES if k in row}
        tk = "Q4" if q == 4 else ("FY" if q == 5 else f"Q{q}")
        for r in range(HDR + 1, maxr + 1):
            if r in inputs: v = inputs[r]
            else:
                v = translate(tk, r, cc)
                if v is None and isinstance(tform[tk][r], str) and not tform[tk][r].startswith("=") and r > HDR: v = None
            cell = ws.cell(r, cc); cell.value = v
            colr = color_for(v, r in blue_rows)
            if colr: cell.font = Font(**{**{k: getattr(cell.font, k) for k in ("name", "sz", "b", "i", "u")}, "color": colr})
    ws["A1"] = f"{a.ticker} - Model"
    wb.calculation.fullCalcOnLoad = True
    wb.save(a.out)
    import modfill; modfill.fix(a.out, a.out)   # the user's MOD fill convention (quarters plain, years grey), every save
    import notebox; notebox.fix(a.out, a.out)   # note boxes open readable (none squashed next to spacer / hidden columns), every save

    # ---------------------------------------------------------------- judgment-call log
    calls = {}
    for key, p in per.items():
        if not (first_fy <= 2000 + int(key[3:]) <= last_fy + 1): continue
        for st in ("IS", "BS", "CF"):
            for role, items in p[st].items():
                for lab, v, tag in items:
                    if tag in ("fold", "fallback", "override"):
                        calls.setdefault((st, lab, role, tag), []).append(key)
    for k, d in q4.items():
        if d.get("fallback") and first_fy <= 2000 + int(k[3:]):
            log.append(("Q4 share source", k, f"no Q4 release with share counts for {k}; used {d['source']}"))
    with open(os.path.join(a.work, "JUDGMENT_CALLS.md"), "w") as f:
        f.write(f"# {a.ticker} model - judgment calls\n\nModel: {os.path.basename(a.out)} | FY{first_fy}-FY{last_fy} + {len(partial)} reported quarter(s) of {est_y}\n\n")
        f.write("## Decisions\n\n")
        for n in dec.get("notes", []): f.write(f"- {n}\n")
        for t, what, why in log: f.write(f"- **{t}:** {what} - {why}\n")
        f.write("\n## Filing lines mapped to a broader model row\n\n| Stmt | Filing line | Model row | Type | Periods |\n|---|---|---|---|---|\n")
        for (st, lab, role, tag), ks in sorted(calls.items()):
            ks = sorted(ks, key=order)
            f.write(f"| {st} | {lab} | {role} | {tag} | {ks[0]} - {ks[-1]} ({len(ks)}) |\n")
    print(f"built {a.out}: FY{first_fy}-FY{last_fy}, partial {est_y} quarters {partial}, {n_annual} annual estimate cols, {len(calls)} mapped-line calls, {len(log)} decisions logged")


def map_roles(st):
    return {"IS": IS_IN, "BS": BS_IN, "CF": CF_IN}[st]


if __name__ == "__main__":
    main()
