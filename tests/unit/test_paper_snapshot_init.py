from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from openhamster.api.db import Base
from openhamster.api.models import ProposalStatus, StrategyProposal
from openhamster.api.services import (
    _bootstrap_paper_trade_for_proposal,
    execute_active_paper_cycle,
    _initialize_paper_snapshot_for_proposal,
    fetch_paper_data,
)
from openhamster.config import get_settings


def test_initialize_paper_snapshot_is_idempotent(monkeypatch, tmp_path: Path) -> None:
    runtime_db = tmp_path / "runtime-paper.db"
    paper_db = tmp_path / "legacy-paper.db"
    app_db = tmp_path / "app.db"

    original_settings = get_settings()
    patched_settings = original_settings.model_copy(
        deep=True,
        update={
            "storage": original_settings.storage.model_copy(
                update={
                    "runtime_db_path": str(runtime_db),
                    "paper_db_path": str(paper_db),
                    "database_url": f"sqlite:///{app_db}",
                }
            )
        },
    )

    import openhamster.api.services as services_module

    monkeypatch.setattr(services_module, "get_settings", lambda: patched_settings)

    engine = create_engine(f"sqlite:///{app_db}", future=True)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)

    current_time = datetime(2026, 3, 13, 10, 0, tzinfo=ZoneInfo(patched_settings.timezone))
    with TestingSession() as db:
        proposal = StrategyProposal(
            run_id="test-run-paper-snapshot",
            title="Paper Snapshot Seed",
            symbol="2800.HK",
            market_scope="HK",
            thesis="Seed initial paper NAV for promoted strategy.",
            source_kind="minimax",
            provider_status="ready",
            provider_model="MiniMax-M2.5",
            provider_message="ok",
            market_snapshot_hash="snapshot-hash",
            event_digest_hash="digest-hash",
            strategy_dsl={"params": {"base_strategy": "rsi"}},
            debate_report={},
            evidence_pack={},
            features_used=["RSI", "macro_summary"],
            deterministic_score=78.0,
            llm_score=80.0,
            final_score=78.6,
            status=ProposalStatus.ACTIVE,
            created_at=current_time,
            updated_at=current_time,
            promoted_at=current_time,
            archived_at=None,
        )
        db.add(proposal)
        db.flush()

        inserted = _initialize_paper_snapshot_for_proposal(
            db,
            proposal=proposal,
            current_time=current_time,
            decision_id="decision-paper-init",
            reason="promoted_to_paper",
        )
        assert inserted is True
        db.commit()

        data = fetch_paper_data(limit=10)
        assert len(data["nav"]) == 1
        assert data["nav"][0]["trade_date"] == current_time.date().isoformat()
        assert data["nav"][0]["cash"] == float(patched_settings.portfolio.default_capital)
        assert data["nav"][0]["position_value"] == 0.0
        assert data["nav"][0]["total_equity"] == float(patched_settings.portfolio.default_capital)

        inserted_again = _initialize_paper_snapshot_for_proposal(
            db,
            proposal=proposal,
            current_time=current_time,
            decision_id="decision-paper-init",
            reason="promoted_to_paper",
        )
        assert inserted_again is False
        db.commit()

        data_again = fetch_paper_data(limit=10)
        assert len(data_again["nav"]) == 1


def test_bootstrap_paper_trade_writes_order_and_position(monkeypatch, tmp_path: Path) -> None:
    runtime_db = tmp_path / "runtime-paper.db"
    paper_db = tmp_path / "legacy-paper.db"
    app_db = tmp_path / "app.db"

    original_settings = get_settings()
    patched_settings = original_settings.model_copy(
        deep=True,
        update={
            "storage": original_settings.storage.model_copy(
                update={
                    "runtime_db_path": str(runtime_db),
                    "paper_db_path": str(paper_db),
                    "database_url": f"sqlite:///{app_db}",
                }
            )
        },
    )

    import openhamster.api.services as services_module

    class DummySourceManager:
        def fetch_latest_price(self, ticker: str) -> float:
            assert ticker == "2800.HK"
            return 20.0

    monkeypatch.setattr(services_module, "get_settings", lambda: patched_settings)
    monkeypatch.setattr(services_module, "get_source_manager", lambda: DummySourceManager())

    engine = create_engine(f"sqlite:///{app_db}", future=True)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)

    current_time = datetime(2026, 3, 13, 10, 0, tzinfo=ZoneInfo(patched_settings.timezone))
    with TestingSession() as db:
        proposal = StrategyProposal(
            run_id="test-run-paper-trade",
            title="Paper Trade Seed",
            symbol="2800.HK",
            market_scope="HK",
            thesis="Seed initial paper trade after promotion.",
            source_kind="minimax",
            provider_status="ready",
            provider_model="MiniMax-M2.5",
            provider_message="ok",
            market_snapshot_hash="snapshot-hash",
            event_digest_hash="digest-hash",
            strategy_dsl={"params": {"base_strategy": "ma_cross"}, "position_sizing": {"mode": "fixed_fraction", "value": 0.25}},
            debate_report={},
            evidence_pack={},
            features_used=["EMA", "macro_summary"],
            deterministic_score=82.0,
            llm_score=84.0,
            final_score=82.6,
            status=ProposalStatus.ACTIVE,
            created_at=current_time,
            updated_at=current_time,
            promoted_at=current_time,
            archived_at=None,
        )
        db.add(proposal)
        db.flush()

        _initialize_paper_snapshot_for_proposal(
            db,
            proposal=proposal,
            current_time=current_time,
            decision_id="decision-paper-init",
            reason="promoted_to_paper",
        )
        inserted = _bootstrap_paper_trade_for_proposal(
            db,
            proposal=proposal,
            current_time=current_time,
            decision_id="decision-paper-trade",
            reason="promoted_to_paper",
        )
        assert inserted is True
        db.commit()

        data = fetch_paper_data(limit=10)
        assert len(data["orders"]) == 1
        assert data["orders"][0]["symbol"] == "2800.HK"
        assert data["orders"][0]["status"] == "filled"
        assert len(data["positions"]) == 1
        assert data["positions"][0]["quantity"] > 0
        assert data["positions"][0]["market_value"] > 0
        assert len(data["nav"]) >= 2


def test_execute_active_paper_cycle_rebalances_and_updates_nav(monkeypatch, tmp_path: Path) -> None:
    runtime_db = tmp_path / "runtime-paper.db"
    paper_db = tmp_path / "legacy-paper.db"
    app_db = tmp_path / "app.db"

    original_settings = get_settings()
    patched_settings = original_settings.model_copy(
        deep=True,
        update={
            "storage": original_settings.storage.model_copy(
                update={
                    "runtime_db_path": str(runtime_db),
                    "paper_db_path": str(paper_db),
                    "database_url": f"sqlite:///{app_db}",
                }
            )
        },
    )

    import openhamster.api.services as services_module

    class DummySourceManager:
        def __init__(self) -> None:
            self.mode = "buy"

        def fetch_latest_price(self, ticker: str) -> float:
            assert ticker == "2800.HK"
            return 20.0 if self.mode == "buy" else 18.0

        def fetch_ohlcv(self, ticker: str, start: str, end: str | None = None) -> pd.DataFrame:
            assert ticker == "2800.HK"
            if self.mode == "buy":
                return pd.DataFrame(
                    {
                        "open": [10.0, 10.0, 10.0, 12.0],
                        "high": [10.2, 10.2, 10.2, 12.2],
                        "low": [9.8, 9.8, 9.8, 11.8],
                        "close": [10.0, 10.0, 10.0, 12.0],
                        "volume": [1000, 1000, 1000, 1000],
                    },
                    index=pd.date_range("2026-03-10", periods=4, freq="D"),
                )
            return pd.DataFrame(
                {
                    "open": [12.0, 12.0, 12.0, 10.0],
                    "high": [12.2, 12.2, 12.2, 10.2],
                    "low": [11.8, 11.8, 11.8, 9.8],
                    "close": [12.0, 12.0, 12.0, 10.0],
                    "volume": [1000, 1000, 1000, 1000],
                },
                index=pd.date_range("2026-03-14", periods=4, freq="D"),
            )

    dummy_source_manager = DummySourceManager()
    monkeypatch.setattr(services_module, "get_settings", lambda: patched_settings)
    monkeypatch.setattr(services_module, "get_source_manager", lambda: dummy_source_manager)

    engine = create_engine(f"sqlite:///{app_db}", future=True)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)

    current_time = datetime(2026, 3, 13, 10, 0, tzinfo=ZoneInfo(patched_settings.timezone))
    with TestingSession() as db:
        proposal = StrategyProposal(
            run_id="test-run-paper-cycle",
            title="Paper Cycle Seed",
            symbol="2800.HK",
            market_scope="HK",
            thesis="Continuously rebalance active paper position.",
            source_kind="minimax",
            provider_status="ready",
            provider_model="MiniMax-M2.5",
            provider_message="ok",
            market_snapshot_hash="snapshot-hash",
            event_digest_hash="digest-hash",
            strategy_dsl={
                "params": {"base_strategy": "ma_cross", "short_window": 2, "long_window": 3},
                "position_sizing": {"mode": "fixed_fraction", "value": 0.25},
            },
            debate_report={},
            evidence_pack={},
            features_used=["EMA", "macro_summary"],
            deterministic_score=82.0,
            llm_score=84.0,
            final_score=82.6,
            status=ProposalStatus.ACTIVE,
            created_at=current_time,
            updated_at=current_time,
            promoted_at=current_time,
            archived_at=None,
        )
        db.add(proposal)
        db.flush()

        _initialize_paper_snapshot_for_proposal(
            db,
            proposal=proposal,
            current_time=current_time,
            decision_id="decision-paper-init",
            reason="promoted_to_paper",
        )

        first_cycle = execute_active_paper_cycle(
            db,
            proposal=proposal,
            current_time=current_time,
            reason="scheduled_execution",
        )
        assert first_cycle["executed"] is True
        assert first_cycle["order_side"] == "buy"
        db.commit()

        dummy_source_manager.mode = "sell"
        second_cycle = execute_active_paper_cycle(
            db,
            proposal=proposal,
            current_time=datetime(2026, 3, 20, 10, 0, tzinfo=ZoneInfo(patched_settings.timezone)),
            reason="scheduled_execution",
        )
        assert second_cycle["executed"] is True
        assert second_cycle["order_side"] == "sell"
        db.commit()

        data = fetch_paper_data(limit=20)
        assert len(data["orders"]) >= 2
        assert data["orders"][0]["side"] == "sell"
        assert data["orders"][1]["side"] == "buy"
        assert len(data["nav"]) >= 3
        assert data["positions"] == []


def test_bootstrap_paper_trade_skips_non_trading_day(monkeypatch, tmp_path: Path) -> None:
    runtime_db = tmp_path / "runtime-paper.db"
    paper_db = tmp_path / "legacy-paper.db"
    app_db = tmp_path / "app.db"

    original_settings = get_settings()
    patched_settings = original_settings.model_copy(
        deep=True,
        update={
            "storage": original_settings.storage.model_copy(
                update={
                    "runtime_db_path": str(runtime_db),
                    "paper_db_path": str(paper_db),
                    "database_url": f"sqlite:///{app_db}",
                }
            )
        },
    )

    import openhamster.api.services as services_module

    class DummySourceManager:
        def fetch_latest_price(self, ticker: str) -> float:
            assert ticker == "2800.HK"
            return 20.0

    monkeypatch.setattr(services_module, "get_settings", lambda: patched_settings)
    monkeypatch.setattr(services_module, "get_source_manager", lambda: DummySourceManager())

    engine = create_engine(f"sqlite:///{app_db}", future=True)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)

    saturday = datetime(2026, 3, 14, 10, 0, tzinfo=ZoneInfo(patched_settings.timezone))
    with TestingSession() as db:
        proposal = StrategyProposal(
            run_id="test-run-paper-trade-weekend",
            title="Weekend Trade Guard",
            symbol="2800.HK",
            market_scope="HK",
            thesis="Do not bootstrap paper fills on weekends.",
            source_kind="minimax",
            provider_status="ready",
            provider_model="MiniMax-M2.5",
            provider_message="ok",
            market_snapshot_hash="snapshot-hash",
            event_digest_hash="digest-hash",
            strategy_dsl={"params": {"base_strategy": "ma_cross"}, "position_sizing": {"mode": "fixed_fraction", "value": 0.25}},
            debate_report={},
            evidence_pack={},
            features_used=["EMA", "macro_summary"],
            deterministic_score=82.0,
            llm_score=84.0,
            final_score=82.6,
            status=ProposalStatus.ACTIVE,
            created_at=saturday,
            updated_at=saturday,
            promoted_at=saturday,
            archived_at=None,
        )
        db.add(proposal)
        db.flush()

        _initialize_paper_snapshot_for_proposal(
            db,
            proposal=proposal,
            current_time=saturday,
            decision_id="decision-paper-init",
            reason="promoted_to_paper",
        )
        inserted = _bootstrap_paper_trade_for_proposal(
            db,
            proposal=proposal,
            current_time=saturday,
            decision_id="decision-paper-trade",
            reason="promoted_to_paper",
        )
        assert inserted is False
        db.commit()

        data = fetch_paper_data(limit=10)
        assert data["orders"] == []
        assert data["positions"] == []
        assert len(data["nav"]) == 1


def test_execute_active_paper_cycle_skips_rebalance_on_non_trading_day(monkeypatch, tmp_path: Path) -> None:
    runtime_db = tmp_path / "runtime-paper.db"
    paper_db = tmp_path / "legacy-paper.db"
    app_db = tmp_path / "app.db"

    original_settings = get_settings()
    patched_settings = original_settings.model_copy(
        deep=True,
        update={
            "storage": original_settings.storage.model_copy(
                update={
                    "runtime_db_path": str(runtime_db),
                    "paper_db_path": str(paper_db),
                    "database_url": f"sqlite:///{app_db}",
                }
            )
        },
    )

    import openhamster.api.services as services_module

    class DummySourceManager:
        def fetch_ohlcv(self, ticker: str, start: str, end: str | None = None) -> pd.DataFrame:
            assert ticker == "2800.HK"
            return pd.DataFrame(
                {
                    "open": [10.0, 10.0, 10.0, 12.0],
                    "high": [10.2, 10.2, 10.2, 12.2],
                    "low": [9.8, 9.8, 9.8, 11.8],
                    "close": [10.0, 10.0, 10.0, 12.0],
                    "volume": [1000, 1000, 1000, 1000],
                },
                index=pd.date_range("2026-03-10", periods=4, freq="D"),
            )

    monkeypatch.setattr(services_module, "get_settings", lambda: patched_settings)
    monkeypatch.setattr(services_module, "get_source_manager", lambda: DummySourceManager())

    engine = create_engine(f"sqlite:///{app_db}", future=True)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)

    friday = datetime(2026, 3, 13, 10, 0, tzinfo=ZoneInfo(patched_settings.timezone))
    saturday = datetime(2026, 3, 14, 10, 0, tzinfo=ZoneInfo(patched_settings.timezone))
    with TestingSession() as db:
        proposal = StrategyProposal(
            run_id="test-run-paper-cycle-weekend",
            title="Weekend Execution Guard",
            symbol="2800.HK",
            market_scope="HK",
            thesis="Do not rebalance on weekends.",
            source_kind="minimax",
            provider_status="ready",
            provider_model="MiniMax-M2.5",
            provider_message="ok",
            market_snapshot_hash="snapshot-hash",
            event_digest_hash="digest-hash",
            strategy_dsl={
                "params": {"base_strategy": "ma_cross", "short_window": 2, "long_window": 3},
                "position_sizing": {"mode": "fixed_fraction", "value": 0.25},
            },
            debate_report={},
            evidence_pack={},
            features_used=["EMA", "macro_summary"],
            deterministic_score=82.0,
            llm_score=84.0,
            final_score=82.6,
            status=ProposalStatus.ACTIVE,
            created_at=friday,
            updated_at=friday,
            promoted_at=friday,
            archived_at=None,
        )
        db.add(proposal)
        db.flush()

        _initialize_paper_snapshot_for_proposal(
            db,
            proposal=proposal,
            current_time=friday,
            decision_id="decision-paper-init",
            reason="promoted_to_paper",
        )
        weekend_cycle = execute_active_paper_cycle(
            db,
            proposal=proposal,
            current_time=saturday,
            reason="scheduled_execution",
        )
        assert weekend_cycle["executed"] is False
        assert weekend_cycle["reason"] == "market_closed_non_trading_day"
        db.commit()

        data = fetch_paper_data(limit=20)
        assert data["orders"] == []
        assert data["positions"] == []
        assert len(data["nav"]) == 2


def test_bootstrap_paper_trade_skips_outside_session(monkeypatch, tmp_path: Path) -> None:
    runtime_db = tmp_path / "runtime-paper.db"
    paper_db = tmp_path / "legacy-paper.db"
    app_db = tmp_path / "app.db"

    original_settings = get_settings()
    patched_settings = original_settings.model_copy(
        deep=True,
        update={
            "storage": original_settings.storage.model_copy(
                update={
                    "runtime_db_path": str(runtime_db),
                    "paper_db_path": str(paper_db),
                    "database_url": f"sqlite:///{app_db}",
                }
            )
        },
    )

    import openhamster.api.services as services_module

    class DummySourceManager:
        def fetch_latest_price(self, ticker: str) -> float:
            assert ticker == "2800.HK"
            return 20.0

    monkeypatch.setattr(services_module, "get_settings", lambda: patched_settings)
    monkeypatch.setattr(services_module, "get_source_manager", lambda: DummySourceManager())

    engine = create_engine(f"sqlite:///{app_db}", future=True)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)

    after_close = datetime(2026, 3, 13, 19, 0, tzinfo=ZoneInfo(patched_settings.timezone))
    with TestingSession() as db:
        proposal = StrategyProposal(
            run_id="test-run-paper-trade-after-close",
            title="After Close Trade Guard",
            symbol="2800.HK",
            market_scope="HK",
            thesis="Do not bootstrap paper fills after market close.",
            source_kind="minimax",
            provider_status="ready",
            provider_model="MiniMax-M2.5",
            provider_message="ok",
            market_snapshot_hash="snapshot-hash",
            event_digest_hash="digest-hash",
            strategy_dsl={"params": {"base_strategy": "ma_cross"}, "position_sizing": {"mode": "fixed_fraction", "value": 0.25}},
            debate_report={},
            evidence_pack={},
            features_used=["EMA", "macro_summary"],
            deterministic_score=82.0,
            llm_score=84.0,
            final_score=82.6,
            status=ProposalStatus.ACTIVE,
            created_at=after_close,
            updated_at=after_close,
            promoted_at=after_close,
            archived_at=None,
        )
        db.add(proposal)
        db.flush()

        _initialize_paper_snapshot_for_proposal(
            db,
            proposal=proposal,
            current_time=after_close,
            decision_id="decision-paper-init",
            reason="promoted_to_paper",
        )
        inserted = _bootstrap_paper_trade_for_proposal(
            db,
            proposal=proposal,
            current_time=after_close,
            decision_id="decision-paper-trade",
            reason="promoted_to_paper",
        )
        assert inserted is False
        db.commit()

        data = fetch_paper_data(limit=10)
        assert data["orders"] == []
        assert data["positions"] == []
        assert len(data["nav"]) == 1
