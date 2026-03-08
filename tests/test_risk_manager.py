"""
风控管理器单元测试

8 个测试用例覆盖全部 7 项风控规则 + 隔夜持仓保留
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from quant_trader import risk_manager_new as rm_module
from quant_trader.risk_manager_new import RiskManager, RiskAction


def create_rm():
    """创建风控管理器（重置全局单例）"""
    rm_module._risk_manager = None
    return RiskManager(
        max_daily_loss_ratio=-0.03,
        max_single_position_ratio=0.15,
        max_total_position_ratio=0.80,
        min_cash_ratio=0.05,
        stop_loss_ratio=-0.08,
        take_profit_ratio=0.15,
        trailing_stop_ratio=0.05,
    )


def test_01_daily_loss_circuit_breaker():
    """单日亏损熔断: 亏 3.1% → REJECT"""
    rm = create_rm()
    rm.reset_daily(day_start_assets=1_000_000)
    rm.record_realized_pnl(-31_000)  # -3.1%
    
    result = rm.pre_trade_check(
        ticker="2800.HK",
        shares=1000,
        price=26.0,
        total_assets=1_000_000,
        cash=1_000_000,
        current_positions={},
    )
    
    assert result.action == RiskAction.REJECT, f"Expected REJECT, got {result.action}"
    assert "单日亏损" in result.reason
    print(f"✅ test_01 PASS: {result.reason}")


def test_02_single_position_limit():
    """单股仓位上限: 15% → REDUCE"""
    rm = create_rm()
    rm.reset_daily(day_start_assets=1_000_000)
    
    result = rm.pre_trade_check(
        ticker="2800.HK",
        shares=2000,
        price=26.0,
        total_assets=1_000_000,
        cash=1_000_000,
        current_positions={
            "2800.HK": {"shares": 1000, "price": 26.0, "value": 26000}
        },
    )
    
    assert result.action == RiskAction.PASS
    print(f"✅ test_02a PASS: {result.reason}")
    
    result2 = rm.pre_trade_check(
        ticker="2800.HK",
        shares=5000,
        price=26.0,
        total_assets=1_000_000,
        cash=1_000_000,
        current_positions={
            "2800.HK": {"shares": 1000, "price": 26.0, "value": 26000}
        },
    )
    
    assert result2.action == RiskAction.REDUCE
    print(f"✅ test_02b PASS: {result2.reason}, adjusted: {result2.adjusted_shares}")


def test_03_total_position_limit():
    """总仓位上限: 80% → REDUCE"""
    rm = create_rm()
    rm.reset_daily(day_start_assets=1_000_000)
    
    result = rm.pre_trade_check(
        ticker="0700.HK",
        shares=10000,
        price=350.0,
        total_assets=1_000_000,
        cash=1_000_000,
        current_positions={
            "2800.HK": {"shares": 20000, "price": 26.0, "value": 520000}
        },
    )
    
    assert result.action == RiskAction.REDUCE
    print(f"✅ test_03 PASS: {result.reason}, adjusted: {result.adjusted_shares}")


def test_04_cash_insufficient():
    """现金不足: >95% → REDUCE"""
    rm = create_rm()
    rm.reset_daily(day_start_assets=1_000_000)
    
    result = rm.pre_trade_check(
        ticker="2800.HK",
        shares=40000,
        price=26.0,
        total_assets=1_000_000,
        cash=1_000_000,
        current_positions={},
    )
    
    assert result.action == RiskAction.REDUCE
    print(f"✅ test_04 PASS: {result.reason}, adjusted: {result.adjusted_shares}")


def test_05_stop_loss():
    """固定止损: 亏 -8% → FORCE_SELL"""
    rm = create_rm()
    rm.reset_daily(day_start_assets=1_000_000)
    rm.register_position("2800.HK", 1000, entry_price=26.0, current_price=26.0)
    
    result = rm.check_positions({"2800.HK": 23.9})
    
    assert len(result) == 1
    ticker, check = result[0]
    assert ticker == "2800.HK"
    assert check.action == RiskAction.FORCE_SELL
    print(f"✅ test_05 PASS: {check.reason}")


def test_06_take_profit():
    """固定止盈: 盈 +15% → FORCE_SELL"""
    rm = create_rm()
    rm.reset_daily(day_start_assets=1_000_000)
    rm.register_position("2800.HK", 1000, entry_price=26.0, current_price=26.0)
    
    result = rm.check_positions({"2800.HK": 29.9})
    
    assert len(result) == 1
    ticker, check = result[0]
    assert ticker == "2800.HK"
    assert check.action == RiskAction.FORCE_SELL
    print(f"✅ test_06 PASS: {check.reason}")


def test_07_trailing_stop():
    """移动止损: 盈利态从高点回撤 5% → FORCE_SELL"""
    rm = create_rm()
    rm.reset_daily(day_start_assets=1_000_000)
    rm.register_position("2800.HK", 1000, entry_price=26.0, current_price=30.0)
    
    result = rm.check_positions({"2800.HK": 28.5})
    
    assert len(result) == 1
    ticker, check = result[0]
    assert ticker == "2800.HK"
    assert check.action == RiskAction.FORCE_SELL
    print(f"✅ test_07 PASS: {check.reason}")


def test_08_overnight_position_retained():
    """隔夜持仓保留: reset_daily 后持仓仍在"""
    rm = create_rm()
    
    rm.register_position("2800.HK", 1000, entry_price=26.0, current_price=26.0)
    rm.reset_daily(day_start_assets=1_000_000)
    
    status = rm.get_status()
    assert "2800.HK" in status["positions"]
    assert status["positions"]["2800.HK"]["shares"] == 1000
    print(f"✅ test_08a PASS: 持仓保留, shares={status['positions']['2800.HK']['shares']}")
    
    result = rm.check_positions({"2800.HK": 23.9})
    assert len(result) == 1
    ticker, check = result[0]
    assert check.action == RiskAction.FORCE_SELL
    print(f"✅ test_08b PASS: 止损触发, {check.reason}")


if __name__ == "__main__":
    print("=" * 50)
    print("RiskManager 单元测试")
    print("=" * 50)
    
    test_01_daily_loss_circuit_breaker()
    test_02_single_position_limit()
    test_03_total_position_limit()
    test_04_cash_insufficient()
    test_05_stop_loss()
    test_06_take_profit()
    test_07_trailing_stop()
    test_08_overnight_position_retained()
    
    print("\n" + "=" * 50)
    print("🎉 全部 8 个测试通过!")
    print("=" * 50)
