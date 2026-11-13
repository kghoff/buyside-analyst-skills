"""Find the three primary financial statements in an SEC filing converted to markdown and parse their rows.

Each row becomes (label, [values...]) where values are floats in the order the columns appear.
Parentheses = negative, em-dash = 0. Values keep the filing's own sign (costs usually positive)."""
import re

HEADS = {
    "BS": r"(condensed )?consolidated balance sheets?",
    "IS": r"(condensed )?consolidated statements? of (operations|income|earnings|operations and comprehensive (income|loss))",
    "CF": r"(condensed )?consolidated statements? of cash flows",
}
NUM = re.compile(r"^\(?-?[\d,]*\.?\d+\)?$")
DASH = {"—", "-", "–", "— )", "—)"}
SKIP_LABEL = re.compile(r"^\(?(in millions|in thousands|unaudited|dollars in)", re.I)


def parse_row(line):
    cells = [c.strip() for c in line.strip().strip("|").split("|")]
    label, vals = None, []
    for c in cells:
        c2 = c.replace("$", "").replace("\\", "").strip()
        if label is None:
            if c2 and not NUM.match(c2) and c2 not in DASH:
                label = c2
                continue
            if not c2:
                continue
        if c2 in ("", ")", "%", ")%"):
            continue
        if c2 in DASH:
            vals.append(0.0)
            continue
        if NUM.match(c2):
            v = float(c2.strip("()").replace(",", ""))
            vals.append(-v if c2.startswith("(") else v)
    return label, vals


def find_tables(text, min_rows=12):
    """Return {"IS"|"BS"|"CF": [(label, values), ...]} for the first real statement of each kind."""
    lines = text.split("\n")
    out = {}
    for key, pat in HEADS.items():
        for i, l in enumerate(lines):
            s = re.sub(r"[|*\s]+", " ", l).strip()
            if not re.fullmatch(pat + r"(\s*\(.*\))?", s, re.I):
                continue
            j = i + 1
            while j < len(lines) and not lines[j].lstrip().startswith("|"):
                j += 1
            head = " ".join(lines[i:j + 4]).lower()
            scale = 0.001 if "in thousands" in head else (1000.0 if "in billions" in head else 1.0)
            rows, blanks = [], 0
            while j < len(lines):
                L = lines[j]
                if L.lstrip().startswith("|"):
                    blanks = 0
                    lab, vals = parse_row(L)
                    if lab and not SKIP_LABEL.match(lab.strip()) and lab.strip() != "---":
                        keep = "per share" in lab.lower() and "shares" not in lab.lower()   # EPS is never scaled
                        rows.append((re.sub(r"\s+", " ", lab).strip(), vals if keep or scale == 1.0 else [round(v * scale, 4) for v in vals]))
                elif L.strip() == "":
                    blanks += 1
                elif len(rows) > min_rows:
                    break
                if blanks > 3 and len(rows) > min_rows:
                    break
                j += 1
            if len(rows) > min_rows:
                out[key] = rows
                out.setdefault("_units", {})[key] = {0.001: "thousands", 1.0: "millions", 1000.0: "billions"}[scale]
                break
    return out


def shares_from_release(text):
    """Q4 press release: first-column basic/diluted share counts and net income (3 months)."""
    sb = sd = ni = None
    for line in text.split("\n"):
        if not line.startswith("|"):
            continue
        lab, v = parse_row(line)
        if not lab or not v:
            continue
        l = lab.lower()
        # "Shares used in ... basic", "Weighted average shares - basic", or MDT's "Basic weighted average shares outstanding"
        share_row = "shares used" in l or "weighted average" in l
        if share_row and "basic and diluted" in l:
            sb = sb or v; sd = sd or v
        elif share_row and "basic" in l:
            sb = sb or v
        elif share_row and "dilut" in l:
            sd = sd or v
        elif re.match(r"net (income|loss|earnings)", l) and "per share" not in l:
            ni = ni or v
    return sb, sd, ni
