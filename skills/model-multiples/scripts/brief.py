"""The valuation brief (spec §2): code, not an agent, cuts the valuation-relevant sections of the newest filings and
street research reports into one file, capped in words. Agents read it first, then look up the full reports.

usage: python3 brief.py --ticker T --out OUT.md [--cap 15000] [--research-dir D]
Prints a JSON summary (reports, included, cut, missing, words). Nothing is dropped silently: every missing or cut
section is listed, and each cut ends with a note saying where to read the rest."""
import argparse
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "..", "..", "lib"))
import settings  # noqa: E402

# (folder, heading pattern, weight) in output order. When the cap bites, each section found gets a share of the cap in
# proportion to its weight (see budgets). Matched by heading text, not number: numbers shift between versions.
WANT = [
    ("Filings Research", r"(executive )?summary", 2),
    ("Filings Research", r"the key drivers", 2),
    ("Filings Research", r"the stock vs the drivers", 2),
    ("Street Research", r"executive summary", 2),
    ("Street Research", r"what changes in our view", 1),
    ("Filings Research", r"management credibility", 1),
    ("Filings Research", r"the industry", 1),
    ("Street Research", r"the key drivers", 1),
    ("Street Research", r"turning points", 1),
    ("Street Research", r"the growth plan", 1),
    ("Street Research", r"industry direction", 1),
    ("Filings Research", r"gaps", 1),
]
FOLDERS = ("Filings Research", "Street Research")
# Top-level sections are numbered with two digits ("## 05 The key drivers", "# 09 Management credibility");
# subsections ("## 9.1 ...", "## 10.1 ...") don't match, so they stay inside their section.
TOP = re.compile(r"^#{1,2} (\d{2}) (.+?)\s*$")


def newest(folder):
    """Newest report by its date-prefixed file name; a "(long version)" only when there is no short one."""
    allf = glob.glob(os.path.join(folder, "*Research Report*.md"))
    short = [f for f in allf if "long version" not in f.lower()]
    fs = short or allf
    return sorted(fs, key=os.path.basename)[-1] if fs else None


def sections(path):
    """[(title, heading line number (1-based), lines)] for the top-level numbered sections."""
    lines = open(path, encoding="utf-8").read().split("\n")
    heads = [(i, m.group(2)) for i, ln in enumerate(lines) if (m := TOP.match(ln))]
    return [(t, i + 1, lines[i:(heads[k + 1][0] if k + 1 < len(heads) else len(lines))])
            for k, (i, t) in enumerate(heads)]


def words(lines):
    return len(" ".join(lines).split())


def trim(lines, room, cap, src):
    """Whole paragraphs while they fit, then a note saying where the rest is."""
    kept, n = [], 0
    for para in "\n".join(lines).split("\n\n"):
        w = len(para.split())
        if n + w > room:
            break
        kept.append(para)
        n += w
    body = "\n\n".join(kept).split("\n") if kept else [lines[0]]
    return body + ["", f"[Cut by the brief's {cap}-word cap. Read the rest in {src}.]"]


def budgets(items, cap):
    """items = [(words, weight)]. Weighted fair share of the cap; a section shorter than its share keeps all of it and
    the leftover is shared by weight among the rest. Repeats until no more sections fit."""
    bud = [None] * len(items)
    while True:
        open_ = [i for i, b in enumerate(bud) if b is None]
        room = cap - sum(items[i][0] for i, b in enumerate(bud) if b is not None)
        tw = sum(items[i][1] for i in open_)
        share = {i: room * items[i][1] / tw for i in open_} if tw else {}
        fit = [i for i in open_ if items[i][0] <= share[i]]
        if not fit:
            for i in open_:
                bud[i] = share[i]
            return bud
        for i in fit:
            bud[i] = items[i][0]


def build(ticker, research_dir, cap=15000):
    base = os.path.join(research_dir, ticker)
    reports = {f: newest(os.path.join(base, f)) for f in FOLDERS}
    secs = {f: (sections(p) if p else []) for f, p in reports.items()}
    s = {"reports": reports, "included": [], "cut": [], "missing": [], "words": 0}
    found, used = [], set()
    for folder, pat, wt in WANT:
        hit = next(((t, ln, ls) for t, ln, ls in secs[folder] if re.match(pat, t, re.I) and (folder, ln) not in used),
                   None)
        if hit is None:
            s["missing"].append(f"{folder}: {pat.replace('(executive )?', '')}")
            continue
        used.add((folder, hit[1]))
        found.append((folder, hit, wt))
    budget = budgets([(words(h[2]), wt) for _, h, wt in found], cap)
    out = []
    for (folder, (title, ln, ls), _), bud in zip(found, budget):
        src = f"{folder}/{os.path.basename(reports[folder])} line {ln}"
        if words(ls) <= bud:
            body = ls
            s["included"].append(f"{folder} / {title}")
        else:
            body = trim(ls, bud, cap, src)
            s["cut"].append({"section": f"{folder} / {title}", "words": words(ls), "budget": round(bud),
                             "kept": words(body), "source": src})
        out += [f"<!-- {title} | source: {src} -->"] + body + [""]
        s["words"] += words(body)
    return "\n".join(out), s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticker", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--cap", type=int, default=15000)
    ap.add_argument("--research-dir")
    a = ap.parse_args()
    text, s = build(a.ticker.upper(), a.research_dir or settings.research_dir(), a.cap)
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    open(a.out, "w", encoding="utf-8").write(text)
    print(json.dumps(s, indent=1))


if __name__ == "__main__":
    main()
