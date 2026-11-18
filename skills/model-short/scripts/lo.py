"""(Copied from model-valuation, Nov 2026; keep in sync, except the profile folder is named model-short so two skills can run at once.) LibreOffice headless helpers: recalculate a workbook (every formula, not the cached values) and render one tab.

A private LibreOffice profile set to "always recalculate on load" is created on first use, so the user's own
LibreOffice settings (if they have any) are never touched."""
import os
import shutil
import subprocess
import tempfile

SOFFICE = next((p for p in ("/Applications/LibreOffice.app/Contents/MacOS/soffice", shutil.which("soffice") or "")
                if p and os.path.exists(p)), None)
PROFILE = os.path.join(tempfile.gettempdir(), "model-short-lo-profile")
XCU = """<?xml version="1.0" encoding="UTF-8"?>
<oor:items xmlns:oor="http://openoffice.org/2001/registry" xmlns:xs="http://www.w3.org/2001/XMLSchema" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
<item oor:path="/org.openoffice.Office.Calc/Formula/Load"><prop oor:name="OOXMLRecalcMode" oor:op="fuse"><value>0</value></prop></item>
<item oor:path="/org.openoffice.Office.Calc/Formula/Load"><prop oor:name="ODFRecalcMode" oor:op="fuse"><value>0</value></prop></item>
</oor:items>"""


def _run(args, outdir):
    if not SOFFICE:
        raise SystemExit("LibreOffice not found. Install it once with: brew install --cask libreoffice")
    os.makedirs(os.path.join(PROFILE, "user"), exist_ok=True)
    with open(os.path.join(PROFILE, "user", "registrymodifications.xcu"), "w") as f:
        f.write(XCU)
    os.makedirs(outdir, exist_ok=True)
    subprocess.run([SOFFICE, f"-env:UserInstallation=file://{PROFILE}", "--headless", "--calc"] + args + ["--outdir", outdir],
                   check=True, capture_output=True, timeout=900)


def recalc(path, outdir):
    """Recalculated copy of `path` in outdir (same file name). Returns its path."""
    tmp = tempfile.mkdtemp(prefix="ipnl_recalc_")
    try:                                      # the temp copy is a copy of the model: never keep it
        src = os.path.join(tmp, os.path.basename(path))
        shutil.copy2(path, src)
        _run(["--convert-to", "xlsx", src], outdir)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return os.path.join(outdir, os.path.basename(path))


def render_pdf(path, outdir):
    """Every tab as one PDF page each (SinglePageSheets). Returns the PDF path."""
    _run(["--convert-to", 'pdf:calc_pdf_Export:{"SinglePageSheets":{"type":"boolean","value":"true"}}', path], outdir)
    return os.path.join(outdir, os.path.splitext(os.path.basename(path))[0] + ".pdf")


def page_png(pdf, page, out_png, width=1800):
    import fitz
    doc = fitz.open(pdf)
    pg = doc[page]
    zoom = width / pg.rect.width
    pg.get_pixmap(matrix=fitz.Matrix(zoom, zoom)).save(out_png)
    return out_png
