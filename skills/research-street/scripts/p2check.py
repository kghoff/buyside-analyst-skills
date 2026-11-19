"""Step 1b / 3 - check the ledger and every reader's and researcher's output before anything is merged.

usage: python3 p2check.py --src <ticker folder> ledger | status | check <id>
  ledger      _work/ledger.csv: header, unique ids, valid topics, non-empty claims, one G<n> row per filings research gap
  status      every reader group (s1, s2, ... from run.json) and researcher (_work/researchers.json): todo|fail|pass
  check <id>  a reader (s<n>: _work/readers/<id>) or a researcher (_work/research/<id>)
Writes _work/checks/<id>.json {ok, problems}; exits 1 and lists the problems when anything fails."""
import argparse, os, re

from p2cites import CITE, canon, cited_urls, normalize, safe_label
from p2common import (FETCH_COLS, FETCH_STATUS, HOLDER_TYPES, LEDGER_COLS, MARK_COLS, STANCES, TIERS, TOPIC, load,
                      peer_items, read_csv, save, work_dir)
from readcheck import _cites, bad_citations   # the filings research

MIN_WORDS, MIN_CITES = 800, 5
WEB_PART = re.compile(r"^.+?,\s*(\d{4}-\d{2}-\d{2}|undated)\s*,\s*https?://\S+$")
EXCERPT = re.compile(r"^## (https?://\S+)\s*$", re.M)


def _ledger(src):
    header, rows = read_csv(os.path.join(work_dir(src), "ledger.csv"))
    return header, rows


def check_ledger(src):
    header, rows = _ledger(src)
    p = []
    if header != LEDGER_COLS:
        p.append("ledger.csv header must be exactly " + ",".join(LEDGER_COLS))
    ids = [r["id"] for r in rows]
    p += [f"duplicate id {i}" for i in sorted({i for i in ids if ids.count(i) > 1})]
    p += [f"{r['id']}: bad topic {r.get('topic')!r}" for r in rows if not re.match(TOPIC, r.get("topic") or "")]
    p += [f"{r['id']}: empty claim" for r in rows if not (r.get("claim") or "").strip()]
    have = {r["id"] for r in rows if r.get("topic") == "gap"}
    gaps = load(os.path.join(work_dir(src), "gaps.json"), [])
    p += [f"Filings research gap {g['n']} has no ledger row G{g['n']} (topic gap)" for g in gaps if f"G{g['n']}" not in have]
    return p


def _web_format(inner, at):
    return [f"{at}web citation needs '<Author or Firm>, <date or undated>, <url>': {x.strip()}"
            for x in inner.split(";") if re.search(r"https?://", x) and not WEB_PART.match(x.strip())]


def _notes_problems(text, labels):
    norm = normalize(text, labels)
    safe = [safe_label(l) for l in labels]
    p = [q for m in CITE.finditer(text) for q in _web_format(m.group(1), "notes.md: ")]
    p += [f"notes.md: citation not allowed here: {c}" for c in bad_citations(norm, safe)]
    words, cites = len(text.split()), len(_cites(norm))
    if words < MIN_WORDS or cites < MIN_CITES:
        p.append(f"notes.md has {words} words and {cites} citations; at least {MIN_WORDS} words and {MIN_CITES} citations needed")
    return p


def _marks_problems(path, ledger, labels):
    header, rows = read_csv(path)
    if header != MARK_COLS:
        return ["marks.csv header must be exactly " + ",".join(MARK_COLS)]
    safe, p = [safe_label(l) for l in labels], []
    for i, r in enumerate(rows, 2):
        at = f"marks.csv line {i}"
        cid = (r["claim_id"] or "").strip()
        if cid != "NEW" and cid not in ledger:
            p.append(f"{at}: claim_id {cid!r} is not in ledger.csv (use NEW for a view no row covers)")
        if r["stance"] not in STANCES:
            p.append(f"{at}: stance {r['stance']!r} must be one of {', '.join(STANCES)}")
        if r["stance"] == "gap-closed":
            if ledger.get(cid, {}).get("topic") != "gap":
                p.append(f"{at}: gap-closed only on gap rows (G<n>)")
            if r["tier"] not in TIERS:
                p.append(f"{at}: gap-closed needs tier primary, secondary or opinion")
        if r["holder_type"] not in HOLDER_TYPES:
            p.append(f"{at}: holder_type {r['holder_type']!r} must be one of {', '.join(HOLDER_TYPES)}")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}|undated", (r["date"] or "").strip()):
            p.append(f"{at}: date must be YYYY-MM-DD or undated")
        if not (r["view"] or "").strip():
            p.append(f"{at}: empty view")
        if not (r["reasoning"] or "").strip():
            p.append(f"{at}: empty reasoning (write \"no reason given\" if the source gives none)")
        source = (r["source"] or "").strip()
        if not source:
            p.append(f"{at}: empty source")
        else:
            p += _web_format(source, f"{at}: ")
            p += [f"{at}: source not allowed here: {c}" for c in bad_citations(normalize(f"[{source}]", labels), safe)]
    return p


def check(src, item):
    w = work_dir(src)
    ledger = {r["id"]: r for r in _ledger(src)[1]}
    reader = re.fullmatch(r"s\d+", item) is not None
    d = os.path.join(w, "readers" if reader else "research", item)
    needed = ["notes.md", "marks.csv", "files_read.txt"] if reader else \
        ["notes.md", "marks.csv", "fetched.csv", "excerpts.md", "searches.txt"]
    p = [f"missing {n}" for n in needed if not os.path.exists(os.path.join(d, n))]
    if p:
        return p
    notes = open(os.path.join(d, "notes.md"), encoding="utf-8-sig").read()
    if reader:
        group = next((g for g in load(os.path.join(w, "run.json"))["groups"] if g["id"] == item), None)
        if group is None:
            return [f"no reader group {item} in run.json"]
        read = {l.strip() for l in open(os.path.join(d, "files_read.txt"), encoding="utf-8-sig")}
        p += [f"not in files_read.txt: {l}" for l in group["labels"] if l not in read]
        labels = group["labels"] + ["Filings research"]
    else:
        header, fetched = read_csv(os.path.join(d, "fetched.csv"))
        if header != FETCH_COLS:
            return p + ["fetched.csv header must be exactly " + ",".join(FETCH_COLS)]
        p += [f"fetched.csv: status {r['status']!r} for {r['url']} must be ok, blocked or failed"
              for r in fetched if r["status"] not in FETCH_STATUS]
        ok = {canon(r["url"]) for r in fetched if r["status"] == "ok"}
        excerpts = set(canon(u) for u in EXCERPT.findall(open(os.path.join(d, "excerpts.md"), encoding="utf-8-sig").read()))
        _, marks = read_csv(os.path.join(d, "marks.csv"))
        used = cited_urls(notes) | cited_urls("\n".join(f"[{m['source']}]" for m in marks))
        p += [f"cited but not fetched ok (fetched.csv): {u}" for u in sorted(used - ok)]
        p += [f"cited but no '## {u}' excerpt in excerpts.md" for u in sorted((used & ok) - excerpts)]
        p += [f"excerpt for a page not fetched ok: {u}" for u in sorted(excerpts - ok)]
        if not open(os.path.join(d, "searches.txt"), encoding="utf-8-sig").read().strip():
            p.append("searches.txt is empty")
        labels = sorted(ok) + ["Filings research"]
    labels += [it["label"] for it in peer_items(src) if item in it["agents"]]   # peer documents fetched for this agent
    p += _marks_problems(os.path.join(d, "marks.csv"), ledger, labels)
    p += _notes_problems(notes, labels)
    return p


def status(src):
    w = work_dir(src)
    ids = [g["id"] for g in load(os.path.join(w, "run.json"))["groups"]]
    ids += [r["id"] for r in load(os.path.join(w, "researchers.json"), [])]
    out = {}
    for i in ids:
        res = load(os.path.join(w, "checks", f"{i}.json"))
        out[i] = "todo" if res is None else ("pass" if res["ok"] else "fail")
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("cmd", choices=["ledger", "status", "check"])
    ap.add_argument("item", nargs="?")
    a = ap.parse_args()
    if a.cmd == "check" and not a.item:
        ap.error("check needs an id (s<n> or a researcher id)")
    if a.cmd == "status":
        for k, v in status(a.src).items():
            print(f"{k}\t{v}")
        raise SystemExit(0)
    probs = check_ledger(a.src) if a.cmd == "ledger" else check(a.src, a.item)
    save(os.path.join(work_dir(a.src), "checks", f"{a.item or 'ledger'}.json"), {"ok": not probs, "problems": probs})
    print("\n".join(probs) if probs else "pass")
    raise SystemExit(1 if probs else 0)
