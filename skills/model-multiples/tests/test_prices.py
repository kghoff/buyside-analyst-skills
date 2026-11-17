import json
import os
import subprocess
import sys

from conftest import HERE

SCRIPT = os.path.join(HERE, "..", "scripts", "prices.py")
GOOD = "Date,Open,High,Low,Close,Volume\n2024-01-02,10,11,9,10.5,100\n2024-01-03,10.5,12,10,11,100\n"


def run(tmp_path, model_dir, src, *tickers):
    # HOME points inside tmp so the real ~/Downloads is never searched.
    env = {**os.environ, "HOME": str(tmp_path / "home")}
    return subprocess.run([sys.executable, SCRIPT, "--model", str(model_dir / "M.xlsx"), "--tickers", *tickers,
                           "--src", str(src)], capture_output=True, text=True, env=env)


def test_core_peer_cli_copies_found_file_and_reports_missing(tmp_path):
    # Core peers' stooq files must end up in Price Data (copied, so the user's download stays), and a ticker the
    # user forgot to download must be reported, not silently skipped.
    model_dir, src = tmp_path / "m", tmp_path / "src"
    model_dir.mkdir()
    src.mkdir()
    (src / "abt_us_d.csv").write_text(GOOD)
    r = run(tmp_path, model_dir, src, "ABT", "abt", "NOPE_ZZ")
    out = json.loads(r.stdout)
    res = {x["ticker"]: x for x in out}
    assert len(out) == 2  # ABT and abt are the same file
    dst = model_dir / "Price Data" / "abt_us_d.csv"
    assert res["abt"]["ok"] and dst.read_bytes() == (src / "abt_us_d.csv").read_bytes()
    assert not res["nope_zz"]["ok"] and res["nope_zz"]["why"] == "not found"
    assert r.returncode == 1


def test_garbled_csv_is_reported_not_a_traceback(tmp_path):
    # An empty download must come back as a per-ticker failure the skill can show the user.
    model_dir, src = tmp_path / "m", tmp_path / "src"
    model_dir.mkdir()
    src.mkdir()
    (src / "mdt_us_d.csv").write_text("")
    r = run(tmp_path, model_dir, src, "mdt")
    res = json.loads(r.stdout)
    assert res[0]["ok"] is False and res[0]["why"] and r.returncode == 1
