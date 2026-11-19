"""Release (8-K Exhibit 99.1/99.2) or 10-Q Markdown tables -> lines the matcher can use.

usage: python3 release.py FILE.md [FILE2.md ...] --out release_lines.json
Each line: id (file:line), file, line (1-based), label, values (as printed, sign applied), decimals (most printed),
factor (to the model's millions; 1 for per-share lines), kind (is / bs / cf / recon / other), table.
Each table: kind, ytd (a cash-flow table without a three-month column), header, scale, scale_known (False = no
"(In millions...)" found in the caption, the header rows or an earlier table of the file: 1.0 assumed, warn the user),
bad (rows dropped because a number-looking cell could not be read; dropped rather than let later values slide)."""
import json
import os
import re
import sys

NUM = re.compile(r"^\(?-?[\d,]*\.?\d+\)?$")
NUMLIKE = re.compile(r"^[($-]*[\d][\d,.]*\)?$")          # looks like a number, whether or not NUM can read it
HEADER_LABEL = re.compile(r"^\((in|dollars|amounts)\b", re.I)
YEAR = re.compile(r"^(19[9]\d|20\d\d|2100)$")
DASH = {"—", "-", "–"}
SCALE = [(re.compile(r"in thousands", re.I), 0.001), (re.compile(r"in billions", re.I), 1000.0),
         (re.compile(r"in millions", re.I), 1.0)]
PER_SHARE = re.compile(r"per share|\bEPS\b", re.I)
NOT_PER_SHARE = re.compile(r"^(shares|weighted)|used (to|for|in)\b", re.I)


def per_share(label):
    """EPS and dividends per share are never scaled; share counts and the income used for EPS are."""
    return bool(PER_SHARE.search(label)) and not NOT_PER_SHARE.search(label.strip())


def _cells(line):
    return [c.strip().replace("\\", "") for c in line.strip().strip("|").split("|")]


def parse_row(line):
    """'| Purchases | (21.0 | ) |' -> ('Purchases', [-21.0], 1, raw). Percent columns are dropped.
    raw = the printed number cells; None when a number-looking cell could not be read (the row must be dropped,
    or every later value would slide one column). decimals is None for a dash-only row."""
    cells = _cells(line)
    label, vals, dec, raw = None, [], None, []
    for i, c in enumerate(cells):
        c = c.replace("$", "").strip()
        if label is None:
            if c and not NUMLIKE.match(c.replace(" ", "")) and c not in DASH:
                label = c
            continue
        if not c or c in (")", "%", ")%"):
            continue
        if c in DASH:
            vals.append(0.0)
            continue
        s = c.replace(" ", "")
        if s.endswith("%"):
            continue
        nxt = next((x.strip() for x in cells[i + 1:] if x.strip() and x.strip() != ")"), "")
        if nxt.startswith("%"):
            continue
        if NUM.match(s):
            neg = s.startswith("(") or s.startswith("-")
            body = s.strip("()").lstrip("-").replace(",", "")
            v = float(body)
            d = len(body.split(".")[1]) if "." in body else 0
            dec = d if dec is None else max(dec, d)
            vals.append(-v if neg else v)
            raw.append(s)
        elif NUMLIKE.match(s):
            raw = None
            break
    return label, vals, dec, raw


def _is_header(label, raw):
    """'(In millions, except per share data) | 2026 | 2025' is a header, not a line with values [2026, 2025]."""
    if HEADER_LABEL.match(label):
        return True
    return bool(raw) and all(YEAR.match(r) for r in raw)


def _kind(labels, caption):
    low = " ".join(labels).lower()
    cap = caption.lower()
    if "total assets" in low:
        return "bs"
    if "operating activities" in low:
        return "cf"
    if "non-gaap" in cap or "non-gaap" in low or re.search(r"(^| )gaap ", low):
        return "recon"
    if re.search(r"\b(revenues?|net sales|sales)\b", low) and re.search(r"\bnet (income|loss|earnings)\b", low):
        return "is"
    if re.search(r"statements? of (operations|income|earnings)", cap) and "comprehensive" not in cap:
        return "is"
    return "other"


def _mode(ds):
    ds = [d for d in ds if d is not None]
    return max(sorted(set(ds)), key=ds.count) if ds else 0


def parse_text(text, name):
    lines = text.split("\n")
    out_t, out_l = [], []
    last_scale = None                                   # a table with no "(In ...)" of its own inherits this
    i = 0
    while i < len(lines):
        if not lines[i].lstrip().startswith("|"):
            i += 1
            continue
        start = i
        while i < len(lines) and lines[i].lstrip().startswith("|"):
            i += 1
        block = list(range(start, i))
        cap, k = [], start - 1
        while k >= 0 and len(cap) < 8 and not lines[k].lstrip().startswith("|"):
            if lines[k].strip():                         # blank lines don't use up the 8
                cap.insert(0, lines[k])                  # caption = text since the previous table only
            k -= 1
        caption = "\n".join(cap)
        rows = [(k, parse_row(lines[k])) for k in block if not re.match(r"^\|\s*-{3}", lines[k].strip())]
        bad = [k + 1 for k, (lab, v, d, raw) in rows if lab and raw is None]
        is_data = lambda lab, v, raw: lab and v and raw is not None and not _is_header(lab, raw)
        data = [(k, lab, v, d) for k, (lab, v, d, raw) in rows if is_data(lab, v, raw)]
        header = "\n".join(lines[k] for k, (lab, v, d, raw) in rows if not is_data(lab, v, raw) and k + 1 not in bad)
        scale = next((f for rx, f in SCALE if rx.search(header)), None)
        if scale is None:
            scale = next((f for rx, f in SCALE if rx.search(caption)), None)
        known = scale is not None or last_scale is not None
        scale = scale if scale is not None else (last_scale if last_scale is not None else 1.0)
        if known:
            last_scale = scale
        if not data:
            continue
        kind = _kind([lab for _, lab, _, _ in data], caption)
        ytd = kind == "cf" and not re.search(r"three months", header, re.I)
        common = _mode([d for _, _, _, d in data])
        t = len(out_t)
        out_t.append({"kind": kind, "ytd": ytd, "header": header, "scale": scale, "scale_known": known,
                      "bad": bad, "start": start + 1})
        for k, lab, v, d in data:
            out_l.append({"id": f"{name}:{k + 1}", "file": name, "line": k + 1, "label": lab, "values": v,
                          "decimals": common if d is None else d, "factor": 1.0 if per_share(lab) else scale,
                          "kind": kind, "table": t})
    return {"tables": out_t, "lines": out_l}


def tolerance(line):
    """Half a unit of the printed precision, in the model's units."""
    return 0.5 * 10 ** -line["decimals"] * line["factor"] + 1e-9


def parse_files(paths, root=None):
    out = {"tables": [], "lines": []}
    for p in paths:
        name = os.path.relpath(p, root) if root else os.path.basename(p)
        r = parse_text(open(p, encoding="utf-8").read(), name)
        off = len(out["tables"])
        for l in r["lines"]:
            l["table"] += off
        out["tables"] += r["tables"]
        out["lines"] += r["lines"]
    return out


if __name__ == "__main__":
    args = sys.argv[1:]
    out = args[args.index("--out") + 1]
    root = args[args.index("--root") + 1] if "--root" in args else None
    files = [a for k, a in enumerate(args) if not a.startswith("--") and args[k - 1] not in ("--out", "--root")]
    json.dump(parse_files(files, root), open(out, "w"), indent=1)
    print(out)
