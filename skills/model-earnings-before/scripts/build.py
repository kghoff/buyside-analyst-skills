# skills/model-earnings-before/scripts/build.py
"""Writes the Earnings tab into a copy of the user's model by raw-XML editing (xlsx.py) and, with --variance
consensus, the grid into the Consensus tab's variance block (variance.py). Every other part of the workbook stays
byte-identical (checked here: the build stops if anything else changed). Yellow = the agent's call, the user's to
change (blue on yellow, a note with the agent's value, anchor and reason); blue = typed from a source; black =
formulas; green = links to other tabs.

A rerun keeps every yellow cell the user changed (W/inputs_written.json records what the last build wrote) and the
forecast frozen for the same quarter (unless --refreeze). The Consensus block is filled when it is model-consensus's
skeleton or this skill's own last fill (W/variance_written.json); when it holds the user's entries the build stops
until the user chooses: --force-variance (overwrite) or --variance earnings (keep theirs; the grid goes on this tab).
Writes W/layout.json (each checked cell's expected value: earnmath on context.json and the resolved inputs) for
verify.py and note.py, and W/inputs_written.next.json and W/variance_written.next.json (SKILL step 9 renames them
once the copy replaces the model).

usage: python3 build.py --model M --work W --ticker T --out OUT.xlsx --variance consensus|earnings
       [--force-variance] [--refreeze]"""
import argparse
import datetime as dt
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))   # run with python3 -I
import earnmath as em  # noqa: E402
import variance as va  # noqa: E402
from tabkit import BLACK, GEN, RED, W, _move_after, _n, changed_parts, resolve_values, sheet_part, tab_parts  # noqa: E402,F401
from xlsx import CT, Package, Styles, colname, comments_parts  # noqa: E402

TAB = "Earnings"
AFTER = ("Short Check", "Valuation")
PCT, MULT, MONEY, NUM, INT, MILL = "0.0%", '0.0"x"', "$#,##0.00", "0.00", "0", "#,##0.0"
BPS, DATE = '0" bps"', "yyyy-mm-dd"
FORMULA = "FORMULA"                         # the code set-up row left to its formula
CODE_PREFIX = "=IF(AND(ISNUMBER("
INPUTS = [  # key, label (unique in column A), format
    ("report_date", "Report date (estimated: type the announced date)", GEN),
    ("stance", "Stance (the agent's call; the rule's answer is in column C)", GEN),
    ("call_q", "The quarter: beat / in line / miss", GEN),
    ("call_g", "The guide: raise / hold / cut / initiate / none given", GEN),
    ("expected_move", "Expected move on the day, either way", PCT),
    ("up_eps", "Upside case: EPS (next 12 months)", MONEY), ("up_pe", "Upside case: P/E", MULT),
    ("down_eps", "Downside case: EPS (next 12 months)", MONEY), ("down_pe", "Downside case: P/E", MULT),
    ("p_beat", "Our P(upside case)", PCT), ("key_metric", "Key metric", GEN),
]
LABEL = {k: lab for k, lab, _ in INPUTS}
FMT = {k: f for k, _, f in INPUTS}
HFMT = {"rr_add": MULT, "edge_add": PCT, "edge_trim": PCT, "rr_trim": MULT, "hedge_mult": MULT,
        "margin_range": PCT, "pe_peak": PCT, "pe_low": PCT, "pe_high": PCT, "rel_perf": PCT}
CHECK_HEADS = ["% yoy", "% yoy, quarter before", "2-year stack", "2-year stack, quarter before", "3-year stack",
               "% qoq", "Average % qoq (5 years)", "Margin", "Average margin (5 years)", "Incremental margin",
               "Hockey stick?"]
CHECK_KEYS = ["yoy", "yoy_prev", "st2", "st2_prev", "st3", "qoq", "qoq_avg", "margin", "margin_avg", "incr"]
FROZEN_RE = re.compile(r"^7\. FROZEN FORECAST: (.+?), frozen (\d{4}-\d{2}-\d{2})")


def tab_part(path):
    return sheet_part(path, TAB)


def read_tab(path, data_only):
    """{column-A label: column-B value} of the Earnings tab (None if absent or no file). The set-up row's own code
    formula reads as FORMULA; any other formula (the user's) stays as written."""
    import openpyxl
    if not path or not os.path.exists(path):
        return None
    wb = openpyxl.load_workbook(path, read_only=True, data_only=data_only)
    if TAB not in wb.sheetnames:
        wb.close()
        return None
    out = {}
    for row in wb[TAB].iter_rows(min_row=1, max_col=2):
        a = row[0]
        if getattr(a, "value", None) is None:
            continue
        v = row[1].value if len(row) > 1 else None
        if not data_only and isinstance(v, str) and v.startswith(CODE_PREFIX) and '"unknown")' in v:
            v = FORMULA
        out[str(a.value).strip()] = v
    wb.close()
    return out


def read_frozen(path):
    """The frozen block of the tab now: {quarter, date, rows [{label, q, fy}]}, or None."""
    import openpyxl
    if not path or not os.path.exists(path):
        return None
    wb = openpyxl.load_workbook(path, read_only=True)
    if TAB not in wb.sheetnames:
        wb.close()
        return None
    g = {}
    for row in wb[TAB].iter_rows(min_row=1, max_col=3):
        for c in row:
            if getattr(c, "value", None) is not None:
                g[(c.row, c.column)] = c.value
    wb.close()
    top = next(((r, m) for (r, c), v in sorted(g.items()) if c == 1 and isinstance(v, str)
                and (m := FROZEN_RE.match(v))), None)
    if not top:
        return None
    r, m = top[0] + 2, top[1]
    rows = []
    while isinstance(g.get((r, 1)), str) and not re.match(r"^\d+\. ", g[(r, 1)]):
        rows.append({"label": g[(r, 1)], "q": g.get((r, 2)), "fy": g.get((r, 3))})
        r += 1
    return {"quarter": m.group(1), "date": m.group(2), "rows": rows}


def _note(x, extra=""):
    a = f"anchor {x.get('anchor', 'judgment')}" + (f" = {x['anchor_value']}" if "anchor_value" in x else "")
    return f"{extra}Agent: {x.get('value', x.get('side'))} | {a} | {x.get('reason', '')}"


def agent_values(plan, ctx):
    v = {LABEL["stance"]: plan["stance"]["value"], LABEL["call_q"]: plan["call"]["quarter"],
         LABEL["call_g"]: plan["call"]["guide"], LABEL["expected_move"]: plan["call"]["expected_move"],
         LABEL["key_metric"]: plan["key_metric"]["value"]}
    for k in em.AGENT_INPUTS:
        v[LABEL[k]] = plan["inputs"][k]["value"]
    for rid, lab, _, _, code in em.SETUP:
        x = (plan.get("setup") or {}).get(rid)
        v[lab] = FORMULA if code and (x is None or x.get("side") == ctx["code"]["setup"][rid]) else x["side"]
    for rid, lab in em.RISKS:
        v[lab] = plan["risks"][rid]["score"]
    for k, lab in em.HOUSE_LABEL.items():
        v[lab] = em.HOUSE[k]
    if ctx["report_date"]["estimated"]:
        v[LABEL["report_date"]] = ctx["report_date"]["value"] or "type the date"
    return v


def _calc(v, lab, values_tab):
    """A cell's value for the math: a user's formula counts at its recalculated value (from the values copy)."""
    return (values_tab or {}).get(lab) if isinstance(v, str) and v.startswith("=") else v


def recode(ctx, H):
    """Code's set-up side and blow-up flags again, on the thresholds the tab now holds."""
    b = ctx["checks"]["blowup"]
    pe = (ctx["links"]["multiples"].get("pe_pct") or {}).get("value")
    return {**ctx, "house": H,
            "code": {"setup": {"value_perf": em.setup_code(pe, ctx["rates"]["rel"]["value"], H)},
                     "blowups": em.blowups(b["margin_range"]["value"], b["ttm_ni"]["value"], b["ttm_fcf"]["value"],
                                           b["cash"]["value"], pe, H)}}


def _days(v, today):
    if isinstance(v, dt.datetime):
        v = v.date()
    if isinstance(v, str):
        try:
            v = dt.date.fromisoformat(v.strip()[:10])
        except ValueError:
            return None
    return (v - dt.date.fromisoformat(today)).days if isinstance(v, dt.date) else None


def _math(ctx, used, values_tab):
    inp = {k: _calc(used[LABEL[k]], LABEL[k], values_tab) for k in em.AGENT_INPUTS}
    H = {}
    for k, lab in em.HOUSE_LABEL.items():
        v = _calc(used[lab], lab, values_tab)
        H[k] = v if _n(v) else em.HOUSE[k]
    c2 = recode(ctx, H)
    sides = {}
    for rid, lab, _, _, code in em.SETUP:
        u = used[lab]
        sides[rid] = c2["code"]["setup"][rid] if u == FORMULA else str(_calc(u, lab, values_tab)).strip().lower()
    s = em.summary(c2, inp, sides, H)
    rd = (_calc(used[LABEL["report_date"]], LABEL["report_date"], values_tab) if ctx["report_date"]["estimated"]
          else ctx["report_date"]["value"])
    prod = lambda a, b: a * b if _n(a) and _n(b) else None   # noqa: E731
    return {**s, "inputs": inp, "H": H, "blowups": c2["code"]["blowups"], "days": _days(rd, ctx["today"]),
            "up_price": prod(inp["up_pe"], inp["up_eps"]), "down_price": prod(inp["down_pe"], inp["down_eps"])}


def rule_formula(ref):
    RR, ED, NT, NB, DN, IM = (ref(k) for k in ("rr", "edge", "net", "nblow", "down", "implied"))
    h = lambda k: ref(f"h_{k}")   # noqa: E731
    return (f'IF(AND(ISNUMBER({RR}),ISNUMBER({ED})),IF(AND({RR}>={h("rr_add")},{ED}>={h("edge_add")},{NT}>=0,'
            f'{NB}<=1),"add",IF(OR({ED}<={h("edge_trim")},AND({RR}<{h("rr_trim")},{NT}<0)),"trim",'
            f'IF(OR(IF(ISNUMBER({IM}),ABS({DN})>={h("hedge_mult")}*{IM}-1E-9,FALSE),{NB}>=2),"hedge","hold"))),"?")')


def setup_formula(PP, REL, ref):
    h = lambda k: ref(f"h_{k}")   # noqa: E731
    return (f'IF(AND(ISNUMBER({PP}),ISNUMBER({REL})),IF(AND({PP}<={h("pe_low")},{REL}<=-{h("rel_perf")}),"long",'
            f'IF(AND({PP}>={h("pe_high")},{REL}>={h("rel_perf")}),"short","neutral")),"unknown")')


def lay_out(w, ctx, plan, used, users, calc, ticker, unverified, frozen, var, fwd):
    """Every cell of the tab. calc = the Python twin of the tab's numbers (_math). fwd = the refs pass 1 found (the
    rule and the set-up row read rows below them); None on pass 1. Returns the refs."""
    F = fwd or {}
    ref = lambda k: F.get(k, "$B$1")   # noqa: E731
    R = {}
    r = 4
    price = ctx["price"]["value"]
    w.text("A1", f"{ticker} earnings preview: {ctx['quarter']} (model-earnings-before, {ctx['today']})", b=True, sz=14)
    w.text("A2", "Yellow = the agent's call, yours to change (its note gives the reason and the anchor); blue = typed "
                 "from a source; black = formulas; green = links to other tabs. Rerun about two weeks before each print.",
           i=True)

    def band(t):
        nonlocal r
        w.text(f"A{r}", t, b=True, sz=12)
        r += 1

    def put(label):
        nonlocal r
        w.text(f"A{r}", label)
        r += 1
        return r - 1

    def inp(label, fmt, x, ukey, extra=""):
        rr = put(label)
        note = (f"You typed {used[label]}. " if label in users else "") + _note(x, extra)
        w.input_(f"B{rr}", label, used[label], fmt, note)
        bad = ukey in unverified
        w.text(f"D{rr}", ("UNVERIFIED: " if bad else "") + str(x.get("reason", "")), color=RED if bad else BLACK)
        R[label] = f"$B${rr}"
        return f"$B${rr}"

    # 1. snapshot and the call
    band("1. PRINT SNAPSHOT AND THE CALL")
    w.text(f"B{put('Quarter being reported')}", ctx["quarter"])
    w.text(f"B{put('Fiscal year')}", ctx["fy"])
    rd = ctx["report_date"]
    if rd["estimated"]:
        RD = inp(LABEL["report_date"], GEN, {"value": rd["value"], "anchor": "judgment", "reason": rd["source"]},
                 "report_date")
    else:
        x = put("Report date")
        w.typed_text(f"B{x}", rd["value"], f"{rd['source']}.")
        RD = f"$B${x}"
    x = put("Preview date")
    w.typed_text(f"B{x}", ctx["today"], "The day this preview was built.")
    PD = f"$B${x}"
    x = put("Days to print")
    w.formula(f"B{x}", f"IFERROR(IF(ISNUMBER({RD}),{RD},DATEVALUE({RD}))-DATEVALUE({PD}),NA())", INT, calc["days"])
    x = put("Price")
    w.typed(f"B{x}", price, MONEY, f"{ctx['price']['source']}.")
    PRICE = R["price"] = f"$B${x}"
    st = inp(LABEL["stance"], GEN, plan["stance"], "stance")
    srow = int(st.split("$")[-1])
    w.formula(f"C{srow}", rule_formula(ref), GEN, calc["rule"] or "?", b=True)
    R["rule"] = f"$C${srow}"
    call = plan["call"]
    inp(LABEL["call_q"], GEN, {"value": call["quarter"], "reason": call["reason"]}, "call")
    inp(LABEL["call_g"], GEN, {"value": call["guide"], "reason": call["reason"]}, "call")
    inp(LABEL["expected_move"], PCT, {"value": call["expected_move"], "reason": call["reason"]}, "call")
    w.text(f"B{put('Net')}", plan["net"])

    # 2. print risk / reward
    r += 1
    band("2. PRINT RISK / REWARD (the core formula: P/E x EPS against today's price; section 13.6)")
    ntm = ctx["checks"]["ntm_eps"]
    x = put(f"NTM EPS: our forecast ({', '.join(ntm['periods'])})")
    w.formula(f"B{x}", ntm["formula"], MONEY, ntm["value"])
    NTM = f"$B${x}"
    w.formula(f"B{put('P/E on NTM EPS')}", f"IFERROR({PRICE}/{NTM},NA())", MULT, em.div(price, ntm["value"]))
    for side in ("up", "down"):
        word = "Upside" if side == "up" else "Downside"
        E = inp(LABEL[f"{side}_eps"], MONEY, plan["inputs"][f"{side}_eps"], f"inputs.{side}_eps")
        P = inp(LABEL[f"{side}_pe"], MULT, plan["inputs"][f"{side}_pe"], f"inputs.{side}_pe")
        x = put(f"{word} case: price")
        w.formula(f"B{x}", f"IFERROR({E}*{P},NA())", MONEY, calc[f"{side}_price"])
        x2 = put(f"Move {side}")
        w.formula(f"B{x2}", f"IFERROR(B{x}/{PRICE}-1,NA())", PCT, calc[side])
        R[side] = f"$B${x2}"
    U, D = R["up"], R["down"]
    x = put("Reward / risk")
    w.formula(f"B{x}", f"IFERROR(IF(AND({U}>0,{D}<0),{U}/ABS({D}),NA()),NA())", MULT, calc["rr"])
    R["rr"] = f"$B${x}"
    x = put("Implied PSUC: the break-even odds of the upside case")
    w.formula(f"B{x}", f"IFERROR(IF(AND({U}>0,{D}<0),ABS({D})/({U}+ABS({D})),NA()),NA())", PCT, calc["psuc"])
    R["psuc"] = f"$B${x}"
    PB = inp(LABEL["p_beat"], PCT, plan["inputs"]["p_beat"], "inputs.p_beat")
    x = put("Edge: our P(upside case) minus the implied PSUC")
    w.formula(f"B{x}", f"IFERROR({PB}-{R['psuc']},NA())", PCT, calc["edge"])
    R["edge"] = f"$B${x}"

    # 3. set-up
    r += 1
    band("3. SET-UP (section 13.4: good set-ups are contrarian)")
    pp = ctx["links"]["multiples"].get("pe_pct")
    x = put("P/E percentile, last 5 years (Multiples)")
    if pp:
        w.link(f"B{x}", pp["ref"], PCT, pp["value"])
    else:
        w.text(f"B{x}", "n/a", i=True)
    PP = f"$B${x}"
    rel = ctx["rates"]["rel"]
    x = put(f"Stock minus SPY since the last print ({rel.get('from') or 'none'} to {rel.get('to') or '-'})")
    w.formula(f"B{x}", rel["formula"], PCT, rel["value"])
    REL = f"$B${x}"
    s0 = r
    for rid, lab, lt, sht, code in em.SETUP:
        x = dict((plan.get("setup") or {}).get(rid) or {})
        extra = f"Long set-up: {lt}. Short set-up: {sht}. "
        if code and used[lab] == FORMULA:
            y = put(lab)
            w.formula(f"B{y}", setup_formula(PP, REL, ref), GEN, calc["sides"][rid])
            w.text(f"D{y}", "Code: long if the P/E percentile and the move against SPY are both at or below the long "
                            "thresholds (band 8); short if both are at or above the short ones.")
            R[lab] = f"$B${y}"
        else:
            inp(lab, GEN, {**x, "value": x.get("side", used[lab])}, f"setup.{rid}", extra)
    x = put("Set-up net: long rows minus short rows")
    w.formula(f"B{x}", f'COUNTIF(B{s0}:B{s0 + len(em.SETUP) - 1},"long")-COUNTIF(B{s0}:B{s0 + len(em.SETUP) - 1},"short")',
              INT, calc["net"])
    R["net"] = f"$B${x}"
    hb = put("Blow-up flags (section 13.4)")
    for col, t in (("B", "Flag"), ("C", "Measure"), ("D", "TTM FCF"), ("E", "Cash")):
        w.text(f"{col}{hb}", t, b=True)
    b, fl = ctx["checks"]["blowup"], calc["blowups"]
    h = lambda k: ref(f"h_{k}")   # noqa: E731
    b0 = put(f"Blow-up: operating-margin range, last {b['margin_range'].get('n', 20)} quarters")
    w.formula(f"C{b0}", b["margin_range"]["formula"], PCT, b["margin_range"]["value"])
    w.formula(f"B{b0}", f'IF(ISNUMBER(C{b0}),IF(C{b0}>{h("margin_range")},"yes","no"),"?")', GEN,
              em.flag_text(fl["margins"]))
    y = put("Blow-up: losing money, or burning more cash in a year than it holds (C = TTM net income)")
    w.formula(f"C{y}", b["ttm_ni"]["formula"], MILL, b["ttm_ni"]["value"])
    w.formula(f"D{y}", b["ttm_fcf"]["formula"], MILL, b["ttm_fcf"]["value"])
    w.formula(f"E{y}", b["cash"]["formula"], MILL, b["cash"]["value"])
    w.formula(f"B{y}", f'IF(ISNUMBER(C{y}),IF(C{y}<0,"yes",IF(IF(ISNUMBER(D{y}),D{y}<0,FALSE),'
                       f'IF(ISNUMBER(E{y}),IF(E{y}<ABS(D{y}),"yes","no"),"?"),"no")),"?")', GEN, em.flag_text(fl["cash"]))
    y = put("Blow-up: peak P/E (5-year percentile)")
    w.formula(f"C{y}", f"IF(ISNUMBER({PP}),{PP},NA())", PCT, (pp or {}).get("value"))
    w.formula(f"B{y}", f'IF(ISNUMBER(C{y}),IF(C{y}>={h("pe_peak")},"yes","no"),"?")', GEN, em.flag_text(fl["peak_pe"]))
    x = put("Blow-up flags: count")
    w.formula(f"B{x}", f'COUNTIF(B{b0}:B{b0 + 2},"yes")', INT, calc["nblow"])
    R["nblow"] = f"$B${x}"
    for rid, lab in em.RISKS:
        rk = plan["risks"][rid]
        inp(lab, INT, {**rk, "value": rk["score"]}, f"risks.{rid}")
    inp(LABEL["key_metric"], GEN, plan["key_metric"], "key_metric")

    # 4. model checks
    r += 1
    band(f"4. MODEL CHECKS: {ctx['quarter']} (live on MOD; section 13.5)")
    x = put("Line")
    for k, t in enumerate(CHECK_HEADS):
        w.text(f"{colname(2 + k)}{x}", t, b=True)
    for m in ctx["checks"]["metrics"]:
        y = put(m["name"])
        for k, key in enumerate(CHECK_KEYS):
            c = m["cells"].get(key)
            if c:
                w.formula(f"{colname(2 + k)}{y}", c["formula"], PCT, c["value"])
        cs = ",".join(f"ISNUMBER({c}{y})" for c in "BCDEGH")
        w.formula(f"L{y}", f'IF(AND({cs}),IF(AND(B{y}>C{y},D{y}>E{y},G{y}>H{y}),"yes","no"),"?")', GEN,
                  m["cells"]["hockey"])
    h2 = ctx["checks"]["h2"]
    y = put(f"Second-half share of {ctx['fy']} revenue (C: the 5-year average)")
    w.formula(f"B{y}", h2["share"]["formula"], PCT, h2["share"]["value"])
    w.formula(f"C{y}", h2["avg"]["formula"], PCT, h2["avg"]["value"])

    # 5. base rates
    r += 1
    band("5. BASE RATES (section 13.6)")
    x = put("Earnings print (newest first)")
    for col, t in zip("BCDEFG", ("Reaction day", "Day move", "|Day move|", "Idio move", "Run-up (T-8 to T-1)",
                                 "Drift (T to T+7)")):
        w.text(f"{col}{x}", t, b=True)
    DR, CR = ctx["rates"]["date_range"], ctx["rates"]["close_range"]
    prints = ctx["rates"]["prints"]
    p0 = r
    for k, p in enumerate(prints):
        y = put(f"Print {k + 1}")
        w.link(f"B{y}", p["refs"]["date"], DATE, None, check=False)
        w.link(f"C{y}", p["refs"]["move"], PCT, p["move"], check=_n(p["move"]))
        w.formula(f"D{y}", f'IF(ISNUMBER(C{y}),ABS(C{y}),"")', PCT, abs(p["move"]) if _n(p["move"]) else None,
                  check=_n(p["move"]))
        w.link(f"E{y}", p["refs"]["idio"], PCT, p["idio"], check=_n(p["idio"]))
        m_ = f"MATCH(B{y},{DR},0)"
        w.formula(f"F{y}", f"IFERROR(IF({m_}>8,INDEX({CR},{m_}-1)/INDEX({CR},{m_}-8)-1,NA()),NA())", PCT, p["run_up"])
        w.formula(f"G{y}", f"IFERROR(INDEX({CR},{m_}+7)/INDEX({CR},{m_})-1,NA())", PCT, p["drift"])
    st_ = ctx["rates"]["stats"]
    if prints:
        pn = r - 1
        C_, D_ = f"C{p0}:C{pn}", f"D{p0}:D{pn}"
        w.formula(f"B{put('Prints counted')}", f"COUNT({C_})", INT, st_["n"])
        x = put("Average |day move|")
        w.formula(f"B{x}", f"IFERROR(AVERAGE({D_}),NA())", PCT, st_["avg_abs"])
        AVG = f"$B${x}"
        w.formula(f"B{put('Median |day move|')}", f"IFERROR(MEDIAN({D_}),NA())", PCT, st_["med_abs"])
        w.formula(f"B{put('Up prints')}", f'COUNTIF({C_},">0")', INT, st_["up"])
        w.formula(f"B{put('Down prints')}", f'COUNTIF({C_},"<0")', INT, st_["down"])
    else:
        put("No earnings prints in Px Events")
        AVG = None
    v = ctx["rates"]["vol"]
    x = put(f"Daily sigma (last {v.get('n', 0)} trading days, Px Data)")
    w.formula(f"B{x}", v["formula"], PCT, v["value"])
    DS = f"$B${x}"
    w.formula(f"B{put('Annual sigma')}", f"IFERROR({DS}*SQRT(252),NA())", PCT, em.annual_sigma(v["value"]))
    if AVG:
        w.formula(f"B{put('Average |day move| in daily sigmas')}", f"IFERROR({AVG}/{DS},NA())", NUM,
                  em.div(st_["avg_abs"], v["value"]))
    x = put("Options-implied move (Yahoo: at-the-money straddle on the first expiry after the print)")
    imp = ctx["yahoo"]["implied_move"]
    if _n(imp):
        sd = ctx["yahoo"].get("straddle") or {}
        w.typed(f"B{x}", imp, PCT, f"Yahoo options: expiry {sd.get('expiry')}, strike {sd.get('strike')}, call "
                                  f"{sd.get('call')} + put {sd.get('put')}, over the price.")
    else:
        w.text(f"B{x}", "n/a", i=True)
        w.text(f"D{x}", "No implied move: the print date isn't announced yet, or Yahoo had no options.", i=True)
    R["implied"] = f"$B${x}"
    if ctx["yahoo"]["surprises"]:
        x = put("Yahoo EPS surprises (last 4 quarters)")
        for col, t in zip("BCD", ("Estimate", "Actual", "Surprise")):
            w.text(f"{col}{x}", t, b=True)
        for s_ in ctx["yahoo"]["surprises"]:
            y = put(f"Quarter ending {s_['quarter']}")
            note = "Yahoo earningsHistory."
            w.typed(f"B{y}", s_["estimate"], MONEY, note)
            w.typed(f"C{y}", s_["actual"], MONEY, note)
            w.typed(f"D{y}", s_["surprise"], PCT, note)
    for bl in ctx["guidance"]:
        x = put(f"Guidance trail: {bl['title']} (Filings Charts)")
        w.text(f"B{x}", "Actual vs first guide midpoint", b=True)
        w.text(f"C{x}", "Changes to the guide", b=True)
        g0 = r
        for row in bl["rows"]:
            y = put(row["year"])
            w.link(f"B{y}", row["vs_mid"]["ref"], PCT, row["vs_mid"]["value"], check=_n(row["vs_mid"]["value"]))
            if row.get("changes"):
                w.link(f"C{y}", row["changes"]["ref"], INT, row["changes"]["value"], check=_n(row["changes"]["value"]))
        gn = r - 1
        y = put("Habitual raiser: beat the first guide's midpoint in 3 of the last 4 years")
        w.formula(f"B{y}", f'IF(COUNT(B{g0}:B{gn})>=3,IF(COUNTIF(B{g0}:B{gn},">0")>=3,"yes","no"),"?")', GEN,
                  bl["habitual"])
    if not ctx["guidance"]:
        put("No 'Guidance vs actual' block on Filings Charts: run /research-filings to add the guidance trail.")

    # 6. variance grid
    r += 1
    band("6. VARIANCE GRID: consensus against our numbers")
    if var["where"] == "consensus":
        put(f"On the Consensus tab, rows {var['rows'][0]}-{var['rows'][-1]} (filled by this skill on {ctx['today']}; "
            "the variance formulas in I-K are model-consensus's).")
    else:
        per = ctx["mod"]["periods"]
        x = put("Line")
        w.text(f"B{x}", "(MOD units; margins and growth in %)", i=True)
        for cols, grp in (("CDE", "Consensus"), ("FGH", "Internal"), ("IJK", "Variance")):
            for c, k in zip(cols, ("q", "fy", "fy1")):
                w.text(f"{c}{x}", f"{grp} {per.get(k) or '-'}", b=True)
        spec = va.grid_rows(ctx)
        rows = list(range(r, r + len(spec)))
        cells, _ = va.grid_cells(ctx, rows)
        snap = (ctx["links"].get("consensus") or {}).get("snapshot")
        for cref, (kind, content, exp, role, fmt) in cells.items():
            if role == "label":
                w.text(f"A{cref[1:]}", content)
            elif role == "typed":
                w.typed(cref, content, fmt, f"Consensus tab mean row (Yahoo snapshot {snap}).")
            elif role == "link":
                w.link(cref, content, fmt, exp)
            else:
                w.formula(cref, content, fmt, exp)
        for (lab, pct), rr in zip(spec, rows):
            for cc, ic, vc in zip("CDE", "FGH", "IJK"):
                cv, iv = (cells.get(f"{cc}{rr}") or (0, 0, None))[2], (cells.get(f"{ic}{rr}") or (0, 0, None))[2]
                if pct:
                    f = f"IFERROR(IF(AND(ISNUMBER({cc}{rr}),ISNUMBER({ic}{rr})),({ic}{rr}-{cc}{rr})*10000,NA()),NA())"
                    want = (iv - cv) * 10000 if _n(cv) and _n(iv) else None
                else:
                    f = f"IFERROR(IF(AND(ISNUMBER({cc}{rr}),ISNUMBER({ic}{rr})),{ic}{rr}/{cc}{rr}-1,NA()),NA())"
                    want = (iv / cv - 1) if _n(cv) and _n(iv) and cv != 0 else None
                w.formula(f"{vc}{rr}", f, BPS if pct else PCT, want)
        r = rows[-1] + 1
        if var.get("reason"):
            put(var["reason"])

    # 7. frozen forecast
    r += 1
    band(f"7. FROZEN FORECAST: {frozen['quarter']}, frozen {frozen['date']} (values: model-earnings-after "
         "compares the print with these)")
    x = put("MOD line")
    w.text(f"B{x}", frozen["quarter"], b=True)
    w.text(f"C{x}", frozen["fy"], b=True)
    w.notes[f"B{x}"] = (f"MOD's forecast on {frozen['date']}, typed as values: they stay put when the model is "
                        "updated for the print.")
    for row in frozen["rows"]:
        y = put(row["label"])
        w.value(f"B{y}", row["q"], MILL)
        w.value(f"C{y}", row["fy"], MILL)

    # 8. thresholds
    r += 1
    band("8. RULE THRESHOLDS (yours to change; the stance rule, the set-up row and the blow-up flags read them)")
    for k, lab in em.HOUSE_LABEL.items():
        R[f"h_{k}"] = inp(lab, HFMT[k], {"value": em.HOUSE[k], "anchor": "house",
                                         "reason": "House default from the spec; change it here and the tab follows."},
                          f"house.{k}")
    return R


def write_tab(pkg, w):
    """Replace the tab whole, put it after Short Check (else Valuation, else last), attach the notes."""
    if TAB in [s[0] for s in pkg.sheets()]:
        pkg.remove_sheet(TAB)
    part = pkg.add_sheet(TAB, "")
    names = [s[0] for s in pkg.sheets()]
    _move_after(pkg, TAB, next((a for a in AFTER if a in names), ""))
    lrid = None
    if w.notes:
        pkg.content_default("vml", "application/vnd.openxmlformats-officedocument.vmlDrawing")
        ids = [int(x) for p, data in pkg.parts.items() if p.endswith(".vml")
               for d in re.findall(rb'<o:idmap v:ext="edit" data="([\d,\s]+)"', data) for x in re.findall(rb"\d+", d)]
        cn, vn = pkg.free("xl/comments{}.xml"), pkg.free("xl/drawings/vmlDrawing{}.vml")
        cx, vml = comments_parts(w.notes, max(ids + [0]) + 1)
        pkg.put(f"xl/comments{cn}.xml", cx)
        pkg.put(f"xl/drawings/vmlDrawing{vn}.vml", vml)
        lrid = pkg.attach(part, "vml", f"xl/drawings/vmlDrawing{vn}.vml")
        pkg.attach(part, "comments", f"xl/comments{cn}.xml", CT["comments"])
    pkg.put(part, w.sh.xml(None, lrid))
    return part


def build(model, work, ticker, out, variance="earnings", force_variance=False, refreeze=False):
    if os.path.abspath(out) == os.path.abspath(model):
        raise SystemExit("model-earnings-before: --out must be a copy, not the model itself.")
    ctx = json.load(open(os.path.join(work, "context.json")))
    plan = json.load(open(os.path.join(work, "earnings_plan.json")))
    def load(n):
        p = os.path.join(work, n)
        return json.load(open(p)) if os.path.exists(p) else None

    written, vwritten = load("inputs_written.json"), load("variance_written.json")
    unverified = set(load("unverified.json") or [])
    existing, existing_v = read_tab(model, False), read_tab(ctx["values"], True)
    warnings = []
    if existing is not None and written is None:
        warnings.append("There is no inputs_written.json (the record of what the last build wrote), so every yellow "
                        "cell that differs from the agent's suggestion is treated as yours.")
    used, users = resolve_values(existing, written, agent_values(plan, ctx))
    for k, lab in em.HOUSE_LABEL.items():
        if not _n(_calc(used[lab], lab, existing_v)):
            warnings.append(f"{lab!r} holds {used[lab]!r}, not a number: the cells that read it show errors. "
                            "Type a number there and rerun.")
    calc = _math(ctx, used, existing_v)

    old = read_frozen(model)
    if old and old["quarter"] == ctx["quarter"] and not refreeze:
        frozen = {**old, "fy": ctx["fy"], "kept": True}
    else:
        frozen = {"quarter": ctx["quarter"], "fy": ctx["fy"], "date": ctx["today"], "kept": False,
                  "rows": [{"label": x["label"], "q": x["q"], "fy": x["fy"]} for x in ctx["frozen"]]}

    pkg = Package(model)
    st = Styles(pkg.text("xl/styles.xml"))
    var, cons_part, expected_cons, var_written = {"where": "earnings"}, None, {}, None
    if variance == "consensus":
        info = va.inspect(model, vwritten)
        if info["status"] in ("missing", "no_block"):
            var["reason"] = (f"The Consensus tab has no variance block ({info['status'].replace('_', ' ')}), so the "
                             "grid is here.")
            warnings.append(var["reason"])
        elif info["status"] == "data" and not force_variance:
            raise SystemExit("model-earnings-before: the Consensus variance table holds your own entries (" +
                             ", ".join(info["filled"][:8]) + "). Ask the user first: overwrite them (rerun build.py "
                             "with --force-variance) or keep them (rerun with --variance earnings).")
        else:
            res = va.fill(pkg, st, ctx, info, force=force_variance or info["status"] == "ours")
            var = {"where": "consensus", "status": info["status"], "rows": info["rows"], "skipped": res["skipped"],
                   "dropped": res["dropped"]}
            cons_part, expected_cons, var_written = res["part"], res["expected"], res["written"]
            if res["skipped"]:
                warnings.append("Consensus cells left as they were (they held something): " + ", ".join(res["skipped"]))
            if res["dropped"]:
                warnings.append("Not enough rows in the Consensus block for: " + ", ".join(res["dropped"]))
    old_parts = tab_parts(pkg, TAB)
    R1 = lay_out(W(st, users), ctx, plan, used, users, calc, ticker, unverified, frozen, var, None)
    w = W(st, users)
    R = lay_out(w, ctx, plan, used, users, calc, ticker, unverified, frozen, var, R1)
    if R != R1:
        raise SystemExit("model-earnings-before: the two layout passes disagree (a bug in build.py).")
    a_texts = list(w.col_a.values())
    for lab in used:
        if lab in w.inputs and a_texts.count(lab) != 1:
            raise SystemExit(f"model-earnings-before: the label {lab!r} appears {a_texts.count(lab)} times in column A.")
    w.sh.comments = w.notes
    w.sh.freeze = "B4"
    w.sh.widths.update({1: 64, 2: 16, 3: 14, **{k: 13 for k in range(4, 13)}})
    part = write_tab(pkg, w)
    pkg.put("xl/styles.xml", st.render())
    pkg.finish()
    pkg.save(out)
    import notebox
    notebox.fix(out, out, since=model)
    new = tab_parts(Package(out), TAB)
    bad = changed_parts(model, out, old_parts | new | {part} | ({cons_part} if cons_part else set()))
    if bad:
        os.remove(out)
        raise SystemExit("model-earnings-before: the build changed parts it must not touch: " + ", ".join(bad))
    serial = {k: v for k, v in calc.items() if k != "inputs"}
    json.dump({"expected": w.expected, "expected_cons": expected_cons, "kinds": w.kinds, "fmt": w.fmt, "refs": R,
               "inputs": w.inputs, "used": used, "users": sorted(users), "calc": serial, "variance": var,
               "frozen": {k: frozen[k] for k in ("quarter", "date", "kept")}, "warnings": warnings},
              open(os.path.join(work, "layout.json"), "w"), indent=0, default=str)
    json.dump({lab: {"value": v, "user": lab in users} for lab, v in used.items()},
              open(os.path.join(work, "inputs_written.next.json"), "w"), indent=1, default=str)
    if var_written is not None:
        json.dump(var_written, open(os.path.join(work, "variance_written.next.json"), "w"), indent=1, default=str)
    return {"tab": TAB, "users_kept": sorted(users), "changed_parts": bad, "stance_rule": calc["rule"],
            "stance_used": used[LABEL["stance"]], "variance": var,
            "frozen": {k: frozen[k] for k in ("quarter", "date", "kept")}, "warnings": warnings}


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--model", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--ticker", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--variance", choices=["consensus", "earnings"], required=True)
    ap.add_argument("--force-variance", action="store_true")
    ap.add_argument("--refreeze", action="store_true")
    a = ap.parse_args()
    print(json.dumps(build(a.model, a.work, a.ticker.upper(), a.out, a.variance, a.force_variance, a.refreeze),
                     indent=1, default=str))


if __name__ == "__main__":
    main()
