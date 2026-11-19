"""SUM must never disagree with the model, so every link is found by its LABEL on the source tab, not by a fixed row.
A row that moves must move the link; a block that is gone must stop the build and name the skill to rerun."""
import shutil

import openpyxl
import pytest

import links


@pytest.fixture(scope="module")
def L(fixture_model):
    return links.collect(fixture_model)


def test_cap_table_ties_to_the_dcf_bridge(L):
    d = L["dcf"]
    assert (d["price"], d["date"], d["shares"], d["net_debt"]) == ("DCF!$C$18", "DCF!$D$18", "DCF!$C$16", "DCF!$C$14")
    assert (d["cash"], d["st"], d["debt_cur"], d["debt_lt"]) == ("DCF!$C$10", "DCF!$C$11", "DCF!$C$12", "DCF!$C$13")


def test_primary_multiple_block(L):
    v = L["val"]
    assert v["kind"] == "P/E" and v["action"] == "Valuation!$B$3"
    assert v["hurdle"] == "Valuation!$B$9" and v["buy_rr"] == "Valuation!$B$10"
    p = v["primary"]
    assert p["ntm1"]["ref"] == "Valuation!$B$36" and p["ntm1"]["label"] == "P/E: NTM+1 EPS (Q1 27E to Q4 27E)"
    assert p["reward_price"]["ref"] == "Valuation!$B$39" and p["risk_metric"]["label"] == "P/E: risk EPS"
    assert p["risk_price"]["ref"] == "Valuation!$B$42" and v["blended_rr"] == "Valuation!$B$71"
    i = v["irr"]
    assert i["irr"]["ref"] == "Valuation!$B$91" and i["price3"]["ref"] == "Valuation!$B$90"
    assert i["mult3"]["ref"] == "Valuation!$B$88" and i["years"]["ref"] == "Valuation!$B$86"


def test_ladder_and_tree(L):
    v = L["val"]
    assert len(v["ladder"]) == 7 and v["ladder"][0]["entry"] == "Valuation!$B$75"
    assert [b["name"] for b in v["tree"]] == ["Bull", "Base", "Risk", "Bear"]
    # only branches whose target IS the primary multiple's reward / risk price get EPS x multiple columns
    assert [b["case"] for b in v["tree"]] == [None, "reward", "risk", None]
    assert v["tree_ev"]["target"] == "Valuation!$B$121"


def test_multiples_ranges_street_and_adv(L):
    m = L["mult"]
    assert m["ranges"]["abs"]["today"] == "Multiples!$B$7"
    assert m["ranges"]["abs"]["5 years median"] == "Multiples!$H$7"
    assert m["ranges"]["sp"]["label"] == "GAAP P/E − S&P 500 P/E" and m["ranges"]["peer"]["today"] == "Multiples!$B$13"
    assert m["street"] == {"2026E": "Multiples!$B$34", "2027E": "Multiples!$C$34"}
    assert m["adv"] == "Multiples!$H$39"


def test_mod_years_and_ntm_fcf_are_internal(L):
    md = L["mod"]
    assert md["years"] == ["2022", "2023", "2024", "2025", "2026E", "2027E", "2028E", "2029E"]
    assert md["ntm_quarters"] == ["Q1 26E", "Q4 26E"]
    assert md["ntm_fcf"].startswith("IF(COUNT(") and md["ntm_fcf"].count("$12") == 8   # 4 quarters x (COUNT + sum)
    assert md["basis"] == "gaap" and md["rows"]["ebitda"] == [6, 10]                    # GAAP: operating income + D&A


def test_moved_row_moves_the_link(fixture_model, tmp_path):
    m = str(tmp_path / "moved.xlsx")
    shutil.copy(fixture_model, m)
    wb = openpyxl.load_workbook(m)
    wb["Valuation"].insert_rows(30)                 # everything from row 30 down moves one row
    wb.save(m)                                      # a test copy, never a user's model
    assert links.collect(m)["val"]["primary"]["reward_price"]["ref"] == "Valuation!$B$40"


def test_missing_block_names_the_skill(fixture_model, tmp_path):
    m = str(tmp_path / "gone.xlsx")
    shutil.copy(fixture_model, m)
    wb = openpyxl.load_workbook(m)
    wb["Valuation"]["A83"] = None
    wb.save(m)
    with pytest.raises(SystemExit, match="model-valuation"):
        links.collect(m)


def test_missing_tab_names_the_skill(fixture_model, tmp_path):
    m = str(tmp_path / "nodcf.xlsx")
    shutil.copy(fixture_model, m)
    wb = openpyxl.load_workbook(m)
    del wb["DCF"]
    wb.save(m)
    with pytest.raises(SystemExit, match="/model-dcf"):
        links.collect(m)


def _copy(fixture_model, tmp_path, name):
    m = str(tmp_path / name)
    shutil.copy(fixture_model, m)
    return m, openpyxl.load_workbook(m)


def test_blended_branch_has_no_case(fixture_model, tmp_path):
    """A real model's tree links blended prices and typed targets; those branches must get no metric x multiple."""
    m, wb = _copy(fixture_model, tmp_path, "blend.xlsx")
    ws = wb["Valuation"]
    ws["B118"] = "=$B$71"                               # Base now links a blended cell
    ws["A119"], ws["B119"] = "Stall", 48.0              # a typed target
    wb.save(m)
    tree = links.collect(m)["val"]["tree"]
    assert [b["name"] for b in tree] == ["Bull", "Base", "Stall", "Bear"]
    assert [b["case"] for b in tree] == [None, None, None, None]


def test_non_gaap_basis(fixture_model, tmp_path):
    m, wb = _copy(fixture_model, tmp_path, "ng.xlsx")
    wb["Px Data"]["C4"] = "P/E (non-GAAP EPS)"
    wb["MOD"]["A14"], wb["MOD"]["B14"] = "NON-GAAP METRICS", "Non-GAAP EPS, Diluted"
    wb.save(m)
    md = links.collect(m)["mod"]
    assert md["basis"] == "ng" and md["rows"]["eps"] == 14
    m2, wb2 = _copy(fixture_model, tmp_path, "ng_missing.xlsx")
    wb2["Px Data"]["C4"] = "P/E (non-GAAP EPS)"
    wb2.save(m2)
    with pytest.raises(SystemExit, match="model-kpis"):
        links.collect(m2)


def test_no_adv_on_comp_sheet(tmp_path):
    import make_fixture
    p = make_fixture.build(str(tmp_path / "noadv.xlsx"), multiples_adv=False)
    assert links.collect(p)["mult"]["adv"] is None


def test_blank_street_year_is_skipped(fixture_model, tmp_path):
    m, wb = _copy(fixture_model, tmp_path, "street.xlsx")
    wb["Multiples"]["C34"] = None
    wb.save(m)
    assert links.collect(m)["mult"]["street"] == {"2026E": "Multiples!$B$34"}


def test_grid_is_capped_at_five_forecast_years(fixture_model, monkeypatch):
    """The grid must stay inside F:N, clear of the scenario block at P: 4 actual + at most 5 forecast years."""
    from modmap import ModMap
    real = ModMap.forecast_years
    monkeypatch.setattr(ModMap, "forecast_years", lambda self: real(self) + ["2026E", "2027E"])
    yrs = links.collect(fixture_model)["mod"]["years"]
    assert len(yrs) == 9 and yrs[4:] == (real(ModMap(fixture_model)) + ["2026E"])[:5]


def test_dcf_period_and_position(fixture_model, tmp_path):
    L = links.collect(fixture_model)
    assert L["dcf"]["period"] == "Q4 25"
    assert L["val"]["position"] == {"ref": "Valuation!$B$14", "value": "long"}
