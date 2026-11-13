"""Each broker's own estimates, from the reports the user drops into Sellside Research (no free feed has them).

  cut    --work W --sellside DIR   for each covering analyst firm, its newest report Markdown with an estimates table
                                    (in the broker folder or, if filed there, the independent-research folder)
                                    -> W/snippets/<slug>.md (lines "L<n>: ..."); for each rating shop / quant firm, the
                                    first page of its newest report. Writes W/estimates_plan.json, with each period
                                    label's end date ("periods") so the reader maps a broker's columns by end month.
  check  --work W                  every value in W/values/<slug>.json must be printed on its cited line (raw), equal
                                    raw x scale, and (eps / revenue) name one of the table's periods; a stated
                                    period_end ("YYYY-MM") must be within 1 month of that label's end (no period_end:
                                    accepted, noted). Writes W/checked.json; exit 1 if anything was rejected.
  choose --work W                  newest report wins per firm / metric / period; stale = report more than 3 days older
                                    than the firm's last rating action, or more than 90 days old. Writes W/estimates.json.

Folder layout: "<Sellside Research>/1 Broker Research/_md" and "2 Independent Research/_md" (/collect-documents's tiers),
or a flat "<Sellside Research>/_md" for folders gathered before the tiers."""
import argparse
import glob
import json
import os
import re
import sys
from datetime import date

import firms as FM
import periods
import ratings
import snapshots

TYPES = ["initiation", "deep dive", "industry", "preview", "flash note", "earnings recap", "rating change",
         "event takeaways", "survey", "company report", "quant rating"]
NAME = re.compile(r"^(\d{4}-\d{2}-\d{2}) (.+?) (" + "|".join(TYPES) + r")\b")
EST = re.compile(r"\bEPS\b|revenue|net sales|\bsales\b", re.I)
STALE_DAYS, SAME_EVENT_DAYS, COVER_LINES = 90, 3, 80


def parse_name(path):
    m = NAME.match(os.path.basename(path))
    return (date.fromisoformat(m.group(1)), m.group(2), m.group(3)) if m else None


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def num(raw):
    s = str(raw).strip().replace("–", "-").replace("−", "-")
    s = re.sub(r"[$€£\s]", "", s)
    s = re.sub(r"[⁰¹²³⁴⁵⁶⁷⁸⁹]+$", "", s)
    s = re.sub(r"[\[(][a-zA-Z][\])]$", "", s)                  # footnote letter: [a] or (a)
    s = re.sub(r"(?<=\d)[EAea*]+$|\*+$", "", s)
    neg = s.startswith("(") and s.endswith(")")
    s = re.sub(r"[()x,%]", "", s)
    v = float(s)
    return -v if neg else v


def cut_lines(path):
    """Indices of the lines to keep: every Markdown table with an EPS / revenue / sales row, plus up to 2 non-blank
    lines above it (its title)."""
    lines = open(path, errors="ignore").read().splitlines()
    keep, i = set(), 0
    while i < len(lines):
        if lines[i].lstrip().startswith("|"):
            j = i
            while j < len(lines) and lines[j].lstrip().startswith("|"):
                j += 1
            if any(EST.search(lines[k]) for k in range(i, j)):
                keep.update(range(i, j))
                above = [k for k in range(max(0, i - 4), i) if lines[k].strip()][-2:]
                keep.update(above)
            i = j
        else:
            i += 1
    return sorted(keep)


def _write_snippet(out, path, idx):
    lines = open(path, errors="ignore").read().splitlines()
    with open(out, "w") as f:
        f.write(f"## {path}\n\n")
        for i in idx:
            f.write(f"L{i + 1}: {lines[i]}\n")


def _dirs(sellside):
    b, i = os.path.join(sellside, "1 Broker Research", "_md"), os.path.join(sellside, "2 Independent Research", "_md")
    if os.path.isdir(b) or os.path.isdir(i):
        return [b], [i]
    flat = os.path.join(sellside, "_md")
    return [flat], [flat]


def _reports(dirs, F, asof):
    by = {}
    for p in sorted({p for d in dirs for p in glob.glob(os.path.join(d, "*.md"))}):
        n = parse_name(p)
        f = F.match(n[1]) if n else None
        if n and f and n[0] <= asof:
            by.setdefault(f["name"], []).append((n[0], p))
    return {k: sorted(v, reverse=True) for k, v in by.items()}


def _unmatched(dirs, F, asof):
    """Report files whose name does not parse or whose firm is not in firms.json (they would be silently ignored)."""
    out, seen = [], set()
    for d in dirs:
        for p in sorted(glob.glob(os.path.join(d, "*.md"))):
            if p in seen:
                continue
            seen.add(p)
            n = parse_name(p)
            if not n:
                out.append({"file": p, "why": "file name does not parse"})
            elif not F.match(n[1]):
                out.append({"file": p, "why": f"firm {n[1]!r} does not match firms.json"})
    return out


def cut(work, sellside):
    F = FM.Firms()
    snap = snapshots.load_all(work)[-1]
    asof = date.fromisoformat(snap["asof"])
    rows, _ = ratings.latest_by_firm(ratings.actions(snap, F), asof)
    analysts = {r["firm"] for r in ratings.split_types(rows)[0]} | set(ratings.nasdaq_covering(snap, F, rows))
    bdirs, idirs = _dirs(sellside)
    os.makedirs(os.path.join(work, "snippets"), exist_ok=True)
    warnings = []
    try:
        c = snapshots.consensus(snap, periods.fye_month(snap))
    except ValueError as e:
        warnings.append(f"Consensus periods unreadable ({e}); period labels unknown, so no broker estimates can be "
                        "matched to a period this run.")
        print("WARNING: " + warnings[-1], file=sys.stderr)
        c = {"labels": {k: None for k in snapshots.CODES}}
    ends = c.get("ends") or {}
    plan = {"labels": c["labels"], "periods": {lab: ends.get(k) for k, lab in c["labels"].items() if lab and ends.get(k)},
            "firms": [], "skipped": _unmatched(bdirs + idirs, F, asof), "warnings": warnings}
    # analyst firms: newest report with an estimates table, wherever it was filed (broker or independent folder)
    for firm, reps in _reports(bdirs + idirs, F, asof).items():
        if firm not in analysts:
            continue
        found = False
        for d, p in reps:
            idx = cut_lines(p)
            if idx:
                out = os.path.join(work, "snippets", f"{slug(firm)}.md")
                _write_snippet(out, p, idx)
                plan["firms"].append({"firm": firm, "kind": "broker", "file": p, "date": d.isoformat(), "snippet": out})
                found = True
                break
        if not found:
            plan["skipped"].append({"firm": firm, "file": reps[0][1], "why": "no EPS/revenue table"})
    for firm, reps in _reports(idirs, F, asof).items():
        f = F.match(firm)
        if f and f["type"] in ("rating shop", "quant"):
            d, p = reps[0]
            out = os.path.join(work, "snippets", f"{slug(firm)}.md")
            n = len(open(p, errors="ignore").read().splitlines())
            _write_snippet(out, p, list(range(min(COVER_LINES, n))))
            plan["firms"].append({"firm": firm, "kind": "shop", "file": p, "date": d.isoformat(), "snippet": out})
    json.dump(plan, open(os.path.join(work, "estimates_plan.json"), "w"), indent=1)
    return plan


def _months(ym_text):
    y, m = str(ym_text).strip()[:7].split("-")
    return int(y) * 12 + int(m)


def check_entry(v, labels, ends=None):
    """(ok, why). ends: {label: "YYYY-MM-DD"} period end dates from the plan. An eps / revenue value without a
    period_end is accepted but gets "period end not stated" added to its note (v is changed in place)."""
    try:
        n = int(v["line_no"])
        if n < 1:
            return False, "line_no must be 1 or more"
        line = open(v["file"], errors="ignore").read().splitlines()[n - 1]
    except (OSError, IndexError, KeyError, ValueError, TypeError):
        return False, "file or line not found"
    squash = lambda s: re.sub(r"\s+", " ", str(s)).strip()
    raw = squash(v.get("raw", ""))
    sq = squash(line)
    pat = re.compile(r"(?<![\d.,])" + re.escape(raw) + r"(?![\d.,])") if raw else None
    if not pat or not (pat.search(sq) or pat.search(sq.replace("\\|", "|"))):
        return False, f"raw {v.get('raw')!r} is not printed on line {v.get('line_no')}"
    metric = v.get("metric")
    if metric in ("eps", "revenue", "target"):
        try:
            want = num(v["raw"]) * float(v.get("scale", 1))
            got = float(v["value"])
        except (ValueError, TypeError, KeyError):
            return False, f"raw {v.get('raw')!r}, scale {v.get('scale')!r} or value {v.get('value')!r} is not a number"
        if abs(want - got) > 1e-6 * max(1.0, abs(want)):
            return False, f"value {v['value']} ≠ raw × scale ({want})"
    elif metric == "rating":
        if squash(v.get("value", "")) != raw:
            return False, "rating value must equal raw"
    else:
        return False, f"unknown metric {metric!r}"
    if metric in ("eps", "revenue"):
        if v.get("period") not in labels:
            return False, f"period {v.get('period')!r} is not one of {sorted(labels)}"
        pe, end = v.get("period_end"), (ends or {}).get(v["period"])
        if pe in (None, ""):
            v["note"] = "; ".join(x for x in (v.get("note"), "period end not stated") if x)
        else:
            if not re.match(r"^\d{4}-\d{2}(-\d{2})?$", str(pe).strip()):
                return False, f"period_end {pe!r} is not YYYY-MM"
            if end and abs(_months(pe) - _months(end)) > 1:
                return False, (f"period end {pe} does not match {v['period']}, which ends {end[:7]} "
                               "(map the report's columns by period end month)")
    return True, ""


def check(work):
    plan = json.load(open(os.path.join(work, "estimates_plan.json")))
    labels = {x for x in plan["labels"].values() if x}
    ends = plan.get("periods") or {}
    acc, rej = [], []
    for e in plan["firms"]:
        p = os.path.join(work, "values", f"{slug(e['firm'])}.json")
        if not os.path.exists(p):
            continue
        for v in json.load(open(p)):
            v["firm"] = e["firm"]
            ok, why = check_entry(v, labels, ends)
            (acc if ok else rej).append(v if ok else {**v, "why": why})
    json.dump({"accepted": acc, "rejected": rej}, open(os.path.join(work, "checked.json"), "w"), indent=1)
    return acc, rej


def is_stale(report_date, last_action, asof):
    """A report is stale when it is more than 3 days older than the firm's last rating action (a later event it
    doesn't reflect), or more than 90 days old."""
    return bool((last_action and (last_action - report_date).days > SAME_EVENT_DAYS)
                or (asof - report_date).days > STALE_DAYS)


def choose(accepted, last_action, asof):
    out = {}
    for v in accepted:
        n = parse_name(v["file"])
        d = n[0] if n else asof
        f = out.setdefault(v["firm"], {"date": None, "file": None, "stale": False, "values": {}})
        cur = f["values"].setdefault(v["metric"], {}).get(v.get("period") or "-")
        if cur is None or d > date.fromisoformat(cur["report_date"]):
            f["values"][v["metric"]][v.get("period") or "-"] = {**v, "report_date": d.isoformat()}
        if f["date"] is None or d.isoformat() > f["date"]:
            f["date"], f["file"] = d.isoformat(), v["file"]
    for firm, f in out.items():
        f["stale"] = is_stale(date.fromisoformat(f["date"]), last_action.get(firm), asof)
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["cut", "check", "choose"])
    ap.add_argument("--work", required=True)
    ap.add_argument("--sellside")
    a = ap.parse_args()
    if a.cmd == "cut":
        if not a.sellside:
            sys.exit("cut needs --sellside")
        plan = cut(a.work, a.sellside)
        print(json.dumps({"labels": plan["labels"], "periods": plan["periods"], "warnings": plan["warnings"], "firms": [(e["firm"], e["kind"], os.path.basename(e["file"]))
                                                              for e in plan["firms"]], "skipped": plan["skipped"]}, indent=1))
    elif a.cmd == "check":
        acc, rej = check(a.work)
        print(json.dumps({"accepted": len(acc), "rejected": [(r["firm"], r["metric"], r.get("period"), r["why"]) for r in rej]},
                         indent=1))
        sys.exit(1 if rej else 0)
    else:
        snap = snapshots.load_all(a.work)[-1]
        asof = date.fromisoformat(snap["asof"])
        rows, _ = ratings.latest_by_firm(ratings.actions(snap, FM.Firms()), asof)
        acc = json.load(open(os.path.join(a.work, "checked.json")))["accepted"]
        out = choose(acc, {r["firm"]: r["date"] for r in rows}, asof)
        json.dump(out, open(os.path.join(a.work, "estimates.json"), "w"), indent=1)
        print(json.dumps({f: {"date": v["date"], "stale": v["stale"], "metrics": sorted(v["values"])} for f, v in out.items()},
                         indent=1))
