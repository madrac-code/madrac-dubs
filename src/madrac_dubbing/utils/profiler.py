"""Startup Profiler — measure and log initialization timing"""
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

logger = logging.getLogger(__name__)


@dataclass
class TimerEvent:
    label: str
    elapsed_s: float


class StartupProfiler:
    """Lightweight profiler that logs and persists startup timing events.

    Usage::

        profiler = StartupProfiler()
        profiler.mark("Workspace initialized")
        ...
        profiler.mark("GUI ready")
        profiler.save(plugins_root / "logs" / "startup_profile.json")
    """

    def __init__(self) -> None:
        self._start = time.perf_counter()
        self._last = self._start
        self._events: List[TimerEvent] = []

    def mark(self, label: str) -> None:
        now = time.perf_counter()
        elapsed = now - self._start
        self._events.append(TimerEvent(label=label, elapsed_s=round(elapsed, 3)))
        logger.info("[PROFILE] %8.3fs  %s", elapsed, label)
        self._last = now

    def log_summary(self) -> None:
        logger.info("── Startup profile ──")
        for ev in self._events:
            logger.info("  [%8.3fs]  %s", ev.elapsed_s, ev.label)
        if self._events:
            total = self._events[-1].elapsed_s
            logger.info("  Total: %.3fs", total)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "total_s": self._events[-1].elapsed_s if self._events else 0,
            "events": [{"label": e.label, "elapsed_s": e.elapsed_s} for e in self._events],
        }
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        logger.debug("Profile saved to %s", path)

    @property
    def events(self) -> List[TimerEvent]:
        return list(self._events)
