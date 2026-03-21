import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from openhamster.data.symbols import detect_market, normalize_cn_symbol, normalize_symbol


def test_detect_market():
    assert detect_market("600519") == "cn"
    assert detect_market("600519.SH") == "cn"
    assert detect_market("000001.SZ") == "cn"
    assert detect_market("0700.HK") == "hk"
    assert detect_market("AAPL") == "us"


def test_normalize_cn_symbol():
    assert normalize_cn_symbol("600519") == "600519.SH"
    assert normalize_cn_symbol("000001") == "000001.SZ"
    assert normalize_cn_symbol("000001.sz") == "000001.SZ"


def test_normalize_symbol():
    assert normalize_symbol("600519") == "600519.SH"
    assert normalize_symbol("700.hk") == "0700.HK"
    assert normalize_symbol("msft") == "MSFT"
