from __future__ import annotations

import asyncio
import contextlib
import logging

from sqlalchemy.orm import Session

from ..api.db import SessionLocal
from ..api.services import sync_agent_state
from ..config import get_settings

logger = logging.getLogger(__name__)


class PipelineScheduler:
    """Run the research pipeline on a fixed cadence."""

    def __init__(self, session_factory=SessionLocal, interval_minutes: int | None = None) -> None:
        self._session_factory = session_factory
        configured_interval = interval_minutes or get_settings().events.expected_sync_interval_minutes
        self.interval_seconds = max(60, configured_interval * 60)
        self._task: asyncio.Task[None] | None = None

    def run_once(self, trigger: str) -> None:
        with self._session_factory() as db:
            sync_agent_state(db, trigger=trigger)

    async def _loop(self) -> None:
        while True:
            await asyncio.sleep(self.interval_seconds)
            try:
                await asyncio.to_thread(self.run_once, "scheduler")
            except Exception:
                logger.exception("Scheduled pipeline sync failed.")

    def start(self) -> asyncio.Task[None]:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._loop())
        return self._task

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task
        self._task = None


def build_pipeline_scheduler() -> PipelineScheduler:
    return PipelineScheduler()
