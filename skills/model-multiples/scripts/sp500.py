"""The S&P 500's trailing P/E by month, from multpl.com (free path, spec §3.1). Trailing, so the stock's own trailing
P/E is compared like with like. Cached per day in the work folder. The latest months are multpl's estimates (marked †);
they're kept and flagged.

usage: python3 sp500.py --work W   (prints rows fetched, first and last date)"""
import argparse
import datetime as dt
import json
import os
import re
import urllib.request

URL = "https://www.multpl.com/s-p-500-pe-ratio/table/by-month"
# The saved page puts each cell on several lines, so every gap is \s*. The value cell holds an optional
# <abbr title="Estimate">†</abbr> flag or an &#x2002; space, then the number.
ROW = re.compile(r'<td>\s*([A-Z][a-z]{2} \d{1,2}, \d{4})\s*</td>\s*<td>\s*(<abbr title="Estimate">[^<]*</abbr>)?'
                 r'\s*(?:&#x2002;)?\s*([\d.]+)\s*</td>')


def parse(html):
    rows = [{"date": dt.datetime.strptime(d, "%b %d, %Y").date(), "pe": float(v), "estimate": bool(est)}
            for d, est, v in ROW.findall(html)]
    if len(rows) < 120:
        raise SystemExit(f"multpl: found {len(rows)} monthly P/E rows at {URL}; expected hundreds. The page layout may "
                         "have changed. The S&P-relative chart can't be built until sp500.py's parser is updated.")
    return sorted(rows, key=lambda r: r["date"])


def save(path, rows, asof):
    json.dump({"asof": asof, "source": URL, "rows": [{**r, "date": r["date"].isoformat()} for r in rows]},
              open(path, "w"), indent=0)


def load_cached(path, asof):
    if not os.path.exists(path):
        return None
    d = json.load(open(path))
    if d["asof"] != asof:
        return None
    return [{**r, "date": dt.date.fromisoformat(r["date"])} for r in d["rows"]]


def get(work, asof=None):
    asof = asof or dt.date.today().isoformat()
    path = os.path.join(work, "sp500.json")
    rows = load_cached(path, asof)
    if rows is None:
        req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0 (research script)"})
        rows = parse(urllib.request.urlopen(req, timeout=60).read().decode("utf-8"))
        save(path, rows, asof)
    return rows


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True)
    a = ap.parse_args()
    r = get(a.work)
    print(json.dumps({"rows": len(r), "first": r[0]["date"].isoformat(), "last": r[-1]["date"].isoformat()}))
