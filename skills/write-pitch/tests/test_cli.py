"""Every script SKILL.md runs must start under `python3 -I` (how SKILL.md runs them): -I drops the script's own folder
from sys.path, so a script that imports a sibling (lo, common, ...) without putting its folder back dies with
ModuleNotFoundError before doing anything. --help reaches every module-level import and nothing more."""
import pathlib
import re
import subprocess

import pytest

SK = pathlib.Path(__file__).resolve().parents[1]
RUN = sorted(set(re.findall(r'"\$SK/(\w+)\.py"', (SK / "SKILL.md").read_text())))
# third-party packages a script may import at module level; preflight tells the user to install a missing one
PACKAGES = {"pptx": "python-pptx", "docx": "python-docx", "openpyxl": "openpyxl", "fitz": "PyMuPDF", "PIL": "Pillow"}


def _imports_under_isolated(mod):
    return subprocess.run(["python3", "-I", "-c", f"import {mod}"], capture_output=True).returncode == 0


def test_skill_md_names_scripts():
    assert len(RUN) >= 10 and "render_tabs" in RUN and "build_deck" in RUN


@pytest.mark.parametrize("name", RUN)
def test_script_starts_under_isolated_mode(name, tmp_path):
    src = (SK / "scripts" / f"{name}.py").read_text()
    for mod, pkg in PACKAGES.items():
        if re.search(rf"^(from|import) {mod}\b", src, re.M) and not _imports_under_isolated(mod):
            pytest.skip(f"{pkg} does not import under `python3 -I` on this machine (installed for the user only); "
                        f"preflight stops a real run with the pip line to fix it")
    r = subprocess.run(["python3", "-I", str(SK / "scripts" / f"{name}.py"), "--help"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert r.returncode == 0 and "Traceback" not in r.stderr, r.stderr


# why: render_tabs once imported lo inside render(), past --help; a run on a missing file reaches the work path
# without starting LibreOffice, and must fail on the file, never on an import
def test_render_tabs_reaches_its_work_under_isolated_mode(tmp_path):
    if not _imports_under_isolated("fitz"):
        pytest.skip("PyMuPDF does not import under `python3 -I` on this machine")
    r = subprocess.run(["python3", "-I", str(SK / "scripts" / "render_tabs.py"), "--values", str(tmp_path / "no.xlsx"),
                        "--out", str(tmp_path / "tabs")], cwd=tmp_path, capture_output=True, text=True)
    assert r.returncode != 0 and "ModuleNotFoundError" not in r.stderr and "no.xlsx" in r.stderr, r.stderr
