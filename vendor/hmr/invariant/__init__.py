"""hmr.invariant — companion subpackage exposing the public API contract.

This subpackage re-exports the public surface of :mod:`hmr` so other
packages in the taiyi workspace can declare a stable dependency on the
contract without coupling to the implementation layout.

1:1 with upstream `vendor/hmr/src/invariant/` (which in TS is just a
re-export barrel; we mirror that pattern as a Python subpackage).
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
