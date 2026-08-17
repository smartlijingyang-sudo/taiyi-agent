"""`taiyi_core_scope.plugin` — cordis plugin entry.

Mirrors upstream `@deepseek-hai/dsh-scope`'s default export: a function
plugin that re-exports the package's surface into ``ctx.scope``.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from cordis import Context, plugin

from taiyi_core_scope.scope import (
    Scope,
    Scoped,
    ScopeKey,
    bind_scope_parent,
    carrier_key_of,
    create_scope,
    is_scope_carrier,
    scope_chain_of,
    scope_of,
    scope_parent_of,
    scope_target,
)

__all__ = [
    "Scope",
    "ScopeKey",
    "Scoped",
    "bind_scope_parent",
    "carrier_key_of",
    "create_scope",
    "is_scope_carrier",
    "scope_chain_of",
    "scope_of",
    "scope_parent_of",
    "scope_target",
]


@plugin(name="scope", inject=[])
async def setup(ctx: Context, config: Any = None) -> Callable[[], None]:
    """Cordis plugin entry for `taiyi_core_scope`.

    The package's API is consumed as ``from taiyi_core_scope import ...``.
    This plugin exists so the loader can mount the package into the bundle;
    it registers a no-op disposer that simply marks the plugin as loaded.
    """
    # Register the surface under ``ctx.scope_lib`` so consumers can opt-in
    # via ``ctx.scope_lib.create_scope(...)`` without colliding with the
    # built-in ``Context.scope(label)`` async context manager.
    surface = {
        "Scope": Scope,
        "ScopeKey": ScopeKey,
        "Scoped": Scoped,
        "bind_scope_parent": bind_scope_parent,
        "carrier_key_of": carrier_key_of,
        "create_scope": create_scope,
        "is_scope_carrier": is_scope_carrier,
        "scope_chain_of": scope_chain_of,
        "scope_of": scope_of,
        "scope_parent_of": scope_parent_of,
        "scope_target": scope_target,
    }
    return ctx.reflect.provide("scope_lib", surface)  # type: ignore[attr-defined]
