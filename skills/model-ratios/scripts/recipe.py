"""MOD's rows after /model-ratios, in order (the house layout, 2026-11-06): every existing MOD row ("keep") with
its analysis rows inserted underneath, the ROIC, ROE, ROA and LEVERAGE & CASH CONVERSION sections between the
balance sheet and the cash flow statement, and FREE CASH FLOW after the cash flow statement.
KPI rows carry calc(ctx, col) -> formula text, or None when the inputs don't exist yet (cell left blank)."""
from dataclasses import dataclass

from openpyxl.utils import get_column_letter as L

from roles import addon_rows

G = ["yoy", "2yr", "qoq"]
# Which analysis rows go under which line (the DXCM example model + the Part-2 additions in the spec)
ANALYSIS = {
    "REV": G, "COGS": G,
    "GP": ["margin", "bps", "yoy", "incr", "2yr", "qoq"],
    "OPEX": G + ["pct_sales", "bps"],
    "TOPEX": ["pct_sales", "bps", "yoy"],
    "OI": ["margin", "bps", "yoy", "incr"], "EBIT": ["margin", "bps", "yoy", "incr"],
    "NI": G + ["margin", "bps", "incr"],
    "EPSD": G, "TCA": G, "TNCA": G, "TA": G, "WCNET": G, "CFO": G, "END": G,
}
LABELS = {"yoy": "% yoy", "2yr": "% 2 year", "qoq": "% qoq", "margin": "% margin", "pct_sales": "% of sales",
          "bps": "bps yoy", "incr": "incremental margin"}


@dataclass
class Row:
    kind: str                 # keep (an existing MOD row) | metric | blank | section | label | kpi | adj | days
    key: str = None           # name other rows refer to: a MOD role, MOD<row>, or a KPI key
    label: str = None
    mod_row: int = None       # keep rows: the row's number before the inserts
    metric: str = None        # metric rows: yoy | 2yr | qoq | margin | pct_sales | bps | incr
    base: str = None          # metric rows: key of the line analysed
    pct: str = None           # bps rows: key of the % row it differences
    fmt: str = "usd"          # usd | pct | pct1 | bps | x | days | int
    bold: bool = False
    units: str = None
    calc: object = None       # kpi rows
    adj: int = None           # adj rows: index into the FCF adjustments


class Ctx:
    """What a KPI calc needs: output rows by key, the period map, and a place to leave cell comments."""
    def __init__(self, rows, periods):
        self.rows, self.p, self.notes = rows, periods, []

    def row(self, key):
        return self.rows[key]

    def a(self, key, c):
        return f"{L(c)}{self.rows[key]}"

    def note(self, key, c, text):
        self.notes.append((key, c, text))


# the DXCM example row styles (the TotalRowCycle macro): subtotal = thin line above, total = also a double line below.
SUBTOTAL = {"NOPAT", "IC_A", "ROIC_A", "CCC"}
TOTAL = {"FCF"}
SUB_ROWS = {"NOPAT_TTM", "FCF_TTM", "KM_NI_TTM", "EBITDA_TTM", "FCF_CONV"}   # italic + indented, like analysis rows
INDENTED = set()
SECTIONS = ("ROIC, ROE, ROA", "LEVERAGE & CASH CONVERSION", "FREE CASH FLOW")
CASH_ROLES = ("CASH", "STSEC")
# the DXCM example invested capital (2026-11-06): operating assets - non-interest-bearing current liabilities.
# Which lines are "operating" is a per-company call (analyze_decisions.json "invested_capital").
IC_DEFAULT = {"operating_assets": ["CASH", "STSEC", "AR", "INV", "PRE", "OCA", "PPE", "ROU", "GWI"],
              "nibcl": ["AP", "PAY", "ACCR", "TAXPAY", "OPLLC", "CLOTH", "OCL"]}     # rows a model lacks are skipped


def K(key, label, calc, fmt="usd", bold=False, units="$ M"):
    return Row("kpi", key=key, label=label, calc=calc, fmt=fmt, bold=bold, units=units)


def metric_rows(base, recipe):
    rows, pct = [], None
    for m in recipe:
        if m in ("margin", "pct_sales"):
            pct = f"{base}:{m}"
        rows.append(Row("metric", key=f"{base}:{m}", label=LABELS[m], metric=m, base=base,
                        pct=pct if m == "bps" else None, fmt="bps" if m == "bps" else "pct"))
    return rows


# ---------------------------------------------------------------- KPI calc helpers
def _link(key):
    return lambda x, c: f"={x.a(key, c)}"


def _ttm(key):
    def f(x, c):
        cols = x.p.ttm(c)
        return None if cols is None else "=" + "+".join(x.a(key, k) for k in cols)
    return f


def _avg(key, basis):
    """basis 'ttm': average with the year-ago balance (matches a TTM flow); 'period': with the prior period-end."""
    def f(x, c):
        k = x.p.yoy(c) if basis == "ttm" else x.p.prev_end(c)
        return None if k is None else f"=({x.a(key, c)}+{x.a(key, k)})/2"
    return f


def _tax_rate(x, c):
    fy = x.p.fy_col(c)
    if fy is not None and x.p.is_est(fy) and not x.p.is_est(c):      # reported quarter of an unfinished year
        fy = x.p.latest_reported_fy()
        if fy is not None:
            x.note("ROIC_TAX", c, f"No reported full year yet for this quarter's year, so NOPAT uses the latest "
                                  f"reported full-year tax rate ({x.p.label(fy)}).")
    if fy is None:
        return None
    return f"=${L(fy)}${x.row('TAXRATE')}"


def _needs(*checks):
    """Wrap a calc so it returns None unless every check(x, c) passes (e.g. TTM history exists)."""
    def deco(fn):
        return lambda x, c: fn(x, c) if all(ch(x, c) for ch in checks) else None
    return deco


HAS_TTM = lambda x, c: x.p.ttm(c) is not None
HAS_YOY = lambda x, c: x.p.yoy(c) is not None
HAS_PREV = lambda x, c: x.p.prev_end(c) is not None


def _int_cov(x, c):
    cols = x.p.ttm(c)
    if cols is None:
        return None
    op = "+".join(x.a("OI", k) for k in cols)
    ie = "+".join(x.a("INTEXP", k) for k in cols)
    return f'=IFERROR(({op})/-({ie}),"n.a.")'


def _days_metric(bal, flow, sign):
    @_needs(HAS_PREV)
    def f(x, c):
        k = x.p.prev_end(c)
        return f"=(({x.a(bal, c)}+{x.a(bal, k)})/2)/{sign}{x.a(flow, c)}*{x.a('DAYS', c)}"
    return f


def _ic(assets, nibcl):
    return lambda x, c: "=(" + "+".join(x.a(k, c) for k in assets) + ")-(" + "+".join(x.a(k, c) for k in nibcl) + ")"


def roic_rows(ic):
    a = lambda x, c, k: x.a(k, c)
    assets, nibcl = ic["operating_assets"], ic["nibcl"]
    roic = lambda num, den: _needs(HAS_TTM, HAS_YOY)(lambda x, c: f"={a(x, c, num)}/{a(x, c, den)}")
    return [
        Row("section", label="ROIC, ROE, ROA"), Row("blank"),
        K("ROIC_OI", "Operating Income (EBIT excluding 'other income')", _link("OI"), bold=True),
        K("ROIC_TAX", "Full Year Tax Rate", _tax_rate, "pct1", units="%"),
        K("ROIC_TAXES", "(-) Taxes only on Op Profit", lambda x, c: f"=-{a(x, c, 'ROIC_OI')}*{a(x, c, 'ROIC_TAX')}"),
        K("NOPAT", "NOPAT", lambda x, c: f"={a(x, c, 'ROIC_TAXES')}+{a(x, c, 'ROIC_OI')}", bold=True),
        K("NOPAT_TTM", "TTM NOPAT", _ttm("NOPAT")),
        Row("blank"),
        K("IC_A", "Invested Capital (asset based)", _ic(assets, nibcl), bold=True),
        K("IC_M", "Invested Capital (minus cash)", _ic([k for k in assets if k not in CASH_ROLES], nibcl), bold=True),
        Row("blank"),
        K("ICAVG_A", "Invested Cap Avg (asset based)", _avg("IC_A", "ttm")),
        K("ICAVG_M", "Invested Cap Avg (minus cash)", _avg("IC_M", "ttm")),
        Row("blank"),
        K("ROIC_A", "ROIC asset (Invested Cap Avg) TTM", roic("NOPAT_TTM", "ICAVG_A"), "pct1", True, "%"),
        K("ROIC_M", "ROIC minus cash (Invested Cap Avg) TTM", roic("NOPAT_TTM", "ICAVG_M"), "pct1", True, "%"),
        Row("blank"),
        K("ROE", "Return on Equity (ROE, avg equity) TTM", _needs(HAS_TTM, HAS_YOY)(lambda x, c:
          f"={a(x, c, 'KM_NI_TTM')}/(({a(x, c, 'EQ')}+{x.a('EQ', x.p.yoy(c))})/2)"), "pct1", units="%"),
        K("ROA", "Return on Assets (ROA, avg assets) TTM", _needs(HAS_TTM, HAS_YOY)(lambda x, c:
          f"={a(x, c, 'KM_NI_TTM')}/(({a(x, c, 'TA')}+{x.a('TA', x.p.yoy(c))})/2)"), "pct1", units="%"),
    ]


def fcf_rows(adj_labels):
    keys = ["FCF_CFO", "FCF_CAPEX"] + [f"ADJ{i}" for i in range(len(adj_labels))]
    return [
        Row("section", label="FREE CASH FLOW"), Row("blank"),
        K("FCF_CFO", "(+/-) Net Cash Provided by Operating Activities", _link("CFO")),
        K("FCF_CAPEX", "(-) Capital Expenditure", _link("CAPEX")),
        *metric_rows("FCF_CAPEX", ["pct_sales"]),
        *[Row("adj", key=f"ADJ{i}", label=lab, adj=i, units="$ M") for i, lab in enumerate(adj_labels)],
        K("FCF", "(+/-) Free Cash Flow", lambda x, c: "=" + "+".join(x.a(k, c) for k in keys), bold=True),
        *metric_rows("FCF", ["margin", "bps", "incr", "yoy", "2yr", "qoq"]),
        K("FCF_TTM", "FCF TTM", _ttm("FCF")),
        K("FCF_CONV", "FCF Conversion % (FCF / net income)", lambda x, c: f"={x.a('FCF', c)}/{x.a('NI', c)}", "pct1", units="%"),
    ]


def lev_rows():
    a = lambda x, c, k: x.a(k, c)
    debt = lambda x, c: f"{a(x, c, 'LTDEBT')}+{a(x, c, 'CURDEBT')}"
    return [
        Row("section", label="LEVERAGE & CASH CONVERSION"), Row("blank"),
        K("KM_NI", "Net Income", _link("NI"), bold=True),
        K("KM_NI_TTM", "TTM", _ttm("KM_NI")),
        K("KM_FCF", "Free Cash Flow", _link("FCF"), bold=True),
        K("KM_OP", "Operating Profit (EBIT excluding 'other income')", _link("OI"), bold=True),
        K("EBITDA", "EBITDA", lambda x, c: f"={a(x, c, 'KM_OP')}+{a(x, c, 'DA')}", bold=True),
        K("EBITDA_TTM", "EBITDA TTM", _ttm("EBITDA")),
        Row("blank"),
        K("NETLEV", "Net Leverage / (Cash) Ratio", _needs(HAS_TTM)(lambda x, c:
          f"=({debt(x, c)}-{a(x, c, 'CASH')}" + (f"-{a(x, c, 'STSEC')}" if "STSEC" in x.rows else "")   # no securities row: debt less cash
          + f")/{a(x, c, 'EBITDA_TTM')}"), "x", units="0.0x"),
        K("LEV", "Leverage Ratio", _needs(HAS_TTM)(lambda x, c: f"=({debt(x, c)})/{a(x, c, 'EBITDA_TTM')}"), "x", units="0.0x"),
        K("INTCOV", "Interest Coverage Ratio", _int_cov, "x", units="0.0x"),
        Row("blank"),
        Row("days", key="DAYS", label="Days in Fiscal Period", fmt="int", units="days"),
        K("DSO", "Days Sales Outstanding (DSO, avg)", _days_metric("AR", "REV", ""), "days", units="days"),
        K("DIO", "Days Inventory Outstanding (DIO, avg)", _days_metric("INV", "COGS", "-"), "days", units="days"),
        K("DPO", "Days Payable Outstanding (DPO, avg)", _days_metric("AP", "COGS", "-"), "days", units="days"),
        K("CCC", "Cash Conversion Cycle (CCC)", _needs(HAS_PREV)(lambda x, c:
          f"={a(x, c, 'DSO')}+{a(x, c, 'DIO')}-{a(x, c, 'DPO')}"), "days", True, "days"),
    ]


def build_layout(mod, roles, starts, opex, adj_labels=(), ic=None):
    """every MOD row once, in order (kind keep), with analysis rows and the three sections inserted"""
    by_row = {r: k for k, r in roles.items()}
    skip = addon_rows(mod)                       # non-GAAP / KPI sections carry their own analysis rows
    out = []
    for r in range(1, mod.max_row + 1):
        if r == starts["CF"]:
            ic = {k: [x for x in v if x in roles] for k, v in (ic or IC_DEFAULT).items() if k != "note"}
            out += roic_rows(ic) + [Row("blank")] + lev_rows() + [Row("blank")]
        out.append(Row("keep", key=by_row.get(r, f"MOD{r}"), mod_row=r))
        has_data = any(mod.cell(r, c).value not in (None, "") for c in range(4, mod.max_column + 1))
        if r <= 2 or r in skip or not has_data: continue
        recipe = ANALYSIS["OPEX"] if r in opex else ANALYSIS.get(by_row.get(r), [])
        out += metric_rows(by_row.get(r, f"MOD{r}"), recipe)
    out += [Row("blank")] + fcf_rows(list(adj_labels))
    return out
