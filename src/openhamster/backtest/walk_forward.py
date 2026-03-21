"""
Walk-forward 回测引擎

滚动窗口验证策略稳健性
"""
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List
import pandas as pd

from .optimizer import GridSearchOptimizer, MultiStrategyOptimizer, STRATEGY_PARAMS
from .backtester import Backtester

logger = logging.getLogger("openhamster.backtest")


@dataclass
class WindowResult:
    """单个窗口结果"""
    train_start: str
    train_end: str
    test_start: str
    test_end: str
    best_short: int
    best_long: int
    test_return: float
    test_max_drawdown: float
    test_sharpe: float


@dataclass
class WalkForwardResult:
    """Walk-forward 结果"""
    windows: List[WindowResult]
    equity_curve: pd.DataFrame
    summary: dict


class WalkForwardEngine:
    """Walk-forward 引擎"""
    
    def __init__(
        self,
        symbol: str,
        train_months: int = 12,
        test_months: int = 3,
        step_months: int = 3,
        provider_name: str = "stooq",
        strategy_name: str = "ma_cross",
    ):
        """
        初始化
        
        Args:
            symbol: 股票代码
            train_months: 训练集月数
            test_months: 测试集月数
            step_months: 滚动步长月数
            provider_name: 数据源
            strategy_name: 策略名称 (ma_cross/rsi/macd)
        """
        self.symbol = symbol
        self.train_months = train_months
        self.test_months = test_months
        self.step_months = step_months
        self.provider_name = provider_name
        self.strategy_name = strategy_name
    
    def run(self, start_date: str, end_date: str) -> WalkForwardResult:
        """
        运行 Walk-forward
        
        Args:
            start_date: 数据开始日期
            end_date: 数据结束日期
            
        Returns:
            WalkForwardResult
        """
        logger.info(f"🚀 开始 Walk-forward: {start_date} ~ {end_date}")
        
        # 转换日期
        start = pd.to_datetime(start_date)
        end = pd.to_datetime(end_date)
        
        # 计算窗口
        windows = []
        train_start = start
        
        while True:
            train_end = self._add_months(train_start, self.train_months)
            test_start = train_end
            test_end = self._add_months(test_start, self.test_months)
            
            # 超出范围则停止
            if test_end > end:
                break
            
            train_start_str = train_start.strftime("%Y-%m-%d")
            train_end_str = train_end.strftime("%Y-%m-%d")
            test_start_str = test_start.strftime("%Y-%m-%d")
            test_end_str = test_end.strftime("%Y-%m-%d")
            
            logger.info(f"📊 窗口: 训练 {train_start_str}~{train_end_str}, 测试 {test_start_str}~{test_end_str}")
            
            # 训练集找最优参数 (支持多策略)
            optimizer = MultiStrategyOptimizer(
                symbol=self.symbol,
                start_date=train_start_str,
                end_date=train_end_str,
                provider_name=self.provider_name,
            )
            
            try:
                top_params = optimizer.search(
                    strategy_names=[self.strategy_name],
                    top_n=1,
                )
                
                if top_params.empty:
                    logger.warning(f"⚠️ 窗口无有效参数，跳过")
                    train_start = test_start
                    continue
                
                # 获取最优策略和参数
                row = top_params.iloc[0]
                strategy_name = row["strategy"]
                
                # 构建策略参数
                strategy_params = self._extract_params(row, strategy_name)
                
                logger.info(f"🔧 最优策略: {strategy_name}, 参数: {strategy_params}")
                
                # 测试集验证
                strategy = STRATEGY_PARAMS[strategy_name]["class"](**strategy_params)
                
                backtester = Backtester(
                    strategy=strategy,
                    symbol=self.symbol,
                    start_date=test_start_str,
                    end_date=test_end_str,
                    provider_name=self.provider_name,
                )
                
                result = backtester.run()
                
                windows.append(WindowResult(
                    train_start=train_start_str,
                    train_end=train_end_str,
                    test_start=test_start_str,
                    test_end=test_end_str,
                    best_short=int(strategy_params.get("short_window", 0)),
                    best_long=int(strategy_params.get("long_window", 0)),
                    test_return=result.total_return,
                    test_max_drawdown=result.max_drawdown,
                    test_sharpe=result.sharpe_ratio,
                ))
                
                # 滚动到下一个窗口
                train_start = self._add_months(train_start, self.step_months)
                
            except Exception as e:
                logger.warning(f"⚠️ 窗口执行失败: {e}")
                train_start = self._add_months(train_start, self.step_months)
        
        # 汇总结果
        return self._aggregate_results(windows)
    
    def _extract_params(self, row: pd.Series, strategy_name: str) -> dict:
        """从结果中提取策略参数"""
        params = {}
        
        if strategy_name == "ma_cross":
            params["short_window"] = int(row["short_window"])
            params["long_window"] = int(row["long_window"])
        elif strategy_name == "rsi":
            params["period"] = int(row["period"])
            params["oversold"] = int(row["oversold"])
            params["overbought"] = int(row["overbought"])
        elif strategy_name == "macd":
            params["fast_period"] = int(row["fast_period"])
            params["slow_period"] = int(row["slow_period"])
            params["signal_period"] = int(row["signal_period"])
        elif strategy_name == "mean_reversion":
            params["z_window"] = int(row["z_window"])
            params["entry_threshold"] = float(row["entry_threshold"])
            params["exit_threshold"] = float(row["exit_threshold"])
            params["use_short"] = bool(row["use_short"])
        elif strategy_name == "channel_breakout":
            params["channel_window"] = int(row["channel_window"])
            params["atr_window"] = int(row["atr_window"])
            params["atr_k"] = float(row["atr_k"])
            params["use_stop_loss"] = bool(row["use_stop_loss"])
        
        return params
    
    def _add_months(self, date, months):
        """日期加月"""
        month = date.month + months
        year = date.year + (month - 1) // 12
        month = (month - 1) % 12 + 1
        day = min(date.day, [31,29 if year%4==0 and (year%100!=0 or year%400==0) else 28,31,30,31,30,31,31,30,31,30,31][month-1])
        return pd.Timestamp(year, month, day)
    
    def _aggregate_results(self, windows: List[WindowResult]) -> WalkForwardResult:
        """汇总结果"""
        if not windows:
            return WalkForwardResult(
                windows=[],
                equity_curve=pd.DataFrame(),
                summary={}
            )
        
        # 计算汇总指标
        returns = [w.test_return for w in windows]
        drawdowns = [w.test_max_drawdown for w in windows]
        sharpes = [w.test_sharpe for w in windows]
        
        summary = {
            "total_windows": len(windows),
            "avg_return": sum(returns) / len(returns),
            "avg_max_drawdown": sum(drawdowns) / len(drawdowns),
            "avg_sharpe": sum(sharpes) / len(sharpes),
            "best_window": max(returns),
            "worst_window": min(returns),
        }
        
        logger.info(f"""
=== Walk-forward 汇总 ===
窗口数: {summary['total_windows']}
平均收益: {summary['avg_return']:.2f}%
平均回撤: {summary['avg_max_drawdown']:.2f}%
平均夏普: {summary['avg_sharpe']:.2f}
""")
        
        return WalkForwardResult(
            windows=windows,
            equity_curve=pd.DataFrame(),  # 可扩展
            summary=summary,
        )
