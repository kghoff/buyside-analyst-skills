"""Step 3 - build the NON-GAAP METRICS section from candidates.json + plan.json.

usage: python3 ng_build.py --model <model.xlsx> --work <work_dir> --plan <plan.json> --out <model_out.xlsx> [--replace]

The plan (written by the agent after reading inventory.md) decides: which metrics, the rows of each bridge
(start link / grouped adjustment rows / links to existing model rows / end), the EPS block, split factors,
and which years use restated comparatives. This script does the mechanical part:
  - inserts the section before `insert_before` (formulas below are shifted, nothing else moves)
  - quarters typed from each period's own release (Q4 typed too), FY = SUM(Q1:Q4) when all four exist,
    otherwise FY typed from the twelve-month column
  - a provenance note on every cell; the user's colours (typed/reported = blue, links = green, formulas = black)
Writes <work>/build_log.json (every judgment-relevant event) for the report."""
import argparse, json, os, re
from copy import copy
import openpyxl
from openpyxl.utils import get_column_letter as L
from xlmodel import (PeriodMap, Evaluator, find_row, section_bounds, sections, insert_rows, delete_rows, norm, note,
                     set_font_color, color_for, number_expr, fmt_num, BLUE, GREEN, BLACK)
from ng_extract import period_of
from openpyxl.styles import Color, PatternFill
SUB_FILL = PatternFill("solid", fgColor=Color(theme=3, tint=0.249977111117893))   # same as /model-ratios's sections

TYPE_RANK = {"release": 0, "deck": 1, "event": 2, "10-Q": 3, "10-K": 3, "other": 4}
order = lambda k: (int(k[3:]), 5 if k.startswith("FY") else int(k[1]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True); ap.add_argument("--work", required=True); ap.add_argument("--plan", required=True)
    ap.add_argument("--out", required=True); ap.add_argument("--replace", action="store_true")
    a = ap.parse_args()
    plan = json.load(open(a.plan)); C = json.load(open(os.path.join(a.work, "candidates.json")))["candidates"]
    wb = openpyxl.load_workbook(a.model); ws = wb[wb.sheetnames[0]]
    log = []
    title = plan.get("section_title", "NON-GAAP METRICS")
    existing = section_bounds(ws, title)
    if existing:
        if not a.replace: raise SystemExit(f"'{title}' already exists (row {existing[0]}). Re-run with --replace to rebuild it.")
        delete_rows(ws, existing[0], existing[1] - existing[0]); log.append(f"Replaced the existing {title} section.")
    pm = PeriodMap(ws)
    # ---------------- reference rows (styles + links) - located before inserting
    IS = "INCOME STATEMENT"
    style_rows = {k: find_row(ws, v, IS) for k, v in plan.get("style_from", {"start": "^gross profit", "item": "r&d", "end": "^gross profit",
                                                                              "shares": "shares, diluted", "eps": "eps, diluted"}).items()}
    hdr_row = section_bounds(ws, IS)[0]
    # ---------------- layout
    layout = [("title", None, None), ("blank", None, None)]
    for m in plan["metrics"]:
        for r in m["rows"]: layout.append((r["role"], m, r))
        layout.append(("blank", None, None))
    eps = plan.get("eps")
    if eps:
        for r in eps["rows"]: layout.append((r["role"], {"key": "eps"}, r))
        layout.append(("blank", None, None))
    at = section_bounds(ws, plan["insert_before"])[0]
    insert_rows(ws, at, len(layout))
    for k in style_rows:
        if style_rows[k] and style_rows[k] >= at: style_rows[k] += len(layout)
    ws = ws; ev = Evaluator(ws)
    maxc = ws.max_column
    rowof = {}
    for i, (role, m, r) in enumerate(layout):
        rr = at + i
        src = {"title": hdr_row, "blank": None, "start": style_rows["start"], "end": style_rows["end"], "link": style_rows["item"],
               "item": style_rows["item"], "sum": style_rows["end"], "shares": style_rows["shares"], "eps": style_rows["eps"]}.get(role)
        for c in range(1, maxc + 1):
            ws.cell(rr, c)._style = copy(ws.cell(src, c)._style) if src else copy(ws.cell(rr, c)._style)
            if role != "title": ws.cell(rr, c).value = None
        if role == "title":
            ws.cell(rr, 1).value = title; ws.cell(rr, 2).value = None; ws.cell(rr, 3).value = ws.cell(hdr_row, 3).value
            for c in range(4, maxc + 1): ws.cell(rr, c).value = None
            for c in range(1, maxc + 1): ws.cell(rr, c).fill = SUB_FILL      # the user's lighter sub-section header
        elif r:
            ws.cell(rr, 2).value = r["label"]; ws.cell(rr, 3).value = r.get("units", "$ M")
            rowof[(m["key"], r["label"])] = rr
    # ---------------- candidates
    cand = {}
    for c in C: cand.setdefault((c["metric"], c["period"]), []).append(c)
    restated = {(x["metric"], x["fiscal_year"] % 100) for x in plan.get("prefer_restated", [])}
    excl = {(x["metric"], x["period"]) for x in plan.get("exclude", [])}
    def pick(metric, key):
        if (metric, key) in excl: return None
        cs = [c for c in cand.get((metric, key), []) if c.get("start_matches_model") is not False]
        if not cs: return None
        pref = (metric, int(key[3:])) in restated
        return sorted(cs, key=lambda c: ((c["vintage"] == "current") if pref else (c["vintage"] != "current"), TYPE_RANK.get(c["type"], 9)))[0]
    def where(c):
        b = os.path.basename(c["source"])
        col = {"current": "", "comparative": " - prior-year comparative column"}[c["vintage"]]
        if c["basis"] == "FY" and not c["period"].startswith("FY") is False: col += " (twelve-month column)" if c["basis"] == "FY" else ""
        return f"{b}" + (f", page {c['page']}" if c.get("page") else "") + f" (md line ~{c['line']}){col}"
    def split(c):
        f = 1; sp = period_of(c["source"]) or c["period"]
        for s in plan.get("share_splits", []):
            if order(sp) <= order(s["through_period"]): f *= s["factor"]
        return f
    keys = sorted({pm.key(c) for c in pm.per if c not in pm.estimate}, key=order)
    def model_link(spec):
        return find_row(ws, spec["label"], spec.get("section", IS))
    def put(rr, c, v, note_text, input_row=False):
        cell = ws.cell(rr, c); cell.value = v
        set_font_color(cell, color_for(v, input_row))
        if note_text: note(cell, note_text)
    # ---------------- metric bridges
    filled, lines_in = {}, {}
    for m in plan["metrics"]:
        mk = m["key"]; rows = m["rows"]
        items_rows = [r for r in rows if r["role"] in ("item", "link")]
        start = next(r for r in rows if r["role"] == "start"); end = next(r for r in rows if r["role"] == "end")
        srow, erow = rowof[(mk, start["label"])], rowof[(mk, end["label"])]
        gaap_r = model_link(start["link"])
        def assign(items):
            out = {r["label"]: [] for r in items_rows}
            for lab, v, ln in items:
                tgt = next((r for r in items_rows if any(re.search(p, norm(lab)) for p in r.get("match", []))), None)
                if tgt is None: raise SystemExit(f"{mk}: no row matches adjustment line '{lab}'. Add a 'match' pattern to plan.json.")
                out[tgt["label"]].append((lab, v, ln))
            return out
        def write_col(c, key, cnd, fy_typed=False):
            put(srow, c, f"={L(c)}{gaap_r}", f"Links to the model's '{ws.cell(gaap_r, 2).value.strip()}' row (row {gaap_r}). {where(cnd)} shows {fmt_num(cnd['start'])}.")
            grouped = assign(cnd["items"])
            for r in items_rows:
                rr = rowof[(mk, r["label"])]; its = grouped[r["label"]]
                lines_in.setdefault((mk, r["label"]), set()).update(lab for lab, _, _ in its)
                rel = sum(v for _, v, _ in its)
                if r["role"] == "link":
                    lr = model_link(r["link"]); sign = r["link"].get("sign", 1)
                    f = f"={'-' if sign < 0 else ''}{L(c)}{lr}"
                    mv = ev.v(ws.cell(lr, c).coordinate)
                    if isinstance(mv, (int, float)) and abs(mv * sign - rel) <= 0.15:
                        put(rr, c, f, f"Links to '{ws.cell(lr, 2).value.strip()}' (row {lr}){' x -1' if sign < 0 else ''}. {where(cnd)} shows {fmt_num(rel)} - matches.")
                    else:
                        put(rr, c, number_expr([v for _, v, _ in its]), f"Source: {where(cnd)}\nTyped: the model's '{ws.cell(lr, 2).value.strip()}' row shows {mv}, the reconciliation shows {fmt_num(rel)}.", True)
                        log.append(f"{mk} {key} {r['label']}: model row disagrees with the release ({mv} vs {fmt_num(rel)}) - typed the release value.")
                else:
                    txt = f"Source: {where(cnd)}"
                    if its: txt += "\nComponents:\n" + "\n".join(f"  {lab}: {fmt_num(v)}" for lab, v, _ in its)
                    if fy_typed: txt += "\nNot every quarter of this year was reconciled, so the full year is typed from the twelve-month column."
                    put(rr, c, number_expr([v for _, v, _ in its]), txt, True)
            parts = "+".join(f"{L(c)}{rowof[(mk, r['label'])]}" for r in [start] + items_rows)
            put(erow, c, "=" + parts, f"Reported '{cnd['end_label']}': {fmt_num(cnd['end'])} ({where(cnd)}).")
            filled[(mk, key)] = cnd
        for key in keys:
            if key.startswith("FY"): continue
            cnd = pick(mk, key)
            if cnd: write_col(pm.by_key(key), key, cnd)
        for key in [k for k in keys if k.startswith("FY")]:
            c = pm.by_key(key); yy = key[3:]; qs = [f"Q{q} {yy}" for q in (1, 2, 3, 4)]
            rep = pick(mk, key)
            if all((mk, q) in filled for q in qs):
                put(srow, c, f"={L(c)}{gaap_r}", f"Links to the model's '{ws.cell(gaap_r, 2).value.strip()}' row (row {gaap_r}).")
                for r in items_rows:
                    rr = rowof[(mk, r["label"])]
                    if r["role"] == "link" and all(isinstance(ws.cell(rr, pm.by_key(q)).value, str) and re.fullmatch(r"=-?[A-Z]+\d+", ws.cell(rr, pm.by_key(q)).value) for q in qs):
                        lr = model_link(r["link"]); sign = r["link"].get("sign", 1)
                        put(rr, c, f"={'-' if sign < 0 else ''}{L(c)}{lr}", f"Links to '{ws.cell(lr, 2).value.strip()}' (row {lr}).")
                    else:
                        put(rr, c, f"=SUM({L(pm.by_key(qs[0]))}{rr}:{L(pm.by_key(qs[3]))}{rr})", "Sum of Q1-Q4.")
                parts = "+".join(f"{L(c)}{rowof[(mk, r['label'])]}" for r in [start] + items_rows)
                put(erow, c, "=" + parts, f"Reported full-year '{rep['end_label']}': {fmt_num(rep['end'])} ({where(rep)})." if rep else "No full-year figure reported to compare.")
                filled[(mk, key)] = rep or {"end": None}
            elif rep:
                write_col(c, key, rep, fy_typed=True); log.append(f"{mk} {key}: typed from the twelve-month column (not all quarters reconciled).")
    # ---------------- EPS block
    if eps:
        R = {r["role"] + ":" + r.get("id", ""): rowof[("eps", r["label"])] for r in eps["rows"]}
        ni_metric = eps["net_income_metric"]
        ni_end = rowof[(ni_metric, next(r for r in next(m for m in plan["metrics"] if m["key"] == ni_metric)["rows"] if r["role"] == "end")["label"])]
        for key in keys:
            if (ni_metric, key) not in filled: continue
            c = pm.by_key(key)
            put(R["link:ni"], c, f"={L(c)}{ni_end}", "Links to Non-GAAP Net Income above.")
            if "item:ifconv" in R:            # optional: only companies with convertible notes need the add-back row
                ic = pick("if-converted add-back", key)
                if ic: put(R["item:ifconv"], c, ic["value"], f"Source: {where(ic)}\n'{ic['label']}' (if-converted add-back)", True)
                else: put(R["item:ifconv"], c, 0, "No if-converted add-back reported for this period.", True)
                put(R["sum:ni_eps"], c, f"={L(c)}{R['link:ni']}+{L(c)}{R['item:ifconv']}", None)
            elif "item:partsec" in R:         # optional: two-class EPS companies (unvested restricted stock shares in earnings)
                ps, nir = model_link({"label": "participating securities"}), model_link({"label": "^net income$"})
                put(R["item:partsec"], c, f"=IFERROR({L(c)}{R['link:ni']}*{L(c)}{ps}/{L(c)}{nir},0)",
                    f"Non-GAAP net income x the GAAP share allocated to participating securities (row {ps} / row {nir}). "
                    "The company does not print the allocation on adjusted earnings; 0 where the GAAP allocation is 0.")
                put(R["sum:ni_eps"], c, f"={L(c)}{R['link:ni']}+{L(c)}{R['item:partsec']}", None)
            else:
                put(R["sum:ni_eps"], c, f"={L(c)}{R['link:ni']}", "Equals non-GAAP net income: no convertible notes, so no if-converted add-back.")
            sh = pick("non-gaap diluted shares", key)
            if sh:
                f = split(sh)
                put(R["shares:"], c, f"={fmt_num(sh['value'])}*{f}" if f != 1 else sh["value"],
                    f"Source: {where(sh)}\n'{sh['label']}'" + (f"\nPre-split count x{f} (stock split) so EPS is comparable." if f != 1 else ""), True)
                rep = pick("reported non-gaap eps", key)
                put(R["eps:"], c, f"={L(c)}{R['sum:ni_eps']}/{L(c)}{R['shares:']}",
                    f"Reported: {fmt_num(rep['value'])} per share ({where(rep)})" + (f", i.e. {fmt_num(rep['value'] / split(rep))} per post-split share" if split(rep) != 1 else "") if rep else None)
                ws.cell(R["eps:"], c).number_format = '"$"#,##0.00_);\\("$"#,##0.00\\)'
    # ---------------- row-label notes: what the row is and every reconciliation line grouped into it
    for m in plan["metrics"] + ([{"key": "eps", "rows": eps["rows"]}] if eps else []):
        for r in m["rows"]:
            rr = rowof[(m["key"], r["label"])]; role = r["role"]
            if role == "start": txt = f"Company's GAAP starting line, linked to the model's '{ws.cell(model_link(r['link']), 2).value.strip()}' row."
            elif role == "end": txt = "Non-GAAP total = the rows above. Each period's note shows the company's reported figure; ng_verify checks they agree."
            elif m["key"] == "eps" and r.get("id") == "partsec": txt = ("Two-class EPS: the slice of non-GAAP net income allocated to unvested restricted stock, "
                                                                         "at the same share as the GAAP allocation (model row 'Earnings Allocated to Participating Securities' / Net Income).")
            elif m["key"] == "eps": txt = {"link": "Non-GAAP net income from the bridge above.", "item": "Interest on convertible notes added back for diluted EPS (if-converted method); 0 where none was reported.",
                                          "sum": "Non-GAAP net income used for diluted EPS.", "shares": "Diluted shares the company used for non-GAAP EPS (split-adjusted where noted).",
                                          "eps": "Non-GAAP diluted EPS = net income for diluted EPS / diluted shares. Each period's note shows the reported figure."}.get(role, "")
            else:
                got = sorted(lines_in.get((m["key"], r["label"]), set()))
                txt = ("Links to the model's own row where it equals the reconciliation line; otherwise the release value is typed. " if role == "link" else "") + \
                      ("Reconciliation lines grouped here:\n" + "\n".join(f"  {x}" for x in got) if got else "No reconciliation line has fallen in this row yet.")
            if txt: note(ws.cell(rr, 2), txt)
    wb.calculation.fullCalcOnLoad = True
    import safe_save; safe_save.safe_save(wb, a.model, a.out)   # never openpyxl's save: it drops the user's text boxes / shapes
    import modfill; modfill.fix(a.out, a.out)   # the user's MOD fill convention (quarters plain, years grey), every save
    import notebox; notebox.fix(a.out, a.out)   # note boxes open readable (none squashed next to spacer / hidden columns), every save
    json.dump({"log": log, "section_rows": [at, at + len(layout) - 1], "rowof": {f"{k[0]}|{k[1]}": v for k, v in rowof.items()}},
              open(os.path.join(a.work, "build_log.json"), "w"), indent=1)
    print(f"section inserted at row {at} ({len(layout)} rows); bridges filled: {len(filled)}; log items: {len(log)}")


if __name__ == "__main__":
    main()
