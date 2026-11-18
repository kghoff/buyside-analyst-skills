# skills/model-short/scripts/note.py
"""The short-check note: Markdown, then a PDF through research-filings' render.py (cover, contents page, footer).

Numbers come from W/layout.json 'expected' (verify.py proved each equals the recalculated tab) and 'used' (the inputs,
the user's own where they changed one); words from short_plan.json and context.json. Nothing is retyped by hand.
If the PDF cannot be made the Markdown still stands; the printed JSON says why ("pdf_skipped").

usage: python3 note.py --work W --ticker T --out-dir "<research_dir>/<T>/Short Check" [--date YYYY-MM-DD]"""
import argparse
import datetime as dt
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))   # run with python3 -I
import shortmath as sm  # noqa: E402
from build import LABEL, MONEY, PCT  # noqa: E402

RENDER = os.path.abspath(os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "..", "research-filings",
                                      "scripts", "render.py"))


def fmt(v, f):
    """A value as the tab's number format shows it."""
    if v is None:
        return "n/a"
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return str(v)
    if f == PCT:
        return f"{v:.1%}"
    if "x" in f:
        return f"{v:.1f}x"
    if f.startswith("$"):
        return f"${v:,.2f}"
    if f == "#,##0":
        return f"{v:,.0f}"
    return f"{v:,.2f}"


def cell(t):
    return str(t).replace("|", "\\|").replace("\n", " ")


def write_md(work, ticker, out_dir, date):
    lay = json.load(open(os.path.join(work, "layout.json")))
    plan = json.load(open(os.path.join(work, "short_plan.json")))
    ctx = json.load(open(os.path.join(work, "context.json")))
    E, R, U, F = lay["expected"], lay["refs"], lay["used"], lay["fmt"]

    def val(key):
        if key not in R:
            return "n/a"
        ref = R[key].replace("$", "")
        return fmt(E.get(ref, U.get(LABEL.get(key, ""))), F.get(ref, ""))

    s = lay["summary"]
    n_rows = {d: sum(1 for _, dim, _, _ in sm.ROWS if dim == d) for d in sm.NEED}
    L = [f'<div class="cover"><h1>{ticker} short check</h1><p>{date} · Chapter 12 FEV screen · price '
         f'{fmt(ctx["price"]["value"], MONEY)} ({ctx["price"]["source"]})</p></div>', "",
         "## Verdict", "",
         f"**{U[LABEL['verdict']]}** (the rule says **{s['verdict']}**) · type: {U[LABEL['type']]} · bucket: "
         f"{U[LABEL['bucket']]}", "", plan["why"], "", f"> [!KEY] {plan['verdict']['reason']}", "",
         f"Reward / risk {val('rr')} · wedge {val('wedge')} · max position ${val('max_pos')}M "
         f"({val('pct_book')} of the short book) · catalyst within two prints: {U[LABEL['catalyst_soon']]}", "",
         "## FEV scorecard", "", "| Row | Tick | Reason |", "|---|---|---|"]
    for rid, dim, lab, _ in sm.ROWS:
        L.append(f"| {dim}: {cell(lab)} | {sm.TICK[s['ticks'][rid]]} | {cell(plan['ticks'][rid]['reason'])} |")
    L += ["", "Passes: " + ", ".join(f"{d} {s['counts'][d]}/{n_rows[d]} ({'pass' if s['passes'][d] else 'fail'}, "
                                     f"needs {sm.NEED[d]})" for d in ("F", "E", "V")), ""]
    for x in plan.get("smoke") or []:
        L.append(f"> [!WATCH] Smoke: {x['flag']}: \"{x['quote']}\" [{x['anchor']}]")
    if not plan.get("smoke"):
        L.append(f"Smoke: none found. {plan['smoke_checked']}")
    L += ["", "## Subpar-algorithm IRR wedge", "",
          "What the stock returns if the P/E just rolls forward, against the hurdle.", "", "| | |", "|---|---|",
          f"| NTM P/E | {val('ntm_pe')} |", f"| 3-year EPS CAGR | {val('cagr')} |", f"| Dividend yield | {val('dy')} |",
          f"| IRR if the P/E rolls forward | {val('irr')} |", f"| Hurdle | {val('hurdle')} |",
          f"| **Wedge** | **{val('wedge')}** |", "",
          "## Risk, sizing and borrow", "", "| | |", "|---|---|",
          f"| Reward price / reward | {val('reward_price')} / {val('reward')} |",
          f"| Dream case / NTM roll-forward / takeout | {val('dream_move')} / {val('roll')} / {val('takeout_premium')} |",
          f"| **Risk case** | **{val('risk')}** |", f"| Reward / risk | {val('rr')} |",
          f"| Print move | {val('print_move')} |"]
    if "earn_move" in R:
        L.append(f"| Median earnings-day idio move | {val('earn_move')} |")
    borrow = U[LABEL["borrow"]]
    L += [f"| Short % of float / days to cover | {val('short_pct_float')} / {val('days_to_cover')} ({val('crowded')}) |",
          f"| Borrow | {fmt(borrow, PCT)} |", f"| Drag at 5% / 20% borrow | {val('drag_low')} / {val('drag_high')} |",
          f"| Reward net of a year's drag | {val('reward_net')} |",
          f"| Max position | ${val('max_pos')}M ({val('pct_book')} of the short book) |", "",
          "## Judgment calls and flags", ""]
    for k, x in plan["inputs"].items():
        mine = " **You changed this.**" if LABEL[k] in lay["users"] else ""
        L.append(f"- {LABEL[k]}: {fmt(U[LABEL[k]], F.get(R[k].replace('$', ''), ''))} (anchor {x['anchor']}). "
                 f"{x['reason']}{mine}")
    for k in ("verdict", "type", "bucket", "catalyst_soon", "takeout_prone"):
        if LABEL[k] in lay["users"]:
            L.append(f"- {LABEL[k]}: {U[LABEL[k]]}. **You changed this.**")
    L.append(f"- Takeout candidate: {U[LABEL['takeout_prone']]}. {plan['takeout_prone']['reason']}"
             + (" Keep the position small (Chapter 12: takeout-prone shorts are never 5-10% positions)."
                if str(U[LABEL["takeout_prone"]]).upper() == "Y" else ""))
    L.append(f"- Catalyst: {plan['catalyst']['text']}")
    if not sm._n(borrow):
        L.append("- Borrow: check with PB. The drag at 5% and 20% borrow is shown above.")
    if ctx["stale"]["flag"]:
        L.append(f"- Stale price: the Valuation tab used {fmt(ctx['stale']['valuation_price'], MONEY)}; "
                 "rerun /model-valuation.")
    if ctx["short"].get("error"):
        L.append(f"- Yahoo failed ({ctx['short']['error']}): price and short data are n/a.")
    for t in ctx["missing"]:
        L.append(f"- The {t} tab is missing: its checks show ?.")
    up = os.path.join(work, "unverified.json")
    for n in (json.load(open(up)) if os.path.exists(up) else []):
        L.append(f"- UNVERIFIED: {n} (its anchor did not hold after two rounds).")
    os.makedirs(out_dir, exist_ok=True)
    p = os.path.join(out_dir, f"{ticker} short check {date}.md")
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
    pdf, why = render(md, md[:-3] + ".pdf", f"{a.ticker.upper()} short check · {a.date}")
    print(json.dumps({"md": md, "pdf": pdf, "pdf_skipped": why}, indent=1))


if __name__ == "__main__":
    main()
