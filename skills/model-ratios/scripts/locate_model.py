"""Step 0 - find the ticker's base model (TICKER_model.xlsx with a MOD tab) and its /collect-documents source folder.

usage: python3 locate_model.py --ticker DXCM
A model is <ticker>_model*.xlsx (any case) with a MOD tab. One in <research_dir>/<TICKER> always wins: every model
lives there. Otherwise the most recently saved one found on the Desktop, or in a light search of Downloads, Documents
and the home folder (shallow; skips Library, hidden and app folders - same as model-historicals), so an old copy
never shadows the one the user is working on.
Prints JSON {"status": "found", "model", "model_dir", "work", "src"} or {"status": "build"} (run /model-historicals)."""
import argparse
import json
import os
import sys

import openpyxl

sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "..", "..", "lib"))
import settings  # noqa: E402

SKIP = {"Library", "Applications", "Pictures", "Music", "Movies", "node_modules", "_md", "_model_work"}


def _walk(root, depth):
    if not os.path.isdir(root):
        return
    base = root.rstrip(os.sep).count(os.sep)
    for d, subs, files in os.walk(root):
        yield d, files
        too_deep = d.count(os.sep) - base >= depth
        subs[:] = [] if too_deep else sorted(s for s in subs if not s.startswith(".") and s not in SKIP)


def _has_mod(path):
    try:
        wb = openpyxl.load_workbook(path, read_only=True)
        ok = "MOD" in wb.sheetnames
        wb.close()
        return ok
    except Exception:
        return False


def _source_dir(model_dir, ticker):
    subs = sorted(os.path.join(model_dir, s) for s in os.listdir(model_dir) if os.path.isdir(os.path.join(model_dir, s)))
    for d in [model_dir] + subs:
        try:
            if json.load(open(os.path.join(d, "_manifest.json"))).get("ticker", "").upper() == ticker:
                return d
        except (OSError, ValueError):
            continue
    return None


def _is_model(f, t):
    f = f.lower()
    return f.startswith(f"{t.lower()}_model") and f.endswith(".xlsx") and not f.startswith("~$")


def find_model(ticker, home=os.path.expanduser("~")):
    t = ticker.upper()
    desktop = os.path.join(home, "Desktop")
    research = [(os.path.join(settings.research_dir(), t), 0)]
    elsewhere = [(desktop, 6), (os.path.join(home, "Downloads"), 6), (os.path.join(home, "Documents"), 6), (home, 4)]
    for roots in (research, elsewhere):
        hits, seen = [], set()
        for root, depth in roots:
            for d, files in _walk(root, depth):
                for f in files:
                    path = os.path.join(d, f)
                    if _is_model(f, t) and path not in seen:
                        seen.add(path)
                        if _has_mod(path):
                            hits.append(path)
        if hits:
            path = max(hits, key=os.path.getmtime)
            d = os.path.dirname(path)
            return {"status": "found", "model": path, "model_dir": d, "work": os.path.join(d, "_model_work"),
                    "src": _source_dir(d, t)}
    return {"status": "build"}

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticker", required=True)
    print(json.dumps(find_model(ap.parse_args().ticker), indent=1))
