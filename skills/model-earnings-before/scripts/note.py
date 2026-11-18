# skills/model-earnings-before/scripts/note.py
"""The earnings preview note: Markdown, then a PDF through research-filings' render.py (cover, contents page,
footer). Sections follow the spec: net, set-up, last quarter, since the last print, expectations, model checks,
variance, risk / reward, what this print will tell us, judgment calls and flags.

Numbers come from W/layout.json 'expected' / 'calc' (verify.py proved they equal the recalculated tab) and 'used'
(the user's own values where they changed one); words from earnings_plan.json and context.json.

usage: python3 note.py --work W --ticker T --out-dir "<research_dir>/<T>/Earnings Previews" [--date YYYY-MM-DD]"""
import argparse
import datetime as dt
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))   # run with python3 -I
import earnmath as em  # noqa: E402
from build import LABEL  # noqa: E402

RENDER = os.path.abspath(os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "..", "research-filings",
                                      "scripts", "render.py"))


def pct(v):
    return "n/a" if not em._n(v) else f"{v:.1%}"


def money(v):
    return "n/a" if not em._n(v) else f"${v:,.2f}"


def mult(v):
    return "n/a" if not em._n(v) else f"{v:.1f}x"


def cell(t):
    return str(t).replace("|", "\\|").replace("\n", " ")


def _points(lst):
    return [f"- {x['text']} \"{x['quote']}\" [{x['anchor']}]" for x in lst] or ["- Nothing on file."]


def write_md(work, ticker, out_dir, date):
    lay = json.load(open(os.path.join(work, "layout.json")))
    plan = json.load(open(os.path.join(work, "earnings_plan.json")))
    ctx = json.load(open(os.path.join(work, "context.json")))
    c, U, users = lay["calc"], lay["used"], set(lay["users"])
    mine = lambda lab: " **You changed this.**" if lab in users else ""   # noqa: E731
    rd = ctx["report_date"]
    rd_text = f"{U.get(LABEL['report_date'], rd['value'])} (estimated)" if rd["estimated"] else rd["value"]
    L = [f'<div class="cover"><h1>{ticker} earnings preview: {ctx["quarter"]}</h1><p>{date} · Chapter 13 · report '
         f'date {rd_text} · price {money(ctx["price"]["value"])} ({ctx["price"]["source"]})</p></div>', "",
         "## 1. Net", "",
         f"**{U[LABEL['stance']]}** (the rule says **{c['rule'] or '?'}**).{mine(LABEL['stance'])} "
         f"The quarter: {U[LABEL['call_q']]} · the guide: {U[LABEL['call_g']]} · expected move "
         f"±{pct(U[LABEL['expected_move']])}.", "", plan["net"], "",
         f"Reward / risk {mult(c['rr'])} · implied PSUC {pct(c['psuc'])} · our P(upside) "
         f"{pct(c['inputs']['p_beat'] if 'inputs' in c else U[LABEL['p_beat']])} · edge {pct(c['edge'])}.", "",
         "## 2. Set-up", "",
         f"Stock minus SPY since the last print ({ctx['last_print']}): {pct(ctx['rates']['rel']['value'])} · P/E "
         f"percentile (5 years): {pct((ctx['links']['multiples'].get('pe_pct') or {}).get('value'))} · options-"
         f"implied move: {pct(ctx['yahoo']['implied_move'])} · average print move: "
         f"{pct(ctx['rates']['stats']['avg_abs'])} over {ctx['rates']['stats']['n']} prints.", "",
         "| Row | Side | Why |", "|---|---|---|"]
    for rid, lab, _, _, code in em.SETUP:
        x = (plan.get("setup") or {}).get(rid) or {}
        why = x.get("reason") or "Code: P/E percentile and the move against SPY since the last print."
        L.append(f"| {cell(lab)} | {c['sides'][rid]} | {cell(why)} |")
    L += ["", f"Set-up net: {c['net']} · blow-up flags: {c['nblow']} "
          f"({', '.join(k for k, v in c['blowups'].items() if v) or 'none'})", "",
          "## 3. Last quarter", ""] + _points(plan["points"]["last_quarter"])
    L += ["", "## 4. Since the last print", ""] + _points(plan["points"]["since_last_print"])
    L += ["", "Documents read: " + ("; ".join(f"{d['date']} {d['label']}" for d in ctx["new_docs"]) or "none"), "",
          "## 5. Expectations", "",
          f"Key metric: **{U[LABEL['key_metric']]}**. {plan['key_metric']['reason']}{mine(LABEL['key_metric'])}", "",
          f"Whisper (our estimate, not a published number): {plan['whisper']['text']} {plan['whisper']['reason']}", ""]
    cons = ctx["links"].get("consensus") or {}
    L.append(f"Consensus (snapshot {cons.get('snapshot')}): EPS {money((cons.get('eps_q') or {}).get('value'))} for "
             f"the quarter, {money((cons.get('eps_fy') or {}).get('value'))} this year, "
             f"{money((cons.get('eps_fy1') or {}).get('value'))} next year.")
    for bl in ctx["guidance"]:
        L.append(f"Guidance trail ({bl['title']}): habitual raiser **{bl['habitual']}**; actual vs the first guide's "
                 "midpoint: " + ", ".join(f"{r['year']} {pct(r['vs_mid']['value'])}" for r in bl["rows"]) + ".")
    for s_ in ctx["yahoo"]["surprises"]:
        L.append(f"- Quarter ending {s_['quarter']}: EPS {s_['actual']} vs {s_['estimate']} ({pct(s_['surprise'])}).")
    L += ["", "## 6. Model checks", ""]
    fired = [m for m in ctx["checks"]["metrics"] if m["cells"]["hockey"] == "yes"]
    for m in fired:
        k = m["cells"]
        L.append(f"- **Hockey stick: {m['name']}.** Growth jumps to {pct(k['yoy']['value'])} from "
                 f"{pct(k['yoy_prev']['value'])} the quarter before, the 2-year stack rises to {pct(k['st2']['value'])} "
                 f"from {pct(k['st2_prev']['value'])}, and sequential growth of {pct(k['qoq']['value'])} beats the "
                 f"5-year average of {pct(k['qoq_avg']['value'])}. Be wary unless there is something concrete behind it.")
    for m in ctx["checks"]["metrics"]:
        k = m["cells"]
        if "margin" in k and em._n(k["margin"]["value"]) and em._n(k["margin_avg"]["value"]) \
                and abs(k["margin"]["value"] - k["margin_avg"]["value"]) >= 0.01:
            L.append(f"- {m['name']} margin {pct(k['margin']['value'])} against a 5-year average of "
                     f"{pct(k['margin_avg']['value'])} for this quarter: ask whether there is a reason.")
    h2 = ctx["checks"]["h2"]
    if em._n(h2["share"]["value"]) and em._n(h2["avg"]["value"]) and abs(h2["share"]["value"] - h2["avg"]["value"]) >= 0.01:
        L.append(f"- Second half carries {pct(h2['share']['value'])} of {ctx['fy']} revenue against a 5-year "
                 f"average of {pct(h2['avg']['value'])}.")
    if L[-1] == "":
        L.append("- No flag fired.")
    var = lay["variance"]
    L += ["", "## 7. Variance", "",
          (f"On the Consensus tab, rows {var['rows'][0]}-{var['rows'][-1]} (consensus typed from the mean row; ours "
           "linked to MOD)." if var["where"] == "consensus" else "On the Earnings tab, band 6."), "",
          "## 8. Risk / reward", "", "| | P/E | EPS | Price | Move |", "|---|---|---|---|---|",
          f"| Today | | | {money(ctx['price']['value'])} | |",
          f"| Upside case | {mult(U[LABEL['up_pe']])} | {money(U[LABEL['up_eps']])} | {money(c['up_price'])} | {pct(c['up'])} |",
          f"| Downside case | {mult(U[LABEL['down_pe']])} | {money(U[LABEL['down_eps']])} | {money(c['down_price'])} | {pct(c['down'])} |",
          "", f"Reward / risk {mult(c['rr'])}; implied PSUC {pct(c['psuc'])}; edge {pct(c['edge'])}; the rule says "
          f"**{c['rule'] or '?'}**.", "", "| Risk score (1 low, 5 high) | Score | Why |", "|---|---|---|"]
    for rid, lab in em.RISKS:
        L.append(f"| {cell(lab)} | {U[lab]} | {cell(plan['risks'][rid]['reason'])} |")
    L += ["", "## 9. What this print will tell us", ""] + _points(plan["points"]["checkpoint"])
    L += ["", "## 10. Judgment calls and flags", ""]
    L += [f"- {x}" for x in plan["judgment_calls"]]
    for k in em.AGENT_INPUTS:
        x = plan["inputs"][k]
        L.append(f"- {LABEL[k]}: {U[LABEL[k]]} (anchor {x['anchor']}). {x['reason']}{mine(LABEL[k])}")
    if rd["estimated"]:
        L.append(f"- Report date estimated: {rd['source']}. Type the announced date on the tab when it is out.")
    for wn in ctx["warnings"] + lay["warnings"]:
        L.append(f"- {wn}")
    for t in ctx["missing"]:
        L.append(f"- Missing tab: {t}; its blocks show ? or n/a.")
    up = os.path.join(work, "unverified.json")
    for n in (json.load(open(up)) if os.path.exists(up) else []):
        L.append(f"- UNVERIFIED: {n} (its anchor did not hold after two rounds).")
    if lay["frozen"]["kept"]:
        L.append(f"- The forecast frozen on {lay['frozen']['date']} was kept (same quarter).")
    os.makedirs(out_dir, exist_ok=True)
    p = os.path.join(out_dir, f"{ticker} {ctx['quarter'].rstrip('E')} earnings preview {date}.md")
    open(p, "w").write("\n".join(L) + "\n")
    return p


def render(md, pdf, footer):
    """(pdf path, None) or (None, the reason the PDF was not made)."""
    if not os.path.exists(RENDER):
        return None, f"research-filings' render.py is not at {RENDER}"
    r = subprocess.run([sys.executable, RENDER, md, pdf, "--footer", footer], capture_output=True, text=True)
    if r.returncode or not os.path.exists(pdf):
        tail = (r.stderr or r.stdout).strip().splitlines()
        why = next((x for x in reversed(tail) if "WeasyPrint" in x or "Error" in x), tail[-1] if tail else "")
        return None, f"render.py failed ({why.strip()}); install WeasyPrint (pip install weasyprint; brew install pango)"
    return pdf, None


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--work", required=True)
    ap.add_argument("--ticker", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--date", default=dt.date.today().isoformat())
    a = ap.parse_args()
    md = write_md(a.work, a.ticker.upper(), a.out_dir, a.date)
    pdf, why = render(md, md[:-3] + ".pdf", f"{a.ticker.upper()} earnings preview · {a.date}")
    print(json.dumps({"md": md, "pdf": pdf, "pdf_skipped": why}, indent=1))


if __name__ == "__main__":
    main()
