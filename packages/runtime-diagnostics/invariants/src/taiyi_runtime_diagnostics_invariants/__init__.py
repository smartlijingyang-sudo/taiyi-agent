"""taiyi-runtime-diagnostics-invariants — invariant registry and test hook.

1:1 Python port of `@deepseek-ai/dsh-invariants`. Provides a package-owned
registry that boots all registered vendor ``invariant`` companion modules
and exposes them under :data:`ctx.invariants`, plus an
:meth:`InvariantRegistry.assert_invariant` test hook for declaring that an
invariant must hold at a given point.

Public surface:

- :class:`InvariantError` — failure thrown when an invariant is violated.
- :class:`InvariantRegistry` — service holding per-vendor surfaces and checks.
- :func:`compile_patterns` — helper validating allowlist / blocklist entries.
- :func:`assert_invariant` — convenience wrapper that delegates to the active
  registry exposed by a ``cordis`` context.
- :mod:`taiyi_runtime_diagnostics_invariants.plugin` — cordis plugin entry.
"""

from __future__ import annotations

from taiyi_runtime_diagnostics_invariants.registry import (
    InvariantConfig,
    InvariantError,
    InvariantRegistry,
    assert_invariant,
    compile_patterns,
)

__version__ = "0.1.0"

__all__ = [
    # Errors
    "InvariantError",
    # Registry
    "InvariantRegistry",
    "InvariantConfig",
    # Helpers
    "compile_patterns",
    "assert_invariant",
    # Meta
    "__version__",
]
