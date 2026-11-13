"""The house MOD fill convention: check it, and re-apply it (fills only; values, fonts, number formats untouched).

usage: python3 modfill.py check MODEL.xlsx          prints the cells that break it; exit 1 if any
       python3 modfill.py fix MODEL.xlsx OUT.xlsx   writes OUT with every MOD fill put back (OUT may equal MODEL)

The convention (house default, taken from a hand-fixed FY2025 in the DXCM model):
- an ordinary row: quarter cells have no fill, the fiscal-year cell has the grey annual fill, the label columns (left of
  the first period column) have the fill ordinary rows' labels have (none);
- a section title row (text in column A): every quarter and year cell carries that section's colour;
- spacer columns, and year columns with no quarters beside them (e.g. a 2050E terminal column), are left alone.
The fills themselves are read from the model (the last fully reported year's columns, by majority), so the rule
needs no colour names and works on any model built from the house template. A model that doesn't follow the convention
at all (no fully reported year, no section titles, or ordinary rows whose year cells aren't filled / whose quarters
are) is left alone: check reports nothing and fix changes nothing, so a majority of wrong cells is never spread. Raw XML: every other part of the file is
copied byte for byte (safe on models with the user's text boxes and pictures). Canonical copy in model-historicals; the other
MOD-writing skills carry copies (keep in sync)."""
import collections
import re
import sys
import zipfile

TAB = "MOD"
Q = re.compile(r"Q[1-4] (\d\d)E?$")
FY = re.compile(r"(\d{4})E?$")
CELL = re.compile(r'<c r="([A-Z]+)(\d+)"([^>]*?)(/>|>(.*?)</c>)', re.S)
ROW = re.compile(r'<row r="(\d+)"([^>]*?)(/>|>(.*?)</row>)', re.S)


def _colnum(s):
    n = 0
    for ch in s:
        n = n * 26 + ord(ch) - 64
    return n


def _colname(n):
    s = ""
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def _fkey(f):
    """'' for no fill (Excel's patternType none / gray125, or openpyxl's bare <patternFill/>), else the fill's XML."""
    if not f or not re.search(r'patternType="(?!none"|gray125")', f):
        return ""
    return re.sub(r"\s+", " ", f)


def _unesc(t):
    return t.replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"').replace("&apos;", "'").replace("&amp;", "&")


class Book:
    def __init__(self, path):
        self.path = path
        z = zipfile.ZipFile(path)
        self.names = z.namelist()
        self.raw = {n: z.read(n) for n in self.names}
        wb = self.raw["xl/workbook.xml"].decode("utf-8")
        rid = re.search(rf'<sheet\b[^>]*name="{TAB}"[^>]*r:id="([^"]+)"', wb) or \
            re.search(rf'<sheet\b[^>]*r:id="([^"]+)"[^>]*name="{TAB}"', wb)
        if not rid:
            raise SystemExit(f"modfill: no '{TAB}' tab")
        rels = self.raw["xl/_rels/workbook.xml.rels"].decode("utf-8")
        tgt = re.search(rf'<Relationship\b[^>]*Id="{rid.group(1)}"[^>]*Target="([^"]+)"', rels) or \
            re.search(rf'<Relationship\b[^>]*Target="([^"]+)"[^>]*Id="{rid.group(1)}"', rels)
        t = tgt.group(1)
        self.sheet = t.lstrip("/") if t.startswith("/") else "xl/" + t
        self.xml = self.raw[self.sheet].decode("utf-8")
        self.styles = self.raw["xl/styles.xml"].decode("utf-8")
        ss = self.raw.get("xl/sharedStrings.xml", b"").decode("utf-8")
        self.strings = ["".join(_unesc(x) for x in re.findall(r"<t[^>]*>(.*?)</t>", si, re.S))
                        for si in re.findall(r"<si>(.*?)</si>", ss, re.S)]
        self.xfs = re.findall(r"<xf\b[^>]*?(?:/>|>.*?</xf>)", re.search(r"<cellXfs\b[^>]*>(.*?)</cellXfs>", self.styles, re.S).group(1), re.S)
        self.fills = re.findall(r"<fill\b[^>]*?(?:/>|>.*?</fill>)", re.search(r"<fills\b[^>]*>(.*?)</fills>", self.styles, re.S).group(1), re.S)

    # ---- reading
    def value(self, attrs, body):
        if body is None:
            return None
        if 't="s"' in attrs:
            v = re.search(r"<v>(\d+)</v>", body)
            return self.strings[int(v.group(1))] if v else None
        if 't="inlineStr"' in attrs:
            return "".join(_unesc(x) for x in re.findall(r"<t[^>]*>(.*?)</t>", body, re.S)) or None
        v = re.search(r"<v>(.*?)</v>", body, re.S)
        return _unesc(v.group(1)) if v else None

    def fill_key(self, s):
        """'' for no fill, else the fill's XML (equal fills compare equal whatever their index)."""
        xf = self.xfs[s] if s < len(self.xfs) else self.xfs[0]
        m = re.search(r'fillId="(\d+)"', xf)
        return _fkey(self.fills[int(m.group(1))] if m and int(m.group(1)) < len(self.fills) else "")

    def grid(self):
        """{row: {col number: (style index, attrs, body)}}"""
        out = {}
        for rm in ROW.finditer(self.xml):
            r = int(rm.group(1))
            cells = {}
            for cm in CELL.finditer(rm.group(4) or ""):
                s = re.search(r'\bs="(\d+)"', cm.group(3))
                cells[_colnum(cm.group(1))] = (int(s.group(1)) if s else 0, cm.group(3), cm.group(5))
            out[r] = cells
        return out


def layout(book, grid):
    """(quarter cols, year cols, reference year's (quarter cols, year col), title rows, first title row)."""
    hdr = {c: str(book.value(a, b) or "").strip() for c, (_, a, b) in grid.get(2, {}).items()}
    hdr = {c: (v[:-2] if re.fullmatch(r"\d{4}\.0", v) else v) for c, v in hdr.items() if v}
    qs = {c: v for c, v in hdr.items() if Q.match(v)}
    yy = {Q.match(v).group(1) for v in qs.values()}
    ys = {c: v for c, v in hdr.items() if FY.match(v) and v[2:4] in yy}
    ref = None
    for c, v in sorted(ys.items()):
        mine = [qc for qc, qv in qs.items() if qv.split()[1][:2] == v[2:4]]
        if len(mine) == 4 and not v.endswith("E") and not any(qs[qc].endswith("E") for qc in mine):
            ref = (sorted(mine), c)
    titles = sorted(r for r, cells in grid.items() if r > 2 and 1 in cells and (book.value(cells[1][1], cells[1][2]) or "").strip())
    if ref is None or not titles:
        return None
    return sorted(qs), sorted(ys), ref, set(titles), titles[0]


def expected(book, grid):
    """{(row, col): wanted fill key} for every quarter / year cell from the first section title down, or {} when the
    model doesn't follow the convention (nothing to enforce)."""
    lay = layout(book, grid)
    if lay is None:
        return {}
    qcols, ycols, (rq, ry), titles, first = lay
    key = lambda r, c: book.fill_key(grid.get(r, {}).get(c, (0,))[0])
    last = max(grid)
    normal = [r for r in range(first, last + 1) if r not in titles]
    want_q = collections.Counter(key(r, c) for r in normal for c in rq).most_common(1)[0][0]
    want_y = collections.Counter(key(r, ry) for r in normal).most_common(1)[0][0]
    if want_q != "" or want_y == "":                 # not the house convention: plain quarters, filled years
        return {}
    labels = list(range(1, min(qcols + ycols)))      # A, B, C... left of the first period column
    want_l = {c: collections.Counter(key(r, c) for r in normal).most_common(1)[0][0] for c in labels}
    out = {}
    for r in range(first, last + 1):
        if r in titles:
            w = collections.Counter(key(r, c) for c in qcols + ycols).most_common(1)[0][0]
            out.update({(r, c): w for c in qcols + ycols})
        else:
            out.update({(r, c): want_q for c in qcols})
            out.update({(r, c): want_y for c in ycols})
            out.update({(r, c): want_l[c] for c in labels})
    return out


def check(path):
    """[(cell, has, wants)] for every MOD cell whose fill breaks the convention ('' = no fill)."""
    b = Book(path)
    g = b.grid()
    bad = []
    for (r, c), w in sorted(expected(b, g).items()):
        have = b.fill_key(g.get(r, {}).get(c, (0,))[0])
        if have != w:
            bad.append((f"{_colname(c)}{r}", have, w))
    return bad


def summary(bad, limit=12):
    """Plain lines for the user / a report: problem cells grouped by row."""
    rows = collections.defaultdict(list)
    for ref, have, want in bad:
        rows[int(re.search(r"\d+", ref).group(0))].append(re.match(r"[A-Z]+", ref).group(0))
    out = [f"MOD row {r}: {len(cs)} cells with the wrong fill ({', '.join(cs[:4])}{' ...' if len(cs) > 4 else ''})"
           for r, cs in sorted(rows.items())[:limit]]
    if len(rows) > limit:
        out.append(f"... and {len(rows) - limit} more rows")
    return out


def fix(path, out):
    """Put every MOD fill back to the convention; returns the number of cells changed."""
    b = Book(path)
    g = b.grid()
    exp = expected(b, g)
    fill_id = {}                                     # fill key -> an existing fillId with it
    for i, f in enumerate(b.fills):
        fill_id.setdefault(_fkey(f), i)
    fill_id[""] = 0
    new_xfs, made = [], {}

    def restyle(s, want):
        if (s, want) not in made:
            xf = b.xfs[s] if s < len(b.xfs) else b.xfs[0]
            head = re.match(r"<xf\b[^>]*?(?=/?>)", xf).group(0)
            rest = xf[len(head):]
            head = re.sub(r'\s*fillId="\d+"', "", head)
            head = re.sub(r'\s*applyFill="\d+"', "", head)
            head += f' fillId="{fill_id[want]}" applyFill="1"'
            new = head + rest
            if new in b.xfs:
                made[(s, want)] = b.xfs.index(new)
            elif new in new_xfs:
                made[(s, want)] = len(b.xfs) + new_xfs.index(new)
            else:
                new_xfs.append(new)
                made[(s, want)] = len(b.xfs) + len(new_xfs) - 1
        return made[(s, want)]

    todo = collections.defaultdict(dict)             # row -> {col: new style}
    for (r, c), w in exp.items():
        s = g.get(r, {}).get(c, (0,))[0]
        if b.fill_key(s) != w:
            if w not in fill_id:
                raise SystemExit(f"modfill: no fill in styles.xml matches the wanted one for {_colname(c)}{r}")
            todo[r][c] = restyle(s, w)
    n = sum(len(v) for v in todo.values())

    def edit_row(m):
        r = int(m.group(1))
        if r not in todo:
            return m.group(0)
        body = m.group(4) or ""
        want = todo[r]
        cells = []
        for cm in CELL.finditer(body):
            c = _colnum(cm.group(1))
            text = cm.group(0)
            if c in want:
                a = cm.group(3)
                a = re.sub(r'\s*\bs="\d+"', "", a) + f' s="{want.pop(c)}"'
                text = f'<c r="{cm.group(1)}{cm.group(2)}"{a}{cm.group(4)}'
            cells.append((c, text))
        cells += [(c, f'<c r="{_colname(c)}{r}" s="{s}"/>') for c, s in want.items()]
        cells.sort(key=lambda x: x[0])
        attrs = re.sub(r'\s*spans="[^"]*"', "", m.group(2))
        return f'<row r="{r}"{attrs}>' + "".join(t for _, t in cells) + "</row>"

    xml = ROW.sub(edit_row, b.xml)
    missing = sorted(r for r in todo if not re.search(rf'<row r="{r}"', xml))
    if missing:                                      # rows with no XML at all: add them in order
        def add(xml, r):
            cells = "".join(f'<c r="{_colname(c)}{r}" s="{s}"/>' for c, s in sorted(todo[r].items()))
            later = next((int(x) for x in re.findall(r'<row r="(\d+)"', xml) if int(x) > r), None)
            el = f'<row r="{r}">{cells}</row>'
            return xml.replace(f'<row r="{later}"', el + f'<row r="{later}"', 1) if later else \
                xml.replace("</sheetData>", el + "</sheetData>", 1)
        for r in missing:
            xml = add(xml, r)
    st = b.styles
    if new_xfs:
        m = re.search(r"<cellXfs\b([^>]*)>(.*?)</cellXfs>", st, re.S)
        attrs = re.sub(r'\s*count="\d+"', "", m.group(1))
        st = st[:m.start()] + f'<cellXfs count="{len(b.xfs) + len(new_xfs)}"{attrs}>{m.group(2)}{"".join(new_xfs)}</cellXfs>' + st[m.end():]
    with zipfile.ZipFile(path) as zin:
        infos = zin.infolist()
    data = dict(b.raw)
    data[b.sheet] = xml.encode("utf-8")
    data["xl/styles.xml"] = st.encode("utf-8")
    tmp = out + ".modfill.tmp"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        for info in infos:
            zout.writestr(info, data[info.filename])
    import os
    os.replace(tmp, out)
    return n


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "check":
        bad = check(sys.argv[2])
        print(f"{len(bad)} MOD cells break the fill convention")
        for line in summary(bad):
            print("  " + line)
        sys.exit(1 if bad else 0)
    if len(sys.argv) >= 4 and sys.argv[1] == "fix":
        print(f"fixed {fix(sys.argv[2], sys.argv[3])} MOD cells")
        sys.exit(0)
    print(__doc__)
    sys.exit(2)
