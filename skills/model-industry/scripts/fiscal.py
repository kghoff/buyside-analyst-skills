"""Fiscal years -> calendar years. A fiscal year belongs to the calendar year holding most of its months
(house default). End date minus 15 days handles 52/53-week years ending in the first days of a month."""
import datetime as dt


def calendar_year(end_iso):
    d = dt.date.fromisoformat(end_iso) - dt.timedelta(days=15)
    return d.year if d.month >= 6 else d.year - 1


def fy_ends(sec, fys):
    """{fy: period end} for the fiscal years wanted. sec = sec/<T>.json from sec_fetch.mjs. Years with no 10-K in
    the list (older than the SEC listing, or a missing fiscal tag) use the fiscal-year-end month/day, with the end
    year assumed to be the fiscal-year label."""
    known = {f["fy"]: f["reportDate"] for f in sec.get("filings", []) if f.get("fy") and f.get("reportDate")}
    mmdd = sec.get("fiscalYearEnd") or "1231"
    return {fy: known.get(fy) or f"{fy}-{mmdd[:2]}-{mmdd[2:]}" for fy in fys}
