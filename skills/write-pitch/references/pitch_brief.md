# Pitch brief: chapter 14 (Pitch Like a Pro), condensed for the pitch-analyst

What a pitch has to do, in our own words, cut down to what you need to write `pitch_plan.json`. Section pointers
(§14.x, §3.x, §5.x, §11.x) lead back to the course chapters for anyone who wants the long version. Nothing here is
about one company: apply it to the company in front of you. The plan's exact fields are in `plan_schema.md`; this file
says what goes in them and why.

## Contents
1. What a pitch is
2. The three critical questions
3. The slide order
4. Thesis points
5. Risks
6. Where we're different
7. Risk / reward and the hurdles
8. Alpha buckets, idea patterns and the stock-picker phrases
9. The call rule
10. Style
11. Reading order and the plate file
12. Common mistakes

## 1. What a pitch is (§14.4, §14.1)
- **A pitch is a commercial transaction.** You are asking someone to commit capital: buy, sell short, or wait for a
  better price. It is not a display of everything you learned. It also has to show the research behind the call,
  so the listener trusts the conclusion; but the research serves the call, never the other way round.
- **It is not a book report.** A book report covers a little of everything. A pitch finds the core debate on the
  stock (the one or two things that will move it) and shows where your work differs on that debate.
- **"The most important thing"** (§14.4): your own view on one piece of the business, strong enough that it changes
  where you expect a specific line (or run of lines) in the income statement, balance sheet or cash flow statement to
  go. It does not have to oppose the Street on direction: a difference in size, an acceleration or slowdown the Street
  misses, or a fresh angle on a stock everyone already likes or hates all count. Often the work disproves a fear rather than proves a hope. Write it as one sentence in
  `most_important_thing`, and make sure every core slide connects back to it.
- **Story and math, always both** (§14.4). People act on fear and greed and on stories far more than on numbers; a
  story needs a character (the company), a goal, a struggle, the effort and a resolution. But a story with no math
  does not get capital. The math answers four questions the listener is asking silently: how much can I make (the
  base and bull cases, the 3-year IRR); how likely am I to lose and how much (the risk case, the R/R); where are we
  versus the Street on estimates; what is it worth on normal earnings or free cash flow. Spoon-feed the math: "from
  {price} to {target_3y}", not "the stock is undervalued".
- **The 20-second pitch** (`pitch_20s`) is the thesis said out loud: position, why it is mispriced, what is changing,
  the number that matters, the valuation gap, and an ask. If you cannot say it in 20 seconds you do not have a
  thesis yet (§14.2, §14.4). The full pitch goes in `pitch_20s` (box budget, 420 characters) and opens the pitch
  sheet; slide 2's takeaway is a shorter version of it, cut to the 160-character takeaway budget.
- **Serve the judgment** (§3.7, §14.2). The PM decides; your job is to lay out the bet so the decision is easy:
  name the driver the bet rides on, and show EPS and the stock across a sensible range of it. Advocate, but never
  "buy this or you're wrong". The listener should leave with a decision, or knowing exactly what would produce one.

## 2. The three critical questions (§14.2, §3.7)
Every PM asks these three, in some form. The core deck must answer all three without the listener having to ask.

**1. Get me up to speed.** A full answer holds: what the company does and how it makes money (one picture beats three
bullets); the industry in a few lines; the history lesson (what has driven the stock and the numbers over the last
few years, and any prior pattern this resembles); the set-up (what just happened to the stock, what the market now
believes, and why that belief may be wrong). Ten to fifteen minutes of the listener's time, not three days. Sources:
the filings report's business and history sections, the Idio Chart and Px Events tabs, the street report's
narrative sections.

**2. Where are we different, and why?** A full answer holds: the key drivers (usually two or three, from the filings
research); what the price embeds for each (the reverse DCF on the DCF and Valuation tabs, the trough or peer multiple);
our estimates against the Street, on the Street's own basis (SUM's internal-vs-Street rows); the bull and bear
debate and which side we take; and the research behind each difference (a driver calculation, a disclosure, a quote,
a channel the Street is not reading). "What is the source of the alpha?" must have a concrete answer.

**3. What is our path to getting paid?** A full answer holds: the mandate fit (a long-duration compounder needs no
near-term catalyst; a higher-turnover book does); the catalyst path, starting with the next print and what it should
show (the earnings preview's stance and key metric); the split of the expected return into the three R's (roll-forward
of the multiple onto later earnings, revisions to estimates, re-rating of the multiple; §4, the Valuation tab); and
the likely incremental buyer (who owns it next, at a higher price, and why).

## 3. The slide order (§14.3, §3.7; spec §7)
The first ten slides are the core deck, short enough to present in well under ten minutes; everything after backs it up. The deck
is an accordion: a point that needs ten slides of proof gets them in support, never in the core.

| # | type | What it must prove | Fed by | Numbers it needs (keys are examples) |
|---|---|---|---|---|
| 1 | `title` | The position and the company in one glance; what the company actually sells | A product picture cropped from the company's own deck (`image`: pdf, page, crop) | none required; the call is in the title ("LONG XYZ", "SHORT XYZ", "WATCH XYZ") |
| 2 | `summary` | Everything the PM would otherwise pull up on a terminal: size, liquidity, capital structure, our EPS vs the Street, multiples by year, buy and no-brainer prices, 3-year target, 12-month base and risk | SUM tab (cap table, estimates vs Street, multiples), Valuation tab | `price`, market cap, ADV, net debt, our and Street EPS by year, P/E by year, `target_3y`, `base_ret`, `risk_ret`, `buy_price`, `nobrainer_price` |
| 3 | `setup` | How we got here: the price path with the big moves labelled, and why the market now holds the view it holds | Idio Chart, Px Events, the filings report's history section, street report | the big moves (date, move) from Px Events; price now vs the high and low |
| 4 | `thesis` | Exactly three reasons to own (or short) it, each with the number that proves it | Filings report key drivers, `drivers.md`, the forecast write-up, street report | the one number per point (e.g. our vs Street EPS, a driver growth rate, an incremental margin) |
| 5 | `risks` | The two risks that could break the thesis, with probability, cost and mitigant; tripwires that tell us we're wrong | Filings and street PM reviews, the short note, the Valuation risk case | each risk's cost if it hits (a price or a return); tripwire levels |
| 6 | `why_now` | Why the mispricing exists: the alpha bucket and why the market has it wrong now | Street report (where outsiders differ), Multiples, Px Events, positioning | a sentiment or positioning number if one exists; the set-up move |
| 7 | `valuation` | Where the stock trades against its own history, the S&P and its peers | Multiples tab (P/E history chart, ranges, comp sheet) | current multiple, its 5- or 10-year median and percentile, the peer median |
| 8 | `different` | Our estimates vs the Street on the key lines, and what the price implies per key driver vs what we think | SUM, Consensus, DCF (reverse DCF), Valuation's DCF scenarios | our and Street revenue / margin / EPS for two or three years; implied vs our driver values |
| 9 | `risk_reward` | Bull / base / bear with probabilities, the 3-year IRR against the hurdle, the three R's, the R/R ladder by entry price | Valuation tab (probability tree, IRR, three R's, ladder); Short Check for a short | each case's EPS, P/E, return and probability; `irr_3y`; the three R's; `rr_12m` |
| 10 | `catalysts` | The path to getting paid and the trading plan: next print and the preview's stance, other dated events, the incremental buyer, tripwires and what we do at each | Earnings tab and preview note, the filings report's catalysts, the after-print note | the next print date; the preview's implied move; trim and add levels |

**Support slides** (10 to 25; `section: "support"`, layouts `text_chart`, `table`, `quote`, `two_column`, `image`,
`checklist`): at least one per thesis point and one per risk, each marked with `supports` (`thesis.1`, `thesis.2`,
`thesis.3`, `risks.1`, `risks.2`). Good material: the driver math, a Filings Charts or Idio Chart picture, the comp
scatter of P/E against growth, the consensus revision history, industry share, a variance table, verbatim cited
quotes from the company or the sell side. A large delta to the Street needs the most backup: show the line items, not
just the total.

**Appendix slides** (`section: "appendix"`), the Q&A bank. Always include:
- the risk checklist (section 5 below) as a `checklist` slide: one item per area, the area and your one-line answer
  in `q` and a short verdict in `a` ("Low risk", "High risk"), plus items for what takes the stock down 25% and 50%
  and how likely each is;
- the 15-question stock-selection checklist (§14.3) as a `checklist` slide: one item per question, "Yes", "No" or
  "Partly" in `a`, with the score in the takeaway. It is a check that the idea earns a place in the book, not a
  scoring formula; a "no" is fine if the slide says why it doesn't matter here. In
  our words: (1) business momentum positive or improving? (2) organic growth above about 5%? (3) room for margins to
  expand? (4) high-return places to put capital? (5) competition stable? (6) self-funding, FCF-positive? (7) cheap in
  absolute terms? (8) cheap against peers? (9) a crowded long? (no is the good answer) (10) management you trust?
  (11) capital deployed logically? (12) a catalyst near enough to reprice it? (13) room for sentiment to improve?
  (14) next estimate revision more likely up? (15) a good set-up into the next quarter? For a short, read each from
  the short side;
- bull vs bear, side by side, and which side we are on;
- management and capital deployment (track record, pay alignment, accounting, buybacks and M&A);
- Likes / Dislikes, two columns;
- the pre-mortem: if this loses money, the most likely reason, written now (§14.5);
- PM challenges: in the first draft, before the PM has run, the challenges you expect yourself (your own attack on
  the pitch); after the PM review, replace them with every PM challenge left standing after your response (section
  11 and the assignment).

**Short pitch** (call `Short`): the same order from the short side. Slide 4 is three reasons the stock goes down
(fundamentals, expectations, valuation; §12). Slide 5's risks are the squeeze cases (the reward case for the bulls,
a takeout). Slide 9 adds the short type, crowding (short interest, days to cover), borrow cost, the VaR-based maximum
size and takeout risk, all from the Short Check tab.

**Hold variant** (call `Watch`, chapter 14's "not quite yet", §14.1, §14.5): slide 1 says WATCH; slide 9's `lead`
line gives the buy price, the no-brainer price and today's 3-year IRR (at those two prices the IRR is the hurdle by
construction, so there is nothing more to show there); slide 10 says what would change the call (a price, a print,
a driver reading). The thesis and risks are still there: the work is done, only the price is wrong.

## 4. Thesis points (§14.3, §3.7)
- **Exactly three.** Fewer looks underpowered; more spreads the listener's attention. They should be related but distinct, and together
  they should make the most important thing believable.
- A strong default mix: one **structural** point (the long-run runway, the secular driver, the business quality
  that keeps compounding); one **set-up** point (why the recent move or the current fear is wrong, or right for a
  short); one **estimates** point (why the numbers are too low or too high, by how much, and when the market sees it).
- **Valuation is a thesis point only if it is essential** to the case (a trough multiple on trough earnings, a
  segment the market is valuing at nothing). "It used to trade at a higher multiple" is never a thesis point; an
  expensive stock can still be a great long on fundamentals and estimates, and then valuation goes in the risks.
- Each point: a head line (one sentence, the claim) and a body that carries the proof: the number, where it comes
  from, and how it differs from what the market assumes. Every point has its own support slide.
- Match the house taste when you know it: a revisions-focused PM wants "why it beats"; a quality-focused PM wants
  "why it compounds". The user's notes may say which.

## 5. Risks (§14.1, §14.3, §14.4)
- **Exactly two key risks**, each with: a probability (`prob`, a fraction between 0 and 1: your own judgment, informed
  by the probability tree; it is typed as a plain number, needs no anchor, and the slide labels it "our estimate"),
  what happens if it hits (`if_hits`: the price or return in that case, anchored), and the mitigant with evidence
  (`mitigant`: why it is unlikely, why it is priced, or how the position is hedged).
- **Name the objection first.** The listener already has the obvious worry in their head ("it's expensive", "the new
  competitor"). Raising it yourself, then walking through why it is handled, buys more credibility than any other
  move in the pitch. If valuation is the obvious objection, it is usually risk 1.
- **Don't hide the ball.** Give the bear case real air time; claim there is no risk and the PM will find one and
  stop trusting the rest. Objective, not dogmatic, while still selling.
- **Tripwires** (`tripwires`): the specific readings that would tell you the thesis is breaking (a driver below a
  level, a margin miss of a size, a competitor event). They become the trading plan: when one trips, sell first and
  ask questions later (§14.5, thesis creep).
- **The risk checklist** (§14.1), run with a short-seller's hat on, as a last check rather than an essay. Answer each
  area in a line on the appendix slide:
  1. *Business model*: would customers miss it; pricing power and unit economics; could an entrant break them;
     high-return places to reinvest?
  2. *Revenue*: is volume steady and forecastable; is demand at a cyclical high the Street is extrapolating; are
     acquisitions hiding organic weakness?
  3. *Margins*: at a historical peak; above peers (over-earning); any volatile cost lines?
  4. *Balance sheet*: self-funding or reliant on outside money; debt comfortable; a refinancing ahead?
  5. *Capital deployment*: real distributable free cash flow; any value-destroying deals; buybacks at sensible
     prices?
  6. *Management*: operating and value-creation record; pay aligned with holders; conservative accounting?
  7. *Equity market*: multiple at a peak; crowded long; likely to miss or beat; what would take it down 25%, and
     50%, and how likely is each?

## 6. Where we're different (§14.2, §3.7, §10)
- **Variance on the key drivers, not just on EPS.** Show our number and the Street's for each key driver and for
  revenue, margin and EPS, on the Street's own basis (GAAP or non-GAAP as the Street reports it; margins in bps), for
  two or three years. SUM holds this table with the Expected Delta; Consensus holds the broker range. Explain what
  drives the high and low ends of the Street range and where we sit.
- **What the price implies vs what we think.** The reverse DCF (DCF tab, Valuation's DCF scenarios) says what each
  driver must do to justify today's price. Put that next to our forecast. The gap between what is baked in and what
  we believe is the opportunity.
- **The bull / bear tension.** State both sides fairly (the street report's debates), then say which side we take
  and the evidence that settles it for us: a driver calculation, a disclosure the Street underweights, a verbatim
  quote, the user's own primary research (cited `user note`).
- A big delta needs backup later in the deck (variance table, model snippets, the specific reason margins or growth
  differ). A delta with no research behind it is a guess, and the PM will say so.

## 7. Risk / reward and the hurdles (§14.1, §14.3, §3.7, §11)
- **The hurdles are the user's.** The Valuation tab holds them as user-owned inputs labelled "IRR hurdle", "Buy at
  R/R" and "Table-pound at R/R"; read them from the digest and use them everywhere below. Only if the tab lacks them,
  use the house defaults (common.HURDLES): **2:1 R/R to buy**, **3:1 R/R to pound the table**, a **20% 3-year IRR**
  and a 30% IRR for the no-brainer price. Say in `notes` which you used. The figures below are the defaults.
- **Twelve months:** base reward and risk-case loss from the Valuation tab; R/R = base return ÷ |risk return|.
  A portfolio of 2:1 bets wins even if only half of them work; a 60/40 coin with a 2:1 payoff is the job.
- **Three years:** IRR = (3-year target ÷ price)^(1/3) − 1. With the market making roughly 10% a year, a 3-year
  IRR in the low teens is little alpha even if the upside looks large in percent.
- **Buy price and no-brainer price**, both from the 3-year target:
  - buy price = 3-year target ÷ (1 + IRR hurdle)^3, the price at which the 3-year IRR equals the hurdle (with the
    20% default, ÷ 1.2^3);
  - no-brainer price = 3-year target ÷ (1 + no-brainer IRR)^3 (with the 30% default, ÷ 1.3^3). If the Valuation
    tab's R/R ladder shows the 12-month R/R passing the pound R/R (default 3:1) at a clearly different price,
    mention it in the notes and say which you used.
  Both go in `numbers` with `calc:` anchors over `target_3y` (and in `sum_boxes`).
- **Never stretch the estimates or the multiple until the hurdle clears** (§14.1). If it doesn't clear at today's
  price, the honest call is Watch with a buy price and a price alert; that is a good outcome, not a failure.
- **When to pound the table** (§14.4): only when you are highly confident *and* the set-up is highly asymmetric
  (3:1 or better, and hard to see a disaster). Pound on everything and you lose credibility; never pound and you never
  get capital. On a less clear-cut idea, say so plainly, and keep your credibility for the day you need it. The
  `action` field carries the size of the conviction: e.g. "Small buy", "Buy", "Pound the table", "Short", "Wait for
  {buy_price}".
- **The checks the PM will run** (section 12 and pm_brief.md): is the risk case at least as likely as the reward case
  you show; is the downside more than a one-sigma move (the Valuation tab's one-sigma check); is the IRR quoted at
  today's price, not at a hoped-for entry?

## 8. Alpha buckets, idea patterns and the stock-picker phrases (§3.3, §5.4, §14.4, §12.3)
Name the bucket on slide 6: it tells the PM which pattern this is and why the mispricing should close.

**Long buckets (nine):** off the menu back onto it (a disliked stock with a visible path back into favour); a
compounder; a mispriced catalyst; extrapolation meets an inflection (the market extends a trend that is about to
turn); complexity becoming simple (a spin, a clean-up, a messy story getting easy to own); a change agent (new
management, an activist); growth accelerating; capital deployment and cash abundance; early insight into an
innovation.

**Short buckets (nine):** an earnings catalyst (a miss, a guide-down, the market changing its mind); a temporary
tailwind about to fade; a melting ice cube; an emerging overhang (on the menu to off it); a mispriced catalyst;
extrapolation meets an inflection; simplicity becoming complex (often a big messy deal); growth decelerating; a
short liquidity runway. For a short, use model-short's own bucket and type words as the Short Check tab shows them.

**Idea patterns** (§5.4), in our words. Long-leaning: a bet that a secular winner keeps growing longer than priced;
incremental margins well above today's margin; new management with a margin plan; organic growth about to speed
up; a likely target in a consolidating industry; an over-reaction to a small problem; holding through a temporary
weak patch. Short-leaning: steady pricing pressure; bolt-on deals filling a leaking organic bucket; earnings that never
turn into cash; a technology threat; a new competitor in a slow market; a crowded long at risk of a miss; a stock with
a history of sharp drops in a calm spell now. Either way: recent or broken IPOs; spins and divestitures;
post-bankruptcy names; regulatory change; a product launch the market may be over- or under-hoping; thinly traded stocks;
a recent large acquisition.

**The stock-picker phrases** (§14.4). Each is a frame for a whole pitch; use one only if the work supports it:
- "Seen this story before": a prior case with the same pattern, and where we are in it.
- "Multiple ways to win": several separate sources of upside the price ignores, so the pitch works even if only a
  couple of them come through.
- "Paid to wait": a catalyst further out than an impatient market will hold for, a strong IRR to it, and some
  return (growth, buybacks, yield) in the meantime.
- "Cheap on the out year": expensive on this year's earnings, cheap on earnings three to five years out.
- "Getting a segment for free": one part of the business alone justifies the price.
- "The market is mistaking cyclical for secular" (or the reverse).
- "Asymmetric": lose little if wrong, make a lot if right; show the ladder.
- "What's baked in, and why it's wrong": the reverse DCF next to ours.

## 9. The call rule (spec §2, §4)
- **Start from the earlier verdicts.** Copy them into `starting_verdicts`, from the digest:
  - Valuation: the row labelled "Overall verdict (the agent's call: Buy / Hold / Sell)". The tab has a verdict per
    multiple too; use only this overall one. If it is empty (the valuation plan had none), treat it as Hold, write
    `Hold`, and say so in `notes`.
  - Short: the Short Check row "Verdict (agent's call)", which the user owns; if it is empty, the row "Verdict (the
    rule)" (B5). Copy it as the tab shows it (e.g. "Alpha short", "Filler short", "Watchlist", "No short");
    comparisons ignore case. No Short Check tab: `null`, and a Short call is impossible.
- **The default mapping:** Buy → `Long`, Sell → `Short`, Hold → `Watch`.
- **You may override**, but only with cited evidence you found that the earlier agent did not weigh (a newer print, a
  quote, a driver calculation, the user's notes). Set `override` to `{"reason": "...", "evidence": "..."}` (evidence
  cites `file:line` or `Tab!Cell`), say it on slide 1's notes and slide 9, and list it in `notes`. No override
  without evidence; "I feel differently" is not evidence.
- **Watch** (from a Hold, or from a Buy that misses the hurdles, or from a PM kill you cannot answer): a full pitch
  with the buy price and no-brainer price; the PM should leave knowing exactly what price or event turns it into a
  Long. Any call other than the mapped one needs `override`, a step down to Watch included (the evidence is then the
  IRR and R/R cells, or the PM challenge you could not answer).
- **Short only when model-short says alpha short.** A Sell from Valuation with any other short verdict (filler
  short, watchlist, no short) becomes `Watch`, not a short pitch; because Watch differs from the Sell → Short mapping,
  set `override` with the Short Check verdict cell as the evidence. A short pitch with no Short Check tab is not
  allowed.
- **A Long must clear a hurdle:** if `irr_3y` is below the IRR hurdle (default 20%) *and* the 12-month R/R
  (`base_ret` ÷ |`risk_ret`|) is below the buy R/R (default 2:1), the call is `Watch`, or `override` explains why it
  is still a Long (e.g. a near catalyst the hurdle misses). An `action` of "Pound the table" needs the pound R/R.
- **Make the call yourself.** Equivocating ("could be long, could be short") is one of the named mistakes. Say what
  you think and how confident you are, then let `action` carry the size.

## 10. Style (§14.4, spec §7)
- **A takeaway line under every title**: the one sentence the slide proves, as a claim ("Street EPS is too low by
  {eps_gap_27} in 2027"), not a topic ("Estimates").
- **A source line at the foot** of every slide (`source`): the tab, report section or document it came from.
- **Tables of ours vs the Street** wherever the point is a difference; label the basis (GAAP / non-GAAP).
- **Quotes as evidence**: verbatim words from the company (calls, decks, filings) or the sell side, short, each
  cited by `file` and `line` in `quotes`. Pick quotes that prove a point, not ones that decorate it. A quote from the
  company admitting a problem, or a sell-side line stating the bear case you are about to rebut, is worth more than
  praise.
- **Likes / Dislikes** in two columns in the appendix: honest dislikes make the likes believable.
- **One visual per idea.** A chart that makes the point fast beats six sentences: the margin path, the P/E against
  its range, the R/R ladder. Pick the single most compelling exhibit for each point; don't build five that say the
  same thing.
- **Speaker notes in the user's voice** (`notes`, up to 1,500 characters): what to say in two or three sentences,
  then "Likely question: ..." and "Answer: ...". Notes are what the user rehearses from; they must make sense read
  aloud.
- **Text budgets** (common.BUDGET, characters): title 70; takeaway 160; bullet 170 (each thesis head, risk head,
  `if_hits`, `mitigant`, tripwire, napkin bullet); row 90 (checklist question); box 420 (each thesis body, `pitch_20s` and
  each SUM text box); note 1,500 (speaker notes); quote 400; cell 24 (table cells, checklist answers).
  `plan_schema.md` lists which field takes which budget. Short beats long: a slide a PM can read in ten seconds.
- **Numbers only through `{key}`** placeholders (plan_schema.md). Never type a number into text.
- **The pitch sheet** (`pitch_sheet`): `script_3min` is twelve short paragraphs following the 3-to-5-minute script
  (§3.7): company and position; the 20-second summary; background and set-up; thesis points 1, 2, 3; risks 1 and 2;
  valuation and the 3-year algorithm; estimates vs the Street; upside, downside and R/R; the catalyst path.
  `napkin` is three to five bullets you could write on a napkin (§14.4). `hard_questions` are the three to five
  hardest questions with your answers: in the first draft, the ones you expect; after the PM review, the hardest
  challenges left standing. `know_cold` lists the number keys you must recite without
  notes (at least price, base return, risk return, 3-year IRR, our vs Street EPS, buy price).
- Plain English throughout. No jargon the PM has to decode; define any metric the company invented.

## 11. Reading order and the plate file (§14.2, spec §6)
**Read in this order** (the assignment's reading list follows it, keeping only files that exist): this brief and
`plan_schema.md`; the user's notes; the filings research report (the standard version; the long version only for a
section you need); the street research report; the earlier agents' reasoning (the filings `drivers.md` and its PM
review with the response; the street `synthesis.md`, PM review and `new_views.md`; the forecast write-up;
`valuation_plan.json`, `short_plan.json`, `earnings_plan.json`, the after-print plan); the valuation, short, preview
and after-print notes; the model digest; the tab pictures. Open any source document when you want to check or quote
it, and cite `file:line`.

**The plate file** (`plate.md`, in the work folder) is your running notebook, written while you read, not after.
Thesis writing is then mostly lifting the summaries out of it and cutting them down further. Its shape:

```
# <TICKER> plate (as of <date>)

## Current conclusions            (rewrite after every source)
- Call: ... (starting verdicts: Valuation ..., Short Check ...; override? why)
- The most important thing: ...
- Thesis: 1 ... 2 ... 3 ...
- Risks: 1 ... (prob, cost, mitigant) 2 ...
- Where we differ from the Street, and why: ...
- Path to getting paid: ...
- Buy price ... no-brainer price ... (from the 3-year target)

## Business
## Set-up
## Key drivers
## Bull vs bear
## Estimates vs Street
## Valuation
## Pre-mortem
## Catalysts
## Management and capital deployment
## Disagreements with earlier verdicts
## Open questions

## Change log                       (dated, newest last)
```

Every bullet under a topic ends with its citation (`file:line`, `Tab!Cell`, or `user note`). On a rerun, read the old
plate first, then only what is newer than its date; add a dated entry to the change log saying what moved, whether the
trading plan's tripwires were hit, and a thesis-creep check: is the thesis still the one you pitched, or has it drifted
one small excuse at a time (§14.5)?

## 12. Common mistakes (§14.4, §14.1)
- **Missing the basics**: the listener should never have to ask the company, the recommendation, what the market
  thinks, what you think, or when the market comes round.
- **No hook**: "great company, great product" describes a business, not a mispriced stock. Say why it is mispriced.
- **Book report**: everything you learned instead of the core debate.
- **Leading with valuation**: valuation supports a thesis; as the first point it signals there is nothing else.
- **"Good business" as the thesis** (or "bad business" for a short).
- **"Time will bail us out"**: holding with no path to getting paid.
- **Too one-sided**: no risks, or risks with no probability. **Too equivocal**: no call.
- **Unclear payoff**: the target's derivation is missing; the PM should not have to do the math. Finish with "right =
  +x%, wrong = −y%".
- **Saving the conclusion for the end**: the call and the most important thing go first.
- **Packing slides**: more facts feel safer and lose the story. Distill.
- **Stretching numbers to clear the hurdle** instead of calling Watch with a buy price.
- **Making things up**: if the documents don't answer a question, write that it is open (plate `Open questions`) and
  put it in the appendix as a follow-up; never invent a number or a quote.
- **Pitching around a weak earlier verdict without saying so**: an override is fine; a silent one is the worst
  outcome. Every judgment call goes in `notes`.
