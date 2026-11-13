"""Segment peers: cut the segment-note tables out of the 10-K Markdown (for the reader) and check what it typed.

usage: python3 segments.py cut --work W --ticker ABT --segment "Diabetes Care"
       python3 segments.py check --work W
cut: every Markdown table (in every 10-K for the ticker in W/fetch.json) whose rows or header mention the segment,
with its 3 caption lines, each line prefixed "L<line number>: ". Writes W/snippets/<T>.md.
check: reads W/values/<T>.json, a list of {"line", "fy", "value", "raw", "scale", "file", "line_no", "note"}.
A value is accepted only if its line is a segment line, `raw`'s number is printed on that line of that file, and
value = number x scale. Several documents for one (line, fy): the newest 10-K wins (it carries recast figures) and
the conflict is reported. Costs are stored negative. Writes W/segments.json and W/segments_check.md; exit 1 if any
value was rejected."""
import argparse
import glob
import json
import os
import re
import sys

import lines

NUMTOK = re.compile(r"\d[\d,]*(?:\.\d+)?")
DOC_FY = re.compile(r" (\d{4}) (10-K|20-F|40-F)\.md$")


def nums(text):
    return {float(t.replace(",", "")) for t in NUMTOK.findall(text)}


def _tables(L):
    out, i = [], 0
    while i < len(L):
        if L[i].lstrip().startswith("|"):
            j = i
            while j < len(L) and L[j].lstrip().startswith("|"):
                j += 1
            out.append((i, j))
            i = j
        else:
            i += 1
    return out


def cut(md_files, segment, out_path):
    pat = re.compile(re.escape(segment), re.I)
    parts, n = [], 0
    for path in md_files:
        L = open(path, encoding="utf-8", errors="ignore").read().split("\n")
        blocks = []
        for s, e in _tables(L):
            if e - s > 120 or not any(pat.search(x) for x in L[s:e]):
                continue
            cap, k = [], s - 1
            while k >= max(0, s - 8) and not L[k].lstrip().startswith("|"):   # stop at the previous table
                if L[k].strip():
                    cap.insert(0, k)
                k -= 1
            cap = cap[-3:]
            blocks.append("\n".join(f"L{k + 1}: {L[k]}" for k in cap + list(range(s, e))))
        if blocks:
            n += len(blocks)
            parts.append(f"## {path}\n\n" + "\n\n".join(blocks))
    with open(out_path, "w") as f:
        f.write(f"# Segment tables mentioning '{segment}'\n\n" + "\n\n".join(parts) + "\n")
    return n


def check_entry(e):
    for k in ("line", "fy", "value", "raw", "file", "line_no"):
        if k not in e:
            return f"missing '{k}'"
    if e["line"] not in lines.SEGMENT_LINES:
        return f"line '{e['line']}' is not a segment line ({', '.join(lines.SEGMENT_LINES)})"
    if not os.path.exists(e["file"]):
        return f"file not found: {e['file']}"
    tok = NUMTOK.search(str(e["raw"]))
    if not tok:
        return f"no number in raw '{e['raw']}'"
    L = open(e["file"], encoding="utf-8", errors="ignore").read().split("\n")
    n = int(e["line_no"])
    num = float(tok.group(0).replace(",", ""))
    if not 0 < n <= len(L) or num not in nums(L[n - 1]):
        return f"'{tok.group(0)}' is not printed at {os.path.basename(e['file'])} line {n}"
    want = num * float(e.get("scale", 1))
    if not isinstance(e["value"], (int, float)) or abs(abs(e["value"]) - abs(want)) > 1e-9 * max(1, abs(want)):
        return f"value {e['value']} != {tok.group(0)} x {e.get('scale', 1)}"
    return None


def _doc_fy(path):
    m = DOC_FY.search(path)
    return int(m.group(1)) if m else 0


def choose(es):
    es = sorted(es, key=lambda e: _doc_fy(e["file"]))
    best = dict(es[-1])
    v = abs(best["value"]) if best["line"] in lines.NEGATIVE or best["line"] in ("revenue", "total_assets", "da") \
        else best["value"]
    best["value"] = -v if best["line"] in lines.NEGATIVE else v
    conflict = len({round(abs(e["value"]), 6) for e in es}) > 1
    return best, conflict


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["cut", "check"])
    ap.add_argument("--work", required=True)
    ap.add_argument("--ticker")
    ap.add_argument("--segment")
    a = ap.parse_args()
    if a.cmd == "cut":
        F = json.load(open(os.path.join(a.work, "fetch.json")))
        os.makedirs(os.path.join(a.work, "snippets"), exist_ok=True)
        out = os.path.join(a.work, "snippets", f"{a.ticker.upper()}.md")
        n = cut(F[a.ticker.upper()]["tenk_md"], a.segment, out)
        print(json.dumps({"snippet": out, "tables": n}))
        raise SystemExit(0 if n else 1)
    accepted, rep, bad = {}, ["# Segment values check", ""], 0
    for path in sorted(glob.glob(os.path.join(a.work, "values", "*.json"))):
        T = os.path.basename(path)[:-5].upper()
        groups = {}
        for e in json.load(open(path)):
            why = check_entry(e)
            if why:
                bad += 1
                rep.append(f"- REJECTED {T} {e.get('line')} FY{e.get('fy')}: {why}")
                continue
            groups.setdefault((e["line"], int(e["fy"])), []).append(e)
        accepted[T] = {}
        for (k, fy), es in sorted(groups.items()):
            best, conflict = choose(es)
            L = open(best["file"], encoding="utf-8", errors="ignore").read().split("\n")
            accepted[T].setdefault(k, {})[str(fy)] = {
                "value": best["value"], "file": best["file"], "line_no": best["line_no"], "raw": best["raw"],
                "quote": L[int(best["line_no"]) - 1].strip()[:200], "note": best.get("note", "")}
            if conflict:
                rep.append(f"- CONFLICT {T} {k} FY{fy}: {sorted({abs(e['value']) for e in es})}; used the newest "
                           f"document ({os.path.basename(best['file'])})")
        rep.append(f"- {T}: {sum(len(v) for v in accepted[T].values())} values accepted")
    json.dump(accepted, open(os.path.join(a.work, "segments.json"), "w"), indent=1)
    open(os.path.join(a.work, "segments_check.md"), "w").write("\n".join(rep) + "\n")
    print("\n".join(rep))
    raise SystemExit(1 if bad else 0)


if __name__ == "__main__":
    main()
