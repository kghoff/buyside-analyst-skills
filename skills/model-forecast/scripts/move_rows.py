"""Move existing MOD rows into another section (e.g. the Revenue Build), as Excel's cut + insert-cut-cells does: the rows
keep their values, formulas, notes and styles, and every reference anywhere follows them.

usage: python3 move_rows.py --model M.xlsx --plan forecast_plan.json --out OUT.xlsx --work DIR
plan["move_rows"]: [{"from": "<SECTION> | <first label>", "through": "<SECTION> | <last label>", "to": "<SECTION>",
                     "before": "<SECTION> | <label>" (optional; default: the end of the `to` section), "why": "..."}]
Keys are the rows' keys BEFORE the move (from the rowmap); afterwards a moved row's key starts with the `to` section.
Proof (exit 1 on any problem, nothing written): LibreOffice recalculates the model before and after, and every cell on
every tab must hold the same value at its new position. A range a move would split is refused. Rule:
every number feeding revenue sits in the Revenue Build, shown and labelled."""
import argparse
import json
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lo           # noqa: E402
import safe_save    # noqa: E402
import xlverify     # noqa: E402
from build import _add_section, _colab  # noqa: E402
from modmap import ModMap  # noqa: E402
from xlsx import Package   # noqa: E402

TAB = "MOD"


def section_end(m, section):
    """First row after `section` (the next section title's row, or one past the last line)."""
    rows = sorted(r for k, r in m.keys.items() if k.split(" | ", 1)[0] == section)
    if not rows:
        raise SystemExit(f"move_rows: no section '{section}' in MOD")
    later = sorted(r for k, r in m.keys.items() if r > rows[-1] and k.split(" | ", 1)[0] != section)
    return later[0] - 1 if later else rows[-1] + 1        # the blank row before the next title stays below


def _planned_section(out, plan, section):
    """Create `section` (empty) if the model lacks it and plan['driver_sections'] will add it (move_rows runs before
    build.py, which then finds it there). Returns (row map for the 2 inserted rows, first row of the new section),
    or None when nothing was created."""
    colab = _colab(out)
    if any(a and str(a).strip() == section for _, a, _ in colab):
        return None
    prev = "REVENUE BUILD"                                 # build.py's default `after` chain
    for ds in plan.get("driver_sections", []):
        if ds["title"] == section:
            pkg = Package(out)
            title = _add_section(pkg, colab, section, ds.get("after", prev), "REVENUE BUILD")
            pkg.finish()
            pkg.save(out)
            return (lambda r: r + 2 if r >= title - 1 else r), title + 1
        prev = ds["title"]
    return None


def move(model, plan, out):
    """Apply plan['move_rows'] to a copy; returns (out, composed row map old -> new)."""
    shutil.copyfile(model, out)
    fns = []
    for mv in plan.get("move_rows", []):
        made = _planned_section(out, plan, mv["to"])
        if made:
            fns.append(made[0])
        m = ModMap(out)
        done = [f"{mv['to']} | {mv[k].split(' | ', 1)[1]}" for k in ("from", "through")]
        if mv["from"] not in m.keys and all(k in m.keys for k in done):
            continue                                       # a rerun: an earlier run already moved these rows
        a, b = m.row(mv["from"]), m.row(mv["through"])
        r = b + 1
        while r in m.analysis_rows:                        # the last line's analysis rows travel with it
            r += 1
        b = r - 1
        before = m.row(mv["before"]) if mv.get("before") else made[1] if made else section_end(m, mv["to"])
        fn = safe_save.move_fn(a, b, before)
        pkg = Package(out)
        try:
            safe_save.remap_rows(pkg, TAB, fn, strict=True)
        except safe_save.RefIntoDeleted as e:
            raise SystemExit(f"move_rows: can't move {mv['from']} .. {mv['through']}: {e}")
        pkg.finish()                                   # drop calcChain: it names the old cells (Excel repairs it)
        pkg.save(out)
        fns.append(fn)

    def total(r):
        for f in fns:
            r = f(r)
        return r
    return out, total


def check(before, after, fn, work):
    """Every cell keeps its value at its new place (after a LibreOffice recalculation of both)."""
    gb = xlverify._grid(lo.recalc(before, os.path.join(work, "mv_before")))
    ga = xlverify._grid(lo.recalc(after, os.path.join(work, "mv_after")))
    bad = []
    for tab, cells in gb.items():
        for (r, c), v in cells.items():
            r2 = fn(r) if tab == TAB else r
            w = ga.get(tab, {}).get((r2, c))
            if v != w and not (isinstance(v, float) and isinstance(w, float) and abs(v - w) <= 1e-9 * max(1, abs(v))):
                bad.append(f"{tab} row {r} col {c}: {v!r} became {w!r} (row {r2})")
    return bad


def main():
    ap = argparse.ArgumentParser()
    for n in ("model", "plan", "out", "work"):
        ap.add_argument("--" + n, required=True)
    a = ap.parse_args()
    plan = json.load(open(a.plan))
    if not plan.get("move_rows"):
        shutil.copyfile(a.model, a.out)
        print(json.dumps({"moved": 0, "problems": []}))
        return
    out, fn = move(a.model, plan, a.out)
    bad = check(a.model, out, fn, a.work)
    print(json.dumps({"moved": len(plan["move_rows"]), "problems": bad[:30], "n_problems": len(bad)}, indent=1))
    if bad:
        os.remove(out)
        sys.exit(1)


if __name__ == "__main__":
    main()
