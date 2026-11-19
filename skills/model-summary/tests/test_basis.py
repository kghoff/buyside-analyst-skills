"""SUM shows our view against the Street's, apples to apples: the EPS we compare must be on the Street's own basis
(GAAP or non-GAAP), and that differs by company, so it is chosen by evidence (the candidate closest to the Street's
current-year EPS), never hardcoded. The user can force it with a yellow cell. Every Street metric the Consensus tab
carries gets its own Street and delta rows through one mapping table, so a new metric is picked up, or named."""
import hashlib
import os
import shutil

import openpyxl
import pytest

import build
import links
from conftest import no_fetch


def _copy(fixture_model, tmp_path, name="m.xlsx"):
    m = str(tmp_path / name)
    shutil.copy(fixture_model, m)
    return m, openpyxl.load_workbook(m)               # a test copy, never a user's model


def _basis(m, tmp_path, override="auto"):
    L = links.collect(m)
    return L, links.street_basis(L, m, str(tmp_path / "w"), override)


def _build(m, tmp_path, work="w", out="o.xlsx"):
    return build.build(m, str(tmp_path / work), "TEST", str(tmp_path / out), research_dir=str(tmp_path),
                       fetch=no_fetch)


def test_auto_picks_non_gaap_when_the_street_sits_there(built):
    """Street FY26 3.20 is 0.6% from our non-GAAP 3.18 and 15% from GAAP 2.78: comparing GAAP would show a fake
    15% 'miss' that is only an accounting difference."""
    sb = built[1]["street_basis"]
    assert sb["chosen"] == "non-GAAP" and sb["source"] == "auto"
    assert sb["evidence"] == ("Street FY26 EPS 3.20 (Consensus 2026-11-12); ours non-GAAP 3.18, GAAP 2.78, "
                              "so non-GAAP")
    ws = openpyxl.load_workbook(built[0])["SUM"]
    R = __import__("json").load(open(os.path.join(built[2], "layout.json")))["refs"]["rows"]
    assert ws[f"E{R['eps']}"].value == "EPS (non-GAAP, the Street's basis)"
    assert ws[f"J{R['eps']}"].value == "=MOD!$BF$14"                    # 2026E, the non-GAAP row
    assert not any("compares different bases" in w for w in built[1]["warnings"])   # the old warning is gone


def test_auto_picks_gaap_when_the_street_sits_there(fixture_model, tmp_path):
    """The same code must pick GAAP for a company whose analysts forecast GAAP: nothing is hardcoded."""
    m, wb = _copy(fixture_model, tmp_path)
    wb["Consensus"]["C7"] = 2.8
    wb.save(m)
    L, sb = _basis(m, tmp_path)
    assert sb["chosen"] == "GAAP" and sb["source"] == "auto" and sb["evidence"].endswith("so GAAP")
    assert L["mod"]["rows"]["eps"] == 8 and L["mod"]["rows"]["ebitda"] == [6, 10]   # GAAP EBITDA: OI + D&A


def test_adjusted_ebitda_follows_the_non_gaap_basis(built):
    """A non-GAAP Street compares adjusted EBITDA, so SUM's EBITDA (and its margin) must be MOD's adjusted row."""
    ws = openpyxl.load_workbook(built[0])["SUM"]
    R = __import__("json").load(open(os.path.join(built[2], "layout.json")))["refs"]["rows"]
    assert ws[f"E{R['ebitda']}"].value == "EBITDA (adjusted)"
    assert ws[f"J{R['ebitda']}"].value == "=MOD!$BF$15"


def test_override_gaap_forces_gaap_warns_and_survives_a_rerun(built, tmp_path):
    """The user owns the call: typing GAAP must force it (with a warning, since the evidence says otherwise) and a
    rerun must keep what they typed."""
    out1, _, work1 = built
    m = str(tmp_path / "TEST_model.xlsx")
    shutil.copy(out1, m)
    wb = openpyxl.load_workbook(m)
    lab = next(c for row in wb["SUM"].iter_rows() for c in row if c.value == "Street EPS basis")
    val = wb["SUM"].cell(lab.row, lab.column + 1)
    assert val.value == "auto" and val.fill.fgColor.rgb == "FFFFFF99"
    val.value = "GAAP"
    wb.save(m)
    work = str(tmp_path / "w")
    shutil.copytree(work1, work)
    os.replace(os.path.join(work, "inputs_written.next.json"), os.path.join(work, "inputs_written.json"))
    rep = build.build(m, work, "TEST", str(tmp_path / "o.xlsx"), research_dir=str(tmp_path), fetch=no_fetch)
    assert rep["street_basis"]["chosen"] == "GAAP" and rep["street_basis"]["source"] == "override"
    assert any("GAAP" in w and "auto would pick non-GAAP" in w for w in rep["warnings"])
    assert "Street EPS basis" in rep["users_kept"]
    s = openpyxl.load_workbook(str(tmp_path / "o.xlsx"))["SUM"]
    assert s.cell(lab.row, lab.column + 1).value == "GAAP"
    os.replace(os.path.join(work, "inputs_written.next.json"), os.path.join(work, "inputs_written.json"))
    shutil.copy(str(tmp_path / "o.xlsx"), m)
    rep2 = build.build(m, work, "TEST", str(tmp_path / "o2.xlsx"), research_dir=str(tmp_path), fetch=no_fetch)
    assert rep2["street_basis"]["chosen"] == "GAAP" and "Street EPS basis" in rep2["users_kept"]


def test_invalid_override_warns_and_uses_auto(fixture_model, tmp_path):
    """A typo must not silently pick a basis: it is named, and auto decides."""
    m = fixture_model
    w = []
    L = links.collect(m)
    sb = links.street_basis(L, m, str(tmp_path / "w"), "adjusted", w)
    assert sb["chosen"] == "non-GAAP" and sb["source"] == "auto"
    assert any("'adjusted'" in x and "auto" in x for x in w)


def test_override_non_gaap_without_the_row_warns_and_uses_auto(fixture_model, tmp_path):
    m, wb = _copy(fixture_model, tmp_path)
    wb["MOD"]["B14"] = "Something else"
    wb.save(m)
    w = []
    L = links.collect(m)
    sb = links.street_basis(L, m, str(tmp_path / "w"), "non-GAAP", w)
    assert sb["chosen"] == "GAAP" and sb["source"] == "auto"
    assert any("no 'Non-GAAP EPS, Diluted' row" in x for x in w)


def test_no_street_eps_falls_back_to_px_data(fixture_model, tmp_path):
    """With no Street EPS there is no evidence; Px Data's P/E basis (the user's choice in model-price-history) wins."""
    m, wb = _copy(fixture_model, tmp_path)
    del wb["Consensus"]
    wb["Multiples"]["B34"] = wb["Multiples"]["C34"] = None
    wb.save(m)
    L, sb = _basis(m, tmp_path)
    assert sb["chosen"] == "GAAP" and sb["source"] == "px_data" and "Px Data" in sb["evidence"]
    wb = openpyxl.load_workbook(m)
    wb["Px Data"]["C4"] = "P/E (non-GAAP EPS)"
    wb.save(m)
    L, sb = _basis(m, tmp_path)
    assert sb["chosen"] == "non-GAAP" and L["mod"]["rows"]["eps"] == 14
    wb["MOD"]["B14"] = "Something else"
    wb.save(m)
    with pytest.raises(SystemExit, match="model-kpis"):
        _basis(m, tmp_path)


def test_generic_street_margin_rows(built):
    """A margin the Street publishes is compared as a margin, in bps, on its own band, right under our margin."""
    import json
    ws = openpyxl.load_workbook(built[0])["SUM"]
    R = json.load(open(os.path.join(built[2], "layout.json")))["refs"]["rows"]
    s, d = R["s_ebitda_m"], R["d_ebitda_m"]
    assert R["margin"] < s == d - 1 and d < R["eps"]
    assert ws[f"E{s}"].value == "Street EBITDA margin"
    assert ws[f"E{d}"].value == "EBITDA margin delta (ours vs Street, bps)"
    assert ws[f"J{s}"].value == "=Consensus!$K$7" and ws[f"K{s}"].value == "n/a"
    assert ws[f"J{d}"].value == f"=IF(AND(ISNUMBER(J{s}),ISNUMBER(J{R['margin']})),(J{R['margin']}-J{s})*10000,NA())"
    assert "12 analysts" in ws[f"J{s}"].comment.text
    assert built[1]["street"]["metrics"]["ebitda_m"] == ["2026E"]


def test_margin_delta_has_its_own_band(built):
    """50 bps on a margin and 3% on EPS are different scales: a margin delta must not be coloured on the 3% band."""
    from test_cf import _rules
    import json
    R = json.load(open(os.path.join(built[2], "layout.json")))["refs"]
    d, mb = R["rows"]["d_ebitda_m"], R["margin_band"]
    ws = openpyxl.load_workbook(built[0])["SUM"]
    assert ws[mb].value == 50 and ws[mb].fill.fgColor.rgb == "FFFFFF99"
    rules = [f for sq, f in _rules(built[0]) if sq == f"F{d}:M{d}"]
    a = mb.replace("C", "$C$")
    assert rules == [f"AND(ISNUMBER(F{d}),F{d}&gt;{a})", f"AND(ISNUMBER(F{d}),F{d}&lt;-{a})"]


def test_unmapped_street_metric_is_named(fixture_model, tmp_path):
    """A metric model-consensus adds later must be visible, not silently dropped, until the mapping table has it."""
    m, wb = _copy(fixture_model, tmp_path)
    wb["Consensus"]["N4"], wb["Consensus"]["N7"] = "Foo mean", 1.0
    wb.save(m)
    rep = _build(m, tmp_path)
    assert any("'Foo mean'" in w for w in rep["warnings"]) and rep["street"]["unmapped"] == ["Foo mean"]


@pytest.mark.slow
def test_missing_cached_values_recalculate_a_copy(fixture_model, tmp_path):
    """MOD's forecast cells are formulas; a file saved without cached values must still be judged, by recalculating
    a COPY, and the user's file must be byte-identical afterwards."""
    m, wb = _copy(fixture_model, tmp_path)
    wb["MOD"]["BF14"] = "=BF8+0.4"                    # a formula with no cached value (openpyxl writes none)
    wb.save(m)
    before = hashlib.sha256(open(m, "rb").read()).hexdigest()
    L, sb = _basis(m, tmp_path)
    assert sb["chosen"] == "non-GAAP" and sb["values_from"] == "recalculated copy"
    assert "ours non-GAAP 3.18" in sb["evidence"]
    assert hashlib.sha256(open(m, "rb").read()).hexdigest() == before
    assert not os.path.exists(str(tmp_path / "w" / "basis_values"))   # no copy of the model kept
