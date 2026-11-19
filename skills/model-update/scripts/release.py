"""Release (8-K Exhibit 99.1/99.2) or 10-Q Markdown tables -> lines the matcher can use.

usage: python3 release.py FILE.md [FILE2.md ...] --out release_lines.json
Each line: id (file:line), file, line (1-based), label, values (as printed, sign applied), decimals (most printed),
factor (to the model's millions; 1 for per-share lines), kind (is / bs / cf / recon / other), table.
Each table: kind, ytd (a cash-flow table without a three-month column), header, scale."""
import json
import os
import re
import sys

NUM = re.compile(r"^\(?-?[\d,]*\.?\d+$")
DASH = {"—", "-", "–"}
SCALE = [(re.compile(r"in thousands", re.I), 0.001), (re.compile(r"in billions", re.I), 1000.0),
         (re.compile(r"in millions", re.I), 1.0)]
PER_SHARE = re.compile(r"per share|\bEPS\b", re.I)


def _cells(line):
    return [c.strip().replace("\\", "") for c in line.strip().strip("|").split("|")]


def parse_row(line):
    """'| Purchases | (21.0 | ) |' -> ('Purchases', [-21.0], 1). Percent columns are dropped."""
    cells = _cells(line)
    label, vals, dec = None, [], 0
    for i, c in enumerate(cells):
        c = c.replace("$", "").strip()
        if label is None:
            if c and not NUM.match(c.replace(" ", "")) and c not in DASH:
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
            body = s.strip("(").lstrip("-").replace(",", "")
            v = float(body)
            dec = max(dec, len(body.split(".")[1]) if "." in body else 0)
            vals.append(-v if neg else v)
    return label, vals, dec


def _kind(labels, caption):
    low = " ".join(labels).lower()
    cap = caption.lower()
    if "total assets" in low:
        return "bs"
    if "operating activities" in low:
        return "cf"
    if "non-gaap" in cap or "non-gaap" in low or re.search(r"(^| )gaap ", low):
        return "recon"
    if "revenue" in low and "net income" in low:
        return "is"
    return "other"


def parse_text(text, name):
    lines = text.split("\n")
    out_t, out_l = [], []
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
            cap.insert(0, lines[k])                      # caption = text since the previous table only
            k -= 1
        caption = "\n".join(cap)
        rows = [(k, parse_row(lines[k])) for k in block if not re.match(r"^\|\s*-{3}", lines[k].strip())]
        data = [(k, lab, v, d) for k, (lab, v, d) in rows if lab and v]
        header = "\n".join(lines[k] for k, (lab, v, d) in rows if not (lab and v))
        if not data:
            continue
        scale = next((f for rx, f in SCALE if rx.search(caption)), 1.0)
        kind = _kind([lab for _, lab, _, _ in data], caption)
        ytd = kind == "cf" and not re.search(r"three months", header, re.I)
        t = len(out_t)
        out_t.append({"kind": kind, "ytd": ytd, "header": header, "scale": scale, "start": start + 1})
        for k, lab, v, d in data:
            out_l.append({"id": f"{name}:{k + 1}", "file": name, "line": k + 1, "label": lab, "values": v,
                          "decimals": d, "factor": 1.0 if PER_SHARE.search(lab) else scale, "kind": kind, "table": t})
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
