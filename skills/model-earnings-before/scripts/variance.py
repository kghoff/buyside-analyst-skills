# skills/model-earnings-before/scripts/variance.py
"""The Consensus tab's variance table (model-consensus band 2) and the grid this skill writes into it, or onto the
Earnings tab when the user keeps their own.

inspect(model, written) -> status: 'skeleton' (model-consensus's empty block: fill without asking), 'ours' (every
cell in B-H is what this skill wrote last time: fill again), 'data' (the user typed something: ask), 'no_block' or
'missing' (no block / no Consensus tab: the grid goes on the Earnings tab).
grid_cells(ctx, rows): labels (B), consensus (C-E: revenue and EPS typed from the Consensus mean row, revenue growth
as a formula; margins, FCF and drivers blank, no free source) and internal (F-H: links to MOD). The variance
formulas (I-K) on the Consensus tab are model-consensus's and are never touched.

usage: python3 variance.py inspect --model M [--written W/variance_written.json]   (prints the status JSON)"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))   # run with python3 -I
import openpyxl  # noqa: E402
from openpyxl.formula.translate import Translator  # noqa: E402
from openpyxl.utils import get_column_letter as L  # noqa: E402

import earnmath as em  # noqa: E402
from xlsx import colnum, esc, unesc  # noqa: E402

TAB = "Consensus"
BAND = "2. VARIANCE"
DEFAULT = ["Revenue", "Revenue growth", "Gross margin", "Operating margin", "FCF", "EPS",
           "(key driver)", "(key driver)", "(key driver)"]
PCT_ROWS = ("Revenue growth", "Gross margin", "Operating margin")
CONS, INT = "CDE", "FGH"
PER = ("q", "fy", "fy1")
NOTE_COL = "L"
BLUE, BLACK, GREEN = "FF0000FF", "FF000000", "FF008000"
MONEY, EPSF, PCT = "#,##0.0", "$0.00", "0.0%"


def inspect(model, written=None):
    wb = openpyxl.load_workbook(model, read_only=True)            # formulas as written, not values
    if TAB not in wb.sheetnames:
        wb.close()
        return {"status": "missing"}
    g = {}                                                        # (row, col) -> value, by the cells' own coordinates
    for row in wb[TAB].iter_rows(min_row=1, max_col=12):
        for c in row:
            if getattr(c, "value", None) not in (None, ""):
                g[(c.row, c.column)] = c.value
    wb.close()
    a = sorted((r, str(v).strip()) for (r, c), v in g.items() if c == 1 and isinstance(v, str))
    band = next((r for r, t in a if t.startswith(BAND)), None)
    if band is None:
        return {"status": "no_block"}
    end = next((r for r, t in a if r > band and re.match(r"\d+\.", t)), max(r for r, _ in g) + 1)
    labels = [(r, g[(r, 2)]) for r in range(band + 2, end) if (r, 2) in g]
    cells = {f"{L(c)}{r}": v for (r, c), v in g.items() if band + 2 <= r < end and 2 <= c <= 8}
    info = {"band": band, "header": band + 1, "rows": [r for r, _ in labels], "labels": [x for _, x in labels],
            "heads": {L(c): g.get((band + 1, c)) for c in range(3, 12)}}
    filled = sorted((ref for ref in cells if not ref.startswith("B")), key=lambda r: (int(r[1:]), r[0]))
    if info["labels"] == DEFAULT and not filled:
        return {**info, "status": "skeleton", "filled": []}
    if written and cells and all(ref in written and written[ref] == v for ref, v in cells.items()):
        return {**info, "status": "ours", "filled": filled}
    return {**info, "status": "data", "filled": filled}


def grid_rows(ctx):
    return [(lab, lab in PCT_ROWS) for lab in DEFAULT[:6]] + [(d["name"], False) for d in ctx["mod"]["drivers"]]


def _r1(a, b):
    r = em.div(a, b)
    return r - 1 if r is not None else None


def grid_cells(ctx, rows):
    """({ref: (kind, content, expected, role, fmt)}, labels dropped for lack of rows). kind 's' / 'n' / 'f' (formula
    without '='); role label / typed / link / formula; expected None means #N/A."""
    M = ctx["mod"]
    cols, R, V = M["cols"], M["rows"], M["vals"]
    cons = (ctx.get("links") or {}).get("consensus") or {}
    spec = grid_rows(ctx)
    out = {}

    def mref(k, row):
        return f"MOD!${cols[k]}${row}" if cols.get(k) else None

    def mv(k, row):
        return (V.get(str(row)) or {}).get(k)

    rev_r = rows[0]
    for (lab, pct), r in zip(spec, rows):
        out[f"B{r}"] = ("s", lab, lab, "label", "General")
        if lab in ("Revenue", "EPS"):
            row, fmt, ck = (R["rev"], MONEY, "rev") if lab == "Revenue" else (R["eps"], EPSF, "eps")
            for cc, ic, k in zip(CONS, INT, PER):
                if f"{ck}_{k}" in cons:
                    out[f"{cc}{r}"] = ("n", cons[f"{ck}_{k}"]["value"], cons[f"{ck}_{k}"]["value"], "typed", fmt)
                if mref(k, row):
                    out[f"{ic}{r}"] = ("f", mref(k, row), mv(k, row), "link", fmt)
        elif lab == "Revenue growth":
            rv = R["rev"]
            for ic, k, base in zip(INT, PER, ("q_ly", "fy_ly", "fy")):
                if mref(k, rv) and mref(base, rv):
                    out[f"{ic}{r}"] = ("f", f"IFERROR({mref(k, rv)}/{mref(base, rv)}-1,NA())",
                                       _r1(mv(k, rv), mv(base, rv)), "formula", PCT)
            cv = {k: (cons.get(f"rev_{k}") or {}).get("value") for k in PER}
            if cv["q"] is not None and mref("q_ly", rv):
                out[f"C{r}"] = ("f", f"IFERROR(C{rev_r}/{mref('q_ly', rv)}-1,NA())", _r1(cv["q"], mv("q_ly", rv)),
                                "formula", PCT)
            if cv["fy"] is not None and mref("fy_ly", rv):
                out[f"D{r}"] = ("f", f"IFERROR(D{rev_r}/{mref('fy_ly', rv)}-1,NA())", _r1(cv["fy"], mv("fy_ly", rv)),
                                "formula", PCT)
            if cv["fy1"] is not None and cv["fy"] is not None:
                out[f"E{r}"] = ("f", f"IFERROR(E{rev_r}/D{rev_r}-1,NA())", _r1(cv["fy1"], cv["fy"]), "formula", PCT)
        elif lab in ("Gross margin", "Operating margin"):
            key = "gp" if lab == "Gross margin" else "oi"
            if key in R:
                for ic, k in zip(INT, PER):
                    if mref(k, R[key]):
                        out[f"{ic}{r}"] = ("f", f"IFERROR({mref(k, R[key])}/{mref(k, R['rev'])},NA())",
                                           em.div(mv(k, R[key]), mv(k, R["rev"])), "formula", PCT)
        else:                                                   # FCF and the drivers: ours only
            row = R.get("fcf") if lab == "FCF" else next(d["row"] for d in M["drivers"] if d["name"] == lab)
            if row:
                for ic, k in zip(INT, PER):
                    if mref(k, row):
                        out[f"{ic}{r}"] = ("f", mref(k, row), mv(k, row), "link", MONEY)
    return out, [lab for lab, _ in spec[len(rows):]]


def note_text(ctx):
    snap = ((ctx.get("links") or {}).get("consensus") or {}).get("snapshot") or "?"
    return (f"Filled by /model-earnings-before on {ctx['today']}: consensus (C-E) typed from this tab's Consensus mean "
            f"row (Yahoo snapshot {snap}); internal (F-H) links to MOD. Gross margin, operating margin, FCF and the "
            "key drivers have no free consensus, so C-E are blank there.")


def _has_content(c):
    return bool(re.search(r"<(v|f|is)\b", c))


def _cell_xml(ref, kind, val, st):
    if kind == "f":
        return f'<c r="{ref}" s="{st}"><f>{esc(val)}</f></c>'
    if kind == "s":
        return f'<c r="{ref}" s="{st}" t="inlineStr"><is><t xml:space="preserve">{esc(val)}</t></is></c>'
    return f'<c r="{ref}" s="{st}"><v>{val!r}</v></c>'


C_ELEM = re.compile(r'<c r="([A-Z]+\d+)"[^>]*?(?:/>|>.*?</c>)', re.S)
F_SHARED = re.compile(r'<f t="shared"([^>]*?)(?:/>|>(.*?)</f>)', re.S)


def unshare(xml, refs):
    """(Copied and adapted from research-filings xledit.unshare, Nov 2026.) Write out, cell by cell, every shared
    formula group whose master or children are among refs: overwriting a master would orphan its children (Excel's
    repair prompt). Cells outside refs keep the same formula, now plain."""
    masters, members = {}, {}
    for m in C_ELEM.finditer(xml):
        f = F_SHARED.search(m.group(0))
        if f:
            si = re.search(r'si="(\d+)"', f.group(1)).group(1)
            members.setdefault(si, set()).add(m.group(1))
            if f.group(2) is not None:
                masters[si] = (m.group(1), unesc(f.group(2)))
    todo = {si for si, cs in members.items() if cs & set(refs) and si in masters}
    if not todo:
        return xml

    def cell(m):
        c = m.group(0)
        f = F_SHARED.search(c)
        if not f:
            return c
        si = re.search(r'si="(\d+)"', f.group(1)).group(1)
        if si not in todo:
            return c
        origin, fx = masters[si]
        text = fx if m.group(1) == origin else Translator("=" + fx, origin=origin).translate_formula(m.group(1))[1:]
        return c[:f.start()] + f"<f>{esc(text)}</f>" + c[f.end():]
    return C_ELEM.sub(cell, xml)


def put_cells(xml, cells, force=False):
    """(Adapted from research-filings xledit.set_cells, Nov 2026.) cells: {'C22': (kind, value, style)}. A cell that
    already holds something is skipped and reported, unless force (the user chose to overwrite)."""
    skipped, by_row = [], {}
    xml = unshare(xml, cells)
    for ref, v in cells.items():
        m = re.match(r"([A-Z]+)(\d+)$", ref)
        by_row.setdefault(int(m.group(2)), []).append((colnum(m.group(1)), ref, v))
    sd = re.search(r"<sheetData\s*/>|<sheetData>(.*?)</sheetData>", xml, re.S)
    rows = {int(m.group(1)): m.group(0)
            for m in re.finditer(r'<row r="(\d+)"[^>]*?(?:/>|>.*?</row>)', sd.group(1) or "", re.S)}
    for r, items in by_row.items():
        row = rows.get(r, f'<row r="{r}"></row>')
        if row.endswith("/>"):
            row = row[:-2] + "></row>"
        head = re.sub(r'\s*spans="[^"]*"', "", row[:row.index(">") + 1])
        cs = {colnum(re.match(r'<c r="([A-Z]+)', c.group(0)).group(1)): c.group(0)
              for c in re.finditer(r'<c r="[A-Z]+\d+"[^>]*?(?:/>|>.*?</c>)', row, re.S)}
        for col, ref, (kind, val, st) in items:
            if col in cs and _has_content(cs[col]) and not force:
                skipped.append(ref)
                continue
            cs[col] = _cell_xml(ref, kind, val, st)
        rows[r] = head + "".join(cs[c] for c in sorted(cs)) + "</row>"
    body = "".join(rows[r] for r in sorted(rows))
    return xml[:sd.start()] + f"<sheetData>{body}</sheetData>" + xml[sd.end():], skipped


def fill(pkg, st, ctx, info, force):
    """Write the grid into the Consensus tab's block. Returns {part, written {ref: content as openpyxl reads it},
    expected {ref: value}, skipped, dropped}."""
    part = {s[0]: s for s in pkg.sheets()}[TAB][3]
    cells, dropped = grid_cells(ctx, info["rows"])
    color = {"label": BLACK, "typed": BLUE, "link": GREEN, "formula": BLACK}
    styles, xcells, written, expected = {}, {}, {}, {}
    for ref, (kind, content, exp, role, fmt) in cells.items():
        key = (color[role], fmt)
        if key not in styles:
            styles[key] = st.xf(color=key[0], fmt=key[1], sz=11)
        xcells[ref] = (kind, content, styles[key])
        written[ref] = "=" + content if kind == "f" else content
        if role != "label":
            expected[ref] = exp
    for r, lab in zip(info["rows"], info["labels"]):            # rows the grid has no label for stay as they were
        written.setdefault(f"B{r}", lab)
        if xcells.get(f"B{r}", (None, None))[1] == lab:         # already reads what we would write: leave it alone
            del xcells[f"B{r}"]
    nref = f"{NOTE_COL}{info['header']}"
    xcells[nref] = ("s", note_text(ctx), st.xf(color=BLACK, fmt="General", sz=11, i=True))
    ph = {f"B{r}" for r, lab in zip(info["rows"], info["labels"]) if lab == DEFAULT[-1]}   # "(key driver)" is
    xml, skipped = put_cells(pkg.text(part), {k: v for k, v in xcells.items() if k not in ph}, force=force)
    xml, _ = put_cells(xml, {k: v for k, v in xcells.items() if k in ph}, force=True)       # model-consensus's own
    pkg.put(part, xml)                                          # placeholder, not the user's words: name it
    return {"part": part, "written": written, "expected": expected, "skipped": skipped, "dropped": dropped}


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("cmd", choices=["inspect"])
    ap.add_argument("--model", required=True)
    ap.add_argument("--written")
    a = ap.parse_args()
    w = json.load(open(a.written)) if a.written and os.path.exists(a.written) else None
    print(json.dumps(inspect(a.model, w), indent=1, default=str))


if __name__ == "__main__":
    main()
