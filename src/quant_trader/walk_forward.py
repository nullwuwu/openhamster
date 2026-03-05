"""
Walk-forward 验证模块

用于验证策略是否过拟合
"""
from __future__ import annotations
import logging
from dataclasses import dataclass

from .models import BacktestResult, WalkForwardResult
from .backtest_engine import BacktestEngine, DualMAStrategy, Strategy
from .data import DataProvider

logger = logging.getLogger("quant_trader.walkforward")


@dataclass
class WalkForwardValidator:
    """
    Walk-forward 验证器
    
    用法:
        validator = WalkForwardValidator()
        result = validator.run(
            ticker="SPY",
            strategy=DualMAStrategy(fast_period=50, short_period=200),
            train_start="2022-01-01",
            train_end="2023-12-31",
            test_start="2024-01-01",
            test_end="2025-02-28",
        )
    """
    
    data_provider: DataProvider | None = None
    robustness_threshold: float = 0.5  # 样本外 Sharpe 衰减不超过 50%
    
    def run(
        self,
        ticker: str,
        strategy: Strategy,
        train_start: str,
        train_end: str,
        test_start: str,
        test_end: str,
    ) -> WalkForwardResult:
        """
        执行 walk-forward 验证
        
        Returns:
            WalkForwardResult: 包含训练集/测试集结果和稳健性判定
        """
        logger.info(f"🔄 [WalkForward] Starting for {ticker}")
        
        engine = BacktestEngine(data_provider=self.data_provider)
        
        # Step 1: 训练集回测
        logger.info(f"📊 [WalkForward] Training: {train_start} to {train_end}")
        train_result = engine.run(
            ticker=ticker,
            strategy=strategy,
            start_date=train_start,
            end_date=train_end,
        )
        
        # Step 2: 测试集回测 (同一组参数)
        logger.info(f"📊 [WalkForward] Testing: {test_start} to {test_end}")
        test_result = engine.run(
            ticker=ticker,
            strategy=strategy,
            start_date=test_start,
            end_date=test_end,
        )
        
        # Step 3: 计算性能衰减
        if train_result.sharpe != 0:
            degradation_ratio = test_result.sharpe / train_result.sharpe
        else:
            degradation_ratio = 0.0
        
        is_robust = degradation_ratio >= self.robustness_threshold
        
        logger.info(
            f"✅ [WalkForward] Done: train_sharpe={train_result.sharpe:.2f}, "
            f"test_sharpe={test_result.sharpe:.2f}, "
            f"degradation={degradation_ratio:.1%}, robust={is_robust}"
        )
        
        return WalkForwardResult(
            ticker=ticker,
            train_start=train_start,
            train_end=train_end,
            test_start=test_start,
            test_end=test_end,
            train_cagr=train_result.cagr,
            train_sharpe=train_result.sharpe,
            train_maxdd=train_result.max_drawdown,
            test_cagr=test_result.cagr,
            test_sharpe=test_result.sharpe,
            test_maxdd=test_result.max_drawdown,
            degradation_ratio=degradation_ratio,
            is_robust=is_robust,
        )


def run_walk_forward(
    ticker: str,
    fast_period: int = 50,
    short_period: int = 200,
    train_start: str = "2022-01-01",
    train_end: str = "2023-12-31",
    test_start: str = "2024-01-01",
    test_end: str = "2025-02-28",
    data_provider: DataProvider | None = None,
) -> WalkForwardResult:
    """
    快速运行 walk-forward 验证
    """
    strategy = DualMAStrategy(fast_period=fast_period, short_period=short_period)
    validator = WalkForwardValidator(data_provider=data_provider)
    
    return validator.run(
        ticker=ticker,
        strategy=strategy,
        train_start=train_start,
        train_end=train_end,
        test_start=test_start,
        test_end=test_end,
    )
