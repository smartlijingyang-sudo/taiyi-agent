"""`cordis.fiber` — Plugin fiber (lifecycle, DI, effects).

Faithful 1:1 port of `~/deepseek-harness/vendor/cordis/src/fiber.ts`.

This module is populated incrementally by Tasks 1.6 (full state machine +
DI) and onward. The current version provides the surface that other
modules (events, reflect) need:

- :class:`FiberState` — PENDING / LOADING / ACTIVE / FAILED / UNLOADING /
  DISPOSED.
- :class:`CordisError` — framework error with stable ``code`` attribute.
- :class:`Fiber` — minimal version with ``effect()`` and ``assert_active()``.

Task 1.6 will expand this module to the full state machine + DI system.
"""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from cordis.utils import DisposableList, EffectMeta, build_outer_stack, compose_error

if TYPE_CHECKING:  # pragma: no cover — import-only for typing
    from cordis.context import Context

__all__ = [
    "Fiber",
    "FiberState",
    "CordisError",
    "ValidationError",
    "resolve_config",
    "INACTIVE",
]


# ---------------------------------------------------------------------------
# Fiber state enum
# ---------------------------------------------------------------------------


class FiberState:
    """Lifecycle states for one plugin fiber (mirrors upstream TS enum)."""

    PENDING = 0
    LOADING = 1
    ACTIVE = 2
    FAILED = 3
    UNLOADING = 4
    DISPOSED = 5

    _NAMES: dict[int, str] = {
        0: "PENDING",
        1: "LOADING",
        2: "ACTIVE",
        3: "FAILED",
        4: "UNLOADING",
        5: "DISPOSED",
    }

    @classmethod
    def name(cls, value: int) -> str:
        """Return the human-readable name of a state code."""
        return cls._NAMES.get(value, "UNKNOWN")


INACTIVE: str = "__INACTIVE__"
"""Sentinel for an inactive dependency epoch (mirrors upstream ``INACTIVE``)."""


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class CordisError(Exception):
    """Stable, machine-readable framework error."""

    def __init__(self, code: str, message: str | None = None) -> None:
        self.code = code
        super().__init__(message or code)


# ---------------------------------------------------------------------------
# Config validation
# ---------------------------------------------------------------------------


class ValidationError(TypeError):
    """Raised when a plugin's config fails standard-schema validation."""

    def __init__(self, issues: list[dict[str, Any]]) -> None:
        msg_lines = ["invalid config:"]
        for issue in issues:
            path = ".".join(str(p) for p in issue.get("path", []))
            text = issue.get("message", "")
            if path:
                msg_lines.append(f"  - {text} (at {path})")
            else:
                msg_lines.append(f"  - {text}")
        super().__init__("\n".join(msg_lines))


def resolve_config(runtime: Any, config: Any) -> Any:
    """Run ``runtime.Config['~standard'].validate(config)`` if available.

    In Python we tolerate both Pydantic models (``model_validate`` /
    ``parse_obj``) and plain callables, falling back to the raw config
    when no schema is registered.
    """
    schema = getattr(runtime, "Config", None)
    if schema is None:
        return config
    # Pydantic v2.
    try:
        return schema.model_validate(config)
    except AttributeError:
        pass
    # Pydantic v1.
    try:
        return schema.parse_obj(config)
    except AttributeError:
        pass
    # Callable / transform.
    try:
        return schema(config)
    except Exception:
        return config


# ---------------------------------------------------------------------------
# Fiber (minimal — Task 1.6 will expand this)
# ---------------------------------------------------------------------------


@dataclass
class _Runner:
    """Per-effect runner state (epoch + execute + collect)."""

    epoch: Any
    execute: Callable[["Fiber"], Any]
    collect: Callable[["Fiber", Callable[[], Any]], None]
    get_outer_stack: Callable[[], list[str]] = field(default_factory=lambda: lambda: [])


class Fiber:
    """Runtime instance of one plugin application.

    The current version is a minimal scaffold focused on what other
    services (events, reflect, registry) need to register and dispose
    effects. Task 1.6 expands this to the full upstream state machine.
    """

    def __init__(  # noqa: PLR0915
        self,
        parent: "Context",
        config: Any,
        inject: dict[str, Any],
        runtime: Any | None,
        get_outer_stack: Callable[[], list[str]] | None = None,
    ) -> None:
        self.parent: "Context" = parent
        self.uid: int | None = None
        self.ctx: "Context"
        self.config: Any = config
        self._config: Any = config
        self.inject: dict[str, Any] = inject
        self.runtime: Any | None = runtime
        self.state: int = FiberState.PENDING
        self.store: dict[str, Any] | None = None
        self.inertia: asyncio.Task[None] | None = None

        self._hooks: dict[str, DisposableList] = {}
        self._disposables: DisposableList = DisposableList()

        self._error: Any = None
        self._store: dict[str, Any] = {}
        self._runner: _Runner = _Runner(
            epoch=INACTIVE,
            execute=lambda f: None,
            collect=lambda f, d: None,
            get_outer_stack=get_outer_stack or build_outer_stack(0),
        )

        if runtime is not None:
            # Plugin fiber.
            try:
                self.uid = parent.registry.counter  # type: ignore[attr-defined]
            except Exception:
                self.uid = 1
            # Extend the parent context with this fiber.
            try:
                self.ctx = parent.extend({"fiber": self})  # type: ignore[arg-defined]
            except Exception:
                self.ctx = parent
            self._runner = _Runner(
                epoch=INACTIVE,
                execute=lambda f: runtime.callback(f.ctx, f.config)
                if not _is_constructor(runtime.callback)
                else None,
                collect=self._collect_disposable,
                get_outer_stack=self._runner.get_outer_stack,
            )
            self._parent_dispose = lambda: None
        else:
            # Root fiber.
            self.uid = 0
            self.ctx = parent
            self.state = FiberState.ACTIVE
            self.store = {}
            self._runner = _Runner(
                epoch="",
                execute=lambda f: None,
                collect=self._collect_disposable,
                get_outer_stack=self._runner.get_outer_stack,
            )
            self._parent_dispose = lambda: None

        # Mirror upstream ``getTraceable`` lookup helpers — the
        # ``context`` attribute alias used in upstream ``Fiber``.
        self._ctx = self.ctx

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _collect_disposable(
        self, _fiber: "Fiber", dispose: Callable[[], Any]
    ) -> None:
        self._disposables.push(dispose)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        """Walk ancestors for the first runtime with a name."""
        fiber: Fiber = self
        while True:
            name = getattr(fiber.runtime, "name", None) if fiber.runtime else None
            if name:
                return name
            try:
                parent_fiber = fiber.parent.fiber  # type: ignore[attr-defined]
            except Exception:
                return "root"
            if parent_fiber is fiber:
                return "root"
            fiber = parent_fiber

    def assert_active(self) -> None:
        """Raise ``CordisError(INACTIVE_EFFECT)`` if the fiber is disposed."""
        if self.uid is None:
            raise CordisError(
                "INACTIVE_EFFECT",
                "cannot create effect on inactive context",
            )

    def effect(  # noqa: PLR0915 — parity-required complexity
        self,
        execute: Callable[[], Any],
        label: str = "anonymous",
    ) -> Any:
        """Register a cleanup-aware effect on this fiber.

        Mirrors upstream ``Fiber.effect``: ``execute`` runs immediately;
        disposers it produces are run in reverse order either when the
        returned wrapper is called or when the fiber unloads.
        """
        self.assert_active()
        if self.state == FiberState.UNLOADING:
            raise CordisError("INACTIVE_EFFECT")

        disposables: list[Callable[[], Any]] = []
        dispose_called = False
        disposal_task: Any = None

        meta = EffectMeta(label=label, children=[])

        def _do_dispose() -> Any:
            nonlocal dispose_called, disposal_task
            if dispose_called:
                return disposal_task
            dispose_called = True
            chain: Any = None
            for disp in reversed(disposables):
                try:
                    result = disp()
                except Exception:  # pragma: no cover — defensive
                    continue
                if chain is None:
                    if inspect.isawaitable(result):
                        chain = result
                else:
                    prev = chain

                    async def _chain(_p: Any, _d: Callable[[], Any]) -> None:
                        await _p
                        v = _d()
                        if inspect.isawaitable(v):
                            await v

                    chain = _chain(prev, disp)
            disposal_task = chain
            return chain

        runner = _Runner(
            epoch=True,
            execute=execute,
            collect=lambda f, d: disposables.append(d),
            get_outer_stack=build_outer_stack(0),
        )

        wrapper: Any = lambda: _do_dispose()
        setattr(wrapper, "cordis.effect", meta)

        # Register wrapper into master disposables BEFORE execute.
        wrapper_remove = self._disposables.push(wrapper)
        # Prevent unused-variable warning in static analysis.
        del wrapper_remove

        try:
            self._execute_runner(runner)
        except Exception as exc:
            try:
                _do_dispose()
            except Exception:  # pragma: no cover
                pass
            raise

        # Add awaitable shape.
        async def _then(
            on_fulfilled: Callable[[Any], Any] | None = None,
            on_rejected: Callable[[Any], Any] | None = None,
        ) -> Any:
            try:
                result = _do_dispose()
                if inspect.isawaitable(result):
                    await result
            except Exception as exc:
                if on_rejected is not None:
                    return on_rejected(exc)
                raise
            if on_fulfilled is not None:
                return on_fulfilled(None)
            return None

        wrapper.then = _then
        return wrapper

    # ------------------------------------------------------------------
    # Internal: _execute + helpers
    # ------------------------------------------------------------------

    def _execute_runner(self, runner: _Runner) -> Any:
        compose_error(
            lambda _info: _run_effect_body(self, runner),
            runner.get_outer_stack,
        )

    # ------------------------------------------------------------------
    # Public awaitable methods
    # ------------------------------------------------------------------

    async def await_(self) -> "Fiber":
        """Wait for inertia; rethrow any startup error."""
        while self.inertia is not None:
            try:
                await self.inertia
            except Exception:
                break
        if self._error is not None:
            raise self._error
        return self

    async def restart(self) -> None:
        """Unload and re-setup; rethrow configuration/startup errors."""
        self.assert_active()
        if self.inertia is None:
            self.inertia = asyncio.ensure_future(self._noop_unload())
        await self.await_()

    async def _noop_unload(self) -> None:
        """Minimal unload: clear disposables, reset state."""
        try:
            disposables = self._disposables.clear()
            for disp in disposables:
                try:
                    result = disp()
                    if inspect.isawaitable(result):
                        await result
                except Exception:  # pragma: no cover — best-effort
                    pass
        finally:
            self.inertia = None


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _is_constructor(func: Any) -> bool:
    """Local variant of ``is_constructor`` avoiding an import cycle risk."""
    import inspect

    try:
        return inspect.isclass(func)
    except Exception:  # pragma: no cover
        return False


def _run_effect_body(fiber: Fiber, runner: _Runner) -> Any:
    """Drive the upstream ``_execute`` body for one effect runner."""
    result = runner.execute(fiber)
    if callable(result):
        # Single disposer.
        runner.collect(fiber, result)
        return None
    if result is None:
        return None

    # Iterator (sync).
    if hasattr(result, "__iter__") and not isinstance(result, (str, bytes)):
        it = iter(result)
        while True:
            try:
                v = next(it)
            except StopIteration:
                break
            runner.collect(fiber, v)
        return None

    # Awaitable.
    if inspect.isawaitable(result):
        async def _then() -> None:
            v = await result
            if callable(v):
                runner.collect(fiber, v)
            elif v is not None:
                raise TypeError("Invalid effect")

        return _then()

    # Async iterator.
    if hasattr(result, "__aiter__"):
        async def _aiter() -> None:
            it = result.__aiter__()
            while True:
                v = await it.__anext__()
                runner.collect(fiber, v)

        return _aiter()

    raise TypeError("Invalid effect")
