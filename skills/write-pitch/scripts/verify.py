# skills/write-pitch/scripts/verify.py
"""Prove sum_boxes.py changed only the SUM boxes before its copy replaces the user's model.

usage: python3 verify.py --before M --after W/out.xlsx [--expect <sum_boxes.py JSON output, or sum_written.next.json>]
Prints one problem per line, or "verify OK"; exit 1 if any problem.

Checks: the same part list; every part byte-identical except the SUM sheet part and xl/workbook.xml, which may differ
only in its calcPr (fullCalcOnLoad); on SUM, everything outside the cells sum_boxes reported is byte-identical and
those cells keep their style (s=, the yellow fill); each reported cell reads back as the value reported (a price as a
number, a text box as its text). Without --expect any SUM cell may change, but nothing else may."""
import argparse
import json
import os
import re
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))   # run with python3 -I
import openpyxl  # noqa: E402

from sum_boxes import CELL, TAB, same  # noqa: E402
from xlsx import Package  # noqa: E402

CALCPR = re.compile(r"<calcPr\b[^>]*/>")


def expected(path):
    """{label: {"cell", "value"}} from sum_boxes.py's output ("cells") or a sum_written(.next).json record."""
    d = json.load(open(path))
    return d["cells"] if "cells" in d else d


def cells_of(xml):
    """(sheet XML with each <c> replaced by a marker, {ref: (attrs, whole <c> text)})."""
    out = {}

    def mark(m):
        ref = re.search(r'\sr="([A-Z]+\d+)"', m.group("a")).group(1)
        out[ref] = (m.group("a"), m.group(0))
        return f"<c {ref}/>"
    return CELL.sub(mark, xml), out


def style(attrs):
    m = re.search(r'\ss="([^"]*)"', attrs)
    return m.group(1) if m else None


def check(before, after, expect=None):
    problems = []
    a, b = zipfile.ZipFile(before), zipfile.ZipFile(after)
    A = {n: a.read(n) for n in a.namelist()}
    B = {n: b.read(n) for n in b.namelist()}
    if sorted(A) != sorted(B):
        problems.append("part list differs: only before " + ", ".join(sorted(set(A) - set(B)))
                        + "; only after " + ", ".join(sorted(set(B) - set(A))))
    part = {s[0]: s[3] for s in Package(before).sheets()}.get(TAB)
    if part is None:
        return problems + ["the model has no SUM tab"]
    for n in sorted(set(A) & set(B)):
        if A[n] == B[n] or n == part:
            continue
        if n == "xl/workbook.xml" and CALCPR.sub("", A[n].decode()) == CALCPR.sub("", B[n].decode()):
            continue
        problems.append(f"{n} changed (only the SUM sheet and workbook.xml's calcPr may)")
    if part not in B:
        return problems
    E = expected(expect) if expect else None
    sa, ca = cells_of(A[part].decode())
    sb, cb = cells_of(B[part].decode())
    added = set(cb) - set(ca)                             # an input cell sum_boxes had to create
    rest = lambda s: re.sub(r"<row\b[^>]*?(?:/>|>.*?</row>)", "", s, flags=re.S)   # noqa: E731
    if rest(sa) != rest(sb):
        problems.append(f"{part}: the sheet changed outside its rows")
    allowed = None if E is None else {v["cell"] for v in E.values()}
    for ref in sorted(set(ca) | set(cb)):
        if ref in ca and ref in cb and ca[ref][1] == cb[ref][1]:
            continue
        if allowed is not None and ref not in allowed:
            problems.append(f"SUM!{ref} changed but sum_boxes did not report writing it")
        elif ref in ca and ref not in cb:
            problems.append(f"SUM!{ref} was removed")
        elif ref in ca and style(ca[ref][0]) != style(cb[ref][0]):
            problems.append(f"SUM!{ref} lost its style (s={style(ca[ref][0])} before, s={style(cb[ref][0])} after)")
    rows = lambda s: [m.group(0) for m in re.finditer(r"<row\b[^>]*?(?:/>|>)", s)]   # noqa: E731
    if not added and rows(sa) != rows(sb):
        problems.append(f"{part}: row attributes changed")
    if E:
        wb = openpyxl.load_workbook(after, read_only=True)
        try:
            ws = wb[TAB]
            for label, e in E.items():
                got = ws[e["cell"]].value
                num = isinstance(e["value"], (int, float)) and not isinstance(e["value"], bool)
                if num and not (isinstance(got, (int, float)) and not isinstance(got, bool)):
                    problems.append(f"SUM!{e['cell']} ({label}) holds {got!r}, not the number {e['value']!r}")
                elif got is None or not same(got, e["value"]):
                    problems.append(f"SUM!{e['cell']} ({label}) holds {got!r}, sum_boxes reported {e['value']!r}")
        finally:
            wb.close()
    return problems


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--before", required=True)
    ap.add_argument("--after", required=True)
    ap.add_argument("--expect")
    a = ap.parse_args()
    problems = check(a.before, a.after, a.expect)
    print("\n".join(problems) if problems else "verify OK")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
