"""Step 8b - write section 10 (the appendix) from the work files; no agent writes it.

usage: python3 appendix.py --src <ticker folder>     (writes <Street Research>/sections/10-appendix.md)"""
import argparse, glob, os

from p2cites import canon
from p2common import STANCES, load, phase_dir, read_csv, work_dir


def _cell(s):
    # '[...]' would print as a footnote in the PDF, so brackets in page titles become parentheses
    return (s or "").replace("|", "/").replace("\n", " ").replace("[", "(").replace("]", ")").strip()


def build(src):
    w = work_dir(src)
    run = load(os.path.join(w, "run.json"), {})
    fetched, searches = [], []
    for d in sorted(glob.glob(os.path.join(w, "research", "*"))):
        rid = os.path.basename(d)
        if os.path.exists(os.path.join(d, "fetched.csv")):
            fetched += [dict(r, by=rid) for r in read_csv(os.path.join(d, "fetched.csv"))[1]]
        if os.path.exists(os.path.join(d, "searches.txt")):
            searches += [(rid, q.strip()) for q in open(os.path.join(d, "searches.txt"), encoding="utf-8-sig") if q.strip()]
    pages = {}                                   # one row per page: repeat fetches and retries list it once, ok wins
    for r in fetched:
        key = canon(r["url"])
        if key not in pages or (r["status"] == "ok" and pages[key]["status"] != "ok"):
            pages[key] = r
    ok = [r for r in pages.values() if r["status"] == "ok"]
    bad = [r for r in pages.values() if r["status"] != "ok"]
    def table(head, rows):
        return ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)] + rows if rows else ["None."]

    L = ["## 10 Appendix", "", f"### 10.1 Sources read ({len(run.get('sellside', []))} sell-side reports, {len(ok)} web pages)",
         "", "**Sell-side reports (Sellside Research folder)**", ""]
    L += table(["Date", "Tier", "Firm", "Type", "File"],
               [f"| {_cell(s['date'])} | {_cell(str(s.get('tier') or ''))} | {_cell(s['firm'])} | {_cell(s['type'])} | {_cell(s['label'])} |"
                for s in run.get("sellside", [])])
    L += ["", "**Web pages**", ""]
    L += table(["Published", "Title", "URL"], [f"| {_cell(r['published']) or 'undated'} | {_cell(r['title'])} | {_cell(r['url'])} |"
                                               for r in sorted(ok, key=lambda r: r["published"] or "")])
    L += ["", f"### 10.2 Search log ({len(searches)} searches)", ""]
    L += table(["Researcher", "Query"], [f"| {rid} | {_cell(q)} |" for rid, q in searches])
    L += ["", f"### 10.3 Blocked or failed pages ({len(bad)})", ""]
    L += table(["Status", "Title", "URL"], [f"| {_cell(r['status'])} | {_cell(r['title'])} | {_cell(r['url'])} |" for r in bad])
    path = os.path.join(w, "ledger_marked.csv")
    if os.path.exists(path):
        _, led = read_csv(path)
        L += ["", f"### 10.4 The claims ledger ({len(led)} company claims and what outside sources said)", ""]
        L += table(["Id", "Topic", "Company claim (from the filings research)", "Agrees", "Differs", "Adds", "Gap closed", "Outside sources"],
                   [f"| {_cell(r['id'])} | {_cell(r['topic'])} | {_cell(r['claim'])} | "
                    + " | ".join(_cell(r.get(k)) or "0" for k in STANCES) + f" | {_cell(r['marks_summary'])} |" for r in led])
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    src = ap.parse_args().src
    out = os.path.join(phase_dir(src), "sections", "10-appendix.md")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    open(out, "w", encoding="utf-8").write(build(src))
    print("wrote", out)
