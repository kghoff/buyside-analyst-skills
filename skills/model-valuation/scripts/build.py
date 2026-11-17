"""Writes the Valuation tab into a copy of the user's model through raw-XML editing (xlsx.py). Every other part of the
workbook stays byte-identical. Yellow = the agent's suggestion, the user's to change (blue font on yellow fill, a note
with the agent's value, anchor and reason); typed numbers blue with a source note; formulas black; links to other tabs
green. A rerun keeps every yellow cell the user changed (resolve_inputs).

Records in W/layout.json the value every checked cell must recalculate to (valmath on context.json's numbers and the
resolved inputs), for verify.py, and in W/inputs_written.next.json what the agent suggested for each yellow cell (SKILL
step 7 renames it to inputs_written.json only when OUT is copied over the model).

Layout: a cursor walks down the sections; each section function takes (b, r) and returns the next free row, so a
section's size follows the plan. Named cells go in b.ref (absolute refs such as "$B$5") for later sections.

usage: python3 build.py --model M --work W --ticker T --out OUT"""
import argparse
import json
import os
import re
from types import SimpleNamespace

import openpyxl

import subject
import valmath
from modmap import ModMap
from xlsx import CT, Package, Sheet, Styles, comments_parts, esc

TAB, AFTER = "Valuation", "Multiples"
BLUE, BLACK, GREEN = "FF0000FF", "FF000000", "FF008000"
YELLOW = "FFFFFF99"
X, PCT, MONEY, MILL, INT = '0.0"x"', "0.0%", "$#,##0.00", "#,##0.0", "0"
KIND = {"pe": "P/E", "ev_ebitda": "EV/EBITDA", "ev_gp": "EV/GP", "ev_rev": "EV/Revenue", "fcf_yield": "FCF yield"}
METRIC_NAME = {"eps": "EPS", "rev": "revenue", "gp": "gross profit", "ebitda": "EBITDA", "fcf": "free cash flow"}
HOUSE_LABEL = {"hurdle": "IRR hurdle", "buy_rr": "Buy at R/R", "pound_rr": "Table-pound at R/R",
               "discount": "Discount rate", "horizon_months": "Horizon (months)",
               "position": "Position (long/short)", "mkt_rev": "Market growth reference: revenue",
               "mkt_oi": "Market growth reference: operating profit", "mkt_eps": "Market growth reference: EPS"}
HOUSE_FMT = {"hurdle": PCT, "buy_rr": X, "pound_rr": X, "discount": PCT, "horizon_months": INT, "position": "General",
             "mkt_rev": PCT, "mkt_oi": PCT, "mkt_eps": PCT}


def _kind_labels():
    out = {}
    for k, lab in KIND.items():
        m = METRIC_NAME[valmath.METRIC[k]]
        word, on = ("yield", "on") if k == "fcf_yield" else ("multiple", "x")
        out[f"weight.{k}"] = lab
        out[f"reward_multiple.{k}"] = f"{lab}: reward {word} ({on} NTM+1)"
        out[f"risk_multiple.{k}"] = f"{lab}: risk {word}"
        out[f"risk_metric.{k}"] = f"{lab}: risk {m}"
        out[f"multiple_3y.{k}"] = f"{lab}: {word} at the 3-year horizon"
    return out


# Input key -> its exact column-A text. Inputs are found on an existing tab by this label, so a layout change between
# versions keeps the user's values. Each label is unique on the tab.
LABEL = {**HOUSE_LABEL, **_kind_labels(), "normalization.margin": "Normal net margin",
         "normalization.multiple": "Normal multiple (P/E)", "normalization.years": "Years to normal"}
assert len(set(LABEL.values())) == len(LABEL)


def col_of(key):
    """The column that holds an input's value on its labelled row."""
    if key.startswith("tree."):
        return "D" if key.endswith(".prob") else "B"
    return "C" if key.startswith("weight.") else "B"


def label_of(key):
    """An input's column-A text: LABEL, or for a probability-tree row (tree.<name>.target / .prob) its name."""
    return key[len("tree."):].rsplit(".", 1)[0] if key.startswith("tree.") else LABEL[key]


class W:
    """Cell writer that remembers styles, what is typed / linked / formula / input, notes and expected values.
    (The pattern of model-multiples' build.W, plus input_ and notes.)"""

    def __init__(self, st):
        self.sh, self.st = Sheet(), st
        self.s = {}
        self.typed, self.links, self.formulas, self.expected = [], [], [], {}
        self.inputs, self.notes = {}, {}
        self.ftext, self.na, self.col_a = {}, [], {}

    def _f(self, ref, f, expect, check):
        self.ftext[ref] = f
        if "NA()" in f:
            self.na.append(ref)
        if check:
            self.expected[ref] = expect

    def style(self, color=BLACK, fmt="General", b=False, i=False, fill=None, sz=11, wrap=False):
        k = (color, fmt, b, i, fill, sz, wrap)
        if k not in self.s:
            self.s[k] = self.st.xf(color=color, fmt=fmt, b=b, i=i, fill=fill, sz=sz, align="left" if wrap else None)
        return self.s[k]

    def text(self, ref, t, **kw):
        self.sh.set(ref, "s", t, self.style(**kw))
        if re.fullmatch(r"A\d+", ref):
            self.col_a[ref] = t

    def typed_(self, ref, v, fmt, note, kind="n", fill=None):
        self.sh.set(ref, kind, v, self.style(BLUE, fmt, fill=fill))
        self.typed.append(ref)
        self.notes[ref] = note

    def link(self, ref, f, fmt, expect=None, check=True):
        self.sh.set(ref, "f", f, self.style(GREEN, fmt))
        self.links.append(ref)
        self._f(ref, f, expect, check)

    def formula(self, ref, f, fmt, expect=None, check=True, b=False, kind="f"):
        self.sh.set(ref, kind, f, self.style(BLACK, fmt, b=b))
        self.formulas.append(ref)
        self._f(ref, f, expect, check)

    def input_(self, ref, key, v, fmt, note):
        """A yellow cell the agent chose and the user owns: blue font on yellow fill, the agent's value/anchor/reason
        in its note. v may be a number, a string ("long"), or ("f", formula, ...) when the user typed a formula."""
        kind, val = ("f", v[1]) if isinstance(v, tuple) else ("s" if isinstance(v, str) else "n", v)
        self.sh.set(ref, kind, val, self.style(BLUE, fmt, fill=YELLOW))
        self.inputs[key] = ref
        self.notes[ref] = note


# ---------------------------------------------------------------- inputs that survive reruns
def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _same(a, b):
    """model-dcf's _same at rel 1e-9 (the plan's tolerance); text compares as text."""
    if isinstance(a, str) or isinstance(b, str):
        return isinstance(a, str) and isinstance(b, str) and a.strip().lower() == b.strip().lower()
    return _num(a) and _num(b) and abs(a - b) <= 1e-9 * max(1.0, abs(b))


def plan_inputs(plan):
    """{key: {value, anchor, [anchor_value], reason}}: the plan's inputs plus normalization's and the probability
    tree's yellow cells (tree.<name>.prob, and tree.<name>.target when the target is anchored, not linked)."""
    out = dict(plan["inputs"])
    n = plan.get("normalization")
    if n:
        out.update({f"normalization.{k}": n[k] for k in ("margin", "multiple", "years")})
    for t in plan.get("tree") or []:
        if "link" not in t["target"]:
            out[f"tree.{t['name']}.target"] = t["target"]
        out[f"tree.{t['name']}.prob"] = t["prob"]
    return out


def _tab_cells(path, data_only):
    """{label in column A: {column letter: value}} for the existing Valuation tab, or None."""
    if not path or not os.path.exists(path):
        return None
    wb = openpyxl.load_workbook(path, read_only=True, data_only=data_only)
    if TAB not in wb.sheetnames:
        wb.close()
        return None
    out = {}
    for row in wb[TAB].iter_rows(max_col=6):
        a = row[0].value
        if isinstance(a, str) and a not in out:
            out[a] = {c.column_letter: c.value for c in row if hasattr(c, "column_letter")}
    wb.close()
    return out


def resolve_inputs(model, plan, written, values=None):
    """{key: value used} and {key: (agent value, user value)} for the cells the user changed. A cell is the user's if it
    holds a formula or differs from what the last build wrote (written: {key: value}); then the user's value (or
    formula) wins. Inputs are found on the existing Valuation tab by their column-A label (LABEL[key]), so a layout
    change between versions keeps them. No tab or no written record: the agent's values.

    A user's formula is used as ("f", formula, its recalculated value from `values`, the recalculated copy)."""
    agent = {k: x["value"] for k, x in plan_inputs(plan).items()}
    used, changed = dict(agent), {}
    f_tab = _tab_cells(model, False) if written else None
    if not f_tab:
        return used, changed
    v_tab = _tab_cells(values, True) or {}
    for key, a in agent.items():
        lab, col = label_of(key), col_of(key)
        cell = (f_tab.get(lab) or {}).get(col)
        if cell is None or key not in written:
            continue
        if isinstance(cell, str) and cell.startswith("="):
            cached = (v_tab.get(lab) or {}).get(col)
            used[key] = ("f", cell[1:], cached)
            changed[key] = (a, cell)
        elif not _same(cell, written[key]):
            used[key] = cell
            changed[key] = (a, cell)
    return used, changed


def val(v):
    """The number (or text) an input stands for: a user's formula counts at its recalculated value."""
    return v[2] if isinstance(v, tuple) else v


def input_note(x, changed=None):
    a = f"anchor {x['anchor']}" + (f" = {x['anchor_value']}" if "anchor_value" in x else "")
    note = f"Agent: {x['value']} | {a} | {x['reason']}"
    return f"You typed {changed[1]}. {note}" if changed else note


# ---------------------------------------------------------------- sections
def header(b, r, text, heads=()):
    """Section header: bold in A, bold column heads from B, and 'Reasoning' bold in H."""
    b.w.text(f"A{r}", text, b=True)
    for j, h in enumerate(heads):
        b.w.text(f"{'BCDEF'[j]}{r}", h, b=True)
    b.w.text(f"H{r}", "Reasoning", b=True)


def put_input(b, r, key, fmt, col=None):
    """Label in A, the yellow cell, its reason in H. Returns the cell's absolute ref."""
    x = b.pin[key]
    col = col or col_of(key)
    b.w.text(f"A{r}", label_of(key))
    b.w.input_(f"{col}{r}", key, b.used[key], fmt, input_note(x, b.changed.get(key)))
    b.w.text(f"H{r}", x["reason"], wrap=True)
    return f"${col}${r}"


def sec_title(b, r):
    b.w.text("A1", f"{b.ticker} valuation: what it's worth and whether the setup is worth owning", b=True, sz=14)
    b.w.text("A2", "Yellow = the agent's suggestion, yours to change (note: its value, anchor and reason). Blue = typed "
                   "from a source. Black = formulas. Green = links to other tabs.", i=True)
    return 4


def sec0_today(b, r):
    """Today's price, volatility and the DCF tab's bridge, then the house inputs."""
    w, m, dcf = b.w, b.ctx["metrics"], b.dcf
    header(b, r, "0. Today and house inputs")
    r += 1
    rows = (("price", "Price", f"={dcf['refs']['price']}", MONEY, dcf["price"]["last"]["value"], "link"),
            ("vol", "Annualized volatility (last 253 closes)", m["vol"]["formula"], PCT, m["vol"]["value"], "fa"),
            ("nd", "Net debt ($M)", f"={dcf['refs']['net_debt']}", MILL, dcf["ctx"]["net_debt"], "link"),
            ("sh", "Diluted shares (M)", f"={dcf['refs']['shares']}", MILL, dcf["ctx"]["shares"], "link"))
    for name, lab, f, fmt, v, kind in rows:
        w.text(f"A{r}", lab)
        if kind == "link":
            w.link(f"B{r}", f.lstrip("="), fmt, v)
        else:                            # a legacy array formula, as model-multiples writes its percentile column
            w.formula(f"B{r}", f, fmt, v, kind="fa")
        b.ref[name] = f"$B${r}"
        r += 1
    for key in HOUSE_LABEL:
        b.ref[key] = put_input(b, r, key, HOUSE_FMT[key])
        r += 1
    return r + 1


def sec1_multiples(b, r):
    header(b, r, "1. Which multiples and why", ("Role", "Weight"))
    r += 1
    cells = []
    for mlt in b.plan["multiples"]:
        k = mlt["kind"]
        b.w.text(f"B{r}", mlt["role"])
        b.ref[f"weight.{k}"] = put_input(b, r, f"weight.{k}", PCT)
        b.w.text(f"H{r}", mlt["reason"] + " Weight: " + b.pin[f"weight.{k}"]["reason"], wrap=True)
        cells.append(f"C{r}")
        r += 1
    b.w.text(f"A{r}", "Weights sum")
    b.w.formula(f"C{r}", f"SUM({','.join(cells)})", PCT,
                sum(val(b.used[f"weight.{m['kind']}"]) for m in b.plan["multiples"]))
    return r + 2


def sec2_growth(b, r):
    """Revenue / operating income / EPS CAGRs from MOD against the house market references; P/E ÷ EPS growth."""
    g = b.ctx["metrics"]["growth"]
    header(b, r, "2. Growth algorithm", ("Start", "End", "Years", "CAGR", "Market ref"))
    r += 1
    for k, lab, mk in (("rev", "Revenue", "mkt_rev"), ("oi", "Operating income", "mkt_oi"), ("eps", "EPS", "mkt_eps")):
        x = g[k]
        fmt = MONEY if k == "eps" else MILL
        b.w.text(f"A{r}", lab)
        b.w.link(f"B{r}", x["start_ref"], fmt, x["start"])
        b.w.link(f"C{r}", x["end_ref"], fmt, x["end"])
        b.w.typed_(f"D{r}", x["years"], INT, f"MOD years {b.year_of(x['start_ref'])}→{b.year_of(x['end_ref'])}")
        b.w.formula(f"E{r}", f"IFERROR((C{r}/B{r})^(1/D{r})-1,NA())", PCT, x["cagr"])
        b.w.formula(f"F{r}", b.ref[mk].replace("$", ""), PCT, val(b.used[mk]))
        b.ref[f"cagr.{k}"] = f"$E${r}"
        r += 1
    eps = b.ctx["metrics"]["eps"]["ntm"]
    price = b.dcf["price"]["last"]["value"]
    b.w.text(f"A{r}", "NTM EPS (first four forecast quarters)")
    b.w.link(f"B{r}", eps["formula"], MONEY, eps["value"])
    b.ref["ntm_eps_growth"] = f"$B${r}"
    r += 1
    pe = price / eps["value"] if eps["value"] else None
    b.w.text(f"A{r}", "Today's NTM P/E")
    b.w.formula(f"B{r}", f"{b.ref['price']}/B{r - 1}", X, pe)
    b.ref["pe_now"] = f"$B${r}"
    r += 1
    c = g["eps"]["cagr"]
    b.w.text(f"A{r}", "P/E ÷ EPS CAGR")
    b.w.formula(f"B{r}", f"IFERROR(B{r - 1}/({b.ref['cagr.eps']}*100),NA())", "0.00",
                pe / (c * 100) if pe is not None and c else None)
    return r + 2


def sec3_earnings_power(b, r):
    """Only with plan['normalization']: normal EPS = MOD revenue(year) × margin ÷ MOD diluted shares(year)."""
    n = b.plan.get("normalization")
    if not n:
        return r
    year = n["year"]
    if year not in b.mm.labels:
        raise SystemExit(f"model-valuation: normalization year {year!r} is not a column in MOD.")
    R = subject.find_rows(b.mm)
    col = b.mm.col(year)
    grid = subject.grid(b.values, max(R["rev"], R["shares"]) + 1)
    rev, shares = subject.num(grid, R["rev"], col), subject.num(grid, R["shares"], col)
    w, U = b.w, b.used
    header(b, r, "3. Earnings power (normalized)")
    r += 1
    w.text(f"A{r}", "Normal year")
    w.text(f"B{r}", year)
    r += 1
    w.text(f"A{r}", f"Normal revenue ({year}, $M)")
    w.link(f"B{r}", f"MOD!${col}${R['rev']}", MILL, rev)
    rr = r
    r += 1
    mg = put_input(b, r, "normalization.margin", PCT)
    r += 1
    w.text(f"A{r}", f"Diluted shares {year} (M)")
    w.link(f"B{r}", f"MOD!${col}${R['shares']}", MILL, shares)
    sr = r
    r += 1
    ok = None not in (rev, shares, val(U["normalization.margin"])) and shares
    eps = rev * val(U["normalization.margin"]) / shares if ok else None
    w.text(f"A{r}", "Normal EPS")
    w.formula(f"B{r}", f"B{rr}*{mg}/B{sr}", MONEY, eps)
    er = r
    r += 1
    mu = put_input(b, r, "normalization.multiple", X)
    r += 1
    yrs = val(U["normalization.years"])
    p, disc = valmath.normalized(val(U["normalization.multiple"]), eps, val(U["discount"]), yrs) \
        if eps is not None else (None, None)
    w.text(f"A{r}", "Normalized price")
    w.formula(f"B{r}", f"{mu}*B{er}", MONEY, p)
    pr = r
    r += 1
    yr = put_input(b, r, "normalization.years", "0.0")
    r += 1
    w.text(f"A{r}", "Discounted at the discount rate")
    w.formula(f"B{r}", f"B{pr}/(1+{b.ref['discount']})^{yr}", MONEY, disc)
    b.ref["normal_price_disc"] = f"$B${r}"
    r += 1
    price = b.dcf["price"]["last"]["value"]
    w.text(f"A{r}", "Return from today")
    w.formula(f"B{r}", f"B{r - 1}/{b.ref['price']}-1", PCT, disc / price - 1 if disc is not None else None)
    return r + 2


# ---------------------------------------------------------------- sections 4-7: reward / risk, IRR, DCF, tree
GREY = "FFD9D9D9"
STEP = "+0%;-0%;0%"
SIGMA_LOW = "risk case inside a 1σ move: too gentle"


def _mfmt(metric):
    return MONEY if metric == "eps" else MILL


def _xfmt(kind):
    return PCT if kind == "fcf_yield" else X


def _short(b):
    return str(val(b.used["position"])).strip().lower() == "short"


def _ok(*xs):
    return all(_num(x) for x in xs)


def _other_value(b, ref):
    """A cell on another tab as last recalculated (W/values): for the Street links' expected values."""
    if "wb_values" not in b.__dict__:
        b.wb_values = openpyxl.load_workbook(b.values, read_only=True, data_only=True)
    sheet, cell = ref.rsplit("!", 1)
    return b.wb_values[sheet.strip("'")][cell.replace("$", "")].value


def _price_formula(kind, mult, metric, nd, sh):
    """valmath.price_from_multiple as an Excel formula: levered multiples price equity, unlevered price EV."""
    if kind == "pe":
        return f"{mult}*{metric}"
    if kind == "fcf_yield":
        return f"IFERROR({metric}/{sh}/{mult},NA())"
    return f"({mult}*{metric}-{nd})/{sh}"


def _rr_rows(b, r, prefix, reward, risk, want_reward, want_risk, extra=True):
    """Reward %, risk %, R/R and verdict (and, with extra, reward-to-vol and the 1σ check) for one pair of prices.
    Returns (next row, (up, down, rr))."""
    w, P, pos = b.w, b.ref["price"], b.ref["position"]
    price = b.dcf["price"]["last"]["value"]
    up = down = rr = None
    if _ok(want_reward, want_risk):
        up, down, rr = valmath.reward_risk(price, want_reward, want_risk, _short(b))
    w.text(f"A{r}", f"{prefix}reward %")
    w.formula(f"B{r}", f'IF({pos}="short",({P}-{risk})/{P},{reward}/{P}-1)', PCT, up)
    ru = r
    r += 1
    w.text(f"A{r}", f"{prefix}risk %")
    w.formula(f"B{r}", f'IF({pos}="short",({reward}-{P})/{P},1-{risk}/{P})', PCT, down)
    rd = r
    r += 1
    w.text(f"A{r}", f"{prefix}reward / risk")
    w.formula(f"B{r}", f"IF(B{rd}>0,B{ru}/B{rd},NA())", X, rr)
    rr_ref = r
    r += 1
    w.text(f"A{r}", f"{prefix}verdict")
    w.formula(f"B{r}", f'IF(B{rr_ref}>={b.ref["pound_rr"]},"table-pound",IF(B{rr_ref}>={b.ref["buy_rr"]},"buy",'
                       f'"below hurdle"))', "General",
              valmath.verdict(rr, val(b.used["buy_rr"]), val(b.used["pound_rr"])) if rr is not None else None)
    r += 1
    if extra:
        vol = b.ctx["metrics"]["vol"]["value"]
        w.text(f"A{r}", f"{prefix}reward-to-volatility")
        w.formula(f"B{r}", f"IFERROR(B{ru}/{b.ref['vol']},NA())", "0.00", up / vol if up is not None and vol else None)
        r += 1
        hz = val(b.used["horizon_months"])
        w.text(f"A{r}", f"{prefix}1σ check")
        w.formula(f"B{r}", f'IF(B{rd}<{b.ref["vol"]}*SQRT({b.ref["horizon_months"]}/12),"{SIGMA_LOW}","ok")', "General",
                  (SIGMA_LOW if valmath.inside_one_sigma(down, vol, hz) else "ok") if down is not None else None)
        r += 1
    return r, (up, down, rr)


def sec4_rr(b, r):
    """One 12-month roll-forward and reward / risk block per multiple, primary first."""
    w, m, U = b.w, b.ctx["metrics"], b.used
    price, nd, sh = b.dcf["price"]["last"]["value"], b.dcf["ctx"]["net_debt"], b.dcf["ctx"]["shares"]
    street = b.plan.get("street") or {}
    b.want = {}
    w.text(f"A{r}", "4. 12-month roll-forward and reward / risk", b=True)
    r += 2
    order = sorted(b.plan["multiples"], key=lambda x: x["role"] != "primary")
    for mlt in order:
        k, role = mlt["kind"], mlt["role"]
        metric, lab = valmath.METRIC[k], KIND[k]
        mname, mf, xf = METRIC_NAME[metric], _mfmt(metric), _xfmt(k)
        header(b, r, f"{lab} ({role})", ("Ours", "Street"))
        r += 1
        for blk, word in (("ntm", "NTM"), ("ntm1", "NTM+1")):
            x = m[metric][blk]
            w.text(f"A{r}", f"{lab}: {word} {mname} ({x['quarters'][0]} to {x['quarters'][-1]})")
            w.link(f"B{r}", x["formula"], mf, x["value"])
            sref = (street.get(k) or {}).get(blk)
            if sref:
                w.link(f"C{r}", sref, mf, _other_value(b, sref))
                b.ref[f"street.{blk}.{k}"] = f"$C${r}"
            else:
                w.text(f"C{r}", "n/a")
            b.ref[f"{blk}.{k}"] = f"$B${r}"
            r += 1
        n0, n1 = m[metric]["ntm"]["value"], m[metric]["ntm1"]["value"]
        P, ND, SH = b.ref["price"], b.ref["nd"], b.ref["sh"]
        N0, N1 = b.ref[f"ntm.{k}"], b.ref[f"ntm1.{k}"]
        now = {"pe": f"IF({N0}>0,{P}/{N0},NA())", "fcf_yield": f"{N0}/({P}*{SH})"}.get(
            k, f"IF({N0}>0,({P}*{SH}+{ND})/{N0},NA())")
        x0 = valmath.multiple_now(k, price, n0, nd, sh) if _ok(n0) and (k == "fcf_yield" or n0 > 0) else None
        w.text(f"A{r}", f"{lab} today (on NTM)")
        w.formula(f"B{r}", now, xf, x0)
        b.ref[f"mult_now.{k}"] = f"$B${r}"
        r += 1
        prices = {}
        for side, mkey, metric_ref, metric_val in (
                ("reward", f"reward_multiple.{k}", N1, n1), ("risk", f"risk_multiple.{k}", None, None)):
            mult = put_input(b, r, mkey, xf)
            r += 1
            if side == "risk":
                metric_ref = put_input(b, r, f"risk_metric.{k}", mf)
                metric_val = val(U[f"risk_metric.{k}"])
                r += 1
            mv = val(U[mkey])
            ok = _ok(mv, metric_val) and (k != "fcf_yield" or mv)
            w.text(f"A{r}", f"{lab}: {side} price")
            w.formula(f"B{r}", _price_formula(k, mult, metric_ref, ND, SH), MONEY,
                      valmath.price_from_multiple(k, mv, metric_val, nd, sh) if ok else None)
            b.ref[f"{side}_px.{k}"] = f"$B${r}"
            prices[side] = b.w.expected[f"B{r}"]
            r += 1
        r, _ = _rr_rows(b, r, f"{lab}: ", b.ref[f"reward_px.{k}"], b.ref[f"risk_px.{k}"],
                        prices["reward"], prices["risk"])
        b.want[k] = prices
        r += 1
    return sec4b_blended(b, r)


def sec4b_blended(b, r):
    w, ms = b.w, b.plan["multiples"]
    header(b, r, "4b. Blended (weights in section 1)")
    r += 1
    for side in ("reward", "risk"):
        f = "+".join(f"{b.ref['weight.' + m['kind']]}*{b.ref[side + '_px.' + m['kind']]}" for m in ms)
        vals = [(val(b.used["weight." + m["kind"]]), b.want[m["kind"]][side]) for m in ms]
        want = sum(x * y for x, y in vals) if all(_ok(x, y) for x, y in vals) else None
        w.text(f"A{r}", f"Blended {side} price")
        w.formula(f"B{r}", f, MONEY, want)
        b.ref[f"blended_{side}"] = f"$B${r}"
        b.want[f"blended_{side}"] = want
        r += 1
    r, _ = _rr_rows(b, r, "Blended ", b.ref["blended_reward"], b.ref["blended_risk"],
                    b.want["blended_reward"], b.want["blended_risk"], extra=False)
    return sec4c_ladder(b, r + 1)


def sec4c_ladder(b, r):
    """Reward, risk and R/R on the blended prices at seven entry prices around today's."""
    w, P, pos = b.w, b.ref["price"], b.ref["position"]
    RW, RK = b.ref["blended_reward"], b.ref["blended_risk"]
    price = b.dcf["price"]["last"]["value"]
    header(b, r, "4c. Reward / risk ladder (blended)", ("Entry", "Reward", "Risk", "R/R"))
    r += 1
    steps = (-0.15, -0.10, -0.05, 0.0, 0.05, 0.10, 0.15)
    rw, rk = b.want["blended_reward"], b.want["blended_risk"]
    rungs = valmath.ladder(rw, rk, price, short=_short(b)) if _ok(rw, rk) else [(None,) * 4] * 7
    for s, (e, up, down, rr) in zip(steps, rungs):
        w.typed_(f"A{r}", s, STEP, "ladder step: entry price vs today's")
        w.formula(f"B{r}", f"{P}*(1+A{r})", MONEY, price * (1 + s))
        w.formula(f"C{r}", f'IF({pos}="short",(B{r}-{RK})/B{r},{RW}/B{r}-1)', PCT, up)
        w.formula(f"D{r}", f'IF({pos}="short",({RW}-B{r})/B{r},1-{RK}/B{r})', PCT, down)
        w.formula(f"E{r}", f"IF(D{r}>0,C{r}/D{r},NA())", X, rr)
        r += 1
    return r + 1


def sec5_irr(b, r):
    """3-year IRR on the primary multiple, split into roll-forward and re-rating (chapter 11.6)."""
    w, m, U = b.w, b.ctx["metrics"], b.used
    k = next(x["kind"] for x in b.plan["multiples"] if x["role"] == "primary")
    metric, lab = valmath.METRIC[k], KIND[k]
    y3, N = m[metric]["y3"], m["years3"]
    price, nd, sh = b.dcf["price"]["last"]["value"], b.dcf["ctx"]["net_debt"], b.dcf["ctx"]["shares"]
    mname, mf, xf = METRIC_NAME[metric], _mfmt(metric), _xfmt(k)
    header(b, r, f"5. {N}-year IRR ({lab}, the primary multiple)")
    r += 1
    rows = {}

    def put(key, label, write):
        nonlocal r
        w.text(f"A{r}", label)
        write(f"B{r}")
        rows[key] = f"B{r}"
        r += 1

    m0, m3 = m[metric]["ntm"]["value"], y3["value"]
    x0 = b.w.expected[b.ref[f"mult_now.{k}"].replace("$", "")]
    put("m0", f"IRR: NTM {mname} now", lambda c: w.formula(c, b.ref[f"ntm.{k}"], mf, m0))
    put("m3", f"IRR: {mname} in {N} years ({y3['quarters'][0]} to {y3['quarters'][-1]})",
        lambda c: w.link(c, y3["formula"], mf, m3))
    put("n", "IRR: years", lambda c: w.typed_(c, N, INT, f"years from NTM to MOD quarters {', '.join(y3['quarters'])}"))
    put("x0", f"IRR: {lab} now", lambda c: w.formula(c, b.ref[f"mult_now.{k}"], xf, x0))
    x3_ref = put_input(b, r, f"multiple_3y.{k}", xf)
    rows["x3"] = x3_ref.replace("$", "")
    r += 1
    x3 = val(U[f"multiple_3y.{k}"])
    put("p0", "IRR: price now", lambda c: w.formula(c, b.ref["price"], MONEY, price))
    ok = _ok(x3, m3) and (k != "fcf_yield" or x3)
    p3 = valmath.price_from_multiple(k, x3, m3, nd, sh) if ok else None
    R = rows
    put("p3", f"IRR: price in {N} years",
        lambda c: w.formula(c, _price_formula(k, R["x3"], R["m3"], b.ref["nd"], b.ref["sh"]), MONEY, p3))
    irr = valmath.irr(price, p3, N) if _ok(p3) and p3 > 0 else None
    put("irr", "IRR", lambda c: w.formula(c, f"IF({R['p3']}>0,({R['p3']}/{R['p0']})^(1/{R['n']})-1,NA())", PCT, irr))
    put("hurdle", "IRR vs hurdle", lambda c: w.formula(
        c, f'IF({R["irr"]}>={b.ref["hurdle"]},"clears","below")', "General",
        ("clears" if irr >= val(U["hurdle"]) else "below") if irr is not None else None))
    w.text(f"A{r}", "The 3 R's", b=True)
    r += 1
    g = valmath.cagr(m0, m3, N)
    put("g", "Roll-forward (metric growth, a year)", lambda c: w.formula(
        c, f"IF(AND({R['m0']}>0,{R['m3']}>0),({R['m3']}/{R['m0']})^(1/{R['n']})-1,NA())", PCT, g))
    # A yield re-rates the other way: price = FCF / shares / yield, so a lower yield is a higher price.
    a, z = ("x3", "x0") if k == "fcf_yield" else ("x0", "x3")
    xa, xz = (x3, x0) if k == "fcf_yield" else (x0, x3)
    rr = valmath.cagr(xa, xz, N) if _ok(xa, xz) else None
    put("rr", "Re-rating (multiple change, a year)", lambda c: w.formula(
        c, f"IF(AND({R[a]}>0,{R[z]}>0),({R[z]}/{R[a]})^(1/{R['n']})-1,NA())", PCT, rr))
    s0 = b.ref.get(f"street.ntm.{k}")
    if s0:
        sv = w.expected.get(s0.replace("$", ""))
        put("rev", "Revisions (our NTM vs the Street's)", lambda c: w.formula(
            c, f"IFERROR({b.ref[f'ntm.{k}']}/{s0}-1,NA())", PCT, m0 / sv - 1 if _ok(m0, sv) and sv else None))
    else:
        put("rev", "Revisions (our NTM vs the Street's)", lambda c: w.text(c, "n/a"))
    if k not in valmath.LEVERED:
        lev = irr - ((1 + g) * (1 + rr) - 1) if None not in (irr, g, rr) else None
        put("lev", "Leverage and other (IRR less growth and re-rating)", lambda c: w.formula(
            c, f"{R['irr']}-((1+{R['g']})*(1+{R['rr']})-1)", PCT, lev))
    # route to a double: share of log(P3/P0) from the multiple. valmath.double_path on (x, P/x) pairs gives the same.
    dp = valmath.double_path(xa, xz, price / xa, p3 / xz) if _ok(xa, xz, p3) and xa > 0 and xz > 0 and p3 > 0 else None
    lp, lx = f"LN({R['p3']}/{R['p0']})", f"LN({R[z]}/{R[a]})"
    put("dp", f"{N}-year double path", lambda c: w.formula(
        c, f'IF({R["p3"]}<=0,NA(),IF({lp}<=0,"no double path (price falls)",IF({lx}/{lp}>=2/3,"P/E expansion",'
           f'IF({lx}/{lp}<=1/3,"EPS growth","both"))))', "General", dp))
    b.irr = irr
    return r + 1


def sec6_dcf(b, r):
    """The agent's final DCF scenarios as model-dcf's math values them (typed from scenario_eval, grey like model-dcf's
    reverse table), against the multiple targets."""
    import datetime as dt
    w, res, ctx = b.w, b.result, b.dcf["ctx"]
    cases = ("bear", "base", "bull")
    when = dt.date.fromtimestamp(os.path.getmtime(os.path.join(b.work, f"scenarios_result_{b.round}.json")))
    note = f"scenario_eval round {b.round}, {when.isoformat()}"
    header(b, r, "6. DCF scenarios (model-dcf's math)", ("Bear", "Base", "Bull", "Today's price implies"))
    rounds = b.plan["scenarios"].get("rounds") or []
    if rounds:
        w.text(f"H{r}", f"Round {rounds[-1].get('round', b.round)}: {rounds[-1].get('why', '')}", wrap=True)
    r += 1
    imp = res.get("implied", {})
    factors = [f["name"] for f in ctx["factors"]]      # the revenue identity's factors (model-dcf's drivers)

    def implied(d, key):
        x = imp.get(d)
        if x is None:
            return None
        return x.get(key) if x.get("status") == "ok" else "out of range"

    rows = [("5-year revenue CAGR", lambda c: res[c]["rev_cagr5"], PCT,
             implied(factors[0], "rev_cagr5") if len(factors) == 1 else None),
            ("Gross margin, year 5", lambda c: res[c]["gm_end"], PCT, implied("dgm", "gm_end"))]
    if len(factors) > 1:
        rows += [(f"{f}: 5-year CAGR", lambda c, f=f: res[c]["factor_cagr5"][f], PCT, implied(f, "driver_cagr5"))
                 for f in factors]
    rows += [("WACC", lambda c: res[c]["inputs"]["wacc"], PCT, None),
             ("Terminal multiple", lambda c: res[c]["inputs"]["tv_mult"], X, None),
             ("DCF value per share", lambda c: res[c]["value_per_share"], MONEY, None),
             ("Terminal value share", lambda c: res[c]["tv_share"], PCT, None)]
    for lab, get, fmt, e in rows:
        w.text(f"A{r}", lab)
        for col, c in zip("BCD", cases):
            w.typed_(f"{col}{r}", get(c), fmt, note, fill=GREY)
        if e is not None:
            w.typed_(f"E{r}", e, fmt, f"reverse DCF on the base case, one driver at a time; {note}",
                     kind="s" if isinstance(e, str) else "n", fill=GREY)
        if lab == "DCF value per share":
            vr = r
            for col, c in zip("BCD", cases):
                b.ref[f"dcf_{c}"] = f"${col}${r}"
        r += 1
    for col, c in zip("BCD", cases):
        w.text(f"H{r - len(rows) + 'BCD'.index(col)}", f"{c.title()}: {b.plan['scenarios']['final'][c]['story']}",
               wrap=True)
    eps = b.ctx["metrics"]["eps"]
    e1 = b.ref.get("ntm1.pe")
    if not e1:
        w.text(f"A{r}", "NTM+1 EPS")
        w.link(f"B{r}", eps["ntm1"]["formula"], MONEY, eps["ntm1"]["value"])
        e1 = f"$B${r}"
        r += 1
    price = b.dcf["price"]["last"]["value"]
    vps = {c: res[c]["value_per_share"] for c in cases}
    for lab, den, dv in (("Implied P/E on NTM EPS", b.ref["ntm_eps_growth"], eps["ntm"]["value"]),
                         ("Implied P/E on NTM+1 EPS", e1, eps["ntm1"]["value"])):
        w.text(f"A{r}", lab)
        for col, c in zip("BCD", cases):
            w.formula(f"{col}{r}", f"IF({den}>0,{col}{vr}/{den},NA())", X, vps[c] / dv if _ok(dv) and dv > 0 else None)
        r += 1
    w.text(f"A{r}", "% vs today's price")
    for col, c in zip("BCD", cases):
        w.formula(f"{col}{r}", f"{col}{vr}/{b.ref['price']}-1", PCT, vps[c] / price - 1)
    r += 1
    # Bear vs the blended risk price, Base vs the blended reward, Bull vs the tree's top target (written by sec7_tree)
    w.text(f"A{r}", "vs the multiple target (bear: blended risk, base: blended reward, bull: the tree's top)")
    gr = r
    for col, c, t in (("B", "bear", "blended_risk"), ("C", "base", "blended_reward")):
        tv = b.want[t]
        w.formula(f"{col}{r}", f"IF({b.ref[t]}>0,{col}{vr}/{b.ref[t]}-1,NA())", PCT,
                  vps[c] / tv - 1 if _ok(tv) and tv > 0 else None)
    b.later.append(lambda: _bull_vs_top(b, f"D{gr}", f"D{vr}", vps["bull"]))
    r += 1
    w.text(f"A{r}", "DCF vs multiple target")
    for col, c in zip("BCD", cases):
        flag = None
        if col != "D":
            g = w.expected[f"{col}{gr}"]
            flag = None if g is None else ("gap > 25%: see note" if abs(g) > 0.25 else "ok")
        w.formula(f"{col}{r}", f'IF(ABS({col}{gr})>0.25,"gap > 25%: see note","ok")', "General", flag)
        if col == "D":
            b.later.append(lambda ref=f"D{r}": w.expected.__setitem__(
                ref, None if w.expected[f"D{gr}"] is None else
                ("gap > 25%: see note" if abs(w.expected[f"D{gr}"]) > 0.25 else "ok")))
    return r + 2


def _bull_vs_top(b, ref, vps_ref, vps):
    """Bull DCF vs the tree's highest target that is not itself a DCF case (so bull is not compared with itself)."""
    tops = [(c, v) for c, v, link in b.tree_targets if not (link or "").startswith("dcf_")] or \
        [(b.ref["blended_reward"].replace("$", ""), b.want["blended_reward"])]
    cells = ",".join(c for c, _ in tops)
    top = max(v for _, v in tops) if all(_ok(v) for _, v in tops) else None
    b.w.formula(ref, f"IF(MAX({cells})>0,{vps_ref}/MAX({cells})-1,NA())", PCT,
                vps / top - 1 if top is not None and top > 0 else None)


def sec7_tree(b, r):
    w, P = b.w, b.ref["price"]
    price = b.dcf["price"]["last"]["value"]
    header(b, r, "7. Probability tree", ("Target", "Return", "Probability"))
    r += 1
    first, rows = r, []
    b.tree_targets = []
    for t in b.plan["tree"]:
        name, tg = t["name"], t["target"]
        if "link" in tg:
            w.text(f"A{r}", name)
            tv = b.want.get(tg["link"]) if tg["link"].startswith("blended_") else \
                b.result[tg["link"][4:]]["value_per_share"]
            w.formula(f"B{r}", b.ref[tg["link"]], MONEY, tv)
        else:
            put_input(b, r, f"tree.{name}.target", MONEY)
            tv = val(b.used[f"tree.{name}.target"])
        pv = val(b.used[f"tree.{name}.prob"])
        w.formula(f"C{r}", f"B{r}/{P}-1", PCT, tv / price - 1 if _ok(tv) else None)
        put_input(b, r, f"tree.{name}.prob", PCT)
        w.text(f"H{r}", f"{t.get('story', '')} Probability: {b.pin[f'tree.{name}.prob']['reason']}", wrap=True)
        b.tree_targets.append((f"B{r}", tv, tg.get("link")))
        rows.append((tv, pv))
        r += 1
    last = r - 1
    ok = all(_ok(t, p) for t, p in rows)
    ev = sum(t * p for t, p in rows) if ok else None
    try:
        ev, _ = valmath.tree(rows, price) if ok else (None, None)
    except ValueError:                   # the user's probabilities don't sum to 100%: the sheet still multiplies out
        pass
    w.text(f"A{r}", "Probability-weighted")
    w.formula(f"B{r}", f"SUMPRODUCT(B{first}:B{last},D{first}:D{last})", MONEY, ev)
    w.formula(f"C{r}", f"B{r}/{P}-1", PCT, ev / price - 1 if ev is not None else None)
    w.formula(f"D{r}", f"SUM(D{first}:D{last})", PCT, sum(p for _, p in rows) if ok else None)
    b.ref["tree_ev"] = f"$B${r}"
    r += 1
    ts = [t for t, _ in rows]
    lo_, hi = (min(ts), max(ts)) if ok else (None, None)
    w.text(f"A{r}", "Where today's price sits (0% = worst case, 100% = best)")
    rng = f"B{first}:B{last}"
    w.formula(f"B{r}", f"IFERROR(({P}-MIN({rng}))/(MAX({rng})-MIN({rng})),NA())", PCT,
              (price - lo_) / (hi - lo_) if ok and hi > lo_ else None)
    return r + 2


SECTIONS = (sec0_today, sec1_multiples, sec2_growth, sec3_earnings_power, sec4_rr, sec5_irr, sec6_dcf, sec7_tree)


# ---------------------------------------------------------------- the workbook
def _move_after(pkg, name, after):
    """Copied from model-dcf build.py, Nov 2026; keep in sync.
    Put tab `name` right after `after` (if that tab exists, else last); keeps every other tab in order."""
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


def write_tab(pkg, w):
    """Replace the Valuation tab whole (chart-free), put it after Multiples (else last), attach the notes. As model-dcf's
    write_tab does."""
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


def _values_path(model, work, ctx):
    """context.py's recalculated copy in W/values (reused, never recalculated here)."""
    p = os.path.join(work, "values", os.path.basename(model))
    if os.path.exists(p):
        return p
    if ctx.get("values") and os.path.exists(ctx["values"]):
        return ctx["values"]
    raise SystemExit(f"model-valuation: no recalculated copy of {os.path.basename(model)} in {work}/values. Run "
                     "context.py first.")


def _last_result(work):
    n = [int(m.group(1)) for f in os.listdir(work) if (m := re.fullmatch(r"scenarios_result_(\d+)\.json", f))]
    if not n:
        raise SystemExit(f"model-valuation: no scenarios_result_<n>.json in {work}. Run scenario_eval.py eval first.")
    return max(n), json.load(open(os.path.join(work, f"scenarios_result_{max(n)}.json")))


def build(model, work, ticker, out):
    if os.path.abspath(out) == os.path.abspath(model):
        raise SystemExit("model-valuation: --out must be a copy, not the model itself.")
    ctx = json.load(open(os.path.join(work, "context.json")))
    dcf = json.load(open(os.path.join(work, "dcf_ctx.json")))
    plan = json.load(open(os.path.join(work, "valuation_plan.json")))
    rnd, result = _last_result(work)
    wp = os.path.join(work, "inputs_written.json")
    written = json.load(open(wp)) if os.path.exists(wp) else None
    values = _values_path(model, work, ctx)
    used, changed = resolve_inputs(model, plan, written, values)

    pkg = Package(model)
    st = Styles(pkg.text("xl/styles.xml"))
    w = W(st)
    mm = ModMap(model)
    by_col = {c: p for p, c in mm.labels.items()}
    b = SimpleNamespace(w=w, ctx=ctx, dcf=dcf, plan=plan, pin=plan_inputs(plan), used=used, changed=changed,
                        ticker=ticker, ref={}, mm=mm, values=values, result=result, round=rnd, work=work, later=[],
                        year_of=lambda ref: by_col.get(re.search(r"\$?([A-Z]+)\$?\d+$", ref).group(1), "?"))
    r = sec_title(b, 1)
    for sec in SECTIONS:
        r = sec(b, r)
    for f in b.later:                         # cells that point forward (section 6 -> the tree)
        f()
    a_texts = list(w.col_a.values())
    for key in w.inputs:                      # inputs are found again on a rerun by their column-A text
        if a_texts.count(label_of(key)) != 1:
            raise SystemExit(f"model-valuation: the label {label_of(key)!r} appears {a_texts.count(label_of(key))} "
                             "times in column A; rename the tree row so it is unique.")

    w.sh.comments = w.notes
    w.sh.freeze = "B3"
    w.sh.widths.update({1: 40, 2: 14, 3: 14, 4: 14, 5: 14, 6: 14, 7: 3, 8: 90})
    warnings = []
    # A workbook-wide name pointing at the old tab would dangle once it is replaced; xlsx.remove_sheet only drops
    # names scoped to the tab (localSheetId), so say so rather than edit the user's names. (From model-multiples.)
    dangling = re.findall(rf'<definedName\b(?![^>]*localSheetId)[^>]*name="([^"]*)"[^>]*>[^<]*\'?{TAB}\'?!',
                          pkg.text("xl/workbook.xml"))
    if dangling:
        warnings.append(f"Workbook name(s) {', '.join(dangling)} refer to the old {TAB} tab and will show #REF! after "
                        "the rebuild; re-point or delete them.")
    write_tab(pkg, w)
    pkg.put("xl/styles.xml", st.render())
    pkg.finish()
    pkg.save(out)
    import notebox
    notebox.fix(out, out, since=model)       # this tab's note boxes open readable (other tabs untouched)
    json.dump({"expected": w.expected, "typed": w.typed, "links": w.links, "formulas": w.formulas,
               "inputs": w.inputs, "ref": b.ref, "formula_text": w.ftext, "na": w.na}, open(os.path.join(work, "layout.json"), "w"), indent=0, default=str)
    json.dump({k: x["value"] for k, x in b.pin.items()},
              open(os.path.join(work, "inputs_written.next.json"), "w"), indent=1)
    return {"tab": TAB, "round": rnd, "user_kept": {k: {"agent": a, "yours": u} for k, (a, u) in changed.items()},
            "warnings": warnings}


def main():
    ap = argparse.ArgumentParser()
    for a in ("model", "work", "ticker", "out"):
        ap.add_argument(f"--{a}", required=True)
    a = ap.parse_args()
    print(json.dumps(build(a.model, a.work, a.ticker.upper(), a.out), indent=1, default=str))


if __name__ == "__main__":
    main()
