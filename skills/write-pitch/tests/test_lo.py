"""lo.py: a LibreOffice run that exits 0 without writing its output must fail loud, not hand back a missing path."""
import subprocess

import pytest

import lo


# why: soffice can exit 0 having written nothing (a busy profile, a file it cannot open); the skill then runs digest.py
# and render_tabs.py on a path that does not exist and the user sees a confusing traceback instead of the cause
def test_recalc_that_writes_nothing_says_so(tmp_path, monkeypatch):
    src = tmp_path / "XYZ_model.xlsx"
    src.write_bytes(b"not really a workbook")
    monkeypatch.setattr(lo, "SOFFICE", "/bin/true")
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0, b"", b""))
    with pytest.raises(SystemExit, match="LibreOffice made no recalculated copy"):
        lo.recalc(str(src), str(tmp_path / "values"))


def test_render_pdf_that_writes_nothing_says_so(tmp_path, monkeypatch):
    src = tmp_path / "XYZ_values.xlsx"
    src.write_bytes(b"x")
    monkeypatch.setattr(lo, "SOFFICE", "/bin/true")
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0, b"", b""))
    with pytest.raises(SystemExit, match="LibreOffice made no PDF"):
        lo.render_pdf(str(src), str(tmp_path / "pdf"))
