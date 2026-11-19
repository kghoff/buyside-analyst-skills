"""Step 1 - check the model, the research reports and the earlier skills' output exist and are fresh.

usage: python3 preflight.py --ticker XYZ [--model PATH] [--research DIR]
Prints JSON {"status": "ok"|"stop", "model", "research", "pitch_dir", "work", "mode": "first"|"rerun",
"optional_missing", "missing": [{"what", "fix"}], "stale": null|{...}, "warnings"} and exits 0. Read-only."""
import argparse
import datetime
import glob
import json
import os
import re
import sys

import openpyxl

HERE = os.path.dirname(os.path.realpath(__file__))
REQUIRED = {"MOD": "/model-historicals", "DCF": "/model-dcf", "Multiples": "/model-multiples",
            "Valuation": "/model-valuation", "SUM": "/model-summary"}
OPTIONAL_TABS = ["Short Check", "Earnings", "Consensus", "Industry P&L", "Industry Comparison", "Filings Charts",
                 "Idio Chart"]
OPTIONAL_NOTES = ["Valuation", "Short Check", "Earnings Previews", "Earnings Reviews"]
QUARTER = re.compile(r"^Q[1-4] \d\d$")


def _row2(ws):
    return [str(v).strip() for v in next(ws.iter_rows(min_row=2, max_row=2, min_col=4, values_only=True), ())
            if v is not None]


def newest_actual_quarter(heads):
    """The last 'Q1 26'-style header in MOD row 2 (no trailing E); same convention as model-earnings-after."""
    q = [h for h in heads if QUARTER.match(h)]
    return q[-1] if q else None


def _day(v):
    """Copied from model-earnings-after/scripts/rates.py _day()."""
    if isinstance(v, datetime.datetime):
        return v.date()
    if isinstance(v, datetime.date):
        return v
    if isinstance(v, str):
        try:
            return datetime.date.fromisoformat(v[:10])
        except ValueError:
            return None
    return None


def release(ws, period):
    """Px Events' full-results release date for a period ('Q3 26'). Copied in minimum from
    model-earnings-after/scripts/rates.py release() and _header()."""
    rows = list(ws.iter_rows(values_only=True))
    for i, row in enumerate(rows[:10]):
        cells = [str(v).strip() if isinstance(v, str) else v for v in row]
        if "Period" in cells and "Full-results release date" in cells:
            cp, cd = cells.index("Period"), cells.index("Full-results release date")
            for r in rows[i + 1:]:
                if str(r[cp] or "").strip().rstrip("E") == period and _day(r[cd]):
                    return _day(r[cd])
    return None


def newest(pattern):
    hits = sorted(glob.glob(pattern))
    return hits[-1] if hits else None


def locate(ticker, model, research):
    if model and research:
        return model, research
    sys.path.insert(0, os.path.join(HERE, "..", "..", "model-ratios", "scripts"))
    sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "lib"))
    import settings
    from locate_model import find_model
    model = model or (find_model(ticker) or {}).get("model")
    return model, research or os.path.join(settings.research_dir(), ticker.upper())


def note_date(path):
    m = re.match(r"(\d{4}-\d{2}-\d{2})", os.path.basename(path)) if path else None
    return datetime.date.fromisoformat(m.group(1)) if m else None


def check(ticker, model, research):
    pitch = os.path.join(research, "Pitch")
    out = {"status": "ok", "model": model, "research": research, "pitch_dir": pitch,
           "work": os.path.join(pitch, "_work"), "mode": "first", "optional_missing": [], "missing": [],
           "stale": None, "warnings": []}
    if os.path.exists(os.path.join(pitch, "_work", "plate.md")):
        out["mode"] = "rerun"
    if not model or not os.path.exists(model):
        out["missing"].append({"what": "model", "fix": "run /model-historicals"})
        out["status"] = "stop"
        return out
    wb = openpyxl.load_workbook(model, read_only=True)
    try:
        return _check_open(wb, out, research, model)
    finally:
        wb.close()


def _check_open(wb, out, research, model):
    tabs = wb.sheetnames
    for t, fix in REQUIRED.items():
        if t not in tabs:
            out["missing"].append({"what": f"{t} tab", "fix": f"run {fix}"})
    heads = _row2(wb["MOD"]) if "MOD" in tabs else []
    if "MOD" in tabs and not any(h.endswith("E") for h in heads):
        out["missing"].append({"what": "MOD forecast", "fix": "run /model-forecast"})
    for pat, fix in [("Filings Research/*Filings Research Report.md", "/research-filings"),
                     ("Street Research/*Street Research Report.md", "/research-street")]:
        if not glob.glob(os.path.join(research, pat)):
            out["missing"].append({"what": pat, "fix": f"run {fix}"})
    out["optional_missing"] = [t for t in OPTIONAL_TABS if t not in tabs]
    out["optional_missing"] += [f"{d} note" for d in OPTIONAL_NOTES if not newest(os.path.join(research, d, "*.md"))]
    out["stale"] = freshness(wb, heads, research, model, out["warnings"])
    if out["missing"] or out["stale"]:
        out["status"] = "stop"
    return out


def freshness(wb, heads, research, model, warnings):
    q = newest_actual_quarter(heads)
    rel = release(wb["Px Events"], q) if q and "Px Events" in wb.sheetnames else None
    if not rel:
        warnings.append("freshness not checked: no release date for the newest actual quarter in Px Events")
        return None
    dated = [(note_date(p), p) for p in glob.glob(os.path.join(research, "Valuation", "*Valuation Note.md"))]
    dated = [x for x in dated if x[0]]
    nd, note = max(dated) if dated else (None, None)
    work = os.path.join(os.path.dirname(model), "_model_work", "model-summary")
    mt = [os.path.getmtime(p) for p in glob.glob(os.path.join(work, "*"))]
    summ = datetime.datetime.fromtimestamp(max(mt)).date() if mt else None
    if not nd and not summ:
        warnings.append("freshness not checked: no dated Valuation note and no model-summary work files")
        return None
    if (nd and rel > nd) or (summ and rel > summ):
        return {"quarter": q, "release": rel.isoformat(), "valuation_note": os.path.basename(note) if note else None,
                "fix": "rerun /model-valuation, then /model-summary"}
    return None


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticker", required=True)
    ap.add_argument("--model")
    ap.add_argument("--research")
    a = ap.parse_args()
    m, r = locate(a.ticker, a.model, a.research)
    print(json.dumps(check(a.ticker, m, r), indent=1))
