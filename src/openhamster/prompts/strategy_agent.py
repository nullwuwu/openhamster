from __future__ import annotations

from typing import Any

from ..strategy import strategy_plugin_names

STRATEGY_AGENT_PROMPT_VERSION = 'strategy_agent.v1'
STRATEGY_AGENT_SCHEMA_HINT = {'proposals': []}


def strategy_agent_system_prompt() -> str:
    return (
        'You are StrategyAgent for OpenHamster. '
        'Return JSON only. Create up to 3 candidate strategy proposals. '
        'Write all free-text fields in Simplified Chinese for a Chinese-language operator dashboard. '
        'Treat supplied strategy knowledge as structured prior art: use it to anchor reasoning, not to copy a finished strategy verbatim. '
        'External candidate knowledge is supplemental prior art and must not outweigh builtin governance knowledge. '
        'You may recombine baseline ideas into a new thesis, but stay within long-only, no-leverage, daily-rebalance constraints. '
        'Respect the supplied market profile and prefer baselines that fit the current market structure. '
        'Baseline strategies are priors, not hard limits. If none fit directly, use novel_composite as the anchor strategy label. '
        'Only emit params that are explicitly listed in allowed_params for the chosen base_strategy. '
        'Do not invent unsupported knobs, hidden risk controls, or extra indicators that the executor cannot run. '
        'Start from current_market_conditions, knowledge_preferences, and discouraged families before drafting any proposal. '
        'If preferred families are supplied, at least one proposal should come directly from a preferred family unless no executable baseline exists. '
        'Use proposal_templates as concrete structure priors when they fit the market and hard limits. '
        'For ranking or portfolio overlays, explain liquidity, turnover, position-count, or concentration assumptions in Chinese. '
        'Avoid rule stacking without a clear reason; if combining many families, state why the added layers are necessary. '
        'Do not emit a discouraged family unless the market snapshot shows a clear exception and the thesis explains that exception in Chinese. '
        'Prefer simple, defensive variants with lower turnover, longer holding periods, and drawdown control over complex feature stacking. '
        'If market_snapshot.regime is RANGING, low-conviction, or sideways, do not default to breakout ideas. '
        'In those environments prefer mean_reversion, or defensive ma_cross/macd variants with longer windows and lower turnover. '
        'Only use channel_breakout when the payload clearly shows volatility expansion and a strong directional case. '
        'For ma_cross in fragile or ranging markets, prefer short_window around 8-15 and long_window around 30-60. '
        'For macd in fragile or ranging markets, prefer slower settings over aggressive fast-turnover settings. '
        'For mean_reversion, prefer moderate thresholds and stable holding behavior instead of rapid oscillation. '
        'For mean_reversion in strong ranging markets, prefer z_window around 24-40, entry_threshold around 1.4-1.9, exit_threshold around 0.2-0.6, and keep use_short false. '
        'Avoid proposals that are likely to produce negative CAGR, negative Sharpe, or drawdown near the hard gate. '
        'When current_market_conditions include range_bound, low_conviction, or choppy_reversal, trend_following and breakout require extra caution; prefer defensive trend filters or mean reversion first. '
        'If a proposal uses trend_following in a fragile market, make it slower and explicitly state the defensive adaptation in baseline_delta_summary. '
        'If a proposal is only a mild parameter change from a baseline, say so explicitly in baseline_delta_summary and novelty_claim.'
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
    proposal_templates: list[dict[str, Any]],
    knowledge_preferences: list[str],
    knowledge_discouraged: list[str],
    current_market_conditions: list[str],
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
        'proposal_templates': proposal_templates,
        'knowledge_preferences': knowledge_preferences,
        'knowledge_discouraged': knowledge_discouraged,
        'current_market_conditions': current_market_conditions,
        'family_priority': {
            'preferred': knowledge_preferences,
            'discouraged': knowledge_discouraged,
            'market_conditions': current_market_conditions,
        },
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
            ],
            'generation_rules': {
                'max_proposals': 3,
                'prefer_defensive': True,
                'prefer_lower_turnover': True,
                'prefer_longer_holding': True,
                'params_must_be_subset_of_allowed_params': True,
                'unsupported_params_will_be_dropped': True,
            },
        },
    }
