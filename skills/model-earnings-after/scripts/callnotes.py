"""The Call Notes tab: one column per quarter (newest at B), topic rows, near-verbatim points with file:line notes.
read() takes the tab as it is; merge() puts this quarter's column in; written() is the record of what we wrote;
write() replaces the whole tab (it is ours: the cells and notes the user typed are kept by merge(), their
formatting is not)."""
import re

import openpyxl

from tabkit import BLACK, RED, W, _move_after
from xlsx import CT, XML_BAD, comments_parts

TAB = "Call Notes"
AFTER = "Earnings"
FIXED_TOP = ["Guidance (near-term)", "Long-term targets"]
FIXED_BOTTOM = ["Margins and costs", "Capital allocation"] + [f"Q&A theme {i}" for i in range(1, 6)] + \
    ["Tone", "Read-throughs mentioned"]
HEADER, DATE_LABEL, FILE_LABEL = "Topic", "Call date", "Transcript"
HEAD_ROW, DATE_ROW, FILE_ROW, FIRST_TOPIC_ROW = 4, 5, 6, 8          # where write() puts them; read() finds them by label
DASH = "—"
SEP = " • "
CAP = 32000                                                         # Excel holds 32,767 characters a cell
CUT = " … (cut: see the after-print note)"
EMPTY = {"order": [], "head": {}, "cells": {}, "topics": [], "notes": {}, "dropped": []}
NO_HEADER = "the Call Notes tab's header row is gone; put 'Topic' back in column A or delete the tab, then rerun"


def topics(drivers):
    """The tab's topic rows in order: the fixed top rows, one 'Driver: <name>' per forecast-plan driver, the rest."""
    return FIXED_TOP + [f"Driver: {d}" for d in drivers] + FIXED_BOTTOM


def clean(t):
    """Text as the tab holds it: one line ending (\\n), no characters XML 1.0 forbids, at most CAP characters."""
    t = XML_BAD.sub("", str(t).replace("\r\n", "\n").replace("\r", "\n"))
    return t if len(t) <= CAP else t[:CAP - len(CUT)] + CUT


def _s(v):
    if hasattr(v, "date") and hasattr(v, "isoformat"):        # a date Excel turned the text into
        return (v.date() if hasattr(v, "hour") else v).isoformat()
    return None if v is None else str(v)


def _empty():
    return {k: (v.copy() if hasattr(v, "copy") else v) for k, v in EMPTY.items()}


def _col(k):
    return openpyxl.utils.get_column_letter(k)


def read(path):
    """The tab as it is now: {order, head {q: {date, file}}, cells {(q, topic): text}, topics, notes {(q, topic):
    comment text}, dropped [{ref, text}]}; all empty if there is no tab. Rows are found by their column-A labels
    (the user may have inserted rows); text outside the quarter columns and topic rows is listed in `dropped`, as
    the rebuild loses it. A tab with no 'Topic' header stops the run rather than lose its history."""
    wb = openpyxl.load_workbook(path)                         # not read_only: that mode skips the comments
    if TAB not in wb.sheetnames:
        wb.close()
        return _empty()
    ws = wb[TAB]
    g = {(c.row, c.column): c.value for row in ws.iter_rows() for c in row if c.value not in (None, "")}
    com = {(c.row, c.column): c.comment.text for row in ws.iter_rows() for c in row if c.comment}
    wb.close()
    a = {r: str(v).strip() for (r, c), v in g.items() if c == 1}
    hr = next((r for r in sorted(a) if a[r] == HEADER), None)
    if hr is None:
        raise SystemExit(NO_HEADER)
    blank = next(r for r in range(hr + 1, max(a) + 2) if r not in a)
    lab = {a[r]: r for r in range(hr + 1, blank)}
    dr, fr = lab.get(DATE_LABEL), lab.get(FILE_LABEL)
    rows = sorted(r for r in a if r > blank)
    cols = sorted(c for (r, c) in g if r == hr and c > 1)
    order = [_s(g[(hr, c)]) for c in cols]
    tops = [_s(g[(r, 1)]) for r in rows]
    head = {q: {"date": _s(g.get((dr, c))), "file": _s(g.get((fr, c)))} for q, c in zip(order, cols)}
    cells = {(q, t): _s(g[(r, c)]) for q, c in zip(order, cols) for r, t in zip(rows, tops) if (r, c) in g}
    notes = {(q, t): com[(r, c)] for q, c in zip(order, cols) for r, t in zip(rows, tops) if (r, c) in com}
    kept = {(r, c) for c in cols for r in [hr, dr, fr] + rows}
    dropped = [{"ref": f"{_col(c)}{r}", "text": _s(v)} for (r, c), v in sorted(g.items())
               if c > 1 and r > hr and (r, c) not in kept]
    return {"order": order, "head": head, "cells": cells, "topics": tops, "notes": notes, "dropped": dropped}


def text(points):
    return clean(SEP.join(p["text"] for p in points or []))


def anchors(points):
    return clean("; ".join(p["anchor"] for p in points or []))


def merge(old, quarter, head, notes, tops, written):
    """This quarter's column into the tab read() found. notes = {topic: [{text, anchor}]}; written = {quarter:
    {topic: text, or None for a cell that was the user's}} from the last build (None: no record).
    Older quarters keep their cells and notes exactly ('—' for a topic new this run). The current quarter's cell is
    the user's when the tab already has this quarter and the cell differs from what our last build wrote there (no
    record: when it is non-empty and differs from the agent's new text), or was the user's before.
    A new quarter goes in at B; a rerun keeps the quarter's column where it is.
    Returns (grid, {(quarter, topic)} the user's cells, kept with their notes). grid["renamed_or_retired"] lists
    old topics this run neither lists nor has points for (renamed or dropped: the run warns)."""
    old = {**_empty(), **(old or {})}
    order = list(old["order"]) if quarter in old["order"] else [quarter] + list(old["order"])
    allt = list(tops) + [t for t in old["topics"] if t not in tops]
    cells, kept, users = {}, {}, set()
    for q in order:
        if q == quarter:
            continue
        for t in allt:
            if (q, t) in old["cells"]:
                cells[(q, t)] = clean(old["cells"][(q, t)])
            else:
                cells[(q, t)] = "" if t in old["topics"] else DASH
            if (q, t) in old["notes"]:
                kept[(q, t)] = clean(old["notes"][(q, t)])
    had = quarter in old["order"]
    rec = (written or {}).get(quarter)
    for t in allt:
        mine = text(notes.get(t))
        cur = clean(old["cells"].get((quarter, t), "")) if had else ""
        if not had:
            theirs = False
        elif rec is not None:
            # ownership is permanent: a cell the user cleared stays blank on every rerun
            theirs = (t in rec and rec[t] is None) or cur != clean(rec.get(t) or "")
        else:
            theirs = cur != "" and cur != mine
        cells[(quarter, t)] = cur if theirs else mine
        if theirs:
            users.add((quarter, t))
            if (quarter, t) in old["notes"]:
                kept[(quarter, t)] = clean(old["notes"][(quarter, t)])
    gone = [t for t in old["topics"] if t not in tops and not notes.get(t)]
    return {"order": order, "current": quarter, "head": {**old["head"], quarter: head}, "cells": cells,
            "topics": allt, "notes": kept, "renamed_or_retired": gone}, users


def written(grid, quarter, users=(), earlier=None):
    """{quarter: {topic: text we wrote, or None for the user's cell}} for call_notes_written.next.json; the earlier
    quarters' records in `earlier` are kept."""
    mine = {t: (None if (quarter, t) in users else grid["cells"].get((quarter, t), "")) for t in grid["topics"]}
    return {**{q: r for q, r in (earlier or {}).items() if q != quarter}, quarter: mine}


def lay_out(st, grid, notes, ticker, unverified=()):
    """The tab's cells (a W). Each current-quarter cell holding the agent's text gets a note with its anchors (red
    text and a note starting "UNVERIFIED:" for a topic in unverified, whose quote or figures failed the check);
    every other cell keeps the note it had (grid["notes"])."""
    w = W(st)
    w.text("A1", f"{ticker} call notes (model-earnings-after): one column per quarter, newest first", b=True, sz=14)
    w.text("A2", "Each column is one earnings call, newest at B; read a row across to see how the story shifted. "
                 "A cell holds near-verbatim lines from the call joined by •; its note gives file:line. "
                 f"{DASH} = not tracked that quarter. Text you type in this quarter's column is kept on a rerun.",
           i=True)
    w.text(f"A{HEAD_ROW}", HEADER, b=True)
    w.text(f"A{DATE_ROW}", DATE_LABEL, b=True)
    w.text(f"A{FILE_ROW}", FILE_LABEL, b=True)
    cur = grid.get("current")
    for k, q in enumerate(grid["order"]):
        c = _col(k + 2)
        h = grid["head"].get(q) or {}
        w.text(f"{c}{HEAD_ROW}", clean(q), b=True)
        for row, key in ((DATE_ROW, "date"), (FILE_ROW, "file")):
            if h.get(key):
                w.text(f"{c}{row}", clean(h[key]))
        for j, t in enumerate(grid["topics"]):
            v = clean(grid["cells"].get((q, t), ""))
            ref = f"{c}{FIRST_TOPIC_ROW + j}"
            pts = notes.get(t) or []
            ours = q == cur and pts and v == text(pts)
            bad = ours and t in unverified
            if ours:
                w.notes[ref] = clean(("UNVERIFIED: " if bad else "") + anchors(pts))
            elif (q, t) in grid.get("notes", {}):
                w.notes[ref] = clean(grid["notes"][(q, t)])
            if v != "":
                w.text(ref, v, color=RED if bad else BLACK, wrap=True)
    for j, t in enumerate(grid["topics"]):
        w.text(f"A{FIRST_TOPIC_ROW + j}", clean(t), wrap=True)
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


def write(pkg, st, grid, notes, ticker, unverified=()):
    """Replace the tab whole (with its comments and VML), right after the Earnings tab. Returns the sheet part.
    The caller renders st into xl/styles.xml and saves pkg."""
    if TAB in [s[0] for s in pkg.sheets()]:
        pkg.remove_sheet(TAB)
    w = lay_out(st, grid, notes, ticker, unverified)
    part = pkg.add_sheet(TAB, "")
    _move_after(pkg, TAB, AFTER)        # put back after Earnings every run, even if the user moved it (none: last)
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
