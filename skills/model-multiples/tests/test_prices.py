import json
import os
import subprocess
import sys

from conftest import HERE


def test_core_peer_cli_copies_found_file_and_reports_missing(tmp_path):
    # Core peers' stooq files must end up in Price Data (copied, so the user's download stays), and a ticker the
    # user forgot to download must be reported, not silently skipped.
    model_dir, src = tmp_path / "m", tmp_path / "src"
    model_dir.mkdir(); src.mkdir()
    (src / "abt_us_d.csv").write_text(
        "Date,Open,High,Low,Close,Volume\n2024-01-02,10,11,9,10.5,100\n2024-01-03,10.5,12,10,11,100\n")
    script = os.path.join(HERE, "..", "scripts", "prices.py")
    r = subprocess.run([sys.executable, script, "--model", str(model_dir / "M.xlsx"), "--tickers", "ABT", "NOPE_ZZ",
                        "--src", str(src)], capture_output=True, text=True)
    res = {x["ticker"]: x for x in json.loads(r.stdout)}
    assert res["ABT"]["ok"] and os.path.isfile(model_dir / "Price Data" / "abt_us_d.csv")
    assert (src / "abt_us_d.csv").exists()
    assert not res["NOPE_ZZ"]["ok"] and res["NOPE_ZZ"]["why"] == "not found"
    assert r.returncode == 1
