"""Fetch what each company in peers.json needs (Step 4 of the skill). Cached: reruns fetch only what's missing.

usage: python3 fetch.py --work W --model M.xlsx
- every company: W/sec/<T>.json (filing list, fiscal-year ends) via sec_fetch.mjs
- consolidated source "xbrl" (and segment peers without a research model): <model dir>/Industry P&L/peers/<T>/xbrl.json
  from the separate edgar-xbrl-financials tool (github.com/kghoff/edgar-xbrl-financials). Its path is the xbrl_cli
  setting; the IPNL_XBRL_CLI environment variable overrides it
- segment peers: 10-K Markdown from <research_dir>/<T>/10-Ks/_md if it has the years, else downloaded into
  peers/<T>/10-K/_md
Writes W/fetch.json: {ticker: {"sec", "xbrl", "tenk_md": [paths]}}."""
import argparse
import glob
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "..", "..", "lib"))
import settings  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))


def xbrl_cli():
    """The edgar-xbrl-financials command line tool; stops with a plain message when it is not installed."""
    cli = os.environ.get("IPNL_XBRL_CLI") or settings.xbrl_cli()
    if not os.path.exists(cli):
        raise SystemExit("model-industry needs edgar-xbrl-financials: clone github.com/kghoff/edgar-xbrl-financials "
                         f"and set xbrl_cli in {settings.path()} (looked for {cli})")
    return cli


def research_md(ticker):
    return sorted(glob.glob(os.path.join(settings.research_dir(), ticker, "10-Ks", "_md", "*10-K*.md")))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True)
    ap.add_argument("--model", required=True)
    a = ap.parse_args()
    P = json.load(open(os.path.join(a.work, "peers.json")))
    peers_dir = os.path.join(os.path.dirname(os.path.abspath(a.model)), "Industry P&L", "peers")
    os.makedirs(os.path.join(a.work, "sec"), exist_ok=True)
    out = {}
    for c in P["companies"]:
        T = c["ticker"].upper()
        rec = out[T] = {"sec": os.path.join(a.work, "sec", f"{T}.json"), "xbrl": None, "tenk_md": []}
        pdir = os.path.join(peers_dir, T)
        need_md = bool(c.get("segment"))
        md = research_md(T) if need_md else []
        args = ["node", os.path.join(HERE, "sec_fetch.mjs"), T, rec["sec"]]
        if need_md and len(md) < 10:
            args += ["--tenk", "10", "--md-dir", os.path.join(pdir, "10-K", "_md")]
        if not os.path.exists(rec["sec"]) or "--tenk" in args:
            subprocess.run(args, check=True)
        if need_md:
            rec["tenk_md"] = md if len(md) >= 10 else json.load(open(rec["sec"]))["md"]
        if c["source"] == "xbrl":
            rec["xbrl"] = os.path.join(pdir, "xbrl.json")
            if not os.path.exists(rec["xbrl"]):
                os.makedirs(pdir, exist_ok=True)
                tmp = rec["xbrl"] + ".tmp"          # a failed pull must not leave a bad cached file
                try:
                    with open(tmp, "w") as f:
                        subprocess.run(["node", xbrl_cli(), T, "--json"], check=True, stdout=f, stderr=subprocess.DEVNULL)
                    os.replace(tmp, rec["xbrl"])
                finally:
                    if os.path.exists(tmp):
                        os.remove(tmp)
    json.dump(out, open(os.path.join(a.work, "fetch.json"), "w"), indent=1)
    print(json.dumps({t: {"xbrl": bool(r["xbrl"]), "tenk_md": len(r["tenk_md"])} for t, r in out.items()}, indent=1))


if __name__ == "__main__":
    main()
