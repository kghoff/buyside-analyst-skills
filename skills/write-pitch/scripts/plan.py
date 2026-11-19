# skills/write-pitch/scripts/plan.py
"""Structure check of the agent's pitch_plan.json. anchors.py then checks the numbers against the model.

check(plan, valuation_verdict, short_verdict, hurdles) returns plain-English problems, one per line; [] means the plan
is sound. Each line starts with its rule id ([R1] ...), the same id plan_schema.md section 12 gives the rule.
usage: python3 plan.py --plan pitch_plan.json [--valuation-verdict Buy] [--short-verdict "Alpha short"]
       [--irr-hurdle 0.2] [--buy-rr 2] [--pound-rr 3]
(the hurdles are the Valuation tab's inputs; common.HURDLES when not given. Prints the problems, or "plan OK";
exit 1 if any)"""
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
VERDICT_CALL = {"buy": "Long", "sell": "Short", "hold": "Watch"}
REQUIRED = ("price", "base_ret", "risk_ret", "irr_3y", "target_3y", "buy_price", "nobrainer_price")
KNOW_COLD = ("price", "base_ret", "risk_ret", "irr_3y", "buy_price")
BULLETS = {"summary": (3, 5), "setup": (3, 5), "why_now": (3, 5), "valuation": (2, 4), "different": (2, 4),
           "catalysts": (3, 6), "text_chart": (2, 5)}       # bullets per slide type; summary's are optional
SUPPORTS = ("thesis.1", "thesis.2", "thesis.3", "risks.1", "risks.2")
SUPPORT_COUNT = (10, 25)                                     # support slides in the long deck
CHECKLIST_ITEMS = (3, 15)
KEY = re.compile(r"^[a-z0-9_]+$")


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
    """(where, budget key, text) for each budgeted text of one slide (plan_schema.md section 11)."""
    yield "title", "title", slide.get("title")
    yield "takeaway", "takeaway", slide.get("takeaway")
    yield "notes", "note", slide.get("notes")
    for k in ("caption", "bucket", "lead"):
        yield k, "bullet", slide.get(k)
    for k in ("bullets", "tripwires"):
        for i, t in enumerate(_as_list(slide.get(k)), 1):
            yield f"{k[:-1]} {i}", "bullet", t
    for i, p in enumerate(_as_list(slide.get("points")), 1):
        if isinstance(p, dict):
            yield f"point {i} head", "bullet", p.get("head")
            yield f"point {i} body", "box", p.get("body")
    for i, r in enumerate(_as_list(slide.get("risks")), 1):
        if isinstance(r, dict):
            for k in ("head", "if_hits", "mitigant"):
                yield f"risk {i} {k}", "bullet", r.get(k)
    for side in ("left", "right"):
        col = slide.get(side)
        if isinstance(col, dict):
            yield f"{side} head", "bullet", col.get("head")
            for i, t in enumerate(_as_list(col.get("bullets")), 1):
                yield f"{side} bullet {i}", "bullet", t
    for i, c in enumerate(_as_list(slide.get("cases")), 1):
        if isinstance(c, dict):
            for k, v in c.items():
                yield f"case {i} {k}", "cell", v
    if isinstance(slide.get("short"), dict):
        for k, v in slide["short"].items():
            yield f"short {k}", "bullet", v
    for i, it in enumerate(_as_list(slide.get("items")), 1):
        if isinstance(it, dict):
            yield f"item {i} q", "bullet", it.get("q")
            yield f"item {i} a", "cell", it.get("a")
    yield "irr", "cell", slide.get("irr")
    if isinstance(slide.get("three_rs"), dict):
        for k, v in slide["three_rs"].items():
            yield f"three_rs {k}", "cell", v
    tbl = slide.get("table")
    if isinstance(tbl, dict):
        for row in [tbl.get("header") or []] + _as_list(tbl.get("rows")):
            for cell in _as_list(row):
                yield "table cell", "cell", cell
    for q in _as_list(slide.get("quotes")):
        if isinstance(q, str) and q in quotes:
            yield f"quote {q}", "quote", quotes[q]


def _holders(plan):
    """(where, key) for every {key} typed anywhere in the plan outside numbers and quotes."""
    parts = [("slide %d" % i, s) for i, s in enumerate(plan.get("slides") or [], 1)]
    parts += [(k, plan.get(k))
              for k in ("action", "pitch_20s", "most_important_thing", "pitch_sheet", "sum_boxes", "notes")]
    for where, part in parts:
        for s in _strings(part):
            for m in HOLDER.findall(s):
                yield where, m


def _numbers(plan, out):
    nums = plan.get("numbers")
    if not isinstance(nums, dict) or not nums:
        out.append("[R3] numbers: missing; every figure in the pitch must be a named number")
        return None
    gone = [k for k in REQUIRED if k not in nums]
    if gone:
        out.append(f"[R3] numbers: missing required keys {', '.join(gone)}")
    for k, n in nums.items():
        if not KEY.match(str(k)):
            out.append(f"[R4] number {k}: key must be lower case letters, digits and _")
        if not isinstance(n, dict):
            out.append(f"[R4] number {k}: must be an object with value, shown and anchor")
            continue
        if not _num(n.get("value")):
            out.append(f"[R4] number {k}: value must be a number, got {n.get('value')!r}")
        if not _text(n.get("shown")):
            out.append(f"[R4] number {k}: needs shown (the text printed on the slide)")
        if not _text(n.get("anchor")):
            out.append(f"[R4] number {k}: needs an anchor (Tab!Cell, file:line or calc: expression)")
    return nums


def _sub(s, nums):
    def one(m):
        n = nums.get(m.group(1))
        return str(n.get("shown")) if isinstance(n, dict) and isinstance(n.get("shown"), str) else m.group(0)
    return HOLDER.sub(one, str(s))


def _slides(plan, out):
    slides = plan.get("slides")
    if not isinstance(slides, list):
        out.append("[R5] slides: missing")
        return []
    for i, want in enumerate(CORE_TYPES):
        got = slides[i].get("type") if i < len(slides) and isinstance(slides[i], dict) else None
        if got != want:
            out.append(f"[R5] slide {i + 1}: expected the {want} slide here, got {got or 'nothing'}")
    for i, s in enumerate(slides[len(CORE_TYPES):], len(CORE_TYPES) + 1):
        if not isinstance(s, dict):
            continue
        if s.get("section") not in ("support", "appendix"):
            out.append(f"[R6] slide {i} ({s.get('type')}): needs section 'support' or 'appendix'")
        if s.get("type") not in SUPPORT_LAYOUTS:
            out.append(f"[R6] slide {i} ({s.get('type')}): support layout must be one of {', '.join(SUPPORT_LAYOUTS)}")
    for i, s in enumerate(slides, 1):
        if isinstance(s, dict):
            for k in ("notes", "source"):
                if not _text(s.get(k)):
                    out.append(f"[R7] slide {i} ({s.get('type')}): needs non-empty {k}")
        else:
            out.append(f"[R7] slide {i}: must be an object")
    return [(i, s) for i, s in enumerate(slides, 1) if isinstance(s, dict)]


def _items(rid, i, t, s, key, label, fields, out):
    """Items of a list on slide i must be objects with every field non-empty; returns the list."""
    items = _as_list(s.get(key))
    for j, x in enumerate(items, 1):
        if not isinstance(x, dict):
            out.append(f"[{rid}] slide {i} ({t}): {label} {j} must be an object with {', '.join(fields)}")
            continue
        for f in fields:
            if not _text(x.get(f)):
                out.append(f"[{rid}] slide {i} ({t}): {label} {j} needs a non-empty {f}")
    return items


def _count(i, t, s, key, lo, hi, out, label=None):
    n = len(_as_list(s.get(key)))
    if not lo <= n <= hi and not (n == 0 and t == "summary"):
        out.append(f"[R8] slide {i} ({t}): needs {lo} to {hi} {label or key}, has {n}")


def _shapes(slides, out):
    covered, n_support = set(), 0
    for i, s in slides:
        t = s.get("type")
        if t in BULLETS:
            _count(i, t, s, "bullets", *BULLETS[t], out)
        if t in ("risks", "catalysts"):
            _count(i, t, s, "tripwires", 2 if t == "risks" else 0, 4, out)
        if t == "quote":
            _count(i, t, s, "quotes", 1, 3, out, "quote ids")
        if t == "two_column":
            for side in ("left", "right"):
                c = s.get(side)
                if not (isinstance(c, dict) and _text(c.get("head")) and isinstance(c.get("bullets"), list)):
                    out.append(f"[R8] slide {i} (two_column): {side} must be an object with head and bullets")
        if t == "checklist":
            _items("R8", i, t, s, "items", "item", ("q", "a"), out)
            _count(i, t, s, "items", *CHECKLIST_ITEMS, out)
        if s.get("section") == "support":
            n_support += 1
            sup = s.get("supports")
            if sup not in SUPPORTS:
                out.append(f"[R12] slide {i} ({t}): supports must be one of {', '.join(SUPPORTS)}, got {sup!r}")
            else:
                covered.add(sup)
        if t == "thesis":
            pts = _items("R9", i, t, s, "points", "thesis point", ("head", "body"), out)
            if len(pts) != 3:
                out.append(f"[R9] slide {i} (thesis): needs exactly 3 thesis points, has {len(pts)}")
        if t == "risks":
            risks = _items("R10", i, t, s, "risks", "risk", ("head", "if_hits", "mitigant"), out)
            if len(risks) != 2:
                out.append(f"[R10] slide {i} (risks): needs exactly 2 risks, has {len(risks)}")
            for j, r in enumerate(risks, 1):
                p = r.get("prob") if isinstance(r, dict) else None
                if not (_num(p) and 0 < p < 1):
                    out.append(f"[R10] slide {i} (risks): risk {j} prob must be a number between 0 and 1, got {p!r}")
        if t == "risk_reward":
            names = {str(c.get("name", "")).strip().lower() for c in _as_list(s.get("cases")) if isinstance(c, dict)}
            for need in ("bull", "base", "bear"):
                if need not in names:
                    out.append(f"[R11] slide {i} (risk_reward): cases are missing the {need} case")
    if slides:    # every thesis point and risk needs a support slide behind it
        for sup in SUPPORTS:
            if sup not in covered:
                out.append(f"[R12] support slides: none supports {sup}; each thesis point and risk needs at least one")
        lo, hi = SUPPORT_COUNT
        if not lo <= n_support <= hi:
            out.append(f"[R12] support slides: needs {lo} to {hi} slides with section 'support', has {n_support}")


def _text_checks(plan, slides, nums, out):
    quotes = {}
    for q in _as_list(plan.get("quotes")):
        if isinstance(q, dict) and isinstance(q.get("id"), str):
            quotes[q["id"]] = q.get("text")
    if nums is not None:      # no numbers: already reported once, so skip the per-placeholder lines
        for where, k in _holders(plan):
            if k not in nums:
                out.append(f"[R13] {where}: {{{k}}} is not defined in numbers")
    nums = nums or {}
    for i, s in slides:
        for q in _as_list(s.get("quotes")):
            if not isinstance(q, str) or q not in quotes:
                out.append(f"[R15] slide {i} ({s.get('type')}): quote id {q!r} is not in quotes")
        for where, kind, text in _fields(s, quotes):
            _budget(f"slide {i} ({s.get('type')}) {where}", kind, text, nums, out)
    for k, kind in (("most_important_thing", "box"), ("pitch_20s", "box")):
        _budget(k, kind, plan.get(k), nums, out)
    sheet = plan.get("pitch_sheet") if isinstance(plan.get("pitch_sheet"), dict) else {}
    for n, t in enumerate(_as_list(sheet.get("script_3min")), 1):
        _budget(f"pitch_sheet script_3min {n}", "box", t, nums, out)
    for n, t in enumerate(_as_list(sheet.get("napkin")), 1):
        _budget(f"pitch_sheet napkin {n}", "bullet", t, nums, out)
    for n, h in enumerate(_as_list(sheet.get("hard_questions")), 1):
        if isinstance(h, dict):
            _budget(f"pitch_sheet hard question {n} q", "bullet", h.get("q"), nums, out)
            _budget(f"pitch_sheet hard question {n} a", "box", h.get("a"), nums, out)
    boxes = plan.get("sum_boxes") if isinstance(plan.get("sum_boxes"), dict) else {}
    for name, t in boxes.items():
        _budget(f"sum_boxes {name}", "box", t, nums, out)


def _typed(text):
    """Tokens that look like a typed measurement: with $ or %, 12x, or a decimal. Years and counts pass."""
    text = HOLDER.sub(" ", text)
    for tok in text.split():
        t = tok.strip(".,;:!?()[]\"'")
        if "$" in t or "%" in t or re.search(r"\d\.\d", t) or re.fullmatch(r"[\d.\-]+[xX]", t):
            yield t


def _budget(where, kind, text, nums, out):
    if not isinstance(text, str):
        return
    if kind != "quote":     # a quote keeps whatever numbers the speaker said
        for t in _typed(text):
            out.append(f"[R14] {where}: typed number {t!r}; use a {{key}} from numbers")
    n = len(_sub(text, nums))
    if n > BUDGET[kind]:
        out.append(f"[R16] {where}: {n} characters after the numbers are filled in, "
                   f"over the {kind} limit of {BUDGET[kind]}")


def _sheet(plan, nums, out):
    sheet = plan.get("pitch_sheet")
    if not isinstance(sheet, dict):
        out.append("[R17] pitch_sheet: missing or not an object")
        return
    kc = _as_list(sheet.get("know_cold"))
    for k in kc:
        if not isinstance(k, str) or k not in (nums or {}):
            out.append(f"[R17] pitch_sheet know_cold: {k} is not in numbers")
    gone = [k for k in KNOW_COLD if k not in kc]
    if gone:
        out.append(f"[R17] pitch_sheet know_cold: must include {', '.join(gone)}")
    n = len(_as_list(sheet.get("script_3min")))
    if n != 12:
        out.append(f"[R17] pitch_sheet script_3min: needs exactly 12 paragraphs, has {n}")
    n = len(_as_list(sheet.get("napkin")))
    if not 3 <= n <= 5:
        out.append(f"[R17] pitch_sheet napkin: needs 3 to 5 bullets, has {n}")
    hq = _as_list(sheet.get("hard_questions"))
    if not 3 <= len(hq) <= 5:
        out.append(f"[R17] pitch_sheet hard_questions: needs 3 to 5 items, has {len(hq)}")
    boxes = plan.get("sum_boxes")
    if boxes is not None and not isinstance(boxes, dict):
        out.append("[R18] sum_boxes: must be an object keyed by SUM box name")
    for k in (boxes if isinstance(boxes, dict) else {}):
        if k not in SUM_BOXES:
            out.append(f"[R18] sum_boxes: {k!r} is not one of the SUM boxes ({', '.join(SUM_BOXES)})")


def _override_ok(o):
    return isinstance(o, dict) and _text(o.get("reason")) and _text(o.get("evidence"))


def _call(plan, nums, val, short, hurdles, out):
    call = plan.get("call")
    if call not in CALLS:       # also catches an unhashable or non-string call
        out.append(f"[R2] call: must be one of {', '.join(CALLS)}, got {call!r}")
        return
    ov = _override_ok(plan.get("override"))
    val = val.strip().lower() if isinstance(val, str) else None
    short = short.strip().lower() if isinstance(short, str) else None
    if call == "Short" and short != "alpha short":
        out.append(f"[R19] call is Short but the short verdict is {short!r}; a short needs the verdict 'alpha short'")
    if val in VERDICT_CALL and VERDICT_CALL[val] != call and not ov:
        out.append(f"[R19] override: the call {call} differs from the Valuation verdict {val} ({VERDICT_CALL[val]}); "
                   f"override needs a non-empty reason and evidence")
    if call != "Long":
        return
    nums = nums or {}
    v = {k: nums[k].get("value") if isinstance(nums.get(k), dict) else None for k in ("irr_3y", "base_ret", "risk_ret")}
    missing = [k for k, x in v.items() if not _num(x)]
    if missing:
        out.append(f"[R20] call is Long but numbers {', '.join(missing)} are missing: the hurdle check can't run")
        return
    # a risk_ret of 0 means no downside, so R/R is infinite and the R/R hurdle is met
    rr = v["base_ret"] / abs(v["risk_ret"]) if v["risk_ret"] else float("inf")
    h = hurdles
    if v["irr_3y"] < h["irr"] and rr < h["buy_rr"] and not ov:
        out.append(f"[R20] call is Long but misses both hurdles (3-year IRR {v['irr_3y']:.1%} under {h['irr']:.0%}, "
                   f"R/R {rr:.1f} under {h['buy_rr']:g}); make the call Watch or give an override")
    act = plan.get("action")
    if isinstance(act, str) and "pound" in act.lower() and rr < h["pound_rr"]:
        out.append(f"[R21] action {act!r} pounds the table but the R/R is {rr:.1f}, under {h['pound_rr']:g}; "
                   f"size the action down (e.g. Buy)")


def _verdict(x):
    return x if isinstance(x, str) else None


def check(plan, valuation_verdict=None, short_verdict=None, hurdles=None):
    """hurdles: {"irr", "buy_rr", "pound_rr"} from the Valuation tab; any key left out falls back to common.HURDLES."""
    h = dict(HURDLES)
    h.update({k: v for k, v in (hurdles or {}).items() if v is not None})
    if not isinstance(plan, dict):
        return ["[R1] plan: the file must hold one JSON object"]
    out = []
    nums = _numbers(plan, out)
    slides = _slides(plan, out)
    _shapes(slides, out)
    _text_checks(plan, slides, nums, out)
    _sheet(plan, nums, out)
    sv = plan.get("starting_verdicts") if isinstance(plan.get("starting_verdicts"), dict) else {}
    _call(plan, nums, valuation_verdict or _verdict(sv.get("valuation")),
          short_verdict or _verdict(sv.get("short")), h, out)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--plan", required=True)
    ap.add_argument("--valuation-verdict")
    ap.add_argument("--short-verdict")
    ap.add_argument("--irr-hurdle", type=float, help="Valuation tab's IRR hurdle as a fraction (0.2)")
    ap.add_argument("--buy-rr", type=float, help="Valuation tab's Buy at R/R (2)")
    ap.add_argument("--pound-rr", type=float, help="Valuation tab's Table-pound at R/R (3)")
    a = ap.parse_args(argv)
    try:
        plan = load(a.plan)
    except ValueError as e:
        print(f"[R1] plan: not valid JSON ({e})")
        return 1
    problems = check(plan, a.valuation_verdict, a.short_verdict,
                     {"irr": a.irr_hurdle, "buy_rr": a.buy_rr, "pound_rr": a.pound_rr})
    print("\n".join(problems) if problems else "plan OK")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
