from __future__ import annotations

from goby_shrimp.prompts import (
    MARKET_ANALYST_PROMPT_VERSION,
    MARKET_ANALYST_SCHEMA_HINT,
    RESEARCH_DEBATE_PROMPT_VERSION,
    RESEARCH_DEBATE_SCHEMA_HINT,
    RISK_MANAGER_LLM_PROMPT_VERSION,
    RISK_MANAGER_LLM_SCHEMA_HINT,
    STRATEGY_AGENT_PROMPT_VERSION,
    STRATEGY_AGENT_SCHEMA_HINT,
    build_market_analyst_payload,
    build_research_debate_payload,
    build_risk_manager_llm_payload,
    build_strategy_agent_payload,
)


def test_market_analyst_prompt_contract() -> None:
    payload = build_market_analyst_payload(
        symbol="2800.HK",
        timezone="Asia/Shanghai",
        deterministic_snapshot={"regime": "balanced", "confidence": 0.63},
        event_digest={"macro_summary": "macro"},
        market_profile={"market_scope": "HK", "label": "Hong Kong"},
    )

    assert payload["prompt_version"] == MARKET_ANALYST_PROMPT_VERSION
    assert payload["market_profile"]["market_scope"] == "HK"
    assert payload["output_schema"]["event_bias"] == "bullish|neutral|defensive"
    assert MARKET_ANALYST_SCHEMA_HINT["summary"] == ""


def test_strategy_agent_prompt_contract() -> None:
    payload = build_strategy_agent_payload(
        symbol="2800.HK",
        market_scope="HK",
        timezone="Asia/Shanghai",
        market_snapshot={"regime": "defensive"},
        market_profile={"market_scope": "HK", "preferred_baseline_tags": ["trend"]},
        baseline_strategies=[{"strategy_name": "ma_cross"}],
        strategy_knowledge=[{"family_key": "trend_following"}],
        knowledge_preferences=["trend_following"],
        knowledge_discouraged=["mean_reversion"],
        baseline_family_map={"ma_cross": ["trend_following"]},
        hard_limits=["long-only", "no leverage"],
    )

    proposal_schema = payload["output_schema"]["proposals"][0]
    assert payload["prompt_version"] == STRATEGY_AGENT_PROMPT_VERSION
    assert payload["market_profile"]["market_scope"] == "HK"
    assert proposal_schema["base_strategy"].endswith("novel_composite")
    assert isinstance(STRATEGY_AGENT_SCHEMA_HINT["proposals"], list)


def test_research_debate_prompt_contract() -> None:
    payload = build_research_debate_payload(
        proposal={"title": "test"},
        market_snapshot={"regime": "balanced"},
        market_profile={"market_scope": "HK"},
        event_digest={"macro_summary": "macro"},
        knowledge_context={"families_used": ["trend_following"]},
    )

    assert payload["prompt_version"] == RESEARCH_DEBATE_PROMPT_VERSION
    assert payload["market_profile"]["market_scope"] == "HK"
    assert payload["output_schema"]["stance_for"] == ["string"]
    assert payload["output_language"] == "zh-CN"
    assert RESEARCH_DEBATE_SCHEMA_HINT["synthesis"] == ""


def test_risk_manager_prompt_contract() -> None:
    payload = build_risk_manager_llm_payload(
        proposal={"title": "test"},
        debate_report={"stance_for": [], "stance_against": [], "synthesis": "none"},
        evidence_pack={"bottom_line_report": {"drawdown_ok": True}},
        market_snapshot={"regime": "balanced"},
        market_profile={"market_scope": "HK"},
        event_digest={"macro_summary": "macro"},
        knowledge_context={"families_used": ["trend_following"]},
    )

    assert payload["prompt_version"] == RISK_MANAGER_LLM_PROMPT_VERSION
    assert payload["market_profile"]["market_scope"] == "HK"
    assert payload["output_schema"]["llm_score"] == "number between 0 and 100"
    assert RISK_MANAGER_LLM_SCHEMA_HINT["llm_explanation"] == ""
