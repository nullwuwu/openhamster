from __future__ import annotations

from typing import Any

RISK_MANAGER_LLM_PROMPT_VERSION = 'risk_manager_llm.v1'
RISK_MANAGER_LLM_SCHEMA_HINT = {
    'llm_score': 70.0,
    'llm_explanation': '',
}


def risk_manager_llm_system_prompt() -> str:
    return (
        'You are the LLM assistant for RiskManagerAgent in OpenHamster. '
        'Return JSON only. You do not control the final decision. '
        'Write explanations in Simplified Chinese for a Chinese-language operator dashboard. '
        'Score contextual fit between 0 and 100 and explain the score briefly, explicitly using the supplied market profile. '
        'Use the supplied strategy knowledge as an evaluation prior for family fit, failure modes, and novelty, but do not override hard gates. '
        'Hard gates are enforced elsewhere and must never be overridden.'
    )


def build_risk_manager_llm_payload(
    *,
    proposal: dict[str, Any],
    debate_report: dict[str, Any],
    evidence_pack: dict[str, Any],
    market_snapshot: dict[str, Any],
    event_digest: dict[str, Any],
    market_profile: dict[str, Any],
    knowledge_context: dict[str, Any],
) -> dict[str, Any]:
    return {
        'prompt_version': RISK_MANAGER_LLM_PROMPT_VERSION,
        'task': 'Score contextual fit for a candidate strategy proposal.',
        'output_language': 'zh-CN',
        'proposal': proposal,
        'debate_report': debate_report,
        'evidence_pack': evidence_pack,
        'market_snapshot': market_snapshot,
        'market_profile': market_profile,
        'event_digest': event_digest,
        'knowledge_context': knowledge_context,
        'output_schema': {
            'llm_score': 'number between 0 and 100',
            'llm_explanation': 'string',
        },
    }
