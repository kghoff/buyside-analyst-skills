# skills/model-short/scripts/build.py
"""Writes the Short Check tab into a copy of the user's model by raw-XML editing (xlsx.py); every other part of the
workbook stays byte-identical (checked here: build stops if anything else changed). Yellow = the agent's suggestion,
the user's to change (blue on yellow, a note with the agent's value, anchor and reason); blue = typed from a source
(note names it); black = formulas; green = links to other tabs.

A rerun keeps every yellow cell the user changed, and a ✓ / ✗ / ? the user typed over a code tick. Records W/layout.json
(the value each checked cell must recalculate to: shortmath on context.json and the resolved inputs) for verify.py
and note.py, and W/inputs_written.next.json (SKILL step 8 renames it once the copy replaces the model).

usage: python3 build.py --model M --work W --ticker T --out OUT.xlsx [--borrow 0.03]"""
import argparse
import json
import os
import re
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))   # run with python3 -I
import shortmath as sm  # noqa: E402
from xlsx import CT, Package, Sheet, Styles, comments_parts, esc, relpath_of, resolve  # noqa: E402

TAB, AFTER = "Short Check", "Valuation"
PRICE = "$B$4"                            # the typed price; tick formulas and the header refer to it
BLUE, BLACK, GREEN, RED, YELLOW = "FF0000FF", "FF000000", "FF008000", "FFC00000", "FFFFFF00"
PCT, MULT, MONEY, NUM, MILL, GEN = "0.0%", '0.0"x"', "$#,##0.00", "0.00", "#,##0", "General"
FORMULA = "FORMULA"                       # a code tick left to its formula
INPUTS = [  # key, label (unique in column A), format
    ("verdict", "Verdict (agent's call)", GEN), ("type", "Short type", GEN), ("bucket", "Alpha bucket", GEN),
    ("catalyst_soon", "Catalyst within the next two prints (Y/N)", GEN), ("takeout_prone", "Takeout candidate (Y/N)", GEN),
    ("hurdle", "IRR hurdle", PCT), ("reward_eps", "Reward case: EPS", MONEY), ("reward_pe", "Reward case: P/E", MULT),
    ("dream_eps", "Dream case: EPS", MONEY), ("dream_pe", "Dream case: P/E", MULT),
    ("takeout_premium", "Takeout premium", PCT), ("print_miss", "Print: EPS miss", PCT),
    ("print_pe_slip", "Print: P/E slip (turns)", NUM), ("crowded_line", "Crowded line (short % of float)", PCT),
    ("borrow", "Borrow rate (prime broker)", PCT), ("fund", "Fund size ($M)", MILL),
    ("bps", "Risk budget per idea (bps)", MILL), ("short_book", "Short book ($M)", MILL),
]
LABEL = {k: lab for k, lab, _ in INPUTS}
FMT = {k: f for k, _, f in INPUTS}
ROWLABEL = {rid: lab for rid, _, lab, _ in sm.ROWS}
TICKF = {  # tick formulas of the computed rows; {r} = the row; mirror shortmath.code_ticks
    "decel": 'IF(ISNUMBER(C{r}),IF(C{r}<=-0.01,"✓","✗"),"?")',
    "incr_margin": 'IF(AND(ISNUMBER(C{r}),ISNUMBER(D{r})),IF(OR(C{r}<D{r},IF(ISNUMBER(E{r}),E{r}>=0.95,FALSE)),"✓","✗"),"?")',
    "capex": 'IF(ISNUMBER(C{r}),IF(C{r}>=1.5,"✓","✗"),"?")',
    "leaky": 'IF(ISNUMBER(C{r}),IF(C{r}>=0.25,"✓","✗"),"?")',
    "fcf": 'IF(ISNUMBER(C{r}),IF(C{r}<0.7,"✓","✗"),"?")',
    "revisions": 'IF(ISNUMBER(C{r}),IF(C{r}<=-0.01,"✓","✗"),"?")',
    "vs_dcf": 'IF(ISNUMBER(C{r}),IF(N({price})>C{r},"✓","✗"),"?")',
    "vs_peers": 'IF(ISNUMBER(D{r}),IF(D{r}>=0.7,"✓","✗"),"?")',
    "vs_history": 'IF(ISNUMBER(D{r}),IF(D{r}>=0.7,"✓","✗"),"?")',
    "vs_algo": 'IF(ISNUMBER(C{r}),IF(C{r}>0,"✓","✗"),"?")',
}
RULE = {"decel": "✓ at −1.0 pt or worse", "incr_margin": "✓ if incremental < TTM margin, or TTM ≥ 95% of the 10-yr FY peak (E)",
        "capex": "✓ at 1.5x or more", "leaky": "✓ at 25% or more", "fcf": "✓ under 70%; D = P/E ÷ conversion",
        "revisions": "✓ at −1% or worse", "vs_dcf": "✓ if the price is above it",
        "vs_peers": "✓ at the 70th percentile or higher (D)", "vs_history": "✓ at the 70th percentile or higher (D)",
        "vs_algo": "✓ if the wedge (section B) is above 0"}


def _same(a, b):
    if sm._n(a) and sm._n(b):
        return abs(a - b) <= 1e-9 * max(1.0, abs(a), abs(b))
    return str(a).strip() == str(b).strip()


def resolve_values(existing, written, new):
    """Per label: (value to write, the user's?). existing = {label: value} on the tab now (None: no tab); written =
    {label: {"value", "user"}} from the last build (None: no record); new = the agent's values now. A value is the
    user's when it differs from what the last build wrote (with no record: from the agent's value), or was the
    user's before."""
    used, users = {}, set()
    for label, v in new.items():
        cur = (existing or {}).get(label)
        if cur is None:
            used[label] = v
            continue
        rec = (written or {}).get(label)
        theirs = (rec.get("user") or not _same(cur, rec.get("value"))) if rec else (existing is not None and not _same(cur, v))
        used[label] = cur if theirs else v
        if theirs:
            users.add(label)
    return used, users


def code_formula(rid, r):
    return "=" + TICKF[rid].format(r=r, price=PRICE)


def read_tab(path, data_only):
    """{column-A label: column-B value} of the Short Check tab (None if absent or no file). A tick cell holding the
    code's own tick formula for its row reads as FORMULA; any other formula (the user's) stays as written."""
    import openpyxl
    if not path or not os.path.exists(path):
        return None
    wb = openpyxl.load_workbook(path, read_only=True, data_only=data_only)
    if TAB not in wb.sheetnames:
        wb.close()
        return None
    rid_of = {lab: rid for rid, _, lab, computed in sm.ROWS if computed}
    out = {}
    for row in wb[TAB].iter_rows(min_row=1, max_col=2):
        a = row[0]
        if getattr(a, "value", None) is None:
            continue
        lab, v = str(a.value).strip(), row[1].value if len(row) > 1 else None
        if lab in rid_of and isinstance(v, str) and v == code_formula(rid_of[lab], a.row):
            v = FORMULA
        out[lab] = v
    wb.close()
    return out


class W:
    """Cell writer: styles, kinds (typed / link / formula / input / text), notes, expected values, number formats."""

    def __init__(self, st, users=()):
        self.sh, self.st, self.s, self.users = Sheet(), st, {}, set(users)
        self.expected, self.notes, self.inputs, self.kinds, self.fmt, self.col_a = {}, {}, {}, {}, {}, {}

    def style(self, color=BLACK, fmt=GEN, b=False, i=False, fill=None, sz=11, wrap=False):
        k = (color, fmt, b, i, fill, sz, wrap)
        if k not in self.s:
            self.s[k] = self.st.xf(color=color, fmt=fmt, b=b, i=i, fill=fill, sz=sz, align="left" if wrap else None)
        return self.s[k]

    def text(self, ref, t, color=BLACK, b=False, i=False, sz=11, wrap=False):
        self.sh.set(ref, "s", str(t), self.style(color, GEN, b, i, None, sz, wrap))
        self.kinds.setdefault(ref, "text")
        if re.fullmatch(r"A\d+", ref):
            self.col_a[ref] = str(t)

    def typed(self, ref, v, fmt, note):
        if not sm._n(v):
            return self.text(ref, "n/a", i=True)
        self.sh.set(ref, "n", v, self.style(BLUE, fmt))
        self.kinds[ref], self.notes[ref], self.fmt[ref] = "typed", note, fmt
        self.expected[ref] = v                    # note.py reads every number from 'expected'

    def link(self, ref, target, fmt, expect):
        self.sh.set(ref, "f", target, self.style(GREEN, fmt))
        self.kinds[ref], self.expected[ref], self.fmt[ref] = "link", expect, fmt

    def formula(self, ref, f, fmt, expect, b=False):
        self.sh.set(ref, "f", f, self.style(BLACK, fmt, b=b))
        self.kinds[ref], self.expected[ref], self.fmt[ref] = "formula", expect, fmt

    def input_(self, ref, label, v, fmt, note):
        if isinstance(v, str) and v.startswith("="):
            kind, val = "f", v[1:]
        else:
            kind, val = ("n", v) if sm._n(v) else ("s", str(v))
        self.sh.set(ref, kind, val, self.style(BLUE, fmt, fill=YELLOW))
        self.kinds[ref], self.inputs[label], self.notes[ref], self.fmt[ref] = "input", ref, note, fmt


def _note(x):
    a = f"anchor {x.get('anchor', 'judgment')}" + (f" = {x['anchor_value']}" if "anchor_value" in x else "")
    return f"Agent: {x.get('value', x.get('tick'))} | {a} | {x.get('reason', '')}"


def agent_values(plan, borrow):
    v = {LABEL["verdict"]: plan["verdict"]["value"], LABEL["type"]: plan["type"]["value"],
         LABEL["bucket"]: plan["bucket"]["value"], LABEL["catalyst_soon"]: "Y" if plan["catalyst"]["soon"] else "N",
         LABEL["takeout_prone"]: "Y" if plan["takeout_prone"]["value"] else "N",
         LABEL["borrow"]: borrow if sm._n(borrow) else "check with PB"}
    for k in (*sm.HOUSE, *sm.AGENT_INPUTS):
        v[LABEL[k]] = plan["inputs"][k]["value"]
    return v


def tick_values(plan, code):
    """The agent's value per tick label: FORMULA where it agrees with code on a computed row, else ✓ / ✗ / ?."""
    out = {}
    for rid, _, lab, computed in sm.ROWS:
        t = plan["ticks"][rid]["tick"]
        out[lab] = FORMULA if computed and t == code[rid] else sm.TICK[t]
    return out


def _calc(v, lab, values_tab):
    """A cell's value for the math: a user's formula counts at its recalculated value (from the values copy)."""
    return (values_tab or {}).get(lab) if isinstance(v, str) and v.startswith("=") else v


def _math(used, values_tab):
    """Plain values for shortmath, keyed as shortmath's inputs, plus borrow and catalyst_soon."""
    return {k: _calc(used[LABEL[k]], LABEL[k], values_tab)
            for k in (*sm.HOUSE, *sm.AGENT_INPUTS, "borrow", "catalyst_soon")}


def _yes(v):
    """The tab's ="Y" test: Excel compares text without case."""
    return isinstance(v, str) and v.upper() == "Y"


def lay_out(w, ctx, plan, used, tick_used, s, ticker, unverified, R_pre):
    """Every cell below the header inputs (rows 6-10, written by build()). R_pre holds their refs: the verdict
    formula reads the catalyst cell. Returns all refs."""
    R, M, Lk, sh = dict(R_pre), ctx["metrics"], ctx["links"], ctx.get("short") or {}
    later = []
    yahoo = f"{sh.get('source', 'Yahoo Finance')}, {sh.get('asof', '')}"
    reasons = {k: plan["inputs"][k] for k in (*sm.HOUSE, *sm.AGENT_INPUTS)}
    reasons.update(borrow={"value": used[LABEL["borrow"]], "anchor": "the user",
                           "reason": "Your prime broker's rate." if sm._n(used[LABEL["borrow"]]) else
                           "Unknown: check with your prime broker. Drag at 5% and 20% shown below."})

    def mf(name):
        return (M.get(name) or {}).get("formula")

    def mv(name):
        return (M.get(name) or {}).get("value")

    def put_input(r, key):
        lab = LABEL[key]
        x = reasons.get(key) or {}
        w.text(f"A{r}", lab)
        note = _note(x) if lab not in w.users else f"You typed {used[lab]}. " + _note(x)
        w.input_(f"B{r}", lab, used[lab], FMT[key], note)
        why = str(x.get("reason", ""))
        if key in unverified:
            w.text(f"G{r}", "UNVERIFIED: " + why, color=RED, wrap=True)
        else:
            w.text(f"G{r}", why, wrap=True)
        R[key] = f"$B${r}"

    w.text("A1", f"{ticker} short check: is there a short here, and what kind (Chapter 12, FEV)", b=True, sz=14)
    w.text("A2", "Yellow = the agent's suggestion, yours to change (note: its value, anchor and reason). Blue = typed "
                 "from a source. Black = formulas. Green = links to other tabs. Ticks: type ✓, ✗ or ?.", i=True)
    w.text("A4", "Price")
    w.typed("B4", ctx["price"]["value"], MONEY, ctx["price"]["source"])
    R["price"] = PRICE
    if "valuation_price" in Lk:
        vp = Lk["valuation_price"]
        w.text("C4", "Valuation tab price")
        w.link("D4", vp["ref"], MONEY, vp["value"])
        d = sm.div(ctx["price"]["value"], vp["value"])
        stale = None if d is None else ("stale: rerun /model-valuation" if abs(d - 1) > sm.STALE_TOL else "price ok")
        w.formula("E4", f'IFERROR(IF(ABS(B4/D4-1)>{sm.STALE_TOL},"stale: rerun /model-valuation","price ok"),NA())',
                  GEN, stale)

    # ---- A. scorecard
    r = 13
    w.text(f"A{r}", "A. FEV scorecard (a short wants all three)", b=True)
    for c, h in zip("BCDEFG", ("Tick", "Evidence", "Also", "Also", "Rule", "Anchor / reason")):
        w.text(f"{c}{r}", h, b=True)
    r += 1
    span = {}
    for dim, title in (("F", "FUNDAMENTALS"), ("E", "EXPECTATIONS"), ("V", "VALUATION")):
        w.text(f"A{r}", title, b=True)
        r += 1
        first = r
        for rid, d, lab, computed in sm.ROWS:
            if d != dim:
                continue
            w.text(f"A{r}", lab)
            tv = tick_used[lab]
            if computed and tv == FORMULA:
                w.formula(f"B{r}", TICKF[rid].format(r=r, price=R["price"]), GEN, sm.TICK[s["code"][rid]])
            else:
                t = plan["ticks"][rid]
                note = _note(t) if lab not in w.users else f"You typed {tv}. " + _note(t)
                w.input_(f"B{r}", lab, tv, GEN, note)
            if computed:
                w.text(f"F{r}", RULE[rid], i=True)
            reason = plan["ticks"][rid].get("reason", "")
            if plan["ticks"][rid].get("anchor"):
                reason += f" [{plan['ticks'][rid]['anchor']}]"
            w.text(f"G{r}", ("UNVERIFIED: " if f"ticks.{rid}" in unverified else "") + reason,
                   color=RED if f"ticks.{rid}" in unverified else BLACK, wrap=True)
            _evidence(w, rid, r, M, Lk, R, s, later)
            R[f"tick_{rid}"] = f"$B${r}"
            r += 1
        span[dim] = (first, r - 1)
    for dim, name in (("F", "Fundamentals"), ("E", "Expectations"), ("V", "Valuation")):
        a, b = span[dim]
        w.text(f"A{r}", f"{name}: ✓ count (passes at {sm.NEED[dim]})", b=True)
        w.formula(f"B{r}", f'COUNTIF(B{a}:B{b},"✓")', GEN, s["counts"][dim], b=True)
        w.formula(f"C{r}", f"B{r}>={sm.NEED[dim]}", GEN, s["passes"][dim], b=True)
        R[f"count_{dim}"], R[f"pass_{dim}"] = f"$B${r}", f"$C${r}"
        r += 1
    for k, sm_ in enumerate(plan.get("smoke") or []):
        w.text(f"A{r}", f"Smoke: {sm_['flag']}", color=RED)
        w.text(f"G{r}", ("UNVERIFIED: " if f"smoke[{k}]" in unverified else "") + f"{sm_['quote']} [{sm_['anchor']}]",
               color=RED if f"smoke[{k}]" in unverified else BLACK, wrap=True)
        r += 1
    if not plan.get("smoke"):
        w.text(f"A{r}", "Smoke: none found")
        w.text(f"G{r}", plan.get("smoke_checked", ""), wrap=True)
        r += 1

    # ---- B. wedge
    r += 1
    w.text(f"A{r}", "B. Subpar-algorithm IRR wedge (exhibit #30): what the stock returns if nothing changes", b=True)
    r += 1
    w.text(f"A{r}", "NTM EPS (first four forecast quarters, MOD)")
    w.formula(f"B{r}", mf("ntm_eps") or "NA()", MONEY, mv("ntm_eps"))
    R["ntm_eps"] = f"$B${r}"
    r += 1
    w.text(f"A{r}", "NTM P/E")
    w.formula(f"B{r}", f"IFERROR({R['price']}/{R['ntm_eps']},NA())", MULT, s["ntm_pe"])
    R["ntm_pe"] = f"$B${r}"
    r += 1
    w.text(f"A{r}", "3-year EPS CAGR (MOD forecast)")
    w.formula(f"B{r}", mf("eps_cagr3") or "NA()", PCT, mv("eps_cagr3"))
    R["cagr"] = f"$B${r}"
    r += 1
    w.text(f"A{r}", "Dividend yield")
    w.typed(f"B{r}", s["dy"], PCT, yahoo)
    R["dy"] = f"$B${r}"
    r += 1
    w.text(f"A{r}", "Expected IRR if the P/E rolls forward (EPS growth + dividend)")
    w.formula(f"B{r}", f"IFERROR({R['cagr']}+{R['dy']},NA())", PCT, s["irr"])
    R["irr"] = f"$B${r}"
    r += 1
    put_input(r, "hurdle")
    r += 1
    w.text(f"A{r}", "Wedge: hurdle − IRR (above 0 = a filler-short candidate)", b=True)
    w.formula(f"B{r}", f"IFERROR({R['hurdle']}-{R['irr']},NA())", PCT, s["wedge"], b=True)
    R["wedge"] = f"$B${r}"
    r += 1
    w.text(f"A{r}", "Path at a constant P/E", i=True)
    for k, c in enumerate("BCDEF"):
        w.text(f"{c}{r}", f"Year {k + 1}", b=True)
    e, p, q = r + 1, r + 2, r + 3
    w.text(f"A{e}", "EPS (grows at the CAGR)")
    w.text(f"A{p}", "P/E (held)")
    w.text(f"A{q}", "Price")
    eps = [mv("ntm_eps")]
    for _ in range(4):
        eps.append(sm.mul(eps[-1], 1 + s["eps_cagr3"]) if sm._n(s.get("eps_cagr3")) else None)
    for k, c in enumerate("BCDEF"):
        prev = "BCDEF"[k - 1]
        w.formula(f"{c}{e}", R["ntm_eps"] if k == 0 else f"IFERROR({prev}{e}*(1+{R['cagr']}),NA())", MONEY, eps[k])
        w.formula(f"{c}{p}", R["ntm_pe"], MULT, s["ntm_pe"])
        w.formula(f"{c}{q}", f"IFERROR({c}{e}*{c}{p},NA())", MONEY, sm.mul(eps[k], s["ntm_pe"]))
    r = q + 2

    # ---- C. risk, print, crowding, borrow, sizing
    w.text(f"A{r}", "C. Risk case, print move, crowding, borrow and sizing", b=True)
    r += 1

    def frow(label, key, f, fmt, expect, bold=False):
        nonlocal r
        w.text(f"A{r}", label, b=bold)
        w.formula(f"B{r}", f, fmt, expect, b=bold)
        R[key] = f"$B${r}"
        r += 1

    for key in ("reward_eps", "reward_pe"):
        put_input(r, key)
        r += 1
    frow("Reward price", "reward_price", f"IFERROR({R['reward_eps']}*{R['reward_pe']},NA())", MONEY, s["reward_price"])
    frow("Reward: the fall to the reward price", "reward", f"IFERROR(1-{R['reward_price']}/{R['price']},NA())", PCT, s["reward"])
    for key in ("dream_eps", "dream_pe"):
        put_input(r, key)
        r += 1
    frow("Dream-case price", "dream_price", f"IFERROR({R['dream_eps']}*{R['dream_pe']},NA())", MONEY, s["dream_price"])
    frow("Risk if the dream case plays out", "dream_move", f"IFERROR({R['dream_price']}/{R['price']}-1,NA())", PCT, s["cases"]["dream"])
    frow("Risk from the NTM roll-forward (next year's EPS growth at today's P/E)", "roll", mf("ntm_growth") or "NA()", PCT, s["cases"]["roll"])
    put_input(r, "takeout_premium")
    r += 1
    frow("Risk case: the largest of the three", "risk",
         f"MAX(IFERROR({R['dream_move']},-1),IFERROR({R['roll']},-1),"
         f"IF(ISNUMBER({R['takeout_premium']}),{R['takeout_premium']},-1))", PCT, s["risk"], True)
    frow("Reward / risk", "rr", f"IF({R['risk']}>0,IFERROR({R['reward']}/{R['risk']},NA()),NA())", '0.0"x"', s["rr"], True)
    for key in ("print_miss", "print_pe_slip"):
        put_input(r, key)
        r += 1
    frow("Print move (EPS miss and P/E slip, exhibit #39)", "print_move",
         f"IFERROR((1+{R['print_miss']})*({R['ntm_pe']}-{R['print_pe_slip']})/{R['ntm_pe']}-1,NA())", PCT, s["print_move"])
    if mf("earn_move"):
        frow("Median earnings-day idio move, either way (Px Events)", "earn_move", mf("earn_move"), PCT, mv("earn_move"))
    for label, key, fmt in (("Short % of float", "short_pct_float", PCT), ("Days to cover", "days_to_cover", NUM)):
        w.text(f"A{r}", label)
        w.typed(f"B{r}", None if sh.get("error") else sh.get(key), fmt,
                f"{yahoo}; short interest as of {sh.get('short_date')}")
        R[key] = f"$B${r}"
        r += 1
    put_input(r, "crowded_line")
    r += 1
    frow("Crowded?", "crowded", f'IF(AND(ISNUMBER({R["short_pct_float"]}),ISNUMBER({R["crowded_line"]})),'
         f'IF({R["short_pct_float"]}>={R["crowded_line"]},"crowded","not crowded"),"n/a")',
         GEN, s["crowded"])
    put_input(r, "borrow")
    r += 1
    frow("Annual drag: borrow + dividend", "drag", f"IF(ISNUMBER({R['borrow']}),IFERROR({R['borrow']}+{R['dy']},NA()),NA())", PCT, s["drag"])
    frow("Drag at 5% borrow", "drag_low", f"IFERROR(0.05+{R['dy']},NA())", PCT, s["drag_low"])
    frow("Drag at 20% borrow", "drag_high", f"IFERROR(0.2+{R['dy']},NA())", PCT, s["drag_high"])
    frow("Reward net of a year's drag (5% borrow if the rate is unknown)", "reward_net",
         f"IFERROR({R['reward']}-IF(ISNUMBER({R['borrow']}),{R['borrow']},0.05)-{R['dy']},NA())", PCT, s["reward_net"])
    for key in ("fund", "bps"):
        put_input(r, key)
        r += 1
    frow("Risk budget per idea ($M)", "budget", f"IFERROR({R['fund']}*{R['bps']}/10000,NA())", NUM, s["size"]["budget"])
    put_input(r, "short_book")
    r += 1
    frow("Max position: budget ÷ risk case ($M, exhibit #34)", "max_pos",
         f"IF({R['risk']}>0,{R['budget']}/{R['risk']},NA())", NUM, s["size"]["max_pos"], True)
    frow("Max position, % of the short book", "pct_book", f"IFERROR({R['max_pos']}/{R['short_book']},NA())", PCT,
         s["size"]["pct_book"], True)

    for f in later:
        f()
    # ---- header block (refers to cells above)
    w.text("A5", "Verdict (the rule)", b=True)
    w.formula("B5", f'IF(AND({R["pass_F"]},{R["pass_E"]},{R["pass_V"]},{R["catalyst_soon"]}="Y",'
                    f'IFERROR({R["rr"]},0)>={sm.RR_ALPHA}),"Alpha short",IF(AND(IFERROR({R["wedge"]},0)>0,{R["pass_V"]},'
                    f'{R["count_F"]}>=1),"Filler short",IF(({R["pass_F"]})+({R["pass_E"]})+({R["pass_V"]})>=2,'
                    '"Watchlist","No short")))', GEN, s["verdict"], b=True)
    R["verdict_rule"] = "B5"
    return R


def _evidence(w, rid, r, M, Lk, R, s, later):
    """Columns C-E of a scorecard row: formulas on MOD, links to other tabs, or 'n/a: why'."""
    def f(col, name, fmt):
        x = M.get(name)
        if x:
            w.formula(f"{col}{r}", x["formula"], fmt, x["value"])
        else:
            w.text(f"{col}{r}", "n/a: not enough MOD history" if name != "revision" else "n/a: no Consensus snapshots", i=True)

    def ln(col, name, fmt, why):
        x = Lk.get(name)
        if x:
            w.link(f"{col}{r}", x["ref"], fmt, x["value"])
        else:
            w.text(f"{col}{r}", f"n/a: {why}", i=True)
    if rid == "decel":
        f("C", "decel", PCT)
    elif rid == "incr_margin":
        f("C", "incr", PCT), f("D", "opm", PCT), f("E", "peak_ratio", NUM)
    elif rid == "capex":
        f("C", "capex_da", MULT)
    elif rid == "leaky":
        f("C", "acq_cfo", PCT)
    elif rid == "fcf":
        f("C", "fcf_conv", PCT)
        if "pe_today" in Lk:
            w.formula(f"D{r}", f"IF(N(C{r})>0,IFERROR({Lk['pe_today']['ref']}/C{r},NA()),NA())", MULT, s["p_fcf"])
    elif rid == "revisions":
        f("C", "revision", PCT)
    elif rid == "vs_dcf":
        ln("C", "dcf_base", MONEY, "no Valuation tab DCF value")
    elif rid in ("vs_peers", "vs_history"):
        a, b = ("peer_gap", "peer_pct") if rid == "vs_peers" else ("pe_today", "pe_pct")
        ln("C", a, MULT, "not on the Multiples tab"), ln("D", b, PCT, "not on the Multiples tab")
    elif rid == "vs_algo":
        later.append(lambda: w.formula(f"C{r}", R["wedge"], PCT, s["wedge"]))


def _move_after(pkg, name, after):
    """Copied from model-valuation build.py, Nov 2026; keep in sync."""
    wb = pkg.text("xl/workbook.xml")
    tags = re.findall(r"<sheet\b[^>]*/>", wb)
    me = [t for t in tags if f'name="{esc(name)}"' in t][0]
    rest = [t for t in tags if t is not me]
    i = next((k for k, t in enumerate(rest) if f'name="{esc(after)}"' in t), len(rest) - 1)
    order = rest[:i + 1] + [me] + rest[i + 1:]
    body = re.search(r"<sheets>(.*?)</sheets>", wb, re.S)
    wb = wb[:body.start(1)] + "".join(order) + wb[body.end(1):]
    new_pos = {tags.index(t): k for k, t in enumerate(order)}
    wb = re.sub(r'(<definedName\b[^>]*?localSheetId=")(\d+)(")',
                lambda m: f"{m.group(1)}{new_pos.get(int(m.group(2)), int(m.group(2)))}{m.group(3)}", wb)
    pkg.put("xl/workbook.xml", wb)


def tab_parts(pkg, name):
    sh = {s[0]: s for s in pkg.sheets()}.get(name)
    if not sh:
        return set()
    part = sh[3]
    out = {part, relpath_of(part)}
    for _, (_, tgt) in pkg.rels(relpath_of(part)).items():
        if "TargetMode" not in tgt:
            out.add(resolve(part, tgt))
    return out


def tab_part(path):
    return {s[0]: s for s in Package(path).sheets()}[TAB][3]


def write_tab(pkg, w):
    """Replace the tab whole, put it after Valuation (else last), attach the notes (as model-valuation's write_tab)."""
    if TAB in [s[0] for s in pkg.sheets()]:
        pkg.remove_sheet(TAB)
    part = pkg.add_sheet(TAB, "")
    _move_after(pkg, TAB, AFTER)
    lrid = None
    if w.notes:
        pkg.content_default("vml", "application/vnd.openxmlformats-officedocument.vmlDrawing")
        ids = [int(x) for p, data in pkg.parts.items() if p.endswith(".vml")
               for d in re.findall(rb'<o:idmap v:ext="edit" data="([\d,\s]+)"', data) for x in re.findall(rb"\d+", d)]
        cn, vn = pkg.free("xl/comments{}.xml"), pkg.free("xl/drawings/vmlDrawing{}.vml")
        cx, vml = comments_parts(w.notes, max(ids + [0]) + 1)
        pkg.put(f"xl/comments{cn}.xml", cx)
        pkg.put(f"xl/drawings/vmlDrawing{vn}.vml", vml)
        lrid = pkg.attach(part, "vml", f"xl/drawings/vmlDrawing{vn}.vml")
        pkg.attach(part, "comments", f"xl/comments{cn}.xml", CT["comments"])
    pkg.put(part, w.sh.xml(None, lrid))
    return part


def changed_parts(model, out, allowed):
    a, b = zipfile.ZipFile(model), zipfile.ZipFile(out)
    A = {n: a.read(n) for n in a.namelist()}
    B = {n: b.read(n) for n in b.namelist()}
    ok = {"xl/workbook.xml", "xl/_rels/workbook.xml.rels", "[Content_Types].xml", "xl/styles.xml",
          "xl/calcChain.xml"} | set(allowed)
    return sorted(n for n in set(A) | set(B) if n not in ok and A.get(n) != B.get(n))


def build(model, work, ticker, out, borrow=None):
    if os.path.abspath(out) == os.path.abspath(model):
        raise SystemExit("model-short: --out must be a copy, not the model itself.")
    ctx = json.load(open(os.path.join(work, "context.json")))
    plan = json.load(open(os.path.join(work, "short_plan.json")))
    wp = os.path.join(work, "inputs_written.json")
    written = json.load(open(wp)) if os.path.exists(wp) else None
    up = os.path.join(work, "unverified.json")
    unverified = set(json.load(open(up))) if os.path.exists(up) else set()
    existing, existing_v = read_tab(model, False), read_tab(ctx["values"], True)

    warnings = []
    if existing is not None and written is None:
        warnings.append("There is no inputs_written.json (the record of what the last build wrote), so every yellow "
                        "cell that differs from the agent's suggestion is treated as yours.")
    used, users = resolve_values(existing, written, agent_values(plan, borrow))
    inp = _math(used, existing_v)
    for k in (*sm.HOUSE, *sm.AGENT_INPUTS):
        if not sm._n(inp[k]):
            warnings.append(f"{LABEL[k]!r} holds {used[LABEL[k]]!r}, not a number; the cells that use it show #N/A "
                            "or fall back as the formulas say. Type a number there and rerun.")
    soon = _yes(inp["catalyst_soon"])
    code = sm.summary(ctx, inp, {}, soon)["code"]
    tick_used, tick_users = resolve_values(existing, written, tick_values(plan, code))
    users |= tick_users
    ticks = {rid: code[rid] if tick_used[lab] == FORMULA else sm.SYM.get(_calc(tick_used[lab], lab, existing_v), "unknown")
             for rid, lab in ROWLABEL.items()}
    s = sm.summary(ctx, inp, ticks, soon, inp["borrow"] if sm._n(inp["borrow"]) else None)

    pkg = Package(model)
    old = tab_parts(pkg, TAB)
    st = Styles(pkg.text("xl/styles.xml"))
    w = W(st, users)
    allv = {**used, **tick_used}
    R_holder = {}

    def put_input_header(r, key):
        lab = LABEL[key]
        w.text(f"A{r}", lab)
        yn = lambda b: "Y" if b else "N"   # noqa: E731
        x = {"verdict": plan["verdict"], "type": plan["type"], "bucket": plan["bucket"],
             "catalyst_soon": {"value": yn(plan["catalyst"]["soon"]), "anchor": plan["catalyst"]["anchor"],
                               "reason": plan["catalyst"]["text"]},
             "takeout_prone": {**plan["takeout_prone"], "value": yn(plan["takeout_prone"]["value"])}}[key]
        note = _note(x) if lab not in users else f"You typed {used[lab]}. " + _note(x)
        w.input_(f"B{r}", lab, used[lab], GEN, note)
        bad_anchor = key == "catalyst_soon" and "catalyst" in unverified
        w.text(f"G{r}", ("UNVERIFIED: " if bad_anchor else "") + str(x.get("reason", "")),
               color=RED if bad_anchor else BLACK, wrap=True)
        R_holder[key] = f"$B${r}"

    for r, key in ((6, "verdict"), (7, "type"), (8, "bucket"), (9, "catalyst_soon"), (10, "takeout_prone")):
        put_input_header(r, key)
    w.text("A11", "Why")
    w.text("B11", plan["why"], wrap=True)
    R = lay_out(w, ctx, plan, allv, tick_used, s, ticker, unverified, R_holder)

    a_texts = list(w.col_a.values())
    for lab in allv:                          # a rerun finds every input and tick again by its column-A text
        if a_texts.count(lab) != 1:
            raise SystemExit(f"model-short: the label {lab!r} appears {a_texts.count(lab)} times in column A.")
    w.sh.comments = w.notes
    w.sh.freeze = "B3"
    w.sh.widths.update({1: 58, 2: 16, 3: 13, 4: 13, 5: 13, 6: 34, 7: 100})
    part = write_tab(pkg, w)
    pkg.put("xl/styles.xml", st.render())
    pkg.finish()
    pkg.save(out)
    import notebox
    notebox.fix(out, out, since=model)
    new = tab_parts(Package(out), TAB)
    bad = changed_parts(model, out, old | new | {part})
    if bad:
        os.remove(out)
        raise SystemExit("model-short: the build changed parts it must not touch: " + ", ".join(bad))
    serial = {k: v for k, v in s.items() if k not in ("path",)}
    json.dump({"expected": w.expected, "kinds": w.kinds, "fmt": w.fmt, "refs": R, "inputs": w.inputs,
               "used": allv, "users": sorted(users), "summary": serial},
              open(os.path.join(work, "layout.json"), "w"), indent=0, default=str)
    json.dump({lab: {"value": v, "user": lab in users} for lab, v in allv.items()},
              open(os.path.join(work, "inputs_written.next.json"), "w"), indent=1, default=str)
    return {"tab": TAB, "users_kept": sorted(users), "changed_parts": bad, "verdict_rule": s["verdict"],
            "verdict_agent": used[LABEL["verdict"]], "warnings": warnings}


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--model", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--ticker", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--borrow", type=float)
    a = ap.parse_args()
    print(json.dumps(build(a.model, a.work, a.ticker.upper(), a.out, a.borrow), indent=1))


if __name__ == "__main__":
    main()
