from __future__ import annotations

from typing import Any

MARKET_ANALYST_PROMPT_VERSION = 'market_analyst.v1'
MARKET_ANALYST_SCHEMA_HINT = {
    'summary': '',
    'event_bias': 'neutral',
    'watchpoints': [],
    'confidence_adjustment': 0.0,
}


def market_analyst_system_prompt() -> str:
    return (
        'You are MarketAnalystAgent for OpenHamster. '
        'Return JSON only. Do not suggest trades. '
        'Write all natural-language fields in Simplified Chinese for a Chinese-language operator dashboard. '
        'Summarize the market regime using price context, macro digest, and the explicit market profile. '
        'Stay within a research-assistant role and do not override hard risk rules.'
    )


def build_market_analyst_payload(
    *,
    symbol: str,
    timezone: str,
    deterministic_snapshot: dict[str, Any],
    event_digest: dict[str, Any],
    market_profile: dict[str, Any],
) -> dict[str, Any]:
    return {
        'prompt_version': MARKET_ANALYST_PROMPT_VERSION,
        'task': 'Summarize market conditions for downstream strategy generation.',
        'output_language': 'zh-CN',
        'symbol': symbol,
        'timezone': timezone,
        'market_profile': market_profile,
        'deterministic_snapshot': deterministic_snapshot,
        'event_digest': event_digest,
        'output_schema': {
            'summary': 'string',
            'event_bias': 'bullish|neutral|defensive',
            'watchpoints': ['string'],
            'confidence_adjustment': 'number between -0.15 and 0.15',
        },
    }
