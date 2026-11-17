"""Core peers' point-in-time TTM P/E history (free path, spec §3.1): quarterly diluted EPS from the edgar-xbrl-
financials JSON, weekly closes from stooq. Peers have no release dates in the model, so a quarter counts as known 45
days after its end (Q1-Q3) or 90 days (Q4): the SEC 10-Q / 10-K deadlines for non-accelerated filers, the latest of
any filer type, since a peer's filer status is unknown. So a quarter is never used before it was public. Conservative:
never hindsight, sometimes a few weeks late. Told to the user as a judgment call."""
import bisect
import calendar
import csv
import datetime as dt
import re

LAG = {1: 45, 2: 45, 3: 45, 4: 90}


def _month_end(y, m):
    return dt.date(y, m, calendar.monthrange(y, m)[1])


def quarter_ends(x):
    """{(fiscal year, quarter): period end}, stepping back three months a quarter from the tool's latest quarter."""
    end = dt.date.fromisoformat(x["ttm"]["endDate"])
    m = re.match(r"Q([1-4]) FY(\d{4})", x["ttm"]["quarter"])
    q, fy, y, mo = int(m[1]), int(m[2]), end.year, end.month
    out = {}
    for _ in range(120):
        out[(fy, q)] = _month_end(y, mo)
        q, fy = (q - 1, fy) if q > 1 else (4, fy - 1)
        mo, y = (mo - 3, y) if mo > 3 else (mo + 9, y - 1)
    return out


def eps_quarters(x):
    """[{fy, q, end, known, eps}] oldest first, one row per quarter the tool lists. eps is None when the tool has no
    diluted EPS for it: the row stays so the gap is visible and ttm() refuses to span it."""
    ends = quarter_ends(x)
    out = []
    for fy, qd in x["quarterly"].items():
        for qn, parts in qd.items():
            k = (int(fy), int(qn[1]))
            if k not in ends:
                raise ValueError(f"quarter {qn} FY{fy} is outside the {len(ends)} quarters counted back from the latest")
            v = parts.get("income", {}).get("diluted_earnings_per_share")
            out.append({"fy": k[0], "q": k[1], "end": ends[k], "known": ends[k] + dt.timedelta(days=LAG[k[1]]), "eps": v})
    return sorted(out, key=lambda r: r["end"])


def ttm(quarters):
    """Each quarter with the sum of it and the three before, only when the four are consecutive and all have EPS
    (build writes SUM of 4 rows, or NA() otherwise: same rule here)."""
    out = []
    for i, r in enumerate(quarters):
        four = quarters[i - 3:i + 1] if i >= 3 else []
        ok = (len(four) == 4
              and all((four[j + 1]["end"] - four[j]["end"]).days in range(88, 94) for j in range(3))
              and all(f["eps"] is not None for f in four))
        out.append({**r, "ttm": sum(f["eps"] for f in four) if ok else None, "consecutive": ok})
    return out


def load_closes(path):
    """[(date, close)] ascending from a stooq daily CSV. Duplicate dates keep the last row in the file."""
    by_date = {}
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            try:
                by_date[dt.date.fromisoformat(r["Date"])] = float(r["Close"])
            except (KeyError, ValueError, TypeError):
                continue
    if not by_date:
        raise SystemExit(f"{path}: no Date/Close rows; is this a stooq daily CSV? (expected header Date,Open,High,Low,Close,Volume)")
    return sorted(by_date.items())


def close_on(closes, day):
    i = bisect.bisect_right(closes, day, key=lambda r: r[0])
    return closes[i - 1][1] if i else None
