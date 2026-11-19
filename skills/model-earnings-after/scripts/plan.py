"""Shape and rules of after_plan.json. check(plan, ctx) -> plain-English problems ([] = OK). A malformed plan (a
string where a dict belongs, a missing list) is listed as problems, never a crash. Run anchors.py only on a plan
that passes this check.
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
# the surprise is against something: its reason names what (the chapter's "versus what number?")
SURPRISE_VS = ("frozen", "forecast", "consensus", "expected", "implied", "preview")
SILENT = "none"            # an SFOT anchor for a row the call and release were silent on
MAX_POINTS = 3
QUOTE_WORDS = 4
LINE = re.compile(r"^(?P<path>.+\.md):\d+$")


def words(s):
    return len(s.split()) if isinstance(s, str) else 0


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _text(v):
    return isinstance(v, str) and v.strip() != ""


def _call_docs(ctx):
    """The call's own documents (context.json docs), the only files SFOT, call notes and guidance may cite."""
    d = ctx.get("docs") if isinstance(ctx.get("docs"), dict) else {}
    return {d[k] for k in ("transcript", "release", "preview") if isinstance(d.get(k), str) and d[k]}


def _quoted(name, x, out, docs=None):
    """A quote of 4+ words with a file.md:line anchor; with docs, the file must be one of the call's documents."""
    if not isinstance(x, dict):
        out.append(f"{name}: must be an object with text, anchor and quote, got {type(x).__name__}")
        return
    q, m = x.get("quote"), LINE.match(str(x.get("anchor", "")))
    if not _text(q) or not m:
        out.append(f"{name}: needs a quote and a file.md:line anchor")
        return
    if words(q) < QUOTE_WORDS:
        out.append(f"{name}: the quote needs at least {QUOTE_WORDS} words (a fragment can hide its meaning)")
    if docs is not None and m["path"] not in docs:
        out.append(f"{name}: cite the call's own documents (context.json docs: {', '.join(sorted(docs)) or 'none'}), "
                   f"not {m['path']!r}")


def _dict(name, x, out):
    if isinstance(x, dict):
        return x
    if x is not None:
        out.append(f"{name}: must be an object, got {type(x).__name__}")
    return {}


def _list(name, x, out, what):
    if isinstance(x, list):
        return x
    out.append(f"{name}: must be a list of {what} ([] if none)")
    return []


def _sfot(p, docs, out):
    s = _dict("sfot", p.get("sfot"), out)
    for k in SFOT:
        x = s.get(k)
        if not isinstance(x, dict):
            out.append(f"sfot.{k}: missing; give value, reason, anchor and quote")
            continue
        if x.get("value") not in SFOT_V:
            out.append(f"sfot.{k}: value must be one of {', '.join(SFOT_V)}")
        if words(x.get("reason")) < 8:
            out.append(f"sfot.{k}: the reason needs at least 8 words")
        if x.get("anchor") == SILENT:
            if x.get("value") != "neutral" or "silent" not in str(x.get("reason", "")).lower() or x.get("quote"):
                out.append(f"sfot.{k}: anchor 'none' is only for a neutral row whose reason says the call and "
                           "release were silent on it, with no quote")
        else:
            _quoted(f"sfot.{k}", x, out, docs)
        if k == "surprise" and not any(w in str(x.get("reason", "")).lower() for w in SURPRISE_VS):
            out.append("sfot.surprise: the reason must say versus what number (the frozen forecast, consensus, "
                       "the implied move or the preview)")


def _notes(p, ctx, docs, out):
    notes = _dict("call_notes", p.get("call_notes"), out)
    for t in ctx["topics"]:
        if t not in notes:
            out.append(f"call_notes: topic {t!r} is missing (use [] when the call said nothing on it)")
    for t, lst in notes.items():
        if t not in ctx["topics"]:
            out.append(f"call_notes: {t!r} is not a topic in context.json")
        if not isinstance(lst, list):
            out.append(f"call_notes.{t}: must be a list ([] when the call said nothing on it)")
            continue
        if len(lst) > MAX_POINTS:
            out.append(f"call_notes.{t}: at most {MAX_POINTS} points per topic, got {len(lst)}")
        for i, x in enumerate(lst):
            _quoted(f"call_notes.{t}[{i}]", x, out, docs)
            if isinstance(x, dict) and not _text(x.get("text")):
                out.append(f"call_notes.{t}[{i}]: needs text")


def _guidance(p, docs, out):
    for i, g in enumerate(_list("guidance", p.get("guidance"), out, "{item, before, now, change, anchor, quote}")):
        if not isinstance(g, dict):
            out.append(f"guidance[{i}]: must be an object, got {type(g).__name__}")
            continue
        if not _text(g.get("item")):
            out.append(f"guidance[{i}].item: name what is guided (e.g. '2027 revenue')")
        for k in ("before", "now"):
            if not _text(g.get(k)):
                out.append(f"guidance[{i}].{k}: needs text (say 'none given' when there was none)")
        if g.get("change") not in GUIDE:
            out.append(f"guidance[{i}].change must be one of {', '.join(GUIDE)}")
        _quoted(f"guidance[{i}]", g, out, docs)


def _lt(p, ctx, out):
    lt = p.get("lt_target")
    if lt is None:
        return
    if not isinstance(lt, dict):
        out.append(f"lt_target: must be null or an object, got {type(lt).__name__}")
        return
    for k in ("num", "den"):
        if lt.get(k) and lt[k] not in ctx["mod_keys"]:
            out.append(f"lt_target.{k}: {lt[k]!r} is not a MOD line (context.json mod_keys)")
    if not lt.get("num"):
        out.append("lt_target.num: name the MOD line the target is on (context.json mod_keys)")
    if not isinstance(lt.get("year"), int) or isinstance(lt.get("year"), bool) or not _num(lt.get("target")):
        out.append("lt_target: needs a whole-number year and a numeric target")
    elif not _num(lt.get("anchor_value")) or abs(lt["target"] - lt["anchor_value"]) > 1e-9:
        out.append("lt_target: target must equal anchor_value, both in MOD's units (20% -> 0.20); use null for a "
                   "target that is not one number in those units")
    elif lt.get("den") and not 0 < abs(lt["target"]) <= 1.5:
        out.append(f"lt_target.target: a ratio target is a fraction (20% -> 0.20), got {lt['target']:g}")
    _quoted("lt_target", lt, out)        # any file under the research root (investor day, deck): anchors.py


def check(p, ctx):
    if not isinstance(p, dict):
        return [f"plan: must be a JSON object, got {type(p).__name__}"]
    out, docs = [], _call_docs(ctx)
    if p.get("quarter") != ctx["quarter"]:
        out.append(f"quarter: plan says {p.get('quarter')!r}, context says {ctx['quarter']!r}")
    _sfot(p, docs, out)
    _notes(p, ctx, docs, out)
    _guidance(p, docs, out)
    _lt(p, ctx, out)
    c = _dict("checkpoint", p.get("checkpoint"), out)
    if c.get("value") not in CHECK:
        out.append(f"checkpoint: value must be one of {', '.join(CHECK)}")
    if words(c.get("reason")) < 8:
        out.append("checkpoint: the reason needs at least 8 words")
    r = _dict("react", p.get("react"), out)
    if r.get("call") not in CALLS:
        out.append(f"react.call must be one of {', '.join(CALLS)}")
    if r.get("pattern") not in PATTERNS:
        out.append(f"react.pattern must be one of: {'; '.join(PATTERNS)}")
    if words(r.get("reason")) < 12:
        out.append("react.reason: needs at least 12 words")
    for k in ("wrong_if", "watch"):
        if words(r.get(k)) < 5:
            out.append(f"react.{k}: needs at least 5 words")
    for i, x in enumerate(_list("catalysts", p.get("catalysts"), out, "{text, when}")):
        if not isinstance(x, dict) or not _text(x.get("text")):
            out.append(f"catalysts[{i}]: needs text")
    cons = _list("controversies", p.get("controversies"), out, "strings")
    if not all(_text(x) for x in cons):
        out.append("controversies: must be a list of non-empty strings ([] if none)")
    for k in ("headline", "quarter_thoughts"):
        if words(p.get(k)) < 8:
            out.append(f"{k}: needs at least 8 words")
    if ctx.get("mode") == "rerun" and ctx.get("drift_ready"):
        po = p.get("played_out") if isinstance(p.get("played_out"), dict) else {}
        if po.get("value") not in PLAYED or words(po.get("reason")) < 8:
            out.append(f"played_out: the T+7 rerun needs value {'/'.join(PLAYED)} and a reason of 8+ words")
    jc = p.get("judgment_calls")
    if not isinstance(jc, list) or not jc or not all(_text(x) for x in jc):
        out.append("judgment_calls: list every judgment call (at least one, each a sentence)")
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
