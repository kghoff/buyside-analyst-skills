"""Step 6 - prove every file was read and every citation points inside the reader's own slice.

usage: python3 readcheck.py --src <ticker folder> status        -> JSON {done: [ids], todo: [{id, title}]}
       python3 readcheck.py --src <ticker folder> check s03     -> JSON {ok, problems}
Reader output lives in _work/readers/<slice id>/: notes.md, data.csv, guidance.csv, files_read.txt.
A passing check writes check.json with the slice hash, so a rerun reuses the reader unless its files changed.
Citation format: [<exact file label>, <locator>]; several sources split by ';'. [Model, ...], [Calc, ...] and
[User's notes, ...] are always allowed. Brackets without a comma ([!KEY], [?]) are not citations."""
import argparse, csv, json, math, os, re

from common import load, save, work_dir

DATA_COLS = ["metric", "period", "value", "unit", "source"]
GUIDE_COLS = ["fiscal_year", "metric", "basis", "kind", "date", "low", "high", "actual", "source"]
PERIOD = re.compile(r"^(Q[1-4] \d{4}|H[12] \d{4}|FY\d{4}|\d{4}-\d{2}-\d{2})$")
CITE = re.compile(r"\[([^\[\]\n]+?)\](?!\()")
ALWAYS_OK = ("Model", "Calc", "User's notes")
NEEDED = ["notes.md", "data.csv", "guidance.csv", "files_read.txt"]


def _starts_source(t, labels):
    t = t.strip()
    return t.split(",")[0].strip() in ALWAYS_OK or any(t == l or t.startswith(l + ",") for l in labels)


def _in(t, labels):
    t = t.strip()
    if "," not in t:
        return t in labels or re.match(r"(%s)\b" % "|".join(map(re.escape, ALWAYS_OK)), t) is not None
    return _starts_source(t, labels)


def _parts(inner, labels):
    """Split on ';' only where the next part starts a new source; otherwise ';' belongs to the locator."""
    out = []
    for i, p in enumerate(inner.split(";")):
        # a part with its own "<name>, <locator>" shape is a new source (possibly out of slice); "Note 3" is a locator
        if out and not (_starts_source(p, labels) or "," in p):
            out[-1] += ";" + p
        else:
            out.append(p)
    return out


def _cites(text):
    return [m.group(1) for m in CITE.finditer(text)
            if not m.group(1).startswith("!") and ("," in m.group(1) or len(m.group(1)) >= 12)]


def bad_citations(text, labels):
    return [p.strip()[:120] for inner in _cites(text) for p in _parts(inner, labels) if not _in(p, labels)]


def _csv_problems(path, name, cols, labels):
    out = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        r = csv.DictReader(f)
        if r.fieldnames != cols:
            return [f"{name} header must be: {','.join(cols)}"]
        for i, row in enumerate(r, 2):
            if any(not _in(p, labels) for p in _parts(row.get("source") or "", labels)):
                out.append(f"{name} line {i}: source {(row.get('source') or '')[:60]!r} is not a file in this slice")
            if name == "data.csv":
                try:
                    if not math.isfinite(float(row["value"])):
                        raise ValueError
                except (TypeError, ValueError):
                    out.append(f"data.csv line {i}: value {row['value']!r} is not a finite number")
                if not PERIOD.match(row["period"] or ""):
                    out.append(f"data.csv line {i}: period {row['period']!r} must look like Q3 2024, H1 2024, "
                               f"FY2024 or 2024-09-30")
    return out[:10]


def check(src, sid):
    w = work_dir(src)
    sl = {s["id"]: s for s in load(os.path.join(w, "slices.json"))}.get(sid)
    if not sl:
        return {"ok": False, "problems": [f"unknown slice {sid}"]}
    d = os.path.join(w, "readers", sid)
    labels = [f["label"] for f in sl["files"]]
    problems = [f"missing {n}" for n in NEEDED if not os.path.exists(os.path.join(d, n))]
    if not problems:
        with open(os.path.join(d, "files_read.txt"), encoding="utf-8-sig") as f:
            read = {l.strip() for l in f if l.strip()}
        unread = [l for l in labels if l not in read]
        extra = sorted(read - set(labels))
        if unread:
            problems.append("not read: " + "; ".join(unread))
        if extra:
            problems.append("listed files outside this slice: " + "; ".join(extra))
        with open(os.path.join(d, "notes.md"), encoding="utf-8-sig") as f:
            notes = f.read()
        bad = bad_citations(notes, labels)
        if bad:
            problems.append(f"{len(bad)} citations outside this slice, e.g. {bad[:3]}; square brackets are only "
                            f"for citations [<file label>, <locator>]; use parentheses for anything else")
        words, cites = len(notes.split()), len(_cites(notes))
        if words < 1000 or cites < 10:
            problems.append(f"notes.md too thin ({words} words, {cites} citations)")
        problems += _csv_problems(os.path.join(d, "data.csv"), "data.csv", DATA_COLS, labels)
        problems += _csv_problems(os.path.join(d, "guidance.csv"), "guidance.csv", GUIDE_COLS, labels)
    ok = not problems
    cj = os.path.join(d, "check.json")
    if ok:
        save(cj, {"hash": sl["hash"]})
    elif os.path.exists(cj):
        os.remove(cj)
    return {"slice": sid, "ok": ok, "problems": problems}


def status(src):
    w = work_dir(src)
    done, todo = [], []
    for s in load(os.path.join(w, "slices.json")):
        c = load(os.path.join(w, "readers", s["id"], "check.json"))
        (done.append(s["id"]) if c and c.get("hash") == s["hash"] else todo.append({"id": s["id"], "title": s["title"]}))
    return {"done": done, "todo": todo}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("cmd", choices=["status", "check"])
    ap.add_argument("slice", nargs="?")
    a = ap.parse_args()
    print(json.dumps(status(a.src) if a.cmd == "status" else check(a.src, a.slice), indent=1))
