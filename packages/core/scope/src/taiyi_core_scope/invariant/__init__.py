"""taiyi_core_scope.invariant — companion subpackage exposing the public API contract.

This subpackage re-exports the public surface of :mod:`taiyi_core_scope`
so other packages in the taiyi workspace can declare a stable dependency
on the contract without coupling to the implementation layout.

1:1 with upstream `packages/core/scope/src/invariant.ts` (a barrel).
"""

from __future__ import annotations

from taiyi_core_scope.scope import (
    Scope,
    Scoped,
    ScopeKey,
    ScopeParentBinding,
    bind_scope_parent,
    carrier_key_of,
    create_scope,
    is_scope_carrier,
    scope_chain_of,
    scope_of,
    scope_parent_of,
    scope_target,
)
from taiyi_core_scope.store import (
    AnonymousEntries,
    EntryValues,
    NamedEntries,
    ScopedLayers,
    ScopeLayer,
)

__all__ = [
    # scope
    "Scope",
    "ScopeKey",
    "Scoped",
    "ScopeParentBinding",
    "bind_scope_parent",
    "scope_parent_of",
    "scope_chain_of",
    "create_scope",
    "scope_of",
    "scope_target",
    "is_scope_carrier",
    "carrier_key_of",
    # store
    "AnonymousEntries",
    "EntryValues",
    "NamedEntries",
    "ScopeLayer",
    "ScopedLayers",
]
