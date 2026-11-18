# model-valuation: notes

Not read at runtime. Read before changing the scripts. Spec: docs/2026-11-17-applied-valuation-design.md §4 (plus §2
brief, §5 testing, §6 judgment calls); plan: docs/2026-11-17-model-valuation-plan.md (both local).

## Pieces
| Script | Job |
|---|---|
| `valmath.py` | the chapter's math, pure: targets, R/R, ladder, IRR and the 3 R's, tree; `METRIC` fixes the pairing |
| `metrics.py` | NTM / NTM+1 / year-3 blocks from MOD's forecast quarters, volatility, growth CAGRs |
| `context.py` | `context.json` + `context.md` for the agent: metrics, the DCF bridge, tab dumps, brief, house defaults |
| `scenarios.py` | expands the agent's compact driver sets into model-dcf inputs; checks the case shape |
| `scenario_eval.py` | the model-dcf bridge, its own process only: `context` / `eval` / `typecheck` |
| `plan.py` | shape and rule check of `valuation_plan.json` |
| `anchors.py` | every anchor checked against its cell, research line or forward sum |
| `build.py` | the Valuation tab by raw-XML editing; keeps the user's yellow cells; writes `layout.json` |
| `verify.py` | recalculate, compare, errors, byte-identity, colours, pairing, DCF re-type, anchors, PNG |
| `note.py` | the valuation note, MD + PDF (research-filings' `render.py`) |
| `xlsx.py lo.py modmap.py notebox.py brief.py subject.py` | copied from model-multiples; keep in sync |

## Decisions (2026-11-17, with the user)
- **Yellow means the agent chose it and the user owns it.**
  - Each yellow cell has a note with the agent's value, its anchor and a one-line reason.
  - A **Reasoning** column (H) runs beside every section.
  - **No approval pause.**
  - A rerun keeps the user's value. A yellow cell is the user's when it differs from what the last build wrote
    (`inputs_written.json`) or holds a formula. The note then says what the agent suggested.
- **The agent works the reverse DCF itself.** It writes `scenarios_try_<n>.json` (base / bull / bear driver sets).
  `scenario_eval.py` runs them through model-dcf's `dcfmath` and `solve` (the same math as the DCF tab). The agent
  revises, for up to 5 rounds, and records why each round changed.
- **1–3 multiples, P/E first unless ruled out; never one in isolation.** Levered metrics are paired with equity value
  and unlevered metrics with EV. Code fixes the pairing (`valmath.METRIC`), and the plan check rejects anything else.
- **The agent reads context, not whole reports.**
  - It reads the valuation brief (`brief.py`, a copy of model-multiples'). It is reused if it is newer than both
    reports.
  - It may Grep or Read the full reports for specifics. Every research number it uses cites `file:line`.
- **Anchors** come in four kinds, all checked by `anchors.py`:
  - **a cell** (`Multiples!F42`): the cell must hold `anchor_value`;
  - **a research line** (`Filings Research/<file>.md:123`): the line must print `anchor_value`;
  - **`house`**: allowed only for the house inputs, which come from chapter 11's defaults;
  - **`judgment`**: allowed only for blend weights, tree probabilities and the long/short switch. A `judgment`
    anchor needs a reason of at least 12 words.

  An input's `value` may differ from its `anchor_value`, for example a 22x reward multiple anchored on a 26.2x
  trough. The reason says why. This is how "never type a number that isn't printed in a source" holds for agent
  judgments: the anchor is printed in a source, and the step away from it is explained.
- **model-dcf is imported, not copied.**
  - `scenario_eval.py` puts `../../model-dcf/scripts` first on `sys.path` and is only ever run as its own process.
    model-dcf's `build`, `context`, `xlsx` and `lo` would otherwise collide with model-valuation's own modules of the
    same names.
  - Why: the spec requires "the math matches the DCF tab exactly", and a copy could drift. Every other shared helper
    is copied, per the house pattern.
- **model-valuation's `lo.py` has its own LibreOffice profile** (`model-valuation-lo-profile`). The DCF re-type check
  runs inside the model-dcf process and uses model-dcf's `lo.py` (a known shared-profile issue, logged in NOTES).
- **NTM is quarterly.**
  - NTM is the sum of MOD's first four forecast quarters; NTM+1 is quarters 5–8 (chapter 11.5: "forward quarters
    five through eight").
  - The 3-year metric is quarters 13–16. With fewer forecast quarters, the IRR horizon becomes the last full year
    available. The tab and the note say so.
  - MOD needs ≥ 8 forecast quarters, or the skill stops.
- **Today's price, net debt and diluted shares link to the DCF tab** (C18, C14, C16), so both tabs use one bridge.
  Annualized volatility is an array formula over Px Data's last 253 closes.

## Review decisions (2026-11-17)
- **An out-of-date DCF tab stops the run** (it used to be a warning). `scenario_eval.py context` sets `stale` when the
  tab's value per share is more than $0.02 from what its inputs give, or when its input rows and year columns are not
  where model-dcf's `build.layout` puts them for the current forecast plan (each input's label on its row, each input
  year in its column, and no `orphans` from `read_inputs`). build and typecheck type into the cells the layout names,
  so an older layout (e.g. fewer revenue drivers) would put the scenarios in the wrong cells. `context.py` raises
  SystemExit with the reason before writing context.json.
- Anchors gained a fifth kind, the **forward sum** `ntm:<metric>`, `ntm1:<metric>` or `y3:<metric>` (metric `eps`,
  `rev`, `gp`, `ebitda` or `fcf`), checked against the MOD sums in context. Risk metrics anchor here. Cell anchors
  match to the decimals the agent wrote.
- **One multiple:** a plan with a single multiple must carry a `notes` entry starting `One multiple:` that says why
  one is enough (the "never one in isolation" rule, made checkable).
- `judgment` is also allowed on `normalization.years` (the years to discount back are rarely printed).
- A house input the agent changes from chapter 11's default needs a reason of at least 12 words.
- User inputs flagged as the user's stay theirs on every rerun, not only the first one after they changed them.
- No `inputs_written.json` record (first run over an older tab, or the record was deleted) = every yellow value that
  differs from the plan is treated as the user's, and the build warns.
- The test fixture is the repo's DXCM example model.
- Tests share LibreOffice work per session (the suite took 12m49s when each test did its own): `fixture_values` (one
  recalculation), `work_base` (context.py once; each test gets a copy via `copy_work`) and `noted_base` (one build +
  verify). Files that need a recalculated work folder are marked `slow` (run-tests.sh --full).
- `scenario_eval.py` appends its own folder to `sys.path` after model-dcf's (theirs win on shared names), and its
  stale check recalculates under `W/dcf_stale/`.
- The note reads every number from verify's recalculated file (layout.json refs, else the tab's column-A labels) in the
  cell's own number format, so a label renamed in `build.py` shows as "n/a" in the note: rename both together.
- The plan has no field for a gap-flag explanation; the agent writes it in `notes` (assignment.md), and the note
  quotes each note naming the case or "gap". None found = the note says so instead of staying quiet.
- The note always has `## 6 Earnings power` (saying "not used" without normalization) so the numbering has no hole.

## Known issues
- The DCF re-type check uses model-dcf's `lo.py` and its LibreOffice profile, which other skills share: don't run two
  skills' verifies at once.
- `subject.py`'s messages say model-multiples (it is a copy).

## DXCM baseline
End-to-end run, 2026-11-17, on a scratch copy of the user's model. The Multiples tab was built first (free path);
the DCF tab was rebuilt with /model-dcf because the forecast plan had gained a revenue term since it was built.
- **Inputs:** price $88.48 (Px Data, 2026-11-04). NTM EPS $2.886, NTM+1 $3.592. Vol 37.7%. DCF tab $91.63.
- **Multiples:** P/E primary (0.7), EV/EBITDA secondary (0.3); FCF yield left out because rebates flatter FCF.
  The agent rejected the 5- and 10-year medians (81.8x P/E), which were set on depressed earnings. It anchored to
  the 1-year window and the comps instead: this was the run's pass criterion.
- **12-month roll-forward:**
  - Blended reward $100.36 (+13.4%).
  - Risk $58.20 (−34.2%).
  - R/R 0.4x, below the hurdle.
  - The 1σ check flags the risk case as inside one standard deviation.
- **3-year IRR:** 11.2% on P/E, made of +20.7% a year EPS growth and −7.8% a year re-rating.
- **DCF:** bear $49.94, base $85.41 (WACC raised to 8.5%), bull $135.23. Two rounds; round 2 trimmed the bull's
  terminal multiple to 11x. Bull vs the blended reward is flagged as a gap over 25%.
- **Tree:** probability-weighted $88.38; today's price sits at 45% of the range.
- **Checks:** plan and anchor checks clean; verify ok, 118 cells checked, 0 failed, DCF re-type within $0.02. The
  note is 4,036 words (MD + PDF).
- **Known cosmetic issue:** two long labels in section 6 are cut off at column A's width.

## Overall verdict (2026-11-18, the user's ask)
- The agent writes `verdict: {value: Buy | Hold | Sell, reason}`. It goes in row 3 (A3 label, B3 yellow, H3 reason),
  above section 0, so no row below moves and model-short's label lookups are unaffected.
- **Agent only, no code rule** (the user's choice). The per-multiple and blended R/R verdicts (`valmath.verdict`)
  stay as they were. plan.py is the only guard: one of the three words, and a reason of at least 12 words.
- It is a `judgment` input like any other (`plan_inputs` adds it), so the user's own verdict survives a rerun.
- It leads the note's cover.
