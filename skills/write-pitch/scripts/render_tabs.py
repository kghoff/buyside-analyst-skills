"""Turn the recalculated values copy of the model into PNG pictures of every tab, so the analyst can see the charts.

usage: python3 render_tabs.py --values <recalculated copy> --out <work>/tabs

Writes tabs/index.json, tabs/index.md and the PNGs. index.json is a list with one entry per PNG:
{"tab", "page", "tile", "row", "col", "png" (relative to the tabs folder), "has_chart", "truncated"}; a tab that produced no
non-blank tile gets one entry with "png": null (and "note" when something went wrong).
- LibreOffice prints every tab, hidden ones too, as ONE page as wide and tall as the tab, in workbook order. Hidden tabs
  are left out of the index and the PNGs. A chartsheet gets an entry with png null (LibreOffice prints it blank).
- That page is cut into a grid of tiles of 1000 pt wide and 1.3 x that high (a narrower page: one column of its own
  width), rendered 1600 px wide, so a normal table or chart is legible. Tiles go row by row from the top-left; blank
  ones are skipped; at most MAX_CHART_TILES (24) non-blank per tab with a chart or image, MAX_PLAIN_TILES (4) without; "truncated": true when more were left out. Each entry has its grid
  "row" and "col" (1-based) and the file name carries them.
- has_chart comes from the xlsx zip itself: the tab's sheet rels point to a drawing part (charts and images).
- The intermediate PDF is deleted after tiling."""
import argparse
import json
import os
import posixpath
import re
import time
import zipfile
from xml.etree import ElementTree as ET

TILE_RATIO = 1.3
TILE_PT = 1000          # tile width in PDF points: about ten table columns or one Excel chart, legible at TILE_PX
TILE_PX = 1600
MAX_CHART_TILES = 24    # a tab with a chart or image: the analyst needs every chart
MAX_PLAIN_TILES = 4     # a tab without: its numbers are in the digest, tiles only show layout
NS_MAIN = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
NS_REL = "{http://schemas.openxmlformats.org/package/2006/relationships}"
NS_R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"


def sheets(xlsx):
    """[(name, state, part path)] in workbook order, from workbook.xml and its rels."""
    with zipfile.ZipFile(xlsx) as z:
        wb = ET.fromstring(z.read("xl/workbook.xml"))
        rels = {r.get("Id"): r.get("Target") for r in ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))}
    out = []
    for s in wb.iter(NS_MAIN + "sheet"):
        target = rels[s.get(NS_R + "id")]
        part = target.lstrip("/") if target.startswith("/") else posixpath.normpath("xl/" + target)
        out.append((s.get("name"), s.get("state") or "visible", part))
    return out


def chart_tabs(xlsx):
    """Names of the tabs whose worksheet has a drawing part (a chart or an image)."""
    found = set()
    with zipfile.ZipFile(xlsx) as z:
        names = set(z.namelist())
        for name, _, part in sheets(xlsx):
            rels = posixpath.join(posixpath.dirname(part), "_rels", posixpath.basename(part) + ".rels")
            if rels in names and any(r.get("Type", "").endswith("/drawing")
                                     for r in ET.fromstring(z.read(rels)) if r.tag == NS_REL + "Relationship"):
                found.add(name)
    return found


def tile_rects(width, height, tile_pt=TILE_PT, ratio=TILE_RATIO):
    """Grid of tiles over a page, row by row from the top-left: [(row, col, (x0, y0, x1, y1))], 1-based.
    Tiles are tile_pt wide (a narrower page: one column of its own width) and ratio x that high; edge tiles are shorter."""
    tw = min(width, tile_pt)
    th = tw * ratio
    out, r, y = [], 1, 0.0
    while y < height - 1e-6:
        c, x = 1, 0.0
        while x < width - 1e-6:
            out.append((r, c, (x, y, min(x + tw, width), min(y + th, height))))
            c, x = c + 1, x + tw
        r, y = r + 1, y + th
    return out


def is_blank(samples, ink_share=0.002):
    """True when almost every pixel of a greyscale sample is white (a tile with nothing on it)."""
    if not samples:
        return True
    return sum(1 for b in samples if b < 245) / len(samples) < ink_share


def pick_tiles(rects, blank, cap):
    """The first `cap` non-blank tiles (blank(tile) -> bool) and whether more non-blank ones were left out."""
    keep = []
    for r in rects:
        if blank(r):
            continue
        if len(keep) == cap:
            return keep, True
        keep.append(r)
    return keep, False


def is_chartsheet(part):
    return part.startswith("xl/chartsheets/")


def cap_for(has_chart):
    return MAX_CHART_TILES if has_chart else MAX_PLAIN_TILES


def first_texts(xlsx, names):
    """{tab: its first text cell (top-left 60 x 20), or None}; the workbook is opened once."""
    import openpyxl
    out = {}
    wb = openpyxl.load_workbook(xlsx, read_only=True, data_only=True)
    try:
        for name in names:
            out[name] = None
            for row in wb[name].iter_rows(max_row=60, max_col=20):
                for c in row:
                    if out[name] is None and isinstance(c.value, str) and len(c.value.strip()) > 3:
                        out[name] = c.value.strip()
                if out[name]:
                    break
    finally:
        wb.close()
    return out


def _on_page(text, page_text):
    """Is the cell text on the page? Case and whitespace are ignored. A cell wider than its column is clipped at one or
    both ends when printed (a centred title, or a long note cut at the column edge), so the match is either the 12
    characters after the first 3, or the inside of one of the first three words (5+ letters, first and last dropped)."""
    norm = lambda t: " ".join(t.upper().split())
    t, pt = norm(text), norm(page_text)
    if t[3:15].strip() in pt:
        return True
    return any(w[1:-1] in pt for w in t.split()[:3] if len(w) >= 5)


def _clear(out):
    """Remove what an earlier run wrote here (only *.png, index.json, index.md)."""
    for f in os.listdir(out):
        if f.endswith(".png") or f in ("index.json", "index.md"):
            os.remove(os.path.join(out, f))


def render(values, out):
    """LibreOffice prints EVERY sheet, hidden ones too, one page each in workbook order. Pages are mapped to all sheets
    by order; hidden sheets are then left out of the index and the PNGs (the analyst reads what the PM can see)."""
    import fitz
    import lo
    os.makedirs(out, exist_ok=True)
    _clear(out)
    allsheets = sheets(values)
    charts = chart_tabs(values)
    texts = first_texts(values, [n for n, _, part in allsheets if not is_chartsheet(part)])
    pdf = lo.render_pdf(values, out)
    index, notes = [], []
    empty = dict(tile=None, row=None, col=None, png=None, truncated=False)
    try:
        doc = fitz.open(pdf)
        if len(doc) != len(allsheets):
            notes.append(f"PDF has {len(doc)} pages for {len(allsheets)} tabs; mapped by order")
        for page_no, (tab, state, part) in enumerate(allsheets, start=1):
            if state != "visible":
                continue
            base = {"tab": tab, "page": page_no, "has_chart": tab in charts or is_chartsheet(part)}
            try:
                if page_no > len(doc):
                    index.append(dict(base, **empty, note="missing from the PDF"))
                    continue
                if is_chartsheet(part):
                    index.append(dict(base, **empty, note="chartsheet: not rendered by LibreOffice"))
                    continue
                page = doc[page_no - 1]
                first = texts.get(tab)
                if first and not _on_page(first, page.get_text()):
                    notes.append(f"tab {tab}: its first text '{first[:25]}' was not found on page {page_no}; mapping by order may be off")
                w, h = page.rect.width, page.rect.height

                def blank(tile, page=page, w=w):
                    z = 160 / min(w, TILE_PT)
                    pix = page.get_pixmap(matrix=fitz.Matrix(z, z), clip=fitz.Rect(*tile[2]), colorspace=fitz.csGRAY)
                    return is_blank(pix.samples)
                keep, truncated = pick_tiles(tile_rects(w, h), blank, cap_for(base["has_chart"]))
                entries = []
                for t, (row, col, r) in enumerate(keep, start=1):
                    z = TILE_PX / min(w, TILE_PT)
                    png = f"{re.sub(r'[^A-Za-z0-9]+', '_', tab).strip('_')}_p{page_no}_r{row}c{col}.png"
                    page.get_pixmap(matrix=fitz.Matrix(z, z), clip=fitz.Rect(*r)).save(os.path.join(out, png))
                    entries.append(dict(base, tile=t, row=row, col=col, png=png, truncated=truncated))
                index += entries or [dict(base, **empty, note="blank tab")]
            except Exception as e:  # e.g. a page too large for MuPDF: say so, keep going
                index.append(dict(base, **empty, note=f"could not render: {e}"))
        doc.close()
    finally:
        if os.path.exists(pdf):
            os.remove(pdf)
    with open(os.path.join(out, "index.json"), "w") as f:
        json.dump(index, f, indent=1)
    write_md(index, notes, out)
    return index


def write_md(index, notes, out):
    tabs = {}
    for e in index:
        tabs.setdefault(e["tab"], []).append(e)
    order = sorted(tabs, key=lambda t: (not tabs[t][0]["has_chart"], tabs[t][0]["page"]))
    lines = ["# Tab pictures", "", "Tabs with a chart or image first. Each PNG is one tile of the tab, row by row from the top-left (r = grid row, c = grid column).", ""]
    for t in order:
        es = tabs[t]
        files = [e["png"] for e in es if e["png"]]
        tag = "chart" if es[0]["has_chart"] else "no chart"
        extra = " (more below was left out: only the first tiles are kept)" if any(e["truncated"] for e in es) else ""
        note = "; ".join(e["note"] for e in es if e.get("note"))
        lines.append(f"- {t} ({tag}): {', '.join(files) if files else 'no picture'}{extra}{' - ' + note if note else ''}")
    if notes:
        lines += ["", "Problems:"] + [f"- {n}" for n in notes]
    with open(os.path.join(out, "index.md"), "w") as f:
        f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--values", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    t0 = time.time()
    idx = render(a.values, a.out)
    print(f"{sum(1 for e in idx if e['png'])} pictures in {time.time() - t0:.0f}s -> {a.out}")
