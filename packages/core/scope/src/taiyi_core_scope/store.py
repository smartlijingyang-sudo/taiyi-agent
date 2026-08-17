"""`taiyi_core_scope.store` — shared insertion-ordered storage for scope-aware registries.

1:1 Python port of `~/deepseek-harness/packages/core/scope/src/store.ts`.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Generic, TypeVar

from cordis import Context

from taiyi_core_scope.scope import ScopeKey, scope_chain_of, scope_of

__all__ = [
    "ScopeLayer",
    "EntryValues",
    "NamedEntries",
    "AnonymousEntries",
    "ScopedLayers",
]


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

_L = TypeVar("_L", bound="ScopeLayer")
_V = TypeVar("_V")


class ScopeLayer:
    """One scope's aggregate contribution to a registry.

    Concrete layer classes provide per-table state and report emptiness
    via :meth:`is_empty`. ``ScopedLayers`` invokes the constructor lazily
    per scope key.
    """

    def is_empty(self) -> bool:
        raise NotImplementedError


class EntryValues(Generic[_V]):
    """Internal read contract shared by both entry-table implementations."""


# ---------------------------------------------------------------------------
# NamedEntries
# ---------------------------------------------------------------------------


class NamedEntries(Generic[_V]):
    """Insertion-ordered named entries with caller-owned duplicate diagnostics."""

    __slots__ = ("_data", "_duplicate_error")

    def __init__(self, duplicate_error: Callable[[str], Exception]) -> None:
        self._data: dict[str, _V] = {}
        self._duplicate_error = duplicate_error

    def insert(self, name: str, value: _V) -> Callable[[], None]:
        """Insert one unique name. Returns an idempotent undo for that exact entry."""
        data = self._data
        if name in data:
            raise self._duplicate_error(name)
        data[name] = value
        active = True

        def _undo() -> None:
            nonlocal active
            if not active:
                return
            active = False
            data.pop(name, None)
            if not data and self._data is data:
                # Free the dict for GC if we are still the canonical one.
                self._data = {}

        return _undo

    def get(self, name: str) -> _V | None:
        return self._data.get(name)

    def has(self, name: str) -> bool:
        return name in self._data

    def keys(self) -> Iterator[str]:
        return iter(self._data)

    def entries(self) -> Iterator[tuple[str, _V]]:
        return iter(self._data.items())

    def values(self) -> Iterator[_V]:
        return iter(self._data.values())

    def is_empty(self) -> bool:
        return not self._data


# ---------------------------------------------------------------------------
# AnonymousEntries
# ---------------------------------------------------------------------------


class AnonymousEntries(Generic[_V]):
    """Insertion-ordered anonymous entries with independent registration identity."""

    __slots__ = ("_data",)

    def __init__(self) -> None:
        self._data: dict[object, _V] = {}

    def append(self, value: _V) -> Callable[[], None]:
        """Append one independently owned value. Returns an idempotent undo for that exact append."""
        # Upstream uses `Symbol()` as a unique key per registration. In Python,
        # `object()` instances are unique for the lifetime of the process.
        key = object()
        data_ref = self._data
        data_ref[key] = value
        active = True

        def _undo() -> None:
            nonlocal active
            if not active:
                return
            active = False
            data_ref.pop(key, None)
            if not data_ref and self._data is data_ref:
                self._data = {}

        return _undo

    def values(self) -> Iterator[_V]:
        return iter(self._data.values())

    def is_empty(self) -> bool:
        return not self._data


# ---------------------------------------------------------------------------
# ScopedLayers
# ---------------------------------------------------------------------------


class ScopedLayers(Generic[_L]):
    """Owns the global and exact-scope layers for one registry."""

    __slots__ = ("_global", "_scoped", "_create_layer", "_on_change")

    def __init__(
        self,
        create_layer: Callable[[ScopeKey | None], _L],
        on_change: Callable[[], None],
    ) -> None:
        self._create_layer = create_layer
        self._on_change = on_change
        self._global: _L = create_layer(None)
        # Map exact-scope key → that scope's layer. Identity-hash dict so
        # ``object()`` scope keys work; entries are reclaimed explicitly
        # when the last effect for that scope disposes.
        self._scoped: dict[ScopeKey, _L] = {}

    @property
    def global_layer(self) -> _L:
        """The eagerly constructed context-global layer."""
        return self._global

    def peek(self, scope: ScopeKey | None) -> _L | None:
        """Read an existing exact-scope overlay. Chain-blind by design."""
        if scope is None:
            return None
        return self._scoped.get(scope)

    def chain_layers(self, scope: ScopeKey | None) -> list[_L]:
        """Existing overlays along the scope's parent chain, farthest first, nearest last."""
        chain: list[_L] = []
        for key in reversed(scope_chain_of(scope)):
            layer = self._scoped.get(key)
            if layer is not None:
                chain.append(layer)
        return chain

    def merge(
        self,
        scope: ScopeKey | None,
        pick: Callable[[_L], NamedEntries[_V]],
    ) -> dict[str, _V]:
        """Materialize global entries + scope-chain shadows (nearest scope wins)."""
        merged: dict[str, _V] = dict(pick(self._global).entries())
        for layer in self.chain_layers(scope):
            for name, value in pick(layer).entries():
                merged[name] = value
        return merged

    def effect(
        self,
        ctx: Context,
        action: Callable[[_L], Callable[[], None]],
        *,
        label: str,
        notify: bool = True,
    ) -> Callable[[], None]:
        """Attach one synchronous layer mutation to its registration context.

        Returns the synchronous disposer returned by ``ctx.effect()``.
        """
        scope = scope_of(ctx)
        scoped_map = self._scoped
        global_layer = self._global
        create_layer = self._create_layer
        on_change = self._on_change

        # Determine / create the target layer.
        if scope is None:
            layer: _L = global_layer
            created = False
        else:
            existing = scoped_map.get(scope)
            if existing is None:
                layer = create_layer(scope)
                scoped_map[scope] = layer
                created = True
            else:
                layer = existing
                created = False

        try:
            undo = action(layer)
        except Exception:
            if scope is not None and created and layer.is_empty():
                scoped_map.pop(scope, None)
            raise

        def _dispose() -> None:
            undo()
            if scope is not None and layer.is_empty():
                scoped_map.pop(scope, None)
            if notify:
                on_change()

        if notify:
            on_change()
        # Register disposer on the calling context.
        ctx.effect(_dispose, label=label)
        return _dispose
