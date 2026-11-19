"""Which quarter this run reports, and the mode.

usage: python3 locate.py --model MODEL --src <research_dir>/<T> --ticker T --work <model dir>/_model_work/update
print: the first MOD quarter whose header ends in E has a full release ('<YYYY> Q<n> <T> release *.md' with an
       income statement AND a balance sheet; the newest such file). A January 'preliminary results' release (revenue
       only, same file-name pattern) is not a print: mode none, reason "preliminary release only". `releases` lists
       every file for the quarter with financial tables (the chosen one first, then e.g. Exhibit 99.2).
tenq:  the quarter before it has state.json with awaiting cells (or tenq_checked false) and its filing exists: the
       10-Q, or for a Q4 the 10-K ('10-Ks/_md/<T> <FY> 10-K.md'). Key `filing` (`tenq` is the same path, kept as an alias).
none:  neither (reason says why)."""
import argparse
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from modmap import ModMap   # noqa: E402
import release              # noqa: E402

FINANCIAL = {"is", "bs", "cf", "recon"}


def _fy(q):
    n, yy = q.rstrip("E").split()
    return 2000 + int(yy[:2]), n


def _kinds(path):
    return {t["kind"] for t in release.parse_files([path])["tables"]}


def releases_for(src, ticker, q):
    """(the newest full release: income statement and balance sheet, or None; every file for the quarter with
    financial tables, that one first; True when files exist but none is a full release)."""
    y, n = _fy(q)
    hits = glob.glob(os.path.join(src, "Press Releases", "_md", f"{y} {n} {ticker} release*.md"))
    date = lambda p: (re.findall(r"\d{4}-\d\d-\d\d", os.path.basename(p)) or [""])[-1]
    hits = sorted(hits, key=lambda p: (date(p), p), reverse=True)
    kinds = {p: _kinds(p) for p in hits}
    full = next((p for p in hits if {"is", "bs"} <= kinds[p]), None)
    rels = ([full] if full else []) + [p for p in hits if p != full and kinds[p] & FINANCIAL]
    return full, rels, bool(hits) and not full


def release_for(src, ticker, q):
    return releases_for(src, ticker, q)[0]


def filing_for(src, ticker, q):
    """The quarter's 10-Q, or the 10-K for a Q4 (there is no Q4 10-Q)."""
    y, n = _fy(q)
    if n == "Q4":
        p = os.path.join(src, "10-Ks", "_md", f"{ticker} {y} 10-K.md")
    else:
        p = os.path.join(src, "10-Qs", "_md", f"{ticker} {y} {n} 10-Q.md")
    return p if os.path.exists(p) else None


tenq_for = filing_for


def locate(model, src, ticker, work):
    m = ModMap(model)
    fq = m.forecast_quarters()
    qs = [p for p in m.order if m.is_q(p)]
    last = qs[qs.index(fq[0]) - 1] if fq and qs.index(fq[0]) else (qs[-1] if qs and not fq else None)
    if last:
        sp = os.path.join(work, last.rstrip("E"), "state.json")
        if os.path.exists(sp):
            st = json.load(open(sp))
            tq = filing_for(src, ticker, last)
            if not st.get("tenq_checked") and tq:
                return {"mode": "tenq", "quarter": last, "filing": tq, "tenq": tq, "state": sp,
                        "release": release_for(src, ticker, last), "forecast_next": fq[0] if fq else None}
    if not fq:
        return {"mode": "none", "reason": "MOD has no forecast quarter (no row-2 header ending in E)"}
    rel, rels, prelim = releases_for(src, ticker, fq[0])
    if prelim:
        return {"mode": "none", "quarter": fq[0], "reason": "preliminary release only: no income statement and balance "
                f"sheet in the {fq[0]} release files yet (run /collect-documents after the full release)"}
    if not rel:
        return {"mode": "none", "quarter": fq[0], "reason": f"no release for {fq[0]} in Press Releases/_md (run /collect-documents)"}
    f = filing_for(src, ticker, fq[0])
    return {"mode": "print", "quarter": fq[0], "release": rel, "releases": rels, "filing": f, "tenq": f,
            "is_q4": fq[0].startswith("Q4"), "fy": m.fy_of(fq[0])}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True), ap.add_argument("--src", required=True)
    ap.add_argument("--ticker", required=True), ap.add_argument("--work", required=True)
    a = ap.parse_args()
    print(json.dumps(locate(a.model, a.src, a.ticker, a.work), indent=1))
