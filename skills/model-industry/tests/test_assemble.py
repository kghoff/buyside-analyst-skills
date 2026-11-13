import json
import os

import pytest

from conftest import FIX, REFERENCE
import assemble


def peers(tmp_path):
    return {"subject": "DXCM", "industry": "CGM",
            "companies": [{"ticker": "DXCM", "name": "DexCom", "source": "mod"},
                          {"ticker": "ABT", "name": "Abbott", "source": "xbrl", "segment": "Diabetes Care"}],
            "excluded": [{"name": "Roche", "why": "not an SEC filer"}]}


def test_subject_links_to_mod_and_segment_peer_estimates_from_parent(tmp_path):
    W = tmp_path
    (W / "sec").mkdir()
    json.dump({"fiscalYearEnd": "1231", "filings": []}, open(W / "sec" / "DXCM.json", "w"))
    json.dump({"fiscalYearEnd": "1231", "filings": []}, open(W / "sec" / "ABT.json", "w"))
    json.dump({"DXCM": {"sec": str(W / "sec" / "DXCM.json"), "xbrl": None, "tenk_md": []},
               "ABT": {"sec": str(W / "sec" / "ABT.json"), "xbrl": os.path.join(FIX, "abt_xbrl.json"),
                       "tenk_md": []}}, open(W / "fetch.json", "w"))
    json.dump({"ABT": {"revenue": {"2025": {"value": 7624.0, "file": "f.md", "line_no": 7, "raw": "7,624",
                                            "quote": "| Diabetes Care | 7,624 |", "note": ""}}}},
              open(W / "segments.json", "w"))
    I = assemble.assemble(peers(W), REFERENCE, str(W))
    assert I["years"][-1] == 2025 and len(I["years"]) == 10
    d = I["companies"][0]
    assert d["lines"]["revenue"]["2025"]["kind"] == "link" and d["lines"]["revenue"]["2025"]["v"] == 4662
    a = I["companies"][1]
    assert a["lines"]["revenue"]["2025"] == {"v": 7624.0, "kind": "typed",
                                             "note": "ABT 10-K segment note: f.md line 7: '| Diabetes Care | 7,624 |'"}
    inv = a["lines"]["inventory"]["2025"]
    share = 7624.0 / 44328.0
    assert inv["kind"] == "est" and abs(inv["v"] - a["parent"]["inventory"]["2025"]["v"] * share) < 1e-9
    assert "2024" not in a["lines"]["inventory"]          # no segment revenue that year -> no estimate
    assert any("Abbott" in w or "ABT" in w for w in I["warnings"]) is False


def workspace(W, xbrl, sec=None, peer=None):
    """A subject (DXCM, the reference MOD) plus one whole-company XBRL peer "PEER" built from `xbrl`."""
    (W / "sec").mkdir(exist_ok=True)
    json.dump({"fiscalYearEnd": "1231", "filings": []}, open(W / "sec" / "DXCM.json", "w"))
    json.dump(sec or {"fiscalYearEnd": "1231", "filings": []}, open(W / "sec" / "PEER.json", "w"))
    json.dump(xbrl, open(W / "peer_xbrl.json", "w"))
    json.dump({"DXCM": {"sec": str(W / "sec" / "DXCM.json"), "xbrl": None, "tenk_md": []},
               "PEER": {"sec": str(W / "sec" / "PEER.json"), "xbrl": str(W / "peer_xbrl.json"), "tenk_md": []}},
              open(W / "fetch.json", "w"))
    return {"subject": "DXCM", "industry": "CGM",
            "companies": [{"ticker": "DXCM", "name": "DexCom", "source": "mod"},
                          dict({"ticker": "PEER", "name": "Peer Co", "source": "xbrl"}, **(peer or {}))]}


def abt_without(year, field):
    d = json.load(open(os.path.join(FIX, "abt_xbrl.json")))
    del d["annual"]["cashFlow"][year][field]
    return d


def test_warns_when_a_core_line_is_missing_in_a_year_with_revenue(tmp_path):
    # A peer with revenue but no CFO that year would silently drop out of industry FCF; the user must be told.
    I = assemble.assemble(workspace(tmp_path, abt_without("2024", "net_cash_flow_from_operating_activities")),
                          REFERENCE, str(tmp_path))
    assert any(w.startswith("PEER:") and "2024 cfo" in w for w in I["warnings"])
    assert not any(w.startswith("DXCM:") for w in I["warnings"])


def test_sanity_warnings_and_override_fix_a_bad_xbrl_revenue(tmp_path):
    # The XBRL engine gave SENS 2022 revenue of $0.66M against ~$16M in the 10-K. A revenue that jumps more than
    # 3x, or a gross margin below -100%, is almost always that kind of mistake; the user fixes it with a sourced override.
    d = json.load(open(os.path.join(FIX, "abt_xbrl.json")))
    d["annual"]["income"]["2024"]["revenues"] = 1e9                  # $1,000M, really ~$42,000M
    I = assemble.assemble(workspace(tmp_path, d), REFERENCE, str(tmp_path))
    w = " | ".join(I["warnings"])
    assert "PEER FY2024: gross margin" in w and "PEER FY2025: revenue" in w and "check against the 10-K" in w
    assert "DXCM FY" not in w                                         # subject comes from the MOD: not checked
    fix = {"overrides": {"revenue": {"2024": {"v": 41950.0, "note": "ABT 2024 10-K income statement"}}}}
    I = assemble.assemble(workspace(tmp_path, d, peer=fix), REFERENCE, str(tmp_path))
    assert not any(w.startswith("PEER FY") for w in I["warnings"])
    assert I["companies"][1]["lines"]["revenue"]["2024"] == {
        "v": 41950.0, "kind": "typed", "note": "Override: ABT 2024 10-K income statement"}


def test_subject_must_come_first(tmp_path):
    # The subject's MOD years set the 10-year window that every peer is cut to; a peer first would break that.
    P = workspace(tmp_path, json.load(open(os.path.join(FIX, "abt_xbrl.json"))))
    P["companies"].reverse()
    with pytest.raises(SystemExit) as e:
        assemble.assemble(P, REFERENCE, str(tmp_path))
    assert "first company must be the subject DXCM" in str(e.value)
    P["companies"].reverse()
    P["subject"] = "ABT"                                   # subject named but MOD company is another ticker
    with pytest.raises(SystemExit):
        assemble.assemble(P, REFERENCE, str(tmp_path))


def test_warns_when_two_fiscal_years_land_in_one_calendar_year(tmp_path):
    # A company that moves its year end can have two fiscal years counting as the same calendar year; only one
    # survives, so the user must hear which one.
    sec = {"fiscalYearEnd": "1231", "filings": [{"fy": 2023, "reportDate": "2023-06-30"},
                                                {"fy": 2024, "reportDate": "2024-01-05"}]}
    I = assemble.assemble(workspace(tmp_path, json.load(open(os.path.join(FIX, "abt_xbrl.json"))), sec=sec),
                          REFERENCE, str(tmp_path))
    assert any("PEER: FY2023" in w and "FY2024" in w and "both count as 2023" in w and "FY2024 is used" in w
               for w in I["warnings"])
    assert I["companies"][1]["lines"]["revenue"]["2023"]["v"] == 41950.0          # FY2024's revenue
