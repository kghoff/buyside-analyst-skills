"""Prove a built forecast: recalculate before and after in LibreOffice, then check that
  - the XML is valid, the balance sheet balances and cash ties (|check| < 0.1) in every forecast column,
  - no forecast cell is an error, annual flow = sum of quarters, annual balance = Q4,
  - each plan `guidance` item lands inside its range (or the plan says why not),
  - revenue is built from the key drivers: each plan `drivers` row feeds its line, no typed growth rate drives
    revenue (unless the plan sets `revenue_engine: "growth"` with a `growth_reason`), and each filings research check in
    `checks` has a number in every forecast year, inside its bounds (house default: a growth-rate engine is the
    last resort; the research exists to set the drivers, and the statements follow from them),
  - nothing else moved: a cell may differ only if it is in a MOD forecast column, or is a formula that reads
    (directly or through other changed cells) a MOD forecast column - "downstream of the forecast".

usage: python3 check.py --before MODEL.xlsx --after BUILT.xlsx --plan forecast_plan.json --work DIR [--report build_report.json]
Prints JSON; exit 1 on any problem. Writes DIR/forecast_headlines.md (revenue, growth, margins, EPS, FCF per forecast year)."""
import argparse
import json
import os
import re
import sys

import openpyxl
from openpyxl.utils import column_index_from_string as CI
from openpyxl.utils import get_column_letter as L

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lo                                                             # noqa: E402
import xlverify                                                       # noqa: E402
from modmap import ModMap                                             # noqa: E402

TOL = 0.1


def _row_of(m, label):
    """Row of the first line whose label (after ' | ') is `label`, or None."""
    return next((r for k, r in m.keys.items() if k.split(" | ", 1)[-1].lower() == label.lower()), None)


def _rows_of(m, label):
    return [r for k, r in m.keys.items() if k.split(" | ", 1)[-1].lower() == label.lower()]


def _half_unit(x):
    """A guide written as a rounded number matches within half a unit of its last written decimal (0.217 -> 0.0005)."""
    from decimal import Decimal
    exp = Decimal(repr(x)).normalize().as_tuple().exponent
    return 0.5 * 10 ** -max(0, -exp) + 1e-12


def check_grid(m, grid, plan, notes=None, preexisting=None):
    """grid {(row, col_letter): value} of MOD after recalculation. Returns a list of problem strings;
    guidance misses the plan explains go to `notes` instead. `preexisting` {(row, col_letter): formula text}: forecast
    cells that were already the same error before the forecast - a note, not a problem."""
    preexisting = preexisting or {}
    out = []
    fq, fy = m.forecast_quarters(), m.forecast_years()
    fcols = [(p, m.col(p)) for p in fq + fy]

    for name in ("Balance Check", "Cash Check"):
        rows = [r for k, r in m.keys.items()
                if re.sub(r" #\d+$", "", k.split(" | ", 1)[-1]).strip().lower().startswith(name.lower())]
        if not rows:
            out.append(f"{name} row is missing from MOD: balance/cash cannot be proven")
        for r in rows:
            for p, c in fcols:
                v = grid.get((r, c))
                if not isinstance(v, (int, float)) or isinstance(v, bool):
                    out.append(f"{name} is empty or not a number ({v!r}) in {p} (row {r})")
                elif abs(v) >= TOL:
                    out.append(f"{name} is {v:.3f} in {p} (row {r})")

    for (r, c), v in sorted(grid.items()):
        if isinstance(v, str) and v.startswith("#") and c in {x for _, x in fcols}:
            p = next(p for p, x in fcols if x == c)
            if (r, c) in preexisting:
                if notes is not None:
                    notes.append(f"already an error before the forecast: MOD!{c}{r} ({p}) {v} {preexisting[(r, c)]}")
            else:
                out.append(f"{v} in {p} row {r}")

    for e in plan.get("rows", []):                       # the evidence columns the plan writes must not be errors
        if e.get("history_template") and e["key"] in m.keys:
            r = m.row(e["key"])
            for p in [p for p in m.order if re.fullmatch(r"\d{4}", p)][-int(e.get("history_years", 5)):]:
                v = grid.get((r, m.col(p)))
                if isinstance(v, str) and (v.startswith("#") or v.startswith("Err:")):
                    out.append(f"{v} in the history ratio of '{e['key']}' ({p}): its history_template reads a row with no history")
    for e in plan.get("rows", []):
        if e.get("kind") not in ("flow", "balance"):
            continue
        r = m.row(e["key"])
        for y in fy:
            qs = m.quarters_of(y)
            fyv = grid.get((r, m.col(y)))
            if e["kind"] == "flow":
                parts = [grid.get((r, m.col(q))) for q in qs]
                if fyv is None and all(x is None for x in parts):
                    continue
                s = sum(x for x in parts if isinstance(x, (int, float)))
                if not isinstance(fyv, (int, float)) or abs(fyv - s) > TOL:
                    out.append(f"{e['key']} {y}: annual {fyv} differs from the sum of quarters {s:.3f}")
            else:
                q4 = grid.get((r, m.col(qs[-1])))
                if fyv is None and q4 is None:
                    continue
                if not (isinstance(fyv, (int, float)) and isinstance(q4, (int, float))) or abs(fyv - q4) > TOL:
                    out.append(f"{e['key']} {y}: annual {fyv} differs from Q4 {q4}")

    for g in plan.get("guidance", []):
        v = grid.get((m.row(g["key"]), m.col(g["period"])))
        lo_, hi_ = g.get("low"), g.get("high")
        if (isinstance(v, (int, float)) and (lo_ is None or v >= lo_ - _half_unit(lo_))
                and (hi_ is None or v <= hi_ + _half_unit(hi_))):
            continue
        want = (f"{lo_}-{hi_}" if lo_ is not None and hi_ is not None else
                f"at least {lo_}" if lo_ is not None else f"at most {hi_}")
        msg = f"{g['what']} {g['period']}: model {v} outside guidance ({want})"
        if g.get("outside"):
            if notes is not None:
                notes.append(f"{msg} (plan says: {g['outside']})")
        else:
            out.append(msg)
    return out


def _precedent_rows(fm, start):
    """Every MOD row a cell reads, directly or through other MOD formulas. fm {(row, col number): formula}."""
    seen, todo, rows = set(), [start], set()
    while todo:
        cell = todo.pop()
        if cell in seen:
            continue
        seen.add(cell)
        f = fm.get(cell)
        if not f:
            continue
        for tab, c1, r1, c2, r2 in _refs("MOD", f):
            if tab != "MOD" or r2 == BIG or c2 == 16384:
                continue
            for r in range(r1, r2 + 1):
                rows.add(r)
                todo += [(r, c) for c in range(c1, c2 + 1)]
    return rows


def _precedent_cells(fm, start):
    """Every MOD cell a cell reads, directly or through other MOD formulas: {(row, col number)}."""
    seen, todo = set(), [start]
    while todo:
        cell = todo.pop()
        if cell in seen:
            continue
        seen.add(cell)
        f = fm.get(cell)
        if not f:
            continue
        for tab, c1, r1, c2, r2 in _refs("MOD", f):
            if tab != "MOD" or r2 == BIG or c2 == 16384:
                continue
            todo += [(r, c) for r in range(r1, r2 + 1) for c in range(c1, c2 + 1)]
    return seen - {start}


def section_of(m, row):
    """The section (column A title) a MOD row sits in."""
    above = [(r, k) for k, r in m.keys.items() if r <= row]
    return max(above)[1].split(" | ", 1)[0] if above else ""


def check_shown_work(m, fm, plan, rev):
    """Rule: show the work, label everything and make the assumptions clear. Every forecast-year
    cell revenue reads sits in the REVENUE BUILD section, and no typed number is a calibration (a value someone solved
    for and typed in: it must be a formula on labelled, sourced rows)."""
    out = []
    fcols = {CI(m.col(p)) for p in m.forecast_quarters() + m.forecast_years()}
    r = m.row(rev)
    outside = set()
    for y in m.forecast_years():
        for (pr, pc) in _precedent_cells(fm, (r, CI(m.col(y)))):
            if pc in fcols and pr != r and section_of(m, pr) != "REVENUE BUILD":
                outside.add(pr)
    for pr in sorted(outside):
        lab = next((k for k, x in m.keys.items() if x == pr), f"row {pr}")
        out.append(f"revenue reads '{lab}' (row {pr}), outside the REVENUE BUILD section: move it there (move_rows)")
    typed = ("values", "rates", "annual_growth")
    for e in plan.get("rows", []):
        if any(e.get(t) for t in typed) and re.search(r"calibrat", e.get("source", ""), re.I):
            out.append(f"'{e['key']}' types in a calibrated number: show the calibration as formulas on labelled, "
                       "sourced rows instead")
    return out


def check_statements_are_formulas(m, plan):
    """Modeling convention: the only typed forecast numbers sit in the REVENUE BUILD and the driver sections; statement rows
    are formulas on them. A plan row elsewhere that types a rate, a schedule or a growth fails."""
    allowed = {"REVENUE BUILD"} | {d["title"] for d in plan.get("driver_sections", [])}
    out = []
    for e in plan.get("rows", []):
        if e["key"] not in m.keys:
            continue
        typed = e["method"] in ("growth", "pct_of", "days", "schedule") or (e["method"] == "seasonal" and not e.get("fy_template")) \
            or (e["method"] == "annual" and e.get("values"))
        if typed and section_of(m, m.row(e["key"])) not in allowed:
            out.append(f"'{e['key']}' types forecast numbers on a statement row: put the assumption in a driver "
                       "section (with its historical ratio) and make this row a formula on it")
    return out


def _revenue_key(m, plan):
    if plan.get("revenue_key"):
        return plan["revenue_key"]
    return next(k for k in m.keys if k.startswith("INCOME STATEMENT | ") and k.split(" | ")[1].lower().startswith("revenue"))


def identity_value(m, grid, ident, fy):
    """Revenue the identity gives at FY column `fy`: sum over terms of the product of their factors (an `average`
    factor is (this FY + prior FY) / 2). None if a factor has no number."""
    from methods import prior_fy
    total = 0.0
    for term in ident["terms"]:
        prod = 1.0
        for f in term["factors"]:
            r = m.row(f["key"])
            v = grid.get((r, m.col(fy)))
            if f.get("average"):
                p = grid.get((r, m.col(prior_fy(m, fy))))
                v = (v + p) / 2 if isinstance(v, (int, float)) and isinstance(p, (int, float)) else None
            if not isinstance(v, (int, float)) or isinstance(v, bool):
                return None
            prod *= v
        total += prod
    return total


def check_identity(m, grid, plan, rev):
    """`revenue_identity` (what /model-dcf extends 30 years) must reproduce revenue in every forecast year, and every
    factor needs a sourced long-run growth (the user owns it in the DCF)."""
    ident = plan.get("revenue_identity")
    if plan.get("revenue_engine", "drivers") == "growth" and not ident:
        return []
    if not ident or not ident.get("terms"):
        return ["no revenue_identity: name the MOD rows whose products sum to revenue (the DCF extends them)"]
    out, r = [], m.row(rev)
    for f in (f for t in ident["terms"] for f in t["factors"]):
        if not isinstance(f.get("long_run"), (int, float)) or not f.get("long_run_source"):
            out.append(f"revenue_identity factor '{f.get('key')}' needs long_run growth and long_run_source")
    for y in m.forecast_years():
        want, got = grid.get((r, m.col(y))), identity_value(m, grid, ident, y)
        if not isinstance(want, (int, float)) or got is None or abs(got - want) > 0.005 * abs(want):
            out.append(f"revenue_identity gives {got} in {y}, revenue is {want}")
    return out


def check_drivers(m, fm, grid, plan, notes=None):
    """The revenue engine is the key drivers (problems as strings). fm {(row, col number): formula} of MOD."""
    out = []
    rev = _revenue_key(m, plan)
    years = m.forecast_years()
    reach = {}

    def reached(key):
        if key not in reach:
            r = m.row(key)
            reach[key] = set().union(*[_precedent_rows(fm, (r, CI(m.col(y)))) for y in years])
        return reach[key]

    if plan.get("revenue_engine", "drivers") == "growth":
        if not plan.get("growth_reason"):
            out.append("revenue_engine is 'growth' without a growth_reason: say why no driver build is possible")
        elif notes is not None:
            notes.append(f"revenue is a growth-rate engine: {plan['growth_reason']}")
    else:
        if not plan.get("drivers"):
            out.append("the plan names no key drivers: revenue must be built from the filings research's key drivers")
        for d in plan.get("drivers", []):
            fed = d.get("feeds", rev)
            missing = [k for k in d.get("rows", []) if m.row(k) not in reached(fed)]
            if not d.get("rows") or missing:
                out.append(f"key driver '{d.get('name')}' does not feed {fed}: {', '.join(missing) or 'no rows named'}")
        for e in plan.get("rows", []):
            typed_growth = e["method"] == "growth" or (e["method"] == "seasonal" and not e.get("fy_template"))
            if typed_growth and m.row(e["key"]) in reached(rev):
                out.append(f"revenue is driven by a typed growth rate on '{e['key']}': build it from the drivers")
    for ck in plan.get("checks", []):
        r = m.row(ck["key"])
        for y in years:
            v = grid.get((r, m.col(y)))
            if not isinstance(v, (int, float)) or isinstance(v, bool):
                out.append(f"check '{ck['what']}' has no number in {y} (row {r}): {v!r}")
                continue
            lo_, hi_ = ck.get("min"), ck.get("max")
            if (lo_ is not None and v < lo_) or (hi_ is not None and v > hi_):
                msg = f"check '{ck['what']}' {y}: {v:.4g} outside [{lo_}, {hi_}]"
                if ck.get("outside"):
                    if notes is not None:
                        notes.append(f"{msg} (plan says: {ck['outside']})")
                else:
                    out.append(msg)
    return out


# ---- downstream of the forecast ------------------------------------------------------------------------------
_SHEET = r"(?:'((?:[^']|'')+)'|([A-Za-z_][\w.]*))!"
_CELL = r"\$?([A-Z]{1,3})\$?(\d+)"
_SHEET2 = r"(?:'(?:[^']|'')+'|[A-Za-z_][\w.]*)!"
_REF = re.compile(rf"(?<![A-Za-z0-9_.!'])(?:{_SHEET})?{_CELL}(?::(?:{_SHEET2})?\$?([A-Z]{{1,3}})\$?(\d+))?(?![A-Za-z0-9_(])")
_ROWS = re.compile(rf"(?<![A-Za-z0-9_.!'$:])(?:{_SHEET})?\$?(\d+):\$?(\d+)(?![A-Za-z0-9_(:])")
_COLS = re.compile(rf"(?<![A-Za-z0-9_.!'])(?:{_SHEET})?\$?([A-Z]{{1,3}}):\$?([A-Z]{{1,3}})(?![A-Za-z0-9_(:])")
_QREF = re.compile(rf"(?<![A-Za-z0-9_.])(?:{_SHEET}){_CELL}(?::\$?([A-Z]{{1,3}})\$?(\d+))?(?![A-Za-z0-9_(])")
BIG = 10 ** 7


def _refs(tab, f):
    """[(tab, col1, row1, col2, row2)] a formula reads (numbers; whole-column ranges get rows 1..BIG)."""
    f = re.sub(r'"[^"]*"', '""', f.lstrip("="))
    out = []
    for rx, cols in ((_REF, False), (_COLS, True), (_ROWS, None)):
        for mt in rx.finditer(f):
            g = mt.groups()
            sheet = (g[0].replace("''", "'") if g[0] else g[1]) or tab
            if cols is None:
                r1, r2 = int(g[2]), int(g[3])
                out.append((sheet, 1, min(r1, r2), 16384, max(r1, r2)))
            elif cols:
                c1, c2 = CI(g[2]), CI(g[3])
                out.append((sheet, min(c1, c2), 1, max(c1, c2), BIG))
            else:
                c1, r1 = CI(g[2]), int(g[3])
                c2, r2 = (CI(g[4]), int(g[5])) if g[4] else (c1, r1)
                out.append((sheet, min(c1, c2), min(r1, r2), max(c1, c2), max(r1, r2)))
    return out


def allowed_diffs(formulas, mod_cols):
    """formulas {tab: {(row, col): formula}} (AFTER file). Returns the set of (tab, row, col) formula cells that may
    legitimately differ: they read a MOD column in `mod_cols` (column numbers), or read a cell that may differ."""
    canon = {t.lower(): t for t in formulas}
    deps = {}
    for t, cells in formulas.items():
        for pos, f in cells.items():
            if isinstance(f, str) and f:
                deps[(t, *pos)] = [(canon.get(s.lower(), s), *rest) for s, *rest in _refs(t, f)]
    allowed, queue = set(), []
    single, wide, tall = {}, {}, []                      # reverse indexes: cell -> dependents; row bucket; long ranges
    for cell, refs in deps.items():
        hit = False
        for t, c1, r1, c2, r2 in refs:
            if t == "MOD" and any(c1 <= c <= c2 for c in mod_cols):
                hit = True
            if c1 == c2 and r1 == r2:
                single.setdefault((t, r1, c1), []).append(cell)
            elif r2 - r1 > 60:
                tall.append((t, c1, r1, c2, r2, cell))
            else:
                for r in range(r1, r2 + 1):
                    wide.setdefault((t, r), []).append((c1, c2, r1, r2, cell))
        if hit:
            allowed.add(cell)
            queue.append(cell)
    while queue:
        t, r, c = queue.pop()
        found = list(single.get((t, r, c), []))
        found += [d for c1, c2, r1, r2, d in wide.get((t, r), []) if c1 <= c <= c2]
        found += [d for t2, c1, r1, c2, r2, d in tall if t2 == t and c1 <= c <= c2 and r1 <= r <= r2]
        for d in found:
            if d not in allowed:
                allowed.add(d)
                queue.append(d)
    return allowed


# ---- headlines -----------------------------------------------------------------------------------------------
def _find(m, section, label, analysis=None):
    for k, r in m.keys.items():
        sec, lab = k.split(" | ", 1)[0], k.split(" | ", 1)[-1]
        if re.search(section, sec, re.I) and re.search(label, lab, re.I):
            if analysis is None:
                return r
            try:
                return m.analysis(k, analysis)
            except KeyError:
                continue
    return None


def _line(m, section, label):
    """Row of the first MOD line whose section and label start with these (case-insensitive, ' #n' stripped); a section
    named exactly so wins over one that only starts with it (INCOME STATEMENT vs INCOME STATEMENT DRIVERS)."""
    hits = []
    for k, r in m.keys.items():
        sec, lab = k.split(" | ", 1)[0].strip().lower(), re.sub(r" #\d+$", "", k.split(" | ", 1)[-1]).strip().lower()
        if sec.startswith(section.lower()) and lab.startswith(label.lower()):
            hits.append((sec != section.lower(), r))
    return min(hits)[1] if hits else None


def headlines(m, grid):
    def val(r, y):
        v = grid.get((r, m.col(y))) if r else None
        return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None

    def ratio(a, b):
        return lambda y: (val(a, y) / val(b, y)) if val(a, y) is not None and val(b, y) else None

    rev = _line(m, "INCOME STATEMENT", "Revenue")
    ni = _line(m, "INCOME STATEMENT", "Net Income")
    fcf = _line(m, "FREE CASH FLOW", "(+/-) Free Cash Flow") or _line(m, "FREE CASH FLOW", "Free Cash Flow")
    try:
        gr = m.analysis(next(k for k, r in m.keys.items() if r == rev), "% yoy") if rev else None
    except KeyError:
        gr = None
    eps = _find(m, "INCOME", r"diluted.*(eps|per share)|(eps|per share).*diluted|^eps")
    items = [("Revenue", lambda y: val(rev, y), "{:,.1f}"),
             ("Revenue growth", lambda y: val(gr, y), "{:.1%}"),
             ("Non-GAAP gross margin", ratio(_line(m, "NON-GAAP", "Non-GAAP Gross Profit"), rev), "{:.1%}"),
             ("Non-GAAP operating margin", ratio(_line(m, "NON-GAAP", "Non-GAAP Operating Income"), rev), "{:.1%}"),
             ("GAAP EPS, diluted", lambda y: val(eps, y), "{:.2f}"),
             ("Free cash flow", lambda y: val(fcf, y), "{:,.1f}"),
             ("FCF conversion (FCF / GAAP net income)", ratio(fcf, ni), "{:.1%}")]
    years = m.forecast_years()
    lines = ["# Forecast headlines", "", "| | " + " | ".join(years) + " |", "|---|" + "---|" * len(years)]
    for name, fn, fmt in items:
        cells = [fmt.format(fn(y)) if fn(y) is not None else "n/a" for y in years]
        lines.append(f"| {name} | " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


# ---- the whole check -----------------------------------------------------------------------------------------
def to_original(inserts):
    """build's inserts are sequential (each `at` in the rows as they stood); compare wants original rows."""
    done, out = [], []                                   # done: (orig_at, n)
    for at, n in inserts:
        orig, shift = at, 0
        for o, k in sorted(done):
            cur = o + shift
            if at >= cur + k:
                orig -= k
            elif at > cur:
                orig = o
            shift += k
        done.append((orig, n))
        out.append(("MOD", orig, n))
    return out


def _formulas(path):
    wb = openpyxl.load_workbook(path, read_only=True)
    out = {}
    for ws in wb.worksheets:
        g = {}
        for row in ws.iter_rows():
            for c in row:
                v = getattr(c, "value", None)
                v = getattr(v, "text", v)
                if isinstance(v, str) and v.startswith("=") and len(v) > 1:
                    g[(c.row, c.column)] = v
        out[ws.title] = g
    return out


def main(before, after, plan, work, inserts=()):
    """Returns the report dict; report['problems'] must be empty."""
    bad = xlverify.bad_parts(after)
    if bad:
        return {"problems": ["broken XML: " + b for b in bad]}
    rb = lo.recalc(before, os.path.join(work, "check_before"))
    ra = lo.recalc(after, os.path.join(work, "check_after"))
    m = ModMap(after)
    mod_cols = {CI(m.col(p)) for p in m.forecast_quarters() + m.forecast_years()}
    allowed = allowed_diffs(_formulas(after), mod_cols)
    counts = {}
    gb, ga = xlverify._grid(rb), xlverify._grid(ra)
    new_rows, shift = set(), 0
    for _, at, n in sorted(to_original(inserts)):         # rows the build inserted, in AFTER-file numbering
        new_rows.update(range(at + shift, at + shift + n))
        shift += n
    own = {m.row(nr["key"]) for nr in plan.get("new_rows", []) if nr["key"] in m.keys}   # rows the plan owns (any run)
    new_rows |= own
    diffs = xlverify.compare(gb, ga, to_original(inserts),
                             allow=lambda t, r, c: (t == "MOD" and (c in mod_cols or r in new_rows)) or (t, r, c) in allowed,
                             counts=counts)
    grid = {(r, L(c)): v for (r, c), v in ga["MOD"].items()}
    notes = []
    moves = to_original(inserts)
    fm = _formulas(after).get("MOD", {})
    pre = {}
    for (r, c), v in gb.get("MOD", {}).items():
        if c in mod_cols and isinstance(v, str) and v.startswith("#"):
            r2 = r + sum(n for _, at, n in moves if r >= at)
            if ga["MOD"].get((r2, c)) == v:
                pre[(r2, L(c))] = fm.get((r2, c), "")
    problems = check_grid(m, grid, plan, notes, pre)
    problems += check_drivers(m, fm, grid, plan, notes)
    problems += check_identity(m, grid, plan, _revenue_key(m, plan))
    problems += check_shown_work(m, fm, plan, _revenue_key(m, plan))
    if plan.get("driver_sections"):                      # v2 plans (driver sections) must keep the statements pure
        problems += check_statements_are_formulas(m, plan)
    import modfill
    problems += [f"fill convention: {x}" for x in modfill.summary(modfill.check(after))]   # quarters plain, years grey
    import notebox; problems += [f"squashed note box: {x}" for x in notebox.check(after)[:12]]
    problems += [f"unexpected change {t}: {x}" for t, x in diffs[:30]]
    os.makedirs(work, exist_ok=True)
    open(os.path.join(work, "forecast_headlines.md"), "w", encoding="utf-8").write(headlines(m, grid))
    return {"problems": problems, "notes": notes, "downstream_of_the_forecast": counts,
            "values_compared": sum(len(g) for g in gb.values())}


def cli():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--before", required=True)
    ap.add_argument("--after", required=True)
    ap.add_argument("--plan", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--report", help="build.py's JSON report (its rows_inserted are passed to the comparison)")
    a = ap.parse_args()
    ins = []
    if a.report:
        ins = [(x["at"], x["n"]) for x in json.load(open(a.report)).get("rows_inserted", [])]
    rep = main(a.before, a.after, json.load(open(a.plan, encoding="utf-8")), a.work, ins)
    print(json.dumps(rep, indent=1))
    sys.exit(1 if rep["problems"] else 0)


if __name__ == "__main__":
    cli()
