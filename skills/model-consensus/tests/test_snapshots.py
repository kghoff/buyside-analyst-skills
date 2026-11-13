# tests/test_snapshots.py
import json
import os

import pytest

import snapshots
from conftest import snap


def trend(period, end, eps, rev, n=10):
    return {"period": period, "endDate": end,
            "earningsEstimate": {"avg": eps, "low": eps - 0.1, "high": eps + 0.1, "numberOfAnalysts": n},
            "revenueEstimate": {"avg": rev * 1e6, "low": (rev - 10) * 1e6, "high": (rev + 10) * 1e6, "numberOfAnalysts": n + 1},
            "epsRevisions": {"upLast30days": 2, "downLast30days": 5}}


SNAP = {"asof": "2026-11-12", "ticker": "X",
        "yahoo": {"trend": [trend("0q", "2026-12-31", 0.7, 1384), trend("+1q", "2027-03-31", 0.6, 1300),
                            trend("0y", "2026-12-31", 2.7, 5228), trend("+1y", "2027-12-31", 3.1, 5775)],
                  "recommendation": [{"period": "0m", "strongBuy": 4, "buy": 22, "hold": 3, "sell": 0, "strongSell": 1}],
                  "financial": {"targetMeanPrice": 98.6, "targetHighPrice": 120, "targetLowPrice": 79, "numberOfAnalystOpinions": 26}},
        "nasdaq": {"forecast": {"quarterlyForecast": {"rows": [
            {"fiscalEnd": "Dec 2026", "consensusEPSForecast": 0.71, "highEPSForecast": 0.76, "lowEPSForecast": 0.67, "noOfEstimates": 10},
            {"fiscalEnd": "Jun 2027", "consensusEPSForecast": "$0.80", "highEPSForecast": 0.9, "lowEPSForecast": 0.7, "noOfEstimates": 5}]}}}}


def test_consensus_uses_the_model_periods_and_millions():
    c = snapshots.consensus(SNAP, 12)
    assert c["labels"] == {"q": "Q4 26", "fy": "FY 26", "fy1": "FY 27"}
    assert c["eps"]["fy1"] == pytest.approx({"mean": 3.1, "low": 3.0, "high": 3.2, "n": 10})
    assert c["rev"]["q"]["mean"] == 1384 and c["rev"]["q"]["n"] == 11
    assert c["pt"] == {"mean": 98.6, "high": 120, "low": 79, "n": 26}


def test_rows_add_nasdaq_only_for_periods_yahoo_lacks():
    rows = snapshots.rows(SNAP, 12)
    labels = [r["period"] for r in rows]
    assert labels == ["Q4 26", "Q1 27", "FY 26", "FY 27", "Q2 27"]
    nas = rows[-1]
    assert nas["source"].startswith("Nasdaq") and nas["eps_mean"] == 0.80 and nas["rev_mean"] is None
    assert rows[0]["buy"] == 26 and rows[0]["hold"] == 3 and rows[0]["sell"] == 1
    assert rows[0]["up30"] == 2 and rows[0]["down30"] == 5 and rows[0]["mean_pt"] == 98.6


def test_load_all_sorts_by_date_and_changes_compares_the_last_two(tmp_path):
    d = tmp_path / "snapshots"; d.mkdir()
    old = json.loads(json.dumps(SNAP)); old["asof"] = "2026-10-01"
    old["yahoo"]["trend"][3]["earningsEstimate"]["avg"] = 3.2
    old["yahoo"]["financial"]["targetMeanPrice"] = 95.0
    json.dump(SNAP, open(d / "2026-11-12.json", "w")); json.dump(old, open(d / "2026-10-01.json", "w"))
    allx = snapshots.load_all(str(tmp_path))
    assert [s["asof"] for s in allx] == ["2026-10-01", "2026-11-12"]
    ch = snapshots.changes(allx[-2], allx[-1], 12)
    assert any("FY 27 EPS" in x and "3.20" in x and "3.10" in x for x in ch)
    assert any("mean price target" in x for x in ch)


def test_real_snapshots_have_rows():
    for t in ("DXCM", "MDT"):
        assert snapshots.rows(snap(t), snapshots.periods.fye_month(snap(t)))


def test_duplicate_period_label_rows_are_skipped():
    s = snap("SENS")
    labels = [r["period"] for r in snapshots.rows(s, 12) if r["source"] == "Yahoo"]
    assert len(labels) == len(set(labels))
    assert snapshots.changes(s, s, 12) == []


def test_changes_survives_a_zero_previous_value():
    a = json.loads(json.dumps(SNAP)); b = json.loads(json.dumps(SNAP))
    a["yahoo"]["trend"][0]["earningsEstimate"]["avg"] = 0
    out = snapshots.changes(a, b, 12)
    assert any("0.00 → 0.70" in l and "%" not in l for l in out)


def test_num_reads_bracket_negatives():
    assert snapshots.num("($0.42)") == -0.42
    assert snapshots.num("(0.42)") == -0.42
