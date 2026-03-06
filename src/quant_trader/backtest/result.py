"""
回测结果数据类
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
import pandas as pd


@dataclass
class BacktestResult:
    """回测结果"""
    
    # 基础信息
    symbol: str
    start_date: str
    end_date: str
    initial_capital: float
    
    # 核心指标
    final_value: float
    total_return: float  # 总收益率 (%)
    annual_return: float  # 年化收益率 (%)
    max_drawdown: float   # 最大回撤 (%)
    sharpe_ratio: float   # 夏普比率
    
    # 交易统计
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    
    # 详细数据
    equity_curve: pd.DataFrame = field(default_factory=pd.DataFrame)  # 逐日净值
    trades: list = field(default_factory=list)  # 交易记录
    
    @property
    def win_rate(self) -> float:
        """胜率"""
        if self.total_trades == 0:
            return 0.0
        return self.winning_trades / self.total_trades * 100
    
    def summary(self) -> str:
        """返回摘要"""
        return f"""
=== {self.symbol} 回测结果 ===
时间: {self.start_date} ~ {self.end_date}
初始资金: HKD {self.initial_capital:,.2f}
最终净值: HKD {self.final_value:,.2f}
总收益率: {self.total_return:.2f}%
年化收益率: {self.annual_return:.2f}%
最大回撤: {self.max_drawdown:.2f}%
夏普比率: {self.sharpe_ratio:.2f}
交易次数: {self.total_trades}
胜率: {self.win_rate:.1f}%
"""
