"""timer.invariant — stable public API contract for taiyi-timer.

This subpackage mirrors the upstream `vendor/timer/src/invariant` barrel
pattern. Consumers that need a stable dependency on the timer API can
import from :mod:`timer.invariant` instead of :mod:`timer` directly.
"""

from __future__ import annotations

from timer.service import CancelHandle, TimerError, TimerService, WrapperWithDispose
from timer.time import Time

__all__ = [
    "CancelHandle",
    "TimerError",
    "TimerService",
    "Time",
    "WrapperWithDispose",
]
