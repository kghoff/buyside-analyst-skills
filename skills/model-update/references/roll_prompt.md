# Forecast roll (model-update)

The quarter `{QUARTER}` is now actuals in the model. Revise the forecast plan **only where the evidence contradicts
it**. You have no shell and no web.

## Read first, in this order (the thesis before the numbers)
{THESIS_READING_LIST}

Then:
- the current plan `{PLAN}` and its write-up `{WRITEUP}`;
- the new documents `{DOCS}` (release, deck, call if collected; if no call is listed, say so in your reply);
- the actual vs frozen forecast table `{ACTUAL_VS_FROZEN}` (what we expected vs what was reported; a blank actual is
  a line the release did not print: it waits for the 10-Q and holds the old forecast as a placeholder);
- the row map `{ROWMAP}` (the reported quarter is no longer a forecast column);
- the new guidance `{GUIDANCE}`.

## Rules
1. Change an assumption only when the print, the call or new guidance contradicts it. Everything else stays exactly
   as it is (code compares the plans; a change you did not list fails).
2. Land inside new guidance, or miss it on purpose with a reason in the entry's `source` (model-forecast's check
   enforces this).
3. Remove or rewrite any entry that refers to `{QUARTER}E` as a forecast period: that column is actuals now.
4. Assumptions only, never structure: leave `new_rows`, `move_rows`, `layout` and `driver_sections` exactly as they
   are, and do not switch a line to the `seasonal` method. Those insert or move MOD rows, and this update keeps every
   row in place (code refuses them). If the print calls for a new row or driver, name it in your reply; the user
   makes it with /model-forecast.
5. For every change write a `changes.json` entry: `{"key": <plan entry key or top-level field>, "was": <old
   assumption in words and numbers>, "now": <new>, "anchor": "<file>:<line>", "reason": <one or two sentences>,
   "thesis": "none" | "supports" | "undercuts"}`. `undercuts` when the change weakens a point the thesis documents
   rely on (name the point in the reason).

Write the revised plan to `{PLAN}` (the old one is saved at `{PLAN_BEFORE}`) and the list to `{CHANGES}` (`[]` when
nothing changes).
Reply with: number of changes, any that undercut the thesis (one line each), any structural change you would make
(for /model-forecast), and whether the call was read.
