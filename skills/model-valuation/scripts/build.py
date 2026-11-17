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
    return "C" if key.startswith("weight.") else "B"


class W:
    """Cell writer that remembers styles, what is typed / linked / formula / input, notes and expected values.
    (The pattern of model-multiples' build.W, plus input_ and notes.)"""

    def __init__(self, st):
        self.sh, self.st = Sheet(), st
        self.s = {}
        self.typed, self.links, self.formulas, self.expected = [], [], [], {}
        self.inputs, self.notes = {}, {}

    def style(self, color=BLACK, fmt="General", b=False, i=False, fill=None, sz=11, wrap=False):
        k = (color, fmt, b, i, fill, sz, wrap)
        if k not in self.s:
            self.s[k] = self.st.xf(color=color, fmt=fmt, b=b, i=i, fill=fill, sz=sz, align="left" if wrap else None)
        return self.s[k]

    def text(self, ref, t, **kw):
        self.sh.set(ref, "s", t, self.style(**kw))

    def typed_(self, ref, v, fmt, note, kind="n"):
        self.sh.set(ref, kind, v, self.style(BLUE, fmt))
        self.typed.append(ref)
        self.notes[ref] = note

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
    """{key: {value, anchor, [anchor_value], reason}}: the plan's inputs plus normalization's yellow cells."""
    out = dict(plan["inputs"])
    n = plan.get("normalization")
    if n:
        out.update({f"normalization.{k}": n[k] for k in ("margin", "multiple", "years")})
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
        lab, col = LABEL.get(key), col_of(key)
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
    b.w.text(f"A{r}", LABEL[key])
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


SECTIONS = (sec0_today, sec1_multiples, sec2_growth, sec3_earnings_power)     # Task 9 appends sections 4-7


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
                        ticker=ticker, ref={}, mm=mm, values=values, result=result, round=rnd,
                        year_of=lambda ref: by_col.get(re.search(r"\$?([A-Z]+)\$?\d+$", ref).group(1), "?"))
    r = sec_title(b, 1)
    for sec in SECTIONS:
        r = sec(b, r)

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
               "inputs": w.inputs, "ref": b.ref}, open(os.path.join(work, "layout.json"), "w"), indent=0, default=str)
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
