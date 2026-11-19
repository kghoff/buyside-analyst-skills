# skills/write-pitch/scripts/build_md.py
"""Markdown copy of the whole pitch. It leads with the call (model-update's forecast roll reads the newest Pitch/*.md
first), then title, as-of, contents, the 20-second pitch, every slide, the pitch sheet, the PM verdict, judgment calls.
usage: python3 build_md.py --plan pitch_plan.json --pm-review pm_review.md --out XYZ_pitch.md"""
import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))   # run with python3 -I
from common import load  # noqa: E402
from fill import fill  # noqa: E402
from fill import label  # noqa: E402


def _anchor(s):
    return re.sub(r"[^a-z0-9 -]", "", s.lower()).replace(" ", "-")


def _verdict(path):
    try:
        for line in open(path, encoding="utf-8"):
            if re.match(r"\s*#+\s*verdict\b", line, re.I):
                return line.lstrip("# \t").strip()
    except (OSError, UnicodeDecodeError):
        pass
    return None


def _cell(t):
    return str(t).replace("|", "\\|").replace("\n", " ")


def _table(t, f):
    rows = [t["header"]] + t["rows"]
    out = ["| " + " | ".join(_cell(f(c)) for c in rows[0]) + " |", "|" + " --- |" * len(rows[0])]
    out += ["| " + " | ".join(_cell(f(c)) for c in r) + " |" for r in rows[1:]]
    return out


SUPPORTS = {"thesis": "thesis point", "risks": "risk"}


def _image(im):
    if "png" in im:
        return f"Image: {im['png']}"
    crop = f", crop {im['crop']}" if im.get("crop") else ""
    return f"Image: {im.get('pdf', '')} page {im.get('page', '')}{crop}"


def _slide(s, i, plan, f):
    L = [f"### {i}. {f(s['title'])}", ""]
    if s.get("supports"):
        kind, _, num = str(s["supports"]).partition(".")
        L += [f"Supports: {SUPPORTS.get(kind, kind)} {num}", ""]
    L += [f"**{f(s['takeaway'])}**", ""]
    bl = lambda items: [f"- {f(x)}" for x in items] + [""]  # noqa: E731
    if s.get("bucket"):
        L += [f"Alpha bucket: {f(s['bucket'])}", ""]
    if s.get("image"):
        L += [_image(s["image"]), ""]
    if s.get("caption"):
        L += [f"Caption: {f(s['caption'])}", ""]
    if s.get("bullets"):
        L += bl(s["bullets"])
    if s.get("events"):
        L += ["Events marked on the chart:"] + [f"- {e['date']}: {f(e['label'])}" for e in s["events"]] + [""]
    for k, p in enumerate(s.get("points", []), 1):
        L += [f"{k}. **{f(p['head'])}**: {f(p['body'])}"]
    if s.get("points"):
        L += [""]
    for r in s.get("risks", []):
        L += [f"- **{f(r['head'])}** (probability {r['prob']:.0%}, our estimate). If it hits: {f(r['if_hits'])} "
              f"Mitigant: {f(r['mitigant'])}"]
    if s.get("risks"):
        L += [""]
    if s.get("tripwires"):
        L += ["Tripwires:"] + bl(s["tripwires"])
    if s.get("table"):
        L += _table(s["table"], f) + [""]
    for side in ("left", "right"):
        if s.get(side):
            L += [f"**{f(s[side]['head'])}**"] + bl(s[side]["bullets"])
    qs = {q["id"]: q for q in plan.get("quotes", [])}
    for qid in s.get("quotes", []):
        q = qs[qid]
        L += [f"> \"{q['text']}\"", f"> ({q['file']}:{q['line']})", ""]
    for it in s.get("items", []):
        L += [f"- {f(it['q'])}: **{f(it['a'])}**"]
    if s.get("items"):
        L += [""]
    if s.get("cases"):
        L += ["| Case | EPS | P/E | Return | Probability |", "| --- | --- | --- | --- | --- |"]
        for c in s["cases"]:
            L += ["| " + " | ".join(_cell(f(c[k])) for k in ("name", "eps", "pe", "ret", "prob")) + " |"]
        L += [""]
    if s.get("ladder"):
        L += [f"R/R ladder: read from the {s['ladder']} tab", ""]
    if s.get("irr"):
        L += [f"3-year IRR: {f(s['irr'])}", ""]
    if s.get("three_rs"):
        t = s["three_rs"]
        L += [f"3 R's: roll {f(t['roll'])}; revisions {f(t['revisions'])}; rerating {f(t['rerating'])}", ""]
    if s.get("lead"):
        L += [f(s["lead"]), ""]
    for k, v in (s.get("short") or {}).items():
        L += [f"- Short, {k}: {f(v)}"]
    if s.get("short"):
        L += [""]
    if s.get("notes"):
        L += ["**Speaker notes:** " + f(s["notes"]), ""]
    if s.get("source"):
        L += [f"Source: {s['source']}", ""]
    return L


def build(plan, pm_review, out):
    n = plan["numbers"]
    f = lambda t: fill(t, n)  # noqa: E731
    sheet = plan["pitch_sheet"]
    L = [f"**Call: {plan['call']}. Action: {plan['action']}.**", ""]
    if plan.get("override"):
        o = plan["override"]
        if isinstance(o, dict):
            L += [f"Override: {f(o.get('reason', ''))} Evidence: {f(o.get('evidence', ''))}", ""]
        else:
            L += [f"Override: {f(o)}", ""]
    L += [f"Most important thing: {f(plan['most_important_thing'])}", "",
          f"# {plan['ticker']} pitch", "", f"As of {plan['as_of']}", "", "## Contents", ""]
    L += [f"- [20-second pitch](#20-second-pitch)", "- [Slides](#slides)"]
    L += [f"  - [{i}. {f(s['title'])}](#{_anchor(f'{i}. ' + f(s['title']))})" for i, s in enumerate(plan["slides"], 1)]
    L += [f"- [{h}](#{_anchor(h)})" for h in ("Pitch sheet", "PM review", "Judgment calls")]
    L += ["", "## 20-second pitch", "", f(plan["pitch_20s"]), "",
                                                        "## Slides", ""]
    for i, s in enumerate(plan["slides"], 1):
        L += _slide(s, i, plan, f)
    L += ["## Pitch sheet", "", "### 3-minute script", ""]
    L += [f"{k}. {f(t)}" for k, t in enumerate(sheet["script_3min"], 1)] + ["", "### On a napkin", ""]
    L += [f"- {f(t)}" for t in sheet["napkin"]] + ["", "### The hardest questions", ""]
    for qa in sheet["hard_questions"]:
        L += [f"**{f(qa['q'])}**", "", f(qa["a"]), ""]
    L += ["### Know cold", ""] + [f"- {label(k)}: {n[k]['shown']}" for k in sheet["know_cold"]] + [""]
    L += ["## PM review", "", _verdict(pm_review) or "PM review: none", "", "## Judgment calls", ""]
    L += [f"- {f(t)}" for t in plan.get("notes") or []] + [""]
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", required=True)
    ap.add_argument("--pm-review", default="")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    print(build(load(a.plan), a.pm_review, a.out))


if __name__ == "__main__":
    main()
