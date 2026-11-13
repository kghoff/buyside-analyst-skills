"""Check the analysis rows in MOD: recalculate them and compare every number with the same metric computed straight
from MOD's line values (own header arithmetic and own KPI maths - no shared code with periods/formulas/recipe).

usage: python3 verify.py --model <TICKER_model.xlsx> --work <_model_work> [--decisions <analyze_decisions.json>] [--src <gather folder>]
Checks: every analysis and KPI cell = independent value | estimate columns hold no errors | no #REF | analysis
rows reference only their own line, the % row above and revenue | colours | FCF adjustment cells commented |
every pre-analyze row still has the same values (moved down) and only this skill's rows were added | other tabs'
MOD links re-pointed to the same rows | with --src: Days in Fiscal Period = manifest dates. Writes <work>/analyze_verify_report.md; exit 1 on failure."""
import argparse
import json
import os
import re
import sys
from collections import defaultdict
from datetime import date

import openpyxl
from openpyxl.utils import get_column_letter as L

from adjust import ytd_values
from evaluate import Book, ERR
from roles import find_roles, addon_rows, analysis_section_rows
from rowmap import map_formula

GREEN, BLUE, BLACK = "FF008000", "FF0000FF", "FF000000"
METRIC_LABELS = {"% yoy": "yoy", "% 2 year": "2yr", "% qoq": "qoq", "% margin": "margin", "% of sales": "pct_sales",
                 "bps yoy": "bps", "incremental margin": "incr"}
KPI_LABELS = {
    "Operating Income (EBIT excluding 'other income')": "ROIC_OI", "Full Year Tax Rate": "ROIC_TAX",
    "(-) Taxes only on Op Profit": "ROIC_TAXES", "NOPAT": "NOPAT", "TTM NOPAT": "NOPAT_TTM",
    "Invested Capital (asset based)": "IC_A", "Invested Capital (minus cash)": "IC_M",
    "Invested Cap Avg (asset based)": "ICAVG_A", "Invested Cap Avg (minus cash)": "ICAVG_M",
    "ROIC asset (Invested Cap Avg) TTM": "ROIC_A", "ROIC minus cash (Invested Cap Avg) TTM": "ROIC_M",
    "(+/-) Net Cash Provided by Operating Activities": "FCF_CFO", "(-) Capital Expenditure": "FCF_CAPEX",
    "(+/-) Free Cash Flow": "FCF", "FCF TTM": "FCF_TTM", "FCF Conversion % (FCF / net income)": "FCF_CONV",
    "Net Income": "KM_NI", "TTM": "KM_NI_TTM",
    "Free Cash Flow": "KM_FCF", "Operating Profit (EBIT excluding 'other income')": "KM_OP", "EBITDA": "EBITDA",
    "EBITDA TTM": "EBITDA_TTM", "Net Leverage / (Cash) Ratio": "NETLEV", "Leverage Ratio": "LEV",
    "Interest Coverage Ratio": "INTCOV", "Return on Equity (ROE, avg equity) TTM": "ROE",
    "Return on Assets (ROA, avg assets) TTM": "ROA", "Days in Fiscal Period": "DAYS",
    "Days Sales Outstanding (DSO, avg)": "DSO", "Days Inventory Outstanding (DIO, avg)": "DIO",
    "Days Payable Outstanding (DPO, avg)": "DPO", "Cash Conversion Cycle (CCC)": "CCC",
}
NA = "n.a."
# The user's invested capital (same default as recipe.IC_DEFAULT, written out again on purpose: independent check)
IC_DEFAULT = {"operating_assets": ["CASH", "STSEC", "AR", "INV", "PRE", "OCA", "PPE", "ROU", "GWI"],
              "nibcl": ["AP", "PAY", "ACCR", "TAXPAY", "OPLLC", "CLOTH", "OCL"]}


def header(ws):
    """-> {col: (q, y, est)} from row 2 (own parser)."""
    out = {}
    for c in range(4, ws.max_column + 1):
        v = ws.cell(2, c).value
        s = "" if v is None else str(v).strip()
        est = s.endswith("E")
        s = s[:-1] if est else s
        if re.fullmatch(r"\d{4}", s): out[c] = (0, int(s), est)
        elif re.fullmatch(r"Q[1-4] \d\d", s): out[c] = (int(s[1]), 2000 + int(s[3:]), est)
    return out


def back(q, y, kind):
    if kind == "yoy": return (q, y - 1)
    if kind == "2yr": return (q, y - 2)
    if kind in ("qoq", "prev"):
        if q == 0: return (0, y - 1) if kind == "prev" else None
        return (4, y - 1) if q == 1 else (q - 1, y)


def ttm_keys(q, y):
    if q == 0: return [(0, y)]
    ks = []
    for _ in range(4):
        ks.append((q, y))
        q, y = (q - 1, y) if q > 1 else (4, y - 1)
    return ks


def num(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def safe(fn):
    """Excel IFERROR semantics for expected values: any arithmetic problem -> 'n.a.'."""
    try:
        v = fn()
        return v if num(v) else NA
    except (ZeroDivisionError, TypeError, KeyError):
        return NA


def manifest_ends(src):
    """-> {(q, y): date} from <src>/_manifest.json: 10-K end stored as (4, fiscal year). Own parser, not adjust.period_ends."""
    path = os.path.join(src, "_manifest.json") if src else None
    if not path or not os.path.exists(path): return None
    out = {}
    for id_, it in json.load(open(path)).get("items", {}).items():
        m = re.fullmatch(r"10-([KQ]):(\d{4})-(\d{2})-(\d{2})", id_)
        if not m: continue
        d, lab = date(int(m.group(2)), int(m.group(3)), int(m.group(4))), it.get("label", "")
        x = re.search(r"\b(\d{4}) 10-K\b", lab) if m.group(1) == "K" else re.search(r"\b(?:Q([1-3]) (\d{2})|(\d{4}) Q([1-3])) 10-Q\b", lab)
        if not x: continue
        if m.group(1) == "K": out[(4, int(x.group(1)))] = d
        else: out[(int(x.group(1) or x.group(4)), 2000 + int(x.group(2)) if x.group(2) else int(x.group(3)))] = d
    return out


def check(model, work, decisions=None, src=None):
    decisions = decisions or {}
    wb = openpyxl.load_workbook(model)
    mod, b = wb["MOD"], Book(wb)
    an = mod
    fails, n = [], 0
    hdr = header(mod)
    rep = {k: c for c, (q, y, e) in hdr.items() if not e for k in [(q, y)]}      # reported (q, y) -> col
    allk = {(q, y): c for c, (q, y, e) in hdr.items()}
    roles, _, _ = find_roles(mod)

    def mv(role):
        return {k: (b.value("MOD", f"{L(c)}{roles[role]}") or 0.0) for k, c in rep.items()}

    def fail(msg):
        if len(fails) < 300: fails.append(msg)

    rm_path = os.path.join(work, "analyze_rowmap.json")
    if not os.path.exists(rm_path):
        return [f"no {rm_path}: run analyze.py first"], 0
    rowmap = json.load(open(rm_path))
    moved = {int(k): v for k, v in rowmap["rows"].items() if v}               # backup row -> row now
    kept = set(moved.values())
    addon, ours = addon_rows(mod), analysis_section_rows(mod)

    # ---- map rows: kept MOD lines, metrics (under a base), KPI rows (by label, inside this skill's sections)
    first = min(hdr)
    link_of, kpi_row, metric_rows, base_of, adj_rows = {}, {}, [], {}, []
    last_base, last_pct, in_adj = None, None, False
    for r in range(3, an.max_row + 1):
        lab = an.cell(r, 2).value
        lab = lab.strip() if isinstance(lab, str) else lab
        if r in kept:
            if lab and r not in addon: link_of[r] = r; last_base, last_pct = r, None
            in_adj = False
            continue
        if lab in METRIC_LABELS:
            metric_rows.append(r); base_of[r] = (last_base, last_pct if METRIC_LABELS[lab] == "bps" else None)
            if METRIC_LABELS[lab] in ("margin", "pct_sales"): last_pct = r
        elif r in ours and lab in KPI_LABELS:
            kpi_row[KPI_LABELS[lab]] = r; last_base, last_pct = r, None
            in_adj = KPI_LABELS[lab] == "FCF_CAPEX"
            continue
        elif r in ours and lab and in_adj:
            adj_rows.append(r)
            continue
        elif r not in ours and any(an.cell(r, c).value not in (None, "") for c in range(1, an.max_column + 1)):
            fail(f"row {r} ({lab!r}) was added but is not one of this skill's rows")
        if not (lab in METRIC_LABELS and METRIC_LABELS[lab] == "pct_sales"): in_adj = False
    rev_row = roles["REV"]

    # ---- truth series {(q, y): value} for every base row: links = MOD values; KPI rows = own maths below
    truth = {r: {k: (b.value("MOD", f"{L(c)}{r}") or 0.0) for k, c in rep.items()} for r in link_of}
    V = {role: mv(role) for role in roles}
    V = defaultdict(lambda: {k: NA for k in rep}, V)     # a role MOD has no row for -> a series of "n.a." (everything built on it is n.a.)
    T = {}
    fy = {k for k in rep if k[0] == 0}
    latest_fy = max(fy, key=lambda k: k[1])

    def ttm(series, k):
        ks = ttm_keys(*k)
        return safe(lambda: sum(series[x] for x in ks)) if all(x in series for x in ks) else None

    def avg(series, k, kind):
        j = back(*k, kind)
        return safe(lambda: (series[k] + series[j]) / 2) if j in series else None

    rate = {k: V["TAXRATE"][(0, k[1]) if (0, k[1]) in rep else latest_fy] for k in rep}
    T["ROIC_OI"] = V["OI"]; T["ROIC_TAX"] = rate
    T["ROIC_TAXES"] = {k: safe(lambda k=k: -V["OI"][k] * rate[k]) for k in rep}
    T["NOPAT"] = {k: safe(lambda k=k: T["ROIC_TAXES"][k] + V["OI"][k]) for k in rep}
    T["NOPAT_TTM"] = {k: ttm(T["NOPAT"], k) for k in rep}
    ic = decisions.get("invested_capital") or IC_DEFAULT
    assets = [x for x in ic["operating_assets"] if x in roles]
    nibcl = [x for x in ic["nibcl"] if x in roles]
    for key, aa in (("IC_A", assets), ("IC_M", [x for x in assets if x not in ("CASH", "STSEC")])):
        T[key] = {k: safe(lambda k=k, aa=aa: sum(V[x][k] for x in aa) - sum(V[x][k] for x in nibcl)) for k in rep}
    for s in "AM":
        T[f"ICAVG_{s}"] = {k: avg(T[f"IC_{s}"], k, "yoy") for k in rep}
        T[f"ROIC_{s}"] = {k: safe(lambda k=k, s=s: T["NOPAT_TTM"][k] / T[f"ICAVG_{s}"][k]) if T["NOPAT_TTM"][k] is not None and T[f"ICAVG_{s}"][k] is not None else None for k in rep}
    filings = json.load(open(os.path.join(work, "filings.json"))) if os.path.exists(os.path.join(work, "filings.json")) else {}
    adj_series = []
    for d in decisions.get("fcf_adjustments", []):
        ytd, s = ytd_values(filings, d["pattern"]), {}
        for (q, y) in rep:
            key = f"FY {y % 100:02d}" if q == 0 else f"Q{q} {y % 100:02d}"
            if q in (0, 1) and key in ytd: s[(q, y)] = ytd[key]
            elif q in (2, 3) and key in ytd: s[(q, y)] = ytd[key] - ytd.get(f"Q{q - 1} {y % 100:02d}", 0.0)
        for (q, y) in rep:
            if q == 4 and (0, y) in s and all((i, y) in s for i in (1, 2, 3)):
                s[(4, y)] = s[(0, y)] - s[(1, y)] - s[(2, y)] - s[(3, y)]
        adj_series.append(s)
    T["FCF_CFO"], T["FCF_CAPEX"] = V["CFO"], V["CAPEX"]
    T["FCF"] = {k: safe(lambda k=k: V["CFO"][k] + V["CAPEX"][k] + sum(s.get(k, 0.0) for s in adj_series)) for k in rep}
    T["FCF_TTM"] = {k: ttm(T["FCF"], k) for k in rep}
    T["FCF_CONV"] = {k: safe(lambda k=k: T["FCF"][k] / V["NI"][k]) for k in rep}
    T["KM_NI"], T["KM_FCF"], T["KM_OP"] = V["NI"], T["FCF"], V["OI"]
    T["KM_NI_TTM"] = {k: ttm(V["NI"], k) for k in rep}
    T["EBITDA"] = {k: safe(lambda k=k: V["OI"][k] + V["DA"][k]) for k in rep}
    T["EBITDA_TTM"] = {k: ttm(T["EBITDA"], k) for k in rep}
    debt = {k: safe(lambda k=k: V["LTDEBT"][k] + V["CURDEBT"][k]) for k in rep}
    T["NETLEV"] = {k: safe(lambda k=k: (debt[k] - V["CASH"][k] - V["STSEC"][k]) / T["EBITDA_TTM"][k]) if T["EBITDA_TTM"][k] is not None else None for k in rep}
    T["LEV"] = {k: safe(lambda k=k: debt[k] / T["EBITDA_TTM"][k]) if T["EBITDA_TTM"][k] is not None else None for k in rep}
    T["INTCOV"] = {k: safe(lambda k=k: ttm(V["OI"], k) / -ttm(V["INTEXP"], k)) if ttm(V["OI"], k) is not None else None for k in rep}
    for key, role in (("ROE", "EQ"), ("ROA", "TA")):
        T[key] = {k: safe(lambda k=k: T["KM_NI_TTM"][k] / avg(V[role], k, "yoy"))
                  if T["KM_NI_TTM"][k] is not None and avg(V[role], k, "yoy") is not None else None for k in rep}
    days = {k: b.value("MOD", f"{L(c)}{kpi_row['DAYS']}") for k, c in rep.items()}
    for (q, y) in rep:                         # FY days = sum of its quarters
        if q == 0 and all((i, y) in rep for i in (1, 2, 3, 4)):
            n += 1
            if abs(days[(0, y)] - sum(days[(i, y)] for i in (1, 2, 3, 4))) > 1e-9:
                fail(f"Days FY {y} != sum of quarters")
    ends = manifest_ends(src)
    if src is not None:
        for (q, y), c in rep.items():
            if q == 0: continue
            prev, cur = (ends or {}).get((4, y - 1) if q == 1 else (q - 1, y)), (ends or {}).get((q, y))
            exp = (cur - prev).days if cur and prev else 91
            if exp == 91 and not (cur and prev):
                n += 1
                cell = an.cell(kpi_row["DAYS"], c)
                if cell.comment is None: fail(f"{cell.coordinate} Days in Fiscal Period: assumed 91 without a comment")
            if ends is None: continue
            n += 1
            if days[(q, y)] != exp: fail(f"{L(c)}{kpi_row['DAYS']} Days in Fiscal Period: expected {exp} from the manifest, got {days[(q, y)]!r}")
    for key, bal, flow, sg in (("DSO", "AR", "REV", 1), ("DIO", "INV", "COGS", -1), ("DPO", "AP", "COGS", -1)):
        T[key] = {k: safe(lambda k=k: avg(V[bal], k, "prev") / (sg * V[flow][k]) * days[k])
                  if avg(V[bal], k, "prev") is not None else None for k in rep}
    T["CCC"] = {k: safe(lambda k=k: T["DSO"][k] + T["DIO"][k] - T["DPO"][k]) if T["DSO"][k] is not None else None for k in rep}
    for key, r in kpi_row.items():
        if key in T: truth[r] = T[key]

    def compare(r, c, exp, what):
        nonlocal n
        n += 1
        got = b.value("MOD", f"{L(c)}{r}")
        ref = f"{L(c)}{r}"
        if exp is None:
            if got not in (None, ""): fail(f"{ref} {what}: expected blank, got {got!r}")
        elif exp == NA:
            if got != NA: fail(f"{ref} {what}: expected n.a., got {got!r}")
        elif not num(got) or abs(got - exp) > 1e-9 * max(1.0, abs(exp)):
            fail(f"{ref} {what}: expected {exp!r}, got {got!r}")

    # ---- KPI rows
    for r in kpi_row.values():                       # kept MOD rows: checked against the backup below
        if r == kpi_row.get("DAYS"): continue
        for k, c in rep.items():
            compare(r, c, truth[r].get(k), an.cell(r, 2).value or f"MOD row {link_of.get(r)}")
    # ---- analysis rows
    for r in metric_rows:
        kind = METRIC_LABELS[an.cell(r, 2).value.strip()]
        base, pct = base_of[r]
        B, R = truth[base], truth[rev_row]
        for k, c in rep.items():
            if kind in ("yoy", "2yr", "qoq"):
                j = back(*k, kind)
                exp = None if j not in allk else safe(lambda: B[k] / B[j] - 1)
            elif kind == "margin": exp = safe(lambda: B[k] / R[k])
            elif kind == "pct_sales": exp = safe(lambda: -B[k] / R[k])
            else:
                j = back(*k, "yoy")
                if j not in allk: exp = None
                elif kind == "bps":
                    P = {x: safe(lambda x=x: (-1 if an.cell(pct, 2).value.strip() == "% of sales" else 1) * B[x] / R[x]) for x in (k, j)}
                    exp = safe(lambda: (P[k] - P[j]) * 10000)
                else: exp = safe(lambda: (B[k] - B[j]) / (R[k] - R[j]))
            compare(r, c, exp, an.cell(r, 2).value)
            f = an.cell(r, c).value
            if isinstance(f, str):
                refs = {int(x) for x in re.findall(r"(?<![A-Z!])\$?[A-Z]{1,3}\$?(\d+)", f)}
                if not refs <= {base, rev_row, pct} - {None}:
                    fail(f"{L(c)}{r}: references rows {sorted(refs)} outside its line")
    # ---- estimate columns, #REF, colours, adjustment comments
    est_cols = [c for c, (_, _, e) in hdr.items() if e]
    for r in range(3, an.max_row + 1):
        if r in kept: continue
        for c in hdr:
            cell = an.cell(r, c)
            v = cell.value
            if v is None: continue
            if isinstance(v, str) and "#REF" in v: fail(f"{cell.coordinate}: #REF")
            if c in est_cols and b.value("MOD", cell.coordinate) is ERR:
                fail(f"{cell.coordinate}: error in estimate column")
            if r in adj_rows:
                exp_col = BLUE
                if cell.comment is None: fail(f"{cell.coordinate}: FCF adjustment without a comment")
            elif not (isinstance(v, str) and v.startswith("=")):
                exp_col = BLUE if num(v) else None
            elif re.fullmatch(r"=\$?[A-Z]{1,3}\$?\d+", v):
                exp_col = GREEN
            else:
                exp_col = BLACK
            got_col = cell.font.color.rgb if cell.font and cell.font.color else None
            if exp_col and got_col != exp_col: fail(f"{cell.coordinate}: colour {got_col} != {exp_col}")
    for r in adj_rows:
        if an.cell(r, 2).comment is None: fail(f"row {r}: FCF adjustment label without a comment")
    # ---- every pre-analyze row is still there with the same values, and other tabs' links follow it
    backup = os.path.join(work, rowmap["backup"])
    if not os.path.exists(backup):
        fail("no pre-analyze backup to compare MOD against")
        return fails, n
    owb = openpyxl.load_workbook(backup)
    old, ob = owb["MOD"], Book(owb)
    for r_old, r_new in moved.items():
        for c in range(1, old.max_column + 1):
            if old.cell(r_old, c).value is None and mod.cell(r_new, c).value is None: continue
            n += 1
            x, y = ob.value("MOD", f"{L(c)}{r_old}"), b.value("MOD", f"{L(c)}{r_new}")
            if x != y and not (num(x) and num(y) and abs(x - y) <= 1e-9 * max(1.0, abs(x))):
                fail(f"MOD changed: {L(c)}{r_old} -> {L(c)}{r_new}: {x!r} became {y!r}")
    tail = max(moved.values()) - max(moved) if moved else 0
    fn = lambda r: moved.get(r, r + tail)
    for sh in owb.worksheets:
        if sh.title == "MOD": continue
        if sh.title not in wb.sheetnames: fail(f"tab {sh.title} missing"); continue
        for row in sh.iter_rows():
            for c in row:
                v = c.value
                want = map_formula(v, "MOD", fn, home=False) if isinstance(v, str) and v.startswith("=") and "MOD" in v else v
                n += 1
                if wb[sh.title][c.coordinate].value != want: fail(f"{sh.title}!{c.coordinate}: {wb[sh.title][c.coordinate].value!r} (expected {want!r})")
    return fails, n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True); ap.add_argument("--work", required=True)
    ap.add_argument("--decisions", default=None); ap.add_argument("--src", default=None)
    a = ap.parse_args()
    dec = json.load(open(a.decisions)) if a.decisions and os.path.exists(a.decisions) else {}
    fails, n = check(a.model, a.work, dec, a.src)
    import modfill
    fails += [f"fill convention: {x}" for x in modfill.summary(modfill.check(a.model))]   # quarters plain, years grey
    import notebox; fails += [f"squashed note box: {x}" for x in notebox.check(a.model)[:12]]
    os.makedirs(a.work, exist_ok=True)
    with open(os.path.join(a.work, "analyze_verify_report.md"), "w") as f:
        f.write(f"# Analysis verification\n\n{n} checks, {len(fails)} failed\n\n" + "".join(f"- {x}\n" for x in fails))
    print(f"{n} checks, {len(fails)} failed")
    for x in fails[:20]: print("  " + x)
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
