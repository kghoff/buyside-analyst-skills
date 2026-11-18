import datetime, os

from fixtures import make_model, make_src
from preflight import check


def research(tmp_path, ticker="TEST"):
    src = tmp_path / "Desktop" / "Research" / ticker
    src.mkdir(parents=True)
    make_src(str(src), [
        ("10-Q:2026-09-30", "10-Qs", f"{ticker} 2026 Q3 10-Q", "Text.", "found"),
        ("sell:2026-11-06:x", "Sellside Research", "2026-11-06 Firm note", "Buy!", "found"),
    ], ticker=ticker)
    return src


def test_everything_present_passes_and_as_of_ignores_newer_sell_side(tmp_path):
    # the as-of date is the newest COMPANY document; a later analyst note must not move it
    src = research(tmp_path)
    make_model(str(src / "TEST_model.xlsx"), px_rows=[(datetime.datetime(2024, 1, 2), 1.0, 2.0)])
    r = check("test", home=str(tmp_path))
    assert r["status"] == "ok" and r["src"] == str(src)
    assert r["as_of"] == "2026-09-30" and r["price"]["kind"] == "tab"


def test_missing_model_stops_and_names_the_model_skills(tmp_path):
    research(tmp_path)
    r = check("TEST", home=str(tmp_path))
    assert r["status"] == "stop"
    assert any(m["what"] == "model" and "/model-historicals" in m["fix"] for m in r["missing"])


def test_missing_price_points_to_model_price_history(tmp_path):
    src = research(tmp_path)
    make_model(str(src / "TEST_model.xlsx"))
    r = check("TEST", home=str(tmp_path))
    fix = next(m["fix"] for m in r["missing"] if m["what"] == "price history")
    assert "/model-price-history" in fix and "stooq" not in fix and os.path.join(str(src), "Price Data") in fix


def test_price_csvs_in_price_data_are_found(tmp_path):
    src = research(tmp_path)
    make_model(str(src / "TEST_model.xlsx"))
    (src / "Price Data").mkdir()
    (src / "Price Data" / "test_us_d.csv").write_text("Date,Close\n")
    (src / "Price Data" / "spy_us_d.csv").write_text("Date,Close\n")
    assert check("TEST", home=str(tmp_path))["price"]["kind"] == "csv"


def test_no_source_folder_stops_and_says_run_model_gather(tmp_path):
    r = check("NOPE", home=str(tmp_path))
    assert r["status"] == "stop" and "/collect-documents NOPE" in r["missing"][0]["fix"]


def test_a_model_path_given_by_the_user_is_used(tmp_path):
    research(tmp_path)
    m = make_model(str(tmp_path / "dxcm_model_user.xlsx"), px_rows=[(datetime.datetime(2024, 1, 2), 1.0, 2.0)])
    r = check("TEST", model=m, home=str(tmp_path))
    assert r["status"] == "ok" and r["model"] == m
