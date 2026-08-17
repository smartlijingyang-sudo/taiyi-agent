"""`cordis.reflect` — Service resolution, accessors, mixins.

Faithful 1:1 port of `~/deepseek-harness/vendor/cordis/src/reflect.ts`.

Task 1.5 ships a minimal :class:`ReflectService` exposing
:meth:`ReflectService.bind`, :meth:`ReflectService.get`, and
:meth:`ReflectService.set`. Task 1.7 expands the module to the full
``ReflectService.handler`` Proxy implementation + ``accessor()``,
``mixin()``, and ``notify()``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from cordis.utils import Tracker, join_prototype

if TYPE_CHECKING:  # pragma: no cover — import-only for typing
    from cordis.context import Context

__all__ = [
    "Impl",
    "Property",
    "ReflectService",
]


# ---------------------------------------------------------------------------
# Impl + Property records
# ---------------------------------------------------------------------------


@dataclass
class Impl:
    """Service implementation record stored in the root reflect service."""

    name: str
    fiber: Any  # "Fiber"
    value: Any = None
    check: Callable[[], bool] | None = None


@dataclass
class Property:
    """Declared context property (service or accessor)."""

    type: str  # "service" | "accessor"
    # Service-only: no extra fields. Accessor-only:
    get: Callable[["Context", Any, Exception], Any] | None = None
    set: Callable[["Context", Any, Any, Exception], bool] | None = None


# ---------------------------------------------------------------------------
# ReflectService (minimal scaffold for Task 1.5)
# ---------------------------------------------------------------------------


class ReflectService:
    """Service-resolution layer installed as ``ctx.reflect``.

    The current version provides the basics needed by :class:`EventsService`
    and the rest of the framework. Task 1.7 expands this to the full Proxy
    handler + ``accessor()``, ``mixin()``, and ``notify()``.
    """

    handler: type[Any] = type("Handler", (), {})
    """Placeholder for the upstream ``ReflectService.handler`` Proxy.

    Task 1.7 binds this to a real handler class so attribute access on
    ``ctx`` resolves through registered services. For now we keep an empty
    sentinel so the public attribute exists.
    """

    def __init__(self, ctx: "Context") -> None:
        self.ctx: "Context" = ctx
        self.store: dict[Any, Impl] = {}
        self.props: dict[str, Property] = {}

        self._tracker = Tracker(property="ctx", no_shadow=True)
        # Mirror upstream: stash tracker under the symbol key on the instance.
        try:
            self.__dict__["cordis.tracker"] = self._tracker
        except Exception:  # pragma: no cover — defensive
            pass

    # ------------------------------------------------------------------
    # Service registration
    # ------------------------------------------------------------------

    def get(self, name: str, strict: bool = True) -> Any:
        """Look up a service by name and return its value, if any.

        Mirrors upstream ``ReflectService.get``:

        - ``strict=True`` returns only impls whose fiber is ACTIVE.
        - ``strict=False`` returns impls of any state.
        """
        impl = self._get_impl(name, strict)
        if not impl:
            return None
        return impl.value

    def _get_impl(self, name: str, strict: bool = True) -> Impl | None:
        """Internal lookup walking isolation scope."""
        try:
            isolate = self.ctx.get(symbols.isolate)  # type: ignore[attr-defined]
        except Exception:
            isolate = None
        if not isinstance(isolate, dict):
            return None
        key = isolate.get(name)
        if key is None:
            return None
        impl = self.store.get(key)
        if not impl:
            return None
        if strict:
            state = getattr(impl.fiber, "state", None)
            if state is None or state != 2:  # ACTIVE
                return None
        return impl

    def set(self, name: str, value: Any, error: Exception | None = None) -> bool:
        """Overwrite a service's value (upstream semantics).

        Raises ``RuntimeError`` if the service is not provided or is owned
        by another fiber.
        """
        try:
            isolate = self.ctx.get(symbols.isolate)  # type: ignore[attr-defined]
        except Exception:
            isolate = None
        if not isinstance(isolate, dict):
            raise RuntimeError(f'cannot set property "{name}" without provide')
        key = isolate.get(name)
        impl = self.store.get(key) if key is not None else None
        if impl is None:
            raise RuntimeError(f'cannot set property "{name}" without provide')
        if impl.fiber is not self.ctx.fiber:  # type: ignore[attr-defined]
            raise RuntimeError(f'cannot set property "{name}" in multiple fibers')
        impl.value = value
        return True

    def provide(
        self,
        name: str,
        value: Any = None,
        check: Callable[[], bool] | None = None,
    ) -> Callable[[], Any]:
        """Register a service implementation owned by the current fiber.

        Returns a disposer that unregisters the service.
        """
        # Initialize isolation scope on the root context if missing.
        root = self.ctx.root  # type: ignore[attr-defined]
        root_isolate = root[symbols.isolate]  # type: ignore[name-defined]
        if name not in root_isolate:
            # Use a stable string key for the isolation scope symbol.
            key: Any = f"__scope__:{name}"
            root_isolate[name] = key

        ctx_isolate = self.ctx[symbols.isolate]  # type: ignore[name-defined]
        key = ctx_isolate.setdefault(name, root_isolate[name])

        from cordis.fiber import FiberState

        fiber = self.ctx.fiber  # type: ignore[attr-defined]
        impl = Impl(name=name, fiber=fiber, value=value, check=check)
        existing = self.store.get(key)  # type: ignore[arg-type]
        if existing is not None:
            raise RuntimeError(
                f'service "{name}" has been registered at <{existing.fiber.name}>'
            )
        self.store[key] = impl  # type: ignore[index]
        if fiber.state == FiberState.ACTIVE:  # type: ignore[attr-defined]
            try:
                self.notify([name])
            except Exception:  # pragma: no cover — defensive
                pass

        async def _dispose() -> None:
            try:
                if key in self.store:
                    del self.store[key]  # type: ignore[index]
            except Exception:  # pragma: no cover
                pass
            try:
                self.notify([name])
            except Exception:  # pragma: no cover — defensive
                pass
            try:
                if fiber.store is not None:
                    fiber.store.pop(name, None)
            except Exception:  # pragma: no cover
                pass

        # Register as an effect on the current fiber so cleanup is automatic.
        try:
            self.ctx.fiber.effect(_make_effect(_dispose), f'ctx.provide("{name}")')  # type: ignore[attr-defined]
        except Exception:  # pragma: no cover — fiberless context
            pass
        return _dispose

    # ------------------------------------------------------------------
    # Notify / accessor / mixin (stubs expanded in Task 1.7)
    # ------------------------------------------------------------------

    def notify(self, names: list[str]) -> list[Any]:
        """Re-evaluate fibers requiring any of ``names`` (Task 1.7 expands)."""
        fibers = []
        try:
            registry = self.ctx.registry  # type: ignore[attr-defined]
            for runtime in registry.values():
                for fiber in runtime.fibers:
                    fiber._check_impl(name)  # noqa: SLF001
                    fiber._refresh()  # noqa: SLF001
                    fibers.append(fiber)
        except Exception:  # pragma: no cover — defensive
            pass
        return fibers

    def accessor(self, name: str, options: dict[str, Any]) -> Callable[[], Any]:
        """Declare a computed property (stub; full impl in Task 1.7)."""
        # For now, record it.
        self.props[name] = Property(type="accessor", get=options.get("get"))
        return lambda: None

    def mixin(
        self, source: Any, mixins: list[str] | dict[str, str]
    ) -> Callable[[], Any]:
        """Expose service members directly on the context (stub)."""
        return lambda: None

    # ------------------------------------------------------------------
    # Value tracing
    # ------------------------------------------------------------------

    def trace(self, value: Any) -> Any:
        """Pass-through wrapper (upstream's ``getTraceable`` semantics)."""
        return value

    def bind(self, callback: Callable[..., Any]) -> Callable[..., Any]:
        """Bind a callback to this context.

        Mirrors upstream ``ReflectService.bind``: returns a Proxy that
        forwards the callback while routing method invocations through
        this service's trace layer. In Python we treat the callback as
        already-bound (``self.__self__`` is the active context); the
        dispatch layer handles free functions by prepending ``this_arg``.

        For now we return the callback unchanged. Plugin authors that
        want richer tracing can override this method on a derived
        service; the rest of the framework treats the result as opaque.
        """
        return callback


def _make_effect(coro_factory: Callable[[], Any]) -> Callable[[], Any]:
    """Build a one-shot effect that calls ``coro_factory`` once."""

    def _effect() -> Any:
        result = coro_factory()
        return result

    return _effect


# Imports resolved late for forward declarations.
try:
    from cordis.utils import symbols as _symbols
except Exception:  # pragma: no cover
    _symbols = None
symbols = _symbols
