"""Turn a LibreOffice-recalculated copy of the model into digest.md: every text cell, every cell note, the numbers that
matter, and a summary (not a row dump) of huge numeric blocks such as daily price history.

usage: python3 digest.py --values <recalculated copy> --out <work>/digest.md [--json <work>/digest.json]

Per tab, in workbook order: Text, Notes, Numbers, Bulk blocks.
- Bulk rule (any tab): split the used range into vertical blocks at fully empty rows. A block of more than 200 rows
  whose cells are at least 80% numeric (dates count) is not listed cell by cell; each numeric column gets one line:
  first (row) value, last (row) value, min, max, latest percentile. Cells outside bulk blocks are still listed.
- Numbers, ordinary tab: one line per row, `r12 (<row label>): B <header>=1.2, C <header>=0.3`; the cell is the column
  letter plus the row. Row label = first text in columns A-C of that row. Column header = the nearest text above the
  cell in the same column within its block (omitted when there is none).
- Numbers, MOD tab (the model's main sheet; period headers in row 2 from column D, labels in column B): one table per
  section (column A name) with a `columns: 2025=H, ...` line above it, the period headers once as the table header
  (repeated every 40 rows) and one row per labelled row `| r12 label | v | ... |`; the periods are the annual
  columns, the last 8 actual quarters and every forecast quarter. MOD skips the bulk rule: its
  columns are already filtered, and a long block of lines with 40 period columns would otherwise look like bulk.
- Notes: every cell comment as `A1 (<row label>) = <value>: <note>`.
The file must be a values copy (data_only), so formulas show their results."""
import argparse
import bisect
import datetime
import json
import re

import openpyxl
from openpyxl.utils import get_column_letter as L

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
    return next((v for c, v in cells if c <= 3 and isinstance(v, str)), "")


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


def is_bulk(block, rows):
    if len(block) <= BULK_ROWS:
        return False
    cells = [v for r in block for _, v in rows[r]]
    return sum(is_num(v) for v in cells) >= BULK_SHARE * len(cells)


def summarize(block, rows):
    cols, heads = {}, {}
    for r in block:
        for c, v in rows[r]:
            if is_num(v):
                cols.setdefault(c, []).append((r, v))
            elif c not in heads:
                heads[c] = v
    out = []
    for c in sorted(cols):
        vals = cols[c]
        try:
            ordered = sorted(v for _, v in vals)
        except TypeError:                                    # dates mixed with numbers in one column
            continue
        last = vals[-1][1]
        pct = round(100 * bisect.bisect_right(ordered, last) / len(ordered))
        out.append({"block": f"rows {block[0]}-{block[-1]}", "column": L(c), "header": str(heads.get(c, L(c))),
                    "first_row": vals[0][0], "first": fmt(vals[0][1]), "last_row": vals[-1][0], "last": fmt(last),
                    "min": fmt(ordered[0]), "max": fmt(ordered[-1]), "latest_percentile": pct})
    return out


def mod_columns(rows):
    """Columns kept on MOD: annual, last 8 actual quarters, all forecast quarters."""
    heads = {c: str(v).strip() for c, v in rows.get(2, []) if c >= 4}
    actual = [c for c, h in heads.items() if QTR.match(h) and not QTR.match(h).group(1)]
    keep = set(c for c, h in heads.items() if YEAR.match(h) and not QTR.match(h))
    keep |= set(actual[-MOD_QUARTERS:])
    keep |= {c for c, h in heads.items() if QTR.match(h) and QTR.match(h).group(1)}
    return keep, heads


def digest_sheet(ws):
    rows, notes = read_sheet(ws)
    d = {"text": {}, "notes": [], "numbers": [], "bulk": []}
    is_mod = ws.title == "MOD"
    keep, mod_heads = mod_columns(rows) if is_mod else (set(), {})
    if is_mod:
        d["mod_columns"] = [(L(c), mod_heads[c]) for c in sorted(keep)]
    bulk_rows, section = set(), ""
    for block in blocks_of(rows):
        if not is_mod and is_bulk(block, rows):
            d["bulk"] += summarize(block, rows)
            bulk_rows.update(block)
            continue
        heads = {}
        for r in block:
            label = next((x for c, x in rows[r] if c == 2 and isinstance(x, str)), "") if is_mod else row_label(rows[r])
            cells = []
            for c, v in rows[r]:
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
    for r, c, v, text in notes:
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
                out.append(f"| r{g['row']} {g['label']} | " + " | ".join(have.get(c, "") for c, _ in cols) + " |")
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


def to_markdown(name, d):
    out = [f"## {name}", "", "### Text"]
    out += [f"{k}: {v}" for k, v in d["text"].items()] or ["(none)"]
    out += ["", "### Notes"]
    out += [f"{n['cell']} ({n['label']}) = {n['value']}: {n['note']}" for n in d["notes"]] or ["(none)"]
    out += ["", "### Numbers"]
    out += (mod_tables(d) if "mod_columns" in d and d["numbers"] else number_lines(d)) or ["(none)"]
    out += ["", "### Bulk blocks"]
    out += [f"{b['header']}: first ({b['first_row']}) {b['first']}, last ({b['last_row']}) {b['last']}, "
            f"min {b['min']}, max {b['max']}, latest percentile {b['latest_percentile']}% "
            f"[col {b['column']}, {b['block']}]" for b in d["bulk"]] or ["(none)"]
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
