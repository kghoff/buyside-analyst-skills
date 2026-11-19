# skills/write-pitch/scripts/plan.py
"""Structure check of the agent's pitch_plan.json. anchors.py then checks the numbers against the model.

check(plan, valuation_verdict, short_verdict) returns plain-English problems, one per line; [] means the plan is sound.
usage: python3 plan.py --plan pitch_plan.json [--valuation-verdict Buy] [--short-verdict "no short"]
(prints the problems, or "plan OK"; exit 1 if any)"""
import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))   # run with python3 -I
from common import BUDGET  # noqa: E402
from common import CALLS  # noqa: E402
from common import CORE_TYPES  # noqa: E402
from common import HURDLES  # noqa: E402
from common import SUM_BOXES  # noqa: E402
from common import SUPPORT_LAYOUTS  # noqa: E402
from common import load  # noqa: E402

HOLDER = re.compile(r"\{(\w+)\}")
VERDICT_CALL = {"Buy": "Long", "Sell": "Short", "Hold": "Watch"}
SUPPORT_TEXT = ("bullets", "body", "text", "left", "right")     # body text of a support slide -> box budget


def _num(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _text(x):
    return isinstance(x, str) and x.strip() != ""


def _strings(x):
    """Every string inside x."""
    if isinstance(x, str):
        yield x
    elif isinstance(x, dict):
        for v in x.values():
            yield from _strings(v)
    elif isinstance(x, list):
        for v in x:
            yield from _strings(v)


def _as_list(x):
    return x if isinstance(x, list) else ([] if x is None else [x])


def _fields(slide, quotes):
    """(where, budget key, text) for each budgeted text of one slide."""
    core = slide.get("section") is None
    yield "title", "title", slide.get("title")
    yield "takeaway", "takeaway", slide.get("takeaway")
    yield "notes", "note", slide.get("notes")
    for k in ("bullets",) if core else SUPPORT_TEXT:
        for t in _as_list(slide.get(k)):
            yield k, "bullet" if core else "box", t
    for i, p in enumerate(_as_list(slide.get("points")), 1):
        if isinstance(p, dict):
            yield f"point {i} head", "bullet", p.get("head")
            yield f"point {i} body", "bullet", p.get("body")
    for i, r in enumerate(_as_list(slide.get("risks")), 1):
        if isinstance(r, dict):
            yield f"risk {i} head", "bullet", r.get("head")
            yield f"risk {i} if_hits", "box", r.get("if_hits")
            yield f"risk {i} mitigant", "box", r.get("mitigant")
    for i, t in enumerate(_as_list(slide.get("tripwires")), 1):
        yield f"tripwire {i}", "bullet", t
    for i, c in enumerate(_as_list(slide.get("cases")), 1):
        if isinstance(c, dict):
            for k, v in c.items():
                yield f"case {i} {k}", "cell", v
    tbl = slide.get("table")
    if isinstance(tbl, dict):
        for row in [tbl.get("header") or []] + _as_list(tbl.get("rows")):
            for cell in _as_list(row):
                yield "table cell", "cell", cell
    for q in _as_list(slide.get("quotes")):
        if q in quotes:
            yield f"quote {q}", "quote", quotes[q]


def _holders(plan):
    """(where, key) for every {key} typed anywhere in the plan outside numbers and quotes."""
    parts = [("slide %d" % i, s) for i, s in enumerate(plan.get("slides") or [], 1)]
    parts += [(k, plan.get(k)) for k in ("pitch_20s", "most_important_thing", "pitch_sheet", "sum_boxes", "notes")]
    for where, part in parts:
        for s in _strings(part):
            for m in HOLDER.findall(s):
                yield where, m


def _numbers(plan, out):
    nums = plan.get("numbers")
    if not isinstance(nums, dict) or not nums:
        out.append("numbers: missing; every figure in the pitch must be a named number")
        return {}
    for k, n in nums.items():
        if not isinstance(n, dict):
            out.append(f"number {k}: must be an object with value, shown and anchor")
            continue
        if not _num(n.get("value")):
            out.append(f"number {k}: value must be a number, got {n.get('value')!r}")
        if not _text(n.get("shown")):
            out.append(f"number {k}: needs shown (the text printed on the slide)")
        if not _text(n.get("anchor")):
            out.append(f"number {k}: needs an anchor (Tab!Cell, file:line or calc: expression)")
    return nums


def _sub(s, nums):
    def one(m):
        n = nums.get(m.group(1))
        return str(n.get("shown")) if isinstance(n, dict) and isinstance(n.get("shown"), str) else m.group(0)
    return HOLDER.sub(one, str(s))


def _slides(plan, out):
    slides = plan.get("slides")
    if not isinstance(slides, list):
        out.append("slides: missing")
        return []
    for i, want in enumerate(CORE_TYPES):
        got = slides[i].get("type") if i < len(slides) and isinstance(slides[i], dict) else None
        if got != want:
            out.append(f"slide {i + 1}: expected the {want} slide here, got {got or 'nothing'}")
    for i, s in enumerate(slides[len(CORE_TYPES):], len(CORE_TYPES) + 1):
        if not isinstance(s, dict):
            continue
        if s.get("section") not in ("support", "appendix"):
            out.append(f"slide {i} ({s.get('type')}): needs section 'support' or 'appendix'")
        if s.get("type") not in SUPPORT_LAYOUTS:
            out.append(f"slide {i} ({s.get('type')}): support layout must be one of {', '.join(SUPPORT_LAYOUTS)}")
    for i, s in enumerate(slides, 1):
        if isinstance(s, dict):
            for k in ("notes", "source"):
                if not _text(s.get(k)):
                    out.append(f"slide {i} ({s.get('type')}): needs non-empty {k}")
        else:
            out.append(f"slide {i}: must be an object")
    return [(i, s) for i, s in enumerate(slides, 1) if isinstance(s, dict)]


def _shapes(slides, out):
    for i, s in slides:
        t = s.get("type")
        if t == "thesis" and len(_as_list(s.get("points"))) != 3:
            out.append(f"slide {i} (thesis): needs exactly 3 thesis points, has {len(_as_list(s.get('points')))}")
        if t == "risks":
            risks = _as_list(s.get("risks"))
            if len(risks) != 2:
                out.append(f"slide {i} (risks): needs exactly 2 risks, has {len(risks)}")
            for j, r in enumerate(risks, 1):
                p = r.get("prob") if isinstance(r, dict) else None
                if not (_num(p) and 0 < p < 1):
                    out.append(f"slide {i} (risks): risk {j} prob must be a number between 0 and 1, got {p!r}")
        if t == "risk_reward":
            names = {str(c.get("name", "")).strip().lower() for c in _as_list(s.get("cases")) if isinstance(c, dict)}
            for need in ("bull", "base", "bear"):
                if need not in names:
                    out.append(f"slide {i} (risk_reward): cases are missing the {need} case")


def _text_checks(plan, slides, nums, out):
    keys = set(nums)
    quotes = {q.get("id"): q.get("text") for q in plan.get("quotes") or [] if isinstance(q, dict)}
    for where, k in _holders(plan):
        if k not in keys:
            out.append(f"{where}: {{{k}}} is not defined in numbers")
    for i, s in slides:
        for q in _as_list(s.get("quotes")):
            if q not in quotes:
                out.append(f"slide {i} ({s.get('type')}): quote id {q} is not in quotes")
        for where, kind, text in _fields(s, quotes):
            _budget(f"slide {i} ({s.get('type')}) {where}", kind, text, nums, out)
    sheet = plan.get("pitch_sheet") or {}
    for n, t in enumerate(_as_list(sheet.get("napkin")), 1):
        _budget(f"pitch_sheet napkin {n}", "bullet", t, nums, out)
    for name, t in (plan.get("sum_boxes") or {}).items():
        if t is not None:
            _budget(f"sum_boxes {name}", "box", t, nums, out)


def _budget(where, kind, text, nums, out):
    if not isinstance(text, str):
        return
    n = len(_sub(text, nums))
    if n > BUDGET[kind]:
        out.append(f"{where}: {n} characters after the numbers are filled in, over the {kind} limit of {BUDGET[kind]}")


def _sheet(plan, nums, out):
    sheet = plan.get("pitch_sheet")
    if not isinstance(sheet, dict):
        out.append("pitch_sheet: missing")
        return
    for k in _as_list(sheet.get("know_cold")):
        if k not in nums:
            out.append(f"pitch_sheet know_cold: {k} is not in numbers")
    if not 3 <= len(_as_list(sheet.get("hard_questions"))) <= 5:
        out.append(f"pitch_sheet hard_questions: needs 3 to 5 items, has {len(_as_list(sheet.get('hard_questions')))}")
    boxes = plan.get("sum_boxes")
    for k in (boxes or {}):
        if k not in SUM_BOXES:
            out.append(f"sum_boxes: {k!r} is not one of the SUM boxes ({', '.join(SUM_BOXES)})")


def _override_ok(o):
    return isinstance(o, dict) and _text(o.get("reason")) and _text(o.get("evidence"))


def _call(plan, nums, val, short, out):
    call = plan.get("call")
    if call not in CALLS:
        out.append(f"call: must be one of {', '.join(CALLS)}, got {call!r}")
        return
    ov = _override_ok(plan.get("override"))
    if call == "Short" and short != "alpha short":
        out.append(f"call is Short but the short verdict is {short!r}; a short needs the verdict 'alpha short'")
    if val in VERDICT_CALL and VERDICT_CALL[val] != call and not ov:
        out.append(f"override: the call {call} differs from the Valuation verdict {val} ({VERDICT_CALL[val]}); "
                   f"override needs a non-empty reason and evidence")
    if call != "Long":
        return
    v = {k: (nums.get(k) or {}).get("value") for k in ("irr_3y", "base_ret", "risk_ret")}
    missing = [k for k, x in v.items() if not _num(x)]
    if missing:
        out.append(f"call is Long but numbers {', '.join(missing)} is missing: the hurdle check can't run")
        return
    rr = v["base_ret"] / abs(v["risk_ret"]) if v["risk_ret"] else float("inf")
    if v["irr_3y"] < HURDLES["irr"] and rr < HURDLES["buy_rr"] and not ov:
        out.append(f"call is Long but misses both hurdles (3-year IRR {v['irr_3y']:.1%} under {HURDLES['irr']:.0%}, "
                   f"R/R {rr:.1f} under {HURDLES['buy_rr']:.1f}); make the call Watch or give an override")


def check(plan, valuation_verdict=None, short_verdict=None):
    out = []
    nums = _numbers(plan, out)
    slides = _slides(plan, out)
    _shapes(slides, out)
    _text_checks(plan, slides, nums, out)
    _sheet(plan, nums, out)
    sv = plan.get("starting_verdicts") or {}
    _call(plan, nums, valuation_verdict or sv.get("valuation"), short_verdict or sv.get("short"), out)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--plan", required=True)
    ap.add_argument("--valuation-verdict")
    ap.add_argument("--short-verdict")
    a = ap.parse_args(argv)
    problems = check(load(a.plan), a.valuation_verdict, a.short_verdict)
    print("\n".join(problems) if problems else "plan OK")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
