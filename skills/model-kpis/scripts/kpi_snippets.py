"""KPI step 3 - for each metric in kpi_plan.json, every line in the source folder that matches its patterns, grouped
by document period, so the readers (subagents) see each period's evidence in one place.

usage: python3 kpi_snippets.py --src <source folder> --work <work_dir> --plan <work>/kpi_plan.json

Table rows come with their table's header row (it says which column is which period). Long paragraphs (call
transcripts) are cut to a window around the match. Writes <work>/snippets/<key>.md and prints hits per metric."""
import argparse, json, os, re
from kpi_scan import newest_key
from ng_extract import discover

WINDOW = 350
MAX_PER_DOC = 15


def table_header(L, i):
    j = i
    while j > 0 and L[j - 1].lstrip().startswith("|"): j -= 1
    return L[j].strip() if j != i else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True); ap.add_argument("--work", required=True); ap.add_argument("--plan", required=True)
    a = ap.parse_args()
    plan = json.load(open(a.plan)); out_dir = os.path.join(a.work, "snippets"); os.makedirs(out_dir, exist_ok=True)
    docs, _ = discover(a.src)
    docs.sort(key=newest_key)
    texts = {d["path"]: open(d["path"], encoding="utf-8", errors="ignore").read().split("\n") for d in docs}
    for m in plan["metrics"]:
        rx = re.compile("|".join(f"(?:{p})" for p in m["patterns"]), re.I)
        types = set(m.get("doc_types") or [])
        parts, hits, pers = [], 0, set()
        for d in docs:
            if types and d["type"] not in types: continue
            L = texts[d["path"]]; got = []
            for i, l in enumerate(L):
                mm = rx.search(l)
                if not mm: continue
                if l.lstrip().startswith("|"):
                    h = table_header(L, i)
                    got.append((i + 1, (f"[table header] {h}\n      " if h else "") + l.strip()))
                else:
                    s, e = max(0, mm.start() - WINDOW), mm.end() + WINDOW
                    got.append((i + 1, ("…" if s else "") + l[s:e].strip() + ("…" if e < len(l) else "")))
                if len(got) >= MAX_PER_DOC: break
            if got:
                hits += len(got); pers.add(d["period"] or d.get("date"))
                rel = os.path.relpath(d["path"], a.src)
                parts.append(f"## {d['period'] or 'undated'} | {d['type']} | `{rel}`\n\n" + "\n".join(f"- L{n}: {t}" for n, t in got) + "\n")
        with open(os.path.join(out_dir, f"{m['key']}.md"), "w") as f:
            f.write(f"# {m['label']} ({m['units']}, {m['kind']})\n\nDefinition: {m.get('definition', '')}\nPatterns: {m['patterns']}\n"
                    f"{hits} matching lines in {len(parts)} documents.\n\n" + "\n".join(parts))
        print(f"  {m['key']}: {hits} lines in {len(parts)} documents")


if __name__ == "__main__":
    main()
