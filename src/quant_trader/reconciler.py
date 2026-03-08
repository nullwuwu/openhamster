"""
持仓对账 (Reconciler)

比对系统持仓与券商持仓，确保一致
"""
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import datetime
import pandas as pd

logger = logging.getLogger("quant_trader.reconciler")


@dataclass
class PositionDiff:
    """持仓差异"""
    symbol: str
    # 系统记录
    sys_qty: float = 0
    sys_avg_cost: float = 0
    # 券商记录
    broker_qty: float = 0
    broker_avg_cost: float = 0
    # 差异
    qty_diff: float = 0
    cost_diff: float = 0
    # 严重程度
    severity: str = "none"  # none/minor/major/critical


@dataclass
class ReconciliationReport:
    """对账报告"""
    date: str
    timestamp: str
    is_balanced: bool
    positions: List[PositionDiff] = field(default_factory=list)
    total_qty_diff: float = 0
    total_value_diff: float = 0
    actions: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


class Reconciler:
    """持仓对账器"""
    
    def __init__(
        self,
        broker,
        db=None,
    ):
        """
        Args:
            broker: 券商接口
            db: 数据库 (可选)
        """
        self.broker = broker
        self.db = db
    
    def reconcile(
        self,
        sys_positions: Dict[str, dict] = None,
    ) -> ReconciliationReport:
        """
        执行对账
        
        Args:
            sys_positions: 系统持仓 {symbol: {"qty": x, "avg_cost": y}}
            
        Returns:
            ReconciliationReport
        """
        logger.info("🔍 开始持仓对账...")
        
        report = ReconciliationReport(
            date=datetime.now().strftime("%Y-%m-%d"),
            timestamp=datetime.now().isoformat(),
            is_balanced=True,
        )
        
        # 1. 获取券商持仓
        broker_positions = {}
        try:
            broker_account = self.broker.get_account()
            holdings = broker_account.get("holdings", [])
            
            for h in holdings:
                symbol = h.get("symbol")
                qty = h.get("qty", 0)
                avg_cost = h.get("avg_cost", 0)
                
                if symbol:
                    broker_positions[symbol] = {"qty": qty, "avg_cost": avg_cost}
                    
        except Exception as e:
            logger.error(f"⚠️ 获取券商持仓失败: {e}")
            report.errors.append(f"获取券商持仓失败: {e}")
            # 尝试从 DB 获取
            if self.db:
                try:
                    sys_positions = self._get_positions_from_db()
                except Exception as e2:
                    report.errors.append(f"获取系统持仓也失败: {e2}")
                    return report
        
        # 2. 获取系统持仓
        if sys_positions is None:
            sys_positions = self._get_positions_from_db()
        
        # 3. 比对
        all_symbols = set(sys_positions.keys()) | set(broker_positions.keys())
        
        for symbol in all_symbols:
            sys = sys_positions.get(symbol, {"qty": 0, "avg_cost": 0})
            broker = broker_positions.get(symbol, {"qty": 0, "avg_cost": 0})
            
            qty_diff = broker["qty"] - sys["qty"]
            cost_diff = (broker["avg_cost"] - sys["avg_cost"]) * broker["qty"]
            
            # 判断严重程度
            if abs(qty_diff) < 0.01:
                severity = "none"
            elif abs(qty_diff) < 10:
                severity = "minor"
            elif abs(qty_diff) < 100:
                severity = "major"
            else:
                severity = "critical"
            
            diff = PositionDiff(
                symbol=symbol,
                sys_qty=sys["qty"],
                sys_avg_cost=sys["avg_cost"],
                broker_qty=broker["qty"],
                broker_avg_cost=broker["avg_cost"],
                qty_diff=qty_diff,
                cost_diff=cost_diff,
                severity=severity,
            )
            
            report.positions.append(diff)
            
            if severity != "none":
                report.is_balanced = False
                report.total_qty_diff += abs(qty_diff)
                report.total_value_diff += abs(cost_diff)
        
        # 4. 生成处理建议
        report.actions = self._generate_actions(report)
        
        # 5. 记录
        if not report.is_balanced:
            logger.warning(f"⚠️ 对账发现问题: {len([p for p in report.positions if p.severity != 'none'])} 个差异")
            
            for diff in report.positions:
                if diff.severity == "critical":
                    logger.error(f"🔴 严重差异: {diff.symbol} 差 {diff.qty_diff} 股")
                elif diff.severity == "major":
                    logger.warning(f"🟠 较大差异: {diff.symbol} 差 {diff.qty_diff} 股")
        
        self._save_report(report)
        
        logger.info(f"✅ 对账完成: {'平衡' if report.is_balanced else '不平衡'}")
        
        return report
    
    def _get_positions_from_db(self) -> Dict[str, dict]:
        """从数据库获取持仓"""
        if not self.db:
            return {}
        
        # 简化实现
        try:
            from .storage import PositionRepository
            repo = PositionRepository(self.db)
            positions = repo.get_all()
            
            return {
                p.symbol: {"qty": p.qty, "avg_cost": p.avg_cost}
                for p in positions
            }
        except Exception as e:
            logger.warning(f"⚠️ DB 获取持仓失败: {e}")
            return {}
    
    def _generate_actions(self, report: ReconciliationReport) -> List[str]:
        """生成处理建议"""
        actions = []
        
        critical_positions = [p for p in report.positions if p.severity == "critical"]
        major_positions = [p for p in report.positions if p.severity == "major"]
        
        if critical_positions:
            actions.append("🚨 严重差异需要人工介入处理")
            for p in critical_positions:
                actions.append(f"   - {p.symbol}: 系统 {p.sys_qty} vs 券商 {p.broker_qty}")
        
        if major_positions:
            actions.append("🟠 较大差异建议手动核对")
            for p in major_positions:
                actions.append(f"   - {p.symbol}: 差 {p.qty_diff:.0f} 股 (约 {p.cost_diff:.2f})")
        
        minor_positions = [p for p in report.positions if p.severity == "minor"]
        if minor_positions:
            actions.append(f"🟡 {len(minor_positions)} 个小幅差异，可忽略或下周期对账")
        
        if report.is_balanced:
            actions.append("✅ 持仓完全一致")
        
        return actions
    
    def _save_report(self, report: ReconciliationReport) -> None:
        """保存报告到数据库"""
        if not self.db:
            return
        
        # 可扩展：保存到数据库
        logger.debug(f"📝 对账报告已生成: {report.is_balanced}")


class AutoReconciler:
    """自动对账调度器"""
    
    def __init__(
        self,
        reconciler: Reconciler,
        check_on_trade: bool = True,  # 交易后检查
        check_daily: bool = True,     # 每日检查
    ):
        """
        Args:
            reconciler: 对账器
            check_on_trade: 交易后自动对账
            check_daily: 每日定时对账
        """
        self.reconciler = reconciler
        self.check_on_trade = check_on_trade
        self.check_daily = check_daily
    
    def check_after_trade(self, trade_result: dict) -> Optional[ReconciliationReport]:
        """交易后自动对账"""
        if not self.check_on_trade:
            return None
        
        logger.info("🔍 交易后自动对账...")
        
        # 等待一小段时间让券商状态更新
        import time
        time.sleep(2)
        
        report = self.reconciler.reconcile()
        
        if not report.is_balanced:
            # 记录差异但不阻塞交易
            logger.warning(f"⚠️ 交易后对账发现问题: {report.total_qty_diff:.0f} 股差异")
        
        return report
    
    def daily_check(self) -> ReconciliationReport:
        """每日对账"""
        if not self.check_daily:
            return None
        
        logger.info("🔍 每日定时对账...")
        
        report = self.reconciler.reconcile()
        
        return report
