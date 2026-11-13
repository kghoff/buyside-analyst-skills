"""check.py: the tab must equal dcfmath, the MOD years tie to MOD, error cells, stray changes and a reverse-DCF row
that does not hit its price are caught."""
import check


def test_value_per_share_tolerance_is_a_cent():
    assert check.cmp_value(10.004, 10.0) is None
    assert "value per share" in check.cmp_value(10.02, 10.0)


def test_rows_tolerance_is_relative_001_percent():
    assert check.cmp_rows("rev", [100.0, 200.0], [100.005, 200.0]) is None
    assert "rev" in check.cmp_rows("rev", [100.0, 200.0], [100.5, 200.0])
    assert check.cmp_rows("rev", [None], [1.0])


def test_base_vs_mod_half_percent():
    assert check.cmp_mod("oi", [100.0], [100.4]) is None
    assert "MOD" in check.cmp_mod("oi", [100.0], [101.0])


def test_error_cells_found_only_in_tab_grid():
    grid = {(3, 3): 1.0, (4, 4): "#DIV/0!", (5, 5): "#N/A"}
    assert check.error_cells(grid) == ["D4", "E5"]
    assert check.error_cells({(1, 1): "text", (2, 2): 5}) == []


def test_exit_status_follows_problems():
    assert check.report([])["ok"] is True
    r = check.report(["x"])
    assert r["ok"] is False and r["problems"] == ["x"]


# ---- end to end on the synthetic workbook (reuses the build fixture)
import json
import subprocess
import sys

import build
from test_build import _edit_dcf, built  # noqa: F401
from test_context import model  # noqa: F401


def _run(built, after):
    p = {}
    for n in ("ctx", "solved"):
        p[n] = str(built["tmp"] / f"{n}.json")
        json.dump(built[n], open(p[n], "w"))
    return subprocess.run([sys.executable, check.__file__, "--before", built["model"], "--after", after, "--ctx", p["ctx"],
                           "--solved", p["solved"], "--work", str(built["tmp"] / "w")], capture_output=True, text=True)


def test_cli_passes_on_a_correct_build(built):
    r = _run(built, built["out"])
    assert r.returncode == 0, r.stdout + r.stderr
    out = json.loads(r.stdout)
    assert out["ok"] is True and out["reverse_rows_recalculated"] >= 1   # each row typed into the tab and recalculated


def test_cli_fails_when_another_tab_was_changed(built):
    from xlsx import Package
    from xledit import set_cells
    pkg = Package(built["out"])
    part = {s[0]: s[3] for s in pkg.sheets()}["After"]
    pkg.put(part, set_cells(pkg.text(part), {"A1": ("n", 999, 0)}, replace=True)[0])
    bad = str(built["tmp"] / "bad.xlsx")
    pkg.save(bad)
    r = _run(built, bad)
    assert r.returncode == 1 and "After" in r.stdout


def test_cli_fails_when_a_reverse_row_misses_its_price(built):
    row = next(r for r, pk, d in build.layout(built["ctx"])["reverse_rows"]
               if built["solved"]["reverse"][pk][d]["status"] == "ok")
    bad = str(built["tmp"] / "rev.xlsx")
    _edit_dcf(built["out"], bad, {f"E{row}": ("n", 0.3, 0)})
    r = _run(built, bad)
    assert r.returncode == 1 and f"reverse row {row}" in r.stdout


def test_cli_fails_when_an_input_disagrees_with_solved(built):
    R = build.layout(built["ctx"])["rows"]
    bad = str(built["tmp"] / "inp.xlsx")
    _edit_dcf(built["out"], bad, {f"{build.tcol(10)}{R['g0']}": ("n", 0.5, 0)})
    r = _run(built, bad)
    assert r.returncode == 1 and "value per share" in r.stdout


def test_error_cells_exact_set_and_err_prefix():
    g = {(1, 1): "#DIV/0!", (1, 2): "#N/A", (1, 3): "Err:502", (1, 4): "#1 ranked", (1, 5): "#", (1, 6): "#NAME?"}
    assert check.error_cells(g) == ["A1", "B1", "C1", "F1"]


def test_cli_fails_when_the_users_formula_moved_from_what_solve_used(built):
    """The snapshot (reverse DCF, value) was solved on the formula's old value; if it recalculates differently, say so."""
    from test_build import _build
    R = build.layout(built["ctx"])["rows"]
    c40, c39 = f"{build.tcol(14)}{R['g0']}", f"{build.tcol(13)}{R['g0']}"
    edited = str(built["tmp"] / "f.xlsx")
    _edit_dcf(built["out"], edited, {c40: ("f", f"{c39}/2", 0)})
    out2 = str(built["tmp"] / "f2.xlsx")
    ctx, solved = _build(edited, out2, built["out"] + ".json")
    good = dict(built, model=edited, out=out2, ctx=ctx, solved=solved)
    r = _run(good, out2)
    assert r.returncode == 0, r.stdout + r.stderr
    solved["inputs"]["Units"]["2040E"] += 0.01
    r = _run(dict(good, solved=solved), out2)
    assert r.returncode == 1 and f"your formula in {c40} now gives" in r.stdout
