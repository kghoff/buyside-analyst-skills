"""The agent's compact DCF driver sets, expanded into model-dcf inputs ({name: {year: v}} per-year, wacc / tv_mult single).

A case's `inputs` overrides the user's current DCF inputs by model-dcf's input names; anything not listed keeps the
user's value. A per-year input takes a number (every input year), {"years": {label: v}} (only those years) or
{"from": a, "to": b, "over": n} (input year i, 1-based, gets a + (b - a) * min(i, n) / n: dcfmath.defaults' fade).
Pure: no model-dcf import (scenario_eval.py runs it inside model-dcf's process)."""
import copy

CASES = ("base", "bull", "bear")
SINGLE = ("wacc", "tv_mult")


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def expand(spec, base, years, names):
    """spec: one case's compact inputs; base: the user's inputs (never mutated); years: the input year labels;
    names: the allowed input names. Returns a full input set (a deep copy of base with spec applied)."""
    out = copy.deepcopy(base)
    for name, v in (spec or {}).items():
        if name not in names:
            raise ValueError(f"unknown DCF input {name!r}; allowed: {', '.join(names)}")
        if name in SINGLE:
            if not _num(v):
                raise ValueError(f"{name} must be a number, got {v!r}")
            out[name] = float(v)
            continue
        row = dict(out.get(name, {}))
        if _num(v):
            row = {y: v for y in years}
        elif isinstance(v, dict) and set(v) == {"years"}:
            bad = [y for y in v["years"] if y not in years]
            if bad:
                raise ValueError(f"{name}: {', '.join(bad)} not an input year ({years[0]}-{years[-1]})")
            row.update(v["years"])
        elif isinstance(v, dict) and set(v) == {"from", "to", "over"} and int(v["over"]) >= 1:
            a, b, n = v["from"], v["to"], int(v["over"])
            row = {y: a + (b - a) * min(i, n) / n for i, y in enumerate(years, 1)}
        else:
            raise ValueError(f"{name}: expected a number, {{'years': {{...}}}} or {{'from', 'to', 'over'}}, got {v!r}")
        out[name] = row
    return out


def check_cases(t):
    """The try's cases dict; base, bull and bear are required."""
    cases = t.get("cases") or {}
    missing = [c for c in CASES if c not in cases]
    if missing:
        raise ValueError(f"the try needs cases base, bull and bear; missing {', '.join(missing)}")
    return cases
