"""Step 4 - recalculate the model independently (no Excel needed) and tie it to the filings.

usage: python3 verify.py --work <work_dir> --model <model.xlsx>   (rows are found by label, same patterns as build.py)

Checks every reported period:
  - balance check = 0 and cash check = 0 (if the template has them)
  - revenue, gross profit, operating income, pre-tax income, net income vs the filing
  - total assets / liabilities / equity vs the filing
  - CFO / CFI / CFF: quarters summed year-to-date vs each 10-Q, FY vs 10-K; ending cash vs the filing
  - Q4 net income (FY - 9M) vs the Q4 press release
  - each input row: Q1+Q2+Q3+Q4 = FY
  - colour convention: every core-financial input row blue (incl. YTD differences and Q4 plugs); other links green, formulas black
Writes <work>/verify_report.md; exit code 1 on any failure."""
import argparse, json, os, re, sys
import openpyxl
from openpyxl.utils import get_column_letter as L, column_index_from_string as CI
from build import ROLE_PATTERNS, IS_IN, CF_IN, BS_IN, INPUT_ROLES, norm, color_for, apply_value_overrides

TOL = 0.11


class Sheet:
    def __init__(self, ws):
        self.ws, self.memo = ws, {}

    def v(self, ref):
        ref = ref.replace("$", "")
        if ref in self.memo: return self.memo[ref]
        x = self.ws[ref].value
        if isinstance(x, str) and x.startswith("="):
            body = x[1:]
            body = re.sub(r"SUM\(\$?([A-Z]{1,3})\$?(\d+):\$?([A-Z]{1,3})\$?(\d+)\)", lambda m: f"_sum('{m.group(1)}{m.group(2)}','{m.group(3)}{m.group(4)}')", body)
            body = re.sub(r"(?<![A-Za-z'])\$?([A-Z]{1,3})\$?(\d+)(?!['\d])", lambda m: f"_v('{m.group(1)}{m.group(2)}')", body)
            body = body.replace("IFERROR(", "_iferror(lambda: ")
            try: x = eval(body, {"_v": self.v, "_sum": self.sum, "_iferror": lambda f, alt: _safe(f, alt)})
            except ZeroDivisionError: x = None
            except TypeError: x = None
        elif x is None or isinstance(x, str): x = 0.0 if x is None else x
        self.memo[ref] = x
        return x

    def sum(self, a, b):
        ca, ra = re.match(r"([A-Z]+)(\d+)", a).groups(); cb, rb = re.match(r"([A-Z]+)(\d+)", b).groups()
        return sum(self.v(f"{L(c)}{r}") or 0 for c in range(CI(ca), CI(cb) + 1) for r in range(int(ra), int(rb) + 1))


def _safe(f, alt):
    try: return f()
    except Exception: return alt


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--work", required=True); ap.add_argument("--model", required=True)
    a = ap.parse_args()
    P = json.load(open(os.path.join(a.work, "periods.json"))); per, q4 = P["periods"], P["q4"]
    dp = os.path.join(a.work, "decisions.json")
    splits = json.load(open(dp)).get("share_splits", []) if os.path.exists(dp) else []
    if os.path.exists(dp): apply_value_overrides(per, json.load(open(dp)))   # check what build typed
    order = lambda k: (int(k[3:]), 4 if k.startswith("FY") else int(k[1]))
    wb = openpyxl.load_workbook(a.model); ws = wb[wb.sheetnames[0]]; S = Sheet(ws)
    # rows by label (same patterns as build)
    sect = {}
    for r in range(1, ws.max_row + 1):
        t = norm(ws.cell(r, 1).value)
        if t.startswith("balance sheet"): sect.setdefault("BS", r)
        if t.startswith("cash flow"): sect.setdefault("CF", r)
    bounds = {"IS": (2, sect["BS"]), "BS": (sect["BS"], sect["CF"]), "CF": (sect["CF"], ws.max_row + 1)}
    row = {}
    for sn, (r0, r1) in bounds.items():
        taken = set()
        for s, role, pat in ROLE_PATTERNS:
            if s != sn or role in row: continue
            for r in range(r0, r1):
                if r not in taken and norm(ws.cell(r, 2).value) and re.search(pat, norm(ws.cell(r, 2).value)):
                    if role == "OTHFIN" and r < row.get("CFI", 0): continue
                    row[role] = r; taken.add(r); break
    cols = {}
    for c in range(4, ws.max_column + 1):
        h = ws.cell(2, c).value
        if isinstance(h, int): cols[f"FY {h % 100:02d}"] = c
        elif isinstance(h, str) and re.fullmatch(r"Q[1-4] \d\d", h): cols[h] = c
    fails, n, warns = [], 0, []
    def chk(label, got, exp, tol=TOL):
        nonlocal n; n += 1
        if got is None or exp is None or abs(got - exp) > tol: fails.append(f"{label}: model {got if got is None else round(got, 2)} vs filing {exp}")
    val = lambda role, key: S.v(f"{L(cols[key])}{row[role]}") if role in row and key in cols else None
    for key in sorted(cols, key=lambda k: (int(k[3:]), 5 if k.startswith("FY") else int(k[1]))):
        c = cols[key]
        for role in ("BALCHK", "CASHCHK"):
            if role in row: chk(f"{key} {role}", val(role, key), 0.0)
        if key.startswith("Q4"):
            d = q4.get(key, {})
            # Q4 = FY - Q1 - Q2 - Q3, four filings each rounded on its own: allow the year's rounding tolerance
            # (3 units at the filing's precision, e.g. $1-3M for whole-million reporters like MDT)
            rtol = per.get(f"FY {key[3:]}", {}).get("CF_chk", {}).get("_RTOL", TOL)
            if d.get("NI") is not None: chk(f"{key} net income vs Q4 release", val("NI", key), d["NI"], rtol)
            continue
        p = per[key]; Ic, Bc, Cc = p["IS_chk"], p["BS_chk"], p["CF_chk"]
        rev = sum(v for _, v, _ in p["IS"].get("REV", [])); cogs = sum(v for _, v, _ in p["IS"].get("COGS", []))
        chk(f"{key} revenue", val("REV", key), rev); chk(f"{key} gross profit", val("GP", key), rev + cogs)
        chk(f"{key} operating income", val("OI", key), Ic.get("OI")); chk(f"{key} pre-tax", val("PRETAX", key), Ic.get("PRETAX_USED"))
        chk(f"{key} net income", val("NI", key), Ic.get("NI"))
        f = 1                                      # EPS to the cent, pre-split periods restated by the split factor
        for sp in splits:
            if order(key) <= order(sp["through_period"]): f *= sp["factor"]
        if Ic.get("EPSB") is not None:
            chk(f"{key} EPS basic vs reported", val("EPSB", key), Ic["EPSB"] / f, 0.0051 / f + 0.0005)
        got = val("EPSD", key)                     # diluted: the company may add back convertible interest (if-converted)
        if Ic.get("EPSD") is not None and got is not None and abs(got - Ic["EPSD"] / f) > 0.0051 / f + 0.0005:
            warns.append(f"{key} EPS diluted: model {round(got, 3)} vs reported {Ic['EPSD'] / f:g} (model = net income to common / diluted shares; "
                         "the company's numerator likely adds back convertible-note interest - see its EPS note)")
        chk(f"{key} total assets", val("TA", key), Bc.get("TA"))
        if Bc.get("TL") is not None:              # some companies print no total-liabilities line
            chk(f"{key} total liabilities", val("TL", key), Bc.get("TL"), Cc.get("_RTOL", TOL))
        chk(f"{key} liabilities + equity", val("TLE", key), Bc.get("TA"))
        y = key[3:]
        qs = [f"Q{k} {y}" for k in range(1, (4 if key.startswith("FY") else int(key[1])) + 1)]
        for role, k in (("CFO", "CFO"), ("CFI", "CFI"), ("CFF", "CFF")):
            got = val(role, key) if key.startswith("FY") else sum(val(role, qq) or 0 for qq in qs)
            chk(f"{key} {role} ({'FY' if key.startswith('FY') else 'YTD'})", got, Cc.get(k))
        chk(f"{key} ending cash", val("END", key), Cc.get("END"))
    # quarters sum to FY for every input / subtotal row
    for key in [k for k in cols if k.startswith("FY")]:
        y = key[3:]
        if not all(f"Q{k} {y}" in cols for k in range(1, 5)): continue
        for role in IS_IN + CF_IN + ["GP", "OI", "NI", "CFO", "CFI", "CFF"]:
            if role in row:
                chk(f"{key} {role} Q1-Q4 sum", sum(val(role, f"Q{k} {y}") or 0 for k in range(1, 5)), val(role, key))
    # colour convention
    bad_col = []
    blue_rows = {row[k] for k in INPUT_ROLES if k in row}
    for key, c in cols.items():
        for r in range(3, ws.max_row + 1):
            v = ws.cell(r, c).value; want = color_for(v, r in blue_rows)
            got = ws.cell(r, c).font.color.rgb if ws.cell(r, c).font.color is not None else None
            if want and got != want: bad_col.append(f"{L(c)}{r}")
    with open(os.path.join(a.work, "verify_report.md"), "w") as f:
        f.write(f"# Verification\n\n{n} checks, {len(fails)} failed; colour-convention exceptions: {len(bad_col)}\n\n")
        for x in fails: f.write(f"- FAIL {x}\n")
        if bad_col: f.write(f"\nColour exceptions: {', '.join(bad_col[:50])}\n")
        if warns: f.write("\n## Warnings (not failures)\n\n" + "".join(f"- {w}\n" for w in warns))
    print(f"{n} checks, {len(fails)} failed, colour exceptions {len(bad_col)}, warnings {len(warns)}")
    for x in fails[:25]: print("  FAIL", x)
    import modfill
    fill_bad = modfill.check(a.model)                 # the user's MOD fill convention
    for x in modfill.summary(fill_bad): print('  FILL', x)
    with open(os.path.join(a.work, 'verify_report.md'), 'a') as f:
        f.write(f"\nFill-convention exceptions: {len(fill_bad)}\n" + ''.join(f'- {x}\n' for x in modfill.summary(fill_bad)))
    import notebox
    note_bad = notebox.check(a.model)                 # note boxes that would open squashed
    for x in note_bad[:12]: print('  NOTE BOX', x)
    sys.exit(1 if fails or bad_col or fill_bad or note_bad else 0)


if __name__ == "__main__":
    main()
