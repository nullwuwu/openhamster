from __future__ import annotations

from typing import Any

from ..strategy import strategy_plugin_names

STRATEGY_AGENT_PROMPT_VERSION = 'strategy_agent.v1'
STRATEGY_AGENT_SCHEMA_HINT = {'proposals': []}


def strategy_agent_system_prompt() -> str:
    return (
        'You are StrategyAgent for GobyShrimp. '
        'Return JSON only. Create up to 3 candidate strategy proposals. '
        'Write all free-text fields in Simplified Chinese for a Chinese-language operator dashboard. '
        'Treat supplied strategy knowledge as structured prior art: use it to anchor reasoning, not to copy a finished strategy verbatim. '
        'External candidate knowledge is supplemental prior art and must not outweigh builtin governance knowledge. '
        'You may recombine baseline ideas into a new thesis, but stay within long-only, no-leverage, daily-rebalance constraints. '
        'Respect the supplied market profile and prefer baselines that fit the current market structure. '
        'Baseline strategies are priors, not hard limits. If none fit directly, use novel_composite as the anchor strategy label.'
    )


def build_strategy_agent_payload(
    *,
    symbol: str,
    market_scope: str,
    timezone: str,
    market_snapshot: dict[str, Any],
    market_profile: dict[str, Any],
    baseline_strategies: list[dict[str, Any]],
    strategy_knowledge: list[dict[str, Any]],
    external_candidate_knowledge: list[dict[str, Any]],
    knowledge_preferences: list[str],
    knowledge_discouraged: list[str],
    baseline_family_map: dict[str, list[str]],
    hard_limits: list[str],
) -> dict[str, Any]:
    strategy_labels = "|".join(strategy_plugin_names(include_llm_anchor=True))
    return {
        'prompt_version': STRATEGY_AGENT_PROMPT_VERSION,
        'task': 'Generate up to 3 candidate strategy proposals for paper trading review.',
        'output_language': 'zh-CN',
        'symbol': symbol,
        'market_scope': market_scope,
        'timezone': timezone,
        'hard_limits': hard_limits,
        'market_snapshot': market_snapshot,
        'market_profile': market_profile,
        'baseline_strategies': baseline_strategies,
        'strategy_knowledge': strategy_knowledge,
        'external_candidate_knowledge': external_candidate_knowledge,
        'knowledge_preferences': knowledge_preferences,
        'knowledge_discouraged': knowledge_discouraged,
        'baseline_family_map': baseline_family_map,
        'output_schema': {
            'proposals': [
                {
                    'title': 'string',
                    'base_strategy': strategy_labels,
                    'thesis': 'string',
                    'knowledge_families_used': ['trend_following'],
                    'baseline_delta_summary': 'string',
                    'novelty_claim': 'string',
                    'features_used': ['SMA', 'EMA', 'RSI', 'MACD', 'ATR', 'ADX', 'Bollinger', 'Donchian', 'ROC', 'Volume MA', 'volatility', 'drawdown', 'macro_summary'],
                    'params': {'any': 'json object'},
                }
            ]
        },
    }
