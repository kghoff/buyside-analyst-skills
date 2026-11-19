"""Step 12 - check every number in the report against the source it cites.

usage: python3 numcheck.py --src <ticker folder> --report <report.md | sections dir>
A unit is one sentence or one table row. A table row with no citation of its own uses the citation in the line
right after the table (its caption). Every number in a unit is checked against every source the unit cites:
  [<file label>, ...]   the ORIGINAL markdown of that file (not the filtered copy)
  [Model, ...] / Calc   series.csv values and every number in drivers_math.json (the skill's own arithmetic)
A number matches when a source holds it at the precision written: 12.3% matches 12.34; $1.2 billion matches
1,234.5 (millions); 12.3% matches 0.1234. Years, Qn, FYnnnn, slide / item / page numbers, numbers under 10 with no
unit, and the citation text itself are not checked.
Writes _work/numcheck.json and _work/numcheck.md (unconfirmed, uncited, bad citations) for the checker agent."""
import argparse, bisect, csv, glob, json, os, re

from common import load, work_dir

CITE = re.compile(r"\[([^\[\]\n]+?)\](?!\()")
SUFFIX = r"(?:%|bps\b|x\b|billion\b|million\b|thousand\b|bn\b|mn\b|[BMK]\b)"
NUM = re.compile(r"(?<![\w./])(\$?)(\d{1,3}(?:,\d{3})+|\d+)(\.\d+)?(\s?" + SUFFIX + ")?", re.I)
RANGE_AFTER = re.compile(r"\s*(?:[–—-]|\bto\b)\s*(\$?)(\d{1,3}(?:,\d{3})+|\d+)(\.\d+)?(\s?" + SUFFIX + ")", re.I)
SKIP_BEFORE = re.compile(r"(?:\b(?:S|Item|p\.|page|pages|slide|slides|note|row|rows|line)\s?)$", re.I)
MONTH_BEFORE = re.compile(r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December|"
                          r"Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\.?\s+$", re.I)
NAME_AFTER = re.compile(r"-(?:(?:day|month|year)s?\b|[KQ]\b)", re.I)
SRC_NUM = re.compile(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?")
SCALES = {"": [1, 1e3, 1e-3], "%": [1, 0.01], "bps": [1, 1e-4, 0.01], "x": [1],
          "billion": [1, 1e3, 1e9], "bn": [1, 1e3, 1e9], "b": [1, 1e3, 1e9],
          "million": [1, 1e6, 1e-3], "mn": [1, 1e6, 1e-3], "m": [1, 1e6, 1e-3], "thousand": [1, 1e3], "k": [1, 1e3]}
ALWAYS = ("Model", "Calc", "User's notes")
MODEL_CELL = re.compile(r"Model,\s*(MOD!\$?[A-Z]+\$?\d+)")
MODEL_HINT = "cite model numbers by cell, e.g. [Model, MOD!H61]"
ANCHOR_WINDOW = 1500


MONTHS = (r"(?:January|February|March|April|May|June|July|August|September|October|November|December|"
          r"Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sept|Sep|Oct|Nov|Dec)")
DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b|\b" + MONTHS + r"\.?\s+\d{1,2}(?:st|nd|rd|th)?\b(?:,?\s+\d{4})?", re.I)


def numbers(text):
    text = CITE.sub(" ", text)
    text = DATE.sub(lambda m: " " * len(m.group()), text)      # dates are not figures; same length keeps offsets valid
    out = []
    for m in NUM.finditer(text):
        dollars, whole, frac, suffix = m.groups()
        before, after = text[:m.start()], text[m.end():]
        if SKIP_BEFORE.search(before) or MONTH_BEFORE.search(before) or NAME_AFTER.match(after):
            continue
        if not suffix:
            r = RANGE_AFTER.match(after)
            if r:                                   # "$4.60-4.625 billion": the first number takes the second's unit
                dollars, suffix = dollars or r.group(1), r.group(4)
        val = float(whole.replace(",", "") + (frac or ""))
        bare = not (dollars or frac or suffix or "," in whole)
        if bare and (1900 <= val <= 2100 or val < 10):
            continue
        digits = (whole.replace(",", "") + (frac or "")[1:]).lstrip("0")
        out.append({"number": m.group(0).strip(), "value": val, "decimals": len(frac) - 1 if frac else 0,
                    "suffix": (suffix or "").strip().lower(), "sig": len(digits)})
    return out


QUOTE = re.compile(r'"([^"]+)"|\u201c([^\u201d]+)\u201d')
ELLIPSIS = re.compile(r"\u2026|\.{3}")
MIN_QUOTE_WORDS = 4


def _norm(text):
    text = text.lower().translate({0x201c: '"', 0x201d: '"', 0x2018: "'", 0x2019: "'"})
    return re.sub(r"\s+", " ", text).strip()


def quotes(unit):
    """Quoted phrases of 4+ words (straight or curly quotes), citation text left out."""
    unit = CITE.sub(" ", unit)
    out = []
    for m in QUOTE.finditer(unit):
        q = (m.group(1) or m.group(2)).strip()
        if len(ELLIPSIS.sub(" ", q).split()) >= MIN_QUOTE_WORDS:
            out.append(q)
    return out


def quote_in(quote, norm_text):
    """Every piece of the quote (split at ellipses) appears in the normalized source."""
    pieces = [_norm(p).strip(" ,;:") for p in ELLIPSIS.split(quote)]
    return all(p in norm_text for p in pieces if p)


def pool_of(text):
    """(values, offsets) sorted by value; offsets are positions in the source text (None for exact pools)."""
    items = sorted((float(m.group().replace(",", "")), m.start()) for m in SRC_NUM.finditer(text))
    return [v for v, _ in items], [o for _, o in items]


def exact_pool(values):
    return sorted(abs(x) for x in values), None


def matches(n, pool):
    """Offsets (or None placeholders) of every pool value equal to the number at the precision written."""
    vals, offs = pool
    tol = 0.5 * 10 ** (-n["decimals"]) + 1e-9
    hits = []
    for k in SCALES.get(n["suffix"], [1]):
        lo, hi = sorted(((n["value"] - tol) * k, (n["value"] + tol) * k))
        i, j = bisect.bisect_left(vals, lo), bisect.bisect_right(vals, hi)
        hits += offs[i:j] if offs is not None else [None] * (j - i)
    return hits


def _units(md):
    lines = md.splitlines()
    i = 0
    while i < len(lines):
        s = lines[i].strip()
        if s.startswith("|"):
            j = i
            while j < len(lines) and lines[j].strip().startswith("|"):
                j += 1
            caption = next((lines[k] for k in range(j, min(j + 3, len(lines))) if lines[k].strip()), "")
            for k in range(i, j):
                row = lines[k].strip()
                if not re.fullmatch(r"\|[\s:|\-]+\|?", row):
                    yield k + 1, row, caption
            i = j
            continue
        if s and not s.startswith(("![", "```")):
            s = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s)).strip()
            for sent in re.split(r"(?<=[.!?])\s+(?=[A-Z(*])", s) if s else []:
                yield i + 1, sent, ""
        i += 1


def check_report(md, sources, model_cells, calc_pool, price_rows=()):
    """sources {label: original markdown}; model_cells {"Model, MOD!H61": [values]}; calc_pool: drivers_math numbers."""
    pools, calc = {}, exact_pool(calc_pool)
    by_date = {r["date"]: [float(r[k]) for k in ("close", "spy") if r.get(k) not in (None, "")] for r in price_rows}
    all_px = [v for vs in by_date.values() for v in vs]
    res = {"confirmed": 0, "unconfirmed": [], "weak": [], "uncited": [], "bad_citations": [], "bad_quotes": []}
    norms = {}

    def bad(c):
        if c not in res["bad_citations"]:
            res["bad_citations"].append(c)

    for ln, unit, caption in _units(md):
        nums = numbers(unit)
        cites = [p.strip() for m in CITE.finditer(unit if CITE.search(unit) else caption)
                 if ("," in m.group(1) or m.group(1).strip() in sources)   # a bare label (a transcript has no pages)
                 and not m.group(1).startswith("!") for p in m.group(1).split(";")]
        docs, exact, cells, cited_cell = [], [], [], False
        for c in cites:
            first = c.split(",")[0].strip()
            if first == "Model":
                m = MODEL_CELL.fullmatch(c)
                if m:
                    cells += model_cells.get("Model, " + m.group(1), [])
                    cited_cell = True
                else:
                    bad(f"{c}: {MODEL_HINT}")
                continue
            if first == "price.csv":                  # one date if the locator names a row of price.csv, else every close and SPY value
                loc = c.split(",")[1].strip() if "," in c else ""
                exact.append(exact_pool(by_date.get(loc, all_px)))
                continue
            if first in ALWAYS:
                if first == "Calc":
                    exact.append(calc)
                else:
                    exact.append(exact_pool([]))      # the user's notes: nothing machine-readable to check against
                continue
            label = max((l for l in sources if c == l or c.startswith(l + ",")), key=len, default=None)
            if label is None:
                bad(c)
                continue
            if label not in pools:
                pools[label] = pool_of(sources[label])
            docs.append(pools[label])
        qs = quotes(unit)
        if qs:
            doc_labels = [l for l in (max((l for l in sources if c == l or c.startswith(l + ",")), key=len, default=None)
                                      for c in cites if c.split(",")[0].strip() not in ALWAYS + ("price.csv",)) if l]
            only_nondoc = all(c.split(",")[0].strip() in ALWAYS + ("price.csv",) for c in cites)
            for q in qs:
                row = {"line": ln, "quote": q, "cites": cites, "text": unit[:160]}
                if not cites or (only_nondoc and "User's notes" not in [c.split(",")[0].strip() for c in cites]):
                    res["bad_quotes"].append(row)
                    continue
                if not doc_labels:
                    continue                            # unknown labels are already listed under bad_citations
                for l in doc_labels:
                    if l not in norms:
                        norms[l] = _norm(sources[l])
                if not any(quote_in(q, norms[l]) for l in doc_labels):
                    res["bad_quotes"].append(row)
        if cited_cell:
            exact.append(exact_pool(cells))
        if re.search(r"\bCalc\b", unit) or re.search(r"\bCalc\b", caption):
            exact.append(calc)
        for n in nums:
            if not docs and not exact:
                if not cites:                           # all-bad citations are already listed once under bad_citations
                    res["uncited"].append({"line": ln, "number": n["number"], "text": unit[:160]})
                continue
            row = {"line": ln, "number": n["number"], "cites": cites, "text": unit[:160]}
            if any(matches(n, p) for p in exact):
                res["confirmed"] += 1
                continue
            hits = [(p, matches(n, p)) for p in docs]
            hits = [h for h in hits if h[1]]
            if not hits:
                res["unconfirmed"].append(row)
            elif n["sig"] >= 3:
                res["confirmed"] += 1
            else:
                anchors = [a for a in nums if a is not n and a["sig"] >= 3]
                ok = any(abs(x - y) <= ANCHOR_WINDOW for p, offs in hits for a in anchors
                         for y in matches(a, p) for x in offs)
                if ok:
                    res["confirmed"] += 1
                else:
                    res["weak"].append(row)
    return res


def _flat(x, out):
    if isinstance(x, bool):
        return out
    if isinstance(x, (int, float)):
        out.append(float(x))
    elif isinstance(x, dict):
        for v in x.values():
            _flat(v, out)
    elif isinstance(x, list):
        for v in x:
            _flat(v, out)
    return out


def _read_report(path):
    if os.path.isdir(path):
        return "\n\n".join(open(p, encoding="utf-8").read() for p in sorted(glob.glob(os.path.join(path, "*.md"))))
    return open(path, encoding="utf-8").read()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--report", required=True)
    a = ap.parse_args()
    w = work_dir(a.src)
    sources = {}
    for d in load(os.path.join(w, "inventory.json")):
        if d["md"]:
            sources[d["label"]] = open(os.path.join(a.src, d["md"]), encoding="utf-8").read()
    calc = _flat(load(os.path.join(w, "drivers_math.json"), {}), [])
    cells = {}
    with open(os.path.join(w, "series.csv"), newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                cells.setdefault(row["source"].strip(), []).append(float(row["value"]))
            except ValueError:
                pass
    with open(os.path.join(w, "price.csv"), newline="", encoding="utf-8") as f:
        px = list(csv.DictReader(f))
    r = check_report(_read_report(a.report), sources, cells, calc, px)
    json.dump(r, open(os.path.join(w, "numcheck.json"), "w"), indent=1)
    L = [f"# Number check: {r['confirmed']} confirmed, {len(r['unconfirmed'])} unconfirmed, {len(r['weak'])} weak, {len(r['uncited'])} "
         f"uncited, {len(r['bad_citations'])} bad citations, {len(r['bad_quotes'])} bad quotes", "", "## Unconfirmed"]
    L += [f"- line {u['line']}: {u['number']} (cites {'; '.join(u['cites'])}): {u['text']}" for u in r["unconfirmed"]]
    L += ["", "## Weak (small number, no nearby anchor in the source: checker reviews)"]
    L += [f"- line {u['line']}: {u['number']} (cites {'; '.join(u['cites'])}): {u['text']}" for u in r["weak"]]
    L += ["", "## Uncited"] + [f"- line {u['line']}: {u['number']}: {u['text']}" for u in r["uncited"]]
    L += ["", "## Bad citations (not a filings research document)"] + [f"- {c}" for c in r["bad_citations"]]
    L += ["", "## Quotes not found in the cited source"]
    L += [f"- line {u['line']}: \"{u['quote']}\" (cites {'; '.join(u['cites']) or 'nothing'}): {u['text']}" for u in r["bad_quotes"]]
    open(os.path.join(w, "numcheck.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")
    print(L[0][2:])
