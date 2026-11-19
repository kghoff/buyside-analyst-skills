"""Shape and rules of after_plan.json. check(plan, ctx) -> plain-English problems ([] = OK).
usage: python3 plan.py --plan P --context C   (prints problems or 'plan OK'; exit 1 on any)"""
import argparse
import json
import re
import sys

SFOT = ("surprise", "fundamentals", "outlook", "tone")
SFOT_V = ("positive", "neutral", "negative")
CALLS = ("add", "hold", "trim", "press", "exit")
PATTERNS = ("hedge-fund dump that bounces", "short squeeze that rolls over", "under-reaction",
            "conservative-guide panic", "sustainable deceleration", "weird reaction", "none")
CHECK = ("green", "yellow", "red")
GUIDE = ("raise", "hold", "cut", "initiate", "withdrawn", "none")
PLAYED = ("yes", "no", "partly")
LINE = re.compile(r"^.+\.md:\d+$")


def words(s):
    return len(str(s or "").split())


def _quoted(name, x, out):
    if not isinstance(x, dict) or not x.get("quote") or not LINE.match(str(x.get("anchor", ""))):
        out.append(f"{name}: needs a quote and a file.md:line anchor")


def check(p, ctx):
    out = []
    if p.get("quarter") != ctx["quarter"]:
        out.append(f"quarter: plan says {p.get('quarter')!r}, context says {ctx['quarter']!r}")
    for k in SFOT:
        x = (p.get("sfot") or {}).get(k) or {}
        if x.get("value") not in SFOT_V:
            out.append(f"sfot.{k}: value must be one of {', '.join(SFOT_V)}")
        if words(x.get("reason")) < 8:
            out.append(f"sfot.{k}: the reason needs at least 8 words")
        _quoted(f"sfot.{k}", x, out)
    notes = p.get("call_notes") or {}
    for t in ctx["topics"]:
        if t not in notes:
            out.append(f"call_notes: topic {t!r} is missing (use [] when the call said nothing on it)")
    for t, lst in notes.items():
        if t not in ctx["topics"]:
            out.append(f"call_notes: {t!r} is not a topic in context.json")
        if not isinstance(lst, list):
            out.append(f"call_notes.{t}: must be a list ([] when the call said nothing on it)")
            continue
        for i, x in enumerate(lst):
            _quoted(f"call_notes.{t}[{i}]", x, out)
            if not isinstance(x, dict) or not x.get("text"):
                out.append(f"call_notes.{t}[{i}]: needs text")
    for i, g in enumerate(p.get("guidance") or []):
        if not str(g.get("item") or "").strip():
            out.append(f"guidance[{i}].item: name what is guided (e.g. '2027 revenue')")
        if g.get("change") not in GUIDE:
            out.append(f"guidance[{i}].change must be one of {', '.join(GUIDE)}")
        _quoted(f"guidance[{i}]", g, out)
    lt = p.get("lt_target")
    if lt:
        for k in ("num", "den"):
            if lt.get(k) and lt[k] not in ctx["mod_keys"]:
                out.append(f"lt_target.{k}: {lt[k]!r} is not a MOD line (context.json mod_keys)")
        if not lt.get("num"):
            out.append("lt_target.num: name the MOD line the target is on (context.json mod_keys)")
        if not isinstance(lt.get("year"), int) or not isinstance(lt.get("target"), (int, float)):
            out.append("lt_target: needs a whole-number year and a numeric target")
        _quoted("lt_target", lt, out)
    c = p.get("checkpoint") or {}
    if c.get("value") not in CHECK:
        out.append(f"checkpoint: value must be one of {', '.join(CHECK)}")
    if words(c.get("reason")) < 8:
        out.append("checkpoint: the reason needs at least 8 words")
    r = p.get("react") or {}
    if r.get("call") not in CALLS:
        out.append(f"react.call must be one of {', '.join(CALLS)}")
    if r.get("pattern") not in PATTERNS:
        out.append(f"react.pattern must be one of: {'; '.join(PATTERNS)}")
    if words(r.get("reason")) < 12:
        out.append("react.reason: needs at least 12 words")
    for k in ("wrong_if", "watch"):
        if words(r.get(k)) < 5:
            out.append(f"react.{k}: needs at least 5 words")
    cats = p.get("catalysts")
    if not isinstance(cats, list):
        out.append("catalysts: must be a list of {text, when} ([] if none)")
    else:
        for i, x in enumerate(cats):
            if not isinstance(x, dict) or not str(x.get("text") or "").strip():
                out.append(f"catalysts[{i}]: needs text")
    cons = p.get("controversies")
    if not isinstance(cons, list) or not all(isinstance(x, str) and x.strip() for x in cons):
        out.append("controversies: must be a list of non-empty strings ([] if none)")
    for k in ("headline", "quarter_thoughts"):
        if words(p.get(k)) < 8:
            out.append(f"{k}: needs at least 8 words")
    if ctx.get("mode") == "rerun" and ctx.get("drift_ready"):
        po = p.get("played_out") or {}
        if po.get("value") not in PLAYED or words(po.get("reason")) < 8:
            out.append(f"played_out: the T+7 rerun needs value {'/'.join(PLAYED)} and a reason of 8+ words")
    if not isinstance(p.get("judgment_calls"), list) or not p["judgment_calls"]:
        out.append("judgment_calls: list every judgment call (at least one)")
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", required=True)
    ap.add_argument("--context", required=True)
    a = ap.parse_args(argv)
    probs = check(json.load(open(a.plan)), json.load(open(a.context)))
    print("\n".join(probs) or "plan OK")
    sys.exit(1 if probs else 0)


if __name__ == "__main__":
    main()
