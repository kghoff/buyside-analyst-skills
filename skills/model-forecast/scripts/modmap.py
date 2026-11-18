"""The user's MOD tab layout: period columns (row 2) and row keys ('<section> | <label>').

usage: python3 modmap.py rowmap <model.xlsx> <out.md>     (the row list the plan agent picks keys from)
Analysis rows (% yoy, % of sales, ...) are not keys of their own: ModMap.analysis(key, name) finds the one under a line.
Duplicate labels in a section are numbered (#2, ...); a row with a unit or a number takes the plain key before a
label-only row (ModMap.label_only), so a layout group named like its own line never takes the line's key."""
import re
import sys

import openpyxl
from openpyxl.utils import get_column_letter as L

ANALYSIS = {"% yoy", "% 2 year", "% qoq", "% of sales", "% margin", "bps yoy", "incremental margin", "% of total rev",
            "% 5 year", "seasonality", "ttm"}


class ModMap:
    def __init__(self, path, tab="MOD"):
        ws = openpyxl.load_workbook(path, read_only=True)[tab]
        full = list(ws.iter_rows(min_row=1, values_only=True))
        rows = [(tuple(r) + (None,) * 3)[:3] for r in full]
        self.labels = {}                                   # period label -> column letter
        hdr = next(ws.iter_rows(min_row=2, max_row=2, values_only=True))
        for k, v in enumerate(hdr, start=1):
            if v is not None and k > 3:
                self.labels[str(v).strip()] = L(k)
        self.order = list(self.labels)
        pcols = [k - 1 for k, v in enumerate(hdr, start=1) if v is not None and k > 3]
        self.keys, self.lines, self.label_only, section, found = {}, [], set(), "", []
        for i, (a, b, c) in enumerate(rows, start=1):
            if a:
                section = str(a).strip()
            if not b:
                continue
            lab = str(b).strip()
            if lab.lower() in ANALYSIS:
                continue
            if c in (None, "") and all(full[i - 1][k] in (None, "") for k in pcols if k < len(full[i - 1])):
                self.label_only.add(i)                     # no unit, no number (a new row, or a layout group name)
            found.append((i, f"{section} | {lab}", c))
        seen, names = {}, {}
        for i, key, c in sorted(found, key=lambda x: x[0] in self.label_only):   # a row with data takes the plain key
            seen[key] = seen.get(key, 0) + 1
            names[i] = key if seen[key] == 1 else f"{key} #{seen[key]}"
        for i, key, c in found:
            self.keys[names[i]] = i
            self.lines.append((i, names[i], c))
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
