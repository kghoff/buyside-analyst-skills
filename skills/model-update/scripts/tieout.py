"""Every release line equals its MOD cell after a recalculation (spec 'tieout').

usage: python3 tieout.py --match match.json --values values_after.json --column L [--fy-column N] [--state state.json]
(exit 1 on any miss). --fy-column: on a Q4 print, lines with fy_cur are also tied to the full-year column.
--state: actuals.py's state.json; its awaiting cells and forecast placeholders are skipped (a placeholder holds a
forecast on purpose, never the release's number). --awaiting (JSON list of refs or {ref: ...}) does the same."""
import argparse
import json
import sys


def _miss(e, ref, want, grid):
    v = grid.get(ref)
    if isinstance(v, (int, float)) and abs(v - want) <= e["tol"]:
        return None
    return {"ref": ref, "label": e["label"], "release": want, "model": v, "file": e["file"], "lineno": e["lineno"]}


def skip_refs(state):
    """The cells tieout leaves alone: every waiting cell and every forecast placeholder in state.json."""
    return {a["ref"] for a in state.get("awaiting", [])} | {p["ref"] for p in state.get("placeholders", [])}


def check(res, grid, col, fy_col=None, waiting=()):
    miss = []
    for e in res["matched"]:
        pairs = [(f"{col}{e['row']}", e.get("cur"))]
        if fy_col:
            pairs.append((f"{fy_col}{e['row']}", e.get("fy_cur")))
        for ref, want in pairs:
            if want is None or ref in waiting:
                continue
            m = _miss(e, ref, want, grid)
            if m:
                miss.append(m)
    return miss


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--match", required=True), ap.add_argument("--values", required=True), ap.add_argument("--column", required=True)
    ap.add_argument("--fy-column"), ap.add_argument("--awaiting"), ap.add_argument("--state")
    a = ap.parse_args()
    wait = set()
    if a.awaiting:
        wait = {x["ref"] if isinstance(x, dict) else x for x in json.load(open(a.awaiting))}
    if a.state:
        wait |= skip_refs(json.load(open(a.state)))
    miss = check(json.load(open(a.match)), json.load(open(a.values))["MOD"], a.column, a.fy_column, wait)
    print(json.dumps(miss, indent=1))
    sys.exit(1 if miss else 0)
