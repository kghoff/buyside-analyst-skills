"""Fiscal period labels from period end dates, for any fiscal calendar.

Labels follow the model's convention: "Q4 26" for a quarter, "FY 26" for a year, each named by the fiscal year it
belongs to, which is named by the calendar year it ends in (a year ending April 2027 is FY 27). 52/53-week years that
end in the first week of a month count as the month before (a year ending 2 January 2027 is FY 26)."""
from datetime import date


def ym(d):
    y, m = d.year, d.month
    if d.day <= 7:
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return y, m


def fiscal(d, fye):
    """(fiscal year, quarter 1-4) of the period ending on date d, for a fiscal year ending in month fye."""
    y, m = ym(d)
    if ((fye - m) % 12) % 3 != 0:
        raise ValueError(f"period ending {d} is not a quarter end for a fiscal year ending in month {fye}")
    fy = y if m <= fye else y + 1
    q = 4 - round(((fye - m) % 12) / 3)
    return fy, q


def qlabel(d, fye):
    fy, q = fiscal(d, fye)
    return f"Q{q} {fy % 100:02d}"


def fylabel(d, fye):
    fy, _ = fiscal(d, fye)
    return f"FY {fy % 100:02d}"


def end_date(x):
    """Yahoo / JSON end dates: ISO strings ('2026-12-31T00:00:00.000Z') or 'YYYY-MM-DD'."""
    return date.fromisoformat(str(x)[:10])


def fye_month(snap):
    """Month the fiscal year ends, from Yahoo's current-year ('0y') period end; None when Yahoo has no estimates."""
    t = next((x for x in snap["yahoo"]["trend"] if x.get("period") == "0y" and x.get("endDate")), None)
    return ym(end_date(t["endDate"]))[1] if t else None
