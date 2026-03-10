"""
定时任务调度器

使用 APScheduler 实现每日定时执行
"""
import argparse
import logging
import os
import signal
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from dotenv import load_dotenv

# 添加 src 到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

# 加载券商凭证
_credentials_dir = Path(__file__).parent.parent.parent / ".credentials"
load_dotenv(_credentials_dir / "longbridge.env")
load_dotenv(_credentials_dir / "alphavantage.env")
load_dotenv(_credentials_dir / "itick.env")

# 设置代理 (如果有)
if not os.environ.get("HTTP_PROXY"):
    os.environ["HTTP_PROXY"] = "http://127.0.0.1:7897"
    os.environ["HTTPS_PROXY"] = "http://127.0.0.1:7897"

from quant_trader.orchestrator import create_orchestrator, DailyReport
from quant_trader.policy import load_policy

logger = logging.getLogger("quant_trader.scheduler")


class TradingScheduler:
    """交易定时调度器"""
    
    def __init__(
        self,
        broker_config: dict,
        symbols: list[str],
        provider_name: str = "stooq",
        run_time: str = "15:30",
        timezone: str = "Asia/Hong_Kong",
    ):
        """
        初始化
        
        Args:
            broker_config: 券商配置
            symbols: 股票列表
            provider_name: 数据源
            run_time: 执行时间 (HH:MM)
            timezone: 时区
        """
        self.broker_config = broker_config
        self.symbols = symbols
        self.provider_name = provider_name
        self.run_time = run_time
        self.timezone = timezone
        
        self.scheduler = BlockingScheduler(timezone=timezone)
        self.orchestrator: Optional[object] = None
        self._running = False
    
    def _run_task(self):
        """执行交易任务"""
        logger.info("=" * 50)
        logger.info(f"⏰ 定时任务触发: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("=" * 50)
        
        try:
            # 创建编排器
            self.orchestrator = create_orchestrator(
                broker_config=self.broker_config,
                symbols=self.symbols,
                provider_name=self.provider_name,
            )
            
            # 执行每日流程
            report = self.orchestrator.run_daily()
            
            # 打印报告摘要
            self._print_report(report)
            
        except Exception as e:
            logger.exception(f"❌ 任务执行失败: {e}")
        finally:
            if self.orchestrator:
                try:
                    self.orchestrator.broker.disconnect()
                    self.orchestrator.db.close()
                except Exception:
                    pass
    
    def _print_report(self, report: DailyReport):
        """打印报告摘要"""
        logger.info("-" * 50)
        logger.info("📋 执行摘要:")
        logger.info(f"  日期: {report.date}")
        logger.info(f"  耗时: {report.total_runtime_seconds:.1f}s")
        logger.info("")
        
        for step in report.steps:
            emoji = "✅" if step.status.value == "success" else "❌" if step.status.value == "failed" else "⏭️"
            logger.info(f"  {emoji} {step.step_name}: {step.message}")
        
        if report.signals:
            logger.info("")
            logger.info("📈 信号:")
            for s in report.signals:
                logger.info(f"  {s['symbol']}: {s['signal']}")
        
        if report.account:
            logger.info("")
            logger.info("💰 账户:")
            logger.info(f"  现金: HKD {report.account.get('cash', 0):,.2f}")
        
        logger.info("-" * 50)
    
    def start(self):
        """启动调度器"""
        # 解析时间
        hour, minute = map(int, self.run_time.split(":"))
        
        # 添加任务
        self.scheduler.add_job(
            self._run_task,
            CronTrigger(hour=hour, minute=minute),
            id="daily_trading",
            name="每日交易",
            replace_existing=True,
        )
        
        logger.info(f"⏰ 调度器已启动: 每日 {self.run_time} ({self.timezone})")
        logger.info(f"📋 股票: {', '.join(self.symbols)}")
        logger.info(f"🔧 券商: {self.broker_config.get('type', 'unknown')}")
        logger.info(f"📡 数据源: {self.provider_name}")
        
        # 设置信号处理
        def signal_handler(signum, frame):
            logger.info("\n🛑 收到停止信号，正在关闭...")
            self.stop()
            sys.exit(0)
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        # 启动
        self._running = True
        self.scheduler.start()
    
    def stop(self):
        """停止调度器"""
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
        logger.info("🔌 调度器已停止")
    
    def run_now(self):
        """立即执行一次"""
        logger.info("🎯 立即执行模式")
        self._run_task()


def main():
    """CLI 入口"""
    parser = argparse.ArgumentParser(description="交易调度器")
    
    # 运行模式
    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument(
        "--run-now",
        action="store_true",
        help="立即执行一次（调试用）"
    )
    mode_group.add_argument(
        "--daemon",
        action="store_true",
        help="常驻后台定时触发"
    )
    
    # 配置
    parser.add_argument(
        "--env",
        default="sim",
        choices=["sim", "live"],
        help="运行环境 (sim=模拟, live=实盘)"
    )
    parser.add_argument(
        "--symbols",
        nargs="+",
        default=["2800.HK"],
        help="股票列表"
    )
    parser.add_argument(
        "--provider",
        default="stooq",
        help="数据源 (默认: stooq)"
    )
    parser.add_argument(
        "--broker-type",
        default="longbridge",
        choices=["paper", "futu", "longbridge"],
        help="券商类型"
    )
    parser.add_argument(
        "--mode",
        default="dry_run",
        choices=["readonly", "dry_run", "live"],
        help="券商模式"
    )
    parser.add_argument(
        "--run-time",
        default="15:30",
        help="执行时间 (默认: 15:30)"
    )
    parser.add_argument(
        "--config",
        default="config/policy.yaml",
        help="配置文件路径"
    )
    
    args = parser.parse_args()
    
    # 配置日志
    import os
    log_dir = "logs"
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, "quant_trader.log")
    
    # 同时输出到控制台和文件
    file_handler = logging.FileHandler(log_file)
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%H:%M:%S")
    )
    
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        handlers=[logging.StreamHandler(), file_handler],
    )
    
    logger.info(f"日志文件: {log_file}")
    
    # 加载配置
    policy = load_policy(args.config)
    
    # 券商配置
    broker_config = {
        "type": args.broker_type,
        "mode": args.mode,
    }
    
    # 从配置覆盖 (policy.broker 是 dataclass)
    if hasattr(policy, "broker"):
        broker_config.update({
            "type": getattr(policy.broker, "type", args.broker_type),
            "mode": getattr(policy.broker, "mode", args.mode),
            "max_order_value": getattr(policy.broker, "max_order_value", 5000),
            "require_confirm_live": getattr(policy.broker, "require_confirm_live", True),
        })
    
    # 股票列表
    symbols = args.symbols
    if hasattr(policy, "portfolio") and hasattr(policy.portfolio, "symbols"):
        symbols = policy.portfolio.symbols
    
    # 调度配置
    run_time = args.run_time
    timezone = "Asia/Hong_Kong"
    
    if hasattr(policy, "scheduler"):
        if hasattr(policy.scheduler, "run_time"):
            run_time = policy.scheduler.run_time
        if hasattr(policy.scheduler, "timezone"):
            timezone = policy.scheduler.timezone
    
    # 根据 env 调整模式
    if args.env == "sim":
        broker_config["mode"] = "dry_run"
        logger.info("🧪 模拟模式: 使用 dry_run")
    elif args.env == "live":
        broker_config["mode"] = "live"
        logger.warning("⚠️ 实盘模式: 使用 live")
    
    # 创建调度器
    scheduler = TradingScheduler(
        broker_config=broker_config,
        symbols=symbols,
        provider_name=args.provider,
        run_time=run_time,
        timezone=timezone,
    )
    
    # 运行
    if args.run_now:
        scheduler.run_now()
    else:
        scheduler.start()


if __name__ == "__main__":
    main()
