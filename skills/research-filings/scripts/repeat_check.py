"""Find paragraphs that say again what another section already says, and count the words (the
first DXCM report ran 64k words partly because sections written by different writers repeated each other).

usage: python3 repeat_check.py --src <ticker folder> [--report <sections dir>]
A paragraph (30+ words once citations and markup are removed) is flagged when 30% or more of its 6-word runs also
appear in another section; a table when 60% or more. The summary (01) restates the report by design, so it is
neither checked nor used as the "other section"; the cover and appendix are not checked or counted either.
Target 17,000-23,000 words. Writes _work/repeat.md; exits 1 if anything is flagged or the count is outside it."""
import argparse, glob, os, re

from common import phase_dir, work_dir
from filter import blocks

K, MIN_WORDS, LIMIT, TABLE_LIMIT = 6, 30, 0.3, 0.6
LOW, HIGH = 17000, 23000
CITE = re.compile(r"\[([^\[\]\n]+?)\](?!\()")


def words(text):
    text = re.sub(r"<[^>]+>|[*_`>|#]", " ", CITE.sub(" ", text))
    return re.findall(r"[a-z0-9]+(?:[.,'’-][a-z0-9]+)*", text.lower())


def runs(ws):
    return {" ".join(ws[i:i + K]) for i in range(len(ws) - K + 1)}


def skip(name):
    return name.startswith(("00", "01")) or "appendix" in name


def check(sections):
    texts = {os.path.basename(f): open(f, encoding="utf-8").read() for f in sorted(glob.glob(os.path.join(sections, "*.md")))}
    pool = {n: runs(words(t)) for n, t in texts.items() if not skip(n)}
    res, total = {}, 0
    for name, text in texts.items():
        if skip(name):
            continue
        total += len(words(text))
        others = set().union(*[r for n, r in pool.items() if n != name]) if len(pool) > 1 else set()
        hits = []
        for kind, block in blocks(text):
            if kind == "heading":
                continue
            if re.match(r"\W*Terms\b", block):        # a section's glossary line restates acronyms by design
                continue
            ws = words(block)
            if len(ws) < MIN_WORDS:
                continue
            r = runs(ws)
            share = len(r & others) / len(r)
            if share >= (TABLE_LIMIT if kind == "table" else LIMIT):
                where = max((n for n in pool if n != name), key=lambda n: len(r & pool[n]))
                hits.append({"share": round(share, 2), "also_in": where, "text": block[:300]})
        if hits:
            res[name] = hits
    return {"words": total, "flagged": res}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--report")
    a = ap.parse_args()
    r = check(a.report or os.path.join(phase_dir(a.src), "sections"))
    n = sum(len(v) for v in r["flagged"].values())
    ok = LOW <= r["words"] <= HIGH
    L = [f"# Repeat check: {n} paragraphs repeat another section; {r['words']:,} words "
         f"(target {LOW:,}-{HIGH:,}, summary and appendix excluded){'' if ok else ' - OUTSIDE THE TARGET'}", ""]
    for name, hits in r["flagged"].items():
        L += [f"## {name}"] + [f"- {h['share']:.0%} of 6-word runs also in {h['also_in']}: {h['text']}" for h in hits] + [""]
    open(os.path.join(work_dir(a.src), "repeat.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")
    print(L[0][2:])
    raise SystemExit(0 if (ok and not n) else 1)
