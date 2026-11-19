---
name: model-update
description: Roll a reported quarter into a company model (TICKER_model.xlsx) - chapter 13's fast model update. On print night it reads the earnings release (8-K Exhibit 99.1, and 99.2 if present), maps every statement, non-GAAP and KPI line to its MOD row by matching the prior-period value the release prints against the model (an agent answers only the lines code can't match), types the actuals blue with a source note, keeps the formula skeleton from last year's column, holds the pre-print forecast in flagged orange placeholder cells for lines the release doesn't print (awaiting the 10-Q), shows any restated prior-period number and asks before changing history, records new guidance for Filings Charts, then has forecast-planner read the thesis (pitch, filings and street research, valuation / short / preview notes) and revise only the forecast assumptions the print contradicts - the user approves a was-to-now table first. Rerun after the 10-Q (or the 10-K for a Q4) to fill the placeholders and check the release numbers. Ends with the list of skills to rerun. Works for any listed company. Run after the print (after /model-earnings-before). Use when the user runs /model-update TICKER or asks to update the model for a print, enter the quarter or roll the model forward.
---

# /model-update

Puts the quarter the company just reported into MOD, the way chapter 13's 15-minute update does, but with every
number matched, anchored and tied out by code. **Any company**: nothing here is specific to one stock. Use plain
English, and tell the user every judgment call. Read `NOTES.md` before changing scripts.

```bash
SK="<this skill's base directory>/scripts"      # the base directory is shown when the skill loads
SKILLS="<this skill's base directory>/.."
FC="$SKILLS/model-forecast/scripts"; RF="$SKILLS/research-filings/scripts"
RD=$(python3 "$SKILLS/../lib/settings.py" research_dir)   # your research folder: research_dir in the settings file
```
Skills and agents are named here without a prefix. Installed as a plugin, Claude Code lists them as `buyside:<name>`.

**Hard rules.**
- Everything is built in one temp copy (`$TMP`); the user's file changes **once**, at the end, after verify.py passes
  and a checksum shows they did not save it meanwhile. Never open it with openpyxl for saving; keep no backup copies.
- History never changes without a yes (the restatement question). A forecast never changes without the user's
  approval of the was-to-now table, unless the roll changes no assumption.
- A placeholder is never a reported number: it is the old forecast, orange, with an `Update: forecast placeholder`
  note, so the forecast formulas reading it keep working until the filing prints the real one.
- `state.json` lives in `$TMP` while the run works and is copied to `$QW` only together with the model: a stopped
  run must not leave a state that says cells were filled.
- research-filings' data (`$SRC/Filings Research/_work`) is changed only through a staged copy in `$TMP/fr`, copied
  back in step 7 after the model copy: a stopped run leaves it as it was.
- Every stop once `$TMP` exists removes it first (`rm -rf "$TMP"`): it holds copies of the model, and the house rule
  is to keep no backup copies.
- Every python call below is logged (command and one-line result) to `$QW/update_log.md`.

Create a task list with these steps.

## 0. Preflight
1. `python3 "$SKILLS/model-ratios/scripts/locate_model.py" --ticker <T>` (or the path the user names): `MODEL` = its
   `model`, `SRC` = its `src`. `{"status": "build"}`: stop, tell the user to run /model-historicals first.
   `MD=$(dirname "$MODEL")`, `UW="$MD/_model_work/update"`, `MWF="$MD/_model_work/forecast"`.
2. No `~$<model file name>` lock file in `$MD` (else ask the user to close Excel and wait).
   `SHA0=$(shasum -a 256 "$MODEL")`.
3. Run /collect-documents for `<T>` (Skill tool) so the new release, deck, call and 10-Q / 10-K are on disk.
4. `python3 "$SK/locate.py" --model "$MODEL" --src "$SRC" --ticker <T> --work "$UW"` prints JSON:
   - `none`: tell the user the `reason` and stop (a preliminary revenue-only release is not a print).
   - `print` → steps 1–9. `tenq` → section "10-Q rerun".
   `Q` = its `quarter` (e.g. `Q3 26E`), `QN` = `Q` without the E, `QW="$UW/$QN"`, `mkdir -p "$QW"`,
   `TMP=$(mktemp -d)`. Keep `releases`, `filing`, `is_q4` and `fy` for later.

## 1. Values and the frozen forecast
```bash
python3 "$SK/grid.py" "$MODEL" "$QW/values.json" --recalc "$TMP/rc0"
python3 "$SK/frozen.py" ensure --model "$MODEL" --quarter "$Q" --values "$QW/values.json" --work "$QW"
```
`values.json` is every tab recalculated before the print: match, actuals, the placeholders and verify all use it.
`"source": "preprint"` → tell the user why (`why`: no Earnings band 7, or band 7 is for another quarter) and that the
pre-print forecast is saved in `$QW/preprint.json` instead.

## 2. Match
```bash
python3 "$SK/release.py" <every file in locate's releases> --root "$SRC" --out "$QW/release_lines.json"
python3 "$SK/match.py" match --release "$QW/release_lines.json" --model "$MODEL" --values "$QW/values.json" --quarter "$Q" --out "$QW/match.json"
python3 "$SK/modmap.py" rowmap "$MODEL" "$QW/rowmap.md"
```
- release.py: any table with `scale_known` false (1.0 assumed) or `bad` rows → tell the user which table and file.
- match.json buckets: `matched` (by value, or by label for a zero; `sign` -1 = the model keeps the line negative; a
  row may be the `sum` of 2-3 printed lines; on a Q4 an annual line fills the year column), `combined` (one printed
  line = 2-4 model rows), `diffs` (a prior-period number the release prints differently from the model: restated),
  `leftover` and `ambiguous` (for the agent), `no_layout` (columns code can't tell apart, e.g. segment columns) and
  `no_prior` (no year-ago value): reported, never guessed; `zero_skipped` (a zero with no exact label match never
  matches by value); `new_lines`, `skipped` (after the agent).

Write `leftover` + `ambiguous` to `$QW/open_lines.json`. Fill `references/reader_prompt.md` into
`$QW/reader.assignment.md`: `{OPEN_LINES}` = that file, `{ROWMAP}` = `$QW/rowmap.md`, `{DOCS}` = locate's
`releases` plus the quarter's deck (`Investor Decks/_md/<YYYY> Q<n> <T> deck.md`) and call
(`Earnings Calls/_md/<YYYY> Q<n> <T> call.md`) when they exist, relative to `$SRC`, `{ROOT}` = `$SRC`,
`{GUIDED}` = every `guidance` entry's `names` and basis in `$SRC/Filings Research/_work/model_handoff.json` (or
`none`), `{ANSWERS}` = `$QW/reader_answers.json`, `{GUIDANCE}` = `$QW/guidance_answers.json`. Dispatch one agent
(model opus, `subagent_type: filings-analyst`): "Read `<path>` and follow it exactly." It does task 2 even with no
open lines. Keep its id. Then:
```bash
python3 "$SK/match.py" apply --match "$QW/match.json" --answers "$QW/reader_answers.json" --model "$MODEL" --release-root "$SRC" --values "$QW/values.json" --quarter "$Q" --out "$QW/match.json"
```
Exit 1 prints the problems (an anchor off its line, a row already taken, a line not answered): send them to the same
agent (SendMessage) and rerun apply until it exits 0. Nothing is applied until every answer passes.

## 3. Enter the quarter, and the restatement question
```bash
python3 "$SK/actuals.py" --model "$MODEL" --quarter "$Q" --match "$QW/match.json" --values "$QW/values.json" --out "$TMP/a.xlsx" --state "$TMP/state.json" --restate no > "$QW/actuals_report.json"
```
actuals.py follows last year's column row by row: its structure formulas are copied, everything else is the release
value (blue, with a note citing file and line) or waits as a placeholder. Year-to-date cash flow becomes the quarter
(`=YTD - earlier quarters`). On a Q4 the year column is typed from the release's full-year value where last year's Q4
was `FY less Q1-Q3` (Q4 stays that plug), else Q4 is typed and the year sums or links as last year's did. The report
(`typed`, `formulas`, `placeholders`, `awaiting`, `typed_subtotals`, `header`, `waiting_read_elsewhere`) feeds step 8.

If `diffs` in match.json is not empty, show the user one table: line, period, model, new, file:line; under it the
report's `restate_knock_on` (each Q4 plug or year total that would move with it, and by how much) and
`restate_skipped` (differences that can't be typed into one cell: a year-to-date difference or a formula cell, with
`why`). Ask ONE AskUserQuestion: update those cells / leave them. On yes, rerun the command with `--restate yes`
(same `--out` and `--state`) and save the report's `restated` list to `$QW/restated.json` for step 7.

## 4. Tie out
```bash
python3 "$SK/grid.py" "$TMP/a.xlsx" "$QW/values_a.json" --recalc "$TMP/rc1"
python3 "$SK/tieout.py" --match "$QW/match.json" --values "$QW/values_a.json" --column <state.json column> --state "$TMP/state.json" [--fy-column <state.json fy_column>]
```
`--fy-column` on a Q4 (state.json `fy_column` is set). Placeholders and waiting cells are skipped. Exit 1 = a line
sits on the wrong row or a subtotal formula disagrees with the release: show the user the list in plain English and
stop (`rm -rf "$TMP"`; their file was never touched).

## 5. Guidance
If `$SRC/Filings Research/_work/model_handoff.json` exists, stage research-filings' data in `$TMP` and record there
(the real folder changes only in step 7, after the model copy):
```bash
FRW="$SRC/Filings Research/_work"; FW="$TMP/fr/Filings Research/_work"; mkdir -p "$FW"
cp "$FRW/model_handoff.json" "$FRW/drivers_math.json" "$FRW/model_series.csv" "$FW/"
(cd "$FRW" && for f in readers/*/guidance.csv; do [ -f "$f" ] && mkdir -p "$FW/$(dirname "$f")" && cp "$f" "$FW/$f"; done)
python3 "$SK/guidance.py" record --work "$FW" --answers "$QW/guidance_answers.json" --quarter "$QN"
```
It records each guided metric's new guide; `no_block` lists metrics the company guides that have no Filings Charts
block (reported, not added). Filings Charts shows completed years only, so on Q1–Q3 the tab does not change. Without
the folder, skip this and step 6b and tell the user.

## 6. Forecast roll
Skip to 6b, with `cp "$TMP/a.xlsx" "$TMP/f.xlsx"`, if `$MWF/forecast_plan.json` does not exist (no /model-forecast
yet: tell the user the forecast columns were left as they were).
1. `cp "$MWF/forecast_plan.json" "$QW/forecast_plan.before.json"` and `cp "$MWF/forecast_plan.json" "$QW/forecast_plan.json"`
   (the agent revises the copy; the plan in `$MWF` changes only with the model). Copy `$MWF/forecast_headlines.md` to
   `$QW/headlines.before.md`, or write "No headline table from the last /model-forecast run." there.
2. ```bash
   python3 "$SK/frozen.py" table --model "$MODEL" --quarter "$Q" --values "$QW/values_a.json" --work "$QW" --column <col> --state "$TMP/state.json" --out "$QW/actual_vs_frozen.md"
   python3 "$SK/modmap.py" rowmap "$TMP/a.xlsx" "$QW/rowmap_a.md"
   ```
3. `{THESIS_READING_LIST}`, one line per file that exists, in this order (the thesis before the numbers):
   - the pitch deck: newest `$SRC/Pitch/*.md` (from a future /write-pitch, when it exists)
   - the filings research report: newest `$SRC/Filings Research/*Filings Research Report.md` (not the long version)
   - the street research report: newest `$SRC/Street Research/*Street Research Report.md`
   - the latest valuation, short and earnings preview notes: newest `.md` in `$SRC/Valuation`, `$SRC/Short Check`,
     `$SRC/Earnings Previews`
4. Fill `references/roll_prompt.md` into `$QW/roll.assignment.md`: `{QUARTER}` = `$QN`, `{PLAN}` =
   `$QW/forecast_plan.json`, `{PLAN_BEFORE}` = `$QW/forecast_plan.before.json`, `{WRITEUP}` =
   `$MWF/forecast_writeup.md` (or `none`), `{DOCS}` = the step 2 list as absolute paths, `{ACTUAL_VS_FROZEN}` =
   `$QW/actual_vs_frozen.md`, `{ROWMAP}` = `$QW/rowmap_a.md`, `{GUIDANCE}` = `$QW/guidance_answers.json`, `{CHANGES}` =
   `$QW/changes.json`. Dispatch forecast-planner (model opus, `subagent_type: forecast-planner`): "Read `<path>` and
   follow it exactly." Keep its id.
5. `python3 "$SK/plandiff.py" check --old "$QW/forecast_plan.before.json" --new "$QW/forecast_plan.json" --changes "$QW/changes.json"`
   — problems (an unlisted change, a listed change that isn't one, a structural change) go back to the agent
   (SendMessage) until it prints `ok`.
6. Dry run on the actuals copy with model-forecast's own scripts (they run even with no changes: the build re-splits
   the year around the new actual quarter):
   ```bash
   R="$TMP/roll"; rm -rf "$R"; mkdir -p "$R"
   python3 "$FC/move_rows.py" --model "$TMP/a.xlsx" --plan "$QW/forecast_plan.json" --out "$R/moved.xlsx" --work "$R" > "$QW/move_report.json"
   python3 "$FC/build.py" --model "$R/moved.xlsx" --plan "$QW/forecast_plan.json" --out "$R/after.xlsx" > "$QW/build_report.json"
   python3 "$FC/check.py" --before "$R/moved.xlsx" --after "$R/after.xlsx" --plan "$QW/forecast_plan.json" --work "$R" --report "$QW/build_report.json" > "$QW/check_report.json"
   python3 "$FC/layout.py" --model "$R/after.xlsx" --plan "$QW/forecast_plan.json" --out "$R/laid.xlsx" --work "$R" > "$QW/layout_report.json"
   python3 -c 'import sys; sys.path.insert(0, sys.argv[1]); import verify; print(verify.moved(sys.argv[2], sys.argv[3]))' "$SK" "$TMP/a.xlsx" "$R/laid.xlsx"
   ```
   Any build error, `check.py` exit 1, layout exit 1, `rows_inserted` in the build report, or a moved line (the last
   command prints anything but `[]`) goes back to the agent; then 5 and 6 again. After two rounds that still fail,
   stop (`rm -rf "$TMP"`) and tell the user (their file was never touched). Copy `$R/forecast_headlines.md` to `$QW/headlines.after.md`.
7. `python3 "$SK/plandiff.py" page --changes "$QW/changes.json" --old-head "$QW/headlines.before.md" --new-head "$QW/headlines.after.md" --guide "<the new guidance, one line per metric>" --out "$QW/approval.md"`.
   Show the user the path, paste the changes table (undercutting changes first, in bold) and the two headline tables,
   and ask ONE AskUserQuestion: approve / change (notes). Notes go to the same agent, then 5–7 again. With no changes
   at all (`changes.json` is `[]`), say so, show the headline tables (they still move with the actual quarter) and do
   not ask: the plan is the one the user already approved.
8. On approval, or with no changes (`changes.json` is `[]`), `cp "$R/laid.xlsx" "$TMP/f.xlsx"`.

## 6b. Q4 only: close the year on Filings Charts
When `is_q4` and step 5 ran:
```bash
python3 "$SK/guidance.py" close-year --work "$FW" --year <fy without E> --model "$TMP/f.xlsx" --rf "$RF"
python3 "$RF/handoff.py" --src "$TMP/fr" --model "$TMP/f.xlsx" --out "$TMP/g.xlsx" --charts-only && mv "$TMP/g.xlsx" "$TMP/f.xlsx"
```
close-year rebuilds the staged `model_series.csv` from the finished copy with research-filings' own extractor (its
MOD rows go stale whenever rows move; the closed year's header has no E now, so it is included) and bumps
`last_year`. `--charts-only` rebuilds Filings Charts from the staged data and leaves Idio Chart and Px Events as they
are. A handoff.py error: stop (`rm -rf "$TMP"`) and show it.

## 7. Verify and replace the model
```bash
python3 "$SK/verify.py" --before "$MODEL" --after "$TMP/f.xlsx" --mid "$TMP/a.xlsx" --state "$TMP/state.json" --work "$TMP/v" --before-values "$QW/values.json" [--restated "$QW/restated.json"] [--charts]
```
Leave out `--mid` when the roll was skipped (`f.xlsx` is the actuals copy); `--restated` only when the user said yes
in step 3; `--charts` only when step 6b ran. Exit 1: show the problems in plain English and stop (`rm -rf "$TMP"`;
their file was never touched). Then:
1. No `~$` lock file (else ask the user to close Excel), and `shasum -a 256 "$MODEL"` equals `SHA0`. If it changed,
   the user saved meanwhile: stop, `rm -rf "$TMP"`, tell them, and rerun from step 0.
2. `cp "$TMP/f.xlsx" "$MODEL"`, `cp "$TMP/state.json" "$QW/state.json"`; if the roll ran,
   `cp "$QW/forecast_plan.json" "$MWF/forecast_plan.json"` and `cp "$QW/headlines.after.md" "$MWF/forecast_headlines.md"`.
3. If step 5 ran, copy back only the staged research-filings files that changed:
   ```bash
   (cd "$FW" && find . -type f | while read -r f; do cmp -s "$f" "$FRW/$f" || { mkdir -p "$FRW/$(dirname "$f")"; cp "$f" "$FRW/$f"; }; done)
   ```
4. `rm -rf "$TMP"`.

## 8. Report
Tell the user, in plain English:
1. What changed: lines typed (by statement), formulas carried from last year's column, restated cells (if approved),
   guidance changes, forecast changes (the was-to-now lines).
2. **The orange cells.** Explain them every time: "These N cells in <quarter> are not reported numbers. The release
   doesn't print them, so each keeps the forecast it had before the print (orange, with a note 'Update: forecast
   placeholder (value), awaiting ...'), so every forecast formula that reads it keeps working. Treat them as
   estimates." List them from the report's `placeholders` by kind: `10-Q` / `10-K` (the filing will print it: rerun
   /model-update <T> once it is collected), `driver` (a forecast driver or a line with no history: the company may
   never print it; type it yourself if you track it), `manual` (an analysis row you keep by hand: re-enter it). Also
   `awaiting` cells left blank (no pre-print value) and `waiting_read_elsewhere` (blank cells other columns read:
   those show errors or zeros until the filing).
3. The quarter vs the frozen forecast: 5–8 headline lines from `actual_vs_frozen.md` (a glance; the full comparison is
   model-earnings-after's job).
4. Every judgment call: agent-mapped and summed lines (with reasons), combined lines, typed subtotals (a printed
   subtotal typed over a formula that reads a placeholder; the 10-Q rerun puts the formula back), new lines and
   metrics reported but not added, `no_layout` / `no_prior` / `zero_skipped` lines, tables with an assumed scale,
   discontinued metrics (keys awaiting now that also awaited in the previous quarter's `state.json`), the frozen-copy
   source, whether the call was read, guided metrics with no Filings Charts block, structural changes the roll agent
   suggested for /model-forecast (tell the user to make them AFTER the 10-Q rerun: a row inserted or moved before
   it makes the rerun stop, because state.json names the waiting cells by row), and that the forecast write-up (`$MWF/forecast_writeup.md`) predates the roll.
5. Rerun, in order: /model-price-history, /model-consensus, /model-dcf, /model-multiples, /model-valuation,
   /model-short (if short), model-earnings-after (once it exists), /model-earnings-before about two weeks before the
   next print.

## 10-Q rerun
locate printed `tenq`: steps 0.1–0.4 have already run (the filing is collected, `SHA0` is taken, and locate is what
sent you here). `Q` = its `quarter` (no E now: the column holds actuals), `QW` as above, `TMP=$(mktemp -d)`; the
filing is `filing` (the 10-Q, or the 10-K for a Q4). Every file this pass writes in `$QW` has a `_10q` name, so
print night's files stay as they were.
```bash
python3 "$SK/grid.py" "$MODEL" "$QW/values_10q.json" --recalc "$TMP/rc0"
python3 "$SK/release.py" "<filing>" --root "$SRC" --out "$QW/filing_lines.json"
python3 "$SK/match.py" match --release "$QW/filing_lines.json" --model "$MODEL" --values "$QW/values_10q.json" --quarter "$Q" --out "$QW/match_10q.json"
```
Open lines go to the reader agent as in step 2, with `{OPEN_LINES}` = `$QW/open_lines_10q.json`, the assignment in
`$QW/reader_10q.assignment.md`, `{ANSWERS}` = `$QW/reader_answers_10q.json`, `{GUIDANCE}` =
`$QW/guidance_answers_10q.json`, `{GUIDED}` = `skip` and `{DOCS}` = the filing; then `match.py apply` with
`--answers "$QW/reader_answers_10q.json"`, `--match`/`--out` `"$QW/match_10q.json"` and the same `--values` and
`--quarter`. Then:
```bash
cp "$QW/state.json" "$TMP/state.json"
python3 "$SK/actuals.py" --model "$MODEL" --quarter "$Q" --match "$QW/match_10q.json" --out "$TMP/a.xlsx" --state "$TMP/state.json" --tenq > "$QW/tenq_report.json"
```
It stops with "MOD rows moved since print night" when a line state.json names is no longer on its row (a
/model-forecast run since print night inserted or moved rows): stop (`rm -rf "$TMP"`), show the message and tell the
user to undo the row change (or restore the model from before it), rerun /model-update for the filing, and make the
structural change after it.

`differences`: show them all (line, release, filing, file:line; `combined` rows compare a combined line with its
rows' sum). Only the ones with `can_take` true can take the filing's number; the others are typed subtotals (their
formula comes back once their parts are filled) or combined lines (no single cell): say so. If any has `can_take`
true, ask ONE AskUserQuestion: keep the release values / take the filing's (all, or the cells the user names). Write
the refs to take to `$QW/take.json` (`[]` keeps the release values), then `cp "$QW/state.json" "$TMP/state.json"`
again (the first pass updated it) and rerun the command with `--take-10q "$QW/take.json"`. Then write
`$QW/kept.json` (`[]` when nothing is kept): the refs of every `can_take` difference the user kept (the cell holds
the release's number on purpose) plus every typed-subtotal difference not in the report's `restored` (its typed
release number stays until its formula can come back). Then:
```bash
python3 "$SK/grid.py" "$TMP/a.xlsx" "$QW/values_a10q.json" --recalc "$TMP/rc1"
python3 "$SK/tieout.py" --match "$QW/match_10q.json" --values "$QW/values_a10q.json" --column <col> --state "$TMP/state.json" --awaiting "$QW/kept.json" [--fy-column <fy col>]
python3 "$SK/verify.py" --before "$MODEL" --after "$TMP/a.xlsx" --state "$TMP/state.json" --work "$TMP/v" --before-values "$QW/values_10q.json"
```
tieout or verify exit 1: show the problems in plain English and stop (`rm -rf "$TMP"`; their file was never
touched). Then step 7's checksum and copy with `$TMP/a.xlsx` as the finished copy (`cp "$TMP/a.xlsx" "$TMP/f.xlsx"`
first), and report: cells filled, formulas restored (`restored`), differences and the user's answer, placeholders
still waiting (and why: `driver` / `manual` never come from a filing). If a filled or changed line feeds the forecast
plan, say so: the next print's roll or /model-forecast picks it up.
