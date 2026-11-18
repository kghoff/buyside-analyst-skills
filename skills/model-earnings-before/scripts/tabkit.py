# skills/model-earnings-before/scripts/tabkit.py
"""(Copied from model-short build.py, Nov 2026; keep in sync. Changes: _n replaces shortmath._n; W.link and W.formula
take check=False for cells verify.py must not compare, such as dates; W.typed_text and W.value are new.) The
tab-writing kit: the cell writer W, what a rerun keeps (resolve_values), and the raw-XML steps that place a whole tab
without touching any other part of the workbook."""
import math
import re
import zipfile

from xlsx import Package, Sheet, esc, relpath_of, resolve

BLUE, BLACK, GREEN, RED, YELLOW = "FF0000FF", "FF000000", "FF008000", "FFC00000", "FFFFFF00"
GEN = "General"


def _n(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _same(a, b):
    if _n(a) and _n(b):
        return abs(a - b) <= 1e-9 * max(1.0, abs(a), abs(b))
    return str(a).strip() == str(b).strip()


def resolve_values(existing, written, new):
    """Per label: (value to write, the user's?). existing = {label: value} on the tab now (None: no tab); written =
    {label: {"value", "user"}} from the last build (None: no record); new = the agent's values now. A value is the
    user's when it differs from what the last build wrote (with no record: from the agent's value), or was the
    user's before."""
    used, users = {}, set()
    for label, v in new.items():
        cur = (existing or {}).get(label)
        if cur is None:
            used[label] = v
            continue
        rec = (written or {}).get(label)
        theirs = (rec.get("user") or not _same(cur, rec.get("value"))) if rec else (existing is not None and not _same(cur, v))
        used[label] = cur if theirs else v
        if theirs:
            users.add(label)
    return used, users


class W:
    """Cell writer: styles, kinds (typed / link / formula / input / text), notes, expected values, number formats."""

    def __init__(self, st, users=()):
        self.sh, self.st, self.s, self.users = Sheet(), st, {}, set(users)
        self.expected, self.notes, self.inputs, self.kinds, self.fmt, self.col_a = {}, {}, {}, {}, {}, {}

    def style(self, color=BLACK, fmt=GEN, b=False, i=False, fill=None, sz=11, wrap=False):
        k = (color, fmt, b, i, fill, sz, wrap)
        if k not in self.s:
            self.s[k] = self.st.xf(color=color, fmt=fmt, b=b, i=i, fill=fill, sz=sz, align="left" if wrap else None)
        return self.s[k]

    def text(self, ref, t, color=BLACK, b=False, i=False, sz=11, wrap=False):
        self.sh.set(ref, "s", str(t), self.style(color, GEN, b, i, None, sz, wrap))
        self.kinds.setdefault(ref, "text")
        if re.fullmatch(r"A\d+", ref):
            self.col_a[ref] = str(t)

    def typed_text(self, ref, t, note):
        self.sh.set(ref, "s", str(t), self.style(BLUE, GEN))
        self.kinds[ref], self.notes[ref] = "typed", note

    def typed(self, ref, v, fmt, note):
        if not _n(v):
            return self.text(ref, "n/a", i=True)
        self.sh.set(ref, "n", v, self.style(BLUE, fmt))
        self.kinds[ref], self.notes[ref], self.fmt[ref] = "typed", note, fmt
        self.expected[ref] = v                    # note.py reads every number from 'expected'

    def value(self, ref, v, fmt):
        """A typed number whose source note sits on its block's header (the frozen forecast)."""
        if _n(v):
            self.sh.set(ref, "n", v, self.style(BLUE, fmt))
            self.kinds[ref], self.fmt[ref], self.expected[ref] = "typed", fmt, v

    def link(self, ref, target, fmt, expect, check=True):
        self.sh.set(ref, "f", target, self.style(GREEN, fmt))
        self.kinds[ref], self.fmt[ref] = "link", fmt
        if check:
            self.expected[ref] = expect

    def formula(self, ref, f, fmt, expect, b=False, check=True):
        self.sh.set(ref, "f", f, self.style(BLACK, fmt, b=b))
        self.kinds[ref], self.fmt[ref] = "formula", fmt
        if check:
            self.expected[ref] = expect

    def input_(self, ref, label, v, fmt, note):
        if isinstance(v, str) and v.startswith("="):
            kind, val = "f", v[1:]
        else:
            kind, val = ("n", v) if _n(v) else ("s", str(v))
        self.sh.set(ref, kind, val, self.style(BLUE, fmt, fill=YELLOW))
        self.kinds[ref], self.inputs[label], self.notes[ref], self.fmt[ref] = "input", ref, note, fmt


def _move_after(pkg, name, after):
    """Copied from model-valuation build.py, Nov 2026; keep in sync."""
    wb = pkg.text("xl/workbook.xml")
    tags = re.findall(r"<sheet\b[^>]*/>", wb)
    me = [t for t in tags if f'name="{esc(name)}"' in t][0]
    rest = [t for t in tags if t is not me]
    i = next((k for k, t in enumerate(rest) if f'name="{esc(after)}"' in t), len(rest) - 1)
    order = rest[:i + 1] + [me] + rest[i + 1:]
    body = re.search(r"<sheets>(.*?)</sheets>", wb, re.S)
    wb = wb[:body.start(1)] + "".join(order) + wb[body.end(1):]
    new_pos = {tags.index(t): k for k, t in enumerate(order)}
    wb = re.sub(r'(<definedName\b[^>]*?localSheetId=")(\d+)(")',
                lambda m: f"{m.group(1)}{new_pos.get(int(m.group(2)), int(m.group(2)))}{m.group(3)}", wb)
    pkg.put("xl/workbook.xml", wb)


def tab_parts(pkg, name):
    sh = {s[0]: s for s in pkg.sheets()}.get(name)
    if not sh:
        return set()
    part = sh[3]
    out = {part, relpath_of(part)}
    for _, (_, tgt) in pkg.rels(relpath_of(part)).items():
        if "TargetMode" not in tgt:
            out.add(resolve(part, tgt))
    return out


def sheet_part(path, name):
    return {s[0]: s for s in Package(path).sheets()}[name][3]


def changed_parts(model, out, allowed):
    a, b = zipfile.ZipFile(model), zipfile.ZipFile(out)
    A = {n: a.read(n) for n in a.namelist()}
    B = {n: b.read(n) for n in b.namelist()}
    ok = {"xl/workbook.xml", "xl/_rels/workbook.xml.rels", "[Content_Types].xml", "xl/styles.xml",
          "xl/calcChain.xml"} | set(allowed)
    return sorted(n for n in set(A) | set(B) if n not in ok and A.get(n) != B.get(n))
