# earnings-analyst assignment: after the print

You are given: W (work folder), W/context.md and W/context.json, the research root R (`<research_dir>/<TICKER>/`;
context.json `research`), references/after_brief.md and the example plan (the skill's
tests/fixtures/plan_example.json). Read the brief first.

## Read, in this order (Markdown before PDF)
1. context.md: the quarter, the mode (first run or T+7 rerun), actual against the frozen forecast, the move in
   sigmas, gap, run-up and drift, estimates before and now, valuation before and after, the IRR now and the fade
   table, the Call Notes topics and history, and the warnings.
2. The transcript (context.json `docs.transcript`), all of it, every line.
3. The release (`docs.release`) and the preview note (`docs.preview`), if listed.
4. The previous Call Notes columns (context.md "Call Notes history"), to judge tone and guidance against them.
Paths are relative to R. Note the line numbers of everything you will cite.

## Decide
- sfot: surprise, fundamentals, outlook, tone. Each: value positive / neutral / negative, a reason of >= 8 words,
  an anchor file.md:N and a quote.
- call_notes: one key per topic in context.json `topics`, exactly those, each a list of 0-3 points
  {text, anchor, quote}. [] when the call said nothing on that topic. Q&A themes: up to 5, one per theme key.
- guidance: a list of items {item, before, now, change, anchor, quote}; item names what is guided (e.g. "2027
  revenue"); change is one of raise / hold / cut / initiate / withdrawn / none.
- lt_target: null, or {metric, num, den, target, year, anchor, anchor_value, quote}. num and den (den may be null
  for a level, not a ratio) are MOD keys from context.json `mod_keys`; year a whole number. A ratio target is a
  fraction: 20% -> target 0.20 and anchor_value 0.20 (the anchor line prints "20%"; a number before % is read x100).
- checkpoint: value green / yellow / red, reason >= 8 words.
- react: call, pattern, reason (>= 12 words: does the move fit what the print justified?), wrong_if and watch
  (>= 5 words each).
  - call: add (buy more), hold, trim (sell some), press (add to a short or a winning trade), exit (sell all).
  - pattern, from the brief section 9, exactly one of:
    "hedge-fund dump that bounces", "short squeeze that rolls over", "under-reaction",
    "conservative-guide panic", "sustainable deceleration", "weird reaction", "none".
- catalysts: a list of {text, when} (text required; when may be "" if no date is known).
- controversies: a list of strings, what management still has to clarify.
- headline (>= 8 words) and quarter_thoughts (>= 8 words): the wrap's first lines.
- played_out: only when context.json mode is "rerun" and drift_ready is true: {value yes / no / partly, reason
  >= 8 words} on whether the react call played out by T+7. Otherwise null.
- judgment_calls: a list of every judgment call you made (at least one).

Every quote is near-verbatim: copied from the cited line (case and spacing may differ), never a paraphrase.
Never type a number the cited line does not print.

## Write
W/after_plan.json in exactly this shape:
{"quarter": "<context.json quarter>",
 "sfot": {"surprise": {"value": "...", "reason": "...", "anchor": "file.md:N", "quote": "..."}, "fundamentals": {},
          "outlook": {}, "tone": {}},
 "call_notes": {"<topic>": [{"text": "...", "anchor": "file.md:N", "quote": "..."}]},
 "guidance": [{"item": "...", "before": "...", "now": "...", "change": "...", "anchor": "file.md:N", "quote": "..."}],
 "lt_target": {"metric": "...", "num": "<mod key>", "den": "<mod key>", "target": 0.0, "year": 2028,
               "anchor": "file.md:N", "anchor_value": 0.0, "quote": "..."},
 "checkpoint": {"value": "...", "reason": "..."},
 "react": {"call": "...", "pattern": "...", "reason": "...", "wrong_if": "...", "watch": "..."},
 "catalysts": [{"text": "...", "when": "..."}], "controversies": ["..."],
 "headline": "...", "quarter_thoughts": "...", "played_out": null, "judgment_calls": ["..."]}
Then reply exactly: PLAN WRITTEN. If you are sent problems, fix only those and reply PLAN WRITTEN again.
