"""(Copied from model-price-history, Nov 2026; trimmed to find/check plus a core-peer CLI. Keep find/check in sync.)
Multiples deliberately reads Close only (P/E uses the traded price) and skips the Adj Close / source checks that
model-price-history's copy has.

usage: python3 prices.py --model M.xlsx --tickers ABT MDT ... [--src DIR]
Looks for <ticker>_us_d.csv in: the model's folder, its "Price Data" subfolder, --src and ~/Downloads (newest wins).
A file found outside "<model folder>/Price Data/" is copied (not moved) into it. Each file is checked (columns,
date range, |daily return| > 40%). Prints a JSON list of results; a missing ticker is reported as
not found. Exit code 1 when any file is missing or unusable."""
import argparse
import json
import os
import shutil

import pandas as pd


def find(ticker, dirs):
    name = f"{ticker.lower()}_us_d.csv"
    hits = [os.path.join(d, name) for d in dirs if os.path.isfile(os.path.join(d, name))]
    return max(hits, key=os.path.getmtime) if hits else None


def check(ticker, path, dates=None):
    df = pd.read_csv(path)
    need = {"Date", "Open", "High", "Low", "Close"}
    if not need <= set(df.columns):
        return {"ticker": ticker, "path": path, "ok": False, "why": f"columns {list(df.columns)}; need {sorted(need)}"}
    df["Date"] = pd.to_datetime(df["Date"])
    df = df.dropna(subset=["Close"]).sort_values("Date")
    s = df.set_index("Date")["Close"]
    r = s.pct_change()
    big = [(d.date().isoformat(), round(float(x), 3)) for d, x in r.items() if abs(x) > 0.40]
    res = {"ticker": ticker, "path": path, "ok": True, "first": s.index.min().date().isoformat(),
           "last": s.index.max().date().isoformat(), "rows": len(s), "big_moves": big}
    if dates is not None:
        win = df[(df["Date"] >= dates[0]) & (df["Date"] <= dates[-1])]
        res["stale_days"] = int(((win.Open == win.High) & (win.High == win.Low) & (win.Low == win.Close)).sum())
        have = set(s.index)
        res["filled_dates"] = [d.date().isoformat() for d in dates if d >= s.index.min() and d not in have]
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--tickers", nargs="+", required=True)
    ap.add_argument("--src")
    a = ap.parse_args()
    mdir = os.path.dirname(os.path.abspath(a.model))
    keep = os.path.join(mdir, "Price Data")
    dirs = [mdir, keep] + ([a.src] if a.src else []) + [os.path.expanduser("~/Downloads")]
    results = []
    for t in dict.fromkeys(x.lower() for x in a.tickers):
        p = find(t, dirs)
        if not p:
            results.append({"ticker": t, "ok": False, "why": "not found"})
            continue
        dst = os.path.join(keep, os.path.basename(p))
        if os.path.abspath(p) != os.path.abspath(dst):
            os.makedirs(keep, exist_ok=True)
            shutil.copy2(p, dst)
            p = dst
        try:
            results.append(check(t, p))
        except Exception as e:
            results.append({"ticker": t, "path": p, "ok": False, "why": str(e)})
    print(json.dumps(results, indent=1))
    raise SystemExit(0 if all(r["ok"] for r in results) else 1)


if __name__ == "__main__":
    main()
