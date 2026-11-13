"""Move MOD's rows to new row numbers in one pass, the way Excel does when rows are inserted or deleted: every
formula in the workbook (MOD itself and other tabs' MOD! links) keeps pointing at the same cells, and comments,
styles, row heights, merged cells and the freeze pane move with their rows.

Same reference rewriting as /model-kpis's xlmodel.py (openpyxl's formula tokenizer); kept separate so each
skill installs on its own."""
import re
from copy import copy

from openpyxl.formula.tokenizer import Tokenizer
from openpyxl.worksheet.dimensions import RowDimension

CELL = re.compile(r"^(\$?)([A-Z]{1,3})(\$?)(\d+)$")
ROWNUM = re.compile(r"^(\$?)(\d+)$")


class RefIntoDeleted(ValueError):
    pass


def _map_ref(ref, fn):
    out = []
    for p in ref.split(":"):
        m = CELL.match(p)
        if m: out.append(f"{m.group(1)}{m.group(2)}{m.group(3)}{fn(int(m.group(4)))}"); continue
        m = ROWNUM.match(p)
        out.append(f"{m.group(1)}{fn(int(m.group(2)))}" if m else p)
    return ":".join(out)


def map_formula(f, sheet, fn, home=True):
    """rewrite the row numbers of every reference to `sheet` in formula f with fn(row); home=True: f is on `sheet`"""
    out = []
    for t in Tokenizer(f).items:
        v = t.value
        if t.type == "OPERAND" and t.subtype == "RANGE":
            if "!" in v:
                s, ref = v.rsplit("!", 1)
                if s.strip("'").replace("''", "'") == sheet: v = s + "!" + _map_ref(ref, fn)
            elif home:
                v = _map_ref(v, fn)
        out.append(v)
    return "=" + "".join(out)


def row_fn(new_of, max_row):
    """new_of {old row: new row} for every surviving row 1..max_row (missing = deleted) -> fn(old) for formulas"""
    olds = sorted(new_of)
    tail = new_of[olds[-1]] - olds[-1] if olds else 0

    def fn(r):
        if r in new_of: return new_of[r]
        if r > max_row: return r + tail
        raise RefIntoDeleted(r)
    return fn


def remap_rows(ws, new_of):
    """move ws's rows: new_of maps each surviving old row to its new row (strictly increasing). Rows not in the map
    are deleted; raises ValueError (nothing changed) if a surviving formula anywhere refers into a deleted row."""
    wb, maxr = ws.parent, ws.max_row
    fn = row_fn(new_of, maxr)
    import safe_save                                     # the save replays this move on the user's raw file
    safe_save.log_move(ws, safe_save.remap_fn(new_of, maxr))
    gone = {r for r in range(1, maxr + 1) if r not in new_of}
    if ws.conditional_formatting._cf_rules or ws.data_validations.dataValidation:
        print(f"WARNING: {ws.title} has conditional formatting / data validation - not moved")
    edits = []
    for sh in wb.worksheets:
        home = sh is ws
        for row in sh.iter_rows():
            for c in row:
                v = c.value
                if not (isinstance(v, str) and v.startswith("=")) or not (home or ws.title in v): continue
                if home and c.row in gone: continue
                try:
                    edits.append((c, map_formula(v, ws.title, fn, home)))
                except RefIntoDeleted:
                    raise ValueError(f"{sh.title}!{c.coordinate} refers into rows being removed: {v}")
    for c, v in edits: c.value = v
    merged = [str(m) for m in ws.merged_cells.ranges]
    for m in merged: ws.unmerge_cells(m)
    cells = list(ws._cells.items())
    ws._cells = {}
    for (r, col), cell in cells:
        if r in gone: continue
        cell.row = new_of[r]
        ws._cells[(cell.row, col)] = cell
    dims = dict(ws.row_dimensions.items())
    ws.row_dimensions.clear()
    for r, d in dims.items():
        if r in gone or r > maxr: continue
        nd = RowDimension(ws, index=new_of[r], ht=d.ht, customHeight=d.customHeight, hidden=d.hidden,
                          outlineLevel=d.outlineLevel, collapsed=d.collapsed)
        nd._style = copy(d._style)
        ws.row_dimensions[new_of[r]] = nd
    for m in merged:
        try: ws.merge_cells(_map_ref(m, fn))
        except RefIntoDeleted: pass
    if ws.freeze_panes:
        m = CELL.match(ws.freeze_panes); r = int(m.group(4))
        keep = [x for x in new_of if x >= r]                       # a removed freeze row: the next surviving one
        ws.freeze_panes = f"{m.group(2)}{fn(r) if r in new_of or r > maxr else new_of[min(keep)] if keep else r}"
