"""
参数网格搜索优化器

搜索最优策略参数，支持多种策略
"""
import logging
from dataclasses import dataclass
from typing import List, Dict, Any, Optional, Type
import pandas as pd

from ..strategy import MACrossStrategy, RSIStrategy, MACDStrategy
from ..strategy.base_strategy import BaseStrategy
from ..data import get_provider

logger = logging.getLogger("quant_trader.backtest")


# 策略参数配置
STRATEGY_PARAMS = {
    "ma_cross": {
        "class": MACrossStrategy,
        "params": {
            "short_window": [5, 10, 15, 20, 30],
            "long_window": [20, 30, 40, 50, 60, 90],
        },
        "validate": lambda p: p.get("short_window", 0) < p.get("long_window", 999),
    },
    "rsi": {
        "class": RSIStrategy,
        "params": {
            "period": [7, 10, 14, 21],
            "oversold": [20, 25, 30, 35],
            "overbought": [65, 70, 75, 80],
        },
        "validate": lambda p: p.get("oversold", 50) < 50 < p.get("overbought", 50),
    },
    "macd": {
        "class": MACDStrategy,
        "params": {
            "fast_period": [8, 10, 12, 15],
            "slow_period": [20, 24, 26, 30],
            "signal_period": [6, 9, 12],
        },
        "validate": lambda p: p.get("fast_period", 0) < p.get("slow_period", 999),
    },
}


@dataclass
class BacktestMetrics:
    """回测指标"""
    total_return: float
    annual_return: float
    max_drawdown: float
    sharpe_ratio: float
    win_rate: float
    total_trades: int


class GridSearchOptimizer:
    """网格搜索优化器"""
    
    def __init__(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        provider_name: str = "stooq",
    ):
        """
        初始化
        
        Args:
            symbol: 股票代码
            start_date: 开始日期
            end_date: 结束日期
            provider_name: 数据源
        """
        self.symbol = symbol
        self.start_date = start_date
        self.end_date = end_date
        self.provider_name = provider_name
    
    def search(
        self,
        short_range: List[int] = [5, 10, 15, 20],
        long_range: List[int] = [20, 30, 40, 50, 60],
        top_n: int = 5,
    ) -> pd.DataFrame:
        """
        搜索最优参数
        
        Args:
            short_range: 短期均线范围
            long_range: 长期均线范围
            top_n: 返回前 N 个结果
            
        Returns:
            DataFrame: Top N 参数及指标
        """
        # 生成参数组合
        params = []
        for short in short_range:
            for long in long_range:
                if short < long:
                    params.append((short, long))
        
        logger.info(f"🔍 开始网格搜索: {len(params)} 组参数")
        
        results = []
        
        for short, long in params:
            try:
                metrics = self._backtest(short, long)
                
                results.append({
                    "short_window": short,
                    "long_window": long,
                    "total_return": metrics.total_return,
                    "annual_return": metrics.annual_return,
                    "max_drawdown": metrics.max_drawdown,
                    "sharpe_ratio": metrics.sharpe_ratio,
                    "win_rate": metrics.win_rate,
                    "total_trades": metrics.total_trades,
                })
                
            except Exception as e:
                logger.warning(f"⚠️ 参数 ({short}, {long}) 回测失败: {e}")
        
        # 排序
        df = pd.DataFrame(results)
        
        if df.empty:
            logger.warning("⚠️ 无有效结果")
            return df
        
        df = df.sort_values("sharpe_ratio", ascending=False).head(top_n)
        
        logger.info(f"✅ 网格搜索完成: Top {len(df)} 参数")
        
        return df
    
    def _backtest(self, short_window: int, long_window: int) -> BacktestMetrics:
        """单次回测"""
        from ..backtest import Backtester
        
        strategy = MACrossStrategy(
            short_window=short_window,
            long_window=long_window,
        )
        
        backtester = Backtester(
            strategy=strategy,
            symbol=self.symbol,
            start_date=self.start_date,
            end_date=self.end_date,
            provider_name=self.provider_name,
        )
        
        result = backtester.run()
        
        return BacktestMetrics(
            total_return=result.total_return,
            annual_return=result.annual_return,
            max_drawdown=result.max_drawdown,
            sharpe_ratio=result.sharpe_ratio,
            win_rate=result.win_rate,
            total_trades=result.total_trades,
        )


class MultiStrategyOptimizer:
    """多策略网格搜索优化器"""
    
    def __init__(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        provider_name: str = "stooq",
    ):
        """初始化"""
        self.symbol = symbol
        self.start_date = start_date
        self.end_date = end_date
        self.provider_name = provider_name
    
    def search(
        self,
        strategy_names: List[str] = None,
        top_n: int = 10,
    ) -> pd.DataFrame:
        """
        搜索所有策略的最优参数
        
        Args:
            strategy_names: 策略名称列表，默认所有
            top_n: 每种策略返回前 N 个结果
            
        Returns:
            DataFrame: Top N 参数及指标
        """
        if strategy_names is None:
            strategy_names = list(STRATEGY_PARAMS.keys())
        
        all_results = []
        
        for strategy_name in strategy_names:
            if strategy_name not in STRATEGY_PARAMS:
                logger.warning(f"⚠️ 未知策略: {strategy_name}")
                continue
            
            logger.info(f"🔍 优化策略: {strategy_name}")
            
            config = STRATEGY_PARAMS[strategy_name]
            strategy_class = config["class"]
            param_defs = config["params"]
            validate = config["validate"]
            
            # 生成参数组合
            param_combinations = self._generate_params(param_defs)
            
            for params in param_combinations:
                if not validate(params):
                    continue
                
                try:
                    metrics = self._backtest_strategy(strategy_class, params)
                    
                    result = {
                        "strategy": strategy_name,
                        **params,
                        "total_return": metrics.total_return,
                        "annual_return": metrics.annual_return,
                        "max_drawdown": metrics.max_drawdown,
                        "sharpe_ratio": metrics.sharpe_ratio,
                        "win_rate": metrics.win_rate,
                        "total_trades": metrics.total_trades,
                    }
                    all_results.append(result)
                    
                except Exception as e:
                    logger.debug(f"⚠️ 参数 {params} 回测失败: {e}")
        
        # 汇总排序
        df = pd.DataFrame(all_results)
        
        if df.empty:
            logger.warning("⚠️ 无有效结果")
            return df
        
        # 按夏普比率排序
        df = df.sort_values("sharpe_ratio", ascending=False).head(top_n)
        
        logger.info(f"✅ 多策略优化完成: 共 {len(df)} 组参数")
        
        return df
    
    def _generate_params(self, param_defs: Dict) -> List[Dict]:
        """生成参数组合"""
        keys = list(param_defs.keys())
        values = list(param_defs.values())
        
        def cartesian_product(*arrays):
            """笛卡尔积"""
            if not arrays:
                yield {}
                return
            for combo in __import__('itertools').product(*arrays):
                yield dict(zip(keys, combo))
        
        return list(cartesian_product(*values))
    
    def _backtest_strategy(
        self,
        strategy_class: Type[BaseStrategy],
        params: Dict[str, Any],
    ) -> BacktestMetrics:
        """单次回测"""
        from ..backtest import Backtester
        
        strategy = strategy_class(**params)
        
        backtester = Backtester(
            strategy=strategy,
            symbol=self.symbol,
            start_date=self.start_date,
            end_date=self.end_date,
            provider_name=self.provider_name,
        )
        
        result = backtester.run()
        
        return BacktestMetrics(
            total_return=result.total_return,
            annual_return=result.annual_return,
            max_drawdown=result.max_drawdown,
            sharpe_ratio=result.sharpe_ratio,
            win_rate=result.win_rate,
            total_trades=result.total_trades,
        )
