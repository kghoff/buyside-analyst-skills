# skills/model-earnings-after/scripts/context.py
"""Everything code can answer after the print, for the earnings-analyst agent (context.md) and build.py
(context.json, with the cell refs the band 9-15 formulas need).

Facts only: the quarter (band 7's, checked against MOD's newest actual), each frozen line against its actual
(placeholders flagged, not scored), the move (release and reaction day, day and idio move, daily sigma over the 252
returns before the reaction day, run-up, drift once T+7 exists, Yahoo's gap and open-to-close), the estimates for
this fiscal year and next before the print (model-update's snapshot) and now (MOD), the valuation before (the last
Valuation Note dated before the release) and after (the Valuation tab), the IRR at the latest close with the fade
table, the documents to read, the Call Notes topics and history.

usage: python3 context.py --model M --work W --ticker T [--values RECALCULATED.xlsx] [--research DIR]
       [--forecast-plan PATH] [--today YYYY-MM-DD] [--quarter-only]
(without --values, M is recalculated in LibreOffice into W/values first; --research defaults to
<research_dir>/<T>; --forecast-plan to <model dir>/_model_work/forecast/forecast_plan.json.
--quarter-only prints {"quarter", "quarter_e", "reaction_day"} from the model alone, no recalculation, and exits.)"""
import argparse
import datetime as dt
import glob
import json
import os
import re
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))   # run with python3 -I
import openpyxl  # noqa: E402
from openpyxl.utils import column_index_from_string as ci  # noqa: E402

import aftermath as am  # noqa: E402
import callnotes  # noqa: E402
import earnings_tab as et  # noqa: E402
import rates  # noqa: E402
import transcript  # noqa: E402
import valnote  # noqa: E402
from modmap import ModMap  # noqa: E402

SKILL = "model-earnings-after"
REQUIRED = {"MOD": "model-historicals", "Px Data": "model-price-history", "Px Events": "model-price-history"}
IN_LINE_LABEL = "In-line band (±, for the beat / miss column)"     # band 9's input (build.py writes it)
HOUSE = {"in_line": 0.01}
EMPTY = ("likely the values copy was not recalculated (run without --values to recalculate in LibreOffice), or "
         "the cell is blank in the model.")
ESTIMATE_KEYS = (("Revenue", r"\| (total )?(net )?(revenues?|sales)$"), ("Gross profit", r"\| gross profit$"),
                 ("Operating income", r"\| operating income"), ("EPS, diluted", r"\| eps,? diluted"))
STALE_PX_DAYS = 5                       # calendar days: Px Data older than this is not today's price


def _stop(msg):
    raise SystemExit(f"{SKILL} stopped: {msg}")


def grid(ws):
    ws.reset_dimensions()
    return {(c.row, c.column): c.value for row in ws.iter_rows() for c in row if getattr(c, "value", None) is not None}


def quarter_of(model):
    """(Earnings tab read, ModMap, quarter, quarter_e) from the model itself, or a stop naming the skill to run."""
    tab = et.read(model)
    if tab is None or not tab["frozen"]:
        _stop("the Earnings tab or its band 7 (the frozen forecast) is missing. Run /model-earnings-before before "
              "the print; without the freeze there is nothing to compare the print with.")
    qe = tab["frozen"]["quarter"]
    q = qe.rstrip("E").strip()
    mm = ModMap(model)
    if f"{q}E" in mm.labels:
        _stop(f"MOD's {q} column is still headed {q}E: its actuals are not in yet. Run /model-update first.")
    actual = [p for p in mm.order if mm.is_q(p) and not p.endswith("E")]
    newest = actual[-1] if actual else None
    if newest != q:
        _stop(f"band 7 froze {qe}, but the model's newest actual quarter is {newest}. The after-print review "
              f"compares a print with its own freeze: rerun /model-earnings-before for the next print, or put "
              f"{q}'s actuals in with /model-update.")
    return tab, mm, q, qe


def reaction(g_ev, day):
    """The first earnings event in Px Events on or after the release day: {row, event_date, reaction_day}."""
    hr, h = rates._header(g_ev, "Reaction day")
    if hr is None or "Type" not in h:
        return None
    ce = h.get("Event date")
    best = None
    for r in range(hr + 1, max(rr for rr, _ in g_ev) + 1):
        t, d = g_ev.get((r, h["Type"])), rates._day(g_ev.get((r, h["Reaction day"])))
        e = rates._day(g_ev.get((r, ce))) if ce else None
        if isinstance(t, str) and t.lower().startswith("earn") and d and (e or d) >= day and (not best or d < best[1]):
            best = (r, d, e or d)
    return {"row": best[0], "reaction_day": best[1], "event_date": best[2]} if best else None


def release_and_reaction(g_ev, q):
    rel = rates.release(g_ev, q)
    if not rel:
        _stop(f"Px Events has no full-results release date for {q}. Rerun /model-price-history after the print.")
    rx = reaction(g_ev, rel[0])
    if not rx:
        _stop(f"Px Events has no earnings reaction on or after {q}'s release ({rel[0]}). Rerun /model-price-history.")
    return rel, rx


# ---------------------------------------------------------------- the move
def sigma_before(P, i):
    """Stdev of the 252 Px Data returns before index i (the reaction day's own return excluded), with its formula."""
    rows = [x for x in P["rows"][:i] if am._n(x["ret"])][-rates.VOL_DAYS:]
    if len(rows) < 20:
        return {"formula": "NA()", "value": None, "n": len(rows)}
    col = P["cols"]["ret"]
    return {"formula": f"IFERROR(STDEV('Px Data'!${col}${rows[0]['row']}:${col}${rows[-1]['row']}),NA())",
            "value": statistics.stdev(x["ret"] for x in rows), "n": len(rows)}


def _yahoo(work):
    p = os.path.join(work, "yahoo_after.json")
    return json.load(open(p)) if os.path.exists(p) else {"error": "fetch_after.mjs was not run"}


def add_trading_days(d, n):
    """d plus n weekdays (holidays are not known here: close enough to say when T+7 is due)."""
    while n:
        d += dt.timedelta(days=1)
        n -= d.weekday() < 5
    return d


def move(g_ev, P, ticker, rel, rx, work, today, warnings):
    idx = {x["date"]: i for i, x in enumerate(P["rows"])}
    day = rx["reaction_day"]
    if P["rows"][-1]["date"] < day:
        _stop(f"Px Data ends {P['rows'][-1]['date']}, before the reaction day {day}. Rerun /model-price-history.")
    if day not in idx:
        _stop(f"Px Data has no row for the reaction day {day} (Px Events' date), though it runs past it. Rerun "
              "/model-price-history.")
    pr = next((p for p in rates.prints(g_ev, P, ticker) if p["row"] == rx["row"]), None)
    if pr is None:
        _stop(f"Px Events' reaction row {rx['row']} has no day move. Rerun /model-price-history.")
    i = idx[day]
    rows, c = P["rows"], P["cols"]["close"]
    ref = lambda k: f"'Px Data'!${c}${rows[k]['row']}"   # noqa: E731
    sg = sigma_before(P, i)
    run_ok, drift_ok = i - 1 - rates.RUN >= 0, i + rates.DRIFT < len(rows) and am._n(rows[i + rates.DRIFT]["close"])
    due = add_trading_days(day, rates.DRIFT)
    if not drift_ok and today >= due.isoformat():
        warnings.append(f"The drift to T+7 ({due}) is due but Px Data ends {rows[-1]['date']}: rerun "
                        "/model-price-history for the drift.")
    y = _yahoo(work)
    if y.get("error"):
        warnings.append(f"Yahoo's reaction-day bars failed ({y['error']}): the gap at the open and open-to-close "
                        "show '?'.")
        y = {}
    elif str(y.get("reaction_day")) != day.isoformat():
        warnings.append(f"yahoo_after.json is for {y.get('reaction_day')}, not the reaction day {day}: the gap at "
                        "the open and open-to-close show '?' (rerun fetch_after.mjs with the right day).")
        y = {}
    o, cl, pc = y.get("open"), y.get("close"), y.get("prev_close")
    return {"release_day": rel[0].isoformat(), "release_ref": rel[1], "reaction_day": day.isoformat(),
            "event_date": rx["event_date"].isoformat(), "reaction_ref": pr["refs"]["date"],
            "day": pr["move"], "day_ref": pr["refs"]["move"], "idio": pr["idio"], "idio_ref": pr["refs"]["idio"],
            "daily_sigma": sg["value"], "sigma_formula": sg["formula"], "sigma_n": sg["n"],
            "sigmas": am.sigmas(pr["move"], sg["value"]),
            "run_up": pr["run_up"] if run_ok else None,
            "run_up_formula": f"IFERROR({ref(i - 1)}/{ref(i - 1 - rates.RUN)}-1,NA())" if run_ok else None,
            "drift": pr["drift"] if drift_ok else None,
            "drift_formula": f"IFERROR({ref(i + rates.DRIFT)}/{ref(i)}-1,NA())" if drift_ok else None,
            "drift_day": rows[i + rates.DRIFT]["date"].isoformat() if drift_ok else None,
            "drift_due": due.isoformat(),
            "open": o if am._n(o) else None, "close": cl if am._n(cl) else None,
            "prev_close": pc if am._n(pc) else None,
            "gap": am.growth(o, pc), "open_to_close": am.growth(cl, o),
            "yahoo_source": f"{y['source']}, {y.get('asof')}" if y.get("source") else None}


# ---------------------------------------------------------------- actual vs frozen
def _state(model, q):
    p = os.path.join(os.path.dirname(os.path.abspath(model)), "_model_work", "update", q)
    st = os.path.join(p, "state.json")
    return p, (json.load(open(st)) if os.path.exists(st) else None)


def frozen_rows(tab, mm, gm, q, state, band, warnings):
    col = mm.col(q)
    ph_refs = {x.get("ref") for x in (state or {}).get("placeholders", [])}
    ph_keys = {x.get("key") for x in (state or {}).get("placeholders", [])}
    out = []
    for f in tab["frozen"]["rows"]:
        r = mm.keys.get(f["label"])
        if r is None:
            warnings.append(f"Band 7's line {f['label']!r} is no longer a MOD line: no actual to compare.")
        a = gm.get((r, ci(col))) if r else None
        a = a if am._n(a) else None
        fq = f["q"] if am._n(f["q"]) else None
        ph = bool(r) and (f"{col}{r}" in ph_refs or f["label"] in ph_keys)
        if r and a is None and not ph:
            warnings.append(f"MOD {col}{r} ({f['label']}, {q}) has no value: {EMPTY}")
        s = None if ph else am.surprise(a, fq)
        out.append({"label": f["label"], "row": f["row"], "frozen": fq, "frozen_ref": f"$B${f['row']}",
                    "frozen_fy": f["fy"] if am._n(f["fy"]) else None, "frozen_fy_ref": f"$C${f['row']}",
                    "mod_row": r, "mod_ref": f"'MOD'!${col}${r}" if r else None, "actual": a,
                    "diff": None if ph or a is None or fq is None else a - fq, "surprise": s,
                    "result": None if ph else am.result(s, band), "placeholder": ph})
    return out


# ---------------------------------------------------------------- estimates
def drivers(mm, plan_path, warnings):
    """(Copied from model-earnings-before context.py.) The forecast plan's revenue-identity factors with a MOD row
    (at most 3), as model-dcf reads them."""
    if not plan_path or not os.path.exists(plan_path):
        warnings.append("No forecast plan found, so the Call Notes have no driver rows and the estimates leave out "
                        "the key drivers (rerun /model-forecast to add them).")
        return []
    out = []
    for t in (json.load(open(plan_path)).get("revenue_identity") or {}).get("terms", []):
        for f in t.get("factors", []):
            try:
                out.append({"name": f.get("name") or f["key"].split(" | ")[-1], "key": f["key"], "row": mm.row(f["key"])})
            except KeyError:
                warnings.append(f"The forecast plan's driver {f['key']!r} has no MOD row; left out.")
    return out[:3]


def _snap_col(snap, period):
    want = period.rstrip("E")
    return next((k[:-1] for k, v in snap.items() if re.fullmatch(r"[A-Z]+2", k) and str(v).strip().rstrip("E") == want),
                None)


def estimates(mm, gm, q, frozen, drv, snap, snap_path, warnings):
    fys = [p for p in mm.order if re.fullmatch(r"\d{4}E?", p)]
    fy = mm.fy_of(q)
    fy1 = fys[fys.index(fy) + 1] if fys.index(fy) + 1 < len(fys) else None
    if snap is None:
        warnings.append("No model-update snapshot (values.json) for this quarter: this year's 'before' comes from "
                        "band 7, next year's is '?'.")
    want = []
    for name, rx in ESTIMATE_KEYS:
        k = next((key for _, key, _ in mm.lines if re.search(rx, key, re.I)), None)
        if k:
            want.append({"name": name, "label": k, "kind": "line"})
    want += [{"name": d["name"], "label": d["key"], "kind": "driver"} for d in drv
             if d["key"] not in {w["label"] for w in want}]
    by_label = {f["label"]: f for f in frozen}
    out = []
    for w in want:
        r = mm.keys[w["label"]]
        label_b = gm.get((r, 2))
        e = {**w, "row": r}
        for slot, p in (("fy", fy), ("fy1", fy1)):
            if not p:
                e[slot] = None
                continue
            col = mm.col(p)
            now = gm.get((r, ci(col)))
            before, src = None, None
            sc = _snap_col(snap, p) if snap else None
            if sc and snap.get(f"B{r}") == label_b and am._n(snap.get(f"{sc}{r}")):
                before, src = snap[f"{sc}{r}"], {"kind": "snapshot", "path": snap_path, "ref": f"{sc}{r}"}
            elif slot == "fy" and (f := by_label.get(w["label"])) and f["frozen_fy"] is not None:
                before, src = f["frozen_fy"], {"kind": "band 7", "ref": f["frozen_fy_ref"]}
            f = by_label.get(w["label"])
            dq = (f["actual"] - f["frozen"]) if slot == "fy" and f and None not in (f["actual"], f["frozen"]) else None
            e[slot] = {"period": p, "ref": f"'MOD'!${col}${r}", "now": now if am._n(now) else None,
                       "before": before, "before_src": src, "change": am.growth(now, before) if am._n(now) else None,
                       "delta_q": dq}
        out.append(e)
    return out


# ---------------------------------------------------------------- consensus (the preview's variance grid)
VAR_EARN, VAR_CONS = "6. VARIANCE GRID", "2. VARIANCE"   # model-earnings-before band 6 / model-consensus band 2


def _notes(model, tab):
    """{ref: comment text} of one tab, read from the raw XML (no full workbook load)."""
    from xlsx import Package, relpath_of, resolve
    pkg = Package(model)
    sh = {s[0]: s for s in pkg.sheets()}.get(tab)
    out = {}
    if not sh:
        return out
    for _, (typ, tgt) in pkg.rels(relpath_of(sh[3])).items():
        if typ.endswith("/comments"):
            x = pkg.text(resolve(sh[3], tgt))
            for ref, body in re.findall(r'<comment ref="([A-Z]+\d+)"[^>]*>(.*?)</comment>', x, re.S):
                out[ref] = re.sub(r"<[^>]+>", "", body).replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    return out


def consensus(model, values, quarter):
    """The consensus the preview's variance grid held for the quarter (column C): on the Earnings tab's band 6, or
    in the Consensus tab's '2. VARIANCE' block (label in B). A minimal locator copied in idea from
    model-earnings-before variance.inspect (not imported: the sibling's modules never mix with ours).
    {where: 'earnings' / 'consensus' / None, rows: [{label, q, q_ref}] (only rows with a number), source: the
    first consensus cell's note, or None}. Blank or skeleton grid: rows []."""
    wb = openpyxl.load_workbook(values, read_only=True, data_only=True)
    for tab, band, lab_col in ((et.TAB, VAR_EARN, 1), ("Consensus", VAR_CONS, 2)):
        if tab not in wb.sheetnames:
            continue
        g = grid(wb[tab])
        a = sorted((r, str(v).strip()) for (r, c), v in g.items() if c == 1 and isinstance(v, str))
        top = next((r for r, t in a if t.startswith(band)), None)
        if top is None:
            continue
        head = str(g.get((top + 1, 3)) or "")
        if quarter not in head.replace("E", ""):
            continue                                  # a grid for another quarter is not this print's consensus
        end = next((r for r, t in a if r > top and re.match(r"\d+\.", t)), max(r for r, _ in g) + 1)
        rows = [{"label": str(g[(r, lab_col)]).strip(), "q": g[(r, 3)], "q_ref": f"'{tab}'!$C${r}"}
                for r in range(top + 2, end) if (r, lab_col) in g and am._n(g.get((r, 3)))]
        if not rows:
            continue
        wb.close()
        src = _notes(model, tab).get(rows[0]["q_ref"].split("!")[1].replace("$", ""))
        return {"where": "earnings" if tab == et.TAB else "consensus", "rows": rows, "source": src}
    wb.close()
    return {"where": None, "rows": [], "source": None}


# ---------------------------------------------------------------- valuation, docs, house
def _fresh_note(root, ticker, day):
    """The newest '<date> <T> Valuation Note.md' dated on or after day, the release day (model-valuation writes one
    every run; its tab title carries no date). The release day, not the reaction day: after an after-close release
    the evening's /model-valuation run is dated the release day and already knows the print."""
    d = os.path.join(root, "Valuation")
    got = sorted(f for f in (os.listdir(d) if os.path.isdir(d) else [])
                 if (m := valnote.NOTE_RE.match(f)) and m.group(2) == ticker and m.group(1) >= day)
    return f"Valuation/{got[-1]}" if got else None


def valuation(root, ticker, release_day, reaction_day, values, warnings):
    p = valnote.latest_before(root, ticker, release_day)
    before = valnote.parse(p) if p else None
    if not p:
        warnings.append(f"No Valuation Note dated before {release_day} in {root}/Valuation: band 13's 'before' "
                        "column shows '?'.")
    elif before["problem"]:
        warnings.append(f"The Valuation Note {os.path.basename(p)}: {before['problem']}; its values show '?'.")
    if before:
        before["path"] = os.path.relpath(p, root)
    aft = valnote.after(values)
    if aft is None:
        warnings.append("The model has no Valuation tab: band 13's 'after' column shows '?'. Run /model-valuation.")
    else:
        aft["fresh_note"] = _fresh_note(root, ticker, release_day)
        if not aft["fresh_note"]:
            warnings.append(f"The Valuation tab may predate the print: no Valuation Note since {release_day}; "
                            "rerun /model-valuation, then this step.")
    mults = list((before or {}).get("multiples") or [])          # note order, then any the tab adds
    for lab in (aft or {}).get("cells", {}):
        m = re.fullmatch(r"(.+): reward price", lab)
        if m and m.group(1) not in mults:
            mults.append(m.group(1))
    labels = valnote.labels(mults)
    if aft:
        empty = [lab for lab in labels if lab in aft["cells"] and aft["cells"][lab]["value"] is None]
        if empty:
            warnings.append(f"The Valuation tab has no value for {', '.join(empty)}: {EMPTY}")
    return {"before": before, "after": aft, "multiples": mults, "labels": labels}


def irr_now(aft, close, close_ref):
    c = (aft or {}).get("cells", {})
    later, years = c.get(valnote.HORIZON, {}), c.get("IRR: years", {})
    lv, yv = later.get("value"), years.get("value")
    yv = yv if am._n(yv) and yv > 0 else None
    return {"value": am.irr(close, lv, yv) if yv else None, "price": close, "price_ref": close_ref,
            "later": lv if am._n(lv) else None, "later_ref": later.get("ref"), "later_label": later.get("label"),
            "years": yv, "years_ref": years.get("ref")}


def docs(root, ticker, q, warnings):
    n, yy = q.split()
    fy = 2000 + int(yy)

    def newest(pat):
        got = sorted(glob.glob(os.path.join(glob.escape(root), pat)))
        return os.path.relpath(got[-1], root) if got else None
    d = {"transcript": transcript.find(root, ticker, q),
         "release": newest(f"Press Releases/_md/{fy} {n} {ticker} release *.md"),
         "preview": newest(f"Earnings Previews/{ticker} {q} earnings preview *.md")}   # model-earnings-before note.py
    if not d["transcript"]:
        _stop(f"no {q} call transcript at {root}/Earnings Calls/_md/{transcript.name(ticker, q)}.md. Run "
              f"/collect-documents {ticker}, or file the user's copy with: python3 transcript.py ingest --root "
              f"{root!r} --ticker {ticker} --quarter {q!r} --file <transcript.pdf|.md>")
    if not d["release"]:
        warnings.append(f"No {q} earnings release in Press Releases/_md: rerun /collect-documents {ticker}.")
    if not d["preview"]:
        warnings.append(f"No {q} earnings preview note in Earnings Previews: the wrap has no written preview to "
                        "judge (band 1 of the Earnings tab still holds the call).")
    return d


def house(wb):
    """The in-line band: the house 1%, or on a rerun the number the user keeps in band 9 (text ignored)."""
    H = dict(HOUSE)
    ws = wb[et.TAB]
    ws.reset_dimensions()
    for row in ws.iter_rows(max_col=2):
        a = getattr(row[0], "value", None)
        v = row[1].value if len(row) > 1 else None
        if isinstance(a, str) and a.strip() == IN_LINE_LABEL and am._n(v):
            H["in_line"] = v
    return H


def earnings_values(wb, refs):
    """{key: value} of the band 1-8 cells bands 9-15 read (earnings_tab refs: price, expected move, move up / down,
    implied move...), from the values copy: build.py's expected values for its same-tab formulas. None = blank or
    not recalculated (build.py then leaves the cell unchecked and warns)."""
    g = grid(wb[et.TAB])
    out = {}
    for k, ref in refs.items():
        m = re.fullmatch(r"\$?([A-Z]+)\$?(\d+)", ref)
        out[k] = g.get((int(m.group(2)), ci(m.group(1))))
    return out


def history(model, quarter):
    """The 4 newest Call Notes columns before this quarter's, newest first. This quarter's own column (on a rerun) is
    left out: it holds our earlier output or the user's typing, not a source a figure may be copied from."""
    if not hasattr(callnotes, "read"):
        return []
    g = callnotes.read(model)
    return [{"quarter": q, "head": g["head"].get(q), "cells": {t: v for (qq, t), v in g["cells"].items() if qq == q}}
            for q in [x for x in g["order"] if x != quarter][:4]]


def _research(ticker, research):
    if research:
        return research
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "..", "..", "lib"))
    import settings
    return os.path.join(settings.research_dir(), ticker)


def quarter_only(model):
    tab, mm, q, qe = quarter_of(model)
    wb = openpyxl.load_workbook(model, read_only=True, data_only=True)
    if "Px Events" not in wb.sheetnames:
        _stop("the model has no Px Events tab. Run /model-price-history.")
    g = grid(wb["Px Events"])
    wb.close()
    rel, rx = release_and_reaction(g, q)
    return {"quarter": q, "quarter_e": qe, "reaction_day": rx["reaction_day"].isoformat()}


def run_mode(tab, q, work):
    """'rerun' when bands 9-15 were built for this quarter: the Earnings tab holds them under a title (or band 9
    header) naming q, or the written record call_notes_written.json (renamed in Step 9 with after_inputs_written.json,
    once the checked copy replaced the model; keyed by quarter) holds q, as after a preview rerun's --clear-after.
    An after_plan.json alone does not count: a run stopped at Step 7 leaves one behind."""
    a = tab.get("after_start")
    if a is not None and re.search(rf": {re.escape(q)}(\s|\(|$)", str((tab.get("labels") or {}).get(a, ""))):
        return "rerun"
    p = os.path.join(work, "call_notes_written.json")
    return "rerun" if os.path.exists(p) and q in (json.load(open(p)) or {}) else "first"


def run(model, work, ticker, values=None, research=None, forecast_plan=None, today=None):
    os.makedirs(work, exist_ok=True)
    today = today or dt.date.today().isoformat()
    tab, mm, q, qe = quarter_of(model)            # stops before any recalculation
    if values is None:
        import lo
        values = lo.recalc(model, os.path.join(work, "values"))
    wb = openpyxl.load_workbook(values, read_only=True, data_only=True)
    for t, skill in REQUIRED.items():
        if t not in wb.sheetnames:
            _stop(f"the model has no {t} tab. Run /{skill} first.")
    g = {t: grid(wb[t]) for t in REQUIRED}
    H = house(wb)
    ev = earnings_values(wb, tab["refs"])
    wb.close()
    mm = ModMap(values)                           # the values copy, as the sibling reads it
    warnings = []
    rel, rx = release_and_reaction(g["Px Events"], q)
    P = rates.px_data(g["Px Data"], ticker)
    mv = move(g["Px Events"], P, ticker, rel, rx, work, today, warnings)
    for k, what in (("day", "the day move (Px Events)"), ("idio", "the idio move (Px Events)"),
                    ("daily_sigma", "the daily sigma (Px Data returns)")):
        if mv[k] is None:
            warnings.append(f"No value for {what}: {EMPTY}")
    root = _research(ticker, research)
    dd = docs(root, ticker, q, warnings)
    upd, state = _state(model, q)
    if state is None:
        warnings.append(f"No model-update state.json for {q}: no line is flagged as a placeholder.")
    fz = frozen_rows(tab, mm, g["MOD"], q, state, H["in_line"], warnings)
    plan_path = forecast_plan or os.path.join(os.path.dirname(os.path.abspath(model)), "_model_work", "forecast",
                                              "forecast_plan.json")
    drv = drivers(mm, plan_path, warnings)
    sp = os.path.join(upd, "values.json")
    snap = json.load(open(sp)).get("MOD") if os.path.exists(sp) else None
    est = estimates(mm, g["MOD"], q, fz, drv, snap, sp, warnings)
    val = valuation(root, ticker, mv["release_day"], mv["reaction_day"], values, warnings)
    lc = rates.last_close(P)
    if (dt.date.fromisoformat(today) - P["rows"][-1]["date"]).days > STALE_PX_DAYS:
        warnings.append(f"Px Data ends {P['rows'][-1]['date']}; rerun /model-price-history for today's price (the "
                        "IRR now uses that last close).")
    close_ref = f"'Px Data'!${P['cols']['close']}${lc['row']}"
    ir = irr_now(val["after"], lc["close"], close_ref)
    ir["price_date"] = lc["date"].isoformat()
    fade = am.fade_table(lc["close"], ir["later"], ir["years"]) if ir["value"] is not None else []
    mode = run_mode(tab, q, work)
    ctx = {"ticker": ticker, "today": today, "values": os.path.abspath(values), "research": root,
           "quarter": q, "quarter_e": qe, "fy": mm.fy_of(q), "mode": mode, "drift_ready": mv["drift"] is not None,
           "frozen": {"quarter": tab["frozen"]["quarter"], "date": tab["frozen"]["date"], "fy": tab["frozen"]["fy"],
                      "rows": fz},
           "earnings_refs": tab["refs"], "earnings_values": ev, "earnings_start": tab["start"],
           "after_start": tab["after_start"],
           "move": mv, "estimates": est, "valuation": val, "irr_now": ir, "fade": fade,
           "consensus": consensus(model, values, q),
           "latest_close": {"value": lc["close"], "date": lc["date"].isoformat(), "ref": close_ref},
           "docs": dd, "topics": callnotes.topics([d["name"] for d in drv]),
           "drivers": [{"name": d["name"], "key": d["key"], "row": d["row"]} for d in drv],
           "history": history(model, q), "mod_keys": [k for _, k, _ in mm.lines], "mod_periods": dict(mm.labels),
           "house": H,
           "update": {"dir": upd, "snapshot": sp if snap is not None else None, "state": state},
           "warnings": warnings}
    json.dump(ctx, open(os.path.join(work, "context.json"), "w"), indent=1, default=str)
    open(os.path.join(work, "context.md"), "w").write(_md(ctx))
    return ctx


# ---------------------------------------------------------------- context.md
def _f(v, kind="num"):
    if v is None:
        return "?"
    if kind == "pct":
        return f"{v * 100:.1f}%"
    return f"{v:,.2f}" if isinstance(v, (int, float)) else str(v)


def _c(s):
    return str(s).replace("|", "\\|")      # a MOD key holds " | ": escaped so the Markdown table keeps its columns


def _md(c):
    m, v = c["move"], c["valuation"]
    L = [f"# {c['ticker']} after the print: context ({c['today']})", "",
         f"Quarter reported: {c['quarter']} (fiscal year {c['fy']}); frozen {c['frozen']['date']} as "
         f"{c['frozen']['quarter']}", f"Run: {c['mode']} (drift ready: {c['drift_ready']})",
         f"In-line band: ±{_f(c['house']['in_line'], 'pct')}", "", "## Warnings"]
    L += [f"- {w}" for w in c["warnings"]] or ["- none"]
    L += ["", "## Actual vs frozen (surprise signed: a smaller cost is a beat)", "",
          "| Line | Frozen | Actual | Surprise | Result |", "|---|---|---|---|---|"]
    for r in c["frozen"]["rows"]:
        tail = "estimate, awaiting 10-Q | placeholder" if r["placeholder"] else \
            f"{_f(r['surprise'], 'pct')} | {r['result'] or '?'}"
        L.append(f"| {_c(r['label'])} | {_f(r['frozen'])} | {_f(r['actual'])} | {tail} |")
    L += ["", "## The move", f"- Release {m['release_day']}, reaction day {m['reaction_day']}",
          f"- Day move {_f(m['day'], 'pct')}, idio {_f(m['idio'], 'pct')}, daily sigma {_f(m['daily_sigma'], 'pct')}"
          f" ({m['sigma_n']} days before the print), {_f(m['sigmas'])} sigmas",
          f"- Gap at the open {_f(m['gap'], 'pct')}, open to close {_f(m['open_to_close'], 'pct')} (Yahoo)",
          f"- Run-up T-8 to T-1 {_f(m['run_up'], 'pct')}; drift to T+7 "
          f"{_f(m['drift'], 'pct') if m['drift'] is not None else 'fills on the T+7 rerun'}",
          "", "## Estimates (before: model-update's pre-print snapshot or band 7; now: MOD)", "",
          "| Line | Period | Before | Now | Change |", "|---|---|---|---|---|"]
    for e in c["estimates"]:
        for s in ("fy", "fy1"):
            x = e[s]
            if x:
                L.append(f"| {e['name']} ({_c(e['label'])}) | {x['period']} | {_f(x['before'])} | {_f(x['now'])} | "
                         f"{_f(x['change'], 'pct')} |")
    b, a = v["before"] or {}, v["after"] or {}
    L += ["", f"## Valuation (before: {b.get('path') or '?'}; after: the Valuation tab, "
              f"{'note ' + a['fresh_note'] if a.get('fresh_note') else 'no note since the print'})", "",
          "| Label | Before | After |", "|---|---|---|"]
    for lab in v["labels"]:
        bv = (b.get("values") or {}).get(lab, {}).get("value")
        av = (a.get("cells") or {}).get(lab, {}).get("value")
        k = "pct" if lab == "IRR" else "num"
        L.append(f"| {lab} | {_f(bv, k)} | {_f(av, k)} |")
    i = c["irr_now"]
    L += ["", f"## IRR at the latest close ({_f(i['price'])} on {i['price_date']}) on the after "
              f"{_f(i['years'])}-year price {_f(i['later'])}: {_f(i['value'], 'pct')}", "",
          "| Price cut | Price | IRR |", "|---|---|---|"]
    L += [f"| {_f(x['cut'], 'pct')} | {_f(x['price'])} | {_f(x['irr'], 'pct')} |" for x in c["fade"]] or ["| ? | | |"]
    L += ["", "## Documents to read (paths relative to the research folder; cite file.md:line)",
          f"Research folder: {c['research']}"]
    L += [f"- {k}: {p or 'not found'}" for k, p in c["docs"].items()]
    L += ["", "## Call Notes topics (answer each)"] + [f"- {t}" for t in c["topics"]]
    L += ["", "## Call Notes history (newest first)"]
    L += [f"- {h['quarter']}: " + "; ".join(f"{t}: {x}" for t, x in h["cells"].items()) for h in c["history"]] \
        or ["- none yet"]
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--model", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--ticker", required=True)
    ap.add_argument("--values")
    ap.add_argument("--research")
    ap.add_argument("--forecast-plan")
    ap.add_argument("--today")
    ap.add_argument("--quarter-only", action="store_true")
    a = ap.parse_args()
    if a.quarter_only:
        print(json.dumps(quarter_only(a.model)))
        return
    c = run(a.model, a.work, a.ticker.upper(), a.values, a.research, a.forecast_plan, a.today)
    print(json.dumps({"quarter": c["quarter"], "mode": c["mode"], "drift_ready": c["drift_ready"],
                      "move": {k: c["move"][k] for k in ("reaction_day", "day", "idio", "sigmas", "drift_due")},
                      "docs": c["docs"], "warnings": c["warnings"]}, indent=1, default=str))


if __name__ == "__main__":
    main()
