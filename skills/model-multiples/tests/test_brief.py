import json
import os
import subprocess
import sys

import brief

SCRIPT = os.path.join(os.path.dirname(__file__), "..", "scripts", "brief.py")


def report(tmp, folder, name, sections):
    d = tmp / "TST" / folder
    d.mkdir(parents=True, exist_ok=True)
    body = []
    for i, (title, words) in enumerate(sections, 1):
        body += [f"## {i:02d} {title}", "", " ".join(["w"] * words), "", "### 1.1 a subsection that stays inside", "x", ""]
    (d / name).write_text("\n".join(body))
    return d / name


def test_reads_newest_short_report_and_ignores_long_version(tmp_path):
    report(tmp_path, "Filings Research", "2026-01-01 TST Filings Research Report (long version).md", [("Summary", 5)])
    report(tmp_path, "Filings Research", "2026-01-02 TST Filings Research Report.md", [("Summary", 7)])
    text, s = brief.build("TST", str(tmp_path), cap=15000)
    assert s["reports"]["Filings Research"].endswith("2026-01-02 TST Filings Research Report.md")
    assert "Filings Research / Summary" in s["included"]


def test_missing_sections_and_reports_are_listed_not_dropped(tmp_path):
    report(tmp_path, "Filings Research", "2026-01-02 TST Filings Research Report.md",
           [("Summary", 5), ("The key drivers", 5)])
    text, s = brief.build("TST", str(tmp_path), cap=15000)
    assert "Filings Research: management credibility" in s["missing"]
    assert any(m.startswith("Street Research:") for m in s["missing"])     # no street report at all
    assert s["reports"]["Street Research"] is None


def test_cap_cuts_lowest_priority_sections_and_says_where_to_read_the_rest(tmp_path):
    report(tmp_path, "Filings Research", "2026-01-02 TST Filings Research Report.md",
           [("Summary", 40), ("The key drivers", 40), ("Gaps", 40)])
    text, s = brief.build("TST", str(tmp_path), cap=70)
    assert "Filings Research / Summary" in s["included"]
    cut = {c["section"] for c in s["cut"]}
    assert "Filings Research / The key drivers" in cut        # second in priority: partly kept
    assert "Filings Research / Gaps" in cut                   # last in priority: nothing left
    assert "Cut by the brief's 70-word cap" in text
    assert s["words"] <= 70 + 60                              # headings and cut notes are the only overrun


def test_source_comment_points_at_the_heading_line(tmp_path):
    p = report(tmp_path, "Filings Research", "2026-01-02 TST Filings Research Report.md",
               [("Summary", 3), ("The stock vs the drivers", 3)])
    text, _ = brief.build("TST", str(tmp_path), cap=15000)
    lines = p.read_text().split("\n")
    m = [l for l in text.split("\n") if "The stock vs the drivers" in l and l.startswith("<!--")][0]
    n = int(m.rsplit("line ", 1)[1].split()[0])
    assert lines[n - 1] == "## 02 The stock vs the drivers"   # agents can open the full report at that line


def test_cli_writes_brief_and_prints_summary(tmp_path):
    report(tmp_path, "Filings Research", "2026-01-02 TST Filings Research Report.md", [("Summary", 3)])
    out = tmp_path / "brief.md"
    r = subprocess.run([sys.executable, SCRIPT, "--ticker", "TST", "--out", str(out), "--research-dir", str(tmp_path)],
                       capture_output=True, text=True, check=True)
    assert out.exists() and json.loads(r.stdout)["included"] == ["Filings Research / Summary"]
