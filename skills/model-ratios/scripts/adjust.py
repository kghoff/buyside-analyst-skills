"""FCF adjustment rows and day counts.

ytd_values / adj_cell: pull one cash-flow line out of every filing model-historicals parsed (<work>/filings.json, values
already in $M, column 0 = current year-to-date) and turn it into quarters the way model-historicals does:
Q1 typed, Q2 = 6M - Q1, Q3 = 9M - Q2 - Q1, Q4 = FY - SUM(Q1:Q3), FY typed.
period_ends / quarter_days: fiscal period-end dates from /collect-documents's _manifest.json ids (10-Q:YYYY-MM-DD).

CLI (for the agent's FCF judgment): python3 adjust.py --work <_model_work> --list
prints every cash-flow line label with the number of filings it appears in and its latest value."""
import argparse
import json
import os
import re
from datetime import date

from openpyxl.utils import get_column_letter as L

from roles import fmt_num


def ytd_values(filings, pattern):
    """-> {period key ('Q2 22' / 'FY 22'): YTD $M}, summing every CF line that matches; 0.0 if none matches."""
    out = {}
    for key, f in filings.items():
        rows = f.get("tables", {}).get("CF", [])
        out[key] = sum((vals[0] for lab, vals in rows if vals and vals[0] is not None and re.search(pattern, lab, re.I)), 0.0)
    return out


def adj_cell(ytd, periods, c, row):
    """Value or formula for one adjustment cell; None for estimate columns and periods with no parsed filing."""
    q, y, est = periods.cols[c]
    if est:
        return None
    if q == 4:
        q1, q3, fy = periods.find(1, y), periods.find(3, y), periods.find(0, y)
        if None in (q1, q3, fy):
            return None
        return f"={L(fy)}{row}-SUM({L(q1)}{row}:{L(q3)}{row})"
    v = ytd.get(f"FY {y % 100:02d}" if q == 0 else f"Q{q} {y % 100:02d}")
    if v is None:
        return None
    if q in (0, 1):
        return round(v, 4)
    cols = [periods.find(k, y) for k in range(q - 1, 0, -1)]
    if None in cols:
        return None
    prior = "-".join(f"{L(c)}{row}" for c in cols)
    return f"={fmt_num(v)}-{prior}"


def period_ends(manifest_path):
    """-> {(q, y): date}; a 10-K's period end is stored as (4, fiscal year)."""
    out = {}
    items = json.load(open(manifest_path)).get("items", {})
    for id_, it in items.items():
        m = re.fullmatch(r"10-([KQ]):(\d{4}-\d{2}-\d{2})", id_)
        if not m:
            continue
        lab, d = it.get("label", ""), date.fromisoformat(m.group(2))
        if m.group(1) == "K":
            x = re.search(r"\b(\d{4}) 10-K\b", lab)
            if x: out[(4, int(x.group(1)))] = d
        else:
            x = re.search(r"\b(?:Q([1-3]) (\d{2})|(\d{4}) Q([1-3])) 10-Q\b", lab)   # "Q1 24 10-Q" (old) or "2024 Q1 10-Q"
            if x: out[(int(x.group(1) or x.group(4)), 2000 + int(x.group(2)) if x.group(2) else int(x.group(3)))] = d
    return out


def quarter_days(ends, q, y):
    prev = ends.get((4, y - 1)) if q == 1 else ends.get((q - 1, y))
    cur = ends.get((q, y))
    return (cur - prev).days if cur and prev else None


def list_cf_lines(filings):
    """-> [(label, filings it appears in, latest value)] for every cash-flow line, most common first."""
    seen = {}
    for key in sorted(filings, key=lambda k: (int(k[3:]), 4 if k.startswith("FY") else int(k[1]))):
        for lab, vals in filings[key].get("tables", {}).get("CF", []):
            if not vals:
                continue
            n, _ = seen.get(lab, (0, None))
            seen[lab] = (n + 1, f"{key}: {vals[0]}")
    return sorted(((lab, n, last) for lab, (n, last) in seen.items()), key=lambda t: -t[1])


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True)
    ap.add_argument("--list", action="store_true", required=True)
    a = ap.parse_args()
    for lab, n, last in list_cf_lines(json.load(open(os.path.join(a.work, "filings.json")))):
        print(f"{n:3d}  {lab}  (latest {last})")
