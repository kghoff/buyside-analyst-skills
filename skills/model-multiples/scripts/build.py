"""Writes the Multiples tab (spec §3.3) into a copy of the user's model through raw-XML editing (xlsx.py). Every
other part of the workbook stays byte-identical. Live formulas: typed numbers blue with a source note on their column
header, formulas black, links to other tabs green. Records in WORK/layout.json the value every checked cell must
recalculate to (engine.py's numbers), for verify.py.

usage: python3 build.py --model M --work W --ticker T --out OUT"""
import argparse
import datetime as dt
import json
import math
import os
import re

import openpyxl

import comps as C
import engine as E
import importer
import lo
import peers as P
import sp500
import subject as S
from charts import line, scatter
from build_parts import NROWS, ROW0
from modmap import ModMap
from xlsx import Package, Sheet, Styles, colname

TAB = "Multiples"
BLUE, BLACK, GREEN = "FF0000FF", "FF000000", "FF008000"
X, PCT, MILL, MONEY, DATE = '0.0"x"', "0.0%", "#,##0", "$#,##0.00", "yyyy-mm-dd"
RAWM = '#,##0,,'                                   # raw dollars shown in millions; the typed value is unchanged
LABELS = {"pe": "P/E", "ev_ebitda": "EV/EBITDA", "ev_gp": "EV/GP", "ev_rev": "EV/Revenue", "fcf_yield": "FCF yield",
          "fcf_yield_ntm": "FCF yield (NTM)", "rel_sp": "P/E − S&P 500 P/E", "rel_peer": "P/E − core-peer median"}
WLAB = {52: "1 year", 260: "5 years", 520: "10 years"}
YELLOW = "FFFFFF99"                                # the user's input cells, the same yellow as the Valuation tab
INC_HEAD, FIT_HEAD = "Include? (1 = yes, 0 = leave out)", "P/E FY1 on the line"


def read_includes(model):
    """{ticker: 0 | 1} from the existing tab's Include? column, so a rerun keeps the user's toggles. Code only ever
    writes 1, so whatever is there is the default or the user's. Anything but 0 or 1 is read as 1, with a warning."""
    wb = openpyxl.load_workbook(model, read_only=True)
    if TAB not in wb.sheetnames:
        wb.close()
        return {}, []
    inc, warns, on = {}, [], False
    for row in wb[TAB].iter_rows(max_col=20, values_only=True):
        a, t = row[0], row[19] if len(row) > 19 else None
        if not on:
            on = a == "Ticker" and t == INC_HEAD
            continue
        if a is None or str(a).startswith(("Average", "Median")):
            break
        if t in (0, 1) and not isinstance(t, bool):
            inc[a] = int(t)
        else:
            inc[a] = 1
            warns.append(f"{a}: its Include? cell held {t!r}, not 0 or 1, so it is included; type 0 to leave it out.")
    wb.close()
    return inc, warns


def labels(mode):
    """Free path: the relative rows are GAAP P/E (multpl's S&P and the peers' XBRL EPS are reported earnings). Paid:
    they stay NTM vs NTM, and the export's trailing FCF is LTM."""
    lab = dict(LABELS)
    if mode == "free":
        lab.update(rel_sp="GAAP P/E − S&P 500 P/E", rel_peer="GAAP P/E − core-peer median")
    else:
        lab["fcf_yield"] = "FCF yield (LTM)"
    return lab


def serial(d):
    return (d - dt.date(1899, 12, 30)).days


def na(f):
    return f"IFERROR({f},NA())"


class W:
    """Cell writer that remembers styles, what is typed / linked / formula, and the expected values."""

    def __init__(self, st):
        self.sh, self.st = Sheet(), st
        self.s = {}
        self.typed, self.links, self.formulas, self.expected, self.inputs = [], [], [], {}, []

    def style(self, color=BLACK, fmt="General", b=False, i=False, fill=None, sz=11):
        k = (color, fmt, b, i, fill, sz)
        if k not in self.s:
            self.s[k] = self.st.xf(color=color, fmt=fmt, b=b, i=i, fill=fill, sz=sz)
        return self.s[k]

    def text(self, ref, t, **kw):
        self.sh.set(ref, "s", t, self.style(**kw))

    def typed_(self, ref, v, fmt, kind="n"):
        if v is None:                     # no number to type: NA() is a formula, not a typed number, so black
            self.sh.set(ref, "f", "NA()", self.style(BLACK, fmt))
            self.formulas.append(ref)
        else:
            self.sh.set(ref, kind, v, self.style(BLUE, fmt))
            self.typed.append(ref)

    def link(self, ref, f, fmt, expect=None, check=True):
        self.sh.set(ref, "f", f, self.style(GREEN, fmt))
        self.links.append(ref)
        if check:
            self.expected[ref] = expect

    def formula(self, ref, f, fmt, expect=None, check=True, b=False, kind="f"):
        self.sh.set(ref, kind, f, self.style(BLACK, fmt, b=b))
        self.formulas.append(ref)
        if check:
            self.expected[ref] = expect


def load_inputs(model, work, ticker):
    cfg = json.load(open(os.path.join(work, "comps.json")))
    mode = json.load(open(os.path.join(work, "mode.json")))["mode"]
    snaps = {}
    for t in [ticker] + [c["ticker"] for c in cfg["comps"]]:
        p = os.path.join(work, "comps", f"{t}.json")
        snaps[t] = json.load(open(p)) if os.path.exists(p) else {"ticker": t, "error": "no snapshot file"}
    return cfg, mode, snaps


def paid_unit_check(path, subj, model, values):
    """The export must be in MOD's units (millions). Compares its latest NTM sales with MOD's last actual FY revenue,
    or, with no sales column, its market cap with its price × MOD's latest diluted shares. Off by more than 5x either
    way: SystemExit naming the likely unit. Returns warnings (a check it could not make)."""
    mm = ModMap(model)
    R = S.find_rows(mm)
    g = S.grid(values, max(R["rev"], R["shares"]) + 1)
    name = os.path.basename(path)

    def last(periods, row):
        return next((v for p in reversed(periods) if (v := S.num(g, row, mm.col(p))) is not None), None)

    sales = next((r["sales_ntm"] for r in reversed(subj) if r.get("sales_ntm") is not None), None)
    if sales is not None:
        x, y = sales, last([p for p in mm.order if re.fullmatch(r"\d{4}", p)], R["rev"])
        what = ("sales", "revenue")
    else:
        r = next((r for r in reversed(subj) if r.get("mcap") is not None and r.get("price") is not None), None)
        sh = last([p for p in mm.order if mm.is_q(p) and not p.endswith("E")], R["shares"])
        x, y = (r["mcap"], r["price"] * sh) if r and sh is not None else (None, None)
        what = ("market cap", "price × diluted shares")
    if not x or not y or x <= 0 or y <= 0:
        return [f"{name}: no sales or market cap to compare with MOD, so the export's units were not checked. They "
                "must be millions, as MOD's."]
    ratio = x / y
    if 0.2 <= ratio <= 5:
        return []
    unit = {1: "thousands", 2: "dollars", -1: "billions"}.get(round(math.log10(ratio) / 3), "different units")
    raise SystemExit(f"{name}: the export's {what[0]} ({x:,.0f}) and MOD's {what[1]} ({y:,.0f}) differ by about "
                     f"{max(ratio, 1 / ratio):,.0f}x. The export looks like it's in {unit} while MOD is in millions. "
                     "Re-export in millions (or the same units as MOD) and rerun.")


def load_rows(model, work, cfg, mode, ticker, recalced):
    """(weekly rows, subject quarters, S&P rows, {core peer: TTM rows}, basis line, warnings) for either path."""
    warnings = []
    peer_q = {}
    if mode == "free":
        quarters, q_notes = S.quarters(model, recalced)     # (rows, plain-English notes): Task 4 review, 2026-11-17
        warnings += q_notes
        weeks = S.weekly(model)
        sp = sp500.get(work)
        peers = {}
        for t in cfg["core"]:
            f = cfg["files"][t]
            x = json.load(open(f["xbrl"]))
            q = P.ttm(P.eps_quarters(x))
            peer_q[t] = q
            # All quarters, gaps included: the sheet's MATCH lands on a gap row (TTM #N/A) too, so the engine must as well.
            peers[t] = {"closes": P.load_closes(f["prices"]), "ttm": q}
        rows = E.free_weekly(quarters, weeks, sp, peers)
        basis = ("Trailing (TTM) multiples as known on each date: a quarter counts from the day after its release "
                 "(Px Events); core peers from 45 / 90 days after quarter end. S&P 500: multpl.com trailing P/E.")
    else:
        files = cfg["files"]
        # ticker=: one export may hold several tickers (Task 8 review); load() keeps that ticker's rows.
        subj = importer.load(files[ticker]["export"], importer.mapping_for(files[ticker]["export"]), ticker=ticker)
        pr = {t: importer.load(files[t]["export"], importer.mapping_for(files[t]["export"]), ticker=t) for t in cfg["core"]}
        for t, rs in [(ticker, subj)] + list(pr.items()):
            if rs.skipped:
                warnings.append(f"{os.path.basename(files[t]['export'])}: {rs.skipped} row(s) with no readable date "
                                "were skipped.")
        warnings += paid_unit_check(files[ticker]["export"], subj, model, recalced)
        rows = E.paid_weekly(subj, pr)
        quarters, sp = [], []
        basis = "NTM consensus multiples from " + ", ".join(sorted({os.path.basename(f["export"]) for f in files.values()}))
        if all(r.get("sp500_pe") is None for r in subj):
            warnings.append("The export has no S&P 500 NTM P/E column, so the S&P-relative rows are #N/A.")
    return rows, quarters, sp, peer_q, basis, warnings


def build(model, work, ticker, out):
    cfg, mode, snaps = load_inputs(model, work, ticker)
    warnings = []
    values = os.path.join(work, "values")
    os.makedirs(values, exist_ok=True)
    recalced = lo.recalc(model, values)                # cached values of the user's formulas, never saved back
    st = Styles(Package(model).text("xl/styles.xml"))
    w = W(st)
    sh = w.sh
    LAB = labels(mode)
    # Non-GAAP history: a GAAP P/E column of its own for the relative rows. GAAP basis: the P/E column already is.
    ng = mode == "free" and S.eps_basis(model) == "ng"
    PG = "pe_gaap" if ng else "pe"

    rows, quarters, sp, peer_q, basis, notes_ = load_rows(model, work, cfg, mode, ticker, recalced)
    warnings += notes_
    kept = [r for r in rows if r.get("pe") is not None or r.get("ev_rev") is not None]
    if kept and len(kept) < len(rows):
        warnings.append(f"{len(rows) - len(kept)} week(s) with neither a P/E nor an EV/Revenue were left out "
                        "(no quarter known yet, or no data in the export).")
    rows = kept or rows
    inc, inc_warn = read_includes(model)
    warnings += inc_warn
    off = {t for t, v in inc.items() if v == 0}
    E.exclude_peers(rows, off & set(cfg["core"]), "pe_gaap" if mode == "free" else "pe")
    # Paid path: the sixth multiple, forward FCF yield, has a history (the export's NTM FCF); the free path has none.
    KEYS = E.KEYS + (("fcf_yield_ntm",) if mode == "paid" else ())
    rg = E.ranges(rows, keys=KEYS)
    rev = E.reverse(rows, rg)
    comp_rows = C.rank([C.row(snaps[ticker], "Subject")] +
                       [C.row(snaps[c["ticker"]], c.get("group", "")) for c in cfg["comps"]])
    warnings += [f"{r['ticker']}: {r['warning']}" for r in comp_rows if r["warning"]]
    for t in C.outliers(comp_rows, ticker):
        pe = next(r["pe1"] for r in comp_rows if r["ticker"] == t)
        warnings.append(f"{t}: next year's P/E ({pe:,.0f}x) is more than twice the peers' median, so it pulls the "
                        "averages, the line through the peers" + (" and the core-peer median" if t in cfg["core"] else "")
                        + (". It is left out (Include? = 0)." if t in off else
                           ". Type 0 in its Include? cell (column T of the comp sheet) to leave it out."))
    fit = C.line_fit(comp_rows, inc, ticker)

    try:
        d1, d2 = dt.date.fromisoformat(str(rows[-1]["date"])[:10]), dt.date.fromisoformat(str(snaps[ticker]["asof"])[:10])
        if (d2 - d1).days > 7:
            warnings.append(f"Px Data ends {d1} but comp prices are {d2}: the history and forward blocks use the {d1} price "
                            f"(${rows[-1]['price']:,.2f}), the comp sheet ${snaps[ticker]['price']:,.2f}. Rerun "
                            "/model-price-history to refresh Px Data.")
    except (ValueError, TypeError, KeyError):
        pass
    # ---------------------------------------------------------------- layout: data blocks at the bottom
    R_RANGE = 5
    R_FWD = R_RANGE + len(KEYS) + 8
    R_COMP = R_FWD + 16
    # The data blocks run wider than column V, so they start below the charts (up to 8 charts free, 9 paid; two across).
    R_DATA = max(R_COMP + len(comp_rows) + 16, ROW0 + -(-(10 if mode == "paid" else 9) // 2) * (NROWS + 1) + 3)
    C0 = R_COMP + 2
    CN = C0 + len(comp_rows) - 1
    inc_ref = {r["ticker"]: f"$T${C0 + i}" for i, r in enumerate(comp_rows)}
    for t in cfg["core"]:
        if t not in inc_ref:
            warnings.append(f"Core peer {t} is not on the comp sheet, so it has no Include? toggle.")
    W0, WN = R_DATA + 2, R_DATA + 1 + len(rows)

    col = {}
    c = 1

    def take(*names):
        nonlocal c
        for n in names:
            col[n] = colname(c)
            c += 1
        c += 1

    base = ["date", "price", "q", "rev", "gp", "ebitda", "eps", *(["eps_gaap"] if ng else []), "fcf", "shares",
            "net_debt"] if mode == "free" else \
        ["date", "price", "eps", "rev", "gp", "ebitda", "fcf", "fcf_ntm", "shares", "net_debt"]
    take(*base, "mcap", "ev", "ev_rev", "ev_gp", "ev_ebitda", "pe", *(["pe_gaap"] if ng else []), "fcf_yield",
         *(["fcf_yield_ntm"] if mode == "paid" else []), "sp_pe", "rel_sp",
         *[f"px_{t}" for t in cfg["core"]], *([f"eps_{t}" for t in cfg["core"]] if mode == "paid" else []),
         *[f"pe_{t}" for t in cfg["core"]], "peer_med", "rel_peer")
    if mode == "free":
        take("q_label", "q_date", "q_rev", "q_gp", "q_ebitda", "q_eps", *(["q_eps_gaap"] if ng else []), "q_fcf",
             "q_shares", "q_nd")
        take("sp_date", "sp_val", "sp_est")
        for t in cfg["core"]:
            take(f"{t}_end", f"{t}_known", f"{t}_eps", f"{t}_ttm")
    L = col
    rng = lambda k, r0, r1: f"${L[k]}${r0}:${L[k]}${r1}"

    w.text("A1", f"{ticker} multiples: where the stock trades against its history, the market and its peers",
           b=True, sz=14)
    w.text("A2", basis, i=True, color="FF595959")
    w.text("A3", "Blue = typed from the source named in the column note. Black = formulas. Green = links to MOD, "
                 "Px Data and Px Events. #N/A = not meaningful (a negative or missing denominator).", i=True,
           color="FF595959")

    # ---------------------------------------------------------------- weekly block
    hdr = {"date": "Week", "price": "Price", "q": "Quarter # known", "rev": "Revenue", "gp": "Gross profit",
           "ebitda": "EBITDA", "eps": "EPS", "eps_gaap": "EPS (GAAP)", "pe_gaap": "P/E (GAAP)", "fcf": "FCF", "fcf_ntm": "NTM FCF", "shares": "Diluted shares",
           "net_debt": "Net debt", "mcap": "Market cap", "ev": "EV", "ev_rev": "EV/Revenue", "ev_gp": "EV/GP",
           "ev_ebitda": "EV/EBITDA", "pe": "P/E", "fcf_yield": LAB["fcf_yield"], "fcf_yield_ntm": "NTM FCF yield",
           "sp_pe": "S&P 500 P/E",
           "rel_sp": LAB["rel_sp"], "peer_med": "Core-peer median P/E", "rel_peer": LAB["rel_peer"]}
    for t in cfg["core"]:
        hdr[f"px_{t}"], hdr[f"eps_{t}"], hdr[f"pe_{t}"] = f"{t} close", f"{t} NTM EPS", f"{t} P/E"
    w.text(f"A{R_DATA}", "WEEKLY DATA", b=True)
    for k, h in hdr.items():
        if k in L:
            w.text(f"{L[k]}{R_DATA + 1}", h, b=True, fill="FFDDEBF7")
    notes = {}
    if mode == "free":
        Q0, QN = W0, W0 + len(quarters) - 1
        SP0, SPN = W0, W0 + len(sp) - 1
        QR = lambda k: rng(k, Q0, QN)
        for i, r in enumerate(rows):
            n = W0 + i
            w.link(f"{L['date']}{n}", f"'Px Data'!$A${r['pxrow']}", DATE, serial(r["date"]))
            w.link(f"{L['price']}{n}", f"'Px Data'!${r['pxcol']}${r['pxrow']}", MONEY, r["price"])
            w.formula(f"{L['q']}{n}", na(f"MATCH({L['date']}{n}-1,{QR('q_date')},1)"), "0",
                      r["q"] + 1 if r["q"] is not None else None)
            for k in ("rev", "gp", "ebitda", "eps", *(["eps_gaap"] if ng else []), "fcf", "shares", "net_debt"):
                w.formula(f"{L[k]}{n}", na(f"INDEX({QR('q_' + {'net_debt': 'nd'}.get(k, k))},"
                                           f"{L['q']}{n})"), MONEY if k.startswith("eps") else MILL, r[k])
            w.formula(f"{L['sp_pe']}{n}", na(f"INDEX({rng('sp_val', SP0, SPN)},MATCH({L['date']}{n},"
                                             f"{rng('sp_date', SP0, SPN)},1))"), X, r["sp_pe"])
        notes[f"{L['date']}{R_DATA + 1}"] = "Last trading day of each week, linked to Px Data (model-price-history)."
        notes[f"{L['q']}{R_DATA + 1}"] = ("Which row of the quarter block is known that week: MATCH(week − 1, release "
                                          "dates). A quarter counts from the day after its full-results release.")
        notes[f"{L[PG]}{R_DATA + 1}"] = ("The relative columns use the GAAP P/E: the S&P 500 P/E (multpl) and the core "
                                         "peers' XBRL EPS are reported (GAAP) earnings, so GAAP is compared with GAAP.")
    else:
        for i, r in enumerate(rows):
            n = W0 + i
            w.typed_(f"{L['date']}{n}", serial(r["date"]), DATE, "d")
            for k, src in (("price", "price"), ("eps", "eps_ntm"), ("rev", "sales_ntm"), ("gp", "gp_ntm"),
                           ("ebitda", "ebitda_ntm"), ("fcf", "fcf_ltm"), ("fcf_ntm", "fcf_ntm")):
                w.typed_(f"{L[k]}{n}", r.get(src), MONEY if k in ("price", "eps") else MILL)
            w.typed_(f"{L['mcap']}{n}", r.get("mcap"), MILL)
            w.typed_(f"{L['ev']}{n}", r.get("ev"), MILL)
            w.typed_(f"{L['sp_pe']}{n}", r.get("sp500_pe"), X)
            for k in ("shares", "net_debt"):
                w.text(f"{L[k]}{n}", "")
        for k in ("price", "eps", "rev", "gp", "ebitda", "fcf", "fcf_ntm", "mcap", "ev", "sp_pe"):
            notes[f"{L[k]}{R_DATA + 1}"] = f"Typed from the export ({os.path.basename(cfg['files'][ticker]['export'])})."
    for i, r in enumerate(rows):
        n = W0 + i
        g = lambda k: f"{L[k]}{n}"
        if mode == "free":
            w.formula(g("mcap"), na(f"{g('price')}*{g('shares')}"), MILL, r["mcap"])
            w.formula(g("ev"), na(f"{g('mcap')}+{g('net_debt')}"), MILL, r["ev"])
        for k, num, den in (("ev_rev", "ev", "rev"), ("ev_gp", "ev", "gp"), ("ev_ebitda", "ev", "ebitda"),
                            ("pe", "price", "eps")):
            w.formula(g(k), na(f"IF({g(den)}>0,{g(num)}/{g(den)},NA())"), X, r[k])
        if ng:
            w.formula(g("pe_gaap"), na(f"IF({g('eps_gaap')}>0,{g('price')}/{g('eps_gaap')},NA())"), X, r["pe_gaap"])
        w.formula(g("fcf_yield"), na(f"IF({g('mcap')}>0,{g('fcf')}/{g('mcap')},NA())"), PCT, r["fcf_yield"])
        if mode == "paid":
            w.formula(g("fcf_yield_ntm"), na(f"IF({g('mcap')}>0,{g('fcf_ntm')}/{g('mcap')},NA())"), PCT,
                      r["fcf_yield_ntm"])
        w.formula(g("rel_sp"), na(f"{g(PG)}-{g('sp_pe')}"), X, r["rel_sp"])
        for t in cfg["core"]:
            w.typed_(g(f"px_{t}"), r["peer_px"].get(t), MONEY)
            if mode == "free":
                K, T = rng(f"{t}_known", W0, W0 + len(peer_q[t]) - 1), rng(f"{t}_ttm", W0, W0 + len(peer_q[t]) - 1)
                e = f"INDEX({T},MATCH({g('date')},{K},1))"
            else:
                e = g(f"eps_{t}")
                w.typed_(e, r["peer_eps"].get(t), MONEY)
            f = f"IF({e}>0,{g(f'px_{t}')}/{e},NA())"
            if t in inc_ref:                  # the user's Include? toggle on the comp sheet
                f = f"IF({inc_ref[t]}=1,{f},NA())"
            w.formula(g(f"pe_{t}"), na(f), X, r["peer_pe"].get(t))
        if cfg["core"]:
            pr = f"{L['pe_' + cfg['core'][0]]}{n}:{L['pe_' + cfg['core'][-1]]}{n}"
            w.formula(g("peer_med"), na(f"_xlfn.AGGREGATE(12,6,{pr})"), X, r["peer_med"])
        w.formula(g("rel_peer"), na(f"{g(PG)}-{g('peer_med')}") if cfg["core"] else "NA()", X, r["rel_peer"])
    for t in cfg["core"]:
        notes[f"{L['px_' + t]}{R_DATA + 1}"] = (f"{t} close on or before the week (stooq daily file "
                                                f"{os.path.basename(cfg['files'][t].get('prices', ''))})."
                                                if mode == "free" else "Typed from the peer's export.")
        if mode == "paid":
            notes[f"{L['eps_' + t]}{R_DATA + 1}"] = (f"Typed from {os.path.basename(cfg['files'][t]['export'])} (NTM "
                                                     "EPS column). The P/E beside it is price ÷ this EPS.")

    # ---------------------------------------------------------------- quarter, S&P and peer blocks (free path)
    if mode == "free":
        for k, h in (("q_label", "Quarter"), ("q_date", "Release date"), ("q_rev", "TTM revenue"),
                     ("q_gp", "TTM gross profit"), ("q_ebitda", "TTM EBITDA"), ("q_eps", "TTM EPS"),
                     *([("q_eps_gaap", "TTM EPS (GAAP)")] if ng else []),
                     ("q_fcf", "TTM FCF"), ("q_shares", "Diluted shares"), ("q_nd", "Net debt"),
                     ("sp_date", "Month"), ("sp_val", "S&P 500 P/E (trailing)"), ("sp_est", "multpl estimate?")):
            w.text(f"{L[k]}{R_DATA + 1}", h, b=True, fill="FFDDEBF7")
        for i, q in enumerate(quarters):
            n = W0 + i
            w.text(f"{L['q_label']}{n}", q["label"])
            w.link(f"{L['q_date']}{n}", f"'Px Events'!$B${q['pxe_row']}", DATE, serial(q["date"]))
            for k, src in (("q_rev", "rev"), ("q_gp", "gp"), ("q_ebitda", "ebitda"), ("q_eps", "eps"),
                           *([("q_eps_gaap", "eps_gaap")] if ng else []), ("q_fcf", "fcf"),
                           ("q_shares", "shares"), ("q_nd", "net_debt")):
                f_ = q[src][1]
                if src == "shares":          # a bare MOD ref: blank is 0 in Excel but None in Python (Task 4 review)
                    f_ = f"IF(ISNUMBER({f_}),{f_},NA())"
                w.link(f"{L[k]}{n}", na(f_), MONEY if k.startswith("q_eps") else MILL, q[src][0])
        notes[f"{L['q_rev']}{R_DATA + 1}"] = "Sum of the last four reported quarters in MOD (live formulas)."
        notes[f"{L['q_nd']}{R_DATA + 1}"] = ("Every debt-like liability row − cash − short-term investments at the "
                                             "quarter end. Operating leases are not debt.")
        for i, s in enumerate(sp):
            n = W0 + i
            w.typed_(f"{L['sp_date']}{n}", serial(s["date"]), DATE, "d")
            w.typed_(f"{L['sp_val']}{n}", s["pe"], X)
            w.text(f"{L['sp_est']}{n}", "estimate" if s["estimate"] else "")
        notes[f"{L['sp_val']}{R_DATA + 1}"] = f"Typed from {sp500.URL} (monthly, trailing); fetched {dt.date.today()}."
        for t in cfg["core"]:
            for k, h in (("end", "Quarter end"), ("known", "Known from"), ("eps", "Diluted EPS (qtr)"),
                         ("ttm", "TTM EPS")):
                w.text(f"{L[f'{t}_{k}']}{R_DATA + 1}", f"{t} {h}", b=True, fill="FFDDEBF7")
            for i, q in enumerate(peer_q[t]):
                n = W0 + i
                w.typed_(f"{L[f'{t}_end']}{n}", serial(q["end"]), DATE, "d")
                w.formula(f"{L[f'{t}_known']}{n}", f"{L[f'{t}_end']}{n}+{P.LAG[q['q']]}", DATE, serial(q["known"]))
                w.typed_(f"{L[f'{t}_eps']}{n}", q["eps"], MONEY)
                f = f"SUM({L[f'{t}_eps']}{n - 3}:{L[f'{t}_eps']}{n})" if q["consecutive"] else "NA()"
                w.formula(f"{L[f'{t}_ttm']}{n}", f, MONEY, q["ttm"])
            notes[f"{L[f'{t}_eps']}{R_DATA + 1}"] = (f"Typed from edgar-xbrl-financials ({os.path.basename(cfg['files'][t]['xbrl'])}"
                                                     "), tag diluted_earnings_per_share.")
            notes[f"{L[f'{t}_end']}{R_DATA + 1}"] = ("Quarter end derived from edgar-xbrl-financials ttm.endDate, "
                                                     "stepping back three months a quarter.")
            notes[f"{L[f'{t}_known']}{R_DATA + 1}"] = "Quarter end + 45 days (Q1-Q3) or 90 days (Q4): the latest SEC filing deadlines."

    # ---------------------------------------------------------------- RANGES and reverse P/E
    last_wk = rows[-1]["date"]
    w.text(f"A{R_RANGE}", f"RANGES (as of {last_wk}, the last weekly close in Px Data)", b=True)
    w.text(f"A{R_RANGE + 1}", "Metric", b=True, fill="FFDDEBF7")
    w.text(f"B{R_RANGE + 1}", "Today", b=True, fill="FFDDEBF7")
    cc = 3
    for n_ in E.WINDOWS:
        for s_ in ("min", "median", "max", "pct"):
            w.text(f"{colname(cc)}{R_RANGE + 1}", f"{WLAB[n_]} {s_ if s_ != 'pct' else 'percentile'}", b=True,
                   fill="FFDDEBF7")
            cc += 1
    for i, k in enumerate(KEYS):
        rr = R_RANGE + 2 + i
        fmt = PCT if k.startswith("fcf_yield") else X
        w.text(f"A{rr}", LAB[k])
        w.formula(f"B{rr}", na(f"{L[k]}{WN}"), fmt, rows[-1].get(k))
        cc = 3
        for n_ in E.WINDOWS:
            R = rng(k, max(W0, WN - n_ + 1), WN)
            stt = rg[k][n_]
            for s_, f in (("min", f"_xlfn.AGGREGATE(5,6,{R})"), ("median", f"_xlfn.AGGREGATE(12,6,{R})"),
                          ("max", f"_xlfn.AGGREGATE(4,6,{R})"),
                          # Not COUNTIF(R,"<="&today): that turns today into 15-digit text and can miscount today
                          # itself. A legacy array formula (kind "fa") compares numbers and evaluates IFERROR over the
                          # array in every Excel version and LibreOffice; IFERROR drops #N/A rows. NM today: #N/A, as
                          # window_stats (pct None), not 0.
                          ("pct", f"IF(ISNUMBER({L[k]}{WN}),SUM(IFERROR(({R}<={L[k]}{WN})*1,0))/COUNT({R}),NA())")):
                w.formula(f"{colname(cc)}{rr}", na(f), PCT if s_ == "pct" else fmt, stt[s_] if stt else None,
                          kind="fa" if s_ == "pct" else "f")
                cc += 1
    rr = R_RANGE + 2 + len(KEYS) + 1
    w.text(f"A{rr}", "Implied earnings power (today's price ÷ P/E)", b=True)
    cc = 3
    for n_ in E.WINDOWS:
        for j, s_ in enumerate(("min", "median", "max")):
            src = f"{colname(3 + 4 * E.WINDOWS.index(n_) + j)}{R_RANGE + 2}"
            w.formula(f"{colname(cc)}{rr}", na(f"{L['price']}{WN}/{src}"), MONEY, rev[n_][s_] if rev[n_] else None)
            cc += 1
        cc += 1
    notes[f"A{rr}"] = ("The chapter's reverse P/E: the earnings power the market implies if the stock traded at that "
                       "P/E. Above your earnings-power view = cheap; below = caution.")

    # ---------------------------------------------------------------- FORWARD
    mm = ModMap(model)
    Rw = S.find_rows(mm)
    eps_row = Rw["eps_ng"] if S.eps_basis(model) == "ng" and "eps_ng" in Rw else Rw["eps_gaap"]
    g = S.grid(recalced, max(v for k, v in Rw.items() if k != "debt") + 5)
    yrs = mm.forecast_years()[:5]
    w.text(f"A{R_FWD}", f"FORWARD (price and EV as of {last_wk}, the last weekly close in Px Data, on each forecast year)", b=True)
    w.text(f"A{R_FWD + 1}", "", b=True, fill="FFDDEBF7")
    for j, y in enumerate(yrs):
        w.text(f"{colname(2 + j)}{R_FWD + 1}", y, b=True, fill="FFDDEBF7")
    ebitda_ng = S.eps_basis(model) == "ng" and "ebitda_ng" in Rw
    lines = [("Revenue", [Rw["rev"]]), ("Gross profit", [Rw["gp"]]),
             ("EBITDA", [Rw["ebitda_ng"]] if ebitda_ng else [Rw["oi"], Rw["da"]]), ("EPS", [eps_row]), ("FCF", [Rw["fcf"]])]
    fv = {}
    for i, (lab, rows_) in enumerate(lines):
        rr = R_FWD + 2 + i
        w.text(f"A{rr}", lab)
        for j, y in enumerate(yrs):
            vals = [S.num(g, r_, mm.col(y)) for r_ in rows_]
            v = sum(vals) if all(x is not None for x in vals) else None
            fv[(lab, y)] = v
            refs = [f"MOD!${mm.col(y)}${r_}" for r_ in rows_]
            # a blank MOD cell is 0 in Excel but None in Python: COUNT-guard it, as subject.quarters does
            w.link(f"{colname(2 + j)}{rr}", na(f"IF(COUNT({','.join(refs)})={len(refs)},{'+'.join(refs)},NA())"),
                   MONEY if lab == "EPS" else MILL, v)
    last = rows[-1]
    for i, (lab, num, den, fmt) in enumerate((("EV/Revenue", "ev", "Revenue", X), ("EV/GP", "ev", "Gross profit", X),
                                              ("EV/EBITDA", "ev", "EBITDA", X), ("P/E", "price", "EPS", X),
                                              ("FCF yield", "mcap", "FCF", PCT))):
        rr = R_FWD + 8 + i
        w.text(f"A{rr}", lab)
        for j, y in enumerate(yrs):
            den_ref = f"{colname(2 + j)}{R_FWD + 2 + [l for l, _ in lines].index(den)}"
            top = f"{L[num]}{WN}"
            if lab == "FCF yield":
                f, v = f"IF({top}>0,{den_ref}/{top},NA())", (fv[(den, y)] / last["mcap"]
                                                             if last.get("mcap") and fv[(den, y)] is not None else None)
            else:
                d_ = fv[(den, y)]
                f, v = f"IF({den_ref}>0,{top}/{den_ref},NA())", (last[num] / d_ if d_ and d_ > 0 and last.get(num)
                                                                 is not None else None)
            w.formula(f"{colname(2 + j)}{rr}", na(f), fmt, v)
    subj = next(r for r in comp_rows if r["ticker"] == ticker)
    for i, (lab, key) in enumerate((("Street EPS (Yahoo consensus, analysts' basis)", "eps"), ("Street P/E", "pe"))):
        rr = R_FWD + 14 + i
        w.text(f"A{rr}", lab)
        if key == "eps":
            notes[f"A{rr}"] = ("Analysts' EPS is usually adjusted (non-GAAP), so it may not match the model's EPS above "
                               "when that is GAAP. Years are matched by name: Yahoo's endDate year = MOD's fiscal-year "
                               "label, both named by the year the fiscal year ends.")
        for j, y in enumerate(yrs):
            yi = int(y.rstrip("E"))
            hit = "0" if subj.get("fy0") == yi else ("1" if subj.get("fy1") == yi else None)
            if hit is None:
                continue
            ref = f"{colname(2 + j)}{rr}"
            if key == "eps":
                w.typed_(ref, subj[f"eps{hit}"], MONEY)
                notes[ref] = f"Yahoo earningsTrend {'0y' if hit == '0' else '+1y'} average, {subj['asof']}."
            else:
                eref = f"{colname(2 + j)}{rr - 1}"
                w.formula(ref, na(f"IF({eref}>0,{L['price']}{WN}/{eref},NA())"), X, subj[f"pe{hit}"] and
                          last["price"] / subj[f"eps{hit}"])

    # ---------------------------------------------------------------- COMPS
    heads = ["Ticker", "Group", "Price", "Market cap ($M)", "Total debt ($M)", "Cash ($M)", "EV ($M)", "3M ADV (shares, M)",
             "Revenue FY0 ($M)", "Revenue FY1 ($M)", "EPS FY0", "EPS FY1", "EBITDA TTM ($M)", "EV/Rev FY0",
             "EV/Rev FY1", "P/E FY0", "P/E FY1", "EV/EBITDA TTM", "Revenue growth FY1"]
    w.text(f"A{R_COMP}", "COMPS (ranked by next year's P/E; Yahoo Finance, " + str(subj.get("asof")) + ")", b=True)
    for j, h in enumerate(heads):
        w.text(f"{colname(1 + j)}{R_COMP + 1}", h, b=True, fill="FFDDEBF7")
    notes[f"C{R_COMP + 1}"] = ("Typed from Yahoo Finance quoteSummary (price, financialData, earningsTrend) saved in "
                               "_model_work/model-multiples/comps/<ticker>.json. Dollar figures are shown in millions "
                               "by number format; the typed values are Yahoo's.")
    w.text(f"T{R_COMP + 1}", INC_HEAD, b=True, fill="FFDDEBF7")
    w.text(f"U{R_COMP + 1}", FIT_HEAD, b=True, fill="FFDDEBF7")
    notes[f"T{R_COMP + 1}"] = ("Yours to change: 1 = in the averages, the medians, the line through the peers and (for a "
                               "core peer) the weekly core-peer median; 0 = left out. A rerun keeps what you typed. "
                               "Excel recalculates the charts and the line when you flip it.")
    notes[f"U{R_COMP + 1}"] = ("The peer's next-year P/E when it is included and has a revenue growth; #N/A otherwise "
                               "(and always for the subject, which is plotted on its own). The scatter and the line "
                               "read this column.")
    for i, r in enumerate(comp_rows):
        n = C0 + i
        A = lambda j: f"{colname(j)}{n}"
        w.text(A(1), r["ticker"], b=r["ticker"] == ticker, color=BLACK)
        w.text(A(2), r["group"] + (f" ({r['warning']})" if r["warning"] else ""))
        if r.get("price") is None:
            continue
        for j, k, fmt in ((3, "price", MONEY), (4, "mcap", RAWM), (5, "debt", RAWM), (6, "cash", RAWM),
                          (9, "rev0", RAWM), (10, "rev1", RAWM), (11, "eps0", MONEY), (12, "eps1", MONEY),
                          (13, "ebitda", RAWM)):
            w.typed_(A(j), r.get(k), fmt)
        w.typed_(A(8), r.get("adv"), RAWM)          # Yahoo's 3-month average daily volume, in shares
        w.formula(A(7), na(f"{A(4)}+{A(5)}-{A(6)}"), RAWM, r["ev"])
        ok = not r.get("ccy_mismatch")      # soft warnings (missing debt / currency) keep EV multiples (Task 7 review)
        for j, num, den, key in ((14, 7, 9, "ev_rev0"), (15, 7, 10, "ev_rev1"), (16, 3, 11, "pe0"), (17, 3, 12, "pe1"),
                                 (18, 7, 13, "ev_ebitda")):
            f = f"IF({A(den)}>0,{A(num)}/{A(den)},NA())" if ok or key.startswith("pe") else "NA()"
            w.formula(A(j), na(f), X, r[key])
        w.formula(A(19), na(f"{A(10)}/{A(9)}-1"), PCT, r["growth1"])
    for i, r in enumerate(comp_rows):     # after the `continue` above, so a failed fetch still gets its toggle
        n = C0 + i
        w.sh.set(f"T{n}", "n", inc.get(r["ticker"], 1), w.style(BLUE, "0", fill=YELLOW))
        w.inputs.append(f"T{n}")
        on_line = r["ticker"] != ticker and C.included(r, inc) and r.get("pe1") is not None \
            and r.get("growth1") is not None
        f = "NA()" if r["ticker"] == ticker else f"IF(AND(T{n}=1,ISNUMBER(Q{n}),ISNUMBER(S{n})),Q{n},NA())"
        w.formula(f"U{n}", na(f), X, r["pe1"] if on_line else None)
    stt = C.stats(comp_rows, inc)
    T_ = f"$T${C0}:$T${CN}"
    for i, (lab, fn) in enumerate((("Average", "AVERAGE"), ("Median", "MEDIAN"))):
        n = CN + 1 + i
        w.text(f"A{n}", lab + " (included rows)", b=True)
        for j, key in ((14, "ev_rev0"), (15, "ev_rev1"), (16, "pe0"), (17, "pe1"), (18, "ev_ebitda"), (19, "growth1")):
            R = f"${colname(j)}${C0}:${colname(j)}${CN}"
            # a legacy array formula, as the percentile column: IF drops the left-out and #N/A rows in Excel and LO
            w.formula(f"{colname(j)}{n}", na(f"{fn}(IF(({T_}=1)*ISNUMBER({R}),{R}))"),
                      PCT if key == "growth1" else X, stt["average" if fn == "AVERAGE" else "median"][key], b=True,
                      kind="fa")

    # ---------------------------------------------------------------- LINE through the peers (chapter 11)
    R0 = CN + 4
    U_, S_ = f"$U${C0}:$U${CN}", f"$S${C0}:$S${CN}"
    m = f"ISNUMBER({U_})"
    srow = C0 + next(i for i, r in enumerate(comp_rows) if r["ticker"] == ticker)
    w.text(f"A{R0}", "LINE THROUGH THE PEERS: next year's P/E on next year's revenue growth (reported, not organic). "
                     "Below the line = structurally underpriced on the multiple.", b=True)
    sums = {k: f"SUM(IF({m},{v},0))" for k, v in (("x", S_), ("y", U_), ("xy", f"{S_}*{U_}"), ("xx", f"{S_}^2"))}
    nB, slB, inB, fairB, peB, gapB = (f"$B${R0 + k}" for k in range(1, 7))
    for k, (lab, f, fmt, v, kind) in enumerate((
            ("Peers on the line (included, with both numbers)", f"SUM(IF({m},1,0))", "0", fit["n"], "fa"),
            ("Slope (P/E turns per 100% of growth)",
             na(f"IF({nB}>=2,({nB}*{sums['xy']}-{sums['x']}*{sums['y']})/({nB}*{sums['xx']}-{sums['x']}^2),NA())"),
             "0.0", fit["slope"], "fa"),
            ("Intercept (the line's P/E at 0% growth)", na(f"({sums['y']}-{slB}*{sums['x']})/{nB}"), X,
             fit["intercept"], "fa"),
            (f"P/E the line gives at {ticker}'s growth",
             na(f"IF(AND({nB}>=3,{slB}>0),{inB}+{slB}*$S${srow},NA())"), X, fit["fair_pe"], "f"),
            (f"{ticker}'s next-year P/E", f"$Q${srow}", X, next(r["pe1"] for r in comp_rows if r["ticker"] == ticker),
             "f"),
            (f"{ticker} − the line (turns; below 0 = under the line)", na(f"{peB}-{fairB}"), X, fit["gap"], "f"),
            (f"Growth the line implies at {ticker}'s P/E",
             na(f"IF(AND({nB}>=3,{slB}>0),({peB}-{inB})/{slB},NA())"), PCT, fit["implied_growth"], "f"),
            ("Reading", f'IF(ISNUMBER({gapB}),IF({gapB}<0,"{C.BELOW}","{C.ABOVE}"),"{C.SAYS_NOTHING}")', "General",
             fit["reading"], "f"))):
        w.text(f"A{R0 + 1 + k}", lab)
        w.formula(f"B{R0 + 1 + k}", f, fmt, v, kind=kind)
    notes[f"A{R0}"] = ("Chapter 11, applying P/E multiples: peers' multiples carry the market's expectation. Fit a "
                       "line of P/E on growth through the included peers; a name under it is paid less for its growth "
                       "than its peers are. Excel's trendline on the scatter is the same line. Under 3 peers or a line "
                       "that does not slope up gives no reading. Growth is Yahoo's reported revenue growth, not organic.")

    # ---------------------------------------------------------------- charts
    chart_list = chart_specs(ticker, mode, rows, comp_rows, C0, lambda k: f"'{TAB}'!{rng(k, W0, WN)}", warnings, LAB,
                             inc, PG, bool(cfg["core"]))

    sh.comments = notes
    sh.freeze = "B5"
    for j in range(1, max(20, c)):                 # every used column, so dates don't show as ###
        sh.widths[j] = 13
    sh.widths[1] = 34
    pkg = Package(model)
    # A workbook-wide name pointing at the old tab would dangle once it is replaced; xlsx.remove_sheet only drops
    # names scoped to the tab (localSheetId), so say so rather than edit the user's names.
    dangling = re.findall(rf'<definedName\b(?![^>]*localSheetId)[^>]*name="([^"]*)"[^>]*>[^<]*\'?{TAB}\'?!',
                          pkg.text("xl/workbook.xml"))
    if dangling:
        warnings.append(f"Workbook name(s) {', '.join(dangling)} refer to the old {TAB} tab and will show #REF! after "
                        "the rebuild; re-point or delete them.")
    if TAB in [n for n, *_ in pkg.sheets()]:
        pkg.remove_sheet(TAB)
    write_parts(pkg, st, sh, chart_list)
    pkg.save(out)
    import notebox
    notebox.fix(out, out, since=model)
    json.dump({"expected": w.expected, "typed": w.typed, "links": w.links, "formulas": w.formulas, "inputs": w.inputs,
               "weeks": len(rows),
               "W0": W0, "WN": WN}, open(os.path.join(work, "layout.json"), "w"), indent=0, default=str)
    return {"tab": TAB, "mode": mode, "weeks": len(rows), "first_week": rows[0]["date"].isoformat(),
            "comps": [{"ticker": r["ticker"], "pe1": r["pe1"]} for r in comp_rows], "core": cfg["core"],
            "ranges": {k: rg[k][260] for k in ("pe", "ev_ebitda", "rel_sp", "rel_peer")}, "reverse_pe_5y": rev[260],
            "left_out": sorted(off), "line": fit,
            "warnings": warnings}


def chart_specs(ticker, mode, rows, comp_rows, C0, ref, warnings, lab, inc=None, PG="pe", core=False):
    """Chart XML for the tab: one line chart per multiple (skipped, with a warning, when every week is NM) and the
    'looks like' scatter from the comp sheet. ref(k) = the absolute range of weekly column k."""
    cat = (ref("date"), [serial(r["date"]) for r in rows])
    ser = lambda k, name, color: {"name": name, "ref": ref(k), "vals": [r.get(k) for r in rows], "color": color}
    word = "NTM" if mode == "paid" else "TTM"
    chart_list = []
    for title, k, name, fmt in ((f"{ticker} P/E ({word})", "pe", "P/E", X),
                                (f"{ticker} {lab['rel_sp']}", "rel_sp", lab["rel_sp"], X),
                                (f"{ticker} {lab['rel_peer']}", "rel_peer", lab["rel_peer"], X),
                                ("PEER", None, None, None),
                                (f"{ticker} EV/EBITDA ({word})", "ev_ebitda", "EV/EBITDA", X),
                                (f"{ticker} EV/GP ({word})", "ev_gp", "EV/GP", X),
                                (f"{ticker} EV/Revenue ({word})", "ev_rev", "EV/Revenue", X),
                                (f"{ticker} {lab['fcf_yield']}", "fcf_yield", lab["fcf_yield"], PCT),
                                *([(f"{ticker} FCF yield (NTM)", "fcf_yield_ntm", "NTM FCF yield", PCT)]
                                  if mode == "paid" else [])):
        if title == "PEER":               # the subject's P/E beside the core-peer median: the history behind rel_peer
            if core and any(r.get("peer_med") is not None for r in rows):
                basis = "TTM, GAAP" if mode == "free" else "NTM"
                chart_list.append(line(f"{ticker} P/E vs core-peer median P/E ({basis})", cat,
                                       [ser(PG, f"{ticker} P/E", "C00000"), ser("peer_med", "Core-peer median", "1F4E79")], X))
            continue
        if any(r.get(k) is not None for r in rows):
            chart_list.append(line(title.replace("\u2212", "-"), cat, [ser(k, name, "1F4E79")], fmt))
        else:                         # every week NM: an empty chart says nothing, so skip it and say so
            warnings.append(f"No week has a {lab[k]} value, so the '{title}' chart is skipped.")
    inc = inc or {}
    # Peers read column U (#N/A when left out), so a toggled-off peer leaves the chart and the line; the subject reads Q.
    on = lambda r: r["ticker"] != ticker and C.included(r, inc) and r["pe1"] is not None and r["growth1"] is not None
    pts = [{"name": r["ticker"], "x": (f"'{TAB}'!$S${C0 + i}", r["growth1"]),
            "y": (f"'{TAB}'!${'Q' if r['ticker'] == ticker else 'U'}${C0 + i}",
                  r["pe1"] if r["ticker"] == ticker or on(r) else None),
            "subject": r["ticker"] == ticker} for i, r in enumerate(comp_rows) if r["pe1"] is not None
           and r["growth1"] is not None]
    CN = C0 + len(comp_rows) - 1
    fit = {"x": (f"'{TAB}'!$S${C0}:$S${CN}", [r["growth1"] for r in comp_rows]),
           "y": (f"'{TAB}'!$U${C0}:$U${CN}", [r["pe1"] if on(r) else None for r in comp_rows])}
    if pts:                           # charts.scatter raises on no points (Task 10 review): skip the chart, say so
        chart_list.append(scatter("Next-year P/E vs next-year revenue growth (reported, not organic): under the "
                                  "line = underpriced vs peers", pts, fit=fit))
    else:
        warnings.append("No comp has both a next-year P/E and revenue growth, so the 'looks like' scatter is skipped.")
    return chart_list


def write_parts(pkg, st, sh, chart_list):
    """Tab, drawing with one anchor per chart (two columns of charts from column V), comments. Same parts and
    relationships as model-consensus/scripts/build.py write_parts, extended to several charts."""
    from build_parts import write_parts as _w
    _w(pkg, st, sh, chart_list, TAB)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--ticker", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    print(json.dumps(build(a.model, a.work, a.ticker.upper(), a.out), indent=1, default=str))
