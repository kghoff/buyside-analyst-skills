"""(Copied from model-earnings-before, Nov 2026; keep in sync. Origin: model-multiples.) Cell-note boxes: check them, and re-anchor the ones that would open squashed (text, authors, cells untouched).

usage: python3 notebox.py check MODEL.xlsx          prints the notes whose box is too narrow; exit 1 if any
       python3 notebox.py fix MODEL.xlsx OUT.xlsx   writes OUT with those boxes re-anchored (OUT may equal MODEL)

Why (house default): a note's box is pinned to the columns its <x:Anchor> names, and Excel draws it as wide as the
visible part of those columns. A note on a year column sits next to a 2-wide spacer and grouped, hidden quarters, so
a box anchored on "the next four columns" opens a few pixels wide and the user had to resize it by hand.
The rule, any sheet, any model: a box narrower than MIN_PX on screen is re-anchored to start in the first visible,
normal-width column right of its cell and to run across visible columns until it is BOX_PX wide. Boxes that are
already wide enough (including every box the user resized) are left alone. Raw XML: only the VML drawing parts change;
every other part of the file is copied byte for byte. Canonical copy in model-historicals; the skills that write notes into
the user's model carry copies (keep in sync)."""
import os
import posixpath
import re
import sys
import zipfile

MIN_PX = 60         # narrower than this on screen counts as squashed (Excel's own default box is ~144 px)
BOX_PX = 320        # width a re-anchored box gets (about 240pt)
SPACER = 3          # columns narrower than this (in Excel width units) are spacers: a box never starts in one
SHAPE = re.compile(r"<v:shape\b.*?</v:shape>", re.S)
ANCHOR = re.compile(r"(<x:Anchor>)([^<]*)(</x:Anchor>)")


def _px(width):
    return 0 if width is None else int(round(width * 7))


def _cols(sheet_xml):
    """{0-based column: width in Excel units, or None if hidden} plus the default width."""
    head = sheet_xml[:sheet_xml.find("<sheetData")]
    m = re.search(r'defaultColWidth="([\d.]+)"', head)
    default = float(m.group(1)) if m else 8.43
    cols = {}
    for m in re.finditer(r"<col\b([^>]*)/?>", head):
        a = dict(re.findall(r'(\w+)="([^"]*)"', m.group(1)))
        w = float(a.get("width", default))
        for c in range(int(a["min"]), int(a["max"]) + 1):
            cols[c - 1] = None if a.get("hidden") in ("1", "true") else w
    return cols, default


def _vml_parts(z):
    """[(sheet name, sheet xml, vml path)] for every sheet with notes."""
    wb = z.read("xl/workbook.xml").decode("utf-8")
    rels = z.read("xl/_rels/workbook.xml.rels").decode("utf-8")
    target = {m.group(1): m.group(2) for m in re.finditer(r'<Relationship\b[^>]*?Id="([^"]+)"[^>]*?Target="([^"]+)"', rels)}
    target.update({m.group(2): m.group(1) for m in re.finditer(r'<Relationship\b[^>]*?Target="([^"]+)"[^>]*?Id="([^"]+)"', rels)})
    out = []
    for m in re.finditer(r'<sheet\b[^>]*?name="([^"]*)"[^>]*?r:id="([^"]+)"', wb):
        t = target.get(m.group(2), "")
        path = t.lstrip("/") if t.startswith("/") else posixpath.normpath(posixpath.join("xl", t))
        rp = posixpath.join(posixpath.dirname(path), "_rels", posixpath.basename(path) + ".rels")
        if path not in z.namelist() or rp not in z.namelist():
            continue
        sx = z.read(path).decode("utf-8")
        lm = re.search(r'<legacyDrawing\b[^>]*r:id="([^"]+)"', sx)
        if not lm:
            continue
        srels = z.read(rp).decode("utf-8")
        vm = re.search(rf'<Relationship\b(?=[^>]*Id="{re.escape(lm.group(1))}")[^>]*Target="([^"]+)"', srels)
        if vm:
            t = vm.group(1)
            out.append((m.group(1), sx, t.lstrip("/") if t.startswith("/") else
                        posixpath.normpath(posixpath.join(posixpath.dirname(path), t))))
    return out


def _width(a, cols, default):
    w = lambda c: _px(cols.get(c, default))
    if a[4] == a[0]:
        return a[5] - a[1]
    return w(a[0]) - a[1] + sum(w(c) for c in range(a[0] + 1, a[4])) + a[5]


def _anchor(col, a, cols, default):
    """New anchor for a note on 0-based column `col`, keeping its rows."""
    width = lambda c: cols.get(c, default)
    left = col + 1
    while width(left) is None or width(left) < SPACER:
        left += 1
    need, right, off = BOX_PX - 15, left, 15
    while True:
        room = _px(width(right)) - (off if right == left else 0)
        if room >= need:
            roff = (off if right == left else 0) + need
            break
        need -= max(room, 0)
        right += 1
    top, toff, bottom, boff = a[2], a[3], a[6], a[7]
    if bottom <= top:
        bottom, boff = top + 5, 16
    return [left, 15, top, toff, right, roff, bottom, boff]


def _scan(z):
    """{vml path: [(sheet, shape text, cell, old anchor, new anchor)]} for every squashed box."""
    out = {}
    for name, sx, vp in _vml_parts(z):
        cols, default = _cols(sx)
        for s in SHAPE.findall(z.read(vp).decode("utf-8", "replace")):
            am, cm, rm = ANCHOR.search(s), re.search(r"<x:Column>\s*(\d+)", s), re.search(r"<x:Row>\s*(\d+)", s)
            if not (am and cm and rm):
                continue
            a = [int(x) for x in am.group(2).replace(",", " ").split()]
            if len(a) != 8 or _width(a, cols, default) >= MIN_PX:
                continue
            col, row = int(cm.group(1)), int(rm.group(1))
            out.setdefault(vp, []).append((name, s, f"{_colname(col + 1)}{row + 1}", a, _anchor(col, a, cols, default)))
    return out


def _colname(n):
    s = ""
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def check(path):
    """['MOD!BM141 (2 px wide)', ...] for every squashed note box."""
    with zipfile.ZipFile(path) as z:
        found = _scan(z)
        widths = {vp: _cols(sx) for _, sx, vp in _vml_parts(z)}
    return [f"{sheet}!{cell} ({_width(a, *widths[vp])} px wide)" for vp, items in found.items() for sheet, _, cell, a, _ in items]


def fix(path, out, since=None):
    """Re-anchor every squashed note box; returns the number of boxes changed. With `since` (the file a build started
    from), note drawings identical to the ones in it are left alone: a skill that may only change its own tabs fixes
    only the notes it wrote."""
    with zipfile.ZipFile(path) as z:
        found = _scan(z)
        infos = z.infolist()
        data = {i.filename: z.read(i.filename) for i in infos}
    if since:
        with zipfile.ZipFile(since) as z0:
            old = {vp: z0.read(vp) for vp in found if vp in z0.namelist()}
        found = {vp: v for vp, v in found.items() if old.get(vp) != data[vp]}
    n = 0
    for vp, items in found.items():
        v = data[vp].decode("utf-8", "replace")
        for _, s, _, _, new in items:
            t = ANCHOR.sub(lambda m: m.group(1) + ", ".join(map(str, new)) + m.group(3), s, count=1)
            t = re.sub(r"(?<![-\w])width:[\d.]+pt", f"width:{BOX_PX * 3 // 4}pt", t, count=1)
            v = v.replace(s, t, 1)
            n += 1
        data[vp] = v.encode("utf-8")
    if n or path != out:
        tmp = out + ".notebox.tmp"
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
            for info in infos:
                zout.writestr(info, data[info.filename])
        os.replace(tmp, out)
    return n


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "check":
        bad = check(sys.argv[2])
        print("\n".join(bad) if bad else "note boxes ok")
        sys.exit(1 if bad else 0)
    if len(sys.argv) == 4 and sys.argv[1] == "fix":
        print(f"{fix(sys.argv[2], sys.argv[3])} note boxes re-anchored")
        sys.exit(0)
    sys.exit(__doc__)
