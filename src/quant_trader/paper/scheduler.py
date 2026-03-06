"""
定时任务调度器

每日自动执行模拟盘
"""
import asyncio
import argparse
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

# 添加 src 到路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from quant_trader.strategy import MACrossStrategy
from quant_trader.paper.service import PaperTradingService

logger = logging.getLogger("quant_trader.scheduler")

# 默认配置
DEFAULT_SYMBOL = "2800.HK"
DEFAULT_INITIAL_CAPITAL = 1_000_000
DEFAULT_DB_PATH = "data/paper_trading.db"
DEFAULT_SCHEDULE_TIME = "18:00"  # 每天 18:00 执行


class Scheduler:
    """定时任务调度器"""
    
    def __init__(
        self,
        service: PaperTradingService,
        schedule_time: str = DEFAULT_SCHEDULE_TIME,
    ):
        """
        初始化
        
        Args:
            service: 模拟盘服务
            schedule_time: 执行时间 (HH:MM)
        """
        self.service = service
        self.schedule_time = schedule_time
    
    def should_run_now(self) -> bool:
        """检查是否应该现在执行"""
        now = datetime.now()
        current_time = now.strftime("%H:%M")
        
        # 检查时间是否匹配
        if current_time >= self.schedule_time:
            # 检查今天是否已执行
            today = now.strftime("%Y-%m-%d")
            from quant_trader.storage import DailyNavRepository
            
            db = self.service.db
            nav_repo = DailyNavRepository(db)
            
            if not nav_repo.exists(today):
                return True
        
        return False
    
    async def run_forever(self, interval_minutes: int = 60):
        """
        持续运行
        
        Args:
            interval_minutes: 检查间隔（分钟）
        """
        logger.info(f"⏰ 调度器启动: 每日 {self.schedule_time} 执行")
        
        while True:
            try:
                if self.should_run_now():
                    logger.info("🎯 触发执行")
                    self.service.run_once()
                else:
                    now = datetime.now().strftime("%H:%M")
                    logger.debug(f"等待中... ({now})")
                
            except Exception as e:
                logger.error(f"执行错误: {e}")
            
            # 等待
            await asyncio.sleep(interval_minutes * 60)
    
    def run_once_cli(self):
        """CLI 手动执行一次"""
        logger.info("🎯 执行一次")
        self.service.run_once()


def main():
    """CLI 入口"""
    parser = argparse.ArgumentParser(description="模拟盘定时任务")
    parser.add_argument(
        "--once",
        action="store_true",
        help="只执行一次，不持续运行"
    )
    parser.add_argument(
        "--symbol",
        default=DEFAULT_SYMBOL,
        help=f"股票代码 (默认: {DEFAULT_SYMBOL})"
    )
    parser.add_argument(
        "--capital",
        type=float,
        default=DEFAULT_INITIAL_CAPITAL,
        help=f"初始资金 (默认: {DEFAULT_INITIAL_CAPITAL})"
    )
    parser.add_argument(
        "--db-path",
        default=DEFAULT_DB_PATH,
        help=f"数据库路径 (默认: {DEFAULT_DB_PATH})"
    )
    parser.add_argument(
        "--schedule-time",
        default=DEFAULT_SCHEDULE_TIME,
        help=f"执行时间 (默认: {DEFAULT_SCHEDULE_TIME})"
    )
    parser.add_argument(
        "--provider",
        default="stooq",
        help="数据源 (默认: stooq)"
    )
    parser.add_argument(
        "--short-window",
        type=int,
        default=5,
        help="短期均线周期"
    )
    parser.add_argument(
        "--long-window",
        type=int,
        default=20,
        help="长期均线周期"
    )
    
    args = parser.parse_args()
    
    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )
    
    # 创建策略
    strategy = MACrossStrategy(
        short_window=args.short_window,
        long_window=args.long_window,
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
    
    if args.once:
        # 只执行一次
        service.run_once()
    else:
        # 持续运行
        scheduler = Scheduler(service, args.schedule_time)
        
        try:
            asyncio.run(scheduler.run_forever())
        except KeyboardInterrupt:
            logger.info("调度器停止")
    
    service.close()


if __name__ == "__main__":
    main()
