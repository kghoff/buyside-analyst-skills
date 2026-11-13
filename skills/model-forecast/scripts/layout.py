"""Lay out the forecast's driver sections the way the user lays out their own: named groups, each with its inputs indented
under the group name, the working rows in italics, the group's result in bold, and a blank row between groups.

usage: python3 layout.py --model M.xlsx --plan forecast_plan.json --out OUT.xlsx --work DIR   (prints a JSON report)
plan["layout"]: [{"section": "<MOD section title>",
                  "groups": [{"title": "<group name>", "rows": ["<SECTION> | <label>", ...],
                              "result": "<one of rows>" or null, "reference": false}]}]
Every line of a listed section must sit in exactly one group (its analysis rows travel with it). Formatting is a rule
on the sheet, not the agent's choice: group name plain, no indent; a row with a typed forecast number (an input)
indent 1; an all-formula row (a working step) italic, indent 2; the result (the group's last row) bold, no indent;
a reference group (guides, cross-checks, history only) italic, indent 1. Rows move like Excel's cut + insert, so every
reference follows them; group-name and blank rows from an earlier layout are rebuilt. Proof (exit 1, nothing
written): LibreOffice recalculates before and after and every cell keeps its value at its new place.
Each group also carries `note`: a short plain-English explanation (what the line is, how it feeds the statements,
what up / down means for the business, ...) written as a cell note on the group's bold result row, or on the group
name when the group has no result. The box is sized to its text and starts right of the cell's spacer / hidden
columns (notebox). A long flat list of line items is not intuitive to read."""
import argparse
import json
import os
import re
import shutil
import sys

import openpyxl
from openpyxl.utils import column_index_from_string as colnum_

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import safe_save    # noqa: E402
from modmap import ModMap  # noqa: E402
import lo           # noqa: E402
import xlverify     # noqa: E402
from xledit import set_cells  # noqa: E402
from xlsx import Package, Styles  # noqa: E402

TAB = "MOD"
GUIDE_NOTE = "Guide: "              # prefix of the layout's own notes: the only notes a rerun may rewrite
CELL_S = re.compile(r'<c r="([A-Z]+)(\d+)"([^>]*?)(/?>)')


def _section_rows(ws_rows, title):
    """(title row, last labelled row) of the section whose column-A title is `title`."""
    t = next((i for i, (a, _, _) in enumerate(ws_rows, start=1) if a and str(a).strip() == title), None)
    if t is None:
        raise ValueError(f"layout: no MOD section '{title}'")
    last = t
    for i in range(t + 1, len(ws_rows) + 1):
        a, b, _ = ws_rows[i - 1]
        if a:
            break
        if b:
            last = i
    return t, last


def plan_order(path, plan):
    """{section: (first, last, [new row contents])} where contents are ('line', old row), ('head', title) or
    ('blank', None); plus problems."""
    m = ModMap(path)
    ws = openpyxl.load_workbook(path, read_only=True)[TAB]
    rows = list(ws.iter_rows(min_row=1, max_col=3, values_only=True))
    full = {i: r for i, r in enumerate(ws.iter_rows(min_row=1, values_only=True), start=1)}
    out, bad = {}, []
    for sec in plan.get("layout", []):
        t, last = _section_rows(rows, sec["section"])
        titles = {g["title"] for g in sec["groups"]}
        lines = [(r, k) for k, r in m.keys.items() if t < r <= last]
        empty = lambda r: not any(v not in (None, "") for v in full[r][3:])
        heads = {r for r, k in lines if k.split(" | ", 1)[1] in titles and empty(r)}
        unit = {}
        for r, k in lines:
            if r in heads:
                continue
            e = r + 1
            while e in m.analysis_rows:
                e += 1
            unit[k] = list(range(r, e))
        listed = [k for g in sec["groups"] for k in g["rows"]]
        bad += [f"{sec['section']}: '{k}' is in no group" for k in unit if k not in listed]
        bad += [f"{sec['section']}: '{k}' is not a row of this section" for k in listed if k not in unit]
        bad += [f"{sec['section']}: '{k}' is in two groups" for k in set(listed) if listed.count(k) > 1]
        bad += [f"{sec['section']}: group '{g['title']}' result '{g['result']}' is not its last row "
                "(list the rows in the order the math flows; the result is the last one computed)"
                for g in sec["groups"] if g.get("result") and g["rows"][-1:] != [g["result"]]]
        bad += [f"{sec['section']}: group '{g['title']}' has no note" for g in sec["groups"]
                if not g.get("reference") and not str(g.get("note") or "").strip()]
        if bad:
            continue
        seq = []
        for n, g in enumerate(sec["groups"]):
            if n:
                seq.append(("blank", None))
            seq.append(("head", g["title"]))
            for k in g["rows"]:
                seq += [("line", r) for r in unit[k]]
        out[sec["section"]] = (t + 1, last, seq)
    return out, bad


def build_fn(order):
    """old row -> new row (None for dropped group-name / blank rows), applying every section's new order."""
    moves, shifts = {}, []
    delta = 0
    for first, last, seq in sorted(order.values()):
        for k, (kind, v) in enumerate(seq):
            if kind == "line":
                moves[v] = first + delta + k
        for r in range(first, last + 1):
            moves.setdefault(r, None)
        shifts.append((last, len(seq) - (last - first + 1)))
        delta += shifts[-1][1]

    def fn(r):
        if r in moves:
            return moves[r]
        return r + sum(d for last, d in shifts if r > last)
    return fn


def check(before, after, fn, work):
    """Every cell keeps its value at its new place (after a LibreOffice recalculation of both); the old group-name and
    blank rows (fn -> None) are rebuilt, so they are not compared."""
    gb = xlverify._grid(lo.recalc(before, os.path.join(work, "lay_before")))
    ga = xlverify._grid(lo.recalc(after, os.path.join(work, "lay_after")))
    bad = []
    for tab, cells in gb.items():
        for (r, c), v in cells.items():
            r2 = fn(r) if tab == TAB else r
            if r2 is None:
                continue
            w = ga.get(tab, {}).get((r2, c))
            if v != w and not (isinstance(v, float) and isinstance(w, float) and abs(v - w) <= 1e-9 * max(1, abs(v))):
                bad.append(f"{tab} row {r} col {c}: {v!r} became {w!r} (row {r2})")
    return bad


def _size_notes(path, notes):
    """Give each group note (0-based row on column B -> text) a box that fits its text: BOX_PX wide, starting in the
    first visible normal-width column right of B (never on a spacer or hidden quarter), as many rows tall as the
    text needs."""
    import notebox
    pkg = Package(path)
    part = next(p for name, _, _, p in pkg.sheets() if name == TAB)
    cols, default = notebox._cols(pkg.text(part))
    for vp in [p for p in pkg.parts if p.endswith(".vml")]:
        v = pkg.text(vp)
        if not any(f"<x:Row>{r}</x:Row>" in v for r in notes):
            continue
        for s in notebox.SHAPE.findall(v):
            rm, cm = re.search(r"<x:Row>\s*(\d+)", s), re.search(r"<x:Column>\s*(\d+)", s)
            if not (rm and cm) or int(cm.group(1)) != 1 or int(rm.group(1)) not in notes:
                continue
            r = int(rm.group(1))
            lines = sum(max(1, -(-len(x) // 48)) for x in notes[r].split("\n"))
            a = notebox._anchor(1, [0, 0, r, 2, 0, 0, r, 0], cols, default)
            a[6], a[7] = r + max(4, -(-lines * 14 // 20) + 1), 4         # ~14 px a line, ~20 px a row
            new = notebox.ANCHOR.sub(lambda m: m.group(1) + ", ".join(map(str, a)) + m.group(3), s, count=1)
            new = re.sub(r"(?<![-\w])height:[\d.]+pt", f"height:{(a[6] - r) * 15}pt", new, count=1)
            v = v.replace(s, new, 1)
        pkg.put(vp, v)
    pkg.save(path)


def layout(model, plan, out):
    order, bad = plan_order(model, plan)
    if bad:
        raise ValueError("layout: " + "; ".join(bad))
    fn = build_fn(order)
    shutil.copyfile(model, out)
    pkg = Package(out)
    safe_save.remap_rows(pkg, TAB, fn, strict=True)
    pkg.finish()                                       # drop calcChain: it names the old cells (Excel repairs it)
    pkg.save(out)

    # styles, on the moved file
    m = ModMap(out)
    wb = openpyxl.load_workbook(out, read_only=True)
    ws = wb[TAB]
    fc = {colnum_(m.col(p)) for p in m.order if p.endswith("E") and p != "2050E"}
    pc = {colnum_(m.col(p)) for p in m.order}
    vals = {i: r for i, r in enumerate(ws.iter_rows(min_row=1, values_only=True), start=1)}
    pkg = Package(out)
    part = next(p for name, _, _, p in pkg.sheets() if name == TAB)
    xml = pkg.text(part)
    st = Styles(pkg.text("xl/styles.xml"))
    want, heads, notes, n_groups = {}, {}, {}, 0      # new row -> (bold, italic, indent); row -> note text
    delta = 0
    for first, last, seq in sorted(order.values()):
        sec = next(s for s in plan["layout"] if order[s["section"]][0] == first)
        gi = -1
        for k, (kind, v) in enumerate(seq):
            r = first + delta + k
            if kind == "head":
                gi += 1
                g = sec["groups"][gi]
                heads[r] = g["title"]
                n_groups += 1
                if g.get("note") and not g.get("result"):
                    notes[r] = g["note"]                # no result row: the note sits on the group name
            elif kind == "line" and r not in m.analysis_rows:
                g = sec["groups"][gi]
                key = next(kk for kk, rr in m.keys.items() if rr == r)
                if g.get("reference"):
                    want[r] = (False, True, 1)
                elif key == g.get("result"):
                    if g.get("note"):
                        notes[r] = g["note"]
                    want[r] = (True, False, 0)
                elif any(isinstance(vals[r][c - 1], (int, float)) for c in fc if c - 1 < len(vals[r])):
                    want[r] = (False, False, 1)
                else:
                    want[r] = (False, True, 2)
        delta += len(seq) - (last - first + 1)

    def restyle(mm):
        col, r = mm.group(1), int(mm.group(2))
        if r not in want:
            return mm.group(0)
        b, i, ind = want[r]
        c = colnum_(col)
        if c != 2 and c not in pc:
            return mm.group(0)
        s = re.search(r'\bs="(\d+)"', mm.group(3))
        new = st.restyle(int(s.group(1)) if s else 0, b, i, ind if c == 2 else None)
        attrs = re.sub(r'\s*\bs="\d+"', "", mm.group(3)) + f' s="{new}"'
        return f'<c r="{col}{r}"{attrs}{mm.group(4)}'
    xml = CELL_S.sub(restyle, xml)
    base = {}
    for r in heads:                                    # a group name: column B like the line below it, plain, no indent
        s = re.search(rf'<c r="B{r + 1}"[^>]*?\bs="(\d+)"', xml)
        base[f"B{r}"] = ("s", heads[r], str(st.restyle(int(s.group(1)) if s else 0, False, False, 0)))
    xml, _ = set_cells(xml, base, replace=True)
    pkg.put(part, xml)
    pkg.put("xl/styles.xml", st.render())
    from build import _add_notes, _ensure_r_ns
    _add_notes(pkg, part, {f"B{r}": GUIDE_NOTE + n.strip() for r, n in notes.items()}, prefix=GUIDE_NOTE)
    pkg.put(part, _ensure_r_ns(pkg.text(part)))
    pkg.finish()
    pkg.save(out)
    import modfill; modfill.fix(out, out)   # the user's MOD fill convention (quarters plain, years grey), every save
    _size_notes(out, {r - 1: n for r, n in notes.items()})
    import notebox; notebox.fix(out, out)   # note boxes open readable (none squashed next to spacer / hidden columns), every save
    return fn, {"sections": len(order), "groups": n_groups, "rows_styled": len(want), "notes": len(notes)}


def main():
    ap = argparse.ArgumentParser()
    for n in ("model", "plan", "out", "work"):
        ap.add_argument("--" + n, required=True)
    a = ap.parse_args()
    plan = json.load(open(a.plan))
    if not plan.get("layout"):
        shutil.copyfile(a.model, a.out)
        print(json.dumps({"sections": 0, "problems": []}))
        return
    try:
        fn, rep = layout(a.model, plan, a.out)
    except ValueError as e:
        print(json.dumps({"problems": str(e).split("; ")}, indent=1))
        sys.exit(1)
    bad = check(a.model, a.out, fn, a.work)
    rep.update(problems=bad[:30], n_problems=len(bad))
    print(json.dumps(rep, indent=1))
    if bad:
        os.remove(a.out)
        sys.exit(1)


if __name__ == "__main__":
    main()
