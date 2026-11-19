import json
import os

import locate
import make_fixture as mf


def test_print_night_when_the_first_forecast_quarter_has_a_release(model, research, tmp_path):
    r = locate.locate(model, research, "TEST", str(tmp_path / "work"))
    assert r["mode"] == "print" and r["quarter"] == "Q3 26E" and r["release"].endswith("2026 Q3 TEST release 2026-10-29.md")


def test_no_release_means_stop(model, tmp_path):
    r = locate.locate(model, mf.research(str(tmp_path / "r2")).replace("TEST", "NONE"), "TEST", str(tmp_path / "w"))
    assert r["mode"] == "none" and "no release" in r["reason"]


def test_tenq_rerun_when_the_last_actual_quarter_still_waits(tmp_path):
    """After print night the quarter is actual; the 10-Q run must find it by its saved state, not its header."""
    p = mf.model(str(tmp_path / "m.xlsx"))
    import openpyxl
    wb = openpyxl.load_workbook(p)
    wb["MOD"]["L2"] = "Q3 26"
    wb.save(p)
    base = mf.research(str(tmp_path / "r"), with_tenq=True)
    os.remove(os.path.join(base, "Press Releases", "_md", "2026 Q3 TEST release 2026-10-29.md"))
    work = tmp_path / "work"
    (work / "Q3 26").mkdir(parents=True)
    (work / "Q3 26" / "state.json").write_text(json.dumps({"awaiting": [{"ref": "L15"}], "tenq_checked": False}))
    r = locate.locate(p, base, "TEST", str(work))
    assert r["mode"] == "tenq" and r["quarter"] == "Q3 26" and r["tenq"].endswith("TEST 2026 Q3 10-Q.md")
