# Earnings preview brief (chapter 13, distilled)

Read this before the assignment. It is the chapter's advice; the code already did the arithmetic.

## 1. Why the print matters
Four print days are about 2% of the year and drive about 20% of a stock's idiosyncratic volatility. The print is
the most common catalyst for the market to converge on a variant view. Price = P/E x EPS: a big move needs EPS
revisions (usually from guidance), a change in the multiple (an "algorithm shift": the market changes its mind about
growth and margins), or both. Example: guide cut $1.00 -> $0.75 and 20x -> 18x = -32.5%.

## 2. What moves a stock on a print
1. Guidance changes (look first). 2. The beat or miss on the key lines and KPIs, and above all business momentum:
markets extrapolate. 3. Tone and forward commentary. Big moves do not come on FX- or tax-driven beats. A one-penny
miss matters when the algorithm shifts (7% grower -> 5%) or the buy-side whisper breaks.

## 3. It is the surprise that matters
"If it's in the press, it's in the price." Management commentary, guidance, sell-side commentary and widely shared
alternative data are beta, not alpha: assume shorter-duration investors have priced every public data point. A
company that always beats (UNH) is priced for the beat: an in-line quarter is the surprise. A prudent CFO guides
low and walks the range up; for a habitual raiser, "no raise" can mean off plan (see the guidance trail).

## 4. The set-up (rows and their ids)
Good set-ups are contrarian. Each row is long, short, neutral or unknown.
| id | Long set-up | Short set-up |
|---|---|---|
| value_perf | Underperformed and at the low end of its P/E range | Performed well and at the high end (code answers this row) |
| consensus | Consensus worried about a weak or decelerating quarter | Consensus expects a strong or accelerating quarter |
| ratings | Recently downgraded | Recently upgraded |
| previews | Sell-side previews cautious | Sell-side previews optimistic |
| positioning | Other investors short and/or nervous | Other investors long and adding |
| view | We expect better than expected | We expect the quarter or outlook to be worse |
A set-up is a matter of degree: a consensus long can still be a good long if the market misjudges the size (NVDA).
Positioning is a paradox: crowded trades are usually right but crash-prone; the unwind happens on prints. Be extra
careful with volatile margins, unprofitable companies that may need capital, and peak P/Es (code flags all three).
Spring-loaded set-up (MEDP Q3 22): multiple compressed, concern high, business normal -> a normal print pops.
Peak-on-peak (TDOC Q1 22): high valuation + deceleration + broken strategy + no visibility -> collapse.

## 5. Expectations
Six dimensions: guidance, sell-side consensus, the narrative, price-implied expectations (reverse DCF, reverse P/E),
the buy-side whisper and positioning. The whisper has to be divined: write your estimate and label it as yours.
Use the 2-year stack to test a guide against the trend (a 5% guide that breaks a 14-15% stack is a low bar).

## 6. The key metric
Usually one metric moves the stock on a print (subscribers, comps, organic growth, gross margin). Name it and say
why, tied to the debate. Print-day trading is not nuanced: traders look for beats and misses on that metric.

## 7. Model checks (code computed them; read them)
- Hockey stick: yoy growth accelerates, the 2-year stack accelerates and sequential growth beats its 5-year average
  for that quarter. Be wary unless something concrete stands behind it (a contract, a launch). If the guide has to
  fall, the multiple falls with it.
- Seasonality: a guide far below the usual quarter-on-quarter step (AMZN Q4 22: 13% vs ~31%) is conservative; far
  above it is aggressive. Mix changes shift seasonality; say so if they do.
- Margin against the quarter's 5-year average and the incremental margin: a guided margin below the run-rate in the
  seasonally strongest quarter can be a set-up for a profit beat.
- Second-half share: a back-half ramp after a weak first half often precedes estimate cuts.
- Exit rate: the market carries the last month's growth forward; say so when the documents mention it.

## 8. Base rates
The average absolute print move, the up / down count, the move in daily sigmas and the options-implied move (when
the date is announced) tell you how much is likely to happen; none tells you the direction. Some stocks blow up
regularly (TDOC); some grind (UNH). Use the history to size the downside case.

## 9. The cases and P(upside)
Upside and downside are each an EPS for the next 12 months and a P/E: price = P/E x EPS against today's price.
- EPS: start from our NTM EPS, consensus (Consensus tab) and the guide; say how far this quarter moves the out-year.
- P/E: anchor to the Multiples ranges (5-year min, median, max) and to what the algorithm shift would do.
- The upside price must be above today's and the downside below it.
- Implied PSUC = |down| / (up + |down|): the odds the market implies for the upside case. P(upside) is your own
  probability of the upside case; edge = P(upside) - implied PSUC. Look for out-of-consensus outcomes with a low
  implied PSUC.

## 10. The stance (the rule decides; you state it)
Stances: add, hold, trim, hedge. Code's rule with the house thresholds (the user can change them on the tab):
- add: R/R >= 2.0, edge >= +10 pts, set-up net long or even, at most one blow-up flag;
- trim: edge <= -10 pts, or R/R < 1.0 with the set-up net short;
- hedge: neither, and the downside is >= 1.5x the implied move, or two or more blow-up flags;
- hold: everything else.
Your stance must equal the rule's answer. If you disagree with it, say why in the stance reason and in
judgment_calls: the user may override it on the tab, you may not.

## 11. The call
- quarter: beat, in line or miss (against consensus on the key metric).
- guide: raise, hold, cut, initiate (first guidance) or none given.
- expected_move: the size of the move on the day, either way (a fraction: 0.05 = 5%).

## 12. Risk scores (1 = lowest risk, 5 = highest)
- profit_stability: the odds of an earnings blow-up (margin volatility, mix, one-off orders).
- liquidity: balance-sheet liquidity (cash, debt, need to raise capital).
- valuation_skew: how far the multiple can reset (high in its range = high score).
- rating_change: the chance of a downgrade (well-liked stocks have further to fall) or an upgrade.
- revision: how far estimates could move after this print.

## 13. What you write
- net: one line (<= 40 words) a PM can act on.
- points: last_quarter (what was guided and flagged), since_last_print (what management, the sell-side and the
  news said since, each with a quote), checkpoint (what this print will tell us about the thesis; catalysts after
  it). Every point quotes its file.md:line.
- judgment_calls: every call you made that the user should hear about (a call the user never hears about is the
  worst outcome).
- Orientation: say which questions matter for an owner with a three-year view ("are we getting too cute?") versus a
  trader's; do not invent the user's position.
