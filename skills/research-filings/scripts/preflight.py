"""Step 1 - check every input before any work; stop with a plain message for each one that's missing.

usage: python3 preflight.py --ticker DXCM [--src DIR] [--model PATH] [--price PATH]
Source folder: <research_dir>/<TICKER>, else a _manifest.json for the ticker on the Desktop, Downloads or
Documents. Model: <TICKER>_model.xlsx with a MOD tab, in the source folder first, then the same places (or --model).
Price: --price (a workbook with a 'Px Data' tab, or a folder of Stooq CSVs for the ticker and SPY), else the model's
'Px Data' tab, else <src>/Price Data/.
Prints JSON {status: ok|stop, missing: [{what, fix}], src, model, price: {kind, path}, as_of, out}; exit 2 on stop."""
import argparse, glob, json, os, sys

import openpyxl

sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "..", "..", "lib"))
import settings  # noqa: E402
from common import load, phase_dir
from inventory import build

HOME = os.path.expanduser("~")
SKIP = {"Library", "Applications", "Pictures", "Music", "Movies", "node_modules", "_md", "_model_work", "_work"}


def _walk(root, depth):
    if not os.path.isdir(root):
        return
    base = root.rstrip(os.sep).count(os.sep)
    for d, subs, files in os.walk(root):
        yield d, files
        too_deep = d.count(os.sep) - base >= depth
        subs[:] = [] if too_deep else sorted(s for s in subs if not s.startswith(".") and s not in SKIP)


def _roots(home):
    return [(os.path.join(home, x), 6) for x in ("Desktop", "Downloads", "Documents")]


def find_src(ticker, home):
    first = os.path.join(settings.research_dir(), ticker)
    if os.path.exists(os.path.join(first, "_manifest.json")):
        return first
    for root, depth in _roots(home):
        for d, files in _walk(root, depth):
            if "_manifest.json" in files and \
                    str((load(os.path.join(d, "_manifest.json")) or {}).get("ticker", "")).upper() == ticker:
                return d
    return None


def has_sheet(path, name):
    try:
        return name in openpyxl.load_workbook(path, read_only=True).sheetnames
    except Exception:
        return False


def find_model(ticker, src, home):
    name = f"{ticker}_model.xlsx".lower()
    for root, depth in ([(src, 1)] if src else []) + _roots(home):
        for d, files in _walk(root, depth):
            hit = next((f for f in files if f.lower() == name), None)
            if hit and has_sheet(os.path.join(d, hit), "MOD"):
                return os.path.join(d, hit)
    return None


def stooq_pair(folder, ticker):
    names = [os.path.basename(p).lower() for p in glob.glob(os.path.join(folder, "*.csv"))]
    return any(n.startswith(ticker.lower()) for n in names) and any(n.startswith("spy") for n in names)


def check(ticker, src=None, model=None, price=None, home=HOME):
    t, missing = ticker.upper(), []
    src = src or find_src(t, home)
    if not src:
        missing.append({"what": "source folder", "fix": f"run /collect-documents {t} first"})
    model = model or find_model(t, src, home)
    if not model or not has_sheet(model, "MOD"):
        missing.append({"what": "model", "fix": f"run /model-historicals {t}, /model-ratios {t} and /model-kpis {t} "
                                                f"first, or give the model's path with --model"})
        model = None
    px = None
    for c in ([price] if price else [model, os.path.join(src, "Price Data") if src else None]):
        if c and os.path.isfile(c) and has_sheet(c, "Px Data"):
            px = {"kind": "tab", "path": c}
            break
        if c and os.path.isdir(c) and stooq_pair(c, t):
            px = {"kind": "csv", "path": c}
            break
    if not px:
        folder = os.path.join(src or "<source folder>", "Price Data")
        missing.append({"what": "price history", "fix": f"download daily price CSVs for {t} and SPY from stooq.com "
                                                        f"({t.lower()}_us_d.csv and spy_us_d.csv) into {folder}"})
    as_of = None
    if src:
        docs, _, _ = build(src)
        dates = [d["date"] for d in docs if d["date"]]
        as_of = max(dates) if dates else None
        if not docs:
            missing.append({"what": "company documents", "fix": f"the manifest lists none; rerun /collect-documents {t}"})
    return {"status": "stop" if missing else "ok", "missing": missing, "src": src, "model": model, "price": px,
            "as_of": as_of, "out": phase_dir(src) if src else None}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticker", required=True)
    ap.add_argument("--src")
    ap.add_argument("--model")
    ap.add_argument("--price")
    a = ap.parse_args()
    r = check(a.ticker, a.src, a.model, a.price)
    print(json.dumps(r, indent=1))
    sys.exit(2 if r["status"] == "stop" else 0)
