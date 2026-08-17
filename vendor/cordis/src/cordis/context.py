"""`cordis.context` — DI container with provide/inject/isolate/fork/scope.

The `Context` is the runtime container of cordis. Subclasses and extensions add
behavior (services, events, fibers). This module defines the *base* lifecycle
operations; higher-level concerns (events, fibers) are layered on in later
modules.

Design (1:1 from upstream `context.ts`):

- A context is a node in a tree. Root contexts have no parent.
- `provide(key, value, *, dispose=None)` stores a binding locally + LIFO.
- `inject(key)` walks parent chain to find a binding (or uses default).
- `isolate(label, fn)` clones + runs `fn` in a child whose `provide` is scoped.
- `fork()` mints an empty child sharing the root.
- `scope(label)` is an async with that introduces a labeled scope.
- `dispose()` LIFO-runs every registered disposer (sync or async), exactly once.
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from typing import Any, Generic, TypeVar

from cordis.disposer import Disposer, run_disposer

_T = TypeVar("_T")

_MISSING: Any = object()
"""Sentinel for missing-key default detection."""


class Hook(Generic[_T]):
    """A registered listener record (filled in by Event service).

    Defined here so `Context.parallel/emit/...` declarations remain valid
    even before the Event module imports them.
    """

    __slots__ = ("ctx", "callback")

    def __init__(self, ctx: Context, callback: Callable[..., Any]) -> None:
        self.ctx = ctx
        self.callback = callback


# Type of a callable receive. Kept here for parity with upstream `Hook`.
def hook(func: Callable[..., Any]) -> Hook[Any]:
    """Return a `Hook` wrapping `func` (legacy helper)."""
    raise NotImplementedError("hook() is not used in this port; use ctx.on().")


# Stubs used by `ctx.parallel/emit/serial/bail/waterfall`. Real implementations
# are mixed in by the Event service in `cordis.event` once that module is loaded.
def ready(_ctx: Context) -> Awaitable[None]:
    raise NotImplementedError


def dispose(_ctx: Context) -> Awaitable[None]:
    raise NotImplementedError


# Tracks the currently-active `Context` for `scope` resolution. Threading +
# nested `scope()` work because the variable is a `ContextVar`.
_active_ctx: ContextVar[Context | None] = ContextVar("cordis_active_ctx", default=None)


class Context:
    """Dependency injection container with isolation, fork, and scope.

    Wire-format:
    - own_bindings: dict mapping key → value (only own keys; parents are walked).
    - parent: parent context (or None for root).
    - disposers: list of disposers in registration order (LIFO on dispose).
    - isolated: dict mapping label → own bindings (for `scope()`). A scope is a
      named child that releases disposers on exit.
    """

    __slots__ = (
        "parent",
        "root",
        "own_bindings",
        "disposers",
        "state_disposed",
        "isolated",
        "_isolation_label",
        "_descendants",
    )

    def __init__(
        self,
        *,
        parent: Context | None = None,
        root: Context | None = None,
        isolation_label: str | None = None,
    ) -> None:
        self.parent = parent
        self.root: Context = root if root is not None else self
        self.own_bindings: dict[str, Any] = {}
        self.disposers: list[Disposer] = []
        self.isolated: dict[str, Context] = {}
        self.state_disposed: bool = False
        self._isolation_label = isolation_label
        self._descendants: list[Context] = []
        if parent is not None:
            parent._descendants.append(self)

    # -- bindings -----------------------------------------------------------

    def provide(
        self,
        key: str,
        value: Any,
        *,
        dispose: Callable[[], Any] | None = None,
    ) -> None:
        """Register `key → value` on this context; optionally register a disposer."""
        if self.state_disposed:
            raise RuntimeError("cannot provide on a disposed context")
        self.own_bindings[key] = value
        if dispose is not None:
            self.disposers.append(Disposer(dispose, label=f"provide:{key}"))

    def inject(self, key: str, *, default: Any = _MISSING) -> Any:
        """Resolve `key`; walk the parent chain; raise `KeyError` if missing.

        Honors the active `scope()`: a value provided inside a scope or its
        forks is read before the context's own bindings or its ancestors'.
        """
        if not self.state_disposed:
            active = _active_ctx.get()
            if active is not None:
                # If `self` is the active ctx, walk self+descendants first.
                if active is self:
                    val = self._walk_local(self, key)
                    if val is not _MISSING:
                        return val
                # Or if self is an ancestor of active, walk active+descendants.
                elif self._is_ancestor_of(active):
                    val = active._local_lookup(key)
                    if val is not _MISSING:
                        return val

        return self._inject_chain(key, default)

    def _local_lookup(self, key: str) -> Any:
        """Lookup restricted to the active context's tree (self + descendants).

        Returns the value if found in the active context (or any descendant),
        else `_MISSING`. Independent of the parent chain.
        """
        active = _active_ctx.get()
        if active is None:
            return _MISSING
        # Walk the active's `own_bindings` and any descendants created via `fork()`.
        return self._walk_local(active, key)

    def _walk_local(self, node: Context, key: str) -> Any:
        if key in node.own_bindings:
            return node.own_bindings[key]
        # Walk descendants of the active ctx that share its root (forks within the scope).
        for descendant in node._descendants:
            val = self._walk_local(descendant, key)
            if val is not _MISSING:
                return val
        return _MISSING

    def _inject_chain(self, key: str, default: Any) -> Any:
        """Walk the parent chain looking for `key`."""
        node: Context | None = self
        while node is not None:
            if key in node.own_bindings:
                return node.own_bindings[key]
            node = node.parent
        if default is _MISSING:
            raise KeyError(key)
        return default

    def _is_ancestor_of(self, other: Context) -> bool:
        node: Context | None = other.parent
        while node is not None:
            if node is self:
                return True
            node = node.parent
        return False

    def _is_scope_descendant(self, root: Context, target: Context) -> bool:
        """True if `target` is the same as `root` or a child created within it."""
        node: Context | None = target
        while node is not None:
            if node is root:
                return True
            node = node.parent
        return False

    # -- derived contexts ---------------------------------------------------

    def fork(self) -> Context:
        """Return a new child context; bindings are inherited (read-only)."""
        return Context(parent=self, root=self.root)

    def isolate(
        self,
        label: str,
        callback: Callable[[Context], Any],
    ) -> Any:
        """Run `callback` in a fresh isolated child; supports sync or async callbacks.

        Sync callbacks return their result directly. Async (coroutine) callbacks
        return a coroutine whose completion runs the callback; awaiting the
        coroutine leaves the scope on exit.
        """
        scoped = Context(parent=self, root=self.root, isolation_label=label)
        # Track the scope under its label so nested lookups can find it.
        self.isolated[label] = scoped

        if inspect.iscoroutinefunction(callback):
            async def _runner() -> Any:
                token = _active_ctx.set(scoped)
                try:
                    return await callback(scoped)
                finally:
                    _active_ctx.reset(token)

            return _runner()

        token = _active_ctx.set(scoped)
        try:
            return callback(scoped)
        finally:
            _active_ctx.reset(token)

    def scope(self, label: str) -> _ScopeCM:
        """Async context manager introducing a labeled scope.

        Within the `async with` block, `inject()` on this context sees values
        provided on the scope first. Disposers added inside the scope are run
        on exit.
        """
        return _ScopeCM(self, label)

    # -- lifecycle ----------------------------------------------------------

    async def dispose(self) -> None:
        """Run all registered disposers in reverse-registration order; idempotent."""
        if self.state_disposed:
            return
        self.state_disposed = True
        # Snapshot to allow disposers to safely provide new entries.
        disposers = self.disposers
        self.disposers = []
        for disp in reversed(disposers):
            await run_disposer(disp)


class _ScopeCM:
    """Async context manager implementing `Context.scope()`.

    Enters by activating the scoped child + registering a disposer for any
    new bindings added during the block; exits by deactivating + running
    those disposers.
    """

    __slots__ = ("_parent", "_label", "_scoped", "_token", "_new_disposer_start")

    def __init__(self, parent: Context, label: str) -> None:
        self._parent = parent
        self._label = label
        # Reuse the existing scope child if already created.
        self._scoped = parent.isolated.get(label) or Context(
            parent=parent, root=parent.root, isolation_label=label
        )
        parent.isolated.setdefault(label, self._scoped)
        self._token: Any = None
        self._new_disposer_start = 0

    @property
    def scoped(self) -> Context:
        return self._scoped

    async def __aenter__(self) -> Context:
        self._token = _active_ctx.set(self._scoped)
        self._new_disposer_start = len(self._scoped.disposers)
        return self._scoped

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        try:
            # Run any disposers registered *inside* the scope, in reverse order.
            new_disposers = self._scoped.disposers[self._new_disposer_start :]
            for disp in reversed(new_disposers):
                await run_disposer(disp)
        finally:
            if self._token is not None:
                _active_ctx.reset(self._token)


__all__ = [
    "Context",
    "Hook",
    "hook",
    "ready",
    "dispose",
]
