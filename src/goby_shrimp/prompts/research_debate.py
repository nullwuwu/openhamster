from __future__ import annotations

from typing import Any

RESEARCH_DEBATE_PROMPT_VERSION = 'research_debate.v1'
RESEARCH_DEBATE_SCHEMA_HINT = {
    'stance_for': [],
    'stance_against': [],
    'synthesis': '',
}


def research_debate_system_prompt() -> str:
    return (
        'You are ResearchDebateAgent for GobyShrimp. '
        'Return JSON only. Produce a concise case-for and case-against for one strategy proposal. '
        'Write all natural-language fields in Simplified Chinese for a Chinese-language operator dashboard. '
        'Assess whether the proposal fits the supplied market profile rather than a generic equity market. '
        'Do not decide promotion. Do not mention execution outside paper trading constraints.'
    )


def build_research_debate_payload(
    *,
    proposal: dict[str, Any],
    market_snapshot: dict[str, Any],
    event_digest: dict[str, Any],
    market_profile: dict[str, Any],
) -> dict[str, Any]:
    return {
        'prompt_version': RESEARCH_DEBATE_PROMPT_VERSION,
        'task': 'Stress test a single strategy proposal and produce debate output.',
        'output_language': 'zh-CN',
        'proposal': proposal,
        'market_snapshot': market_snapshot,
        'market_profile': market_profile,
        'event_digest': event_digest,
        'output_schema': {
            'stance_for': ['string'],
            'stance_against': ['string'],
            'synthesis': 'string',
        },
    }
