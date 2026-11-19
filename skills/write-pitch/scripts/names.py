"""The file names of this run's pitch in <research>/<T>/Pitch/, never overwriting an earlier pitch.

usage: python3 names.py --pitch-dir <research>/<T>/Pitch --ticker XYZ [--date YYYY-MM-DD]
Prints JSON {"long", "core", "sheet", "md"}: bare file names (.pptx, .pptx, .docx, .md), checked against --pitch-dir;
the skill builds them in its build folder and only `mv -n` puts them in Pitch/. The PDFs export_pdf.py makes sit next
to them with the same stem. The set is "<date> <T> Pitch", "<date> <T> Pitch (core)", "<date> <T> Pitch Sheet";
when any file of that set (any extension) exists, every name gets " (2)", then " (3)" ..., so one run's files share a
suffix and no earlier file is ever overwritten.
"""
import argparse
import datetime
import glob
import json
import os


def stems(ticker, date, n):
    sfx = "" if n == 1 else f" ({n})"
    base = f"{date} {ticker.upper()} Pitch"
    return {"long": base + sfx, "core": base + " (core)" + sfx, "sheet": base + " Sheet" + sfx}


def taken(pitch_dir, stem):
    return bool(glob.glob(os.path.join(glob.escape(os.path.abspath(pitch_dir)), glob.escape(stem)) + ".*"))


def names(pitch_dir, ticker, date=None):
    date = date or datetime.date.today().isoformat()
    n = 1
    while any(taken(pitch_dir, s) for s in stems(ticker, date, n).values()):
        n += 1
    s = stems(ticker, date, n)
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
