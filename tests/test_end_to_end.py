import re

import pytest


def test_small_one_table(small_html):
    assert small_html.count('class="table-section"') == 1


def test_small_title(small_html):
    assert "TABLE 57.5.5.5" in small_html


def test_small_thead_two_rows(small_html):
    thead = re.search(r'<thead>(.*?)</thead>', small_html, re.DOTALL).group(1)
    assert thead.count('<tr>') == 2


def test_small_column_headers(small_html):
    assert "EFG PH20 SC" in small_html
    assert "PBO PH20 SC" in small_html
    assert "ALL PARTICIPANTS" in small_html


def test_small_known_cell_value(small_html):
    assert "629" in small_html


def test_small_no_footnote_in_output(small_html):
    assert "RANDOMIZED PARTICIPANTS, mITT" not in small_html


def test_big_table_count(big_html):
    assert big_html.count('class="table-section"') == 110


def test_big_no_cox_footnote_in_body(big_html):
    assert "&lt;a&gt; COX PROPORTIONAL" not in big_html


def test_big_no_eci_definition_in_body(big_html):
    assert "ECI = EVIDENCE OF CLINICAL IMPROVEMENT" not in big_html


def test_big_1451_has_10_col_header(big_html):
    assert "HAZARD RATIO" in big_html
    assert "p-VALUE" in big_html


def test_big_toc_sidebar(big_html):
    assert 'id="sidebar"' in big_html
    assert 'id="toc-search"' in big_html
