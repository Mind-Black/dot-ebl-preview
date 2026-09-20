"""Progress tracking, timing, and cancellation support."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, Optional


class JobCancelledError(Exception):
    """Raised when a job is cancelled."""
    pass


@dataclass
class ProgressTracker:
    """Progress tracker supporting ETA, elapsed time, and cancellation."""
    total_steps: int
    step: int = 0
    start_time: float = field(default_factory=time.time)
    is_cancelled: bool = False
    callback: Optional[Callable[[float, float, Optional[float]], None]] = None

    def cancel(self) -> None:
        self.is_cancelled = True

    def check_cancellation(self) -> None:
        if self.is_cancelled:
            raise JobCancelledError("Job execution was cancelled by user.")

    def advance(self, amount: int = 1) -> None:
        self.check_cancellation()
        self.step = min(self.total_steps, self.step + amount)
        self._notify()

    def update_to(self, step: int) -> None:
        self.check_cancellation()
        self.step = min(self.total_steps, max(0, step))
        self._notify()

    def finish(self) -> None:
        self.check_cancellation()
        self.step = self.total_steps
        self._notify()

    @property
    def fraction(self) -> float:
        if self.total_steps <= 0:
            return 1.0
        return float(self.step) / float(self.total_steps)

    @property
    def elapsed_seconds(self) -> float:
        return time.time() - self.start_time

    @property
    def eta_seconds(self) -> Optional[float]:
        frac = self.fraction
        if frac <= 0.0 or frac >= 1.0:
            return 0.0 if frac >= 1.0 else None
        elapsed = self.elapsed_seconds
        total_estimated = elapsed / frac
        return max(0.0, total_estimated - elapsed)

    def _notify(self) -> None:
        if self.callback is not None:
            self.callback(self.fraction, self.elapsed_seconds, self.eta_seconds)
