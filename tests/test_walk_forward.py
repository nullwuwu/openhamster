"""
Walk-forward 验证测试
"""
import pytest
from quant_trader.backtest.backtest_engine import DualMAStrategy
from quant_trader.models import WalkForwardResult


class TestWalkForwardValidation:
    """测试 Walk-forward 验证逻辑"""
    
    def test_degradation_ratio_formula(self):
        """验证 degradation_ratio = test_sharpe / train_sharpe"""
        
        # Case 1: test_sharpe = train_sharpe (无衰减)
        result = WalkForwardResult(
            ticker="TEST",
            train_start="2022-01-01",
            train_end="2023-12-31",
            test_start="2024-01-01",
            test_end="2025-02-28",
            train_cagr=0.10,
            train_sharpe=1.0,
            train_maxdd=0.10,
            test_cagr=0.10,
            test_sharpe=1.0,
            test_maxdd=0.10,
            degradation_ratio=1.0,
            is_robust=True,
        )
        
        assert result.degradation_ratio == 1.0
        assert result.test_sharpe / result.train_sharpe == 1.0
    
    def test_degradation_ratio_50_percent(self):
        """验证 50% 衰减的边界情况"""
        
        result = WalkForwardResult(
            ticker="TEST",
            train_start="2022-01-01",
            train_end="2023-12-31",
            test_start="2024-01-01",
            test_end="2025-02-28",
            train_cagr=0.10,
            train_sharpe=1.0,
            train_maxdd=0.10,
            test_cagr=0.05,
            test_sharpe=0.5,  # 50% of train
            test_maxdd=0.12,
            degradation_ratio=0.5,
            is_robust=True,  # >= 0.5 should pass
        )
        
        assert result.degradation_ratio == 0.5
        assert result.is_robust == True
    
    def test_degradation_ratio_above_threshold(self):
        """验证 > 50% 衰减 = 不稳健"""
        
        result = WalkForwardResult(
            ticker="TEST",
            train_start="2022-01-01",
            train_end="2023-12-31",
            test_start="2024-01-01",
            test_end="2025-02-28",
            train_cagr=0.10,
            train_sharpe=1.0,
            train_maxdd=0.10,
            test_cagr=0.03,
            test_sharpe=0.3,  # 30% of train
            test_maxdd=0.15,
            degradation_ratio=0.3,
            is_robust=False,  # < 0.5 should fail
        )
        
        assert result.degradation_ratio == 0.3
        assert result.is_robust == False
    
    def test_negative_sharpe_degradation(self):
        """验证负 Shar p e 的边界情况"""
        
        # 训练集正 Shar p e，测试集负 Shar p e
        result = WalkForwardResult(
            ticker="TEST",
            train_start="2022-01-01",
            train_end="2023-12-31",
            test_start="2024-01-01",
            test_end="2025-02-28",
            train_cagr=0.10,
            train_sharpe=1.0,
            train_maxdd=0.10,
            test_cagr=0.0,
            test_sharpe=-0.22,  # 负 Shar p e
            test_maxdd=0.05,
            degradation_ratio=-0.22,  # 负数
            is_robust=False,
        )
        
        assert result.degradation_ratio < 0
        assert result.is_robust == False
    
    def test_zero_train_sharpe(self):
        """验证训练集 Shar p e 为 0 的边界情况"""
        
        result = WalkForwardResult(
            ticker="TEST",
            train_start="2022-01-01",
            train_end="2023-12-31",
            test_start="2024-01-01",
            test_end="2025-02-28",
            train_cagr=0.0,
            train_sharpe=0.0,  # 训练集无收益
            train_maxdd=0.0,
            test_cagr=0.0,
            test_sharpe=0.0,
            test_maxdd=0.0,
            degradation_ratio=0.0,
            is_robust=False,
        )
        
        assert result.degradation_ratio == 0.0
        assert result.is_robust == False


class TestWalkForwardRobustness:
    """测试稳健性判断"""
    
    def test_robust_strategy_pass(self):
        """构造一个稳健策略通过测试"""
        # 测试集 Shar p e = 训练集的 60%
        result = WalkForwardResult(
            ticker="TEST",
            train_start="2022-01-01",
            train_end="2023-12-31",
            test_start="2024-01-01",
            test_end="2025-02-28",
            train_cagr=0.15,
            train_sharpe=1.2,
            train_maxdd=0.12,
            test_cagr=0.10,
            test_sharpe=0.72,  # 60%
            test_maxdd=0.14,
            degradation_ratio=0.6,
            is_robust=True,
        )
        
        assert result.degradation_ratio >= 0.5
        assert result.is_robust == True
    
    def test_fragile_strategy_fail(self):
        """构造一个脆弱策略不通过测试"""
        # 测试集 Shar p e = 训练集的 20%
        result = WalkForwardResult(
            ticker="TEST",
            train_start="2022-01-01",
            train_end="2023-12-31",
            test_start="2024-01-01",
            test_end="2025-02-28",
            train_cagr=0.15,
            train_sharpe=1.2,
            train_maxdd=0.12,
            test_cagr=0.02,
            test_sharpe=0.24,  # 20%
            test_maxdd=0.18,
            degradation_ratio=0.2,
            is_robust=False,
        )
        
        assert result.degradation_ratio < 0.5
        assert result.is_robust == False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
