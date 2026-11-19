# skills/model-earnings-after/scripts/build.py
"""Writes bands 9-15 ("AFTER THE PRINT") under band 8 of the Earnings tab and the Call Notes tab into a copy of the
user's model by raw-XML editing. Bands 1-8 stay byte for byte (earnings_tab.splice) and every other part of the
workbook stays byte-identical (checked here: the build stops if anything else changed). Yellow = the agent's call,
the user's to change (blue on yellow, a note with the agent's value, anchor and reason, the reason in column D);
blue = typed from a source (a note names it); black = formulas; green = links to other tabs.

A rerun keeps every yellow cell the user changed (W/after_inputs_written.json records what the last build wrote);
with --rebuild and no band 9 on the tab (a /model-earnings-before rerun cleared it), the values the record marks as
the user's are put back. Call Notes: callnotes.merge keeps older quarters and the user's cells
(W/call_notes_written.json).

Writes W/layout.json (each checked cell's expected value: aftermath's math on context.json and the resolved inputs;
None = #N/A expected) for verify.py and note.py, and W/after_inputs_written.next.json and
W/call_notes_written.next.json (the SKILL renames them once the copy replaces the model).

usage: python3 build.py --model M --work W --ticker T --out OUT.xlsx [--rebuild]"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))   # run with python3 -I
import aftermath as am  # noqa: E402
import callnotes  # noqa: E402
import earnings_tab as et  # noqa: E402
import valnote  # noqa: E402
from context import HOUSE, IN_LINE_LABEL  # noqa: E402
from tabkit import BLACK, GEN, RED, W, _n, changed_parts, resolve_values, tab_parts  # noqa: E402
from xlsx import Package, Styles, colnum  # noqa: E402

SKILL = "model-earnings-after"
TAB = et.TAB
PCT, MULT, MONEY, NUM, INT, MILL = "0.0%", '0.0"x"', "$#,##0.00", "0.00", "0", "#,##0.0"
PLACEHOLDER = "estimate, awaiting 10-Q"
T7_FILL = "fills on the T+7 rerun"
T7_ASK = "asked on the T+7 rerun"
SFOT = ("surprise", "fundamentals", "outlook", "tone")
REACT = (("call", "React: the call"), ("pattern", "React: the pattern"),
         ("wrong_if", "React: what would prove it wrong"), ("watch", "React: what to watch through T+7"))
PLAYED = "Played out by T+7?"
CHECKPOINT = "Checkpoint: is the thesis on track? (green / yellow / red)"
TARGET = "Blended reward price"          # the blended target band 13's "target change minus the day's move" reads


def _stop(msg):
    raise SystemExit(f"{SKILL} stopped: {msg}")


def _uniq(label, seen):
    """label, or label (2), (3)... when it is already in seen (column-A labels are unique within bands 9-15)."""
    out, k = label, 2
    while out in seen:
        out, k = f"{label} ({k})", k + 1
    seen.add(out)
    return out


def guidance_labels(plan):
    seen = set()
    return [_uniq(f"Guidance: {g.get('item')}", seen) for g in plan.get("guidance") or []]


def played_asked(ctx):
    return ctx.get("mode") == "rerun" and bool(ctx.get("drift_ready"))


def agent_values(plan, ctx):
    """({input label: the agent's value}, {input label: its column}) for bands 9-15."""
    v = {IN_LINE_LABEL: HOUSE["in_line"]}
    for k in SFOT:
        v[f"SFOT: {k}"] = plan["sfot"][k]["value"]
    cols = {lab: "B" for lab in v}
    for lab, g in zip(guidance_labels(plan), plan.get("guidance") or []):
        v[lab], cols[lab] = g["change"], "E"
    v[CHECKPOINT] = plan["checkpoint"]["value"]
    for k, lab in REACT:
        v[lab] = plan["react"][k]
    if played_asked(ctx):
        v[PLAYED] = (plan.get("played_out") or {}).get("value") or "?"
    return v, {lab: cols.get(lab, "B") for lab in v}


def read_inputs(path, cols, start):
    """{label: value} of the input cells on the tab now (band 9 down), by column-A label, formulas as written."""
    import openpyxl
    wb = openpyxl.load_workbook(path, read_only=True)
    ws = wb[TAB]
    ws.reset_dimensions()
    out = {}
    for row in ws.iter_rows(min_row=start, max_col=6):
        a = getattr(row[0], "value", None) if row else None
        if not isinstance(a, str) or a.strip() not in cols:
            continue
        k = colnum(cols[a.strip()]) - 1
        v = getattr(row[k], "value", None) if len(row) > k else None
        if v is not None:
            out[a.strip()] = v
    wb.close()
    return out


def _note(x):
    a = f"anchor {x.get('anchor', 'judgment')}"
    return f"Agent: {x.get('value')} | {a} | {x.get('reason', '')}"


def mod_values(values, keys, years, periods):
    """{(key, year): value} of MOD's fiscal-year cells in the values copy (None when blank or not recalculated)."""
    import openpyxl
    from modmap import ModMap
    mm = ModMap(values)
    rows = {k: mm.keys.get(k) for k in keys}
    wb = openpyxl.load_workbook(values, read_only=True, data_only=True)
    ws = wb["MOD"]
    ws.reset_dimensions()
    g = {(c.row, c.column): c.value for row in ws.iter_rows() for c in row if getattr(c, "value", None) is not None}
    wb.close()
    out = {}
    for k, r in rows.items():
        for y in years:
            c = year_col(periods, y)
            v = g.get((r, colnum(c))) if r and c else None
            out[(k, y)] = v if _n(v) else None
    return rows, out


def year_col(periods, y):
    return periods.get(str(y)) or periods.get(f"{y}E")


def lay_out(w, ctx, plan, used, users, unverified, ticker, mod):
    """Every cell of bands 9-15, from ctx['earnings_start'] down. Returns (refs {label: "$B$n"}, unchecked labels,
    placeholder labels, warnings)."""
    R, unchecked, placeholders, warn, seen = {}, [], [], [], set()
    ev, eref = ctx.get("earnings_values") or {}, ctx["earnings_refs"]
    r = ctx["earnings_start"]
    q = ctx["quarter"]

    def band(t):
        nonlocal r
        w.text(f"A{r}", t, b=True, sz=12)
        r += 1

    def put(label, unique=True):
        nonlocal r
        lab = _uniq(label, seen) if unique else label
        w.text(f"A{r}", lab)
        R.setdefault(lab, f"$B${r}")
        r += 1
        return r - 1

    def inp(label, fmt, x, ukey, col="B", reason=None):
        if label in seen:
            raise SystemExit(f"{SKILL}: the input label {label!r} appears twice in column A (a bug in build.py).")
        rr = put(label)
        note = (f"You typed {used[label]}. " if label in users else "") + _note(x)
        w.input_(f"{col}{rr}", label, used[label], fmt, note)
        bad = ukey in unverified
        why = reason if reason is not None else str(x.get("reason", ""))
        w.text(f"D{rr}", ("UNVERIFIED: " if bad else "") + why, color=RED if bad else BLACK)
        R[label] = f"${col}${rr}"
        return rr

    def q_(ref):
        w.text(ref, "?", i=True)

    def check_or_skip(label, v):
        if v is None:
            unchecked.append(label)
        return v is not None

    def same_tab(cell, key, label, fmt):
        """A formula onto a band 1-8 cell; '?' when the preview has text there or no such row. Returns the ref
        (or None) and its value."""
        ref, v = eref.get(key), ev.get(key)
        if not ref or isinstance(v, str):
            q_(cell)
            return None, None
        w.formula(cell, ref, fmt, v, check=check_or_skip(label, v))
        return cell, v

    # title and 9. actual vs frozen
    w.text(f"A{r}", f"{ticker} after the print: {q} (model-earnings-after, {ctx['today']})", b=True, sz=12)
    r += 1
    fz = ctx["frozen"]
    band(f"9. ACTUAL VS FROZEN: {q} against the forecast frozen {fz['date']} (section 13.6)")
    inp(IN_LINE_LABEL, PCT, {"value": HOUSE["in_line"], "anchor": "house",
                             "reason": "House default: within this of the frozen line is 'in line'. Change it and "
                                       "column F follows."}, "house.in_line")
    BAND = R[IN_LINE_LABEL]
    band_v = used[IN_LINE_LABEL]
    if not _n(band_v):
        warn.append(f"{IN_LINE_LABEL!r} holds {band_v!r}, not a number: band 9's results are not checked. Type a "
                    "number there and rerun.")
    x = put("Line (band 7's frozen forecast against MOD's actual)")
    for col, t in zip("BCDEF", ("Frozen", "Actual", "Difference", "% (signed: a smaller cost is a beat)", "Result")):
        w.text(f"{col}{x}", t, b=True)
    for f in fz["rows"]:
        if f["frozen"] is None and f["actual"] is None:
            continue
        y = put(f["label"])
        lab = w.col_a[f"A{y}"]
        fmt = MONEY if "eps" in f["label"].lower() else MILL
        w.formula(f"B{y}", f"IF(ISNUMBER({f['frozen_ref']}),{f['frozen_ref']},NA())", fmt, f["frozen"])
        if f["mod_ref"]:
            w.link(f"C{y}", f["mod_ref"], fmt, f["actual"], check=check_or_skip(lab, f["actual"]))
        else:
            q_(f"C{y}")
        if f["placeholder"]:
            w.text(f"F{y}", PLACEHOLDER, i=True)
            placeholders.append(lab)
            continue
        ok = f["mod_ref"] is not None and f["actual"] is not None
        s = am.surprise(f["actual"], f["frozen"])
        diff = f["actual"] - f["frozen"] if _n(f["actual"]) and _n(f["frozen"]) else None
        w.formula(f"D{y}", f"IFERROR(C{y}-B{y},NA())", fmt, diff, check=ok)
        w.formula(f"E{y}", f"IFERROR((C{y}-B{y})/ABS(B{y}),NA())", PCT, s, check=ok)
        w.formula(f"F{y}", f'IF(ISNUMBER(E{y}),IF(ABS(E{y})<={BAND},"in line",IF(E{y}>0,"beat","miss")),"?")', GEN,
                  am.result(s, band_v) or "?", check=ok and _n(band_v))

    # 10. SFOT
    r += 1
    band("10. SFOT (section 13.6: surprise, fundamentals, outlook, tone)")
    for k in SFOT:
        x = plan["sfot"][k]
        inp(f"SFOT: {k}", GEN, x, f"sfot.{k}", reason=f"{x.get('reason', '')} ({x.get('anchor')})")

    # 11. the move
    r += 1
    band("11. THE MOVE (section 13.6-13.7)")
    mv = ctx["move"]
    x = put("Reaction day")
    w.typed_text(f"B{x}", mv["reaction_day"], f"Px Events {mv['reaction_ref']}: the first trading day of the "
                                              f"reaction to the release on {mv['release_day']}.")
    x = put("Day move (Px Events)")
    w.link(f"B{x}", mv["day_ref"], PCT, mv["day"], check=check_or_skip("Day move (Px Events)", mv["day"]))
    DAY = f"$B${x}"
    x = put("Idio move (Px Events)")
    w.link(f"B{x}", mv["idio_ref"], PCT, mv["idio"], check=check_or_skip("Idio move (Px Events)", mv["idio"]))
    lab = f"Daily sigma, {mv['sigma_n']} trading days before the print (Px Data)"
    x = put(lab)
    w.formula(f"B{x}", mv["sigma_formula"], PCT, mv["daily_sigma"], check=check_or_skip(lab, mv["daily_sigma"]))
    SIG = f"$B${x}"
    x = put("Move in daily sigmas")
    w.formula(f"B{x}", f"IFERROR({DAY}/{SIG},NA())", NUM, am.sigmas(mv["day"], mv["daily_sigma"]),
              check=mv["day"] is not None and mv["daily_sigma"] is not None)
    for key, lab, how in (("gap", "Gap at the open (Yahoo)", "open over the previous close"),
                          ("open_to_close", "Open to close (Yahoo)", "close over the open")):
        x = put(lab)
        if _n(mv[key]):
            w.typed(f"B{x}", mv[key], PCT, f"{mv['yahoo_source']}: reaction-day {how} (open {mv['open']}, close "
                                           f"{mv['close']}, previous close {mv['prev_close']}).")
        else:
            q_(f"B{x}")
            w.text(f"D{x}", "Yahoo had no reaction-day bars for this (see the warnings).", i=True)
    x = put("Expected move (preview, band 1)")
    EXP, exp_v = same_tab(f"B{x}", "expected_move", "Expected move (preview, band 1)", PCT)
    x = put("Day move minus expected (|day move| - expected)")
    if EXP:
        want = abs(mv["day"]) - exp_v if _n(mv["day"]) and _n(exp_v) else None
        w.formula(f"B{x}", f"IFERROR(ABS({DAY})-{EXP},NA())", PCT, want,
                  check=check_or_skip("Day move minus expected (|day move| - expected)", want))
    else:
        q_(f"B{x}")
    x = put("Options-implied move (preview, band 5)")
    if not same_tab(f"B{x}", "implied", "Options-implied move (preview, band 5)", PCT)[0]:
        w.text(f"D{x}", "The preview had no implied move.", i=True)
    for key, lab in (("up", "Preview's upside move (band 2)"), ("down", "Preview's downside move (band 2)")):
        same_tab(f"B{put(lab)}", key, lab, PCT)
    x = put("Run-up, T-8 to T-1 (Px Data)")
    if mv["run_up_formula"]:
        w.formula(f"B{x}", mv["run_up_formula"], PCT, mv["run_up"])
    else:
        q_(f"B{x}")
    x = put("Drift, reaction-day close to T+7 (Px Data)")
    if mv["drift_formula"]:
        w.formula(f"B{x}", mv["drift_formula"], PCT, mv["drift"])
    else:
        w.text(f"B{x}", T7_FILL, i=True)

    # 12. estimates
    r += 1
    band("12. ESTIMATES (before the print: model-update's snapshot; now: MOD)")
    est = ctx["estimates"]
    if est:
        x = put("Estimate")
        for cols, slot in (("BCD", "fy"), ("EFG", "fy1")):
            p = next((e[slot]["period"] for e in est if e.get(slot)), None)
            if p:
                for c, t in zip(cols, (f"FY{p} before", "now", "change %")):
                    w.text(f"{c}{x}", t, b=True)
    else:
        put("No estimate lines found on MOD")
    for e in est:
        y = put(f"Estimate: {e['name']}")
        lab = w.col_a[f"A{y}"]
        fmt = MONEY if "eps" in e["name"].lower() else MILL
        for cols, slot in (("BCD", "fy"), ("EFG", "fy1")):
            s = e.get(slot)
            if not s:
                continue
            b, c, d = cols
            src = s.get("before_src") or {}
            if _n(s["before"]):
                note = (f"model-update's pre-print snapshot {src.get('path')}, cell {src.get('ref')}."
                        if src.get("kind") == "snapshot" else f"Band 7's frozen forecast, cell {src.get('ref')}.")
                w.typed(f"{b}{y}", s["before"], fmt, note)
            else:
                q_(f"{b}{y}")
            w.link(f"{c}{y}", s["ref"], fmt, s["now"], check=check_or_skip(f"{lab} ({s['period']})", s["now"]))
            if _n(s["before"]):
                w.formula(f"{d}{y}", f"IFERROR(IF({b}{y}>0,{c}{y}/{b}{y}-1,NA()),NA())", PCT,
                          am.growth(s["now"], s["before"]), check=s["now"] is not None)
            else:
                q_(f"{d}{y}")

    # 13. valuation
    r += 1
    val = ctx["valuation"]
    before, after = val.get("before") or {}, val.get("after") or {}
    vb, va = before.get("values") or {}, after.get("cells") or {}
    src = before.get("path") or "no Valuation Note before the print"
    band(f"13. VALUATION (before: {src}; after: the Valuation tab)")
    x = put("Valuation line")
    for c, t in zip("BCD", ("Before", "After", "Change")):
        w.text(f"{c}{x}", t, b=True)
    rows13 = {}
    for lab in val["labels"]:
        diff = lab == "IRR" or lab.endswith("reward / risk")
        fmt = PCT if lab == "IRR" else MULT if lab.endswith("reward / risk") else INT if lab == "IRR: years" else MONEY
        y = put(lab)
        bx = vb.get(lab) or {}
        bv = bx.get("value")
        if _n(bv):
            w.typed(f"B{y}", bv, fmt, f"{before['path']}:{bx['line']}")
        else:
            q_(f"B{y}")
        ax = va.get(lab)
        av = (ax or {}).get("value")
        if ax and ax.get("ref"):
            w.link(f"C{y}", ax["ref"], fmt, av, check=check_or_skip(f"{lab} (after)", av))
        else:
            q_(f"C{y}")
        rows13[lab] = (y, _n(bv), bool(ax and ax.get("ref")), bv, av if _n(av) else None)
        if _n(bv) and ax and ax.get("ref"):
            if diff:
                f_, want, dfmt = f"IFERROR(C{y}-B{y},NA())", (av - bv if _n(av) else None), fmt
            else:
                f_, want, dfmt = f"IFERROR(C{y}/B{y}-1,NA())", (av / bv - 1 if _n(av) and bv else None), PCT
            w.formula(f"D{y}", f_, dfmt, want, check=_n(av))
        else:
            q_(f"D{y}")
    lc = ctx["latest_close"]
    lab = f"Latest close ({lc['date']}, Px Data)"
    x = put(lab)
    w.link(f"B{x}", lc["ref"], MONEY, lc["value"], check=check_or_skip(lab, lc["value"]))
    CLOSE = f"$B${x}"
    ir = ctx["irr_now"]
    hz, yr = rows13.get(valnote.HORIZON), rows13.get("IRR: years")
    x = put("IRR at the latest close on the after horizon price (section 13.7)")
    fade_ok = bool(hz and yr and hz[2] and yr[2])
    if fade_ok:
        P3, YRS = f"$C${hz[0]}", f"$C${yr[0]}"
        w.formula(f"B{x}", f"IFERROR(IF(AND({P3}>0,{CLOSE}>0,{YRS}>0),({P3}/{CLOSE})^(1/{YRS})-1,NA()),NA())", PCT,
                  ir["value"], check=hz[4] is not None and yr[4] is not None)
    else:
        q_(f"B{x}")
    x = put("Target change minus the day's move (positive = the stock under-reacted; section 13.6)")
    tg = rows13.get(TARGET)
    if tg and tg[1] and tg[2]:
        tc = tg[4] / tg[3] - 1 if tg[4] is not None and tg[3] else None
        w.formula(f"B{x}", f"IFERROR(($C${tg[0]}/$B${tg[0]}-1)-{DAY},NA())", PCT, am.gap(tc, mv["day"]),
                  check=tg[4] is not None and mv["day"] is not None)
    else:
        q_(f"B{x}")
    x = put("Fade table: if the stock gives back the move (section 13.7)")
    if fade_ok and ctx["fade"]:
        for c, t in zip("BCD", ("Price change", "Price", "3-year IRR")):
            w.text(f"{c}{x}", t, b=True)
        ok = hz[4] is not None and yr[4] is not None and lc["value"] is not None
        for fd in ctx["fade"]:
            y = put(f"Fade: price {fd['cut']:+.0%}")
            w.typed(f"B{y}", fd["cut"], PCT, "Chapter 13.7's fade table: the price change tried from the latest close.")
            w.formula(f"C{y}", f"{CLOSE}*(1+B{y})", MONEY, fd["price"], check=lc["value"] is not None)
            w.formula(f"D{y}", f"IFERROR(IF(AND({P3}>0,C{y}>0,{YRS}>0),({P3}/C{y})^(1/{YRS})-1,NA()),NA())", PCT,
                      fd["irr"], check=ok)
    else:
        q_(f"B{x}")

    # 14. guidance and checkpoint
    r += 1
    band("14. GUIDANCE AND CHECKPOINT (section 13.7)")
    gl = guidance_labels(plan)
    if gl:
        x = put("Guidance item")
        for c, t in zip("BCDE", ("Before", "Now", "Source", "Change (yours to change)")):
            w.text(f"{c}{x}", t, b=True)
    else:
        put("No guidance items in the plan")
    for i, (lab, g) in enumerate(zip(gl, plan.get("guidance") or [])):
        y = inp(lab, GEN, {"value": g["change"], "anchor": g.get("anchor"), "reason": g.get("quote", "")},
                f"guidance[{i}]", col="E", reason=f"\"{g.get('quote', '')}\" ({g.get('anchor')})")
        w.typed_text(f"B{y}", g["before"], f"{g.get('anchor')}: before this call.")
        w.typed_text(f"C{y}", g["now"], f"{g.get('anchor')}: \"{g.get('quote', '')}\"")
    lt = plan.get("lt_target")
    if lt:
        fy0 = int(str(ctx["fy"])[:4])
        ratio = bool(lt.get("den"))
        fmt = PCT if ratio else MILL
        per = ctx["mod_periods"]
        rows, vals = mod
        y = put(f"Long-term target: {lt.get('metric')}")
        w.typed(f"B{y}", lt["target"], fmt, f"{lt.get('anchor')}: \"{lt.get('quote', '')}\"")
        T = f"$B${y}"
        y = put("Long-term target: year")
        w.typed(f"B{y}", lt["year"], INT, f"{lt.get('anchor')}: \"{lt.get('quote', '')}\"")
        Y = f"$B${y}"

        def expr(yy):
            c, n, d = year_col(per, yy), rows.get(lt["num"]), rows.get(lt.get("den"))
            if not c or not n or (ratio and not d):
                return None, None
            nv = vals.get((lt["num"], yy))
            if ratio:
                dv = vals.get((lt["den"], yy))
                v = nv / dv if _n(nv) and _n(dv) and dv else None
                return f"'MOD'!${c}${n}/'MOD'!${c}${d}", v
            return f"'MOD'!${c}${n}", nv

        e0, v0 = expr(fy0)
        e3, v3 = expr(fy0 - am.TREND_YEARS)
        slope = am.trend({fy0: v0, fy0 - am.TREND_YEARS: v3}, fy0)
        pace = am.lt_pace(v0, fy0, slope, lt["target"], lt["year"])
        y = put(f"Long-term target: latest ({ctx['fy']}, MOD)")
        LATEST = f"$B${y}"
        if e0:
            w.formula(f"B{y}", f"IFERROR({e0},NA())", fmt, v0, check=check_or_skip(w.col_a[f"A{y}"], v0))
        else:
            q_(f"B{y}")
        y = put(f"Long-term target: trend a year ({fy0 - am.TREND_YEARS} to {fy0})")
        TREND = f"$B${y}"
        if e0 and e3:
            w.formula(f"B{y}", f"IFERROR(({LATEST}-{e3})/{am.TREND_YEARS},NA())", fmt, slope,
                      check=v0 is not None and v3 is not None)
        else:
            q_(f"B{y}")
        ok = v0 is not None and v3 is not None
        yrs = f"({Y}-{fy0})"
        y = put("Long-term target: run rate at the target year on that trend")
        RUN = f"$B${y}"
        w.formula(f"B{y}", f"IFERROR(IF({yrs}>0,{LATEST}+{TREND}*{yrs},NA()),NA())", fmt, pace["run_rate"], check=ok)
        y = put("Long-term target: needed a year")
        w.formula(f"B{y}", f"IFERROR(IF({yrs}>0,({T}-{LATEST})/{yrs},NA()),NA())", fmt, pace["needed_per_year"],
                  check=v0 is not None)
        y = put("Long-term target: status")
        w.formula(f"B{y}", f'IF(AND(ISNUMBER({RUN}),ISNUMBER({T}),ISNUMBER({LATEST})),IF({T}>={LATEST},'
                           f'IF({RUN}>={T},"on pace","behind pace"),IF({RUN}<={T},"on pace","behind pace")),"?")',
                  GEN, pace["status"], check=ok)
    inp(CHECKPOINT, GEN, plan["checkpoint"], "checkpoint")

    # 15. react
    r += 1
    band("15. REACT (section 13.7: predict, then react)")
    rc = plan["react"]
    for k, lab in REACT:
        reason = rc.get("reason", "") if k in ("call", "pattern") else \
            "The agent's; yours to change." if k == "wrong_if" else "The agent's; the T+7 rerun checks it."
        inp(lab, GEN, {"value": rc[k], "reason": reason}, "react", reason=reason)
    if played_asked(ctx):
        inp(PLAYED, GEN, plan.get("played_out") or {}, "played_out")
    else:
        w.text(f"B{put(PLAYED)}", T7_ASK, i=True)
    for c in plan.get("catalysts") or []:
        w.text(f"B{put('Catalyst: ' + str(c.get('when') or 'no date given'))}", c.get("text", ""))
    for i, c in enumerate(plan.get("controversies") or [], start=1):
        w.text(f"B{put(f'Controversy {i}')}", c)
    if unchecked:
        warn.append("Not checked by verify (no value in the values copy, likely not recalculated): "
                    + "; ".join(unchecked) + ".")
    return R, unchecked, placeholders, warn


def build(model, work, ticker, out, rebuild=False):
    if os.path.abspath(out) == os.path.abspath(model):
        raise SystemExit(f"{SKILL}: --out must be a copy, not the model itself.")
    ctx = json.load(open(os.path.join(work, "context.json")))
    plan = json.load(open(os.path.join(work, "after_plan.json")))

    def load(n):
        p = os.path.join(work, n)
        return json.load(open(p)) if os.path.exists(p) else None

    written, cn_written = load("after_inputs_written.json"), load("call_notes_written.json")
    unverified = set(load("unverified.json") or [])
    tab = et.read(model)
    if tab is None or not tab["frozen"]:
        _stop("the Earnings tab or its band 7 is gone. Run /model-earnings-before, then this skill.")
    if tab["start"] != ctx["earnings_start"]:
        _stop(f"bands 9-15 would start at row {tab['start']}, but context.json says {ctx['earnings_start']}: the "
              "Earnings tab changed since context.py ran. Rerun context.py, then build.py.")
    warnings = list(ctx.get("warnings") or [])
    new, cols = agent_values(plan, ctx)
    if tab["after_start"] is not None:
        existing = read_inputs(model, cols, tab["after_start"])
        if written is None:
            warnings.append("There is no after_inputs_written.json (the record of what the last build wrote), so "
                            "every yellow cell that differs from the agent's suggestion is treated as yours.")
    elif rebuild and written:
        existing = {lab: rec["value"] for lab, rec in written.items() if rec.get("user") and lab in new}
    else:
        existing = None
    used, users = resolve_values(existing, written, new)

    lt = plan.get("lt_target")
    mod = ({}, {})
    if lt:
        fy0 = int(str(ctx["fy"])[:4])
        mod = mod_values(ctx["values"], [k for k in (lt.get("num"), lt.get("den")) if k],
                         [fy0, fy0 - am.TREND_YEARS], ctx["mod_periods"])

    pkg = Package(model)
    st = Styles(pkg.text("xl/styles.xml"))
    old_parts = tab_parts(pkg, TAB) | tab_parts(pkg, callnotes.TAB)
    w = W(st, users)
    R, unchecked, placeholders, warn = lay_out(w, ctx, plan, used, users, unverified, ticker, mod)
    warnings += warn
    a_texts = list(w.col_a.values())
    dup = sorted({t for t in a_texts if a_texts.count(t) > 1})
    if dup:
        raise SystemExit(f"{SKILL}: column-A labels repeat in bands 9-15: {dup} (a bug in build.py).")
    part = et.part(pkg)
    et.splice(pkg, part, tab["start"], w.sh, w.notes, tab["after_start"])

    old_cn = callnotes.read(model)
    head = {"date": ctx["move"]["release_day"], "file": ctx["docs"]["transcript"]}
    grid, cn_users = callnotes.merge(old_cn, ctx["quarter"], head, plan.get("call_notes") or {}, ctx["topics"],
                                     cn_written)
    callnotes.write(pkg, st, grid, plan.get("call_notes") or {}, ticker)
    if old_cn["dropped"]:
        warnings.append("Call Notes text outside the quarter columns and topic rows was dropped by the rebuild: "
                        + "; ".join(f"{d['ref']} {d['text']!r}" for d in old_cn["dropped"]) + ".")
    if grid["renamed_or_retired"]:
        warnings.append("Call Notes topics no longer asked this quarter (renamed or retired; older columns keep "
                        "them): " + ", ".join(grid["renamed_or_retired"]) + ".")
    if cn_users:
        warnings.append("Call Notes cells you edited in this quarter's column were kept: "
                        + ", ".join(t for _, t in sorted(cn_users)) + ".")
    if users:
        warnings.append("Yellow cells you changed were kept: " + ", ".join(sorted(users)) + ".")

    pkg.put("xl/styles.xml", st.render())
    pkg.finish()
    pkg.save(out)
    import notebox
    notebox.fix(out, out, since=model)
    p2 = Package(out)
    bad = changed_parts(model, out, old_parts | tab_parts(p2, TAB) | tab_parts(p2, callnotes.TAB) | {part})
    if bad:
        os.remove(out)
        raise SystemExit(f"{SKILL}: the build changed parts it must not touch: " + ", ".join(bad))
    json.dump({"expected": w.expected, "kinds": w.kinds, "fmt": w.fmt, "refs": R, "inputs": w.inputs, "used": used,
               "users": sorted(users), "unchecked": unchecked, "placeholders": placeholders, "warnings": warnings,
               "start": tab["start"], "call_notes_users": sorted(t for _, t in cn_users)},
              open(os.path.join(work, "layout.json"), "w"), indent=0, default=str)
    json.dump({lab: {"value": v, "user": lab in users} for lab, v in used.items()},
              open(os.path.join(work, "after_inputs_written.next.json"), "w"), indent=1, default=str)
    json.dump(callnotes.written(grid, ctx["quarter"], cn_users, cn_written),
              open(os.path.join(work, "call_notes_written.next.json"), "w"), indent=1, default=str)
    return {"tab": TAB, "users_kept": sorted(users), "call_notes_users_kept": sorted(t for _, t in cn_users),
            "rows": [tab["start"], max(r for r, _ in w.sh.cells)], "placeholders": placeholders,
            "unchecked": unchecked, "warnings": warnings, "changed_parts": bad}


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--model", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--ticker", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--rebuild", action="store_true")
    a = ap.parse_args()
    print(json.dumps(build(a.model, a.work, a.ticker.upper(), a.out, a.rebuild), indent=1, default=str))


if __name__ == "__main__":
    main()
