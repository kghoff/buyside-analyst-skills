"""Write the Industry P&L and Industry Comparison tabs into a copy of the user's model (raw XML; nothing else changes).

usage: python3 build.py --model M.xlsx --work W --out OUT.xlsx [--replace]
Reads W/industry.json (assemble.py). Writes OUT and W/layout.json ({"rows", "expected": {cell: value}, ...}),
which verify.py checks after a LibreOffice recalc. Exit 2: the tabs exist (rerun with --replace after the user's yes).
Exit 3: another tab has formulas pointing into them."""
import argparse
import json
import math
import os
import re

import charts
import compute
import lines
from xlsx import Package, Sheet, Styles, CT, colname, comments_parts, vml_blocks

TABS = ("Industry P&L", "Industry Comparison")
P = "'Industry P&L'"
BLUE, BLACK, GREEN, GREY, NAVY, WHITE = "FF0000FF", "FF000000", "FF008000", "FF808080", "FF002060", "FFFFFFFF"
MNY, PCT, MULT = '#,##0.0_);\\(#,##0.0\\);"–"', "0.0%", '0.0"x"'   # MNY as Excel writes it (as re-saved in Excel)
AN_ROWS = [("growth", "Revenue growth", PCT), ("share", "Share of industry revenue", PCT),
           ("gm", "Gross margin", PCT), ("om", "Operating margin", PCT), ("em", "EBITDA margin", PCT),
           ("capex_sales", "Capex ÷ sales", PCT), ("capex_da", "Capex ÷ D&A", MULT), ("fcf_m", "FCF margin", PCT),
           ("tax_rate", "Tax rate (effective)", PCT), ("nopat", "NOPAT", MNY),
           ("ic", "Invested capital (approx.)", MNY), ("roic", "ROIC (approx.)", PCT),
           ("d_rev", "Δ revenue (both years)", MNY), ("prior_rev", "Prior revenue (both years)", MNY)]
ROIC_NOTE = ("Condensed approximation of the MOD definition: NOPAT (operating income x (1 - effective tax rate)) "
             "/ average of (cash + receivables + inventory + PP&E + goodwill & intangibles - payables & accrued). "
             "Same formula for every company so they compare.")
NOTE3 = ("How to read: share of new dollars = the subject's revenue change ÷ the industry's revenue change that year "
         "(same companies both years). Bars above the line mean it is taking more than its share of the growth, which "
         "usually shows up in total share later. Gaps are years when the industry barely grew (under 1%) or shrank.")
NOTE6 = ("How to read: capex ÷ sales and capex ÷ D&A show how hard the industry is investing (capex ÷ D&A above 1x "
         "means it is growing its asset base). In a classic capital cycle, high returns attract spending and the new "
         "capacity later pushes returns down: watch for ROIC falling a few years after a spending peak.")


def _styles(st):
    x = lambda **k: st.xf(**k)
    return {"title": x(sz=16, b=True), "note": x(color=GREY, sz=11, i=True, align="left"), "hdr": x(b=True, fmt="0", color=WHITE, fill=NAVY),
            "note_nw": x(color=GREY, sz=11, i=True), "band_navy": x(color=WHITE, fill=NAVY),
            "band_blue": x(color=WHITE, b=True, fill="FF0070C0"),
            "sect": x(color=NAVY, b=True), "sub": x(b=True), "lab": x(), "lab_i": x(color=GREY, i=True),
            "typed": x(color=BLUE, fmt=MNY), "link": x(color=GREEN, fmt=MNY), "est": x(color=GREY, i=True, fmt=MNY),
            "calc": x(fmt=MNY), "calc_b": x(fmt=MNY, b=True), "pct": x(fmt=PCT), "mult": x(fmt=MULT),
            "int": x(fmt="0"), "pct_hl": x(fmt=PCT, fill="FFFCE4D6"), "mny_hl": x(fmt=MNY, fill="FFFCE4D6"),
            "lab_hl": x(b=True, fill="FFFCE4D6"), "th": x(b=True, color=WHITE, fill="FF002060", align="center")}


def ratio(n, d, neg=False):
    num = f"-{n}" if neg else n
    return f'IF(AND(ISNUMBER({n}),ISNUMBER({d}),{d}<>0),{num}/{d},NA())'


def axis_range(*series):
    """Value-axis min/max from the industry and subject series only, padded 0.1 and rounded out to 10% steps (min
    never above 0), so one peer outlier (an op. margin of -14,000%) is clipped instead of flattening the lines."""
    v = [x for s in series for x in s if isinstance(x, (int, float)) and math.isfinite(x)]
    if not v:
        return {}
    return {"min": min(0, math.floor(round((min(v) - 0.1) * 10, 6)) / 10),
            "max": math.ceil(round((max(v) + 0.1) * 10, 6)) / 10}


def build(model, work, out, replace=False):
    I = json.load(open(os.path.join(work, "industry.json")))
    S = compute.run(I)
    years = I["years"]
    col = {y: colname(3 + i) for i, y in enumerate(years)}
    pkg = Package(model)
    have = [s[0] for s in pkg.sheets()]
    if any(t in have for t in TABS):
        if not replace:
            print(json.dumps({"status": "exists", "tabs": [t for t in TABS if t in have]}))
            raise SystemExit(2)
        refs = []
        for name, _, _, part in pkg.sheets():
            if name not in TABS and re.search(r"Industry (P&amp;L|Comparison)'?!", pkg.text(part)):
                refs.append(name)
        if refs:
            print(json.dumps({"status": "referenced", "tabs": refs}))
            raise SystemExit(3)
        for t in TABS:
            if t in have:
                pkg.remove_sheet(t)
    st = Styles(pkg.text("xl/styles.xml"))
    sty = _styles(st)
    sh = Sheet()
    sh.freeze, sh.zoom = "C5", 100
    exp, rows, typed, notes = {}, {}, [], {}
    # House formatting: year columns 13 wide, 22 pt title row, navy header row, notes on one line
    sh.widths.update({1: 2, 2: 44, **{2 + i + 1: 13 for i in range(len(years))}})
    sh.heights[1] = 22
    last_col = col[years[-1]]

    def band(r, text, style, at="B"):
        for c in ["A", "B"] + list(col.values()):
            sh.set(f"{c}{r}", "blank", None, style)
        sh.set(f"{at}{r}", "s", text, style)
    sh.set("A1", "s", f"{I['industry']} industry P&L ($M, calendar years)", sty["title"])
    sh.set("A2", "s", "Sum of the public companies below. Blue = typed from a filing (see the cell note), green = "
                      "linked to MOD, grey italic = estimated from the parent's figure x the segment's share of revenue, "
                      "black = formula. Costs and outflows are negative, as in MOD.", sty["note_nw"])
    sh.set("A3", "s", "Not included: " + ("; ".join(f"{e['name']} ({e['why']})" for e in I["excluded"]) or "none"),
           sty["note_nw"])
    band(4, "($M)", sty["hdr"])
    for y in years:
        sh.set(f"{col[y]}4", "n", y, sty["hdr"])
    r = 6

    def put(ref, kind, val, style, want):
        sh.set(ref, kind, val, style)
        if kind in ("f", "n"):
            exp[ref] = want

    def line_block(tag, L, Svals, kinds, start):
        """Statement lines for one company (or the industry). Returns {key: row} and the next free row."""
        rr, rmap = start, {}
        for stmt in ("IS", "BS", "CF"):
            if kinds is None:       # industry block: blue band across the row
                band(rr, lines.STMT_TITLE[stmt], sty["band_blue"])
            else:
                sh.set(f"B{rr}", "s", lines.STMT_TITLE[stmt], sty["sub"])
            rr += 1
            for k in lines.KEYS:
                if lines.STMT[k] == stmt:
                    rmap[k] = rr
                    rr += 1
        for k, rk in rmap.items():
            sh.set(f"B{rk}", "s", lines.LABEL[k], sty["lab"])
            for y in years:
                ref = f"{col[y]}{rk}"
                if kinds is None:     # industry: SUM of the company cells (calc lines too, as compute.py does)
                    cells = ",".join(f"{col[y]}{rows[t][k]}" for t in tags_order)
                    put(ref, "f", f'IF(COUNT({cells})=0,"",SUM({cells}))',
                        sty["calc_b"] if k in lines.CALC else sty["calc"], Svals[k][y])
                elif k in lines.CALC:
                    a, b = (f"{col[y]}{rmap[x]}" for x in lines.CALC[k])
                    put(ref, "f", f'IF(AND(ISNUMBER({a}),ISNUMBER({b})),{a}+{b},"")', sty["calc_b"], Svals[k][y])
                else:
                    x = L.get(k, {}).get(str(y))
                    if not x:
                        continue
                    if x["kind"] == "link":
                        put(ref, "f", x["f"], sty["link"], x["v"])
                    elif x["kind"] == "typed":
                        put(ref, "n", x["v"], sty["typed"], x["v"])
                        typed.append(ref)
                        if x.get("note"):
                            notes[ref] = x["note"]
                    else:   # est: parent cell x segment revenue / parent revenue
                        pc, sr, pr = (f"{col[y]}{kinds[k]}", f"{col[y]}{rmap['revenue']}", f"{col[y]}{kinds['revenue']}")
                        put(ref, "f", f"{pc}*{sr}/{pr}", sty["est"], x["v"])
                        notes[ref] = x["note"]
        return rmap, rr

    def an_block(tag, rmap, an, start, ind_rev_row=None, ind=False):
        rr, amap = start, {}
        for key, label, fmt in AN_ROWS:
            if key == "share" and ind:
                continue
            amap[key] = rr
            sh.set(f"B{rr}", "s", label, sty["lab_i"] if key in ("d_rev", "prior_rev") else sty["lab"])
            rr += 1
        for i, y in enumerate(years):
            c, p = col[y], (col[years[i - 1]] if i else None)
            R = lambda k: f"{c}{rmap[k]}"
            A = lambda k: f"{c}{amap[k]}"
            f = {}
            if p:
                rv, pv = R("revenue"), f"{p}{rmap['revenue']}"
                both = f"AND(ISNUMBER({rv}),ISNUMBER({pv}))"
                f["d_rev"] = f'IF({both},{rv}-{pv},"")'
                f["prior_rev"] = f'IF({both},{pv},"")'
                f["growth"] = f"IF(AND({both},{pv}<>0),{rv}/{pv}-1,NA())"
            else:
                f["d_rev"] = f["prior_rev"] = '""'
                f["growth"] = "NA()"
            if not ind:
                f["share"] = ratio(R("revenue"), f"{c}{ind_rev_row}")
            f["gm"], f["om"], f["em"] = ratio(R("gross_profit"), R("revenue")), ratio(R("oi"), R("revenue")), \
                ratio(R("ebitda"), R("revenue"))
            f["capex_sales"] = ratio(R("capex"), R("revenue"), neg=True)
            f["capex_da"] = ratio(R("capex"), R("da"), neg=True)
            f["fcf_m"] = ratio(R("fcf"), R("revenue"))
            f["tax_rate"] = f"IF(AND(ISNUMBER({R('pretax')}),N({R('pretax')})>0),-N({R('tax')})/{R('pretax')},0)"
            f["nopat"] = f'IF(ISNUMBER({R("oi")}),{R("oi")}*(1-{A("tax_rate")}),NA())'
            parts = "+".join(f"N({R(k)})" for k in ("cash", "receivables", "inventory", "ppe", "gwi"))
            f["ic"] = f"IF(ISNUMBER({R('revenue')}),{parts}-N({R('payables')}),NA())"
            if p:
                icp = f"{p}{amap['ic']}"
                f["roic"] = (f"IF(AND(ISNUMBER({A('nopat')}),ISNUMBER({icp}),ISNUMBER({A('ic')}),N({icp})+N({A('ic')})<>0),"
                             f"{A('nopat')}/(({icp}+{A('ic')})/2),NA())")
            else:
                f["roic"] = "NA()"
            for key, label, fmt in AN_ROWS:
                if key not in amap:
                    continue
                stl = sty["pct"] if fmt == PCT else sty["mult"] if fmt == MULT else sty["calc"]
                put(f"{c}{amap[key]}", "f", f[key], stl, an[key][y])
        return amap, rr

    tags_order = [c["ticker"] for c in I["companies"]]
    # industry section placeholder rows are computed first so company blocks can point at industry revenue
    ind_start = r
    n_lines = len(lines.KEYS) + 3
    ind_an_start = ind_start + 1 + n_lines + 1
    n_ind_an = len(AN_ROWS) - 1 + 2
    r = ind_an_start + 1 + n_ind_an + 1
    ind_rev_row = ind_start + 2                      # title row, "Income statement" row, then Revenue
    for c in I["companies"]:
        T = c["ticker"]
        sh.set(f"A{r}", "s", f"{c['name']} ({T})" + (" — subject" if c["role"] == "subject" else ""), sty["sect"])
        sh.set(f"B{r + 1}", "s", c["header"], sty["note"])
        sh.heights[r + 1] = 16 * max(1, math.ceil(len(c["header"]) / 50))     # wrapped in column B
        par_rows = None
        if c.get("parent"):
            # parent block goes after this company's lines + analysis, but estimates need its rows now
            par_start = r + 2 + n_lines + len(AN_ROWS) + 1
            par_rows, k0 = {}, par_start + 1
            for k in lines.KEYS:
                if k not in lines.CALC:
                    par_rows[k] = k0
                    k0 += 1
        rows[T], nxt = line_block(T, c["lines"], S["co"][T]["lines"], par_rows or {}, r + 2)
        amap, nxt = an_block(T, rows[T], S["co"][T]["an"], nxt, ind_rev_row)
        rows[T].update({"an_" + k: v for k, v in amap.items()})
        if c.get("parent"):
            sh.set(f"B{par_start}", "s", f"{c['name']} consolidated (used for the estimates above)", sty["sub"])
            for k, rk in par_rows.items():
                sh.set(f"B{rk}", "s", lines.LABEL[k], sty["lab_i"])
                for y in years:
                    x = c["parent"].get(k, {}).get(str(y))
                    if x:
                        ref = f"{col[y]}{rk}"
                        put(ref, "n", x["v"], sty["typed"], x["v"])
                        typed.append(ref)
                        notes[ref] = x["note"]
            rows[T].update({"parent_" + k: v for k, v in par_rows.items()})
            nxt = k0
        r = nxt + 1
    # industry total + analysis
    sh.set(f"A{ind_start}", "s", "INDUSTRY TOTAL", sty["sect"])
    rows["IND"], _ = line_block("IND", None, S["ind"], None, ind_start + 1)
    assert rows["IND"]["revenue"] == ind_rev_row
    band(ind_an_start, "INDUSTRY ANALYSIS", sty["band_navy"], at="A")
    cnt_row = ind_an_start + 1
    sh.set(f"B{cnt_row}", "s", "Companies included (with revenue)", sty["lab"])
    for y in years:
        cells = ",".join(f"{col[y]}{rows[t]['revenue']}" for t in tags_order)
        put(f"{col[y]}{cnt_row}", "f", f"COUNT({cells})", sty["int"], S["ind_an"]["count"][y])
    amap, nd_row = an_block("IND", rows["IND"], S["ind_an"], cnt_row + 1, ind=True)
    for i, y in enumerate(years):        # industry growth / Δ / prior: same companies both years
        c = col[y]
        d = ",".join(f"{c}{rows[t]['an_d_rev']}" for t in tags_order)
        p = ",".join(f"{c}{rows[t]['an_prior_rev']}" for t in tags_order)
        put(f"{c}{amap['d_rev']}", "f", f'IF(COUNT({d})=0,"",SUM({d}))', sty["calc"], S["ind_an"]["d_rev"][y])
        put(f"{c}{amap['prior_rev']}", "f", f'IF(COUNT({p})=0,"",SUM({p}))', sty["calc"], S["ind_an"]["prior_rev"][y])
        put(f"{c}{amap['growth']}", "f", ratio(f"{c}{amap['d_rev']}", f"{c}{amap['prior_rev']}"), sty["pct"],
            S["ind_an"]["growth"][y])
        sd, dI, pI = f"{c}{rows[tags_order[0]]['an_d_rev']}", f"{c}{amap['d_rev']}", f"{c}{amap['prior_rev']}"
        put(f"{c}{nd_row}", "f", f"IF(AND(ISNUMBER({sd}),ISNUMBER({dI}),ISNUMBER({pI})),IF(AND({pI}<>0,{dI}>0,{dI}>=0.01*{pI}),"
                                 f"{sd}/{dI},NA()),NA())", sty["pct"], S["ind_an"]["new_dollars"][y])
    sh.set(f"B{nd_row}", "s", f"{I['subject']} share of new dollars", sty["lab"])
    rows["IND_AN"] = dict(amap, count=cnt_row, new_dollars=nd_row)
    notes[f"B{amap['roic']}"] = ROIC_NOTE
    sh.set(f"A{r}", "s", "EXCLUDED PLAYERS", sty["sect"])
    for e in I["excluded"]:
        r += 1
        sh.set(f"B{r}", "s", f"{e['name']}: {e['why']}", sty["lab_i"])
    sh.comments = notes

    ic, charts_xml = comparison(I, S, sty, rows, col, exp)
    write_parts(pkg, st, sh, ic, charts_xml)
    pkg.save(out)
    import notebox; notebox.fix(out, out, since=model)   # this tab's note boxes open readable (other tabs untouched)
    layout = {"rows": rows, "expected": exp, "typed_without_note": [t for t in typed if t not in notes]}
    json.dump(layout, open(os.path.join(work, "layout.json"), "w"), indent=1)
    return layout


def comparison(I, S, sty, rows, col, exp):
    years, subj = I["years"], I["subject"]
    first, last = col[years[0]], col[years[-1]]
    ic = Sheet()
    ic.zoom = 117
    for k in range(1, 21):
        ic.widths[k] = 9 if k == 1 else 13      # wider columns, bigger charts
    ic.heights[1] = 22
    ic.set("A1", "s", f"{I['industry']} industry comparison: {subj} against the public players", sty["title"])
    names = ", ".join(c["name"] + (f" ({c['segment']})" if c.get("segment") else "") for c in I["companies"])
    ic.set("A2", "s", f"Included: {names}. Calendar years {years[0]}–{years[-1]}. Data: 'Industry P&L'.", sty["note"])
    ic.set("A3", "s", "Not included: " + ("; ".join(f"{e['name']} ({e['why']})" for e in I["excluded"]) or "none"),
           sty["note"])
    ic.merges += ["A2:T2", "A3:T3"]
    ic.heights[2] = ic.heights[3] = 30
    cat = (f"{P}!${first}$4:${last}$4", years)
    rng = lambda r: f"{P}!${first}${r}:${last}${r}"
    ser = lambda name_r, r, vals, color, **kw: dict({"name_ref": f"{P}!$B${name_r}", "ref": rng(r), "vals": vals,
                                                     "color": color}, **kw)
    yv = lambda d: [d[y] for y in years]
    IND, IA = rows["IND"], rows["IND_AN"]
    peers = [c for c in I["companies"] if c["ticker"] != subj]
    pc = {c["ticker"]: charts.PEERS[k % len(charts.PEERS)] for k, c in enumerate(peers)}
    sa = S["co"][subj]["an"]
    R = rows[subj]
    out = []
    out.append(charts.chart(f"{I['industry']} industry revenue ($M) and growth", cat, [
        {"type": "bar", "axis": 1, "series": [ser(IND["revenue"], IND["revenue"], yv(S["ind"]["revenue"]), charts.BAR,
                                                  name="Industry revenue", labels="#,##0")]},
        {"type": "line", "axis": 2, "series": [
            ser(IA["growth"], IA["growth"], yv(S["ind_an"]["growth"]), charts.INDUSTRY, name="Industry growth", marker=True),
            ser(R["an_growth"], R["an_growth"], yv(sa["growth"]), charts.SUBJECT, name=f"{subj} growth", marker=True)]}],
        {"fmt": "#,##0", "title": "$M"}, {"fmt": "0%", "title": "growth"}))
    out.append(charts.chart("Market share (share of industry revenue)", cat, [
        {"type": "area", "grouping": "stacked", "axis": 1, "series":
            [ser(R["an_share"], R["an_share"], yv(sa["share"]), charts.SUBJECT, name=subj)] +
            [ser(rows[c["ticker"]]["an_share"], rows[c["ticker"]]["an_share"], yv(S["co"][c["ticker"]]["an"]["share"]),
                 pc[c["ticker"]], name=c["ticker"]) for c in peers]}],
        {"fmt": "0%", "title": "share", "min": 0, "max": 1}))
    out.append(charts.chart(f"{subj} share of new dollars vs share of revenue", cat, [
        {"type": "bar", "axis": 1, "series": [ser(IA["new_dollars"], IA["new_dollars"], yv(S["ind_an"]["new_dollars"]),
                                                  charts.SUBJECT, name="Share of new dollars", labels="0%")]},
        {"type": "line", "axis": 1, "series": [ser(R["an_share"], R["an_share"], yv(sa["share"]), charts.INDUSTRY,
                                                   name="Share of revenue", marker=True)]}],
        {"fmt": "0%", "title": "%"}))
    out.append(charts.chart("Gross and operating margin", cat, [
        {"type": "line", "axis": 1, "series": [
            ser(IA["gm"], IA["gm"], yv(S["ind_an"]["gm"]), charts.INDUSTRY, name="Industry gross margin"),
            ser(IA["om"], IA["om"], yv(S["ind_an"]["om"]), charts.INDUSTRY, name="Industry op. margin", dash=True),
            ser(R["an_gm"], R["an_gm"], yv(sa["gm"]), charts.SUBJECT, name=f"{subj} gross margin"),
            ser(R["an_om"], R["an_om"], yv(sa["om"]), charts.SUBJECT, name=f"{subj} op. margin", dash=True)] +
            [ser(rows[c["ticker"]]["an_om"], rows[c["ticker"]]["an_om"], yv(S["co"][c["ticker"]]["an"]["om"]),
                 pc[c["ticker"]], name=f"{c['ticker']} op. margin", thin=True) for c in peers]}],
        dict({"fmt": "0%", "title": "% of revenue"}, **axis_range(*(yv(d[k]) for d in (S["ind_an"], sa)
                                                                     for k in ("gm", "om"))))))
    out.append(charts.chart("ROIC (approx.: NOPAT ÷ avg. operating assets less payables)", cat, [
        {"type": "line", "axis": 1, "series": [
            ser(IA["roic"], IA["roic"], yv(S["ind_an"]["roic"]), charts.INDUSTRY, name="Industry", marker=True),
            ser(R["an_roic"], R["an_roic"], yv(sa["roic"]), charts.SUBJECT, name=subj, marker=True)] +
            [ser(rows[c["ticker"]]["an_roic"], rows[c["ticker"]]["an_roic"], yv(S["co"][c["ticker"]]["an"]["roic"]),
                 pc[c["ticker"]], name=c["ticker"], thin=True) for c in peers]}],
        dict({"fmt": "0%", "title": "ROIC"}, **axis_range(yv(S["ind_an"]["roic"]), yv(sa["roic"])))))
    out.append(charts.chart("Capital cycle: industry capex intensity vs returns", cat, [
        {"type": "bar", "axis": 1, "series": [ser(IA["capex_sales"], IA["capex_sales"], yv(S["ind_an"]["capex_sales"]),
                                                  charts.BAR, name="Capex ÷ sales")]},
        {"type": "line", "axis": 1, "series": [ser(IA["roic"], IA["roic"], yv(S["ind_an"]["roic"]), charts.INDUSTRY,
                                                   name="Industry ROIC", marker=True)]},
        {"type": "line", "axis": 2, "series": [ser(IA["capex_da"], IA["capex_da"], yv(S["ind_an"]["capex_da"]),
                                                   charts.PEERS[1], name="Capex ÷ D&A (right)", marker=True, dash=True)]}],
        {"fmt": "0%", "title": "% of sales / ROIC"}, {"fmt": '0.0"x"', "title": "capex ÷ D&A"}))
    for k, (rr, txt) in enumerate(((5 + 23 + 20, NOTE3), (5 + 46 + 20, NOTE6))):
        c0 = "A" if k == 0 else "K"
        c1 = "I" if k == 0 else "S"
        ic.set(f"{c0}{rr}", "s", txt, sty["note"])
        ic.merges.append(f"{c0}{rr}:{c1}{rr + 1}")
        ic.heights[rr] = ic.heights[rr + 1] = 30
    # peer table
    t0 = 76
    heads = ["Company", "", "", f"Revenue {years[-1]}", "Growth", "Gross margin", "Op. margin", "ROIC", "Capex ÷ sales",
             "FCF margin", "Share"]
    for j, h in enumerate(heads):
        ic.set(f"{colname(j + 1)}{t0}", "s", h, sty["th"])
    ic.merges.append(f"A{t0}:C{t0}")
    ic.heights[t0] = 34
    entries = [(c["name"], c["ticker"]) for c in I["companies"]] + [("Industry", "IND")]
    for i, (name, T) in enumerate(entries):
        rr = t0 + 1 + i
        hl = T == subj
        ic.set(f"A{rr}", "s", name, sty["lab_hl"] if hl else sty["lab"])
        ic.merges.append(f"A{rr}:C{rr}")
        src = rows[T] if T != "IND" else rows["IND"]
        an = (lambda k: rows[T]["an_" + k]) if T != "IND" else (lambda k: rows["IND_AN"][k])
        vals = S["co"][T]["an"] if T != "IND" else S["ind_an"]
        cells = [("revenue", f"{P}!{last}{src['revenue']}", S["co"][T]["lines"]["revenue"][years[-1]] if T != "IND"
                  else S["ind"]["revenue"][years[-1]], "mny")] + \
                [(k, f"{P}!{last}{an(k)}", vals[k][years[-1]], "pct") for k in ("growth", "gm", "om", "roic", "capex_sales",
                                                                                 "fcf_m")] + \
                ([("share", f"{P}!{last}{an('share')}", vals["share"][years[-1]], "pct")] if T != "IND" else [])
        for j, (k, f, want, kind) in enumerate(cells):
            ref = f"{colname(4 + j)}{rr}"
            stl = sty[("pct" if kind == "pct" else "mny") + ("_hl" if hl else "")] if hl else \
                (sty["pct"] if kind == "pct" else sty["calc"])
            ic.set(ref, "f", f, stl)
            exp["IC!" + ref] = want
    return ic, out


def write_parts(pkg, st, pnl, ic, charts_xml):
    pkg.put("xl/styles.xml", st.render())
    pkg.content_default("vml", "application/vnd.openxmlformats-officedocument.vmlDrawing")
    vml_ids = [int(x) for p, data in pkg.parts.items() if p.endswith(".vml")      # Excel writes lists: data="1,2,3"
               for d in re.findall(rb'<o:idmap v:ext="edit" data="([\d,\s]+)"', data) for x in re.findall(rb"\d+", d)]
    nxt_vml = max(vml_ids + [0]) + 1
    for name, sh in (("Industry P&L", pnl), ("Industry Comparison", ic)):
        part = pkg.add_sheet(name, "")
        drid = lrid = None
        if name == "Industry Comparison":
            dn = pkg.free("xl/drawings/drawing{}.xml")
            dpart = f"xl/drawings/drawing{dn}.xml"
            anchors = []
            for k, xml_ in enumerate(charts_xml):
                cn = pkg.free("xl/charts/chart{}.xml")
                cpart = f"xl/charts/chart{cn}.xml"
                pkg.put(cpart, xml_)
                pkg.content_override(cpart, CT["chart"])
                rid = pkg.attach(dpart, "chart", cpart)
                anchors.append(anchor(0 if k % 2 == 0 else 10, 4 + 23 * (k // 2), k + 2, f"Chart {k + 1}", rid))
            pkg.put(dpart, '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
                           '<xdr:wsDr xmlns:xdr="http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing" '
                           'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">' + "".join(anchors) + "</xdr:wsDr>")
            pkg.content_override(dpart, CT["drawing"])
            drid = pkg.attach(part, "drawing", dpart)
        if sh.comments:
            cn = pkg.free("xl/comments{}.xml")
            vn = pkg.free("xl/drawings/vmlDrawing{}.vml")
            cx, vml = comments_parts(sh.comments, nxt_vml)
            nxt_vml += vml_blocks(len(sh.comments))
            pkg.put(f"xl/comments{cn}.xml", cx)
            pkg.put(f"xl/drawings/vmlDrawing{vn}.vml", vml)
            lrid = pkg.attach(part, "vml", f"xl/drawings/vmlDrawing{vn}.vml")
            pkg.attach(part, "comments", f"xl/comments{cn}.xml", CT["comments"])
        pkg.put(part, sh.xml(drid, lrid))
    pkg.finish()


def anchor(col, row, nid, name, rid, ncols=9, nrows=20):
    # two-cell anchor: the chart covers exactly ncols x nrows cells, whatever row height the app draws empty rows at
    # (LibreOffice draws them ~14 pt, so a fixed 320 pt chart ran into the note under it)
    return (f'<xdr:twoCellAnchor editAs="oneCell"><xdr:from><xdr:col>{col}</xdr:col><xdr:colOff>0</xdr:colOff>'
            f'<xdr:row>{row}</xdr:row><xdr:rowOff>0</xdr:rowOff></xdr:from><xdr:to><xdr:col>{col + ncols}</xdr:col>'
            f'<xdr:colOff>0</xdr:colOff><xdr:row>{row + nrows}</xdr:row><xdr:rowOff>0</xdr:rowOff></xdr:to>'
            '<xdr:graphicFrame macro="">'
            f'<xdr:nvGraphicFramePr><xdr:cNvPr id="{nid}" name="{name}"/><xdr:cNvGraphicFramePr/></xdr:nvGraphicFramePr>'
            '<xdr:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/></xdr:xfrm><a:graphic>'
            '<a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/chart">'
            '<c:chart xmlns:c="http://schemas.openxmlformats.org/drawingml/2006/chart" '
            f'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" r:id="{rid}"/>'
            "</a:graphicData></a:graphic></xdr:graphicFrame><xdr:clientData/></xdr:twoCellAnchor>")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--replace", action="store_true")
    a = ap.parse_args()
    L = build(a.model, a.work, a.out, a.replace)
    print(json.dumps({"status": "built", "out": a.out, "cells_checked_later": len(L["expected"]),
                      "typed_without_note": L["typed_without_note"]}, indent=1))
