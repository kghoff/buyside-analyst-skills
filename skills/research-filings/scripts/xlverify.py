"""Prove an edit of the user's model changed nothing it shouldn't: recalculate the before and after files in LibreOffice
and compare every value on every tab that existed before.

usage: python3 xlverify.py BEFORE.xlsx AFTER.xlsx --work DIR [--insert MOD:34:5] [--new-tab "Filings Charts"]
       [--written cells.json]
MOD values are compared at their shifted rows. Cells Claude wrote (cells.json: {"Tab": ["A1", ...]}) and new tabs
are skipped. Prints a JSON summary; exit 1 when any value moved."""
import argparse
import json
import math
import os
import sys

import openpyxl

import lo


def _grid(path):
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    out = {}
    for ws in wb.worksheets:
        g = {}
        for row in ws.iter_rows():
            for c in row:
                if getattr(c, "value", None) is not None:
                    g[(c.row, c.column)] = c.value
        out[ws.title] = g
    return out


def bad_parts(path):
    """XML parts Excel would refuse (LibreOffice forgives some, e.g. a bare '&'). Must be empty."""
    import zipfile
    from xml.dom import minidom
    z, bad = zipfile.ZipFile(path), []
    for n in z.namelist():
        if n.endswith((".xml", ".rels", ".vml")):
            try:
                minidom.parseString(z.read(n))
            except Exception as e:
                bad.append(f"{n}: {e}")
    return bad


def _same(a, b):
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool):
        return math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-9)
    return a == b


def compare(before, after, inserts=(), written=None):
    """before / after: {tab: {(row, col): value}}. inserts: [(tab, at, n)]. Returns the list of differences."""
    written = written or {}
    diffs = []
    for tab, g in before.items():
        moves = [(at, n) for t, at, n in inserts if t == tab]
        skip = written.get(tab, set())
        ga = after.get(tab)
        if ga is None:
            diffs.append((tab, "tab missing"))
            continue
        for (r, c), v in g.items():
            r2 = r + sum(n for at, n in moves if r >= at)
            if (r2, c) in skip:
                continue
            if not _same(v, ga.get((r2, c))):
                diffs.append((tab, f"{openpyxl.utils.get_column_letter(c)}{r} -> row {r2}: {v!r} became {ga.get((r2, c))!r}"))
    return diffs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("before")
    ap.add_argument("after")
    ap.add_argument("--work", required=True)
    ap.add_argument("--insert", action="append", default=[])
    ap.add_argument("--written")
    a = ap.parse_args()
    bad = bad_parts(a.after)
    if bad:
        print(json.dumps({"broken_xml": bad}, indent=1))
        sys.exit(1)
    rb = lo.recalc(a.before, os.path.join(a.work, "verify_before"))
    ra = lo.recalc(a.after, os.path.join(a.work, "verify_after"))
    inserts = [(s.rsplit(":", 2)[0], int(s.rsplit(":", 2)[1]), int(s.rsplit(":", 2)[2])) for s in a.insert]
    written = {}
    if a.written:
        from openpyxl.utils.cell import coordinate_from_string, column_index_from_string
        for tab, refs in json.load(open(a.written)).items():
            written[tab] = {(coordinate_from_string(x)[1], column_index_from_string(coordinate_from_string(x)[0])) for x in refs}
    before, after = _grid(rb), _grid(ra)
    d = compare(before, after, inserts, written)
    print(json.dumps({"values_compared": sum(len(g) for g in before.values()), "differences": len(d),
                      "first": [f"{t}: {x}" for t, x in d[:15]]}, indent=1))
    sys.exit(1 if d else 0)


if __name__ == "__main__":
    main()
