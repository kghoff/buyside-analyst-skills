"""Shape and rule check of the agent's valuation_plan.json (chapter 11's rules and the user's).

check(plan, context) returns plain-English problems; an empty list means the plan may be built. It checks shape and
where each kind of anchor is allowed; anchors.py checks that each anchored number is really printed there.

usage: plan.py --plan valuation_plan.json --context context.json   (prints the problems; exit 1 if any)"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))   # run with python3 -I
import valmath  # noqa: E402

ROLES = {"primary", "secondary", "floor", "tiebreaker"}
PER_KIND = ("weight", "reward_multiple", "risk_multiple", "risk_metric", "multiple_3y")
HOUSE = ("hurdle", "buy_rr", "pound_rr", "discount", "horizon_months", "position", "mkt_rev", "mkt_oi", "mkt_eps")
LINKS = {"blended_reward", "blended_risk", "dcf_base", "dcf_bull", "dcf_bear"}
CASES = ("base", "bull", "bear")
CELL = re.compile(r"^[A-Za-z' &]+!\$?[A-Z]{1,3}\$?\d+$")
LINE = re.compile(r"^.+\.md:\d+$")
NTM = re.compile(r"^(ntm|ntm1|y3):(" + "|".join(sorted(set(valmath.METRIC.values()))) + r")$")   # a forward sum
ONE_MULTIPLE = "One multiple:"      # a notes entry starting with this (any case) says why one multiple is enough
TOL = 1e-9


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _anchored(name, x, judgment_ok, house_ok):
    """Problems with one anchored input {value, anchor, [anchor_value], reason}. A cell, research line or forward-sum
    (ntm:eps, ntm1:rev, y3:fcf ...) anchor is allowed anywhere; house and judgment only where the flags say."""
    if not isinstance(x, dict):
        return [f"{name}: expected {{value, anchor, reason}}, got {x!r}"]
    out = []
    for k in ("value", "anchor"):
        if k not in x:
            out.append(f"{name}: missing {k}")
    reason = x.get("reason")
    if not (isinstance(reason, str) and reason.strip()):
        out.append(f"{name}: needs a reason")
    a = x.get("anchor")
    if a == "house":
        if not house_ok:
            out.append(f"{name}: a 'house' anchor is only for the house inputs ({', '.join(HOUSE)})")
    elif a == "judgment":
        if not judgment_ok:
            out.append(f"{name}: a 'judgment' anchor is only for blend weights, tree probabilities, the position "
                       "and normalization.years")
        elif isinstance(reason, str) and len(reason.split()) < 12:
            out.append(f"{name}: a 'judgment' anchor needs a reason of at least 12 words")
    elif isinstance(a, str):
        if not (CELL.match(a) or LINE.match(a) or NTM.match(a)):
            out.append(f"{name}: anchor {a!r} is not a cell (Sheet!$A$1), a research line (file.md:123) or a "
                       "forward sum (ntm:eps, ntm1:ebitda, y3:rev ...)")
        if "anchor_value" not in x:
            out.append(f"{name}: a cell, line or forward-sum anchor needs anchor_value (the number it holds)")
    elif "anchor" in x:
        out.append(f"{name}: anchor must be text, got {a!r}")
    return out


def _multiples(plan):
    out = []
    ms = plan.get("multiples")
    if not isinstance(ms, list) or not 1 <= len(ms) <= 3:
        return [f"multiples: use 1-3 multiples, got {len(ms) if isinstance(ms, list) else ms!r}"], []
    kinds = [m.get("kind") for m in ms]
    for k in kinds:
        if k not in valmath.METRIC:
            out.append(f"multiples: {k!r} is not one of {', '.join(valmath.METRIC)}")
    if len(set(kinds)) != len(kinds):
        out.append("multiples: each kind may appear only once")
    roles = [m.get("role") for m in ms]
    for r in roles:
        if r not in ROLES:
            out.append(f"multiples: role {r!r} is not one of {', '.join(sorted(ROLES))}")
    if roles.count("primary") != 1:
        out.append(f"multiples: exactly one must be primary, got {roles.count('primary')}")
    if "pe" not in kinds and not any("P/E" in (m.get("reason") or "") for m in ms):
        out.append("multiples: P/E comes first unless ruled out; some multiple's reason must say why P/E is ruled out")
    notes = [n for n in plan.get("notes") or [] if isinstance(n, str)]
    if len(ms) == 1 and not any(n.strip().lower().startswith(ONE_MULTIPLE.lower()) for n in notes):
        out.append(f"multiples: one multiple alone needs a notes entry starting \"{ONE_MULTIPLE}\" that says why one "
                   "multiple is enough")
    return out, [k for k in kinds if k in valmath.METRIC]


def _inputs(plan, kinds):
    out = []
    inp = plan.get("inputs")
    if not isinstance(inp, dict):
        return ["inputs: missing"]
    for k in kinds:
        for p in PER_KIND:
            if f"{p}.{k}" not in inp:
                out.append(f"inputs: {p}.{k} is missing")
    w = [inp[f"weight.{k}"].get("value") for k in kinds if isinstance(inp.get(f"weight.{k}"), dict)]
    if all(_num(x) for x in w) and abs(sum(w) - 1) > TOL:
        out.append(f"inputs: the weights sum to {sum(w):g}, not 1")
    for h in HOUSE:
        if h not in inp:
            out.append(f"inputs: house input {h} is missing")
    for name, x in inp.items():
        out += _anchored(name, x, name.startswith("weight.") or name == "position", name in HOUSE)
        if not isinstance(x, dict):
            continue
        v = x.get("value")
        p, _, kind = name.partition(".")
        if p in ("reward_multiple", "risk_multiple", "multiple_3y") and kind in kinds:
            if not _num(v):
                out.append(f"{name}: value must be a number")
            elif kind == "fcf_yield" and p != "multiple_3y" and not 0.001 <= v <= 0.5:
                out.append(f"{name}: an FCF yield is a fraction between 0.001 and 0.5 (5% is 0.05), got {v}")
            elif v <= 0:
                out.append(f"{name}: a multiple must be > 0, got {v}")
        elif name != "position" and "value" in x and not _num(v):
            out.append(f"{name}: value must be a number")
    pos = inp.get("position")
    if isinstance(pos, dict) and pos.get("value") not in ("long", "short"):
        out.append(f"position: must be 'long' or 'short', got {pos.get('value')!r}")
    return out


def _scenarios(plan):
    s = plan.get("scenarios")
    if not isinstance(s, dict):
        return ["scenarios: missing"]
    out = []
    r = s.get("rounds")
    if not isinstance(r, list) or not 1 <= len(r) <= 5:
        out.append(f"scenarios: rounds must have 1-5 entries, got {len(r) if isinstance(r, list) else r!r}")
    f = s.get("final") or {}
    vps = {}
    for c in CASES:
        v = (f.get(c) or {}).get("value_per_share") if isinstance(f.get(c), dict) else None
        if not _num(v):
            out.append(f"scenarios: final.{c} needs a numeric value_per_share")
        else:
            vps[c] = v
    if len(vps) == 3 and not vps["bull"] >= vps["base"] >= vps["bear"]:
        out.append(f"scenarios: need bull >= base >= bear, got {vps['bull']:.2f} / {vps['base']:.2f} / {vps['bear']:.2f}")
    return out


def _tree(plan):
    t = plan.get("tree")
    if not isinstance(t, list) or not 4 <= len(t) <= 5:
        return [f"tree: needs 4-5 rows, got {len(t) if isinstance(t, list) else t!r}"]
    out, probs = [], []
    for i, row in enumerate(t, 1):
        name = f"tree[{i}] {row.get('name', '')}".rstrip()
        tg = row.get("target")
        if isinstance(tg, dict) and "link" in tg:
            if tg["link"] not in LINKS:
                out.append(f"{name}: target link {tg['link']!r} is not one of {', '.join(sorted(LINKS))}")
        else:
            out += _anchored(f"{name} target", tg, False, False)
        out += _anchored(f"{name} prob", row.get("prob"), True, False)
        probs.append((row.get("prob") or {}).get("value") if isinstance(row.get("prob"), dict) else None)
    if all(_num(p) for p in probs) and abs(sum(probs) - 1) > TOL:
        out.append(f"tree: the probabilities sum to {sum(probs):g}, not 1")
    return out


def _street(plan):
    st = plan.get("street")
    if st is None:
        return []
    if not isinstance(st, dict):
        return [f"street: expected {{kind: {{ntm, ntm1}}}}, got {st!r}"]
    out = []
    for kind, refs in st.items():
        for k, ref in (refs.items() if isinstance(refs, dict) else [("?", refs)]):
            if not (isinstance(ref, str) and CELL.match(ref)):
                out.append(f"street: {kind}.{k} must be a cell (Sheet!$A$1), got {ref!r}")
    return out


def _normalization(plan):
    n = plan.get("normalization")
    if n is None:
        return []
    if not isinstance(n, dict):
        return [f"normalization: expected an object or null, got {n!r}"]
    out = [] if isinstance(n.get("year"), str) else ["normalization: needs a year label such as 2029E"]
    for k in ("margin", "multiple", "years"):           # years to discount back are rarely printed: judgment allowed
        out += _anchored(f"normalization.{k}", n.get(k), k == "years", False)
    return out


def _nm(plan, context, kinds):
    m = (context or {}).get("metrics")
    if not m:
        return []
    out = []
    for k in kinds:
        metric = valmath.METRIC[k]
        v = ((m.get(metric) or {}).get("ntm") or {}).get("value")
        if not _num(v) or v <= 0:
            out.append(f"{k}: NTM {metric} is negative or missing, so the multiple is not meaningful. "
                       "Use EV/Revenue or EV/GP, or normalized EPS.")
    return out


VERDICTS = ("Buy", "Hold", "Sell")


def _verdict(plan):
    """The agent's overall call at the top of the tab. Code does not decide it (the user's choice, 2026-11-18), so it
    must be one of three words and carry a reason long enough to say which numbers it rests on."""
    v = plan.get("verdict")
    if not isinstance(v, dict):
        return ["verdict: missing; give {value: Buy | Hold | Sell, reason}"]
    out = []
    if v.get("value") not in VERDICTS:
        out.append(f"verdict: {v.get('value')!r} is not one of {', '.join(VERDICTS)}")
    reason = v.get("reason")
    if not (isinstance(reason, str) and len(reason.split()) >= 12):
        out.append("verdict: needs a reason of at least 12 words (which numbers it rests on: R/R, IRR, DCF)")
    return out


def check(plan, context):
    """Plain-English problems with the plan; [] means OK. context: context.json (only its metrics are read)."""
    out, kinds = _multiples(plan)
    out += _inputs(plan, kinds)
    out += _scenarios(plan)
    out += _tree(plan)
    out += _street(plan)
    out += _normalization(plan)
    out += _nm(plan, context, kinds)
    out += _verdict(plan)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--plan", required=True)
    ap.add_argument("--context", required=True)
    a = ap.parse_args(argv)
    probs = check(json.load(open(a.plan)), json.load(open(a.context)))
    for p in probs:
        print(p)
    return 1 if probs else 0


if __name__ == "__main__":
    sys.exit(main())
