# skills/model-earnings-after/scripts/note.py
"""The after-print note: Markdown with a cover and a table of contents, then a PDF through research-filings'
render.py (its own contents page with page numbers replaces the Markdown one; cover, footer). Sections: 1 Headline,
2 Reaction, 3 Call summary, 4 The wrap (the chapter's seven items), 5 React, 6 Placeholders and gaps, 7 Judgment
calls.

Every number comes from the recalculated copy (verify.run's `recalculated` file, passed as --values), found through
W/layout.json's refs (column-A labels) and printed in the cell's own number format (fmt). The words come from
after_plan.json (headline, thoughts, quotes with file:line, judgment calls) and the tab's own reason column. Figures
inside quoted call lines are the company's words; no other number is retyped from context or the plan.

If the PDF cannot be made (WeasyPrint missing, say), the Markdown still stands and the printed JSON has "pdf": null and
"pdf_skipped" with the reason; exit 0, and the SKILL tells the user.

usage: python3 note.py --work W --ticker T --out-dir "<research_dir>/<T>/Earnings Reviews" --values RECALCULATED.xlsx
       [--date YYYY-MM-DD]"""
import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))   # run with python3 -I
import openpyxl  # noqa: E402

import callnotes  # noqa: E402
from build import CHECKPOINT, PLACEHOLDER, PLAYED, REACT, SFOT, T7_ASK, TAB, guidance_labels  # noqa: E402
from context import IN_LINE_LABEL  # noqa: E402

RENDER = os.path.abspath(os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "..", "research-filings",
                                      "scripts", "render.py"))
SECTIONS = ("Headline", "Reaction", "Call summary", "The wrap", "React", "Placeholders and gaps", "Judgment calls")
WRAP = ("Thoughts on the quarter", "Estimates and the multiple", "Catalyst path", "Controversies", "Updated guidance",
        "Updated IRR", "Updated risk/reward")
TOC_START, TOC_END = "<!-- contents -->", "<!-- /contents -->"


def fmt(cell):
    """Copied from model-valuation note.py, Nov 2026; keep in sync.
    A cell's value as Excel would show it (its own number format), in plain text."""
    v, f = cell.value, cell.number_format or "General"
    if v is None:
        return "n/a"
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return str(v)
    if "%" in f:
        s = f"{v * 100:.0f}%" if "0%" in f and ".0%" not in f else f"{v * 100:.1f}%"
        return ("+" + s if v > 0 else s) if f.startswith("\\+") else s
    if "x" in f:
        return f"{v:.1f}x"
    if "$" in f:
        return f"-${-v:,.2f}" if v < 0 else f"${v:,.2f}"
    if f in ("#,##0.0",):
        return f"{v:,.1f}"
    if f == "0":
        return f"{v:.0f}"
    if f == "0.00":
        return f"{v:.2f}"
    return f"{v:,.2f}" if isinstance(v, float) else str(v)


def show(cell):
    """fmt, with an error cell as n/a and a date as yyyy-mm-dd."""
    v = cell.value
    if isinstance(v, str) and v.startswith("#"):
        return "n/a"
    if isinstance(v, (dt.date, dt.datetime)):
        return (v.date() if isinstance(v, dt.datetime) else v).isoformat()
    return fmt(cell)


def cell_text(v):
    return str(v).replace("|", "\\|").replace("\n", " ")


class Tab:
    """The recalculated Earnings tab, read by bands 9-15's column-A labels (layout.json refs)."""

    def __init__(self, values, lay):
        self.wb = openpyxl.load_workbook(values, data_only=True)
        if TAB not in self.wb.sheetnames:
            raise SystemExit(f"model-earnings-after: {values} has no {TAB} tab; pass verify's recalculated file.")
        self.ws, self.refs = self.wb[TAB], lay["refs"]

    def has(self, label):
        return label in self.refs

    def ref(self, label, col=None):
        c, r = re.fullmatch(r"\$?([A-Z]+)\$?(\d+)", self.refs[label]).groups()
        return f"{col or c}{r}"

    def cell(self, label, col=None):
        return self.ws[self.ref(label, col)]

    def v(self, label, col=None):
        """The cell as the tab shows it; '?' when the label is not on the tab."""
        return show(self.cell(label, col)) if self.has(label) else "?"

    def raw(self, label, col=None):
        return self.cell(label, col).value if self.has(label) else None

    def labels(self, prefix):
        return [k for k in self.refs if k.startswith(prefix)]

    def between(self, first, last):
        """Labels whose rows lie strictly between two labels' rows, in row order."""
        a, b = int(self.ref(first)[1:]), int(self.ref(last)[1:])
        return sorted((k for k in self.refs if a < int(re.sub(r"\D", "", self.refs[k])) < b),
                      key=lambda k: int(re.sub(r"\D", "", self.refs[k])))

    def call_notes(self):
        """{quarter: {topic: text}} from the copy's Call Notes tab, and its quarters in column order."""
        if callnotes.TAB not in self.wb.sheetnames:
            return {}, []
        ws = self.wb[callnotes.TAB]
        rows = list(ws.iter_rows(values_only=True))
        h = next((i for i, r in enumerate(rows) if r and r[0] == callnotes.HEADER), None)
        if h is None:
            return {}, []
        qs = [(j, str(q).strip()) for j, q in enumerate(rows[h]) if j and q is not None]
        blank = next((i for i in range(h + 1, len(rows)) if not rows[i] or rows[i][0] in (None, "")), len(rows))
        out = {q: {} for _, q in qs}
        for r in rows[blank + 1:]:
            if r and r[0]:
                for j, q in qs:
                    if j < len(r) and r[j] not in (None, ""):
                        out[q][str(r[0]).strip()] = str(r[j])
        return out, [q for _, q in qs]


def _quote(p):
    return f"- \"{p['quote']}\" [{p['anchor']}]" if p.get("quote") else f"- [{p['anchor']}]"


def write_md(work, ticker, out_dir, date, values):
    lay = json.load(open(os.path.join(work, "layout.json")))
    plan = json.load(open(os.path.join(work, "after_plan.json")))
    ctx = json.load(open(os.path.join(work, "context.json")))
    t = Tab(values, lay)
    q, users = ctx["quarter"], set(lay["users"])
    mine = lambda lab: " **You changed this.**" if lab in users else ""   # noqa: E731
    reason = lambda lab: t.raw(lab, "D") or ""                            # noqa: E731
    eref = ctx.get("earnings_refs") or {}
    prev = lambda k: show(t.ws[eref[k].replace("$", "")]) if k in eref else "?"   # noqa: E731
    head9 = "Line (band 7's frozen forecast against MOD's actual)"
    lines9 = t.between(head9, "SFOT: surprise") if t.has(head9) and t.has("SFOT: surprise") else []
    results = [f"{lab.split(' | ')[-1]} {t.v(lab, 'F')} ({t.v(lab, 'E')})" for lab in lines9
               if t.raw(lab, "F") in ("beat", "in line", "miss")]
    gl = [lab for lab in guidance_labels(plan) if t.has(lab)]
    call = REACT[0][1]

    L = [f'<div class="cover"><h1>{ticker} after the print: {q}</h1><p>{date} · Chapter 13 · reaction day '
         f'{t.v("Reaction day")} · day move {t.v("Day move (Px Events)")} · the call: {t.v(call)} · checkpoint '
         f'{t.v(CHECKPOINT)}</p></div>', "", TOC_START, "**Contents**", ""]
    L += [f"{i}. [{s}](#{i}-{s.lower().replace(' ', '-')})" for i, s in enumerate(SECTIONS, start=1)]
    L += [TOC_END, ""]

    # 1 Headline
    L += ["## 1 Headline", "", plan["headline"], "",
          f"- The move: {t.v('Day move (Px Events)')} on {t.v('Reaction day')}, {t.v('Move in daily sigmas')} daily "
          f"sigmas (idio {t.v('Idio move (Px Events)')}).",
          "- Against the frozen forecast: " + ("; ".join(results) or "no line has a result yet") + ".",
          "- Guidance: " + ("; ".join(f"{lab.split(': ', 1)[1]} {t.v(lab)}" for lab in gl) or "none in the plan")
          + ".",
          f"- React: **{t.v(call)}**; thesis checkpoint **{t.v(CHECKPOINT)}**.", ""]

    # 2 Reaction
    L += ["## 2 Reaction", "", f"Actual against the forecast frozen {ctx['frozen']['date']} (Earnings tab band 9; "
          f"in line = within {t.v(IN_LINE_LABEL)}).", "",
          "| Line | Frozen | Actual | Difference | % | Result |", "|---|---|---|---|---|---|"]
    for lab in lines9:
        cells = [t.v(lab, c) if t.raw(lab, c) is not None else "" for c in "BCDEF"]
        L.append(f"| {cell_text(lab)} | " + " | ".join(cell_text(c) for c in cells) + " |")
    if lay["placeholders"]:
        L += ["", f"Marked \"{PLACEHOLDER}\": " + ", ".join(lay["placeholders"]) + " (model-update's placeholder; "
              "no result until the 10-Q)."]
    L += ["", f"The preview called the quarter **{prev('call_q')}** and the guide **{prev('call_g')}**.", "",
          "**SFOT** (surprise, fundamentals, outlook, tone):", "", "| | Answer | Why |", "|---|---|---|"]
    for k in SFOT:
        lab = f"SFOT: {k}"
        L.append(f"| {k} | {t.v(lab)}{mine(lab)} | {cell_text(reason(lab))} |")
    L += ["", "**The move against what we expected:**", "", "| | |", "|---|---|"]
    for lab in ("Day move (Px Events)", "Idio move (Px Events)", "Gap at the open (Yahoo)", "Open to close (Yahoo)",
                *t.labels("Daily sigma"), "Move in daily sigmas", "Expected move (preview, band 1)",
                "Day move minus expected (|day move| - expected)", "Options-implied move (preview, band 5)",
                "Preview's upside move (band 2)", "Preview's downside move (band 2)", "Run-up, T-8 to T-1 (Px Data)",
                "Drift, reaction-day close to T+7 (Px Data)"):
        if t.has(lab):
            L.append(f"| {cell_text(lab)} | {t.v(lab)} |")

    # 3 Call summary
    notes, order = t.call_notes()
    pq = next((x for x in order[order.index(q) + 1:]), None) if q in order else None
    L += ["", "## 3 Call summary", "", f"From the {q} call ({ctx['docs']['transcript']}), near-verbatim by topic; "
          "each quote carries its file and line.", ""]
    pts = plan.get("call_notes") or {}
    for topic in ctx["topics"] + [k for k in pts if k not in ctx["topics"]]:
        L += [f"### {topic}", ""]
        L += [_quote(p) for p in pts.get(topic) or []] or ["- Nothing on this call."]
        if topic in lay.get("call_notes_users", []):
            L.append(f"- You edited this cell on the Call Notes tab; it reads: {notes.get(q, {}).get(topic, '')}")
        if pq is None:
            L += ["", "First quarter in Call Notes."]
        else:
            was = notes.get(pq, {}).get(topic)
            now = notes.get(q, {}).get(topic)
            L += ["", f"Changed since last quarter: " + (
                f"nothing; {pq} read the same." if was == now else
                f"{pq} read: {was}" if was not in (None, callnotes.DASH) else f"new this quarter (nothing in {pq}).")]
        L.append("")

    # 4 The wrap
    L += ["## 4 The wrap", "", "Chapter 13.7's seven items.", "",
          f"### 4.1 {WRAP[0]}", "", plan["quarter_thoughts"], "",
          "SFOT: " + ", ".join(f"{k} {t.v('SFOT: ' + k)}" for k in SFOT) + ".", "",
          f"### 4.2 {WRAP[1]}", ""]
    est = t.labels("Estimate: ")
    if est and t.has("Estimate"):
        hdr = [t.v("Estimate", c) for c in "BCDEFG"]
        L += ["| Estimate | " + " | ".join(h if h != "n/a" else "" for h in hdr) + " |", "|---|" + "---|" * 6]
        for lab in est:
            L.append(f"| {cell_text(lab.split(': ', 1)[1])} | "
                     + " | ".join(t.v(lab, c) if t.raw(lab, c) is not None else "" for c in "BCDEFG") + " |")
    else:
        L.append("No estimate lines on MOD.")
    val = [lab for lab in ctx["valuation"]["labels"] if t.has(lab)]
    mults = [lab for lab in val if not lab.startswith(("Blended", "IRR"))]
    L += ["", "The multiple: each chosen multiple's prices before (pre-print Valuation Note) and after (Valuation "
          "tab).", ""] + _vtable(t, mults)
    L += ["", f"### 4.3 {WRAP[2]}", ""]
    L += [f"- {lab.split(': ', 1)[1]}: {t.v(lab)}" for lab in t.labels("Catalyst: ")] or ["- None named."]
    L += ["", f"### 4.4 {WRAP[3]}", ""]
    L += [f"- {t.v(lab)}" for lab in t.labels("Controversy ")] or ["- None named."]
    L += ["", f"### 4.5 {WRAP[4]}", ""]
    if gl:
        L += ["| Item | Before | Now | Change |", "|---|---|---|---|"]
        L += [f"| {cell_text(lab.split(': ', 1)[1])} | {cell_text(t.v(lab, 'B'))} | {cell_text(t.v(lab, 'C'))} | "
              f"{t.v(lab)}{mine(lab)} |" for lab in gl]
        L += [""] + [f"- {lab.split(': ', 1)[1]}: {reason(lab)}" for lab in gl]
    else:
        L.append("No guidance items.")
    lt = t.labels("Long-term target: ")
    if lt:
        L += ["", "Long-term target pace (13.7):", "", "| | |", "|---|---|"]
        L += [f"| {cell_text(lab.split(': ', 1)[1])} | {t.v(lab)} |" for lab in lt]
    L += ["", f"Thesis checkpoint: **{t.v(CHECKPOINT)}**{mine(CHECKPOINT)}. {reason(CHECKPOINT)}", "",
          f"### 4.6 {WRAP[5]}", ""] + _vtable(t, [lab for lab in val if lab.startswith("IRR")])
    L.append("")
    for lab in t.labels("IRR at the latest close") + t.labels("Latest close"):
        L.append(f"- {lab}: {t.v(lab)}")
    fades = t.labels("Fade: ")
    if fades:
        L += ["", "If the stock gives back the move (13.7):", "", "| Price change | Price | 3-year IRR |",
              "|---|---|---|"]
        L += [f"| {t.v(lab, 'B')} | {t.v(lab, 'C')} | {t.v(lab, 'D')} |" for lab in fades]
    L += ["", f"### 4.7 {WRAP[6]}", ""] + _vtable(t, [lab for lab in val if lab.startswith("Blended")]) + [""]
    for lab in t.labels("Target change minus"):
        L.append(f"- {lab}: {t.v(lab)}")

    # 5 React
    L += ["", "## 5 React", ""]
    for k, lab in REACT:
        what = lab.split(": ", 1)[1]
        L.append(f"- {what[0].upper() + what[1:]}: **{t.v(lab)}**{mine(lab)}"
                 + (f". {reason(lab)}" if k == "call" else ""))   # call and pattern share one reason
    drift = "Drift, reaction-day close to T+7 (Px Data)"
    if t.has(PLAYED) and t.raw(PLAYED) != T7_ASK:
        L.append(f"- Played out by T+7: **{t.v(PLAYED)}**{mine(PLAYED)} (drift {t.v(drift)}). {reason(PLAYED)}")
    else:
        L.append(f"- Played out by T+7: {T7_ASK} (drift: {t.v(drift)}).")

    # 6 Placeholders and gaps
    L += ["", "## 6 Placeholders and gaps", ""]
    L += [f"- {lab}: \"{PLACEHOLDER}\" (model-update's placeholder; no result until the 10-Q)."
          for lab in lay["placeholders"]]
    for row in t.ws.iter_rows(min_row=lay["start"]):
        for c in row:
            if c.value == "?" and c.column > 1:
                a = t.ws.cell(c.row, 1).value
                d = t.ws.cell(c.row, 4).value
                why = d if c.column != 4 and d not in (None, "?") else "no source value (see the warnings below)"
                L.append(f"- {a} ({c.coordinate}) shows ?: {why}")
    for wn in lay["warnings"]:
        L.append(f"- {wn}")
    if lay["unchecked"]:
        L.append("- Not checked against code's math: " + "; ".join(lay["unchecked"]) + ".")
    if L[-1] == "":
        L.append("- None.")

    # 7 Judgment calls
    L += ["", "## 7 Judgment calls", "", "The agent's calls, then every yellow cell (yours to change on the "
          f"{TAB} tab).", ""]
    L += [f"- {x}" for x in plan["judgment_calls"]]
    L += ["", "| Yellow cell | Value | Reason | Cell |", "|---|---|---|---|"]
    for lab, ref in lay["inputs"].items():
        if t.has(lab):
            L.append(f"| {cell_text(lab)} | {cell_text(t.v(lab))}{mine(lab)} | {cell_text(reason(lab))} | "
                     f"{TAB}!{ref} |")
    if users:
        L += ["", "Your changes kept: " + ", ".join(sorted(users)) + "."]
    if lay.get("call_notes_users"):
        L += ["", "Your Call Notes edits kept: " + ", ".join(lay["call_notes_users"]) + "."]
    up = os.path.join(work, "unverified.json")
    bad = json.load(open(up)) if os.path.exists(up) else []
    L += [""] if bad else []
    for n in bad:
        L.append(f"- UNVERIFIED: {n} (its anchor did not hold after two rounds; marked red on the tab).")
    os.makedirs(out_dir, exist_ok=True)
    p = os.path.join(out_dir, f"{ticker} {q} after-print note {date}.md")
    open(p, "w").write("\n".join(L) + "\n")
    return p


def _vtable(t, labels):
    if not labels:
        return ["Not on the tab (no Valuation tab or no pre-print Valuation Note)."]
    return ["| Line | Before | After | Change |", "|---|---|---|---|"] + \
        [f"| {cell_text(lab)} | {t.v(lab, 'B')} | {t.v(lab, 'C')} | {t.v(lab, 'D')} |" for lab in labels]


def render(md, pdf, footer):
    """(pdf path, None) or (None, the reason the PDF was not made). The Markdown contents list is left out of the PDF:
    render.py puts its own contents page, with page numbers, after the cover."""
    if not os.path.exists(RENDER):
        return None, f"research-filings' render.py is not at {RENDER}"
    text = open(md).read()
    src = pdf[:-4] + ".render.md"
    open(src, "w").write(re.sub(re.escape(TOC_START) + r".*?" + re.escape(TOC_END) + r"\n?", "", text, flags=re.S))
    try:
        r = subprocess.run([sys.executable, RENDER, src, pdf, "--footer", footer], capture_output=True, text=True)
    finally:
        os.remove(src)
    if r.returncode or not os.path.exists(pdf):
        tail = (r.stderr or r.stdout).strip().splitlines()
        why = next((x for x in reversed(tail) if "WeasyPrint" in x or "Error" in x), tail[-1] if tail else "")
        return None, f"render.py failed ({why.strip()}); install WeasyPrint (pip install weasyprint; brew install pango)"
    return pdf, None


def main():
    ap = argparse.ArgumentParser(description="The after-print note: Markdown, then a PDF.")
    ap.add_argument("--work", required=True)
    ap.add_argument("--ticker", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--values", required=True, help="verify.py's recalculated copy")
    ap.add_argument("--date", default=dt.date.today().isoformat())
    a = ap.parse_args()
    md = write_md(a.work, a.ticker.upper(), a.out_dir, a.date, a.values)
    pdf, why = render(md, md[:-3] + ".pdf", f"{a.ticker.upper()} after-print note · {a.date}")
    print(json.dumps({"md": md, "pdf": pdf, "pdf_skipped": why}, indent=1))


if __name__ == "__main__":
    main()
