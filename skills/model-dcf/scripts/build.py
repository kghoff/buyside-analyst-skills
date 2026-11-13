"""Writes the DCF tab (replaced whole on a rerun, placed right after 'DCF Cheat Sheet') into a copy of the user's model.

usage: python3 build.py --model M --ctx context.json --solved solved.json --out OUT.xlsx --written inputs_written.json
Live formulas implement "The DCF math" exactly as dcfmath.run does (check.py proves it). Yellow fill + blue font = the user's
inputs (values from solved.json: kept from their tab or defaulted), green = links to MOD / Px Data, black = formulas,
grey italic = the reverse-DCF snapshot from solved.json. Layout and formatting follow the user's own edit of the DXCM tab
(2026-11-10): title row, terminal value in the valuation block, TTM EPS, spacer rows between line groups, $ formats. Raw XML (xlsx.py): every other part of the workbook is copied
byte for byte. Also read_inputs(): the values the user typed in an existing DCF tab, found by row label and year."""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from context import find_rows  # noqa: E402
from dcfmath import label  # noqa: E402
from modmap import ModMap  # noqa: E402
from xlsx import CT, Package, Sheet, Styles, colname, comments_parts, esc  # noqa: E402
from openpyxl.utils import column_index_from_string as openpyxl_col  # noqa: E402

TAB, AFTER = "DCF", "DCF Cheat Sheet"
BLUE, BLACK, GREEN, GREY, WHITE, NAVY, RED = "FF0000FF", "FF000000", "FF008000", "FF808080", "FFFFFFFF", "FF002060", "FFC00000"
YELLOW = "FFFFFF99"
MNY, PCT, BPS, CUS, DLR, MULT, PX = ('#,##0.0_);\\(#,##0.0\\);"–"', "0.0%", '#,##0_);\\(#,##0\\);"–"',
                                     '#,##0.0_);\\(#,##0.0\\);"-"_)', '"$"#,##0', '0.0"x"', '"$"#,##0.00')
USD = '"$"#,##0.0_);\\("$"#,##0.0\\);"-"_)'     # the user's $M format on the yearly lines
HIST0, Y0C, TVC = 3, 8, 39            # history C..G (5 years), year 0 in H, t = 1..30 in I..AL, terminal value in AM
PXB = "'Px Data'!$B:$B"
YEARS_LABEL = "$M, fiscal years"
WACC_LABEL, MULT_LABEL = "WACC", "Terminal multiple (x year-30 unlevered FCF)"
INPUT_LABELS = {"dgm": "   Gross margin change, bps yoy", "opex_inc": "   Incremental opex per $ of new revenue",
                "tax": "Tax rate", "da_pct": "   D&A % of revenue", "capex_pct": "   Capex % of revenue",
                "wc_inc": "   Working capital per $ of new revenue"}
LEGACY_WRITTEN = {"Installed Base growth, % yoy": "gc", "Average customer growth, % yoy": "gc",
                  "Revenue per customer growth, % yoy": "gp"}   # the previous version's fixed driver rows (one-time migration)
REST = ["rev", "rev_yoy", None, "gm", "dgm", None, "gross", "opex", "opex_pct", "opex_inc", None, "oi", "oi_margin",
        "inc_margin", "tax", None, "nopat", "da", "da_pct", "capex", "capex_pct", "wc", "wc_inc", None, "ufcf",
        "ufcf_margin", None, "pv", "cum_pv"]            # None = a blank spacer row (the user's layout)
MODL = ["mrev"]
PRICES = [("last", "Last close"), ("high3y", "3-year high"), ("low3y", "3-year low")]


def tcol(t):
    """Column letter of forecast year t (0 = year 0)."""
    return colname(Y0C + t)


def growth_label(name):
    return f"{name} growth, % yoy"


def lines(ctx):
    """The yearly rows: a level row and a growth row per revenue-identity factor, then the rest."""
    out = []
    for j in range(len(ctx["factors"])):
        out += [f"lv{j}", f"g{j}", None]
    return out + REST


def drivers(ctx):
    """Reverse-DCF drivers: each factor (by name), then the gross-margin change."""
    return [f["name"] for f in ctx["factors"]] + ["dgm"]


def driver_row(ctx, R, name):
    """Row of a driver's yellow growth cells (a factor's growth row, or dgm)."""
    if name == "dgm":
        return R["dgm"]
    return R[f"g{[f['name'] for f in ctx['factors']].index(name)}"]


def layout(ctx):
    """Row layout: fixed blocks on top, the reverse-DCF rows (3 prices x the drivers), then the yearly lines (one
    block per revenue driver), so check.py can find every cell."""
    rows = {"title": 1, "val_hdr": 2, "wacc": 3, "mult": 4, "pv_fcf": 5, "tv": 6, "pv_tv": 7, "tv_share": 8, "ev": 9,
            "cash": 10, "st": 11, "debt_cur": 12, "debt_lt": 13, "net_debt": 14, "equity": 15, "shares": 16, "vps": 17,
            "price": 18, "ret": 19, "eps_hdr": 21, "rev_hdr": 30, "rev_user": 32}
    dr = drivers(ctx)
    blk = len(dr) + 1                     # per price: a label row, then one row per driver (names in column B)
    rows.update({f"price_{pk}": rows["rev_user"] + 1 + blk * i for i, (pk, _) in enumerate(PRICES)})
    rev_rows = [(rows["rev_user"] + 2 + blk * i + j, pk, d) for i, (pk, _) in enumerate(PRICES) for j, d in enumerate(dr)]
    rows["years"] = rev_rows[-1][0] + 3
    rows["period"] = rows["years"] + 1
    first = rows["years"] + 3
    ls = lines(ctx)
    for i, n in enumerate(ls):
        if n:
            rows[n] = first + i
    rows["mod_hdr"] = first + len(ls) + 1
    for i, n in enumerate(MODL):
        rows[n] = rows["mod_hdr"] + 1 + i
    assert len(set(rows.values())) == len(rows), "two DCF lines share a row"
    return {"tab": TAB, "rows": rows, "value_per_share": f"C{rows['vps']}", "tv_col": colname(TVC),
            "year_cols": {t: tcol(t) for t in range(0, 31)}, "reverse_rows": rev_rows}


def input_cells(ctx):
    """{input: [year labels]} of the tab's yellow cells (None = the single WACC / multiple cell)."""
    k = ctx["k"]
    yrs = [label(ctx, t) for t in range(k + 1, 31)]
    out = {f["name"]: list(yrs) for f in ctx["factors"]}
    out.update({n: list(yrs) for n in ("dgm", "opex_inc", "tax", "da_pct", "capex_pct", "wc_inc")})
    out.update(wacc=[None], tv_mult=[None])
    return out


def input_label(name, ctx):
    if name == "wacc":
        return WACC_LABEL
    if name == "tv_mult":
        return MULT_LABEL
    return INPUT_LABELS.get(name) or growth_label(name)


def span(years):
    """['2031E', ..., '2056E'] -> '2031E-2056E' (contiguous runs joined by commas)."""
    if years == ["value"]:
        return "value"
    runs, start, prev = [], None, None
    for y in years:
        n = int(y[:4])
        if start is None:
            start = prev = (y, n)
        elif n == prev[1] + 1:
            prev = (y, n)
        else:
            runs.append((start, prev))
            start = prev = (y, n)
    runs.append((start, prev))
    return ", ".join(a[0] if a == b else f"{a[0]}-{b[0]}" for a, b in runs)


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _same(a, b):
    return _num(a) and _num(b) and abs(a - b) <= 1e-12 * max(1.0, abs(b))


def _unrecognised(why):
    return SystemExit(f"model-dcf: the model's DCF tab has a layout this skill does not recognise ({why}), so it "
                      "can't tell which numbers you typed. Nothing was changed. Rename the tab (e.g. 'DCF old') to keep "
                      "it and rerun, and a fresh DCF tab will be built beside it.")


def _rows(path, data_only):
    import openpyxl
    wb = openpyxl.load_workbook(path, read_only=True, data_only=data_only)
    if TAB not in wb.sheetnames:
        wb.close()
        return None
    grid = {r: list(row) for r, row in enumerate(wb[TAB].iter_rows(values_only=True), start=1)}
    wb.close()
    return grid


def read_inputs(model, ctx, written=None):
    """What the user typed in an existing DCF tab: (kept {input: {year: value}, 'wacc': v, 'tv_mult': v},
    formulas {input: {year: formula}}, kind, orphans). Read only. kind: None (no DCF tab) or 'existing'.
    Inputs are found by row label and year column, so a tab built for other drivers still gives up the inputs it
    shares with this one. A yellow cell is the user's if it holds a formula, or a number that differs from what the last
    build wrote there (written = that build's inputs_written.json; missing file = every number is theirs). orphans:
    growth-input rows in the old tab that this layout doesn't have (e.g. after the drivers changed), with any years
    the user typed in them, so they can retype them where they now belong. Stops if the tab has no year header."""
    grid = _rows(model, False)
    if grid is None:
        return {}, {}, None, []
    lab = lambda r: " ".join(grid[r][1].split()) if len(grid[r]) > 1 and isinstance(grid[r][1], str) else None
    hdr = next((r for r in grid if lab(r) == YEARS_LABEL), None)
    if hdr is None:
        raise _unrecognised(f"no '{YEARS_LABEL}' row")
    col = {v: i for i, v in enumerate(grid[hdr]) if isinstance(v, str)}
    at = lambda r, c: grid[r][c] if r in grid and c < len(grid[r]) else None
    by_label = {lab(r): r for r in grid if lab(r)}
    w = json.load(open(written)) if written and os.path.exists(written) else None
    cells, names = {}, set()                     # (name, year or None) -> (row, col index)
    for name, years in input_cells(ctx).items():
        text = " ".join(input_label(name, ctx).split())
        names.add(text)
        if text not in by_label:
            continue
        for y in years:
            if y is None or y in col:
                cells[(name, y)] = (by_label[text], 2 if y is None else col[y])
    orphans = []
    for text, r in by_label.items():
        if text.endswith("growth, % yoy") and text not in names:
            inputs_yrs = {label(ctx, t) for t in range(ctx["k"] + 1, 31)}
            rec = (w or {}).get(LEGACY_WRITTEN.get(text, text[:-len(" growth, % yoy")]), {})
            mine = [y for y, c in col.items() if y in inputs_yrs and _num(at(r, c)) and not _same(float(at(r, c)), rec.get(y))]
            orphans.append({"row_label": text, "typed_years": mine if w is not None else "unknown (no build record)"})
    kept, formulas, need = {}, {}, []
    for (name, y), (r, c) in cells.items():
        v = at(r, c)
        if isinstance(v, str) and v.startswith("="):
            formulas.setdefault(name, {})[y or "value"] = v[1:]
            need.append((name, y, r, c))
        elif _num(v):
            if w is not None and _same(float(v), w.get(name) if y is None else w.get(name, {}).get(y)):
                continue
            _keep(kept, name, y, float(v))
    if need:
        vals = _rows(model, True)
        if any(not _num(vals.get(r, [None] * (c + 1))[c] if c < len(vals.get(r, [])) else None) for _, _, r, c in need):
            import tempfile
            import lo
            vals = _rows(lo.recalc(model, tempfile.mkdtemp(prefix="dcf_read_")), True)
        for name, y, r, c in need:
            v = vals[r][c] if r in vals and c < len(vals[r]) else None
            if not _num(v):
                raise SystemExit(f"model-dcf: your formula in the DCF tab ({name}, {y or 'value'}) gives {v!r}, not a "
                                 "number. Fix it and rerun.")
            _keep(kept, name, y, float(v))
    return kept, formulas, "existing", orphans


def _keep(kept, name, y, v):
    if y is None:
        kept[name] = v
    else:
        kept.setdefault(name, {})[y] = v


def _q(ref):
    """'Px Data!B5' -> "'Px Data'!B5" (sheet names with spaces quoted)."""
    sh, cell = ref.rsplit("!", 1)
    sh = sh.strip("'")
    return f"{sh}!{cell}" if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.]*", sh) else f"'{sh}'!{cell}"


class Tab:
    def __init__(self, st):
        self.sh, self.st, self.notes = Sheet(), st, {}
        self.sh.widths = {1: 2, 2: 39.5, **{c: 11 for c in range(3, TVC + 1)}}
        S = st.xf
        self.title = S(NAVY, sz=16, b=True)
        self.hdr = S(WHITE, b=True, fill=NAVY)
        self.hc = S(WHITE, b=True, fill=NAVY, align="center")
        self.lab, self.sub = S(BLACK), S(BLACK, b=True)
        self.it = S(GREY, i=True, sz=10)
        self.grey_txt = S(GREY, i=True)

    def put(self, ref, kind, val, color=BLACK, fmt="General", b=False, i=False, border=None):
        self.sh.set(ref, kind, val, self.st.xf(color, fmt, b=b, i=i, border=border))

    def inp(self, ref, val, fmt, formula=None, i=False):
        """A yellow input cell: The user types over it (a formula they typed is written back as their formula)."""
        st = self.st.xf(BLUE, fmt, i=i, fill=YELLOW)
        self.sh.set(ref, *(("f", formula) if formula else ("n", float(val))), st)

    def label(self, r, text, bold=False, i=False, indent=0):
        st = self.sub if bold else self.lab
        if i or indent:
            st = self.st.xf(BLACK, b=bold, i=i, indent=indent)
        self.sh.set(f"B{r}", "s", text, st)

    def header(self, r, text, heads=(), first=3):
        self.sh.set(f"B{r}", "s", text, self.hdr)
        for k, h in enumerate(heads):
            self.sh.set(f"{colname(first + k)}{r}", "s" if isinstance(h, str) else "n", h, self.hc)

    def note(self, ref, text):
        self.notes[ref] = text


def build(model, ctx, solved, out, written_path=None):
    """written_path: where to save the default written into each input cell (inputs_written.json; a rerun compares
    the tab against it to tell the user's typing from the build's defaults). The user's cells (kept, formulas) aren't saved."""
    L = layout(ctx)
    R = L["rows"]
    F = ctx["factors"]
    inputs, as_of, formulas = solved["inputs"], solved["as_of"], solved.get("formulas", {})
    kept = solved.get("kept", {})            # the user's cells: never recorded, so a rerun still sees them as theirs
    written = {}
    k, refs, y0 = ctx["k"], ctx["refs"], ctx["year0"]
    if not 1 <= k <= 5:
        raise SystemExit(f"model-dcf: MOD needs 1-5 forecast years after {y0} (found {k}); run /model-forecast first.")
    lab = lambda t: label(ctx, t)

    mm = ModMap(model)
    MR = find_rows(mm)                       # MOD rows by role (the same lookup context.py used)
    pkg = Package(model)
    st = Styles(pkg.text("xl/styles.xml"))
    T = Tab(st)
    P = T.put

    # ---------------------------------------------------------------- title and legend
    ticker = ctx.get("source_model", "").split("_")[0].split(".")[0].upper()
    T.sh.set(f"B{R['title']}", "s", f"{ticker} 30 yr DCF".lstrip(), T.title)
    T.sh.heights[R["title"]] = 24
    T.note(f"B{R['title']}", "Yellow = your input: type over it (rerunning /model-dcf keeps what you typed). Green = link "
                             "to MOD / Px Data. Black = formula. Grey italic = reverse-DCF snapshot from the last /model-dcf "
                             f"run. Year 0 = {y0}; forecast {lab(1)}-{lab(30)}; valuation date = end of {y0[:4]}. "
                             f"{lab(1)}-{lab(k)}: the revenue drivers, gross profit and costs link to MOD, so revenue "
                             "and operating income equal your MOD forecast; your inputs start in "
                             f"{lab(k + 1)}. Revenue = " + " + ".join(
                                 " x ".join(("avg " if F[j]["average"] else "") + F[j]["name"] for j in term)
                                 for term in ctx["terms"]) + " (the forecast plan's revenue identity)."
                             + (" FALLBACK: the forecast plan has no revenue identity, so revenue itself is the only "
                                "driver; rerun /model-forecast to build it from the key drivers." if ctx.get("identity_fallback") else ""))

    # ---------------------------------------------------------------- valuation block
    first, last, tvc = tcol(1), tcol(30), colname(TVC)
    q = ctx["cap"]["quarter"]
    T.header(R["val_hdr"], "VALUATION, $M except per share")
    rows_v = [
        ("pv_fcf", f"PV of FCF, {lab(1)}-{lab(30)}", f"SUM({first}{R['pv']}:{last}{R['pv']})", BLACK, MNY),
        ("tv", "Terminal Value", f"{last}{R['ufcf']}*C{R['mult']}", BLACK, MNY),
        ("pv_tv", "PV of terminal value", f"C{R['tv']}/(1+C{R['wacc']})^{last}{R['period']}", BLACK, MNY),
        ("tv_share", "Terminal value % of EV (check: under ~25%)", f"C{R['pv_tv']}/C{R['ev']}", BLACK, PCT),
        ("ev", "Enterprise value", f"C{R['pv_fcf']}+C{R['pv_tv']}", BLACK, MNY),
        ("cash", f"Cash & equivalents ({q})", _q(refs["cap_cash"]), GREEN, MNY),
        ("st", f"Short-term marketable securities ({q})", _q(refs["cap_st_securities"]) if refs.get("cap_st_securities")
         else "0", GREEN, MNY),
        ("debt_cur", f"Current debt ({q})", "+".join(_q(x) for x in refs["cap_debt_current"]) or "0", GREEN, MNY),
        ("debt_lt", f"Long-term debt ({q})", "+".join(_q(x) for x in refs["cap_debt_lt"]) or "0", GREEN, MNY),
        ("net_debt", "Net debt (debt - cash - securities)", f"C{R['debt_cur']}+C{R['debt_lt']}-C{R['cash']}-C{R['st']}",
         BLACK, MNY),
        ("equity", "Equity value (MCAP)", f"C{R['ev']}-C{R['net_debt']}", BLACK, MNY),
        ("shares", f"Diluted shares, M ({q})", _q(refs["cap_shares"]), GREEN, MNY),
        ("vps", "Value per share", f"C{R['equity']}/C{R['shares']}", BLACK, PX),
        ("price", "Price (last close in Px Data; date beside it)", f"INDEX({PXB},MATCH(9.99E+307,{PXB}))", GREEN, PX),
        ("ret", "% return to value", f"C{R['vps']}/C{R['price']}-1", BLACK, PCT),
    ]
    for key, text, fmt in (("wacc", WACC_LABEL, PCT), ("tv_mult", MULT_LABEL, MULT)):
        r = R["wacc" if key == "wacc" else "mult"]
        T.label(r, text)
        f = formulas.get(key, {}).get("value")
        T.inp(f"C{r}", inputs[key], fmt, f)
        if not f and key not in kept:
            written[key] = float(inputs[key])
    for key, text, f, color, fmt in rows_v:
        T.label(R[key], text, key in ("vps", "ev", "equity"))
        P(f"C{R[key]}", "f", f, color, fmt, b=key in ("vps", "equity"))
    P(f"D{R['price']}", "f", f"INDEX('Px Data'!$A:$A,MATCH(9.99E+307,{PXB}))", GREEN, "yyyy-mm-dd")
    P(f"D{R['tv_share']}", "f", f'IF(C{R["tv_share"]}>0.25,"above 25%: check","ok")', BLACK)
    T.sh.cf.append((f"C{R['tv_share']}:D{R['tv_share']}", f"$C${R['tv_share']}>0.25", st.dxf_font(RED)))

    r = R["eps_hdr"]
    T.header(r, "Implied P/E on MOD EPS", ["EPS", "P/E at price", "P/E at value"])
    ttm = [q for q in mm.order if mm.is_q(q) and not q.endswith("E")][-4:]     # the last four reported quarters
    eps_rows = [(f"TTM {nm} EPS", "+".join(f"MOD!{mm.col(q)}{MR[key]}" for q in ttm)
                 if len(ttm) == 4 and key in MR else None) for nm, key in (("GAAP", "eps"), ("non-GAAP", "eps_ng"))]
    eps_rows += [(f"{yl} {nm} EPS", f"MOD!{mm.col(yl)}{MR[key]}" if key in MR else None)
                 for nm, key in (("GAAP", "eps"), ("non-GAAP", "eps_ng")) for yl in (y0, lab(1))]
    if len(ttm) == 4:
        T.note(f"B{r + 1}", f"TTM = the last four reported quarters in MOD ({ttm[0]} to {ttm[-1]}).")
    T.sh.heights[r] = 17
    for i, (text, ref) in enumerate(eps_rows, start=r + 1):
        if ref is None:                          # fewer than four reported quarters: no TTM
            continue
        T.label(i, text)
        P(f"C{i}", "f", ref, GREEN, "0.00")
        P(f"D{i}", "f", f"$C${R['price']}/C{i}", BLACK, '0.0"x"')
        P(f"E{i}", "f", f"$C${R['vps']}/C{i}", BLACK, '0.0"x"')

    # ---------------------------------------------------------------- reverse DCF snapshot
    sy = solved["shift_years"]
    y5, yk = sy[-1], lab(k)
    heads = ["Price", "Shift unit", f"Added to each year {sy[0]}-{y5}", f"That driver's CAGR {yk}-{y5}",
             f"Revenue CAGR {yk}-{y5}", f"{y5} revenue", f"{y5} gross margin", "Return to your value"]
    T.header(R["rev_hdr"], f"REVERSE DCF snapshot {as_of}", heads)
    T.sh.heights[R["rev_hdr"]] = 68
    T.note(f"B{R['rev_hdr']}", f"One driver at a time, shift on {sy[0]}-{y5}: the amount added to each of that "
                               f"driver's yellow cells {sy[0]}-{y5} (others at your inputs) that makes value per share "
                               f"equal the price (growth in % points, gross margin in bps). Values from the /model-dcf run "
                               f"on {as_of}; editing inputs does not move them (rerun /model-dcf to refresh).")
    grey = lambda ref, v, fmt: P(ref, "n", float(v), GREY, fmt, i=True)
    kv, user_vals = R["rev_user"], solved["user"]
    T.label(kv, "Your inputs", True)
    grey(f"C{kv}", solved["value_per_share"], PX)
    T.sh.set(f"D{kv}", "s", "(value per share)", T.grey_txt)
    mcols = (("G", "rev_cagr5", PCT), ("H", "rev_end", MNY), ("I", "gm_end", PCT))
    for col, key, fmt in mcols:
        grey(f"{col}{kv}", user_vals[key], fmt)
    pname = dict(PRICES)
    dname = {d: ("Gross margin" if d == "dgm" else d) for d in drivers(ctx)}
    for pk, _ in PRICES:
        T.label(R[f"price_{pk}"], f"{pname[pk]} ({ctx['price'][pk]['date']})", True)
    for row, pk, d in L["reverse_rows"]:
        res = solved["reverse"][pk]
        x = res[d]
        T.label(row, dname[d], indent=1)
        grey(f"C{row}", res["price"], PX)
        T.sh.set(f"D{row}", "s", "bps / yr" if d == "dgm" else "% pts / yr", T.grey_txt)
        if x.get("status") != "ok":
            T.sh.set(f"E{row}", "s", "out of range", T.grey_txt)
            continue
        grey(f"E{row}", x["shift"], "0" if d == "dgm" else "0.0%")
        if "driver_cagr5" in x:
            grey(f"F{row}", x["driver_cagr5"], PCT)
        for col, key, fmt in mcols:
            grey(f"{col}{row}", x[key], fmt)
        grey(f"J{row}", solved["value_per_share"] / res["price"] - 1, PCT)

    # ---------------------------------------------------------------- year header
    hist = ctx["history"][-5:]
    hcols = list(range(Y0C - len(hist), Y0C))
    T.header(R["years"], YEARS_LABEL)
    T.sh.heights[R["years"]] = 17
    for c, h in zip(hcols, hist):
        T.sh.set(f"{colname(c)}{R['years']}", "s", h["year"], T.hc)
    for t in range(0, 31):
        T.sh.set(f"{tcol(t)}{R['years']}", "s", lab(t), T.hc)
    T.sh.set(f"{tvc}{R['years']}", "s", "TV", T.hc)
    T.label(R["period"], "Discount period t (year-end)")
    for t in range(0, 31):
        P(f"{tcol(t)}{R['period']}", "n", t, BLACK, "0")

    # ---------------------------------------------------------------- the yearly lines
    labels = {"rev": "Revenue", "rev_yoy": "   % yoy", "gm": "Gross margin", "gross": "Gross profit",
              "opex": "Opex (all operating expenses)", "opex_pct": "   % of revenue", "oi": "Operating income",
              "oi_margin": "   % margin", "inc_margin": "   incremental margin", "nopat": "NOPAT", "da": "(+) D&A",
              "capex": "(-) Capex", "wc": "(+/-) Working capital change", "ufcf": "UNLEVERED FCF",
              "ufcf_margin": "   % margin", "pv": "PV of FCF", "cum_pv": "Cumulative PV % of EV", **INPUT_LABELS}
    fmts = {"gm": PCT, "tax": PCT, "cum_pv": PCT, "dgm": BPS, "opex_inc": PCT, "da_pct": PCT, "capex_pct": PCT,
            "wc_inc": PCT}
    for j, f in enumerate(F):
        unit = f.get("unit") or ""
        labels[f"lv{j}"] = f["name"] + (f" ({unit})" if unit else "")
        labels[f"g{j}"] = growth_label(f["name"])
        fmts[f"lv{j}"] = USD if "$" in unit else CUS
        fmts[f"g{j}"] = PCT
    gnames = {f"g{j}": f["name"] for j, f in enumerate(F)}       # growth row -> its input name
    bold = ("rev", "oi", "nopat", "ufcf", "pv")                     # values in bold
    bold_lab = tuple(f"lv{j}" for j in range(len(F))) + ("rev", "gm", "oi", "nopat", "ufcf")
    ital = tuple(gnames) + ("da_pct", "capex_pct", "wc_inc", "ufcf_margin")
    indent = tuple(gnames) + ("da", "da_pct", "capex", "capex_pct", "wc", "wc_inc")
    ls = [n for n in lines(ctx) if n]
    for n in ls:
        T.label(R[n], labels[n], n in bold_lab, n in ital, 1 if n in indent else 0)
    for n in ls:
        fmts.setdefault(n, PCT if n.endswith(("_yoy", "_margin", "_pct")) else USD)

    def cell(n, c):
        return f"{c}{R[n]}"

    def put(n, c, f, color=BLACK, border=None):
        P(cell(n, c), "f", f, color, fmts[n], b=n in bold, i=n in ital, border=border)

    def inp(n, t):
        name = gnames.get(n, n)
        f = formulas.get(name, {}).get(lab(t))
        T.inp(cell(n, tcol(t)), inputs[name][lab(t)], fmts[n], f, i=n in ital)
        if not f and lab(t) not in kept.get(name, ()):
            written.setdefault(name, {})[lab(t)] = float(inputs[name][lab(t)])

    def mref(key, yl):
        return f"MOD!{mm.col(yl)}{MR[key]}"

    def fref(j, yl):
        return f"MOD!{mm.col(yl)}{F[j]['row']}"

    # history, year 0 and MOD's forecast years: links to MOD (the drivers, revenue, gross profit and costs)
    c0 = tcol(0)
    linked = [(colname(c_i), h["year"]) for c_i, h in zip(hcols, hist)] + [(c0, y0)] + [(tcol(t), lab(t)) for t in range(1, k + 1)]
    for c, yl in linked:
        for j in range(len(F)):
            put(f"lv{j}", c, fref(j, yl), GREEN)
        if c in (tcol(t) for t in range(1, k + 1)):
            terms = []
            p = colname(openpyxl_col(c) - 1)
            for term in ctx["terms"]:
                terms.append("*".join(f"({cell(f'lv{j}', c)}+{cell(f'lv{j}', p)})/2" if F[j]["average"]
                                      else cell(f"lv{j}", c) for j in term))
            put("rev", c, "+".join(terms))
        else:
            put("rev", c, mref("rev", yl), GREEN)
        put("gross", c, mref("gp", yl), GREEN)
        put("opex", c, f"{mref('gp', yl)}-{mref('oi', yl)}", GREEN)
        put("tax", c, mref("tax_rate", yl), GREEN)
        put("da", c, mref("da", yl), GREEN)
        put("capex", c, f"-{mref('capex', yl)}", GREEN)
        put("wc", c, mref("wc", yl), GREEN)
        put("gm", c, f"{cell('gross', c)}/{cell('rev', c)}")
        put("da_pct", c, f"{cell('da', c)}/{cell('rev', c)}")
        put("capex_pct", c, f"{cell('capex', c)}/{cell('rev', c)}")
    lc = [c for c, _ in linked]
    for i in range(1, len(lc)):
        c, p = lc[i], lc[i - 1]
        for j in range(len(F)):
            put(f"g{j}", c, f'IFERROR({cell(f"lv{j}", c)}/{cell(f"lv{j}", p)}-1,"")')
        put("dgm", c, f"({cell('gm', c)}-{cell('gm', p)})*10000")
        put("opex_inc", c, f'IFERROR(({cell("opex", c)}-{cell("opex", p)})/({cell("rev", c)}-{cell("rev", p)}),"")')
        put("wc_inc", c, f'IFERROR(-{cell("wc", c)}/({cell("rev", c)}-{cell("rev", p)}),"")')

    # years after MOD: The user's inputs
    W, M = f"$C${R['wacc']}", f"$C${R['mult']}"
    for t in range(k + 1, 31):
        c, p = tcol(t), tcol(t - 1)
        for j in range(len(F)):
            inp(f"g{j}", t)
            put(f"lv{j}", c, f"{cell(f'lv{j}', p)}*(1+{cell(f'g{j}', c)})")
        terms = ["*".join(f"({cell(f'lv{j}', c)}+{cell(f'lv{j}', p)})/2" if F[j]["average"] else cell(f"lv{j}", c)
                          for j in term) for term in ctx["terms"]]
        put("rev", c, "+".join(terms))
        inp("dgm", t)
        put("gm", c, f"{cell('gm', p)}+{cell('dgm', c)}/10000")
        put("gross", c, f"{cell('rev', c)}*{cell('gm', c)}")
        inp("opex_inc", t)
        inp("wc_inc", t)
        put("opex", c, f"{cell('opex', p)}+{cell('opex_inc', c)}*({cell('rev', c)}-{cell('rev', p)})")
        inp("tax", t)
        inp("da_pct", t)
        inp("capex_pct", t)
        put("da", c, f"{cell('da_pct', c)}*{cell('rev', c)}")
        put("capex", c, f"{cell('capex_pct', c)}*{cell('rev', c)}")
        put("wc", c, f"-{cell('wc_inc', c)}*({cell('rev', c)}-{cell('rev', p)})")
    for j, f in enumerate(F):
        T.note(cell(f"g{j}", tcol(k + 1)), f"Default: fades in a straight line from the {lab(k)} growth to the long-run "
                                           f"{f['long_run']:.1%} by {lab(min(k + 10, 30))}, then holds. Long-run source "
                                           f"(forecast plan): {f.get('long_run_source') or 'none given'}")
    for t in range(1, 31):
        c = tcol(t)
        put("oi", c, f"{cell('gross', c)}-{cell('opex', c)}")
        put("nopat", c, f"{cell('oi', c)}*(1-{cell('tax', c)})")
        put("ufcf", c, f"{cell('nopat', c)}+{cell('da', c)}-{cell('capex', c)}+{cell('wc', c)}")
        put("pv", c, f"{cell('ufcf', c)}/(1+{W})^{cell('period', c)}", border="tb" + ("r" if t == 30 else ""))
        put("cum_pv", c, f"SUM(${tcol(1)}${R['pv']}:{cell('pv', c)})/$C${R['ev']}")
    for c in [colname(x) for x in hcols] + [c0]:
        put("oi", c, f"{cell('gross', c)}-{cell('opex', c)}")
        put("nopat", c, f"{cell('oi', c)}*(1-{cell('tax', c)})")
        put("ufcf", c, f"{cell('nopat', c)}+{cell('da', c)}-{cell('capex', c)}+{cell('wc', c)}")
    allc = [colname(x) for x in hcols] + [tcol(t) for t in range(0, 31)]
    for i, c in enumerate(allc):
        put("opex_pct", c, f"{cell('opex', c)}/{cell('rev', c)}")
        put("oi_margin", c, f"{cell('oi', c)}/{cell('rev', c)}")
        put("ufcf_margin", c, f"{cell('ufcf', c)}/{cell('rev', c)}")
        if i == 0:
            continue
        p = allc[i - 1]
        put("rev_yoy", c, f'IFERROR({cell("rev", c)}/{cell("rev", p)}-1,"")')
        put("inc_margin", c, f'IFERROR(({cell("oi", c)}-{cell("oi", p)})/({cell("rev", c)}-{cell("rev", p)}),"")')
    put("pv", c0, f"{cell('ufcf', c0)}/(1+{W})^{cell('period', c0)}", border="ltb")   # year 0: shown, not in the sum
    put("ufcf", tvc, f"{M}*{cell('ufcf', tcol(30))}")
    T.note(cell("ufcf", tvc), "Terminal value = terminal multiple x year-30 unlevered FCF (ex-growth multiple).")

    # ---------------------------------------------------------------- MOD revenue (the identity must equal it)
    T.label(R["mod_hdr"], f"MOD forecast (links, {lab(1)}-{lab(k)})", True)
    T.label(R["mrev"], "   MOD Revenue (check: equals Revenue above)")
    for t in range(1, k + 1):
        P(f"{tcol(t)}{R['mrev']}", "f", _q(refs["mod"]["rev"][t - 1]), GREEN, USD)

    write_tab(pkg, T)
    pkg.put("xl/styles.xml", st.render())
    pkg.finish()
    pkg.save(out)
    import notebox; notebox.fix(out, out, since=model)   # this tab's note boxes open readable (other tabs untouched)
    if written_path:
        json.dump(written, open(written_path, "w"), indent=1)
    return L


def write_tab(pkg, T):
    """Replace the DCF tab whole (chart-free), put it right after DCF Cheat Sheet, attach the notes."""
    if TAB in [s[0] for s in pkg.sheets()]:
        pkg.remove_sheet(TAB)
    part = pkg.add_sheet(TAB, "")
    _move_after(pkg, TAB, AFTER)
    lrid = None
    if T.notes:
        pkg.content_default("vml", "application/vnd.openxmlformats-officedocument.vmlDrawing")
        ids = [int(x) for p, data in pkg.parts.items() if p.endswith(".vml")
               for d in re.findall(rb'<o:idmap v:ext="edit" data="([\d,\s]+)"', data) for x in re.findall(rb"\d+", d)]
        cn, vn = pkg.free("xl/comments{}.xml"), pkg.free("xl/drawings/vmlDrawing{}.vml")
        cx, vml = comments_parts(T.notes, max(ids + [0]) + 1)
        pkg.put(f"xl/comments{cn}.xml", cx)
        pkg.put(f"xl/drawings/vmlDrawing{vn}.vml", vml)
        lrid = pkg.attach(part, "vml", f"xl/drawings/vmlDrawing{vn}.vml")
        pkg.attach(part, "comments", f"xl/comments{cn}.xml", CT["comments"])
    T.sh.freeze = "C1"
    T.sh.zoom = 115
    pkg.put(part, T.sh.xml(None, lrid))


def _move_after(pkg, name, after):
    """Put tab `name` right after `after` (if that tab exists, else last); keeps every other tab in order."""
    wb = pkg.text("xl/workbook.xml")
    tags = re.findall(r"<sheet\b[^>]*/>", wb)
    me = [t for t in tags if f'name="{esc(name)}"' in t][0]
    rest = [t for t in tags if t is not me]
    i = next((k for k, t in enumerate(rest) if f'name="{esc(after)}"' in t), len(rest) - 1)
    order = rest[:i + 1] + [me] + rest[i + 1:]
    body = re.search(r"<sheets>(.*?)</sheets>", wb, re.S)
    wb = wb[:body.start(1)] + "".join(order) + wb[body.end(1):]
    new_pos = {tags.index(t): k for k, t in enumerate(order)}      # old tab index -> new tab index
    wb = re.sub(r'(<definedName\b[^>]*?localSheetId=")(\d+)(")',
                lambda m: f"{m.group(1)}{new_pos.get(int(m.group(2)), int(m.group(2)))}{m.group(3)}", wb)
    pkg.put("xl/workbook.xml", wb)


def main():
    ap = argparse.ArgumentParser()
    for a in ("model", "ctx", "solved", "out", "written"):
        ap.add_argument(f"--{a}", required=True)
    a = ap.parse_args()
    if os.path.abspath(a.out) == os.path.abspath(a.model):
        raise SystemExit("model-dcf: --out must be a copy, not the model itself.")
    L = build(a.model, json.load(open(a.ctx)), json.load(open(a.solved)), a.out, a.written)
    print(json.dumps({"wrote": a.out, "tab": TAB, "value_per_share": L["value_per_share"],
                      "rows": L["rows"], "year_cols": L["year_cols"]}, indent=1))


if __name__ == "__main__":
    main()
