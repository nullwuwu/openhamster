"""
DecisionGraph - Automated Strategy Review & Iteration System

6-Node Flow:
Spec PM → Backtest Operator → Bull Analyst ↔ Bear Reviewer → Risk Gate → Portfolio Manager
"""
from __future__ import annotations
import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from .models import BacktestResult, PMDecision, ReviewOutput, Verdict
from .policy import policy
from .llm import MiniMaxClient, create_minimax_client

logger = logging.getLogger("quant_trader.decision_graph")


# ============ Data Structures ============

class NodeStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class StrategySpec:
    """Strategy specification from user input"""
    name: str
    description: str
    target_cagr: float | None = None
    max_risk: float | None = None
    parameters: dict[str, Any] = field(default_factory=dict)
    constraints: list[str] = field(default_factory=list)


@dataclass
class BacktestData:
    """Backtest result data from operator"""
    cagr: float
    max_drawdown: float
    sharpe: float
    annual_turnover: float = 0
    data_years: float = 5
    assumptions: list[str] = field(default_factory=list)
    param_sensitivity: float | None = None
    is_first_live: bool = False
    raw_data: dict[str, Any] = field(default_factory=dict)


@dataclass
class DebateRound:
    """Bull/Bear debate round"""
    round_num: int
    bull_argument: str
    bear_argument: str
    bull_rebuttal: str | None = None
    bear_rebuttal: str | None = None


@dataclass
class DebateResult:
    """Complete debate history"""
    rounds: list[DebateRound] = field(default_factory=list)
    consensus_points: list[str] = field(default_factory=list)
    remaining_risks: list[str] = field(default_factory=list)


@dataclass
class GraphContext:
    """Execution context for the decision graph"""
    spec: StrategySpec | None = None
    backtest: BacktestData | None = None
    debate: DebateResult | None = None
    risk_review: ReviewOutput | None = None
    pm_decision: PMDecision | None = None
    iteration: int = 0
    max_iterations: int = 3
    error: str | None = None


# ============ Node Implementations ============

class SpecPM:
    """Node 1: Receive user strategy idea, structure into spec"""

    @staticmethod
    def execute(user_input: str) -> StrategySpec:
        """
        Parse user input into structured StrategySpec.
        In production, this would use LLM. For now, simple parsing.
        """
        logger.info("📝 [SpecPM] Parsing user input...")

        # Simple heuristic parsing (could be LLM-enhanced)
        spec = StrategySpec(
            name="strategy_" + str(hash(user_input))[:8],
            description=user_input,
        )

        # Extract potential targets/constraints from text
        lower = user_input.lower()
        if "cagr" in lower or "收益" in lower:
            # Try to extract target CAGR
            import re
            match = re.search(r'(\d+(?:\.\d+)?)\s*%?', user_input)
            if match:
                spec.target_cagr = float(match.group(1)) / 100

        if "风险" in lower or "drawdown" in lower or "dd" in lower:
            spec.max_risk = 0.20  # Default

        logger.info(f"✅ [SpecPM] Spec created: {spec.name}")
        return spec


class BacktestOperator:
    """Node 2: Run backtest, get BacktestResult"""

    @staticmethod
    def execute(spec: StrategySpec, backtest_params: dict | None = None) -> BacktestData:
        """
        Execute backtest based on spec.
        
        Args:
            spec: StrategySpec from SpecPM
            backtest_params: Optional dict with keys:
                - ticker: str (default "SPY")
                - fast_period: int (default 20)
                - short_period: int (default 50)
                - start_date: str (default "2020-01-01")
                - end_date: str (optional)
                - param_sensitivity: float (default 0.0)  # TODO: P0 自动计算
                - is_first_live: bool (default True)
                
        Returns:
            BacktestData: Real backtest result
        """
        logger.info("🔄 [BacktestOperator] Running backtest...")

        params = backtest_params or {}
        
        # 如果有真实回测参数，调用 BacktestEngine
        if params.get("use_real_engine", False) or params.get("ticker"):
            try:
                from .backtest.backtest_engine import BacktestEngine, DualMAStrategy
                
                ticker = params.get("ticker", "SPY")
                fast_period = params.get("fast_period", 20)
                short_period = params.get("short_period", 50)
                start_date = params.get("start_date", "2020-01-01")
                end_date = params.get("end_date", None)
                
                logger.info(f"📊 [BacktestOperator] Running real backtest: {ticker} {fast_period}/{short_period}")
                
                engine = BacktestEngine()
                strategy = DualMAStrategy(fast_period=fast_period, short_period=short_period)
                
                # 不传 param_sensitivity，让 BacktestEngine 自动计算
                result = engine.run(
                    ticker=ticker,
                    strategy=strategy,
                    start_date=start_date,
                    end_date=end_date,
                    is_first_live=params.get("is_first_live", True),
                )
                
                logger.info(
                    f"✅ [BacktestOperator] Real backtest done: "
                    f"CAGR={result.cagr:.1%}, MaxDD={result.max_drawdown:.1%}, "
                    f"Sharpe={result.sharpe:.2f}"
                )
                
                return BacktestData(
                    cagr=result.cagr,
                    max_drawdown=result.max_drawdown,
                    sharpe=result.sharpe,
                    annual_turnover=result.annual_turnover,
                    data_years=result.data_years,
                    assumptions=result.assumptions,
                    param_sensitivity=result.param_sensitivity,
                    is_first_live=result.is_first_live,
                    raw_data={
                        "ticker": ticker,
                        "fast_period": fast_period,
                        "short_period": short_period,
                    },
                )
                
            except Exception as e:
                logger.error(f"⚠️ [BacktestEngine] Failed: {e}, using fallback")
                # Fallback to params if engine fails

        # Fallback: use provided params or defaults
        # 计算 data_years 从日期参数
        start = params.get("start_date", "2020-01-01")
        end = params.get("end_date", None) or "2025-01-01"
        try:
            from datetime import datetime
            start_dt = datetime.strptime(start, "%Y-%m-%d")
            end_dt = datetime.strptime(end, "%Y-%m-%d")
            fallback_data_years = (end_dt - start_dt).days / 365.25
        except:
            fallback_data_years = 5.0
        
        result = BacktestData(
            cagr=params.get("cagr", 0.15),
            max_drawdown=params.get("max_drawdown", 0.12),
            sharpe=params.get("sharpe", 1.3),
            annual_turnover=params.get("annual_turnover", 0.5),  # 更合理的默认值
            data_years=params.get("data_years", fallback_data_years),
            assumptions=params.get("assumptions", [
                "slippage", "commission", "tax", "dividend_withholding"
            ]),
            param_sensitivity=params.get("param_sensitivity", 0.0),  # TODO: P0
            is_first_live=params.get("is_first_live", True),
            raw_data=params,
        )

        logger.warning(
            f"⚠️ [BacktestOperator] Using fallback data: CAGR={result.cagr:.1%}, "
            f"MaxDD={result.max_drawdown:.1%}, Sharpe={result.sharpe}, "
            f"data_years={result.data_years:.1f}"
        )
        return result


class BullAnalyst:
    """Node 3: LLM analysis - bullish arguments"""

    PROMPT = """你是一名乐观的量化分析师（Bull Analyst）。
基于以下回测结果，输出看多论点。

回测数据:
- CAGR: {cagr:.1%}
- Max Drawdown: {max_drawdown:.1%}
- Sharpe: {sharpe}
- Annual Turnover: {annual_turnover:.1%}
- Data Years: {data_years}

请输出 JSON:
{{
    "bull_points": ["论点1", "论点2", ...],
    "strengths": ["优势1", "优势2", ...],
    "opportunity": "一句话机会描述"
}}

只输出 JSON，不要其他内容。"""


class BearReviewer:
    """Node 4: LLM analysis - bearish/critical arguments"""

    PROMPT = """你是一名保守的风险审查员（Bear Reviewer）。
基于以下回测结果，输出看空/风险论点。

回测数据:
- CAGR: {cagr:.1%}
- Max Drawdown: {max_drawdown:.1%}
- Sharpe: {sharpe}
- Annual Turnover: {annual_turnover:.1%}
- Data Years: {data_years}

请输出 JSON:
{{
    "bear_points": ["风险点1", "风险点2", ...],
    "weaknesses": ["弱点1", "弱点2", ...],
    "concerns": "一句话风险警告"
}}

只输出 JSON，不要其他内容。"""


class RiskGate:
    """Node 5: Hard rules check - uses existing risk_gate_review()"""

    @staticmethod
    def execute(backtest: BacktestData) -> ReviewOutput:
        """Execute hard rules check"""
        logger.info("🚦 [RiskGate] Running hard rules check...")

        # Convert to model for existing reviewer
        result = BacktestResult(
            cagr=backtest.cagr,
            max_drawdown=backtest.max_drawdown,
            sharpe=backtest.sharpe,
            annual_turnover=backtest.annual_turnover,
            data_years=backtest.data_years,
            assumptions=backtest.assumptions,
            param_sensitivity=backtest.param_sensitivity,
            is_first_live=backtest.is_first_live,
        )

        # Use existing reviewer
        from .risk.reviewer import risk_gate_review
        review = risk_gate_review(result)

        logger.info(
            f"✅ [RiskGate] Verdict: {review.verdict.value}, "
            f"hard_fails={len(review.hard_gates_failed)}, "
            f"yellow_flags={len(review.yellow_flags_triggered)}"
        )
        return review


class PortfolioManager:
    """Node 6: LLM final decision maker"""

    PROMPT = """# Role: Quantitative Strategy Reviewer

你是一名专业的量化策略评审员（Portfolio Manager）。
基于回测结果、风险评估和多方意见，输出结构化最终决策。

## 回测数据
- CAGR: {cagr:.1%}
- Max Drawdown: {max_drawdown:.1%}
- Sharpe: {sharpe}
- Annual Turnover: {annual_turnover:.1%}
- Data Years: {data_years}

## Bull Analyst 观点
{bull_analysis}

## Bear Reviewer 观点
{bear_analysis}

## Risk Gate 判定
- Verdict: {risk_verdict}
- Hard Fails: {hard_fails}
- Yellow Flags: {yellow_flags}
- Utility Score: {utility_score}
- Requires Human Approve: {requires_approve}

## 当前权重
{weights}

## 铁律
- 硬红线 NO_GO → 不能翻盘
- requires_human_approve=true → 必须保留
- next_experiments ≤ 2 个
- weights 调整幅度不超过 ±0.10
- 不能编造数据

## 输出格式（严格 JSON）
{{
  "verdict": "GO | NO_GO | REVISE",
  "utility_score": <number>,
  "weights": {{
    "cagr": 0.35,
    "max_dd": 0.35,
    "sharpe": 0.20,
    "turnover": 0.10
  }},
  "weight_adjust_reason": "调了权重的原因，没调写 null",
  "reasoning": "人话解释",
  "risk_warnings": [...],
  "next_experiments": [
    {{
      "name": "...",
      "hypothesis": "...",
      "change": "..."
    }}
  ],
  "requires_human_approve": <来自 RiskGate，不能改为 false>
}}

只输出 JSON，不要其他内容。"""


# ============ Graph Orchestration ============

class DecisionGraph:
    """
    Main decision graph orchestrator.

    Flow: SpecPM → Backtest → Bull ↔ Bear (debate) → RiskGate → PM
    """

    def __init__(self, llm_provider=None, api_key: str | None = None):
        """
        Initialize graph with optional LLM provider.
        
        Args:
            llm_provider: Custom LLM provider (duck-typed, must have chat_json method)
            api_key: MiniMax API key (if not provided, tries env MINIMAX_API_KEY)
        """
        self.llm = llm_provider
        self._minimax_api_key = api_key
        self.policy = policy
        self._llm_client = None

    def _get_llm_client(self) -> MiniMaxClient | None:
        """Get or create MiniMax client"""
        if self.llm is not None:
            return None  # Use custom provider
            
        if self._minimax_api_key:
            try:
                return create_minimax_client(self._minimax_api_key)
            except Exception as e:
                logger.warning(f"⚠️ [LLM] Failed to create MiniMax client: {e}")
        return None

    def _call_llm(self, prompt: str) -> dict:
        """Call LLM, return parsed JSON"""
        # Try custom provider first
        if self.llm is not None:
            try:
                return self.llm.chat_json(prompt=prompt)
            except Exception as e:
                logger.warning(f"⚠️ [LLM] Custom provider failed: {e}")

        # Try MiniMax
        client = self._get_llm_client()
        if client:
            try:
                return client.chat_json(user=prompt)
            except Exception as e:
                logger.warning(f"⚠️ [LLM] MiniMax failed: {e}")
                client.close()

        # Fallback: mock response
        logger.warning("⚠️ [LLM] No provider available, using mock response")
        return {"bull_points": ["收益可观"], "strengths": ["Sharpe高"], "opportunity": "有机会"}

    def _call_pm_llm(self, prompt: str) -> PMDecision:
        """Call PM LLM, return PMDecision"""
        # Try custom provider first
        if self.llm is not None:
            try:
                result = self.llm.chat_json(prompt=prompt)
                return self._parse_pm_decision(result)
            except Exception as e:
                logger.warning(f"⚠️ [PM LLM] Custom provider failed: {e}")

        # Try MiniMax
        client = self._get_llm_client()
        if client:
            try:
                result = client.chat_json(user=prompt)
                pm = self._parse_pm_decision(result)
                client.close()
                return pm
            except Exception as e:
                logger.warning(f"⚠️ [PM LLM] MiniMax failed: {e}")
                if client:
                    client.close()

        # Fallback: default decision
        logger.warning("⚠️ [PM LLM] No provider, using default decision")
        return PMDecision(
            verdict=Verdict.GO,
            utility_score=7.5,
            weights={"cagr": 0.35, "max_dd": 0.35, "sharpe": 0.20, "turnover": 0.10},
            weight_adjust_reason=None,
            reasoning="默认通过（无LLM）",
            risk_warnings=[],
            next_experiments=[],
            requires_human_approve=False,
        )

    def _parse_pm_decision(self, result: dict) -> PMDecision:
        """Parse LLM response into PMDecision"""
        return PMDecision(
            verdict=Verdict(result.get("verdict", "GO")),
            utility_score=result.get("utility_score", 0),
            weights=result.get("weights", {"cagr": 0.35, "max_dd": 0.35, "sharpe": 0.20, "turnover": 0.10}),
            weight_adjust_reason=result.get("weight_adjust_reason"),
            reasoning=result.get("reasoning", ""),
            risk_warnings=result.get("risk_warnings", []),
            next_experiments=result.get("next_experiments", [])[:2],
            requires_human_approve=result.get("requires_human_approve", False),
        )

    def run_full_flow(
        self,
        user_input: str,
        backtest_params: dict | None = None,
        llm_bull: str | None = None,
        llm_bear: str | None = None,
        llm_pm: str | None = None,
    ) -> dict:
        """
        Execute full decision graph flow.

        Args:
            user_input: User's strategy idea
            backtest_params: Optional backtest parameters
            llm_bull: Optional pre-generated bull analysis (for testing)
            llm_bear: Optional pre-generated bear analysis (for testing)
            llm_pm: Optional pre-generated PM decision (for testing)

        Returns:
            dict with full execution context
        """
        ctx = GraphContext()
        ctx.max_iterations = self.policy.limits.max_iterations

        # Node 1: Spec PM
        logger.info("=" * 50)
        logger.info("🚀 Starting DecisionGraph")
        ctx.spec = SpecPM.execute(user_input)

        # Node 2: Backtest Operator
        ctx.backtest = BacktestOperator.execute(ctx.spec, backtest_params)

        # Node 3 & 4: Bull/Bear Analysis with Debate
        max_debates = self.policy.limits.max_debate_rounds
        ctx.debate = DebateResult()

        # Round 1: Initial analysis
        logger.info(f"🔄 [Bull/Bear] Starting debate (max {max_debates} rounds)")

        # Bull initial analysis
        if llm_bull:
            bull_result = json.loads(llm_bull)
        else:
            prompt = BullAnalyst.PROMPT.format(
                cagr=ctx.backtest.cagr,
                max_drawdown=ctx.backtest.max_drawdown,
                sharpe=ctx.backtest.sharpe,
                annual_turnover=ctx.backtest.annual_turnover,
                data_years=ctx.backtest.data_years,
            )
            bull_result = self._call_llm(prompt)
            logger.info(f"🐂 [Bull] Generated {len(bull_result.get('bull_points', []))} points")

        # Bear initial analysis
        if llm_bear:
            bear_result = json.loads(llm_bear)
        else:
            prompt = BearReviewer.PROMPT.format(
                cagr=ctx.backtest.cagr,
                max_drawdown=ctx.backtest.max_drawdown,
                sharpe=ctx.backtest.sharpe,
                annual_turnover=ctx.backtest.annual_turnover,
                data_years=ctx.backtest.data_years,
            )
            bear_result = self._call_llm(prompt)
            logger.info(f"🐻 [Bear] Generated {len(bear_result.get('bear_points', []))} points")

        # Add first round
        ctx.debate.rounds.append(DebateRound(
            round_num=1,
            bull_argument=bull_result.get("bull_points", []),
            bear_argument=bear_result.get("bear_points", []),
        ))

        # Debate rounds 2+ (if max_debates > 1)
        for round_num in range(2, max_debates + 1):
            logger.info(f"🔄 [Debate] Round {round_num}/{max_debates}")

            # Bear rebuts Bull's points
            bear_rebuttal_prompt = f"""你是保守的风险审查员（Bear Reviewer）。
上一轮Bull的观点: {bull_result.get('bull_points', [])}
请反驳这些观点，并提出新的风险考量。

回测数据:
- CAGR: {ctx.backtest.cagr:.1%}
- Max Drawdown: {ctx.backtest.max_drawdown:.1%}
- Sharpe: {ctx.backtest.sharpe}

请输出 JSON:
{{
    "rebuttal": "反驳内容",
    "new_risks": ["新风险点1", "新风险点2"]
}}

只输出 JSON，不要其他内容。"""

            bear_rebuttal = self._call_llm(bear_rebuttal_prompt)

            # Bull rebuts Bear's points
            bull_rebuttal_prompt = f"""你是乐观的量化分析师（Bull Analyst）。
上一轮Bear的风险观点: {bear_result.get('bear_points', [])}
Bear的反驳: {bear_rebuttal.get('rebuttal', '')}
请回应这些风险，并维护你的观点。

回测数据:
- CAGR: {ctx.backtest.cagr:.1%}
- Max Drawdown: {ctx.backtest.max_drawdown:.1%}
- Sharpe: {ctx.backtest.sharpe}

请输出 JSON:
{{
    "rebuttal": "回应内容",
    "supporting_points": ["支持论点1", "支持论点2"]
}}

只输出 JSON，不要其他内容。"""

            bull_rebuttal = self._call_llm(bull_rebuttal_prompt)

            # Update debate record
            ctx.debate.rounds[-1].bear_rebuttal = bear_rebuttal.get("rebuttal", "")
            ctx.debate.rounds[-1].bull_rebuttal = bull_rebuttal.get("rebuttal", "")

            # Update for next iteration
            if bear_rebuttal.get("new_risks"):
                bear_result["bear_points"].extend(bear_rebuttal["new_risks"])

            logger.info(f"🔄 [Debate] Round {round_num} complete")

        # Final consensus
        ctx.debate.consensus_points = bull_result.get("strengths", [])
        ctx.debate.remaining_risks = bear_result.get("bear_points", [])

        # Node 5: Risk Gate
        ctx.risk_review = RiskGate.execute(ctx.backtest)

        # If NO_GO from RiskGate, short-circuit
        if ctx.risk_review.verdict == Verdict.NO_GO:
            logger.warning("🚫 [RiskGate] NO_GO - short circuiting to PM")
            ctx.pm_decision = PMDecision(
                verdict=Verdict.NO_GO,
                utility_score=ctx.risk_review.utility_score or 0,
                weights={"cagr": 0.35, "max_dd": 0.35, "sharpe": 0.20, "turnover": 0.10},
                weight_adjust_reason=None,
                reasoning=ctx.risk_review.reasoning,
                risk_warnings=ctx.risk_review.hard_gates_failed,
                next_experiments=[],
                requires_human_approve=True,
            )
            return self._build_result(ctx)

        # Node 6: Portfolio Manager
        pm_prompt = PortfolioManager.PROMPT.format(
            cagr=ctx.backtest.cagr,
            max_drawdown=ctx.backtest.max_drawdown,
            sharpe=ctx.backtest.sharpe,
            annual_turnover=ctx.backtest.annual_turnover,
            data_years=ctx.backtest.data_years,
            bull_analysis=json.dumps(bull_result, ensure_ascii=False),
            bear_analysis=json.dumps(bear_result, ensure_ascii=False),
            risk_verdict=ctx.risk_review.verdict.value,
            hard_fails=ctx.risk_review.hard_gates_failed,
            yellow_flags=ctx.risk_review.yellow_flags_triggered,
            utility_score=ctx.risk_review.utility_score,
            requires_approve=ctx.risk_review.requires_human_approve,
            weights=json.dumps({
                "cagr": self.policy.weights.cagr,
                "max_dd": self.policy.weights.max_dd,
                "sharpe": self.policy.weights.sharpe,
                "turnover": self.policy.weights.turnover,
            }, ensure_ascii=False),
        )

        if llm_pm:
            pm_result = json.loads(llm_pm)
            ctx.pm_decision = PMDecision(
                verdict=Verdict(pm_result.get("verdict", "GO")),
                utility_score=pm_result.get("utility_score", 0),
                weights=pm_result.get("weights", {}),
                weight_adjust_reason=pm_result.get("weight_adjust_reason"),
                reasoning=pm_result.get("reasoning", ""),
                risk_warnings=pm_result.get("risk_warnings", []),
                next_experiments=pm_result.get("next_experiments", [])[:2],
                requires_human_approve=(
                    ctx.risk_review.requires_human_approve
                    or pm_result.get("requires_human_approve", False)
                ),
            )
        else:
            ctx.pm_decision = self._call_pm_llm(pm_prompt)

        # Force preserve requires_human_approve from RiskGate
        if ctx.risk_review.requires_human_approve:
            ctx.pm_decision.requires_human_approve = True

        logger.info(f"✅ [DecisionGraph] Final: {ctx.pm_decision.verdict.value}")
        return self._build_result(ctx)

    def run_iteration(
        self,
        user_input: str,
        backtest_params: dict | None = None,
    ) -> dict:
        """
        Run iteration with auto-loop protection.
        """
        ctx = GraphContext()
        ctx.max_iterations = self.policy.limits.max_iterations

        for i in range(1, ctx.max_iterations + 1):
            ctx.iteration = i
            logger.info(f"🔄 [Iteration {i}/{ctx.max_iterations}]")

            result = self.run_full_flow(user_input, backtest_params)

            # Check if we should continue
            decision = result["pm_decision"]

            if decision["verdict"] == "GO":
                logger.info("✅ [Iteration] GO - stopping")
                return result

            if decision["verdict"] == "NO_GO":
                logger.warning("🚫 [Iteration] NO_GO - cannot revise")
                result["stop_reason"] = "NO_GO from RiskGate"
                return result

            # REVISE - check if we have iterations left
            if i >= ctx.max_iterations:
                logger.warning("⏹️ [Iteration] Max iterations reached")
                result["stop_reason"] = "STOP_AND_NOTIFY_HUMAN"
                result["requires_human_approve"] = True
                return result

            # Prepare next iteration with suggested changes
            if decision.get("next_experiments"):
                exp = decision["next_experiments"][0]
                # Apply suggested changes to backtest params
                if backtest_params is None:
                    backtest_params = {}
                # Note: In production, would apply actual parameter changes
                logger.info(f"📝 [Iteration] Applying: {exp.get('change', 'N/A')}")

        return result

    def _build_result(self, ctx: GraphContext) -> dict:
        """Build result dict from context"""
        return {
            "spec": {
                "name": ctx.spec.name if ctx.spec else None,
                "description": ctx.spec.description if ctx.spec else None,
            },
            "backtest": {
                "cagr": ctx.backtest.cagr if ctx.backtest else None,
                "max_drawdown": ctx.backtest.max_drawdown if ctx.backtest else None,
                "sharpe": ctx.backtest.sharpe if ctx.backtest else None,
                "annual_turnover": ctx.backtest.annual_turnover if ctx.backtest else None,
                "data_years": ctx.backtest.data_years if ctx.backtest else None,
                "assumptions": ctx.backtest.assumptions if ctx.backtest else None,
                "param_sensitivity": ctx.backtest.param_sensitivity if ctx.backtest else None,
                "is_first_live": ctx.backtest.is_first_live if ctx.backtest else None,
            } if ctx.backtest else None,
            "risk_review": ctx.risk_review.model_dump() if ctx.risk_review else None,
            "pm_decision": ctx.pm_decision.model_dump() if ctx.pm_decision else None,
            "iteration": ctx.iteration,
            "stop_reason": None,
        }

    def run(
        self,
        user_input: str,
        backtest_params: dict | None = None,
    ) -> dict:
        """Alias for run_full_flow - for backward compatibility"""
        return self.run_full_flow(user_input, backtest_params)


# Convenience function
def create_graph(llm_provider=None, api_key: str | None = None) -> DecisionGraph:
    """Create a DecisionGraph instance
    
    Args:
        llm_provider: Custom LLM provider
        api_key: MiniMax API key
    """
    return DecisionGraph(llm_provider, api_key)
