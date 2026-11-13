"""Read the user's MOD tab by label: period columns (quarters and fiscal years) and the rows this skill needs.

usage: python3 modmap.py --model M.xlsx [--values V.xlsx]   (prints the JSON it found)
Never uses row numbers: The user inserts rows. Every role has an ordered list of label patterns; the first that matches
wins, and the JSON names the label it matched so the skill can show the user. `--values` is a recalculated copy (from
verify.recalc) when M has formulas with no cached values (a model openpyxl wrote)."""
import argparse
import json
import re

import openpyxl
from openpyxl.utils import get_column_letter

Q_RE = re.compile(r"^Q([1-4]) (\d\d)(E?)$")
FY_RE = re.compile(r"^(\d{4})(E?)$")

# role -> label patterns, most specific first (the user's hand-edited DXCM labels and /model-ratios's both appear).
ROLES = {
    "eps_gaap": [r"^EPS, diluted$", r"^Diluted EPS$", r"^EPS.*diluted"],
    "eps_ng": [r"^Non-GAAP EPS, Diluted$", r"^(Non-GAAP|Adjusted) (Diluted )?EPS", r"^(Non-GAAP|Adjusted) EPS"],
    "revenue": [r"^Revenue:?$", r"^Total Revenues?:?$", r"^Net Revenues?:?$", r"^Net Sales:?$", r"^Revenues?, net:?$"],
    "oi_gaap": [r"^Operating Income$", r"^Operating Income \(Loss\)$", r"^GAAP Operating Income$",
                r"^Income \(Loss\) from Operations$", r"^Income from Operations$"],
    "oi_ng": [r"^Non-GAAP Operating Income$", r"^Adjusted Operating Income$"],
    "ebitda_ng": [r"^Adjusted EBITDA$", r"^Non-GAAP EBITDA$"],
    "ebitda_gaap": [r"^EBITDA$"],
    "roic": [r"^ROICasset TTM$", r"^ROIC asset \(Invested Cap Avg\) TTM$", r"^ROIC ?asset.*TTM"],
    "roic_ex_cash": [r"^ROIC\(minus cash\) TTM$", r"^ROIC minus cash \(Invested Cap Avg\) TTM$", r"^ROIC.*minus cash.*TTM"],
    "fcf": [r"^\(\+/-\) Free Cash Flow$", r"^Free Cash Flow$"],
    "buyback_net": [r"^\(\+/-\) Stock Issuance / Repurchase$"],
    "buyback": [r"^\(-\) Share Repurchases$", r"^\(-\) Repurchases? of (Common )?Stock"],
    "issuance": [r"^\(\+\) Stock Issuance / Employee Plans$", r"^\(\+\) (Proceeds from )?(Stock|Share) Issuance"],
}
# FCF must come from the FREE CASH FLOW section, not the leverage section's "Free Cash Flow" helper row: prefer the
# last match for these roles (the cash-flow sections sit lowest in MOD).
LAST_MATCH = {"fcf"}


def clean(v):
    return re.sub(r"\s+", " ", str(v or "")).strip()


def header_row(ws, max_row=10):
    best, row = 0, None
    for r in range(1, max_row + 1):
        n = sum(1 for c in ws[r] if Q_RE.match(clean(c.value)))
        if n > best:
            best, row = n, r
    return row


def periods(ws, hr):
    """Quarters and fiscal years in sheet order: [{label, col, kind, year, q, est}]"""
    out = []
    for c in ws[hr]:
        lab = clean(c.value)
        m = Q_RE.match(lab)
        if m:
            out.append({"label": lab, "col": c.column_letter, "kind": "q", "q": int(m[1]), "year": 2000 + int(m[2]),
                        "est": bool(m[3])})
            continue
        m = FY_RE.match(lab)
        if m and 1990 < int(m[1]) < 2100:
            out.append({"label": lab, "col": c.column_letter, "kind": "fy", "year": int(m[1]), "est": bool(m[2])})
    return out


def find_rows(ws):
    labels = {r: clean(ws.cell(r, 2).value) for r in range(1, ws.max_row + 1)}
    found = {}
    for role, pats in ROLES.items():
        for p in pats:
            hits = [r for r, lab in labels.items() if re.search(p, lab, re.I)]
            if hits:
                r = hits[-1] if role in LAST_MATCH else hits[0]
                found[role] = {"row": r, "label": labels[r], "pattern": p, "all_rows": hits}
                break
    return found


def read(model, values=None):
    wf = openpyxl.load_workbook(model, read_only=True)
    ws = wf["MOD"]
    hr = header_row(ws)
    per = periods(ws, hr)
    rows = find_rows(ws)
    wf.close()
    wv = openpyxl.load_workbook(values or model, read_only=True, data_only=True)["MOD"]
    grid = {r: row for r, row in enumerate(wv.iter_rows(min_row=1, max_row=max(x["row"] for x in rows.values()),
                                                         values_only=True), 1)}
    from openpyxl.utils import column_index_from_string as ci
    vals = {}
    for role, x in rows.items():
        line = grid.get(x["row"], ())
        vals[role] = {}
        for p in per:
            v = line[ci(p["col"]) - 1] if ci(p["col"]) - 1 < len(line) else None
            vals[role][p["label"]] = v if isinstance(v, (int, float)) and not isinstance(v, bool) else None
    missing_cache = sum(1 for role in vals for v in vals[role].values() if v is None)
    return {"header_row": hr, "periods": per, "rows": rows, "values": vals, "none_count": missing_cache}


def quarters(per, actual_only=False):
    return [p for p in per if p["kind"] == "q" and not (actual_only and p["est"])]


def fy_of(per, year):
    return next((p for p in per if p["kind"] == "fy" and p["year"] == year), None)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--values")
    a = ap.parse_args()
    d = read(a.model, a.values)
    q = quarters(d["periods"])
    print(json.dumps({"header_row": d["header_row"], "first_quarter": q[0]["label"], "last_quarter": q[-1]["label"],
                      "last_actual_quarter": quarters(d["periods"], True)[-1]["label"],
                      "rows": {k: {"row": v["row"], "label": v["label"]} for k, v in d["rows"].items()},
                      "missing_roles": [k for k in ROLES if k not in d["rows"]]}, indent=1))
