"""Step 4 - merge every reader's and researcher's marks onto the ledger.

usage: python3 merge_marks.py --src <ticker folder>
Writes in _work/: marks_all.csv (every mark + 'by' = reader/researcher id), ledger_marked.csv (ledger + a count per
stance + marks_summary), stance_matrix.csv (topic, holder_type, stance, count), gap_status.csv
(n, group, title, status, best_tier, sources) and new_views.md (marks with claim_id NEW).
marks_summary is mechanical (any differs > any adds > any gap-closed > agrees); the synthesis agent judges."""
import argparse, collections, glob, os

from p2common import MARK_COLS, STANCES, load, read_csv, work_dir, write_csv

RANK = {"primary": 0, "secondary": 1, "opinion": 2}


def summary(counts):
    if not any(counts.values()):
        return "no outside view"
    for s in ("differs", "adds", "gap-closed"):
        if counts[s]:
            return s
    return "agrees"


def gap_status(marks):
    tiers = sorted({m["tier"] for m in marks if m["stance"] == "gap-closed" and m["tier"] in RANK}, key=RANK.get)
    if tiers and tiers[0] in ("primary", "secondary"):
        status = "closed-fact"
    elif tiers or any(m["stance"] in ("differs", "adds") for m in marks):
        status = "estimate-only"
    else:
        status = "open"
    return status, (tiers[0] if tiers else "")


def merge(src):
    w = work_dir(src)
    _, ledger = read_csv(os.path.join(w, "ledger.csv"))
    marks = []
    for path in sorted(glob.glob(os.path.join(w, "readers", "*", "marks.csv")) +
                       glob.glob(os.path.join(w, "research", "*", "marks.csv"))):
        by = os.path.basename(os.path.dirname(path))
        marks += [dict(r, by=by) for r in read_csv(path)[1]]
    write_csv(os.path.join(w, "marks_all.csv"), MARK_COLS + ["by"], marks)

    per = collections.defaultdict(list)
    for mk in marks:
        per[mk["claim_id"].strip()].append(mk)
    out = []
    for r in ledger:
        counts = collections.Counter(mk["stance"] for mk in per[r["id"]])
        out.append(dict(r, **{s: counts[s] for s in STANCES}, marks_summary=summary(counts)))
    write_csv(os.path.join(w, "ledger_marked.csv"), list(ledger[0]) + list(STANCES) + ["marks_summary"] if ledger else [], out)

    topic = {r["id"]: r["topic"] for r in ledger}
    mat = collections.Counter((topic.get(mk["claim_id"].strip(), "new"), mk["holder_type"], mk["stance"]) for mk in marks)
    write_csv(os.path.join(w, "stance_matrix.csv"), ["topic", "holder_type", "stance", "count"],
              [{"topic": t, "holder_type": h, "stance": s, "count": c} for (t, h, s), c in sorted(mat.items())])

    rows = []
    for g in load(os.path.join(w, "gaps.json"), []):
        gm = per[f"G{g['n']}"]
        status, tier = gap_status(gm)
        rows.append({"n": g["n"], "group": g.get("group", ""), "title": g.get("title", ""), "status": status,
                     "best_tier": tier, "sources": "; ".join(sorted({mk["source"] for mk in gm}))})
    write_csv(os.path.join(w, "gap_status.csv"), ["n", "group", "title", "status", "best_tier", "sources"], rows)

    new = [mk for mk in marks if mk["claim_id"].strip() == "NEW"]
    lines = ["# Views with no ledger row (claim_id NEW)", ""]
    lines += [f"- ({mk['stance']}, {mk['holder_type']}, {mk['by']}) {mk['holder']}: {mk['view']} Why: {mk['reasoning']} "
              f"[{mk['source']}]" for mk in new] or ["None."]
    open(os.path.join(w, "new_views.md"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
    return len(marks), len(new)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    n, new = merge(ap.parse_args().src)
    print(f"{n} marks merged, {new} new views")
