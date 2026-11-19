"""The file names of this run's pitch in <research>/<T>/Pitch/, never overwriting an earlier pitch.

usage: python3 names.py --pitch-dir <research>/<T>/Pitch --ticker XYZ [--date YYYY-MM-DD]
Prints JSON {"long", "core", "sheet", "md"} (absolute paths: .pptx, .pptx, .docx, .md). The PDFs export_pdf.py makes
sit next to them with the same stem. The set is "<date> <T> Pitch", "<date> <T> Pitch (core)", "<date> <T> Pitch Sheet";
when any file of that set (any extension) exists, every name gets " (2)", then " (3)" ..., so one run's files share a
suffix and no earlier file is ever overwritten.
"""
import argparse
import datetime
import glob
import json
import os


def stems(pitch_dir, ticker, date, n):
    sfx = "" if n == 1 else f" ({n})"
    base = os.path.join(os.path.abspath(pitch_dir), f"{date} {ticker.upper()} Pitch")
    return {"long": base + sfx, "core": base + " (core)" + sfx, "sheet": base + " Sheet" + sfx}


def taken(stem):
    return bool(glob.glob(glob.escape(stem) + ".*"))


def names(pitch_dir, ticker, date=None):
    date = date or datetime.date.today().isoformat()
    n = 1
    while any(taken(s) for s in stems(pitch_dir, ticker, date, n).values()):
        n += 1
    s = stems(pitch_dir, ticker, date, n)
    return {"long": s["long"] + ".pptx", "core": s["core"] + ".pptx", "sheet": s["sheet"] + ".docx",
            "md": s["long"] + ".md"}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--pitch-dir", required=True)
    ap.add_argument("--ticker", required=True)
    ap.add_argument("--date")
    a = ap.parse_args(argv)
    print(json.dumps(names(a.pitch_dir, a.ticker, a.date), indent=1))


if __name__ == "__main__":
    main()
