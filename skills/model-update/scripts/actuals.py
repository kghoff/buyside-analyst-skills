"""Enter a reported quarter into a COPY of the model (MOD tab, raw XML). See the spec's 'Entering actuals'.

usage: python3 actuals.py --model MODEL --quarter "Q3 26E" --match match.json --values values.json --out OUT.xlsx --state state.json [--restate yes|no]
       python3 actuals.py --model MODEL --quarter "Q3 26" --match match_10q.json --out OUT.xlsx --state state.json --tenq [--take-10q refs.json]
--values: MOD's values before the print (the recalculated grid match.py used); without it the model's cached values.
Prints a JSON report: typed, formulas, placeholders (ref, key, kind, value), awaiting (ref, key, kind: 10-Q / 10-K /
driver / manual), typed_subtotals, restated, restate_skipped, restate_knock_on, header, waiting_read_elsewhere
(blank waiting cells that formulas in other columns read: they show errors or zeros there until the filing).

What goes in the reported quarter (and on a Q4 the year column), row by row, following the year-ago column:
- STRUCTURE there is copied: a formula with no constant and no absolute reference whose references are all in its
  own column or earlier ones (=L4-L6, SUM(L14:L16), a TTM sum, beginning cash = last quarter's ending cash).
  Anything else (plugs reading the year column, constants inside formulas, absolute references, other tabs) is an
  INPUT: the release value if the row is mapped, else the cell waits.
- A waiting cell keeps the pre-print forecast VALUE (from --values, never a formula) as a constant in ORANGE with the
  note 'Update: forecast placeholder (<value>), awaiting <10-Q|10-K|driver|manual>; not reported', so the formulas
  that read it keep working. No pre-print value: it stays blank. A placeholder is never a reported value.
- Q2/Q3 cash flow from a year-to-date release: '=<printed YTD in model sign>-<earlier quarters>', blue.
- Q4: where last year's Q4 is 'FY less Q1-Q3' (or '= FY' for a balance), the year column is typed from the
  release's full-year value and Q4 is that plug; with no full-year value Q4 is typed and the year sums (flows) or
  links (balances); a per-share / share-count / rate line waits instead of summing.
- Structure formulas over a placeholder stay formulas; only where the release PRINTS the subtotal is the printed
  value typed (typed_subtotals, saved in state.json; the filing rerun (fill_tenq) puts the formula back)."""
import argparse
import json
import os
import re
import sys

import openpyxl
from openpyxl.formula.tokenizer import Tokenizer
from openpyxl.formula.translate import Translator
from openpyxl.utils import column_index_from_string as cnum, get_column_letter as cname

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from modmap import ModMap                      # noqa: E402
from xledit import set_cells, unshare          # noqa: E402
from xlsx import Package, Styles               # noqa: E402
import mnotes                                  # noqa: E402

TAB = "MOD"
BLUE, BLACK, ORANGE = "FF0000FF", "FF000000", "FFC65911"
CELL = re.compile(r"^(\$?)([A-Z]{1,3})(\$?)(\d+)$")
NOT_ADDITIVE = re.compile(r"shares|per share|\beps\b|rate|ratio|margin|%|average|price", re.I)
MAX_RANGE = 20000
ERRORS = ("#REF!", "#DIV/0!", "#VALUE!", "#NAME?", "#N/A", "#NUM!", "#NULL!")


def refs(formula):
    """(cells the formula reads [(col, row, absolute)], has a numeric constant, reads something else: another tab, a
    name, a whole row or column). Ranges are expanded (SUM(L14:L16) reads L15 too); function names are not cells."""
    try:
        items = Tokenizer("=" + formula).items
    except Exception:
        return [], False, True
    out, num, other = [], False, False
    for t in items:
        if t.type != "OPERAND":
            continue
        if t.subtype == "NUMBER":
            num = True
        elif t.subtype == "RANGE":
            ends = [CELL.match(x) for x in t.value.split(":")]
            if "!" in t.value or len(ends) > 2 or not all(ends):
                other = True
                continue
            ab = any(e.group(1) or e.group(3) for e in ends)
            (c1, r1), (c2, r2) = [(cnum(e.group(2)), int(e.group(4))) for e in (ends[0], ends[-1])]
            if (abs(c2 - c1) + 1) * (abs(r2 - r1) + 1) > MAX_RANGE:
                other = True
                continue
            out += [(cname(c), r, ab) for c in range(min(c1, c2), max(c1, c2) + 1)
                    for r in range(min(r1, r2), max(r1, r2) + 1)]
    return out, num, other


def deps(formula):
    return {f"{c}{r}" for c, r, _ in refs(formula)[0]}


def structure(formula, col):
    """A formula that only arranges numbers already in the model: no numeric constant, no absolute reference, nothing
    from another tab, and every reference in this column or an EARLIER one (=L4-L6, SUM(L14:L16), a TTM
    SUM(I386:L386), an average of earlier quarters, beginning cash = last quarter's ending cash). Only such a formula
    is copied from the year-ago column. Anything else is an input: a constant inside, an absolute reference, or a
    later column (a Q4 plug reads the year column to its right)."""
    rs, num, other = refs(formula)
    return bool(rs) and not num and not other and all(cnum(c) <= cnum(col) and not a for c, _, a in rs)


def _within(formula, row, cols, need=None):
    """Only relative references to this row in `cols` (and `need` among them), no constants, nothing else."""
    rs, num, other = refs(formula)
    used = {c for c, _, _ in rs}
    return bool(rs) and not num and not other and all(r == row and not a for _, r, a in rs) and used <= set(cols) \
        and (need is None or need in used)


def _tr(formula, src, dst):
    return Translator("=" + formula, origin=src).translate_formula(dst)[1:]


def _part(pkg):
    return next(p for n, _, _, p in pkg.sheets() if n == TAB)


def _cells(model):
    """{ref: formula text without '='}, {ref: value} and {ref: font rgb} straight from the file (formulas as written)."""
    ws = openpyxl.load_workbook(model)[TAB]
    f, v, color = {}, {}, {}
    for row in ws.iter_rows():
        for c in row:
            if c.value is None:
                continue
            if isinstance(c.value, str) and c.value.startswith("="):
                f[c.coordinate] = c.value[1:]
            else:
                v[c.coordinate] = c.value
            rgb = c.font.color.rgb if c.font is not None and c.font.color is not None else None
            if isinstance(rgb, str):
                color[c.coordinate] = rgb
    return f, v, color


def _style_of(xml, ref):
    m = re.search(rf'<c r="{ref}"(?:\s[^>]*?)?\ss="(\d+)"', xml)
    return int(m.group(1)) if m else 0


def _fmt(x):
    return f"{x:,.2f}" if abs(x) < 10 and x != int(x) else f"{x:,.1f}"


def _num_text(x):
    return f"{round(x, 6):.15g}"


def _note(e, earlier=True, value=None, what=""):
    v = value if value is not None else e.get("printed")
    v = _fmt(v) if v is not None else ""
    ytd = " YTD" if e.get("ytd") and earlier else ""
    tail = " less earlier quarters in MOD" if e.get("ytd") and earlier else ""
    src = f"{e['file']} line {e['lineno']}"
    if e.get("lines"):                                # a row that is the sum of printed lines cites each one
        src = f"{e['file']} lines " + " + ".join(str(x["lineno"]) for x in e["lines"])
    return f"{mnotes.NOTE}{e['label']}{what}{ytd} {v}{tail} - {src}"


def _input(m, e, row, q, qc):
    """What to write for a reported line: (kind, value, note). A year-to-date cash flow after Q1 is the house form
    '=<printed YTD in model sign>-<earlier quarters>' (an input formula, blue, like history); else the typed value."""
    qs = m.quarters_of(m.fy_of(q))
    earlier = qs[:qs.index(q)]
    if e.get("ytd") and earlier:
        ytd = e["printed"] * e["factor"] * e["sign"]
        return "fi", _num_text(ytd) + "".join(f"-{m.col(p)}{row}" for p in reversed(earlier)), _note(e)
    return "n", float(e["cur"]), _note(e, earlier=False)


STATEMENTS = ("INCOME STATEMENT", "BALANCE SHEET", "ASSETS", "LIABILITIES", "CASH FLOW", "NON-GAAP", "KEY OPERATING")


def _kind_of(m, row, key, formulas, values, q, year_ago=None):
    """Why a cell waits: 'driver' (a DRIVERS section, or a row with no history: model-forecast's); 'manual' (an
    analysis row whose year-ago formula is not structure (a constant, an absolute cell, a later column, e.g. =L11*4):
    no filing prints it, the user re-enters it); else the filing that will print it: '10-Q', or '10-K' for a Q4."""
    sec = key.split(" | ")[0].upper()
    if "DRIVERS" in sec:
        return "driver"
    if year_ago in formulas and not sec.startswith(STATEMENTS):
        return "manual"
    now = {q.rstrip("E"), m.fy_of(q).rstrip("E")}
    actual = [p for p in m.order if not p.endswith("E") and p not in now]
    if not any(f"{m.col(p)}{row}" in formulas or f"{m.col(p)}{row}" in values for p in actual):
        return "driver"
    return "10-K" if q.startswith("Q4") else "10-Q"


def _knock_on(m, diffs, formulas, values):
    """For each prior-period difference with a cell: the same row's Q4 / FY formulas of that year that read it (a Q4
    plug = FY less Q1-Q3 moves when a quarter is restated; FY = SUM moves). Reported so the ask can show it."""
    period = {c: p for p, c in m.labels.items()}
    out = []
    for d in diffs:
        ref = d.get("ref")
        if not ref or ref in formulas:
            continue
        col, row = re.match(r"([A-Z]+)(\d+)$", ref).groups()
        p = period.get(col, "")
        if not p:
            continue
        fy = p if not m.is_q(p) else m.fy_of(p)
        cols = [m.col(x) for x in m.quarters_of(fy)] + [m.col(fy)]
        delta = (d["new"] or 0) - (d["model"] or 0)
        for c in cols:
            f = formulas.get(f"{c}{row}")
            if c != col and f and ref in deps(f):
                sign = -1 if re.search(rf"-\s*{ref}\b", f) else 1
                out.append({"ref": ref, "moves": f"{c}{row}", "period": period.get(c), "formula": "=" + f,
                            "by": round(sign * delta, 6)})
    return out


def _cached(model):
    """MOD's cached values (what Excel last calculated): the pre-print forecast a placeholder keeps."""
    ws = openpyxl.load_workbook(model, data_only=True)[TAB]
    return {c.coordinate: c.value for row in ws.iter_rows() for c in row if c.value is not None}


def build(model, quarter, res, out, state_path, restate=False, grid=None):
    m = ModMap(model)
    q, py = quarter, m.pyq(quarter)
    qc, pc = m.col(q), m.col(py)
    fy, pfy = m.fy_of(q), m.fy_of(py)
    fc, pfc = m.col(fy), m.col(pfy)
    q4 = q.startswith("Q4")
    cq = [m.col(p) for p in m.quarters_of(fy)]          # this year's quarter columns
    pq = [m.col(p) for p in m.quarters_of(pfy)]         # last year's
    formulas, values, colors = _cells(model)
    pkg = Package(model)
    part = _part(pkg)
    xml = unshare(pkg.text(part), TAB, TAB)
    st = Styles(pkg.text("xl/styles.xml"))
    combined_rows = {r for c in res["combined"] for r in c["rows"]}
    mapped = {e["row"]: e for e in res["matched"] if e["row"] not in combined_rows
              and (e.get("cur") is not None or (q4 and e.get("fy_cur") is not None))}   # annual: the year only
    if grid is None:
        grid = _cached(model)
    has = lambda ref: ref in formulas or ref in values
    plan = {}                                         # ref -> {k: n | fi | fs | '', v, c, note, alt}

    def quarter_cell(row, e):
        ref, pref = f"{qc}{row}", f"{pc}{row}"
        e = e if e and e.get("cur") is not None else None     # an annual line prints no quarter
        pf = formulas.get(pref)
        if pf is not None and structure(pf, pc) and (e or has(ref)):     # never new content in an empty cell
            return {"k": "fs", "v": _tr(pf, pref, ref), "alt": _input(m, e, row, q, qc) if e else None}
        if e:
            k, v, note = _input(m, e, row, q, qc)
            return {"k": k, "v": v, "c": BLUE, "note": note}
        return {"k": ""} if has(ref) else None

    def fy_cell(row, e, fyv, label):
        """The year column on a Q4 print: last year's structure if it has one, else the full-year value, else the
        sum of the quarters (flows only), else it waits."""
        rf, pf = f"{fc}{row}", formulas.get(f"{pfc}{row}")
        if pf is not None and (e or has(rf)) and (_within(pf, row, [pfc] + pq) or structure(pf, pfc)):
            t = _tr(pf, f"{pfc}{row}", rf)
            if structure(t, fc) or _within(t, row, [fc] + cq):
                alt = ("n", float(fyv), _note(e, False, fyv, f" {fy.rstrip('E')}")) if e and fyv is not None else None
                return {"k": "fs", "v": t, "alt": alt}
        if e and fyv is not None:
            return {"k": "n", "v": float(fyv), "c": BLUE, "note": _note(e, False, fyv, f" {fy.rstrip('E')}")}
        if e and e.get("kind") == "bs":
            return {"k": "fs", "v": f"{qc}{row}"}
        if e and not NOT_ADDITIVE.search(label) and not NOT_ADDITIVE.search(e["key"]):
            return {"k": "fs", "v": f"SUM({cq[0]}{row}:{cq[-1]}{row})"}
        return {"k": ""} if has(rf) or e else None

    def year_cells(row, e):
        """Q4 print: the quarter and the fiscal-year column, the way last year's pair is built."""
        r4, rf = f"{qc}{row}", f"{fc}{row}"
        p4 = formulas.get(f"{pc}{row}")
        fyv = None if not e else e.get("fy_cur", e["cur"] if e.get("kind") == "bs" else None)
        label = (e or {}).get("label", "")
        if p4 is not None and _within(p4, row, [pfc] + pq[:-1], need=pfc):
            # last year Q4 = FY less Q1-Q3 (or = FY for a balance): the year is the input, Q4 follows it
            t = _tr(p4, f"{pc}{row}", r4)
            ok = _within(t, row, [fc] + cq[:-1], need=fc)
            color = colors.get(f"{pc}{row}", BLUE)
            if e and fyv is not None and ok:
                link = deps(t) == {rf}
                return {rf: {"k": "n", "v": float(fyv), "c": BLUE, "note": _note(e, False, fyv, f" {fy.rstrip('E')}")},
                        r4: {"k": "fi", "v": t, "c": color,
                             "note": f"{mnotes.NOTE}{label} " + ("year-end balance (= the year column)" if link else
                                                                  "= the full year less Q1-Q3 in MOD")
                                     + f" - {e['file']} line {e['lineno']}"}}
            if e and e.get("cur") is None:             # an annual line, no plug possible: the year typed, Q4 waits
                return {rf: fy_cell(row, e, fyv, label), r4: {"k": ""} if has(r4) else None}
            if e:                                      # no full-year value printed: type Q4, the year follows it
                return {r4: {"k": "n", "v": float(e["cur"]), "c": BLUE, "note": _note(e, False)},
                        rf: fy_cell(row, e, None, label)}
            # not printed: the year keeps its own structure (or waits); Q4 is the plug over it, and waits (saved,
            # restored by the 10-K rerun) while the year does
            return {rf: fy_cell(row, None, None, label),
                    r4: {"k": "fs", "v": t, "c": color} if ok else ({"k": ""} if has(r4) else None)}
        return {r4: quarter_cell(row, e), rf: fy_cell(row, e, fyv, label)}

    for row, key, _ in m.lines:
        if row <= 2:
            continue                                  # title and period-header rows
        e = mapped.get(row)
        cells_ = year_cells(row, e) if q4 else {f"{qc}{row}": quarter_cell(row, e)}
        plan.update({r: p for r, p in cells_.items() if p is not None})
    waiting = {r for r, p in plan.items() if p["k"] == ""}
    typed_sub, tainted, changed = [], set(waiting), True
    while changed:
        # a structure formula over a placeholder stays a formula (the placeholder holds a number), unless the release
        # PRINTS its value: then the printed subtotal is typed (restored by the filing rerun)
        changed = False
        for ref, p in list(plan.items()):
            if p["k"] != "fs" or ref in tainted or not deps(p["v"]) & tainted:
                continue
            if p.get("alt"):
                k, v, note = p["alt"]
                plan[ref] = {"k": k, "v": v, "c": BLUE, "note": note}
                typed_sub.append({"ref": ref, "formula": p["v"]})
            else:
                tainted.add(ref)
            changed = True
    key_of = {}
    for r, k, _ in m.lines:
        key_of[f"{qc}{r}"] = key_of[f"{fc}{r}"] = (r, k)
    row_of = lambda ref: int(re.match(r"[A-Z]+(\d+)$", ref).group(1))

    def why(ref):
        r, k = key_of.get(ref, (row_of(ref), None))
        yr = f"{pfc if ref.startswith(fc) and re.match(rf'{fc}\d+$', ref) else pc}{r}"
        return _kind_of(m, r, k or "", formulas, values, q, yr)
    kinds = {r: why(r) for r in waiting}
    placeholders = []
    for ref in sorted(waiting):                       # the pre-print forecast VALUE, flagged; never a formula
        v = grid.get(ref)
        if isinstance(v, bool) or not isinstance(v, (int, float, str)) or v in ERRORS or v == "":
            continue                                  # nothing to keep (no value, or an error): stays blank
        v = float(v) if not isinstance(v, str) else v  # a typed 'n.a' is kept as the text it was
        plan[ref] = {"k": "p", "v": v, "note": f"{mnotes.NOTE}forecast placeholder ({_fmt(v) if not isinstance(v, str) else v}),"
                                               f" awaiting {kinds[ref]}; not reported"}
        placeholders.append({"ref": ref, "key": key_of.get(ref, (0, None))[1], "kind": kinds[ref], "value": v})
    cells, notes, typed = {}, {}, {}
    for ref, p in plan.items():
        s = _style_of(xml, ref)
        if p["k"] == "n":
            cells[ref] = ("n", p["v"], st.recolor(s, BLUE))
            typed[ref] = p["v"]
        elif p["k"] == "p":
            cells[ref] = ("s" if isinstance(p["v"], str) else "n", p["v"], st.recolor(s, ORANGE))
        elif p["k"] == "fi":
            cells[ref] = ("f", p["v"], st.recolor(s, p.get("c", BLUE)))
            e = mapped.get(row_of(ref))
            if e and e.get("cur") is not None and re.match(rf"{qc}\d+$", ref):
                typed[ref] = float(e["cur"])          # the discrete quarter, for the 10-Q comparison
        elif p["k"] == "fs":
            cells[ref] = ("f", p["v"], st.recolor(s, p.get("c", BLACK)))
        else:
            cells[ref] = ("", None, s)
        if p.get("note"):
            notes[ref] = p["note"]
    rewritten = list(cells)
    cells[f"{qc}2"] = ("s", q.rstrip("E"), _style_of(xml, f"{qc}2"))
    header = [q.rstrip("E")]
    if q4:
        prior = values.get(f"{pfc}2")
        num = isinstance(prior, (int, float)) and not isinstance(prior, bool)
        cells[f"{fc}2"] = ("n", int(fy[:4]), _style_of(xml, f"{fc}2")) if num else ("s", fy.rstrip("E"), _style_of(xml, f"{fc}2"))
        header.append(int(fy[:4]) if num else fy.rstrip("E"))
    restated, skipped = [], []
    if restate:
        for d in res["diffs"]:
            if not d.get("ref"):
                skipped.append({**d, "why": "year-to-date difference: no single cell"})
            elif d["ref"] in formulas:
                skipped.append({**d, "why": "the model cell is a formula"})
            else:
                cells[d["ref"]] = ("n", float(d["new"]), st.recolor(_style_of(xml, d["ref"]), BLUE))
                notes[d["ref"]] = f"{mnotes.NOTE}recast in {d['file']} line {d['lineno']} (was {d['model']})"
                restated.append(d["ref"])
    knock = _knock_on(m, res["diffs"], formulas, values)
    xml, _ = set_cells(xml, cells, replace=True)
    pkg.put(part, xml)
    mnotes.drop_notes(pkg, part, rewritten)           # model-forecast's 'Plan: ' notes (and stale own notes)
    mnotes.add_notes(pkg, part, notes)
    pkg.put("xl/styles.xml", st.render())
    pkg.finish()
    pkg.save(out)
    import modfill; modfill.fix(out, out)
    import notebox; notebox.fix(out, out)
    state = {"quarter": q.rstrip("E"), "column": qc, "fy_column": fc if q4 else None,
             "awaiting": [{"ref": r, "key": key_of.get(r, (0, None))[1], "kind": kinds[r]} for r in sorted(waiting)],
             "placeholders": placeholders, "typed_subtotals": typed_sub, "release_values": typed,
             "combined": res["combined"], "tenq_checked": False}
    json.dump(state, open(state_path, "w"), indent=1)
    written = {qc, fc} if q4 else {qc}
    blank = waiting - {p["ref"] for p in placeholders}
    readers = {}                                      # blank waiting cells other columns' formulas read (errors there)
    for ref, f in formulas.items():
        if re.match(r"[A-Z]+", ref).group(0) not in written:
            for d in deps(f) & blank:
                readers.setdefault(d, []).append(ref)
    return {"typed": sum(1 for r in rewritten if plan[r]["k"] == "n"),
            "formulas": sum(1 for k, *_ in (cells[r] for r in rewritten) if k == "f"),
            "placeholders": placeholders, "awaiting": state["awaiting"], "typed_subtotals": typed_sub, "restated": restated,
            "restate_skipped": skipped, "restate_knock_on": knock, "header": header,
            "waiting_read_elsewhere": {d: sorted(r) for d, r in sorted(readers.items())}}


def fill_tenq(model, res, out, state_path, take=None):
    """10-Q (or 10-K) rerun: replace the waiting cells it prints (placeholders and blanks: blue, with a note), list
    where it differs from the release (never from a placeholder: that is a forecast, not a reported value), and bring
    back every typed subtotal's formula once none of the cells it reads waits. A 10-K's annual line fills the year
    column only; Q4 follows it where print night kept last year's plug ('FY less Q1-Q3')."""
    state = json.load(open(state_path))
    qc, fc = state["column"], state.get("fy_column")
    m = ModMap(model)
    q = state["quarter"]
    pkg = Package(model)
    part = _part(pkg)
    xml = unshare(pkg.text(part), TAB, TAB)
    st = Styles(pkg.text("xl/styles.xml"))
    waiting = {a["ref"] for a in state["awaiting"]}
    saved = {t["ref"]: t["formula"] for t in state["typed_subtotals"]}
    rv = state["release_values"]
    cells, notes, diffs, filled = {}, {}, [], []
    new = {}
    q_label = next(p for p in m.order if p.rstrip("E") == q)

    def differs(ref, e, value):
        if ref in rv and abs(rv[ref] - value) > e["tol"]:
            diffs.append({"ref": ref, "key": e["key"], "release": rv[ref], "tenq": value, "file": e["file"],
                          "lineno": e["lineno"]})
            return True
        return False
    for e in res["matched"]:
        row = e["row"]
        if fc and e.get("fy_cur") is not None:
            r = f"{fc}{row}"
            if r in waiting and r not in saved:
                cells[r] = ("n", float(e["fy_cur"]), st.recolor(_style_of(xml, r), BLUE))
                notes[r] = _note(e, False, e["fy_cur"], f" {m.fy_of(q_label).rstrip('E')}")
                filled.append(r)
            elif differs(r, e, e["fy_cur"]) and take and r in take and r not in saved:
                cells[r] = ("n", float(e["fy_cur"]), st.recolor(_style_of(xml, r), BLUE))
                notes[r] = _note(e, False, e["fy_cur"], f" {m.fy_of(q_label).rstrip('E')}") + f" (release said {rv[r]})"
        ref = f"{qc}{row}"
        if e.get("cur") is None:                     # an annual line: the year column only (Q4 is its plug)
            continue
        new[ref] = e
        if ref in saved:
            pass                                      # a structure formula comes back below, never a typed value
        elif ref in waiting:
            k, v, note = _input(m, e, row, q_label, qc)
            cells[ref] = ("f" if k == "fi" else "n", v, st.recolor(_style_of(xml, ref), BLUE))
            notes[ref] = note
            filled.append(ref)
            continue
        if differs(ref, e, e["cur"]) and take and ref in take and ref not in saved:
            k, v, note = _input(m, e, row, q_label, qc)
            cells[ref] = ("f" if k == "fi" else "n", v, st.recolor(_style_of(xml, ref), BLUE))
            notes[ref] = note + f" (release said {rv[ref]})"
    for c in state["combined"]:
        parts = [new.get(f"{qc}{r}") for r in c["rows"]]
        if c.get("cur") is not None and all(parts) and abs(sum(p["cur"] for p in parts) - c["cur"]) > c["tol"] * len(parts):
            diffs.append({"ref": None, "key": " + ".join(c["keys"]), "release": c["cur"],
                          "tenq": sum(p["cur"] for p in parts), "file": c["file"], "lineno": c["lineno"], "combined": True})
    waiting -= set(filled)
    restored, pending, changed = [], dict(saved), True
    while changed:                                    # restoring one can free another (NI -> EPS)
        changed = False
        for ref, f in list(pending.items()):
            if not deps(f) & waiting:
                cells[ref] = ("f", f, st.recolor(_style_of(xml, ref), BLACK))
                notes.pop(ref, None)
                restored.append(ref)
                waiting.discard(ref)
                del pending[ref]
                changed = True
    xml, _ = set_cells(xml, cells, replace=True)
    pkg.put(part, xml)
    mnotes.drop_notes(pkg, part, restored)
    mnotes.add_notes(pkg, part, notes)
    pkg.put("xl/styles.xml", st.render())
    pkg.finish()
    pkg.save(out)
    import modfill; modfill.fix(out, out)
    import notebox; notebox.fix(out, out)
    state["awaiting"] = [a for a in state["awaiting"] if a["ref"] in waiting]
    state["placeholders"] = [p for p in state.get("placeholders", []) if p["ref"] in waiting]
    state["typed_subtotals"] = [t for t in state["typed_subtotals"] if t["ref"] in pending]
    state["tenq_checked"] = not diffs or take is not None
    json.dump(state, open(state_path, "w"), indent=1)
    return {"filled": filled, "restored": restored, "differences": diffs, "awaiting": state["awaiting"],
            "placeholders": state["placeholders"]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True), ap.add_argument("--quarter", required=True)
    ap.add_argument("--match", required=True), ap.add_argument("--out", required=True)
    ap.add_argument("--state", required=True), ap.add_argument("--restate", default="no")
    ap.add_argument("--tenq", action="store_true"), ap.add_argument("--take-10q"), ap.add_argument("--values")
    a = ap.parse_args()
    if os.path.abspath(a.out) == os.path.abspath(a.model):
        sys.exit("--out must be a new file, not the model itself")
    res = json.load(open(a.match))
    if a.tenq:
        take = json.load(open(a.take_10q)) if a.take_10q else None
        print(json.dumps(fill_tenq(a.model, res, a.out, a.state, take), indent=1))
    else:
        grid = json.load(open(a.values))["MOD"] if a.values else None
        print(json.dumps(build(a.model, a.quarter, res, a.out, a.state, a.restate == "yes", grid), indent=1))


if __name__ == "__main__":
    main()
