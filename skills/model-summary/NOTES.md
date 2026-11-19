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
- Street EPS and revenue come from the Consensus tab's latest snapshot (2026-11-19, reversing the earlier "Consensus not read"
  decision): the user asked, Consensus has more years than Multiples' 2-year forward table and has revenue. Multiples'
  forward-table Street EPS is the fallback when there is no Consensus tab or snapshot (no revenue then). Each Street cell
  notes the snapshot date and analyst count. Street EPS is the analysts' basis, so a GAAP model gets a warning.
- No NCI: SUM's EV must equal the DCF / Valuation bridge, which has none.
- Conditional formatting only on returns, IRR vs hurdle, R/R vs Buy-at-R/R, and Expected Delta vs a 3% band. The
  user declined price-vs-action-price and multiple-vs-history shading. The thresholds point at SUM cells that link
  Valuation's house inputs, not at the other tab directly, because Excel 2007 can't read another sheet in a CF rule.

## Formatting (2026-11-19, the user, after the DXCM build; modelled on the course instructor's NFLX SUM tab)
- Each block reads apart: a dark-blue (FF002060) title bar with white bold text across the block, light-blue bold
  column headers (years, scenario and ladder columns, Min / Median / Max), a thin outline per block, a thick one
  on the cap table, a top border between the grid's P&L rows and its multiples rows. Title 14 bold, body 11.
- Yellow means only "yours to type": the pale yellow FFFFFF99 of Valuation and Short Check. The instructor also
  fills key OUTPUT rows yellow; we don't (house rule). Key results (% return, x money, IRR, EPS, Expected Delta,
  risk price) are bold on pale blue with an outline instead.
- Formatting only: no cell moved. Styles are added after writing (tabkit.paint / box re-resolve a cell's style
  key); blank styled cells carry fills and borders. Mgmt contact's merge widened to B:D to line up with the blocks.
- Row 4 is fixed at 16pt: right-aligned headers carry wrapText (xlsx.Styles sets it with any alignment) and
  LibreOffice would otherwise grow the row.

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
