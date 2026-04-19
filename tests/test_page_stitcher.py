from sas_parser import PageStitcher

PS = PageStitcher()


def test_strip_footnotes_uppercase():
    result = PS._strip_footnotes(["DATA ROW", "", "FOOTNOTE LINE"])
    assert result == ["DATA ROW"]


def test_strip_footnotes_lowercase():
    result = PS._strip_footnotes(["DATA ROW", "", "n (%) = definition"])
    assert result == ["DATA ROW"]


def test_strip_footnotes_digit_starter():
    result = PS._strip_footnotes(["DATA ROW", "", "88TH EVENT IN STAGE B."])
    assert result == ["DATA ROW"]


def test_strip_footnotes_angle_bracket():
    result = PS._strip_footnotes(["DATA ROW", "", "<a> COX PROPORTIONAL HAZARDS"])
    assert result == ["DATA ROW"]


def test_strip_footnotes_with_indented_continuation():
    lines = ["DATA ROW", "", "FOOTNOTE FIRST LINE", " - indented continuation"]
    result = PS._strip_footnotes(lines)
    assert result == ["DATA ROW"]


def test_strip_footnotes_no_blank_gap_preserved():
    # Col-0 data row with no blank line before it must NOT be stripped
    lines = ["CORTICOSTEROIDS", "    ALL PARTICIPANTS  59"]
    result = PS._strip_footnotes(lines)
    assert len(result) == 2


def test_strip_footnotes_trailing_blanks_removed():
    result = PS._strip_footnotes(["DATA ROW", "", ""])
    assert result == ["DATA ROW"]


def test_same_title_normalises_whitespace():
    assert PS._same_title("TABLE 1.2.3 : FOO BAR", "TABLE  1.2.3 :  FOO  BAR")


def test_same_title_different():
    assert not PS._same_title("TABLE 1.2.3 : FOO", "TABLE 1.2.4 : FOO")
