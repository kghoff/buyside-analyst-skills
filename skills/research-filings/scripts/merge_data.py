"""Step 7 - merge the model with what the readers found, flag conflicts, build the coverage and guidance tables.

usage: python3 merge_data.py --src <ticker folder>
Inputs: _work/model_series.csv, _work/readers/*/data.csv and guidance.csv, _work/inventory.json (document dates).
Writes: series.csv (model + reader numbers; the model wins, then the newest document), conflicts.md,
coverage.md + coverage.json (which years each metric was disclosed), guidance_track.csv."""
import argparse, csv, glob, os, re

from common import load, save, work_dir

TOL = 0.005
COLS = ["metric", "period", "value", "unit", "source"]
TRACK = ["fiscal_year", "metric", "basis", "initial_date", "initial_kind", "initial_low", "initial_high", "revisions",
         "latest_date", "latest_low", "latest_high", "actual", "vs_initial_mid", "sources"]


def _label(source, labels):
    s = source.strip()
    return max((l for l in labels if s == l or s.startswith(l + ",")), key=len, default=s.split(",")[0])


def merge(model_rows, reader_rows, doc_dates):
    by = {}
    for x in model_rows:
        by.setdefault((x["metric"], x["period"]), []).append((x, (1, "")))
    for x in reader_rows:
        by.setdefault((x["metric"], x["period"]), []).append((x, (0, doc_dates.get(_label(x["source"], doc_dates), ""))))
    rows, conflicts = [], []
    for (metric, period), cands in by.items():
        best = max(cands, key=lambda c: c[1])[0]
        b = float(best["value"])
        others = [c[0] for c in cands if c[0] is not best and abs(float(c[0]["value"]) - b) > TOL * max(abs(b), 1e-9)]
        if others:
            conflicts.append({"metric": metric, "period": period, "kept": best, "others": others})
        rows.append({k: best[k] for k in COLS})
    return rows, conflicts


def _year(period):
    m = re.search(r"(\d{4})", period)
    return int(m.group(1)) if m else None


def coverage(rows):
    yrs = {}
    for x in rows:
        y = _year(x["period"])
        if y:
            yrs.setdefault(x["metric"], set()).add(y)
    out = {}
    for m, ys in yrs.items():
        lo, hi = min(ys), max(ys)
        out[m] = {"first": lo, "last": hi, "years": len(ys), "gaps": [y for y in range(lo, hi + 1) if y not in ys],
                  "from": "model" if any(x["source"].startswith("Model,") for x in rows if x["metric"] == m) else "documents"}
    return out


def coverage_table(cov, min_years=1):
    lines = ["| Metric | From | First | Last | Years | Gaps |", "|---|---|---|---|---|---|"]
    lines += [f"| {m.replace('|', chr(92) + '|')} | {c['from']} | {c['first']} | {c['last']} | {c['years']} | {', '.join(map(str, c['gaps']))} |"
              for m, c in sorted(cov.items(), key=lambda kv: (kv[1]["from"], kv[0])) if c["years"] >= min_years]
    return lines


def _num(s):
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def fill_dates(guides, doc_dates):
    """Give guidance rows whose date is not YYYY-MM-DD the inventory date of the document they cite."""
    out, undated = [], 0
    for g in guides:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", g["date"].strip()):
            d = doc_dates.get(_label(g["source"], doc_dates), "")
            if d:
                g = {**g, "date": d}
            else:
                undated += 1
        out.append(g)
    return out, undated


def track(guides):
    groups = {}
    for g in guides:
        groups.setdefault((g["fiscal_year"], g["metric"], g["basis"]), []).append(g)
    out = []
    for (fy, metric, basis), rows in sorted(groups.items()):
        rows.sort(key=lambda g: g["date"])
        guided = [g for g in rows if g["low"] or g["high"]]
        actual = next((g["actual"] for g in reversed(rows) if g["actual"]), "")
        if not guided:
            continue
        i, l = guided[0], guided[-1]
        lo, hi, a = _num(i["low"]), _num(i["high"]), _num(actual)
        mid = (lo + hi) / 2 if lo is not None and hi is not None else (lo if hi is None else hi)
        out.append({"fiscal_year": fy, "metric": metric, "basis": basis, "initial_date": i["date"],
                    "initial_kind": i["kind"], "initial_low": i["low"], "initial_high": i["high"],
                    "revisions": sum(1 for a, b in zip(guided, guided[1:]) if (a["low"], a["high"]) != (b["low"], b["high"])), "latest_date": l["date"], "latest_low": l["low"],
                    "latest_high": l["high"], "actual": actual,
                    "vs_initial_mid": (a / mid - 1) if a is not None and mid else "",
                    "sources": "; ".join(dict.fromkeys(g["source"] for g in rows))})
    return out


def _read(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def run(src):
    w = work_dir(src)
    dates = {d["label"]: d["date"] or "" for d in load(os.path.join(w, "inventory.json"))}
    model_rows = _read(os.path.join(w, "model_series.csv"))
    reader_rows = [x for p in sorted(glob.glob(os.path.join(w, "readers", "*", "data.csv"))) for x in _read(p)]
    guides = [x for p in sorted(glob.glob(os.path.join(w, "readers", "*", "guidance.csv"))) for x in _read(p)]
    rows, conflicts = merge(model_rows, reader_rows, dates)
    with open(os.path.join(w, "series.csv"), "w", newline="", encoding="utf-8") as f:
        wr = csv.DictWriter(f, COLS)
        wr.writeheader()
        wr.writerows(rows)
    cov = coverage(rows)
    save(os.path.join(w, "coverage.json"), cov)
    open(os.path.join(w, "coverage.md"), "w", encoding="utf-8").write("\n".join(["# Disclosure coverage", ""] + coverage_table(cov)) + "\n")
    open(os.path.join(w, "coverage_key.md"), "w", encoding="utf-8").write("\n".join(
        ["# Disclosure coverage (metrics with 3+ years; full list in coverage.md)", ""] + coverage_table(cov, 3)) + "\n")
    cl = ["# Conflicts between sources", "", "Kept value first; the model wins, then the newest document.", ""]
    for c in conflicts:
        cl.append(f"- {c['metric']} {c['period']}: kept {c['kept']['value']} [{c['kept']['source']}]; also "
                  + "; ".join(f"{o['value']} [{o['source']}]" for o in c["others"]))
    open(os.path.join(w, "conflicts.md"), "w", encoding="utf-8").write("\n".join(cl) + "\n")
    guides, undated = fill_dates(guides, dates)
    t = track(guides)
    with open(os.path.join(w, "guidance_track.csv"), "w", newline="", encoding="utf-8") as f:
        wr = csv.DictWriter(f, TRACK)
        wr.writeheader()
        wr.writerows(t)
    return len(rows), len(conflicts), len(cov), len(t), undated


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    n, c, m, g, u = run(ap.parse_args().src)
    print(f"{n} values, {c} conflicts, {m} metrics in coverage, {g} guidance lines, {u} guidance_undated")
