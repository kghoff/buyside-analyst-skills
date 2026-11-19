"""Turn a LibreOffice-recalculated copy of the model into digest.md: every text cell, every cell note, the numbers that
matter, and a summary (not a row dump) of huge numeric blocks such as daily price history.

usage: python3 digest.py --values <recalculated copy> --out <work>/digest.md [--json <work>/digest.json]

Per tab, in workbook order: Text, Notes, Numbers, Bulk blocks.
- Bulk rule (any tab but MOD): split the used range into vertical blocks at fully empty rows. In a block of more than
  200 rows, a column with more than 200 non-empty cells that are at least 80% numeric (dates count) is not listed cell
  by cell; it gets one line: first (row) value, last (row) value, min, max, latest percentile. A column mixing dates
  and numbers gets one line per type. In such a block a column with more than 200 text cells gets one line too (count,
  distinct, rows, first, last, up to 30 distinct values). Every other cell, in the block or outside, is still listed,
  including stray text in a bulk column (only its header, the first text, is folded into the summary line).
- Numbers, ordinary tab: one line per row, `r12 (<row label>): B <header>=1.2, C <header>=0.3`; the cell is the column
  letter plus the row. Row label = first text in columns A-C of that row. Column header = the nearest text above the
  cell in the same column within its block (omitted when there is none).
- Numbers, MOD tab (the model's main sheet; period headers in row 2 from column D, labels in column B): one table per
  section (column A name) with a `columns: 2025=H, ...` line above it, the period headers once as the table header
  (repeated every 40 rows) and one row per labelled row `| r12 label | v | ... |`; the periods are the annual
  columns, the last 8 actual quarters and every forecast quarter. MOD skips the bulk rule: its
  columns are already filtered, and a long block of lines with 40 period columns would otherwise look like bulk.
- Notes: every cell comment as `A1 (<row label>) = <value>: <note>`. On MOD, notes on period columns that were dropped
  are left out, and the count is stated.
- MOD period headers that match no rule (e.g. a date) are named in a `skipped columns:` line, with the count of older
  actual quarters dropped. Hidden sheets are marked `(hidden)`.
- Excel error cells (#N/A ...) are never headers or labels and are not listed one by one: one `errors:` line under
  Text gives each contiguous run per column as a range.
The file must be a values copy (data_only), so formulas show their results."""
import argparse
import bisect
import datetime
import json
import re

import openpyxl
from openpyxl.utils import get_column_letter as L

ERRORS = {"#N/A", "#DIV/0!", "#VALUE!", "#REF!", "#NAME?", "#NUM!", "#NULL!"}
BULK_ROWS, BULK_SHARE, MOD_QUARTERS = 200, 0.8, 8
QTR = re.compile(r"^Q[1-4] \d\d(E?)$")
YEAR = re.compile(r"^(FY ?)?(\d{2}|\d{4})E?$")


def is_num(v):
    return isinstance(v, (int, float, datetime.date)) and not isinstance(v, bool)


def fmt(v):
    if isinstance(v, datetime.datetime):
        return v.date().isoformat() if v.time() == datetime.time(0) else v.isoformat(sep=" ")
    if isinstance(v, datetime.date):
        return v.isoformat()
    if isinstance(v, float):
        if v == int(v) and abs(v) < 1e15:
            return str(int(v))
        if abs(v) < 0.001:
            return f"{v:.3g}"
        return f"{round(v, 4):.4f}".rstrip("0").rstrip(".")
    return str(v)


def read_sheet(ws):
    """rows: {row: [(col, value)]} for non-empty cells; notes: [(row, col, value, text)]."""
    rows, notes = {}, []
    for row in ws.iter_rows():
        for c in row:
            v = c.value
            if isinstance(v, str):
                v = v.strip() or None
            if v is not None:
                rows.setdefault(c.row, []).append((c.column, v))
            if c.comment is not None:
                notes.append((c.row, c.column, v, " ".join(c.comment.text.split())))
    return rows, notes


def row_label(cells):
    return next((v for c, v in cells if c <= 3 and isinstance(v, str) and v not in ERRORS), "")


def blocks_of(rows):
    out, cur = [], []
    for r in sorted(rows):
        if cur and r != cur[-1] + 1:
            out.append(cur)
            cur = []
        cur.append(r)
    if cur:
        out.append(cur)
    return out


def dkey(v):
    return v.date() if isinstance(v, datetime.datetime) else v


def stat_line(vals, header, c, block):
    keys = sorted(dkey(v) for _, v in vals)
    last = vals[-1][1]
    return {"kind": "numeric", "block": f"rows {block[0]}-{block[-1]}", "column": L(c), "header": header,
            "first_row": vals[0][0], "first": fmt(vals[0][1]), "last_row": vals[-1][0], "last": fmt(last),
            "min": fmt(keys[0]), "max": fmt(keys[-1]),
            "latest_percentile": round(100 * bisect.bisect_right(keys, dkey(last)) / len(keys))}


def bulk_columns(block, rows):
    """(numeric bulk columns, text bulk columns) of a block; none unless the block has more than 200 rows."""
    if len(block) <= BULK_ROWS:
        return set(), set()
    n, t = {}, {}
    for r in block:
        for c, v in rows[r]:
            n[c] = n.get(c, 0) + 1
            if not is_num(v):
                t[c] = t.get(c, 0) + 1
    num = {c for c, k in n.items() if k > BULK_ROWS and (k - t.get(c, 0)) >= BULK_SHARE * k}
    return num, ({c for c, k in t.items() if k > BULK_ROWS and c not in num} if num else set())


def summarize(block, rows, num_cols, txt_cols):
    cols, heads = {}, {}
    for r in block:
        for c, v in rows[r]:
            if c in num_cols and is_num(v):
                cols.setdefault(c, []).append((r, v))
            elif c in num_cols | txt_cols and not is_num(v) and v not in ERRORS:
                if c not in heads:
                    heads[c] = str(v)
                elif c in txt_cols:
                    cols.setdefault(c, []).append((r, str(v)))
    out = []
    for c in sorted(cols):
        h = heads.get(c, L(c))
        if c in txt_cols:
            vals = cols[c]
            distinct = list(dict.fromkeys(v for _, v in vals))
            out.append({"kind": "text", "block": f"rows {block[0]}-{block[-1]}", "column": L(c), "header": h,
                        "count": len(vals), "distinct": len(distinct), "first_row": vals[0][0],
                        "last_row": vals[-1][0], "first": vals[0][1], "last": vals[-1][1], "values": distinct[:30]})
            continue
        dates = [x for x in cols[c] if isinstance(x[1], datetime.date)]
        nums = [x for x in cols[c] if not isinstance(x[1], datetime.date)]
        for kind, vals in (("dates", dates), ("numbers", nums)):
            if vals:
                out.append(stat_line(vals, h + (f" ({kind})" if dates and nums else ""), c, block))
    return out


def mod_columns(rows):
    """Columns kept on MOD: annual, last 8 actual quarters, all forecast quarters.
    Also the unrecognised headers (named, so the drop is visible) and how many older actual quarters were dropped."""
    heads = {c: (v.strip() if isinstance(v, str) else fmt(v)) for c, v in rows.get(2, []) if c >= 4}
    actual = [c for c, h in heads.items() if QTR.match(h) and not QTR.match(h).group(1)]
    keep = {c for c, h in heads.items() if YEAR.match(h) and not QTR.match(h)}
    keep |= set(actual[-MOD_QUARTERS:])
    keep |= {c for c, h in heads.items() if QTR.match(h) and QTR.match(h).group(1)}
    skipped = [f"{L(c)}={h}" for c, h in heads.items() if not (YEAR.match(h) or QTR.match(h))]
    return keep, heads, skipped, max(len(actual) - MOD_QUARTERS, 0)


def error_runs(errs):
    """errs: {col: [(row, error)]} -> 'AB5:AB8 #N/A (4 cells)' per contiguous run of one error in one column."""
    out = []
    for c in sorted(errs):
        run = []
        for r, e in errs[c] + [(None, None)]:
            if run and (r is None or e != run[-1][1] or r != run[-1][0] + 1):
                a, b = f"{L(c)}{run[0][0]}", f"{L(c)}{run[-1][0]}"
                out.append(f"{a}{':' + b if len(run) > 1 else ''} {run[0][1]} ({len(run)} cell{'s' if len(run) > 1 else ''})")
                run = []
            if r is not None:
                run.append((r, e))
    return out


def digest_sheet(ws):
    rows, notes = read_sheet(ws)
    d = {"hidden": ws.sheet_state != "visible", "text": {}, "errors": [], "notes": [], "numbers": [], "bulk": []}
    errs = {}
    is_mod = ws.title == "MOD"
    keep, mod_heads = set(), {}
    if is_mod:
        keep, mod_heads, d["skipped_columns"], d["old_quarters_dropped"] = mod_columns(rows)
        d["mod_columns"] = [(L(c), mod_heads[c]) for c in sorted(keep)]
    section = ""
    for block in blocks_of(rows):
        num_cols, txt_cols = (set(), set()) if is_mod else bulk_columns(block, rows)
        d["bulk"] += summarize(block, rows, num_cols, txt_cols) if num_cols else []
        heads, folded = {}, set()
        for r in block:
            label = row_label(rows[r])
            if is_mod:                                       # the label is column B; fall back to A-C when B is empty
                label = next((x for c, x in rows[r] if c == 2 and isinstance(x, str)), label)
            cells = []
            for c, v in rows[r]:
                if isinstance(v, str) and v in ERRORS:
                    errs.setdefault(c, []).append((r, v))
                    continue
                if c in txt_cols and not is_num(v):
                    continue
                if c in num_cols:
                    if is_num(v):
                        continue
                    if c not in folded:                      # the column header, folded into the summary line
                        folded.add(c)
                        continue
                if not is_num(v):
                    d["text"][f"{L(c)}{r}"] = str(v)
                    heads[c] = str(v)
                    if is_mod and c == 1:
                        section = str(v)
                elif is_mod:
                    if label and r != 2 and c in keep:
                        cells.append({"col": L(c), "header": mod_heads[c], "value": fmt(v)})
                else:
                    cells.append({"col": L(c), "header": heads.get(c, ""), "value": fmt(v)})
            if cells:
                d["numbers"].append({"section": section, "row": r, "label": label, "cells": cells})
    d["errors"] = error_runs(errs)
    d["notes_omitted"] = 0
    for r, c, v, text in notes:
        if is_mod and c > 3 and c not in keep:
            d["notes_omitted"] += 1
            continue
        d["notes"].append({"cell": f"{L(c)}{r}", "label": row_label(rows.get(r, [])),
                           "value": "" if v is None else fmt(v), "note": text})
    return d


def mod_tables(d):
    """One table per MOD section: kept period headers once (repeated every 40 rows), one row per labelled row."""
    cols = d["mod_columns"]
    heads = "| row | " + " | ".join(h for _, h in cols) + " |\n|" + "---|" * (len(cols) + 1)
    out, group = [], []
    for n in d["numbers"] + [None]:
        if n is None or (group and n["section"] != group[0]["section"]):
            out += ["", f"{group[0]['section'] or '(no section)'}", "columns: " + ", ".join(f"{h}={c}" for c, h in cols)]
            for i, g in enumerate(group):
                if i % 40 == 0:
                    out.append(heads)
                have = {x["col"]: x["value"] for x in g["cells"]}
                out.append(f"| r{g['row']} {g['label'].replace('|', chr(92) + '|')} | " + " | ".join(have.get(c, "") for c, _ in cols) + " |")
            group = []
        if n is not None:
            group.append(n)
    return out


def number_lines(d):
    out = []
    for n in d["numbers"]:
        cells = ", ".join(f"{c['col']}{' ' + c['header'] if c['header'] else ''}={c['value']}" for c in n["cells"])
        label = " (" + n["label"] + ")" if n["label"] else ""
        out.append(f"r{n['row']}{label}: {cells}")
    return out


def bulk_line(b):
    if b["kind"] == "text":
        return (f"col {b['column']} {b['header']}: {b['count']} text cells, {b['distinct']} distinct, "
                f"rows {b['first_row']}-{b['last_row']}; first: {b['first']}, last: {b['last']}; "
                f"values: {'; '.join(b['values'])} [{b['block']}]")
    return (f"{b['header']}: first ({b['first_row']}) {b['first']}, last ({b['last_row']}) {b['last']}, "
            f"min {b['min']}, max {b['max']}, latest percentile {b['latest_percentile']}% "
            f"[col {b['column']}, {b['block']}]")


def to_markdown(name, d):
    out = [f"## {name}{' (hidden)' if d['hidden'] else ''}", "", "### Text"]
    out += [f"{k}: {v}" for k, v in d["text"].items()]
    if d["errors"]:
        out.append("errors: " + ", ".join(d["errors"]))
    out += [] if d["text"] or d["errors"] else ["(none)"]
    out += ["", "### Notes"]
    out += [f"{n['cell']} ({n['label']}) = {n['value']}: {n['note']}" for n in d["notes"]] or ["(none)"]
    if d["notes_omitted"]:
        out.append(f"({d['notes_omitted']} notes on dropped period columns omitted)")
    out += ["", "### Numbers"]
    if "mod_columns" in d:
        out.append("skipped columns: " + (", ".join(d["skipped_columns"]) or "none")
                   + f"; older actual quarters dropped: {d['old_quarters_dropped']}")
    out += (mod_tables(d) if "mod_columns" in d and d["numbers"] else number_lines(d)) or ["(none)"]
    out += ["", "### Bulk blocks"]
    out += [bulk_line(b) for b in d["bulk"]] or ["(none)"]
    return "\n".join(out) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--values", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--json")
    a = ap.parse_args()
    wb = openpyxl.load_workbook(a.values, data_only=True)
    digest = {ws.title: digest_sheet(ws) for ws in wb.worksheets}
    with open(a.out, "w") as f:
        f.write("\n".join(to_markdown(n, d) for n, d in digest.items()))
    if a.json:
        with open(a.json, "w") as f:
            json.dump(digest, f, indent=1)


if __name__ == "__main__":
    main()
