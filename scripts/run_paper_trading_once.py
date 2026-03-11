#!/usr/bin/env python3
"""
手动运行模拟盘一次

用法:
    python scripts/run_paper_trading_once.py
    python scripts/run_paper_trading_once.py --symbol 2800.HK --capital 1000000
"""
import argparse
import logging
import sys
from pathlib import Path

# 添加 src 到路径
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from quant_trader.strategy import MACrossStrategy
from quant_trader.paper import PaperTradingService
from quant_trader.storage import init_db
from quant_trader.config import get_settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger()


def main():
    settings = get_settings()
    parser = argparse.ArgumentParser(description="手动运行模拟盘")
    parser.add_argument("--symbol", default="2800.HK", help="股票代码")
    parser.add_argument("--capital", type=float, default=1_000_000, help="初始资金")
    parser.add_argument("--db-path", default=settings.storage.paper_db_path, help="数据库路径")
    parser.add_argument("--provider", default="stooq", help="数据源")
    parser.add_argument("--short", type=int, default=5, help="短期均线")
    parser.add_argument("--long", type=int, default=20, help="长期均线")
    
    args = parser.parse_args()
    
    logger.info("=" * 50)
    logger.info("模拟盘手动执行")
    logger.info("=" * 50)
    
    # 初始化数据库
    db = init_db(args.db_path)
    
    # 创建策略
    strategy = MACrossStrategy(
        short_window=args.short,
        long_window=args.long,
    )
    
    # 创建服务
    service = PaperTradingService(
        strategy=strategy,
        symbol=args.symbol,
        db_path=args.db_path,
        initial_capital=args.capital,
        provider_name=args.provider,
    )
    
    # 启动
    service.bootstrap()
    
    # 执行
    service.run_once()
    
    # 关闭
    service.close()
    
    logger.info("完成!")


if __name__ == "__main__":
    main()
