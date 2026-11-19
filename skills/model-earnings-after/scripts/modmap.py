"""(Copied from model-earnings-before, Nov 2026; keep in sync. Origin: model-multiples.) The user's MOD tab layout: period columns (row 2) and row keys ('<section> | <label>').

usage: python3 modmap.py rowmap <model.xlsx> <out.md>     (the row list the plan agent picks keys from)
Analysis rows (% yoy, % of sales, ...) are not keys of their own: ModMap.analysis(key, name) finds the one under a line."""
import re
import sys

import openpyxl
from openpyxl.utils import get_column_letter as L

ANALYSIS = {"% yoy", "% 2 year", "% qoq", "% of sales", "% margin", "bps yoy", "incremental margin", "% of total rev",
            "% 5 year", "seasonality", "ttm"}


class ModMap:
    def __init__(self, path, tab="MOD"):
        ws = openpyxl.load_workbook(path, read_only=True)[tab]
        rows = list(ws.iter_rows(min_row=1, max_col=3, values_only=True))
        self.labels = {}                                   # period label -> column letter
        hdr = next(ws.iter_rows(min_row=2, max_row=2, values_only=True))
        for k, v in enumerate(hdr, start=1):
            if v is not None and k > 3:
                self.labels[str(v).strip()] = L(k)
        self.order = list(self.labels)
        self.keys, self.lines, section, seen = {}, [], "", {}
        for i, (a, b, c) in enumerate(rows, start=1):
            if a:
                section = str(a).strip()
            if not b:
                continue
            lab = str(b).strip()
            if lab.lower() in ANALYSIS:
                continue
            key = f"{section} | {lab}"
            seen[key] = seen.get(key, 0) + 1
            if seen[key] > 1:
                key = f"{key} #{seen[key]}"
            self.keys[key] = i
            self.lines.append((i, key, c))
        self.analysis_rows = {i: str(r[1]).strip().lower() for i, r in enumerate(rows, start=1)
                              if r[1] and str(r[1]).strip().lower() in ANALYSIS}

    # periods
    def col(self, p):
        return self.labels[p]

    def is_q(self, p):
        return bool(re.match(r"Q[1-4] \d\d", p))

    def forecast_quarters(self):
        return [p for p in self.order if self.is_q(p) and p.endswith("E")]

    def forecast_years(self):
        return [p for p in self.order if re.match(r"\d{4}E$", p) and any(self.fy_of(q) == p for q in self.forecast_quarters())]

    def fy_of(self, q):
        y = 2000 + int(q.split()[1][:2])
        return next(p for p in (f"{y}E", str(y)) if p in self.labels)

    def quarters_of(self, fy):
        yy = fy[2:4]
        return [p for p in self.order if self.is_q(p) and p.split()[1][:2] == yy]

    def prev(self, q):
        qs = [p for p in self.order if self.is_q(p)]
        i = qs.index(q)
        if i == 0:
            raise ValueError(f"no quarter before {q}")
        return qs[i - 1]

    def pyq(self, q):
        n, yy = q.split()
        target = f"{n} {int(yy[:2]) - 1:02d}"
        return next(p for p in self.order if p.rstrip("E") == target)

    # rows
    def row(self, key):
        if key not in self.keys:
            raise KeyError(f"no MOD row '{key}' (see rowmap)")
        return self.keys[key]

    def analysis(self, key, name):
        r = self.row(key) + 1
        while r in self.analysis_rows:
            if self.analysis_rows[r] == name.lower():
                return r
            r += 1
        raise KeyError(f"no '{name}' row under '{key}'")


def rowmap(path, out):
    m = ModMap(path)
    L_ = ["# MOD rows (key | row | unit | analysis rows under it)", ""]
    for i, key, unit in m.lines:
        an = []
        r = i + 1
        while r in m.analysis_rows:
            an.append(m.analysis_rows[r])
            r += 1
        L_.append(f"- `{key}` | {i} | {unit or ''} | {', '.join(an)}")
    L_ += ["", "Forecast quarters: " + ", ".join(m.forecast_quarters()), "Forecast years: " + ", ".join(m.forecast_years())]
    open(out, "w", encoding="utf-8").write("\n".join(L_) + "\n")


if __name__ == "__main__":
    if sys.argv[1] == "rowmap":
        rowmap(sys.argv[2], sys.argv[3])
