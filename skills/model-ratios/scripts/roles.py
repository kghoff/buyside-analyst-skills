"""Find MOD's rows by their labels, using model-historicals's own ROLE_PATTERNS so both skills always agree on what a
row is. build.py is loaded by file path (not via sys.path) so model-historicals's other scripts can't shadow ours."""
import importlib.util
import os
import re

MB = os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "..", "model-historicals", "scripts", "build.py")
if not os.path.exists(MB):
    raise SystemExit(f"model-historicals is not installed ({MB} missing); model-ratios reads its row labels.")
_spec = importlib.util.spec_from_file_location("model_base_build", MB)
_mb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mb)
ROLE_PATTERNS, norm, fmt_num = _mb.ROLE_PATTERNS, _mb.norm, _mb.fmt


ADDONS = ("non-gaap", "key operating metrics")   # sections /model-kpis adds to MOD; they carry their own analysis rows


# sections /model-ratios inserts (current names, plus the ANALYZED-tab era's, so --replace finds both)
OURS = ("roic", "leverage & cash conversion", "free cash flow", "key metrics & ratios")


def section_rows(ws, prefixes):
    """rows of the column-A sections whose title starts with one of prefixes (title row up to the next heading)"""
    out, inside = set(), False
    for r in range(1, ws.max_row + 1):
        a = norm(ws.cell(r, 1).value)
        if a: inside = a.startswith(prefixes)
        if inside: out.add(r)
    return out


def addon_rows(ws):
    """rows of the sections /model-kpis inserts into MOD"""
    return section_rows(ws, ADDONS)


def analysis_section_rows(ws):
    """rows of the ROIC / leverage / FCF sections this skill inserts into MOD"""
    return section_rows(ws, OURS)


def find_roles(ws):
    """-> (roles {role: row}, section starts {IS, BS, CF: row}, opex line rows), same search as model-historicals build.py."""
    maxr = ws.max_row
    starts = {}
    for r in range(1, maxr + 1):
        t = norm(ws.cell(r, 1).value)
        if t.startswith("income statement"): starts.setdefault("IS", r)
        if t.startswith("balance sheet"): starts.setdefault("BS", r)
        if t.startswith("cash flow"): starts.setdefault("CF", r)
    starts.setdefault("IS", 2)                    # KPI rows may sit above the income statement
    bounds = {"IS": (starts["IS"], starts["BS"]), "BS": (starts["BS"], starts["CF"]), "CF": (starts["CF"], maxr + 1)}
    roles, skip = {}, addon_rows(ws) | analysis_section_rows(ws)
    for sect, (r0, r1) in bounds.items():
        taken = set()
        for s, role, pat in ROLE_PATTERNS:
            if s != sect or role in roles: continue
            for r in range(r0, r1):
                lab = norm(ws.cell(r, 2).value)
                if r in taken or r in skip or not lab or not re.search(pat, lab): continue
                if role == "OTHFIN" and r < roles.get("CFI", 0): continue
                roles[role] = r
                taken.add(r)
                break
    opex = []
    if "GP" in roles and "TOPEX" in roles:
        hdr = next((r for r in range(roles["GP"] + 1, roles["TOPEX"]) if "operating expenses" in norm(ws.cell(r, 2).value)), roles["GP"])
        opex = [r for r in range(hdr + 1, roles["TOPEX"]) if norm(ws.cell(r, 2).value)]
    return roles, starts, opex
