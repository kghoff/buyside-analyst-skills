# skills/model-summary/scripts/modrows.py
"""(Adapted from model-valuation subject.py, Nov 2026: only the rows SUM reads.) MOD rows found by label within their
statement section, as model-dcf does, and the GAAP / non-GAAP EPS choice the user made in model-price-history."""
import re

import openpyxl

ROLES = [  # (name, section regex, label regex, required)
    ("rev", r"^income statement:?$", r"^revenue", True),
    ("gp", r"^income statement:?$", r"^gross profit", False),
    ("oi", r"^income statement:?$", r"^operating income", True),
    ("eps_gaap", r"^income statement:?$", r"^eps, diluted", True),
    ("eps_ng", r"^non-gaap", r"non-gaap eps, diluted", False),
    ("ebitda_ng", r"^non-gaap", r"^adjusted ebitda", False),
    ("da", r"operating activities", r"depreciation", True),
]
FCF = r"free cash flow$"            # the last match: the FREE CASH FLOW section sits lowest in MOD


def norm(t):
    return " ".join(t.lower().replace("(-)", "").replace("(+)", "").replace("(+/-)", "").split())


def find_rows(mm):
    lines = [(r, k.split(" | ", 1)[0].lower(), norm(re.sub(r" #\d+$", "", k.split(" | ", 1)[1])))
             for k, r in mm.keys.items()]
    out, missing = {}, []
    for name, sec, lab, req in ROLES:
        hit = next((r for r, s, l in lines if re.search(sec, s) and re.search(lab, l)), None)
        if hit is not None:
            out[name] = hit
        elif req:
            missing.append(name)
    fcf = [r for r, s, l in lines if re.search(FCF, l)]
    if fcf:
        out["fcf"] = fcf[-1]
    else:
        missing.append("fcf")
    if missing:
        raise SystemExit("model-summary: MOD has no row for " + ", ".join(missing) + ". It looks for them by label "
                         "within their statement section, as model-dcf does. Check the row labels in the model.")
    return out


def eps_basis(model):
    """'ng' when Px Data's P/E header says non-GAAP, else 'gaap'."""
    wb = openpyxl.load_workbook(model, read_only=True)
    try:
        hdr = next(wb["Px Data"].iter_rows(min_row=4, max_row=4, values_only=True))
    finally:
        wb.close()
    pe = next((str(h) for h in hdr if h and str(h).startswith("P/E")), "")
    return "ng" if "non-gaap" in pe.lower() else "gaap"
