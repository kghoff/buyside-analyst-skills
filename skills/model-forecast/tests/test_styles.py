import re

from xlsx import Styles

XML = ('<styleSheet><numFmts count="1"><numFmt numFmtId="164" formatCode="0.0%"/></numFmts>'
       '<fonts count="2"><font><sz val="12"/><color rgb="FF000000"/><name val="Aptos Narrow"/></font>'
       '<font><b/><sz val="11"/><color theme="1"/><name val="Calibri"/></font></fonts>'
       '<cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
       '<xf numFmtId="164" fontId="1" fillId="0" borderId="2" xfId="0" applyNumberFormat="1"><alignment horizontal="right"/></xf>'
       '</cellXfs></styleSheet>')


def test_recolor_keeps_the_number_format_border_and_font_but_changes_only_the_color():
    # a forecast cell must look like the user's history cell in the same row (same % format, bold, border) - only the
    # blue/green/black convention differs
    st = Styles(XML)
    k = st.recolor(1, "FF0000FF")
    assert k == 2 and st.recolor(1, "FF0000FF") == 2          # cached: one new xf per (xf, color)
    out = st.render()
    xfs = re.findall(r"<xf\b[^>]*?(?:/>|>.*?</xf>)", re.search(r"<cellXfs.*?</cellXfs>", out, re.S).group(0), re.S)
    new = xfs[2]
    assert 'numFmtId="164"' in new and 'borderId="2"' in new and "<alignment" in new and 'fontId="2"' in new
    fonts = re.findall(r"<font>.*?</font>", out, re.S)
    assert len(fonts) == 3 and "<b/>" in fonts[2] and 'rgb="FF0000FF"' in fonts[2] and "theme" not in fonts[2]
    assert xfs[1] == '<xf numFmtId="164" fontId="1" fillId="0" borderId="2" xfId="0" applyNumberFormat="1"><alignment horizontal="right"/></xf>'
    assert st.recolor(1, "FF008000") == 3


def test_recolor_on_a_rerun_reuses_the_style_it_added_before():
    # every rebuild would otherwise append another font + xf to the user's styles.xml
    st = Styles(XML)
    k = st.recolor(1, "FF0000FF")
    once = st.render()
    st2 = Styles(once)
    assert st2.recolor(1, "FF0000FF") == k and st2.render() == once
