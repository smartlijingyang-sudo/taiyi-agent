"""`cordis.registry` — Plugin registry and dependency injection helpers.

Faithful 1:1 port of `~/deepseek-harness/vendor/cordis/src/registry.ts`.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Generic, TypeVar

from cordis.utils import DisposableList, Tracker, build_outer_stack, join_prototype

if TYPE_CHECKING:  # pragma: no cover — import-only for typing
    from cordis.context import Context
    from cordis.fiber import Fiber

__all__ = [
    "Plugin",
    "Inject",
    "InjectKey",
    "Inject_resolve",
    "RegistryService",
    "PluginRuntime",
]


_T = TypeVar("_T")


# ---------------------------------------------------------------------------
# Inject type aliases
# ---------------------------------------------------------------------------


# A simple alias — Python's type system is simpler than TypeScript's.
Inject = list[str] | dict[str, Any]


@dataclass
class PluginRuntime:
    """Mutable registry record shared by all fibers of one plugin callback."""

    name: str | None = None
    callback: Callable[..., Any] = field(default=lambda: lambda *a, **k: None)
    Config: Any = None
    fibers: DisposableList = field(default_factory=DisposableList)


# ---------------------------------------------------------------------------
# isApplicable + Inject.resolve
# ---------------------------------------------------------------------------


def _is_applicable(plugin: Any) -> bool:
    """Return True if ``plugin`` is an object with an ``apply`` method."""
    return bool(plugin) and isinstance(plugin, dict) and callable(plugin.get("apply"))


def Inject_resolve(
    inject: Inject | None, result: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Normalize plugin dependency declarations into a plain dict."""
    if result is None:
        result = {}
    if inject is None:
        return result
    if isinstance(inject, list):
        for name in inject:
            result[name] = None
    else:
        for name, value in inject.items():
            result[name] = value if value is not None else None
    return result


# ---------------------------------------------------------------------------
# RegistryService
# ---------------------------------------------------------------------------


class RegistryService:
    """Plugin registry installed as ``ctx.registry``."""

    def __init__(self, ctx: "Context") -> None:
        self.ctx: "Context" = ctx
        self._counter: int = 0
        self._internal: dict[Callable[..., Any], PluginRuntime] = {}

        self._tracker = Tracker(property="ctx", no_shadow=True)
        try:
            self.__dict__["cordis.tracker"] = self._tracker
        except Exception:  # pragma: no cover — defensive
            pass

    @property
    def counter(self) -> int:
        """Increment-and-return the next fiber uid."""
        self._counter += 1
        return self._counter

    @property
    def size(self) -> int:
        """Number of registered plugin runtimes."""
        return len(self._internal)

    # ------------------------------------------------------------------
    # Lookup helpers
    # ------------------------------------------------------------------

    def resolve(self, plugin: Any) -> Callable[..., Any] | None:
        """Resolve a supported plugin shape to its executable callback."""
        try:
            if callable(plugin):
                return plugin
            if _is_applicable(plugin):
                return plugin["apply"]
        except Exception:
            pass
        return None

    def get(self, plugin: Any) -> PluginRuntime | None:
        """Look up the runtime record for a plugin."""
        key = self.resolve(plugin)
        if not key:
            return None
        return self._internal.get(key)

    def has(self, plugin: Any) -> bool:
        """True when at least one fiber of the plugin is registered."""
        key = self.resolve(plugin)
        return bool(key) and key in self._internal

    def delete(self, plugin: Any) -> PluginRuntime | None:
        """Dispose every running fiber and remove the runtime record."""
        key = self.resolve(plugin)
        if not key:
            return None
        runtime = self._internal.pop(key, None)
        if runtime is None:
            return None
        for fiber in list(runtime.fibers):
            try:
                result = fiber.dispose()
                # ``dispose`` may be async — surface it for the caller.
                if result is not None:
                    # Best-effort; can't await in a sync method.
                    pass
            except Exception:  # pragma: no cover
                pass
        return runtime

    # ------------------------------------------------------------------
    # Iteration
    # ------------------------------------------------------------------

    def keys(self):
        return self._internal.keys()

    def values(self):
        return self._internal.values()

    def entries(self):
        return self._internal.entries()

    def forEach(
        self, callback: Callable[[PluginRuntime, Callable[..., Any]], None]
    ) -> None:
        for key, value in self._internal.items():
            callback(value, key)

    # ------------------------------------------------------------------
    # Plugin loading
    # ------------------------------------------------------------------

    def plugin(
        self,
        plugin: Any,
        config: Any = None,
        get_outer_stack: Callable[[], list[str]] | None = None,
    ) -> "Fiber":
        """Start a plugin in the current context and return its fiber."""
        from cordis.fiber import Fiber

        callback = self.resolve(plugin)
        if not callback:
            raise TypeError(
                "invalid plugin, expect function or object with an \"apply\" method, "
                f"received {type(plugin).__name__}"
            )

        try:
            self.ctx.fiber.assert_active()  # type: ignore[attr-defined]
        except Exception:
            pass

        runtime = self._internal.get(callback)
        if runtime is None:
            name = getattr(plugin, "name", None)
            if name == "apply":
                name = None
            runtime_config = getattr(plugin, "Config", None)
            if runtime_config is None and isinstance(plugin, dict):
                runtime_config = plugin.get("Config")
            runtime = PluginRuntime(
                name=name,
                callback=callback,
                Config=runtime_config,
            )
            self._internal[callback] = runtime

        inject_value = getattr(plugin, "inject", None)
        if inject_value is None and isinstance(plugin, dict):
            inject_value = plugin.get("inject")
        inject = Inject_resolve(inject_value)
        outer = get_outer_stack or build_outer_stack(0)
        fiber = Fiber(
            self.ctx,
            config,
            inject,
            runtime,
            outer,
        )
        # Add to runtime list.
        runtime.fibers.push(fiber)
        return fiber
