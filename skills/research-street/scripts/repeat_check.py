"""Step 10a - find paragraphs in the street research report that repeat the filings research, and count the words.

usage: python3 repeat_check.py --src <ticker folder> [--report <sections dir or file>]
A paragraph (30+ words once citations and markup are removed) is flagged when 30% or more of its 6-word runs also
appear in the filings research report; a table when 60% or more. The appendix and cover files are neither checked nor counted
(words target 15,000-25,000).
Writes _work/repeat.md; exits 1 if anything is flagged."""
import argparse, glob, os, re

from p2common import load, phase_dir, work_dir   # first: puts research-filings' scripts on sys.path
from filter import blocks   # research-filings' paragraph splitter

K, MIN_WORDS, LIMIT, TABLE_LIMIT = 6, 30, 0.3, 0.6   # scorecard tables legitimately restate the company view in a column
CITE = re.compile(r"\[([^\[\]\n]+?)\](?!\()")


def words(text):
    text = re.sub(r"<[^>]+>|[*_`>|#]", " ", CITE.sub(" ", text))
    return re.findall(r"[a-z0-9]+(?:[.,'’-][a-z0-9]+)*", text.lower())


def runs(ws):
    return {" ".join(ws[i:i + K]) for i in range(len(ws) - K + 1)}


def flagged(md, p1_runs):
    out = []
    for kind, text in blocks(md):
        if kind == "heading":
            continue
        ws = words(text)
        if len(ws) < MIN_WORDS:
            continue
        r = runs(ws)
        share = len(r & p1_runs) / len(r)
        if share >= (TABLE_LIMIT if kind == "table" else LIMIT):
            out.append({"share": round(share, 2), "text": text[:300]})
    return out


def check(report, phase1_report):
    p1 = runs(words(open(phase1_report, encoding="utf-8").read()))
    files = sorted(glob.glob(os.path.join(report, "*.md"))) if os.path.isdir(report) else [report]
    res, total = {}, 0
    for f in files:
        text = open(f, encoding="utf-8").read()
        name = os.path.basename(f)
        if "appendix" in name or name.startswith("00"):
            continue
        total += len(words(text))
        hits = flagged(text, p1)
        if hits:
            res[name] = hits
    return {"words": total, "flagged": res}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--report")
    a = ap.parse_args()
    run = load(os.path.join(work_dir(a.src), "run.json"))
    r = check(a.report or os.path.join(phase_dir(a.src), "sections"), run["phase1_report"])
    n = sum(len(v) for v in r["flagged"].values())
    L = [f"# Repeat check: {n} paragraphs repeat the filings research; {r['words']:,} words (target 15,000-25,000, appendix excluded)", ""]
    for name, hits in r["flagged"].items():
        L += [f"## {name}"] + [f"- {h['share']:.0%} of 6-word runs in the filings research: {h['text']}" for h in hits] + [""]
    open(os.path.join(work_dir(a.src), "repeat.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")
    print(L[0][2:])
    raise SystemExit(1 if n else 0)
