"""taiyi-group.invariant — companion subpackage exposing the stable contract.

This subpackage re-exports the public API contract so cross-package
importers can depend on a stable surface without coupling to
implementation layout. Mirrors the upstream TS pattern of a separate
``invariant/`` barrel directory.
"""

from __future__ import annotations

from group.service import (
    GROUP_MARKER,
    Group,
    GroupEntry,
    GroupUpdateError,
    carrier_key_of,
    is_group_carrier,
)

__all__ = [
    "Group",
    "GroupEntry",
    "GroupUpdateError",
    "GROUP_MARKER",
    "carrier_key_of",
    "is_group_carrier",
]
