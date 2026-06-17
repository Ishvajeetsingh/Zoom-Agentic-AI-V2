from __future__ import annotations

import threading
import time

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class SyncScheduler:
    _instance: SyncScheduler | None = None

    def __init__(self) -> None:
        self._shutdown_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._poll_interval: float = 60.0

    @classmethod
    def get_instance(cls) -> SyncScheduler:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def start(self, poll_interval: float = 60.0) -> None:
        if self._thread is not None and self._thread.is_alive():
            logger.warning("sync_scheduler.already_running")
            return

        self._poll_interval = poll_interval
        self._shutdown_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop,
            name="sync-scheduler",
            daemon=True,
        )
        self._thread.start()
        logger.info("sync_scheduler.started", extra={"poll_interval": poll_interval})

    def stop(self, timeout: float = 30.0) -> None:
        self._shutdown_event.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            self._thread = None
        logger.info("sync_scheduler.stopped")

    @property
    def is_running(self) -> bool:
        return not self._shutdown_event.is_set() and self._thread is not None and self._thread.is_alive()

    def _run_loop(self) -> None:
        logger.info("sync_scheduler.loop_started")
        while not self._shutdown_event.is_set():
            try:
                self._run_sync_cycle()
            except Exception:
                logger.exception("sync_scheduler.cycle_error")
            self._shutdown_event.wait(self._poll_interval)

    def _run_sync_cycle(self) -> None:
        from app.services.sync_service import SyncService
        try:
            service = SyncService()
            service.run_auto_sync()
        except Exception:
            logger.exception("sync_scheduler.sync_cycle_error")
