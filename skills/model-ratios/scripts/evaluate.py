"""Recalculate formulas the way Excel would, for the subset model-historicals and model-ratios write:
+ - * / ( ), numbers, references (A1, $A$1, MOD!A1), SUM(range), IFERROR, IF(ISBLANK(ref),...), string literals.
Blank cells count as 0 in arithmetic (Excel's rule); "" or text in arithmetic is an error (#VALUE!).
openpyxl doesn't calculate, so this is how verify.py and the outlier flags read numbers."""
import re
import sys

from openpyxl.utils import get_column_letter as L, column_index_from_string as CI

sys.setrecursionlimit(20000)       # beginning-cash links chain across every column


class _Err:
    def __repr__(self):
        return "ERR"


ERR = _Err()


class _Txt(str):
    """Text read from a cell: passes through a plain link, but any arithmetic on it is an error (Excel #VALUE!)."""
    def _bad(self, *a):
        raise TypeError("text in arithmetic")
    __add__ = __radd__ = __sub__ = __rsub__ = __mul__ = __rmul__ = __truediv__ = __rtruediv__ = _bad
    __neg__ = __pos__ = _bad

_TOK = re.compile(
    r'(?P<str>"[^"]*")'
    r'|ISBLANK\((?:(?P<bs>[A-Za-z_]+)!)?\$?(?P<bc>[A-Z]{1,3})\$?(?P<br>\d+)\)'
    r'|SUM\((?:(?P<ss>[A-Za-z_]+)!)?\$?(?P<sc1>[A-Z]{1,3})\$?(?P<sr1>\d+):\$?(?P<sc2>[A-Z]{1,3})\$?(?P<sr2>\d+)\)'
    r'|(?P<fn>IFERROR|IF)\('
    r'|(?:(?P<rs>[A-Za-z_]+)!)?\$?(?P<rc>[A-Z]{1,3})\$?(?P<rr>\d+)')


def _to_python(body):
    def rep(m):
        g = m.groupdict()
        if g["str"]:
            return g["str"]
        if g["bc"]:
            return f"_isblank({g['bs']!r},'{g['bc']}{g['br']}')"
        if g["sc1"]:
            return f"_sum({g['ss']!r},'{g['sc1']}{g['sr1']}','{g['sc2']}{g['sr2']}')"
        if g["fn"] == "IFERROR":
            return "_iferror(lambda: "
        if g["fn"] == "IF":
            return "_if("
        return f"_v({g['rs']!r},'{g['rc']}{g['rr']}')"
    return _TOK.sub(rep, body)


def _iferror(f, alt):
    try:
        x = f()
    except Exception:
        return alt
    return alt if x is ERR else x


class Book:
    def __init__(self, wb):
        self.wb, self.memo = wb, {}

    def raw(self, sheet, ref):
        return self.wb[sheet][ref].value

    def value(self, sheet, ref):
        """Calculated value of one cell: number, string, None (blank) or ERR."""
        key = (sheet, ref)
        if key in self.memo:
            return self.memo[key]
        x = self.raw(sheet, ref)
        if isinstance(x, str) and x.startswith("="):
            env = {
                "_v": lambda s, r: self._num(s or sheet, r),
                "_sum": lambda s, a, b: self._sum(s or sheet, a, b),
                "_isblank": lambda s, r: self.raw(s or sheet, r) in (None, ""),
                "_iferror": _iferror,
                "_if": lambda cond, a, b: a if cond else b,
            }
            try:
                x = eval(_to_python(x[1:]), env)
            except Exception:
                x = ERR
        self.memo[key] = x
        return x

    def _num(self, sheet, ref):
        x = self.value(sheet, ref)
        if x is ERR:
            raise ValueError("error in referenced cell")
        return 0.0 if x is None else _Txt(x) if isinstance(x, str) else x

    def _sum(self, sheet, a, b):
        ca, ra = re.match(r"([A-Z]+)(\d+)", a).groups()
        cb, rb = re.match(r"([A-Z]+)(\d+)", b).groups()
        total = 0.0
        for c in range(CI(ca), CI(cb) + 1):
            for r in range(int(ra), int(rb) + 1):
                x = self.value(sheet, f"{L(c)}{r}")
                if x is ERR:
                    raise ValueError("error in summed cell")
                if isinstance(x, (int, float)) and not isinstance(x, bool):
                    total += x
        return total
