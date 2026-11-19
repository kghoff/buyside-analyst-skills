"""Test helper standing in for the user's edit in Excel: types one cell of one tab in the raw XML (the rest of the
file byte for byte). Test workbooks only, never a user's model."""
import os
import re

from xlsx import Package, esc


def set_text(path, tab, ref, text):
    """Rewrite cell `ref` on `tab` as an inline string, keeping its style."""
    pkg = Package(path)
    part = {s[0]: s for s in pkg.sheets()}[tab][3]
    xml = pkg.text(part)
    m = re.search(rf'<c r="{ref}"(?P<a>[^>]*?)(?:/>|>.*?</c>)', xml, re.S)
    if m is None:
        raise KeyError(f"{tab}!{ref} has no cell to edit")
    a = re.sub(r'\s+t="[^"]*"', "", m.group("a"))
    new = f'<c r="{ref}"{a} t="inlineStr"><is><t xml:space="preserve">{esc(text)}</t></is></c>'
    pkg.put(part, xml[:m.start()] + new + xml[m.end():])
    pkg.save(path + ".tmp")
    os.replace(path + ".tmp", path)
