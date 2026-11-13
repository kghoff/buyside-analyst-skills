"""Read the user's model (never written) into the long table the driver math and charts use; read the price history.

usage: python3 modeldata.py --model <TICKER_model.xlsx> --work <_work dir> --ticker DXCM --price-kind tab|csv --price <path>
MOD layout (model-historicals and the DXCM example model): period labels in row 2 ('Q1 15', 2015), section titles in column A,
line labels in column B, units in column C, data from column D. Analysis rows (% yoy, margins, bps...) and estimate
columns (E) are skipped: the filings research is history, and driver math recomputes what it needs.
Writes model_series.csv (metric, period, value, unit, source), model_rows.md (rows readers need not extract) and
price.csv (date, close, spy)."""
import argparse, csv, datetime, glob, os

import openpyxl
from openpyxl.utils import get_column_letter as L

from evaluate import ERR, Book
from periods import parse_period

ANALYSIS = {"% yoy", "% 2 year", "% qoq", "% margin", "bps yoy", "incremental margin", "% of sales", "ttm"}
COLS = ["metric", "period", "value", "unit", "source"]


def period_name(p):
    q, y, _ = p
    return f"FY{y}" if q == 0 else f"Q{q} {y}"


def _number(v, cached):
    """The evaluated value, or the workbook's cached value when the evaluator gave up (ERR)."""
    if v is ERR:
        v = cached
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def extract(model_path):
    wb = openpyxl.load_workbook(model_path)
    cache = openpyxl.load_workbook(model_path, data_only=True)["MOD"] if "MOD" in wb.sheetnames else None
    if "MOD" not in wb.sheetnames:
        raise SystemExit(f"{model_path} has no MOD tab")
    ws, book = wb["MOD"], Book(wb)
    cols = {c: parse_period(ws.cell(2, c).value) for c in range(4, ws.max_column + 1)}
    cols = {c: p for c, p in cols.items() if p and not p[2]}
    rows, section, sub, seen = [], "", "", set()

    def val(r, c):
        return _number(book.value("MOD", f"{L(c)}{r}"), cache.cell(r, c).value)

    for r in range(2, ws.max_row + 1):
        a, b, unit = ws.cell(r, 1).value, ws.cell(r, 2).value, ws.cell(r, 3).value
        if isinstance(a, str) and a.strip():
            section, sub = a.strip().rstrip(":"), ""
        if r == 2 or not isinstance(b, str) or not b.strip():
            if not (isinstance(b, str) and b.strip()):
                sub = ""
            continue
        low = b.strip().lower()
        if low in ANALYSIS or low.startswith("%") or low == "fcf conversion %":
            continue
        label = " ".join(b.split()).rstrip(":")
        if not any(val(r, c) is not None for c in cols):
            sub = label
            continue
        name = f"{section} | {sub} | {label}" if sub else f"{section} | {label}"
        if name in seen:
            name = f"{name} (row {r})"
        seen.add(name)
        for c, p in cols.items():
            v = val(r, c)
            if v is None:
                continue
            rows.append({"metric": name, "period": period_name(p), "value": v, "unit": unit or "",
                         "source": f"Model, MOD!{L(c)}{r}"})
    return rows


def rows_summary(rows):
    span = {}
    for r in rows:
        span.setdefault(r["metric"], []).append(r["period"])
    lines = ["# Rows already in the user's model", "", "Readers: don't extract these numbers again; the model has them.", ""]
    for m, ps in span.items():
        fys = sorted(p for p in ps if p.startswith("FY"))
        lines.append(f"- {m} ({fys[0]}–{fys[-1]})" if fys else f"- {m} (quarters only)")
    return "\n".join(lines) + "\n"


def price_from_tab(path):
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    if "Px Data" not in wb.sheetnames:
        return None
    out, started = [], False
    for row in wb["Px Data"].iter_rows(values_only=True):
        row = tuple(row) + (None, None, None)
        if not started:
            started = row[0] == "Date"
            continue
        d, px, spy = row[:3]
        if isinstance(d, (datetime.date, datetime.datetime)) and isinstance(px, (int, float)):
            day = d.date() if isinstance(d, datetime.datetime) else d
            out.append((day.isoformat(), px, spy if isinstance(spy, (int, float)) else None))
    return out


def _stooq(path):
    with open(path, newline="") as f:
        return {r["Date"]: float(r["Close"]) for r in csv.DictReader(f) if r.get("Close")}


def price_from_csv(folder, ticker):
    csvs = sorted(glob.glob(os.path.join(folder, "*.csv")))
    t = next(p for p in csvs if os.path.basename(p).lower().startswith(ticker.lower()))
    s = next((p for p in csvs if os.path.basename(p).lower().startswith("spy")), None)
    tk, spy = _stooq(t), (_stooq(s) if s else {})
    return [(d, tk[d], spy.get(d)) for d in sorted(tk)]


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--ticker", required=True)
    ap.add_argument("--price-kind", choices=["tab", "csv"], required=True)
    ap.add_argument("--price", required=True)
    a = ap.parse_args()
    os.makedirs(a.work, exist_ok=True)
    rows = extract(a.model)
    with open(os.path.join(a.work, "model_series.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, COLS)
        w.writeheader()
        w.writerows(rows)
    with open(os.path.join(a.work, "model_rows.md"), "w", encoding="utf-8") as f:
        f.write(rows_summary(rows))
    px = price_from_tab(a.price) if a.price_kind == "tab" else price_from_csv(a.price, a.ticker)
    with open(os.path.join(a.work, "price.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "close", "spy"])
        w.writerows(px)
    print(f"{len({r['metric'] for r in rows})} model rows, {len(rows)} values; {len(px)} price days")
