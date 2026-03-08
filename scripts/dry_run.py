#!/usr/bin/env python3
"""
Dry Run 验证脚本

跑 N 天观察信号，不实际下单
"""
import sys
import argparse
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import List

# 添加 src 到路径
sys.path.insert(0, str(Path(__file__).parent / "src"))

from quant_trader.strategy import MACrossStrategy, RSIStrategy, MACDStrategy, Signal
from quant_trader.strategy.base_strategy import BaseStrategy
from quant_trader.data import get_provider
from quant_trader.risk import EnhancedRiskManager
from quant_trader.symbol_selector import SymbolSelector

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("quant_trader.dryrun")


def run_dry_run(
    symbols: List[str],
    strategy_name: str = "ma_cross",
    start_date: str = None,
    end_date: str = None,
    days: int = 3,
    provider_name: str = "stooq",
):
    """
    运行 Dry Run
    
    Args:
        symbols: 股票列表
        strategy_name: 策略名称
        start_date: 开始日期
        end_date: 结束日期
        days: 运行天数
        provider_name: 数据源
    """
    # 确定日期范围
    if end_date is None:
        end_date = datetime.now()
    else:
        end_date = datetime.strptime(end_date, "%Y-%m-%d")
    
    if start_date is None:
        start_date = end_date - timedelta(days=days)
    else:
        start_date = datetime.strptime(start_date, "%Y-%m-%d")
    
    start_str = start_date.strftime("%Y-%m-%d")
    end_str = end_date.strftime("%Y-%m-%d")
    
    logger.info("=" * 60)
    logger.info(f"🦞 Dry Run 验证")
    logger.info(f"   标的: {symbols}")
    logger.info(f"   策略: {strategy_name}")
    logger.info(f"   周期: {start_str} ~ {end_str}")
    logger.info("=" * 60)
    
    # 创建策略
    strategy = _create_strategy(strategy_name)
    provider = get_provider(provider_name)
    risk_mgr = EnhancedRiskManager()
    
    signals_log = []
    
    for symbol in symbols:
        logger.info(f"\n📊 分析 {symbol}...")
        
        # 获取数据
        try:
            data = provider.fetch_ohlcv(symbol, start_str, end_str)
        except Exception as e:
            logger.warning(f"⚠️ 获取数据失败: {e}")
            continue
        
        if data is None or len(data) < 5:
            logger.warning(f"⚠️ 数据不足")
            continue
        
        # 生成信号
        for date, row in data.iterrows():
            daily_data = data.loc[:date]
            
            signal = strategy.generate_signal(daily_data)
            
            if signal != Signal.HOLD:
                logger.info(f"   {date.strftime('%Y-%m-%d')}: {signal.value} {symbol}")
                
                # 风控检查
                current_price = row['close']
                
                # 更新风控状态
                risk_mgr.update_state(
                    total_equity=100000,
                    cash=50000,
                    positions={},
                )
                
                # 评估信号
                reviewed_signal = risk_mgr.evaluate(signal, symbol, current_price)
                
                if reviewed_signal != signal:
                    logger.info(f"      → 风控拦截: {reviewed_signal.value}")
                
                signals_log.append({
                    "date": date.strftime("%Y-%m-%d"),
                    "symbol": symbol,
                    "original_signal": signal.value,
                    "final_signal": reviewed_signal.value,
                    "price": current_price,
                })
    
    # 汇总
    logger.info("\n" + "=" * 60)
    logger.info("📋 信号汇总:")
    logger.info("=" * 60)
    
    if signals_log:
        total_buys = sum(1 for s in signals_log if s['final_signal'] == 'BUY')
        total_sells = sum(1 for s in signals_log if s['final_signal'] == 'SELL')
        
        logger.info(f"   买入信号: {total_buys}")
        logger.info(f"   卖出信号: {total_sells}")
        
        for s in signals_log:
            logger.info(f"   {s['date']} {s['symbol']}: {s['original_signal']} → {s['final_signal']} @ {s['price']:.2f}")
    else:
        logger.info("   无信号")
    
    return signals_log


def _create_strategy(strategy_name: str) -> BaseStrategy:
    """创建策略"""
    strategies = {
        "ma_cross": lambda: MACrossStrategy(short_window=10, long_window=30),
        "rsi": lambda: RSIStrategy(period=14, oversold=30, overbought=70),
        "macd": lambda: MACDStrategy(fast_period=12, slow_period=26, signal_period=9),
    }
    
    factory = strategies.get(strategy_name)
    if factory is None:
        logger.warning(f"⚠️ 未知策略 {strategy_name}，使用 MA Cross")
        return MACrossStrategy()
    
    return factory()


def auto_select_and_run(
    strategy_name: str = "ma_cross",
    n_symbols: int = 3,
    days: int = 3,
    market: str = "hk",
):
    """自动选标的并运行"""
    logger.info(f"🔍 自动选择标的 (市场: {market})...")
    
    selector = SymbolSelector(market=market)
    symbols = selector.select(n=n_symbols)
    
    return run_dry_run(
        symbols=symbols,
        strategy_name=strategy_name,
        days=days,
    )


def main():
    parser = argparse.ArgumentParser(description="Dry Run 验证")
    parser.add_argument("--symbols", nargs="+", help="股票代码列表")
    parser.add_argument("--strategy", default="ma_cross", help="策略名称")
    parser.add_argument("--days", type=int, default=3, help="运行天数")
    parser.add_argument("--auto-select", action="store_true", help="自动选择标的")
    parser.add_argument("--market", default="hk", help="市场 (hk/us)")
    parser.add_argument("--n-symbols", type=int, default=3, help="标的数量")
    parser.add_argument("--start", help="开始日期 YYYY-MM-DD")
    parser.add_argument("--end", help="结束日期 YYYY-MM-DD")
    
    args = parser.parse_args()
    
    if args.auto_select:
        auto_select_and_run(
            strategy_name=args.strategy,
            n_symbols=args.n_symbols,
            days=args.days,
            market=args.market,
        )
    elif args.symbols:
        run_dry_run(
            symbols=args.symbols,
            strategy_name=args.strategy,
            start_date=args.start,
            end_date=args.end,
            days=args.days,
        )
    else:
        # 默认自动选标的
        auto_select_and_run(
            strategy_name=args.strategy,
            n_symbols=args.n_symbols,
            days=args.days,
            market=args.market,
        )


if __name__ == "__main__":
    main()
