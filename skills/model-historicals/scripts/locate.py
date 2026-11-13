"""Step 0 - find the ticker's source documents (the folder /collect-documents fills) and check they cover the model.

usage: python3 locate.py --ticker DXCM [--years 10]

A source folder is any folder with a _manifest.json for this ticker (the manifest's "ticker" field, or the
folder path naming the ticker when the manifest has none). Search order, stopping at the first complete one:
  1. <research_dir>/<TICKER>   (/collect-documents's default output)
  2. anywhere else on the Desktop
  3. light search: ~/Downloads, ~/Documents, then the rest of the home folder (shallow; skips Library, hidden
     and app folders)
"Complete" = a 10-K plus Q1-Q3 10-Qs for each of the last --years fiscal years (what build.py needs).

Prints JSON: {"status": "found" | "gather", "src", "model_dir", "complete_years", "candidates": [...], "best"}
  status "gather" = nothing complete was found; run /collect-documents <TICKER>, then run this again.
  best            = the candidate with the most complete years (use it if /collect-documents can't fill the gap, e.g. a
                    young company with under 10 years of filings)."""
import argparse, json, os, sys
from extract import discover

sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "..", "..", "lib"))
import settings  # noqa: E402

HOME = os.path.expanduser("~")
SKIP = {"Library", "Applications", "Pictures", "Music", "Movies", "node_modules", "_md", "_model_work"}


def manifest_dirs(root, depth):
    """Folders under root (at most depth levels down) that hold a _manifest.json; doesn't descend into them."""
    if not os.path.isdir(root):
        return
    base = root.rstrip(os.sep).count(os.sep)
    for d, subs, files in os.walk(root):
        if "_manifest.json" in files:
            subs[:] = []
            yield d
            continue
        too_deep = d.count(os.sep) - base >= depth
        subs[:] = [] if too_deep else sorted(s for s in subs if not s.startswith(".") and s not in SKIP)


def is_for(d, ticker):
    try:
        t = json.load(open(os.path.join(d, "_manifest.json"))).get("ticker")
    except (OSError, ValueError):
        return False
    if t:
        return t.upper() == ticker
    return ticker in (p.upper() for p in d.split(os.sep))


def coverage(src, years):
    found = discover(src)
    fys = sorted(k[1] for k in found if k[0] == "10-K")
    if not fys:
        return {"complete_years": 0, "latest_fy": None, "missing": ["no 10-K markdown"]}
    last = fys[-1]
    missing, complete = [], 0
    for y in range(last, last - years, -1):
        gaps = ([f"FY{y} 10-K"] if ("10-K", y) not in found else []) + \
               [f"{y} Q{q} 10-Q" for q in (1, 2, 3) if ("10-Q", y, q) not in found]
        if gaps:
            missing += gaps
        elif not missing:
            complete += 1     # consecutive complete years counting back from the latest
    return {"complete_years": complete, "latest_fy": last, "missing": missing}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticker", required=True); ap.add_argument("--years", type=int, default=10)
    a = ap.parse_args()
    t = a.ticker.upper()
    desktop = os.path.join(HOME, "Desktop")
    roots = [(os.path.join(settings.research_dir(), t), 0), (desktop, 6),
             (os.path.join(HOME, "Downloads"), 6), (os.path.join(HOME, "Documents"), 6), (HOME, 4)]
    cands, seen = [], set()
    for root, depth in roots:
        for d in manifest_dirs(root, depth):
            if d in seen or not is_for(d, t):
                continue
            seen.add(d)
            c = {"src": d, "model_dir": d if os.path.basename(d).upper() == t else os.path.dirname(d), **coverage(d, a.years)}
            cands.append(c)
            if c["complete_years"] >= a.years:
                print(json.dumps({"status": "found", **c, "candidates": cands}, indent=1))
                return
    best = max(cands, key=lambda c: c["complete_years"], default=None)
    print(json.dumps({"status": "gather", "candidates": cands, "best": best}, indent=1))


if __name__ == "__main__":
    main()
