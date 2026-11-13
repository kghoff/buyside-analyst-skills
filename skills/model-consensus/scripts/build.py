"""Write (or refresh) the Consensus tab in a copy of the user's model, for any stock. Raw XML: only this tab's own parts
plus workbook.xml, its rels, [Content_Types].xml and styles.xml change (xlsx.py); every other part stays byte-identical.

usage: python3 build.py --model M.xlsx --work W --ticker T --out W/built.xlsx
Reads W/snapshots/*.json (newest = this run), W/estimates.json (optional, from estimates.py choose), the model's
Px Data tab (closes for the chart and the log) and the old Consensus tab, if any: the user's variance-table entries (labels
and inputs, columns B-H) are carried over cell for cell, formulas re-pointed if the block moved. Writes OUT and
W/layout.json (expected values for verify.py) and prints a JSON summary for the agent's report.
The user's own cells in the variance columns I-K (a typed value, or a formula other than the skill's) are kept too, and
named in the summary warnings. A rerun puts the tab back at the position the user gave it.
Exit 3: another tab, a defined name, a chart, pivot or table points into the old Consensus tab (show the user, stop)."""
import argparse
import json
import os
import re
import sys
from datetime import date, datetime, timedelta

import openpyxl

import charts
import estimates as ES
import firms as FM
import periods
import ratings
import snapshots
from openpyxl.worksheet.formula import ArrayFormula

from xlsx import CT, Package, Sheet, Styles, colname, colnum, comments_parts, relpath_of, resolve, unesc

TAB = "Consensus"
BLUE, GREEN, GREY, NAVY, WHITE = "FF0000FF", "FF008000", "FF808080", "FF002060", "FFFFFFFF"
MNY, PCT, MULT, PX, EPS, DATE = '#,##0.0_);\\(#,##0.0\\);"–"', "0.0%", '0.0"x"', "$#,##0.00", "$0.00", "yyyy-mm-dd"
BPS = '#,##0" bps";\\(#,##0\\)" bps"'
YELLOW, CONS = "FFFFFF99", "FFFFF2CC"
VAR_ROWS = ["Revenue", "Revenue growth", "Gross margin", "Operating margin", "FCF", "EPS",
            "(key driver)", "(key driver)", "(key driver)"]
BANDS = ["1. BROKER TABLE", "2. VARIANCE TABLE: consensus vs your own numbers (type them in)",
         "3. RATING HISTORY CHART (last 5 years)", "4. RATING HISTORY LOG (last 5 years, newest first)",
         "5. CONSENSUS SNAPSHOTS (rows added on every run)"]
BT = dict(zip(["n", "firm", "type", "rating", "bucket", "pt", "upside", "ldate", "lkind",
               "eq", "efy", "efy1", "rq", "rfy", "rfy1", "src"], "ABCDEFGHIJKLMNOP"))
TYPE_LABEL = {"bank": "Bank", "independent": "Independent", "specialist": "Specialist", "rating shop": "Rating shop",
              "quant": "Quant score", "other": "Other"}
NASDAQ_NOTE = ("Listed as covering by Nasdaq (Zacks); no rating action on Yahoo in the last 12 months, so rating and "
               "target are unknown.")
# a cell reference, optionally with a sheet prefix and a range end; text in double quotes is matched (and kept) whole
REF = re.compile(r'"[^"]*"|(?<![\w$.\'!:])((?:\'[^\']+\'|[A-Za-z_][\w.]*)!)?(\$?[A-Z]{1,3}\$?)(\d+)'
                 r'(?::(\$?[A-Z]{1,3}\$?)(\d+))?(?![\w(])')


def serial(d):
    return (d - date(1899, 12, 30)).days


def is_bps(label):
    """Margins, growth and rates vary in bps (whole words only: "Integrated" is not a rate)."""
    return bool(re.search(r"\b(margins?|growth|rates?)\b|%", str(label or ""), re.I))


def var_formula(label, cc, ic, rv):
    """(formula, bps?) for the variance cell comparing consensus column cc with the user's column ic on row rv."""
    if is_bps(label):
        return f'IF(OR({cc}{rv}="",{ic}{rv}=""),"",IFERROR(({ic}{rv}-{cc}{rv})*10000,""))', True
    return f'IF(OR({cc}{rv}="",{ic}{rv}=""),"",IFERROR({ic}{rv}/{cc}{rv}-1,""))', False


def generated_variants(cc, ic, rv):
    """Every variance formula a build writes (or an earlier build wrote) on row rv: a cell holding one of these is
    the skill's own, not the user's, so it is regenerated (the row label may have changed between bps and %)."""
    return {var_formula("margin", cc, ic, rv)[0], var_formula("", cc, ic, rv)[0],
            f'IF(OR({cc}{rv}="",{ic}{rv}=""),"",({ic}{rv}-{cc}{rv})*10000)'}    # pre-IFERROR bps formula


def carry(v):
    """(kind, content) for a cell value carried over from the old tab; formulas without the leading '='."""
    if isinstance(v, ArrayFormula):
        return "fa", str(v.text or "").lstrip("=")
    if isinstance(v, str) and v.startswith("="):
        return "f", v[1:]
    if isinstance(v, (datetime, date)):
        return "n", serial(v.date() if isinstance(v, datetime) else v)
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return "n", v
    return "s", str(v)


# references to the Consensus tab: Consensus!A1 or 'Consensus'!A1, never 'Old Consensus'!A1 or My.Consensus!A1
REF_TO_TAB = re.compile(r"(?:(?<![\w'.])Consensus|'Consensus')!")
STRIP_TEXT = re.compile(r"<(\w+:)?v>.*?</(\w+:)?v>|<is>.*?</is>|<a:t>.*?</a:t>", re.S)    # cached values and text


def consensus_refs(pkg):
    """Where the rest of the workbook points into the Consensus tab (it would break when the tab is replaced):
    other tabs' formulas, defined names (except the tab's own local names, which go with it), charts, pivot caches /
    tables and table parts not owned by the tab itself."""
    names = [s[0] for s in pkg.sheets()]
    if TAB not in names:
        return []
    idx = names.index(TAB)
    own = verify_tab_parts(pkg)
    hits = []
    for name, _, _, part in pkg.sheets():
        if name != TAB and REF_TO_TAB.search(unesc(STRIP_TEXT.sub("", pkg.text(part)))):
            hits.append(f"tab '{name}'")
    for m in re.finditer(r"<definedName\b([^>]*)>(.*?)</definedName>", pkg.text("xl/workbook.xml"), re.S):
        loc = re.search(r'localSheetId="(\d+)"', m.group(1))
        if loc and int(loc.group(1)) == idx:
            continue
        if REF_TO_TAB.search(unesc(m.group(2))):
            hits.append("defined name " + unesc(re.search(r'name="([^"]*)"', m.group(1)).group(1)))
    for part in sorted(pkg.parts):
        if part in own or not part.endswith(".xml") or not re.match(
                r"xl/(charts|chartsheets|pivotCache|pivotTables|tables)/", part):
            continue
        x = unesc(STRIP_TEXT.sub("", pkg.text(part)))
        if REF_TO_TAB.search(x) or re.search(r'<worksheetSource\b[^>]*\bsheet="Consensus"', x):
            hits.append(part)
    return hits


def verify_tab_parts(pkg):
    """Parts hanging off the Consensus tab (its drawing, charts, comments, VML), with their rels files."""
    todo = [p for n, _, _, p in pkg.sheets() if n == TAB]
    seen = set()
    while todo:
        p = todo.pop()
        if p in seen:
            continue
        seen |= {p, relpath_of(p)}
        todo += [resolve(p, tgt) for _, (_, tgt) in pkg.rels(relpath_of(p)).items() if "TargetMode" not in tgt]
    return seen


def next_vml_id(pkg):
    """First free VML shape-id block across the workbook's VML drawings (o:idmap data, any attribute order)."""
    ids = [int(x) for p, data in pkg.parts.items() if p.endswith(".vml")
           for d in re.findall(rb'idmap\b[^>]*\bdata="([\d,\s]+)"', data) for x in re.findall(rb"\d+", d)]
    return max(ids + [0]) + 1


def view_state(pkg):
    """activeTab / firstSheet of the first workbookView, as written (None if absent)."""
    m = re.search(r"<workbookView\b[^>]*>", pkg.text("xl/workbook.xml"))
    g = lambda a: (re.search(rf'\b{a}="(\d+)"', m.group(0)) or [None, None])[1] if m else None
    return {"activeTab": g("activeTab"), "firstSheet": g("firstSheet")}


def put_back(pkg, idx, views):
    """Move the freshly appended Consensus <sheet> to tab position idx (where the user had it). Tab order is then the same
    as before the rerun, so the workbook views get their old activeTab / firstSheet back and names local to tabs at
    or after idx get back the localSheetId remove_sheet lowered."""
    wb = pkg.text("xl/workbook.xml")
    tags = re.findall(r"<sheet\b[^>]*/>", wb)
    if idx < len(tags) - 1:
        wb = wb.replace(tags[-1], "", 1).replace(tags[idx], tags[-1] + tags[idx], 1)
    wb = re.sub(r'(<definedName\b[^>]*localSheetId=")(\d+)(")',
                lambda m: m.group(1) + str(int(m.group(2)) + (int(m.group(2)) >= idx)) + m.group(3), wb)

    def view(m):
        t = m.group(0)
        for a, v in views.items():
            if v is not None:
                t = re.sub(rf'\b{a}="\d+"', f'{a}="{v}"', t)
        return t
    wb = re.sub(r"<workbookView\b[^>]*>", view, wb, count=1)
    pkg.put("xl/workbook.xml", wb)


def shift_formula(f, delta, lo, hi):
    """Move same-sheet cell references whose row is inside [lo, hi] by delta rows (the variance block moved because
    the broker table above it changed length). Other tabs' refs (whole ranges), quoted text and function names stay."""
    def mv(m):
        if m.group(0).startswith('"') or m.group(1):
            return m.group(0)
        r = lambda x: str(int(x) + delta if lo <= int(x) <= hi else int(x))
        out = f"{m.group(2)}{r(m.group(3))}"
        return out + (f":{m.group(4)}{r(m.group(5))}" if m.group(4) else "")
    return REF.sub(mv, f)


def outside_refs(f, lo, hi):
    """Same-sheet references in f that point outside rows [lo, hi] (they can't be re-pointed safely)."""
    out = []
    for m in REF.finditer(f):
        if m.group(0).startswith('"') or m.group(1):
            continue
        rows = [int(m.group(3))] + ([int(m.group(5))] if m.group(4) else [])
        if any(not lo <= x <= hi for x in rows):
            out.append(m.group(0))
    return out


def styles(st):
    x = lambda **k: st.xf(**k)
    return {"title": x(sz=16, b=True), "note": x(color=GREY, sz=11, i=True), "band": x(color=WHITE, b=True, fill=NAVY),
            "th": x(b=True, color=WHITE, fill="FF0070C0", align="center"), "lab": x(), "lab_b": x(b=True),
            "lab_i": x(color=GREY, i=True), "cons": x(b=True, fill=CONS), "txt_t": x(color=BLUE),
            "px_t": x(color=BLUE, fmt=PX), "eps_t": x(color=BLUE, fmt=EPS), "mny_t": x(color=BLUE, fmt=MNY),
            "eps_s": x(color=GREY, i=True, fmt=EPS), "mny_s": x(color=GREY, i=True, fmt=MNY),
            "date_t": x(color=BLUE, fmt=DATE), "int_t": x(color=BLUE, fmt="0"), "pct": x(fmt=PCT), "mult": x(fmt=MULT),
            "cnt": x(fmt="0"), "px": x(fmt=PX), "date_l": x(color=GREEN, fmt=DATE), "px_l": x(color=GREEN, fmt=PX),
            "in": x(color=BLUE, fill=YELLOW), "bps": x(fmt=BPS)}


def read_px(model, ticker):
    wb = openpyxl.load_workbook(model, read_only=True, data_only=True)
    if "Px Data" not in wb.sheetnames:
        wb.close()
        return None
    ws, hdr, ccol, guessed, rows = wb["Px Data"], None, None, False, []
    for r, row in enumerate(ws.iter_rows(values_only=True), 1):
        if hdr is None:
            if row and isinstance(row[0], str) and row[0].strip().lower() == "date":
                hdr = r
                names = [str(v).strip().lower() if v is not None else "" for v in row]
                want = f"{ticker.lower()} close"
                ccol, guessed = (names.index(want) + 1, False) if want in names else (2, True)
            continue
        d = row[0] if row else None
        if isinstance(d, datetime) and len(row) >= ccol and isinstance(row[ccol - 1], (int, float)):
            rows.append((r, d.date(), float(row[ccol - 1])))
    wb.close()
    if not rows:
        return None
    return {"col": colname(ccol), "rows": rows, "guessed": guessed, "first": rows[0][0], "last": rows[-1][0]}


def read_variance(model):
    """The user's entries in the old tab's variance block, data rows only: "cells" = {(offset from band row, col): value}
    for their inputs (B-H), "ik" = the same for the variance columns I-K (generated formulas, or their overrides). The
    block ends at the next band ("3. " ... "9. "); with no later band, at the first run of 3 empty rows (warned)."""
    wb = openpyxl.load_workbook(model, read_only=True)
    if TAB not in wb.sheetnames:
        wb.close()
        return None
    band = end = None
    cells, ik, empty, warnings, banded = {}, {}, 0, [], False
    for r, row in enumerate(wb[TAB].iter_rows(max_col=11, values_only=True), 1):
        a = row[0] if row else None
        if band is None:
            if isinstance(a, str) and a.startswith("2. VARIANCE"):
                band = r
            continue
        if isinstance(a, str) and re.match(r"^[3-9]\. ", a):
            end, banded = r, True
            break
        if r < band + 2:
            continue
        vals = {c: row[c - 1] for c in range(1, 12) if c - 1 < len(row) and row[c - 1] not in (None, "")}
        empty = 0 if vals else empty + 1
        if empty == 3:
            end = r - 2
            break
        for c, v in vals.items():
            if 2 <= c <= 8:
                cells[(r - band, c)] = v
            elif c >= 9:
                ik[(r - band, c)] = v
    wb.close()
    if not band:
        return None
    if not banded:
        warnings.append("The old Consensus tab has no band after the variance table, so its end was taken "
                        + (f"at row {end - 1} (3 empty rows follow)" if end else "as the last row") +
                        ": check nothing of yours below it was left out.")
    return {"band": band, "end": end, "cells": cells, "ik": ik, "warnings": warnings}


def mod_quarter_labels(model):
    wb = openpyxl.load_workbook(model, read_only=True)
    out = set()
    if "MOD" in wb.sheetnames:
        for row in wb["MOD"].iter_rows(max_row=15, values_only=True):
            for v in row:
                if isinstance(v, str) and re.match(r"^Q[1-4] \d{2}E?$", v.strip()):
                    out.add(v.strip().rstrip("E"))
    wb.close()
    return out


def blank_consensus(snap):
    """Consensus with the period-based figures blank (period labels unknown); the target consensus still shows."""
    c = snapshots.consensus(snap, None)
    empty = {"mean": None, "low": None, "high": None, "n": None}
    return {**c, "eps": {k: dict(empty) for k in snapshots.CODES}, "rev": {k: dict(empty) for k in snapshots.CODES}}


def build(model, work, ticker, out):
    T = ticker.upper()
    snaps = snapshots.load_all(work)
    if not snaps:
        sys.exit("no snapshots in W/snapshots: run fetch.mjs first")
    snap = snaps[-1]
    asof = date.fromisoformat(snap["asof"])
    F = FM.Firms()
    acts = ratings.actions(snap, F)
    rows, dropped = ratings.latest_by_firm(acts, asof)
    analysts, shops, unknown = ratings.split_types(rows)
    nasdaq_only = ratings.nasdaq_covering(snap, F, rows)
    fye = periods.fye_month(snap)
    warnings = []
    if fye is None:
        warnings.append("Yahoo has no consensus estimates, so the period labels are unknown; estimate columns stay blank.")
        cons = blank_consensus(snap)
    else:
        try:
            cons = snapshots.consensus(snap, fye)
        except ValueError as e:
            warnings.append(f"Consensus periods unreadable ({e}); period labels unknown, consensus estimates left blank.")
            cons = blank_consensus(snap)
    lab = cons["labels"]
    estp = os.path.join(work, "estimates.json")
    est = json.load(open(estp)) if os.path.exists(estp) else {}
    last_action = {r["firm"]: r["date"] for r in rows}
    for firm, f in est.items():                     # this snapshot decides staleness, not the flag stored earlier
        if f.get("date"):
            f["stale"] = ES.is_stale(date.fromisoformat(f["date"]), last_action.get(firm), asof)
    cur = (snap.get("price") or {}).get("currency")
    fcur = (snap["yahoo"].get("financial") or {}).get("financialCurrency")
    cm = "$M" if (fcur or "USD") == "USD" else f"{fcur} M"           # revenue unit: millions, reporting currency
    mixed = bool(fcur and cur and fcur != cur)
    if mixed:
        warnings.append(f"Price is in {cur} but the estimates are in {fcur} (the reporting currency): P/E rows left "
                        "blank. Check whether EPS is per ADR or per share.")
    px = read_px(model, T)
    old = read_variance(model)
    if old:
        warnings += old["warnings"]
    mq = mod_quarter_labels(model)
    if mq and lab.get("q") and lab["q"] not in mq:
        warnings.append(f"Consensus next quarter {lab['q']} is not a MOD column label: check the fiscal calendar.")
    if px is None:
        warnings.append("No Px Data tab (or no closes in it): rating chart and 'close that day' skipped. Run /model-price-history, then rerun.")
    elif px["guessed"]:
        warnings.append(f"Px Data has no '{T} close' header: column B used as the close. Check it.")

    pkg = Package(model)
    have = [s[0] for s in pkg.sheets()]
    old_pos = views = None
    if TAB in have:
        refs = consensus_refs(pkg)
        if refs:
            print(json.dumps({"status": "referenced", "tabs": refs}))
            raise SystemExit(3)
        old_pos, views = have.index(TAB), view_state(pkg)
        pkg.remove_sheet(TAB)
    st = Styles(pkg.text("xl/styles.xml"))
    sty = styles(st)
    sh = Sheet()
    sh.freeze, sh.zoom = "A6", 100
    exp, notes, preserved = {}, {}, {}
    header_noted, stale_refs = [], []        # verify.py: typed numbers explained by a header note; stale (grey) cells

    def put(ref, kind, val, style, want=None, note=None):
        if kind == "s" and (val is None or val == ""):
            return
        sh.set(ref, kind, val, style)
        if kind in ("f", "fa"):
            exp[ref] = want
        if note:
            notes[ref] = note

    widths = {"A": 11, "B": 26, "C": 14, "D": 16, "E": 13, "F": 10, "G": 9, "H": 11, "I": 15, "J": 10, "K": 10,
              "L": 10, "M": 11, "N": 11, "O": 11, "P": 16, "Q": 14, "R": 11, "S": 10, "T": 11, "U": 10, "V": 11}
    sh.widths.update({colnum(c): w for c, w in widths.items()})
    sh.heights[1] = 22

    def band(r, text, cols="ABCDEFGHIJKLMNOP"):
        for c in cols:
            sh.set(f"{c}{r}", "blank", None, sty["band"])
        sh.set(f"A{r}", "s", text, sty["band"])

    # ---------------- header
    price = (snap.get("price") or {}).get("value")
    ptime = (snap.get("price") or {}).get("time")
    put("A1", "s", f"{T} sell-side consensus: ratings, targets, estimates and how they moved", sty["title"])
    put("A2", "s", f"As of {snap['asof']}. Sources: Yahoo Finance (ratings, targets, consensus; yahoo-finance2), "
                   "Nasdaq/Zacks (covering list, extra periods), broker reports in Sellside Research (each broker's own "
                   "estimates). Blue = typed (each has a note), green = link, black = formula, grey italic = stale "
                   "estimate.", sty["note"])
    # House style: "Price:" sits right next to the price (E3, bold); any currency caveat goes after it (G3)
    put("E3", "s", "Price:", sty["lab_b"])
    ccy = (f"{cur}; estimates in {fcur}, the reporting currency: P/E not computed" if mixed else
           f"{cur}; estimates in the reporting currency as the sources give them" if cur and cur != "USD" else "")
    if ccy:
        put("G3", "s", ccy, sty["note"])
    if price is not None:
        put("F3", "n", price, sty["px_t"], note=f"Yahoo regularMarketPrice at fetch ({ptime}), snapshot {snap['asof']}.")
    flags = []
    if unknown:
        flags.append("Unclassified firms (not in the table): " + ", ".join(sorted({u['firm'] for u in unknown})))
    an_dropped = [d for d in dropped if d["type"] in FM.ANALYST and (asof - d["date"]).days <= 1827
                  and d["firm"] not in nasdaq_only]
    if an_dropped:
        flags.append("May have dropped coverage (no action in 12 months): " +
                     ", ".join(f"{d['firm']} ({d['date']})" for d in sorted(an_dropped, key=lambda d: d["firm"])))
    if nasdaq_only:
        flags.append("Covering per Nasdaq but no Yahoo action in 12 months (rating unknown): " + ", ".join(nasdaq_only))
    stale = sorted(f for f, v in est.items() if v.get("stale"))
    if stale:
        flags.append("Stale estimates (grey): " + ", ".join(stale))
    put("A4", "s", " · ".join(flags) if flags else "No flags.", sty["note"])

    # ---------------- 1. broker table
    r = 6
    band(r, BANDS[0])
    hdr = {"n": "#", "firm": "Firm", "type": "Type", "rating": "Rating (their words)", "bucket": "Bucket", "pt": "PT",
           "upside": "Upside", "ldate": "Last action", "lkind": "Action", "eq": f"EPS {lab.get('q') or 'next Q'}",
           "efy": f"EPS {lab.get('fy') or 'FY'}", "efy1": f"EPS {lab.get('fy1') or 'FY+1'}",
           "rq": f"Rev {lab.get('q') or 'next Q'} ({cm})", "rfy": f"Rev {lab.get('fy') or 'FY'} ({cm})",
           "rfy1": f"Rev {lab.get('fy1') or 'FY+1'} ({cm})", "src": "Estimates from"}
    for k, h in hdr.items():
        put(f"{BT[k]}{r + 1}", "s", h, sty["th"])
    sh.heights[r + 1] = 32

    def ev(firm, metric, key):
        return (est.get(firm) or {}).get("values", {}).get(metric, {}).get(lab.get(key) or "")

    def sort_key(a):
        e = ev(a["firm"], "eps", "fy1")
        return (0, -e["value"], a["firm"]) if e else (1, -(a["pt"] or 0), a["firm"])

    nq_rows = [{"firm": n, "type": F.match(n)["type"], "pt": None, "nasdaq_only": True} for n in nasdaq_only]
    table = sorted(analysts + nq_rows, key=sort_key)
    rated = [a for a in table if not a.get("nasdaq_only")]
    r0 = r + 2
    for i, a in enumerate(table):
        rr = r0 + i
        put(f"A{rr}", "n", i + 1, sty["int_t"])
        put(f"B{rr}", "s", a["firm"], sty["lab"], note=NASDAQ_NOTE if a.get("nasdaq_only") else None)
        put(f"C{rr}", "s", TYPE_LABEL[a["type"]], sty["lab"])
        if not a.get("nasdaq_only"):
            put(f"D{rr}", "s", a["to"] or "–", sty["txt_t"],
                note=f"Yahoo upgrade/downgrade history: {a['kind']} on {a['date']} "
                     f"({a['raw']}: {a['from'] or '–'} → {a['to'] or '–'}).")
            put(f"E{rr}", "s", a["bucket"] or "?", sty["lab"])
            if a["pt"]:
                put(f"F{rr}", "n", round(a["pt"], 4), sty["px_t"],
                    note=f"Yahoo: latest price target, set {a['pt_date']}" + (" (split-adjusted)" if a["split_adj"] else "") + ".")
                if price:
                    put(f"G{rr}", "f", f'IF(F{rr}="","",F{rr}/$F$3-1)', sty["pct"], round(a["pt"], 4) / price - 1)
            put(f"H{rr}", "d", serial(a["date"]), sty["date_t"], note=f"Yahoo: {a['kind']} by {a['raw']} on {a['date']}.")
            put(f"I{rr}", "s", a["kind"], sty["lab"])
        fe = est.get(a["firm"]) or {}
        for key, metric, colkey, s_fresh, s_stale in (("q", "eps", "eq", "eps_t", "eps_s"), ("fy", "eps", "efy", "eps_t", "eps_s"),
                                                      ("fy1", "eps", "efy1", "eps_t", "eps_s"), ("q", "revenue", "rq", "mny_t", "mny_s"),
                                                      ("fy", "revenue", "rfy", "mny_t", "mny_s"), ("fy1", "revenue", "rfy1", "mny_t", "mny_s")):
            v = ev(a["firm"], metric, key)
            if v:
                if fe.get("stale"):
                    stale_refs.append(f"{BT[colkey]}{rr}")
                put(f"{BT[colkey]}{rr}", "n", v["value"], sty[s_stale if fe.get("stale") else s_fresh],
                    note=f"{os.path.basename(v['file'])}, line {v['line_no']}: \"{v['raw']}\" "
                         f"({v.get('basis') or 'basis unstated'})" + (". STALE: report older than the firm's last "
                                                                      "action or 90+ days old." if fe.get("stale") else "."))
        if fe.get("date"):
            put(f"P{rr}", "s", f"{fe['date']}" + (" (stale)" if fe.get("stale") else ""),
                sty["lab_i"] if fe.get("stale") else sty["lab"])
    r1 = r0 + max(len(table), 1) - 1
    notes[f"A{r + 1}"] = "Row number. Rows sort by next year's EPS (brokers with a report first), then by price target."
    if table:
        header_noted.append(f"A{r0}:A{r1}")
    rng = lambda c: f"{c}{r0}:{c}{r1}"

    # consensus rows
    rr = r1 + 2
    # House style: repeat the column headers (Type .. Estimates from) right above the consensus rows
    for c in "AB":
        sh.set(f"{c}{rr}", "blank", None, sty["th"])
    for k, h in hdr.items():
        if k not in ("n", "firm"):
            put(f"{BT[k]}{rr}", "s", h, sty["th"])
    sh.heights[rr] = 32
    rr += 1
    crow = {}
    src = f"Yahoo earningsTrend / financialData, snapshot {snap['asof']}"
    for name, key in (("Consensus mean", "mean"), ("Consensus high", "high"), ("Consensus low", "low"), ("# of estimates", "n")):
        crow[key] = rr
        put(f"B{rr}", "s", name, sty["cons"] if key == "mean" else sty["lab_b"])
        v = cons["pt"].get(key)
        if v is not None:
            put(f"F{rr}", "n", v, sty["int_t"] if key == "n" else sty["px_t"],
                note=f"{src}: target {key}" + (" (number of analyst opinions)" if key == "n" else "") + ".")
        for colkey, metric, pkey in (("eq", "eps", "q"), ("efy", "eps", "fy"), ("efy1", "eps", "fy1"),
                                     ("rq", "rev", "q"), ("rfy", "rev", "fy"), ("rfy1", "rev", "fy1")):
            v = cons[metric][pkey].get(key)
            if v is not None:
                s_ = "int_t" if key == "n" else ("eps_t" if metric == "eps" else "mny_t")
                put(f"{BT[colkey]}{rr}", "n", v, sty[s_],
                    note=f"{src}: {'EPS' if metric == 'eps' else f'revenue ({cm})'} {lab.get(pkey)} {key}.")
        rr += 1
    put(f"B{rr}", "s", "Street low vs high", sty["lab_b"])
    for colkey in ("pt", "eq", "efy", "efy1", "rq", "rfy", "rfy1"):
        c = BT[colkey]
        if colkey == "pt":
            hi, lo = cons["pt"]["high"], cons["pt"]["low"]
        else:
            metric = "eps" if colkey.startswith("e") else "rev"
            pkey = {"eq": "q", "efy": "fy", "efy1": "fy1", "rq": "q", "rfy": "fy", "rfy1": "fy1"}[colkey]
            hi, lo = cons[metric][pkey]["high"], cons[metric][pkey]["low"]
        want = (lo / hi - 1) if (hi and lo is not None) else None
        L_, H_ = f"{c}{crow['low']}", f"{c}{crow['high']}"
        put(f"{c}{rr}", "f", f'IF(OR({L_}="",{H_}=""),"",IFERROR({L_}/{H_}-1,""))', sty["pct"], want)
    rr += 1
    pe_col = BT["efy1"]
    for name, key in (("P/E on Street high EPS", "high"), ("P/E on Street low EPS", "low"), ("P/E on consensus EPS", "mean")):
        e = cons["eps"]["fy1"][key]
        put(f"B{rr}", "s", f"{name} ({lab.get('fy1') or 'FY+1'})", sty["lab_b"],
            note=f"Not computed: price and EPS in different currencies (price {cur}, EPS {fcur})." if mixed else None)
        if not mixed:
            put(f"{pe_col}{rr}", "f", f'IF({pe_col}{crow[key]}="","",IFERROR($F$3/{pe_col}{crow[key]},""))',
                sty["mult"], (price / e) if (price and e) else None)
        rr += 1
    rr += 1
    buckets = ["Buy", "Hold", "Sell"] + (["Unrated"] if any(a.get("bucket") == "Unrated" for a in rated) else [])
    for b in buckets:
        put(f"B{rr}", "s", f"Ratings: {b}", sty["lab"])
        put(f"E{rr}", "f", f'COUNTIF({rng("E")},"{b}")', sty["cnt"], sum(1 for a in rated if a["bucket"] == b))
        rr += 1
    pts = [round(a["pt"], 4) for a in rated if a["pt"]]
    put(f"B{rr}", "s", "Average PT (brokers above)", sty["lab"])
    put(f"F{rr}", "f", f'IFERROR(AVERAGE({rng("F")}),"")', sty["px"], (sum(pts) / len(pts)) if pts else None)
    rr += 2
    # rating shops and quant scores
    put(f"B{rr}", "s", "Rating shops and quant scores (not in the counts above)", sty["lab_b"])
    rr += 1
    for k, h in zip("BCDFH", ["Firm", "Type", "Rating / score", "Target / fair value", "Date"]):
        put(f"{k}{rr}", "s", h, sty["th"])
    sh.heights[rr] = 34                                    # wrapped header fits
    rr += 1
    shop_rows = {s["firm"]: {"type": s["type"], "rating": s["to"], "pt": s["pt"], "date": s["date"],
                             "note": f"Yahoo: {s['kind']} on {s['date']}."} for s in shops}
    for firm, f in est.items():
        fm = F.match(firm)
        if fm and fm["type"] in ("rating shop", "quant"):
            rt = next(iter((f["values"].get("rating") or {}).values()), None)
            tg = next(iter((f["values"].get("target") or {}).values()), None)
            shop_rows[firm] = {"type": fm["type"], "rating": rt["value"] if rt else "", "pt": tg["value"] if tg else None,
                               "date": date.fromisoformat(f["date"]),
                               "note": f"{os.path.basename(f['file'])}" + (f", line {rt['line_no']}" if rt else "") + "."}
    for firm in sorted(shop_rows):
        s = shop_rows[firm]
        put(f"B{rr}", "s", firm, sty["lab"])
        put(f"C{rr}", "s", TYPE_LABEL[s["type"]], sty["lab"])
        rt = s["rating"] or "–"
        if re.fullmatch(r"-?\d+(\.\d+)?", str(rt).strip()):   # a numeric score (e.g. 7 of 10) is a number
            put(f"D{rr}", "n", float(rt) if "." in str(rt) else int(rt), sty["txt_t"], note=s["note"])
        else:
            put(f"D{rr}", "s", rt, sty["txt_t"], note=s["note"])
        if s["pt"]:
            put(f"F{rr}", "n", s["pt"], sty["px_t"], note=s["note"])
        put(f"H{rr}", "d", serial(s["date"]), sty["date_t"], note=s["note"])
        rr += 1
    if not shop_rows:
        put(f"B{rr}", "s", "None found (drop Morningstar / CFRA / Argus reports into Sellside Research to fill this).", sty["lab_i"])
        rr += 1

    # ---------------- 2. variance table
    vb = rr + 1
    band(vb, BANDS[1])
    vh = vb + 1
    put(f"B{vh}", "s", f"({cm} except per share; margins and growth in %)", sty["th"])
    for grp, cols in (("Consensus", "CDE"), ("Internal", "FGH"), ("Variance", "IJK")):
        for c, key in zip(cols, ("q", "fy", "fy1")):
            put(f"{c}{vh}", "s", f"{grp} {lab.get(key) or key.upper()}", sty["th"])
    sh.heights[vh] = 32
    if old:
        cells, ik = dict(old["cells"]), dict(old["ik"])
        n_rows = max([off for off, _ in list(cells) + list(ik)] + [1 + len(VAR_ROWS)]) - 1
        lo_, hi_ = old["band"], (old["end"] - 1) if old["end"] else 10 ** 6
    else:
        cells, ik = {(2 + i, 2): t for i, t in enumerate(VAR_ROWS)}, {}
        n_rows = len(VAR_ROWS)

    def keep(ref, v, style):
        """Write the user's cell as they left it (formulas re-pointed if the block moved); returns (kind, content)."""
        kind, content = carry(v)
        if kind in ("f", "fa"):
            raw = content
            if old:
                content = shift_formula(raw, vb - old["band"], lo_, hi_)
                away = outside_refs(raw, lo_, hi_)
                if away:
                    warnings.append(f"Your variance formula in {TAB}!{ref} (={content}) points at {', '.join(away)}, "
                                    "outside the variance table; the rows above it may have moved, so check it.")
            if kind == "fa" and isinstance(v, ArrayFormula) and ":" in str(v.ref or ""):
                warnings.append(f"Your array formula in {TAB}!{ref} spanned {v.ref}; it was carried over into "
                                f"{ref} only: re-enter it over the full range.")
        sh.set(ref, kind, content, style)
        preserved[ref] = [kind, content]
        return kind, content

    for i in range(n_rows):
        off = 2 + i
        rv = vb + off
        label = cells.get((off, 2))
        kinds = {}
        for c in range(2, 9):
            ref = f"{colname(c)}{rv}"
            v = cells.get((off, c))
            style = sty["lab"] if c == 2 else sty["in"]
            if v is None:
                if c > 2 and label is not None:
                    sh.set(ref, "blank", None, style)
                continue
            kinds[c] = keep(ref, v, style)
        for cc, ic, vc in zip("CDE", "FGH", "IJK"):
            ref = f"{vc}{rv}"
            f, bps = var_formula(label, cc, ic, rv)
            stl = sty["bps"] if bps else sty["pct"]
            mine = ik.get((off, colnum(vc)))
            if mine is not None:
                k, content = carry(mine)
                if not (k == "f" and old and shift_formula(content, vb - old["band"], lo_, hi_)
                        in generated_variants(cc, ic, rv)):
                    content = keep(ref, mine, stl)[1]
                    warnings.append(f"You typed over the variance cell {TAB}!{ref} ({content!r} instead of the "
                                    "skill's formula); your cell was kept as is.")
                    continue
            if label is None:
                continue
            a, b = kinds.get(colnum(cc)), kinds.get(colnum(ic))
            if a is None or b is None:
                want = None
            elif a[0] in ("f", "fa") or b[0] in ("f", "fa"):
                sh.set(ref, "f", f, stl)                         # inputs are the user's formulas: verify skips the value
                continue
            elif a[0] == "n" and b[0] == "n":
                want = (b[1] - a[1]) * 10000 if bps else ((b[1] / a[1] - 1) if a[1] else None)
            else:
                want = None                                      # text in an input: IFERROR gives ""
            put(ref, "f", f, stl, want)
    rr = vb + 2 + n_rows + 1

    # ---------------- 3. chart (data helper in R-V)
    cb = rr
    band(cb, BANDS[2])
    lg = ratings.log(acts, asof)
    chart_xml = None
    log_start = cb + 27
    l0, l1 = log_start + 2, log_start + 1 + len(lg)
    if px:
        start = asof - timedelta(days=round(365.25 * ratings.LOG_YEARS))
        days = [x for x in px["rows"] if start <= x[1] <= asof]
        avg = ratings.avg_pt(acts, [d for _, d, _ in days])
        h0 = cb + 1
        for k, h in zip("RSTUV", ["Date", f"{T} close", "Average PT", "Upgrade", "Downgrade"]):
            put(f"{k}{h0}", "s", h, sty["th"])
        sh.heights[h0] = 34                                # house style
        notes[f"T{h0}"] = ("Computed by the skill from the rating log: each day, the mean of each covering analyst "
                           "firm's latest price target (targets older than 12 months dropped; split-adjusted).")
        ups = {a["date"] for a in lg if a["kind"] == "Upgrade"}
        downs = {a["date"] for a in lg if a["kind"] == "Downgrade"}
        cat_vals, cl, av, upv, dnv = [], [], [], [], []
        for i, ((pr, d, c), a) in enumerate(zip(days, avg)):
            hr = h0 + 1 + i
            put(f"R{hr}", "f", f"'Px Data'!$A${pr}", sty["date_l"], serial(d))
            put(f"S{hr}", "f", f"'Px Data'!${px['col']}${pr}", sty["px_l"], c)
            if a is not None:                                   # blank, never NA(): only empty cells break the line
                put(f"T{hr}", "n", round(a, 4), sty["px_t"])
            if lg:
                put(f"U{hr}", "f", f'IF(COUNTIFS($A${l0}:$A${l1},R{hr},$C${l0}:$C${l1},"Upgrade")>0,S{hr},NA())',
                    sty["px"], c if d in ups else None)
                put(f"V{hr}", "f", f'IF(COUNTIFS($A${l0}:$A${l1},R{hr},$C${l0}:$C${l1},"Downgrade")>0,S{hr},NA())',
                    sty["px"], c if d in downs else None)
            cat_vals.append(serial(d)); cl.append(c); av.append(round(a, 4) if a is not None else None)
            upv.append(c if d in ups else None); dnv.append(c if d in downs else None)
        if days:
            e0, e1 = h0 + 1, h0 + len(days)
            header_noted.append(f"T{e0}:T{e1}")
            ref = lambda c: f"'{TAB}'!${c}${e0}:${c}${e1}"
            series = [{"name": f"{T} close", "ref": ref("S"), "vals": cl, "color": charts.CLOSE},
                      {"name": "Average price target", "ref": ref("T"), "vals": av, "color": charts.AVG, "dash": True}]
            if lg:
                series += [{"name": "Upgrade", "ref": ref("U"), "vals": upv, "color": charts.UP, "marker": "triangle"},
                           {"name": "Downgrade", "ref": ref("V"), "vals": dnv, "color": charts.DOWN, "marker": "diamond"}]
            chart_xml = charts.rating_chart(f"{T}: price, average target and rating changes", (ref("R"), cat_vals), series)
            put(f"A{cb + 25}", "s", "Green triangles = upgrades, red diamonds = downgrades, at that day's close. Targets "
                                   "set before a stock split are divided by the split ratio, like the closes. Chart data "
                                   "in columns R-V.", sty["note"])
        else:
            warnings.append(f"Px Data has no closes in the last {ratings.LOG_YEARS} years: rating chart skipped.")
            put(f"A{cb + 1}", "s", "No closes in Px Data for the last 5 years: chart skipped.", sty["note"])
    else:
        put(f"A{cb + 1}", "s", "No Px Data tab in this model: run /model-price-history, then rerun /model-consensus "
                               "to add this chart.", sty["note"])

    # ---------------- 4. log
    band(log_start, BANDS[3])
    for k, h in zip("ABCDEFGHI", ["Date", "Firm", "Action", "Rating from", "Rating to", "PT from", "PT to",
                                  "PT change", "Close that day"]):
        put(f"{k}{log_start + 1}", "s", h, sty["th"])
    sh.heights[log_start + 1] = 17                         # house style
    split_txt = ", ".join(f"{s['ratio']:g}:1 on {s['date']}" for s in snap.get("splits") or [])
    notes[f"A{log_start + 1}"] = ("Yahoo upgrade/downgrade history (New York dates)."
                                  + (f" Targets before each split divided by its ratio ({split_txt})." if split_txt else ""))
    px_rng = (f"'Px Data'!${px['col']}${px['first']}:${px['col']}${px['last']}",
              f"'Px Data'!$A${px['first']}:$A${px['last']}") if px else None
    for i, a in enumerate(lg):
        lr = l0 + i
        put(f"A{lr}", "d", serial(a["date"]), sty["date_t"])
        put(f"B{lr}", "s", a["firm"], sty["lab"])
        put(f"C{lr}", "s", a["kind"], sty["lab"])
        put(f"D{lr}", "s", a["from"], sty["txt_t"])
        put(f"E{lr}", "s", a["to"], sty["txt_t"])
        if a["pt_from"]:
            put(f"F{lr}", "n", round(a["pt_from"], 4), sty["px_t"])
        if a["pt_to"]:
            put(f"G{lr}", "n", round(a["pt_to"], 4), sty["px_t"])
        put(f"H{lr}", "f", f'IF(OR(F{lr}="",G{lr}=""),"",G{lr}/F{lr}-1)', sty["pct"],
            (round(a["pt_to"], 4) / round(a["pt_from"], 4) - 1) if a["pt_from"] and a["pt_to"] else None)
        if px:
            prior = [c for _, d, c in px["rows"] if d <= a["date"]]
            put(f"I{lr}", "f", f'IFERROR(INDEX({px_rng[0]},MATCH(A{lr},{px_rng[1]},1)),"")', sty["px"],
                prior[-1] if prior else None)
    if lg:
        header_noted.append(f"A{l0}:I{l1}")
    rr = max(l1, log_start + 1) + 2

    # ---------------- 5. snapshots
    band(rr, BANDS[4], "ABCDEFGHIJKLMNOPQ")
    sh_hdr = ["Snapshot", "Period", "EPS mean", "EPS low", "EPS high", "# EPS", f"Rev mean ({cm})", "Rev low", "Rev high",
              "# Rev", "Revisions up (30d)", "Revisions down (30d)", "Mean PT", "Buy", "Hold", "Sell", "Source"]
    for c, h in zip("ABCDEFGHIJKLMNOPQ", sh_hdr):
        put(f"{c}{rr + 1}", "s", h, sty["th"])
    sh.heights[rr + 1] = 51                                # three-line wrapped headers
    notes[f"A{rr + 1}"] = "One block per run, from W/snapshots/<date>.json (Yahoo; Nasdaq/Zacks only for periods Yahoo lacks)."
    sr = rr + 2
    keys = ["eps_mean", "eps_low", "eps_high", "eps_n", "rev_mean", "rev_low", "rev_high", "rev_n", "up30", "down30",
            "mean_pt", "buy", "hold", "sell"]
    fmts = ["eps_t", "eps_t", "eps_t", "int_t", "mny_t", "mny_t", "mny_t", "int_t", "int_t", "int_t", "px_t", "int_t",
            "int_t", "int_t"]
    for s in snaps:
        try:
            srows = snapshots.rows(s, periods.fye_month(s) or fye)
        except ValueError as e:
            warnings.append(f"Snapshot {s['asof']} skipped in the snapshot block: {e}.")
            continue
        for row in srows:
            put(f"A{sr}", "d", serial(date.fromisoformat(row["asof"])), sty["date_t"])
            put(f"B{sr}", "s", row["period"], sty["lab"])
            for c, k, f in zip("CDEFGHIJKLMNOP", keys, fmts):
                if row[k] is not None:
                    put(f"{c}{sr}", "n", row[k], sty[f])
            put(f"Q{sr}", "s", row["source"], sty["lab_i"])
            sr += 1

    if sr > rr + 2:
        header_noted.append(f"A{rr + 2}:P{sr - 1}")
    sh.comments = notes
    write_parts(pkg, st, sh, chart_xml, (0, cb, 16, 23))
    if old_pos is not None:
        put_back(pkg, old_pos, views)
    pkg.save(out)
    import notebox
    notebox.fix(out, out, since=model)
    json.dump({"expected": exp, "preserved": preserved, "header_noted": header_noted, "stale": stale_refs,
               "user": f"A{vb}:K{vb + 1 + n_rows}", "variance_band": vb, "carried_over": bool(old)}, open(os.path.join(work, "layout.json"), "w"), indent=0, default=str)
    try:
        changes = snapshots.changes(snaps[-2], snap, fye) if len(snaps) > 1 and fye else []
    except ValueError as e:
        changes = []
        warnings.append(f"Changes since the last snapshot not computed: {e}.")
    summary = {"asof": snap["asof"], "labels": lab, "analysts": len(rated), "nasdaq_only": len(nasdaq_only),
               "with_estimates": sorted(f for f in est if F.match(f) and F.match(f)["type"] in FM.ANALYST),
               "stale": stale, "unknown_firms": sorted({u["firm"] for u in unknown}),
               "unknown_grades": sorted({a["to"] for a in rated if a["bucket"] is None}),
               "dropped": [d["firm"] for d in an_dropped], "log_rows": len(lg), "snapshots": len(snaps),
               "chart": chart_xml is not None, "variance_carried_over": bool(old), "warnings": warnings,
               "changes": changes +
                          [f"{a['firm']}: {a['kind']} {a['from']} → {a['to']} on {a['date']}" for a in lg
                           if len(snaps) > 1 and a["date"] > date.fromisoformat(snaps[-2]["asof"])
                           and a["kind"] in ("Upgrade", "Downgrade", "Initiation")] +
                          [f"{a['firm']}: PT {a['pt_from']:.2f} → {a['pt_to']:.2f} on {a['date']}" for a in lg
                           if len(snaps) > 1 and a["date"] > date.fromisoformat(snaps[-2]["asof"])
                           and a["kind"] == "Target change"]}
    return summary


def write_parts(pkg, st, sh, chart_xml, box):
    pkg.put("xl/styles.xml", st.render())
    pkg.content_default("vml", "application/vnd.openxmlformats-officedocument.vmlDrawing")
    nxt = next_vml_id(pkg)
    part = pkg.add_sheet(TAB, "")
    drid = lrid = None
    if chart_xml:
        dn = pkg.free("xl/drawings/drawing{}.xml")
        dpart = f"xl/drawings/drawing{dn}.xml"
        cn = pkg.free("xl/charts/chart{}.xml")
        cpart = f"xl/charts/chart{cn}.xml"
        pkg.put(cpart, chart_xml)
        pkg.content_override(cpart, CT["chart"])
        rid = pkg.attach(dpart, "chart", cpart)
        col, row, ncols, nrows = box
        pkg.put(dpart, '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
                       '<xdr:wsDr xmlns:xdr="http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing" '
                       'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
                       + anchor(col, row, 2, "Rating history", rid, ncols, nrows) + "</xdr:wsDr>")
        pkg.content_override(dpart, CT["drawing"])
        drid = pkg.attach(part, "drawing", dpart)
    if sh.comments:
        cn = pkg.free("xl/comments{}.xml")
        vn = pkg.free("xl/drawings/vmlDrawing{}.vml")
        cx, vml = comments_parts(sh.comments, nxt)
        pkg.put(f"xl/comments{cn}.xml", cx)
        pkg.put(f"xl/drawings/vmlDrawing{vn}.vml", vml)
        lrid = pkg.attach(part, "vml", f"xl/drawings/vmlDrawing{vn}.vml")
        pkg.attach(part, "comments", f"xl/comments{cn}.xml", CT["comments"])
    pkg.put(part, sh.xml(drid, lrid))
    pkg.finish()


def anchor(col, row, nid, name, rid, ncols, nrows):
    return (f'<xdr:twoCellAnchor editAs="oneCell"><xdr:from><xdr:col>{col}</xdr:col><xdr:colOff>0</xdr:colOff>'
            f'<xdr:row>{row}</xdr:row><xdr:rowOff>0</xdr:rowOff></xdr:from><xdr:to><xdr:col>{col + ncols}</xdr:col>'
            f'<xdr:colOff>0</xdr:colOff><xdr:row>{row + nrows}</xdr:row><xdr:rowOff>0</xdr:rowOff></xdr:to>'
            '<xdr:graphicFrame macro="">'
            f'<xdr:nvGraphicFramePr><xdr:cNvPr id="{nid}" name="{name}"/><xdr:cNvGraphicFramePr/></xdr:nvGraphicFramePr>'
            '<xdr:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/></xdr:xfrm><a:graphic>'
            '<a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/chart">'
            '<c:chart xmlns:c="http://schemas.openxmlformats.org/drawingml/2006/chart" '
            f'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" r:id="{rid}"/>'
            "</a:graphicData></a:graphic></xdr:graphicFrame><xdr:clientData/></xdr:twoCellAnchor>")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--ticker", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    print(json.dumps(build(a.model, a.work, a.ticker, a.out), indent=1, default=str))
