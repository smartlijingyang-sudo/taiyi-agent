"""taiyi-hmr — Python port of @deepseek-ai/hmr (hot-module reload).

Public API re-exported here for convenience. The stable contract is
defined in :mod:`hmr.invariant`; consumers should depend on that
submodule when they need a stable API surface.

1:1 alignment with `~/deepseek-harness/vendor/hmr/src/`.
"""

from __future__ import annotations

from hmr.error import HmrError
from hmr.service import (
    EVENT_CHANGE,
    EVENT_RELOAD,
    ConfigRegistration,
    Hmr,
    HmrConfig,
)

__all__ = [
    "Hmr",
    "HmrConfig",
    "ConfigRegistration",
    "HmrError",
    "EVENT_CHANGE",
    "EVENT_RELOAD",
]
