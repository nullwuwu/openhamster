"""
标的池管理器

自动筛选和管理交易标的
"""
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
from datetime import datetime
import pandas as pd
import numpy as np

from .data import get_provider

logger = logging.getLogger("quant_trader.symbols")


@dataclass
class SymbolMetrics:
    """标的指标"""
    symbol: str
    # 流动性
    avg_volume: float = 0
    volume_ratio: float = 0  # 与市场平均比较
    
    # 波动性
    volatility: float = 0  # 日收益率标准差
    atr_pct: float = 0  # ATR 占价格比例
    
    # 趋势
    trend_score: float = 0  # -1 到 1
    
    # 相关性
    correlation_to_portfolio: float = 0
    
    # 综合得分
    score: float = 0


class SymbolSelector:
    """标的选择器"""
    
    # 预定义候选池 (可根据需要扩展)
    DEFAULT_POOL = {
        "hk": [
            "2800.HK",  # 恒生指数 ETF - 指数
            "0700.HK",  # 腾讯 - 科技
            "9988.HK",  # 阿里巴巴 - 科技
            "2318.HK",  # 平安保险 - 金融
            "0939.HK",  # 建设银行 - 金融
            "1299.HK",  # 友邦保险 - 金融
            "0388.HK",  # 港交所 - 金融
            "0005.HK",  # 汇丰控股 - 金融
            "0941.HK",  # 中国移动 - 通信
            "0669.HK",  # 中国平安 - 科技
        ],
        "us": [
            "SPY",    # S&P 500 ETF - 指数
            "QQQ",    # Nasdaq 100 ETF - 指数
            "AAPL",   # Apple - 科技
            "MSFT",   # Microsoft - 科技
            "GOOGL",  # Google - 科技
            "AMZN",   # Amazon - 消费
            "NVDA",   # Nvidia - 科技
            "TSLA",   # Tesla - 汽车
            "JPM",    # JP Morgan - 金融
            "V",      # Visa - 金融
        ],
    }
    
    # 板块分类
    SECTOR_MAP = {
        "hk": {
            "2800.HK": "index",
            "0700.HK": "tech",
            "9988.HK": "tech",
            "2318.HK": "financial",
            "0939.HK": "financial",
            "1299.HK": "financial",
            "0388.HK": "financial",
            "0005.HK": "financial",
            "0941.HK": "telecom",
            "0669.HK": "tech",
        },
        "us": {
            "SPY": "index",
            "QQQ": "index",
            "AAPL": "tech",
            "MSFT": "tech",
            "GOOGL": "tech",
            "AMZN": "consumer",
            "NVDA": "tech",
            "TSLA": "auto",
            "JPM": "financial",
            "V": "financial",
        },
    }
    
    def __init__(
        self,
        market: str = "hk",
        provider_name: str = "stooq",
        max_per_sector: int = 2,
    ):
        """
        初始化
        
        Args:
            market: 市场 (hk/us)
            provider_name: 数据源
            max_per_sector: 同一板块最多选几个
        """
        self.market = market
        self.provider = get_provider(provider_name)
        self.candidates = self.DEFAULT_POOL.get(market, self.DEFAULT_POOL["hk"])
        self.max_per_sector = max_per_sector
        self.sector_map = self.SECTOR_MAP.get(market, {})
    
    def select(
        self,
        n: int = 3,
        lookback_days: int = 60,
        min_volume: float = 1000000,
        max_correlation: float = 0.7,
        exclude_sectors: List[str] = None,
    ) -> List[str]:
        """
        筛选标的
        
        Args:
            n: 选择数量
            lookback_days: 回看天数
            min_volume: 最小日均成交量
            max_correlation: 组合内最大相关性
            exclude_sectors: 排除板块
            
        Returns:
            List[str]: 选中的标的
        """
        logger.info(f"🔍 开始标的筛选: {len(self.candidates)} 个候选")
        
        # 获取所有候选标的数据
        all_metrics = []
        
        for symbol in self.candidates:
            try:
                metrics = self._calculate_metrics(symbol, lookback_days)
                
                # 过滤流动性
                if metrics.avg_volume < min_volume:
                    logger.debug(f"⚠️ {symbol} 流动性不足: {metrics.avg_volume:.0f}")
                    continue
                
                # 过滤波动性 (太高的不要)
                if metrics.volatility > 0.10:  # 日波动 > 10%
                    logger.debug(f"⚠️ {symbol} 波动过大: {metrics.volatility:.2%}")
                    continue
                
                all_metrics.append(metrics)
                
            except Exception as e:
                logger.warning(f"⚠️ {symbol} 计算指标失败: {e}")
        
        if not all_metrics:
            logger.warning("⚠️ 无有效标的，使用默认池")
            return self.candidates[:n]
        
        # 计算综合得分
        all_metrics = self._calculate_scores(all_metrics)
        
        # 按得分排序
        all_metrics.sort(key=lambda x: x.score, reverse=True)
        
        # 选择低相关性的标的
        selected = self._select_diverse(all_metrics, n, max_correlation)
        
        logger.info(f"✅ 选中标的: {selected}")
        
        return selected
    
    def _calculate_metrics(self, symbol: str, days: int) -> SymbolMetrics:
        """计算标的指标"""
        # 获取数据
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - pd.Timedelta(days=days * 2)).strftime("%Y-%m-%d")
        
        try:
            data = self.provider.fetch_ohlcv(symbol, start_date, end_date)
        except Exception as e:
            raise ValueError(f"获取数据失败: {e}")
        
        if data is None or len(data) < days // 2:
            raise ValueError(f"数据不足: {len(data) if data is not None else 0} 条")
        
        # 只取最后 days 天
        data = data.tail(days)
        
        # 计算收益率
        returns = data['close'].pct_change().dropna()
        
        # 流动性指标
        avg_volume = data['volume'].mean()
        
        # 波动性指标
        volatility = returns.std()
        
        # ATR
        high_low = data['high'] - data['low']
        atr = high_low.rolling(14).mean().iloc[-1]
        close = data['close'].iloc[-1]
        atr_pct = atr / close if close > 0 else 0
        
        # 趋势指标 (价格 vs MA)
        ma20 = data['close'].rolling(20).mean().iloc[-1]
        ma60 = data['close'].rolling(60).mean().iloc[-1]
        current_price = data['close'].iloc[-1]
        
        # 趋势得分: 价格 > MA20 > MA60 为强势
        if pd.notna(ma20) and pd.notna(ma60):
            if current_price > ma20 > ma60:
                trend_score = 1.0
            elif current_price > ma20:
                trend_score = 0.5
            elif current_price < ma20 < ma60:
                trend_score = -1.0
            elif current_price < ma20:
                trend_score = -0.5
            else:
                trend_score = 0
        else:
            trend_score = 0
        
        return SymbolMetrics(
            symbol=symbol,
            avg_volume=avg_volume,
            volatility=volatility,
            atr_pct=atr_pct,
            trend_score=trend_score,
        )
    
    def _calculate_scores(self, metrics: List[SymbolMetrics]) -> List[SymbolMetrics]:
        """计算综合得分"""
        if not metrics:
            return metrics
        
        # 归一化指标
        volumes = [m.avg_volume for m in metrics]
        volatilities = [m.volatility for m in metrics]
        trends = [m.trend_score for m in metrics]
        
        vol_min, vol_max = min(volumes), max(volumes)
        vol_range = vol_max - vol_min if vol_max > vol_min else 1
        
        vol_min_v, vol_max_v = min(volatilities), max(volatilities)
        vol_range_v = vol_max_v - vol_min_v if vol_max_v > vol_min_v else 1
        
        for m in metrics:
            # 流动性得分 (越高越好)
            volume_score = (m.avg_volume - vol_min) / vol_range if vol_range > 0 else 0
            
            # 波动性得分 (适中最好，太高不好)
            if m.volatility < 0.02:
                volatility_score = 1.0
            elif m.volatility > 0.08:
                volatility_score = 0.0
            else:
                volatility_score = 1.0 - (m.volatility - 0.02) / 0.06
            
            # 趋势得分
            trend_score = m.trend_score
            
            # 综合得分
            m.score = (
                volume_score * 0.3 +
                volatility_score * 0.3 +
                trend_score * 0.4
            )
        
        return metrics
    
    def _select_diverse(
        self,
        metrics: List[SymbolMetrics],
        n: int,
        max_correlation: float,
    ) -> List[str]:
        """选择低相关性标的（考虑板块分散）"""
        if len(metrics) <= n:
            return [m.symbol for m in metrics]
        
        selected = []
        sector_count = {}  # {sector: count}
        
        # 按得分排序
        sorted_metrics = sorted(metrics, key=lambda x: x.score, reverse=True)
        
        for m in sorted_metrics:
            if len(selected) >= n:
                break
            
            # 板块检查
            sector = self.sector_map.get(m.symbol, "other")
            if sector_count.get(sector, 0) >= self.max_per_sector:
                logger.debug(f"⚠️ {m.symbol} 板块 {sector} 已达上限，跳过")
                continue
            
            selected.append(m.symbol)
            sector_count[sector] = sector_count.get(sector, 0) + 1
        
        return selected
    
    def get_pool(self) -> List[str]:
        """获取候选池"""
        return self.candidates.copy()
    
    def add_candidate(self, symbol: str) -> None:
        """添加候选标的"""
        if symbol not in self.candidates:
            self.candidates.append(symbol)
    
    def remove_candidate(self, symbol: str) -> None:
        """移除候选标的"""
        if symbol in self.candidates:
            self.candidates.remove(symbol)


class DynamicSymbolManager:
    """动态标的管理器 - 根据市场状态调整持仓"""
    
    def __init__(
        self,
        selector: SymbolSelector,
        rebalance_threshold: float = 0.2,
    ):
        """
        Args:
            selector: 标的选择器
            rebalance_threshold: 再平衡阈值 (20% 变化触发)
        """
        self.selector = selector
        self.rebalance_threshold = rebalance_threshold
        self.current_symbols: List[str] = []
        self.last_rebalance_date: Optional[str] = None
    
    def should_rebalance(self, current_positions: List[str]) -> bool:
        """判断是否需要再平衡"""
        if not current_positions:
            return True
        
        # 检查持仓是否在当前候选池中
        pool = set(self.selector.get_pool())
        
        # 有持仓被移除
        for symbol in current_positions:
            if symbol not in pool:
                logger.info(f"⚠️ 持仓 {symbol} 已不在候选池，需要再平衡")
                return True
        
        # 检查是否需要更换标的
        target = set(self.selector.select(n=len(current_positions)))
        current = set(current_positions)
        
        # 计算变化比例
        changed = len(target - current) / len(target) if target else 0
        
        if changed >= self.rebalance_threshold:
            logger.info(f"🔄 标的池变化: {changed:.0%}，触发再平衡")
            return True
        
        return False
    
    def rebalance(
        self,
        current_positions: List[str] = None,
        n: int = 3,
    ) -> List[str]:
        """执行再平衡"""
        current_positions = current_positions or []
        
        new_symbols = self.selector.select(n=n)
        
        self.current_symbols = new_symbols
        self.last_rebalance_date = datetime.now().strftime("%Y-%m-%d")
        
        logger.info(f"🔄 标的再平衡: {current_positions} → {new_symbols}")
        
        return new_symbols
