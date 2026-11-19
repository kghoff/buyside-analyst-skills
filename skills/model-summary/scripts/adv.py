# skills/model-summary/scripts/adv.py
"""3-month average daily volume for the cap table, in millions of shares. Routes, in order:
1. multiples:  the Multiples comp sheet's subject row (Yahoo's 3-month average, already in the model): a link.
2. price_data: the mean volume of the last 63 trading days in Px Data's source file,
               <research_dir>/<T>/Price Data/<t>_us_d.csv.
3. yahoo:      fetch_prices.mjs into the work folder.
4. work_csv:   a CSV with the same columns (Date, ..., Volume) already in the work folder, placed there by hand.
Routes 2-4 count only when the file's last date is Px Data's last date or later (the day of SUM's price).
Returns {"route", "ref" (route 1) | "value", "note"}; stops when every route fails."""
import csv
import datetime as dt
import os
import subprocess

import openpyxl

N = 63
HERE = os.path.dirname(os.path.realpath(__file__))


def from_csv(path):
    with open(path) as f:
        rows = [r for r in csv.DictReader(f) if (r.get("Volume") or "0") not in ("", "0")]
    if len(rows) < N:
        return None
    last = rows[-N:]
    return {"value": sum(float(r["Volume"]) for r in last) / N / 1e6, "first": last[0]["Date"],
            "last": last[-1]["Date"]}


def px_last(model):
    wb = openpyxl.load_workbook(model, read_only=True)
    try:
        ws = wb["Px Data"]
        last = None
        for (a,) in ws.iter_rows(min_row=5, max_col=1, values_only=True):
            if isinstance(a, (dt.datetime, dt.date)):
                last = a
    finally:
        wb.close()
    return (last.date() if isinstance(last, dt.datetime) else last).isoformat() if last else None


def yahoo(work, ticker):
    r = subprocess.run(["node", os.path.join(HERE, "fetch_prices.mjs"), work, ticker], capture_output=True, text=True)
    return r.returncode == 0


def _try(path, route, last):
    if not os.path.exists(path):
        return None
    r = from_csv(path)
    if not r or (last and r["last"] < last):
        return None
    return {"route": route, "value": r["value"],
            "note": f"3-month ADV: mean volume of the last {N} trading days, {r['first']} to {r['last']}, from "
                    f"{path} ({route.replace('_', ' ')}), in millions of shares."}


def adv(model, mult_ref, research_dir, ticker, work, fetch=yahoo):
    if mult_ref:
        return {"route": "multiples", "ref": mult_ref,
                "note": "3-month ADV: Yahoo's 3-month average daily volume on the Multiples comp sheet's subject "
                        "row (raw shares there; shown here in millions). As of the last /model-multiples run."}
    last = px_last(model)
    t = ticker.lower()
    got = _try(os.path.join(research_dir, ticker, "Price Data", f"{t}_us_d.csv"), "price_data", last)
    if got:
        return got
    wcsv = os.path.join(work, f"{t}_us_d.csv")
    os.makedirs(work, exist_ok=True)
    hand = os.path.exists(wcsv)
    if fetch(work, ticker):
        got = _try(wcsv, "yahoo", last)
        if got:
            return got
    if hand:
        got = _try(wcsv, "work_csv", last)
        if got:
            return got
    raise SystemExit(f"model-summary: no 3-month ADV. The Multiples comp sheet has none, Px Data's source file is "
                     f"missing or older than {last}, and Yahoo failed. Put a daily CSV (Date,Open,High,Low,Close,"
                     f"Volume) ending {last} or later at {wcsv} and rerun.")
