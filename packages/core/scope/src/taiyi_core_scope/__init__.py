"""taiyi-core-scope — per-agent isolation primitives.

1:1 Python port of `@deepseek-ai/dsh-scope`. Public surface:

- :class:`Scope`, :data:`ScopeKey`, :data:`Scoped`
- :func:`bind_scope_parent`, :func:`scope_parent_of`, :func:`scope_chain_of`
- :func:`create_scope`, :func:`scope_of`
- :func:`scope_target`, :func:`is_scope_carrier`, :func:`carrier_key_of`
- :class:`AnonymousEntries`, :class:`NamedEntries`, :class:`ScopedLayers`,
  :class:`ScopeLayer`
- :mod:`taiyi_core_scope.plugin` — cordis plugin entry
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

__version__ = "0.1.0"

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
    # meta
    "__version__",
]
