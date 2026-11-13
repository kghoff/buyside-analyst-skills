"""Period map for a house-layout sheet: which column is which quarter / fiscal year, and which column each
analysis compares against. Same rules as the house Excel macros, BuySideMacros.bas (not included in this repo: ParsePeriod / CompareCol / FillTTM):
yoy = same period last year, 2 year = two years ago, qoq = previous quarter (Q1 -> last year's Q4, none for FY)."""
import re

HDR = 2          # model-historicals writes period labels in row 2
FIRST_COL = 4    # data starts in column D


def parse_period(v):
    """Header label -> (q, y, est): q = 1-4 for a quarter, 0 for a fiscal year; est = True for an E column."""
    if isinstance(v, int) and 1900 < v < 2100:
        return (0, v, False)
    if not isinstance(v, str):
        return None
    s = v.strip().upper()
    m = re.fullmatch(r"Q([1-4]) (\d{2})(E?)", s)
    if m:
        return (int(m.group(1)), 2000 + int(m.group(2)), bool(m.group(3)))
    m = re.fullmatch(r"(\d{4})(E?)", s)
    if m:
        return (0, int(m.group(1)), bool(m.group(2)))
    return None


class Periods:
    def __init__(self, ws, hdr=HDR):
        self.cols = {}
        for c in range(FIRST_COL, ws.max_column + 1):
            p = parse_period(ws.cell(hdr, c).value)
            if p:
                self.cols[c] = p
        self.at = {(q, y): c for c, (q, y, _) in self.cols.items()}

    def find(self, q, y):
        return self.at.get((q, y))

    def is_est(self, c):
        return self.cols[c][2]

    def label(self, c):
        q, y, est = self.cols[c]
        return (f"FY {y}" if q == 0 else f"Q{q} {y % 100:02d}") + ("E" if est else "")

    def yoy(self, c):
        q, y, _ = self.cols[c]
        return self.find(q, y - 1)

    def two_year(self, c):
        q, y, _ = self.cols[c]
        return self.find(q, y - 2)

    def qoq(self, c):
        q, y, _ = self.cols[c]
        if q == 0:
            return None
        return self.find(4, y - 1) if q == 1 else self.find(q - 1, y)

    def prev_end(self, c):
        """Previous balance-sheet date: prior quarter-end for a quarter (Q1 -> last year's Q4), prior FY-end for a year."""
        q, y, _ = self.cols[c]
        return self.find(0, y - 1) if q == 0 else self.qoq(c)

    def ttm(self, c):
        """Columns that sum to trailing twelve months, newest first. FY = the year itself; None without 4 quarters."""
        q, y, _ = self.cols[c]
        if q == 0:
            return [c]
        out = []
        for _ in range(4):
            k = self.find(q, y)
            if k is None:
                return None
            out.append(k)
            q, y = (q - 1, y) if q > 1 else (4, y - 1)
        return out

    def fy_col(self, c):
        return self.find(0, self.cols[c][1])

    def latest_reported_fy(self):
        ys = [y for (q, y, est) in self.cols.values() if q == 0 and not est]
        return self.find(0, max(ys)) if ys else None
