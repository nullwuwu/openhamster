"""
对账逻辑

比对券商持仓与本地持仓
"""
import logging
from typing import List, Dict
from datetime import datetime

from ..storage import Database, PositionRepository

logger = logging.getLogger("quant_trader.broker")


class Reconciler:
    """对账器"""
    
    def __init__(self, db: Database):
        self.db = db
    
    def run(
        self,
        broker_positions: List[Dict],
        local_positions: List[Dict],
    ) -> Dict:
        """
        执行对账
        
        Args:
            broker_positions: 券商持仓
            local_positions: 本地持仓
            
        Returns:
            dict: 对账结果
        """
        # 构建 symbol -> qty 映射
        broker_map = {p["symbol"]: p["qty"] for p in broker_positions}
        local_map = {p["symbol"]: p["qty"] for p in local_positions}
        
        # 所有标的
        all_symbols = set(broker_map.keys()) | set(local_map.keys())
        
        differences = []
        
        for symbol in all_symbols:
            broker_qty = broker_map.get(symbol, 0)
            local_qty = local_map.get(symbol, 0)
            
            if broker_qty != local_qty:
                diff = broker_qty - local_qty
                differences.append({
                    "symbol": symbol,
                    "broker_qty": broker_qty,
                    "local_qty": local_qty,
                    "diff": diff,
                })
        
        # 记录对账结果
        if differences:
            for d in differences:
                logger.warning(f"⚠️ 对账差异: {d['symbol']} 券商={d['broker_qty']} 本地={d['local_qty']} 差={d['diff']}")
                
                # 写入日志表
                self._log_difference(d)
        
        # 对账结果
        result = {
            "timestamp": datetime.now().isoformat(),
            "total_checked": len(all_symbols),
            "differences": len(differences),
            "status": "MATCH" if len(differences) == 0 else "MISMATCH",
            "details": differences,
        }
        
        if differences:
            logger.warning(f"⚠️ 对账完成: 发现 {len(differences)} 处差异")
        else:
            logger.info(f"✅ 对账完成: 全部匹配")
        
        return result
    
    def _log_difference(self, diff: Dict):
        """记录差异到数据库"""
        # 可以扩展存储到 reconciliation_log 表
        pass
