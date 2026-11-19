"""Band 13's before side, from model-valuation's dated note (`<date> <T> Valuation Note.md`, written by code in a
fixed layout: model-valuation scripts/note.py), and its after side, from the Valuation tab's column-A labels (the
same labels the note prints). parse() returns no values and a 'problem' when the layout is not recognised: band 13
shows '?' then."""
import os
import re

import openpyxl

# Strings model-valuation's note.py / build.py write and this parser depends on (tests/test_valnote.py checks them).
RELIED_ON = ("## 1 The recommendation", "## 2 Targets and risk/reward", "## 3 Three-year IRR", "**Blended**",
             "reward price", "risk price", "reward / risk", "IRR: price now", "IRR: price in 3 years", "IRR: years",
             "Blended ")
NOTE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2}) (.+) Valuation Note\.md$")
ROW = re.compile(r"^\| ([^|]+?) \| ([^|]*?) \|")
BLENDED = re.compile(r"\*\*Blended\*\*: reward [^(]*\(to \$([\d,.]+)\), risk [^(]*\(to \$([\d,.]+)\), "
                     r"reward / risk ([\d.]+)x")
ROLES = ("primary", "secondary", "tertiary")


def latest_before(research_root, ticker, release_day):
    """The newest '<date> <ticker> Valuation Note.md' dated before release_day (YYYY-MM-DD), or None."""
    d = os.path.join(research_root, "Valuation")
    if not os.path.isdir(d):
        return None
    got = sorted(f for f in os.listdir(d) if (m := NOTE_RE.match(f)) and m.group(2) == ticker
                 and m.group(1) < release_day)
    return os.path.join(d, got[-1]) if got else None


def _num(t):
    """'$1,234.5' / '-$5.00' / '11.2%' / '0.7x' / '3' -> float (% as a fraction); anything else None."""
    t = t.strip().replace(",", "")
    m = re.fullmatch(r"(-?)\$?(-?\d+(?:\.\d+)?)(%|x)?", t)
    if not m:
        return None
    v = float(m.group(2)) * (-1 if m.group(1) else 1)
    return v / 100 if m.group(3) == "%" else v


def parse(path):
    """{values: {label: {value, line}}, multiples: [names in role order], problem: None or why, path}."""
    lines = open(path, encoding="utf-8").read().splitlines()
    if not all(any(ln.startswith(h) for ln in lines) for h in RELIED_ON[:3]):
        return {"values": {}, "multiples": [], "problem": "layout not recognised (headings missing)", "path": path}
    sec, vals, mults = None, {}, []
    for i, ln in enumerate(lines, start=1):
        if ln.startswith("## "):
            sec = ln[3:4]
        m = ROW.match(ln)
        if m and sec == "1" and m.group(2).strip() in ROLES:
            mults.append(m.group(1).strip())
        if m and sec in ("2", "3") and (v := _num(m.group(2))) is not None:
            vals.setdefault(m.group(1).strip(), {"value": v, "line": i})
        if sec == "2" and (b := BLENDED.search(ln)):
            for lab, x in zip(("Blended reward price", "Blended risk price", "Blended reward / risk"), b.groups()):
                vals[lab] = {"value": float(x.replace(",", "")), "line": i}
    return {"values": vals, "multiples": mults, "problem": None if vals else "layout not recognised (no values)",
            "path": path}


def labels(multiples):
    """The labels band 13 compares, before (note) against after (tab)."""
    out = []
    for m in multiples:
        out += [f"{m}: reward price", f"{m}: risk price", f"{m}: reward / risk"]
    return out + ["Blended reward price", "Blended risk price", "Blended reward / risk", "IRR: price now",
                  "IRR: price in 3 years", "IRR: years", "IRR"]


def after(values_path):
    """{cells: {label: {"ref": "'Valuation'!$B$n", "value"}}, title} from the (recalculated) copy's Valuation tab;
    None without one. The first row with a label wins."""
    wb = openpyxl.load_workbook(values_path, read_only=True, data_only=True)
    if "Valuation" not in wb.sheetnames:
        wb.close()
        return None
    out, title = {}, None
    for row in wb["Valuation"].iter_rows(max_col=2):
        a, b = row[0], row[1] if len(row) > 1 else None
        if getattr(a, "row", None) == 1:
            title = a.value
        if isinstance(getattr(a, "value", None), str) and a.value.strip() not in out:
            out[a.value.strip()] = {"ref": f"'Valuation'!$B${a.row}", "value": getattr(b, "value", None)}
    wb.close()
    return {"cells": out, "title": title}
