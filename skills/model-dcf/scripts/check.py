"""Proves the DCF tab is right: nothing outside it changed, and the recalculated tab equals dcfmath.

usage: python3 check.py --before M.xlsx --after OUT.xlsx --ctx context.json --solved solved.json --work DIR
Checks (one LibreOffice recalculation of each file): XML parts valid; every other tab unchanged; the tab's value per
share (to $0.01) and revenue / operating-income rows (to 0.01%) equal dcfmath for the inputs in solved.json; revenue
and operating income for the MOD years equal MOD to 0.5%; no error cells; each reverse-DCF row, typed into a copy
of the tab (its shift added to the driver's yellow cells) and recalculated, gives its price to $0.02; every formula
the user typed in an input cell recalculates to the value solve.py used (1e-9). Prints a JSON report; exit 1 on any problem."""
import argparse
import json
import os
import sys

from openpyxl.utils import get_column_letter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build  # noqa: E402
import dcfmath  # noqa: E402
import lo  # noqa: E402
import solve  # noqa: E402
import xlverify  # noqa: E402
from xledit import set_cells  # noqa: E402
from xlsx import Package  # noqa: E402

ERRORS = {"#DIV/0!", "#VALUE!", "#REF!", "#NAME?", "#N/A", "#NUM!", "#NULL!"}


def cmp_value(a, b):
    if not isinstance(a, (int, float)) or abs(a - b) >= 0.01:
        return f"value per share {a!r} vs dcfmath {b:.4f}"


def cmp_rows(name, tab, ref, rel=1e-4):
    for t, (a, b) in enumerate(zip(tab, ref), start=1):
        if not isinstance(a, (int, float)) or abs(a - b) > rel * abs(b) + 1e-6:
            return f"{name} year {t}: tab {a!r} vs dcfmath {b:.4f}"
    if len(tab) != len(ref):
        return f"{name}: {len(tab)} years in tab vs {len(ref)}"


def cmp_mod(name, tab, mod):
    for t, (a, b) in enumerate(zip(tab, mod), start=1):
        if not isinstance(a, (int, float)) or abs(a - b) > 0.005 * abs(b):
            return f"{name} year {t}: tab {a!r} vs MOD {b:.4f}"


def error_cells(grid):
    return [f"{get_column_letter(c)}{r}" for (r, c), v in sorted(grid.items())
            if isinstance(v, str) and (v in ERRORS or v.startswith("Err:"))]


def reverse_in_tab(after, solved, ctx, work):
    """Each reverse-DCF row, as the user would reproduce it: add its shift (column E) to the driver's yellow cells in the
    shift years on a copy of the built tab, recalculate, and require value per share = its price (column C) to $0.02."""
    L = build.layout(ctx)
    R, rows = L["rows"], L["reverse_rows"]
    pkg0 = Package(after)
    part = {s[0]: s[3] for s in pkg0.sheets()}[build.TAB]
    snap = xlverify._grid(after)[build.TAB]
    cols = {dcfmath.label(ctx, t): build.tcol(t) for t in range(0, 31)}
    out, n = [], 0
    for row, pk, d in rows:
        price, x = snap.get((row, 3)), snap.get((row, 5))
        if x == "out of range":
            continue
        if not isinstance(price, (int, float)) or not isinstance(x, (int, float)):
            out.append(f"reverse row {row}: price {price!r}, shift {x!r}")
            continue
        sh = solve.shift(solved["inputs"], ctx, d, x)
        cells = {f"{cols[y]}{build.driver_row(ctx, R, d)}": ("n", sh[d][y], 0) for y in solved["shift_years"]}
        p = os.path.join(work, f"reverse{row}.xlsx")
        pkg = Package(after)
        pkg.put(part, set_cells(pkg.text(part), cells, replace=True)[0])
        pkg.save(p)
        v = xlverify._grid(lo.recalc(p, os.path.join(work, f"rr{row}")))[build.TAB].get((R["vps"], 3))
        n += 1
        if not isinstance(v, (int, float)) or abs(v - price) > 0.02:
            out.append(f"reverse row {row} ({pk}, {d}): typing the shift into the tab gives {v!r}, price ${price:.2f}")
    return out, n


def input_row(ctx, R, name):
    """Row of an input's yellow cells: a factor's growth row, dgm or a cost row."""
    return R[name] if name in R else build.driver_row(ctx, R, name)


def formula_drift(solved, g, ctx):
    """The user's formula cells must recalculate to the value solve.py used (the snapshot was solved on it)."""
    R = build.layout(ctx)["rows"]
    out = []
    for name, by_year in solved.get("formulas", {}).items():
        for y in by_year:
            if y == "value":
                r, c, used = R["wacc" if name == "wacc" else "mult"], 3, solved["inputs"][name]
            else:
                r, c, used = input_row(ctx, R, name), 8 + [dcfmath.label(ctx, t) for t in range(0, 31)].index(y), solved["inputs"][name][y]
            v = g.get((r, c))
            if not isinstance(v, (int, float)) or abs(v - used) > 1e-9:
                out.append(f"your formula in {get_column_letter(c)}{r} now gives {v!r}, the reverse DCF used {used!r}; "
                           "rerun /model-dcf")
    return out


def _with_formula_values(solved, g, ctx):
    """The user's formula cells: the math uses what they recalculate to in the built tab."""
    inputs = {k: (dict(v) if isinstance(v, dict) else v) for k, v in solved["inputs"].items()}
    L = build.layout(ctx)
    R = L["rows"]
    cols = {dcfmath.label(ctx, t): 8 + t for t in range(0, 31)}
    for name, by_year in solved.get("formulas", {}).items():
        for y in by_year:
            if y == "value":
                inputs[name] = g.get((R["wacc" if name == "wacc" else "mult"], 3))
            else:
                inputs[name][y] = g.get((input_row(ctx, R, name), cols[y]))
    return inputs


def report(problems, **extra):
    return {"ok": not problems, "problems": problems, **extra}


def main():
    ap = argparse.ArgumentParser()
    for n in ("before", "after", "ctx", "solved", "work"):
        ap.add_argument("--" + n, required=True)
    a = ap.parse_args()
    ctx0, solved = json.load(open(a.ctx)), json.load(open(a.solved))
    problems, L = [], build.layout(ctx0)
    R = L["rows"]
    problems += [f"broken XML: {b}" for b in xlverify.bad_parts(a.after)]

    before = xlverify._grid(lo.recalc(a.before, os.path.join(a.work, "before")))
    after = xlverify._grid(lo.recalc(a.after, os.path.join(a.work, "after")))
    before.pop(build.TAB, None)  # a rerun replaces the old tab
    problems += [f"{t}: {d}" for t, d in xlverify.compare(before, after, new_tabs={build.TAB})]

    g = after[build.TAB]
    problems += formula_drift(solved, g, ctx0)
    inputs = _with_formula_values(solved, g, ctx0)
    ctx = dcfmath.prepare(ctx0, inputs)
    scn = dcfmath.to_scn(inputs, ctx)
    o = dcfmath.run(scn, ctx)
    vps = g.get((R["vps"], 3))
    rev = [g.get((R["rev"], 9 + t)) for t in range(30)]
    oi = [g.get((R["oi"], 9 + t)) for t in range(30)]
    problems += [m for m in (cmp_value(vps, o["value_per_share"]), cmp_rows("revenue", rev, o["rev"]),
                             cmp_rows("operating income", oi, o["oi"])) if m]
    k = ctx["k"]
    mod_oi = [gp - ox for gp, ox in zip(ctx["mod"]["gp"], ctx["mod"]["opex"])]
    problems += [m for m in (cmp_mod("revenue", rev[:k], ctx["mod"]["rev"][:k]),
                             cmp_mod("operating income", oi[:k], mod_oi[:k])) if m]
    errs = error_cells(g)
    if errs:
        problems.append(f"error cells in DCF tab: {errs[:10]}")
    rp, n = reverse_in_tab(a.after, dict(solved, inputs=inputs), ctx0, a.work)
    problems += rp
    print(json.dumps(report(problems, tab_value_per_share=vps, dcfmath_value_per_share=o["value_per_share"],
                            tv_share=o["tv_share"], reverse_rows_recalculated=n), indent=1))
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
