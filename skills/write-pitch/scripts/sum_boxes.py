# skills/write-pitch/scripts/sum_boxes.py
"""Fill the SUM tab's yellow write-pitch boxes (Thesis Summary, Trading Plan, Valuation Thoughts, Buy price,
No-brainer price, Mgmt contact) from pitch_plan.json's sum_boxes, in a copy of the user's model.

usage: python3 sum_boxes.py --model M --plan pitch_plan.json --record <model dir>/_model_work/write-pitch/sum_written.json
                            --out <work>/out.xlsx
Prints JSON {"written", "kept", "skipped_null", "missing", "cells", "warnings"} and writes out.xlsx plus
sum_written.next.json next to --record (the skill renames it to sum_written.json once the copy-over succeeds).

Each box is found by its label on SUM (model-summary moves the boxes with its grid, so never by a fixed address); the
input cell sits at INPUT_OFFSET from the label. A box is written when it is empty or still holds what the last run
wrote (the record); anything else is the user's and is kept. null in the plan = leave the box alone. Prices go in as
numbers (numbers[key].value), text boxes as inline strings with every {key} replaced by numbers[key].shown; the
cell keeps its style (the yellow fill). Raw XML only: the SUM sheet part changes in those cells, workbook.xml gets
fullCalcOnLoad so SUM's formulas on the prices recalculate on open, and every other part is copied byte for byte.
calcChain.xml is left as it is: it lists formula cells, and no formula cell is added or removed."""
import argparse
import json
import math
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))   # run with python3 -I
import openpyxl  # noqa: E402

import common  # noqa: E402
from common import ILLEGAL  # noqa: E402
from fill import HOLDER, fill  # noqa: E402
from xlsx import Package, colname, colnum, esc  # noqa: E402

TAB = "SUM"
# label -> (columns, rows) from the label cell to the input cell. Copied from model-summary layout.INPUT_OFFSET
# (keep in sync; test_sum_boxes checks it): prices one column right of the label, text boxes one row below it.
INPUT_OFFSET = {"Buy price": (1, 0), "No-brainer price": (1, 0), "Mgmt contact": (0, 1), "Thesis Summary": (0, 1),
                "Trading Plan": (0, 1), "Valuation Thoughts": (0, 1)}
PRICES = ("Buy price", "No-brainer price")
CELL = re.compile(r"<c\b(?P<a>[^>]*?)(?:/>|>(?P<body>.*?)</c>)", re.S)
ROW = re.compile(r"<row\b(?P<a>[^>]*?)(?:/>|>(?P<body>.*?)</row>)", re.S)
CALCPR = re.compile(r"<calcPr\b(?P<a>[^>]*?)(?:/>|>\s*</calcPr>)")


def ref_of(c, r):
    return f"{colname(c)}{r}"


def split_ref(ref):
    m = re.match(r"([A-Z]+)(\d+)$", ref)
    return colnum(m.group(1)), int(m.group(2))


def empty(v):
    return v is None or (isinstance(v, str) and not v.strip())


def same(a, b):
    num = lambda x: isinstance(x, (int, float)) and not isinstance(x, bool)   # noqa: E731
    if num(a) and num(b):
        return abs(a - b) <= 1e-9 * max(1.0, abs(a), abs(b))
    return str(a).strip() == str(b).strip()


def find_boxes(model):
    """({label: (input ref, value now)}, warnings) from the SUM tab, found by label."""
    wb = openpyxl.load_workbook(model, read_only=True)
    try:
        if TAB not in wb.sheetnames:
            raise SystemExit("write-pitch: the model has no SUM tab. Run /model-summary first.")
        ws = wb[TAB]
        ws.reset_dimensions()          # a stale <dimension> would cut rows off and make a typed box read as empty
        g = {(r, c): v for r, row in enumerate(ws.iter_rows(values_only=True), 1)
             for c, v in enumerate(row, 1) if v is not None}
    finally:
        wb.close()
    found, warnings = {}, []
    for (r, c), v in sorted(g.items()):
        lab = v.strip() if isinstance(v, str) else None
        if lab not in INPUT_OFFSET:
            continue
        dc, dr = INPUT_OFFSET[lab]
        if lab in found:
            warnings.append(f"'{lab}' appears more than once on SUM; used the first ({found[lab][0]} is its box).")
            continue
        found[lab] = (ref_of(c + dc, r + dr), g.get((r + dr, c + dc)))
    return found, warnings


def wanted(label, text, numbers):
    """The value the plan asks for: a number for a price box, a string with {key} replaced for a text box."""
    for k in HOLDER.findall(text):
        if k not in numbers:
            raise SystemExit(f"write-pitch: sum_boxes['{label}'] uses {{{k}}}, which is not in numbers.")
    if label in PRICES:
        m = re.fullmatch(r"\s*\{(\w+)\}\s*", text)
        if not m:
            raise SystemExit(f"write-pitch: sum_boxes['{label}'] must be a single {{key}} (e.g. \"{{buy_price}}\"), "
                             f"got {text!r}.")
        v = numbers[m.group(1)]["value"]
        if not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(v):
            raise SystemExit(f"write-pitch: numbers['{m.group(1)}'].value is not a finite number ({v!r}); fix the "
                             "plan's number before filling SUM.")
        return v
    t = fill(text, numbers).replace("\r\n", "\n").replace("\r", "\n")
    if len(t) > common.EXCEL_CELL_MAX:
        raise SystemExit(f"write-pitch: sum_boxes['{label}'] is {len(t):,} characters with the numbers filled in; an "
                         f"Excel cell holds at most {common.EXCEL_CELL_MAX:,}. Shorten the plan's text.")
    if ILLEGAL.search(t):
        raise SystemExit(f"write-pitch: sum_boxes['{label}'] has control characters Excel cannot store: {t!r}.")
    if t.lstrip().startswith("="):
        raise SystemExit(f"write-pitch: sum_boxes['{label}'] starts with '=', which model-summary would turn into a "
                         "formula on its next rerun. Reword the plan's text so it does not start with '='.")
    return t


def cell_xml(ref, attrs, value):
    """A new <c> for ref keeping the old cell's style (s=); a number or an inline string."""
    s = re.search(r'\ss="[^"]*"', attrs or "")
    s = s.group(0) if s else ""
    if isinstance(value, str):
        return f'<c r="{ref}"{s} t="inlineStr"><is><t xml:space="preserve">{esc(value)}</t></is></c>'
    return f'<c r="{ref}"{s}><v>{value!r}</v></c>'


def put_cell(xml, ref, value):
    """The sheet XML with ref's cell replaced (or inserted in column order, its row created if need be)."""
    col, row = split_ref(ref)
    for m in CELL.finditer(xml):
        if re.search(rf'\sr="{ref}"', m.group("a")):
            return xml[:m.start()] + cell_xml(ref, m.group("a"), value) + xml[m.end():]
    new = cell_xml(ref, "", value)
    for m in ROW.finditer(xml):
        r = int(re.search(r'\sr="(\d+)"', m.group("a")).group(1))
        if r == row:
            body = m.group("body") or ""
            at = next((c.start() for c in CELL.finditer(body)
                       if split_ref(re.search(r'\sr="([A-Z]+\d+)"', c.group("a")).group(1))[0] > col), len(body))
            body = body[:at] + new + body[at:]
            return xml[:m.start()] + f"<row{m.group('a')}>{body}</row>" + xml[m.end():]
        if r > row:
            return xml[:m.start()] + f'<row r="{row}">{new}</row>' + xml[m.start():]
    if "<sheetData/>" in xml:
        return xml.replace("<sheetData/>", f'<sheetData><row r="{row}">{new}</row></sheetData>', 1)
    return xml.replace("</sheetData>", f'<row r="{row}">{new}</row></sheetData>', 1)


def full_calc_on_load(wb):
    """workbook.xml with calcPr fullCalcOnLoad="1" (as model-summary's Package.finish sets it)."""
    if CALCPR.search(wb):
        return CALCPR.sub(lambda m: "<calcPr" + re.sub(r'\s*fullCalcOnLoad="\w+"', "", m.group("a"))
                          + ' fullCalcOnLoad="1"/>', wb, count=1)
    return re.sub(r"(</sheets>(?:\s*<functionGroups[^>]*/>)?(?:\s*<externalReferences>.*?</externalReferences>)?"
                  r"(?:\s*<definedNames>.*?</definedNames>)?)", r'\1<calcPr fullCalcOnLoad="1"/>', wb, count=1,
                  flags=re.S)


def run(model, plan, record, out):
    if os.path.abspath(out) == os.path.abspath(model):
        raise SystemExit("write-pitch: --out must be a copy, not the model itself.")
    P = common.load(plan)
    boxes, numbers = P.get("sum_boxes") or {}, P.get("numbers") or {}
    bad = sorted(set(boxes) - set(common.SUM_BOXES))
    if bad:
        raise SystemExit("write-pitch: sum_boxes has labels SUM does not have: " + ", ".join(bad))
    has_record = bool(record) and os.path.exists(record)
    last = common.load(record) if has_record else {}
    found, warnings = find_boxes(model)
    if not has_record:
        warnings.append("No sum_written.json (the record of what the last run wrote), so only empty boxes are "
                        "written; every filled box is treated as yours.")
    rep = {"written": [], "kept": [], "skipped_null": [], "missing": [], "cells": {}, "warnings": warnings}
    nxt = {}
    pkg = Package(model)
    part = {s[0]: s[3] for s in pkg.sheets()}[TAB]
    xml = pkg.text(part)
    for label in common.SUM_BOXES:
        rec = last.get(label)
        if label not in found:                                          # can't see the box: keep what we knew
            if label in boxes:
                rep["missing"].append(label)
            if rec:
                nxt[label] = rec
            continue
        ref, now = found[label]
        text = boxes.get(label)
        if text is None:                                                # null or left out: leave the box alone
            if label in boxes:
                rep["skipped_null"].append(label)
            if rec and not empty(now) and same(now, rec["value"]):     # still ours: keep it on the record
                nxt[label] = rec
            continue
        if not (empty(now) or (rec and same(now, rec["value"]))):
            rep["kept"].append(label)
            continue
        v = wanted(label, text, numbers)
        xml = put_cell(xml, ref, v)
        rep["written"].append(label)
        rep["cells"][label] = nxt[label] = {"cell": ref, "value": v}
    if rep["missing"]:
        warnings.append("Not found on SUM (rerun /model-summary to lay the boxes out): " + ", ".join(rep["missing"]))
    pkg.put(part, xml)
    if rep["written"]:
        pkg.put("xl/workbook.xml", full_calc_on_load(pkg.text("xl/workbook.xml")))
    pkg.save(out)
    if record:
        os.makedirs(os.path.dirname(os.path.abspath(record)), exist_ok=True)
        common.save(os.path.join(os.path.dirname(os.path.abspath(record)), "sum_written.next.json"), nxt)
    return rep


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    for k in ("--model", "--plan", "--record", "--out"):
        ap.add_argument(k, required=True)
    a = ap.parse_args()
    print(json.dumps(run(a.model, a.plan, a.record, a.out), indent=1))


if __name__ == "__main__":
    main()
