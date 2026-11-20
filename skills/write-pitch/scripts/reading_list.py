"""The analyst's reading list ({READING_LIST} in assignment.md), in the spec's reading order (section 6).

usage: python3 reading_list.py --research <research root> --model-dir <model dir> --work <work> [--since YYYY-MM-DD]
Prints Markdown: a numbered list of the files that exist (absolute paths), then "Missing (optional)" naming the
expected files not found. With --since (rerun mode) the old plate (<work>/plate.md) comes first and only files changed
on or after that date are listed (the rest under "Unchanged since"); the digest and the tab index are always listed,
since every run regenerates them. Read-only; nothing company-specific.
"""
import argparse
import datetime
import glob
import os
import re

DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


def newest(pattern, exclude=None):
    """Newest file matching the glob: by the date in its name (else its modified date), then by modified time."""
    hits = [p for p in glob.glob(pattern) if os.path.isfile(p) and not (exclude and exclude in os.path.basename(p))]

    def key(p):
        m = DATE.search(os.path.basename(p))
        mt = os.path.getmtime(p)
        return (m.group(0) if m else datetime.date.fromtimestamp(mt).isoformat(), mt)
    return max(hits, key=key) if hits else None


def expected(research, model_dir, work):
    """[(what, path or None, glob or path looked for)] in reading order."""
    R = lambda *p: os.path.join(research, *p)                  # noqa: E731
    MW = lambda *p: os.path.join(model_dir, "_model_work", *p)  # noqa: E731

    def one(what, path):
        return (what, path if os.path.isfile(path) else None, path)

    def glob_one(what, pattern, exclude=None):
        return (what, newest(pattern, exclude), pattern)

    return [
        one("Your notes for this pitch", os.path.join(work, "user_notes.md")),
        glob_one("Filings research report", R("Filings Research", "*Filings Research Report.md")),
        glob_one("Street research report", R("Street Research", "*Street Research Report.md")),
        one("Filings research: the driver analysis", R("Filings Research", "_work", "drivers.md")),
        one("Filings research: the PM review and its response", R("Filings Research", "_work", "pm_review.md")),
        one("Street research: the synthesis", R("Street Research", "_work", "synthesis.md")),
        one("Street research: the PM review and its response", R("Street Research", "_work", "pm_review.md")),
        one("Street research: the new views", R("Street Research", "_work", "new_views.md")),
        one("Forecast write-up", MW("forecast", "forecast_writeup.md")),
        one("Valuation plan (the valuation analyst's choices and reasons)", MW("model-valuation", "valuation_plan.json")),
        one("Short check plan (the short analyst's answers)", MW("model-short", "short_plan.json")),
        one("Earnings preview plan", MW("model-earnings-before", "earnings_plan.json")),
        one("After-print plan", MW("model-earnings-after", "after_plan.json")),
        glob_one("Valuation note", R("Valuation", "*.md")),
        glob_one("Short check note", R("Short Check", "*.md")),
        glob_one("Earnings preview note", R("Earnings Previews", "*.md")),
        glob_one("Earnings review note", R("Earnings Reviews", "*.md")),
        one("Model digest (every tab's text, notes and numbers with their cells)", os.path.join(work, "digest.md")),
        one("Tab pictures index", os.path.join(work, "tabs", "index.md")),
    ]


ALWAYS = {"Model digest (every tab's text, notes and numbers with their cells)", "Tab pictures index"}


def build(research, model_dir, work, since=None):
    research, model_dir, work = (os.path.abspath(p) for p in (research, model_dir, work))
    items, missing, unchanged = [], [], []
    if since:
        plate = os.path.join(work, "plate.md")
        if os.path.isfile(plate):
            items.append(("The old plate file (your last pitch's notebook): read it first", plate, ""))
        else:
            missing.append(("The old plate file", plate))
    for what, path, looked in expected(research, model_dir, work):
        if not path:
            missing.append((what, looked))
        elif since and what not in ALWAYS and datetime.date.fromtimestamp(os.path.getmtime(path)) < since:
            unchanged.append((what, path))
        else:
            extra = ""
            if what == "Filings research report":
                long_v = newest(os.path.join(research, "Filings Research", "*Filings Research Report (long version).md"))
                if long_v:
                    extra = f" (the long version, `{long_v}`, is optional: open it only for the sections you need)"
            items.append((what, path, extra))
    lines = [f"{i}. {what}: `{path}`{extra}" for i, (what, path, extra) in enumerate(items, 1)]
    if unchanged:
        lines += ["", f"Unchanged since {since.isoformat()} (read on the last run; open one only to check a point):"]
        lines += [f"- {what}: `{path}`" for what, path in unchanged]
    lines += ["", "Missing (optional; work without them and say so in `notes`):"]
    lines += [f"- {what} (looked for `{looked}`)" for what, looked in missing] or ["- none"]
    return "\n".join(lines) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--research", required=True)
    ap.add_argument("--model-dir", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--since", type=datetime.date.fromisoformat)
    a = ap.parse_args(argv)
    print(build(a.research, a.model_dir, a.work, a.since), end="")


if __name__ == "__main__":
    main()
