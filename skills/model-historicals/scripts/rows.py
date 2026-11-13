"""Insert / delete rows of the one-sheet template with every formula kept pointing at the same cells.

Deleting is how build.py drops the optional rows a company never reports (house default): a deleted row's term is
removed from every sum that used it ("=D5+D6+D7" -> "=D5+D7"), and a deleted optional subtotal is replaced by its
fallback row (EPS on "Net Income to Common" -> "Net Income" when there is no NCI or preferred dividend). A deleted row
used any other way (a ratio) is an error, so nothing is ever silently wrong.

Same tokenizer approach as /model-ratios's rowmap.py; kept separate so each skill installs on its own."""
import re
from copy import copy

from openpyxl.formula.tokenizer import Tokenizer, Token
from openpyxl.worksheet.dimensions import RowDimension

CELL = re.compile(r"^(\$?)([A-Z]{1,3})(\$?)(\d+)$")


def _map_ref(ref, fn):
    out = []
    for p in ref.split(":"):
        m = CELL.match(p)
        out.append(f"{m.group(1)}{m.group(2)}{m.group(3)}{fn(int(m.group(4)))}" if m else p)
    return ":".join(out)


def _ref_row(v):
    m = CELL.match(v.split("!")[-1])
    return int(m.group(4)) if m else None


def drop_terms(f, gone, fallback):
    """formula f without the terms that refer to rows in `gone` (fallback rows substituted first)"""
    items = [t for t in Tokenizer(f).items if t.type != Token.WSPACE]
    out, i = [], 0
    while i < len(items):
        t = items[i]
        r = _ref_row(t.value) if t.type == Token.OPERAND and t.subtype == Token.RANGE else None
        if r in fallback:
            t = Token(_map_ref(t.value, lambda x: fallback.get(x, x)), t.type, t.subtype)
        elif r in gone:
            prev = out[-1] if out else None
            nxt = items[i + 1] if i + 1 < len(items) else None
            linear = lambda x: x is None or (x.type == Token.OP_IN and x.value in "+-") or x.value in ("", "(", ")") \
                or x.type == Token.SEP
            if not (linear(prev) and linear(nxt)):
                raise ValueError(f"{f}: row {r} is used in a non-sum formula and has no fallback")
            if prev is not None and prev.type == Token.OP_IN:
                out.pop()                                     # "+D7" -> ""
            elif nxt is not None and nxt.type == Token.OP_IN:
                if nxt.value == "-": out.append(Token("-", Token.OP_PRE))
                i += 1                                        # "D5+" -> ""
            i += 1
            continue
        out.append(t)
        i += 1
    body = "".join(t.value for t in out)
    return "=" + (body if body.strip() else "0")


def remap(ws, new_of):
    """move rows: new_of {old row: new row} for every surviving row (rows not in it are deleted)"""
    maxr = ws.max_row
    olds = sorted(new_of)
    tail = (new_of[olds[-1]] - olds[-1]) if olds else 0
    fn = lambda r: new_of.get(r, r + tail if r > maxr else r)
    for row in ws.iter_rows():
        for c in row:
            if isinstance(c.value, str) and c.value.startswith("="):
                out = []
                for t in Tokenizer(c.value).items:
                    v = t.value
                    if t.type == Token.OPERAND and t.subtype == Token.RANGE and "!" not in v: v = _map_ref(v, fn)
                    out.append(v)
                c.value = "=" + "".join(out)
    merged = [str(m) for m in ws.merged_cells.ranges]
    for m in merged: ws.unmerge_cells(m)
    cells = list(ws._cells.items())
    ws._cells = {}
    for (r, col), cell in cells:
        if r not in new_of: continue
        cell.row = new_of[r]
        ws._cells[(cell.row, col)] = cell
    dims = dict(ws.row_dimensions.items())
    ws.row_dimensions.clear()
    for r, d in dims.items():
        if r not in new_of: continue
        nd = RowDimension(ws, index=new_of[r], ht=d.ht, customHeight=d.customHeight, hidden=d.hidden,
                          outlineLevel=d.outlineLevel, collapsed=d.collapsed)
        nd._style = copy(d._style)
        ws.row_dimensions[new_of[r]] = nd
    for m in merged: ws.merge_cells(_map_ref(m, fn))
    if ws.freeze_panes:
        m = CELL.match(ws.freeze_panes); r = int(m.group(4))
        keep = [x for x in olds if x >= r]
        ws.freeze_panes = f"{m.group(2)}{new_of[keep[0]] if keep else r}"


def insert_rows(ws, at, n=1):
    """n blank rows before row `at`"""
    remap(ws, {r: (r if r < at else r + n) for r in range(1, ws.max_row + 1)})


def delete_rows(ws, rows, fallback=None):
    """delete `rows`; sums lose their terms, fallback {deleted row: replacement row} for subtotals"""
    gone, fallback = set(rows), fallback or {}
    for row in ws.iter_rows():
        for c in row:
            if c.row in gone or not (isinstance(c.value, str) and c.value.startswith("=")): continue
            refs = {_ref_row(t.value) for t in Tokenizer(c.value).items if t.type == Token.OPERAND and t.subtype == Token.RANGE}
            if refs & (gone | set(fallback)): c.value = drop_terms(c.value, gone, fallback)
    kept = [r for r in range(1, ws.max_row + 1) if r not in gone]
    remap(ws, {r: i for i, r in enumerate(kept, 1)})
