"""`taiyi_core_scope.scope` — scoped context primitive.

1:1 Python port of `~/deepseek-harness/packages/core/scope/src/index.ts`.

Exports the public surface for scoped-dispatch:

- :class:`Scope`, :data:`ScopeKey`, :data:`Scoped`
- :func:`bind_scope_parent`, :func:`scope_parent_of`, :func:`scope_chain_of`
- :func:`create_scope`, :func:`scope_of`
- :func:`scope_target`, :func:`is_scope_carrier`, :func:`carrier_key_of`
"""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Callable
from typing import Any, Generic, TypeVar

from cordis import Context, Fiber

__all__ = [
    "Scope",
    "ScopeKey",
    "Scoped",
    "ScopeParentBinding",
    "CreateScopeOptions",
    "bind_scope_parent",
    "scope_parent_of",
    "scope_chain_of",
    "create_scope",
    "scope_of",
    "scope_target",
    "is_scope_carrier",
    "carrier_key_of",
]


# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------

# `ScopeKey` is an opaque, identity-compared object.
ScopeKey = object

# Context tag written by `create_scope`; downstream code reads it via
# `scope_of(ctx)`. Mirrors upstream's private ``kScope = Symbol('dsh.scope')``.
_SCOPE_KEY_ATTR = "__taiyi_scope_key__"

# A unique private sentinel attribute marking a value as a scope carrier.
# Mirrors upstream ``declare const ScopedBrand: unique symbol``.
_SCOPED_BRAND = "_brand"

# The Cordis attribute name used to read a context's filter callback.
# Mirrors upstream `CordisContext.filter` symbol → stringified constant.
_FILTER_ATTR = Context.filter  # "cordis.filter"

_T = TypeVar("_T")


class Scoped(Generic[_T]):
    """Routing-only event receiver built by :func:`scope_target`.

    Wraps ``base`` and overrides the Cordis filter to admit listeners that
    are tagged with the carrier's key or any of its ancestors. The subject
    itself is not exposed; event payloads carry the real value.
    """


# ---------------------------------------------------------------------------
# Module-private state
# ---------------------------------------------------------------------------

# Each carrier's routing key. Presence distinguishes an unkeyed carrier
# (`None`) from a non-carrier (key absent). Uses identity-hash dict because
# callers may mint keys as ``object()`` which is not weakly-referenceable.
_carrier_keys: dict[object, ScopeKey | None] = {}

# Each scope key's parent link. ``scopeParents`` in upstream. Identity-hash
# dict (mirrors upstream ``WeakMap`` semantics modulo GC: the entry stays
# alive as long as the caller holds a binding, which is the natural agent
# lifecycle).
_scope_parents: dict[ScopeKey, ScopeKey] = {}


# ---------------------------------------------------------------------------
# Parent linking
# ---------------------------------------------------------------------------


class ScopeParentBinding:
    """Privileged handle to re-link one scope key's parent."""

    __slots__ = ("_key",)

    def __init__(self, key: ScopeKey) -> None:
        self._key = key

    def rebind(self, parent: ScopeKey) -> None:
        """Re-link the bound key to a different parent (cycle-checked)."""
        _link_scope_parent(self._key, parent)


def _link_scope_parent(key: ScopeKey, parent: ScopeKey) -> None:
    """Cycle-checked write shared by :func:`bind_scope_parent` and :meth:`ScopeParentBinding.rebind`."""
    cursor: ScopeKey | None = parent
    while cursor is not None:
        if cursor is key:
            raise RuntimeError("dsh-scope: scope parent link would form a cycle")
        cursor = _scope_parents.get(cursor)
    _scope_parents[key] = parent


def bind_scope_parent(key: ScopeKey, parent: ScopeKey) -> ScopeParentBinding:
    """Bind ``parent`` as ``key``'s enclosing scope, once.

    Returns a :class:`ScopeParentBinding` that alone may re-link ``key``.
    Raises if ``key`` already has a parent or if the new link would cycle.
    """
    if key in _scope_parents:
        raise RuntimeError(
            "dsh-scope: scope key is already bound to a parent; re-linking "
            "requires the binding returned by the original bind"
        )
    _link_scope_parent(key, parent)
    return ScopeParentBinding(key)


def scope_parent_of(key: ScopeKey) -> ScopeKey | None:
    """Read one key's enclosing scope, or ``None`` for a root scope."""
    return _scope_parents.get(key)


def scope_chain_of(key: ScopeKey | None) -> list[ScopeKey]:
    """Walk ``key`` to its root ancestor. Returns ``[]`` for ``None``."""
    chain: list[ScopeKey] = []
    cursor: ScopeKey | None = key
    while cursor is not None:
        chain.append(cursor)
        cursor = _scope_parents.get(cursor)
    return chain


# ---------------------------------------------------------------------------
# create_scope / Scope
# ---------------------------------------------------------------------------


class CreateScopeOptions:
    """Options accepted by :func:`create_scope`."""

    __slots__ = ("parent",)

    def __init__(self, parent: ScopeKey | None = None) -> None:
        self.parent = parent


class Scope:
    """A minted registration scope and its quiescent disposal boundaries."""

    __slots__ = ("ctx", "raw_dispose", "_fiber", "_disposing")

    def __init__(
        self,
        ctx: Context,
        raw_dispose: Callable[[], Any],
        fiber: Fiber,
    ) -> None:
        self.ctx = ctx
        self.raw_dispose = raw_dispose
        self._fiber = fiber
        self._disposing: asyncio.Future[None] | None = None

    async def dispose(self) -> None:
        """Dispose every scope-owned registration; racing calls await the same completion."""
        if self._disposing is None:
            future: asyncio.Future[None] = asyncio.get_running_loop().create_future()
            self._disposing = future
            try:
                await _quiesce_fiber(self._fiber)
            except BaseException as exc:  # noqa: BLE001
                future.set_exception(exc)
                raise
            else:
                future.set_result(None)
        else:
            await self._disposing


async def _quiesce_fiber(fiber: Fiber) -> None:
    """Follow a Cordis fiber through asynchronous teardown even if its raw disposer was already claimed."""
    # ``fiber.dispose`` is the raw disposer; upstream awaits ``Promise.resolve(fiber.dispose())``.
    result = fiber.dispose()
    if inspect.isawaitable(result):
        await result
    # Then await any pending inertia.
    while True:
        inertia = getattr(fiber, "inertia", None)
        if inertia is None:
            break
        try:
            await inertia
        except Exception:
            break


# Shared no-op plugin used as the backing scope fiber (upstream `function scope() {}`).
def _scope_noop() -> None:
    """No-op plugin function; backed by Cordis to mint a child fiber."""


def create_scope(
    ctx: Context,
    key: ScopeKey,
    options: CreateScopeOptions | None = None,
) -> Scope:
    """Mint a scope under ``ctx``. Returns the scoped context and disposal boundaries."""
    if options is not None and options.parent is not None:
        bind_scope_parent(key, options.parent)
    # `ctx.registry.plugin(...)` mints a child fiber; upstream uses
    # ``ctx.plugin(scope)`` which routes through the same registry API.
    fiber = ctx.registry.plugin(_scope_noop)
    # Mirror upstream: ``fiber.ctx.extend({ [kScope]: key })``.
    scoped_ctx = fiber.ctx.extend({_SCOPE_KEY_ATTR: key})
    return Scope(scoped_ctx, fiber.dispose, fiber)


def scope_of(ctx: Context) -> ScopeKey | None:
    """Read the nearest scope tag inherited by ``ctx`` (or ``None`` for unscoped)."""
    return getattr(ctx, _SCOPE_KEY_ATTR, None)


# ---------------------------------------------------------------------------
# scope_target / carriers
# ---------------------------------------------------------------------------


class _Carrier:
    """Routing-only wrapper produced by :func:`scope_target`.

    Overrides the Cordis filter to:
    1. Run the wrapped base filter first.
    2. Admit untagged listeners (when ``ctx`` has no scope tag).
    3. Admit tagged listeners whose tag is the carrier key or any ancestor.
    """

    __slots__ = ("_base", "_key", "_base_filter", "_brand")

    def __init__(self, base: Any, key: ScopeKey | None) -> None:
        object.__setattr__(self, "_base", base)
        object.__setattr__(self, "_key", key)
        # Cache the base's filter callback, if any (read via the symbol-name attr).
        base_filter = None
        try:
            base_filter = getattr(base, _FILTER_ATTR, None)
        except Exception:  # pragma: no cover — defensive
            base_filter = None
        object.__setattr__(self, "_base_filter", base_filter)
        object.__setattr__(self, "_brand", True)

    def __getattr__(self, name: str) -> Any:
        # Delegate everything else to ``base``. The cordis filter symbol is
        # intercepted below.
        if name == _FILTER_ATTR:
            return self._make_filter()
        return getattr(self._base, name)

    def _make_filter(self) -> Callable[[Context], bool]:
        base_filter = self._base_filter
        key = self._key

        def _filter(ctx: Context) -> bool:
            if base_filter is not None:
                try:
                    if not base_filter(ctx):
                        return False
                except Exception:  # pragma: no cover — defensive
                    return False
            tag = scope_of(ctx)
            if tag is None:
                return True
            cursor: ScopeKey | None = key
            while cursor is not None:
                if cursor is tag:
                    return True
                cursor = _scope_parents.get(cursor)
            return False

        return _filter


def scope_target(base: Any, key: ScopeKey | None) -> Scoped[Any]:
    """Build an opaque carrier that preserves ``base``'s filter and routes by ``key``."""
    carrier = _Carrier(base, key)
    _carrier_keys[carrier] = key
    return carrier  # type: ignore[return-value]


def is_scope_carrier(value: object) -> bool:
    """Return True if ``value`` was produced by :func:`scope_target`."""
    if not isinstance(value, object) or value is None:
        return False
    if not getattr(value, _SCOPED_BRAND, False):
        return False
    return value in _carrier_keys


def carrier_key_of(value: object) -> ScopeKey | None:
    """Read a carrier's routing key, or ``None`` for unkeyed/non-carrier."""
    if not is_scope_carrier(value):
        return None
    return _carrier_keys.get(value)  # type: ignore[arg-type]
