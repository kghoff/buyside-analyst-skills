"""Write a forecast plan into a COPY of the user's model (MOD tab), on the raw XML (xlsx.py says why not openpyxl).

usage: python3 build.py --model TICKER_model.xlsx --plan forecast_plan.json --out OUT.xlsx   (prints the JSON report)

1. new_rows: insert each line (+ its analysis rows) at the end of its `after` section, history linked (green) to
   its `history` row if it has one (a new driver or check row with no past stays blank in history columns; its
   number format comes from `format`, else `unit` "%" -> 0.0%). A seasonal row without a 'seasonality' row gets one under its analysis rows.
2. rows: methods.cells_for per plan entry; blue / green / black fonts on a copy of the row's own history style
   (same number format); a note with the plan's `source` on the first typed cell of each driver row.
2b. Analysis rows under every plan line (% yoy, % of sales ...) get the user's history formula carried into forecast cells
   the plan did not write (empty or typed; typed ones are reported as replaced_stale).
3. Refuses (writes nothing) if any cell lands outside the forecast columns, except the new rows themselves.
4. Typed numbers in forecast columns of rows the plan does not touch are reported (stale_cells), never deleted."""
import argparse
import json
import os
import re
import sys
import tempfile

import openpyxl
from openpyxl.formula.translate import Translator

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from methods import cells_for                                         # noqa: E402
from modmap import ANALYSIS, ModMap                                    # noqa: E402
from xledit import _insert_before_first, insert_rows, set_cells, unshare        # noqa: E402
from xlsx import CT, RT, Styles, colnum, comments_parts, esc, relpath_of, resolve, unesc  # noqa: E402

TAB = "MOD"
PLAN_NOTE = "Plan: "                 # prefix of the build's own notes: the only notes a rerun may rewrite
RGB = {"blue": "FF0000FF", "green": "FF008000", "black": "FF000000"}
AFTER_LEGACY = ("legacyDrawingHF", "picture", "oleObjects", "controls", "webPublishItems", "tableParts", "extLst")


def _part(pkg):
    return next(p for name, _, _, p in pkg.sheets() if name == TAB)


def _remap(pkg):
    """ModMap of the package as it stands (rows move on every insert)."""
    fd, tmp = tempfile.mkstemp(suffix=".xlsx")
    os.close(fd)
    try:
        pkg.save(tmp)
        return ModMap(tmp), _colab(tmp)
    finally:
        os.remove(tmp)


def _colab(path):
    ws = openpyxl.load_workbook(path, read_only=True)[TAB]
    return [(i, r[0], r[1]) for i, r in enumerate(ws.iter_rows(min_row=1, max_col=2, values_only=True), start=1)]


def _cell_attr(xml, ref, attr):
    m = re.search(rf'<c r="{ref}"([^>]*?)/?>', xml)
    a = m and re.search(rf'\b{attr}="([^"]*)"', m.group(1))
    return a.group(1) if a else None


def _row_style(xml, m, row):
    """s= of the newest styled history cell in `row` (the user's current number format for that line), or None."""
    for p in reversed(m.order):
        if not p.endswith("E"):
            s = _cell_attr(xml, f"{m.col(p)}{row}", "s")
            if s is not None:
                return int(s)
    return None


def _style(st, xml, m, row, color, label="", src=None, fmts=None):
    s = _row_style(xml, m, (src or {}).get(row, row))
    fmt = (fmts or {}).get(row)                       # a format the plan states wins over the inserted row's General
    if s is not None:
        return st.refmt(st.recolor(s, RGB[color]), fmt) if fmt else st.recolor(s, RGB[color])
    if fmt:
        return st.xf(RGB[color], fmt)
    pct = label.startswith("%") or label == "seasonality"
    return st.xf(RGB[color], "0.0%" if pct else "#,##0.0")


def _section_end(colab, section):
    """Row to insert at: just below the last labelled row of `section` (before any spacer and the next title)."""
    start = next((i for i, a, _ in colab if a and str(a).strip() == section), None)
    if start is None:
        raise KeyError(f"no MOD section '{section}'")
    last = start
    for i, a, b in colab:
        if i <= start:
            continue
        if a:
            break
        if b:
            last = i
    return last + 1


def _add_section(pkg, colab, title, after, like):
    """A new section: a blank spacer row and a title row (column A) at the end of section `after`, every cell styled
    like the title row of section `like` (so it looks like the user's other section titles)."""
    at = _section_end(colab, after)
    while any(i == at and (a or b) for i, a, b in colab):      # past the spacer rows of `after`
        at += 1
    insert_rows(pkg, TAB, at, 2)
    part = _part(pkg)
    xml = pkg.text(part)
    src = next(i for i, a, _ in colab if a and str(a).strip() == like)
    src = src + 2 if src >= at else src
    row = re.search(rf'<row r="{src}"[^>]*?(?:/>|>(.*?)</row>)', xml, re.S)
    cells = {}
    for cm in re.finditer(r'<c r="([A-Z]+)\d+"([^>]*?)(?:/>|>.*?</c>)', (row.group(1) or "") if row else "", re.S):
        s = re.search(r'\bs="(\d+)"', cm.group(2))
        cells[f"{cm.group(1)}{at + 1}"] = ("e", None, s.group(1) if s else "0")
    s_a = cells.get(f"A{at + 1}", ("e", None, "0"))[2]
    cells[f"A{at + 1}"] = ("s", title, s_a)
    xml, _ = set_cells(xml, cells, replace=True)
    pkg.put(part, xml)
    return at + 1


def _insert(pkg, at, labels):
    """Insert len(labels) rows at `at`; labels: [(col B text, col C text or None)], styled like the row above."""
    insert_rows(pkg, TAB, at, len(labels))
    part = _part(pkg)
    xml = pkg.text(part)
    src = at - 1                                       # an ordinary labelled row above, never a section title (whose
    while src > 1 and not (_cell_attr(xml, f"B{src}", "s") and re.search(rf'<c r="B{src}"[^>]*?(?:t="s"|t="inlineStr")', xml)
                           and not re.search(rf'<c r="A{src}"[^>]*?(?:t="s"|t="inlineStr")', xml)):
        src -= 1                                       # white bold label on navy would spread to every new row)
    sb = _cell_attr(xml, f"B{src}", "s") or "0"
    sc = _cell_attr(xml, f"C{src}", "s") or "0"
    cells = {}
    for k, (b, c) in enumerate(labels):
        cells[f"B{at + k}"] = ("s", b, sb)
        if c:
            cells[f"C{at + k}"] = ("s", c, sc)
    xml, _ = set_cells(xml, cells, replace=True)
    pkg.put(part, xml)


def _add_notes(pkg, part, notes, prefix=PLAN_NOTE):
    """Notes on MOD: append to its comments part (a note already on that cell is replaced), or create one. Only a
    note starting with `prefix` (the skill's own) is rewritten; on the user's note the text is appended."""
    if not notes:
        return
    rels = {t: resolve(part, g) for _, (t, g) in pkg.rels(relpath_of(part)).items()}
    if RT["comments"] in rels and RT["vml"] in rels:
        cpart, vpart = rels[RT["comments"]], rels[RT["vml"]]
        cx = pkg.text(cpart)
        notes = dict(notes)
        for ref in list(notes):
            old = re.search(rf'<comment ref="{ref}"[^>]*>.*?</comment>', cx, re.S)
            if not old:
                continue
            text = "".join(unesc(t) for t in re.findall(r"<t\b[^>]*>(.*?)</t>", old.group(0), re.S))
            if text.startswith(prefix):               # the skill's own note: rewrite it
                cx = cx[:old.start()] + cx[old.end():]
                continue
            # The user's note: keep it, (re)append the plan's source as its own run
            c = re.sub(r"<r>(?:(?!</r>).)*?<t\b[^>]*>\n\n" + re.escape(prefix) + r".*?</t></r>", "", old.group(0), flags=re.S)
            c = re.sub(r"<text>(<t\b[^>]*>.*?</t>)", r"<text><r>\1</r>", c, flags=re.S)
            c = c.replace("</text>", f'<r><t xml:space="preserve">{esc(chr(10) * 2 + notes.pop(ref))}</t></r></text>')
            cx = cx[:old.start()] + c + cx[old.end():]
        cx = cx.replace("<commentList/>", "<commentList></commentList>")
        add = "".join(f'<comment ref="{r}" authorId="0"><text><r><rPr><sz val="10"/><rFont val="Tahoma"/></rPr>'
                      f'<t xml:space="preserve">{esc(t)}</t></r></text></comment>' for r, t in notes.items())
        pkg.put(cpart, cx.replace("</commentList>", add + "</commentList>"))
        vml = pkg.text(vpart)
        rc = [(int(re.search(r"\d+", r).group(0)) - 1, colnum(re.match(r"[A-Z]+", r).group(0)) - 1) for r in notes]
        for row, col in rc:                         # drop the old shape of a replaced note
            vml = re.sub(rf"<v:shape\b(?:(?!</v:shape>).)*?<x:Row>{row}</x:Row>\s*<x:Column>{col}</x:Column>.*?</v:shape>",
                         "", vml, flags=re.S)
        others = {int(x) for p, data in pkg.parts.items() if p.endswith(".vml") and p != vpart
                  for d in re.findall(rb'<\w+:idmap\b[^>]*?\bdata="([\d,\s]+)"', data) for x in re.findall(rb"\d+", d)}
        vml = _vml_ns(vml)
        vml, new_ids = _alloc_ids(vml, len(rc), others)
        shapes = ""
        for k, (row, col) in enumerate(rc):
            shapes += (f'<v:shape id="_x0000_s{new_ids[k]}" type="#_x0000_t202" style="position:absolute;margin-left:59.25pt;'
                       'margin-top:1.5pt;width:240pt;height:80pt;z-index:1;visibility:hidden" fillcolor="#ffffe1" o:insetmode="auto">'
                       '<v:fill color2="#ffffe1"/><v:shadow on="t" color="black" obscured="t"/><v:path o:connecttype="none"/>'
                       '<v:textbox style="mso-direction-alt:auto"><div style="text-align:left"/></v:textbox>'
                       f'<x:ClientData ObjectType="Note"><x:MoveWithCells/><x:SizeWithCells/><x:Anchor>{col + 1}, 15, {row}, 2, '
                       f'{col + 5}, 15, {row + 5}, 16</x:Anchor><x:AutoFill>False</x:AutoFill><x:Row>{row}</x:Row>'
                       f'<x:Column>{col}</x:Column></x:ClientData></v:shape>')
        if 'id="_x0000_t202"' not in vml:
            shapes = ('<v:shapetype id="_x0000_t202" coordsize="21600,21600" o:spt="202" path="m,l,21600r21600,l21600,xe">'
                      '<v:stroke joinstyle="miter"/><v:path gradientshapeok="t" o:connecttype="rect"/></v:shapetype>' + shapes)
        pkg.put(vpart, vml.replace("</xml>", shapes + "</xml>"))
        return
    pkg.content_default("vml", "application/vnd.openxmlformats-officedocument.vmlDrawing")
    ids = [int(x) for p, data in pkg.parts.items() if p.endswith(".vml")
           for d in re.findall(rb'<\w+:idmap\b[^>]*?\bdata="([\d,\s]+)"', data) for x in re.findall(rb"\d+", d)]
    cn, vn = pkg.free("xl/comments{}.xml"), pkg.free("xl/drawings/vmlDrawing{}.vml")
    cx, vml = comments_parts(notes, max(ids + [0]) + 1)
    pkg.put(f"xl/comments{cn}.xml", cx)
    pkg.put(f"xl/drawings/vmlDrawing{vn}.vml", vml)
    lrid = pkg.attach(part, "vml", f"xl/drawings/vmlDrawing{vn}.vml")
    pkg.attach(part, "comments", f"xl/comments{cn}.xml", CT["comments"])
    pkg.put(part, _insert_before_first(pkg.text(part), AFTER_LEGACY, f'<legacyDrawing r:id="{lrid}"/>'))


VML_NS = {"v": "urn:schemas-microsoft-com:vml", "o": "urn:schemas-microsoft-com:office:office",
          "x": "urn:schemas-microsoft-com:office:excel"}


def _vml_ns(vml):
    """Declare v: o: x: on the root (openpyxl writes its VML with ns0: prefixes and a bare <xml>)."""
    root = re.search(r"<xml\b[^>]*>", vml).group(0)
    add = "".join(f' xmlns:{p}="{u}"' for p, u in VML_NS.items() if f"xmlns:{p}=" not in root)
    return vml.replace(root, root[:-1] + add + ">", 1) if add else vml


def _alloc_ids(vml, count, others):
    """`count` new shape ids for a VML drawing, each inside a block listed in its <o:idmap data> (block n holds ids
    1024*n+1 .. 1024*n+1023). Blocks are added to the list as needed, never one another .vml part uses (`others`).
    Returns (vml with the updated idmap, ids)."""
    m = re.search(r'(<\w+:idmap\b[^>]*?\bdata=")([\d,\s]*)(")', vml)
    blocks = [int(x) for x in re.findall(r"\d+", m.group(2))] if m else []
    have = [int(i) for i in re.findall(r'id="_x0000_s(\d+)"', vml)]
    cand = max(have) + 1 if have else (1024 * blocks[0] + 1 if blocks else None)
    if cand is None:
        b = next(n for n in range(1, 10 ** 6) if n not in others)
        blocks, cand = [b], 1024 * b + 1
    ids = []
    while len(ids) < count:
        b, off = divmod(cand, 1024)
        if off == 0:                                   # 1024*n is in no block
            cand += 1
            continue
        if b not in blocks:
            if b in others:                            # jump to the next block nobody uses
                b = next(n for n in range(b + 1, 10 ** 6) if n not in others and n not in blocks)
                cand = 1024 * b + 1
            blocks.append(b)
        ids.append(cand)
        cand += 1
    data = ",".join(str(b) for b in blocks)
    if m:
        vml = vml[:m.start()] + m.group(1) + data + m.group(3) + vml[m.end():]
    else:
        vml = re.sub(r"(<xml\b[^>]*>)", r'\1<o:shapelayout v:ext="edit"><o:idmap v:ext="edit" data="' + data
                     + '"/></o:shapelayout>', vml, count=1)
    return vml, ids


def _cell(xml, ref):
    """(formula or None, has a typed value) of one cell in the sheet XML."""
    c = re.search(rf'<c r="{ref}"([^>]*?)(?:/>|>(.*?)</c>)', xml, re.S)
    if not c:
        return None, False
    body = c.group(2) or ""
    f = re.search(r"<f\b[^>]*>(.*?)</f>", body, re.S)
    if f:
        return unesc(f.group(1)), False
    return None, "<v>" in body and not re.search(r'\bt="(?!n")', c.group(1))


def _fill_analysis(xml, m, plan, planned, st):
    """Forecast cells of the analysis rows under each plan line (% yoy, % of sales, bps yoy ...) that the plan did not
    write and that are empty or typed: The user's formula from the last actual quarter (quarter cells) or last actual FY
    (FY cells), translated. Returns (cells, typed refs replaced, typed refs left because history has no formula)."""
    hist = [p for p in m.order if not p.endswith("E")]
    last_q = next((p for p in reversed(hist) if m.is_q(p)), None)
    last_y = next((p for p in reversed(hist) if re.match(r"\d{4}$", p)), None)
    out, replaced, left = {}, [], []
    lines = sorted({m.row(e["key"]) for e in plan.get("rows", [])})
    for line in lines:
        r = line + 1
        while r in m.analysis_rows:
            for p in m.forecast_quarters() + m.forecast_years():
                ref = f"{m.col(p)}{r}"
                if ref in planned:
                    continue
                f, typed = _cell(xml, ref)
                if f is not None:
                    continue
                srcp = last_q if m.is_q(p) else last_y
                hf = _cell(xml, f"{m.col(srcp)}{r}")[0] if srcp else None
                if hf is None:
                    if typed:
                        left.append(ref)
                    continue
                t = Translator("=" + hf, origin=f"{m.col(srcp)}{r}").translate_formula(ref)[1:]
                out[ref] = ("f", t, _style(st, xml, m, r, "black", m.analysis_rows[r]))
                if typed:
                    replaced.append(ref)
            r += 1
    return out, replaced, left


def _ensure_r_ns(xml):
    root = re.search(r"<worksheet\b[^>]*>", xml).group(0)
    if "xmlns:r=" in root:
        return xml
    return xml.replace(root, root[:-1] + ' xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">', 1)


ROW_FIELDS = {"key", "method", "kind", "source", "rates", "values", "of", "sign", "rate_row", "annual_growth", "shares",
              "template", "templates", "fy_template", "history_values", "unit", "history_template", "history_years"}
NEW_ROW_FIELDS = {"key", "after", "unit", "history", "analysis", "format", "history_values", "source"}


def unknown_fields(plan):
    """Plan fields the build would ignore: a typo or an unsupported field must stop the build, never vanish silently."""
    out = [f"rows: '{e.get('key')}' has unknown field(s) {sorted(set(e) - ROW_FIELDS)}"
           for e in plan.get("rows", []) if set(e) - ROW_FIELDS]
    out += [f"new_rows: '{e.get('key')}' has unknown field(s) {sorted(set(e) - NEW_ROW_FIELDS)}"
            for e in plan.get("new_rows", []) if set(e) - NEW_ROW_FIELDS]
    return out


def build(model, plan, out):
    from xlsx import Package
    bad = unknown_fields(plan)
    kept = {k["key"] for k in plan.get("keep", [])}
    bad += [f"'{e['key']}' is under keep (the user's row): the plan may not write it" for e in plan.get("rows", []) if e["key"] in kept]
    if bad:
        raise ValueError("forecast plan: " + "; ".join(bad))
    pkg = Package(model)
    m, colab = _remap(pkg)
    inserted, new_rows = [], set()

    # 0. driver sections (convention: company-specific builds, then IS / working capital / cash flow & capital drivers)
    prev = "REVENUE BUILD"
    for ds in plan.get("driver_sections", []):
        if not any(a and str(a).strip() == ds["title"] for _, a, _ in colab):
            at = _add_section(pkg, colab, ds["title"], ds.get("after", prev), "REVENUE BUILD")
            inserted.append({"key": ds["title"], "at": at - 1, "n": 2})
            m, colab = _remap(pkg)
        prev = ds["title"]

    # 1. new rows (labels only; links once rows have stopped moving)
    for nr in plan.get("new_rows", []):
        if nr["key"] in m.keys:                    # rerun: the row is already there
            continue
        label = nr["key"].split(" | ", 1)[1]
        if label.lower() in ANALYSIS:
            raise ValueError(f"new row label '{label}' is an analysis row name")
        at = _section_end(colab, nr["after"])
        _insert(pkg, at, [(label, nr.get("unit"))] + [(a, None) for a in nr.get("analysis", [])])
        inserted.append({"key": nr["key"], "at": at, "n": 1 + len(nr.get("analysis", []))})
        m, colab = _remap(pkg)
    for e in plan.get("rows", []):
        if e["method"] != "seasonal":
            continue
        try:
            m.analysis(e["key"], "seasonality")
        except KeyError:
            r = m.row(e["key"]) + 1
            while r in m.analysis_rows:
                r += 1
            _insert(pkg, r, [("seasonality", None)])
            inserted.append({"key": e["key"] + " | seasonality", "at": r, "n": 1})
            m, colab = _remap(pkg)
    for nr in plan.get("new_rows", []):
        r = m.row(nr["key"])
        new_rows.add(r)
        while r + 1 in m.analysis_rows:
            r += 1
            new_rows.add(r)
    for e in plan.get("rows", []):
        if e["method"] == "seasonal" and any(i["key"] == e["key"] + " | seasonality" for i in inserted):
            new_rows.add(m.analysis(e["key"], "seasonality"))

    part = _part(pkg)
    xml = pkg.text(part)
    st = Styles(pkg.text("xl/styles.xml"))
    cells, typed, notes, written_rows = {}, {}, {}, set()

    # 2. history links of the new rows; a new line takes its look from its history row (same on every rerun)
    src = {m.row(nr["key"]): m.row(nr["history"]) for nr in plan.get("new_rows", []) if nr.get("history")}
    fmts = {m.row(nr["key"]): nr.get("format") or ("0.0%" if nr.get("unit") == "%" else None)
            for nr in plan.get("new_rows", []) if not nr.get("history")}
    for nr in plan.get("new_rows", []):
        if not nr.get("history"):
            continue
        r, h = m.row(nr["key"]), m.row(nr["history"])
        for p in m.order:
            if not p.endswith("E"):
                c = m.col(p)
                cells[f"{c}{r}"] = ("f", f"{c}{h}", _style(st, xml, m, h, "green"))

    # 3. the plan's forecast cells
    allowed = {m.col(p) for p in m.forecast_quarters() + m.forecast_years()}
    hist = {nr["key"]: nr["history_values"] for nr in plan.get("new_rows", []) if nr.get("history_values")}
    planned = {e["key"] for e in plan.get("rows", [])}
    src_of = {nr["key"]: nr.get("source", "") for nr in plan.get("new_rows", [])}
    extra = [{"key": k, "method": "annual", "kind": "annual", "values": {}, "source": src_of[k]}   # a figure only in
             for k in hist if k not in planned]                                                 # the year it describes
    for e in plan.get("rows", []) + extra:
        if e["key"] in hist:                               # a starting point may be given on the new_rows entry too
            e = dict(e, history_values={**hist[e["key"]], **e.get("history_values", {})})
        got = cells_for(m, e)
        mine = m.row(e["key"]) in new_rows                 # a row the plan adds has no history to protect
        bad = sorted(ref for ref in got if re.match(r"[A-Z]+", ref).group(0) not in allowed
                     and not (mine and ("history_values" in e or "history_template" in e)))
        if bad:
            raise ValueError(f"{e['key']}: refusing to write outside the forecast columns: {', '.join(bad)}")
        first = {}
        for ref, (kind, val, color) in got.items():
            row = int(re.search(r"\d+", ref).group(0))
            lab = m.analysis_rows.get(row, "")
            cells[ref] = (kind, val, _style(st, xml, m, row, color, lab, src, fmts))
            written_rows.add(row)
            if color == "blue":
                typed[ref] = e["key"]
                c = colnum(re.match(r"[A-Z]+", ref).group(0))
                if row not in first or c < first[row][0]:
                    first[row] = (c, ref)
        written_rows.add(m.row(e["key"]))
        if e.get("source"):
            for _, ref in first.values():
                notes[ref] = PLAN_NOTE + e["source"]

    xml = unshare(xml, TAB, TAB)       # a replaced shared-formula master must not orphan its children

    # 3b. analysis rows under every plan line: The user's own history formula carried into the forecast columns
    fill, replaced, keep_stale = _fill_analysis(xml, m, plan, cells, st)
    cells.update(fill)
    xml, _ = set_cells(xml, cells, replace=True)

    # 4. typed numbers left in forecast columns of rows the plan does not touch (the user's experiments): report only
    stale = []
    for rm in re.finditer(r'<row r="(\d+)"[^>]*?(?:/>|>(.*?)</row>)', xml, re.S):
        r = int(rm.group(1))
        if r in written_rows or r in new_rows or not rm.group(2):
            continue
        for cm in re.finditer(r'<c r="([A-Z]+)(\d+)"([^>]*?)(?:/>|>(.*?)</c>)', rm.group(2), re.S):
            body, attrs = cm.group(4) or "", cm.group(3)
            if cm.group(1) in allowed and "<v>" in body and "<f" not in body and not re.search(r'\bt="(?!n")', attrs):
                stale.append(f"{cm.group(1)}{cm.group(2)}")
    stale += [r for r in keep_stale if r not in stale]

    pkg.put(part, _ensure_r_ns(xml))
    _add_notes(pkg, part, notes)
    pkg.put("xl/styles.xml", st.render())
    pkg.finish()
    pkg.save(out)
    import modfill; modfill.fix(out, out)   # the user's MOD fill convention (quarters plain, years grey), every save
    import notebox; notebox.fix(out, out)   # note boxes open readable (none squashed next to spacer / hidden columns), every save
    return {"out": out, "rows_written": [e["key"] for e in plan.get("rows", [])], "cells_written": len(cells),
            "typed_inputs": len(typed), "notes": len(notes), "rows_inserted": inserted, "stale_cells": stale,
            "analysis_filled": len(fill), "replaced_stale": replaced}


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--model", required=True)
    ap.add_argument("--plan", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    if os.path.abspath(a.out) == os.path.abspath(a.model):
        sys.exit("--out must be a new file, not the model itself")
    plan = json.load(open(a.plan, encoding="utf-8"))
    print(json.dumps(build(a.model, plan, a.out), indent=1))


if __name__ == "__main__":
    main()
