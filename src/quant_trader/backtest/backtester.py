"""
Backtester 回测引擎

逐 bar 驱动策略执行回测
"""
from __future__ import annotations
import logging
from datetime import datetime
from typing import Optional

import pandas as pd
import numpy as np

from ..strategy import BaseStrategy, Signal
from ..data import get_provider
from ..risk import RiskManager
from .result import BacktestResult

logger = logging.getLogger("quant_trader.backtest")

# 默认回测参数
DEFAULT_INITIAL_CAPITAL = 1_000_000  # HKD 100万
DEFAULT_COMMISSION = 0.001  # 0.1% 手续费


class Backtester:
    """回测引擎"""
    
    def __init__(
        self,
        strategy: BaseStrategy,
        symbol: str,
        start_date: str,
        end_date: str,
        initial_capital: float = DEFAULT_INITIAL_CAPITAL,
        commission: float = DEFAULT_COMMISSION,
        provider_name: str = "akshare",
        risk_manager: Optional[RiskManager] = None,
    ):
        """
        初始化
        
        Args:
            strategy: 交易策略
            symbol: 股票代码 (如 "2800.HK")
            start_date: 开始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)
            initial_capital: 初始资金
            commission: 手续费率 (0.001 = 0.1%)
            provider_name: 数据源名称
            risk_manager: 风控管理器 (可选)
        """
        self.strategy = strategy
        self.symbol = symbol
        self.start_date = start_date
        self.end_date = end_date
        self.initial_capital = initial_capital
        self.commission = commission
        self.provider_name = provider_name
        self.risk_manager = risk_manager
        
        # 回测状态
        self._cash: float = initial_capital
        self._position: int = 0  # 持仓股数
        self._position_cost: float = 0.0  # 持仓成本
        self._equity_curve: list = []
        self._trades: list = []
        self._deprecated_notice_logged = False
        
    def run(self) -> BacktestResult:
        """
        运行回测
        
        Returns:
            BacktestResult: 回测结果
        """
        logger.info(f"🚀 开始回测: {self.symbol} ({self.start_date} ~ {self.end_date})")
        if not self._deprecated_notice_logged:
            logger.warning("⚠️ Backtester 正在兼容模式运行，建议使用 BacktestEngine")
            self._deprecated_notice_logged = True
        
        # 1. 获取数据
        data = self._fetch_data()
        
        if data.empty:
            raise ValueError(f"无数据: {self.symbol}")
        
        logger.info(f"📊 加载 {len(data)} 条数据")
        
        # 2. 重置策略状态
        self.strategy.reset()
        self._cash = self.initial_capital
        self._position = 0
        self._equity_curve = []
        self._trades = []
        
        # 3. 逐 bar 回测
        for i in range(len(data)):
            # 当前 bar
            bar = data.iloc[i]
            current_price = bar['close']
            current_date = data.index[i]
            
            # 获取历史数据（用于信号生成）
            hist_data = data.iloc[:i+1]
            
            # 生成信号
            signal = self.strategy.generate_signal(hist_data)
            
            # 风控评估
            if self.risk_manager:
                # 计算当前回撤
                equity_series = pd.Series([e['total_value'] for e in self._equity_curve] + [self._cash + self._position * current_price])
                cummax = equity_series.cummax()
                drawdown = (equity_series - cummax) / cummax
                max_drawdown = drawdown.min() if len(drawdown) > 0 else 0
                
                # 构建上下文
                avg_cost = self._position_cost / self._position if self._position > 0 else 0
                context = {
                    "ticker": self.symbol,
                    "date": current_date,
                    "price": current_price,
                    "position": self._position,
                    "avg_cost": avg_cost,
                    "current_price": current_price,
                    "total_equity": self._cash + self._position * current_price,
                    "total_assets": self._cash + self._position * current_price,
                    "cash": self._cash,
                    "max_drawdown_pct": max_drawdown,
                    "current_positions": {
                        self.symbol: {
                            "shares": self._position,
                            "price": avg_cost,
                            "value": self._position * avg_cost,
                        }
                    } if self._position > 0 else {},
                }
                
                original_signal = signal
                signal, adjusted_shares = self.risk_manager.evaluate(signal, context)
                
                if original_signal != signal:
                    logger.info(f"⚠️ 风控干预: {original_signal} -> {signal}, adjusted_shares={adjusted_shares}")
            else:
                adjusted_shares = None
            
            # 执行交易
            self._execute_trade(signal, current_price, current_date, adjusted_shares)
            
            # 记录净值
            portfolio_value = self._cash + self._position * current_price
            self._equity_curve.append({
                'date': current_date,
                'cash': self._cash,
                'position_value': self._position * current_price,
                'total_value': portfolio_value,
                'price': current_price,
            })
        
        # 4. 计算结果
        result = self._calculate_result(data)
        
        logger.info(f"✅ 回测完成: 总收益率 {result.total_return:.2f}%")
        
        return result
    
    def _fetch_data(self) -> pd.DataFrame:
        """获取数据，自动 fallback"""
        # 尝试主数据源
        try:
            provider = get_provider(self.provider_name)
            logger.info(f"📥 使用数据源: {self.provider_name}")
            return provider.fetch_ohlcv(self.symbol, self.start_date, self.end_date)
        except Exception as e:
            logger.warning(f"⚠️ {self.provider_name} 失败: {e}")
            
            # Fallback 到 stooq
            if self.provider_name != "stooq":
                try:
                    provider = get_provider("stooq")
                    logger.info("📥 Fallback 到 Stooq")
                    return provider.fetch_ohlcv(self.symbol, self.start_date, self.end_date)
                except Exception as e2:
                    logger.warning(f"⚠️ Stooq 也失败: {e2}")
            
            raise RuntimeError(f"所有数据源均失败: {e}")
    
    def _execute_trade(
        self, 
        signal: Signal, 
        price: float, 
        date: pd.Timestamp,
        adjusted_shares: int = None,
    ) -> None:
        """执行交易"""
        # 统一使用字符串比较
        signal_val = str(signal.value) if hasattr(signal, 'value') else str(signal)
        
        # 买入
        if signal_val == "BUY" and self._position == 0:  # BUY
            # 用全部现金买入（或调整后的股数）
            if adjusted_shares:
                shares = adjusted_shares
            else:
                shares = int(self._cash / (price * (1 + self.commission)))
            if shares > 0:
                cost = shares * price * (1 + self.commission)
                self._cash -= cost
                self._position = shares
                self._position_cost = shares * price  # 记录持仓成本
                self._trades.append({
                    'date': date,
                    'action': 'BUY',
                    'price': price,
                    'shares': shares,
                    'cost': cost,
                })
        
        # 卖出
        elif signal_val == "SELL" and self._position > 0:  # SELL
            proceeds = self._position * price * (1 - self.commission)
            self._cash += proceeds
            self._trades.append({
                'date': date,
                'action': 'SELL',
                'price': price,
                'shares': self._position,
                'proceeds': proceeds,
            })
            self._position = 0
            self._position_cost = 0.0
    
    def _calculate_result(self, data: pd.DataFrame) -> BacktestResult:
        """计算回测指标"""
        # 转换为 DataFrame
        equity_df = pd.DataFrame(self._equity_curve)
        equity_df.set_index('date', inplace=True)
        
        # 计算收益率
        final_value = self._equity_curve[-1]['total_value'] if self._equity_curve else self.initial_capital
        total_return = (final_value - self.initial_capital) / self.initial_capital * 100
        
        # 计算交易日天数
        trading_days = len(data)
        years = trading_days / 252
        annual_return = ((final_value / self.initial_capital) ** (1 / years) - 1) * 100 if years > 0 else 0
        
        # 计算最大回撤
        equity_series = equity_df['total_value']
        cummax = equity_series.cummax()
        drawdown = (equity_series - cummax) / cummax * 100
        max_drawdown = drawdown.min()  # 回撤是负数
        
        # 计算夏普比率 (简化版)
        daily_returns = equity_series.pct_change().dropna()
        if len(daily_returns) > 0 and daily_returns.std() > 0:
            sharpe_ratio = (daily_returns.mean() / daily_returns.std()) * np.sqrt(252)
        else:
            sharpe_ratio = 0.0
        
        # 统计交易
        winning = sum(1 for t in self._trades if t['action'] == 'SELL' and t.get('proceeds', 0) > 0)
        
        return BacktestResult(
            symbol=self.symbol,
            start_date=self.start_date,
            end_date=self.end_date,
            initial_capital=self.initial_capital,
            final_value=final_value,
            total_return=total_return,
            annual_return=annual_return,
            max_drawdown=max_drawdown,
            sharpe_ratio=sharpe_ratio,
            total_trades=len(self._trades),
            winning_trades=winning,
            losing_trades=len(self._trades) - winning,
            equity_curve=equity_df,
            trades=self._trades,
        )
