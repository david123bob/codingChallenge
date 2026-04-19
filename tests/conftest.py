import pytest
from pathlib import Path


@pytest.fixture(scope="session")
def small_txt():
    return Path("small.txt").read_text(encoding="utf-8", errors="replace")


@pytest.fixture(scope="session")
def big_txt():
    return Path("big.txt").read_text(encoding="utf-8", errors="replace")


@pytest.fixture(scope="session")
def small_html(small_txt):
    from sas_parser import convert
    return convert(small_txt)


@pytest.fixture(scope="session")
def big_html(big_txt):
    from sas_parser import convert
    return convert(big_txt)
