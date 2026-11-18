"""Filings research -> the user's model: the charts and tables they keep using, written into their workbook.

usage: python3 handoff.py --src <ticker folder> --model <TICKER_model.xlsx> --context      (for the agent, first)
       python3 handoff.py --src <ticker folder> --model <TICKER_model.xlsx> --out <OUT.xlsx> [--idio-only]
--idio-only: only the Idio Chart and Px Events parts below (for /model-price-history's refresh); Filings Charts is
left as it is.
Reads _work/drivers_math.json (config), _work/model_series.csv (the MOD cell of each metric; rerun modeldata.py
first if MOD rows moved), the readers' guidance.csv files and _work/model_handoff.json (the handoff agent's
takeaways, eras, annotations, tables; references/handoff_prompt.md). Writes OUT:
  - 'Filings Charts' tab, replaced whole on a rerun: fixed vs variable costs, profit bridge, price vs volume (when a
    unit metric is configured), guidance vs actual per guided metric, and the agent's company-specific blocks.
    Every number links to MOD (green) or is a formula on those links (black); guides typed from the documents are
    blue with their sources in a note.
  - 'Idio Chart': annotations on the alpha chart (shapes named 'P1 ...', redrawn on a rerun); empty 'Your
    annotation' cells filled; below the charts, yearly returns vs SPY and the sector ETF with the eras beside them,
    then the stock section's tables and takeaways (rows below the charts are cleared and rewritten on a rerun).
  - 'Px Events': empty 'What happened / why' cells filled.
The user's own cells and shapes are never changed. Prints a JSON summary (cells skipped because the user filled them)."""
import argparse
import csv
import datetime as dt
import glob
import json
import os
import re

import openpyxl

import xlcharts
from modeldata import is_total_return
from xledit import add_cf, add_merges, arrow, drawing_part, put_anchors, set_cells, textbox
from xlsx import CT, Package, Sheet, Styles, colname, colnum, comments_parts, esc, vml_blocks

TAB = "Filings Charts"
BLUE, BLACK, GREEN, WHITE, GREY, NAVY = "FF0000FF", "FF000000", "FF008000", "FFFFFFFF", "FF808080", "FF002060"
MNY, PCT, PTS, DLR = '#,##0.0_);\\(#,##0.0\\);"–"', "0.0%", '0.0_);\\(0.0\\)', '"$"#,##0'
EMU_IN, ROW_EMU = 914400, 203200            # 16 pt default rows
COLORS = ["3F78D1", "E07040", "1BAF7A", "6250D6", "EDA100", "7F7F7F"]
UP, DOWN, TOTAL = "1BAF7A", "D9534F", "1F3864"
SECTOR_HDR = r"(\w+) close \((?:stooq adj\.|dividends in)\)$"   # Px Data factor header, old and Yahoo-era wording


# ---------------------------------------------------------------- inputs
def _work(src):
    return os.path.join(src, "Filings Research", "_work")


def load_mod(work):
    """{(metric, year): (col letter, row, value)} from model_series.csv's 'Model, MOD!BP104' sources."""
    out = {}
    with open(os.path.join(work, "model_series.csv"), newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            m = re.match(r"FY(\d{4})$", r["period"])
            c = re.search(r"MOD!([A-Z]+)(\d+)", r["source"])
            if m and c:
                out[(r["metric"], int(m.group(1)))] = (c.group(1), int(c.group(2)), float(r["value"]))
    return out


def check_rows(model, M, metrics):
    """model_series.csv must point at today's MOD rows (it goes stale when rows are inserted)."""
    wb = openpyxl.load_workbook(model, read_only=True)
    ws = wb["MOD"]
    labels = {i: str(r[1].value or "").strip() for i, r in enumerate(ws.iter_rows(min_col=1, max_col=2), start=1)}
    for k in metrics:
        hit = next(((c, r) for (m, y), (c, r, _) in M.items() if m == k), None)
        if hit and labels.get(hit[1], "").rstrip(": ") != k.split(" | ")[-1].strip().rstrip(": "):
            raise SystemExit(f"model_series.csv is stale: '{k}' is not on MOD row {hit[1]}. Rerun modeldata.py first.")


def guide_paths(work, spec, last_year):
    """{fiscal_year: [(date, low, high, source), ...]} for one guided metric: dated guides only, in date order,
    consecutive repeats dropped, nothing dated after the year ended (those are actuals)."""
    names = {n.lower(): spec.get("scale", {}).get(n, 1) for n in spec["names"]}
    rows = []
    for p in sorted(glob.glob(os.path.join(work, "readers", "*", "guidance.csv"))):
        with open(p, newline="", encoding="utf-8") as f:
            rows += list(csv.DictReader(f))
    out = {}
    for g in rows:
        name = g["metric"].strip().lower()
        if name not in names or g["basis"].strip() not in spec["basis"] or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", g["date"].strip()):
            continue
        y4 = re.search(r"\d{4}", g["fiscal_year"] or "")      # readers write 2018 or FY2018
        if not y4:
            continue
        fy = int(y4.group(0))
        if g["date"] > f"{fy}-12-31" or fy > last_year + 1:
            continue
        lo, hi = _num(g["low"]), _num(g["high"])
        if lo is None and hi is None:
            continue
        lo, hi = (lo if lo is not None else hi), (hi if hi is not None else lo)
        k = names[name]
        out.setdefault(fy, []).append((g["date"], lo * k, hi * k, g["source"], g["kind"]))
    paths = {}
    for fy, gs in out.items():
        gs.sort(key=lambda x: (x[0], x[4] != "hard"))
        path = []
        for d, lo, hi, s, _ in gs:
            if path and path[-1][0] == d:
                continue
            if path and (round(path[-1][1], 6), round(path[-1][2], 6)) == (round(lo, 6), round(hi, 6)):
                continue
            path.append((d, lo, hi, s))
        paths[fy] = path
    return paths


def _num(s):
    try:
        return float(str(s).replace(",", ""))
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------- the Filings Charts tab
class Tab:
    """Rows written top to bottom; charts placed under their table, two side by side."""

    def __init__(self, st, first_col=3, ncols=12):
        self.sh, self.st, self.r, self.charts = Sheet(), st, 2, []
        self.c0, self.n = first_col, ncols
        self.sh.widths = {1: 2, 2: 42, **{c: 12.5 for c in range(first_col, first_col + ncols + 2)}}
        S = st.xf
        self.s = {"title": S(NAVY, sz=16, b=True), "h": S(WHITE, b=True, fill=NAVY, align="center"),
                  "hl": S(WHITE, b=True, fill=NAVY), "lab": S(BLACK), "sub": S(BLACK, b=True), "it": S(GREY, i=True, sz=10),
                  "text": S(BLACK, sz=11, align="left"), "key": S(BLACK, sz=11, b=True, align="left")}

    def style(self, color, fmt, b=False):
        return self.st.xf(color, fmt, b=b)

    def title(self, text):
        self.r += 1
        self.sh.set(f"B{self.r}", "s", text, self.s["title"])
        self.sh.heights[self.r] = 24
        self.r += 1

    def para(self, text, bold=False, chars=150):
        if not text:
            return
        last = colname(self.c0 + 10)                 # the widest table (11 years) ends here
        self.sh.set(f"B{self.r}", "s", text, self.s["key" if bold else "text"])
        self.sh.merges.append(f"B{self.r}:{last}{self.r}")
        lines = sum(max(1, -(-len(p) // chars)) for p in text.split("\n"))
        self.sh.heights[self.r] = max(16, 15 * lines + 4)
        self.r += 1

    def header(self, label, heads):
        self.sh.set(f"B{self.r}", "s", label, self.s["hl"])
        for k, h in enumerate(heads):
            self.sh.set(f"{colname(self.c0 + k)}{self.r}", "s" if isinstance(h, str) else "n", h, self.s["h"])
        self.r += 1
        return self.r - 1

    def row(self, label, cells, bold=False):
        """cells: [(kind, value, style) or None]; returns the row number."""
        self.sh.set(f"B{self.r}", "s", label, self.s["sub" if bold else "lab"])
        for k, c in enumerate(cells):
            if c is not None:
                self.sh.set(f"{colname(self.c0 + k)}{self.r}", *c)
        self.r += 1
        return self.r - 1

    def note(self, text):
        self.sh.set(f"B{self.r}", "s", text, self.s["it"])
        self.r += 1

    def charts_row(self, xmls, h_in=3.6):
        """One or two charts under the table; reserves rows (16 pt each) for their height."""
        w = 6.6 if len(xmls) > 1 else 9.0
        for k, x in enumerate(xmls):
            self.charts.append((x, self.r - 1, k * (w + 0.25), w, h_in))
        rows = int(h_in * 72 / 16) + 2
        for r in range(self.r, self.r + rows):
            self.sh.heights[r] = 16
        self.r += rows


def _ref(col, row):
    return f"MOD!{col}{row}"


def _rng(tab_row, c0, n):
    return f"'{TAB}'!${colname(c0)}${tab_row}:${colname(c0 + n - 1)}${tab_row}"


def block_fixed_variable(T, M, cfg, take):
    last, first = cfg["last_year"], cfg["first_year"] - 1
    years = list(range(first, last + 1))
    lines = [cfg["cogs"]] + list(cfg["opex"])
    if not all((cfg["revenue"], y) in M for y in years) or not all((k, y) in M for k in lines for y in years):
        return False
    T.title("Fixed vs variable costs")
    T.para(take)
    hr = T.header("$M (costs shown as positive)", years)
    lk, cl, pc = T.style(GREEN, MNY), T.style(BLACK, MNY), T.style(BLACK, PCT)
    rev = T.row("Revenue", [("f", _ref(*M[(cfg["revenue"], y)][:2]), lk) for y in years], bold=True)
    rows = {}
    for k in lines:
        rows[k] = T.row(_short(k), [("f", f"ABS({_ref(*M[(k, y)][:2])})", cl) for y in years])
    T.r += 1
    T.row("Cost as % of revenue", [], bold=True)
    pr = {k: T.row("   " + _short(k), [("f", f"{colname(T.c0 + i)}{rows[k]}/{colname(T.c0 + i)}{rev}", pc)
                                         for i in range(len(years))]) for k in lines}
    T.row("Incremental cost per $1 of new revenue", [], bold=True)
    for k in lines:
        T.row("   " + _short(k), [None] + [("f", f"IFERROR(({colname(T.c0 + i)}{rows[k]}-{colname(T.c0 + i - 1)}{rows[k]})/"
                                                    f"({colname(T.c0 + i)}{rev}-{colname(T.c0 + i - 1)}{rev}),\"n.a.\")", pc)
                                           for i in range(1, len(years))])
    T.r += 1
    n5 = 5
    a, b = colname(T.c0 + len(years) - 1 - n5), colname(T.c0 + len(years) - 1)
    sh = T.header(f"Last {n5} years ({years[-1 - n5]}–{years[-1]})", ["Avg % rev.", "Per new $", "Ratio", "Class"])
    cats, avg_v, inc_v = [], [], []
    for k in lines:
        avg = f"SUM({a}{rows[k]}:{b}{rows[k]})/SUM({a}{rev}:{b}{rev})"
        inc = f"({b}{rows[k]}-{a}{rows[k]})/({b}{rev}-{a}{rev})"
        c = colname
        rr = T.row(_short(k), [("f", avg, pc), ("f", inc, pc), ("f", f"{c(T.c0 + 1)}{T.r}/{c(T.c0)}{T.r}", T.style(BLACK, '0.0"x"')),
                               ("f", f'IF({c(T.c0 + 2)}{T.r}>=0.8,"variable",IF({c(T.c0 + 2)}{T.r}<=0.4,"fixed","semi-fixed"))',
                                T.style(BLACK, "General"))])
        ys = range(len(years) - 1 - n5, len(years))
        C = [abs(M[(k, years[i])][2]) for i in ys]
        R = [M[(cfg["revenue"], years[i])][2] for i in ys]
        cats.append(_short(k))
        avg_v.append(sum(C) / sum(R))
        inc_v.append((C[-1] - C[0]) / (R[-1] - R[0]))
    T.note("Ratio = incremental ÷ average. 0.8x or more = variable (grows with revenue); 0.4x or less = fixed; "
           "between = semi-fixed. Same rule as the filings research's driver math.")
    cat = (f"'{TAB}'!$B${sh + 1}:$B${sh + len(lines)}", cats)
    pct_series = [{"name": _short(k), "ref": _rng(pr[k], T.c0, len(years)), "color": COLORS[i],
                   "vals": [abs(M[(k, y)][2]) / M[(cfg["revenue"], y)][2] for y in years]} for i, k in enumerate(lines)]
    ch1 = xlcharts.chart("Costs as % of revenue", (_rng(hr, T.c0, len(years)), years),
                         [{"type": "line", "series": pct_series}], {"fmt": "0%"})
    ch2 = xlcharts.chart(f"Average vs incremental cost per $ of revenue ({years[-1 - n5]}–{years[-1]})", cat,
                         [{"type": "bar", "series": [
                             {"name": "Average % of revenue", "ref": f"'{TAB}'!${colname(T.c0)}${sh + 1}:${colname(T.c0)}${sh + len(lines)}",
                              "vals": avg_v, "color": "9DC3E6", "labels": "0%"},
                             {"name": "Incremental (per $1 of new revenue)", "ref": f"'{TAB}'!${colname(T.c0 + 1)}${sh + 1}:${colname(T.c0 + 1)}${sh + len(lines)}",
                              "vals": inc_v, "color": "3F78D1", "labels": "0%"}]}], {"fmt": "0%"})
    T.charts_row([ch1, ch2])
    return True


def block_profit_bridge(T, M, cfg, take):
    years = list(range(cfg["first_year"] - 1, cfg["last_year"] + 1))
    need = [cfg["revenue"], cfg["cogs"], cfg["operating_income"]] + list(cfg["opex"])
    if not all((k, y) in M for k in need for y in years):
        return False
    T.title("Profit bridge: what changed operating income each year")
    T.para(take)
    hr = T.header("$M", years)
    lk, cl, pc = T.style(GREEN, MNY), T.style(BLACK, MNY), T.style(BLACK, PCT)
    c = lambda i: colname(T.c0 + i)
    rev = T.row("Revenue", [("f", _ref(*M[(cfg["revenue"], y)][:2]), lk) for y in years])
    cogs = T.row("Cost of sales", [("f", f"ABS({_ref(*M[(cfg['cogs'], y)][:2])})", cl) for y in years])
    gm = T.row("Gross margin", [("f", f"({c(i)}{rev}-{c(i)}{cogs})/{c(i)}{rev}", pc) for i in range(len(years))])
    ox = {k: T.row(_short(k), [("f", f"ABS({_ref(*M[(k, y)][:2])})", cl) for y in years]) for k in cfg["opex"]}
    oi = T.row("Operating income", [("f", _ref(*M[(cfg["operating_income"], y)][:2]), lk) for y in years])
    T.r += 1
    T.row("Bridge: positive = helped operating income, negative = hurt it", [], bold=True)
    br = {}
    br["Revenue growth (at last year's gross margin)"] = T.row("Revenue growth (at last year's gross margin)",
        [None] + [("f", f"({c(i)}{rev}-{c(i - 1)}{rev})*{c(i - 1)}{gm}", cl) for i in range(1, len(years))])
    br["Gross margin rate"] = T.row("Gross margin rate", [None] + [("f", f"({c(i)}{gm}-{c(i - 1)}{gm})*{c(i)}{rev}", cl)
                                                                  for i in range(1, len(years))])
    for k in cfg["opex"]:
        br[_short(k)] = T.row(_short(k), [None] + [("f", f"-({c(i)}{ox[k]}-{c(i - 1)}{ox[k]})", cl) for i in range(1, len(years))])
    keys = list(br)
    br["Other"] = T.row("Other", [None] + [("f", f"({c(i)}{oi}-{c(i - 1)}{oi})-(" + "+".join(f"{c(i)}{br[k]}" for k in keys) + ")", cl)
                                           for i in range(1, len(years))])
    chg = T.row("Change in operating income", [None] + [("f", f"{c(i)}{oi}-{c(i - 1)}{oi}", T.style(BLACK, MNY, b=True))
                                                        for i in range(1, len(years))], bold=True)
    # values for the chart caches (same math as drivers.profit_bridge)
    V = {k: [] for k in br}
    V["change"] = []
    for y in years[1:]:
        R, R0 = M[(cfg["revenue"], y)][2], M[(cfg["revenue"], y - 1)][2]
        C, C0 = abs(M[(cfg["cogs"], y)][2]), abs(M[(cfg["cogs"], y - 1)][2])
        g, g0 = (R - C) / R, (R0 - C0) / R0
        parts = {"Revenue growth (at last year's gross margin)": (R - R0) * g0, "Gross margin rate": (g - g0) * R}
        for k in cfg["opex"]:
            parts[_short(k)] = -(abs(M[(k, y)][2]) - abs(M[(k, y - 1)][2]))
        d = M[(cfg["operating_income"], y)][2] - M[(cfg["operating_income"], y - 1)][2]
        parts["Other"] = d - sum(parts.values())
        for k in br:
            V[k].append(parts[k])
        V["change"].append(d)
    ys = years[1:]
    cat = (f"'{TAB}'!${c(1)}${hr}:${c(len(years) - 1)}${hr}", ys)
    ser = [{"name": k.split(" (")[0], "ref": f"'{TAB}'!${c(1)}${br[k]}:${c(len(years) - 1)}${br[k]}", "vals": V[k],
            "color": COLORS[i % len(COLORS)]} for i, k in enumerate(br)]
    ch1 = xlcharts.chart("Profit bridge by year ($M)", cat,
                         [{"type": "bar", "grouping": "stacked", "series": ser},
                          {"type": "line", "series": [{"name": "Change in operating income", "ref": f"'{TAB}'!${c(1)}${chg}:${c(len(years) - 1)}${chg}",
                                                       "vals": V["change"], "color": "000000", "noline": True, "symbol": "dash", "size": 12}]}],
                         {"fmt": "#,##0"})
    # waterfall for the last year: invisible base + up + down + totals, on helper rows
    T.r += 1
    y = years[-1]
    steps = [(f"{y - 1} operating income", M[(cfg["operating_income"], y - 1)][2], "total")]
    steps += [(k.split(" (")[0], V[k][-1], "step") for k in br]
    steps += [(f"{y} operating income", M[(cfg["operating_income"], y)][2], "total")]
    wh = T.header(f"Waterfall helper ({y})", ["Value", "Base", "Up", "Down", "Total"])
    run, base_v, up_v, dn_v, tot_v = 0.0, [], [], [], []
    src = {k: f"{c(len(years) - 1)}{br[k]}" for k in br}
    for k, (lab, v, kind) in enumerate(steps):
        r = T.r
        if kind == "total":
            val = f"{c(len(years) - 2 if k == 0 else len(years) - 1)}{oi}"
            cells = [("f", val, cl), ("n", 0, cl), ("n", 0, cl), ("n", 0, cl), ("f", f"{c(0)}{r}", cl)]
            base_v.append(0), up_v.append(0), dn_v.append(0), tot_v.append(v)
            run = v
        else:
            key = [kk for kk in br if kk.split(" (")[0] == lab][0]
            prev = f"(SUM({c(0)}${wh + 1}:{c(0)}{r - 1})-0)"
            cells = [("f", src[key], cl), ("f", f"MIN({prev},{prev}+{c(0)}{r})", cl), ("f", f"MAX({c(0)}{r},0)", cl),
                     ("f", f"MAX(-{c(0)}{r},0)", cl), ("n", 0, cl)]
            base_v.append(min(run, run + v)), up_v.append(max(v, 0)), dn_v.append(max(-v, 0)), tot_v.append(0)
            run += v
        T.row(lab, cells)
    n = len(steps)
    wcat = (f"'{TAB}'!$B${wh + 1}:$B${wh + n}", [s[0] for s in steps])
    col = lambda j: f"'{TAB}'!${c(j)}${wh + 1}:${c(j)}${wh + n}"
    ch2 = xlcharts.chart(f"Operating income bridge {y - 1} to {y} ($M)", wcat,
                         [{"type": "bar", "grouping": "stacked", "series": [
                             {"name": "base", "ref": col(1), "vals": base_v, "color": None},
                             {"name": "Helped", "ref": col(2), "vals": up_v, "color": UP},
                             {"name": "Hurt", "ref": col(3), "vals": dn_v, "color": DOWN},
                             {"name": "Operating income", "ref": col(4), "vals": tot_v, "color": TOTAL}]}], {"fmt": "#,##0"})
    T.note("Waterfall helper: the first step's base sums the rows above it, so the steps chain from last year's operating income.")
    T.charts_row([ch1, ch2])
    return True


def block_price_volume(T, M, cfg, take):
    u = (cfg.get("units") or [None])[0]
    if not u:
        return False
    years = [y for y in range(cfg["first_year"] - 1, cfg["last_year"] + 1) if (u["units"], y) in M and (u["revenue"], y) in M]
    if len(years) < 4:
        return False
    T.title(f"Price vs volume: {u['name'].lower()}")
    T.para(take)
    hr = T.header("", years)
    lk, cl, pc = T.style(GREEN, MNY), T.style(BLACK, MNY), T.style(BLACK, PCT)
    c = lambda i: colname(T.c0 + i)
    rev = T.row("Revenue ($M)", [("f", _ref(*M[(u["revenue"], y)][:2]), lk) for y in years])
    un = T.row(f"{_short(u['units'])} (year end)", [("f", _ref(*M[(u["units"], y)][:2]), T.style(GREEN, "#,##0.00")) for y in years])
    av = T.row("Average units (start + end) ÷ 2", [None] + [("f", f"({c(i)}{un}+{c(i - 1)}{un})/2", T.style(BLACK, "#,##0.00"))
                                                         for i in range(1, len(years))])
    rpu = T.row("Revenue per average unit", [None] + [("f", f"{c(i)}{rev}/{c(i)}{av}", T.style(BLACK, "#,##0"))
                                                       for i in range(1, len(years))], bold=True)
    gr = T.row("Revenue growth", [None] + [("f", f"{c(i)}{rev}/{c(i - 1)}{rev}-1", pc) for i in range(1, len(years))])
    ug = T.row("Unit growth (average units)", [None, None] + [("f", f"{c(i)}{av}/{c(i - 1)}{av}-1", pc) for i in range(2, len(years))])
    pg = T.row("Price growth (revenue per average unit)", [None, None] + [("f", f"{c(i)}{rpu}/{c(i - 1)}{rpu}-1", pc)
                                                                         for i in range(2, len(years))])
    R = [M[(u["revenue"], y)][2] for y in years]
    U = [M[(u["units"], y)][2] for y in years]
    A = [None] + [(U[i] + U[i - 1]) / 2 for i in range(1, len(years))]
    P = [None] + [R[i] / A[i] for i in range(1, len(years))]
    i0 = 2
    ys = years[i0:]
    cat = (f"'{TAB}'!${c(i0)}${hr}:${c(len(years) - 1)}${hr}", ys)
    rng = lambda r: f"'{TAB}'!${c(i0)}${r}:${c(len(years) - 1)}${r}"
    ch = xlcharts.chart("Units grew faster than revenue: price per unit fell", cat,
                        [{"type": "bar", "series": [
                            {"name": "Revenue growth", "ref": rng(gr), "vals": [R[i] / R[i - 1] - 1 for i in range(i0, len(years))], "color": "3F78D1", "labels": "0%"},
                            {"name": "Unit growth", "ref": rng(ug), "vals": [A[i] / A[i - 1] - 1 for i in range(i0, len(years))], "color": "1BAF7A", "labels": "0%"},
                            {"name": "Price growth", "ref": rng(pg), "vals": [P[i] / P[i - 1] - 1 for i in range(i0, len(years))], "color": "D9534F", "labels": "0%"}]},
                         {"type": "line", "axis": 2, "series": [
                             {"name": "Revenue per average unit (right)", "ref": rng(rpu), "vals": P[i0:], "color": "000000", "marker": True}]}],
                        {"fmt": "0%"}, {"fmt": "#,##0", "title": "per unit"})
    T.charts_row([ch])
    return True


def block_guidance(T, M, work, spec, cfg, take, comments):
    paths = guide_paths(work, spec, cfg["last_year"])
    pct = spec.get("unit") == "%"
    act = spec.get("actual", {})
    years = sorted(y for y in paths if paths[y] and _actual(M, act, y) is not None)
    if len(years) < 3:
        return False
    T.title(f"Guidance vs actual: {spec['title']}")
    T.para(take)
    fmt = PTS if pct else MNY
    ty, cl, lk = T.style(BLUE, fmt), T.style(BLACK, fmt), T.style(GREEN, fmt)
    hr = T.header("Fiscal year", ["First guide", "Low", "High", "Last guide", "Low", "High", "Actual",
                                  "vs first mid", "Changes", "Path of the guide (date: range)"])
    c = lambda i: colname(T.c0 + i)
    vals = {"lo": [], "rng": [], "last": [], "act": [], "beat": []}
    for y in years:
        p = paths[y]
        (d0, l0, h0, s0), (d1, l1, h1, s1) = p[0], p[-1]
        r = T.r
        a = act_formula(M, act, y, pct)
        mid = f"AVERAGE({c(1)}{r},{c(2)}{r})"
        beat = (f"{c(6)}{r}-{mid}" if pct else f"{c(6)}{r}/{mid}-1")   # column 6 = Actual
        path = " → ".join(f"{_d(d)}: {_fmt(lo, hi, pct)}" for d, lo, hi, _ in p)
        T.row(str(y), [("s", d0, T.style(BLUE, "General")), ("n", l0, ty), ("n", h0, ty), ("s", d1, T.style(BLUE, "General")),
                       ("n", l1, ty), ("n", h1, ty), ("f", a, lk if act.get("metric") else cl),
                       ("f", beat, T.style(BLACK, '+0.0" pts";-0.0" pts"' if pct else "+0.0%;-0.0%")),
                       ("n", len(p) - 1, T.style(BLACK, "0")), ("s", path, T.style(BLACK, "General"))])
        comments[f"{c(1)}{r}"] = "First guide: " + s0 + ("\nLast guide: " + s1 if s1 != s0 else "")
        av = _actual(M, act, y) * (100 if pct else 1)
        vals["lo"].append(l0), vals["rng"].append(h0 - l0), vals["last"].append((l1 + h1) / 2), vals["act"].append(av)
        vals["beat"].append(av - (l0 + h0) / 2 if pct else av / ((l0 + h0) / 2) - 1)
    end = T.r - 1
    # helper columns for the chart: range = high - low, last mid
    T.r += 1
    hh = T.header("Chart helper", years)
    rng_r = T.row("First guide range (high − low)", [("f", f"INDEX(${c(2)}${hr + 1}:${c(2)}${end},{k + 1})-INDEX(${c(1)}${hr + 1}:${c(1)}${end},{k + 1})", cl)
                                                    for k in range(len(years))])
    lo_r = T.row("First guide low", [("f", f"INDEX(${c(1)}${hr + 1}:${c(1)}${end},{k + 1})", cl) for k in range(len(years))])
    mid_r = T.row("First guide midpoint", [("f", f"AVERAGE(INDEX(${c(1)}${hr + 1}:${c(1)}${end},{k + 1}),INDEX(${c(2)}${hr + 1}:${c(2)}${end},{k + 1}))", cl)
                                           for k in range(len(years))])
    last_r = T.row("Last guide midpoint", [("f", f"AVERAGE(INDEX(${c(4)}${hr + 1}:${c(4)}${end},{k + 1}),INDEX(${c(5)}${hr + 1}:${c(5)}${end},{k + 1}))", cl)
                                           for k in range(len(years))])
    act_r = T.row("Actual", [("f", f"INDEX(${c(6)}${hr + 1}:${c(6)}${end},{k + 1})", cl) for k in range(len(years))])
    beat_r = T.row("Actual vs first guide midpoint", [("f", f"INDEX(${c(7)}${hr + 1}:${c(7)}${end},{k + 1})", cl if pct else T.style(BLACK, PCT))
                                                      for k in range(len(years))])
    cat = (_rng(hh, T.c0, len(years)), years)
    lo_all = min(vals["lo"] + vals["act"] + vals["last"])
    hi_all = max([a + b for a, b in zip(vals["lo"], vals["rng"])] + vals["act"] + vals["last"])
    pad = (hi_all - lo_all) * 0.15 or 1
    ymin = max(0, (lo_all - pad) // (1 if pct else 100) * (1 if pct else 100))
    unit = " (%)" if pct else " ($M)"
    ch1 = xlcharts.chart(f"{spec['title']}: first guide range, last guide and actual", cat,
                         [{"type": "bar", "grouping": "stacked", "series": [
                             {"name": "base", "ref": _rng(lo_r, T.c0, len(years)), "vals": vals["lo"], "color": None},
                             {"name": "First guide range", "ref": _rng(rng_r, T.c0, len(years)), "vals": vals["rng"], "color": "9DC3E6"}]},
                          {"type": "line", "series": [
                              {"name": "First guide (midpoint)", "ref": _rng(mid_r, T.c0, len(years)),
                               "vals": [lo + rg / 2 for lo, rg in zip(vals["lo"], vals["rng"])], "color": "3F78D1",
                               "noline": True, "symbol": "dash", "size": 12},
                              {"name": "Last guide (midpoint)", "ref": _rng(last_r, T.c0, len(years)), "vals": vals["last"],
                               "color": "E07040", "noline": True, "symbol": "diamond", "size": 8},
                              {"name": "Actual", "ref": _rng(act_r, T.c0, len(years)), "vals": vals["act"], "color": "000000",
                               "noline": True, "size": 7}]}],
                         {"fmt": "0" if pct else "#,##0", "title": unit.strip(" ()"), "min": ymin})
    ch2 = xlcharts.chart(f"{spec['title']}: actual vs first guide midpoint", cat,
                         [{"type": "bar", "series": [{"name": "pts" if pct else "%", "ref": _rng(beat_r, T.c0, len(years)),
                                                      "vals": vals["beat"], "color": "3F78D1", "labels": "+0.0;-0.0" if pct else "+0%;-0%"}]}],
                         {"fmt": "0.0" if pct else "0%"})
    T.note("Blue = typed from the company's releases, decks and calls (sources in the note on each first guide). "
           "Guides dated after the year ended are actuals and left out.")
    T.charts_row([ch1, ch2])
    return True


def _actual(M, act, y):
    if act.get("metric"):
        return M.get((act["metric"], y), (None, None, None))[2]
    if act.get("ratio"):
        n, d = M.get((act["ratio"][0], y)), M.get((act["ratio"][1], y))
        return n[2] / d[2] if n and d and d[2] else None
    return None


def act_formula(M, act, y, pct):
    if act.get("metric"):
        return _ref(*M[(act["metric"], y)][:2])
    n, d = M[(act["ratio"][0], y)], M[(act["ratio"][1], y)]
    return f"{_ref(*n[:2])}/{_ref(*d[:2])}" + ("*100" if pct else "")


def block_custom(T, M, b):
    """Company-specific block: {"title", "takeaway", "years": [a, b], "rows": [{"label", "metric", "fmt"}],
    "chart": {"title", "rows": [i...], "type": "line"|"bar", "fmt", "right": [i...], "right_fmt"}}"""
    years = list(range(b["years"][0], b["years"][1] + 1))
    T.title(b["title"])
    T.para(b.get("takeaway"))
    hr = T.header("", years)
    rr = []
    for row in b["rows"]:
        fmt = {"pct": PCT, "usd": DLR, "mny": MNY}.get(row.get("fmt", "mny"), row.get("fmt"))
        cells = [("f", _ref(*M[(row["metric"], y)][:2]), T.style(GREEN, fmt)) if (row["metric"], y) in M else None for y in years]
        rr.append((T.row(row["label"], cells), [M.get((row["metric"], y), (0, 0, None))[2] for y in years]))
    if b.get("note"):
        T.note(b["note"])
    ch = b.get("chart")
    if ch:
        cat = (_rng(hr, T.c0, len(years)), years)
        left = [i for i in ch["rows"] if i not in ch.get("right", [])]
        groups = [{"type": ch.get("type", "line"), "series": [
            {"name": b["rows"][i]["label"], "ref": _rng(rr[i][0], T.c0, len(years)), "vals": rr[i][1],
             "color": COLORS[k], "marker": True, "labels": ch.get("labels")} for k, i in enumerate(left)]}]
        if ch.get("right"):
            groups.append({"type": "line", "axis": 2, "series": [
                {"name": b["rows"][i]["label"] + " (right)", "ref": _rng(rr[i][0], T.c0, len(years)), "vals": rr[i][1],
                 "color": COLORS[len(left) + k], "marker": True} for k, i in enumerate(ch["right"])]})
        T.charts_row([xlcharts.chart(ch["title"], cat, groups, {"fmt": ch.get("fmt", "#,##0")},
                                     {"fmt": ch.get("right_fmt", "0%")} if ch.get("right") else None)])
    return True


def _short(metric):
    return re.sub(r"^\(-\)\s*|^\(\+/?-?\)\s*", "", metric.split(" | ")[-1]).strip()


def _d(iso):
    d = dt.date.fromisoformat(iso)
    return d.strftime("%b %-d %y").replace(" 2", " '2", 1) if False else d.strftime("%b %-d '%y")


def _fmt(lo, hi, pct):
    f = (lambda v: f"{v:g}") if pct else (lambda v: f"{v:,.0f}")
    return f(lo) if abs(hi - lo) < 1e-9 else f"{f(lo)}–{f(hi)}"


# ---------------------------------------------------------------- writing the parts
def chart_anchor(x, rid, row, x_in, w_in, h_in, nid, name, widths=None):
    """oneCellAnchor x_in inches right of column B's left edge; fixed size."""
    colw = lambda c: int(((256 * (widths or {}).get(c + 1, 8.43) + 16) / 256) * 8) * 9525   # Excel, 8 px digits
    col, off = 1, int(x_in * EMU_IN)
    while off >= colw(col):
        off -= colw(col)
        col += 1
    return (f'<xdr:oneCellAnchor><xdr:from><xdr:col>{col}</xdr:col><xdr:colOff>{off}</xdr:colOff><xdr:row>{row}</xdr:row>'
            f'<xdr:rowOff>0</xdr:rowOff></xdr:from><xdr:ext cx="{int(w_in * EMU_IN)}" cy="{int(h_in * EMU_IN)}"/>'
            f'<xdr:graphicFrame macro=""><xdr:nvGraphicFramePr><xdr:cNvPr id="{nid}" name="{esc(name)}"/><xdr:cNvGraphicFramePr/>'
            '</xdr:nvGraphicFramePr><xdr:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/></xdr:xfrm><a:graphic>'
            '<a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/chart">'
            '<c:chart xmlns:c="http://schemas.openxmlformats.org/drawingml/2006/chart" '
            f'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" r:id="{rid}"/>'
            "</a:graphicData></a:graphic></xdr:graphicFrame><xdr:clientData/></xdr:oneCellAnchor>")


def write_tab(pkg, T, comments):
    if TAB in [s[0] for s in pkg.sheets()]:
        pkg.remove_sheet(TAB)
    part = pkg.add_sheet(TAB, "")
    _move_after(pkg, TAB, "Research")
    drid = lrid = None
    if T.charts:
        dn = pkg.free("xl/drawings/drawing{}.xml")
        dpart = f"xl/drawings/drawing{dn}.xml"
        anchors = []
        for k, (xml_, row, x_in, w, h) in enumerate(T.charts):
            cn = pkg.free("xl/charts/chart{}.xml")
            cpart = f"xl/charts/chart{cn}.xml"
            pkg.put(cpart, xml_)
            pkg.content_override(cpart, CT["chart"])
            anchors.append(chart_anchor(xml_, pkg.attach(dpart, "chart", cpart), row, x_in, w, h, k + 2, f"Chart {k + 1}", T.sh.widths))
        pkg.put(dpart, '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
                       '<xdr:wsDr xmlns:xdr="http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing" '
                       'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">' + "".join(anchors) + "</xdr:wsDr>")
        pkg.content_override(dpart, CT["drawing"])
        drid = pkg.attach(part, "drawing", dpart)
    if comments:
        pkg.content_default("vml", "application/vnd.openxmlformats-officedocument.vmlDrawing")
        ids = [int(x) for p, data in pkg.parts.items() if p.endswith(".vml")
               for d in re.findall(rb'<o:idmap v:ext="edit" data="([\d,\s]+)"', data) for x in re.findall(rb"\d+", d)]
        cn, vn = pkg.free("xl/comments{}.xml"), pkg.free("xl/drawings/vmlDrawing{}.vml")
        cx, vml = comments_parts(comments, max(ids + [0]) + 1)
        pkg.put(f"xl/comments{cn}.xml", cx)
        pkg.put(f"xl/drawings/vmlDrawing{vn}.vml", vml)
        lrid = pkg.attach(part, "vml", f"xl/drawings/vmlDrawing{vn}.vml")
        pkg.attach(part, "comments", f"xl/comments{cn}.xml", CT["comments"])
    T.sh.zoom = 90
    pkg.put(part, T.sh.xml(drid, lrid))


def _move_after(pkg, name, after):
    """Put tab `name` right after `after` (if that tab exists); keeps every other tab in order."""
    wb = pkg.text("xl/workbook.xml")
    tags = re.findall(r"<sheet\b[^>]*/>", wb)
    me = [t for t in tags if f'name="{esc(name)}"' in t][0]
    rest = [t for t in tags if t is not me]
    i = next((k for k, t in enumerate(rest) if f'name="{esc(after)}"' in t), len(rest) - 1)
    order = rest[:i + 1] + [me] + rest[i + 1:]
    body = re.search(r"<sheets>(.*?)</sheets>", wb, re.S)
    pkg.put("xl/workbook.xml", wb[:body.start(1)] + "".join(order) + wb[body.end(1):])
    # sheet-scoped names refer to tabs by position: none in the user's models (checked in tests)


# ---------------------------------------------------------------- Idio Chart and Px Events
def _sheet_part(pkg, name):
    return {s[0]: s[3] for s in pkg.sheets()}.get(name)


def _strings(pkg):
    if "xl/sharedStrings.xml" not in pkg.parts:
        return []
    from xlsx import unesc
    return [unesc("".join(re.findall(r"<t[^>]*>(.*?)</t>", si, re.S)))
            for si in re.findall(r"<si>(.*?)</si>", pkg.text("xl/sharedStrings.xml"), re.S)]


def _cells(xml, ss):
    """{ref: value} of a tab's cells (numbers as float, text as str)."""
    out = {}
    for m in re.finditer(r'<c r="([A-Z]+\d+)"([^>]*?)(?:/>|>(.*?)</c>)', xml, re.S):
        body, attrs = m.group(3) or "", m.group(2)
        v = re.search(r"<v>(.*?)</v>", body)
        if 't="s"' in attrs and v:
            out[m.group(1)] = ss[int(v.group(1))]
        elif 't="inlineStr"' in attrs:
            out[m.group(1)] = "".join(re.findall(r"<t[^>]*>(.*?)</t>", body))
        elif v:
            try:
                out[m.group(1)] = float(v.group(1))
            except ValueError:
                out[m.group(1)] = v.group(1)
    return out


def _serial(iso):
    return (dt.date.fromisoformat(iso) - dt.date(1899, 12, 30)).days


def fill_notes(pkg, st, H, ss):
    """Empty 'Your annotation' cells on Idio Chart and 'What happened / why' cells on Px Events."""
    skipped, filled = [], 0
    s = st.xf(BLACK, sz=11)
    for tab, key, notes in (("Idio Chart", "Your annotation", H.get("top_day_notes", {})),
                            ("Px Events", "What happened / why", H.get("event_notes", {}))):
        part = _sheet_part(pkg, tab)
        if not part or not notes:
            continue
        xml = pkg.text(part)
        cells = _cells(xml, ss)
        heads = [(ref, v) for ref, v in cells.items() if isinstance(v, str) and v.startswith(key)]
        want = {}
        for href, _ in heads:
            col, row = re.match(r"([A-Z]+)(\d+)", href).groups()
            date_col = _date_col(cells, int(row), tab)
            for r2 in _table_rows(cells, date_col, int(row)):
                iso = (dt.date(1899, 12, 30) + dt.timedelta(days=int(cells[f"{date_col}{r2}"]))).isoformat()
                if iso in notes:
                    want[f"{col}{r2}"] = ("s", notes[iso], s)
        xml, sk = set_cells(xml, want)
        skipped += [f"{tab}!{r}" for r in sk]
        filled += len(want) - len(sk)
        pkg.put(part, xml)
    return filled, skipped


def _table_rows(cells, date_col, head_row):
    """Rows of the table under a header: from the next row until the first row without a date."""
    r = head_row + 1
    while isinstance(cells.get(f"{date_col}{r}"), float):
        yield r
        r += 1


def _date_col(cells, head_row, tab):
    want = "Date" if tab == "Idio Chart" else "Event date"
    for ref, v in cells.items():
        c, r = re.match(r"([A-Z]+)(\d+)", ref).groups()
        if int(r) == head_row and v == want:
            return c
    raise SystemExit(f"{tab}: no '{want}' column next to the annotation column")


# alpha chart geometry (Excel: 16 pt rows; columns from the tab's widths at the default font's digit width)
def _col_emu(xml, mdw=8):
    widths = {}
    for m in re.finditer(r'<col min="(\d+)" max="(\d+)" width="([\d.]+)"', xml):
        for c in range(int(m.group(1)), int(m.group(2)) + 1):
            widths[c] = float(m.group(3))
    dflt = float(re.search(r'defaultColWidth="([\d.]+)"', xml).group(1)) if "defaultColWidth" in xml else 8.43
    px = lambda w: int(((256 * w + int(128 / mdw)) / 256) * mdw)
    return lambda c: px(widths.get(c + 1, dflt)) * 9525      # c is 0-based


def _calibrated(dxml, sxml):
    """Column widths in EMU as Excel drew them, from shapes already on the drawing: each text box stores its
    anchor (column + offset) and its drawn position. One unknown width per distinct column width. None if too few."""
    import numpy as np
    widths = {}
    for m in re.finditer(r'<col min="(\d+)" max="(\d+)" width="([\d.]+)"', sxml):
        for c in range(int(m.group(1)), int(m.group(2)) + 1):
            widths[c - 1] = float(m.group(3))
    dflt = float(re.search(r'defaultColWidth="([\d.]+)"', sxml).group(1)) if "defaultColWidth" in sxml else 8.43
    rows, b = [], []
    for a in re.findall(r"<xdr:twoCellAnchor\b.*?</xdr:twoCellAnchor>", dxml, re.S):
        f = re.search(r"<xdr:from><xdr:col>(\d+)</xdr:col><xdr:colOff>(\d+)</xdr:colOff>", a)
        o = re.search(r'<a:off x="(\d+)"', a)
        if "txBox" in a and f and o and 'name="P1 ' not in a:
            rows.append([widths.get(k, dflt) for k in range(int(f.group(1)))])
            b.append(int(o.group(1)) - int(f.group(2)))
    classes = sorted({w for r in rows for w in r})
    if len(b) < 3 or not classes:
        return None
    A = np.array([[r.count(w) for w in classes] for r in rows], float)
    sol = np.linalg.lstsq(A, np.array(b, float), rcond=None)[0]
    emu = dict(zip(classes, sol))
    if max(abs(A @ sol - np.array(b))) > 20000:
        return None
    return lambda c: emu.get(widths.get(c, dflt)) or _col_emu(sxml)(c)


def _to_cell(x, y, colw):
    c, acc = 0, 0
    while acc + colw(c) <= x:
        acc += colw(c)
        c += 1
    return (c, int(x - acc), int(y // ROW_EMU), int(y % ROW_EMU))


def alpha_geometry(pkg, part, title_word="idiosyncratic"):
    """(frame x, y, w, h in EMU, plot fractions, chart part) of the alpha chart on Idio Chart."""
    d = drawing_part(pkg, part)
    x = pkg.text(d)
    rels = pkg.rels(d.rsplit("/", 1)[0] + "/_rels/" + d.rsplit("/", 1)[1] + ".rels")
    from xlsx import resolve
    for a in re.findall(r"<xdr:oneCellAnchor>.*?</xdr:oneCellAnchor>", x, re.S):
        rid = re.search(r'r:id="(rId\d+)"', a)
        if not rid:
            continue
        cp = resolve(d, rels[rid.group(1)][1])
        cx = pkg.text(cp)
        if title_word not in cx:
            continue
        f = re.search(r"<xdr:col>(\d+)</xdr:col><xdr:colOff>(\d+)</xdr:colOff><xdr:row>(\d+)</xdr:row><xdr:rowOff>(\d+)</xdr:rowOff>", a)
        ext = re.search(r'<xdr:ext cx="(\d+)" cy="(\d+)"', a)
        lay = re.search(r'<c:plotArea><c:layout><c:manualLayout>.*?<c:x val="([\d.E-]+)"/><c:y val="([\d.E-]+)"/>'
                        r'<c:w val="([\d.E-]+)"/><c:h val="([\d.E-]+)"/>', cx, re.S)
        colw = _calibrated(x, pkg.text(part)) or _col_emu(pkg.text(part))
        x0 = sum(colw(k) for k in range(int(f.group(1)))) + int(f.group(2))
        y0 = int(f.group(3)) * ROW_EMU + int(f.group(4))
        return {"x0": x0, "y0": y0, "w": int(ext.group(1)), "h": int(ext.group(2)),
                "lay": [float(v) for v in lay.groups()], "chart": cp, "colw": colw}
    return None


def annotate_alpha(pkg, H, geo, series, axis):
    """Text boxes + arrows for the agent's notes, placed by date and alpha value; boxes avoid the user's and each other."""
    notes = H.get("idio_notes", [])
    if not notes or not geo:
        return 0
    (dates, vals), (vmin, vmax) = series, axis
    lx, ly, lw, lh = geo["lay"]
    PX0, PY0 = geo["x0"] + lx * geo["w"], geo["y0"] + ly * geo["h"]
    PW, PH = lw * geo["w"], lh * geo["h"]
    d0, d1 = dates[0], dates[-1]

    def pt(iso):
        d = dt.date.fromisoformat(iso)
        j = min(range(len(dates)), key=lambda i: abs((dates[i] - d).days))
        x = PX0 + (dates[j] - d0).days / (d1 - d0).days * PW
        y = PY0 + (vmax - vals[j]) / (vmax - vmin) * PH
        return x, y
    dp = drawing_part(pkg, geo["part"])
    taken = _boxes(pkg.text(dp), geo["colw"])
    anchors, skipped = [], []
    W, Hl = int(1.15 * EMU_IN), int(0.19 * EMU_IN)          # 11 pt, about 15 characters a line (the user's boxes)
    for k, n in enumerate(notes):
        x, y = pt(n["date"])
        lines = max(1, -(-len(n["text"]) // 12)) + 1     # LibreOffice draws text a bit larger than Excel
        h = Hl * lines + int(0.06 * EMU_IN)
        pref = [-1, 1] if n.get("side", "above") == "above" else [1, -1]
        box = None
        for dist in [0.45 + 0.3 * i for i in range(12)]:          # up to about 3.75 inches away
            for sgn in pref:
                by = y - dist * EMU_IN - h if sgn < 0 else y + dist * EMU_IN
                bx = min(max(x - W / 2, PX0), PX0 + PW - W)
                cand = (bx, by, bx + W, by + h)
                if by < PY0 or by + h > PY0 + PH:
                    continue
                if not any(_overlap(cand, t) for t in taken):
                    box = cand
                    break
            if box:
                break
        if not box:                     # no free spot: leave it off rather than cover the user's notes
            skipped.append(n["date"])
            continue
        taken.append(box)
        cw = geo["colw"]
        tl, br = _to_cell(box[0], box[1], cw), _to_cell(box[2], box[3], cw)
        anchors.append(textbox(f"note {k + 1} {n['date']}", tl, br, n["text"]))
        ax = (box[0] + box[2]) / 2
        ay = box[3] if box[3] <= y else box[1]
        anchors.append(arrow(f"note {k + 1} arrow", _to_cell(ax, ay, cw), _to_cell(x, y, cw)))
    put_anchors(pkg, dp, anchors)
    return {"placed": len(notes) - len(skipped), "left_off_no_room": skipped}


def _boxes(xml, colw):
    out = []
    for a in re.findall(r"<xdr:twoCellAnchor\b.*?</xdr:twoCellAnchor>", xml, re.S):
        if "txBox" not in a and "<xdr:sp " not in a and "<xdr:sp>" not in a:
            continue
        p = re.findall(r"<xdr:(?:from|to)>\s*<xdr:col>(\d+)</xdr:col>\s*<xdr:colOff>(-?\d+)</xdr:colOff>\s*<xdr:row>(\d+)</xdr:row>"
                       r"\s*<xdr:rowOff>(-?\d+)</xdr:rowOff>", a)
        if len(p) == 2 and 'name="P1 ' not in a:
            (c1, o1, r1, q1), (c2, o2, r2, q2) = [[int(v) for v in t] for t in p]
            xa = sum(colw(k) for k in range(c1)) + o1
            xb = sum(colw(k) for k in range(c2)) + o2
            out.append((xa, r1 * ROW_EMU + q1, xb, r2 * ROW_EMU + q2))
    return out


def _overlap(a, b, pad=30000):
    return not (a[2] + pad <= b[0] or b[2] + pad <= a[0] or a[3] + pad <= b[1] or b[3] + pad <= a[1])


def alpha_series(model, chart_xml):
    """Week-end dates and alpha values the chart plots (its first series), from the workbook's cached values,
    and Excel's automatic value-axis range for them."""
    ser = re.search(r"<c:ser>.*?</c:ser>", chart_xml, re.S)
    if ser:                     # the chart's own cache: exactly what it plots (a fresh /model-price-history build has
        def cache(tag):         # no cached cell values yet, but it writes these)
            blk = re.search(rf"<c:{tag}>.*?</c:{tag}>", ser.group(0), re.S)
            return {int(i): float(v) for i, v in re.findall(r'<c:pt idx="(\d+)"><c:v>([^<]*)</c:v>', blk.group(0))} if blk else {}
        cd, cv = cache("cat"), cache("val")
        pts = [(dt.date(1899, 12, 30) + dt.timedelta(days=int(cd[i])), cv[i]) for i in sorted(cd) if i in cv]
        if pts:
            lo, hi = min(v for _, v in pts), max(v for _, v in pts)
            return ([p[0] for p in pts], [p[1] for p in pts]), _auto_axis(lo, hi)
    refs = re.findall(r"<c:f>([^<]*)</c:f>", chart_xml)
    cat = next(r for r in refs if ":" in r)
    val = [r for r in refs if ":" in r][1]
    wb = openpyxl.load_workbook(model, read_only=True, data_only=True)

    def col(ref):
        sh, rng = ref.rsplit("!", 1)
        ws = wb[sh.strip("'")]
        return [c[0].value for c in ws[rng.replace("$", "")]]
    D = [d.date() if isinstance(d, dt.datetime) else d for d in col(cat)]
    V = col(val)
    pts = [(d, v) for d, v in zip(D, V) if isinstance(d, dt.date) and isinstance(v, (int, float))]
    lo, hi = min(v for _, v in pts), max(v for _, v in pts)
    return ([p[0] for p in pts], [p[1] for p in pts]), _auto_axis(lo, hi)


def _auto_axis(lo, hi):
    """Excel's automatic value-axis bounds: pad the data by 5% of its range each way, take the smallest 1 / 2 / 5 x 10^k
    major unit that gives 10 intervals or fewer, round the padded ends out to it (zero kept when all data >= 0)."""
    import math
    rng = hi - min(lo, 0)
    top, bot = hi + 0.05 * rng, (lo - 0.05 * rng if lo < 0 else 0)
    unit = next(u for u in sorted(m * 10 ** e for e in range(-4, 7) for m in (1, 2, 5)) if (top - bot) / u <= 10)
    return math.floor(bot / unit) * unit, math.ceil(top / unit) * unit


# ---------------------------------------------------------------- stock blocks under the Idio charts
MARK = "FILINGS RESEARCH: THE STOCK"


def _clear_from(xml, row):
    """Drop rows >= row, and the merges and conditional formats that start there (Claude's region on a rerun)."""
    xml = re.sub(r'<row r="(\d+)"[^>]*?(?:/>|>.*?</row>)', lambda m: "" if int(m.group(1)) >= row else m.group(0), xml, flags=re.S)
    keep = [r for r in re.findall(r'<mergeCell ref="([^"]+)"/>', xml) if int(re.match(r"[A-Z]+(\d+)", r).group(1)) < row]
    xml = re.sub(r"<mergeCells\b.*?</mergeCells>", (f'<mergeCells count="{len(keep)}">' + "".join(f'<mergeCell ref="{r}"/>' for r in keep)
                                                    + "</mergeCells>") if keep else "", xml, flags=re.S)
    return re.sub(r'<conditionalFormatting sqref="([A-Z]+)(\d+)[^"]*">.*?</conditionalFormatting>',
                  lambda m: "" if int(m.group(2)) >= row else m.group(0), xml, flags=re.S)


def _bottom_row(pkg, part):
    x = pkg.text(drawing_part(pkg, part))
    rows = [int(r) + 1 for r in re.findall(r"<xdr:to>\s*<xdr:col>\d+</xdr:col>\s*<xdr:colOff>-?\d+</xdr:colOff>\s*<xdr:row>(\d+)</xdr:row>", x)]
    for a in re.findall(r"<xdr:oneCellAnchor>.*?</xdr:oneCellAnchor>", x, re.S):
        r = re.search(r"<xdr:row>(\d+)</xdr:row><xdr:rowOff>(\d+)</xdr:rowOff>", a)
        cy = re.search(r'<xdr:ext cx="\d+" cy="(\d+)"', a)
        rows.append(int((int(r.group(1)) * ROW_EMU + int(r.group(2)) + int(cy.group(1))) // ROW_EMU) + 1)
    return max(rows + [1])


def _event_moves(e):
    """The typed moves for one event row: the stock's own (B), SPY (C), idio (D); None falls back to Px Events."""
    return {"B": e.get("stock"), "C": e.get("spy"), "D": e.get("idio")}


def stock_blocks(pkg, st, part, H, ticker, sector):
    xml = pkg.text(part)
    ss = _strings(pkg)
    cells = _cells(xml, ss)
    mine = next((int(re.match(r"[A-Z]+(\d+)", r).group(1)) for r, v in cells.items() if v == MARK), None)
    if mine:                     # everything from the marker down is Claude's (the marker row says so)
        xml = _clear_from(xml, mine)
    start = mine or _bottom_row(pkg, part) + 3
    S = lambda **k: st.xf(**k)
    sty = {"t": S(color=NAVY, sz=14, b=True), "h": S(color=WHITE, b=True, fill=NAVY, align="center"),
           "hl": S(color=WHITE, b=True, fill=NAVY, align="left"), "txt": S(color=BLACK, sz=11, align="left"),
           "pct": st.xf(BLACK, "0.0%"), "pctb": st.xf(BLUE, "0.0%"), "date": st.xf(BLUE, "m/d/yy"),
           "yr": st.xf(BLACK, "0", b=True), "it": st.xf(GREY, sz=10, i=True), "lab": S(color=BLACK, b=True)}
    C, M, HT, CF = {}, [], {}, []
    r = start
    C[f"A{r}"] = ("s", MARK, sty["t"])
    HT[r] = 22
    r += 1
    C[f"A{r}"] = ("s", "Written by /research-filings from its stock section; a rerun replaces everything from the row above "
                       "down. Green / red = beat / lagged SPY that year. Returns are total returns from Px Data (dividends "
                       "included).", sty["it"])
    r += 2
    # yearly returns
    C[f"A{r}"] = ("s", f"{ticker} yearly returns vs the market", sty["t"])
    r += 1
    for k, h in enumerate(["Year", ticker, "SPY", sector or "Sector", "vs SPY", f"vs {sector or 'sector'}"]):
        C[f"{colname(k + 1)}{r}"] = ("s", h, sty["h"])
    C[f"G{r}"] = ("s", "Era: what the business was doing", sty["hl"])
    M.append(f"G{r}:T{r}")
    hr = r
    r += 1
    years = H["returns_years"]
    first = r
    look = lambda y, col: f"LOOKUP(DATE({y},12,31),'Px Data'!$A$5:$A$20000,'Px Data'!${col}$5:${col}$20000)"
    sec_col = H.get("sector_col")
    sc = H.get("stock_col") or "B"           # the stock's total-return column in Px Data (see _stock_col)
    for y in range(years[0], years[1] + 1):
        lab = f"{y}" if y < years[1] or not H.get("last_is_ytd") else f"{y} YTD"
        C[f"A{r}"] = ("s" if "YTD" in lab else "n", lab if "YTD" in lab else y, sty["yr"])
        C[f"B{r}"] = ("f", f"IFERROR({look(y, sc)}/{look(y - 1, sc)}-1,\"n.a.\")", sty["pct"])
        C[f"C{r}"] = ("f", f"IFERROR({look(y, 'C')}/{look(y - 1, 'C')}-1,\"n.a.\")", sty["pct"])
        if sec_col:
            C[f"D{r}"] = ("f", f"IFERROR({look(y, sec_col)}/{look(y - 1, sec_col)}-1,\"n.a.\")", sty["pct"])
            C[f"F{r}"] = ("f", f'IFERROR(B{r}-D{r},"n.a.")', sty["pct"])
        C[f"E{r}"] = ("f", f'IFERROR(B{r}-C{r},"n.a.")', sty["pct"])
        HT[r] = 18
        r += 1
    last = r - 1
    for e in H.get("eras", []):
        a, b = first + e["from"] - years[0], first + min(e["to"], years[1]) - years[0]
        if a > last or b < first:
            continue
        a, b = max(a, first), min(b, last)
        C[f"G{a}"] = ("s", f"{e['name']}: {e['text']}", sty["txt"])
        M.append(f"G{a}:T{b}")
        need = -(-len(e["name"] + e["text"]) // 120) * 15 + 6
        per = max(18, -(-need // (b - a + 1)))
        for k in range(a, b + 1):
            HT[k] = max(HT.get(k, 18), per)
    red = st._add("dxfs", '<dxf><font><color rgb="FF9C0006"/></font><fill><patternFill><bgColor rgb="FFFFC7CE"/></patternFill></fill></dxf>')
    grn = st._add("dxfs", '<dxf><font><color rgb="FF006100"/></font><fill><patternFill><bgColor rgb="FFC6EFCE"/></patternFill></fill></dxf>')
    CF += [(f"A{first}:B{last} E{first}:E{last}", f"AND(ISNUMBER($E{first}),$E{first}<0)", red),
           (f"A{first}:B{last} E{first}:E{last}", f"AND(ISNUMBER($E{first}),$E{first}>=0)", grn)]
    r += 1
    C[f"A{r}"] = ("s", "Total", sty["lab"])
    C[f"B{r}"] = ("f", f"{look(years[1], sc)}/{look(years[0] - 1, sc)}-1", sty["pct"])
    C[f"C{r}"] = ("f", f"{look(years[1], 'C')}/{look(years[0] - 1, 'C')}-1", sty["pct"])
    r += 2
    # event moves
    ev = H.get("event_moves", [])
    if ev:
        C[f"A{r}"] = ("s", "The big moves around company events", sty["t"])
        r += 1
        for col, h in (("A", "Event date"), ("B", ticker), ("C", "SPY"), ("D", "Idio")):
            C[f"{col}{r}"] = ("s", h, sty["h"])
        C[f"E{r}"] = ("s", "What the company said", sty["hl"])
        C[f"P{r}"] = ("s", "Driver", sty["hl"])
        M += [f"E{r}:O{r}", f"P{r}:T{r}"]
        r += 1
        for e in ev:
            C[f"A{r}"] = ("n", _serial(e["date"]), sty["date"])
            for col, src in (("B", "O"), ("C", "P"), ("D", "R")):
                typed = _event_moves(e)[col]
                C[f"{col}{r}"] = (("n", typed, sty["pctb"]) if typed is not None else
                                  ("f", f"IFERROR(INDEX('Px Events'!${src}$1:${src}$2000,MATCH(A{r},'Px Events'!$J$1:$J$2000,0)),\"n.a.\")", sty["pct"]))
            C[f"E{r}"] = ("s", e["what"], sty["txt"])
            C[f"P{r}"] = ("s", e["driver"], sty["txt"])
            M += [f"E{r}:O{r}", f"P{r}:T{r}"]
            HT[r] = max(18, -(-len(e["what"]) // 95) * 15 + 4, -(-len(e["driver"]) // 40) * 15 + 4)
            r += 1
        C[f"A{r}"] = ("s", "Moves: the reaction day in Px Events (next trading day for releases after the close). "
                           "The driver column is the filings research's judgment, not a company statement.", sty["it"])
        r += 2
    nv = H.get("no_event_moves", [])
    if nv:
        C[f"A{r}"] = ("s", "Big moves with no company event", sty["t"])
        r += 1
        for col, h in (("A", "From"), ("B", "To"), ("C", ticker), ("D", "SPY")):
            C[f"{col}{r}"] = ("s", h, sty["h"])
        C[f"E{r}"] = ("s", "What the company documents say (and don't)", sty["hl"])
        M.append(f"E{r}:T{r}")
        r += 1
        for e in nv:
            C[f"A{r}"] = ("n", _serial(e["from"]), sty["date"])
            C[f"B{r}"] = ("n", _serial(e["to"]), sty["date"])
            for col, pc in (("C", sc), ("D", "C")):
                lk = lambda cell: f"LOOKUP({cell},'Px Data'!$A$5:$A$20000,'Px Data'!${pc}$5:${pc}$20000)"
                C[f"{col}{r}"] = ("f", f"IFERROR({lk(f'B{r}')}/{lk(f'A{r}')}-1,\"n.a.\")", sty["pct"])
            C[f"E{r}"] = ("s", e["what"], sty["txt"])
            M.append(f"E{r}:T{r}")
            HT[r] = max(18, -(-len(e["what"]) // 140) * 15 + 4)
            r += 1
        r += 1
    dv = H.get("driver_by_period", [])
    if dv:
        C[f"A{r}"] = ("s", "Which driver moved the stock", sty["t"])
        r += 1
        for col, h, span in (("A", "Period", "A{r}:B{r}"), ("C", "Driver", "C{r}:G{r}"), ("H", "Evidence", "H{r}:T{r}")):
            C[f"{col}{r}"] = ("s", h, sty["hl"])
            M.append(span.format(r=r))
        r += 1
        for e in dv:
            C[f"A{r}"] = ("s", e["period"], sty["lab"])
            C[f"C{r}"] = ("s", e["driver"], sty["txt"])
            C[f"H{r}"] = ("s", e["evidence"], sty["txt"])
            M += [f"A{r}:B{r}", f"C{r}:G{r}", f"H{r}:T{r}"]
            HT[r] = max(18, -(-len(e["evidence"]) // 110) * 15 + 4, -(-len(e["driver"]) // 40) * 15 + 4)
            r += 1
        r += 1
    tk = H.get("stock_takeaways", [])
    if tk:
        C[f"A{r}"] = ("s", "Takeaways", sty["t"])
        r += 1
        for t in tk:
            C[f"A{r}"] = ("s", "• " + t, sty["txt"])
            M.append(f"A{r}:T{r}")
            HT[r] = max(18, -(-len(t) // 150) * 15 + 4)
            r += 1
    xml, skipped = set_cells(xml, C, HT)
    xml = add_merges(xml, M)
    xml = add_cf(xml, CF)
    pkg.put(part, xml)
    return start, skipped


def _sector(pkg, ss):
    """The sector ETF Px Data holds next to the momentum factor ('XHE close (dividends in)', or 'XHE close (stooq adj.)'
    in models built before the Yahoo switch), and its column."""
    cells = _cells(pkg.text(_sheet_part(pkg, "Px Data")), ss)
    for ref, v in sorted(cells.items(), key=lambda kv: colnum(re.match(r"[A-Z]+", kv[0]).group(0))):
        m = re.match(r"([A-Z]+)4$", ref)
        if m and isinstance(v, str):
            t = re.match(SECTOR_HDR, v)
            if t and t.group(1) != "MTUM":
                return t.group(1), m.group(1)
    return None, None


def _stock_col(pkg, ss):
    """The stock's total-return column in Px Data: the leftmost row-4 header ending 'total return (dividends in)'
    (Yahoo-era models, where B is the traded price), else B (older stooq models, where B is already dividend-adjusted)."""
    cells = _cells(pkg.text(_sheet_part(pkg, "Px Data")), ss)
    for ref, v in sorted(cells.items(), key=lambda kv: colnum(re.match(r"[A-Z]+", kv[0]).group(0))):
        m = re.match(r"([A-Z]+)4$", ref)
        if m and is_total_return(v):
            return m.group(1)
    return "B"


def context(model, work):
    """What the handoff agent needs from the model (it has no shell): the user's notes already on the alpha chart, the
    top-20 idio days and the Px Events dates, each with any annotation already there."""
    pkg = Package(model)
    ss = _strings(pkg)
    out = {"user_alpha_notes": [], "top_days": [], "events": []}
    part = _sheet_part(pkg, "Idio Chart")
    if part:
        d = drawing_part(pkg, part)
        if d:
            for a in re.findall(r"<xdr:twoCellAnchor\b.*?</xdr:twoCellAnchor>", pkg.text(d), re.S):
                t = " ".join(re.findall(r"<a:t>([^<]*)</a:t>", a)).strip()
                if t and 'name="P1 ' not in a:
                    out["user_alpha_notes"].append(t)
        out["top_days"] = _listing(_cells(pkg.text(part), ss), "Your annotation", "Date", ["X"])
    pe = _sheet_part(pkg, "Px Events")
    if pe:
        out["events"] = _listing(_cells(pkg.text(pe), ss), "What happened / why", "Event date", ["L"])
    with open(os.path.join(work, "handoff_context.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)
    return {k: len(v) for k, v in out.items()}


def _listing(cells, key, date_head, extra_cols):
    rows = []
    for href, v in cells.items():
        if not (isinstance(v, str) and v.startswith(key)):
            continue
        col, hrow = re.match(r"([A-Z]+)(\d+)", href).groups()
        dcol = next(re.match(r"[A-Z]+", r).group(0) for r, x in cells.items()
                    if x == date_head and re.search(r"\d+", r).group(0) == hrow)
        for r in _table_rows(cells, dcol, int(hrow)):
            iso = (dt.date(1899, 12, 30) + dt.timedelta(days=int(cells[f"{dcol}{r}"]))).isoformat()
            rows.append({"date": iso, "info": [cells.get(f"{e}{r}") for e in extra_cols],
                         "already": cells.get(f"{col}{r}") or ""})
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--out")
    ap.add_argument("--context", action="store_true", help="write _work/handoff_context.json for the agent and stop")
    ap.add_argument("--idio-only", action="store_true", help="leave Filings Charts as it is (price-history refresh)")
    a = ap.parse_args()
    work = _work(a.src)
    if a.context:
        print(json.dumps(context(a.model, work)))
        return
    cfg = json.load(open(os.path.join(work, "drivers_math.json")))["config"]
    H = json.load(open(os.path.join(work, "model_handoff.json")))
    M = load_mod(work)
    check_rows(a.model, M, [cfg["revenue"], cfg["cogs"], cfg["operating_income"]])
    pkg = Package(a.model)
    st = Styles(pkg.text("xl/styles.xml"))
    ticker = H["ticker"]
    T = Tab(st)
    comments = {}
    T.sh.set("B2", "s", f"{ticker}: filings research charts", T.s["title"])
    T.sh.heights[2] = 26
    T.r = 3
    T.note(f"Written by /research-filings ({dt.date.today().isoformat()}); a rerun replaces this tab. Green = links to MOD, "
           "black = formulas, blue = typed from company documents (source in the cell note). Takeaways come from the "
           "filings research report.")
    tk = H.get("takeaways", {})
    built = [] if a.idio_only else [name for name, ok in (
        ("fixed vs variable", block_fixed_variable(T, M, cfg, tk.get("fixed_variable"))),
        ("profit bridge", block_profit_bridge(T, M, cfg, tk.get("profit_bridge"))),
        ("price vs volume", block_price_volume(T, M, cfg, tk.get("price_volume")))) if ok]
    for g in ([] if a.idio_only else H.get("guidance", [])):
        if block_guidance(T, M, work, g, cfg, tk.get("guidance_" + g["key"]), comments):
            built.append("guidance " + g["key"])
    for b in ([] if a.idio_only else H.get("company_blocks", [])):
        block_custom(T, M, b)
        built.append(b["title"])
    out = {"tab": TAB, "blocks": built}
    part = _sheet_part(pkg, "Idio Chart")
    if part:
        ss = _strings(pkg)
        filled, skipped = fill_notes(pkg, st, H, ss)
        geo = alpha_geometry(pkg, part)
        n = 0
        if geo:
            geo["part"] = part
            series, axis = alpha_series(a.model, pkg.text(geo["chart"]))
            n = annotate_alpha(pkg, H, geo, series, axis)
            out["alpha_axis_assumed"] = axis
        sector, sec_col = _sector(pkg, ss)
        H["sector_col"] = sec_col
        H["stock_col"] = _stock_col(pkg, ss)
        start, sk2 = stock_blocks(pkg, st, part, H, ticker, sector)
        out.update({"annotation_cells_filled": filled, "kept_users_cells": skipped + sk2, "alpha_notes": n,
                    "stock_rows_from": start})
    else:
        out["idio"] = "no Idio Chart tab: run /model-price-history first"
    if not a.idio_only:
        write_tab(pkg, T, comments)
    pkg.put("xl/styles.xml", st.render())
    pkg.finish()
    pkg.save(a.out)
    import notebox; notebox.fix(a.out, a.out, since=a.model)   # this tab's note boxes open readable (other tabs untouched)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
