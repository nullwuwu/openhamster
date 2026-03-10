import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from quant_trader.broker.paper_broker import PaperBroker


def test_cn_lot_size_rule():
    broker = PaperBroker(initial_capital=1_000_000, cn_lot_size=100, cn_t_plus_one=True)
    with pytest.raises(PermissionError):
        broker.place_order("600519.SH", "BUY", qty=50, price=100.0)


def test_cn_t_plus_one_rule():
    broker = PaperBroker(initial_capital=1_000_000, cn_lot_size=100, cn_t_plus_one=True)
    broker.place_order("600519.SH", "BUY", qty=100, price=100.0)
    with pytest.raises(PermissionError):
        broker.place_order("600519.SH", "SELL", qty=100, price=101.0)


def test_no_short_sell_without_position():
    broker = PaperBroker(initial_capital=1_000_000, allow_short=False)
    with pytest.raises(PermissionError):
        broker.place_order("600519.SH", "SELL", qty=100, price=100.0)
