"""3-month ADV uses what the model already has before fetching anything: the Multiples comp sheet first, then Px
Data's own source file, then Yahoo, then a CSV placed in the work folder by hand. Every fallback must be as fresh as
Px Data (the same day as SUM's price), and when all fail the build stops and says where to put a file."""
import os

import pytest

import adv

LAST = "2026-11-14"          # the fixture's last Px Data date


def _csv(path, last_day=14, n=70, vol=lambda k: 1_000_000 + k * 1000):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    rows = ["Date,Open,High,Low,Close,Volume"]
    for k in range(n):
        d = f"2026-{8 + (k // 31):02d}-{(k % 28) + 1:02d}" if k < n - 1 else f"2026-11-{last_day:02d}"
        rows.append(f"{d},1,1,1,50,{vol(k)}")
    open(path, "w").write("\n".join(rows) + "\n")


def boom(work, ticker):
    raise AssertionError("must not fetch")


def test_multiples_link_first(fixture_model, tmp_path):
    r = adv.adv(fixture_model, "Multiples!$H$39", str(tmp_path), "TEST", str(tmp_path), fetch=boom)
    assert r["route"] == "multiples" and r["ref"] == "Multiples!$H$39"


def test_fresh_price_data_csv_no_fetch(fixture_model, tmp_path):
    _csv(str(tmp_path / "TEST" / "Price Data" / "test_us_d.csv"))
    r = adv.adv(fixture_model, None, str(tmp_path), "TEST", str(tmp_path / "w"), fetch=boom)
    want = sum(1_000_000 + k * 1000 for k in range(70 - 63, 70)) / 63 / 1e6     # last 63 days, in millions
    assert r["route"] == "price_data" and abs(r["value"] - want) < 1e-9 and LAST in r["note"]


def test_stale_csv_goes_to_yahoo(fixture_model, tmp_path):
    _csv(str(tmp_path / "TEST" / "Price Data" / "test_us_d.csv"), last_day=7)
    work = str(tmp_path / "w")
    os.makedirs(work)
    r = adv.adv(fixture_model, None, str(tmp_path), "TEST", work,
                fetch=lambda w, t: (_csv(os.path.join(w, "test_us_d.csv")), True)[1])
    assert r["route"] == "yahoo"


def test_yahoo_fails_hand_csv_used(fixture_model, tmp_path):
    work = str(tmp_path / "w")
    _csv(os.path.join(work, "test_us_d.csv"))
    r = adv.adv(fixture_model, None, str(tmp_path), "TEST", work, fetch=lambda w, t: False)
    assert r["route"] == "work_csv"


def test_everything_fails_stops_and_names_the_file(fixture_model, tmp_path):
    work = str(tmp_path / "w")
    os.makedirs(work)
    with pytest.raises(SystemExit, match="test_us_d.csv"):
        adv.adv(fixture_model, None, str(tmp_path), "TEST", work, fetch=lambda w, t: False)


def test_yahoo_missing_node_is_a_failed_route_not_a_crash(monkeypatch, tmp_path):
    def nope(*a, **k):
        raise FileNotFoundError("node")
    monkeypatch.setattr(adv.subprocess, "run", nope)
    assert adv.yahoo(str(tmp_path), "TEST") is False


def test_hand_csv_is_never_overwritten_by_the_download(fixture_model, tmp_path):
    work = str(tmp_path / "w")
    _csv(os.path.join(work, "test_us_d.csv"), vol=lambda k: 5_000_000)
    r = adv.adv(fixture_model, None, str(tmp_path), "TEST", work,
                fetch=lambda w, t: (_csv(os.path.join(w, "test_us_d.csv"), last_day=7), True)[1])
    assert r["route"] == "work_csv" and abs(r["value"] - 5.0) < 1e-9
    assert open(os.path.join(work, "test_us_d.csv")).read().count("5000000") == 70


def test_zero_or_garbage_volume_rows_are_not_counted(tmp_path):
    p = str(tmp_path / "x.csv")
    _csv(p, n=70)
    with open(p, "a") as f:
        f.write("2026-11-15,1,1,1,50,abc\n2026-11-16,1,1,1,50,0.0\n2026-11-17,1,1,1,50,-5\n")
    assert adv.from_csv(p)["last"] == "2026-11-14"


def test_failure_message_says_why_each_file_failed(fixture_model, tmp_path):
    _csv(str(tmp_path / "TEST" / "Price Data" / "test_us_d.csv"), n=30)
    work = str(tmp_path / "w")
    with pytest.raises(SystemExit, match="63"):
        adv.adv(fixture_model, None, str(tmp_path), "TEST", work, fetch=lambda w, t: False)
