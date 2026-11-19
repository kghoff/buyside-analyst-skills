"""Final checks on the finished copy before it replaces the user's model (spec 'verify.py'). Read only: it never
writes either workbook (the recalculations go to --work).

usage: python3 verify.py --before MODEL --after FINAL.xlsx --state state.json --work DIR
                         [--mid ACTUALS.xlsx] [--before-values grid.json] [--restated refs.json] [--charts]
--mid: the actuals copy before the forecast roll (actuals.py's --out). Checks 3 and 5 then run on --before -> --mid,
  where state.json's refs are still right, and the roll (--mid -> --after) may change only forecast (E) columns, with
  every MOD line on the same row (check 7). Without --mid (no roll: the 10-Q rerun) they run on --before -> --after.
--before-values: the original's recalculated values, all tabs (grid.py --recalc); without it the original is
  recalculated into --work. --restated: the prior-period cells the user approved restating. --charts: a Q4 print
  rebuilt Filings Charts (handoff.py --charts-only), so its sheet, drawing and chart parts may change.
Checks:
1. no NEW error cells after a recalculation: per tab, no more than the recalculated original has;
2. every zip part byte-identical except MOD's sheet part, its .rels and the parts it points at (notes, VML),
   xl/styles.xml, [Content_Types].xml, xl/workbook.xml (+ its .rels and calcChain, which Package.finish drops),
   and with --charts Filings Charts' parts;
3. MOD cells outside the reported column, the Q4 year column (state fy_column), the forecast (E) columns and the
   restated refs are unchanged (formula text or value);
4. the reported column balances: total assets = total liabilities and equity (rows found by label), within 0.01;
5. every typed release value and every forecast placeholder has a note starting 'Update: ' (or, on a cell that had
   the user's own note, 'Update: ' appended after it); every placeholder is
   orange; every cell carrying a placeholder note is listed in state.json's placeholders;
6. every formula on another tab that refers to MOD!<col><row> points at a row with the same column-B label and a
   column with the same period header (E dropped) as before;
7. (with --mid) no MOD line moved in the roll: model-forecast's layout.py / build.py / move_rows.py can move rows when
   a plan adds rows or changes its layout, and then every ref in state.json (awaiting cells, placeholders, typed
   subtotals and their saved formulas) would point at the wrong row on the 10-Q rerun. A targeted roll changes
   assumptions only; structure changes belong to /model-forecast.
Exit 1 with the problems listed (JSON); nothing is copied then."""
import argparse
import json
import os
import re
import sys

import openpyxl

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import grid                                         # noqa: E402
from modmap import ModMap                           # noqa: E402
from mnotes import NOTE                             # noqa: E402
from xlsx import Package, relpath_of, resolve       # noqa: E402

TAB = "MOD"
ORANGE = "FFC65911"
PLACEHOLDER = NOTE + "forecast placeholder"
MODREF = re.compile(r"(?<![A-Za-z0-9_.'])'?MOD'?!\$?([A-Z]{1,3})\$?(\d+)")
_CACHE = {}


def _ours(text, what=NOTE):
    """The skill's note: the whole note, or appended after the user's own note (mnotes keeps the user's words)."""
    return text.startswith(what) or ("\n\n" + what) in text


def _book(path):
    """{sheet: {ref: value or '=formula'}}, MOD's {ref: note text} and {ref: font rgb}; loaded once per file."""
    key = (os.path.abspath(path), os.path.getmtime(path))
    if key not in _CACHE:
        wb = openpyxl.load_workbook(path)
        cells = {ws.title: {c.coordinate: c.value for row in ws.iter_rows() for c in row if c.value is not None}
                 for ws in wb.worksheets}
        notes, color = {}, {}
        for row in wb[TAB].iter_rows():
            for c in row:
                if c.comment is not None:
                    notes[c.coordinate] = c.comment.text or ""
                rgb = c.font.color.rgb if c.font is not None and c.font.color is not None else None
                if isinstance(rgb, str):
                    color[c.coordinate] = rgb
        _CACHE.clear()                              # keep at most the last pair of workbooks in memory
        _CACHE[key] = (cells, notes, color)
    return _CACHE[key]


def _col(ref):
    return re.match(r"[A-Z]+", ref).group(0)


def allowed_cols(model, state):
    """Columns print night may rewrite: the reported quarter, the year column on a Q4, every forecast (E) column."""
    m = ModMap(model)
    cols = {state["column"]} | {m.col(p) for p in m.order if p.endswith("E")}
    return cols | ({state["fy_column"]} if state.get("fy_column") else set())


def _sheet_parts(pkg, name):
    part = next((p for n, _, _, p in pkg.sheets() if n == name), None)
    if not part:
        return set()
    out = {part, relpath_of(part)}
    for _, (t, g) in pkg.rels(relpath_of(part)).items():
        if not g.startswith(("http:", "https:", "file:")):
            out.add(resolve(part, g))
    return out


def parts(before, after, charts=False):
    a, b = Package(before), Package(after)
    allow = {"xl/styles.xml", "[Content_Types].xml", "xl/workbook.xml", "xl/_rels/workbook.xml.rels",
             "xl/calcChain.xml"} | _sheet_parts(a, TAB) | _sheet_parts(b, TAB)
    if charts:
        allow |= _sheet_parts(a, "Filings Charts") | _sheet_parts(b, "Filings Charts")
        allow |= {p for p in set(a.parts) | set(b.parts) if p.startswith(("xl/charts/", "xl/drawings/"))}
    return [f"part changed: {p}" for p in sorted(set(a.parts) | set(b.parts))
            if p not in allow and a.parts.get(p) != b.parts.get(p)]


def static(before, after, state, allow_cols, restated=()):
    fa = _book(before)[0][TAB]
    fb, notes, color = _book(after)
    fb = fb[TAB]
    probs = []
    for ref in sorted(set(fa) | set(fb), key=lambda r: (int(re.sub(r"[A-Z]+", "", r)), len(_col(r)), _col(r))):
        if _col(ref) in allow_cols or ref in restated:
            continue
        if fa.get(ref) != fb.get(ref):
            probs.append(f"MOD!{ref} changed: {fa.get(ref)!r} -> {fb.get(ref)!r}")
    listed = {p["ref"] for p in state.get("placeholders", [])}
    for ref in list(state.get("release_values", {})) + sorted(listed):
        if not _ours(notes.get(ref, "")):
            probs.append(f"MOD!{ref} has no 'Update: ' note")
    for ref in sorted(listed):
        if color.get(ref) != ORANGE:
            probs.append(f"MOD!{ref} placeholder is not orange")
    written = {state["column"], state.get("fy_column")} - {None}
    for ref, text in sorted(notes.items()):
        if _col(ref) in written and _ours(text, PLACEHOLDER) and ref not in listed:
            probs.append(f"MOD!{ref} has a placeholder note but is not listed in state.json")
    return probs


def forecast_cols(model):
    m = ModMap(model)
    return {m.col(p) for p in m.order if p.endswith("E")}


def moved(mid, after):
    """MOD lines whose row differs between the actuals copy and the rolled copy (or that are gone): [(key, was, now)]."""
    a, b = ModMap(mid), ModMap(after)
    return [(k, r, b.keys.get(k)) for k, r in sorted(a.keys.items(), key=lambda x: x[1]) if b.keys.get(k) != r]


def roll(mid, after, state):
    """Check 7, then the roll may change only forecast columns (notes and placeholders re-checked on the rolled copy)."""
    mv = moved(mid, after)
    if mv:
        shown = "; ".join(f"{k}: row {r} -> {'gone' if n is None else f'row {n}'}" for k, r, n in mv[:10])
        return [f"the forecast roll moved {len(mv)} MOD line(s) ({shown}): model-update keeps rows in place so "
                "state.json stays right for the 10-Q rerun; drop the structural change (new rows, move_rows, layout, "
                "a new seasonal method) from the roll and make it with /model-forecast after this update"]
    return static(mid, after, state, forecast_cols(mid))


def links(before, after):
    fa, fb = _book(before)[0], _book(after)[0]
    la, lb = fa[TAB], fb[TAB]
    label = lambda g, r: g.get(f"B{r}")
    period = lambda g, c: str(g.get(f"{c}2", "")).strip().rstrip("E")
    probs = []
    for s in fa:
        if s == TAB or s not in fb:
            continue
        for ref, f in fa[s].items():
            g = fb[s].get(ref)
            if not (isinstance(f, str) and f.startswith("=") and isinstance(g, str)):
                continue
            for (c1, r1), (c2, r2) in zip(MODREF.findall(f), MODREF.findall(g)):
                if label(la, r1) != label(lb, r2):
                    probs.append(f"{s}!{ref} -> MOD!{c2}{r2}: was {label(la, r1)!r}, now {label(lb, r2)!r}")
                elif period(la, c1) != period(lb, c2):
                    probs.append(f"{s}!{ref} -> MOD!{c2}{r2}: was period {period(la, c1)!r}, now {period(lb, c2)!r}")
    return probs


def balance(after_values, model, col):
    m = ModMap(model)
    # 'TOTAL ASSETS:', "Total liabilities and stockholders' equity", 'TOTAL LIABILITIES & EQUITY:'
    name = lambda k: re.sub(r"\s*#\d+$", "", k.split(" | ")[-1]).strip().rstrip(":").strip().lower()
    ta = next((r for r, k, _ in m.lines if name(k) == "total assets"), None)
    tle = next((r for r, k, _ in m.lines if re.fullmatch(r"total liabilities,? (and|&) .*equity", name(k))), None)
    if not (ta and tle):
        return ["balance sheet check: no 'Total assets' and 'Total liabilities and equity' rows found in MOD column B"]
    a, b = after_values.get(f"{col}{ta}"), after_values.get(f"{col}{tle}")
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and abs(a - b) > 0.01:
        return [f"balance sheet does not balance in {col}: total assets {a} vs liabilities and equity {b}"]
    return []


def new_errors(before_grid, after_grid):
    """Per tab: more error cells than the recalculated original had (the original may carry a few)."""
    probs = []
    for s, g in after_grid.items():
        now = grid.errors({s: g})
        was = grid.errors({s: before_grid.get(s, {})})
        if len(now) > len(was):
            fresh = sorted(set(now) - set(was))
            probs.append(f"{s}: {len(now)} error cells, was {len(was)} ({', '.join(fresh[:10])})")
    return probs


def check(before, after, state, after_grid, before_grid, restated=(), charts=False, mid=None):
    probs = new_errors(before_grid, after_grid)
    probs += parts(before, after, charts)
    probs += static(before, mid or after, state, allowed_cols(before, state), set(restated))
    if mid:
        probs += roll(mid, after, state)
    probs += balance(after_grid.get(TAB, {}), after, state["column"])
    probs += links(before, after)
    return probs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--before", required=True), ap.add_argument("--after", required=True)
    ap.add_argument("--state", required=True), ap.add_argument("--work", required=True)
    ap.add_argument("--before-values"), ap.add_argument("--restated"), ap.add_argument("--charts", action="store_true")
    ap.add_argument("--mid")
    a = ap.parse_args()
    st = json.load(open(a.state))
    restated = set(json.load(open(a.restated))) if a.restated else set()
    ga = json.load(open(a.before_values)) if a.before_values else grid.dump(a.before, os.path.join(a.work, "verify_before"))
    gb = grid.dump(a.after, os.path.join(a.work, "verify_after"))
    probs = check(a.before, a.after, st, gb, ga, restated, a.charts, a.mid)
    print(json.dumps(probs, indent=1))
    sys.exit(1 if probs else 0)


if __name__ == "__main__":
    main()
