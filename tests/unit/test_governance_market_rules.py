from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from goby_shrimp.api.models import ProposalStatus, RiskDecisionAction
from goby_shrimp.api.services import _governance_action
from goby_shrimp.config import get_settings


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
    )

    assert status == ProposalStatus.ACTIVE
    assert action == RiskDecisionAction.PROMOTE_TO_PAPER
    assert report['active_comparison']['replacing_mock_active'] is True
