"""Shared helpers for working on a house-layout model (Q1 | Q2 | Q3 | Q4 | FY | spacer per year) with openpyxl.

- period map from the header row (same parsing as the BuySideMacros ParsePeriod / LoadPeriodMap)
- find rows by their column-B label inside a section (sections = non-empty column-A headers)
- insert / delete rows WITH formula references shifted (openpyxl's insert_rows does not do this)
- The user's colour rule, provenance notes, and a small formula evaluator for checks (no Excel needed)"""
import re
from copy import copy
from openpyxl.comments import Comment
from openpyxl.formula.tokenizer import Tokenizer
from openpyxl.worksheet.dimensions import RowDimension
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter as L, column_index_from_string as CI

BLUE, GREEN, BLACK = "FF0000FF", "FF008000", "FF000000"
PCT_FMT = "#,##0.0%_);(#,##0.0%)"
BPS_FMT = "#,##0_);(#,##0)"
ANALYSIS_INDENT = 2


# ------------------------------------------------------------------ periods
def parse_period(v):
    """'Q1 23' -> (1, 2023); 2023 / '2023' / 'FY23' / '2026E' -> (0, 2023); else None"""
    if v is None: return None
    s = str(v).upper().replace(" ", "").replace("'", "").replace("’", "").replace("-", "").replace("/", "")
    if len(s) < 2: return None
    if s[-1] in "EA": s = s[:-1]
    fy = s.startswith("FY")
    if fy: s = s[2:]
    m = re.fullmatch(r"Q([1-4])(.*)", s) or re.fullmatch(r"([1-4])Q(.*)", s)
    q, rest = (int(m.group(1)), m.group(2)) if m else (0, s)
    if re.fullmatch(r"\d{4}", rest):
        y = int(rest)
        if not 1900 <= y <= 2100: return None
    elif re.fullmatch(r"\d{2}", rest):
        if q == 0 and not fy: return None
        y = int(rest); y += 2000 if y < 50 else 1900
    else:
        return None
    return (q, y)


class PeriodMap:
    def __init__(self, ws):
        best, self.hdr = 0, None
        for r in range(1, 16):
            n = sum(1 for c in range(1, min(ws.max_column, 1000) + 1) if parse_period(ws.cell(r, c).value))
            if n > best: best, self.hdr = n, r
        self.col = {}          # (q, y) -> col ; q = 0 for FY
        self.per = {}          # col -> (q, y)
        self.estimate = set()  # columns whose header ends with E
        for c in range(1, ws.max_column + 1):
            v = ws.cell(self.hdr, c).value
            p = parse_period(v)
            if p:
                self.col.setdefault(p, c); self.per[c] = p
                if str(v).strip().upper().endswith("E"): self.estimate.add(c)
        self.first = min(self.per) if self.per else None

    def key(self, c):
        q, y = self.per[c]
        return f"FY {y % 100:02d}" if q == 0 else f"Q{q} {y % 100:02d}"

    def by_key(self, k):
        q = 0 if k.startswith("FY") else int(k[1]); y = 2000 + int(k[3:])
        return self.col.get((q, y))

    def compare(self, c, kind):
        q, y = self.per[c]
        if kind == "yoy": return self.col.get((q, y - 1))
        if kind == "2yr": return self.col.get((q, y - 2))
        if kind == "qoq":
            if q == 1: return self.col.get((4, y - 1))
            if q > 1: return self.col.get((q - 1, y))
        return None


# ------------------------------------------------------------------ rows / sections
def norm(s):
    return re.sub(r"\s+", " ", str(s or "").replace("\t", " ").replace(":", "")).strip().lower()


def sections(ws):
    """[(row, title)] for column-A section headers (top-level, ALL CAPS rows like 'INCOME STATEMENT')"""
    out = []
    for r in range(1, ws.max_row + 1):
        a = ws.cell(r, 1).value
        if isinstance(a, str) and a.strip() and a.strip() == a.strip().upper() and not a.strip().endswith(":") and "MODEL" not in a.upper():
            out.append((r, a.strip()))
    return out


def section_bounds(ws, title):
    secs = sections(ws)
    for i, (r, t) in enumerate(secs):
        if norm(t) == norm(title) or norm(t).startswith(norm(title)):
            end = secs[i + 1][0] if i + 1 < len(secs) else ws.max_row + 1
            return r, end
    return None


def find_row(ws, pattern, section=None, after=None):
    r0, r1 = section_bounds(ws, section) if section else (1, ws.max_row + 1)
    for r in range(max(r0, after or 0), r1):
        if re.search(pattern, norm(ws.cell(r, 2).value)):
            return r
    return None


# ------------------------------------------------------------------ insert / delete rows with references shifted
# Excel shifts every reference to moved rows, on every sheet; openpyxl shifts none. insert_rows / delete_rows do what
# Excel does: formulas on the edited sheet (bare or 'MOD!' references) and on every other sheet (e.g. the ANALYZED
# tab's '=MOD!F12' links), ranges, whole-row ranges, merged cells, freeze panes, row heights and outline levels.
CELL = re.compile(r"^(\$?)([A-Z]{1,3})(\$?)(\d+)$")
ROWNUM = re.compile(r"^(\$?)(\d+)$")


class RefIntoDeleted(ValueError):
    pass


def _row(r, at, n):
    if n >= 0: return r + n if r >= at else r
    if at <= r < at - n: raise RefIntoDeleted(r)
    return r + n if r >= at - n else r


def _map_ref(ref, fn):
    """'C40', '$C$40:D41', '5:7' (no sheet prefix) -> rows mapped by fn; whole columns and names are left alone"""
    out = []
    for p in ref.split(":"):
        m = CELL.match(p)
        if m: out.append(f"{m.group(1)}{m.group(2)}{m.group(3)}{fn(int(m.group(4)))}"); continue
        m = ROWNUM.match(p)
        out.append(f"{m.group(1)}{fn(int(m.group(2)))}" if m else p)
    return ":".join(out)


def _shift_ref(ref, at, n):
    return _map_ref(ref, lambda r: _row(r, at, n))


def map_formula(f, sheet, fn, home=True):
    """rewrite the row numbers of every reference to `sheet` in formula f with fn(row).
    home=True: f sits on `sheet`, so bare references count too."""
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


def shift_formula(f, sheet, at, n, home=True):
    """shift the references to `sheet` in formula f as Excel does when n rows are inserted (n < 0: deleted) at `at`"""
    return map_formula(f, sheet, lambda r: _row(r, at, n), home)


def sheet_refs(f, sheet, home=True):
    """single-cell coordinates on `sheet` that formula f refers to, in order (ranges expanded)"""
    out = []
    for t in Tokenizer(f).items:
        if not (t.type == "OPERAND" and t.subtype == "RANGE"): continue
        v = t.value
        if "!" in v:
            s, v = v.rsplit("!", 1)
            if s.strip("'").replace("''", "'") != sheet: continue
        elif not home: continue
        parts = [CELL.match(p) for p in v.replace("$", "").split(":")]
        if not all(parts): continue
        if len(parts) == 1: out.append(f"{parts[0].group(2)}{parts[0].group(4)}"); continue
        (c1, r1), (c2, r2) = [(CI(p.group(2)), int(p.group(4))) for p in parts]
        out += [f"{L(c)}{r}" for c in range(c1, c2 + 1) for r in range(r1, r2 + 1)]
    return out


def _shift_rows(ws, at, n):
    wb = ws.parent
    import safe_save                                     # the save replays this move on the user's raw file
    safe_save.log_move(ws, safe_save.insert_fn(at, n) if n > 0 else safe_save.delete_fn(at, -n))
    for sh in wb.worksheets:
        home = sh is ws
        if home and (sh.conditional_formatting._cf_rules or sh.data_validations.dataValidation):
            print(f"WARNING: {sh.title} has conditional formatting / data validation - not shifted")
        for row in sh.iter_rows():
            for c in row:
                if not (isinstance(c.value, str) and c.value.startswith("=")) or not (home or ws.title in c.value): continue
                if home and n < 0 and at <= c.row < at - n: continue          # deleted with its row
                try:
                    c.value = shift_formula(c.value, ws.title, at, n, home)
                except RefIntoDeleted:
                    raise ValueError(f"{sh.title}!{c.coordinate} refers into rows being deleted: {c.value}")
    merged = [str(m) for m in ws.merged_cells.ranges]
    for m in merged: ws.unmerge_cells(m)
    dims = dict(ws.row_dimensions.items())
    if n > 0: ws.insert_rows(at, n)
    else: ws.delete_rows(at, -n)
    ws.row_dimensions.clear()
    for r, d in dims.items():
        if n < 0 and at <= r < at - n: continue
        nr = _row(r, at, n)
        nd = RowDimension(ws, index=nr, ht=d.ht, customHeight=d.customHeight, hidden=d.hidden, outlineLevel=d.outlineLevel, collapsed=d.collapsed)
        nd._style = copy(d._style)
        ws.row_dimensions[nr] = nd
    for m in merged:
        try: ws.merge_cells(_shift_ref(m, at, n))
        except RefIntoDeleted: pass                                           # merged range was inside the deleted rows
    if ws.freeze_panes:
        m = CELL.match(ws.freeze_panes); r = int(m.group(4))
        ws.freeze_panes = f"{m.group(2)}{at if n < 0 and at <= r < at - n else _row(r, at, n)}"


def insert_rows(ws, at, n=1):
    """insert n blank rows before row `at`; every formula in the workbook keeps pointing at the same cells"""
    if n > 0: _shift_rows(ws, at, n)


def delete_rows(ws, at, n=1):
    """delete n rows from `at`; raises (before saving anything) if a formula outside them refers into them"""
    if n > 0: _shift_rows(ws, at, -n)


# ------------------------------------------------------------------ colours / notes
def color_for(v, input_row=False):
    """The user's rule: reported numbers blue (incl. Q4 plugs / number-only formulas), links green, other formulas black."""
    if v is None: return None
    if input_row: return BLUE
    if not isinstance(v, str) or not v.startswith("="): return BLUE
    body = v[1:].replace("$", "")
    if re.fullmatch(r"[\d.+\-*/() ]+", body): return BLUE
    if re.fullmatch(r"-?[A-Z]{1,3}\d+", body): return GREEN
    return BLACK


def set_font_color(cell, color):
    f = cell.font
    cell.font = Font(name=f.name, sz=f.sz, b=f.b, i=f.i, u=f.u, color=color)


def note(cell, text, author="Claude"):
    keep = ""
    if cell.comment and author not in (cell.comment.author or ""):
        keep = cell.comment.text + "\n\n"                    # never drop the user's own note
    cm = Comment(keep + text, author); cm.width, cm.height = 360, 140
    cell.comment = cm


def fmt_num(x):
    return f"{round(x, 4):.4f}".rstrip("0").rstrip(".")


def number_expr(vals):
    """[0.6, 3.2] -> '=0.6+3.2' ; [7.2] -> 7.2 ; [] -> 0  (the house convention for combined typed numbers)"""
    vals = [round(v, 4) for v in vals if abs(v) > 1e-9]
    if not vals: return 0
    if len(vals) == 1: return vals[0]
    return "=" + fmt_num(vals[0]) + "".join(("+" if v > 0 else "-") + fmt_num(abs(v)) for v in vals[1:])


# ------------------------------------------------------------------ evaluator (enough for model formulas)
class Evaluator:
    def __init__(self, ws):
        self.ws, self.memo = ws, {}

    def v(self, ref):
        ref = ref.replace("$", "")
        if ref in self.memo: return self.memo[ref]
        self.memo[ref] = None
        x = self.ws[ref].value
        if isinstance(x, str) and x.startswith("="):
            body = x[1:]
            body = re.sub(r"(SUM|AVERAGE)\(\$?([A-Z]{1,3})\$?(\d+):\$?([A-Z]{1,3})\$?(\d+)\)",
                          lambda m: f"_{m.group(1).lower()}('{m.group(2)}{m.group(3)}','{m.group(4)}{m.group(5)}')", body)
            body = re.sub(r"(?<![A-Za-z'_])\$?([A-Z]{1,3})\$?(\d+)(?!['\d])", lambda m: f"_v('{m.group(1)}{m.group(2)}')", body)
            body = re.sub(r"IFERROR\(", "_iferror(lambda: ", body).replace("SUM(", "_sumargs(")
            try:
                x = eval(body, {"_v": self._num, "_sum": self.sum, "_average": self.avg, "_sumargs": lambda *a: sum(a),
                                "_iferror": self._iferror})
            except Exception:
                x = None
        self.memo[ref] = x
        return x

    def _num(self, ref):
        x = self.v(ref)
        if x is None: return 0.0
        if isinstance(x, str): raise TypeError(x)
        return x

    def _iferror(self, f, alt):
        try: return f()
        except Exception: return alt

    def rng(self, a, b):
        ca, ra = re.match(r"([A-Z]+)(\d+)", a).groups(); cb, rb = re.match(r"([A-Z]+)(\d+)", b).groups()
        return [self.v(f"{L(c)}{r}") for c in range(CI(ca), CI(cb) + 1) for r in range(int(ra), int(rb) + 1)]

    def sum(self, a, b): return sum(x for x in self.rng(a, b) if isinstance(x, (int, float)))

    def avg(self, a, b):
        xs = [x for x in self.rng(a, b) if isinstance(x, (int, float))]
        return sum(xs) / len(xs) if xs else 0
