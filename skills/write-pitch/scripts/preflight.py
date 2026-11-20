"""Step 1 - check the model, the research reports and the earlier skills' output exist and are fresh.

usage: python3 preflight.py --ticker XYZ [--model PATH] [--research DIR]
Prints JSON {"status": "ok"|"stop", "model", "research", "pitch_dir", "work", "mode": "first"|"rerun",
"optional_missing", "missing": [{"what", "fix"}], "stale": null|{...}, "warnings"} and exits 0. Read-only.
`stale` is set when Px Events shows full results already released for a quarter MOD still forecasts (fix: run
/model-update, then /model-valuation and /model-summary), or when MOD's newest quarter was released after the newest
Valuation note or the last finished /model-summary (its inputs_written.json, promoted only on copy-over).
First it checks that the Python packages the run needs import in this interpreter (the skill runs every script with
python3 -I, which hides the user site-packages, so a `pip install --user` package counts as missing)."""
import argparse
import datetime
import glob
import importlib
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
REQUIRED = {"MOD": "/model-historicals", "DCF": "/model-dcf", "Multiples": "/model-multiples",
            "Valuation": "/model-valuation", "SUM": "/model-summary"}
OPTIONAL_TABS = ["Short Check", "Earnings", "Consensus", "Industry P&L", "Industry Comparison", "Filings Charts",
                 "Idio Chart"]
OPTIONAL_NOTES = ["Valuation", "Short Check", "Earnings Previews", "Earnings Reviews"]
QUARTER = re.compile(r"^Q[1-4] \d\d$")


# import name -> pip package name; openpyxl is imported only after this check passes
PACKAGES = {"pptx": "python-pptx", "docx": "python-docx", "fitz": "pymupdf", "openpyxl": "openpyxl", "PIL": "pillow"}
INSTALL = "python3 -m pip install " + " ".join(PACKAGES.values())


def deps(importer=importlib.import_module):
    """[{"what", "fix"}] for each package that does not import (importer is injectable for tests)."""
    out = []
    for mod, pkg in PACKAGES.items():
        try:
            importer(mod)
        except ImportError:
            out.append({"what": pkg, "fix": INSTALL})
    return out


def _rows(ws):
    """Every row of a read-only sheet as a list (rows can be ragged). A stale <dimension> would otherwise cut rows and
    columns off: read-only openpyxl trusts it (same as sum_boxes.find_boxes and model-earnings-after/context.py)."""
    ws.reset_dimensions()
    return [list(r) for r in ws.iter_rows(values_only=True)]


def _at(row, c):
    return row[c] if 0 <= c < len(row) else None


def _row2(ws):
    rows = _rows(ws)
    return [str(v).strip() for v in (rows[1][3:] if len(rows) > 1 else []) if v is not None]


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


def _period_key(p):
    """('Q3 26') -> (26, 3) for ordering; None for anything else."""
    m = re.match(r"^Q([1-4]) (\d\d)$", str(p or "").strip().rstrip("E").strip())
    return (int(m.group(2)), int(m.group(1))) if m else None


def _header(rows, wanted):
    """(row index, {header: column}) of the first of the top 10 rows holding every `wanted` header, else (None, {})."""
    for i, row in enumerate(rows[:10]):
        heads = {}
        for c, v in enumerate(row):
            if isinstance(v, str):
                heads.setdefault(v.strip(), c)
        if all(w in heads for w in wanted):
            return i, heads
    return None, {}


def release(rows, period):
    """Px Events' full-results release date for a period ('Q3 26'). Copied in minimum from
    model-earnings-after/scripts/rates.py release() and _header()."""
    i, h = _header(rows, ("Period", "Full-results release date"))
    if i is None:
        return None
    cp, cd = h["Period"], h["Full-results release date"]
    for r in rows[i + 1:]:
        if str(_at(r, cp) or "").strip().rstrip("E") == period and _day(_at(r, cd)):
            return _day(_at(r, cd))
    return None


def reported_after(rows, quarter, today):
    """[(period, date)] of full results released on or before today for a quarter later than MOD's newest actual one.
    Px Events' left block lists only MOD's actual quarters (model-price-history builds it from them), so the later
    period can show only in the event block: an "Earnings" event named "<period> earnings" (events.py), or a Period
    row the user typed."""
    last = _period_key(quarter)
    out = []
    i, h = _header(rows, ("Period", "Full-results release date"))
    if i is not None:
        out += [(str(_at(r, h["Period"])).strip(), _day(_at(r, h["Full-results release date"]))) for r in rows[i + 1:]]
    i, h = _header(rows, ("Event date", "Type", "Event"))
    if i is not None:
        for r in rows[i + 1:]:
            m = re.match(r"^(Q[1-4] \d\d) earnings$", str(_at(r, h["Event"]) or "").strip())
            if m and str(_at(r, h["Type"]) or "").strip() == "Earnings":
                out.append((m.group(1), _day(_at(r, h["Event date"]))))
    hits = {p: d for p, d in out if d and d <= today and _period_key(p) and _period_key(p) > last}
    return sorted(hits.items(), key=lambda x: _period_key(x[0]))


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


def check(ticker, model, research, importer=importlib.import_module):
    pitch = os.path.join(research, "Pitch")
    out = {"status": "ok", "model": model, "research": research, "pitch_dir": pitch,
           "work": os.path.join(pitch, "_work"), "mode": "first", "optional_missing": [], "missing": [],
           "stale": None, "warnings": []}
    if os.path.exists(os.path.join(pitch, "_work", "plate.md")):
        out["mode"] = "rerun"
    out["missing"] = deps(importer)
    if out["missing"]:
        out["status"] = "stop"
        return out
    if not model or not os.path.exists(model):
        out["missing"].append({"what": "model", "fix": "run /model-historicals"})
        out["status"] = "stop"
        return out
    import openpyxl
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


SUMMARY_RECORD = "inputs_written.json"   # model-summary's copyover.py promotes it only after a successful copy-over


def freshness(wb, heads, research, model, warnings, today=None):
    q = newest_actual_quarter(heads)
    ev = _rows(wb["Px Events"]) if "Px Events" in wb.sheetnames else None
    if q and ev and _period_key(q):
        late = reported_after(ev, q, today or datetime.date.today())
        if late:
            p, d = late[-1]
            return {"quarter": p, "release": d.isoformat(), "valuation_note": None, "mod_newest_actual": q,
                    "fix": "run /model-update, then /model-valuation and /model-summary"}
    rel = release(ev, q) if q and ev else None
    if not rel:
        warnings.append("freshness not checked: no release date for the newest actual quarter in Px Events")
        return None
    dated = [(note_date(p), p) for p in glob.glob(os.path.join(research, "Valuation", "*Valuation Note.md"))]
    dated = [x for x in dated if x[0]]
    nd, note = max(dated) if dated else (None, None)
    work = os.path.join(os.path.dirname(model), "_model_work", "model-summary")
    rec = os.path.join(work, SUMMARY_RECORD)
    summ = datetime.datetime.fromtimestamp(os.path.getmtime(rec)).date() if os.path.exists(rec) else None
    if not summ and glob.glob(os.path.join(work, "*")):
        warnings.append(f"SUM's freshness not checked: _model_work/model-summary has no {SUMMARY_RECORD} (written "
                        "only when /model-summary copies its build over the model), so its last run may not have "
                        "finished")
    if not nd and not summ:
        warnings.append("freshness not checked: no dated Valuation note and no finished /model-summary run")
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
