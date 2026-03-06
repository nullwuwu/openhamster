"""
参数网格搜索优化器

搜索最优策略参数
"""
import logging
from dataclasses import dataclass
from typing import List, Tuple
import pandas as pd

from ..strategy import MACrossStrategy
from ..data import get_provider

logger = logging.getLogger("quant_trader.backtest")


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
