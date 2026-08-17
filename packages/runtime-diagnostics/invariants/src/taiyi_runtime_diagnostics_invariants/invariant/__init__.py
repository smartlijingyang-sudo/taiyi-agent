"""taiyi_runtime_diagnostics_invariants.invariant — companion subpackage.

Mirrors upstream `packages/runtime-diagnostics/invariants/src/invariant.ts`:
re-exports the public surface so consumers can depend on a stable API
without coupling to internal layout.
"""

from __future__ import annotations

from taiyi_runtime_diagnostics_invariants.registry import (
    InvariantConfig,
    InvariantError,
    InvariantRegistry,
    assert_invariant,
    compile_patterns,
)

__all__ = [
    "InvariantError",
    "InvariantConfig",
    "InvariantRegistry",
    "assert_invariant",
    "compile_patterns",
]
