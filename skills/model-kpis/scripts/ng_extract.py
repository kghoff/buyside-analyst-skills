"""Step 1 - find every non-GAAP reconciliation in the company's source folder and turn it into candidates.

usage: python3 ng_extract.py --src "<TICKER>/<source folder>" --model <model.xlsx> --work <work_dir>

- Walks the WHOLE source folder (its name varies). Uses .md files; lists PDFs that have no .md twin.
- Every file is grepped for 'non-gaap' / 'adjusted'; files with hits are parsed for reconciliation blocks:
    a row 'GAAP <metric>' ... adjustment rows ... 'Non-GAAP <metric>' / 'Adjusted <metric>' (or 'Adjusted EBITDA' after 'GAAP net income')
  plus non-GAAP share counts and the convertible-note if-converted add-back.
- Each block column is assigned to a period by matching its GAAP starting value to the model's GAAP row
  (quarter, full year), so we never rely on column order alone.
Writes <work>/sources.json, <work>/candidates.json, <work>/inventory.md"""
import argparse, json, os, re, glob
import openpyxl
from mdtable import table_rows, page_of, restatement_bridges
from xlmodel import PeriodMap, Evaluator, find_row, norm

FOOT = re.compile(r"\s*(\(\d+\)|\*+|\(\d+\)\s*\(\d+\))\s*")


def clean(lab): return FOOT.sub(" ", lab).replace("’", "'").strip()


def metric_of(text):
    t = norm(clean(text))
    t = re.sub(r"^(gaap|u\.s\. gaap|reported|as reported|non-gaap|adjusted)\s+", "", t)
    t = t.replace("income (loss)", "income").replace("net loss", "net income").replace("operating loss", "operating income") \
         .replace("(loss)", "").replace("gross margin", "gross profit")
    return re.sub(r"\s+", " ", t).strip()


DOC_TYPES = [("call", r"\bcalls?\b|transcript"), ("release", r"release|press|earnings"), ("deck", r"deck|presentation|slides"),
             ("event", r"event|conference|investor day"), ("10-K", r"10-k"), ("10-Q", r"10-q")]


# /collect-documents's category folders (the Markdown sits in <Category>/_md/)
CATEGORY_TYPES = {"press releases": "release", "investor decks": "deck", "investor events": "event", "earnings calls": "call",
                  "10-ks": "10-K", "10-qs": "10-Q", "segment recasts": "recast"}


def classify_doc(path):
    parts = [x.lower() for x in os.path.normpath(path).split(os.sep)]
    for x in reversed(parts[:-1]):
        if x in CATEGORY_TYPES: return CATEGORY_TYPES[x]
    p = path.lower()
    for where in (os.path.basename(p), os.path.dirname(p)):           # file name first: 'Earnings Calls/x call.md' is a call
        for t, pat in DOC_TYPES:
            if re.search(pat, where): return t
    return "other"


def period_of(path):
    b = os.path.basename(path)
    m = re.search(r"\b20(\d\d) Q([1-4])\b", b)          # /collect-documents: "2024 Q3 DXCM release", "DXCM 2024 Q3 10-Q"
    if m: return f"Q{m.group(2)} {m.group(1)}"
    m = re.search(r"\bQ([1-4]) ?(\d{2})(?![\d-])", b) or re.search(r"\b([1-4])Q ?(\d{2})\b", b)   # older "Q3 24 ..."
    if m: return f"Q{m.group(1)} {m.group(2)}"
    m = re.search(r"\b(20\d\d) 10-K\b", b)
    if m: return f"FY {int(m.group(1)) % 100:02d}"
    return None


def discover(src):
    md = sorted(glob.glob(os.path.join(src, "**", "*.md"), recursive=True))
    stems = {os.path.splitext(os.path.basename(p))[0] for p in md}
    pdf_only = [p for p in glob.glob(os.path.join(src, "**", "*.pdf"), recursive=True) if os.path.splitext(os.path.basename(p))[0] not in stems]
    out = []
    for p in md:
        if os.path.basename(p).startswith("_"): continue
        t = open(p, encoding="utf-8", errors="ignore").read()
        hits = len(re.findall(r"non-gaap|adjusted ebitda|adjusted (operating|net|gross|eps|diluted)", t, re.I))
        out.append({"path": p, "type": classify_doc(p), "period": period_of(p), "hits": hits, "bytes": len(t)})
    return out, pdf_only


EXTRAS = ("non-gaap diluted shares", "if-converted add-back", "reported non-gaap eps")


def blocks(rows):
    """yield (metric, rows) for each reconciliation block, plus share rows and if-converted add-backs"""
    out, cur = [], None
    for i, (ln, lab, v) in enumerate(rows):
        l = norm(clean(lab))
        start = re.match(r"^(gaap|u\.s\. gaap|reported|as reported) ", l) and v and "per share" not in l and "used for diluted" not in l \
                and "shares" not in l and "margin" not in l
        if start:
            cur = {"start_metric": metric_of(lab), "rows": [(ln, lab, v)]}; continue
        if cur is None: continue
        if l.startswith("gaap") and ("used for diluted" in l or "per share" in l):
            cur = None; continue                                    # if-converted / per-share sub-tables are handled separately
        cur["rows"].append((ln, lab, v))
        end_m = re.match(r"^(non-gaap|adjusted) ", l) or l in ("ebitda",)
        if end_m and v:
            m = metric_of(lab)
            if m == cur["start_metric"] or ("ebitda" in m and cur["start_metric"].startswith("net income")):
                key = ("adjusted ebitda" if "ebitda" in m else "non-gaap " + m)
                out.append((key, cur["rows"])); cur = None
            elif "used for diluted" in l or "per share" in l:
                cur = None
    extras = []
    last_eps = -99
    for i, (ln, lab, v) in enumerate(rows):
        l = norm(clean(lab))
        # older layout (DXCM 2015-18): a 'Shares used to compute ... per share' heading, then 'Basic' / 'Diluted'
        # rows, right below the non-GAAP EPS line
        if l == "diluted" and v and i - last_eps <= 3 and any("shares used" in norm(rows[k][1]) for k in (i - 1, i - 2) if k >= 0):
            head = next(rows[k][1] for k in (i - 1, i - 2) if "shares used" in norm(rows[k][1]))
            extras.append(("non-gaap diluted shares", [(ln, f"Diluted ({clean(head).rstrip(':')})", v)]))
        if v and ("shares" in l) and ("non-gaap" in l) and "reconciliation" not in l:
            extras.append(("non-gaap diluted shares", [(ln, lab, v)]))
        if v and l.startswith("non-gaap net income used for diluted") and i and "convertible" in norm(rows[i - 1][1]):
            extras.append(("if-converted add-back", [rows[i - 1]]))
        if v and re.match(r"non-gaap (diluted )?net (income|loss).*per (diluted |basic )?share|non-gaap diluted net income.*per share", l):
            extras.append(("reported non-gaap eps", [(ln, lab, v)])); last_eps = i
    return out + extras


# ---------------------------------------------------------------- "wide" reconciliations (Medtronic)
# One table per period: the header row names the metrics across the columns (Net Sales | Cost of Products Sold |
# Gross Margin Percent | Operating Profit | ...), the rows are stages: GAAP, each adjustment, Non-GAAP. A caption row
# above says the period ("Three months ended July 28, 2023", "Fiscal year ended April 26, 2024").
WIDE_CAPTION = re.compile(r"\b(three|six|nine|twelve) months ended|fiscal year ended", re.I)
WIDE_METRICS = {"operating profit": "operating income", "net income": "net income", "net income attributable": "net income"}


def wide_cells(line):
    """'| GAAP | $ | 7,166 |  | (10 | ) | 68.4 | % |' -> (label, [(value, is_percent)]). Dashes are 0; '(10 | )' is -10."""
    cells = [c.strip().replace("\\", "") for c in line.strip().strip("|").split("|")]
    label = cells[0] if cells else ""
    vals, open_neg = [], False
    for c in cells[1:]:
        c = c.replace("$", "").replace(" ", "").strip()
        if not c: continue
        if c == "%":
            if vals: vals[-1] = (vals[-1][0], True)
            continue
        if c == ")":
            if open_neg and vals: vals[-1] = (-abs(vals[-1][0]), vals[-1][1]); open_neg = False
            continue
        if c in DASH_CELLS: vals.append((0.0, False)); continue
        pct = c.endswith("%"); c = c.rstrip("%")
        neg = c.startswith("(")
        num = c.strip("()").replace(",", "")
        if not re.fullmatch(r"-?\d*\.?\d+", num): continue
        v = float(num)
        if neg and c.endswith(")"): v = -v
        elif neg: v = -v; open_neg = True         # '(10' with its ')' in the next cell
        vals.append((v, pct))
    return clean(label), vals


DASH_CELLS = ("—", "-", "–")


def wide_tables(text):
    """-> [{caption, basis, line, metrics, rows: [(line, label, {metric: value})], unresolved: [...]}]"""
    L = text.split("\n"); out = []
    for i, line in enumerate(L):
        if not line.lstrip().startswith("|"): continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        heads = [c for c in cells[1:] if c]
        # 'Net (Loss) Income attributable to Medtronic', 'Diluted (LPS) EPS' in loss quarters (Q3 FY18, U.S. Tax Act)
        hn = [re.sub(r"\((loss|lps)\)\s*", "", norm(clean(h))) for h in heads]
        if not (any(h == "net sales" for h in hn) and any(h.startswith("operating profit") for h in hn)): continue
        cap = next((L[k] for k in range(i - 1, max(-1, i - 5), -1) if WIDE_CAPTION.search(L[k])), "")
        m = WIDE_CAPTION.search(cap)
        if not m: continue
        basis = {"three": "3M", "twelve": "FY"}.get(m.group(1).lower() if m.group(1) else "twelve", "YTD")
        pct = [("percent" in h or "rate" in h) for h in hn]
        tbl = {"caption": re.sub(r"[|\s]+", " ", cap).strip(), "basis": basis, "line": i + 1, "metrics": hn, "rows": [], "unresolved": []}
        for k in range(i + 1, len(L)):
            if not L[k].lstrip().startswith("|") or WIDE_CAPTION.search(L[k]) or "net sales" in L[k].lower(): break
            lab, vals = wide_cells(L[k])
            if not vals or set(L[k]) <= set("|- "): continue
            # adjustment rows may leave the margin-% columns (and sometimes the tax-rate column) empty
            fits = [hn, [h for h in hn if "percent" not in h], [h for h, p in zip(hn, pct) if not p]]
            cols = next((f for f in fits if len(f) == len(vals)), None)
            if cols: row = dict(zip(cols, (v for v, _ in vals)))
            else:
                tbl["unresolved"].append((k + 1, lab, len(vals), len(hn))); continue
            tbl["rows"].append((k + 1, lab, row))
        out.append(tbl)
    return out


def rounding_item(start, items, end, values):
    """Tables in whole millions don't foot exactly: each line is rounded on its own. A gap of up to 3 units goes on its
    own line (as /model-historicals does), so the bridge equals the reported total."""
    whole = all(float(v).is_integer() for v in values)
    d = round(end - (start + sum(x for _, x, _ in items)), 6)
    if whole and 0.15 < abs(d) <= 3:
        return [("Rounding (each line is rounded to whole millions)", d, 0)]
    return []


def wide_candidates(text, s, P, rev_of):
    """Turn each wide table into the same candidates the row-wise reader makes. The period of a table is found by
    matching its GAAP net sales to the model's revenue (current or prior-year column), never by position."""
    cands, unresolved = [], []
    yy = int(P[3:])
    for t in wide_tables(text):
        if t["basis"] == "YTD": continue
        rows = t["rows"]
        g = next((r for r in rows if norm(r[1]) == "gaap"), None)
        n = next((r for r in rows if norm(r[1]) == "non-gaap"), None)
        unresolved += [(s["path"], "wide table", t["caption"], f"md line {ln}: '{lab}' has {k} values for {h} columns") for ln, lab, k, h in t["unresolved"]]
        if not g or not n or "net sales" not in g[2]:
            continue
        adj = [r for r in rows if g[0] < r[0] < n[0] and abs(r[2].get("net sales", 0.0) - g[2]["net sales"]) > 0.5]
        if t["basis"] == "3M": opts = [(P, "current"), (f"{P[:2]} {yy - 1:02d}", "comparative")]
        else: opts = [(f"FY {yy:02d}", "current"), (f"FY {yy - 1:02d}", "comparative")]
        tol = 3 if float(g[2]["net sales"]).is_integer() else 0.5
        fit = sorted((abs(rev_of(p) - g[2]["net sales"]), p, v) for p, v in opts if rev_of(p) is not None)
        per = next(((p, v) for d, p, v in fit if d <= tol), None)        # closest: Q4 FY18 and Q4 FY19 were $2M apart
        if not per and (all(rev_of(p) is None for p, _ in opts) or rev_of(opts[-1][0]) is None):
            continue                                       # a period before the model starts (e.g. FY16 comparatives)
        if not per:
            unresolved.append((s["path"], "wide table", t["caption"], f"GAAP net sales {g[2]['net sales']} matches no model revenue in {[p for p, _ in opts]}"))
            continue
        per, vint = per
        base = {"period": per, "basis": t["basis"], "vintage": vint, "source": s["path"], "type": s["type"], "line": g[0],
                "page": page_of(text, g[0]), "col": 0, "ncols": 1, "table": t["caption"]}
        cogs = next((h for h in g[2] if h.startswith("cost of")), None)
        if cogs:                       # gross profit = net sales - cost; a cost adjustment of (16) raises gross profit by 16
            st, en = g[2]["net sales"] - g[2][cogs], n[2].get("net sales", g[2]["net sales"]) - n[2][cogs]
            items = [(clean(lab), v.get("net sales", 0.0) - v.get(cogs, 0.0), ln) for ln, lab, v in adj
                     if v.get(cogs) or v.get("net sales")]
            cands.append({**base, "metric": "non-gaap gross profit", "start": st, "end": en, "items": items,
                          "start_label": "GAAP Net Sales - Cost of Products Sold", "end_label": "Non-GAAP Net Sales - Cost of Products Sold",
                          "start_metric": "gross profit"})
        for h in g[2]:
            if "percent" in h or "rate" in h: continue             # margin / tax-rate columns, not amounts
            key = next((m for p, m in WIDE_METRICS.items() if h == p or h.startswith(p + " ")), None)
            if not key or h not in n[2]: continue
            items = [(clean(lab), v.get(h, 0.0), ln) for ln, lab, v in adj if v.get(h)]
            cands.append({**base, "metric": "non-gaap " + key, "start": g[2][h], "end": n[2][h], "items": items,
                          "start_label": f"GAAP {h}", "end_label": f"Non-GAAP {h}", "start_metric": key})
        eps = next((h for h in n[2] if "eps" in h), None)
        if eps:
            cands.append({**base, "metric": "reported non-gaap eps", "line": n[0], "label": f"Non-GAAP {eps}", "value": n[2][eps]})
    return cands, unresolved


def wide_shares(text, s, P):
    """Medtronic prints no non-GAAP share count: its non-GAAP EPS divides by the GAAP diluted weighted-average count from
    the income statement in the same release. Columns are [quarter, prior-year quarter, (year-to-date | full year) x2]."""
    yy = int(P[3:]); out = []
    # In a GAAP loss quarter the GAAP diluted count equals basic; the footnote then states the count non-GAAP EPS used
    # (Q3 FY18: "Non-GAAP diluted EPS ... calculated using diluted weighted average shares of 1,364.5 million").
    fn = None
    rows = {norm(clean(lab)): v for _, lab, v in table_rows(text) if v}
    basic = next((v for k, v in rows.items() if k.startswith("basic weighted average shares")), None)
    dil = next((v for k, v in rows.items() if k.startswith("diluted weighted average shares")), None)
    loss_quarter = bool(basic and dil and basic[0] == dil[0])   # only then is the footnote about this quarter
    for i, line in enumerate(text.split("\n") if loss_quarter else []):
        m = re.search(r"non-gaap diluted eps[^|]{0,200}?weighted average shares of ([\d,]+\.?\d*) million", line, re.I)
        if m:
            fn = (i + 1, float(m.group(1).replace(",", "")))
            out.append({"metric": "non-gaap diluted shares", "period": P, "basis": "3M", "vintage": "current", "source": s["path"],
                        "type": s["type"], "line": fn[0], "page": page_of(text, fn[0]), "value": fn[1], "col": 0, "ncols": 1,
                        "label": "Diluted shares for non-GAAP EPS (footnote: GAAP used basic shares in a loss quarter)",
                        "start_matches_model": None})
            break
    for ln, lab, v in table_rows(text):
        if not re.match(r"^diluted weighted average shares", norm(clean(lab))) or not v: continue
        roles = ([(P, "3M", "current"), (f"Q4 {yy - 1:02d}", "3M", "comparative"), (f"FY {yy:02d}", "FY", "current"), (f"FY {yy - 1:02d}", "FY", "comparative")]
                 if P.startswith("Q4") else [(P, "3M", "current"), (f"{P[:2]} {yy - 1:02d}", "3M", "comparative")])
        for i, (per, basis, vint) in enumerate(roles[:len(v)]):
            if fn and i == 0: continue                  # the footnote count above replaces the loss quarter's GAAP count
            out.append({"metric": "non-gaap diluted shares", "period": per, "basis": basis, "vintage": vint, "source": s["path"], "type": s["type"],
                        "line": ln, "page": page_of(text, ln), "label": f"{clean(lab)} (GAAP count; the company uses it for non-GAAP EPS)",
                        "value": v[i], "col": i, "ncols": len(v), "start_matches_model": None})
        break
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True); ap.add_argument("--model", required=True); ap.add_argument("--work", required=True)
    ap.add_argument("--gaap-rows", default='{"gross profit": "^gross profit", "operating income": "^operating income", "net income": "^net income"}',
                    help="JSON: block start metric -> regex of the model's GAAP row label (income statement section)")
    a = ap.parse_args(); os.makedirs(a.work, exist_ok=True)
    srcs, pdf_only = discover(a.src)
    json.dump({"sources": srcs, "pdf_only": pdf_only}, open(os.path.join(a.work, "sources.json"), "w"), indent=1)
    wb = openpyxl.load_workbook(a.model); ws = wb[wb.sheetnames[0]]; ev = Evaluator(ws); pm = PeriodMap(ws)
    gaap = {}
    for m, pat in json.loads(a.gaap_rows).items():
        r = find_row(ws, pat, "INCOME STATEMENT")
        if r: gaap[m] = r
    def model_val(metric, key):
        r = gaap.get(metric.replace("net income", "net income")); c = pm.by_key(key)
        if not r or not c: return None
        v = ev.v(ws.cell(r, c).coordinate)
        return v if isinstance(v, (int, float)) else None
    def ytd(metric, key):
        q, yy = int(key[1]), key[3:]
        vs = [model_val(metric, f"Q{k} {yy}") for k in range(1, q + 1)]
        return sum(vs) if all(v is not None for v in vs) else None
    rev_row = find_row(ws, "^revenue", "INCOME STATEMENT")
    def rev_of(key):
        c = pm.by_key(key)
        if not rev_row or not c: return None
        v = ev.v(ws.cell(rev_row, c).coordinate)
        return v if isinstance(v, (int, float)) else None
    cands, unresolved, bridges = [], [], []
    for s in sorted(srcs, key=lambda s: (s["type"] != "release", s["path"])):
        if not s["hits"] or not s["period"] or s["type"] == "call": continue
        text = open(s["path"], encoding="utf-8", errors="ignore").read()
        P = s["period"]; yy = int(P[3:])
        fy_only_doc = False
        off_basis = set()          # (period, basis) columns of THIS document whose GAAP start differs from the model
        br = restatement_bridges(text)
        bridges += [{"source": s["path"], "lines": [a, b], "header": h, "page": page_of(text, a)} for a, b, h in br]
        bl = blocks([r for r in table_rows(text) if not any(a <= r[0] <= b for a, b, _ in br)])
        bl = [b for b in bl if b[0] not in EXTRAS] + [b for b in bl if b[0] in EXTRAS]     # bridges first: they tell us the column layout
        for key, rows in bl:
            first = rows[0]; n = len(first[2])
            # candidate periods for each column position, in the order filings print them
            if P.startswith("FY"): roles = [(f"FY {yy - i:02d}", "FY", "current" if i == 0 else "comparative") for i in range(n)]
            elif P.startswith("Q4"): roles = [(f"Q4 {yy:02d}", "3M", "current"), (f"Q4 {yy - 1:02d}", "3M", "comparative"),
                                             (f"FY {yy:02d}", "FY", "current"), (f"FY {yy - 1:02d}", "FY", "comparative")]
            else: roles = [(P, "3M", "current"), (f"{P[:2]} {yy - 1:02d}", "3M", "comparative"),
                           (P, "YTD", "current"), (f"{P[:2]} {yy - 1:02d}", "YTD", "comparative")]
            if key in EXTRAS:
                if n == 2 and P.startswith("Q4") and fy_only_doc: roles = roles[2:]
                for i, v in enumerate(first[2][:len(roles)]):
                    per, basis, vint = roles[i]
                    if basis == "YTD": continue                          # a six/nine-month figure is not the quarter's
                    # shares / add-backs / EPS have no GAAP start of their own: a column whose reconciliation in the same
                    # document starts from a different GAAP figure (restated comparatives) is on that other basis too
                    cands.append({"metric": key, "period": per, "basis": basis, "vintage": vint, "source": s["path"], "type": s["type"],
                                  "line": first[0], "page": page_of(text, first[0]), "label": clean(first[1]), "value": v, "col": i, "ncols": n,
                                  "start_matches_model": False if (per, basis) in off_basis else None})
                continue
            start_metric = metric_of(first[1])
            # resolve 2-column tables in Q4 documents (Q4-only vs full-year) by matching the model
            if n == 2 and P.startswith("Q4") and start_metric in gaap:
                if model_val(start_metric, f"FY {yy:02d}") is not None and abs(model_val(start_metric, f"FY {yy:02d}") - first[2][0]) < 0.15:
                    roles = roles[2:]; fy_only_doc = True
            for i in range(min(n, len(roles))):
                per, basis, vint = roles[i]
                if basis == "YTD": continue
                start, end = first[2][i], rows[-1][2][i] if len(rows[-1][2]) > i else None
                if end is None: continue
                items = [(clean(lab), v[i], ln) for ln, lab, v in rows[1:-1] if len(v) > i]
                if abs(start - end) < 0.05: items = []                    # nothing adjusted in this column (blank cells)
                elif abs(start + sum(x for _, x, _ in items) - end) > 0.15:
                    unresolved.append((s["path"], key, per, "items do not add up")); continue
                mv = model_val(start_metric, per) if start_metric in gaap else None
                if mv is not None and abs(mv - start) >= 0.15: off_basis.add((per, basis))
                cands.append({"metric": key, "period": per, "basis": basis, "vintage": vint, "source": s["path"], "type": s["type"],
                              "line": first[0], "page": page_of(text, first[0]), "start": start, "end": end, "items": items,
                              "start_label": clean(first[1]), "end_label": clean(rows[-1][1]), "start_metric": start_metric,
                              "model_start": mv, "start_matches_model": (mv is not None and abs(mv - start) < 0.15) if start_metric in gaap else None,
                              "col": i, "ncols": n})
        wc, wu = wide_candidates(text, s, P, rev_of)
        unresolved += wu
        for c in wc:
            if "start" in c:
                mv = model_val(c["start_metric"], c["period"]) if c["start_metric"] in gaap else None
                whole = all(float(x).is_integer() for x in [c["start"], c["end"]] + [v for _, v, _ in c["items"]])
                tol = 3 if whole else 0.15
                ok = mv is not None and abs(mv - c["start"]) <= tol
                c["model_start"] = mv
                c["start_matches_model"] = ok if c["start_metric"] in gaap else None
                if mv is not None and not ok: off_basis.add((c["period"], c["basis"]))
                c["items"] += rounding_item(mv if ok else c["start"], c["items"], c["end"], [c["start"], c["end"]] + [v for _, v, _ in c["items"]])
                if abs((mv if ok else c["start"]) + sum(x for _, x, _ in c["items"]) - c["end"]) > 0.15:
                    unresolved.append((s["path"], c["metric"], c["period"], "items do not add up")); continue
            else:
                c["start_matches_model"] = False if (c["period"], c["basis"]) in off_basis else None
            cands.append(c)
        if wc and s["type"] == "release":
            cands += [dict(x, start_matches_model=False if (x["period"], x["basis"]) in off_basis else None) for x in wide_shares(text, s, P)]
    json.dump({"candidates": cands, "unresolved": unresolved, "gaap_rows": gaap, "restatement_bridges": bridges}, open(os.path.join(a.work, "candidates.json"), "w"), indent=1)
    # ---------------- inventory report
    by = {}
    for c in cands: by.setdefault(c["metric"], []).append(c)
    order = lambda k: (int(k[3:]), 5 if k.startswith("FY") else int(k[1]))
    with open(os.path.join(a.work, "inventory.md"), "w") as f:
        f.write(f"# Non-GAAP inventory\n\nFiles searched: {len(srcs)} ({sum(1 for s in srcs if s['hits'])} mention non-GAAP / adjusted). "
                f"PDFs with no markdown twin: {len(pdf_only)}\n\n")
        for m, cs in sorted(by.items()):
            pers = sorted({c["period"] for c in cs}, key=order)
            f.write(f"## {m}\n\nPeriods: {len(pers)} ({pers[0]} .. {pers[-1]})\n\n")
            if "items" in cs[0]:
                labs = {}
                for c in cs:
                    for lab, v, _ in c["items"]: labs.setdefault(lab, []).append((c["period"], v))
                f.write("| adjustment line | # | periods | example values |\n|---|---|---|---|\n")
                for lab, xs in sorted(labs.items(), key=lambda kv: -len(kv[1])):
                    ps = sorted({p for p, _ in xs}, key=order)
                    f.write(f"| {lab} | {len(xs)} | {ps[0]} .. {ps[-1]} | {', '.join(f'{p}: {v}' for p, v in xs[:3])} |\n")
                # conflicts: same period, different reported totals -> restatement / definition change
                conf = {}
                for c in cs: conf.setdefault(c["period"], set()).add((round(c["end"], 1)))
                bad = {p: sorted(v) for p, v in conf.items() if len(v) > 1}
                if bad:
                    f.write("\n**Different totals for the same period across documents (restated / redefined):** " +
                            "; ".join(f"{p}: {v}" for p, v in sorted(bad.items(), key=lambda kv: order(kv[0]))) + "\n")
                mism = sorted({c["period"] for c in cs if c.get("start_matches_model") is False}, key=order)
                if mism: f.write(f"\n**GAAP starting value differs from the model:** {mism}\n")
            f.write("\n")
        if bridges:
            f.write("## Restatement bridges (not used as data)\n\nThese tables walk previously reported figures to restated ones. "
                    "Their columns are bases, not periods. They show which periods were restated and why; the restated "
                    "comparatives themselves are read from the regular tables.\n\n")
            f.write("".join(f"- {os.path.basename(b['source'])}" + (f", page {b['page']}" if b['page'] else "") + f" (md lines {b['lines'][0]}-{b['lines'][1]}): {b['header']}\n" for b in bridges) + "\n")
        if unresolved: f.write("## Blocks that did not add up (check the table by hand)\n\n" + "\n".join(f"- {u}" for u in unresolved) + "\n")
    print(f"files: {len(srcs)}, with hits: {sum(1 for s in srcs if s['hits'])}, pdf-only: {len(pdf_only)}, candidates: {len(cands)}, "
          f"unresolved: {len(unresolved)}, restatement bridges skipped: {len(bridges)}")
    for m, cs in sorted(by.items()): print(f"  {m}: {len({c['period'] for c in cs})} periods")


if __name__ == "__main__":
    main()
