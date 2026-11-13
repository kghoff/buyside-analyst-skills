"""Step 7 - the street research figures, drawn in research-filings' chart style.

usage: python3 p2charts.py --src <ticker folder> sheets | all
  sheets   contact sheets of every sell-side PDF (_work/sheets/<label>/sheet-NN.jpg, pages tagged S1, S2...)
  all      fig/stance_heatmap.png (stance_matrix.csv), fig/gap_status.png (gap_status.csv), every spec in
           _work/charts.json (research-filings kinds price | waterfall | diagram; price uses research-filings' price.csv) and every
           sell-side page in _work/grabs.json [{file: <label>, page, out, crop: [l,t,r,b] or null, caption}]"""
import argparse, collections, os

from matplotlib.colors import LinearSegmentedColormap
from matplotlib.patches import Rectangle

from p2common import load, p1_work, phase_dir, read_csv, work_dir   # first: puts research-filings' scripts on sys.path
import charts, slides   # the filings research (charts sets the style and the Agg backend)
from charts import GREEN, INK, INK2, MUTED, RED, YELLOW, plt

LEAN = LinearSegmentedColormap.from_list("lean", [GREEN, "#f2f1ec", RED])
# "partial" is set after the PM review downgrades a closed gap; gap_status.csv may not have any.
STATUS = [("closed-fact", GREEN, "Closed with a fact"), ("partial", "#8fbf8f", "Partly closed"),
          ("estimate-only", YELLOW, "Estimate only"), ("open", MUTED, "Still open")]
SERIES_KINDS = {"line", "bar", "stacked", "share", "guidance"}


def lean(counts):
    """Share of marks that differ from or add to the company view (0 = all agree, 1 = none agree)."""
    n = sum(counts.values())
    return None if not n else (n - counts.get("agrees", 0)) / n


def _order(t):
    return (0, t) if t.startswith("driver") else (1, ["industry", "plan", "debate", "turning", "gap", "other", "new"].index(t)
                                                  if t in ("industry", "plan", "debate", "turning", "gap", "other", "new") else 9)


def heatmap(rows, fig_dir):
    cells = collections.defaultdict(collections.Counter)
    for r in rows:
        if r["stance"] != "gap-closed":
            cells[(r["topic"], r["holder_type"])][r["stance"]] += int(r["count"])
    if not cells:
        return None
    topics = sorted({t for t, _ in cells}, key=_order)
    holders = sorted({h for _, h in cells})
    fig, ax = plt.subplots(figsize=(8.6, 0.45 * len(topics) + 1.6))
    for i, t in enumerate(topics):
        for j, h in enumerate(holders):
            c = cells.get((t, h))
            v = lean(c) if c else None
            ax.add_patch(Rectangle((j, i), 0.96, 0.9, fc=LEAN(v) if v is not None else "white", ec="#e6e5e1"))
            if c:
                ax.text(j + 0.48, i + 0.45, str(sum(c.values())), ha="center", va="center", fontsize=8, color=INK)
    ax.set_xlim(0, len(holders))
    ax.set_ylim(len(topics), 0)
    ax.set_xticks([j + 0.48 for j in range(len(holders))], holders)
    ax.set_yticks([i + 0.45 for i in range(len(topics))], topics)
    ax.grid(False)
    ax.set_title("Where outside views agree (green) or differ (red), by topic and source type")
    fig.text(0.01, -0.03, "Number = marks. Source: _work/stance_matrix.csv (every sell-side and web mark).",
             fontsize=7, color=MUTED)
    return _save(fig, fig_dir, "stance_heatmap")


def gap_chart(rows, fig_dir):
    if not rows:
        return None
    groups = list(dict.fromkeys(r["group"] or "Other" for r in rows))
    fig, ax = plt.subplots(figsize=(8.6, 0.42 * len(groups) + 1.4))
    left = [0] * len(groups)
    for key, color, label in STATUS:
        vals = [sum(1 for r in rows if (r["group"] or "Other") == g and r["status"] == key) for g in groups]
        ax.barh(groups, vals, left=left, color=color, label=label)
        left = [a + b for a, b in zip(left, vals)]
    ax.invert_yaxis()
    ax.grid(False)
    ax.legend(loc="lower right")
    ax.set_title("Open questions from the filings research, after the street research")
    ax.set_xlabel("Gaps", color=INK2)
    ax.xaxis.get_major_locator().set_params(integer=True)
    fig.text(0.01, -0.05, "Source: _work/gap_status.csv.", fontsize=7, color=MUTED)
    return _save(fig, fig_dir, "gap_status")


def _save(fig, fig_dir, name):
    os.makedirs(fig_dir, exist_ok=True)
    out = os.path.join(fig_dir, name + ".png")
    fig.savefig(out, bbox_inches="tight", dpi=200)
    plt.close(fig)
    return out


def draw_all(src):
    w, fig_dir, errors = work_dir(src), os.path.join(phase_dir(src), "fig"), []
    if os.path.exists(os.path.join(w, "stance_matrix.csv")):
        heatmap(read_csv(os.path.join(w, "stance_matrix.csv"))[1], fig_dir)
    if os.path.exists(os.path.join(w, "gap_status.csv")):
        gap_chart(read_csv(os.path.join(w, "gap_status.csv"))[1], fig_dir)
    for spec in load(os.path.join(w, "charts.json"), []) or []:
        if spec.get("kind") in SERIES_KINDS:
            errors.append(f"chart {spec.get('id')}: the street research has no series.csv; use price, waterfall or diagram")
            continue
        try:
            charts.draw(spec, {}, p1_work(src), fig_dir)
        except (ValueError, KeyError, FileNotFoundError) as e:
            errors.append(f"chart {spec.get('id')}: {e}")
    pdfs = {it["label"]: it["pdf"] for it in load(os.path.join(w, "run.json"))["sellside"]}
    for g in load(os.path.join(w, "grabs.json"), []) or []:
        try:
            slides.grab(os.path.join(src, pdfs[g["file"]]), g["page"], os.path.join(fig_dir, g["out"]),
                        crop=tuple(g["crop"]) if g.get("crop") else None)
        except Exception as e:   # one bad pick must not stop the rest; it is reported and fixed in grabs.json
            errors.append(f"grab {g.get('out')}: {e}")
    return errors


def all_sheets(src):
    n = 0
    for it in load(os.path.join(work_dir(src), "run.json"))["sellside"]:
        if it["pdf"] and os.path.exists(os.path.join(src, it["pdf"])):
            n += slides.sheets(os.path.join(src, it["pdf"]), os.path.join(work_dir(src), "sheets", it["label"]))
    return n


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("cmd", choices=["sheets", "all"])
    a = ap.parse_args()
    if a.cmd == "sheets":
        print(f"{all_sheets(a.src)} sell-side pages on contact sheets")
    else:
        errs = draw_all(a.src)
        print("\n".join(errs) if errs else "all figures drawn")
        raise SystemExit(1 if errs else 0)
