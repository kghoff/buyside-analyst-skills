# model-short notes

Why things are the way they are. Read before changing scripts.

## Origin
- Built 2026-11-18 from Chapter 12 (Short Selling). Spec docs/2026-11-18-model-short-design.md, plan
  docs/2026-11-18-model-short-plan.md (local). RED baseline docs/2026-11-18-research-short-red.md: a no-skill agent
  flipped the long R/R and skipped the FEV scorecard, short type, wedge, risk case, takeout, sizing and borrow.
- Same shape as model-valuation: context.py → short-analyst agent → plan.py + anchors.py → build.py (raw XML) →
  verify.py (one recalculation) → note.py. All math lives in shortmath.py; the tab's formulas compute the same things
  and verify.py proves they agree.

## Choices
- Peak margin is "TTM operating margin ÷ the 10-year FY peak" (✓ at 95%), not a percentile: MOD interleaves quarter
  and FY columns, so there is no contiguous range for a percentile; a ratio to MAX() works on any MOD.
- peak_ratio can exceed 1 (above 100%): the numerator is TTM, the denominator the peak of the prior ten fiscal years,
  so a TTM margin above every past full year reads as more than 100%. That is a ✓, not an error.
- Code ticks the rows numbers can answer (shortmath.THRESH), as live formulas; the agent may override with a
  >= 12-word reason (the cell then holds the agent's symbol and turns yellow). A ✓ / ✗ / ? the user types over a code
  tick survives a rerun. Only "✓" counts in the score (COUNTIF), so type the symbol.
- A user formula in a tick cell is kept too. build.read_tab reads a tick cell as "code's own formula" only when it is
  exactly code's formula for that row; any other formula is the user's, is kept as written, and counts at its
  recalculated value (from the values copy). The same holds for a formula in a yellow input cell.
- The revisions row needs two Consensus snapshots of one period (the "5. CONSENSUS SNAPSHOTS" block; the period with
  the most snapshots, first vs last). With one snapshot it stays `?` until /model-consensus is rerun after the next
  print adds a second.
- earn_move (median absolute idio move on earnings days) uses every earnings day in Px Events (every row whose Type
  contains "earn"), not just the last few. It frames the print move; it is not a tick.
- EPS basis is GAAP diluted (MOD's "EPS, diluted"), as model-valuation uses. FCF conversion uses MOD's non-GAAP net
  income row when there is one (context.json mod.basis says which).
- A link to a blank cell on another tab is n/a (no link, the tick is `?`), not a 0: Excel shows a blank as 0, which
  would have ticked or unticked a row on nothing (commit 0f9ebc9).
- Verdict rule and house defaults: shortmath.verdict and shortmath.HOUSE; the brief (references/short_brief.md,
  section 11) copies both, and test_docs checks the brief names every row, type, bucket and verdict.

## Deviations from the plan's code (found by comparing the plan with what was merged; commit bodies carry no detail)
- build.py formulas changed so the tab shows #N/A (or a fallback) exactly where shortmath returns None, which
  verify.py requires (#N/A parity):
  - incr_margin: a non-number peak ratio counts as FALSE, not 0, inside the OR (`IF(ISNUMBER(E),E>=0.95,FALSE)`).
  - vs_dcf: the price is read through `N()`, so a blank or "n/a" price compares as 0 instead of erroring.
  - risk: the takeout premium enters the MAX through `IF(ISNUMBER(...),...,-1)`, as shortmath.risk_of does.
  - crowded: "n/a" unless both the short % of float and the crowded line are numbers.
  - borrow drag and risk budget: wrapped in IFERROR(...,NA()) so a text input gives #N/A, not #VALUE!.
  - P/FCF: #N/A unless FCF conversion is above 0 (shortmath.p_fcf).
  - the roll-forward path's EPS and price are computed from NTM EPS and the CAGR one step at a time, as the
    formulas chain them, instead of shortmath.roll_path.
- build.py reruns (user-kept values):
  - read_tab recognises code's own tick formula by exact text (code_formula), so a user's formula is not mistaken for
    code's (see Choices).
  - _math also resolves borrow and catalyst_soon, so a user's formula there counts at its recalculated value; the
    catalyst cell's "Y" test ignores case, as Excel's ="Y" does.
  - The header inputs (catalyst, takeout) are written as "Y" / "N", and the unique-label check covers every input
    and tick label, so a rerun finds each again by its column-A text.
  - build returns `warnings`: no inputs_written.json record (every differing yellow cell treated as the user's), and
    any yellow cell holding text where a number belongs.
  - The price ref is one constant (PRICE = $B$4) shared by the header and the tick formulas.
  - UNVERIFIED marks also cover smoke flags (`smoke[i]`) and the catalyst (`catalyst`).
- context.py: a Multiples link to a blank cell is dropped (above).
- verify.py: TRUE / FALSE compare as booleans whatever form LibreOffice returns them in (bool, 1 / 0 or text).
- tests/fixtures/plan_example.json: the reward case is a fall in price, not a rise (commit 5d5f606).

## Tests
- Tests use a ~50 KB synthetic fixture (tests/fixtures/make_fixture.py), never a real model; one slow test
  (test_recalc) recalculates in LibreOffice. The user asked for this after model-valuation's suite took a day. The
  fast suite (`python3 -m pytest -q -m "not slow"`) must stay under 30 s.
- lo.py has its own profile folder (model-short-lo-profile) so it never collides with another skill's run.
