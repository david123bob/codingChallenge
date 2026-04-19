from sas_parser import BodyParser, BodyCell, Column

BP = BodyParser()


def test_detect_alignment_numeric():
    rows = [
        [BodyCell(""), BodyCell("100")],
        [BodyCell(""), BodyCell("200")],
        [BodyCell(""), BodyCell("50.5")],
    ]
    assert BP.detect_alignment(rows, 1) == "right"


def test_detect_alignment_ci():
    rows = [
        [BodyCell(""), BodyCell("(61.0; 71.6)")],
        [BodyCell(""), BodyCell("(50.0; 60.0)")],
    ]
    assert BP.detect_alignment(rows, 1) == "center"


def test_detect_alignment_text():
    rows = [
        [BodyCell("TREATMENT A"), BodyCell("")],
        [BodyCell("TREATMENT B"), BodyCell("")],
    ]
    assert BP.detect_alignment(rows, 0) == "left"


def test_detect_alignment_empty_column():
    rows = [[BodyCell("A"), BodyCell("")], [BodyCell("B"), BodyCell("")]]
    assert BP.detect_alignment(rows, 1) == "left"   # no values → left


def test_label_continuation_merged():
    cols = [Column(0, 40), Column(41, 60)]
    lines = [
        " LONG LABEL THAT WRAPS ONTO NEXT LINE    100",
        " CONTINUATION TEXT",
    ]
    rows = BP.extract_rows(lines, cols)
    assert len(rows) == 1
    assert "CONTINUATION TEXT" in rows[0][0].text


def test_section_header_not_merged():
    cols = [Column(0, 30), Column(31, 50)]
    lines = [
        "CORTICOSTEROIDS",
        "    ALL PARTICIPANTS              59",
    ]
    rows = BP.extract_rows(lines, cols)
    assert len(rows) == 2


def test_blank_lines_skipped():
    cols = [Column(0, 20), Column(21, 40)]
    lines = [" ROW ONE   10", "", " ROW TWO   20"]
    rows = BP.extract_rows(lines, cols)
    assert len(rows) == 2


def test_dash_rule_lines_skipped():
    cols = [Column(0, 20), Column(21, 40)]
    lines = [" ROW ONE   10", " ----------  ----------", " ROW TWO   20"]
    rows = BP.extract_rows(lines, cols)
    assert len(rows) == 2


def test_compute_rowspans_blank_col0():
    cols = [Column(0, 14), Column(15, 35), Column(36, 50)]
    lines = [
        " TREATMENT     EFG VS PBO      -0.941",
        "               PBO VS PBO       0.000",
    ]
    rows = BP.extract_rows(lines, cols)
    rows = BP.compute_rowspans(rows)
    assert rows[0][0].rowspan == 2
    assert rows[1][0].skip is True
