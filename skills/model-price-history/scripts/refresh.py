"""Refresh: rebuild the three tabs with new prices and keep what the user and /research-filings added to them.

usage: python3 refresh.py extract --model M.xlsx --work W [--handoff <model_handoff.json>]
       python3 refresh.py restore --model M.xlsx --built B.xlsx --work W --out OUT.xlsx
extract (before build.py --refresh) writes W/carry.json from the user's model:
  - the tabs' positions in the tab order;
  - every drawing on Idio Chart that the build does not make: not one of its four charts ('Chart 1'..'Chart 4'), and
    not a /research-filings note ('P1 ...') when its handoff file exists (handoff.py redraws those by date);
  - every typed note: Idio Chart 'Your annotation' (keyed by the row's date), Px Events annotation (keyed by event
    date and name).
restore (after build.py --refresh) writes OUT = the built file plus the carried shapes and notes, with the three tabs
back in their places. It first checks what other tabs read from the three tabs (exit 3 = stop, nothing written):
  - a single cell: its column header and its row (the date in Px Data; the period and event in Px Events) must be
    the same as before, so the reference still reads the same thing;
  - a range or whole column: its column header must be the same; a range that ends above the new last row is a
    warning (it misses the new days), not a stop.
Prints a JSON summary: shapes carried, notes placed and not placed (their row left the table), reference warnings."""
import argparse
import datetime as dt
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from xlsx import NS_REL, Package, colnum, esc, new_rid, relative, relpath_of, resolve, unesc  # noqa: E402

TABS = ("Idio Chart", "Px Events", "Px Data")
BUILD_CHARTS = {f"Chart {k}" for k in range(1, 5)}
OWN = "P1 "                              # /research-filings' shapes
HEADER_ROW = {"Px Data": 4, "Px Events": 4}
ANCHOR = re.compile(r"<(?:xdr:)?(twoCellAnchor|oneCellAnchor|absoluteAnchor)\b.*?</(?:xdr:)?\1>", re.S)
CELL = re.compile(r'<c r="([A-Z]+)(\d+)"([^>]*?)(?:/>|>(.*?)</c>)', re.S)
REF = re.compile(r"'?(Idio Chart|Px Events|Px Data)'?!(\$?[A-Z]+)(\$?\d+)?(?::(\$?[A-Z]+)(\$?\d+)?)?")


# ------------------------------------------------------------------ reading the package
def _strings(pkg):
    if "xl/sharedStrings.xml" not in pkg.parts:
        return []
    x = pkg.text("xl/sharedStrings.xml")
    return [unesc("".join(re.findall(r"<t[^>]*>(.*?)</t>", si, re.S))) for si in re.findall(r"<si>(.*?)</si>", x, re.S)]


def cells(pkg, part, ss=None):
    """{ref: (kind, content, cached)}: kind 'f' (formula text; cached value or None), 's' text, 'n' number."""
    ss = _strings(pkg) if ss is None else ss
    out = {}
    for col, row, attrs, body in CELL.findall(pkg.text(part)):
        body = body or ""
        f = re.search(r"<f\b[^>]*>(.*?)</f>|<f\b[^>]*/>", body, re.S)
        v = re.search(r"<v>(.*?)</v>", body, re.S)
        t = (re.search(r'\bt="(\w+)"', attrs) or [None, None])[1]
        if t == "inlineStr":
            val = ("s", unesc("".join(re.findall(r"<t[^>]*>(.*?)</t>", body, re.S))))
        elif v and t == "s":
            val = ("s", ss[int(v.group(1))])
        elif v and t in ("str", "e"):
            val = ("s", unesc(v.group(1)))
        elif v:
            val = ("n", float(v.group(1)))
        else:
            val = None
        if f:
            cached = val[1] if val else None
            out[col + row] = ("f", unesc(f.group(1) or ""), cached)
        elif val:
            out[col + row] = (val[0], val[1], val[1])
    return out


def sheet_parts(pkg):
    return {name: part for name, _, _, part in pkg.sheets()}


def drawing_of(pkg, part):
    for _, (typ, tgt) in pkg.rels(relpath_of(part)).items():
        if typ.endswith("/drawing"):
            return resolve(part, tgt)
    return None


def tab_parts(pkg):
    """Every part hanging off the three tabs (sheet, drawing, charts, comments, images) and their rels."""
    out = set()
    for name, part in sheet_parts(pkg).items():
        if name not in TABS:
            continue
        todo = [part]
        out |= {part, relpath_of(part)}
        while todo:
            p = todo.pop()
            for _, (_, tgt) in pkg.rels(relpath_of(p)).items():
                q = resolve(p, tgt)
                if q not in out:
                    out |= {q, relpath_of(q)}
                    todo.append(q)
    return out


def strip_id(a):
    return re.sub(r'(<(?:xdr:)?cNvPr\b[^>]*\bid=")\d+', r"\g<1>", a)


def _iso(serial):
    return (dt.date(1899, 12, 30) + dt.timedelta(days=int(serial))).isoformat()


def _text(c):
    return (c[2] if c and c[0] == "f" else c[1] if c else None)


# ------------------------------------------------------------------ extract
def _notes(cs, head_word, key_heads):
    """Rows under a header row holding `head_word`: {key: note} for every non-empty note. Keys from key_heads columns
    (dates as ISO)."""
    heads = {}
    for ref, c in cs.items():
        if c[0] == "s" and isinstance(c[1], str):
            col, row = re.match(r"([A-Z]+)(\d+)$", ref).groups()
            heads.setdefault(int(row), {})[c[1].strip()] = col
    out = []
    for hr, hs in heads.items():
        note_col = next((col for h, col in hs.items() if head_word in h.lower()), None)
        key_cols = [hs.get(k) for k in key_heads]
        if not note_col or None in key_cols:
            continue
        r = hr + 1
        while f"{key_cols[0]}{r}" in cs:              # the table ends at its first row with no key
            note = _text(cs.get(f"{note_col}{r}"))
            if isinstance(note, str) and note.strip():
                key = []
                for k in key_cols:
                    v = _text(cs.get(f"{k}{r}"))
                    key.append(_iso(v) if isinstance(v, float) else v)
                out.append({"key": key, "note": note, "from": f"{note_col}{r}"})
            r += 1
    return out


def extract(model, handoff=None):
    pkg = Package(model)
    names = [s[0] for s in pkg.sheets()]
    missing = [t for t in TABS if t not in names]
    if missing:
        raise SystemExit(f"refresh needs the three tabs; missing {missing}. Run a normal build instead.")
    parts = sheet_parts(pkg)
    ss = _strings(pkg)
    out = {"positions": {t: names.index(t) for t in TABS}, "order": names, "handoff": bool(handoff), "shapes": [],
           "not_carried": [], "notes": {}}
    d = drawing_of(pkg, parts["Idio Chart"])
    if d:
        drels = pkg.rels(relpath_of(d))
        for m in ANCHOR.finditer(pkg.text(d)):
            a = m.group(0)
            name = (re.search(r'<(?:xdr:)?cNvPr\b[^>]*\bname="([^"]*)"', a) or [None, ""])[1]
            is_chart = "drawingml/2006/chart" in a
            if is_chart and unesc(name) in BUILD_CHARTS:
                continue
            if handoff and unesc(name).startswith(OWN):
                continue
            rids = re.findall(r'r:(?:embed|id|link)="([^"]+)"', a)
            if is_chart or any(not drels.get(r, ("", ""))[0].endswith("/image") for r in rids):
                out["not_carried"].append(f"{unesc(name)} (a chart or linked object of your own: redraw it)")
                continue
            media = {r: resolve(d, drels[r][1]) for r in rids}
            out["shapes"].append({"name": unesc(name), "xml": a, "media": media})
    out["notes"]["Idio Chart"] = _notes(cells(pkg, parts["Idio Chart"], ss), "your annotation", ["Date"])
    out["notes"]["Px Events"] = _notes(cells(pkg, parts["Px Events"], ss), "annotation", ["Event date", "Event"])
    return out


# ------------------------------------------------------------------ references from other tabs
def references(pkg):
    """[(tab, cell, target tab, col1, row1, col2, row2)] for every reference from another tab into the three."""
    out = []
    for name, part in sheet_parts(pkg).items():
        if name in TABS:
            continue
        for ref, c in cells(pkg, part).items():
            if c[0] != "f":
                continue
            for m in REF.finditer(c[1].replace("&apos;", "'")):
                t, c1, r1, c2, r2 = m.groups()
                strip = lambda s: s.replace("$", "") if s else None
                out.append((name, ref, t, strip(c1), strip(r1), strip(c2), strip(r2)))
    return out


def _row_key(cs, tab, row):
    if tab == "Px Data":
        return (_text(cs.get(f"A{row}")),)
    if tab == "Px Events":
        return tuple(_text(cs.get(f"{k}{row}")) for k in ("A", "J", "L"))
    return None


def check_refs(old, new, last_rows):
    """(stops, warnings) for the references other tabs hold into the three tabs."""
    po, pn = sheet_parts(old), sheet_parts(new)
    co = {t: cells(old, po[t]) for t in TABS}
    cn = {t: cells(new, pn[t]) for t in TABS}
    stops, warns, seen = {}, [], set()
    show = lambda v: "empty" if v in (None, "") else f"'{v}'"
    for tab, ref, t, c1, r1, c2, r2 in references(old):
        where = f"{tab} reads '{t}'!{c1}{r1 or ''}{':' + c2 + (r2 or '') if c2 else ''}"
        hr = HEADER_ROW.get(t)
        single = c2 is None and r1
        if single and (hr is None or int(r1) <= hr):
            if _text(co[t].get(c1 + r1)) != _text(cn[t].get(c1 + r1)):
                stops.setdefault(f"{where}: the cell now holds something else", []).append(ref)
            continue
        for col in {c1, c2 or c1}:
            if hr and _text(co[t].get(f"{col}{hr}")) != _text(cn[t].get(f"{col}{hr}")):
                stops.setdefault(f"{where}: column {col} was {show(_text(co[t].get(f'{col}{hr}')))}, now "
                                 f"{show(_text(cn[t].get(f'{col}{hr}')))}", []).append(ref)
        if single:
            if _row_key(co[t], t, int(r1)) != _row_key(cn[t], t, int(r1)):
                stops.setdefault(f"{where}: row {r1} was {_row_key(co[t], t, int(r1))}, now "
                                 f"{_row_key(cn[t], t, int(r1))}", []).append(ref)
        elif r2 and t in last_rows and int(r2) < last_rows[t] and (tab, t, c1, r2) not in seen:
            seen.add((tab, t, c1, r2))
            warns.append(f"{tab} reads '{t}'!{c1}{r1}:{c2}{r2}, but the data now runs to row {last_rows[t]}: "
                         "those cells miss the new days")
    out = []
    for k, v in stops.items():
        v = list(dict.fromkeys(v))
        out.append(f"{k} ({len(v)} cell{'s' if len(v) > 1 else ''}: {', '.join(v[:5])}{', ...' if len(v) > 5 else ''})")
    return out, warns


# ------------------------------------------------------------------ restore
def _set_text(xml, ref, text):
    """Put an inline string in `ref` (replacing an empty cell, keeping its style)."""
    col, row = re.match(r"([A-Z]+)(\d+)$", ref).groups()
    cell = f'<is><t xml:space="preserve">{esc(text)}</t></is>'
    m = re.search(rf'<c r="{ref}"([^>]*?)(?:/>|>.*?</c>)', xml, re.S)
    if m:
        st = (re.search(r'\bs="(\d+)"', m.group(1)) or [None, None])[1]
        new = f'<c r="{ref}"{f" s={chr(34)}{st}{chr(34)}" if st else ""} t="inlineStr">{cell}</c>'
        return xml[:m.start()] + new + xml[m.end():]
    new = f'<c r="{ref}" t="inlineStr">{cell}</c>'
    rm = re.search(rf'<row r="{row}"[^>]*?(?:/>|>(.*?)</row>)', xml, re.S)
    if not rm:
        rows = [(int(x.group(1)), x.start()) for x in re.finditer(r'<row r="(\d+)"', xml)]
        at = next((p for r, p in rows if r > int(row)), xml.index("</sheetData>"))
        return xml[:at] + f'<row r="{row}">{new}</row>' + xml[at:]
    if rm.group(0).endswith("/>"):
        return xml[:rm.start()] + rm.group(0)[:-2] + f">{new}</row>" + xml[rm.end():]
    body = rm.group(1)
    for cm in re.finditer(r'<c r="([A-Z]+)\d+"', body):
        if colnum(cm.group(1)) > colnum(col):
            at = rm.start(1) + cm.start()
            return xml[:at] + new + xml[at:]
    at = rm.end(1)
    return xml[:at] + new + xml[at:]


def place_notes(carried, rows):
    """carried: [{key, note}], rows: {tuple key: cell ref}. Returns (placed {ref: note}, unplaced [notes])."""
    placed, unplaced = {}, []
    for n in carried:
        ref = rows.get(tuple(n["key"]))
        (placed.__setitem__(ref, n["note"]) if ref and ref not in placed else unplaced.append(n))
    return placed, unplaced


def _reorder(pkg, order):
    """Put the workbook's tabs in `order` (names); local defined names and the active tab follow their sheets."""
    wb = pkg.text("xl/workbook.xml")
    tags = re.findall(r"<sheet\b[^>]*/>", wb)
    by_name = {unesc(re.search(r'name="([^"]*)"', t).group(1)): t for t in tags}
    now = [unesc(re.search(r'name="([^"]*)"', t).group(1)) for t in tags]
    order = [n for n in order if n in by_name] + [n for n in now if n not in order]
    pos = {now.index(n): k for k, n in enumerate(order)}
    body = "".join(by_name[n] for n in order)
    wb = re.sub(r"(<sheets>).*?(</sheets>)", lambda m: m.group(1) + body + m.group(2), wb, flags=re.S)
    wb = re.sub(r'(<definedName\b[^>]*localSheetId=")(\d+)(")', lambda m: f"{m.group(1)}{pos[int(m.group(2))]}{m.group(3)}", wb)
    wb = re.sub(r'(activeTab=")(\d+)(")', lambda m: f"{m.group(1)}{pos.get(int(m.group(2)), 0)}{m.group(3)}", wb)
    pkg.put("xl/workbook.xml", wb)


def restore(model, built, work, out):
    C = json.load(open(os.path.join(work, "carry.json")))
    L = json.load(open(os.path.join(work, "layout.json")))
    old, pkg = Package(model), Package(built)
    last = {"Px Data": L["rows"]["RN"], "Px Events": max(L["rows"]["QN"], L["rows"]["EVN"])}
    stops, warns = check_refs(old, pkg, last)
    if stops:
        print(json.dumps({"status": "references", "stops": stops[:50], "warnings": warns}, indent=1))
        raise SystemExit(3)
    parts = sheet_parts(pkg)
    rep = {"status": "restored", "shapes": 0, "not_carried": C["not_carried"], "notes_placed": 0, "notes_not_placed": [],
           "reference_warnings": warns}
    # shapes: appended to the new Idio Chart drawing as they were (same cells, so the same spot); ids renumbered
    d = drawing_of(pkg, parts["Idio Chart"])
    if C["shapes"]:
        x = pkg.text(d)
        ids = [int(i) for i in re.findall(r'<(?:xdr:)?cNvPr\b[^>]*\bid="(\d+)"', x)]
        nxt = max(ids + [1]) + 1
        add = []
        for s in C["shapes"]:
            a = s["xml"]
            for rid, src in s["media"].items():
                if src not in pkg.parts:
                    pkg.put(src, old.parts[src])
                rels = pkg.rels(relpath_of(d))
                rid_new = new_rid(rels)
                rels[rid_new] = (f"{NS_REL}/image", relative(d, src))
                pkg.write_rels(relpath_of(d), rels)
                a = re.sub(rf'(r:(?:embed|id|link)="){re.escape(rid)}"', lambda m: f'{m.group(1)}{rid_new}"', a)
            a = re.sub(r'(<(?:xdr:)?cNvPr\b[^>]*\bid=")\d+(")', lambda m: f"{m.group(1)}{nxt}{m.group(2)}", a, count=1)
            nxt += 1
            add.append(a)
        root = re.search(r"<(?:xdr:)?wsDr\b[^>]*>", x).group(0)
        for ns in ('xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"',
                   'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'):
            if ns.split("=")[0] not in root and ns.split("=")[0].split(":")[1] + ":" in "".join(add):
                x = x.replace(root, root[:-1] + " " + ns + ">", 1)
                root = root[:-1] + " " + ns + ">"
        end = x.rindex("</")
        pkg.put(d, x[:end] + "".join(add) + x[end:])
        rep["shapes"] = len(add)
    # notes: into the rows that hold the same date (Idio Chart) or the same event (Px Events)
    targets = {"Idio Chart": {(iso,): f"AB{r}" for r, iso in L["idio_rows"]},
               "Px Events": {(iso, name): f"{L['events']['e_note']}{r}" for r, iso, name in L["event_rows"]}}
    for tab in ("Idio Chart", "Px Events"):
        placed, unplaced = place_notes(C["notes"].get(tab, []), targets[tab])
        x = pkg.text(parts[tab])
        for ref, note in placed.items():
            x = _set_text(x, ref, note)
        pkg.put(parts[tab], x)
        rep["notes_placed"] += len(placed)
        rep["notes_not_placed"] += [f"{tab} {'/'.join(map(str, n['key']))}: {n['note']}" for n in unplaced]
    _reorder(pkg, C["order"])
    pkg.finish()
    pkg.save(out)
    return rep


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["extract", "restore"])
    ap.add_argument("--model", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--built")
    ap.add_argument("--out")
    ap.add_argument("--handoff", help="/research-filings' model_handoff.json, if it exists")
    a = ap.parse_args()
    if a.cmd == "extract":
        h = a.handoff if a.handoff and os.path.exists(a.handoff) else None
        C = extract(a.model, h)
        json.dump(C, open(os.path.join(a.work, "carry.json"), "w"), indent=1)
        print(json.dumps({"shapes": [s["name"] for s in C["shapes"]], "not_carried": C["not_carried"],
                          "notes": {k: len(v) for k, v in C["notes"].items()}, "positions": C["positions"],
                          "research_shapes_redrawn_by_handoff": bool(h)}, indent=1))
    else:
        print(json.dumps(restore(a.model, a.built, a.work, a.out), indent=1))
