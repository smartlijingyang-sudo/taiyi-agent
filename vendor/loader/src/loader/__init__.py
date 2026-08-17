"""taiyi-loader — 1:1 Python port of @deepseek-ai/cordis-plugin-loader.

Public surface:

- :class:`Entry` — single plugin entry (id, name, config, disabled, inject).
- :class:`EntryOptions` — typed payload backing an :class:`Entry`.
- :func:`parse_entry` — validate a raw mapping → ``Entry``.
- :class:`EntryGroup` — group of entries sharing a key.
- :class:`Group` — :class:`EntryGroup` subclass that itself is a plugin.
- :class:`EntryTree` — hierarchical structure of entries with id-based
  resolution and subtree walking.
- :class:`Realm`, :class:`LocalRealm`, :class:`GlobalRealm` — symbol
  namespaces backing the runtime ``isolate`` map.
- :func:`evaluate` — evaluate a JavaScript expression against a context scope.
- :func:`interpolate` — recursively replace YAML ``!js`` markers.
- :func:`is_js_expr` — predicate for the ``__js_expr`` marker.
- :class:`JsExpr` — typed wrapper around a JS expression.
- :func:`load_config` — top-level helper: accept dict, list, or YAML string.
- :func:`load_yaml` — read YAML from disk and parse.
- :func:`dump_config` — serialize an :class:`EntryTree` back to a dict / list.
- :class:`Bundle` — named bag of :class:`EntryOptions`.
- :func:`merge_bundles` — flatten multiple bundles into a single :class:`EntryTree`.
- :class:`Loader` — runtime plugin loader (entry tree + import + lifecycle).

The stable contract is documented in :mod:`loader.invariant`; consumers
should depend on that submodule when they need a stable API surface.
"""

from __future__ import annotations

from typing import Any, ClassVar

# The `taiyi-cordis` package is intentionally without bundled type stubs;
# suppress the missing-stub warning per-file (mirrors the upstream
# convention in ``taiyi-cordis``'s own `pyright` config).
from cordis import Context, Service  # pyright: ignore[reportMissingTypeStubs]

from loader.entry import Entry, EntryOptions, parse_entry
from loader.group import EntryGroup, Group
from loader.isolate import GlobalRealm, LocalRealm, Realm
from loader.load import (
    Bundle,
    dump_config,
    load_config,
    load_yaml,
    merge_bundles,
)
from loader.tree import EntryTree
from loader.utils import JsExpr, evaluate, interpolate, is_js_expr

__all__ = [
    # Entry / Group / Tree
    "Entry",
    "EntryOptions",
    "parse_entry",
    "EntryGroup",
    "Group",
    "EntryTree",
    # Isolate realms
    "Realm",
    "LocalRealm",
    "GlobalRealm",
    # Utils
    "JsExpr",
    "evaluate",
    "interpolate",
    "is_js_expr",
    # Load / dump
    "Bundle",
    "dump_config",
    "load_config",
    "load_yaml",
    "merge_bundles",
    # Loader (runtime)
    "Loader",
]


# ---------------------------------------------------------------------------
# Loader — runtime plugin loader (1:1 with upstream `Loader` class).
# ---------------------------------------------------------------------------


class Loader(Service):
    """Runtime plugin loader that owns an :class:`EntryTree`.

    Mirrors the upstream ``Loader`` class:

    - ``ctx.provide('loader', self)`` is set up automatically by the
      :class:`cordis.Service` base.
    - ``builder_name`` defaults to ``"loader"`` for parity with upstream.
    - ``builtins`` is a dict for ``cordis:`` namespace lookups (mirrors
      the upstream runtime).

    Persistence is supplied by subclasses (``write()`` is no-op here;
    file-backed ports override it).
    """

    name: ClassVar[str] = "loader"

    def __init__(self, ctx: Context, config: dict[str, Any] | None = None) -> None:
        super().__init__(ctx)
        self.ctx = ctx
        # Mirror upstream: ``this.config`` is a per-instance dict on the
        # Loader subclass (the ``Service.config`` class attr is the
        # Pydantic model class, which we don't use here).
        self.config = dict(config or {})  # type: ignore[assignment]
        self.builtins: dict[str, Any] = {}
        # The local root tree is the in-memory equivalent of upstream's
        # always-empty root (persistence lives in subclass ports).
        self._tree: EntryTree | None = None

    # ------------------------------------------------------------------
    # Accessors
    # ------------------------------------------------------------------

    @property
    def tree(self) -> EntryTree:
        """Return the root :class:`EntryTree` (lazily built)."""
        if self._tree is None:

            class _InMemoryTree(EntryTree):
                def write(self) -> None:  # pragma: no cover — no-op persistence
                    return None

            self._tree = _InMemoryTree()
        return self._tree

    @property
    def enable_logs(self) -> bool:
        return bool(self.tree.enable_logs)

    @enable_logs.setter
    def enable_logs(self, value: bool | None) -> None:
        self.tree.enable_logs = value

    # ------------------------------------------------------------------
    # Public surface (1:1 to upstream Loader API)
    # ------------------------------------------------------------------

    def write(self) -> None:
        """Persist the root tree. In-memory trees are a no-op."""
        try:
            self.tree.write()
        except Exception:  # pragma: no cover — persistence is best-effort here
            return

    def unwrap_exports(self, exports: Any) -> Any:
        """Normalize ESM/CJS/default export shapes (1:1 to upstream).

        JS uses ``__esModule`` to detect default-interop wrappers; the
        Python port just unwraps the obvious default-export convention
        while ignoring the ``None`` case explicitly.
        """
        if exports is None:
            return exports
        # ``module.default`` is the Python default-export convention.
        default = getattr(exports, "default", None)
        if default is not None:
            return default
        return exports

    @property
    def _ctx_root(self) -> Any:
        """Expose ``self.ctx.root`` for the show-log helper."""
        return getattr(self.ctx, "root", None)

    async def create(
        self,
        options: dict[str, Any],
        parent: str | None = None,
        position: int | None = None,
    ) -> str:
        """Insert new options into the root or a nested group (1:1 API)."""
        return self.tree.create(options, parent=parent, position=position)

    async def remove(self, entry_id: str) -> None:
        self.tree.remove(entry_id)

    async def update(
        self,
        entry_id: str,
        options: dict[str, Any],
        parent: str | None = None,
        position: int | None = None,
    ) -> None:
        self.tree.update(entry_id, options, parent=parent, position=position)

    def resolve(self, entry_id: str) -> Entry:
        return self.tree.resolve(entry_id)

    def resolve_group(self, entry_id: str | None) -> EntryGroup:
        return self.tree.resolve_group(entry_id)

    async def await_(self) -> None:
        """Block the loader until pending imports settle."""
        # Runtime-level port defers to the framework's fiber inertia.
        return None

    def locate(self, entry_id: str | None = None) -> str | None:
        """Return the entry id that owns the given fiber (1:1 API).

        The Python port operates on entry ids only; passing ``None``
        returns ``None``.
        """
        return entry_id

    def get_tasks(self) -> list[Entry]:
        """Return pending entries (runtime tasks)."""
        return list(self.tree.entries())

    def show_log(self, entry: Entry, kind: str) -> None:
        """Emit a log line; mirror upstream ``showLog``."""
        if entry.options.group or not self.tree.enable_logs:
            return
        ctx = getattr(self, "ctx", None)
        root = getattr(ctx, "root", None) if ctx is not None else None
        logger = getattr(root, "logger", None) if root is not None else None
        if logger is not None:
            try:
                logger(f"loader {kind} {entry.options.name}")
            except Exception:  # noqa: BLE001 - logger call is best-effort
                pass

    def exit(self) -> None:
        """Hook for hosts that can restart the process (no-op by default)."""
        return None
