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
ZW = re.compile("[\u200b\u200c\u200d\ufeff]")                      # invisible characters some filings put in empty cells
PER_SHARE = re.compile(r"per (common |ordinary )?share", re.I)


def parse_row(line):
    cells = [c.strip() for c in line.strip().strip("|").split("|")]
    label, vals = None, []
    for c in cells:
        c2 = ZW.sub("", c.replace("$", "").replace("\\", "")).strip()
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


def _scales(head):
    """(dollar scale, share scale) to $ millions / millions of shares. ABT 10-Qs say 'dollars in millions ...; shares in
    thousands', so the dollar unit is read with the shares phrase removed, and share rows get their own unit."""
    dollars = re.sub(r"shares in (thousands|millions)", "", head)
    scale = 0.001 if "in thousands" in dollars else (1000.0 if "in billions" in dollars else 1.0)
    shares = 0.001 if "shares in thousands" in head else (1.0 if "shares in millions" in head else scale)
    return scale, shares


def _rows(lines, j, scale, shares, min_rows):
    """rows of the table starting at line j; an unlabeled row keeps label "" (ABT prints total assets with no label);
    a row of years (a column header) is dropped"""
    rows, blanks = [], 0
    while j < len(lines):
        L = lines[j]
        if L.lstrip().startswith("|"):
            blanks = 0
            lab, vals = parse_row(L)
            if lab is None and vals and not all(v == int(v) and 1990 <= v <= 2100 for v in vals):
                lab = ""
            if lab is not None and not SKIP_LABEL.match(lab.strip()) and lab.strip() != "---":
                lab = re.sub(r"\s+", " ", lab).strip()
                low = lab.lower()
                f = 1.0 if PER_SHARE.search(low) and "shares" not in low else (shares if "shares" in low else scale)
                rows.append((lab, vals if f == 1.0 else [round(v * f, 4) for v in vals]))
        elif ZW.sub("", L).strip() == "":                  # a line holding only an invisible character is blank too
            blanks += 1
        elif len(rows) > min_rows:
            break
        if blanks > 3 and len(rows) > min_rows:
            break
        j += 1
    return rows, j


def find_tables(text, min_rows=12):
    """Return {"IS"|"BS"|"CF": [(label, values), ...]} for the first real statement of each kind. A balance sheet whose
    first table has no liabilities continues under the next heading of the same kind (ABT prints one per page)."""
    lines = text.split("\n")
    out = {}
    for key, pat in HEADS.items():
        heads = [i for i, l in enumerate(lines) if re.fullmatch(pat + r"(\s*\(.*\))?", re.sub(r"[|*\s]+", " ", l).strip(), re.I)]
        for n, i in enumerate(heads):
            j = i + 1
            while j < len(lines) and not lines[j].lstrip().startswith("|"):
                j += 1
            head = " ".join(lines[i:j + 4]).lower()
            scale, shares = _scales(head)
            rows, end = _rows(lines, j, scale, shares, min_rows)
            if len(rows) <= min_rows:
                continue
            if key == "BS" and not any("liabilit" in r[0].lower() for r in rows):
                nxt = next((h for h in heads[n + 1:] if h >= end), None)
                if nxt is not None:
                    k = nxt + 1
                    while k < len(lines) and not lines[k].lstrip().startswith("|"):
                        k += 1
                    rows += _rows(lines, k, scale, shares, 0)[0]
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
