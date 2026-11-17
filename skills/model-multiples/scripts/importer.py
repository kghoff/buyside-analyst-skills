"""Paid path (spec §3.1): read a FactSet / Bloomberg / CapIQ / Koyfin export (CSV or XLSX) into weekly rows of NTM
fundamentals. Code recognises the usual column names. When it can't, Claude proposes a mapping.json
({field: "header text"}), shows the user, and reruns with it. Units are taken as exported (EV, sales, EBITDA, GP and FCF
must share one unit, as every vendor's own multiples assume)."""
import csv
import datetime as dt
import json
import os
import re

import openpyxl

from multiples import fcf_yield, ratio

ALIASES = {
    "date": {"date", "as of", "as of date", "period", "dates"},
    "ticker": {"ticker", "symbol", "security"},
    "price": {"price", "close", "px last", "last price", "stock price", "price close"},
    "eps_ntm": {"eps", "ntm eps", "eps ntm", "eps (ntm)", "best eps", "eps - ntm", "fwd eps", "forward eps"},
    "sales_ntm": {"sales", "ntm sales", "sales ntm", "revenue ntm", "ntm revenue", "best sales", "revenue (ntm)"},
    "gp_ntm": {"gp", "gross profit", "ntm gp", "ntm gross profit", "best gross profit"},
    "ebitda_ntm": {"ebitda", "ntm ebitda", "best ebitda", "ebitda (ntm)"},
    "fcf_ltm": {"ltm fcf", "fcf ltm", "trailing fcf", "ttm fcf"},
    "fcf_ntm": {"ntm fcf", "fcf ntm", "best fcf", "fcf (ntm)"},
    "mcap": {"mcap", "market cap", "mkt cap", "cur mkt cap", "market capitalization"},
    "ev": {"ev", "enterprise value", "curr entp val", "tev", "total enterprise value"},
    "sp500_pe": {"s&p 500 ntm p/e", "spx ntm p/e", "s&p 500 p/e", "spx p/e"},
}
REQUIRED = ("date", "price", "eps_ntm")


def _norm(h):
    return " ".join(re.sub(r"[_.]", " ", str(h or "")).lower().split())


def detect(headers):
    """({field: column index}, unrecognised headers, missing required fields)."""
    m, unknown = {}, []
    for i, h in enumerate(headers):
        f = next((k for k, al in ALIASES.items() if _norm(h) in al and k not in m), None)
        if f:
            m[f] = i
        else:
            unknown.append(h)
    return m, unknown, [f for f in REQUIRED if f not in m]


def require(m, missing, path):
    if missing:
        raise SystemExit(f"{os.path.basename(path)}: no column for {', '.join(missing)}. Write mapping.json next to it "
                         '({"date": "<header>", "price": "<header>", "eps_ntm": "<header>", ...}) and rerun.')


def _date(v):
    if isinstance(v, dt.datetime):
        return v.date()
    if isinstance(v, dt.date):
        return v
    s = str(v).strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%y", "%m/%d/%Y", "%d-%b-%Y", "%d-%b-%y"):
        try:
            return dt.datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return None


_THOUSANDS = re.compile(r"^-?\d{1,3}(,\d{3})+(\.\d+)?$")
_EU = re.compile(r"^-?\d{1,3}(\.\d{3})+(,\d+)?$|^-?\d+(,\d+)?$")


def _num(v, semi=False, where=""):
    """Cell to float. Placeholders ("n/a", "--", "#N/A", "") are None. ';' files: ',' is the decimal mark and '.' the
    thousands mark. ',' files: a comma is valid only as a thousands separator; anything else stops the run."""
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        x = float(v)
        return x if x == x and abs(x) != float("inf") else None
    s = str(v if v is not None else "").strip().replace("$", "").strip()
    if not s:
        return None
    neg, pct = False, False
    if s.startswith("(") and s.endswith(")"):
        neg, s = True, s[1:-1].strip()
    if s.endswith("%"):
        pct, s = True, s[:-1].strip()
    if "," in s:
        if semi and _EU.match(s):
            s = s.replace(".", "").replace(",", ".")
        elif not semi and _THOUSANDS.match(s):
            s = s.replace(",", "")
        else:
            raise SystemExit(f"{where}: cannot read the number {v!r}: a comma is only valid as a thousands separator "
                             "(1,234.5) in a comma file, or as the decimal mark in a semicolon file.")
    elif semi and re.match(r"^-?\d{1,3}(\.\d{3})+$", s):
        s = s.replace(".", "")
    try:
        x = float(s)
    except ValueError:
        return None
    if x != x or abs(x) == float("inf"):
        return None
    x = -x if neg else x
    return x / 100 if pct else x


def _table(path):
    """(rows, semicolon-delimited?)"""
    if path.lower().endswith((".xlsx", ".xlsm")):
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        return [list(r) for r in wb.worksheets[0].iter_rows(values_only=True)], False
    with open(path, newline="", encoding="utf-8-sig") as f:
        text = f.read()
    try:
        d = csv.Sniffer().sniff(text[:4096], delimiters=",;").delimiter
    except csv.Error:
        d = ","
    return list(csv.reader(text.splitlines(), delimiter=d)), d == ";"


def _symbol(v):
    return re.split(r"[\s\-/.]+", str(v or "").strip().upper())[0]


def _duplicates(headers):
    seen, dup = {}, []
    for h in headers:
        f = next((k for k, al in ALIASES.items() if _norm(h) in al), None)
        if f and f in seen:
            dup.append((f, seen[f], h))
        elif f:
            seen[f] = h
    return dup


class Rows(list):
    """Weekly rows; .skipped counts data rows dropped for an unparseable date (report it, never hide it)."""
    skipped = 0


def load(path, mapping=None, ticker=None):
    """Weekly rows (last observation of each ISO week), oldest first. mapping: {field: header text} override.
    ticker: pick one symbol out of a multi-ticker file (case-insensitive; "ABT US Equity" matches "ABT")."""
    name = os.path.basename(path)
    raw, semi = _table(path)
    t = [r for r in raw if any(c not in (None, "") for c in r)]
    if mapping and "date" not in mapping:
        raise SystemExit(f'{name}: mapping.json must name the "date" column ({{"date": "<header>", ...}}).')
    if mapping:
        hi = next((i for i, r in enumerate(t) if str(mapping.get("date")) in [str(c) for c in r]), None)
    else:
        hi = next((i for i, r in enumerate(t) if detect(r)[0].get("date") is not None), None)
    if hi is None:
        require({}, list(REQUIRED), path)
    headers = t[hi]
    if mapping:
        bad = [h for h in mapping.values() if h not in headers]
        if bad:
            raise SystemExit(f"{os.path.basename(path)}: mapping.json names header(s) not in the file: "
                             f"{', '.join(map(str, bad))}. Headers found: {', '.join(map(str, headers))}.")
        m = {f: headers.index(h) for f, h in mapping.items()}
        missing = [f for f in REQUIRED if f not in m]
    else:
        m, _, missing = detect(headers)
        for f, h1, h2 in _duplicates(headers):
            raise SystemExit(f"{name}: two columns both look like {f}: {h1!r} and {h2!r}. Pick one in mapping.json "
                             f'({{"{f}": "{h1}"}} or {{"{f}": "{h2}"}}) and rerun.')
    require(m, missing, path)
    body = t[hi + 1:]
    if "ticker" in m:
        syms = {_symbol(r[m["ticker"]]) for r in body if m["ticker"] < len(r) and r[m["ticker"]] not in (None, "")}
        if len(syms) > 1:
            if not ticker:
                raise SystemExit(f"{name}: holds several tickers ({', '.join(sorted(syms))}). Rerun with the one you "
                                 "want.")
            want = _symbol(ticker)
            body = [r for r in body if m["ticker"] < len(r) and _symbol(r[m["ticker"]]) == want]
    weeks, skipped = {}, 0
    for n, r in enumerate(body, 1):
        d = _date(r[m["date"]]) if m["date"] < len(r) else None
        if d is None:
            skipped += 1
            continue
        rec = {"date": d, **{f: ((r[i] if i < len(r) else None) if f == "ticker" else _num(r[i] if i < len(r) else None, semi, f"{name} data row {n}, column {headers[i]!r}"))
                             for f, i in m.items() if f != "date"}}
        k = d.isocalendar()[:2]
        if all(v is None for f, v in rec.items() if f not in ("date", "ticker")) and k in weeks:
            continue
        if k not in weeks or weeks[k]["date"] < d:
            weeks[k] = rec
    out = Rows(weeks[k] for k in sorted(weeks))
    out.skipped = skipped
    return out


def multiples(r):
    g = r.get
    return {"pe": ratio(g("price"), g("eps_ntm")), "ev_rev": ratio(g("ev"), g("sales_ntm")),
            "ev_gp": ratio(g("ev"), g("gp_ntm")), "ev_ebitda": ratio(g("ev"), g("ebitda_ntm")),
            "fcf_yield": fcf_yield(g("fcf_ltm"), g("mcap")), "fcf_yield_ntm": fcf_yield(g("fcf_ntm"), g("mcap"))}


def mapping_for(path):
    p = os.path.join(os.path.dirname(path), "mapping.json")
    return json.load(open(p)).get(os.path.basename(path)) if os.path.exists(p) else None
