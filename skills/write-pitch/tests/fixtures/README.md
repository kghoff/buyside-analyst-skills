# Fixtures

`plan_example.json` is a valid pitch plan for the made-up ticker XYZ. Its anchors point at these cells, which the
fixture workbook (built in the anchors tests) must hold with exactly these values.

| Key | Anchor | Value |
|---|---|---|
| price | Valuation!C5 | 72.40 |
| target_3y | Valuation!C30 | 120 |
| base_ret | Valuation!F20 | 0.31 |
| risk_ret | Valuation!F21 | -0.15 |
| nobrainer_price | Valuation!C32 | 55.00 |
| bull_eps | Valuation!D12 | 4.10 |
| bull_pe | Valuation!D13 | 32 |
| bull_ret | Valuation!D14 | 0.81 |
| bull_p | Valuation!D15 | 0.25 |
| r_roll | Valuation!C40 | 0.06 |
| r_rev | Valuation!C41 | 0.08 |
| r_rer | Valuation!C42 | 0.04 |
| eps_27_ours | SUM!J12 | 3.30 |
| eps_27_street | SUM!K12 | 3.05 |
| rev_26 | SUM!H8 | 1250 |
| rev_27 | SUM!J8 | 1420 |

Calc anchors: `irr_3y` = `(target_3y/price)^(1/3)-1` (0.1834, shown 18.3%); `buy_price` = `target_3y/1.2^3` (69.44).

Research line: `Earnings Calls/_md/2026 Q3 XYZ call.md` line 214 must contain `15%` (the `guide_growth` number, shown
15%) and the quote q1 text, `We expect to grow 15% next year.`
