"""
BacktestEngine - 量化回测引擎

支持:
- 数据源: DataProvider (可插拔)
- 策略: Dual MA (双均线交叉)
- 输出: BacktestResult
"""
from __future__ import annotations
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional
from datetime import datetime

import pandas as pd
import numpy as np

from ..models import BacktestResult
from ..policy import policy
from ..data import DataProvider, YFinanceProvider, TwelveDataProvider

logger = logging.getLogger("quant_trader.backtest")


# ============ Strategy Interface ============

class Strategy(ABC):
    """策略基类"""

    @abstractmethod
    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        """
        生成交易信号
        Returns:
            pd.Series: 1=做多, -1=做空, 0=空仓
        """
        pass

    @abstractmethod
    def get_params(self) -> dict[str, Any]:
        """返回策略参数"""
        pass


# ============ Dual MA Strategy ============

class DualMAStrategy(Strategy):
    """双均线交叉策略
    
    规则:
    - 快线 > 慢线 → 做多 (1)
    - 快线 < 慢线 → 做空 (-1)
    - 也可以选择: 快线 > 慢线 → 做多，快线 < 慢线 → 空仓
    """

    def __init__(
        self,
        fast_period: int = 20,
        short_period: int = 50,
        use_long_only: bool = True,
        use_regime_filter: bool = False,  # 是否启用 regime filter
        regime_config: "RegimeConfig" = None,  # Regime 配置
    ):
        self.fast_period = fast_period
        self.short_period = short_period
        self.use_long_only = use_long_only
        self.use_regime_filter = use_regime_filter
        self.regime_config = regime_config

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        """生成交易信号"""
        close = data['close']  # lowercase after normalization
        
        # 计算均线
        fast_ma = close.rolling(window=self.fast_period).mean()
        slow_ma = close.rolling(window=self.short_period).mean()
        
        # 生成信号
        signals = pd.Series(0, index=data.index)
        signals[fast_ma > slow_ma] = 1  # 做多
        signals[fast_ma < slow_ma] = -1 if not self.use_long_only else 0
        
        # Regime filter: ranging 时强制空仓
        if self.use_regime_filter:
            from .regime import RegimeDetector
            config = self.regime_config
            detector = RegimeDetector(config)
            
            # 逐日判断 regime
            for i in range(len(data)):
                if i < 50:  # 需要足够历史
                    continue
                
                window = data.iloc[:i+1]
                regime = detector.detect(window)
                
                if regime.value == "ranging":
                    signals.iloc[i] = 0  # 震荡市不交易
        
        return signals

    def get_params(self) -> dict[str, Any]:
        return {
            "name": "DualMA",
            "fast_period": self.fast_period,
            "short_period": self.short_period,
            "use_long_only": self.use_long_only,
            "use_regime_filter": self.use_regime_filter,
        }
    
    def count_crossovers(self, data: pd.DataFrame) -> int:
        """
        统计均线交叉次数
        
        金叉 (golden cross): fast MA 从下方穿过 slow MA → 信号从 0/-1 变成 1
        死叉 (death cross): fast MA 从上方穿过 slow MA → 信号从 1 变成 0/-1
        
        Returns:
            int: 交叉总次数 (金叉 + 死叉)
        """
        signals = self.generate_signals(data)
        
        # 计算信号变化
        signal_diff = signals.diff().fillna(0)
        
        # 金叉: 从非1变成1 (0→1 或 -1→1)
        golden_cross = ((signal_diff == 1) | (signal_diff == 2)).sum()
        
        # 死叉: 从非0变成0 (1→0 或 1→-1) 或 从1变成-1
        death_cross = ((signal_diff == -1) | (signal_diff == -2)).sum()
        
        return golden_cross + death_cross
    
    def calculate_param_sensitivity(
        self, 
        data: pd.DataFrame,
        perturb_pct: float = 0.10,
    ) -> float:
        """
        计算参数敏感性
        
        基准参数: fast_period, short_period
        扰动方式: fast/slow 各 ±10%
        敏感性指标: max(|CAGR_change| / CAGR_base)
        
        Args:
            data: OHLCV 数据
            perturb_pct: 扰动百分比 (默认 10%)
            
        Returns:
            float: 敏感性指标 (0-1, 越大越不稳定)
        """
        # 基准参数
        base_fast = self.fast_period
        base_short = self.short_period
        
        # 计算基准 CAGR
        base_signals = self.generate_signals(data)
        base_returns = self._calc_returns(data, base_signals)
        base_cagr = self._calc_cagr_from_returns(base_returns, data)
        
        if base_cagr == 0:
            return 0.0
        
        # 扰动参数组合 (±10%)
        perturbations = [
            (base_fast * (1 + perturb_pct), base_short),      # fast +10%
            (base_fast * (1 - perturb_pct), base_short),      # fast -10%
            (base_fast, base_short * (1 + perturb_pct)),       # short +10%
            (base_fast, base_short * (1 - perturb_pct)),       # short -10%
        ]
        
        max_change = 0.0
        
        for fast_p, short_p in perturbations:
            # 确保参数有效
            fast_p = max(1, int(fast_p))
            short_p = max(fast_p + 1, int(short_p))  # short > fast
            
            temp_strategy = DualMAStrategy(
                fast_period=fast_p,
                short_period=short_p,
                use_long_only=self.use_long_only,
            )
            
            try:
                signals = temp_strategy.generate_signals(data)
                returns = self._calc_returns(data, signals)
                cagr = self._calc_cagr_from_returns(returns, data)
                
                change = abs(cagr - base_cagr) / abs(base_cagr)
                max_change = max(max_change, change)
                
            except Exception:
                continue
        
        return min(max_change, 1.0)  # 限制在 0-1 范围
    
    @staticmethod
    def _calc_returns(data: pd.DataFrame, signals: pd.Series) -> pd.Series:
        """从信号计算收益率"""
        close = data['close']
        daily_returns = close.pct_change()
        position = signals.shift(1).fillna(0)
        return position * daily_returns
    
    @staticmethod
    def _calc_cagr_from_returns(returns: pd.Series, data: pd.DataFrame, initial_capital: float = 100000) -> float:
        """从收益率序列计算 CAGR"""
        if len(returns) < 2:
            return 0.0
        
        equity = initial_capital * (1 + returns.fillna(0)).cumprod()
        
        total_return = equity.iloc[-1] / equity.iloc[0]
        years = len(equity) / 252
        
        if years <= 0:
            return 0.0
        
        return total_return ** (1 / years) - 1


# ============ Backtest Engine ============

@dataclass
class Trade:
    """单笔交易"""
    entry_date: str
    exit_date: str
    entry_price: float
    exit_price: float
    position: int  # 1=多, -1=空
    pnl: float
    return_pct: float


@dataclass
class BacktestEngine:
    """
    回测引擎
    
    用法:
        engine = BacktestEngine()
        result = engine.run(
            ticker="SPY",
            strategy=DualMAStrategy(fast_period=20, short_period=50),
            start_date="2020-01-01",
            end_date="2025-01-01",
        )
        
    支持自定义数据源:
        from quant_trader.data import TwelveDataProvider
        provider = TwelveDataProvider(api_key="xxx")
        engine = BacktestEngine(data_provider=provider)
    """

    data_provider: Optional[DataProvider] = None
    slippage_bps: float = 0  # 滑点 (basis points)
    commission_rate: float = 0  # 佣金率
    tax_rate: float = 0  # 印花税率
    dividend_withholding: float = 0  # 股息预扣税率

    def __post_init__(self):
        """初始化"""
        # 加载交易成本假设
        tc = policy.trading_costs
        self.slippage_bps = tc.slippage_bps
        self.commission_rate = tc.commission_rate
        self.tax_rate = tc.tax_rate
        self.dividend_withholding = tc.dividend_withholding
        
        # 设置默认数据源（如果未提供）
        if self.data_provider is None:
            self.data_provider = self._create_default_provider()
    
    def _create_default_provider(self) -> DataProvider:
        """创建默认数据源（先尝试 TwelveData，失败则 fallback 到 yfinance）"""
        # 优先尝试 Twelve Data
        try:
            provider = TwelveDataProvider()
            # 测试连接 (使用较新的日期范围，避免 free tier 限制)
            test_data = provider.fetch_ohlcv("SPY", "2025-01-01", "2025-01-05")
            if not test_data.empty:
                logger.info("✅ [BacktestEngine] Using TwelveDataProvider")
                return provider
        except Exception as e:
            logger.warning(f"⚠️ [BacktestEngine] TwelveDataProvider failed: {e}, falling back to yfinance")
        
        # Fallback 到 yfinance
        logger.info("✅ [BacktestEngine] Using YFinanceProvider (fallback)")
        return YFinanceProvider()

    def load_data(self, ticker: str, start_date: str, end_date: str) -> pd.DataFrame:
        """通过 DataProvider 加载数据"""
        logger.info(f"📥 [BacktestEngine] Loading {ticker} from {start_date} to {end_date}")
        
        try:
            data = self.data_provider.fetch_ohlcv(ticker, start_date, end_date)
            
            # 标准化列名
            data = self._normalize_columns(data)
            
            logger.info(f"✅ [BacktestEngine] Loaded {len(data)} rows")
            return data
            
        except Exception as e:
            logger.error(f"❌ [BacktestEngine] Data fetch failed: {e}")
            
            # 如果当前不是 yfinance，尝试 fallback
            if not isinstance(self.data_provider, YFinanceProvider):
                logger.warning("⚠️ [BacktestEngine] Falling back to YFinanceProvider")
                self.data_provider = YFinanceProvider()
                try:
                    data = self.data_provider.fetch_ohlcv(ticker, start_date, end_date)
                    data = self._normalize_columns(data)
                    return data
                except Exception as e2:
                    logger.error(f"❌ [BacktestEngine] Fallback also failed: {e2}")
            
            raise
    
    def _normalize_columns(self, data: pd.DataFrame) -> pd.DataFrame:
        """标准化列名"""
        # 转小写
        data = data.copy()
        data.columns = [c.lower() for c in data.columns]
        
        # 确保有需要的列
        required = ['open', 'high', 'low', 'close', 'volume']
        for col in required:
            if col not in data.columns:
                raise ValueError(f"Missing required column: {col}")
        
        return data
        
        if data.empty:
            raise ValueError(f"No data for {ticker}")
        
        # Flatten columns if MultiIndex
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.get_level_values(0)
        
        logger.info(f"✅ [BacktestEngine] Loaded {len(data)} rows")
        return data

    def run(
        self,
        ticker: str,
        strategy: Strategy,
        start_date: str = "2020-01-01",
        end_date: str | None = None,
        initial_capital: float = 100000,
        param_sensitivity: float | None = None,
        is_first_live: bool = False,
    ) -> BacktestResult:
        """
        运行回测
        
        Args:
            ticker: 股票代码 (e.g., "SPY", "QQQ")
            strategy: 策略实例
            start_date: 开始日期
            end_date: 结束日期 (默认今天)
            initial_capital: 初始资金
            param_sensitivity: 参数敏感性 (可选)
            is_first_live: 是否首次实盘
            
        Returns:
            BacktestResult: 回测结果
        """
        import datetime
        if end_date is None:
            end_date = datetime.datetime.now().strftime("%Y-%m-%d")
        
        # 加载数据
        data = self.load_data(ticker, start_date, end_date)
        
        # 生成信号
        signals = strategy.generate_signals(data)
        
        # 计算收益
        returns = self._calculate_returns(data, signals)
        
        # 计算 equity curve
        equity = initial_capital * (1 + returns).cumprod()
        
        # 计算交易统计
        trades = self._extract_trades(data, signals)
        
        # 计算指标
        cagr = self._calc_cagr(equity)
        max_dd = self._calc_max_drawdown(equity)
        sharpe = self._calc_sharpe(returns)
        
        # 使用均线交叉次数计算 annual_turnover
        crossover_count = strategy.count_crossovers(data)
        data_years = (data.index[-1] - data.index[0]).days / 365.25
        turnover = crossover_count / data_years if data_years > 0 else 0.0
        
        logger.info(f"📊 [BacktestEngine] Crossovers: {crossover_count}, Years: {data_years:.1f}, Turnover: {turnover:.2f}x")
        
        # 假设清单
        assumptions = []
        if self.slippage_bps > 0:
            assumptions.append("slippage")
        if self.commission_rate > 0:
            assumptions.append("commission")
        if self.tax_rate > 0:
            assumptions.append("tax")
        if self.dividend_withholding > 0:
            assumptions.append("dividend_withholding")
        
        # 如果没有设置假设，默认添加基础假设
        if not assumptions:
            assumptions = ["slippage", "commission", "tax", "dividend_withholding"]
        
        logger.info(
            f"✅ [BacktestEngine] Done: CAGR={cagr:.1%}, MaxDD={max_dd:.1%}, "
            f"Sharpe={sharpe:.2f}, Turnover={turnover:.1f}x"
        )
        
        # 自动计算 param_sensitivity (如果未提供)
        if param_sensitivity is None and data_years >= 1:
            try:
                logger.info("🔄 [BacktestEngine] Calculating param sensitivity...")
                param_sensitivity = strategy.calculate_param_sensitivity(data)
                logger.info(f"✅ [BacktestEngine] Param sensitivity: {param_sensitivity:.2%}")
            except Exception as e:
                logger.warning(f"⚠️ [BacktestEngine] Param sensitivity calculation failed: {e}")
                param_sensitivity = 0.0
        
        return BacktestResult(
            cagr=cagr,
            max_drawdown=max_dd,
            sharpe=sharpe,
            annual_turnover=turnover,
            data_years=data_years,
            assumptions=assumptions,
            param_sensitivity=param_sensitivity if param_sensitivity is not None else 0.0,
            is_first_live=is_first_live,
        )

    def _calculate_returns(self, data: pd.DataFrame, signals: pd.Series) -> pd.Series:
        """计算策略收益（考虑交易成本）"""
        close = data['close']
        
        # 日收益率
        daily_returns = close.pct_change()
        
        # 信号延迟一天（避免未来函数）
        position = signals.shift(1).fillna(0)
        
        # 策略收益
        strategy_returns = position * daily_returns
        
        # 交易成本
        trade_signals = signals.diff().fillna(0).abs()
        trade_cost = trade_signals * (
            self.slippage_bps / 10000 + 
            self.commission_rate + 
            self.tax_rate
        )
        
        # 净收益
        net_returns = strategy_returns - trade_cost
        
        return net_returns.fillna(0)

    def _calc_cagr(self, equity: pd.Series) -> float:
        """计算年化收益率"""
        if len(equity) < 2:
            return 0.0
        
        total_return = equity.iloc[-1] / equity.iloc[0]
        years = len(equity) / 252  # 假设一年252个交易日
        
        if years <= 0:
            return 0.0
            
        return total_return ** (1 / years) - 1

    def _calc_max_drawdown(self, equity: pd.Series) -> float:
        """计算最大回撤"""
        cummax = equity.cummax()
        drawdown = (equity - cummax) / cummax
        return abs(drawdown.min())

    def _calc_sharpe(self, returns: pd.Series, risk_free_rate: float = 0.02) -> float:
        """计算夏普比率"""
        if len(returns) < 2:
            return 0.0
        
        excess_returns = returns - risk_free_rate / 252
        return np.sqrt(252) * excess_returns.mean() / excess_returns.std()

    def _calc_annual_turnover(self, trades: list[Trade], data: pd.DataFrame, initial_capital: float = 100000) -> float:
        """计算年化换手率
        
        换手率 = 总交易金额 / 初始资金 / 年数
        """
        if not trades or len(data) == 0:
            return 0.0
        
        years = len(data) / 252
        if years <= 0:
            return 0.0
        
        # 计算总交易金额 (往返)
        total_traded = sum(
            (t.entry_price + t.exit_price) * 100  # 假设每次交易100股
            for t in trades
        )
        
        # 年化换手率
        turnover = total_traded / initial_capital / years
        
        return turnover

    def _extract_trades(self, data: pd.DataFrame, signals: pd.Series) -> list[Trade]:
        """提取交易记录"""
        trades = []
        position = 0
        entry_price = 0.0
        entry_date = ""
        
        close = data['close']
        
        for i, (date, signal) in enumerate(signals.items()):
            if signal != position:
                # 平仓
                if position != 0:
                    exit_price = close.iloc[i]
                    pnl = (exit_price - entry_price) * position
                    return_pct = pnl / entry_price if entry_price > 0 else 0
                    
                    trades.append(Trade(
                        entry_date=entry_date,
                        exit_date=str(date.date()),
                        entry_price=entry_price,
                        exit_price=exit_price,
                        position=position,
                        pnl=pnl,
                        return_pct=return_pct,
                    ))
                
                # 开仓
                if signal != 0:
                    position = signal
                    entry_price = close.iloc[i]
                    entry_date = str(date.date())
                else:
                    position = 0
        
        return trades


# ============ Convenience Functions ============

def run_dual_ma_backtest(
    ticker: str = "SPY",
    fast_period: int = 20,
    short_period: int = 50,
    start_date: str = "2020-01-01",
    end_date: str | None = None,
    initial_capital: float = 100000,
    param_sensitivity: float | None = None,
    is_first_live: bool = False,
) -> BacktestResult:
    """快速运行 Dual MA 回测"""
    strategy = DualMAStrategy(fast_period=fast_period, short_period=short_period)
    engine = BacktestEngine()
    
    return engine.run(
        ticker=ticker,
        strategy=strategy,
        start_date=start_date,
        end_date=end_date,
        initial_capital=initial_capital,
        param_sensitivity=param_sensitivity,
        is_first_live=is_first_live,
    )
