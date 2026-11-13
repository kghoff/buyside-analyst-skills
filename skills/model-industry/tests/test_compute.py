import json
import os

from conftest import FIX
import compute

I = json.load(open(os.path.join(FIX, "industry_small.json")))


def test_industry_growth_counts_only_companies_present_both_years():
    # BBB enters in 2024: industry revenue jumps 100 -> 420, but that is a bigger peer set, not growth
    S = compute.run(I)
    assert S["ind"]["revenue"][2024] == 420
    assert abs(S["ind_an"]["growth"][2024] - 0.20) < 1e-12          # only AAA both years: 120/100 - 1
    assert abs(S["ind_an"]["growth"][2025] - 31 / 420) < 1e-12


def test_share_of_new_dollars_gaps_when_industry_barely_grows():
    S = compute.run(I)
    assert S["ind_an"]["new_dollars"][2024] == 1.0                   # AAA is the only both-year company
    assert abs(S["ind_an"]["new_dollars"][2025] - 30 / 31) < 1e-12   # 31 / 420 = 7.4% > 1%
    I2 = json.loads(json.dumps(I))
    I2["companies"][0]["lines"]["revenue"]["2025"]["v"] = 121        # industry +2 on 420 = 0.5% -> gap
    assert compute.run(I2)["ind_an"]["new_dollars"][2025] is None


def test_calc_lines_and_roic():
    S = compute.run(I)
    a = S["co"]["AAA"]
    assert a["lines"]["gross_profit"][2025] == 90
    assert a["lines"]["fcf"][2025] is None                           # no CFO: FCF missing, not -15
    assert a["an"]["tax_rate"][2025] == 0.2
    assert a["an"]["ic"][2024] == 120 and a["an"]["ic"][2025] == 140
    assert abs(a["an"]["roic"][2025] - 24 / 130) < 1e-12            # NOPAT 30 x 0.8 / avg IC 130
    assert a["an"]["ic"][2023] == 0                                  # revenue but no balance sheet lines -> 0
    assert a["an"]["roic"][2023] is None                            # first year: no prior IC
    assert abs(a["an"]["share"][2025] - 150 / 451) < 1e-12
    assert S["ind_an"]["count"][2023] == 1
