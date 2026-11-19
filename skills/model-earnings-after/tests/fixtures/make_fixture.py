"""TEST_model.xlsx after its Q4 26 print, made the realistic way. model-earnings-before's own fixture and scripts
build the Earnings tab before the print (subprocesses: its modules never mix with ours, and a format change there
breaks these tests); then the print happens: MOD's Q4 26E becomes Q4 26 with actuals (revenue +4%, operating income
-3% against the freeze), Px Data and Px Events run past the reaction day, and a Valuation tab with the after-print
numbers is added. Also writes the research folder (transcript, release, pre-print Valuation Note, preview note) and
model-update's work folder (pre-print values.json, state.json with one placeholder). A test workbook made by
openpyxl: never a user's model."""
import datetime as dt
import json
import os
import shutil
import subprocess
import sys

import openpyxl
from openpyxl.utils import get_column_letter

HERE = os.path.dirname(os.path.abspath(__file__))
EB = os.path.abspath(os.path.join(HERE, "..", "..", "..", "model-earnings-before"))
EBFX = os.path.join(EB, "tests", "fixtures")
TICKER, Q, QE, FY = "TEST", "Q4 26", "Q4 26E", "2026"
TODAY_BEFORE = "2026-11-18"                       # the day model-earnings-before froze the quarter
RELEASE_DAY, REACTION_DAY = dt.date(2027, 2, 10), dt.date(2027, 2, 11)
DAY_MOVE, SPY_MOVE, IDIO = 0.08, 0.005, 0.075     # idio = move - beta (1.0) x SPY
DAYS_AFTER = 10                                   # trading days in Px Data after the reaction day (T+7 needs > 7)
ACTUAL_X = {"rev": 1.04, "gp": 1.04, "oi": 0.97, "ni": 0.97, "eps": 0.97}   # actual = frozen x this
MOD_KEYS = {"Revenue": "rev", "Gross Profit": "gp", "Operating Income": "oi", "Net Income": "ni",
            "EPS, diluted": "eps"}
PLACEHOLDER_KEY = "KEY OPERATING METRICS | Units"
TRANSCRIPT = f"Earnings Calls/_md/2026 Q4 {TICKER} call.md"
RELEASE = f"Press Releases/_md/2026 Q4 {TICKER} release {RELEASE_DAY}.md"
VALNOTE = f"Valuation/2026-11-17 {TICKER} Valuation Note.md"
PREVIEW = f"Earnings Previews/{TICKER} 2026 Q4 earnings preview 2026-11-18.md"
YAHOO = {"ticker": TICKER, "asof": "2027-02-25", "source": "Yahoo Finance chart (fixture)", "reaction_day":
         str(REACTION_DAY), "open": 55.0, "close": None, "prev_close": None, "price": None}
VALUATION_DATE = "2027-02-24"                     # after the reaction day on purpose: an after-print Valuation tab
VALUATION = {  # label: (before in the note, after on the tab)
    "P/E: reward price": (107.76, 118.00), "P/E: risk price": (59.80, 64.00), "P/E: reward / risk": (0.7, 1.1),
    "Blended reward price": (106.66, 116.00), "Blended risk price": (61.99, 66.00),
    "Blended reward / risk": (0.7, 1.0), "IRR: price now": (88.48, 95.00), "IRR: price in 3 years": (121.71, 140.00),
    "IRR": (0.112, 0.139), "IRR: years": (3, 3)}

TRANSCRIPT_LINES = [
    "# TEST Q4 2026 earnings call", "",
    "Jane Doe, CEO: Revenue grew 14% in the fourth quarter, our best quarter of the year.",
    "Jane Doe, CEO: For 2027 we expect revenue of $640 million to $650 million.",
    "John Roe, CFO: Operating margin was 16.5%, below last year because of launch costs.",
    "John Roe, CFO: We remain committed to a 20% operating margin by 2028.",
    "John Roe, CFO: We bought back $50 million of stock in the quarter.",
    "Analyst: How should we think about units next year?",
    "Jane Doe, CEO: Units should grow faster than revenue as the new product ramps.",
    "Jane Doe, CEO: We feel better about the business than at any time in the last two years.",
    "Jane Doe, CEO: A competitor's recall helped our new-patient adds in December.",
]


def _run(args):
    """A sibling-skill step in its own isolated interpreter; its stderr in the error if it fails."""
    p = subprocess.run([sys.executable, "-I", *args], capture_output=True, text=True)
    if p.returncode:
        raise RuntimeError(f"{args[0] if args[0] != '-c' else 'make_fixture'} failed:\n{p.stderr}")
    return p.stdout


def _preprint(path, work):
    """model-earnings-before's fixture + context + build: an Earnings tab with Q4 26E frozen on 2026-11-18."""
    base = path + ".base.xlsx"
    os.makedirs(work, exist_ok=True)
    # its fixture builds the workbook and dumps its Yahoo constant (EARN), never imported here: a module named
    # make_fixture in our sys.modules would shadow this file
    _run(["-c", f"import json, sys; sys.path.insert(0, {EBFX!r}); import make_fixture as m; m.build({base!r}); "
                f"json.dump(m.EARN, open({os.path.join(work, 'earnings.json')!r}, 'w'))"])
    sc = os.path.join(EB, "scripts")
    _run([os.path.join(sc, "context.py"), "--model", base, "--work", work, "--ticker", TICKER, "--values", base,
          "--research", os.path.join(EBFX, "research", TICKER),
          "--forecast-plan", os.path.join(EBFX, "forecast_plan.json"), "--today", TODAY_BEFORE])
    shutil.copy(os.path.join(EBFX, "plan_example.json"), os.path.join(work, "earnings_plan.json"))
    _run([os.path.join(sc, "build.py"), "--model", base, "--work", work, "--ticker", TICKER, "--out", path,
          "--variance", "earnings"])
    os.remove(base)


def _update_work(model_dir, model_path):
    """model-update's pre-print snapshot (every MOD cell as it was before the print, header still Q4 26E) and
    state.json naming one forecast placeholder: Units in the Q4 26 column, holding its pre-print value."""
    qw = os.path.join(model_dir, "_model_work", "update", Q)
    os.makedirs(qw, exist_ok=True)
    wb = openpyxl.load_workbook(model_path, read_only=True, data_only=True)
    mod = {c.coordinate: c.value for row in wb["MOD"].iter_rows() for c in row
           if getattr(c, "value", None) is not None}
    wb.close()
    json.dump({"MOD": mod}, open(os.path.join(qw, "values.json"), "w"), default=str)
    col = next(k[:-1] for k, v in mod.items() if v == QE and k[:-1].isalpha() and k[-1] == "2" and len(k) <= 4)
    unit_row = next(int(k[1:]) for k, v in mod.items() if k.startswith("B") and k[1:].isdigit() and v == "Units")
    ref = f"{col}{unit_row}"
    json.dump({"quarter": Q, "column": col, "fy_column": None, "awaiting": [],
               "placeholders": [{"ref": ref, "key": PLACEHOLDER_KEY, "kind": "10-Q", "value": mod[ref]}]},
              open(os.path.join(qw, "state.json"), "w"))


def _trading_days(start, end):
    d, out = start, []
    while d <= end:
        if d.weekday() < 5:
            out.append(d)
        d += dt.timedelta(days=1)
    return out


def _print(path):
    """The print: Q4 26 actuals in MOD, prices through the reaction day + DAYS_AFTER, the print's Px Events row and
    an after-print Valuation tab."""
    wb = openpyxl.load_workbook(path)
    mod = wb["MOD"]
    col = next(c.column for c in mod[2] if c.value == QE)
    mod.cell(2, col, Q)
    for r in range(3, mod.max_row + 1):
        key = MOD_KEYS.get(mod.cell(r, 2).value)
        if key and isinstance(mod.cell(r, col).value, (int, float)):
            mod.cell(r, col, mod.cell(r, col).value * ACTUAL_X[key])
    px = wb["Px Data"]
    last = max(r for r in range(5, px.max_row + 1) if px.cell(r, 1).value)
    d0, p, s = px.cell(last, 1).value, px.cell(last, 2).value, px.cell(last, 3).value
    d0 = d0.date() if isinstance(d0, dt.datetime) else d0
    days = _trading_days(d0 + dt.timedelta(days=1), REACTION_DAY + dt.timedelta(days=21))
    days = days[:days.index(REACTION_DAY) + DAYS_AFTER + 1]
    for i, d in enumerate(days):
        r = last + 1 + i
        ret = DAY_MOVE if d == REACTION_DAY else 0.001 * (1 if i % 2 else -1)
        p, s = p * (1 + ret), s * (1 + (SPY_MOVE if d == REACTION_DAY else 0.0002))
        px.cell(r, 1, d).number_format = "yyyy-mm-dd"
        px.cell(r, 2, p)
        px.cell(r, 3, s)
        px.cell(r, 4, ret)
    ev = wb["Px Events"]   # model-earnings-before's layout: Event date 9, Type 10, ..., Reaction day 13, Idio 17
    r = ev.max_row + 1
    for c, v in ((1, Q), (2, RELEASE_DAY), (9, RELEASE_DAY), (10, "Earnings"), (11, f"{Q} results"),
                 (12, "After close"), (13, REACTION_DAY), (14, DAY_MOVE), (15, SPY_MOVE), (16, 1.0), (17, IDIO)):
        ev.cell(r, c, v)
        if isinstance(v, dt.date):
            ev.cell(r, c).number_format = "yyyy-mm-dd"
    v = wb.create_sheet("Valuation")
    v["A1"] = f"{TICKER} valuation (model-valuation, {VALUATION_DATE})"
    for i, (lab, (_, after)) in enumerate(VALUATION.items()):
        v.cell(4 + i, 1, lab)
        v.cell(4 + i, 2, after)
    wb.save(path)


def _research(root):
    def put(rel, lines):
        p = os.path.join(root, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w") as f:
            f.write("\n".join(lines) + "\n")
    put(TRANSCRIPT, TRANSCRIPT_LINES)
    put(RELEASE, ["# TEST reports fourth quarter 2026 results", "",
                  "Fourth quarter revenue grew 14% to $140.4 million.",
                  "The company expects 2027 revenue of $640 million to $650 million."])
    put(PREVIEW, ["# TEST 2026 Q4 earnings preview", "", "Stance: hold."])
    v = {k: b for k, (b, _) in VALUATION.items()}
    now = v["IRR: price now"]
    rw, rk = v["Blended reward price"] / now - 1, 1 - v["Blended risk price"] / now
    prw, prk = v["P/E: reward price"] / now - 1, 1 - v["P/E: risk price"] / now
    put(VALNOTE, [  # model-valuation's note, sections 1-3, in its exact headings, bullets and table rows
        "## 1 The recommendation", "",
        f"The note values {TICKER} on 1 multiple, blended by weight.", "",
        "| 1. Which multiples and why | Role | Weight |", "|---|---|---|", "| P/E | primary | 100.0% |",
        "| Weights sum |  | 100.0% |", "",
        "- **P/E (primary)**: profitable on GAAP, the multiple the Street quotes.", "",
        "## 2 Targets and risk/reward", "",
        f"Today's price is ${now:.2f}.", "",
        f"- **P/E**: reward {prw * 100:.1f}% (to ${v['P/E: reward price']:.2f}), risk {prk * 100:.1f}% (to "
        f"${v['P/E: risk price']:.2f}), reward / risk {v['P/E: reward / risk']:.1f}x: below hurdle.",
        f"- **Blended**: reward {rw * 100:.1f}% (to ${v['Blended reward price']:.2f}), risk {rk * 100:.1f}% (to "
        f"${v['Blended risk price']:.2f}), reward / risk {v['Blended reward / risk']:.1f}x: below hurdle.", "",
        "### P/E", "", "| P/E (primary) | Ours | Street |", "|---|---|---|",
        f"| P/E: reward price | ${v['P/E: reward price']:.2f} |  |",
        f"| P/E: risk price | ${v['P/E: risk price']:.2f} |  |",
        f"| P/E: reward / risk | {v['P/E: reward / risk']:.1f}x |  |", "",
        "## 3 Three-year IRR", "", "| 5. 3-year IRR (P/E, the primary multiple) |  |", "|---|---|",
        f"| IRR: years | {v['IRR: years']} |",
        f"| IRR: price now | ${now:.2f} |",
        f"| IRR: price in 3 years | ${v['IRR: price in 3 years']:.2f} |",
        f"| IRR | {v['IRR'] * 100:.1f}% |", "", "## 4 The DCF scenarios", ""])


def build(model_dir, research_root):
    """Returns the model path. model_dir gets TEST_model.xlsx and _model_work/; research_root gets the documents."""
    os.makedirs(model_dir, exist_ok=True)
    path = os.path.join(model_dir, "TEST_model.xlsx")
    _preprint(path, os.path.join(model_dir, "_model_work", "model-earnings-before"))
    _update_work(model_dir, path)      # before the print: the snapshot is MOD as it was
    _print(path)
    _research(research_root)
    return path
