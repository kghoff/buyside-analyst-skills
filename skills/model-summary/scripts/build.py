# skills/model-summary/scripts/build.py
"""Build the SUM tab into a copy of the user's model. SUM goes first (left of MOD); every number links to its home
tab; the yellow boxes are write-pitch's; a rerun keeps whatever was typed in them (found by label).

usage: python3 build.py --model M --work W --ticker T --out W/out.xlsx
Prints the report's facts as JSON. Writes W/layout.json and W/inputs_written.next.json (copyover.py promotes it)."""
import argparse
import datetime as dt
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "lib"))
import openpyxl  # noqa: E402

import adv as advmod  # noqa: E402
import layout  # noqa: E402
import links  # noqa: E402
from tabkit import W, changed_parts, move_first, resolve_values, tab_parts  # noqa: E402
from xlsx import CT, Package, Styles, comments_parts  # noqa: E402

TAB = "SUM"


def defaults(L):
    return {"Action": "=" + L["val"]["action"], "Buy price": "", "No-brainer price": "", layout.BAND: 0.03,
            "Mgmt contact": "", "Thesis Summary": "", "Trading Plan": "", "Valuation Thoughts": ""}


def read_existing(model):
    """{label: value now} for every yellow cell on the current SUM tab (None: no SUM tab)."""
    wb = openpyxl.load_workbook(model, read_only=True)
    if TAB not in wb.sheetnames:
        return None
    g = links.grid(wb[TAB])
    out = {}
    for (r, c), v in g.items():
        if isinstance(v, str) and v.strip() in layout.INPUT_OFFSET:
            dc, dr = layout.INPUT_OFFSET[v.strip()]
            out[v.strip()] = g.get((r + dr, c + dc))
    return out


def write_tab(pkg, w):
    """Replace SUM whole, put it first, attach the notes."""
    if TAB in [s[0] for s in pkg.sheets()]:
        pkg.remove_sheet(TAB)
    part = pkg.add_sheet(TAB, "")
    move_first(pkg, TAB)
    lrid = None
    if w.notes:
        pkg.content_default("vml", "application/vnd.openxmlformats-officedocument.vmlDrawing")
        ids = [int(x) for p, data in pkg.parts.items() if p.endswith(".vml")
               for d in re.findall(rb'<o:idmap v:ext="edit" data="([\d,\s]+)"', data) for x in re.findall(rb"\d+", d)]
        cn, vn = pkg.free("xl/comments{}.xml"), pkg.free("xl/drawings/vmlDrawing{}.vml")
        cx, vml = comments_parts(w.notes, max(ids + [0]) + 1)
        pkg.put(f"xl/comments{cn}.xml", cx)
        pkg.put(f"xl/drawings/vmlDrawing{vn}.vml", vml)
        lrid = pkg.attach(part, "vml", f"xl/drawings/vmlDrawing{vn}.vml")
        pkg.attach(part, "comments", f"xl/comments{cn}.xml", CT["comments"])
    pkg.put(part, w.sh.xml(None, lrid))
    return part


def build(model, work, ticker, out, research_dir, fetch=advmod.yahoo, today=None):
    if os.path.abspath(out) == os.path.abspath(model):
        raise SystemExit("model-summary: --out must be a copy, not the model itself.")
    os.makedirs(work, exist_ok=True)
    L = links.collect(model)
    A = advmod.adv(model, L["mult"]["adv"], research_dir, ticker, work, fetch)
    p = os.path.join(work, "inputs_written.json")
    written = json.load(open(p)) if os.path.exists(p) else None
    existing = read_existing(model)
    warnings = []
    if existing is not None and written is None:
        warnings.append("There is no inputs_written.json (the record of what the last build wrote), so every yellow "
                        "cell that differs from the default is treated as typed by you or write-pitch.")
    used, users = resolve_values(existing, written, defaults(L))

    pkg = Package(model)
    st = Styles(pkg.text("xl/styles.xml"))
    old = tab_parts(pkg, TAB)
    w = W(st, users)
    R = layout.lay_out(w, L, A, used, ticker, today or dt.date.today())
    w.sh.comments = w.notes
    w.sh.widths.update({1: 2, 2: 36, 3: 14, 4: 11, 5: 30, **{k: 11 for k in range(6, 15)}, 15: 2, 16: 24,
                        **{k: 11 for k in range(17, 22)}, 22: 2, **{k: 11 for k in range(23, 28)}})
    part = write_tab(pkg, w)
    pkg.put("xl/styles.xml", st.render())
    pkg.finish()
    pkg.save(out)
    import notebox
    notebox.fix(out, out, since=model)
    bad = changed_parts(model, out, old | tab_parts(Package(out), TAB) | {part})
    if bad:
        os.remove(out)
        raise SystemExit("model-summary: the build changed parts it must not touch: " + ", ".join(bad))

    no_street = [y for y in L["mod"]["years"] if y.endswith("E") and y not in L["mult"]["street"]]
    if no_street:
        warnings.append("No Street EPS on the Multiples forward table for " + ", ".join(no_street) + ": those Street "
                        "rows show n/a.")
    if "Action" in users:
        warnings.append(f"Action holds {used['Action']!r}, typed over Valuation's verdict; it no longer follows "
                        "Valuation. Clear the cell and rerun to link it again.")
    json.dump({"refs": R, "kinds": w.kinds, "notes": w.notes, "inputs": w.inputs, "users": sorted(users),
               "irr_years": L["val"]["irr"]["years"]["ref"], "warnings": warnings},
              open(os.path.join(work, "layout.json"), "w"), indent=0, default=str)
    json.dump({lab: {"value": v, "user": lab in users} for lab, v in used.items()},
              open(os.path.join(work, "inputs_written.next.json"), "w"), indent=1, default=str)
    return {"tab": TAB, "primary": L["val"]["kind"], "ntm_quarters": L["mod"]["ntm_quarters"],
            "years": L["mod"]["years"], "street_years": sorted(L["mult"]["street"]),
            "tree": [b["name"] for b in L["val"]["tree"]], "ladder_rungs": len(L["val"]["ladder"]),
            "adv": {"route": A["route"], "note": A["note"]}, "users_kept": sorted(users),
            "action_follows_valuation": "Action" not in users, "warnings": warnings}


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--model", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--ticker", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    import settings
    print(json.dumps(build(a.model, a.work, a.ticker.upper(), a.out, settings.research_dir()), indent=1, default=str))


if __name__ == "__main__":
    main()
