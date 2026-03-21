from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from openhamster.api.db import Base
from openhamster.api.models import ProposalStatus, StrategyProposal
from openhamster.api.services import prune_strategy_proposals
from openhamster.config import get_settings


def _make_proposal(
    *,
    run_id: str,
    title: str,
    status: ProposalStatus,
    score: float,
    created_at: datetime,
) -> StrategyProposal:
    return StrategyProposal(
        run_id=run_id,
        title=title,
        symbol="2800.HK",
        market_scope="HK",
        thesis=f"{title} thesis",
        source_kind="minimax",
        provider_status="ready",
        provider_model="MiniMax-M2.5",
        provider_message="ok",
        market_snapshot_hash=f"snapshot-{run_id}",
        event_digest_hash=f"digest-{run_id}",
        strategy_dsl={"params": {"base_strategy": "rsi"}},
        debate_report={},
        evidence_pack={},
        features_used=["RSI"],
        deterministic_score=score,
        llm_score=score,
        final_score=score,
        status=status,
        created_at=created_at,
        updated_at=created_at,
        promoted_at=created_at if status == ProposalStatus.ACTIVE else None,
        archived_at=None,
    )


def test_prune_strategy_proposals_archives_old_rejected_and_candidate_overflow(monkeypatch, tmp_path: Path) -> None:
    app_db = tmp_path / "app.db"
    original_settings = get_settings()
    patched_settings = original_settings.model_copy(
        deep=True,
        update={
            "storage": original_settings.storage.model_copy(
                update={"database_url": f"sqlite:///{app_db}"}
            ),
            "governance": original_settings.governance.model_copy(
                update={
                    "candidate_retention_limit": 2,
                    "candidate_max_age_days": 7,
                    "rejected_retention_days": 2,
                }
            ),
        },
    )

    import openhamster.api.services as services_module

    monkeypatch.setattr(services_module, "get_settings", lambda: patched_settings)

    engine = create_engine(f"sqlite:///{app_db}", future=True)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)

    current_time = datetime(2026, 3, 15, 12, 0, tzinfo=ZoneInfo(patched_settings.timezone))
    with TestingSession() as db:
        db.add_all(
            [
                _make_proposal(
                    run_id="active-1",
                    title="Active Baseline",
                    status=ProposalStatus.ACTIVE,
                    score=82.0,
                    created_at=current_time - timedelta(days=1),
                ),
                _make_proposal(
                    run_id="cand-1",
                    title="Candidate 1",
                    status=ProposalStatus.CANDIDATE,
                    score=81.0,
                    created_at=current_time - timedelta(days=1),
                ),
                _make_proposal(
                    run_id="cand-2",
                    title="Candidate 2",
                    status=ProposalStatus.CANDIDATE,
                    score=79.0,
                    created_at=current_time - timedelta(days=2),
                ),
                _make_proposal(
                    run_id="cand-3",
                    title="Candidate 3",
                    status=ProposalStatus.CANDIDATE,
                    score=73.0,
                    created_at=current_time - timedelta(days=3),
                ),
                _make_proposal(
                    run_id="cand-old",
                    title="Old Candidate",
                    status=ProposalStatus.CANDIDATE,
                    score=77.0,
                    created_at=current_time - timedelta(days=10),
                ),
                _make_proposal(
                    run_id="rej-old",
                    title="Old Rejected",
                    status=ProposalStatus.REJECTED,
                    score=60.0,
                    created_at=current_time - timedelta(days=5),
                ),
            ]
        )
        db.commit()

        archived = prune_strategy_proposals(
            db,
            active_symbol="2800.HK",
            active_market_scope="HK",
            current_time=current_time,
        )
        db.commit()

        assert archived["rejected_retention"] == 1
        assert archived["aged_candidates"] == 1
        assert archived["overflow_candidates"] == 1

        remaining_candidates = {
            proposal.run_id
            for proposal in db.query(StrategyProposal)
            .filter(StrategyProposal.status == ProposalStatus.CANDIDATE)
            .all()
        }
        assert remaining_candidates == {"cand-1", "cand-2"}

        archived_runs = {
            proposal.run_id
            for proposal in db.query(StrategyProposal)
            .filter(StrategyProposal.status == ProposalStatus.ARCHIVED)
            .all()
        }
        assert {"cand-3", "cand-old", "rej-old"}.issubset(archived_runs)
