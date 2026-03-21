from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from openhamster.api.models import ProposalStatus, RiskDecisionAction
from openhamster.api.services import _governance_action
from openhamster.config import get_settings


def test_real_candidate_can_replace_mock_active_without_delta_threshold() -> None:
    current_time = datetime.now(ZoneInfo(get_settings().timezone))
    status, action, report = _governance_action(
        final_score=76.5,
        bottom_line_passed=True,
        active_context={
            'title': 'Legacy Mock Active',
            'final_score': 75.9,
            'source_kind': 'mock',
            'promoted_at': current_time.isoformat(),
        },
        macro_status={'degraded': False, 'provider': 'fred', 'status': 'ready'},
        market_scope='HK',
        current_time=current_time,
        proposal_source_kind='minimax',
        backtest_gate={
            'eligible_for_paper': True,
            'blocked_reasons': [],
            'summary': 'Backtest admission passed.',
        },
    )

    assert status == ProposalStatus.ACTIVE
    assert action == RiskDecisionAction.PROMOTE_TO_PAPER
    assert report['active_comparison']['replacing_mock_active'] is True


def test_backtest_gate_blocks_promotion_to_paper() -> None:
    current_time = datetime.now(ZoneInfo(get_settings().timezone))
    status, action, report = _governance_action(
        final_score=83.0,
        bottom_line_passed=True,
        active_context=None,
        macro_status={'degraded': False, 'provider': 'fred', 'status': 'ready'},
        market_scope='HK',
        current_time=current_time,
        proposal_source_kind='minimax',
        backtest_gate={
            'eligible_for_paper': False,
            'blocked_reasons': ['backtest_review_required'],
            'summary': 'Backtest requires human review before paper promotion.',
        },
    )

    assert status == ProposalStatus.CANDIDATE
    assert action == RiskDecisionAction.KEEP_CANDIDATE
    assert 'backtest_review_required' in report['promotion_gate']['blocked_reasons']
    assert report['promotion_gate']['backtest_required'] is True
