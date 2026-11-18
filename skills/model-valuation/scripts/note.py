"""The valuation note: Markdown, then a PDF through research-filings' render.py (cover, contents page, footer).

Every number comes from the recalculated Valuation tab (verify.run's `recalculated` file, passed as --values), found
through W/layout.json's refs or the tab's own row labels, and is printed in the cell's own number format. The words
come from the plan (reasons, notes, scenario rounds), context.json (the brief's cut and missing sections) and
inputs_written.next.json (the cells the user changed). Nothing is retyped by hand.

If the PDF cannot be made (WeasyPrint missing, say), the Markdown still stands and the printed JSON has "pdf": null and
"pdf_skipped" with the reason; exit 0, and the SKILL tells the user.

usage: python3 note.py --work W --ticker T --out-dir "<research_dir>/<T>/Valuation" --values RECALCULATED.xlsx
       [--date YYYY-MM-DD]"""
import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys

import openpyxl

import build

RENDER = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "research-filings", "scripts",
                                      "render.py"))
GAP = 0.25


def fmt(cell):
    """A cell's value as Excel would show it (its own number format), in plain text."""
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


def cell_text(v):
    return str(v).replace("|", "\\|").replace("\n", " ")


class Tab:
    """The recalculated Valuation tab: cells by ref, rows by their column-A label, blocks split at blank rows."""

    def __init__(self, path):
        wb = openpyxl.load_workbook(path, data_only=True)
        if build.TAB not in wb.sheetnames:
            raise SystemExit(f"model-valuation: {path} has no {build.TAB} tab; pass verify's recalculated file.")
        self.ws = wb[build.TAB]
        self.rows = {}
        for (c,) in self.ws.iter_rows(min_col=1, max_col=1):
            if isinstance(c.value, str):
                self.rows.setdefault(c.value.strip(), c.row)

    def at(self, ref):
        return self.ws[ref.replace("$", "")]

    def f(self, ref):
        return fmt(self.at(ref))

    def row(self, label):
        return self.rows.get(label)

    def get(self, label, col="B"):
        r = self.row(label)
        return None if r is None else self.ws[f"{col}{r}"]

    def g(self, label, col="B"):
        c = self.get(label, col)
        return "n/a" if c is None else fmt(c)

    def block(self, prefix):
        """Rows of the section whose header in A starts with `prefix`, up to the next blank row."""
        start = next((r for lab, r in self.rows.items() if lab.startswith(prefix)), None)
        if start is None:
            return []
        out, r = [], start
        while r <= self.ws.max_row and any(self.ws.cell(r, j).value is not None for j in range(1, 7)):
            out.append(r)
            r += 1
        return out

    def table(self, rows, cols, heads=None):
        """A Markdown table of `rows` over columns `cols` (letters); the first row is the header unless `heads`."""
        if not rows:
            return ""
        if heads is None:
            heads = [cell_text(self.ws[f"{c}{rows[0]}"].value or "") for c in cols]
            rows = rows[1:]
        L = ["| " + " | ".join(heads) + " |", "|" + "---|" * len(heads)]
        for r in rows:
            L.append("| " + " | ".join(cell_text(fmt(self.ws[f"{c}{r}"]) if self.ws[f"{c}{r}"].value is not None
                                                 else "") for c in cols) + " |")
        return "\n".join(L)


def _load(work, name, default=None):
    p = os.path.join(work, name)
    return json.load(open(p)) if os.path.exists(p) else default


def _user_changes(work):
    """{key: value the user kept}, from this build's record (or the last one if the build's was already promoted)."""
    rec = _load(work, "inputs_written.next.json") or _load(work, "inputs_written.json") or {}
    return {k: v["value"] for k, v in rec.items() if v.get("user")}


def _label(key):
    """The tab's label, with the weight's and the tree's cells told apart (their column-A label is the multiple or
    the branch name alone)."""
    if key.startswith("weight."):
        return f"Weight on {build.label_of(key)}"
    if key.startswith("tree."):
        return f"Tree branch {build.label_of(key)}: {'probability' if key.endswith('.prob') else 'target'}"
    return build.label_of(key)


def _as_input(tab, ref, v):
    """A raw input value printed in its yellow cell's number format."""
    c = tab.at(ref)
    if isinstance(v, str) and v.startswith("="):
        return f"the formula {v}"
    fake = type("C", (), {"value": v, "number_format": c.number_format})()
    return fmt(fake)


def write_md(work, ticker, values, date):
    plan = _load(work, "valuation_plan.json")
    ctx = _load(work, "context.json")
    lay = _load(work, "layout.json")
    if not (plan and ctx and lay):
        raise SystemExit("model-valuation: the work folder needs valuation_plan.json, context.json and layout.json.")
    t, ref = Tab(values), lay["ref"]
    kinds = [(m["kind"], build.KIND[m["kind"]]) for m in plan["multiples"]]
    L = []

    # cover
    target, rr, verdict = t.f(ref["blended_reward"]), t.g("Blended reward / risk"), t.g("Blended verdict")
    vcall = t.g(build.LABEL["verdict"]) if "verdict" in lay["inputs"] else None
    L += [f'<div class="cover"><div class="band"><h1>{ticker} valuation note</h1><div class="sub">What it is worth and '
          f'whether the setup is worth owning, as of {date}</div></div><div class="meta">'
          + (f'<b>Overall verdict: {vcall}.</b> {plan["verdict"]["reason"]} ' if vcall else "")
          + f'Blended target {target} against today\'s {t.f(ref["price"])}: reward / risk {rr}, {verdict}. Numbers come from the recalculated '
          f'Valuation tab of {ticker}_model.xlsx; the judgment calls are the valuation agent\'s, and every one is a '
          f'yellow cell you own. Prepared {date}.</div></div>', ""]

    # 1
    L += ["## 1 The recommendation", "",
          f"The note values {ticker} on {len(kinds)} multiple{'s' if len(kinds) > 1 else ''}, blended by weight. "
          "Levered multiples (P/E, FCF yield) are paired with equity value and unlevered ones (EV/...) with "
          "enterprise value; code fixes that pairing.", ""]
    L += [t.table(t.block("1. "), "ABC"), ""]
    for m in plan["multiples"]:
        L.append(f"- **{build.KIND[m['kind']]} ({m['role']})**: {m['reason']}")
    L.append("")

    # 2
    L += ["## 2 Targets and risk/reward", "",
          f"Today's price is {t.f(ref['price'])}, and the stock's annualized volatility over the last 253 closes is "
          f"{t.f(ref['vol'])}. Each multiple gives a 12-month reward price (a reward multiple on next year's forward "
          "metric) and a risk price (a risk multiple on a cut metric). Reward / risk is the upside over the downside; "
          f"the house buys at {t.f(ref['buy_rr'])} and presses at {t.f(ref['pound_rr'])}.", ""]
    for k, lab in kinds:
        L.append(f"- **{lab}**: reward {t.g(f'{lab}: reward %')} (to {t.g(f'{lab}: reward price')}), risk "
                 f"{t.g(f'{lab}: risk %')} (to {t.g(f'{lab}: risk price')}), reward / risk "
                 f"{t.g(f'{lab}: reward / risk')}: {t.g(f'{lab}: verdict')}. Reward-to-volatility "
                 f"{t.g(f'{lab}: reward-to-volatility')}; 1σ check: {t.g(f'{lab}: 1σ check')}.")
    L += [f"- **Blended**: reward {t.g('Blended reward %')} (to {t.f(ref['blended_reward'])}), risk "
          f"{t.g('Blended risk %')} (to {t.f(ref['blended_risk'])}), reward / risk {rr}: {verdict}.", ""]
    for k, lab in kinds:
        rows = t.block(f"{lab} (")
        if rows:
            L += [f"### {lab}", "", t.table(rows, "ABC"), ""]
    lad = t.block("4c.")
    if lad:
        L += ["### The reward / risk ladder", "",
              "The ladder shows how the blended reward / risk changes if you enter above or below today's price.", "",
              t.table(lad[1:], "ABCDE", ["Entry vs today", "Entry price", "Reward", "Risk", "Reward / risk"]), ""]

    # 3
    irr_rows = t.block("5. ")
    yrs = t.get("IRR: years")
    L += ["## 3 Three-year IRR", ""]
    if irr_rows:
        L += [f"Buying at {t.g('IRR: price now')} and selling at {t.g('IRR: price in 3 years')} gives an IRR of "
              f"{t.g('IRR')} a year, {t.g('IRR vs hurdle')} the {t.f(ref['hurdle'])} hurdle. The 3 R's split it: "
              f"roll-forward (the metric's growth) {t.g('Roll-forward (metric growth, a year)')} a year, re-rating "
              f"(the multiple's change) {t.g('Re-rating (multiple change, a year)')} a year, and revisions (our "
              f"forward numbers against the Street's) {t.g('Revisions (our NTM vs the Street' + chr(39) + 's)')}.",
              ""]
        dp = next((lab for lab in t.rows if lab.endswith("-year double path")), None)
        if dp:
            L += [f"The route to a double: {t.g(dp)}.", ""]
        if yrs is not None and isinstance(yrs.value, (int, float)) and yrs.value < 3:
            L += [f"MOD has fewer than 16 forecast quarters, so the IRR horizon is {fmt(yrs)} years, the last full "
                  "year available.", ""]
        L += [t.table(irr_rows, "AB"), ""]
    else:
        L += ["The tab has no IRR section.", ""]

    # 4
    dcf = t.block("6. ")
    L += ["## 4 The DCF scenarios", "",
          "The agent wrote bear, base and bull driver sets, and model-dcf's own math valued each one (verify re-typed "
          "each case into a copy of the DCF tab to prove the value per share). The last column is what today's price "
          "implies: the reverse DCF.", "", t.table(dcf, "ABCDE"), ""]
    imp = [r for r in dcf[1:] if t.ws[f"E{r}"].value is not None]
    if imp:
        L += ["What today's price implies, driver by driver:", ""]
        for r in imp:
            L.append(f"- {t.ws[f'A{r}'].value}: {fmt(t.ws[f'E{r}'])} (base case {fmt(t.ws[f'C{r}'])}).")
        L.append("")
    L += [f"The terminal value is {t.g('Terminal value share')} of the bear value, "
          f"{t.g('Terminal value share', 'C')} of the base and {t.g('Terminal value share', 'D')} of the bull.", ""]
    for case in ("bear", "base", "bull"):
        sc = plan["scenarios"]["final"].get(case)
        if sc:
            L.append(f"- **{case.capitalize()}** ({t.f(ref['dcf_' + case])}): {sc['story']}")
    L.append("")
    flag_r = t.row("DCF vs multiple target")
    pct_r = next((r for lab, r in t.rows.items() if lab.startswith("vs the multiple target")), None)
    flagged = []
    for col, case in zip("BCD", ("bear", "base", "bull")):
        v = t.ws[f"{col}{flag_r}"].value if flag_r else None
        if isinstance(v, str) and v.startswith("gap"):
            flagged.append((col, case))
    L += [f"A gap flag goes up when a DCF case is more than {GAP:.0%} from its multiple-based target (bear against "
          "the blended risk price, base against the blended reward price, bull against the top multiple target).", ""]
    if not flagged:
        L += ["No case is more than 25% from its target, so there are no gap flags.", ""]
    for col, case in flagged:
        why = [n for n in plan["notes"] if re.search(rf"\b{case}\b|\bgap\b", n, re.I)]
        gap = fmt(t.ws[f"{col}{pct_r}"]) if pct_r else "n/a"
        L.append(f"- **{case.capitalize()}**: {gap} from its target. "
                 + (" ".join(why) if why else "The plan's notes give no explanation for this gap; ask the agent "
                                              "for one before relying on this case."))
    L.append("")

    # 5
    tree = t.block("7. ")
    L += ["## 5 Probability tree", "",
          f"Each branch is a price with a probability the agent chose. The probability-weighted value is "
          f"{t.f(ref['tree_ev'])} against today's {t.f(ref['price'])}.", "", t.table(tree, "ABCD"), ""]
    sits = next((lab for lab in t.rows if lab.startswith("Where today's price sits")), None)
    if sits:
        L += [f"Today's price sits {t.g(sits)} of the way from the worst branch (0%) to the best (100%).", ""]
    for b in plan.get("tree") or []:
        L.append(f"- **{b['name']}**: {b['story']} Probability: {b['prob']['reason']}")
    L.append("")

    # 6
    L += ["## 6 Earnings power", ""]
    ep = t.block("3. ")
    if plan.get("normalization") and ep:
        L += ["The agent valued normalized earnings: a normal year's revenue times a normal margin, over that year's "
              "shares, discounted back at the house rate.", "", t.table(ep, "AB"), ""]
    else:
        L += ["Not used: the plan has no normalization, so the targets rest on the forecast's own forward earnings.",
              ""]

    # 7
    pin = build.plan_inputs(plan)
    L += ["## 7 Judgment calls", "", "### The agent's notes", ""]
    L += [f"- {n}" for n in plan["notes"]] + [""]
    L += ["### DCF scenario rounds", ""]
    for rd in plan["scenarios"]["rounds"]:
        L.append(f"- Round {rd['round']}: {rd['why']} Rejected: {rd['rejected']}")
    L += ["", "### Every yellow cell", "",
          "Each one is the agent's suggestion and yours to change. Its anchor is the cell, research line or forward "
          "sum it starts from; `house` means chapter 11's default and `judgment` an explained call.", "",
          "| Input | Value | Anchor | Reason |", "|---|---|---|---|"]
    for key, cref in lay["inputs"].items():
        x = pin.get(key, {})
        a = x.get("anchor", "")
        if "anchor_value" in x:
            a += f" = {x['anchor_value']:.4g}" if isinstance(x["anchor_value"], float) else f" = {x['anchor_value']}"
        L.append(f"| {cell_text(_label(key))} | {cell_text(t.f(cref))} | {cell_text(a)} | "
                 f"{cell_text(x.get('reason', ''))} |")
    L += ["", "### Your changes", ""]
    user = _user_changes(work)
    if user:
        L.append("These cells hold your value, not the agent's, and the rebuild kept them:")
        for key, v in user.items():
            cref = lay["inputs"].get(key)
            agent = pin.get(key, {}).get("value")
            show = (lambda z: _as_input(t, cref, z)) if cref else str
            L.append(f"- {_label(key)}: agent {show(agent)} → yours {show(v)}")
    else:
        L.append("None: every yellow cell holds the agent's value.")
    house = ctx.get("house", {})
    moved = [k for k, v in house.items() if k in pin and pin[k].get("value") != v]
    L += ["", "### Fixed calls", "",
          "- NTM is the sum of MOD's first four forecast quarters and NTM+1 is quarters 5 to 8; the 3-year metric is "
          "quarters 13 to 16 (with fewer forecast quarters, the IRR horizon is the last full year).",
          "- Today's price, net debt and diluted shares link to the DCF tab, so both tabs use one bridge.",
          f"- A DCF case more than {GAP:.0%} from its multiple-based target is flagged, and the agent explains it.",
          "- House inputs (hurdle, buy and pound reward / risk, discount, horizon, market growth) are chapter 11's "
          "defaults" + (f"; the agent changed {', '.join(moved)}, with the reason in the table above." if moved
                        else ", unchanged."),
          "- Every number the agent chose is anchored to a cell, a research line, a forward sum, a house default or "
          "an explained judgment, and code checked each anchor before the build."]
    if (ctx.get("dcf") or {}).get("stale"):
        L.append("- The DCF tab was stale when this ran (its inputs no longer matched MOD); the scenarios use it as "
                 "it stood. Rerun /model-dcf to refresh it.")
    L.append("")

    # 8
    b = ctx.get("brief") or {}
    L += ["## 8 What the brief cut", "",
          "The agent read a short valuation brief of the research reports, not the whole reports. This is what the "
          "brief left out.", ""]
    for name, p in (b.get("reports") or {}).items():
        L.append(f"- {name}: {os.path.basename(p) if p else 'no report found'}")
    L.append("")
    if b.get("cut"):
        L += ["Cut short (the rest is in the full report):", ""]
        L += [f"- {c['section']}: kept {c['kept']} of {c['words']} words (rest at {c['source']})" for c in b["cut"]]
        L.append("")
    if b.get("missing"):
        L += ["Missing (the section was not found, so the agent did not see it):", ""]
        L += [f"- {m}" for m in b["missing"]]
        L.append("")
    if not b.get("cut") and not b.get("missing"):
        L += ["Nothing: every section was included in full.", ""]
    return "\n".join(L)


def render(md_path, pdf_path, footer):
    """(pdf path, None) or (None, the reason the PDF was not made)."""
    if not os.path.exists(RENDER):
        return None, f"research-filings' render.py is not at {RENDER}"
    r = subprocess.run([sys.executable, RENDER, md_path, pdf_path, "--footer", footer], capture_output=True, text=True)
    if r.returncode or not os.path.exists(pdf_path):
        tail = (r.stderr or r.stdout).strip().splitlines()
        why = next((x for x in reversed(tail) if "WeasyPrint" in x or "Error" in x), tail[-1] if tail else "")
        return None, f"render.py failed ({why.strip()}); install WeasyPrint (pip install weasyprint; brew install pango)"
    return pdf_path, None


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True)
    ap.add_argument("--ticker", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--values", required=True, help="verify's recalculated file")
    ap.add_argument("--date", default=dt.date.today().isoformat())
    a = ap.parse_args(argv)
    md = write_md(a.work, a.ticker, a.values, a.date)
    os.makedirs(a.out_dir, exist_ok=True)
    base = os.path.join(a.out_dir, f"{a.date} {a.ticker} Valuation Note")
    with open(base + ".md", "w") as fh:
        fh.write(md)
    footer = f"{a.ticker} valuation note · {dt.date.fromisoformat(a.date).strftime('%b %Y')}"
    pdf, why = render(base + ".md", base + ".pdf", footer)
    res = {"md": base + ".md", "pdf": pdf, "words": len(re.sub(r"<[^>]+>", " ", md).split())}
    if why:
        res["pdf_skipped"] = why
    return res


if __name__ == "__main__":
    print(json.dumps(main(), indent=1))
