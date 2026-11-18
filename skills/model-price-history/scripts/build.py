"""Write the Px Data, Px Events and Idio Chart tabs into a copy of the user's model (raw XML; nothing else changes).

usage: python3 build.py --model M.xlsx --work W --out OUT.xlsx [--replace]
Reads W/price_history.json (the user's choices), W/events.json (reviewed event list) and W/prices.json (from prices.py).
Exit 2: the model already has one of the three tabs (rerun with --replace after the user says yes).
Exit 3: another tab has formulas pointing into the tabs --replace would delete (named in the output).
Every number lives in an Excel formula (so the user can click into it) except typed inputs: prices, dates, labels.
Layout (lean; the user 2026-11-08 dropped the orphaned columns): see `px_data_layout`."""
import argparse
import datetime as dt
import json
import math
import os
import re
import sys

import pandas as pd

import engine
import lo
import modmap
from xlsx import Package, Sheet, Styles, CT, colname, colnum, comments_parts, esc

TABS = ("Idio Chart", "Px Events", "Px Data")
ASSETS = os.path.join(os.path.dirname(__file__), "..", "assets")
BLUE, BLACK, GREEN, GREY, WHITE, NAVY, UP, DOWN = ("FF0000FF", "FF000000", "FF008000", "FF808080", "FFFFFFFF",
                                                   "FF002060", "FF00B050", "FFFF0000")
DATE, PCT2, PCT1, NUM2, EPS, PE, IDX, INT, MNY = ("yyyy\\-mm\\-dd", "0.00%", "0.0%", "0.00", "0.00_);\\(0.00\\)",
                                                  '0.0"x"', "0.0", "0", "#,##0.0")
OV_NAMES = {"rev_g": "TTM revenue growth (as reported)", "om": "TTM {b} op. margin", "em": "TTM {e} margin",
            "roic": "ROIC {r} (TTM)"}
OV_COLORS = {"rev_g": "ED7D31", "om": "1BAF7A", "em": "EDA100", "roic": "6250D6"}


def serial(d):
    return (pd.Timestamp(d) - pd.Timestamp("1899-12-30")).days


def isnum(x):
    return engine.isnum(x)


# ------------------------------------------------------------------ inputs
def prepare(model, work):
    """Everything build.py and verify.py both need: config, MOD map, engine run, layout."""
    C = json.load(open(os.path.join(work, "price_history.json")))
    E = json.load(open(os.path.join(work, "events.json")))
    P = json.load(open(os.path.join(work, "prices.json")))
    mod = modmap.read(model)
    need_roles = ["revenue", "fcf"]
    # A model saved by openpyxl (the earlier skills) has formulas with no cached results (e.g. every Q4 = FY - Q1-Q3):
    # if any reported quarter of revenue / EPS reads blank, read the values from a LibreOffice-recalculated copy.
    actual = [p["label"] for p in modmap.quarters(mod["periods"], actual_only=True)]
    if any(mod["values"].get(r, {}).get(q) is None for r in ("revenue", "eps_gaap") for q in actual):
        mod = modmap.read(model, lo.recalc(model, os.path.join(work, "_mod_values")))
    R = mod["rows"]
    ng = C.get("overlay_basis", "non-gaap") == "non-gaap"
    cfg = {"oi_role": "oi_ng" if ng else "oi_gaap",
           "ebitda_role": ("ebitda_ng" if ng else "ebitda_gaap") if C.get("ebitda") else None,
           "roic_role": C.get("roic_role", "roic"),
           "eps_role": "eps_ng" if "eps_ng" in R else "eps_gaap",
           "fcf_role": "fcf",
           "bb_roles": ["buyback_net"] if "buyback_net" in R else [r for r in ("buyback", "issuance") if r in R],
           "fye_month": int(C.get("fye_month", 12))}
    cfg["ttm_key"] = "ttm_n" if cfg["eps_role"] == "eps_ng" else "ttm_g"
    for role in need_roles + [cfg["oi_role"], cfg["roic_role"], cfg["eps_role"]] + \
            ([cfg["ebitda_role"]] if cfg["ebitda_role"] else []):
        if role not in R:
            raise SystemExit(f"MOD row not found for '{role}' (patterns: {modmap.ROLES[role]}). Rename the row or add a "
                             "pattern, then rerun.")
    if not cfg["bb_roles"]:
        raise SystemExit("No buyback / stock issuance row found in MOD.")
    actual = [p["label"] for p in modmap.quarters(mod["periods"], actual_only=True)]
    missing = [q for q in actual if q not in E["full"]]
    if missing:
        raise SystemExit(f"events.json has no full-results release date for {missing}. Add them (Step 2).")
    full = {q: pd.Timestamp(E["full"][q]["date"]) for q in actual}
    events = [{**e, "date": pd.Timestamp(e["date"])} for e in E["events"]]
    files = {k: P["files"][k]["path"] for k in ("stock", "spy", "etf", "mom")}
    prices = {k: engine.load_close(p) for k, p in files.items()}
    run = engine.run(cfg, prices, mod, full, events)
    return {"C": C, "E": E, "P": P, "mod": mod, "cfg": cfg, "run": run, "files": files,
            "tick": {k: P["files"][k]["ticker"].upper() for k in files}}


def px_data_layout(okeys):
    """Column letters for every Px Data block, left to right; each block sits next to what it feeds."""
    L, c = {}, 1

    def take(names):
        nonlocal c
        for n in names:
            L[n] = colname(c); c += 1
        c += 1                                                  # one empty column between blocks
    take(["date", "close", "spy", "ret", "spy_ret", "beta", "idio", "event"] + [f"ov_{k}" for k in okeys]
         + ["ttm_eps", "pe"])
    take(["m_date", "m_close", "m_pe", "m_ttm_eps"])
    take(["a_fy", "a_fcf", "a_bb", "a_pe", "a_n"])
    take(["f_etf", "f_mom", "f_spy_ret", "f_ind_x", "f_mom_x"])
    take(["w_date", "w_close", "w_spy", "w_etf", "w_mom", "w_ret", "w_spy_ret", "w_ind_x", "w_mom_x", "w_end",
          "w_b_mkt", "w_b_ind", "w_b_mom", "w_r2", "w_idio3", "w_idx3", "w_pct3"] + [f"w_ov_{k}" for k in okeys])
    return L


def px_events_layout(okeys):
    L = {k: v for k, v in zip(["period", "date", "eps_g", "eps_n", "fy_g", "fy_n", "ttm_g", "ttm_n"], "ABCDEFGH")}
    L.update(zip(["e_date", "e_type", "e_name", "e_timing", "e_react", "e_r", "e_rs", "e_beta", "e_idio", "e_note"],
                 "JKLMNOPQRS"))
    c = colnum("U")
    for k in ["ttm_rev"] + okeys:
        L[k] = colname(c); c += 1
    return L


# ------------------------------------------------------------------ the three tabs
def build(model, work, out, replace=False):
    S = prepare(model, work)
    C, E, mod, cfg, run, tick = S["C"], S["E"], S["mod"], S["cfg"], S["run"], S["tick"]
    T = C["ticker"].upper()
    ETF, MOM = tick["etf"], tick["mom"]
    ind = C.get("etf_label", "industry")
    okeys = run["okeys"]
    ng_ov = C.get("overlay_basis", "non-gaap") == "non-gaap"
    epsb = "non-GAAP" if cfg["eps_role"] == "eps_ng" else "GAAP"
    roic_lab = mod["rows"][cfg["roic_role"]]["label"]
    roic_word = "ex-cash" if "minus cash" in roic_lab.lower() or "ex" in cfg["roic_role"] else "asset-based"
    ov_name = {k: OV_NAMES[k].format(b="non-GAAP" if ng_ov else "GAAP", e="adj. EBITDA" if ng_ov else "EBITDA",
                                     r=roic_word) for k in okeys}

    pkg = Package(model)
    present = [n for n, *_ in pkg.sheets() if n in TABS]
    if present and not replace:
        print(json.dumps({"status": "exists", "tabs": present}))
        raise SystemExit(2)
    if present:
        refs = []
        for name, _, _, part in pkg.sheets():
            if name in TABS:
                continue
            x = pkg.text(part)
            for t in TABS:
                for m in re.finditer(rf"<c r=\"([A-Z]+\d+)\"[^>]*>(?:<f[^>]*>([^<]*'?{re.escape(t)}'?![^<]*)</f>)", x):
                    refs.append(f"{name}!{m.group(1)} -> {t}")
        if refs:
            print(json.dumps({"status": "referenced", "cells": refs[:50]}))
            raise SystemExit(3)
        for t in present:
            pkg.remove_sheet(t)

    st = Styles(pkg.text("xl/styles.xml"))
    S_ = lambda **k: st.xf(**k)
    sty = {"title": S_(b=True, sz=14), "title16": S_(b=True, sz=16), "note": S_(color=GREY, sz=10, i=True),
           "hdr": S_(color=WHITE, b=True, fill=NAVY, align="center"), "bold": S_(b=True),
           "in_date": S_(color=BLUE, fmt=DATE), "in_num": S_(color=BLUE, fmt=NUM2), "in_txt": S_(color=BLUE),
           "in_idx": S_(color=BLUE, fmt=IDX), "grey_pct2": S_(color=GREY, fmt=PCT2), "grey": S_(color=GREY),
           "date": S_(fmt=DATE), "pct2": S_(fmt=PCT2), "pct1": S_(fmt=PCT1), "num2": S_(fmt=NUM2), "eps": S_(fmt=EPS),
           "pe": S_(fmt=PE), "idx": S_(fmt=IDX), "int": S_(fmt=INT), "gen": S_(), "mny": S_(fmt=MNY),
           "g_eps": S_(color=GREEN, fmt=EPS), "g_pct1": S_(color=GREEN, fmt=PCT1), "g_idx": S_(color=GREEN, fmt=IDX),
           "up": S_(color=UP, fmt=PCT1), "down": S_(color=DOWN, fmt=PCT1)}
    dxf_grey = st.dxf_font("FFBFBFBF")

    dates, b = run["dates"], run["base"]
    n = len(dates)
    R0, RB = 5, 5 + b
    RS, RN = RB + 1, 4 + n
    DL = px_data_layout(okeys)
    EL = px_events_layout(okeys)
    rng = lambda key, r0=R0, r1=RN: f"${DL[key]}${r0}:${DL[key]}${r1}"
    A_ = rng("date")
    per = {p["label"]: p for p in mod["periods"]}
    qlabels = [p["label"] for p in modmap.quarters(mod["periods"])]
    Q = run["quarters"]
    Q0, QN = 5, 4 + len(Q)
    EVS = run["events"]
    EV0, EVN = 5, 4 + max(1, len(EVS))
    PXE = lambda key, r0, r1: f"'Px Events'!${EL[key]}${r0}:${EL[key]}${r1}"
    PXD = lambda key: f"'Px Data'!${DL[key]}${R0}:${DL[key]}${RN}"
    mrow = lambda role: mod["rows"][role]["row"]
    mref = lambda role, label: f"MOD!{per[label]['col']}{mrow(role)}"

    # ================= Px Events =================
    ev = Sheet(); ev.freeze = "A5"
    ev.set("A1", "s", f"{T} events — release dates, TTM EPS (linked to MOD) and event-day returns", sty["title"])
    ev.set("A2", "s", "Blue = typed from source files (dates from the press-release / investor-event file names). Green = "
                      "links to MOD. Black = formulas. 'After close' releases react the next trading day; 'Same day' "
                      "ones (pre-market releases, preliminary revenue, investor events) react that day.", sty["note"])
    ev.set(f"{EL['ttm_rev']}3", "s", "Quarterly TTM fundamentals → feed the overlays on the Idio Chart tab (Q4 rows fall "
                                     "back to the fiscal year when quarters are missing)", sty["note"])
    heads = {"period": "Period", "date": "Full-results release date", "eps_g": "GAAP EPS (qtr)",
             "eps_n": "Non-GAAP EPS (qtr)", "fy_g": "GAAP EPS (FY)", "fy_n": "Non-GAAP EPS (FY)",
             "ttm_g": "TTM GAAP EPS", "ttm_n": "TTM non-GAAP EPS", "e_date": "Event date", "e_type": "Type",
             "e_name": "Event", "e_timing": "Timing", "e_react": "Reaction day", "e_r": f"{T} % chg",
             "e_rs": "SPY % chg", "e_beta": "β (252d)", "e_idio": "Idio % chg",
             "e_note": "What happened / why (your annotation)", "ttm_rev": "TTM revenue ($M)",
             **{k: (ov_name[k].replace(" (as reported)", "") if k != "roic" else f"{ov_name[k]}") for k in okeys}}
    widths = {"A": 9, "B": 13, "C": 11, "D": 11, "E": 11, "F": 11, "G": 11, "H": 11, "J": 12, "K": 14, "L": 26, "M": 11,
              "N": 12, "O": 10, "P": 10, "Q": 9, "R": 10, "S": 60}
    for k, h in heads.items():
        ev.set(f"{EL[k]}4", "s", h, sty["hdr"])
    for L_, w in widths.items():
        ev.widths[colnum(L_)] = w
    for k in ["ttm_rev"] + okeys:
        ev.widths[colnum(EL[k])] = 13
    ev.heights[4] = 34
    ev.comments[f"{EL['ttm_g']}4"] = ("TTM = sum of the last 4 quarterly diluted EPS. If a quarter is missing in MOD, the "
                                     "Q4 row falls back to the FY figure; otherwise #N/A.")
    ev.comments[f"{EL['roic']}4"] = f"Links to MOD row {mrow(cfg['roic_role'])} ({roic_lab})."
    for k, q in enumerate(Q):
        r = Q0 + k
        lab = q["label"]
        p = per[lab]
        i = qlabels.index(lab)
        prev4 = qlabels[i - 3:i + 1] if i >= 3 else None
        fy = modmap.fy_of(mod["periods"], p["year"]) if p["q"] == 4 else None
        ev.set(f"A{r}", "s", lab, sty["in_txt"])
        ev.set(f"B{r}", "d", serial(q["date"]), sty["in_date"])
        ev.comments[f"B{r}"] = E["full"][lab]["source"]
        for key, role in (("eps_g", "eps_gaap"), ("eps_n", "eps_ng")):
            if role in mod["rows"]:
                ref = mref(role, lab)
                ev.set(f"{EL[key]}{r}", "f", f'IF(ISNUMBER({ref}),{ref},"")', sty["g_eps"])
            if fy and role in mod["rows"]:
                ref = mref(role, fy["label"])
                ev.set(f"{EL['fy_' + key[-1]]}{r}", "f", f'IF(ISNUMBER({ref}),{ref},"")', sty["g_eps"])
        for key, qk, fk in (("ttm_g", "eps_g", "fy_g"), ("ttm_n", "eps_n", "fy_n")):
            fb = f"IF(ISNUMBER({EL[fk]}{r}),{EL[fk]}{r},NA())"
            f = (f"IF(COUNT({EL[qk]}{r - 3}:{EL[qk]}{r})=4,SUM({EL[qk]}{r - 3}:{EL[qk]}{r}),{fb})" if k >= 3 else fb)
            ev.set(f"{EL[key]}{r}", "f", f, sty["eps"])
        U = EL["ttm_rev"]
        if prev4:
            refs = [mref("revenue", l) for l in prev4]
            ev.set(f"{U}{r}", "f", f"IF(COUNT({','.join(refs)})=4,{'+'.join(refs)},NA())", sty["mny"])
        else:
            ev.set(f"{U}{r}", "f", "NA()", sty["mny"])
        ev.set(f"{EL['rev_g']}{r}", "f", f"IFERROR({U}{r}/{U}{r - 4}-1,NA())" if k >= 4 else "NA()", sty["pct1"])
        for key, role in (("om", cfg["oi_role"]), ("em", cfg["ebitda_role"])):
            if key not in okeys:
                continue
            fb = (f"IF(ISNUMBER({mref(role, fy['label'])}),{mref(role, fy['label'])}/{mref('revenue', fy['label'])},NA())"
                  if fy else "NA()")
            if prev4:
                refs = [mref(role, l) for l in prev4]
                f = f"IFERROR(IF(COUNT({','.join(refs)})=4,({'+'.join(refs)})/{U}{r},{fb}),NA())"
            else:
                f = f"IFERROR({fb},NA())"
            ev.set(f"{EL[key]}{r}", "f", f, sty["pct1"])
        ref = mref(cfg["roic_role"], lab)
        ev.set(f"{EL['roic']}{r}", "f", f"IF(ISNUMBER({ref}),{ref},NA())", sty["g_pct1"])
    ev.cf.append((f"{EL['ttm_rev']}{Q0}:{EL[okeys[-1]]}{QN}", f"ISNA({EL['ttm_rev']}{Q0})", dxf_grey))
    for k, e in enumerate(EVS):
        r = EV0 + k
        ev.set(f"J{r}", "d", serial(e["date"]), sty["in_date"])
        ev.comments[f"J{r}"] = f"Source: {e['source']}"
        ev.set(f"K{r}", "s", e["type"], sty["in_txt"])
        ev.set(f"L{r}", "s", e["name"], sty["in_txt"])
        ev.set(f"M{r}", "s", e["timing"], sty["in_txt"])
        ev.set(f"N{r}", "f", f"IFERROR(INDEX({PXD('date')},MATCH(J{r},{PXD('date')},1)+IF(M{r}=\"After close\",1,0)),\"\")",
               sty["date"])
        for key, src, s in (("e_r", "ret", "pct1"), ("e_rs", "spy_ret", "pct1"), ("e_beta", "beta", "num2"),
                            ("e_idio", "idio", "pct1")):
            ev.set(f"{EL[key]}{r}", "f", f"IFERROR(INDEX({PXD(src)},MATCH(N{r},{PXD('date')},0)),\"\")", sty[s])

    # ================= Px Data =================
    pdx = Sheet(); pdx.freeze = "D5"
    first_file = os.path.basename(S["files"]["stock"])
    pdx.set("A1", "s", f"{T} and SPY daily closes, returns, rolling β, idiosyncratic (alpha) return and P/E", sty["title"])
    pdx.set("A2", "s", f"Closes: stooq daily files {first_file} / {os.path.basename(S['files']['spy'])} (adjusted for "
                       f"splits and dividends, so SPY = total return). The first 252 rows are a warm-up for the first "
                       f"252-day β. Index base = {dates[b].date()}. Point-in-time columns use the latest full-results "
                       "release dated before each day.", sty["note"])
    hd = {"date": "Date", "close": f"{T} close", "spy": "SPY close", "ret": f"{T} daily return",
          "spy_ret": "SPY daily return", "beta": "β (252d, through prior day)", "idio": f"Idio return  ({T} − β×SPY)",
          "event": "Event (reaction day)", **{f"ov_{k}": ov_name[k] for k in okeys},
          "ttm_eps": f"TTM {epsb} EPS", "pe": f"P/E (TTM {epsb})",
          "m_date": "Month-end", "m_close": "Close", "m_pe": f"P/E (TTM {epsb})",
          "m_ttm_eps": f"TTM EPS ({epsb})", "a_fy": "Fiscal year", "a_fcf": "Free cash flow ($M)",
          "a_bb": "Net share repurchases ($M; negative = net issuance)", "a_pe": f"Avg P/E (TTM {epsb}, month-ends)",
          "a_n": "# month-ends in P/E avg", "f_etf": f"{ETF} close (stooq adj.)", "f_mom": f"{MOM} close (stooq adj.)",
          "f_spy_ret": "SPY daily return", "f_ind_x": f"{ind.capitalize()} excess daily return  ({ETF} − SPY)",
          "f_mom_x": f"Momentum excess daily return  ({MOM} − SPY)", "w_date": "Week-end", "w_close": f"{T} close",
          "w_spy": "SPY close", "w_etf": f"{ETF} close", "w_mom": f"{MOM} close", "w_ret": f"{T} weekly return",
          "w_spy_ret": "SPY weekly return", "w_ind_x": f"{ind.capitalize()} excess weekly return  ({ETF} − SPY)",
          "w_mom_x": f"Momentum excess weekly return  ({MOM} − SPY)",
          "w_end": "Regression window end (daily row # of prior week-end)", "w_b_mkt": "β market",
          "w_b_ind": f"β {ind}", "w_b_mom": "β momentum", "w_r2": "R² (3-factor, 252d daily)",
          "w_idio3": "Weekly 3-factor idio return", "w_idx3": "3-factor alpha index (weekly)",
          "w_pct3": "3-factor alpha vs S&P, cumulative (%)", **{f"w_ov_{k}": ov_name[k] for k in okeys}}
    for k, h in hd.items():
        pdx.set(f"{DL[k]}4", "s", h, sty["hdr"])
        pdx.widths[colnum(DL[k])] = 12
    pdx.widths[1] = 11; pdx.widths[colnum(DL["event"])] = 28
    pdx.heights[4] = 51
    sfile = lambda k: (f"Source: {os.path.basename(S['files'][k])} from stooq.com (split- and dividend-adjusted "
                       f"closes), file dated {S['P']['files'][k].get('downloaded', '?')}.")
    pdx.comments[f"{DL['close']}4"] = sfile("stock")
    pdx.comments[f"{DL['spy']}4"] = sfile("spy") + " Dividend-adjusted, so returns are total returns."
    pdx.comments[f"{DL['beta']}4"] = (f"SLOPE of {T} daily returns on SPY daily returns over the previous 252 trading "
                                      "days (~1 year), ending the day before, so today's move never feeds today's β.")
    pdx.comments[f"{DL['ov_' + okeys[0]]}4"] = ("Steps on the trading day after each full-results release, so the line "
                                                "shows what investors knew at the time.")
    pdx.comments[f"{DL['pe']}4"] = ("Close / TTM EPS reported as of that day: trailing, what was known at the time. "
                                    "Not NTM: there is no free history of the consensus estimates of the time. "
                                    "#N/A where TTM EPS is zero or negative.")
    fills = run["fills"]
    pdx.comments[f"{DL['f_etf']}4"] = sfile("etf") + (f" Missing dates take the prior close: {', '.join(d.date().isoformat() for d in fills['etf'])}." if fills["etf"] else "")
    pdx.comments[f"{DL['f_mom']}4"] = sfile("mom") + (f" Missing dates take the prior close: {', '.join(d.date().isoformat() for d in fills['mom'])}." if fills["mom"] else "") \
        + " MTUM is long-only and rebalances twice a year, so it is a rough momentum proxy."
    px, sp = run["px"], run["spy"]
    D_ = DL
    ev_name, ev_react = PXE("e_name", EV0, EVN), PXE("e_react", EV0, EVN)
    rel_b = PXE("date", Q0, QN)
    for i in range(n):
        r = R0 + i
        warm = r <= RB
        pdx.set(f"{D_['date']}{r}", "d", serial(dates[i]), sty["in_date"])
        pdx.set(f"{D_['close']}{r}", "n", round(float(px[i]), 6), sty["in_num"])
        pdx.set(f"{D_['spy']}{r}", "n", round(float(sp[i]), 6), sty["in_num"])
        if i:
            pdx.set(f"{D_['ret']}{r}", "f", f"{D_['close']}{r}/{D_['close']}{r - 1}-1", sty["grey_pct2" if warm else "pct2"])
            pdx.set(f"{D_['spy_ret']}{r}", "f", f"{D_['spy']}{r}/{D_['spy']}{r - 1}-1", sty["grey_pct2" if warm else "pct2"])
            pdx.set(f"{D_['f_spy_ret']}{r}", "f", f"{D_['spy']}{r}/{D_['spy']}{r - 1}-1", sty["pct2"])
            for key, src in (("f_ind_x", "f_etf"), ("f_mom_x", "f_mom")):
                c0, c1 = f"{D_[src]}{r - 1}", f"{D_[src]}{r}"
                pdx.set(f"{D_[key]}{r}", "f", f"IF(AND(ISNUMBER({c1}),ISNUMBER({c0})),{c1}/{c0}-1-{D_['f_spy_ret']}{r},NA())",
                        sty["pct2"])
        for key, arr in (("f_etf", run["etf"]), ("f_mom", run["mom"])):
            if isnum(float(arr[i])):
                pdx.set(f"{D_[key]}{r}", "n", round(float(arr[i]), 6), sty["in_num"])
        if r < RS:
            continue
        pdx.set(f"{D_['beta']}{r}", "f", f"SLOPE({D_['ret']}{r - 252}:{D_['ret']}{r - 1},{D_['spy_ret']}{r - 252}:{D_['spy_ret']}{r - 1})",
                sty["num2"])
        pdx.set(f"{D_['idio']}{r}", "f", f"{D_['ret']}{r}-{D_['beta']}{r}*{D_['spy_ret']}{r}", sty["pct2"])
        pdx.set(f"{D_['event']}{r}", "f", f'IFERROR(INDEX({ev_name},MATCH({D_["date"]}{r},{ev_react},0)),"")', sty["gen"])
        pit = lambda col: f"IFERROR(INDEX({PXE(col, Q0, QN)},MATCH({D_['date']}{r}-1,{rel_b},1)),NA())"
        for k in okeys:
            pdx.set(f"{D_['ov_' + k]}{r}", "f", pit(k), sty["pct1"])
        pdx.set(f"{D_['ttm_eps']}{r}", "f", pit(cfg["ttm_key"]), sty["eps"])
        e = f"{D_['ttm_eps']}{r}"
        pdx.set(f"{D_['pe']}{r}", "f", f"IF(ISNUMBER({e}),IF({e}>0,{D_['close']}{r}/{e},NA()),NA())", sty["pe"])
    pdx.cf.append((f"{D_['ov_' + okeys[0]]}{RS}:{D_['pe']}{RN}", f"ISNA({D_['ov_' + okeys[0]]}{RS})", dxf_grey))

    # monthly
    M = run["monthly"]
    MN = 4 + len(M["date"])
    pdx.set(f"{D_['m_date']}2", "s", f"MONTH-END P/E (TTM) — feeds the P/E chart on the Idio Chart tab. Last trading day of "
                                     f"each month. P/E = close / trailing-12-month {epsb} EPS reported as of that day "
                                     "(trailing, not forward: no free consensus history).", sty["note"])
    for j in range(len(M["date"])):
        r = 5 + j
        prev = f"DATE({M['date'][0].year},{M['date'][0].month},0)" if j == 0 else f"{D_['m_date']}{r - 1}"
        pdx.set(f"{D_['m_date']}{r}", "f", f'_xlfn.MAXIFS({A_},{A_},"<="&EOMONTH({prev},1))', sty["date"])
        mt = f"MATCH({D_['m_date']}{r},{A_},0)"
        pdx.set(f"{D_['m_close']}{r}", "f", f"INDEX({rng('close')},{mt})", sty["eps"])
        for key, src, s in (("m_pe", "pe", "pe"), ("m_ttm_eps", "ttm_eps", "eps")):
            pdx.set(f"{D_[key]}{r}", "f", f"IFERROR(INDEX({rng(src)},{mt}),NA())", sty[s])

    # annual
    A = run["annual"]
    AN = 4 + len(A["fy"])
    fcf_lab = mod["rows"]["fcf"]["label"]
    bb_lab = " + ".join(mod["rows"][x]["label"] for x in cfg["bb_roles"])
    pdx.set(f"{D_['a_fy']}2", "s", f"FCF vs BUYBACKS — annual, from MOD ('{fcf_lab}', row {mrow('fcf')}; '{bb_lab}', sign "
                                   f"flipped so buybacks are positive). P/E = average of that fiscal year's month-end TTM {epsb} "
                                   "P/Es; the count column says how many months had one. Feeds the chart on Idio Chart.",
            sty["note"])
    mpe, mdt = rng("m_pe", 5, MN), rng("m_date", 5, MN)
    fyem = cfg["fye_month"]
    fy_of = f"YEAR({mdt})" if fyem == 12 else f"(YEAR({mdt})+(MONTH({mdt})>{fyem}))"   # month-end -> fiscal year
    for j, y in enumerate(A["fy"]):
        r = 5 + j
        col = A["col"][j]
        pdx.set(f"{D_['a_fy']}{r}", "n", y, sty["int"])
        pdx.set(f"{D_['a_fcf']}{r}", "f", f"MOD!{col}{mrow('fcf')}", sty["g_idx"])
        bbs = [f"MOD!{col}{mrow(x)}" for x in cfg["bb_roles"]]
        pdx.set(f"{D_['a_bb']}{r}", "f", f"-{bbs[0]}" if len(bbs) == 1 else f"-({'+'.join(bbs)})", sty["g_idx"])
        fyc = f"{D_['a_fy']}{r}"
        pdx.set(f"{D_['a_pe']}{r}", "fa", f"IFERROR(AVERAGE(IF(ISNUMBER({mpe})*({fy_of}={fyc}),{mpe})),NA())", sty["pe"])
        pdx.set(f"{D_['a_n']}{r}", "f", f"SUMPRODUCT(ISNUMBER({mpe})*({fy_of}={fyc}))", sty["int"])

    # factor + weekly
    W = run["weekly"]
    WN = 4 + len(W["date"])
    fl = lambda k: ", ".join(d.date().isoformat() for d in fills[k]) or "none"
    pdx.set(f"{D_['f_etf']}2", "s", f"FACTOR PRICES — stooq split/dividend-adjusted closes, pasted as values. If stooq has "
                                    f"no price for a date, the prior day's close is used ({ETF}: {fl('etf')}; {MOM}: "
                                    f"{fl('mom')}). {ETF} history starts {run['first']['etf'].date()}; {MOM} "
                                    f"{run['first']['mom'].date()}.", sty["note"])
    pdx.set(f"{D_['w_date']}2", "s", f"3-FACTOR ALPHA INDEX — each week: regress {T} daily returns on [SPY, {ETF}−SPY, "
                                     f"{MOM}−SPY] over the 252 trading days ending at the prior week-end (LINEST, no "
                                     f"look-ahead), then weekly idio = {T} − β_mkt×SPY − β_{ind}×({ETF}−SPY) − β_mom×"
                                     f"({MOM}−SPY). Index = 100 on {W['date'][0].date()}, the first week-end with a full "
                                     "year of factor returns. Week-end = last trading day of each Sat–Fri week. Feeds "
                                     "the 3-factor chart on Idio Chart.", sty["note"])
    fri = W["date"][0] + pd.Timedelta(days=(4 - W["date"][0].weekday()) % 7)
    X1, X3 = rng("f_spy_ret"), rng("f_mom_x")
    for j in range(len(W["date"])):
        r = 5 + j
        wd = f"{D_['w_date']}{r}"
        lim = f"DATE({fri.year},{fri.month},{fri.day})" if j == 0 else \
            f"({D_['w_date']}{r - 1}+14-WEEKDAY({D_['w_date']}{r - 1},16))"
        pdx.set(wd, "f", f'_xlfn.MAXIFS({A_},{A_},"<="&{lim})', sty["date"])
        mt = f"MATCH({wd},{A_},0)"
        for key, src in (("w_close", "close"), ("w_spy", "spy"), ("w_etf", "f_etf"), ("w_mom", "f_mom")):
            pdx.set(f"{D_[key]}{r}", "f", f"INDEX({rng(src)},{mt})", sty["eps"])
        for k in okeys:
            # IF(ISNUMBER(..)): a week-end on the index base date points at a blank daily cell, which INDEX reads as 0
            ix = f"INDEX({rng('ov_' + k)},{mt})"
            pdx.set(f"{D_['w_ov_' + k]}{r}", "f", f"IFERROR(IF(ISNUMBER({ix}),{ix},NA()),NA())", sty["pct1"])
        pdx.set(f"{D_['w_pct3']}{r}", "f", f"{D_['w_idx3']}{r}/100-1", sty["pct1"])
        if j == 0:
            pdx.set(f"{D_['w_idx3']}{r}", "n", 100, sty["in_idx"])
            continue
        c = lambda key, rr=r: f"{D_[key]}{rr}"
        pdx.set(c("w_ret"), "f", f"{c('w_close')}/{c('w_close', r - 1)}-1", sty["pct2"])
        pdx.set(c("w_spy_ret"), "f", f"{c('w_spy')}/{c('w_spy', r - 1)}-1", sty["pct2"])
        pdx.set(c("w_ind_x"), "f", f"{c('w_etf')}/{c('w_etf', r - 1)}-1-{c('w_spy_ret')}", sty["pct2"])
        pdx.set(c("w_mom_x"), "f", f"{c('w_mom')}/{c('w_mom', r - 1)}-1-{c('w_spy_ret')}", sty["pct2"])
        pdx.set(c("w_end"), "f", f"MATCH({c('w_date', r - 1)},{A_},0)", sty["int"])
        k_ = c("w_end")
        y = f"INDEX({rng('ret')},{k_}-251):INDEX({rng('ret')},{k_})"
        x = f"INDEX({X1},{k_}-251):INDEX({X3},{k_})"
        for key, j3 in (("w_b_mkt", 3), ("w_b_ind", 2), ("w_b_mom", 1)):
            pdx.set(c(key), "f", f"INDEX(LINEST({y},{x}),1,{j3})", sty["num2"])
        pdx.set(c("w_r2"), "f", f"INDEX(LINEST({y},{x},TRUE,TRUE),3,1)", sty["pct1"])
        pdx.set(c("w_idio3"), "f", f"{c('w_ret')}-{c('w_b_mkt')}*{c('w_spy_ret')}-{c('w_b_ind')}*{c('w_ind_x')}-"
                                   f"{c('w_b_mom')}*{c('w_mom_x')}", sty["pct2"])
        pdx.set(c("w_idx3"), "f", f"{c('w_idx3', r - 1)}*(1+{c('w_idio3')})", sty["idx"])

    # ================= Idio Chart =================
    ic = Sheet(); ic.zoom = 115
    ic.set("A1", "s", f"{T} — idio chart", sty["title16"])
    ic.set("A2", "s", f"Four charts: (1) share price with point-in-time TTM fundamentals (right axis); (2) month-end P/E "
                      f"on TTM {epsb} EPS, with that EPS; (3) free cash flow vs. net buybacks with the average TTM P/E; (4) {T}'s "
                      f"idiosyncratic performance with the market, {ind} ({ETF}) and momentum ({MOM}) stripped out, weekly, "
                      "with the same fundamentals. Data: 'Px Data'. Release and event dates: 'Px Events'.", sty["note"])
    ic.set("A3", "s", f"How to read alpha: each week, idio return = {T} return − β_mkt×SPY − β_{ind}×({ETF}−SPY) − "
                      f"β_mom×({MOM}−SPY), with the betas fitted on the prior year of daily returns. The line compounds "
                      f"those, so it moves only on the part of {T}'s move that the market, its industry and momentum "
                      "can't explain. The tables on the right list the 20 biggest daily idio moves (daily β vs SPY); "
                      "annotate them and the line's big steps.", sty["note"])
    G = f"'Px Data'!${D_['idio']}${RS}:${D_['idio']}${RN}"
    pxr = lambda key: f"'Px Data'!${D_[key]}${RS}:${D_[key]}${RN}"
    for blk, (title, fn, s) in enumerate((("Top 20 UP days", "LARGE", "up"), ("Top 20 DOWN days", "SMALL", "down"))):
        r0 = 5 + blk * 25
        ic.set(f"V{r0}", "s", title, sty["bold"])
        for L_, h in zip("V W X Y Z AA AB".split(), ["#", "Date", "Idio %", f"{T} %", "SPY %", "Event that day (auto)",
                                                      "Your annotation"]):
            ic.set(f"{L_}{r0 + 1}", "s", h, sty["hdr"])
        ic.heights[r0 + 1] = 34
        for k in range(1, 21):
            r = r0 + 1 + k
            m = f"MATCH(X{r},{G},0)"
            ic.set(f"V{r}", "n", k, sty["grey"])
            ic.set(f"W{r}", "f", f"INDEX({pxr('date')},{m})", sty["date"])
            ic.set(f"X{r}", "f", f"{fn}({G},{k})", sty[s])
            ic.set(f"Y{r}", "f", f"INDEX({pxr('ret')},{m})", sty[s])
            ic.set(f"Z{r}", "f", f"INDEX({pxr('spy_ret')},{m})", sty["pct1"])
            ic.set(f"AA{r}", "f", f"INDEX({pxr('event')},{m})", sty["gen"])
            ic.set(f"AB{r}", "blank", None, sty["in_txt"])
    for L_, w in {"A": 10, "V": 4, "W": 11, "X": 8, "Y": 8, "Z": 8, "AA": 26, "AB": 50}.items():
        ic.widths[colnum(L_)] = w

    # ================= charts =================
    okd = [run["daily"][k][b + 1:] for k in okeys]
    lo_p, hi_p = engine.axis_range(*okd)
    lo_a, hi_a = engine.axis_range(*[W[k] for k in okeys])
    cat_d = (f"'Px Data'!${D_['date']}${RS}:${D_['date']}${RN}", [serial(d) for d in dates[b + 1:]])
    ser_d = lambda key, vals: (f"'Px Data'!${D_[key]}$4", hd[key], f"'Px Data'!${D_[key]}${RS}:${D_[key]}${RN}", vals)
    charts = []
    charts.append(chart("price", f"{T} share price with TTM fundamentals (right axis)", cat_d,
                        [ser_d("close", list(px[b + 1:]))] + [ser_d("ov_" + k, list(run["daily"][k][b + 1:])) for k in okeys],
                        okeys, (lo_p, hi_p)))
    cat_m = (f"'Px Data'!${D_['m_date']}$5:${D_['m_date']}${MN}", [serial(d) for d in M["date"]])
    ser_m = lambda key, vals: (f"'Px Data'!${D_[key]}$4", hd[key], f"'Px Data'!${D_[key]}$5:${D_[key]}${MN}", vals)
    charts.append(chart("pe", f"{T} P/E on TTM {epsb} EPS (month-end), with TTM EPS (right axis)", cat_m,
                        [ser_m("m_pe", M["pe"]), ser_m("m_ttm_eps", M["ttm_eps"])], okeys, None))
    cat_a = (f"'Px Data'!${D_['a_fy']}$5:${D_['a_fy']}${AN}", A["fy"])
    ser_a = lambda key, vals: (f"'Px Data'!${D_[key]}$4", hd[key], f"'Px Data'!${D_[key]}$5:${D_[key]}${AN}", vals)
    charts.append(chart("fcf", "Free cash flow vs. net buybacks ($M) with average TTM P/E (right axis)", cat_a,
                        [ser_a("a_fcf", A["fcf"]), ser_a("a_bb", A["bb"]), ser_a("a_pe", A["pe"])], okeys, None))
    cat_w = (f"'Px Data'!${D_['w_date']}$5:${D_['w_date']}${WN}", [serial(d) for d in W["date"]])
    ser_w = lambda key, vals: (f"'Px Data'!${D_[key]}$4", hd[key], f"'Px Data'!${D_[key]}$5:${D_[key]}${WN}", vals)
    charts.append(chart("alpha", f"{T} idiosyncratic performance: market, {ind} & momentum stripped (weekly) with TTM "
                                 "fundamentals (right axis)", cat_w,
                        [ser_w("w_pct3", W["pct3"])] + [ser_w("w_ov_" + k, W[k]) for k in okeys], okeys, (lo_a, hi_a)))

    # ================= write parts =================
    st_xml = st.render()
    pkg.put("xl/styles.xml", st_xml)
    pkg.content_default("vml", "application/vnd.openxmlformats-officedocument.vmlDrawing")
    vml_ids = [int(x) for p, data in pkg.parts.items() if p.endswith(".vml")
               for x in re.findall(rb'<o:idmap v:ext="edit" data="(\d+)"', data)]
    next_vml_id = max(vml_ids + [0]) + 1
    for name, sh in (("Idio Chart", ic), ("Px Events", ev), ("Px Data", pdx)):
        part = pkg.add_sheet(name, "")
        drid = lrid = None
        if name == "Idio Chart":
            dn = pkg.free("xl/drawings/drawing{}.xml")
            dpart = f"xl/drawings/drawing{dn}.xml"
            anchors = []
            for k, ((xml_, _), (row, cy)) in enumerate(zip(charts, ((4, 8737600), (47, 7594600), (86, 7569200),
                                                                    (126, 7569200)))):
                cn = pkg.free("xl/charts/chart{}.xml")
                cpart = f"xl/charts/chart{cn}.xml"
                pkg.put(cpart, xml_)
                pkg.content_override(cpart, CT["chart"])
                rid = pkg.attach(dpart, "chart", cpart)
                anchors.append(anchor(row, cy, k + 2, f"Chart {k + 1}", rid))
            pkg.put(dpart, '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
                           '<xdr:wsDr xmlns:xdr="http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing" '
                           'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">' + "".join(anchors) + "</xdr:wsDr>")
            pkg.content_override(dpart, CT["drawing"])
            drid = pkg.attach(part, "drawing", dpart)
        if sh.comments:
            cn = pkg.free("xl/comments{}.xml")
            vn = pkg.free("xl/drawings/vmlDrawing{}.vml")
            cx, vml = comments_parts(sh.comments, next_vml_id)
            next_vml_id += 1
            pkg.put(f"xl/comments{cn}.xml", cx)
            pkg.put(f"xl/drawings/vmlDrawing{vn}.vml", vml)
            lrid = pkg.attach(part, "vml", f"xl/drawings/vmlDrawing{vn}.vml")
            pkg.attach(part, "comments", f"xl/comments{cn}.xml", CT["comments"])
        pkg.put(part, sh.xml(drid, lrid))
    pkg.finish()
    pkg.save(out)
    import notebox; notebox.fix(out, out, since=model)   # this tab's note boxes open readable (other tabs untouched)

    layout = {"daily": DL, "events": EL, "rows": {"R0": R0, "RB": RB, "RS": RS, "RN": RN, "Q0": Q0, "QN": QN,
                                                   "EV0": EV0, "EVN": EVN, "MN": MN, "AN": AN, "WN": WN},
              "axis": {"price": [lo_p, hi_p], "alpha": [lo_a, hi_a]}}
    json.dump(layout, open(os.path.join(work, "layout.json"), "w"), indent=1)
    return S, layout


# ------------------------------------------------------------------ charts
def numcache(vals, fmt):
    pts = "".join(f'<c:pt idx="{j}"><c:v>{float(v)!r}</c:v></c:pt>' for j, v in enumerate(vals) if isnum(v))
    return f"<c:numCache><c:formatCode>{esc(fmt)}</c:formatCode><c:ptCount val=\"{len(vals)}\"/>{pts}</c:numCache>"


def chart(kind, title, cat, series, okeys, axis):
    """Fill one template: series refs + caches in template order, title, overlay axis min / max."""
    x = open(os.path.join(ASSETS, f"chart_{kind}.xml"), encoding="utf-8").read()
    sers = re.findall(r"<c:ser>.*?</c:ser>", x, re.S)
    if kind in ("price", "alpha") and "em" not in okeys:          # template order: main, rev_g, om, em, roic
        x = x.replace(sers[3], "", 1)
        sers = re.findall(r"<c:ser>.*?</c:ser>", x, re.S)
    assert len(sers) == len(series), (kind, len(sers), len(series))
    cat_ref, cat_vals = cat
    for k, (s_old, (tx_ref, name, val_ref, vals)) in enumerate(zip(sers, series)):
        s = re.sub(r"<c:idx val=\"\d+\"/><c:order val=\"\d+\"/>", f'<c:idx val="{k}"/><c:order val="{k}"/>', s_old, count=1)
        s = re.sub(r"<c:tx><c:strRef><c:f>[^<]*</c:f><c:strCache>.*?</c:strCache>",
                   lambda _: f'<c:tx><c:strRef><c:f>{esc(tx_ref)}</c:f><c:strCache><c:ptCount val="1"/><c:pt idx="0">'
                             f"<c:v>{esc(name)}</c:v></c:pt></c:strCache>", s, count=1, flags=re.S)
        s = re.sub(r"<c:cat><c:numRef><c:f>[^<]*</c:f><c:numCache><c:formatCode>([^<]*)</c:formatCode>.*?</c:numCache>",
                   lambda m: f"<c:cat><c:numRef><c:f>{esc(cat_ref)}</c:f>" + numcache(cat_vals, unesc_(m.group(1))), s,
                   count=1, flags=re.S)
        s = re.sub(r"<c:val><c:numRef><c:f>[^<]*</c:f><c:numCache><c:formatCode>([^<]*)</c:formatCode>.*?</c:numCache>",
                   lambda m: f"<c:val><c:numRef><c:f>{esc(val_ref)}</c:f>" + numcache(vals, unesc_(m.group(1))), s,
                   count=1, flags=re.S)
        x = x.replace(s_old, s, 1)
    x = re.sub(r"(<c:title><c:tx><c:rich>.*?<a:t>)[^<]*(</a:t>)", lambda m: m.group(1) + esc(title) + m.group(2), x,
               count=1, flags=re.S)
    if axis:
        x = re.sub(r'(<c:valAx><c:axId val="200"/><c:scaling><c:orientation val="minMax"/>)<c:max val="[^"]*"/><c:min val="[^"]*"/>',
                   rf'\g<1><c:max val="{axis[1]}"/><c:min val="{axis[0]}"/>', x, count=1)
        assert f'<c:max val="{axis[1]}"/>' in x, kind
    return x, kind


def unesc_(t):
    return t.replace("&quot;", '"').replace("&amp;", "&")


def anchor(row, cy, nid, name, rid):
    return (f'<xdr:oneCellAnchor><xdr:from><xdr:col>0</xdr:col><xdr:colOff>0</xdr:colOff><xdr:row>{row}</xdr:row>'
            f'<xdr:rowOff>0</xdr:rowOff></xdr:from><xdr:ext cx="11880000" cy="{cy}"/><xdr:graphicFrame macro="">'
            f'<xdr:nvGraphicFramePr><xdr:cNvPr id="{nid}" name="{name}"/><xdr:cNvGraphicFramePr/></xdr:nvGraphicFramePr>'
            '<xdr:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/></xdr:xfrm><a:graphic>'
            '<a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/chart">'
            '<c:chart xmlns:c="http://schemas.openxmlformats.org/drawingml/2006/chart" '
            f'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" r:id="{rid}"/>'
            "</a:graphicData></a:graphic></xdr:graphicFrame><xdr:clientData/></xdr:oneCellAnchor>")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--replace", action="store_true")
    a = ap.parse_args()
    S, layout = build(a.model, a.work, a.out, a.replace)
    run = S["run"]
    print(json.dumps({"status": "built", "out": a.out, "daily_rows": len(run["dates"]),
                      "first": run["dates"][0].date().isoformat(), "base": run["dates"][run["base"]].date().isoformat(),
                      "last": run["dates"][-1].date().isoformat(), "quarters": len(run["quarters"]),
                      "events": len(run["events"]), "months": len(run["monthly"]["date"]),
                      "weeks": len(run["weekly"]["date"]), "three_factor_start": run["weekly"]["date"][0].date().isoformat(),
                      "fiscal_years": run["annual"]["fy"], "overlays": run["okeys"], "axis": layout["axis"],
                      "fills": {k: [d.date().isoformat() for d in v] for k, v in run["fills"].items()}}, indent=1))
