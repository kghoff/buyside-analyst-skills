# model-summary: notes

## Decisions (2026-11-19, with the user)
- SUM only sets the table: code only, no agent. Judgment cells (Buy / No-brainer price, Thesis Summary, Trading
  Plan, Valuation Thoughts, Mgmt contact) are empty yellow boxes that write-pitch fills. Action links Valuation's
  verdict until typed over.
- Course-template layout (all 10 Mod6 example models share it): left cap table and targets, middle estimates,
  right scenarios and ranges, far right the tactical R/R grid.
- Scenarios mirror Valuation's probability tree row for row (any branch names). The metric x multiple columns are
  filled only where a branch's target formula is the primary multiple's reward or risk price.
- ADV: the Multiples comp sheet first (Yahoo's 3-month average, raw shares), then Px Data's source CSV (63 days, as
  fresh as Px Data), then Yahoo, then a CSV placed in the work folder by hand.
- Street EPS comes from the Multiples forward table, so the Consensus tab isn't read.
- No NCI: SUM's EV must equal the DCF / Valuation bridge, which has none.
- Conditional formatting only on returns, IRR vs hurdle, R/R vs Buy-at-R/R, and Expected Delta vs a 3% band. The
  user declined price-vs-action-price and multiple-vs-history shading. The thresholds point at SUM cells that link
  Valuation's house inputs, not at the other tab directly, because Excel 2007 can't read another sheet in a CF rule.

## Pieces
- links.py finds everything by label (formulas only, no recalculation); a missing label stops and names the skill.
- SUM goes to position 0. tabkit.move_first shifts localSheetId, activeTab and firstSheet; xlsx.remove_sheet now
  shifts activeTab and firstSheet down too, so remove-then-add reruns don't drift the open tab.
- Rerun keeps are found by label (layout.INPUT_OFFSET), so a change of shape (more years, longer ladder) keeps them.
- Grid: the last 4 actual years plus at most 5 forecast years (links.MAX_FORECAST_YEARS), so it stays inside F:N.
- The 12-month base and risk headers say "({kind} only)": the blended R/R and the tree use blended prices.
- Cap table header names the balance-sheet period from the DCF bridge (may be a forecast quarter, e.g. Q4 26E).
- SUM is made visible on open (firstSheet = 0); the open tab (activeTab) is kept.
- Build warns when Valuation's "Position (long/short)" is short: SUM's returns and colours are long-side math.
- ADV: the Yahoo download goes into W/yahoo/ and never overwrites a hand-placed W/<t>_us_d.csv. The stop message
  says why each route failed (missing, fewer than 63 days, or stale).
- verify's slow tests include proof that a wrong link target is caught.

## Known issues
- styles.xml gains about 23 cellXfs and 3 dxfs per rerun: the shared xlsx.Styles appends and never reuses.
  Harmless, but it grows.
