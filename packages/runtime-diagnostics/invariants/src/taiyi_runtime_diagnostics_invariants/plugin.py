"""`taiyi_runtime_diagnostics_invariants.plugin` — cordis plugin entry.

1:1 Python port of `@deepseek-ai/dsh-invariants`'s default export.

Boot-time plugin that:

1. Registers an :class:`InvariantRegistry` service under ``ctx.invariants``.
2. Walks the canonical vendor ``invariant`` companion modules and registers
   each as a package-owned surface (subject to the configured allow/block
   filters).
3. Returns a single disposer that releases every vendor registration plus
   the service binding.
"""

from __future__ import annotations

import importlib
from collections.abc import Callable
from typing import Any

from cordis import Context, plugin

from taiyi_runtime_diagnostics_invariants.registry import (
    InvariantRegistry,
    compile_patterns,
)

__all__ = [
    "setup",
    "PACKAGE_NAME",
    "VENDOR_INVARIANT_MODULES",
    "list_installed_vendors",
]


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


PACKAGE_NAME: str = "@deepseek-ai/dsh-invariants"
"""Full npm package name owning this runtime diagnostic (1:1 with upstream)."""


VENDOR_INVARIANT_MODULES: tuple[str, ...] = (
    # Vendor packages (alphabetical)
    "cordis.invariant",
    "group.invariant",
    "hmr.invariant",
    "include.invariant",
    "loader.invariant",
    "logger_console.invariant",
    "schemastery.invariant",
    "taiyi_core_scope.invariant",
    "taiyi_core_session.invariant",
    "timer.invariant",
)
"""Dotted module paths of every companion barrel the boot plugin enumerates."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def list_installed_vendors() -> list[str]:
    """Return the subset of :data:`VENDOR_INVARIANT_MODULES` that import.

    Vendors whose companion module is not installed in the current
    environment are silently skipped (no fail-fast on missing optional
    surfaces).
    """
    installed: list[str] = []
    for module_path in VENDOR_INVARIANT_MODULES:
        try:
            importlib.import_module(module_path)
        except ImportError:
            continue
        installed.append(module_path)
    return installed


def _short_name(module_path: str) -> str:
    """Reduce ``a.b.c.invariant`` to ``c`` (the vendor's canonical name)."""
    parts = module_path.split(".")
    if parts[-1] == "invariant":
        return parts[-2]
    return parts[-1]


# ---------------------------------------------------------------------------
# Plugin
# ---------------------------------------------------------------------------


@plugin(name="runtime-diagnostics-invariants", inject=[])
async def setup(ctx: Context, config: Any = None) -> Callable[[], None]:
    """Install the invariant registry and load every vendor companion barrel.

    Returns a disposer that removes every vendor registration plus the
    ``ctx.invariants`` service binding.
    """
    cfg: dict[str, Any] = dict(config) if isinstance(config, dict) else {}
    registry = InvariantRegistry(ctx, **cfg)

    # Provide the service under ``ctx.invariants``. The disposer from
    # ``reflect.provide`` releases the binding when the plugin disposes.
    service_dispose = ctx.reflect.provide("invariants", registry)  # type: ignore[attr-defined]

    # Validate patterns eagerly so misconfiguration fails on boot, not on
    # first use.
    compile_patterns("package_allowlist", cfg.get("package_allowlist", []))
    compile_patterns("package_blocklist", cfg.get("package_blocklist", []))

    vendor_disposes: list[Callable[[], None]] = []
    loaded: list[str] = []
    skipped_filter: list[str] = []
    for module_path in list_installed_vendors():
        package_name = _short_name(module_path)
        if not registry.selected(package_name):
            skipped_filter.append(package_name)
            continue
        try:
            module = importlib.import_module(module_path)
        except ImportError:  # pragma: no cover — `list_installed_vendors` already guarded
            continue
        vendor_disposes.append(registry.register(package_name, module))
        loaded.append(package_name)

    # Record the boot outcome on the registry for diagnostics.
    registry._loaded = tuple(loaded)  # type: ignore[attr-defined]
    registry._skipped_filter = tuple(skipped_filter)  # type: ignore[attr-defined]

    def _dispose_all() -> None:
        # Release vendor registrations first, then the service binding.
        for dispose in reversed(vendor_disposes):
            try:
                dispose()
            except Exception:  # pragma: no cover — defensive
                pass
        try:
            service_dispose()
        except Exception:  # pragma: no cover — defensive
            pass

    return _dispose_all
