---
name: model-earnings-after
description: Wrap the print in a company model (TICKER_model.xlsx) - chapter 13's after-print review. Adds bands 9-15 ("AFTER THE PRINT") under the preview on the Earnings tab - actual against the forecast frozen before the print (beat / in line / miss, placeholders named), SFOT (surprise, fundamentals, outlook, tone), the move (gap at the open, day, idio, move in daily sigma against the expected and implied move, run-up, and the T+7 drift on a rerun), estimates before and now, valuation before (the pre-print Valuation Note) and after (the Valuation tab), the IRR at today's price and the fade table, guidance and the long-term target pace, the thesis checkpoint, and the react call and reaction pattern; keeps a Call Notes tab (one column per quarter, topics down the side, near-verbatim lines with file:line) and writes an after-print reaction note (Markdown + PDF). An agent (earnings-analyst) reads the call transcript and makes the judgments; code checks every quote and number. Every judgment is a yellow cell the user owns; a rerun keeps the user's changes. Works for any listed company. Run after the call and /model-update (and the reruns model-update lists); rerun on or after T+7 for the drift. Use when the user runs /model-earnings-after TICKER or asks to wrap the print, for an after-print or reaction note, a call summary, or the T+7 drift.
---

# /model-earnings-after

Adds bands 9-15 to the **Earnings** tab, keeps a **Call Notes** tab and writes an after-print note. They answer:
what happened against our frozen forecast, how the stock moved against what we expected, what the call said and how
it differs from last quarter, how estimates, the target, the IRR and the R/R changed, whether the thesis is on
track, and what to do now. **Any company**: nothing here is specific to one stock. Use plain English, and tell the
user every judgment call. Read `NOTES.md` before changing scripts.

```bash
SK="<this skill's base directory>/scripts"      # the base directory is shown when the skill loads
SKILLS="<this skill's base directory>/.."
RD=$(python3 "$SKILLS/../lib/settings.py" research_dir)   # your research folder: research_dir in the settings file
```
Skills and agents are named here without a prefix. Installed as a plugin, Claude Code lists them as `buyside:<name>`.

Yellow means the agent chose it and the user owns it. There is **no approval pause** (only the transcript question in
Step 3): the agent decides, the code checks every quote and number, and the report tells the user every call.

## Requirements
- Python 3 with openpyxl (PyMuPDF only to read a PDF transcript the user supplies); pytest to run the tests.
- Node, with this skill's `npm install` done once (yahoo-finance2; Step 4 does it if `node_modules` is missing).
- LibreOffice for the recalculations (`brew install --cask libreoffice`).
- WeasyPrint for the note's PDF (research-filings' `render.py`). Without it the note is Markdown only; say so.
- The model needs the Earnings tab from /model-earnings-before with band 7 frozen for the quarter just reported,
  MOD with that quarter's actuals (/model-update), and Px Data and Px Events through the reaction day. The Valuation
  tab, the pre-print Valuation Note, the preview note, the Consensus variance grid and the forecast plan are used when
  present; the rows that need them show `?` with the reason otherwise.

## Step 1: Locate and check
1. `python3 "$SKILLS/model-ratios/scripts/locate_model.py" --ticker <T>` (or the path the user names). It prints
   JSON; `model` is the file. If it prints `{"status": "build"}` there is no model yet: stop and tell the user to run
   /model-historicals (and the skills after it) first. Set `M` to it and
   `W=<model dir>/_model_work/model-earnings-after` (`mkdir -p "$W"`). All working files stay in `$W`.
2. If `~$<model file name>` exists next to `M`, ask the user to close Excel and wait.
3. `shasum -a 256 "$M"`: keep it for Step 9. Never write to `M` before then; keep no backup copies.
4. With `--rebuild` (see the section at the end): skip Steps 3, 4, 6 and 7 and reuse `$W/after_plan.json`.

## Step 2: Quarter
`python3 -I "$SK/context.py" --model "$M" --work "$W" --ticker <T> --quarter-only` prints
`{"quarter": "Q3 26", "quarter_e": "Q3 26E", "reaction_day": "2026-10-31"}` from the model itself (no
recalculation). Keep `Q` (the quarter) and the reaction day. It stops, naming the skill to run, when band 7 is
missing or froze another quarter (/model-earnings-before), the quarter's actuals are not in (/model-update), or Px
Events has no release or reaction for it (/model-price-history): pass the message on.

## Step 3: Transcript
1. `python3 -I "$SK/transcript.py" find --root "$RD/<T>" --ticker <T> --quarter "<Q>"` prints the transcript's path
   (exit 0) or nothing (exit 1).
2. Missing: run /collect-documents <T>, then `find` again.
3. Still missing: **ask the user** (AskUserQuestion): "Alpha Vantage hasn't posted the <Q> call transcript yet. Can
   you get it from FactSet, Koyfin, Bloomberg or similar and save it in `<RD>/<T>/Earnings Calls/`?" Options: "I
   saved it" / "Stop; I'll rerun later". Stop → stop the run; the model is untouched.
4. Saved: find the new file in `$RD/<T>/Earnings Calls/` (PDF or Markdown) and file it:
   `python3 -I "$SK/transcript.py" ingest --root "$RD/<T>" --ticker <T> --quarter "<Q>" --file "<the new file>"`.
   It writes `Earnings Calls/_md/<FY> Q<n> <T> call.md` (and, for a PDF, `Earnings Calls/<FY> Q<n> <T> call.pdf`),
   never overwriting one already there. Then register it in collect-documents' manifest so a later
   /collect-documents run counts it as found (`<FY>` is the 4-digit year, e.g. `2026`):
   ```bash
   node "$SKILLS/collect-documents/scripts/manifest.mjs" add "$RD/<T>" --id "call:<FY>Q<n>" \
     --category "Earnings Calls" --label "<FY> Q<n> <T> call" --status found \
     --file "Earnings Calls/_md/<FY> Q<n> <T> call.md" --note "supplied by user"
   ```
   For a PDF, add `--file "Earnings Calls/<FY> Q<n> <T> call.pdf"` (ingest copied it there); for Markdown, don't
   (a listed file that doesn't exist makes collect-documents fetch the call again).

## Step 4: Market data
```bash
(cd "$SK/.." && { [ -d node_modules ] || npm install --silent; }) && node "$SK/fetch_after.mjs" "$W" <T> <reaction day>
```
It writes `$W/yahoo_after.json` (the reaction day's open and close, the previous close, the latest close). Exit 1
means Yahoo failed: carry on and tell the user the gap at the open and open-to-close rows show `?` (Px Data has
closes only).

## Step 5: Context
`python3 -I "$SK/context.py" --model "$M" --work "$W" --ticker <T>`. It recalculates a copy of the model in
LibreOffice into `$W/values/` (a minute or two), then writes `$W/context.json` and `$W/context.md`: actual against
frozen, the move, estimates before (model-update's pre-print snapshot) and now, valuation before and after, the IRR
now and the fade table, the Call Notes history. It prints the quarter, `mode` (`rerun` when bands 9-15 were
already built for this quarter: on the tab, or in the Call Notes record after a preview rerun cleared them; a plan
left by a run that stopped at Step 7 does not count; otherwise `first`), `drift_ready`,
the move (with `drift_due`, the T+7 date), the documents found and the warnings. It stops, naming the skill to run,
when a tab it needs is missing or Px Data stops short of the reaction day; then delete the copy it made
(`rm -rf "$W/out.xlsx" "$W/values" "$W/values_out"`) and pass the message on.

## Step 6: Agent
Dispatch the `earnings-analyst` agent with the assignment `references/after_assignment.md` (the skill's folder) and
the paths: `W`, `$W/context.md`, `$W/context.json`, the research root `$RD/<T>/`, the brief
`references/after_brief.md` and the example plan `tests/fixtures/plan_example.json` (both in the skill's folder).
Wait for `PLAN WRITTEN`. It writes `$W/after_plan.json`. On a rerun once the drift is in (mode `rerun`,
`drift_ready` true: the T+7 rerun), the assignment's "T+7 rerun" section applies: the agent copies the previous plan,
answers "played out?" and changes the react call only if the drift changes it.

## Step 7: Check (at most 2 rounds back to the agent)
```bash
python3 -I "$SK/plan.py" --plan "$W/after_plan.json" --context "$W/context.json"
python3 -I "$SK/anchors.py" --plan "$W/after_plan.json" --context "$W/context.json" --research "$RD/<T>" \
  --unverified "$W/unverified.json"
```
(anchors.py reads the recalculated copy from context.json `values`; run it only on a plan that passed plan.py.) Each
prints one problem per line (or `plan OK` / `anchors OK`) and exits 1 on any. Problems → SendMessage them all to the
same agent; run both again. After round 2:
- plan.py problems stop the run: show the user the problems in plain English and do not build. The model stays
  untouched. Delete the copies of the model Step 5 made (keep none): `rm -rf "$W/out.xlsx" "$W/values" "$W/values_out"`.
- anchors.py problems: build anyway. The last anchors.py run has written the names still failing (e.g.
  `sfot.tone.reason`, `guidance[0].now`, `call_notes.Tone[0]`) to `$W/unverified.json`; the build marks their cells
  UNVERIFIED in red (a name marks the cell it names and the cells below it: `sfot.tone.reason` marks the SFOT tone
  row) and the note lists them. When every anchor holds, anchors.py deletes that file, so no old name is left.

## Step 8: Build and verify
```bash
python3 -I "$SK/build.py" --model "$M" --work "$W" --ticker <T> --out "$W/out.xlsx"      # add --rebuild for a rebuild
python3 -I "$SK/verify.py" --out "$W/out.xlsx" --work "$W"
```
build.py never touches `M`: it splices bands 9-15 under band 8 of a copy (bands 1-8 byte for byte), rebuilds the
Call Notes tab, and stops if any other part of the workbook changed. It prints JSON; keep for the report:
`users_kept`, `call_notes_users_kept`, `placeholders`, `unchecked` and `warnings`. verify.py recalculates the copy
once into `$W/values_out/` and compares every checked cell with `aftermath.py`; it prints `problems`, `warnings` and
`recalculated` (keep that path for Step 10). Any problem: stop, tell the user the first problems in plain English,
show them build.py's `warnings` too (they often explain the problem), and do not copy. Never hand-edit the output.
On a stop, delete every copy of the model the run made: `rm -rf "$W/out.xlsx" "$W/values" "$W/values_out"`.

## Step 9: Replace the model
1. `shasum -a 256 "$M"` again: if it changed, stop (the user saved meanwhile): delete the copies made from the old
   file (`rm -rf "$W/out.xlsx" "$W/values" "$W/values_out"`) and rerun from Step 5.
2. Check `~$<model file name>` again (ask the user to close Excel). Then
   ```bash
   cp "$W/out.xlsx" "$M" && mv "$W/after_inputs_written.next.json" "$W/after_inputs_written.json" \
     && mv "$W/call_notes_written.next.json" "$W/call_notes_written.json"
   rm -rf "$W/out.xlsx" "$W/values"
   ```
   Keep no backups. `$W/values_out` stays until the note is written (Step 10). Keep the plan, context, `layout.json`,
   `yahoo_after.json` and the written records.

## Step 10: Note and report
```bash
python3 -I "$SK/note.py" --work "$W" --ticker <T> --out-dir "$RD/<T>/Earnings Reviews" --values "<verify's recalculated>"
rm -rf "$W/values_out"
```
It writes `<T> <Q> after-print note <date>.md` and `.pdf` in `Earnings Reviews` and prints their paths (the date is
context.json `today`, the run's date, unless `--date` is given). The name deviates from the spec's
`<date> <T> After-Print Note.md` on purpose: it matches the preview note's `<T> <Q> earnings preview <date>.md`, so
a quarter's preview and wrap sort together. If `"pdf"` is null, tell the user the PDF was skipped and why
(`pdf_skipped`). Delete `$W/values_out` after it, whether or not it worked: keep no copy
of the model.

Then tell the user, in plain English:
- The headline: the quarter, the move, the key metric beat or miss, guidance raised / held / cut, the react call and
  the checkpoint colour.
- Beats and misses on the key lines against the frozen forecast (and against consensus where the preview's variance
  grid holds it); name every line still an "estimate, awaiting 10-Q" placeholder (`placeholders`).
- SFOT: surprise, fundamentals, outlook, tone, each with its reason.
- The move: day and idio move in daily sigmas, against the expected (band 2's up / down cases) and the implied move;
  gap at the open and open to close (or `?` because Yahoo failed); the run-up; the drift if in.
- Estimates and valuation before → after (price, each multiple's target, blended target, R/R, the IRR), or `?`
  and why (no Valuation Note before the print; no /model-valuation note dated on or after the release day). The
  "before" is the note as printed (0.7x, 11.2%), so the change compares the tab's value rounded the same way: a
  value that did not move shows no change.
- The IRR at today's price on the after target, and the fade table.
- Guidance before and now, and the long-term target pace (the pace needed against the ratable path), if any.
- The checkpoint, the react call and the reaction pattern, what would prove it wrong; "played out?" when it was asked.
- Every judgment call (the plan's `judgment_calls`, each yellow cell's reason), the UNVERIFIED names (from
  `$W/unverified.json`) and which cells they marked red, the cells the
  user had changed (`users_kept`, `call_notes_users_kept`) and that they were kept, and every warning.
- The note's path, and a reminder to open the model in Excel, where it recalculates.
- When `drift_ready` is false: "Rerun /model-earnings-after <T> on or after <drift_due> for the drift." (`drift_due`
  is the reaction day + 7 trading days from Step 5's output; holidays are not counted, so a day later may be needed.)
- That the wrap on the Earnings tab lasts until the next preview: any /model-earnings-before run after /model-update
  targets the next quarter and clears bands 9-15 without asking (it reports `after_cleared`). The after-print note
  and the Call Notes tab keep the wrap.

## --rebuild: after a preview rerun for the same quarter
A /model-earnings-before rerun for the quarter already reviewed can shift the rows bands 9-15 point at, so it stops
unless given `--clear-after`, which removes bands 9-15. Use `/model-earnings-after <T> --rebuild` after it: Steps 1,
2, 5, 8, 9 and 10 only. No transcript, no Yahoo, no agent: build.py re-lays bands 9-15 from the saved
`$W/after_plan.json` and puts back the values the record (`after_inputs_written.json`) marks as the user's. The
Call Notes tab is untouched by the preview, so its cells are kept as on any rerun. If `$W/after_plan.json` is missing
or is for another quarter, run without `--rebuild` instead. If the drift has come in since the saved plan, "played
out?" shows `?`: run without `--rebuild` for the agent's answer.
