"""Recalculate the built model in LibreOffice and check the Valuation tab before it replaces the user's file:
- compare: every checked cell (layout.json "expected") recalculates to valmath's value (rel 1e-6; text equal; an
  expected None means #N/A, not a blank); #N/A is fine wherever the math says None (a long whose risk price is above
  today's price has no R/R, so its verdict is #N/A too); any other error value on the tab fails;
- changed_parts: every other part of the workbook is byte-identical to the input (the old Valuation tab's parts may
  change or go);
- colours: typed blue, links green, formulas black, inputs blue on yellow, nothing else yellow, every yellow cell noted;
- pairing: unlevered multiples price EV (take off net debt, divide by shares); levered ones price equity (P/E uses
  neither; FCF yield divides FCF by shares but never takes off net debt);
- dcf: each final DCF scenario typed into a copy of the DCF tab gives the plan's value per share (scenario_eval
  typecheck, in model-dcf's own process);
- anchors: anchors.check again on W/values, as a guard;
- png: the Valuation page as W/valuation.png, for Claude to look at (not a pass/fail check).

usage: python3 verify.py --model M --out OUT --work W [--research-dir D]   (prints JSON; exit 1 unless ok)"""
import argparse
import datetime as dt
import json
import math
import os
import re
import subprocess
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))   # run with python3 -I

import openpyxl  # noqa: E402

import anchors  # noqa: E402
import lo  # noqa: E402
import valmath  # noqa: E402
from xlsx import Package, relpath_of, resolve  # noqa: E402

ALLOWED = {"xl/workbook.xml", "xl/_rels/workbook.xml.rels", "[Content_Types].xml", "xl/styles.xml", "xl/calcChain.xml",
           "docProps/app.xml"}
TAB = "Valuation"
TITLE = "valuation: what it's worth"
BLUE, BLACK, GREEN, YELLOW = "FF0000FF", "FF000000", "FF008000", "FFFFFF99"
HERE = os.path.dirname(os.path.realpath(__file__))


def _layout(work):
    return json.load(open(os.path.join(work, "layout.json")))


def close(a, b):
    """model-multiples' close, plus text: a text cell must equal its expected text; None matches #N/A only."""
    if isinstance(a, dt.datetime):                        # date-formatted cells read back as datetimes
        a = (a - dt.datetime(1899, 12, 30)).total_seconds() / 86400
    if b is None:
        return a == "#N/A"
    if isinstance(b, str):
        return a == b
    if not isinstance(a, (int, float)) or isinstance(a, bool):
        return False
    return math.isclose(a, b, rel_tol=1e-6, abs_tol=1e-9)


def compare(out, work):
    """Recalculate OUT into W/verify/ and compare the tab with layout.json. Returns {checked, valued (checked cells
    with a value, not #N/A, expected), failed, errors, recalculated}."""
    lay = _layout(work)
    rec = lo.recalc(out, os.path.join(work, "verify"))
    ws = openpyxl.load_workbook(rec, data_only=True)[TAB]
    exp = lay["expected"]
    failed = [{"cell": ref, "got": ws[ref].value, "want": want} for ref, want in exp.items()
              if not close(ws[ref].value, want)]
    na_ok = {ref for ref, want in exp.items() if want is None}
    errors = [c.coordinate for row in ws.iter_rows() for c in row
              if isinstance(c.value, str) and c.value.startswith("#") and not (c.value == "#N/A" and c.coordinate in na_ok)]
    return {"checked": len(exp), "valued": sum(v is not None for v in exp.values()), "failed": failed[:30],
            "errors": errors[:30], "recalculated": rec}


def tab_parts(path):
    """The Valuation tab's own parts (sheet, rels, comments, VML) in `path`; empty when it has no such tab."""
    pkg = Package(path)
    todo = [p for n, _, _, p in pkg.sheets() if n == TAB]
    seen = set()
    while todo:
        p = todo.pop()
        if p in seen:
            continue
        seen |= {p, relpath_of(p)}
        todo += [resolve(p, t) for _, (_, t) in pkg.rels(relpath_of(p)).items() if "TargetMode" not in t]
    return seen


def changed_parts(model, out):
    """Parts of the model that OUT dropped or changed, other than ALLOWED and the old Valuation tab's own parts."""
    a, b = zipfile.ZipFile(model), zipfile.ZipFile(out)
    skip, have = ALLOWED | tab_parts(model), set(b.namelist())
    return [n for n in a.namelist() if n not in skip and (n not in have or a.read(n) != b.read(n))]


def _rgb(c):
    return c.rgb if c is not None and isinstance(getattr(c, "rgb", None), str) else None


def colours(out, work):
    """Colour problems, each naming its cell; [] means every cell is the colour its role says."""
    lay = _layout(work)
    ws = openpyxl.load_workbook(out)[TAB]
    probs = []
    for key, want, what in (("typed", BLUE, "typed number: blue"), ("links", GREEN, "link to another tab: green"),
                            ("formulas", BLACK, "formula: black")):
        for ref in lay[key]:
            got = _rgb(ws[ref].font.color)
            if got != want:
                probs.append(f"{ref}: {what}, but its font is {got}")
    inputs = set(lay["inputs"].values())
    for key, ref in lay["inputs"].items():
        c = ws[ref]
        if _rgb(c.font.color) != BLUE or _rgb(c.fill.fgColor) != YELLOW or c.fill.fill_type != "solid":
            probs.append(f"{ref} ({key}): an input must be blue on yellow (font {_rgb(c.font.color)}, "
                         f"fill {_rgb(c.fill.fgColor)})")
    for row in ws.iter_rows():
        for c in row:
            if c.fill.fill_type == "solid" and _rgb(c.fill.fgColor) == YELLOW:
                if c.coordinate not in inputs:
                    probs.append(f"{c.coordinate}: yellow, but it is not one of the agent's inputs")
                if c.comment is None:
                    probs.append(f"{c.coordinate}: yellow with no note (the agent's value, anchor and reason)")
    return probs


def _uses(formula, ref):
    return re.search(re.escape(ref) + r"(?!\d)", formula) is not None


def pairing(work):
    """Chapter 11.2: unlevered multiples (EV/x) price EV, so take off net debt and divide by shares; P/E prices the
    share from EPS alone; FCF yield divides FCF by shares and never takes off net debt."""
    lay = _layout(work)
    ref, ft = lay["ref"], lay["formula_text"]
    nd, sh = ref["nd"], ref["sh"]
    probs = []
    for name, cell in ref.items():
        m = re.fullmatch(r"(reward|risk)_px\.(\w+)", name)
        if not m:
            continue
        k, f = m.group(2), ft.get(cell.replace("$", ""), "")
        want_nd, want_sh = k not in valmath.LEVERED, k != "pe"
        if _uses(f, nd) != want_nd or _uses(f, sh) != want_sh:
            probs.append(f"{cell.replace('$', '')} ({m.group(1)} price, {k}): net debt "
                         f"{'needed' if want_nd else 'not allowed'}, shares {'needed' if want_sh else 'not allowed'}; "
                         f"formula is ={f}")
    return probs


def dcf_retype(out, work):
    """scenario_eval typecheck (model-dcf's own process): problems, [] when every final case's value holds."""
    cmd = [sys.executable, "-I", os.path.join(HERE, "scenario_eval.py"), "typecheck", "--after", out,
           "--dcf", os.path.join(work, "dcf_ctx.json"), "--plan", os.path.join(work, "valuation_plan.json"),
           "--work", os.path.join(work, "verify")]
    r = subprocess.run(cmd, capture_output=True, text=True)
    try:
        return json.loads(r.stdout)["problems"]
    except (ValueError, KeyError):
        return [f"the DCF re-type check did not run: {(r.stderr or r.stdout).strip()[-400:]}"]


def anchor_check(work, research_dir=None):
    """anchors.check on the recalculated copy context.py made; the research folder is looked up only when a plan
    anchor cites a research line."""
    plan = json.load(open(os.path.join(work, "valuation_plan.json")))
    ctx = json.load(open(os.path.join(work, "context.json")))
    if research_dir is None and any(isinstance(x, dict) and anchors.LINE.match(str(x.get("anchor", "")))
                                    for _, x in anchors._walk(plan)):
        sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "lib"))
        import settings
        research_dir = settings.research_dir()
    root = os.path.join(research_dir or "", ctx["ticker"])
    return anchors.check(plan, ctx["values"], root, ctx)


def find_page(pdf):
    """PDF page of the Valuation tab: the one whose text has the tab's title (one page per tab)."""
    import fitz
    for i, pg in enumerate(fitz.open(pdf)):
        if TITLE in pg.get_text().lower().replace("’", "'"):
            return i
    raise ValueError("no page with the Valuation title")


def run(model, out, work, research_dir=None):
    c = compare(out, work)
    changed = changed_parts(model, out)
    col, pair = colours(out, work), pairing(work)
    dcf = dcf_retype(out, work)
    anc = anchor_check(work, research_dir)
    png = os.path.join(work, "valuation.png")
    try:
        pdf = lo.render_pdf(c["recalculated"], os.path.join(work, "verify"))
        lo.page_png(pdf, find_page(pdf), png)
    except Exception as e:                                # the PNG is for looking, not for passing
        png = f"not rendered: {e}"
    ok = not (c["failed"] or c["errors"] or changed or col or pair or dcf or anc)
    return {"checked": c["checked"], "failed": c["failed"], "errors": c["errors"], "changed_parts": changed,
            "colours": col[:30], "pairing": pair, "dcf": dcf, "anchors": anc, "png": png,
            "recalculated": c["recalculated"], "ok": ok}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--research-dir", help="default: settings research_dir (read only for research-line anchors)")
    a = ap.parse_args()
    r = run(a.model, a.out, a.work, a.research_dir)
    print(json.dumps(r, indent=1, default=str))
    raise SystemExit(0 if r["ok"] else 1)
