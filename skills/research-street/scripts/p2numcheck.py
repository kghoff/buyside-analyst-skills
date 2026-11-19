"""Step 10b - check every number and quote in the street research report against what it cites, with research-filings' numcheck.

usage: python3 p2numcheck.py --src <ticker folder> --report <sections dir | file> [--out <path.md>]
A citation can point to:
  [<sell-side file label>, p3]                 that page of the report's markdown (pages split at '## Page N';
                                               any other locator, e.g. p3-4, checks the whole report)
  [<Author or Firm>, <date>, <url>]            the text saved under '## <url>' in _work/research/*/excerpts.md
  [Filings research, §10.2]                             the filings research report
  [<company file label>, ...] / [Model, ...] / [Calc, ...] / [price.csv, ...]   as in the filings research (research-filings' _work)
Also lists sources dated after the as-of date. Writes --out (default _work/numcheck.md) and a .json alongside."""
import argparse, csv, glob, json, os, re

from p2common import load, p1_work, peer_items, work_dir   # first: puts research-filings' scripts on sys.path
from numcheck import _flat, _read_report, check_report   # the filings research
from p2cites import canon, cited_urls, normalize, safe_label, web_dates
from p2common import read_csv

HEAD = re.compile(r"^## (https?://\S+)\s*$")
PAGE = re.compile(r"^## Page (\d+)\s*$", re.M)


def excerpts(text):
    out, cur = {}, None
    for line in text.splitlines():
        m = HEAD.match(line)
        if m:
            cur = canon(m.group(1))
            out.setdefault(cur, "")
        elif cur:
            out[cur] += line + "\n"
    return out


def pages(text):
    """{page number: text} from a sell-side markdown split at '## Page N' lines."""
    parts = PAGE.split(text)
    return {int(n): body for n, body in zip(parts[1::2], parts[2::2])}


def _plain(text):
    """Drop bold/italic markers so a quote spanning '**told us**' still matches (research-filings' normalizer keeps them)."""
    return re.sub(r"\*\*|__", "", text)


def build_sources(src, run):
    sources = {}
    for d in load(os.path.join(p1_work(src), "inventory.json"), []) or []:
        if d.get("md") and os.path.exists(os.path.join(src, d["md"])):
            sources[d["label"]] = open(os.path.join(src, d["md"]), encoding="utf-8").read()
    for it in run["sellside"]:
        text = _plain(open(os.path.join(src, it["md"]), encoding="utf-8").read())
        sources[safe_label(it["label"])] = text                      # page ranges and other locators
        for n, body in pages(text).items():
            sources[f"{safe_label(it['label'])}, p{n}"] = body          # '[label, p3]' checks page 3 only
    for it in peer_items(src):                                      # a peer's own call or filing, fetched for an agent
        text = _plain(open(it["md"], encoding="utf-8").read())
        sources[it["label"]] = text
        for n, body in pages(text).items():
            sources[f"{it['label']}, p{n}"] = body
    sources["Filings research"] = _plain(open(run["phase1_report"], encoding="utf-8").read())
    for p in sorted(glob.glob(os.path.join(work_dir(src), "research", "*", "excerpts.md"))):
        for url, text in excerpts(open(p, encoding="utf-8").read()).items():
            sources[url] = sources.get(url, "") + _plain(text)
    return sources


def _p1_pools(src):
    w = p1_work(src)
    calc = _flat(load(os.path.join(w, "drivers_math.json"), {}) or {}, [])
    cells, px = {}, []
    if os.path.exists(os.path.join(w, "series.csv")):
        with open(os.path.join(w, "series.csv"), newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                try:
                    cells.setdefault(row["source"].strip(), []).append(float(row["value"]))
                except ValueError:
                    pass
    if os.path.exists(os.path.join(w, "price.csv")):
        with open(os.path.join(w, "price.csv"), newline="", encoding="utf-8") as f:
            px = list(csv.DictReader(f))
    return cells, calc, px


def published_dates(src):
    """{canon url: published} from every research/*/fetched.csv."""
    out = {}
    for p in glob.glob(os.path.join(work_dir(src), "research", "*", "fetched.csv")):
        out.update({canon(r["url"]): (r["published"] or "").strip() for r in read_csv(p)[1]})
    return out


def late(text, as_of, sellside_labels, published=None):
    out = {f"{u} (dated {d})" for d, u in web_dates(text) if d != "undated" and d > as_of}
    out |= {f"{u} (published {p})" for u in cited_urls(text) for p in [(published or {}).get(u, "")]
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", p) and p > as_of}
    out |= {l for l in sellside_labels if l[:10] > as_of and l in text}
    return sorted(out)


def run_check(src, md):
    run = load(os.path.join(work_dir(src), "run.json"))
    labels = [it["label"] for it in run["sellside"]]
    cells, calc, px = _p1_pools(src)
    r = check_report(normalize(md, labels), build_sources(src, run), cells, calc, px)
    r["late"] = late(md, run["as_of"], labels, published_dates(src))
    return r


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--report", required=True)
    ap.add_argument("--out", help="markdown result path (default _work/numcheck.md); the .json goes alongside")
    a = ap.parse_args()
    out = a.out or os.path.join(work_dir(a.src), "numcheck.md")
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    r = run_check(a.src, _read_report(a.report))
    json.dump(r, open(os.path.splitext(out)[0] + ".json", "w"), indent=1)

    def row(u):
        return f"- line {u['line']}: {u['number']} (cites {'; '.join(u['cites'])}): {u['text']}"

    L = [f"# Number check: {r['confirmed']} confirmed, {len(r['unconfirmed'])} unconfirmed, {len(r['weak'])} weak, "
         f"{len(r['uncited'])} uncited, {len(r['bad_citations'])} bad citations, {len(r['bad_quotes'])} bad quotes, "
         f"{len(r['late'])} dated after the as-of date", "", "## Unconfirmed"]
    L += [row(u) for u in r["unconfirmed"]]
    L += ["", "## Weak (small number, no nearby anchor in the source: checker reviews)"] + [row(u) for u in r["weak"]]
    L += ["", "## Uncited"] + [f"- line {u['line']}: {u['number']}: {u['text']}" for u in r["uncited"]]
    L += ["", "## Bad citations (not a known source: sell-side label, fetched URL with an excerpt, the filings research, or a company document)"]
    L += [f"- {c}" for c in r["bad_citations"]]
    L += ["", "## Quotes not found in the cited source"]
    L += [f"- line {u['line']}: \"{u['quote']}\" (cites {'; '.join(u['cites']) or 'nothing'}): {u['text']}" for u in r["bad_quotes"]]
    L += ["", "## Dated after the as-of date"] + [f"- {x}" for x in r["late"]]
    open(out, "w", encoding="utf-8").write("\n".join(L) + "\n")
    print(L[0][2:])
