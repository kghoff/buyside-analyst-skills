"""Step 3 - mark what is new in each document, so readers spend their time on what changed.

usage: python3 filter.py --src <ticker folder>
Each document is compared with earlier documents of the same kind, paragraph by paragraph:
  exact repeat (whitespace / case ignored) -> dropped; a marker line says how many, and since which filing
  small edit (word match >= DIFF)            -> compact diff: changed sentences only, **[+ new +]** ~~[- old -]~~
  rewritten (NEAR <= match < DIFF)           -> kept in full, marked "revised since"
  new                                        -> kept in full
Tables, headings and lines under MIN_WORDS words are always kept. Calls, press releases and decks only lose exact
repeats that appeared in at least BOILERPLATE_MIN earlier documents (boilerplate). Groups: 10-Ks vs earlier 10-Ks; 10-Qs vs earlier 10-Qs and 10-Ks; proxies vs earlier proxies; any other
type vs earlier documents of its own type. The first document of a group is kept whole.
Writes _work/filtered/<category>/<label>.md and _work/filter_stats.json."""
import argparse, difflib, hashlib, os, re, zlib

from common import load, save, work_dir

MIN_WORDS = 8
NEAR = 0.6        # word-match ratio at or above this = a revised version of an earlier paragraph
DIFF = 0.8        # at or above this the change is small enough to show as a compact diff
K = 5             # words per shingle (candidate lookup only)
SAMPLE = 4        # long blocks index 1 in SAMPLE shingles, to keep memory small on 50+ filings
BOILERPLATE_MIN = 3  # exact-only groups drop a repeat only after it has appeared in this many earlier documents
MAX_POSTING = 200  # a shingle shared by more blocks than this is boilerplate; useless for finding a match
GROUPS = {"10-Ks": ([], True), "10-Qs": (["10-Ks"], True), "Proxy Statements": ([], True)}


def blocks(md):
    """(kind, text) blocks: 'heading' lines, 'table' runs of | lines, 'text' paragraphs."""
    out, cur, kind = [], [], None

    def flush():
        nonlocal cur, kind
        if cur:
            out.append((kind, "\n".join(cur)))
        cur, kind = [], None

    for line in md.splitlines():
        s = line.strip()
        if not s:
            flush()
            continue
        if s.startswith("#"):
            flush()
            out.append(("heading", line))
            continue
        k = "table" if s.startswith("|") else "text"
        if kind and k != kind:
            flush()
        kind = k
        cur.append(line)
    flush()
    return out


def _h(s):
    """Stable hash (the built-in hash() changes with every run, which would change the output)."""
    return zlib.crc32(s.encode())


def _shingles(low):
    if len(low) < K:
        return {_h(" ".join(low))}
    hs = {_h(" ".join(low[i:i + K])) for i in range(len(low) - K + 1)}
    if len(low) < 40:
        return hs
    return {h for h in hs if h % SAMPLE == 0} or hs


def _key(low):
    return hashlib.md5(" ".join(low).encode()).hexdigest()


class History:
    """Every paragraph seen so far in a comparison group."""

    def __init__(self):
        self.exact, self.docs, self.index, self.prior = {}, {}, {}, []

    def add(self, toks, low, label):
        key = _key(low)
        self.exact.setdefault(key, label)
        self.docs.setdefault(key, set()).add(label)
        bid = len(self.prior)
        self.prior.append((toks, low, label))
        for h in _shingles(low):
            self.index.setdefault(h, []).append(bid)

    def exact_match(self, low, min_docs=1):
        key = _key(low)
        return self.exact.get(key) if len(self.docs.get(key, ())) >= min_docs else None

    def near_match(self, low):
        counts = {}
        for h in _shingles(low):
            post = self.index.get(h, ())
            if len(post) > MAX_POSTING:
                continue
            for bid in post:
                counts[bid] = counts.get(bid, 0) + 1
        best, best_r = None, 0.0
        for bid, _ in sorted(counts.items(), key=lambda x: (-x[1], -x[0]))[:5]:
            r = difflib.SequenceMatcher(None, self.prior[bid][1], low, autojunk=False).ratio()
            if r > best_r:  # strict: candidates run newest first, so the newest wins ties
                best, best_r = bid, r
        return (self.prior[best], best_r) if best is not None and best_r >= NEAR else None


def _sentence_ids(words):
    """Sentence number of each word: a sentence ends at a word ending . ! or ? when the next word starts with a capital or digit."""
    ids, n = [], 0
    for i, w in enumerate(words):
        ids.append(n)
        if re.search(r"[.!?]$", w) and i + 1 < len(words) and re.match(r"[A-Z0-9]", words[i + 1]):
            n += 1
    return ids


def word_diff(old, new):
    """Whole sentences that changed, with the edits marked inline; runs of unchanged sentences become a single ..."""
    sm = difflib.SequenceMatcher(None, [w.lower() for w in old], [w.lower() for w in new], autojunk=False)
    ids = _sentence_ids(new)
    last = ids[-1] if ids else 0
    pieces, changed = [[] for _ in range(last + 1)], set()
    for op, a1, a2, b1, b2 in sm.get_opcodes():
        if op == "equal":
            for k in range(b1, b2):
                pieces[ids[k]].append(new[k])
            continue
        at = ids[b1] if b1 < len(ids) else last      # a pure deletion marks the sentence where it sits
        if a2 > a1:
            pieces[at].append("~~[- " + " ".join(old[a1:a2]) + " -]~~")
            changed.add(at)
        for sid in dict.fromkeys(ids[b1:b2]):
            pieces[sid].append("**[+ " + " ".join(new[k] for k in range(b1, b2) if ids[k] == sid) + " +]**")
            changed.add(sid)
    out, gap = [], False
    for sid, ps in enumerate(pieces):
        if sid in changed:
            if gap:
                out.append("…")
            gap = False
            out.append(" ".join(ps))
        else:
            gap = True
    if gap:
        out.append("…")
    return " ".join(out)


def filter_doc(md, hist, label, near):
    pending = []  # new paragraphs join the history only after the whole document, never compared with itself
    out, stats, run_ = [], {"kept": 0, "changed": 0, "revised": 0, "dropped": 0}, []

    def end_run():
        if run_:
            n = len(run_)
            out.append(f"*[{n} paragraph{'s' if n > 1 else ''} unchanged since {run_[0]}]*")
            run_.clear()

    for kind, text in blocks(md):
        toks = re.findall(r"\S+", text)
        if kind != "text" or len(toks) < MIN_WORDS:
            end_run()
            out.append(text)
            stats["kept"] += 1
            continue
        low = [t.lower() for t in toks]
        seen = hist.exact_match(low, 1 if near else BOILERPLATE_MIN)
        if seen:
            run_.append(seen)
            stats["dropped"] += 1
            continue
        end_run()
        hit = hist.near_match(low) if near else None
        if hit and hit[1] >= DIFF:
            out.append(f"*[changed since {hit[0][2]}]* " + word_diff(hit[0][0], toks))
            stats["changed"] += 1
        elif hit:
            out.append(f"*[revised since {hit[0][2]}]* " + text)
            stats["revised"] += 1
        else:
            out.append(text)
            stats["kept"] += 1
        pending.append((toks, low))
    end_run()
    for toks, low in pending:
        hist.add(toks, low, label)
    return "\n\n".join(out) + "\n", stats


def _remember(hist, md, label):
    for kind, text in blocks(md):
        toks = re.findall(r"\S+", text)
        if kind == "text" and len(toks) >= MIN_WORDS:
            hist.add(toks, [t.lower() for t in toks], label)


def run(src):
    w = work_dir(src)
    inv = load(os.path.join(w, "inventory.json"))
    if inv is None:
        raise SystemExit("run inventory.py first")
    stats = {}
    for cat in dict.fromkeys(d["category"] for d in inv):
        seeds, near = GROUPS.get(cat, ([], False))
        group = sorted((d for d in inv if d["md"] and d["category"] in [cat, *seeds]),
                       key=lambda d: (d["date"] or "", d["category"] == cat))
        hist = History()
        for d in group:
            with open(os.path.join(src, d["md"]), encoding="utf-8") as f:
                text = f.read()
            if d["category"] != cat:      # seed documents are only remembered; their own group writes them
                _remember(hist, text, d["label"])
                continue
            out, st = filter_doc(text, hist, d["label"], near)
            rel = os.path.join("filtered", cat, d["label"] + ".md")
            head = f"<!-- {d['label']}: filtered copy for the filings research readers; original: {d['md']} -->\n"
            p = os.path.join(w, rel)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "w", encoding="utf-8") as f:
                f.write(head + out)
            stats[d["label"]] = {**st, "original_bytes": len(text.encode()),
                                 "filtered_bytes": len((head + out).encode()), "filtered": rel}
    save(os.path.join(w, "filter_stats.json"), stats)
    return stats


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    st = run(ap.parse_args().src)
    o = sum(s["original_bytes"] for s in st.values())
    k = sum(s["filtered_bytes"] for s in st.values())
    print(f"{len(st)} documents: {o / 1e6:.1f} MB -> {k / 1e6:.1f} MB ({k / max(o, 1):.0%} kept)")
