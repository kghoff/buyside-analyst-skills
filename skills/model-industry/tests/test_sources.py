from conftest import REFERENCE
import sources


def test_mod_read_finds_dxcm_rows_by_label():
    m = sources.mod_read(REFERENCE)
    assert 2015 in m["fy_cols"] and 2025 in m["fy_cols"] and 2026 not in m["fy_cols"]   # estimates excluded
    v = m["values"]
    assert v["revenue"][2025] == 4662
    assert v["cogs"][2025] == -1860.1
    assert abs(v["cash"][2025] - (917.7 + 1081)) < 1e-9          # cash + short-term securities summed
    assert v["pretax"][2025] == 1088.4                           # DXCM has no pre-tax row: EBIT fallback
    assert v["capex"][2025] == -363.5
    assert v["buybacks"][2025] == -471.9
    assert v["dividends"] == {}                                  # DXCM pays none: no row, not zeros
    col = m["fy_cols"][2025]
    assert m["formula"]["cash"][2025] == f"MOD!{col}228+MOD!{col}229"


def test_mod_read_uses_first_match_so_leverage_section_rows_are_ignored():
    # "Net Income" also labels a leverage-section helper row lower down; the income statement row must win
    m = sources.mod_read(REFERENCE)
    assert m["rows"]["net_income"] == [147]


def test_missing_cache_counts_uncached_formulas_on_every_line(tmp_path):
    # The OI / Net Income / Total Assets / CFO FY cells are formulas. A copy openpyxl saved has no cached
    # results, so without a recalc those lines would go None silently even though revenue (typed) is present.
    import openpyxl
    assert sources.mod_read(REFERENCE)["missing_cache"] == 0
    p = tmp_path / "resaved.xlsx"
    openpyxl.load_workbook(REFERENCE).save(p)
    m = sources.mod_read(str(p))
    assert m["missing_cache"] > 0
