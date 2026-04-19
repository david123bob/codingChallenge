from sas_parser import ColumnDetector, PageStitcher

CD = ColumnDetector()

# Leaf dash rule from small.txt
SMALL_RULE = (
    " -------------------------------------------------- "
    "---------------------- ---------------------- ----------------------"
)


def test_dash_runs_count():
    runs = CD.dash_runs(SMALL_RULE)
    assert len(runs) == 4


def test_dash_runs_first_position():
    runs = CD.dash_runs(SMALL_RULE)
    assert runs[0][0] == 1   # first run starts after leading space


def test_leaf_columns_count():
    header_lines = [
        "                                                    EFG PH20 SC"
        "            PBO PH20 SC            ALL PARTICIPANTS",
        " ANALYSIS SET                                         n"
        "                      n                      n",
        SMALL_RULE,
    ]
    cols = CD.leaf_columns(header_lines)
    assert len(cols) == 4   # implicit col-0 + 3 explicit


def test_leaf_rule_picks_most_runs():
    lines = [
        "          PARENT A           PARENT B",
        "          ----------  -------  -------",   # 2 runs — intermediate
        " COL1     COL2        COL3     COL4",
        " -------- ----------  -------  -------",   # 4 runs — leaf
    ]
    idx = PageStitcher()._find_leaf_rule_idx(lines)
    assert idx == 3


def test_leaf_rule_tie_prefers_first():
    lines = [
        " --------------------",              # 1 run — column ruler
        " PARTICIPANTS WITH CONFIRMED ECI",
        " -------------------------------",  # 1 run — section-header dash
        " <= WEEK 4   111 (44.5)",
        " <= WEEK 8   174 (54.0)",
    ]
    idx = PageStitcher()._find_leaf_rule_idx(lines)
    assert idx == 0


def test_leaf_rule_multi_run_tie_prefers_last():
    # Two dash rules with equal run counts (≥2): the LAST is the leaf (sits just above data)
    lines = [
        "             ACTUAL VALUES      CHANGES FROM BASELINE",
        "             ------------------ ------------------",   # 2 runs — intermediate
        "             EFG PH70 SC        EFG PH70 SC",
        "             (N=322)            (N=322)",
        "             ------------------ ------------------",   # 2 runs — leaf
    ]
    idx = PageStitcher()._find_leaf_rule_idx(lines)
    assert idx == 4
