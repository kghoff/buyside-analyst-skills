# Short brief: chapter 12 (Short Selling), condensed for the short-analyst

The chapter's rules in its own words, cut down to what you need to fill `short_plan.json`. Section numbers (§12.x)
point back to the chapter. Nothing here is about one company: apply it to the company in front of you.

## Contents
1. Why stocks go down
2. FEV: the scorecard
3. Current vs future state, peak on peak, secular vs cyclical, temporary tailwinds
4. Short alpha buckets and types of shorts
5. Potential shorts and high odds of mispricing
6. Subpar algorithm (filler) shorts
7. Where to be careful
8. The risk case
9. Catalysts
10. Smoke
11. The verdict rule, code's ticks and the house defaults

## 1. Why stocks go down (§12.2)
- Price = P/E × EPS. A stock goes down for one of two reasons: **the EPS stream falls, or the P/E multiple falls.**
- EPS falls when revenue, margins or both shrink: slowly (a declining market, competition, compressing margins) or
  all at once on a print, when estimates are revised sharply lower. "A dollar of EPS can become fifty cents within a
  minute of an earnings release, or gradually over years."
- The P/E falls when the market reassesses revenue growth, margin trajectory, capital intensity or capital
  deployment; the terminal value (regulatory, competitive or technological overhangs); the riskiness of long-term
  cash flows; or rates and risk appetite. A stock with no terminal value should rarely trade above about 5x.
- **A low P/E is not safety.** "Many of the best shorts look cheap." If margins are temporarily high, a stock that
  fell from 15x to 8x may trade at 25x normalized earnings. If EPS is in decline, 7x may still be far too expensive;
  perhaps it should trade at 2x. "A stock that looks cheap may be a value trap."
- The short-seller mentality: focus on **something going wrong at the business**; work from source documents, not
  management or the sell side (still be able to state the bull case); dig into accounting policies; discount the
  Wall Street promotion machine ("the entire ecosystem is designed for stocks to go up").

## 2. FEV: the scorecard (§12.2)
"A stock should not be shorted on valuation alone, expectations alone or fundamentals alone; the goal is the
**confluence of all three**." Each bullet below is one scorecard row; its id is in `code`. Rows marked *(code)* are
ticked by code from the model; the rest are your judgment.

**FUNDAMENTALS**: "a business that needs more and more gas in the tank just to maintain its current equilibrium."
| id | Row | The chapter's words |
|---|---|---|
| `decel` *(code)* | Decelerating revenue growth | Weak and deteriorating revenue growth |
| `pricing` | Weakening pricing power | Weakening pricing power |
| `margin_pressure` | Margin or cost pressure | Margin pressure and rising cost pressure, or pricing pressure flowing through |
| `tailwind` | Mean reversion of a temporary tailwind | Mean reversion from strong to weak, such as the dissipation of a temporary tailwind (one of the most productive patterns) |
| `share_loss` | Market share loss | Market share losses |
| `incr_margin` *(code)* | Weak incremental margin, or margin at its peak | Weak incremental margins, or peak margins ("if margins are at a peak, there is only one way to go") |
| `capex` *(code)* | Capex step-up just to hold profit | Weak incremental ROIC: a step-up in capex merely to maintain current profitability |
| `leaky` *(code)* | Leaky bucket | Bolt-on M&A required just to keep profit flat, which implies the organic business is deteriorating |
| `fcf` *(code)* | Weak FCF | The promise of free cash flow "tomorrow," with poor free cash flow economics today. "Free cash flow is the ultimate driver of value." |

**EXPECTATIONS**: "Fundamentals are a necessary starting point but not sufficient."
| id | Row | The chapter's words |
|---|---|---|
| `hope` | Hope dissipation | A new product or initiative that is "in the stock" but likely to fail |
| `overhang` | A hard-to-disprove overhang | A perception risk not yet discussed that could enter the narrative as a "hard to disprove" controversy; such debates can take a decade, so valuations stay compressed while it persists |
| `miss` | An upcoming quarterly miss | Upcoming quarterly earnings misses |
| `revisions` *(code)* | Negative revisions | Negative revisions to annual Street estimates |

Misses and negative revisions "tend to be the catalysts that move the stock down."

**VALUATION**
| id | Row | The chapter's words |
|---|---|---|
| `vs_dcf` *(code)* | Expensive vs intrinsic value | Expensive relative to intrinsic value (an internal DCF) |
| `vs_peers` *(code)* | Expensive vs closest peers | Expensive relative to closest peers, ideally near the historical peak gap |
| `vs_history` *(code)* | Expensive vs its own history | Expensive relative to its own history, ideally near a (beta-adjusted) peak |
| `vs_algo` *(code)* | Expensive vs its growth algorithm | "If most 8% EPS growers trade at 14–16x, why is this one at 24x?" |

"Ideally, a short earns a check mark on all three dimensions."

## 3. Current vs future state, peak on peak, secular vs cyclical, temporary tailwinds (§12.2)
- Separate the **current state** from the **future state**. "The ideal time to short is often when the facts in
  front of the investor are most terrifying." When revenue is growing fast, margins are expanding, the narrative is
  strong and the sell side is supportive, ask what the business looks like when the tailwind fades. "The alpha comes
  from anticipating the future": if you wait for the facts to turn clearly negative, the trade has been missed.
- An EV/Revenue multiple bakes in a view on (1) long-duration growth and (2) margin: EV/EBITDA = EV/Revenue ÷ EBITDA
  margin (18x ÷ 20% = 90x). A huge multiple on a one-off surge assumes elevated growth stays elevated forever.
- **The market often mistakes cyclical for secular.** A secular trend continues in the same direction; a cyclical
  business rises and falls with the cycle. The market extrapolates an elevated level of growth.
- **Peak on peak**: the valuation at its peak *and* cyclical fundamentals at their peak. A crack in the P/E with a
  crack in EPS takes a stock from $300 to $30. The mirror image, **trough on trough**, works on the long side.
- **Temporary tailwind**: the market capitalizes a non-recurring EPS stream. Baseline EPS $1.00 at 25x = $25; a
  one-time $1.00 lifts EPS to $2.00 at 35x = $70 (+180%); when it goes, EPS $1.00 at 25x = $25 (−64.3%). "It is the
  'E' that matters", above all its run rate: a stock that quadrupled can look "cheaper" at 15x on peak EPS.
- The tactical signal for the peak is **sequential deceleration, then sequential decline**.

## 4. Short alpha buckets and types of shorts (§12.3)
Write `bucket.value` and `type.value` exactly as below (or `none`).

**Short alpha buckets**
- `Earnings catalyst`: a miss, a guide below, a "market mind change". A short's payday is more likely than a long's
  to come in one outsized move around earnings; the position has to be on *before* the cat is out of the bag.
- `Temporary tailwind set to dissipate`: a boost to revenue or margin that will not recur.
- `Melting ice cube`: a business in slow, steady structural decline.
- `Emerging overhang`: "on the menu to off the menu"; something off the regulatory or competitive menu begins to
  rumble, raising questions about terminal value. These narratives move in cycles.
- `Mispriced catalyst`: an event whose outcome the market prices wrongly.
- `Extrapolation, meet inflection`: an improving KPI is extrapolated into the stock; find the point where it slows
  before the market sees it.
- `Simplicity to complexity`: a large, messy acquisition or new initiative; complexity is priced at a discount.
- `Growth deceleration`: any slowing of the algorithm.
- `Liquidity runway`: the balance sheet and cash flow show the business may run out of cash (often the perception
  alone is enough).

**Types of shorts**
- `Temporary tailwind`: a one-off boost the market has capitalized as if it were recurring.
- `Dumpster fire`: a great deal going on, much of it unlikely to go well (acquisition, synergy targets, channel
  stuffing, a distribution overhaul, a worse business priced near a better one). None is a smoking gun; together
  they burn.
- `Liquidity pothole`: a company running out of cash.
- `Melting ice cube`: secular decline; often looks cheap and is a value trap.
- `Hope dissipation`: hope for a new product launch or turnaround that will be dashed.
- `Equilibrium to disequilibrium`: a settled market broken up, e.g. a new competitor in a slow-growing market.
- `Terminal value fear anticipation`: a long-term viability fear about to enter the narrative and compress the P/E.
- `Imminent time-out`: a company about to miss guidance, which takes two or three quarters to rebuild credibility,
  so the stock goes "off the menu".
- `Peak on peak`: peak multiple on peak (cyclical) fundamentals.
- `Decelerating momentum`: business momentum slowing, e.g. from 10% growth to 5%.
- `Subpar algorithm`: a filler short; see section 6.
- `Fraud`: needs a distinct toolkit (auditors, PCAOB filings, the web of promoters, on-the-ground diligence). Only
  call it with documentary evidence.

Also in the chapter: **broken roll-ups** (debt-funded acquisitions never integrated; they unravel when organic
growth or margins slip) and **tapering roll-outs** ("short restaurants when half the TAM has been addressed"; the
second half of a roll-out is harder and the multiple goes from 25–35x to 10–15x). Map them to the nearest type above.

## 5. Potential shorts and high odds of mispricing (§12.3)
| Potential shorts | High odds of mispricing (long or short) |
|---|---|
| Persistent pricing pressure in the business model | Recent or broken IPOs |
| A leaky-bucket business model, with bolt-ons to fill the hole | Corporate structure changes: divestitures, spins and the like |
| "Where's the cash?" accounting games | Post-bankruptcy companies |
| A secular threat from technology | Imminent regulatory change |
| A new competitor in a slow-growing market | A new product launch: too much hope, or not enough? |
| A consensus long at risk of an earnings miss | Less liquid stocks (under about $5 million a day) |
| A stock with past "freak-outs" but calm waters now | Recent major M&A |

- **Persistent pricing pressure**: prices falling 3–5% a year with volumes up 4% gives flat revenue, while opex grows
  with inflation and wages; the company must cut costs every year just to hold its margin.
- **The leaky bucket**: heavy acquisitions fill a hole left by a declining core; more and more EBITDA must be poured
  in to stay flat, until it can't and the decline shows.
- **"Where's the cash?"**: check GAAP and non-GAAP EPS against free cash flow per share. Profitable on a non-GAAP
  basis but persistently burning cash is a red flag. P/FCF = P/E ÷ FCF conversion (30x ÷ 25.6% ≈ 117x).
- **A new competitor in a slow-growing market**: in a market growing 1%, a new entrant taking a point of share from
  each incumbent makes them defend share aggressively, and the equilibrium breaks down.
- Structural decliners share secular revenue pressure, accelerating competition and margin pressure: a weak earnings
  algorithm, EPS barely growing or declining.

## 6. Subpar algorithm (filler) shorts (§12.3)
- Not every short is a 20–40% faller. **Filler** shorts are "below-average businesses at above-average multiples that
  will generate subpar returns." If the longs go up and the shorts merely stay flat, the difference is alpha: the
  **portfolio wedge**.
- If the P/E simply rolls forward, the return is EPS growth (plus the dividend, which the short pays). EPS +3% a year
  at a fixed 25x: $25.00, $25.75, $26.52, $27.32, $28.14. "There is no room for a 3% IRR stock in the long market
  value, but there is room for it in the short market value."
- On the tab: IRR = 3-year forward EPS CAGR + dividend yield; **wedge = hurdle − IRR**. A wedge above 0 means the
  stock returns less than the hurdle if nothing changes. Good filler shorts combine high valuation, a subpar
  algorithm and a subpar IRR.

## 7. Where to be careful (§12.3)
- **Pure valuation shorts**: when the business is good and accelerating, expensive can become more expensive.
- **Open-ended growth without a catalyst**: at 10x EV/Revenue with revenue growing 20% and accelerating, the multiple
  rolls forward and the short absorbs the growth. Find the algorithm shift: the deceleration.
- **Compounders without a catalyst**: "the algorithm can eat the short seller alive."
- **Crowded shorts**: short interest of about **10% of float is the Mendoza line**. Heavily shorted stocks are
  empirically good shorts, but a 10–15% short interest name must be sized very differently from a 1–2% one: the
  squeeze risk is far higher. Days to cover = shares sold short ÷ average daily volume.
- Borrow: the short pays the dividend and the borrow rate (low single digits for most stocks; 15–20% or more when
  hard to borrow). A 30% fall with a 30% borrow is roughly break-even.

## 8. The risk case (§12.4)
Ask:
- **What is the dream case?** What could a semi-rational person believe; how big and profitable could the business
  become if everything goes right? → `dream_eps`, `dream_pe`.
- **Is the short based on trough multiples and trough earnings**, or is it a genuine peak-on-peak setup? Shorting
  a trough is how a cheap stock rips against you.
- **Is this a takeover candidate?** What would a strategic or financial buyer want? "It is far more common to have
  shorts taken out than longs": a CEO who sees headwinds sells at a **20–60% premium**. Takeout-prone shorts must not
  be 5–10% positions. → `takeout_prone`, `takeout_premium`.
- **Is it a restructuring candidate?** Could the board or an activist unlock value?
- **The NTM roll-forward**: where can the stock be in 12 months? If revenue grows 30% with no crack at a constant
  multiple, the short loses 30% just on the roll-forward. The tab uses next year's EPS growth at today's P/E.
- The risk on the tab is the largest of: the dream case move, the roll-forward and the takeout premium.
- The reward case (`reward_eps`, `reward_pe`) is where EPS and the multiple land if the thesis is right. R/R =
  reward ÷ risk; the chapter's entry example is 70% ÷ 50% = **1.4x**.
- **VaR sizing**: a wrong short should cost no more than **50 bps** of the fund; max position = risk budget ÷
  risk-case move ($5M ÷ 50% = $10M, 2.0% of a $500M short book). Most shorts run 1–2%, high conviction 3–4%,
  rarely above 5%.
- **Print move**: if EPS misses 5% and the P/E slips a turn (20x → 19x), the stock falls 9.7%. Past earnings-day
  moves and implied volatility help frame it.

## 9. Catalysts (§12.4)
- First an **expectations gap** (a variant view the market doesn't see); then the market has to see the same
  information. The catalyst is where price and value converge. **The earnings print is the most common catalyst.**
- "Catalysts matter more on the short side": time is not on the short seller's side, since markets and the average
  stock rise over time. A naked short with no catalyst exposes the investor to many things going wrong.
- **Revisions**: look for the print at which management must change its tune on forward estimates; on that day
  estimates collapse and much of the return comes at once ("stocks follow numbers").
- **Imminent "time-out"**: a guidance miss that takes two or three quarters to rebuild.
- Why investors sell: something changed, a new risk or debate, the business slowed, guidance missed, long-term
  guidance pulled, a feared externality, or the stock went "off the menu". Anticipate that event.
- Timing is existential on the short side: "being right but early can look exactly the same as being wrong." Hence
  "shoot it in the back": wait for momentum to turn.
- `catalyst.soon` is true only if a dated or clearly expected event falls within **the next two prints**.

## 10. Smoke (§12.2)
"Where there's smoke, there's fire." Signs of obfuscation or aggressive accounting that can point to deeper issues:
- management integrity issues;
- changing auditors;
- changing CFOs or chief accounting officers (not always a paying signal);
- constantly changing metric disclosures (a KPI dropped, redefined or newly adjusted).
Win rates are lower and the chance of a disastrous outcome higher wherever there are signs of obfuscation or fraud.
Each smoke flag needs a `file.md:line` anchor and the quote.

## 11. The verdict rule, code's ticks and the house defaults
**Scores.** Count the ✓ per dimension. A dimension **passes** at: Fundamentals **≥ 5 of 9**, Expectations **≥ 2 of
4**, Valuation **≥ 2 of 4**. Only ✓ counts; ✗ and ? do not.

**The verdict rule** (code computes it, checked top to bottom; a different call needs a reason of ≥ 12 words, and it
shows beside the rule's verdict on the tab and in the note):
| Verdict | When |
|---|---|
| Alpha short | FEV confluence (all three dimensions pass), a catalyst within the next two prints, R/R ≥ 1.4x |
| Filler short | wedge > 0 (IRR below the hurdle), valuation passes, at least one fundamentals ✓ |
| Watchlist | two of the three dimensions pass |
| No short | otherwise |

"No short" is a good answer when the evidence says so.

**When code ticks** (shortmath.THRESH; `?` when the number can't be computed, e.g. a missing tab):
| id | Number (from context.md) | ✓ when |
|---|---|---|
| `decel` | TTM revenue growth minus TTM growth a year earlier | −1.0 point or worse (≤ −0.01) |
| `incr_margin` | incremental operating margin (TTM vs prior TTM) and TTM margin ÷ the 10-year FY peak | incremental < TTM margin, or TTM at ≥ 95% of the peak |
| `capex` | TTM capex ÷ D&A | ≥ 1.5x |
| `leaky` | acquisitions ÷ cash from operations, last 20 quarters | ≥ 25% |
| `fcf` | FCF ÷ net income (non-GAAP when MOD has it), last 20 quarters | < 70% |
| `revisions` | change in the Street EPS mean between the first and last Consensus snapshots of one period | −1% or worse |
| `vs_dcf` | price vs the Valuation tab's DCF base value per share | price above it |
| `vs_peers` | percentile of the P/E gap to the core-peer median (Multiples) | ≥ 70th |
| `vs_history` | percentile of the P/E in its own history (Multiples) | ≥ 70th |
| `vs_algo` | the wedge (hurdle − 3-year EPS CAGR − dividend yield) | above 0 |

Keep code's tick unless the documents show code is misreading the number (e.g. growth capex for a new plant, a
one-off acquisition); an override needs a reason of ≥ 12 words.

**House defaults** (each is a yellow cell the user owns; keep anchor `house` unless a ≥ 12-word reason says why not):
| Input | Default |
|---|---|
| `hurdle` (IRR hurdle) | 8% (0.08) |
| `fund` (fund size, $M) | 1,000 |
| `bps` (risk budget per idea) | 50 |
| `short_book` (short book, $M) | 500 |
| `crowded_line` (short % of float) | 10% (0.10) |
| `print_miss` (EPS miss on a bad print) | −5% (−0.05) |
| `print_pe_slip` (P/E turns lost on a bad print) | 1.0 |

The borrow rate is the user's (their prime broker's quote); unknown shows "check with PB" and the drag at 5% and 20%.
