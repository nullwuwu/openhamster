"""
交易编排器

每日自动执行完整交易流程
"""
import logging
import subprocess
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any
from dataclasses import dataclass, field
from enum import Enum

import pandas as pd

from .strategy import BaseStrategy, MACrossStrategy, get_strategy_factory, StrategyFactory
from .strategy.signals import Signal
from .strategy_selector import get_strategy_selector
from .market_regime import get_market_regime
from .broker import BaseBroker, create_broker
from .data import get_provider, get_source_manager, reset_source_manager
from .storage import Database, OrderRepository, PositionRepository, DailyNavRepository, init_db
from .storage.models import DailyNav
from .policy import load_policy
from .notify import NotifierFactory
from .universe_selector import AStockUniverseSelector, UniverseConfig
from .config import get_settings

logger = logging.getLogger("quant_trader.orchestrator")


class StepStatus(Enum):
    """步骤状态"""
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
    CONTINUE = "continue"  # 失败但继续下一步


@dataclass
class StepResult:
    """步骤执行结果"""
    step_name: str
    status: StepStatus
    message: str = ""
    data: Dict[str, Any] = field(default_factory=dict)
    error: Optional[Exception] = None


@dataclass
class DailyReport:
    """每日报告"""
    date: str
    steps: List[StepResult] = field(default_factory=list)
    signals: List[Dict] = field(default_factory=list)
    orders: List[Dict] = field(default_factory=list)
    positions: List[Dict] = field(default_factory=list)
    account: Dict[str, float] = field(default_factory=dict)
    total_runtime_seconds: float = 0


class Orchestrator:
    """
    交易编排器
    
    按顺序执行:
    1. 拉取行情数据
    2. 运行策略生成信号
    3. 风控检查
    4. 执行下单
    5. 记录日志
    6. 发送通知
    """
    
    def __init__(
        self,
        broker: BaseBroker,
        strategy: Optional[BaseStrategy],
        db: Database,
        symbols: List[str],
        provider_name: str = "stooq",
        notifier: Optional[Any] = None,
        strategy_factory: Optional[StrategyFactory] = None,
        strategy_mode: str = "manual",
        manual_strategy: str = "ma_cross",
        strategy_params: Optional[dict] = None,
        universe_selector: Optional[AStockUniverseSelector] = None,
        universe_mode: str = "static",
        universe_top_n: int = 20,
    ):
        """
        初始化
        
        Args:
            broker: 券商
            strategy: 策略
            db: 数据库
            symbols: 股票列表
            provider_name: 数据源名称
            notifier: 通知器
        """
        self.broker = broker
        self.strategy = strategy
        self.db = db
        self.symbols = symbols
        self.provider_name = provider_name
        self.notifier = notifier
        self.strategy_factory = strategy_factory or get_strategy_factory()
        self._use_injected_strategy = strategy is not None and strategy_factory is None
        self.strategy_mode = strategy_mode
        self.manual_strategy = manual_strategy
        self.strategy_params = strategy_params or {}
        self.universe_selector = universe_selector
        self.universe_mode = universe_mode
        self.universe_top_n = universe_top_n
        
        # 仓库
        self.order_repo = OrderRepository(db)
        self.position_repo = PositionRepository(db)
        self.nav_repo = DailyNavRepository(db)
        
        # 数据源
        self.provider = get_provider(provider_name)
        self.source_manager = get_source_manager()
        self.strategy_selector = get_strategy_selector()
        self.market_regime = get_market_regime()

        # 策略信号缓存
        self._signals: Dict[str, Signal] = {}
        self._strategy_by_symbol: Dict[str, BaseStrategy] = {}
    
    def run_daily(self) -> DailyReport:
        """
        执行每日交易流程
        
        Returns:
            DailyReport: 每日报告
        """
        start_time = datetime.now()
        self._runtime_seconds = 0  # 初始化
        self._report_steps = []  # 用于通知
        self._signals = {}
        self._strategy_by_symbol = {}
        report = DailyReport(date=start_time.strftime("%Y-%m-%d"))
        
        logger.info("=" * 50)
        logger.info("🚀 开始每日交易流程")
        logger.info("=" * 50)
        
        # Step 1: 拉取行情数据
        result = self._step_fetch_data()
        report.steps.append(result)
        self._report_steps.append(result)
        
        if result.status == StepStatus.FAILED:
            # Step 1 失败，终止流程
            logger.error("❌ Step 1 失败，终止流程")
            self._send_notification(report)
            report.total_runtime_seconds = (datetime.now() - start_time).total_seconds()
            return report
        
        # Step 2: 运行策略
        result = self._step_generate_signals()
        report.steps.append(result)
        self._report_steps.append(result)
        report.signals = [
            {"symbol": symbol, "signal": signal.value}
            for symbol, signal in self._signals.items()
        ]
        
        # Step 3: 风控检查
        result = self._step_risk_check()
        report.steps.append(result)
        self._report_steps.append(result)
        
        if result.status == StepStatus.FAILED:
            # 风控失败，跳过执行但继续后续步骤
            logger.warning("⚠️ 风控检查失败，跳过执行步骤")
        
        # Step 4: 执行下单 (如果风控通过)
        risk_passed = any(s.status != StepStatus.FAILED for s in report.steps[2:3])
        if risk_passed and self._signals:
            result = self._step_execute_orders()
            report.steps.append(result)
            report.orders = self.order_repo.get_all()
        else:
            report.steps.append(StepResult(
                step_name="Step 4: 执行下单",
                status=StepStatus.SKIPPED,
                message="风控失败或无信号，跳过执行"
            ))
        
        # Step 5: 记录日志
        result = self._step_logging()
        report.steps.append(result)
        self._report_steps.append(result)
        
        # Step 6: 发送通知
        result = self._step_notify()
        report.steps.append(result)
        self._report_steps.append(result)
        
        # 获取最新账户状态
        report.account = self.broker.get_account()
        report.positions = self.broker.get_positions()
        
        self._runtime_seconds = (datetime.now() - start_time).total_seconds()
        report.total_runtime_seconds = self._runtime_seconds
        
        logger.info("=" * 50)
        logger.info(f"✅ 每日交易流程完成，耗时 {self._runtime_seconds:.1f}s")
        logger.info("=" * 50)
        
        return report
    
    def _step_fetch_data(self) -> StepResult:
        """Step 1: 拉取行情数据"""
        logger.info("📊 Step 1: 拉取行情数据")

        # 动态选股（A股）
        if self.universe_mode == "dynamic_cn" and self.universe_selector is not None:
            try:
                selected = self.universe_selector.select()
                if selected:
                    self.symbols = selected[: self.universe_top_n]
                    logger.info(f"  🧠 动态选股完成: {len(self.symbols)} 只")
            except Exception as exc:
                logger.warning(f"  ⚠️ 动态选股失败，使用原始股票池: {exc}")

        success_count = 0
        failed_symbols = []

        try:
            end_date = datetime.now().strftime("%Y-%m-%d")
            start_date = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")

            for symbol in self.symbols:
                try:
                    logger.info(f"  拉取 {symbol}...")
                    try:
                        df = self.provider.fetch_ohlcv(
                            ticker=symbol,
                            start=start_date,
                            end=end_date,
                        )
                        if not isinstance(df, pd.DataFrame) and hasattr(self.provider, "get_bars"):
                            df = self.provider.get_bars(symbol, start_date, end_date)
                    except Exception:
                        df = self.source_manager.fetch_ohlcv(
                            ticker=symbol,
                            start=start_date,
                            end=end_date,
                        )
                    if df is not None and not df.empty:
                        logger.info(f"    获取 {len(df)} 条数据")
                        success_count += 1
                    else:
                        logger.warning("    无数据，跳过")
                        failed_symbols.append(symbol)
                except Exception as e:
                    logger.warning(f"    ⚠️ {symbol} 拉取失败: {e}")
                    failed_symbols.append(symbol)
            
            if success_count == 0:
                return StepResult(
                    step_name="Step 1: 拉取行情数据",
                    status=StepStatus.FAILED,
                    message=f"所有股票拉取失败: {failed_symbols}",
                )
            
            status = StepStatus.SUCCESS if not failed_symbols else StepStatus.CONTINUE
            msg = f"成功 {success_count} 只{f', 失败 {len(failed_symbols)} 只: {failed_symbols}' if failed_symbols else ''}"
            return StepResult(
                step_name="Step 1: 拉取行情数据",
                status=status,
                message=msg,
            )
            
        except Exception as e:
            logger.error(f"  ❌ 拉取失败: {e}")
            return StepResult(
                step_name="Step 1: 拉取行情数据",
                status=StepStatus.FAILED,
                message=str(e),
                error=e,
            )
    
    def _step_generate_signals(self) -> StepResult:
        """Step 2: 运行策略生成信号"""
        logger.info("📈 Step 2: 运行策略生成信号")

        success_count = 0
        failed_symbols = []

        try:
            end_date = datetime.now().strftime("%Y-%m-%d")
            start_date = (datetime.now() - timedelta(days=120)).strftime("%Y-%m-%d")

            for symbol in self.symbols:
                logger.info(f"  分析 {symbol}...")

                try:
                    # 拉取数据
                    try:
                        df = self.provider.fetch_ohlcv(
                            ticker=symbol,
                            start=start_date,
                            end=end_date,
                        )
                        if not isinstance(df, pd.DataFrame) and hasattr(self.provider, "get_bars"):
                            df = self.provider.get_bars(symbol, start_date, end_date)
                    except Exception:
                        df = self.source_manager.fetch_ohlcv(
                            ticker=symbol,
                            start=start_date,
                            end=end_date,
                        )
                    
                    if df is None or df.empty:
                        logger.warning("    无数据，跳过")
                        failed_symbols.append(symbol)
                        continue

                    if self._use_injected_strategy and self.strategy is not None:
                        selected_name = getattr(self.strategy, "name", "injected")
                        strategy = self.strategy
                    else:
                        selected_name = self.manual_strategy
                        if self.strategy_mode == "auto":
                            ohlcv = {
                                "close": df["close"].tolist(),
                                "high": df["high"].tolist(),
                                "low": df["low"].tolist(),
                                "volume": df["volume"].tolist(),
                            }
                            regime_result = self.market_regime.analyze(ohlcv)
                            if regime_result is not None:
                                recommendation = self.strategy_selector.select_primary(
                                    market_regime=regime_result.regime,
                                    volatility=float(regime_result.indicators.get("volatility", 0.02)),
                                )
                                selected_name = recommendation.strategy.value

                        params = self.strategy_params.get(selected_name, {})
                        if self.strategy_factory:
                            strategy = self.strategy_factory.create(
                                name=selected_name,
                                mode="stream",
                                params=params,
                            )
                        elif self.strategy:
                            strategy = self.strategy
                        else:
                            strategy = MACrossStrategy(short_window=5, long_window=20)

                    signal = strategy.generate_signal(df)
                    self._strategy_by_symbol[symbol] = strategy
                    self._signals[symbol] = signal

                    emoji = "🟢" if signal == Signal.BUY else "🔴" if signal == Signal.SELL else "⚪"
                    logger.info(f"    {emoji} {symbol}: {signal.value} [{selected_name}]")
                    success_count += 1
                except Exception as e:
                    logger.warning(f"    ⚠️ {symbol} 分析失败: {e}")
                    failed_symbols.append(symbol)

            # 动态池：不在池中的现有持仓，标记卖出
            if self.universe_mode == "dynamic_cn":
                current_positions = self.broker.get_positions()
                current_symbols = {pos.get("symbol") for pos in current_positions if pos.get("symbol")}
                removed = sorted(current_symbols - set(self.symbols))
                for symbol in removed:
                    self._signals[symbol] = Signal.SELL
                    logger.info(f"    🧹 {symbol}: 不在最新股票池，标记 SELL")
            
            if success_count == 0:
                return StepResult(
                    step_name="Step 2: 运行策略生成信号",
                    status=StepStatus.FAILED,
                    message=f"所有股票分析失败: {failed_symbols}",
                )
            
            status = StepStatus.SUCCESS if not failed_symbols else StepStatus.CONTINUE
            msg = f"生成 {success_count} 个信号{f', 失败 {len(failed_symbols)} 只: {failed_symbols}' if failed_symbols else ''}"
            return StepResult(
                step_name="Step 2: 运行策略生成信号",
                status=status,
                message=msg,
            )
            
        except Exception as e:
            logger.error(f"  ❌ 策略执行失败: {e}")
            return StepResult(
                step_name="Step 2: 运行策略生成信号",
                status=StepStatus.FAILED,
                message=str(e),
                error=e,
            )
    
    def _step_risk_check(self) -> StepResult:
        """Step 3: 风控检查"""
        logger.info("🛡️ Step 3: 风控检查")
        
        try:
            # 检查账户资金
            account = self.broker.get_account()
            cash = account.get("cash", 0)
            
            logger.info(f"  账户现金: HKD {cash:,.2f}")
            
            # 检查持仓集中度
            positions = self.broker.get_positions()
            total_value = sum(p.get("market_value", 0) for p in positions)
            
            logger.info(f"  持仓市值: HKD {total_value:,.2f}")
            
            # 检查是否有足够的资金
            if self._signals:
                # 简单检查：有买入信号时现金是否足够
                buy_signals = [s for s in self._signals.values() if s == Signal.BUY]
                if buy_signals and cash < 10000:
                    logger.warning("  ⚠️ 现金不足")
                    return StepResult(
                        step_name="Step 3: 风控检查",
                        status=StepStatus.FAILED,
                        message="现金不足",
                    )
            
            logger.info("  ✅ 风控检查通过")
            return StepResult(
                step_name="Step 3: 风控检查",
                status=StepStatus.SUCCESS,
                message="风控检查通过",
            )
            
        except Exception as e:
            logger.error(f"  ❌ 风控检查失败: {e}")
            return StepResult(
                step_name="Step 3: 风控检查",
                status=StepStatus.FAILED,
                message=str(e),
                error=e,
            )
    
    def _step_execute_orders(self) -> StepResult:
        """Step 4: 执行下单"""
        logger.info("📝 Step 4: 执行下单")
        
        try:
            executed = 0
            
            for symbol, signal in self._signals.items():
                if signal == Signal.HOLD:
                    logger.info(f"  ⏭️ {symbol}: HOLD，跳过")
                    continue
                
                # 获取当前价格（使用最新价）
                try:
                    end_date = datetime.now().strftime("%Y-%m-%d")
                    df = self.source_manager.fetch_ohlcv(
                        ticker=symbol,
                        start=end_date,
                        end=end_date,
                    )
                    if df is None or df.empty:
                        continue
                    price = float(df.iloc[-1]["close"])
                except Exception as e:
                    logger.warning(f"  ⚠️ 获取价格失败: {e}")
                    continue
                
                # 计算数量（简单按固定金额）
                qty = 100
                side = "BUY" if signal == Signal.BUY else "SELL"
                
                logger.info(f"  📌 {symbol}: {side} {qty} @ {price}")
                
                try:
                    order_id = self.broker.place_order(
                        symbol=symbol,
                        side=side,
                        qty=qty,
                        price=price,
                    )
                    
                    # 记录订单
                    self.order_repo.create(
                        ticker=symbol,
                        side=side,
                        qty=qty,
                        price=price,
                        order_id=order_id,
                        status="SUBMITTED",
                    )
                    
                    executed += 1
                    logger.info(f"    ✅ 订单已提交: {order_id}")
                    
                except PermissionError as e:
                    logger.info(f"    ⏭️ 模式限制跳过: {e}")
                except Exception as e:
                    logger.error(f"    ❌ 下单失败: {e}")
            
            return StepResult(
                step_name="Step 4: 执行下单",
                status=StepStatus.SUCCESS,
                message=f"执行 {executed} 个订单",
            )
            
        except Exception as e:
            logger.error(f"  ❌ 执行失败: {e}")
            return StepResult(
                step_name="Step 4: 执行下单",
                status=StepStatus.FAILED,
                message=str(e),
                error=e,
            )
    
    def _step_logging(self) -> StepResult:
        """Step 5: 记录交易日志"""
        logger.info("💾 Step 5: 记录交易日志")
        
        try:
            # 记录每日净值
            account = self.broker.get_account()
            positions = self.broker.get_positions()
            
            positions_value = sum(p.get("market_value", 0) for p in positions)
            total_assets = account.get("cash", 0) + positions_value
            
            today = datetime.now().strftime("%Y-%m-%d")
            
            nav = DailyNav(
                trade_date=today,
                total_equity=total_assets,
                cash=account.get("cash", 0),
                position_value=positions_value,
                created_at=datetime.now().isoformat(),
            )
            self.nav_repo.create(nav)
            
            logger.info(f"  ✅ 记录净值: HKD {total_assets:,.2f}")
            
            return StepResult(
                step_name="Step 5: 记录交易日志",
                status=StepStatus.SUCCESS,
                message=f"记录净值 HKD {total_assets:,.2f}",
            )
            
        except Exception as e:
            logger.error(f"  ❌ 记录失败: {e}")
            return StepResult(
                step_name="Step 5: 记录交易日志",
                status=StepStatus.FAILED,
                message=str(e),
                error=e,
            )
    
    def _step_notify(self) -> StepResult:
        """Step 6: 发送通知"""
        logger.info("📧 Step 6: 发送通知")
        
        # 加载通知配置
        policy = load_policy()
        config = getattr(policy, 'notifications', None)
        
        if not config:
            logger.info("  ⏭️ 未配置通知器，跳过")
            return StepResult(
                step_name="Step 6: 发送通知",
                status=StepStatus.SKIPPED,
                message="未配置通知器",
            )
        
        # 格式化消息（直接在 Step 6 里构造）
        account = self.broker.get_account()
        cash = account.get('cash', 0)
        risk_status = "正常"
        
        signal_texts = []
        for symbol, signal in self._signals.items():
            signal_texts.append(f"{symbol} → {signal.name} ({str(signal.value)})")
        
        message = (
            f"📊 量化交易日报 | {datetime.now().strftime('%Y-%m-%d')}\n"
            f"\n"
            f"📈 信号：{', '.join(signal_texts) if signal_texts else '无'}\n"
            f"💰 账户净值：HKD {cash:,.2f}\n"
            f"🛡️ 风控状态：{risk_status}\n"
            f"⏱️ 运行耗时：{self._runtime_seconds:.1f}s\n"
            f"🔧 模式：{self.broker.mode}"
        )
        
        # 检查是否有告警
        has_alert = any(s.status == StepStatus.FAILED for s in self._report_steps)
        if has_alert:
            message = f"⚠️ 告警\n\n{message}"
        
        sent = False
        errors = []
        
        # Telegram 通知
        telegram_config = getattr(config, 'telegram', None)
        if telegram_config and getattr(telegram_config, 'enabled', False):
            chat_id = getattr(telegram_config, 'chat_id', None)
            if chat_id:
                try:
                    result = subprocess.run(
                        ["openclaw", "message", "send", "--channel", "telegram", "--target", chat_id, "--message", message],
                        capture_output=True,
                        text=True,
                    )
                    if result.returncode != 0:
                        logger.warning(f"  ⚠️ Telegram 通知失败: {result.stderr}")
                        errors.append(f"Telegram: {result.stderr}")
                    else:
                        logger.info("  ✅ Telegram 通知发送成功")
                        sent = True
                except Exception as e:
                    logger.warning(f"  ⚠️ Telegram 通知异常: {e}")
                    errors.append(f"Telegram: {e}")
            else:
                logger.warning("  ⚠️ Telegram chat_id 未配置")
        
        # Gmail 通知 (备用)
        email_config = getattr(config, 'email', None)
        if email_config and getattr(email_config, 'enabled', False):
            # Gmail 发送逻辑（如果配置了的话）
            logger.info("  📧 Gmail 通知（暂未实现）")
        
        if sent:
            return StepResult(
                step_name="Step 6: 发送通知",
                status=StepStatus.SUCCESS,
                message="通知已发送",
            )
        elif errors:
            return StepResult(
                step_name="Step 6: 发送通知",
                status=StepStatus.FAILED,
                message="; ".join(errors),
            )
        else:
            return StepResult(
                step_name="Step 6: 发送通知",
                status=StepStatus.SKIPPED,
                message="通知未启用",
            )
    
    def _format_notification(self) -> str:
        """格式化通知内容"""
        # 获取账户信息
        account = self.broker.get_account()
        cash = account.get('cash', 0)
        
        # 获取风控状态
        risk_passed = all(s.status != StepStatus.FAILED for s in self.steps if "风控" in s.step_name)
        risk_status = "正常" if risk_passed else "异常"
        
        # 获取信号
        signal_texts = []
        for symbol, signal in self._signals.items():
            signal_texts.append(f"{symbol} → {signal.name} ({str(signal.value)})")
        
        # 格式化
        lines = [
            f"📊 量化交易日报 | {datetime.now().strftime('%Y-%m-%d')}",
            "",
            f"📈 信号：{', '.join(signal_texts) if signal_texts else '无'}",
            f"💰 账户净值：HKD {cash:,.2f}",
            f"🛡️ 风控状态：{risk_status}",
            f"⏱️ 运行耗时：{self._runtime_seconds:.1f}s",
            f"🔧 模式：{self.broker.mode}",
        ]
        
        return "\n".join(lines)
    
    def _send_notification(self, report: DailyReport):
        """发送告警（失败时）"""
        if not self.notifier:
            return
        
        try:
            content = f"""
❌ 每日交易流程失败

日期: {report.date}
失败步骤: {report.steps[0].step_name if report.steps else 'N/A'}
错误信息: {report.steps[0].message if report.steps else 'N/A'}
"""
            self.notifier.send(title="交易异常告警", content=content)
        except Exception as e:
            logger.error(f"告警发送失败: {e}")


def create_orchestrator(
    broker_config: Dict,
    symbols: List[str],
    provider_name: str = "stooq",
) -> Orchestrator:
    """
    创建编排器
    
    Args:
        broker_config: 券商配置
        symbols: 股票列表
        provider_name: 数据源名称
        
    Returns:
        Orchestrator 实例
    """
    # 加载配置
    policy = load_policy()
    if (
        (not provider_name)
        and hasattr(policy, "data_source")
        and getattr(policy.data_source, "provider", None)
    ):
        provider_name = policy.data_source.provider
    if hasattr(policy, "data_source"):
        settings = get_settings()
        reset_source_manager(
            enable_cache=bool(getattr(policy.data_source, "cache_enabled", True)),
            cache_path=str(getattr(policy.data_source, "cache_path", settings.storage.market_cache_path)),
        )
    
    # 创建券商
    broker = create_broker(broker_config)
    
    # 连接券商
    if not broker.connect():
        logger.warning("⚠️ 券商连接失败，将以只读模式运行")
    
    # 策略配置
    strategy_mode = getattr(getattr(policy, "strategy", None), "mode", "manual")
    manual_strategy = getattr(getattr(policy, "strategy", None), "manual_primary", "ma_cross")
    strategy_params = getattr(getattr(policy, "strategy", None), "default_params", {}) or {}

    strategy_factory = get_strategy_factory()
    try:
        fallback_strategy = strategy_factory.create(
            name=manual_strategy,
            mode="stream",
            params=strategy_params.get(manual_strategy, {}),
        )
    except Exception:
        fallback_strategy = MACrossStrategy(short_window=5, long_window=20)

    settings = get_settings()

    # 创建数据库
    db = Database(settings.storage.runtime_db_path)
    init_db(settings.storage.runtime_db_path)
    
    # 创建通知器（可选）
    notifier = None
    try:
        notifier = NotifierFactory.create({"channels": []})
    except Exception as e:
        logger.warning(f"通知器创建失败: {e}")

    # 动态选股配置
    universe_mode = getattr(getattr(policy, "universe", None), "mode", "static")
    top_n = int(getattr(getattr(policy, "universe", None), "top_n", 20))
    universe_selector = None
    if universe_mode == "dynamic_cn":
        universe_selector = AStockUniverseSelector(
            config=UniverseConfig(
                top_n=top_n,
                min_list_days=int(getattr(policy.universe, "min_list_days", 120)),
                exclude_st=bool(getattr(policy.universe, "exclude_st", True)),
                include_gem=bool(getattr(policy.universe, "include_gem", True)),
            )
        )
    
    return Orchestrator(
        broker=broker,
        strategy=fallback_strategy,
        db=db,
        symbols=symbols,
        provider_name=provider_name,
        notifier=notifier,
        strategy_factory=strategy_factory,
        strategy_mode=strategy_mode,
        manual_strategy=manual_strategy,
        strategy_params=strategy_params,
        universe_selector=universe_selector,
        universe_mode=universe_mode,
        universe_top_n=top_n,
    )
