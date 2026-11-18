# skills/model-earnings-before/scripts/plan.py
"""Shape and rule check of the agent's earnings_plan.json (chapter 13's discipline). anchors.py then checks that
each anchored number and quote is really where it says.

check(plan, context) returns plain-English problems; [] means the plan may be built.
usage: python3 plan.py --plan earnings_plan.json --context context.json   (prints problems; exit 1 if any)"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))   # run with python3 -I
import earnmath as em  # noqa: E402

CELL = re.compile(r"^(?P<sheet>[A-Za-z' &]+)!\$?[A-Z]{1,3}\$?\d+$")
LINE = re.compile(r"^.+\.md:\d+$")
REASON, OVERRIDE = 8, 12


def words(s):
    return len(str(s or "").split())


def _anchored(name, x, out):
    """A judgment that takes a side rests on a line (with its quote or number) or a cell (with the value it shows)."""
    a = x.get("anchor")
    if not isinstance(a, str) or not (LINE.match(a) or CELL.match(a)):
        out.append(f"{name}: a long or short side needs an anchor (file.md:line or Sheet!$A$1)"
                   if name.startswith("setup.") else f"{name}: needs an anchor (file.md:line or Sheet!$A$1)")
    elif LINE.match(a) and not x.get("quote") and "anchor_value" not in x:
        out.append(f"{name}: a line anchor needs the quote (or anchor_value) it rests on")
    elif CELL.match(a) and "anchor_value" not in x:
        out.append(f"{name}: a cell anchor needs the anchor_value the cell shows")


def _setup(plan, ctx, out):
    sides, setup = {}, plan.get("setup") or {}
    for rid, label, _, _, code in em.SETUP:
        x = setup.get(rid)
        if code and x is None:
            continue                                      # code answers it
        if not isinstance(x, dict):
            out.append(f"setup.{rid}: missing ({label})")
            continue
        side = x.get("side")
        if side not in em.SIDES:
            out.append(f"setup.{rid}: side must be one of {', '.join(em.SIDES)}, got {side!r}")
            continue
        if code and side != ctx["code"]["setup"].get(rid) and words(x.get("reason")) < OVERRIDE:
            out.append(f"setup.{rid}: overriding code's side ({ctx['code']['setup'].get(rid)}) needs a reason of at "
                       f"least {OVERRIDE} words")
        elif words(x.get("reason")) < REASON:
            out.append(f"setup.{rid}: the reason needs at least {REASON} words")
        if side in ("long", "short") and not code:
            _anchored(f"setup.{rid}", x, out)
        sides[rid] = side
    return sides


def _inputs(plan, out):
    inp = plan.get("inputs") or {}
    vals = {}
    for k in em.AGENT_INPUTS:
        x = inp.get(k)
        if not isinstance(x, dict):
            out.append(f"inputs.{k}: missing")
            continue
        v = x.get("value")
        if not em._n(v):
            out.append(f"inputs.{k}: value must be a number, got {v!r}")
            continue
        if k == "p_beat" and not 0 <= v <= 1:
            out.append("inputs.p_beat: must be between 0 and 1 (a probability)")
        if k.endswith("_pe") and v <= 0:
            out.append(f"inputs.{k}: a P/E must be above 0")
        if x.get("anchor") == "judgment":
            if words(x.get("reason")) < OVERRIDE:
                out.append(f"inputs.{k}: a judgment needs a reason of at least {OVERRIDE} words")
        else:
            _anchored(f"inputs.{k}", x, out)
            if words(x.get("reason")) < REASON:
                out.append(f"inputs.{k}: the reason needs at least {REASON} words")
        vals[k] = v
    return vals


def check(plan, ctx):
    out = []
    if plan.get("quarter") != ctx["quarter"]:
        out.append(f"quarter: the plan is for {plan.get('quarter')!r}; the quarter being reported is {ctx['quarter']}")
    km = plan.get("key_metric") or {}
    if not str(km.get("value") or "").strip() or words(km.get("reason")) < REASON:
        out.append(f"key_metric: needs a value and a reason of at least {REASON} words")
    _anchored("key_metric", km, out)
    sides = _setup(plan, ctx, out)
    for rid, label in em.RISKS:
        x = (plan.get("risks") or {}).get(rid) or {}
        if x.get("score") not in (1, 2, 3, 4, 5) or isinstance(x.get("score"), bool):
            out.append(f"risks.{rid}: score must be a whole number from 1 (lowest) to 5 ({label})")
        if words(x.get("reason")) < REASON:
            out.append(f"risks.{rid}: the reason needs at least {REASON} words")
    inp = _inputs(plan, out)
    c = plan.get("call") or {}
    if c.get("quarter") not in em.CALL_Q:
        out.append(f"call.quarter: must be one of {', '.join(em.CALL_Q)}")
    if c.get("guide") not in em.CALL_G:
        out.append(f"call.guide: must be one of {', '.join(em.CALL_G)}")
    if not em._n(c.get("expected_move")):
        out.append("call.expected_move: a number (0.05 = a 5% move either way)")
    if words(c.get("reason")) < REASON:
        out.append(f"call: the reason needs at least {REASON} words")
    w = plan.get("whisper") or {}
    if not str(w.get("text") or "").strip() or words(w.get("reason")) < REASON:
        out.append("whisper: say what you think the buy-side really expects (your estimate) and why")
    if not str(plan.get("net") or "").strip() or words(plan.get("net")) > 40:
        out.append("net: one line of at most 40 words")
    pts = plan.get("points") or {}
    for sec in ("last_quarter", "since_last_print", "checkpoint"):
        lst = pts.get(sec)
        if not isinstance(lst, list):
            out.append(f"points.{sec}: must be a list (empty if there is nothing)")
            continue
        for i, x in enumerate(lst):
            if not (str(x.get("text") or "").strip() and LINE.match(str(x.get("anchor") or "")) and x.get("quote")):
                out.append(f"points.{sec}[{i}]: needs text, a file.md:line anchor and the quote")
    if ctx.get("new_docs") and not pts.get("since_last_print"):
        out.append("points.since_last_print: there are documents since the last print; say what they add")
    if not isinstance(plan.get("judgment_calls"), list) or not plan["judgment_calls"]:
        out.append("judgment_calls: list every call you made (at least one)")
    st = plan.get("stance") or {}
    if st.get("value") not in em.STANCES:
        out.append(f"stance: must be one of {', '.join(em.STANCES)}")
    elif not out:
        s = em.summary(ctx, inp, sides)
        if not (em._n(s["up"]) and s["up"] > 0 and em._n(s["down"]) and s["down"] < 0):
            out.append(f"inputs: the upside case must be above today's price and the downside case below it "
                       f"(up {s['up']}, down {s['down']}, price {s['price']})")
        elif st["value"] != s["rule"]:
            out.append(f"stance: the rule says {s['rule']} (R/R {s['rr']:.2f}, edge {s['edge']:+.2f}, set-up net "
                       f"{s['net']}, {s['nblow']} blow-up flags); the plan says {st['value']}. The stance must follow "
                       "the rule; the user may override it on the tab.")
    if words(st.get("reason")) < REASON:
        out.append(f"stance: the reason needs at least {REASON} words")
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--plan", required=True)
    ap.add_argument("--context", required=True)
    a = ap.parse_args(argv)
    p = check(json.load(open(a.plan)), json.load(open(a.context)))
    print("\n".join(p) if p else "plan OK")
    sys.exit(1 if p else 0)


if __name__ == "__main__":
    main()
