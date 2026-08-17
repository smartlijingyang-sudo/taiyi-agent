"""taiyi-timer — 1:1 Python port of @deepseek-ai/timer.

Public API surface re-exported here for convenience. The stable contract
is defined in :mod:`timer.invariant`; consumers should depend on that
submodule when they need a stable API surface.
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
