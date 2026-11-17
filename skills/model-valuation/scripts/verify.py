"""Recalculate the built model in LibreOffice and check the Valuation tab against valmath (layout.json "expected").
Task 10 adds the byte-identity, colour, pairing, DCF re-type, anchor and PNG checks and the command line.

compare(out, work): every checked cell within rel 1e-6 (text equal; None = #N/A); no error values on the tab except
#N/A in cells whose formula can return NA() (layout "na")."""
import datetime as dt
import math
import json
import os

import openpyxl

import lo

TAB = "Valuation"


def close(a, b):
    """model-multiples' close, plus text: a text cell must equal its expected text."""
    if isinstance(a, dt.datetime):                        # date-formatted cells read back as datetimes
        a = (a - dt.datetime(1899, 12, 30)).total_seconds() / 86400
    if b is None:
        return a in (None, "#N/A")
    if isinstance(b, str):
        return a == b
    if not isinstance(a, (int, float)) or isinstance(a, bool):
        return False
    return math.isclose(a, b, rel_tol=1e-6, abs_tol=1e-9)


def compare(out, work):
    """Recalculate OUT into W/verify/ and compare the tab with layout.json. Returns {checked, failed, errors,
    recalculated}."""
    lay = json.load(open(os.path.join(work, "layout.json")))
    rec = lo.recalc(out, os.path.join(work, "verify"))
    ws = openpyxl.load_workbook(rec, data_only=True)[TAB]
    failed = [{"cell": ref, "got": ws[ref].value, "want": want} for ref, want in lay["expected"].items()
              if not close(ws[ref].value, want)]
    na = set(lay.get("na", []))
    errors = [c.coordinate for row in ws.iter_rows() for c in row
              if isinstance(c.value, str) and c.value.startswith("#") and not (c.value == "#N/A" and c.coordinate in na)]
    return {"checked": len(lay["expected"]), "failed": failed[:30], "errors": errors[:30], "recalculated": rec}
