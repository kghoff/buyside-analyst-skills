"""Step 10 - draw the report's charts, one spec per chart, in the house style (plain titles, simple over dense).

usage: python3 charts.py --src <ticker folder>     (reads _work/charts.json, writes <Filings Research>/fig/<id>.png)
Spec kinds (all need id, kind, title, source):
  line | bar | stacked | share   metrics, labels, freq FY|Q, start, end, unit       (from series.csv)
      a metrics entry is a series name, or a derived series (labels still name each one):
        {"ratio": [numerator, denominator]}  numerator / denominator x 100, in %; |numerator| is used so a cost
                                             line like "(-) Cost of Sales" gives a positive %; a missing input = gap
        {"growth": metric}                   yoy % vs the same period a year earlier (FY2024 vs FY2023, Q3 2024 vs Q3 2023)
  waterfall                     steps [[label, value], ...]; a label starting '=' is a total bar
  guidance                      metric [, basis]: initial guide range vs actual by year (guidance_track.csv)
  price                         events [[date, label], ...], start: ticker vs SPY indexed to 100 (price.csv)
  diagram                       boxes [{x, y, w, h, title, body}] on a 100x100 canvas, arrows [[x1, y1, x2, y2]]"""
import argparse, csv, datetime, json, logging, os, textwrap

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
from matplotlib.ticker import FuncFormatter

from common import load, phase_dir, work_dir
from drivers import load_series

BLUE, ORANGE, AQUA, YELLOW, MAGENTA, GREEN, VIOLET, RED = ("#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4",
                                                           "#008300", "#6250d6", "#e34948")
PALETTE = [BLUE, ORANGE, AQUA, YELLOW, MAGENTA, VIOLET, GREEN, RED]
INK, INK2, MUTED, GRID, SURF = "#0b0b0b", "#52514e", "#8a8984", "#e6e5e1", "#ffffff"
logging.getLogger("matplotlib.font_manager").setLevel(logging.ERROR)
THOUSANDS = FuncFormatter(lambda v, _: f"{v:,.0f}")
plt.rcParams.update({
    "font.family": ["Inter", "Helvetica", "Arial", "DejaVu Sans"], "font.size": 9, "axes.edgecolor": GRID,
    "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2, "axes.titlesize": 11,
    "axes.titleweight": "semibold", "axes.titlelocation": "left", "axes.titlecolor": INK, "axes.spines.top": False,
    "axes.spines.right": False, "axes.spines.left": False, "axes.grid": True, "axes.grid.axis": "y",
    "grid.color": GRID, "grid.linewidth": 0.6, "legend.frameon": False, "legend.fontsize": 8.5,
    "lines.linewidth": 2, "xtick.major.size": 0, "ytick.major.size": 0, "figure.facecolor": SURF, "axes.facecolor": SURF,
})


def periods(freq, start, end):
    if freq == "FY":
        return [f"FY{y}" for y in range(start, end + 1)]
    return [f"Q{q} {y}" for y in range(start, end + 1) for q in range(1, 5)]


def tick_marks(ps):
    """[(index, label)] - FY: every year; quarters: only Q1, labelled with the year."""
    if ps and ps[0].startswith("FY"):
        step = max(1, len(ps) // 12)
        return [(i, p[2:]) for i, p in enumerate(ps) if i % step == 0]
    marks = [(i, p[-4:]) for i, p in enumerate(ps) if p.startswith("Q1")]
    step = max(1, len(marks) // 12)
    return marks[::step]


def prior_year(p):
    return f"FY{int(p[2:]) - 1}" if p.startswith("FY") else f"{p[:-4]}{int(p[-4:]) - 1}"


def _inputs(m):
    if isinstance(m, dict):
        return list(m["ratio"]) if "ratio" in m else [m["growth"]]
    return [m]


def _value(m, p, series):
    if isinstance(m, str):
        return series[m].get(p)
    if "ratio" in m:
        num, den = series[m["ratio"][0]].get(p), series[m["ratio"][1]].get(p)
        return None if num is None or not den else abs(num) / den * 100
    now, before = series[m["growth"]].get(p), series[m["growth"]].get(prior_year(p))
    return None if now is None or not before else (now / before - 1) * 100


def _series_chart(ax, spec, series):
    missing = [n for m in spec["metrics"] for n in _inputs(m) if n not in series]
    if missing:
        raise ValueError(f"chart {spec['id']}: not in series.csv: {'; '.join(missing)}")
    ps = periods(spec.get("freq", "FY"), spec["start"], spec["end"])
    data = [[_value(m, p, series) for p in ps] for m in spec["metrics"]]
    keep = [i for i in range(len(ps)) if any(d[i] is not None for d in data)]
    ps, data = [ps[i] for i in keep], [[d[i] for i in keep] for d in data]
    if not ps:
        raise ValueError(f"chart {spec['id']}: no values for {spec['metrics']} in {spec['start']}-{spec['end']}")
    labels, x, kind = spec.get("labels", [m if isinstance(m, str) else json.dumps(m) for m in spec["metrics"]]), list(range(len(ps))), spec["kind"]
    if kind == "share":
        tot = [sum(abs(d[i] or 0) for d in data) or 1 for i in x]
        data = [[(d[i] or 0) / tot[i] * 100 for i in x] for d in data]
    if kind == "line":
        for d, l, c in zip(data, labels, PALETTE):
            ax.plot(x, [v if v is not None else float("nan") for v in d], label=l, color=c)
    elif kind == "bar":
        n = len(data)
        for i, (d, l, c) in enumerate(zip(data, labels, PALETTE)):
            ax.bar([xi + (i - (n - 1) / 2) * 0.8 / n for xi in x], [v or 0 for v in d], 0.8 / n, label=l, color=c)
    else:
        bottom = [0.0] * len(x)
        for d, l, c in zip(data, labels, PALETTE):
            vals = [v or 0 for v in d]
            ax.bar(x, vals, 0.75, bottom=bottom, label=l, color=c)
            bottom = [b + v for b, v in zip(bottom, vals)]
    marks = tick_marks(ps)
    ax.set_xticks([i for i, _ in marks])
    ax.set_xticklabels([l for _, l in marks])
    if kind != "share":
        ax.yaxis.set_major_formatter(THOUSANDS)
    if len(data) > 1:
        ax.legend(loc="lower left", bbox_to_anchor=(0, 1.02), ncol=len(data))
        return True
    return False


def _waterfall(ax, spec):
    level = 0
    steps = spec["steps"]
    for i, (label, v) in enumerate(steps):
        if label.startswith("="):
            bars = ax.bar(i, v, 0.6, color=BLUE)
            ax.bar_label(bars, fmt="{:,.0f}", fontsize=8, color=INK2, padding=2)
            level = v
        else:
            bars = ax.bar(i, v, 0.6, bottom=level, color=GREEN if v >= 0 else RED)
            ax.bar_label(bars, labels=[f"{v:+,.0f}"], fontsize=8, color=INK2, padding=2)
            level += v
    lows, highs, lvl = [0], [0], 0
    for label, v in steps:
        a, b = (0, v) if label.startswith("=") else (lvl, lvl + v)
        lvl = v if label.startswith("=") else lvl + v
        lows.append(min(a, b))
        highs.append(max(a, b))
    pad = 0.12 * (max(highs) - min(lows))
    ax.set_ylim(min(lows) - (pad if min(lows) < 0 else 0), max(highs) + pad)
    ax.yaxis.set_major_formatter(THOUSANDS)
    ax.set_ylabel(spec.get("unit", "$M"))
    ax.set_xticks(range(len(steps)))
    if len(steps) <= 7:
        ax.set_xticklabels([l.lstrip("=") for l, _ in steps])
    else:
        ax.set_xticklabels([l.lstrip("=") for l, _ in steps], rotation=30, ha="right")


def _guidance(ax, spec, work):
    with open(os.path.join(work, "guidance_track.csv"), newline="") as f:
        rows = [r for r in csv.DictReader(f) if r["metric"] == spec["metric"]
                and (not spec.get("basis") or r["basis"] == spec["basis"])]
    if not rows:
        raise ValueError(f"chart {spec['id']}: no guidance rows for {spec['metric']}")
    ax.margins(y=0.2)
    ax.set_xlim(-0.6, len(rows) - 0.4)
    ax.yaxis.set_major_formatter(THOUSANDS)
    ax.set_ylabel(spec.get("unit", ""))
    shown_latest = False
    for i, r in enumerate(rows):
        lo, hi = float(r["initial_low"] or r["initial_high"]), float(r["initial_high"] or r["initial_low"])
        ax.vlines(i - 0.08, lo, hi, lw=10, color="#86b6ef", label="Initial guide" if i == 0 else None)
        if r["latest_low"] or r["latest_high"]:
            llo = float(r["latest_low"] or r["latest_high"])
            lhi = float(r["latest_high"] or r["latest_low"])
            if (llo, lhi) != (lo, hi):
                ax.vlines(i + 0.08, llo, lhi, lw=5, color=BLUE, label=None if shown_latest else "Latest guide")
                shown_latest = True
        if r["actual"]:
            act = float(r["actual"])
            ax.scatter(i, act, color=ORANGE, zorder=3, label="Actual" if i == 0 else None)
            if r.get("vs_initial_mid"):
                ax.annotate(f"{float(r['vs_initial_mid']):+.1%} vs guide mid", (i, act), textcoords="offset points",
                            xytext=(0, 8), ha="center", fontsize=7.5, color=INK2)
    ax.set_xticks(range(len(rows)))
    ax.set_xticklabels([r["fiscal_year"] for r in rows])
    ax.legend(loc="lower left", bbox_to_anchor=(0, 1.02), ncol=3)
    return True


def _price(ax, spec, work):
    with open(os.path.join(work, "price.csv"), newline="") as f:
        px = [r for r in csv.DictReader(f) if r["date"] >= spec.get("start", "0000")]
    dates = [datetime.date.fromisoformat(r["date"]) for r in px]
    base = float(px[0]["close"])
    ax.plot(dates, [float(r["close"]) / base * 100 for r in px], color=BLUE, label=spec.get("ticker", "Stock"))
    spy = [(d, float(r["spy"])) for d, r in zip(dates, px) if r["spy"]]
    if spy:
        ax.plot([d for d, _ in spy], [v / spy[0][1] * 100 for _, v in spy], color=MUTED, lw=1.2, label="SPY")
    top = ax.get_ylim()[1]
    for d, label in spec.get("events", []):
        day = datetime.date.fromisoformat(d)
        ax.axvline(day, color=MUTED, lw=0.6, ls=":")
        ax.annotate(label, (day, top), rotation=90, fontsize=6.5, va="top", ha="right", color=INK2,
                    bbox=dict(fc="white", ec="none", alpha=0.85))
    ax.set_ylabel(spec.get("unit", "Indexed (start = 100)"))
    ax.legend(loc="upper left")


def _diagram(fig, ax, spec):
    fig.set_size_inches(9.2, 5.4)
    ax.set_xlim(0, 100)
    ax.set_ylim(min(b["y"] for b in spec["boxes"]) - 4, max(b["y"] + b["h"] for b in spec["boxes"]) + 4)
    ax.axis("off")
    for i, b in enumerate(spec["boxes"]):
        c = PALETTE[i % len(PALETTE)]
        ax.add_patch(FancyBboxPatch((b["x"], b["y"]), b["w"], b["h"], boxstyle="round,pad=0.4,rounding_size=1.2",
                                    fc=c + "1a", ec=c, lw=1.2))
        ax.text(b["x"] + 1.2, b["y"] + b["h"] - 2.2, b["title"], fontsize=8.6, weight="bold", color=INK, va="top")
        body = "\n".join(textwrap.fill(line, max(8, int(b["w"] * 1.6))) for line in b.get("body", "").split("\n"))
        ax.text(b["x"] + 1.2, b["y"] + b["h"] - 7.2, body, fontsize=7.2, color=INK2, va="top", linespacing=1.35)
    for x1, y1, x2, y2 in spec.get("arrows", []):
        ax.annotate("", (x2, y2), (x1, y1), arrowprops=dict(arrowstyle="-|>", color=MUTED, lw=1))


def draw(spec, series, work, fig_dir):
    for k in ("id", "kind", "title", "source"):
        if not spec.get(k):
            raise ValueError(f"chart {spec.get('id', '?')}: missing {k} (every chart needs a source line)")
    fig, ax = plt.subplots(figsize=(8.6, 3.6))
    try:
        kind = spec["kind"]
        legend_above = False
        if kind in ("line", "bar", "stacked", "share"):
            legend_above = _series_chart(ax, spec, series)
        elif kind == "waterfall":
            _waterfall(ax, spec)
        elif kind == "guidance":
            legend_above = _guidance(ax, spec, work)
        elif kind == "price":
            _price(ax, spec, work)
        elif kind == "diagram":
            _diagram(fig, ax, spec)
        else:
            raise ValueError(f"chart {spec['id']}: unknown kind {kind!r}")
        ax.set_title(spec["title"], pad=26 if legend_above else 6)
        if spec.get("unit"):
            ax.set_ylabel("%" if kind == "share" else spec["unit"])
        fig.canvas.draw()
        bb = ax.get_tightbbox().transformed(fig.transFigure.inverted())
        fig.text(bb.x0, bb.y0 - 0.02, "Source: " + spec["source"], fontsize=7, color=MUTED, ha="left", va="top")
        os.makedirs(fig_dir, exist_ok=True)
        out = os.path.join(fig_dir, spec["id"] + ".png")
        fig.savefig(out, bbox_inches="tight", facecolor=SURF, dpi=200)
        return out
    finally:
        plt.close(fig)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    a = ap.parse_args()
    w = work_dir(a.src)
    series = load_series(os.path.join(w, "series.csv"))
    errors = 0
    for spec in load(os.path.join(w, "charts.json")):
        try:
            print("wrote", draw(spec, series, w, os.path.join(phase_dir(a.src), "fig")))
        except (ValueError, KeyError, FileNotFoundError) as e:
            errors += 1
            print("FAILED", e)
    raise SystemExit(1 if errors else 0)
