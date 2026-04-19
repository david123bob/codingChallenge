from sas_parser import LineClassifier as LC


def test_blank():
    assert LC.is_blank("")
    assert LC.is_blank("   ")
    assert not LC.is_blank("x")


def test_full_rule():
    assert LC.is_full_rule("-" * 74)
    assert not LC.is_full_rule("-" * 59)   # too short
    assert not LC.is_full_rule("-- --")    # gaps → dash_rule, not full_rule


def test_dash_rule():
    assert LC.is_dash_rule(" --- --- ---")
    assert LC.is_dash_rule("---- ---- ----   ")
    assert not LC.is_dash_rule(" VARIABLE  LEVEL ")
    assert not LC.is_dash_rule("-" * 74)   # full_rule is NOT a dash_rule


def test_table_title():
    assert LC.is_table_title("TABLE 14.7.5.1.1 : TIME TO...")
    assert LC.is_table_title("table 1.2.3")        # case insensitive
    assert not LC.is_table_title(" TABLE ...")      # leading space → not a title


def test_footnote_line():
    assert LC.is_footnote_line("ECI = EVIDENCE OF CLINICAL IMPROVEMENT.")
    assert LC.is_footnote_line("n (%) = NUMBER OF PARTICIPANTS")   # lowercase
    assert LC.is_footnote_line("88TH EVENT IN STAGE B.")           # digit starter
    assert LC.is_footnote_line("<a> COX PROPORTIONAL HAZARDS")     # angle-bracket
    assert not LC.is_footnote_line(" INDENTED DATA ROW")           # space-starting
    assert not LC.is_footnote_line("TABLE 14.7.5.1.1 : TITLE")    # table title
    assert not LC.is_footnote_line("--- --- ---")                  # dash rule
