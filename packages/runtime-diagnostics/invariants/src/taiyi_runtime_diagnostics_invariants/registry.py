"""`taiyi_runtime_diagnostics_invariants.registry` — the InvariantRegistry service.

Faithful Python port of `~/deepseek-harness/packages/runtime-diagnostics/
invariants/src/index.ts`. The TS source defines:

- :class:`InvariantRegistry` (a Cordis service) that owns the registry.
- :class:`InvariantError` raised by the per-package ``fail`` reporter.
- :func:`compilePatterns` validating allow/block regex lists.
- A ``selected(packageName)`` helper honouring the configured filters.

The Python adaptation keeps the same semantics but uses Pydantic for the
config model, a plain :class:`dict` for the surface store, and synchronous
``register``/``dispose`` calls (no child-fiber management in Python; the
companion module's installer is a no-op since the registry *is* the
mutation boundary already).
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field
from typing import Any, ClassVar

from cordis import Context, Service

__all__ = [
    "InvariantError",
    "InvariantConfig",
    "InvariantRegistry",
    "compile_patterns",
    "assert_invariant",
]


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class InvariantError(Exception):
    """Raised when a package-owned runtime invariant is violated.

    Mirrors upstream ``InvariantError``: the ``code`` is the stable machine
    code (``'INVARIANT'``), ``package_name`` records which package's check
    was the source of the violation, and the message carries the violated
    contract text.
    """

    code: ClassVar[str] = "INVARIANT"

    package_name: str

    def __init__(self, package_name: str, message: str) -> None:
        super().__init__(f'invariant violated by "{package_name}": {message}')
        self.package_name = package_name
        self.name = "InvariantError"


# ---------------------------------------------------------------------------
# Config (1:1 with upstream `Config`)
# ---------------------------------------------------------------------------


@dataclass
class InvariantConfig:
    """Runtime invariant selection configured on the service plugin."""

    enabled: bool = True
    package_allowlist: list[str] = field(default_factory=list)
    package_blocklist: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# compilePatterns (1:1 with upstream)
# ---------------------------------------------------------------------------


def compile_patterns(
    field: str,
    values: Iterable[str],
) -> list[re.Pattern[str]]:
    """Compile and validate one package-filter list.

    Mirrors upstream ``compilePatterns``: rejects blank entries, duplicates,
    and invalid regex sources; otherwise returns the compiled patterns.
    """
    seen: set[str] = set()
    out: list[re.Pattern[str]] = []
    for value in values:
        if len(value) == 0 or value.strip() != value:
            raise ValueError(
                f"invariants: {field} entries must be non-blank and have no surrounding whitespace"
            )
        if value in seen:
            raise ValueError(f"invariants: {field} contains duplicate regex {value!r}")
        seen.add(value)
        try:
            out.append(re.compile(value))
        except re.error as cause:
            raise ValueError(f"invariants: {field} contains invalid regex {value!r}") from cause
    return out


# ---------------------------------------------------------------------------
# InvariantRegistry (1:1 with upstream `InvariantRegistry` extends `Service`)
# ---------------------------------------------------------------------------


class InvariantRegistry(Service):
    """Package-owned invariant registry with global and regex-based selection.

    Mirrors upstream ``InvariantRegistry``:

    - ``enabled`` / ``package_allowlist`` / ``package_blocklist`` filter
      which packages participate in the runtime checks.
    - ``register(package_name, surface)`` records a vendor's invariant
      surface and returns a disposer.
    - ``assert_invariant(name, fn)`` is the test hook for declaring that
      an invariant must hold; it records the check and runs it once,
      raising :class:`InvariantError` on a falsy return value.
    - ``check(name)`` re-runs a previously-asserted check.
    """

    config: ClassVar[type[Any] | None] = InvariantConfig

    def __init__(self, ctx: Context, **config: Any) -> None:
        super().__init__(ctx, **config)
        cfg = InvariantConfig(**config)
        self.enabled: bool = cfg.enabled
        self._package_allowlist: list[re.Pattern[str]] = compile_patterns(
            "package_allowlist", cfg.package_allowlist
        )
        self._package_blocklist: list[re.Pattern[str]] = compile_patterns(
            "package_blocklist", cfg.package_blocklist
        )
        self._surfaces: dict[str, Any] = {}
        self._disposers: dict[str, Callable[[], None]] = {}
        self._checks: dict[str, Callable[[], Any]] = {}

    # ------------------------------------------------------------------
    # Selection
    # ------------------------------------------------------------------

    def selected(self, package_name: str) -> bool:
        """Return whether ``package_name`` passes the configured filters."""
        if not self.enabled:
            return False
        if self._package_allowlist and not any(
            pattern.search(package_name) for pattern in self._package_allowlist
        ):
            return False
        return not any(pattern.search(package_name) for pattern in self._package_blocklist)

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, package_name: str, surface: Any) -> Callable[[], None]:
        """Register one package's invariant surface.

        The ``surface`` may be a module (the typical case: a vendor's
        ``invariant`` companion barrel) or any other marker object. The
        returned disposer removes the registration when called.
        """
        if (
            not package_name
            or package_name.strip() != package_name
            or any(ch.isspace() for ch in package_name)
        ):
            raise ValueError("invariants: packageName must be non-blank and contain no whitespace")
        if package_name in self._surfaces:
            raise ValueError(f'invariants: package "{package_name}" is already registered')
        self._surfaces[package_name] = surface

        def _dispose() -> None:
            self._surfaces.pop(package_name, None)
            self._disposers.pop(package_name, None)

        self._disposers[package_name] = _dispose
        return _dispose

    # ------------------------------------------------------------------
    # Surface lookup
    # ------------------------------------------------------------------

    def names(self) -> list[str]:
        """Sorted list of currently registered package names."""
        return sorted(self._surfaces.keys())

    def get(self, package_name: str, default: Any = None) -> Any:
        """Map-like lookup with a default value."""
        return self._surfaces.get(package_name, default)

    def __contains__(self, package_name: object) -> bool:
        return isinstance(package_name, str) and package_name in self._surfaces

    def __getitem__(self, package_name: str) -> Any:
        return self._surfaces[package_name]

    def __iter__(self) -> Iterator[str]:
        return iter(sorted(self._surfaces.keys()))

    # ------------------------------------------------------------------
    # Test hook: assert_invariant / check
    # ------------------------------------------------------------------

    def assert_invariant(
        self,
        name: str,
        fn: Callable[[], Any],
    ) -> None:
        """Record and verify an invariant check (test-time helper).

        The check ``fn`` runs immediately. A falsy return value triggers
        :class:`InvariantError`; any exception raised inside ``fn``
        propagates as-is so callers see the original failure.
        """
        if name in self._checks:
            raise ValueError(f"invariant {name!r} already asserted")
        self._checks[name] = fn
        result = fn()
        if result is False:
            raise InvariantError(name, "invariant check returned false")

    def check(self, name: str) -> None:
        """Re-run the check registered under ``name``."""
        fn = self._checks.get(name)
        if fn is None:
            raise KeyError(f"invariant {name!r} is not asserted")
        result = fn()
        if result is False:
            raise InvariantError(name, "invariant check returned false")


# ---------------------------------------------------------------------------
# Module-level helper
# ---------------------------------------------------------------------------


def assert_invariant(
    ctx: Context | Any,
    name: str,
    fn: Callable[[], Any],
) -> None:
    """Convenience wrapper that finds an ``InvariantRegistry`` on ``ctx``.

    The active registry is resolved from ``ctx.invariants``. Raises
    :class:`InvariantError` if the check fails.
    """
    registry = ctx.invariants  # type: ignore[attr-defined]
    if not isinstance(registry, InvariantRegistry):  # pragma: no cover — defensive
        raise TypeError("ctx.invariants is not an InvariantRegistry; did the plugin run?")
    registry.assert_invariant(name, fn)
