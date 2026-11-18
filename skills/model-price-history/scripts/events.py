"""Propose the Px Events list from the /collect-documents folder: full-results release date per quarter, preliminary-revenue
releases, other releases and investor events, each with its source file and reaction timing.

usage: python3 events.py --src <gather folder> --model M.xlsx --out W/events.json
The JSON is a PROPOSAL. Read its `review` list and fix what it flags before building (the skill's Step 2).

- Release files: "<Press Releases>/_md/<FY> Q<n> <T> release <YYYY-MM-DD>[ EX-99.xx].md". EX-99.2+ side exhibits
  are skipped. A release is "full results" when it has a diluted-EPS line inside a table.
- Timing: "After close" (reaction the next trading day) when the call is at/after 4pm ET or the text says after the
  close; "Same day" when the call is before 9:30am ET or the text says before the open. Preliminary releases and
  investor events default to "Same day". Anything assumed is listed in `review`.
- Investor events: "<Investor Events>/_md/<YYYY-MM-DD> <T> <name>.md", "Same day".
- Events dated before Jan 1 of MOD's first fiscal year are left out (the chart starts there)."""
import argparse
import datetime as dt
import json
import os
import re

import modmap

REL_RE = re.compile(r"^(\d{4}) Q([1-4]) (\S+) release (\d{4}-\d\d-\d\d)(.*)\.md$")
EVT_RE = re.compile(r"^(\d{4}-\d\d-\d\d) (\S+) (.+)\.md$")
MAIN_EXHIBIT = re.compile(r"^\s*(EX-99\.0?1|EX-99)?\s*$", re.I)
MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"
TZ = {"eastern": 0, "et": 0, "est": 0, "edt": 0, "central": 1, "ct": 1, "cst": 1, "cdt": 1, "mountain": 2, "mt": 2,
      "pacific": 3, "pt": 3, "pst": 3, "pdt": 3}


def md_files(folder):
    d = os.path.join(folder, "_md")
    d = d if os.path.isdir(d) else folder
    return sorted(f for f in os.listdir(d) if f.endswith(".md")), d if os.path.isdir(folder) else None


def is_full(text):
    for line in text.splitlines():
        if "|" in line and re.search(r"diluted", line, re.I) and re.search(r"per share|EPS|net (income|loss)", line, re.I):
            return True
    return False


def headline(text):
    for line in text.splitlines():
        s = line.strip().strip("*#_ ").strip()
        if len(s) > 25 and not s.lower().startswith(("ex-99", "exhibit", "<!--", "![", "|")):
            return s[:160]
    return ""


def timing(text, default):
    t = re.sub(r"\s+", " ", text)
    m = re.search(r"(\d{1,2})(?::(\d\d))?\s*([ap])\.?\s?m\.?,?\s*\(?\s*(Eastern|Pacific|Central|Mountain|[ECMP][SD]?T)\b", t, re.I)
    if m:
        h = int(m[1]) % 12 + (12 if m[3].lower() == "p" else 0)
        et = h + TZ.get(m[4].lower(), 0) + int(m[2] or 0) / 60
        return ("After close" if et >= 16 else "Same day" if et <= 9.5 else default), f"call at {m.group(0)}"
    if re.search(r"after (the )?(market|stock market)s? clos", t, re.I):
        return "After close", "text: after the market close"
    if re.search(r"before (the )?(market|stock market)s? open", t, re.I):
        return "Same day", "text: before the market open"
    return default, None


def stated_date(text, after):
    """A future full-results date stated in another release (a prelim: 'will report its audited full fourth quarter
    ... results on Tuesday, February 27, 2018'). Must fall after `after` (that release's own date)."""
    t = re.sub(r"\s+", " ", text)
    for m in re.finditer(rf"will (report|release|announce)[^.]{{0,200}}?({MONTHS}) (\d{{1,2}}), (\d{{4}})", t, re.I):
        d = dt.datetime.strptime(f"{m[2]} {m[3]} {m[4]}", "%B %d %Y").date().isoformat()
        if d > after:
            return d, m.group(0)[:220]
    return None, None


def propose(src, mod):
    first_fy = min(p["year"] for p in mod["periods"] if p["kind"] == "fy")
    since = dt.date(first_fy, 1, 1).isoformat()
    actual = [p["label"] for p in modmap.quarters(mod["periods"], actual_only=True)]
    out = {"since": since, "full": {}, "events": [], "skipped": [], "review": [], "notes": []}
    pr_dir = os.path.join(src, "Press Releases")
    files, d = md_files(pr_dir) if os.path.isdir(pr_dir) else ([], None)
    fulls = {}
    texts = {}
    for f in files:
        m = REL_RE.match(f)
        if not m:
            out["skipped"].append({"file": f, "why": "name not '<FY> Q<n> <T> release <date>'"})
            continue
        if not MAIN_EXHIBIT.match(m[5]):
            out["skipped"].append({"file": f, "why": f"side exhibit ({m[5].strip()})"})
            continue
        period = f"Q{m[2]} {int(m[1]) % 100:02d}"
        text = open(os.path.join(d, f), encoding="utf-8", errors="ignore").read()
        texts[f] = (period, text, m[4])
        date = m[4]
        if is_full(text):
            fulls.setdefault(period, []).append((date, f))
            tm, why = timing(text, "After close")
            if date >= since:
                out["events"].append({"date": date, "type": "Earnings", "name": f"{period} earnings", "timing": tm,
                                      "source": f, "timing_evidence": why})
            if not why:
                out["review"].append(f"{f}: no call time found; timing assumed 'After close'")
        else:
            head = headline(text)
            prelim = re.search(r"prelim|unaudited", head, re.I) or re.search(r"preliminary[^.]{0,80}revenue", text[:4000], re.I)
            # a call time in these is the coming full-results call, not this release: default to same-day reaction
            tm, why = "Same day", None
            if prelim:
                guide = " + guide" if re.search(r"guidance|outlook|expects? (full|fiscal|20\d\d)", text[:8000], re.I) else ""
                ev = {"type": "Prelim revenue", "name": f"{period} prelim revenue{guide}"}
            else:
                ev = {"type": "Other release", "name": head[:60] or f"{period} release"}
                out["review"].append(f"{f}: not an earnings or preliminary-revenue release ('{head[:80]}'). Keep it as an "
                                     "event, or delete it.")
            if date >= since:
                out["events"].append({"date": date, **ev, "timing": tm, "source": f, "timing_evidence": why})
    for period, lst in fulls.items():
        lst.sort()
        out["full"][period] = {"date": lst[0][0], "source": f"Source: {lst[0][1]}"}
        if len(lst) > 1:
            out["review"].append(f"{period}: {len(lst)} full-results releases ({', '.join(x[1] for x in lst)}); using "
                                 f"the first, {lst[0][0]}")
    for period in actual:
        if period in out["full"]:
            continue
        hint = None
        for f, (p, text, fdate) in texts.items():
            if p == period:
                date, quote = stated_date(text, fdate)
                if date:
                    hint = {"date": date, "source": f"Source: date stated in '{f}' (full-results release not in folder)",
                            "quote": quote}
                    break
        if hint:
            out["full"][period] = {k: hint[k] for k in ("date", "source")}
            out["events"].append({"date": hint["date"], "type": "Earnings", "name": f"{period} earnings",
                                  "timing": "After close", "source": hint["source"].replace("Source: ", ""),
                                  "timing_evidence": None})
            out["review"].append(f"{period}: full-results release not in the folder; date {hint['date']} taken from "
                                 f"the text \"{hint['quote']}\". Confirm it.")
        else:
            out["review"].append(f"{period}: MISSING full-results release date. Find it (10-Q filing date, a later "
                                 "release, the call transcript) and add it to `full` and `events`.")
    ev_dir = os.path.join(src, "Investor Events")
    files, d = md_files(ev_dir) if os.path.isdir(ev_dir) else ([], None)
    for f in files:
        m = EVT_RE.match(f)
        if not m:
            out["skipped"].append({"file": f, "why": "name not '<date> <T> <event>'"})
            continue
        if m[1] >= since:
            out["events"].append({"date": m[1], "type": "Investor event", "name": m[3], "timing": "Same day",
                                  "source": f, "timing_evidence": None})
    if any(e["type"] in ("Prelim revenue", "Other release") for e in out["events"]):
        out["review"].append("Preliminary-revenue and other releases are set to 'Same day' (pre-market, e.g. at the JPM "
                             "conference, is typical). Change any that came out after the close.")
    out["events"].sort(key=lambda e: (e["date"], e["type"] != "Earnings"))
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    res = propose(a.src, modmap.read(a.model))
    json.dump(res, open(a.out, "w"), indent=1)
    print(json.dumps({"quarters_with_full_date": len(res["full"]), "events": len(res["events"]),
                      "by_type": {t: sum(e["type"] == t for e in res["events"]) for t in
                                  ("Earnings", "Prelim revenue", "Other release", "Investor event")},
                      "skipped": len(res["skipped"]), "review": res["review"]}, indent=1))
