"""Tests for `taiyi_core_scope.invariant` companion subpackage.

The companion is a thin re-export barrel — make sure every public symbol
in the implementation is surfaced here so downstream consumers can depend
on it without coupling to the layout.
"""

from __future__ import annotations

from cordis import Context

from taiyi_core_scope.invariant import (
    AnonymousEntries,
    EntryValues,
    NamedEntries,
    Scope,
    ScopedLayers,
    ScopeKey,
    ScopeLayer,
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
from taiyi_core_scope.scope import (
    Scope as _Impl_Scope,
)
from taiyi_core_scope.scope import (
    ScopeKey as _Impl_Key,
)
from taiyi_core_scope.scope import (
    ScopeParentBinding as _Impl_Binding,
)
from taiyi_core_scope.scope import (
    bind_scope_parent as _impl_bind,
)
from taiyi_core_scope.scope import (
    carrier_key_of as _impl_ckey,
)
from taiyi_core_scope.scope import (
    create_scope as _impl_create,
)
from taiyi_core_scope.scope import (
    is_scope_carrier as _impl_isc,
)
from taiyi_core_scope.scope import (
    scope_chain_of as _impl_chain,
)
from taiyi_core_scope.scope import (
    scope_of as _impl_scope_of,
)
from taiyi_core_scope.scope import (
    scope_parent_of as _impl_spo,
)
from taiyi_core_scope.scope import (
    scope_target as _impl_target,
)
from taiyi_core_scope.store import (
    AnonymousEntries as _Impl_Anonymous,
)
from taiyi_core_scope.store import (
    EntryValues as _Impl_EntryValues,
)
from taiyi_core_scope.store import (
    NamedEntries as _Impl_Named,
)
from taiyi_core_scope.store import (
    ScopedLayers as _Impl_Layers,
)
from taiyi_core_scope.store import (
    ScopeLayer as _Impl_Layer,
)


def test_invariant_exports_match_implementation() -> None:
    """The barrel re-exports the same object identity as the implementation."""
    assert AnonymousEntries is _Impl_Anonymous
    assert NamedEntries is _Impl_Named
    assert Scope is _Impl_Scope
    assert ScopeKey is _Impl_Key
    assert ScopeLayer is _Impl_Layer
    assert ScopeParentBinding is _Impl_Binding
    assert ScopedLayers is _Impl_Layers
    assert EntryValues is _Impl_EntryValues
    assert bind_scope_parent is _impl_bind
    assert carrier_key_of is _impl_ckey
    assert create_scope is _impl_create
    assert is_scope_carrier is _impl_isc
    assert scope_chain_of is _impl_chain
    assert scope_of is _impl_scope_of
    assert scope_parent_of is _impl_spo
    assert scope_target is _impl_target


def test_invariant_round_trip(make_ctx: Context) -> None:
    """`bind_scope_parent` → `scope_parent_of` round-trip via the barrel."""
    a, b = object(), object()
    bind_scope_parent(b, a)
    assert scope_parent_of(b) is a
    assert scope_chain_of(b) == [b, a]
