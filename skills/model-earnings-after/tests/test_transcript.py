"""The call summary rests on the transcript: it must be this quarter's, found by collect-documents' naming. A user
who has the transcript from FactSet / Koyfin / Bloomberg saves it in Earnings Calls/ and ingest() files it under the
same name so every later skill finds it; a PDF is converted to Markdown by code, never retyped. The folder's own
file always wins: a transcript collect-documents already saved is never overwritten."""
import pytest

import make_fixture as mf
import transcript as tr


def test_finds_this_quarters_call(fixture_research):
    assert tr.find(fixture_research, "TEST", "Q4 26") == mf.TRANSCRIPT
    assert tr.find(fixture_research, "TEST", "Q1 27") is None


def test_name_for_quarter():
    assert tr.name("TEST", "Q4 26") == "2026 Q4 TEST call"
    assert tr.name("TEST", "Q4 26E") == "2026 Q4 TEST call"


def _root(tmp_path):
    root = tmp_path / "TEST"
    (root / "Earnings Calls").mkdir(parents=True)
    return root


def test_ingest_text_file(tmp_path):
    root = _root(tmp_path)
    src = root / "Earnings Calls" / "factset.txt"
    src.write_text("CEO: hello\n")
    rel = tr.ingest(str(root), "TEST", "Q1 27", str(src))
    assert rel == "Earnings Calls/_md/2027 Q1 TEST call.md"
    assert (root / rel).read_text().startswith("CEO: hello")
    assert tr.find(str(root), "TEST", "Q1 27") == rel


def test_ingest_pdf_converts_and_keeps_pdf(tmp_path):
    fitz = pytest.importorskip("fitz")
    root = _root(tmp_path)
    src = tmp_path / "bloomberg.pdf"
    doc = fitz.open()
    doc.new_page().insert_text((72, 72), "CFO: margins expand")
    doc.save(str(src))
    rel = tr.ingest(str(root), "TEST", "Q1 27", str(src))
    assert "CFO: margins expand" in (root / rel).read_text()
    assert (root / "Earnings Calls" / "2027 Q1 TEST call.pdf").is_file()


def test_ingest_refuses_to_overwrite(fixture_research, tmp_path):
    src = tmp_path / "other.txt"
    src.write_text("different")
    before = open(f"{fixture_research}/{mf.TRANSCRIPT}").read()
    with pytest.raises(SystemExit) as e:
        tr.ingest(fixture_research, "TEST", "Q4 26", str(src))
    assert "already" in str(e.value)
    assert open(f"{fixture_research}/{mf.TRANSCRIPT}").read() == before
