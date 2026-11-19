"""The Call Notes tab: one column per quarter (newest at B), topic rows, near-verbatim points with file:line notes.
read() takes the tab as it is; merge() puts this quarter's column in; written() is the record of what we wrote;
write() replaces the whole tab (it is ours: the cells the user typed are kept by merge(), their formatting is not)."""
import re

import openpyxl

from tabkit import W, _move_after
from xlsx import CT, comments_parts

TAB = "Call Notes"
AFTER = "Earnings"
FIXED_TOP = ["Guidance (near-term)", "Long-term targets"]
FIXED_BOTTOM = ["Margins and costs", "Capital allocation"] + [f"Q&A theme {i}" for i in range(1, 6)] + \
    ["Tone", "Read-throughs mentioned"]
HEAD_ROW, DATE_ROW, FILE_ROW, FIRST_TOPIC_ROW = 4, 5, 6, 8
DASH = "—"
SEP = " • "
EMPTY = {"order": [], "head": {}, "cells": {}, "topics": []}


def topics(drivers):
    """The tab's topic rows in order: the fixed top rows, one 'Driver: <name>' per forecast-plan driver, the rest."""
    return FIXED_TOP + [f"Driver: {d}" for d in drivers] + FIXED_BOTTOM


def _s(v):
    if hasattr(v, "date") and hasattr(v, "isoformat"):        # a date Excel turned the text into
        return (v.date() if hasattr(v, "hour") else v).isoformat()
    return None if v is None else str(v)


def read(path):
    """The tab as it is now: {order, head {q: {date, file}}, cells {(q, topic): text}, topics}; all empty if absent."""
    wb = openpyxl.load_workbook(path, read_only=True)
    if TAB not in wb.sheetnames:
        wb.close()
        return {k: (v.copy() if hasattr(v, "copy") else v) for k, v in EMPTY.items()}
    ws = wb[TAB]
    ws.reset_dimensions()
    g = {(c.row, c.column): c.value for row in ws.iter_rows() for c in row
         if getattr(c, "value", None) not in (None, "")}
    wb.close()
    cols = sorted(c for (r, c) in g if r == HEAD_ROW and c > 1)
    order = [_s(g[(HEAD_ROW, c)]) for c in cols]
    rows = sorted(r for (r, c) in g if c == 1 and r >= FIRST_TOPIC_ROW)
    tops = [_s(g[(r, 1)]) for r in rows]
    head = {q: {"date": _s(g.get((DATE_ROW, c))), "file": _s(g.get((FILE_ROW, c)))} for q, c in zip(order, cols)}
    cells = {(q, t): _s(g[(r, c)]) for q, c in zip(order, cols) for r, t in zip(rows, tops) if (r, c) in g}
    return {"order": order, "head": head, "cells": cells, "topics": tops}


def text(points):
    return SEP.join(p["text"] for p in points or [])


def merge(old, quarter, head, notes, tops, written):
    """This quarter's column into the tab read() found. notes = {topic: [{text, anchor}]}; written = {quarter:
    {topic: text, or None for a cell that was the user's}} from the last build (None: no record).
    Older quarters keep their cells exactly ('—' for a topic new this run). The current quarter's cell is the
    user's when the tab already has this quarter and the cell differs from what our last build wrote there (no
    record: when it is non-empty and differs from the agent's new text), or was the user's before.
    Returns (grid, {(quarter, topic)} the user's cells, which are kept)."""
    old = old or EMPTY
    order = [quarter] + [q for q in old["order"] if q != quarter]
    allt = list(tops) + [t for t in old["topics"] if t not in tops]
    cells, users = {}, set()
    for q in order[1:]:
        for t in allt:
            if (q, t) in old["cells"]:
                cells[(q, t)] = old["cells"][(q, t)]
            else:
                cells[(q, t)] = "" if t in old["topics"] else DASH
    had = quarter in old["order"]
    rec = (written or {}).get(quarter)
    for t in allt:
        mine = text(notes.get(t))
        cur = old["cells"].get((quarter, t), "") if had else ""
        if not had:
            theirs = False
        elif rec is not None:
            theirs = (t in rec and rec[t] is None) or cur != (rec.get(t) or "")
        else:
            theirs = cur != "" and cur != mine
        cells[(quarter, t)] = cur if theirs else mine
        if theirs:
            users.add((quarter, t))
    return {"order": order, "head": {**old["head"], quarter: head}, "cells": cells, "topics": allt}, users


def written(grid, quarter, users=(), earlier=None):
    """{quarter: {topic: text we wrote, or None for the user's cell}} for call_notes_written.next.json; the earlier
    quarters' records in `earlier` are kept."""
    mine = {t: (None if (quarter, t) in users else grid["cells"].get((quarter, t), "")) for t in grid["topics"]}
    return {**{q: r for q, r in (earlier or {}).items() if q != quarter}, quarter: mine}


def _col(k):
    return openpyxl.utils.get_column_letter(k)


def lay_out(st, grid, notes, ticker):
    """The tab's cells (a W). A note with the anchors goes on each current-quarter cell that holds the agent's text."""
    w = W(st)
    w.text("A1", f"{ticker} call notes (model-earnings-after): one column per quarter, newest first", b=True, sz=14)
    w.text("A2", "Each column is one earnings call, newest at B; read a row across to see how the story shifted. "
                 "A cell holds near-verbatim lines from the call joined by •; its note gives file:line. "
                 f"{DASH} = not tracked that quarter. Text you type in this quarter's column is kept on a rerun.",
           i=True)
    w.text(f"A{HEAD_ROW}", "Topic", b=True)
    w.text(f"A{DATE_ROW}", "Call date", b=True)
    w.text(f"A{FILE_ROW}", "Transcript", b=True)
    cur = grid["order"][0] if grid["order"] else None
    for k, q in enumerate(grid["order"]):
        c = _col(k + 2)
        h = grid["head"].get(q) or {}
        w.text(f"{c}{HEAD_ROW}", q, b=True)
        for row, key in ((DATE_ROW, "date"), (FILE_ROW, "file")):
            if h.get(key):
                w.text(f"{c}{row}", h[key])
        for j, t in enumerate(grid["topics"]):
            v = grid["cells"].get((q, t), "")
            if v == "":
                continue
            ref = f"{c}{FIRST_TOPIC_ROW + j}"
            w.text(ref, v, wrap=True)
            pts = notes.get(t) or []
            if q == cur and pts and v == text(pts):
                w.notes[ref] = "; ".join(p["anchor"] for p in pts)
    for j, t in enumerate(grid["topics"]):
        w.text(f"A{FIRST_TOPIC_ROW + j}", t, wrap=True)
    w.sh.widths = {1: 28, **{k + 2: 60 for k in range(max(1, len(grid["order"])))}}
    w.sh.freeze = f"B{FIRST_TOPIC_ROW}"
    return w


def _free_block(pkg):
    """The first shape-id block no VML drawing in the workbook uses (by idmap or by shape id)."""
    vmls = [d for p, d in pkg.parts.items() if p.endswith(".vml")]
    blocks = {int(b) for d in vmls for m in re.findall(rb'<\w+:idmap\b[^>]*?data="([\d,\s]*)"', d)
              for b in re.findall(rb"\d+", m)}
    blocks |= {int(x) // 1024 for d in vmls for x in re.findall(rb"_x0000_s(\d+)", d)}
    return max(blocks | {0}) + 1


def write(pkg, st, grid, notes, ticker):
    """Replace the tab whole (with its comments and VML), right after the Earnings tab. Returns the sheet part.
    The caller renders st into xl/styles.xml and saves pkg."""
    if TAB in [s[0] for s in pkg.sheets()]:
        pkg.remove_sheet(TAB)
    w = lay_out(st, grid, notes, ticker)
    part = pkg.add_sheet(TAB, "")
    _move_after(pkg, TAB, AFTER)
    lrid = None
    if w.notes:
        pkg.content_default("vml", "application/vnd.openxmlformats-officedocument.vmlDrawing")
        cn, vn = pkg.free("xl/comments{}.xml"), pkg.free("xl/drawings/vmlDrawing{}.vml")
        cx, vml = comments_parts(w.notes, _free_block(pkg))
        pkg.put(f"xl/comments{cn}.xml", cx)
        pkg.put(f"xl/drawings/vmlDrawing{vn}.vml", vml)
        lrid = pkg.attach(part, "vml", f"xl/drawings/vmlDrawing{vn}.vml")
        pkg.attach(part, "comments", f"xl/comments{cn}.xml", CT["comments"])
    pkg.put(part, w.sh.xml(None, lrid))
    return part
