"""Markdown table parsing for SEC filings / press releases / decks converted to .md"""
import re
NUM = re.compile(r"^\(?-?[\d,]*\.?\d+\)?$")
DASH = ("—", "-", "–")


def row_vals(line):
    """'| Label | $ | (3.7 | ) | 12 | % |' -> ('Label', [-3.7])  (percent columns dropped, dashes = 0)"""
    cells = [c.strip().replace("$", "").replace("\\", "").strip() for c in line.strip().strip("|").split("|")]
    label, vals = None, []
    for i, c in enumerate(cells):
        if label is None:
            if c and not NUM.match(c) and c not in DASH: label = c
            continue
        if c in DASH: vals.append(0.0); continue
        c2 = c.replace(" ", "")
        if c2.endswith("%"): continue
        if NUM.match(c2):
            nxt = next((x for x in cells[i + 1:] if x), "")
            if nxt.startswith("%") or nxt == ")%" or (nxt == ")" and next((x for x in cells[i + 2:] if x), "").startswith("%")): continue
            v = float(c2.strip("()").replace(",", "")); vals.append(-v if c2.startswith("(") else v)
    return label, vals


def table_rows(text):
    """every table row in the document: (line_no, label, values)"""
    out = []
    for i, l in enumerate(text.split("\n")):
        if l.lstrip().startswith("|"):
            lab, v = row_vals(l)
            if lab and lab.strip() not in ("---",): out.append((i + 1, re.sub(r"\s+", " ", lab).strip(), v))
    return out


BRIDGE_HDR = re.compile(r"(previously|originally) reported", re.I)
BRIDGE_ADJ = re.compile(r"adjust|restat|revis", re.I)


def restatement_bridges(text):
    """tables that walk an old figure to a restated one ('As Previously Reported | ASU 2020-06 Adjustment | As Adjusted').
    Their columns are bases, not periods, so they must not be read as reconciliations.
    -> [(first_line, last_line, header_text)] (1-based, inclusive)"""
    L = text.split("\n"); out = []; i = 0
    while i < len(L):
        if not L[i].lstrip().startswith("|"): i += 1; continue
        j = i
        while j + 1 < len(L) and L[j + 1].lstrip().startswith("|"): j += 1
        hdr = L[i]
        if BRIDGE_HDR.search(hdr) and BRIDGE_ADJ.search(hdr.split("|", 2)[-1]):
            out.append((i + 1, j + 1, re.sub(r"\s*\|\s*", " | ", hdr.strip().strip("|")).strip()))
        i = j + 1
    return out


def page_of(text, line):
    """page number printed after `line` (the converters write the page footer as a bare number before '* * *')"""
    L = text.split("\n")
    for i in range(line, min(len(L), line + 400)):
        if re.fullmatch(r"\s*\d{1,3}\s*", L[i]) and any("* * *" in L[j] for j in range(i + 1, min(len(L), i + 4))):
            return int(L[i])
        m = re.match(r"^## Slide (\d+)", L[i])
        if m: return int(m.group(1)) - 1 if i > line else int(m.group(1))
    return None
