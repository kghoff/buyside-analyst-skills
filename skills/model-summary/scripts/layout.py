# skills/model-summary/scripts/layout.py
"""Where every SUM cell goes (the course template: left B:D cap table and targets; middle E:N internal estimates,
then the Thesis Summary and Trading Plan boxes; right P:U the probability tree, multiple ranges and the Valuation
Thoughts box; far right W:AA the tactical R/R ladder) and its conditional formatting. Pure: reads the links
(links.collect), the ADV (adv.adv) and the yellow values to write (used); writes through W; returns {name: SUM ref}."""
import datetime as dt

from tabkit import GEN
from xlsx import colname

MNY, PX, PCT, MULT, X, BPS, SHR, DATE, TURNS = ('#,##0;(#,##0)', '$#,##0.00', '0.0%;(0.0%)', '0.0"x"', '0.00"x"',
                                                '#,##0;(#,##0)', '#,##0.0', 'yyyy-mm-dd', '0.0;(0.0)')
GOOD, BAD, AMBER = ("FFC6EFCE", "FF006100"), ("FFFFC7CE", "FF9C0006"), ("FFFFEB9C", "FF9C5700")
BAND = "Street variance band (±)"
# The yellow cells: label -> (columns, rows) from the label cell to the value cell. build.py finds them by label on a
# rerun, so a change of shape never loses what was typed.
INPUT_OFFSET = {"Action": (1, 0), "Buy price": (1, 0), "No-brainer price": (1, 0), BAND: (1, 0),
                "Mgmt contact": (0, 1), "Thesis Summary": (0, 1), "Trading Plan": (0, 1), "Valuation Thoughts": (0, 1)}
PITCH = "Yellow: write-pitch (or you) fills this; a rerun keeps it."


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
    na = lambda ref: w.text(ref, "n/a", i=True)                                          # noqa: E731
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

    head("B6", "Cap table ($M except per share)")
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

    head("B18", "Action prices (write-pitch fills these)")
    for r, name in ((19, "Buy price"), (20, "No-brainer price")):
        w.text(f"B{r}", name)
        w.input_(f"C{r}", name, used[name], PX, PITCH)
        f(f"D{r}", f'IF(ISNUMBER(C{r}),C{r}/$C$7-1,"")', PCT)

    q0, q1 = Md["ntm_quarters"]
    w.text("B22", f"NTM free cash flow (internal: MOD {q0} to {q1})")
    link("C22", Md["ntm_fcf"], MNY)
    w.text("B23", "NTM FCF per share"), f("C23", "IF(C8>0,C22/C8,NA())", PX)
    w.text("B24", "NTM FCF yield"), f("C24", "IF(C9>0,C22/C9,NA())", PCT)

    head("B26", f"3-year target ({kind}, the primary multiple)")
    w.text("B27", I["metric3"]["label"].replace("IRR: ", "")), link("C27", I["metric3"]["ref"], MF)
    w.text("B28", I["mult3"]["label"]), link("C28", I["mult3"]["ref"], XF)
    w.text("B29", "3-year target price"), link("C29", I["price3"]["ref"], PX)
    w.text("B30", "% return"), f("C30", "IF(C29>0,C29/$C$7-1,NA())", PCT)
    w.text("B31", "x money"), f("C31", "IF(C29>0,C29/$C$7,NA())", X)
    w.text("B32", "Years"), link("C32", I["years"]["ref"], "0")
    w.text("B33", "IRR"), link("C33", I["irr"]["ref"], PCT)
    w.text("B34", "IRR hurdle"), link("C34", V["hurdle"], PCT)

    head("B36", "12-month base target")
    w.text("B37", P["ntm1"]["label"]), link("C37", P["ntm1"]["ref"], MF)
    w.text("B38", P["reward_mult"]["label"]), link("C38", P["reward_mult"]["ref"], XF)
    w.text("B39", "12-month target"), link("C39", P["reward_price"]["ref"], PX)
    w.text("B40", "% return"), f("C40", "IF(C39>0,C39/$C$7-1,NA())", PCT)
    w.text("B41", "x money"), f("C41", "IF(C39>0,C39/$C$7,NA())", X)

    head("B43", "12-month risk case")
    w.text("B44", P["risk_metric"]["label"]), link("C44", P["risk_metric"]["ref"], MF)
    w.text("B45", P["risk_mult"]["label"]), link("C45", P["risk_mult"]["ref"], XF)
    w.text("B46", "Risk price"), link("C46", P["risk_price"]["ref"], PX)
    w.text("B47", "% return"), f("C47", "IF(C46>0,C46/$C$7-1,NA())", PCT)

    w.text("B49", "Blended reward / risk"), link("C49", V["blended_rr"], X)
    w.text("B50", "Buy at R/R"), link("C50", V["buy_rr"], X)
    w.text("B51", BAND)
    w.input_("C51", BAND, used[BAND], PCT, "Expected Delta turns green above +band and red below -band. 3% is the "
                                           "skill's default, not a course number; change it here (a rerun keeps it).")
    w.text("B53", "Mgmt contact")
    w.input_("B54", "Mgmt contact", used["Mgmt contact"], GEN, PITCH, wrap=True)
    w.sh.merges.append("B54:C57")
    R.update(price="C7", mcap="C9", ev="C13", adv="C15", ret3="C30", target3="C29", years="C32", irr="C33",
             hurdle="C34", base="C39", risk="C46", blended_rr="C49", buy_rr="C50", band="C51")

    # ---- middle block (E:N): internal estimates, today's price and EV on every year
    yrs = Md["years"]
    cols = [colname(6 + k) for k in range(len(yrs))]
    rows = Md["rows"]
    m = lambda y, r: f"MOD!${Md['col'][y]}${r}"                                         # noqa: E731
    eb = lambda y: "+".join(m(y, r) for r in rows["ebitda"])                             # noqa: E731
    head("E3", "Internal estimates (our model; multiples at today's price and EV)")
    eps_lab = "EPS (non-GAAP)" if Md["basis"] == "ng" else "EPS (GAAP)"
    extra = {"EV/GP": "EV/GP", "FCF yield": "FCF yield"}.get(kind)
    for r, t in ((5, "Revenue"), (6, "% yoy"), (7, "EBITDA"), (8, "% margin"), (9, "bps yoy"), (10, eps_lab),
                 (11, "% yoy"), (12, "Street EPS"), (13, "Expected Delta (ours vs Street)"), (14, "EV/Sales"),
                 (15, "EV/EBITDA"), (16, "P/E"), (17, "Street P/E")) + (((18, extra),) if extra else ()):
        w.text(f"E{r}", t)
    for c, y in zip(cols, yrs):
        p = Md["prev"][y]
        w.text(f"{c}4", y + ("A" if y.isdigit() else ""), b=True)
        link(f"{c}5", m(y, rows["rev"]), MNY)
        link(f"{c}7", eb(y), MNY)
        f(f"{c}8", f"IF({c}5>0,{c}7/{c}5,NA())", PCT)
        link(f"{c}10", m(y, rows["eps"]), PX)
        if p:
            f(f"{c}6", f"IFERROR({m(y, rows['rev'])}/{m(p, rows['rev'])}-1,NA())", PCT)
            f(f"{c}9", f"IFERROR(({c}8-({eb(p)})/{m(p, rows['rev'])})*10000,NA())", BPS)
            f(f"{c}11", f"IF({m(p, rows['eps'])}>0,{m(y, rows['eps'])}/{m(p, rows['eps'])}-1,NA())", PCT)
        else:
            na(f"{c}6"), na(f"{c}9"), na(f"{c}11")
        s = Mu["street"].get(y)
        if s:
            link(f"{c}12", s, PX)
            f(f"{c}13", f"IF(AND({c}12>0,ISNUMBER({c}10)),{c}10/{c}12-1,NA())", PCT)
            f(f"{c}17", f"IF({c}12>0,$C$7/{c}12,NA())", MULT)
        else:
            na(f"{c}12"), na(f"{c}13"), na(f"{c}17")
        f(f"{c}14", f"IF({c}5>0,$C$13/{c}5,NA())", MULT)
        f(f"{c}15", f"IF({c}7>0,$C$13/{c}7,NA())", MULT)
        f(f"{c}16", f"IF({c}10>0,$C$7/{c}10,NA())", MULT)
        if extra == "EV/GP" and rows["gp"]:
            f(f"{c}18", f"IF({m(y, rows['gp'])}>0,$C$13/{m(y, rows['gp'])},NA())", MULT)
        elif extra == "FCF yield":
            f(f"{c}18", f"IF($C$9>0,{m(y, rows['fcf'])}/$C$9,NA())", PCT)
    last = cols[-1]
    tl = cols[0]
    w.sh.cf.append((f"{tl}13:{last}13", f"AND(ISNUMBER({tl}13),{tl}13>$C$51)", w.st.dxf(*GOOD)))
    w.sh.cf.append((f"{tl}13:{last}13", f"AND(ISNUMBER({tl}13),{tl}13<-$C$51)", w.st.dxf(*BAD)))
    head("E20", "Thesis Summary")
    w.input_("E21", "Thesis Summary", used["Thesis Summary"], GEN, PITCH, wrap=True)
    w.sh.merges.append(f"E21:{last}30")
    head("E32", "Trading Plan")
    w.input_("E33", "Trading Plan", used["Trading Plan"], GEN, PITCH, wrap=True)
    w.sh.merges.append(f"E33:{last}42")
    R.update(grid_cols=cols, delta_row=13)

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
    R["tree"] = [5, r]

    r += 2
    for key, title, fmt in (("abs", f"{kind}: own history", XF), ("sp", "GAAP P/E minus the S&P 500 (turns)", TURNS),
                            ("peer", "GAAP P/E minus the core-peer median (turns)", TURNS)):
        rg = Mu["ranges"][key]
        head(f"P{r}", title)
        if rg is None:
            na(f"Q{r}")
            r += 2
            continue
        w.text(f"T{r}", "Today"), link(f"U{r}", rg["today"], fmt)
        r += 1
        for c, h in zip("QRS", ("Min", "Median", "Max")):
            w.text(f"{c}{r}", h, b=True)
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

    # ---- conditional formatting: returns, IRR vs hurdle, R/R vs Buy-at-R/R (both linked from Valuation)
    for rng in ("C30", "C40", "C47", f"T5:T{R['tree'][1]}"):
        _cf_sign(w, rng)
    w.sh.cf.append(("C33", "AND(ISNUMBER(C33),C33>=$C$34)", w.st.dxf(*GOOD)))
    w.sh.cf.append(("C33", "AND(ISNUMBER(C33),C33<$C$34)", w.st.dxf(*BAD)))
    _cf_rr(w, "C49")
    _cf_rr(w, f"AA5:AA{R['ladder'][1]}")
    return R
