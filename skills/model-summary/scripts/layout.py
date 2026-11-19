# skills/model-summary/scripts/layout.py
"""Where every SUM cell goes (the course template: left B:D cap table and targets; middle E:N internal estimates,
then the Thesis Summary and Trading Plan boxes; right P:U the probability tree, multiple ranges and the Valuation
Thoughts box; far right W:AA the tactical R/R ladder), its block formatting (dark-blue title bars, light-blue column
headers, outlines, bold key results) and its conditional formatting. Pure: reads the links
(links.collect), the ADV (adv.adv) and the yellow values to write (used); writes through W; returns {name: SUM ref}."""
import datetime as dt

from links import STREET_MAP

from tabkit import GEN, box, paint
from xlsx import colname

MNY, PX, PCT, MULT, X, BPS, SHR, DATE, TURNS = ('#,##0;(#,##0)', '$#,##0.00', '0.0%;(0.0%)', '0.0"x";(0.0"x")', '0.00"x";(0.00"x")',
                                                '#,##0;(#,##0)', '#,##0.0', 'yyyy-mm-dd', '0.0;(0.0)')
GOOD, BAD, AMBER = ("FFC6EFCE", "FF006100"), ("FFFFC7CE", "FF9C0006"), ("FFFFEB9C", "FF9C5700")
BAND = "Street variance band (±)"
BASIS = "Street EPS basis"
MBAND = "Street margin band (bps)"
# The yellow cells: label -> (columns, rows) from the label cell to the value cell. build.py finds them by label on a
# rerun, so a change of shape never loses what was typed.
INPUT_OFFSET = {"Action": (1, 0), "Buy price": (1, 0), "No-brainer price": (1, 0), BAND: (1, 0), BASIS: (1, 0),
                MBAND: (1, 0),
                "Mgmt contact": (0, 1), "Thesis Summary": (0, 1), "Trading Plan": (0, 1), "Valuation Thoughts": (0, 1)}
NAVY, WHITE, LIGHT, PALE = "FF002060", "FFFFFFFF", "FFBDD7EE", "FFDDEBF7"
PITCH = "Yellow: write-pitch (or you) fills this; a rerun keeps it."


def bar(w, rng):
    """A block's title: a full-width dark-blue bar, white bold text."""
    paint(w, rng, color=WHITE, fill=NAVY, b=True)


def hdr(w, rng, align=None):
    """A column-header row (years, scenario columns, Min / Median / Max): light blue, bold."""
    paint(w, rng, fill=LIGHT, b=True, **({"align": align} if align else {}))


def result(w, rng):
    """A key result row (% return, x money, IRR, EPS, Expected Delta, risk price): bold, pale blue, outlined.
    Never yellow: yellow means only a user input."""
    paint(w, rng, b=True, fill=PALE)
    box(w, rng)


def _cf_sign(w, rng):
    tl = rng.split(":")[0]
    w.sh.cf.append((rng, f"AND(ISNUMBER({tl}),{tl}>0)", w.st.dxf(*GOOD)))
    w.sh.cf.append((rng, f"AND(ISNUMBER({tl}),{tl}<0)", w.st.dxf(*BAD)))


def _cf_rr(w, rng, buy="$C$50"):
    tl = rng.split(":")[0]
    w.sh.cf.append((rng, f"AND(ISNUMBER({tl}),{tl}>={buy})", w.st.dxf(*GOOD)))
    w.sh.cf.append((rng, f"AND(ISNUMBER({tl}),{tl}>=1,{tl}<{buy})", w.st.dxf(*AMBER)))
    w.sh.cf.append((rng, f"AND(ISNUMBER({tl}),{tl}<1)", w.st.dxf(*BAD)))


def lay_out(w, L, adv, used, ticker, today):
    D, V, Mu, Md = L["dcf"], L["val"], L["mult"], L["mod"]
    P, I, kind = V["primary"], V["irr"], V["kind"]
    MF = PX if kind == "P/E" else MNY                         # the primary multiple's metric format
    XF = PCT if kind == "FCF yield" else MULT
    link = lambda ref, tgt, fmt: w.link(ref, tgt, fmt, None, check=False)             # noqa: E731
    f = lambda ref, fm, fmt, b=False: w.formula(ref, fm, fmt, None, b=b, check=False)  # noqa: E731
    na = lambda ref: w.text(ref, "n/a", i=True, align="right")                                          # noqa: E731
    head = lambda ref, t: w.text(ref, t, b=True)                                         # noqa: E731
    R = {}

    # ---- left block (B:D)
    head("B1", f"{ticker} summary: the PM's one-page view. Every number links to the tab it comes from.")
    w.text("B2", "Ticker"), w.typed_text("C2", ticker, "The model's ticker.")
    w.text("B3", "Action")
    if used["Action"] == "=" + V["action"]:
        link("C3", V["action"], GEN)
    else:
        w.input_("C3", "Action", used["Action"], GEN,
                 "Typed over Valuation's verdict; a rerun keeps it. Clear the cell and rerun to link it again.")
    w.inputs["Action"] = "C3"
    w.text("B4", "Last updated")
    w.typed("C4", (today - dt.date(1899, 12, 30)).days, DATE, "The date /model-summary last built this tab.")
    w.restyle("B1", sz=14)
    w.sh.heights[1] = 22
    box(w, "B2:D4")

    per = D.get("period")
    head("B6", "Cap table ($M except per share" + (f"; balance sheet at {per}, the DCF bridge)" if per else ")"))
    w.text("B7", "Price (date beside it)"), link("C7", D["price"], PX), link("D7", D["date"], DATE)
    w.text("B8", "Diluted shares (M)"), link("C8", D["shares"], SHR)
    w.text("B9", "Market cap"), f("C9", "C7*C8", MNY)
    w.text("B10", "Total debt"), link("C10", f"{D['debt_cur']}+{D['debt_lt']}", MNY)
    w.text("B11", "Cash & short-term securities"), link("C11", f"{D['cash']}+{D['st']}", MNY)
    w.text("B12", "Net debt"), link("C12", D["net_debt"], MNY)
    w.text("B13", "Enterprise value"), f("C13", "C9+C12", MNY)
    w.text("B14", "Cash per share"), f("C14", "IF(C8>0,C11/C8,NA())", PX)
    w.text("B15", "3M ADV (M shares)")
    if adv["route"] == "multiples":
        link("C15", f"{adv['ref']}/1000000", SHR)
        w.notes["C15"] = adv["note"]
    else:
        w.typed("C15", adv["value"], SHR, adv["note"])
    w.text("B16", "3M ADV ($M)"), f("C16", "C15*C7", MNY)
    bar(w, "B6:D6"), box(w, "B6:D16", "medium")

    head("B18", "Action prices (write-pitch fills these)")
    for r, name in ((19, "Buy price"), (20, "No-brainer price")):
        w.text(f"B{r}", name)
        w.input_(f"C{r}", name, used[name], PX, PITCH)
        f(f"D{r}", f'IF(ISNUMBER(C{r}),C{r}/$C$7-1,"")', PCT)
    bar(w, "B18:D18"), box(w, "B18:D20")

    q0, q1 = Md["ntm_quarters"]
    w.text("B22", f"NTM free cash flow (internal: MOD {q0} to {q1})")
    link("C22", Md["ntm_fcf"], MNY)
    w.text("B23", "NTM FCF per share"), f("C23", "IF(C8>0,C22/C8,NA())", PX)
    w.text("B24", "NTM FCF yield"), f("C24", "IF(C9>0,C22/C9,NA())", PCT)
    hdr(w, "B22:D22"), box(w, "B22:D24")

    head("B26", f"3-year target ({kind}, the primary multiple)")
    w.text("B27", I["metric3"]["label"].replace("IRR: ", "")), link("C27", I["metric3"]["ref"], MF)
    w.text("B28", I["mult3"]["label"]), link("C28", I["mult3"]["ref"], XF)
    w.text("B29", "3-year target price"), link("C29", I["price3"]["ref"], PX)
    w.text("B30", "% return"), f("C30", "IF(C29>0,C29/$C$7-1,NA())", PCT)
    w.text("B31", "x money"), f("C31", "IF(C29>0,C29/$C$7,NA())", X)
    w.text("B32", "Years"), link("C32", I["years"]["ref"], "0")
    w.text("B33", "IRR"), link("C33", I["irr"]["ref"], PCT)
    w.text("B34", "IRR hurdle"), link("C34", V["hurdle"], PCT)
    bar(w, "B26:D26"), result(w, "B30:D31"), result(w, "B33:D33"), box(w, "B26:D34")

    head("B36", f"12-month base target ({kind} only)")
    w.text("B37", P["ntm1"]["label"]), link("C37", P["ntm1"]["ref"], MF)
    w.text("B38", P["reward_mult"]["label"]), link("C38", P["reward_mult"]["ref"], XF)
    w.text("B39", "12-month target"), link("C39", P["reward_price"]["ref"], PX)
    w.text("B40", "% return"), f("C40", "IF(C39>0,C39/$C$7-1,NA())", PCT)
    w.text("B41", "x money"), f("C41", "IF(C39>0,C39/$C$7,NA())", X)
    bar(w, "B36:D36"), result(w, "B40:D41"), box(w, "B36:D41")

    head("B43", f"12-month risk case ({kind} only)")
    w.text("B44", P["risk_metric"]["label"]), link("C44", P["risk_metric"]["ref"], MF)
    w.text("B45", P["risk_mult"]["label"]), link("C45", P["risk_mult"]["ref"], XF)
    w.text("B46", "Risk price"), link("C46", P["risk_price"]["ref"], PX)
    w.text("B47", "% return"), f("C47", "IF(C46>0,C46/$C$7-1,NA())", PCT)
    bar(w, "B43:D43"), result(w, "B46:D47"), box(w, "B43:D47")

    w.text("B49", "Blended reward / risk"), link("C49", V["blended_rr"], X)
    w.text("B50", "Buy at R/R"), link("C50", V["buy_rr"], X)
    w.text("B51", BAND)
    w.input_("C51", BAND, used[BAND], PCT, "Expected Delta turns green above +band and red below -band. 3% is the "
                                           "skill's default, not a course number; change it here (a rerun keeps it).")
    w.text("B52", BASIS)
    w.input_("C52", BASIS, used[BASIS], GEN, "auto = the basis closest to the Street's current-year EPS; type GAAP or "
                                             "non-GAAP to force it, then rerun /model-summary.")
    w.text("B53", MBAND)
    w.input_("C53", MBAND, used[MBAND], BPS, "Margin deltas (bps) turn green above +band and red below -band. 50 bps "
                                            "is the skill's default, not a course number; change it here (a rerun "
                                            "keeps it).")
    w.text("B55", "Mgmt contact")
    w.input_("B56", "Mgmt contact", used["Mgmt contact"], GEN, PITCH, wrap=True)
    w.sh.merges.append("B56:D59")
    box(w, "B49:D53"), bar(w, "B55:D55"), box(w, "B56:D59")
    R.update(price="C7", mcap="C9", ev="C13", adv="C15", ret3="C30", target3="C29", years="C32", irr="C33",
             hurdle="C34", base="C39", risk="C46", blended_rr="C49", buy_rr="C50", band="C51", basis="C52",
             margin_band="C53")

    # ---- middle block (E:N): internal estimates, today's price and EV on every year
    yrs = Md["years"]
    cols = [colname(6 + k) for k in range(len(yrs))]
    rows = Md["rows"]
    m = lambda y, r: f"MOD!${Md['col'][y]}${r}"                                         # noqa: E731
    eb = lambda y: "+".join(m(y, r) for r in rows["ebitda"])                             # noqa: E731
    head("E3", "Internal estimates (our model; multiples at today's price and EV)")
    St, sb = L["street"], L["street_basis"]
    word = "non-GAAP" if Md["basis"] == "ng" else "GAAP"
    why = {"auto": "the Street's basis", "px_data": "Px Data's basis"}.get(sb["source"]) or (
        "the Street's basis" if sb["chosen"] == sb.get("auto") else "your override")
    eb_lab = "EBITDA (adjusted)" if Md.get("ebitda_adj") else "EBITDA (operating income + D&A)"
    extra = {"EV/GP": "EV/GP", "FCF yield": "FCF yield"}.get(kind)
    by_key = {k: (kd, nm) for k, kd, nm in STREET_MAP.values()}
    street = {"eps": {}, "rev": {}, **St["metrics"]}          # EPS and revenue always show (n/a when empty)

    def st_rows(*keys):                                       # a Street row and a delta row per metric it has
        out = []
        for k in keys:
            if k in street:
                kd, nm = by_key[k]
                out += [(f"s_{k}", f"Street {nm}"), (f"d_{k}", "Expected Delta (ours vs Street)" if k == "eps" else
                                                     f"{nm[0].upper()}{nm[1:]} delta (ours vs Street"
                                                     + (", bps)" if kd == "margin" else ")"))]
        return out
    seq = ([("rev", "Revenue"), ("rev_g", "% yoy")] + st_rows("rev")
           + ([("gm", "Gross margin")] + st_rows("gm") if "gm" in street else [])
           + [("ebitda", eb_lab), ("margin", "% margin"), ("bps", "bps yoy")] + st_rows("ebitda", "ebitda_m")
           + ([("om", "Operating margin")] + st_rows("om") if "om" in street else [])
           + [("eps", f"EPS ({word}, {why})"), ("eps_g", "% yoy")] + st_rows("eps")
           + [("ev_s", "EV/Sales"), ("ev_e", "EV/EBITDA"), ("pe", "P/E"), ("s_pe", "Street P/E")]
           + ([("extra", extra)] if extra else []))
    rw = {n: 5 + k for k, (n, _) in enumerate(seq)}
    for n, t in seq:
        w.text(f"E{rw[n]}", t)
    names = [n for n, _ in seq]
    c_ = lambda n, c: f"{c}{rw[n]}"                                                      # noqa: E731
    ours = {"eps": "eps", "rev": "rev", "ebitda": "ebitda", "ebitda_m": "margin", "gm": "gm", "om": "om"}
    sfmt = {"eps": PX, "rev": MNY, "ebitda": MNY}

    def note(n):
        d = St["snapshot"]
        return (f"Consensus snapshot {d}" + (f", {n} analysts" if n else "") if St["source"] == "consensus" else
                "Multiples forward table (Yahoo consensus, analysts' basis); no analyst count there.")

    for c, y in zip(cols, yrs):
        p = Md["prev"][y]
        w.text(f"{c}4", y + ("A" if y.isdigit() else ""), b=True, align="right")
        link(c_("rev", c), m(y, rows["rev"]), MNY)
        link(c_("ebitda", c), eb(y), MNY)
        f(c_("margin", c), f"IF({c_('rev', c)}>0,{c_('ebitda', c)}/{c_('rev', c)},NA())", PCT)
        for k, r_ in (("gm", rows["gp"]), ("om", rows["oi"])):
            if k in rw:
                f(c_(k, c), f"IF({c_('rev', c)}>0,{m(y, r_)}/{c_('rev', c)},NA())", PCT)
        link(c_("eps", c), m(y, rows["eps"]), PX)
        if p:
            f(c_("rev_g", c), f"IFERROR({m(y, rows['rev'])}/{m(p, rows['rev'])}-1,NA())", PCT)
            f(c_("bps", c), f"IFERROR(({c_('margin', c)}-({eb(p)})/{m(p, rows['rev'])})*10000,NA())", BPS)
            f(c_("eps_g", c), f"IF({m(p, rows['eps'])}>0,{m(y, rows['eps'])}/{m(p, rows['eps'])}-1,NA())", PCT)
        else:
            na(c_("rev_g", c)), na(c_("bps", c)), na(c_("eps_g", c))
        for k, yrs_k in street.items():
            s, sr, dr, o = yrs_k.get(y), c_(f"s_{k}", c), c_(f"d_{k}", c), c_(ours[k], c)
            if not s:
                na(sr), na(dr)
                continue
            if by_key[k][0] == "margin":
                link(sr, s["ref"], PCT)
                f(dr, f"IF(AND(ISNUMBER({sr}),ISNUMBER({o})),({o}-{sr})*10000,NA())", BPS)
            else:
                link(sr, s["ref"], sfmt[k])
                f(dr, f"IF(AND({sr}>0,ISNUMBER({o})),{o}/{sr}-1,NA())", PCT)
            w.notes[sr] = note(s["n"])
        s = street.get("eps", {}).get(y)
        if s:
            f(c_("s_pe", c), f"IF({c_('s_eps', c)}>0,$C$7/{c_('s_eps', c)},NA())", MULT)
            w.notes[c_("s_pe", c)] = note(s["n"])
        else:
            na(c_("s_pe", c))
        f(c_("ev_s", c), f"IF({c_('rev', c)}>0,$C$13/{c_('rev', c)},NA())", MULT)
        f(c_("ev_e", c), f"IF({c_('ebitda', c)}>0,$C$13/{c_('ebitda', c)},NA())", MULT)
        f(c_("pe", c), f"IF({c_('eps', c)}>0,$C$7/{c_('eps', c)},NA())", MULT)
        if extra == "EV/GP" and rows["gp"]:
            f(c_("extra", c), f"IF({m(y, rows['gp'])}>0,$C$13/{m(y, rows['gp'])},NA())", MULT)
        elif extra == "FCF yield":
            f(c_("extra", c), f"IF($C$9>0,{m(y, rows['fcf'])}/$C$9,NA())", PCT)
    last = cols[-1]
    assert last <= "N" and len(last) == 1, f"the estimates grid ran past column N ({last}); it would hit the scenario block"
    tl = cols[0]
    deltas = [n for n in names if n.startswith("d_")]
    for n in deltas:                                          # levels on the % band, margins on the bps band
        r_, th = rw[n], "$C$53" if by_key[n[2:]][0] == "margin" else "$C$51"
        w.sh.cf.append((f"{tl}{r_}:{last}{r_}", f"AND(ISNUMBER({tl}{r_}),{tl}{r_}>{th})", w.st.dxf(*GOOD)))
        w.sh.cf.append((f"{tl}{r_}:{last}{r_}", f"AND(ISNUMBER({tl}{r_}),{tl}{r_}<-{th})", w.st.dxf(*BAD)))
    bar(w, f"E3:{last}3"), hdr(w, f"E4:{last}4")
    for n in ["eps"] + deltas:
        result(w, f"E{rw[n]}:{last}{rw[n]}")
    for c in ["E"] + cols:                                    # the multiples rows sit apart from the P&L rows
        w.edge(f"{c}{rw['ev_s']}", top="thin")
    end = 5 + len(names) - 1
    box(w, f"E3:{last}{end}")
    t1 = end + 2                                              # Thesis Summary bar; the boxes follow, 10 rows each
    t2 = t1 + 12
    head(f"E{t1}", "Thesis Summary")
    w.input_(f"E{t1 + 1}", "Thesis Summary", used["Thesis Summary"], GEN, PITCH, wrap=True)
    w.sh.merges.append(f"E{t1 + 1}:{last}{t1 + 10}")
    head(f"E{t2}", "Trading Plan")
    w.input_(f"E{t2 + 1}", "Trading Plan", used["Trading Plan"], GEN, PITCH, wrap=True)
    w.sh.merges.append(f"E{t2 + 1}:{last}{t2 + 10}")
    for t in (t1, t2):
        bar(w, f"E{t}:{last}{t}"), box(w, f"E{t + 1}:{last}{t + 10}")
    R.update(grid_cols=cols, delta_row=rw.get("d_eps"), rev_delta_row=rw.get("d_rev"), eps_row=rw["eps"], rows=rw,
             thesis_row=t1, plan_row=t2)

    # ---- right block (P:U): Valuation's probability tree, row for row
    metric_word = P["ntm1"]["label"].split("NTM+1 ", 1)[1].split(" (")[0]
    head("P3", "1-year return scenarios (Valuation's probability tree)")
    for c, h in zip("PQRSTU", ("Scenario", metric_word, kind, "Target", "% return", "Probability")):
        w.text(f"{c}4", h, b=True)
    r = 5
    for br in V["tree"]:
        w.text(f"P{r}", br["name"])
        if br["case"] == "reward":
            link(f"Q{r}", P["ntm1"]["ref"], MF), link(f"R{r}", P["reward_mult"]["ref"], XF)
        elif br["case"] == "risk":
            link(f"Q{r}", P["risk_metric"]["ref"], MF), link(f"R{r}", P["risk_mult"]["ref"], XF)
        else:
            na(f"Q{r}"), na(f"R{r}")
        link(f"S{r}", br["target"], PX), link(f"T{r}", br["ret"], PCT), link(f"U{r}", br["prob"], PCT)
        r += 1
    w.text(f"P{r}", "Probability-weighted", b=True)
    link(f"S{r}", V["tree_ev"]["target"], PX), link(f"T{r}", V["tree_ev"]["ret"], PCT)
    link(f"U{r}", V["tree_ev"]["prob"], PCT)
    bar(w, "P3:U3"), hdr(w, "P4:P4"), hdr(w, "Q4:U4", "right"), result(w, f"P{r}:U{r}"), box(w, f"P3:U{r}")
    R["tree"] = [5, r]

    r += 2
    for key, title, fmt in (("abs", f"{kind}: own history", XF), ("sp", "GAAP P/E minus the S&P 500 (turns)", TURNS),
                            ("peer", "GAAP P/E minus the core-peer median (turns)", TURNS)):
        rg = Mu["ranges"][key]
        head(f"P{r}", title)
        if rg is None:
            na(f"Q{r}")
            bar(w, f"P{r}:U{r}"), box(w, f"P{r}:U{r}")
            r += 2
            continue
        w.text(f"T{r}", "Today"), link(f"U{r}", rg["today"], fmt)
        bar(w, f"P{r}:S{r}"), hdr(w, f"T{r}:U{r}", "right"), box(w, f"P{r}:U{r + 4}")
        r += 1
        for c, h in zip("QRS", ("Min", "Median", "Max")):
            w.text(f"{c}{r}", h, b=True)
        hdr(w, f"P{r}:P{r}"), hdr(w, f"Q{r}:S{r}", "right")
        r += 1
        for y in ("1 year", "5 years", "10 years"):
            w.text(f"P{r}", y)
            for c, s in zip("QRS", ("min", "median", "max")):
                ref = rg[f"{y} {s}"]
                link(f"{c}{r}", ref, fmt) if ref else na(f"{c}{r}")
            r += 1
        r += 1
    head(f"P{r}", "Valuation Thoughts")
    w.input_(f"P{r + 1}", "Valuation Thoughts", used["Valuation Thoughts"], GEN, PITCH, wrap=True)
    w.sh.merges.append(f"P{r + 1}:U{r + 10}")
    bar(w, f"P{r}:U{r}"), box(w, f"P{r + 1}:U{r + 10}")

    # ---- far right (W:AA): the tactical R/R ladder
    head("W3", "Tactical R/R (Valuation's blended ladder)")
    for c, h in zip(("W", "X", "Y", "Z", "AA"), ("% move", "Entry price", "Reward", "Risk", "R/R")):
        w.text(f"{c}4", h, b=True)
    r = 5
    for rung in V["ladder"]:
        link(f"W{r}", rung["move"], PCT), link(f"X{r}", rung["entry"], PX), link(f"Y{r}", rung["reward"], PCT)
        link(f"Z{r}", rung["risk"], PCT), link(f"AA{r}", rung["rr"], X)
        r += 1
    R["ladder"] = [5, r - 1]
    bar(w, "W3:AA3"), hdr(w, "W4:AA4", "right"), box(w, f"W3:AA{r - 1}")
    w.sh.heights[4] = 16                     # right-aligned headers wrap; keep the header row one line high

    # ---- conditional formatting: returns, IRR vs hurdle, R/R vs Buy-at-R/R (both linked from Valuation)
    for rng in ("C30", "C40", "C47", f"T5:T{R['tree'][1]}"):
        _cf_sign(w, rng)
    w.sh.cf.append(("C33", "AND(ISNUMBER(C33),C33>=$C$34)", w.st.dxf(*GOOD)))
    w.sh.cf.append(("C33", "AND(ISNUMBER(C33),C33<$C$34)", w.st.dxf(*BAD)))
    _cf_rr(w, "C49")
    _cf_rr(w, f"AA5:AA{R['ladder'][1]}")
    return R
