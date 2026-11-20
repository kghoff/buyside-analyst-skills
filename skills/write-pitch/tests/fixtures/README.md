# Fixtures

`plan_example.json` is a valid pitch plan for the made-up ticker XYZ. Its anchors point at these cells, which the
fixture workbook (built in the anchors tests) must hold with exactly these values.

| Key | Anchor | Value |
|---|---|---|
| price | Valuation!C5 | 72.40 |
| target_3y | Valuation!C30 | 130 |
| base_ret | Valuation!F20 | 0.31 |
| risk_ret | Valuation!F21 | -0.15 |
| nobrainer_price | Valuation!C32 | 59.17 |
| bull_eps | Valuation!D12 | 4.10 |
| bull_pe | Valuation!D13 | 32 |
| bull_ret | Valuation!D14 | 0.81 |
| bull_p | Valuation!D15 | 0.25 |
| r_roll | Valuation!C40 | 0.06 |
| r_rev | Valuation!C41 | 0.08 |
| r_rer | Valuation!C42 | 0.04 |
| base_pe | Valuation!C13 | 28 |
| base_p | Valuation!C15 | 0.5 |
| bear_eps | Valuation!E12 | 2.60 |
| bear_pe | Valuation!E13 | 22 |
| bear_p | Valuation!E15 | 0.25 |
| eps_26_ours | SUM!H12 | 2.85 |
| eps_27_ours | SUM!J12 | 3.30 |
| eps_27_street | SUM!K12 | 3.05 |
| rev_26 | SUM!H8 | 1250 |
| rev_27 | SUM!J8 | 1420 |

The ten support slides and the checklist appendix slide carry no numbers, so they add no cells.

Calc anchors: `irr_3y` = `(target_3y/price)^(1/3)-1` (0.2154, shown 21.5%); `buy_price` = `target_3y/1.2^3` (75.23;
the fixture has no Valuation hurdle inputs, so plan.py uses the 20% default). `nobrainer_price` = 130 / 1.3^3 = 59.17.
The plan is a Long that clears both house hurdles (IRR 21.5% over 20%, R/R 2.1 over 2:1).

Research line: `Earnings Calls/_md/2026 Q3 XYZ call.md` line 214 must contain `15%` (the `guide_growth` number, shown
15%) and the quote q1 text, `We expect to grow 15% next year.`
