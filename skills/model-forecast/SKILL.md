---
name: model-forecast
description: Build the user's driver-based quarterly 3-statement forecast in their company model (TICKER_model.xlsx, MOD tab) from the forecast structure the filings research recommends. Revenue is built the way the filings research's key-drivers and forecast sections describe, adjusted by the user's notes: the assumptions sit on the driver rows and revenue is a formula of them (a typed growth-rate engine only as a last resort). A planning agent writes a forecast plan (the driver rows and their typed assumptions, then one entry per line - % of revenue, days, seasonal shares, schedules or linked formulas, each with its source); scripts write it into the forecast columns as live Excel formulas with blue typed inputs and source notes, then prove revenue comes from the drivers, the filings research's checks hold, the balance sheet balances, cash ties, annual = quarters and guidance is hit. The user approves the plan before their file changes. Run after /research-filings (and /research-street if done). Use when the user runs /model-forecast TICKER or asks to forecast or project a model.
---

# /model-forecast

```bash
SK="<this skill's base directory>/scripts"      # the base directory is shown when the skill loads
SKILLS="<this skill's base directory>/.."
RD=$(python3 "$SKILLS/../lib/settings.py" research_dir)   # your research folder: research_dir in the settings file
```
Skills and agents are named here without a prefix. Installed as a plugin, Claude Code lists them as
`buyside:<name>` (e.g. skill `buyside:model-historicals`, agent `buyside:filings-analyst`): use the name as listed.

`R="$SKILLS/model-forecast"` (scripts in `$R/scripts`, prompts in `$R/references`). Agent:
`subagent_type: forecast-planner` (no web, no shell). The agent ships in the repo's `agents/` folder.

The scripts do everything code can answer; the agent does the judgment. Everything you tell the user is
plain English.

**Hard rules.**
- The user's model is never edited in place and never opened with openpyxl for saving (that deletes their text boxes and
  pictures). Builds run on a copy in a temp folder; their file is replaced only after they approve the plan and the
  check passes, and only if the file is unchanged since the copy.
- Only the MOD forecast columns (labels ending in `E`, except `2050E`) change, plus the rows the plan inserts.
  check.py proves it.
- No backup copies of the model are kept (the user's rule). Work files live in `$MW` (`_model_work/forecast/`); temp
  folders are removed.
- One base case, the filings research's view. Non-GAAP margins drive; GAAP is derived. Interest last, on beginning balances.
- Never say "done" with a check open.

Create a task list with these steps.

## Prompt fills (references/plan_prompt.md)
- `{TICKER}`, `{COMPANY}`
- `{MODEL_WORK}`: `$MW`
- `{P1_SECTIONS}`: `$P1/sections`; `{P1_WORK}`: `$P1/_work`
- `{P2_SECTIONS_OR_NONE}`: `$P2/sections`, or `none`
- `{ROWMAP}`: `$MW/rowmap.md`
- `{USER_NOTES_OR_NONE}`: the path of `$MW/user_notes.md` if the user gave notes, or `none`

Write the filled prompt to `$MW/plan.assignment.md` and dispatch with "Read `<that path>` and follow it exactly."

**MOD fill convention (house default).** Ordinary rows: quarter cells plain, fiscal-year cells grey; section title rows (text in column A) carry their section colour across every quarter and year; spacer columns and year columns with no quarters (2050E) untouched. `scripts/modfill.py` enforces it: the build runs `fix` after every save and the check fails on any break (`python3 scripts/modfill.py check MODEL`). Never hand-colour MOD cells; if you add or rewrite MOD rows outside the scripts, run `python3 scripts/modfill.py fix MODEL MODEL` and then `check` before saying done.

## 0. Preflight
1. The model: `$RD/<T>/<T>_model.xlsx` if it exists; otherwise ask the user for the path (e.g. `<model dir>/TICKER_model.xlsx`).
   `MODEL=<path>`,
   `MW=<model folder>/_model_work/forecast` (create it).
2. The filings research: `P1="$RD/<T>/Filings Research"`. If `$P1/sections` has no `*forecast*.md`, stop and tell
   the user: "run /research-filings first; the forecast is built from its recommendations."
3. The street research: `P2="$RD/<T>/Street Research"` if `$P2/sections` exists, else none.
4. The model must not be open in Excel: no `~$<model file name>` lock file in its folder. If there is one, ask the user
   to close it.
5. Ask the user ONE AskUserQuestion: "Any notes for the forecast (assumptions you want, guidance you trust or don't)?"
   (typed notes or none). Save them to `$MW/user_notes.md`.
6. If `$MW/forecast_plan.json` already exists (a rerun), tell the agent to revise it rather than start over.

## 1. Row map
```bash
python3 $R/scripts/modmap.py rowmap "$MODEL" "$MW/rowmap.md"
```
modmap only reads. The row map lists every MOD line key, its row, unit and the analysis rows under it, then the
forecast quarters and years. If it lists no forecast quarters, stop: the model has no forecast columns (labels
ending in `E` in row 2) and the user needs to add them.

## 2. Plan agent
Dispatch the plan agent (model opus, `subagent_type: forecast-planner`, `$R/references/plan_prompt.md`). It writes
`$MW/forecast_plan.json` and replies with five headline lines. Keep its agent id for steps 3 and 4.

## 2b. Research-coverage review
Dispatch a SEPARATE reviewer (model opus, `subagent_type: forecast-planner`, `$R/references/review_prompt.md`, same
fills; write it to `$MW/review.assignment.md`). It builds its own checklist of every forecast recommendation in
the filings research, the street research's what-changes section and the user's notes BEFORE reading the plan, then marks each built / explained /
missing in `$MW/coverage.json`. Send every `missing` item to the plan agent (SendMessage), then rerun the reviewer
(SendMessage: "the plan changed, re-check"). Repeat until nothing is missing. Do not show the user a plan with a
`missing` item.

## 3. Dry run and check
```bash
T=$(mktemp -d)
cp "$MODEL" "$T/before.xlsx"
python3 $R/scripts/move_rows.py --model "$T/before.xlsx" --plan "$MW/forecast_plan.json" --out "$T/moved.xlsx" --work "$T" > "$MW/move_report.json"
python3 $R/scripts/build.py --model "$T/moved.xlsx" --plan "$MW/forecast_plan.json" --out "$T/after.xlsx" > "$MW/build_report.json"
python3 $R/scripts/check.py --before "$T/moved.xlsx" --after "$T/after.xlsx" --plan "$MW/forecast_plan.json" --work "$T" --report "$MW/build_report.json" > "$MW/check_report.json"
```
- move_rows.py moves the plan's `move_rows` blocks (e.g. operating rows into the Revenue Build) and proves, after a
  LibreOffice recalculation, that every cell keeps its value at its new place; exit 1 = a range the move would split
  or a value that changed (send it to the plan agent). With no moves it just copies the file.
- build.py stops with an error on a bad key, a missing analysis row, a missing first-year value, or a cell outside
  the forecast columns. It writes nothing then.
- check.py exits 1 if anything is wrong: `problems` lists a balance or cash check not 0 (which quarter, which row),
  an error cell (`#REF!`, `#DIV/0!` ...), an annual that isn't the sum of its quarters (or Q4 for a balance), a
  guide missed, or a change outside the forecast. `notes` lists guides the plan deliberately misses, with its reason.
  It also writes `$T/forecast_headlines.md`; copy it to `$MW/forecast_headlines.md`.
- Send every build error or check problem back to the plan agent (SendMessage), with the plain text of the problem,
  then rerun this step on a fresh `$T`. Repeat until check.py exits 0. Remove each `$T` when done with it.
- `stale_cells` in the build report are typed numbers the user left in forecast columns of rows the plan doesn't touch.
  They are never deleted; list them for the user in step 7.

## 4. The user approves the plan
```bash
python3 $R/scripts/plan_page.py --model "$MODEL" --plan "$MW/forecast_plan.json" --out "$MW/forecast_plan.md" --headlines "$MW/forecast_headlines.md" --coverage "$MW/coverage.json"
```
Show the user the path of `$MW/forecast_plan.md`, the driver tree (the page's "Key drivers" section: which rows carry
each driver and the typed assumptions on them, 2027 and 2030), and paste the headline table (revenue, growth, non-GAAP gross and
operating margin, EPS, FCF per forecast year) in chat, with the guidance it has to land inside. Then ask ONE
AskUserQuestion: approve / change (their notes). Changes go to the plan agent (SendMessage), then steps 3 and 4 again.

## 5. Build the user's file
On approval:
```bash
T=$(mktemp -d)
cp "$MODEL" "$T/before.xlsx"
python3 $R/scripts/move_rows.py --model "$T/before.xlsx" --plan "$MW/forecast_plan.json" --out "$T/moved.xlsx" --work "$T" > "$MW/move_report.json"
python3 $R/scripts/build.py --model "$T/moved.xlsx" --plan "$MW/forecast_plan.json" --out "$T/after.xlsx" > "$MW/build_report.json"
python3 $R/scripts/check.py --before "$T/moved.xlsx" --after "$T/after.xlsx" --plan "$MW/forecast_plan.json" --work "$T" --report "$MW/build_report.json" > "$MW/check_report.json"
```
Then lay out the driver sections (the plan's `layout`: named groups in the user's formatting; rows move, every formula
follows, and LibreOffice proves every value kept its place):
```bash
python3 $R/scripts/layout.py --model "$T/after.xlsx" --plan "$MW/forecast_plan.json" --out "$T/laid.xlsx" --work "$T" > "$MW/layout_report.json"
```
Exit 1 lists a line in no group, a key that isn't in its section, or a value that moved: send it to the plan agent
and rerun step 5 on a fresh `$T`. Run layout.py in the step 3 dry run too (after check.py), so a bad layout is caught
before the user approves. Copy `$T/laid.xlsx` (not `after.xlsx`) to `$MODEL` below.
check.py must exit 0. Its driver problems (a driver that doesn't feed revenue, a typed growth rate driving
revenue, a filings research check missing or out of bounds) go back to the plan agent like any other plan problem. Then check the model is unchanged since the copy (`cmp -s "$MODEL" "$T/before.xlsx"`) and no
lock file appeared; if it changed, the user edited it meanwhile: tell them and rerun this step. Otherwise
`cp "$T/laid.xlsx" "$MODEL"` and remove `$T`.

## 5b. Write-up (house default: explain each section, how it works and why certain key numbers are there)
```bash
python3 $R/scripts/modmap.py rowmap "$MODEL" "$MW/rowmap_after.md"
```
Fill `$R/references/writeup_prompt.md` (same fills as the plan prompt) into `$MW/writeup.assignment.md` and send it
to the plan agent (SendMessage, "Read `<that path>` and follow it exactly"): it knows why it built what it built. If
that agent is gone (a later session), dispatch a new one (model opus, `subagent_type: forecast-planner`). It writes
`$MW/forecast_writeup.md`. Check every row number it cites against `rowmap_after.md` and send wrong ones back. Then
render it (the contents page is on by default; the user wants one in every report):
```bash
python3 "$SKILLS/research-filings/scripts/render.py" "$MW/forecast_writeup.md" "$MW/<T> Forecast Write-up.pdf" --footer "<T> forecast write-up · <Mon YYYY>"
```

## 6. Look
`python3 -c "import sys; sys.path.insert(0,'$R/scripts'); import lo; print(lo.render_pdf('$MODEL', '$MW/preview'))"`,
then render the MOD pages that hold the forecast columns (`lo.page_png`) and look at them: blue typed inputs,
black formulas, numbers formatted like the history, no `#` errors, nothing cut off, the new Revenue Build rows in
place. LibreOffice draws a little differently from Excel; judge layout, not pixels. Remove `$MW/preview` after.

## 7. Deliver
Tell the user, in plain English:
- the build: the driver tree (the assumptions on each driver, and how revenue follows from them), then what drives costs, working capital, capex and the capital plan (2-3 sentences)
- the headline table vs the company's guidance and long-range plan (where it lands inside, where outside and why)
- the checks: revenue traced to the drivers, each filings research check row in bounds (or why not), balance sheet balances and cash ties in every forecast quarter and year, no errors, annual = quarters,
  nothing outside the forecast changed (and how many cells downstream of the forecast moved, e.g. charts and other
  tabs reading MOD)
- rows inserted, cells written, typed inputs and notes (build report)
- judgment calls: the assumptions with the weakest sources (the agent's list), anything marked `assumption:`,
  rows left blank under `keep` and why
- stale cells: typed numbers in forecast columns the plan didn't touch (`stale_cells`), by row, so they can clear them
- the write-up PDF path (`$MW/<T> Forecast Write-up.pdf`) and the three assumptions the agent says to look at first
- where the plan lives (`$MW/forecast_plan.md` and `.json`) so they can change an assumption and rerun
- next: offer to run /model-dcf (a 30-year key-driver DCF with yellow inputs they own, 2027-2030 tied to this
  forecast, and a reverse DCF: what the price implies)
