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


def test_cap_is_shared_by_weight_so_no_section_is_starved(tmp_path):
    report(tmp_path, "Filings Research", "2026-01-02 TST Filings Research Report.md",
           [("Summary", 40), ("The key drivers", 40), ("Gaps", 40)])
    text, s = brief.build("TST", str(tmp_path), cap=70)
    cut = {c["section"]: c for c in s["cut"]}
    assert set(cut) == {"Filings Research / Summary", "Filings Research / The key drivers", "Filings Research / Gaps"}
    assert all(c["kept"] > 0 for c in cut.values())           # even the lowest-weight section keeps its heading
    assert cut["Filings Research / Summary"]["budget"] > cut["Filings Research / Gaps"]["budget"]   # weight 2 vs 1
    assert "Cut by the brief's 70-word cap" in text
    assert s["words"] <= 70 + 60                              # headings and cut notes are the only overrun


def test_short_section_stays_whole_and_its_unused_budget_flows_to_a_long_one(tmp_path):
    report(tmp_path, "Filings Research", "2026-01-02 TST Filings Research Report.md",
           [("Summary", 5), ("The key drivers", 200)])
    _, s = brief.build("TST", str(tmp_path), cap=100)
    assert "Filings Research / Summary" in s["included"]      # shorter than its share: kept whole
    c = s["cut"][0]
    assert c["section"] == "Filings Research / The key drivers"
    assert c["budget"] > 100 * 2 / 4                          # more than an equal-weight share: it got the leftover


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
