"""Which quarter this run reports, and the mode.

usage: python3 locate.py --model MODEL --src <research_dir>/<T> --ticker T --work <model dir>/_model_work/update
print: the first MOD quarter whose header ends in E has a release ('<YYYY> Q<n> <T> release *.md').
tenq:  the quarter before it has state.json with awaiting cells (or tenq_checked false) and its 10-Q exists.
none:  neither (reason says why)."""
import argparse
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from modmap import ModMap   # noqa: E402


def _fy(q):
    n, yy = q.rstrip("E").split()
    return 2000 + int(yy[:2]), n


def release_for(src, ticker, q):
    y, n = _fy(q)
    hits = sorted(glob.glob(os.path.join(src, "Press Releases", "_md", f"{y} {n} {ticker} release*.md")))
    return hits[-1] if hits else None


def tenq_for(src, ticker, q):
    y, n = _fy(q)
    p = os.path.join(src, "10-Qs", "_md", f"{ticker} {y} {n} 10-Q.md")
    return p if os.path.exists(p) else None


def locate(model, src, ticker, work):
    m = ModMap(model)
    fq = m.forecast_quarters()
    qs = [p for p in m.order if m.is_q(p)]
    last = qs[qs.index(fq[0]) - 1] if fq and qs.index(fq[0]) else (qs[-1] if qs and not fq else None)
    if last:
        sp = os.path.join(work, last.rstrip("E"), "state.json")
        if os.path.exists(sp):
            st = json.load(open(sp))
            tq = tenq_for(src, ticker, last)
            if not st.get("tenq_checked") and tq:
                return {"mode": "tenq", "quarter": last, "tenq": tq, "state": sp,
                        "release": release_for(src, ticker, last), "forecast_next": fq[0] if fq else None}
    if not fq:
        return {"mode": "none", "reason": "MOD has no forecast quarter (no row-2 header ending in E)"}
    rel = release_for(src, ticker, fq[0])
    if not rel:
        return {"mode": "none", "quarter": fq[0], "reason": f"no release for {fq[0]} in Press Releases/_md (run /collect-documents)"}
    return {"mode": "print", "quarter": fq[0], "release": rel, "tenq": tenq_for(src, ticker, fq[0]),
            "is_q4": fq[0].startswith("Q4"), "fy": m.fy_of(fq[0])}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True), ap.add_argument("--src", required=True)
    ap.add_argument("--ticker", required=True), ap.add_argument("--work", required=True)
    a = ap.parse_args()
    print(json.dumps(locate(a.model, a.src, a.ticker, a.work), indent=1))
