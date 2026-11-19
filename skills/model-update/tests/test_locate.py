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


def _prelim(base, name="2026 Q3 TEST release 2026-10-05.md"):
    p = os.path.join(base, "Press Releases", "_md", name)
    with open(p, "w", encoding="utf-8") as f:
        f.write("# TEST Reports Preliminary, Unaudited Results\n\nRevenue of approximately $140 million.\n")
    return p


def test_a_preliminary_release_alone_is_not_a_print(model, tmp_path):
    """January 'preliminary results' (revenue only) share the file pattern; entering it would blank the quarter."""
    base = mf.research(str(tmp_path / "r"))
    os.remove(os.path.join(base, "Press Releases", "_md", "2026 Q3 TEST release 2026-10-29.md"))
    _prelim(base)
    r = locate.locate(model, base, "TEST", str(tmp_path / "w"))
    assert r["mode"] == "none" and "preliminary release only" in r["reason"]


def test_the_full_release_wins_over_a_newer_file_without_statements(model, tmp_path):
    """The newest file with an income statement and a balance sheet is the print; exhibits without tables are not
    sources."""
    base = mf.research(str(tmp_path / "r"))
    _prelim(base, "2026 Q3 TEST release 2026-11-02 EX-99.2.md")
    r = locate.locate(model, base, "TEST", str(tmp_path / "w"))
    assert r["mode"] == "print" and r["release"].endswith("2026-10-29.md")
    assert [os.path.basename(x) for x in r["releases"]] == ["2026 Q3 TEST release 2026-10-29.md"]


def test_a_q4_rerun_waits_for_the_10k_not_a_10q(tmp_path):
    """There is no Q4 10-Q: the fourth quarter's filing is the annual report."""
    p = mf.model(str(tmp_path / "m.xlsx"), actual_q3=True)
    import openpyxl
    wb = openpyxl.load_workbook(p)
    wb["MOD"]["M2"] = "Q4 26"
    wb.save(p)
    base = mf.research(str(tmp_path / "r"))
    k = os.path.join(base, "10-Ks", "_md")
    os.makedirs(k)
    open(os.path.join(k, "TEST 2026 10-K.md"), "w").write("annual report")
    work = tmp_path / "work"
    (work / "Q4 26").mkdir(parents=True)
    (work / "Q4 26" / "state.json").write_text(json.dumps({"awaiting": [{"ref": "M15"}], "tenq_checked": False}))
    r = locate.locate(p, base, "TEST", str(work))
    assert r["mode"] == "tenq" and r["filing"].endswith("TEST 2026 10-K.md") and r["tenq"] == r["filing"]
