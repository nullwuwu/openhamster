"""
End-to-End Integration Test: BacktestEngine → DecisionGraph

流程：SPY 5年数据 → DualMA(50,200) → BacktestEngine → DecisionGraph 6节点 → PMDecision
"""
import pytest
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from quant_trader.decision_graph import DecisionGraph
from quant_trader.models import Verdict


API_KEY = "sk-cp-chvjPxnd87lki9lOdWmiyurwlytJk48KdIwyS8ebYHW6yYaM27o2z6rjqEK_sRLBAWepOAztd7GXGNvSMjSY9W_nxW8e5gCu27v8MJN2_YDS3duXaVob9hI"


def test_e2e_real_backtest():
    """
    End-to-end test: 
    1. Run real backtest on SPY (5 years, DualMA 50/200)
    2. Pass result through DecisionGraph
    3. Verify PMDecision
    """
    print("\n" + "=" * 60)
    print("🚀 E2E Test: Real Backtest → DecisionGraph")
    print("=" * 60)
    
    # Create DecisionGraph with real LLM
    graph = DecisionGraph(api_key=API_KEY)
    
    # Real backtest params
    backtest_params = {
        "ticker": "SPY",
        "fast_period": 50,
        "short_period": 200,
        "start_date": "2020-01-01",
        # end_date defaults to today
        "param_sensitivity": 0.0,  # TODO: P0 自动计算
        "is_first_live": True,
    }
    
    print(f"\n📊 Backtest Params: {backtest_params}")
    
    # Run full flow
    result = graph.run(
        user_input="SPY 50/200 Dual MA 策略",
        backtest_params=backtest_params,
    )
    
    # Extract results
    backtest = result.get("backtest", {})
    risk_review = result.get("risk_review", {})
    pm_decision = result.get("pm_decision", {})
    
    print("\n" + "-" * 40)
    print("📈 BACKTEST RESULT")
    print("-" * 40)
    print(f"  CAGR: {backtest.get('cagr', 0):.2%}")
    print(f"  Max Drawdown: {backtest.get('max_drawdown', 0):.2%}")
    print(f"  Sharpe: {backtest.get('sharpe', 0):.2f}")
    print(f"  Annual Turnover: {backtest.get('annual_turnover', 0):.2f}x")
    print(f"  Data Years: {backtest.get('data_years', 0):.1f}")
    
    print("\n" + "-" * 40)
    print("🚦 RISK GATE RESULT")
    print("-" * 40)
    print(f"  Verdict: {risk_review.get('verdict')}")
    print(f"  Hard Fails: {risk_review.get('hard_gates_failed', [])}")
    print(f"  Yellow Flags: {risk_review.get('yellow_flags_triggered', [])}")
    print(f"  Utility Score: {risk_review.get('utility_score')}")
    
    print("\n" + "-" * 40)
    print("🎯 PM DECISION")
    print("-" * 40)
    print(f"  Verdict: {pm_decision.get('verdict')}")
    print(f"  Utility Score: {pm_decision.get('utility_score')}")
    print(f"  Reasoning: {pm_decision.get('reasoning', '')[:200]}...")
    print(f"  Risk Warnings: {pm_decision.get('risk_warnings', [])}")
    print(f"  Next Experiments: {len(pm_decision.get('next_experiments', []))}个")
    print(f"  Requires Human Approve: {pm_decision.get('requires_human_approve')}")
    
    # ===== ASSERTIONS =====
    
    # 1. BacktestResult 指标不为 0（验证是真实数据）
    assert backtest.get("cagr", 0) != 0, "CAGR should not be 0"
    assert backtest.get("max_drawdown", 0) != 0, "Max Drawdown should not be 0"
    assert backtest.get("sharpe", 0) != 0, "Sharpe should not be 0"
    print("\n✅ Assertion 1: Backtest metrics are non-zero (real data)")
    
    # 2. verdict 是 GO / NO_GO / REVISE 之一
    verdict = pm_decision.get("verdict")
    assert verdict in [Verdict.GO, Verdict.NO_GO, Verdict.REVISE], \
        f"Verdict should be GO/NO_GO/REVISE, got {verdict}"
    print(f"✅ Assertion 2: Verdict is valid: {verdict}")
    
    # 3. Risk Review 有结果
    assert risk_review.get("verdict") is not None, "Risk review should have verdict"
    print("✅ Assertion 3: Risk review completed")
    
    # 4. Data years 应该是 5+ 年（如果是真实回测）
    # 注意：如果 yfinance 限流，会回退到默认值，这个断言会跳过
    data_years = backtest.get("data_years", 0)
    if data_years > 0:
        assert data_years >= 4, f"Data years should be >= 4, got {data_years}"
        print(f"✅ Assertion 4: Data years >= 4: {data_years:.1f}")
    else:
        print("⚠️  Assertion 4: Skipped (yfinance rate limited, using fallback)")
    
    print("\n" + "=" * 60)
    print("✅ ALL E2E TESTS PASSED!")
    print("=" * 60)
    
    return result


if __name__ == "__main__":
    test_e2e_real_backtest()
