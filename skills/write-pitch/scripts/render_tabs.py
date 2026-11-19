"""Turn the recalculated values copy of the model into PNG pictures of every tab, so the analyst can see the charts.

usage: python3 render_tabs.py --values <recalculated copy> --out <work>/tabs

Writes tabs/index.json, tabs/index.md and the PNGs. index.json is a list with one entry per PNG:
{"tab", "page", "tile", "png" (relative to the tabs folder), "has_chart", "truncated"}; a tab that produced no
non-blank tile gets one entry with "png": null (and "note" when something went wrong).
- LibreOffice prints each visible tab as ONE tall PDF page (hidden tabs are skipped), in tab order.
- A tab with thousands of rows (daily prices) would be one useless giant picture, so each page is cut into tiles of
  full width and height 1.3 x width, rendered about 1600 px wide. Blank tiles are skipped; at most 8 non-blank
  tiles per tab (the top holds the charts and summary); "truncated": true when more non-blank tiles were left out.
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
TILE_PX = 1600
MAX_TILES = 8
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


def tile_rects(width, height, ratio=TILE_RATIO):
    """Every (x0, y0, x1, y1) tile of a page: full width, height ratio x width, the last one shorter."""
    step = width * ratio
    rects, y = [], 0.0
    while y < height - 1e-6:
        rects.append((0, y, width, min(y + step, height)))
        y += step
    return rects


def is_blank(samples, ink_share=0.002):
    """True when almost every pixel of a greyscale sample is white (a tile with nothing on it)."""
    if not samples:
        return True
    return sum(1 for b in samples if b < 245) / len(samples) < ink_share


def pick_tiles(rects, blank, cap=MAX_TILES):
    """The first `cap` non-blank rects (blank(rect) -> bool) and whether more non-blank ones were left out."""
    keep = []
    for r in rects:
        if blank(r):
            continue
        if len(keep) == cap:
            return keep, True
        keep.append(r)
    return keep, False


def _first_text(xlsx, name):
    import openpyxl
    wb = openpyxl.load_workbook(xlsx, read_only=True, data_only=True)
    try:
        for row in wb[name].iter_rows(max_row=60, max_col=20):
            for c in row:
                if isinstance(c.value, str) and len(c.value.strip()) > 3:
                    return c.value.strip()
    finally:
        wb.close()
    return None


def render(values, out):
    import fitz
    import lo
    os.makedirs(out, exist_ok=True)
    visible = [n for n, st, _ in sheets(values) if st == "visible"]
    charts = chart_tabs(values)
    pdf = lo.render_pdf(values, out)
    index, notes = [], []
    try:
        doc = fitz.open(pdf)
        if len(doc) != len(visible):
            notes.append(f"PDF has {len(doc)} pages for {len(visible)} visible tabs; mapped by order up to the shorter")
        for page_no, tab in enumerate(visible[:len(doc)], start=1):
            page = doc[page_no - 1]
            base = {"tab": tab, "page": page_no, "has_chart": tab in charts}
            first = _first_text(values, tab)
            if first and first[:25] not in page.get_text():
                notes.append(f"tab {tab}: its first text '{first[:25]}' was not found on page {page_no}; mapping by order may be off")
            w, h = page.rect.width, page.rect.height

            def blank(r, page=page):
                z = 160 / w
                pix = page.get_pixmap(matrix=fitz.Matrix(z, z), clip=fitz.Rect(*r), colorspace=fitz.csGRAY)
                return is_blank(pix.samples)
            try:
                keep, truncated = pick_tiles(tile_rects(w, h), blank)
                entries = []
                for t, r in enumerate(keep, start=1):
                    z = TILE_PX / w
                    png = f"{re.sub(r'[^A-Za-z0-9]+', '_', tab).strip('_')}_p{page_no}_t{t}.png"
                    page.get_pixmap(matrix=fitz.Matrix(z, z), clip=fitz.Rect(*r)).save(os.path.join(out, png))
                    entries.append(dict(base, tile=t, png=png, truncated=truncated))
                index += entries or [dict(base, tile=None, png=None, truncated=False, note="blank tab")]
            except Exception as e:  # a page too large for MuPDF: say so, keep going
                index.append(dict(base, tile=None, png=None, truncated=False, note=f"could not render: {e}"))
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
    lines = ["# Tab pictures", "", "Tabs with a chart or image first. Each PNG is one slice of the tab, top to bottom.", ""]
    for t in order:
        es = tabs[t]
        files = [e["png"] for e in es if e["png"]]
        tag = "chart" if es[0]["has_chart"] else "no chart"
        extra = " (more below was left out: only the top slices are kept)" if any(e["truncated"] for e in es) else ""
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
