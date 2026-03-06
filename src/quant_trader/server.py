from __future__ import annotations
import json
import logging

from mcp.server.fastmcp import FastMCP

from .models import BacktestResult
from .risk.reviewer import risk_gate_review
from .decision_graph import DecisionGraph, create_graph

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)

mcp = FastMCP("quant-trader")

# Decision graph instance (can be replaced with LLM-enabled version)
_graph: DecisionGraph | None = None


def get_graph() -> DecisionGraph:
    """Get or create DecisionGraph instance"""
    global _graph
    if _graph is None:
        _graph = create_graph()
    return _graph


@mcp.tool()
def strategy_review(
    cagr: float,
    max_drawdown: float,
    sharpe: float,
    annual_turnover: float = 0,
    data_years: float = 5,
    assumptions: list[str] | None = None,
    param_sensitivity: float | None = None,
    is_first_live: bool = False,
) -> dict:
    """执行量化策略评审（Risk Gate），返回 GO / NO_GO / REVISE"""
    result = BacktestResult(
        cagr=cagr,
        max_drawdown=max_drawdown,
        sharpe=sharpe,
        annual_turnover=annual_turnover,
        data_years=data_years,
        assumptions=assumptions or [],
        param_sensitivity=param_sensitivity,
        is_first_live=is_first_live,
    )
    return risk_gate_review(result).model_dump()


@mcp.tool()
def get_policy() -> dict:
    """获取当前风控策略配置"""
    from .policy import policy
    import dataclasses
    return dataclasses.asdict(policy)


@mcp.tool()
def strategy_review_full(
    user_input: str,
    backtest_params: str = "{}",
) -> dict:
    """
    执行完整策略评审流程（DecisionGraph）。
    
    输入:
        user_input: 用户策略描述/想法
        backtest_params: JSON 字符串，回测参数（可选）
    
    输出:
        PMDecision + 人话总结 + 完整执行上下文
    """
    logger = logging.getLogger("quant_trader.server.strategy_review_full")
    logger.info(f"📊 [strategy_review_full] Processing: {user_input[:50]}...")

    try:
        params = json.loads(backtest_params) if isinstance(backtest_params, str) else backtest_params
    except json.JSONDecodeError:
        params = {}

    graph = get_graph()
    result = graph.run_full_flow(user_input, params)

    # Add human-readable summary
    pm = result.get("pm_decision", {})
    summary = _generate_summary(result)

    return {
        "success": True,
        "summary": summary,
        **result,
    }


@mcp.tool()
def strategy_iterate(
    user_input: str,
    backtest_params: str = "{}",
) -> dict:
    """
    自动迭代评审流程。
    
    最多迭代 max_iterations=3 次，每次根据 PM 反馈调整参数。
    达到上限或 NO_GO 时停止并通知人工。
    
    输入:
        user_input: 用户策略描述/想法
        backtest_params: JSON 字符串，初始回测参数（可选）
    
    输出:
        PMDecision + 迭代历史 + 最终结论
    """
    logger = logging.getLogger("quant_trader.server.strategy_iterate")
    logger.info(f"🔄 [strategy_iterate] Starting iteration for: {user_input[:50]}...")

    try:
        params = json.loads(backtest_params) if isinstance(backtest_params, str) else backtest_params
    except json.JSONDecodeError:
        params = {}

    graph = get_graph()
    result = graph.run_iteration(user_input, params)

    # Add summary
    summary = _generate_summary(result)
    summary += f"\n\n迭代次数: {result.get('iteration', 1)}"
    if result.get("stop_reason"):
        summary += f"\n停止原因: {result['stop_reason']}"

    return {
        "success": True,
        "summary": summary,
        **result,
    }


def _generate_summary(result: dict) -> str:
    """生成人话总结"""
    pm = result.get("pm_decision", {})
    risk = result.get("risk_review", {})
    backtest = result.get("backtest", {})

    verdict = pm.get("verdict", "UNKNOWN")
    verdict_emoji = {"GO": "✅", "NO_GO": "🚫", "REVISE": "🔄"}.get(verdict, "❓")

    lines = [
        f"{verdict_emoji} 评审结果: **{verdict}**",
        "",
        f"📈 回测: CAGR={backtest.get('cagr', 0):.1%}, "
        f"MaxDD={backtest.get('max_drawdown', 0):.1%}, "
        f"Sharpe={backtest.get('sharpe', 0):.1f}",
    ]

    if pm.get("reasoning"):
        lines.append(f"\n💡 {pm['reasoning']}")

    if risk.get("yellow_flags_triggered"):
        lines.append(f"\n⚠️ 黄线: {', '.join(risk['yellow_flags_triggered'])}")

    if risk.get("hard_gates_failed"):
        lines.append(f"\n🔴 硬红线: {', '.join(risk['hard_gates_failed'])}")

    if pm.get("risk_warnings"):
        lines.append(f"\n🚨 风险警告: {', '.join(pm['risk_warnings'])}")

    if pm.get("next_experiments"):
        lines.append(f"\n🔬 下一步实验: {len(pm['next_experiments'])} 个")

    if pm.get("requires_human_approve"):
        lines.append("\n👤 **需要人工确认**")

    return "\n".join(lines)


if __name__ == "__main__":
    mcp.run()
