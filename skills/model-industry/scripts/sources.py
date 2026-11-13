"""Read a MOD-style model (the subject's, or a peer's own research model) by label into {line: {fy: value}}.

Values come from the cached results (data_only). A model openpyxl wrote has no cached results: `missing_cache`
counts formula cells (any matched row, any FY) with no cached value; then pass `values`, a LibreOffice-recalculated
copy (lo.recalc). Only actual fiscal-year columns (header "2025", not "2025E")."""
import re

import openpyxl
from openpyxl.utils import get_column_letter

import lines

Q_RE = re.compile(r"^Q[1-4] \d\d")
FY_RE = re.compile(r"^(\d{4})$")


def clean(v):
    return re.sub(r"\s+", " ", str(v if v is not None else "")).strip()


def _grid(path, data_only=True):
    wb = openpyxl.load_workbook(path, read_only=True, data_only=data_only)
    g = [list(r) for r in wb["MOD"].iter_rows(values_only=True)]
    wb.close()
    return g


def _match(labels, groups):
    for grp in groups:
        rows, ok = [], True
        for p in grp:
            opt = p.startswith("?")
            pat = p[1:] if opt else p
            hit = next((r for r, lab in labels if re.search(pat, lab, re.I)), None)
            if hit is None and not opt:
                ok = False
                break
            if hit is not None:
                rows.append(hit)
        if ok and rows:
            return rows
    return None


def mod_read(model, values=None):
    g = _grid(model)
    hr = max(range(min(10, len(g))), key=lambda i: sum(1 for c in g[i] if Q_RE.match(clean(c))))
    fy_cols = {}
    for j, h in enumerate(g[hr]):
        m = FY_RE.match(clean(h))
        if m and 1990 < int(m[1]) < 2100:
            fy_cols[int(m[1])] = get_column_letter(j + 1)
    labels = [(i + 1, clean(r[1] if len(r) > 1 else None)) for i, r in enumerate(g)]
    vg = _grid(values) if values else g
    fg = _grid(model, data_only=False)
    rows, vals, formula, missing = {}, {}, {}, 0
    for k in lines.INPUTS:
        rs = _match(labels, lines.MOD[k])
        rows[k], vals[k], formula[k] = rs, {}, {}
        if not rs:
            continue
        for fy, col in fy_cols.items():
            j = openpyxl.utils.column_index_from_string(col) - 1
            missing += sum(1 for r in rs if j < len(fg[r - 1]) and str(fg[r - 1][j]).startswith("=")
                           and (j >= len(g[r - 1]) or g[r - 1][j] is None))
            nums = [vg[r - 1][j] for r in rs if j < len(vg[r - 1])]
            nums = [x for x in nums if isinstance(x, (int, float)) and not isinstance(x, bool)]
            vals[k][fy] = sum(nums) if nums else None
            formula[k][fy] = "+".join(f"MOD!{col}{r}" for r in rs)
    labs = {k: [dict(labels)[r] for r in (rows[k] or [])] for k in rows}
    return {"fy_cols": fy_cols, "rows": rows, "labels": labs, "values": vals, "formula": formula,
            "missing_cache": missing}
