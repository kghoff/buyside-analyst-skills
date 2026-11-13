"""Step 10b - contact sheets for picking deck slides by eye, and full-resolution grabs of the chosen ones.

usage: python3 slides.py sheets --src <ticker folder>        every deck / event PDF -> _work/slides/<label>/sheet-NN.jpg
       python3 slides.py grab <pdf> <page> <out.png> [--dpi 170] [--crop l,t,r,b]     (crop as fractions 0-1)
       python3 slides.py grabs --src <ticker folder>         every pick in _work/slides.json -> <Filings Research>/fig/
Sheets show 6 slides each, labeled S1, S2... in the corner. Cite a slide as [<file label>, S41]."""
import argparse, glob, os, re, subprocess, tempfile

from PIL import Image, ImageDraw, ImageFont

from common import load, phase_dir, work_dir


def sheets(pdf, out_dir, per=6):
    pg = os.path.join(out_dir, "pg")
    os.makedirs(pg, exist_ok=True)
    subprocess.run(["pdftoppm", "-r", "55", "-jpeg", pdf, os.path.join(pg, "p")], check=True)
    files = sorted(glob.glob(os.path.join(pg, "p-*.jpg")), key=lambda f: int(re.search(r"-(\d+)\.jpg$", f).group(1)))
    for k in range(0, len(files), per):
        ims = [Image.open(f) for f in files[k:k + per]]
        w, h = ims[0].size
        sheet = Image.new("RGB", (w * 2 + 10, h * 3 + 20), "white")
        d = ImageDraw.Draw(sheet)
        font = ImageFont.load_default(size=22)
        for i, im in enumerate(ims):
            x, y = (i % 2) * (w + 10), (i // 2) * (h + 10)
            sheet.paste(im.resize((w, h)), (x, y))
            label = f"S{k + i + 1}"
            l, t, r, b = d.textbbox((x + 4, y + 2), label, font=font)
            d.rectangle([x, y, r + 4, b + 2], fill="black")
            d.text((x + 4, y + 2), label, fill="yellow", font=font)
        sheet.save(os.path.join(out_dir, f"sheet-{k // per + 1:02d}.jpg"), quality=80)
    return len(files)


def page_count(pdf):
    info = subprocess.run(["pdfinfo", pdf], check=True, capture_output=True, text=True).stdout
    return int(re.search(r"^Pages:\s+(\d+)", info, re.M).group(1))


def grab(pdf, page, out, dpi=170, crop=None):
    n = page_count(pdf)
    if not 1 <= page <= n:
        raise ValueError(f"page {page} is outside {os.path.basename(pdf)} (1-{n})")
    if crop:
        l, top, r, b = crop
        if not (0 <= l < r <= 1 and 0 <= top < b <= 1):
            raise ValueError(f"crop {crop} must be (left, top, right, bottom) fractions with 0 <= left < right <= 1 "
                             "and 0 <= top < bottom <= 1")
    with tempfile.TemporaryDirectory() as t:
        subprocess.run(["pdftoppm", "-r", str(dpi), "-f", str(page), "-l", str(page), "-png", pdf,
                        os.path.join(t, "p")], check=True)
        im = Image.open(glob.glob(os.path.join(t, "p*.png"))[0])
        if crop:
            l, top, r, b = crop
            W, H = im.size
            im = im.crop((int(l * W), int(top * H), int(r * W), int(b * H)))
        os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
        im.save(out)
    return out


def all_sheets(src):
    w = work_dir(src)
    n = 0
    for d in load(os.path.join(w, "inventory.json")):
        if d["category"] in ("Investor Decks", "Investor Events") and d["pdf"]:
            out = os.path.join(w, "slides", d["label"])
            first, pdf = os.path.join(out, "sheet-01.jpg"), os.path.join(src, d["pdf"])
            if not os.path.exists(first) or os.path.getmtime(pdf) > os.path.getmtime(first):
                n += sheets(pdf, out)
    return n


def all_grabs(src):
    """_work/slides.json: [{file: <label>, page, out: 'slide_<tag>.png', crop: [l,t,r,b] or null, caption}]"""
    w = work_dir(src)
    pdfs = {d["label"]: d["pdf"] for d in load(os.path.join(w, "inventory.json")) if d["pdf"]}
    picks = load(os.path.join(w, "slides.json"), [])
    for p in picks:
        grab(os.path.join(src, pdfs[p["file"]]), p["page"], os.path.join(phase_dir(src), "fig", p["out"]),
             crop=p.get("crop"))
    return len(picks)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["sheets", "grab", "grabs"])
    ap.add_argument("args", nargs="*")
    ap.add_argument("--src")
    ap.add_argument("--dpi", type=int, default=170)
    ap.add_argument("--crop")
    a = ap.parse_args()
    if a.cmd == "sheets":
        print(f"{all_sheets(a.src)} slides on new contact sheets")
    elif a.cmd == "grabs":
        print(f"{all_grabs(a.src)} slides grabbed")
    else:
        pdf, page, out = a.args
        print(grab(pdf, int(page), out, a.dpi, tuple(float(x) for x in a.crop.split(",")) if a.crop else None))
