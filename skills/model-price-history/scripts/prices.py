"""Find and check the stooq price files (Step 4 of the skill, after the user downloads them).

usage: python3 prices.py --model M.xlsx --src <gather folder> --stock dxcm --etf xhe --mom mtum --out W/prices.json
Looks for <ticker>_us_d.csv in: the model's folder, its "Price Data" subfolder, the gather folder, ~/Downloads (newest
wins) and MOVES each into "<model folder>/Price Data/", deleting other same-named copies there, so after a run the
price files exist only in Price Data (house default). Checks:
- columns Date..Close, coverage: the stock and SPY must reach back to the warm-up start, all files to the same end
- factor dates missing from the stock/SPY trading days (filled with the prior close in the model, and listed)
- stale days (open = high = low = close) and |daily return| > 40% (possible split stooq missed)
Exit code 1 when a file is missing or unusable; the JSON says why."""
import argparse
import datetime as dt
import json
import os
import shutil

import pandas as pd

import engine
import modmap


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
    ap.add_argument("--src")
    ap.add_argument("--stock", required=True)
    ap.add_argument("--etf", required=True)
    ap.add_argument("--mom", default="mtum")
    ap.add_argument("--out", required=True)
    ap.add_argument("--no-move", "--no-copy", dest="no_move", action="store_true", help="leave the files where they are (tests)")
    a = ap.parse_args()
    mdir = os.path.dirname(os.path.abspath(a.model))
    keep = os.path.join(mdir, "Price Data")
    dirs = [mdir, keep] + ([a.src] if a.src else []) + [os.path.expanduser("~/Downloads")]
    tick = {"stock": a.stock, "spy": "spy", "etf": a.etf, "mom": a.mom}
    out = {"files": {}, "problems": [], "notes": []}
    paths = {k: find(t, dirs) for k, t in tick.items()}
    for k, p in paths.items():
        if not p:
            out["problems"].append(f"{tick[k].lower()}_us_d.csv not found in {', '.join(dirs)}")
    if out["problems"]:
        print(json.dumps(out, indent=1)); json.dump(out, open(a.out, "w"), indent=1); raise SystemExit(1)
    if not a.no_move:
        # Rule: after a run the price files live only in "<model folder>/Price Data/". Move the newest
        # copy there and delete any other same-named copies in the searched folders (Downloads, model folder, gather).
        os.makedirs(keep, exist_ok=True)
        for k, p in paths.items():
            name = os.path.basename(p)
            dst = os.path.join(keep, name)
            if os.path.abspath(p) != os.path.abspath(dst):
                shutil.move(p, dst)
                out["notes"].append(f"moved {p} -> {dst}")
                paths[k] = dst
            for d in dirs:
                old = os.path.join(d, name)
                if os.path.abspath(d) != os.path.abspath(keep) and os.path.isfile(old):
                    os.remove(old)
                    out["notes"].append(f"deleted older copy {old}")
    first_fy = min(p["year"] for p in modmap.read(a.model)["periods"] if p["kind"] == "fy")
    stock, spy = engine.load_close(paths["stock"]), engine.load_close(paths["spy"])
    dates, b = engine.daily_dates(stock, spy, first_fy)
    base_day = pd.Timestamp(first_fy - 1, 12, 31)
    out["daily"] = {"first": dates[0].date().isoformat(), "base": dates[b].date().isoformat(),
                    "last": dates[-1].date().isoformat(), "rows": len(dates)}
    if dates[b] < base_day - pd.Timedelta(days=7) or dates[b] > base_day:
        out["notes"].append(f"Index base is {dates[b].date()} instead of the last trading day of {first_fy - 1}: the "
                            f"stock's history starts {stock.index.min().date()}, so the 252-day warm-up starts there.")
    for k, p in paths.items():
        res = check(tick[k], p, dates if k in ("etf", "mom") else None)
        res["downloaded"] = dt.date.fromtimestamp(os.path.getmtime(p)).isoformat()
        out["files"][k] = res
        if not res["ok"]:
            out["problems"].append(f"{tick[k]}: {res['why']}")
            continue
        if res["last"] < out["daily"]["last"]:
            out["notes"].append(f"{tick[k]} ends {res['last']}, before the stock/SPY end {out['daily']['last']}; "
                                "its last closes are carried forward. Re-download it.")
        if k in ("etf", "mom") and pd.Timestamp(res["first"]) > dates[b]:
            out["notes"].append(f"{tick[k].upper()} history starts {res['first']}, after the index base: the 3-factor "
                                "chart starts once a full 252-day window exists (about a year later).")
        for d, x in res["big_moves"]:
            out["notes"].append(f"{tick[k]} moved {x:+.0%} on {d}: check for a split stooq missed (news can explain it).")
    json.dump(out, open(a.out, "w"), indent=1)
    print(json.dumps(out, indent=1))
    raise SystemExit(1 if out["problems"] else 0)


if __name__ == "__main__":
    main()
