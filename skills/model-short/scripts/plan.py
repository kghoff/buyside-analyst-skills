# skills/model-short/scripts/plan.py
"""Shape and rule check of the agent's short_plan.json (chapter 12's discipline). anchors.py then checks that each
anchored number and quote is really where it says.

check(plan, context) returns plain-English problems; [] means the plan may be built.
usage: python3 plan.py --plan short_plan.json --context context.json   (prints problems; exit 1 if any)"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))   # run with python3 -I
import shortmath as sm  # noqa: E402

CELL = re.compile(r"^(?P<sheet>[A-Za-z' &]+)!\$?[A-Z]{1,3}\$?\d+$")
LINE = re.compile(r"^.+\.md:\d+$")
REASON, OVERRIDE = 8, 12


def words(s):
    return len(str(s or "").split())


def _ticks(plan, code_ticks, out):
    ticks = plan.get("ticks") or {}
    for rid, _, label, computed in sm.ROWS:
        t = ticks.get(rid)
        if not isinstance(t, dict):
            out.append(f"ticks.{rid}: missing ({label})")
            continue
        if t.get("tick") not in sm.TICK:
            out.append(f"ticks.{rid}: tick must be yes, no or unknown, got {t.get('tick')!r}")
        if words(t.get("reason")) < REASON:
            out.append(f"ticks.{rid}: the reason needs at least {REASON} words")
        if computed:
            code = code_ticks.get(rid)
            if t.get("tick") != code and words(t.get("reason")) < OVERRIDE:
                out.append(f"ticks.{rid}: code says {code}, plan says {t.get('tick')}; an override needs a reason of "
                           f"at least {OVERRIDE} words")
        elif t.get("tick") == "yes":                 # a judgment ✓ rests on a line; no / unknown need only a reason
            a = t.get("anchor")
            if not isinstance(a, str) or not (LINE.match(a) or CELL.match(a)):
                out.append(f"ticks.{rid}: a ✓ needs an anchor (file.md:line or Sheet!$A$1)")
            elif LINE.match(a) and not t.get("quote") and "anchor_value" not in t:
                out.append(f"ticks.{rid}: a line anchor needs the quote (or anchor_value) it rests on")
            elif CELL.match(a) and "anchor_value" not in t:      # else anchors.py has nothing to check
                out.append(f"ticks.{rid}: a cell anchor needs the anchor_value the cell shows")
    return {rid: (ticks.get(rid) or {}).get("tick") for rid, *_ in sm.ROWS}


def _inputs(plan, out):
    inp = plan.get("inputs") or {}
    for k in (*sm.HOUSE, *sm.AGENT_INPUTS):
        x = inp.get(k)
        if not isinstance(x, dict):
            out.append(f"inputs.{k}: missing")
            continue
        if not sm._n(x.get("value")):
            out.append(f"inputs.{k}: value must be a number, got {x.get('value')!r}")
        a = x.get("anchor")
        if a == "house":
            if k not in sm.HOUSE:
                out.append(f"inputs.{k}: only the house inputs may anchor to 'house'")
        elif a == "judgment":
            if words(x.get("reason")) < OVERRIDE:
                out.append(f"inputs.{k}: a judgment needs a reason of at least {OVERRIDE} words")
        elif isinstance(a, str) and (CELL.match(a) or LINE.match(a)):
            if "anchor_value" not in x:
                out.append(f"inputs.{k}: a cell or line anchor needs the anchor_value printed there")
        else:
            out.append(f"inputs.{k}: anchor must be house, judgment, Sheet!$A$1 or file.md:line, got {a!r}")
        if not str(x.get("reason") or "").strip():
            out.append(f"inputs.{k}: missing reason")
    return {k: (inp.get(k) or {}).get("value") for k in (*sm.HOUSE, *sm.AGENT_INPUTS)}


def check(plan, ctx):
    out, inp_out = [], []
    vals = _inputs(plan, inp_out)
    c = plan.get("catalyst") or {}
    code = ctx["code_ticks"]                 # the house hurdle; with valid inputs, the plan's own (as build.py does)
    if not inp_out:
        code = sm.summary(ctx, vals, {}, c.get("soon") is True)["code"]
    ticks = _ticks(plan, code, out)
    out += inp_out
    for f, allowed in (("type", sm.TYPES), ("bucket", sm.BUCKETS)):
        x = plan.get(f) or {}
        if x.get("value") not in (*allowed, "none"):
            out.append(f"{f}: {x.get('value')!r} is not one of chapter 12's: {', '.join(allowed)} (or none)")
        if words(x.get("reason")) < REASON:
            out.append(f"{f}: the reason needs at least {REASON} words")
    if not isinstance(c.get("soon"), bool) or not str(c.get("text") or "").strip() or not c.get("anchor"):
        out.append("catalyst: needs soon (true / false), text and anchor")
    elif c["soon"] and not (LINE.match(str(c["anchor"])) and str(c.get("quote") or "").strip()):
        out.append("catalyst: soon = true needs a file.md:line anchor and the quote that dates the event")
    if not isinstance((plan.get("takeout_prone") or {}).get("value"), bool):
        out.append("takeout_prone: value must be true or false")
    for i, s in enumerate(plan.get("smoke") or []):
        if not (s.get("flag") and LINE.match(str(s.get("anchor"))) and s.get("quote")):
            out.append(f"smoke[{i}]: needs flag, a file.md:line anchor and the quote")
    if words(plan.get("smoke_checked")) < REASON:
        out.append("smoke_checked: say what was read for auditor, CFO / CAO and metric-disclosure changes")
    if not str(plan.get("why") or "").strip() or words(plan.get("why")) > 40:
        out.append("why: one line of at most 40 words")
    v = plan.get("verdict") or {}
    if v.get("value") not in sm.VERDICTS:
        out.append(f"verdict: must be one of {', '.join(sm.VERDICTS)}")
    elif not out:
        rule = sm.summary(ctx, vals, ticks, c["soon"])["verdict"]
        if v["value"] != rule and words(v.get("reason")) < OVERRIDE:
            out.append(f"verdict: the rule says {rule}, plan says {v['value']}; an override needs a reason of at "
                       f"least {OVERRIDE} words")
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
