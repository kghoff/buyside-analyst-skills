---
name: model-summary
description: Add the SUM tab to a company model (TICKER_model.xlsx) as its first sheet, left of MOD - the PM's one-page view from the course: ticker and action (linked to Valuation's verdict), cap table (price, diluted shares, market cap, debt, cash, net debt, EV, cash per share, 3-month ADV), Buy and No-brainer price boxes, NTM free cash flow and yield on our own estimates, the 3-year target and IRR, the 12-month base target and risk case on the primary multiple, blended R/R, internal estimates for the last 4 actual and up to 5 forecast years against the Street (EPS and revenue from the Consensus tab) with Expected Delta and Revenue delta and valuation on each year, Valuation's probability tree row for row, the multiple's own, S&P-relative and peer-relative ranges, and the tactical R/R ladder. Every number links to the tab it comes from; the thesis summary, trading plan, valuation thoughts, action prices and management contact are empty yellow boxes for write-pitch; conditional formatting on returns, IRR vs hurdle, R/R and Street variance. Code only, no agent. A rerun keeps what was typed. Works for any listed company. Run after /model-valuation; rerun each print. Use when the user runs /model-summary TICKER or asks for a summary tab, a SUM tab or a PM one-pager in the model.
---

# /model-summary

```bash
SK="<this skill's base directory>/scripts"      # the base directory is shown when the skill loads
SKILLS="<this skill's base directory>/.."
```

Adds one tab, **SUM**, as the first sheet. It **sets the table**: it links what the other tabs already worked out and
leaves the judgment boxes empty for write-pitch. Code only, no agent, no web search except the ADV fallback.

## Requirements
The model needs MOD (with at least 4 forecast quarters), Px Data, DCF, Multiples and Valuation. If one is missing,
build.py stops and names the skill to run.

## Step 1: Locate and check
1. `python3 "$SKILLS/model-ratios/scripts/locate_model.py" --ticker <T>` (or the path the user names). Set `M` to it and
   `W=<model dir>/_model_work/model-summary`.
2. If `~$<model file name>` exists next to `M`, ask the user to close Excel and wait.
3. `SHA=$(shasum -a 256 "$M" | cut -d' ' -f1)`. Never write to `M` before Step 4; keep no backup copies.

## Step 2: Build
`python3 "$SK/build.py" --model "$M" --work "$W" --ticker <T> --out "$W/out.xlsx"`. It prints the report's facts as JSON. If it stops, tell the user exactly what it says (which tab or row is
missing, and the skill to rerun) and stop.

If it stops on **no 3-month ADV**, it names the file it wants in `$W`. Tell the user. The message says why each route failed (file missing, fewer than 63 trading days, or stale). Put a daily CSV with that name
and the columns `Date,Open,High,Low,Close,Volume` there from any source you have, then rerun Step 2.

SUM opens visible: the build sets firstSheet to 0 and keeps the tab that was open (activeTab).

## Step 3: Verify
`python3 "$SK/verify.py" --out "$W/out.xlsx" --work "$W"`. It must exit 0 (its slow tests prove that a wrong link target is caught). On a problem, fix the cause; never copy a
failing build over the model.

## Step 4: Copy over
`python3 "$SK/copyover.py" --model "$M" --built "$W/out.xlsx" --sha "$SHA" --work "$W"`. It refuses if the model
changed since Step 1 or Excel has it open.

## Step 5: Report (plain English)
- That SUM is now the first tab, and a reminder to open the file in Excel, where it recalculates.
- The primary multiple behind the 3-year target, 12-month base and risk case (Valuation's choice).
- The NTM window (`ntm_quarters`): our own estimates, never the Street's.
- The ADV route (`adv.note`): the Multiples comp sheet, Px Data's source file, Yahoo, or a CSV placed by hand.
- The grid's years (`years`: the last 4 actual and at most 5 forecast years, so it stays inside columns F:N) and the Street: its source (`street.source`: the Consensus tab's latest snapshot, or the Multiples forward table as the fallback), the snapshot date, and the years with Street EPS (`street.eps_years`) and Street revenue (`street.rev_years`); the other years show n/a.
- The tree's branches and the ladder's rungs, as Valuation has them.
- The build report's keys: `tab`, `primary`, `ntm_quarters`, `years`, `street` (`source`, `snapshot`, `eps_years`, `rev_years`), `tree`, `ladder_rungs`, `adv` (`route`, `note`), `users_kept`, `action_follows_valuation` and `warnings`.
- Every warning (including the GAAP-basis warning: analysts' EPS is usually non-GAAP, so with a GAAP model the EPS Expected Delta compares different bases; and the short warning: if Valuation's "Position (long/short)" is short, SUM's % returns and their colours are long-side math, so read them inverted), and which yellow cells were kept (`users_kept`). Say whether Action still follows Valuation.
- That Buy price, No-brainer price, Thesis Summary, Trading Plan, Valuation Thoughts and Mgmt contact are empty
  boxes waiting for write-pitch (or the user).
- Judgment calls to name every time:
  - the Street variance band defaults to 3% (the skill's choice, not the course's);
  - actual years' multiples use today's price and EV (as in the course);
  - the 12-month base and risk headers say "({kind} only)" because the blended R/R and the tree use blended prices;
  - the cap table header names the balance-sheet period from the DCF bridge (it may be a forecast quarter, e.g. Q4 26E);
  - Street EPS and revenue come from the Consensus tab's latest snapshot (each cell's note names the date and analyst count); without Consensus, Street EPS falls back to the Multiples forward table (2 years) and Street revenue is n/a;
  - NCI is not in the cap table because the DCF bridge, and so Valuation's EV, has none.
