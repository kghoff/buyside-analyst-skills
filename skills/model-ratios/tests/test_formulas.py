from formulas import growth, margin, pct_sales, bps, incremental, ttm, mod_link, for_estimate

P, J, M, L_, K = 16, 10, 13, 12, 11   # column numbers of P, J, M, L, K


def test_macro_formulas_match_the_dxcm_example_cells():
    assert growth(4, P, J) == '=IFERROR(P4/J4-1,"n.a.")'                       # DXCM P5
    assert margin(12, P, 4) == '=IFERROR(P12/P$4,"n.a.")'                      # DXCM P13
    assert bps(13, P, J) == '=IFERROR((P13-J13)*10000,"n.a.")'                 # DXCM P14
    assert incremental(12, P, J, 4) == '=IFERROR((P12-J12)/(P$4-J$4),"n.a.")'  # DXCM P16
    assert pct_sales(30, P, 4) == '=IFERROR(-P30/P$4,"n.a.")'                  # DXCM P31
    assert ttm(109, [P, M, L_, K]) == "=P109+M109+L109+K109"                   # DXCM P110


def test_links_to_mod():
    assert mod_link(4, P, est=False) == "=MOD!P4"
    assert mod_link(4, P, est=True) == '=IF(ISBLANK(MOD!P4),"",MOD!P4)'      # blank until a forecast is typed


def test_estimate_columns_stay_blank_instead_of_na():
    assert for_estimate('=IFERROR(P4/J4-1,"n.a.")') == '=IFERROR(P4/J4-1,"")'
    assert for_estimate("=P1/P2") == '=IFERROR(P1/P2,"")'
