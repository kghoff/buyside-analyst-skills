---
name: model-earnings-before
description: Add the Earnings tab to a company model (TICKER_model.xlsx) about two weeks before a print - chapter 13's earnings preview. Code computes the model checks on the quarter being reported (yoy, 2- and 3-year stacks, sequential growth and margin against the 5-year average for that quarter, incremental margin, the hockey-stick flag, second-half share), the base rates (the last 12 print moves, idio moves, run-up and drift, daily sigma), the options-implied move and the guidance trail; an agent (earnings-analyst) reads the documents since the last print and a web scrub and answers the set-up, the five risk scores, the key metric, the upside and downside cases, P(upside) and the call; the stance (add / hold / trim / hedge) follows a fixed rule on reward / risk, edge over the implied PSUC, the set-up and blow-up flags. Fills the Consensus tab's variance table (asks first if you typed in it) or puts the grid on the Earnings tab, freezes the forecast for the after-print comparison, and writes a preview note (Markdown + PDF). Every judgment is a yellow cell the user owns; a rerun keeps the user's changes. Works for any listed company. Run after /model-valuation (and /model-consensus). Use when the user runs /model-earnings-before TICKER or asks for an earnings preview, a print set-up, the implied move or the risk / reward into earnings.
---

# /model-earnings-before

Adds one tab, **Earnings**, that answers: what is baked in, where do we differ, how big is the move likely to be,
what is the risk / reward on the print, and what to do. It also writes a preview note. **Any company**: nothing here
is specific to one stock. Use plain English, and tell the user every judgment call. Read `NOTES.md` before changing
scripts.

```bash
SK="<this skill's base directory>/scripts"      # the base directory is shown when the skill loads
SKILLS="<this skill's base directory>/.."
RD=$(python3 "$SKILLS/../lib/settings.py" research_dir)   # your research folder: research_dir in the settings file
```
Skills and agents are named here without a prefix. Installed as a plugin, Claude Code lists them as `buyside:<name>`.

Yellow means the agent chose it and the user owns it. There is **no approval pause** (except the variance question
in Step 7): the agent decides, the code checks every number, and the report tells the user every call.

## Requirements
- Python 3 with openpyxl; pytest to run the tests.
- Node, with this skill's `npm install` done once (yahoo-finance2; Step 2 does it if `node_modules` is missing).
- LibreOffice for the recalculations (`brew install --cask libreoffice`).
- WeasyPrint for the note's PDF (research-filings' `render.py`). Without it the note is Markdown only; say so.
- The model needs MOD with a forecast, Px Data, Px Events and Multiples. Consensus, Valuation and Filings Charts are
  used when present; the blocks that need them show `?` or n/a otherwise.

## Step 1: Locate and check
1. `python3 "$SKILLS/model-ratios/scripts/locate_model.py" --ticker <T>` (or the path the user names). It prints
   JSON; `model` is the file. If it prints `{"status": "build"}` there is no model yet: stop and tell the user to run
   /model-historicals (and the skills after it) first. Set `M` to it and
   `W=<model dir>/_model_work/model-earnings-before` (`mkdir -p "$W"`). All working files stay in `$W`.
2. If `~$<model file name>` exists next to `M`, ask the user to close Excel and wait.
3. `shasum -a 256 "$M"`: keep it for Step 9. Never write to `M` before then; keep no backup copies.
4. An Earnings tab already there is normal (rerun each quarter). The build replaces it; the user's changes and the
   forecast frozen for the same quarter are kept.

## Step 2: Market data
```bash
(cd "$SK/.." && { [ -d node_modules ] || npm install --silent; }) && node "$SK/fetch_earnings.mjs" "$W" <T>
```
It writes `$W/earnings.json`. Exit 1 means Yahoo failed: carry on (the price comes from Px Data; no implied move, no
surprises) and tell the user. "past: will be estimated" means the company hasn't announced the date yet.

## Step 3: Context
`python3 -I "$SK/context.py" --model "$M" --work "$W" --ticker <T>`. It recalculates a copy of the model in
LibreOffice into `$W/values/` (a minute or two), then writes `$W/context.json`, `$W/context.md` and `$W/rowmap.md`.
It stops, naming the skill to run, when MOD, Px Data, Px Events or Multiples is missing, or MOD has no forecast; then
delete the copy it made (`rm -rf "$W/out.xlsx" "$W/values" "$W/values_out"`) and pass the message on. It prints the
quarter, the report date (and whether it is estimated), code's answers, the number of documents since the last print
and the warnings. If there are no new documents, tell the user to rerun /collect-documents or drop the latest broker
previews into Sellside Research, and carry on.

## Step 4: Web pass
Fill `references/web_assignment.md` (`{COMPANY}`, `{TICKER}`, `{AS_OF}` = today, `{SINCE}` = context.json
`last_release` (the last print's release date), `{QUARTER}`, `{OUT_DIR}` = `$RD/<T>/Earnings Previews/_web/<quarter>`; `mkdir -p` it) and dispatch one
`street-researcher` agent (model sonnet) with it. Wait for its reply. Nothing found is fine: say so in the report.

## Step 5: Agent
Dispatch the `earnings-analyst` agent with the assignment `references/assignment.md` (the skill's folder) and the
paths: `W`, `$W/context.md`, `$W/context.json`, `$W/rowmap.md`, the research root `$RD/<T>/`, the web folder from
Step 4, the brief `references/earnings_brief.md` and the example plan `tests/fixtures/plan_example.json` (both in
the skill's folder). Wait for `PLAN WRITTEN`.

## Step 6: Check (at most 2 rounds back to the agent)
```bash
python3 -I "$SK/plan.py" --plan "$W/earnings_plan.json" --context "$W/context.json"
python3 -I "$SK/anchors.py" --plan "$W/earnings_plan.json" --values "$W/values/<model file name>" --context "$W/context.json"
```
(`--values` is the recalculated copy Step 3 made; context.json's `values` holds its path. anchors.py reads the
research folder from context.json.) Each prints one problem per line (or `plan OK` / `anchors OK`) and exits 1 on
any. Problems → SendMessage them all to the same agent; run both again. After round 2:
- plan.py problems stop the run: show the user the problems in plain English and do not build. The model stays
  untouched. Delete the copies of the model Step 3 made (keep none): `rm -rf "$W/out.xlsx" "$W/values" "$W/values_out"`.
- anchors.py problems: write the names still failing (the text before the first ":" of each problem, e.g.
  `inputs.up_pe`, `setup.consensus`, `key_metric`, `points.since_last_print[0]`) as a JSON list to
  `$W/unverified.json`; the build marks them UNVERIFIED in red and the note lists them. Otherwise make sure no old
  `$W/unverified.json` is left (`rm -f "$W/unverified.json"`).

## Step 7: The variance table
`python3 -I "$SK/variance.py" inspect --model "$M" --written "$W/variance_written.json"`. By its `status`:
- `skeleton` (model-consensus's empty table) or `ours` (only what this skill wrote last time): `V="--variance consensus"`.
- `"data"` (the user typed in it; `filled` lists the cells): **Ask the user** (AskUserQuestion), naming the cells:
  "Your Consensus variance table has your own entries (<cells>). Overwrite them with the preview's numbers, or keep
  yours and put the preview's grid on the Earnings tab?" Overwrite → `V="--variance consensus --force-variance"`;
  keep → `V="--variance earnings"`.
- `missing` or `no_block` (no Consensus tab, or no variance block): `V="--variance earnings"`; tell the user.

## Step 8: Build and verify
```bash
python3 -I "$SK/build.py" --model "$M" --work "$W" --ticker <T> --out "$W/out.xlsx" $V
python3 -I "$SK/verify.py" --out "$W/out.xlsx" --work "$W"
```
Add `--refreeze` only if the user asks to freeze the forecast again for the same quarter. If the tab already holds
/model-earnings-after's wrap (bands 9-15) for this same quarter, build.py stops (the rebuild would clear it): **ask
the user** (AskUserQuestion) "Rebuild the preview and clear the after-print wrap (restore it with
/model-earnings-after <T> --rebuild), or stop?" Rebuild → rerun build.py with `--clear-after`, and tell the user to run
`/model-earnings-after <T> --rebuild` afterwards; stop → stop. A preview for a new quarter clears last quarter's
wrap without asking; when the JSON says `after_cleared` true, tell the user (the wrap lives on in the after-print note
and the Call Notes tab, which build.py never touches). build.py never touches `M`,
and stops if any part of the workbook other than the Earnings tab (and the Consensus tab when it fills it, plus the
workbook, styles and content-type parts it must update) changed. It prints JSON; keep for the report: `stance_rule`
and `stance_used`, `users_kept`, `variance` (where the grid went, and any `skipped` or `dropped` rows), `frozen`
(`kept` true when the earlier freeze stood) and `warnings`. verify.py recalculates the copy once and compares every
checked cell with `earnmath.py`; any problem: stop, tell the user the first problems in plain English, show them
build.py's `warnings` too (they often explain the problem, e.g. a threshold cell holding text), and do not copy. Never hand-edit the output. On a stop, delete every copy of the model the run made:
`rm -rf "$W/out.xlsx" "$W/values" "$W/values_out"`.

## Step 9: Replace the model
1. `shasum -a 256 "$M"` again: if it changed, stop (the user saved meanwhile): delete the copies made from the old
   file (`rm -rf "$W/out.xlsx" "$W/values" "$W/values_out"`) and rerun from Step 3.
2. Check `~$<model file name>` again (ask the user to close Excel). Then
   `cp "$W/out.xlsx" "$M" && mv "$W/inputs_written.next.json" "$W/inputs_written.json"`, and if
   `$W/variance_written.next.json` exists, `mv "$W/variance_written.next.json" "$W/variance_written.json"`.
3. Delete every copy of the model the run made (keep none): `rm -rf "$W/out.xlsx" "$W/values" "$W/values_out"`.
   Keep the plan, context, `layout.json`, `earnings.json` and the written records.

## Step 10: Note and report
`python3 -I "$SK/note.py" --work "$W" --ticker <T> --out-dir "$RD/<T>/Earnings Previews"`. It writes
`<T> <quarter> earnings preview <date>.md` and `.pdf` and prints their paths; if `"pdf"` is null, tell the user the
PDF was skipped and why.

Then tell the user, in plain English:
- The stance and the rule's answer (`stance_used`, `stance_rule`); the call (quarter, guide, expected move).
- The upside and downside cases (P/E x EPS, price, move), R/R, the implied PSUC, P(upside) and the edge.
- The set-up (each row's side, net), the blow-up flags, the risk scores and the key metric.
- The model-check flags that fired (hockey stick, margin or second-half share off the 5-year average), the base
  rates (average and median print move, up / down, move in sigmas) and the implied move (or why there is none).
- The guidance trail: habitual raiser or not.
- Where the variance grid went, and that the forecast for <quarter> is frozen (or the earlier freeze was kept).
- Every judgment call (the plan's `judgment_calls`, each input's anchor and reason), the report date if estimated,
  UNVERIFIED names, the cells the user had changed (`users_kept`) and that they were kept, every warning, the
  missing optional tabs, and the web pass result.
- The note's path, that the Earnings tab sits after Short Check (else Valuation, else last), and a reminder to open
  the file in Excel, where it recalculates.
