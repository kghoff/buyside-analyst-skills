"""Step 1 - pull what the filings research concluded into one file for the ledger agent, plus its numbered gaps and big moves.

usage: python3 ledger_extract.py --src <ticker folder>
Writes _work/phase1_extract.md (the filings research's industry, management, key drivers, forecast, stock, debates and gaps
sections, verbatim; found by file name, so both the 16-section and the 8-section filings research layouts work), _work/gaps.json
[{n, group, title, text}] and _work/turning_points.json [{event, date, major, row}]. Stops if no numbered gaps."""
import argparse, glob, os, re

from p2common import p1_dir, save, work_dir

WANTED = ("industry", "management", "key-drivers", "forecast", "stock", "debates", "gaps")
GAP = re.compile(r"^(\d+)\.\s+\*\*(.+?)\*\*\s*(.*)$")
GROUP = re.compile(r"^\*\*([^*]+)\*\*\s*$")
SEP = re.compile(r"^\|[\s:|\-]+\|?$")
DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


def gaps(md):
    out, group = [], ""
    for line in md.splitlines():
        s = line.strip()
        if s.startswith("### B"):
            break
        g = GROUP.match(s)
        if g:
            group = g.group(1).strip()
            continue
        m = GAP.match(s)
        if m:
            out.append({"n": int(m.group(1)), "group": group, "title": m.group(2).strip().rstrip("."),
                        "text": m.group(3).strip()})
    return out


def turning_points(md):
    lines, out, on, noevent, table = md.splitlines(), [], False, False, 0   # table: 0 not seen, 1 inside, 2 done
    for i, line in enumerate(lines):
        s = line.strip()
        if s.startswith("#"):
            on = "big move" in s.lower()
            noevent = on and re.search(r"\bno\b.*\bevent", s.lower()) is not None
            table = 0
            continue
        if not on or s.startswith(">"):
            continue
        if not s.startswith("|"):
            table = 2 if table == 1 else table          # a blank/text line ends the first table
            b = re.match(r"^[-*]\s+\*\*(.+?)\*\*", s)
            if noevent and b:
                d = DATE.search(s)
                out.append({"event": b.group(1).strip().rstrip("."), "date": d.group(0) if d else None, "major": False,
                            "kind": "no-event", "row": s[:600]})
            continue
        if table == 2 or SEP.match(s):
            continue
        table = 1
        if i + 1 < len(lines) and SEP.match(lines[i + 1].strip()):
            continue                                   # header row
        cell = s.strip("|").split("|")[0].strip()
        d = DATE.search(cell)
        out.append({"event": cell.strip("* "), "date": d.group(0) if d else None, "major": cell.startswith("**"),
                    "kind": "event", "row": s[:600]})
    return out


def extract(src):
    sections = os.path.join(p1_dir(src), "sections")
    files = [p for p in sorted(glob.glob(os.path.join(sections, "*.md"))) if any(w in os.path.basename(p) for w in WANTED)]
    parts, gap_rows, moves = [], [], []
    for p in files:
        text = open(p, encoding="utf-8").read()
        parts.append(f"<!-- Filings research file: {os.path.basename(p)} -->\n\n{text}")
        if "gaps" in os.path.basename(p):
            gap_rows = gaps(text)
        if "stock" in os.path.basename(p):
            moves = turning_points(text)
    if not gap_rows:
        raise SystemExit("no numbered gaps found in the filings research gaps section; check its format ('N. **Title.** text')")
    w = work_dir(src)
    os.makedirs(w, exist_ok=True)
    open(os.path.join(w, "phase1_extract.md"), "w", encoding="utf-8").write("\n\n".join(parts))
    save(os.path.join(w, "gaps.json"), gap_rows)
    save(os.path.join(w, "turning_points.json"), moves)
    return len(gap_rows), len(moves)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    g, t = extract(ap.parse_args().src)
    print(f"{g} gaps, {t} turning points" + ("" if t else " (WARNING: no big-move table found in the filings research stock section)"))
