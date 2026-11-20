# skills/write-pitch/scripts/export_pdf.py
"""PDF of a deck or the pitch sheet (LibreOffice), and one PNG per page of a PDF (PyMuPDF) for the look step.
usage: python3 export_pdf.py in.pptx|in.docx --out-dir DIR        (prints the PDF path)
       python3 export_pdf.py --pngs in.pdf --out-dir DIR [--width 1600]   (prints each PNG path)"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))   # run with python3 -I
import lo  # noqa: E402


def to_pdf(path, outdir):
    """PDF of a .pptx / .docx in outdir. Each call uses its own throwaway LibreOffice profile, so two conversions can
    run at once (a shared profile makes the second one fail). Failures end as one plain sentence."""
    if not os.path.exists(path):
        raise SystemExit(f"Cannot export: {path} does not exist.")
    if not lo.SOFFICE:
        raise SystemExit("LibreOffice not found. Install it once with: brew install --cask libreoffice")
    os.makedirs(outdir, exist_ok=True)
    profile = tempfile.mkdtemp(prefix="write-pitch-lo-")
    try:
        subprocess.run([lo.SOFFICE, f"-env:UserInstallation=file://{profile}", "--headless", "--convert-to", "pdf",
                        "--outdir", outdir, path], check=True, capture_output=True, timeout=180)
    except subprocess.CalledProcessError as e:
        tail = (e.stderr or b"").decode("utf-8", "replace").strip()[-300:]
        raise SystemExit(f"LibreOffice could not convert {path} to PDF. {tail}")
    except subprocess.TimeoutExpired as e:
        tail = (e.stderr or b"").decode("utf-8", "replace").strip()[-300:] if e.stderr else ""
        raise SystemExit(f"LibreOffice took over 3 minutes converting {path} and was stopped. {tail}")
    except OSError as e:
        raise SystemExit(f"LibreOffice could not be started ({e}).")
    finally:
        shutil.rmtree(profile, ignore_errors=True)
    pdf = os.path.join(outdir, os.path.splitext(os.path.basename(path))[0] + ".pdf")
    if not os.path.exists(pdf):
        raise SystemExit(f"LibreOffice made no PDF for {path}")
    return pdf


def pngs(pdf, outdir, width=1600):
    """One PNG per page, `width` px wide. Returns the paths."""
    import fitz
    os.makedirs(outdir, exist_ok=True)
    base = os.path.splitext(os.path.basename(pdf))[0]
    out = []
    for i, pg in enumerate(fitz.open(pdf), 1):
        z = width / pg.rect.width
        p = os.path.join(outdir, f"{base}_p{i:02d}.png")
        pg.get_pixmap(matrix=fitz.Matrix(z, z)).save(p)
        out.append(p)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src", nargs="?")
    ap.add_argument("--pngs")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--width", type=int, default=1600)
    a = ap.parse_args()
    if a.pngs:
        print("\n".join(pngs(a.pngs, a.out_dir, a.width)))
    elif a.src:
        print(to_pdf(a.src, a.out_dir))
    else:
        ap.error("give a .pptx / .docx, or --pngs <pdf>")


if __name__ == "__main__":
    main()
