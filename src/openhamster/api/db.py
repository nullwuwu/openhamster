from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine, event, inspect
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from ..config import get_settings
from ..runtime_state import init_runtime_state_store


class Base(DeclarativeBase):
    pass


_settings = get_settings()
_database_url = _settings.storage.database_url
_connect_args = {"check_same_thread": False, "timeout": 30} if _database_url.startswith("sqlite") else {}

if _database_url.startswith("sqlite"):
    database_path = make_url(_database_url).database
    if database_path and database_path != ":memory:":
        Path(database_path).parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(_database_url, future=True, connect_args=_connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


if _database_url.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.close()


def get_db() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def init_database() -> None:
    # Ensure SQLAlchemy model metadata is imported before create_all.
    from . import models as _models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    init_runtime_state_store()
    if _database_url.startswith("sqlite"):
        _repair_sqlite_schema()


def _repair_sqlite_schema() -> None:
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    try:
        with engine.begin() as conn:
            if "strategy_proposals" in existing_tables:
                columns = {column["name"] for column in inspector.get_columns("strategy_proposals")}
                if "provider_status" not in columns:
                    conn.exec_driver_sql(
                        "ALTER TABLE strategy_proposals ADD COLUMN provider_status VARCHAR(32) NOT NULL DEFAULT 'mock'"
                    )
                if "provider_model" not in columns:
                    conn.exec_driver_sql(
                        "ALTER TABLE strategy_proposals ADD COLUMN provider_model VARCHAR(64) NOT NULL DEFAULT ''"
                    )
                if "provider_message" not in columns:
                    conn.exec_driver_sql(
                        "ALTER TABLE strategy_proposals ADD COLUMN provider_message TEXT NOT NULL DEFAULT ''"
                    )

            if "runtime_settings" not in existing_tables:
                conn.exec_driver_sql(
                    """
                    CREATE TABLE runtime_settings (
                        key VARCHAR(64) PRIMARY KEY NOT NULL,
                        value_json JSON NOT NULL,
                        updated_at DATETIME NOT NULL
                    )
                    """
                )

            if "event_records" in existing_tables:
                conn.exec_driver_sql("DELETE FROM event_records WHERE event_type != 'macro'")
                conn.exec_driver_sql(
                    "CREATE INDEX IF NOT EXISTS ix_event_records_market_published_at "
                    "ON event_records (market_scope, published_at)"
                )

            if "daily_event_digests" in existing_tables:
                digest_columns = {column["name"] for column in inspector.get_columns("daily_event_digests")}
                legacy_digest_columns = {"news_summary", "announcement_summary", "news_heat", "announcement_risk"}
                if digest_columns & legacy_digest_columns:
                    conn.exec_driver_sql(
                        """
                        CREATE TABLE daily_event_digests__new (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            trade_date VARCHAR(10) NOT NULL,
                            market_scope VARCHAR(16) NOT NULL DEFAULT 'HK',
                            symbol_scope VARCHAR(32) NOT NULL DEFAULT '*',
                            macro_summary TEXT NOT NULL DEFAULT '',
                            event_scores JSON NOT NULL DEFAULT '{}',
                            digest_hash VARCHAR(64) NOT NULL,
                            event_ids JSON NOT NULL DEFAULT '[]',
                            created_at DATETIME NOT NULL,
                            CONSTRAINT uq_daily_digest_scope UNIQUE (trade_date, market_scope, symbol_scope)
                        )
                        """
                    )
                    conn.exec_driver_sql(
                        """
                        INSERT INTO daily_event_digests__new (
                            id, trade_date, market_scope, symbol_scope, macro_summary, event_scores, digest_hash, event_ids, created_at
                        )
                        SELECT
                            id,
                            trade_date,
                            COALESCE(market_scope, 'HK'),
                            COALESCE(symbol_scope, '*'),
                            COALESCE(macro_summary, ''),
                            COALESCE(event_scores, '{}'),
                            digest_hash,
                            COALESCE(event_ids, '[]'),
                            created_at
                        FROM daily_event_digests
                        """
                    )
                    conn.exec_driver_sql("DROP TABLE daily_event_digests")
                    conn.exec_driver_sql("ALTER TABLE daily_event_digests__new RENAME TO daily_event_digests")
                    conn.exec_driver_sql(
                        "CREATE INDEX IF NOT EXISTS ix_daily_event_digests_digest_hash ON daily_event_digests (digest_hash)"
                    )
                    conn.exec_driver_sql(
                        "CREATE INDEX IF NOT EXISTS ix_daily_event_digests_trade_date ON daily_event_digests (trade_date)"
                    )
                conn.exec_driver_sql(
                    "CREATE INDEX IF NOT EXISTS ix_daily_event_digests_scope_trade_date "
                    "ON daily_event_digests (market_scope, symbol_scope, trade_date)"
                )
                conn.exec_driver_sql(
                    """
                    UPDATE daily_event_digests
                    SET event_scores = json_set(
                        COALESCE(event_scores, '{}'),
                        '$.aggregate_sentiment', COALESCE(json_extract(event_scores, '$.aggregate_sentiment'), 0.0),
                        '$.macro_bias', COALESCE(json_extract(event_scores, '$.macro_bias'), COALESCE(json_extract(event_scores, '$.macro_pressure'), 0.0))
                    )
                    """
                )

            if "audit_records" in existing_tables:
                conn.exec_driver_sql(
                    "CREATE INDEX IF NOT EXISTS ix_audit_records_event_created_at "
                    "ON audit_records (event_type, created_at)"
                )
                conn.exec_driver_sql(
                    "CREATE INDEX IF NOT EXISTS ix_audit_records_entity_event_created_at "
                    "ON audit_records (entity_type, event_type, created_at)"
                )
                conn.exec_driver_sql(
                    "CREATE INDEX IF NOT EXISTS ix_audit_records_decision_created_at "
                    "ON audit_records (decision_id, created_at)"
                )
    except OperationalError as exc:
        if "database is locked" not in str(exc).lower():
            raise
