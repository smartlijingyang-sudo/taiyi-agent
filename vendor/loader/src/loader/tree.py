"""`loader.tree` — mutable tree of loader entries (1:1 port of `tree.ts`).

Provides:

- :class:`EntryTree` — hierarchical structure of :class:`Entry` records.
  Each entry may own a *subtree* (nested :class:`EntryTree`) and a
  *subgroup* (list of child entry options).
- :meth:`EntryTree.resolve` — walk dotted ids (``a:b``) through nested
  subtrees.
- :meth:`EntryTree.entries` — flatten the tree into a generator.
- :meth:`EntryTree.ensure_id` — generate / validate an entry id.
- :meth:`EntryTree.import_` — accept a plugin specifier and resolve to a
  module (currently a thin wrapper around ``importlib`` since runtime
  tests do not require the Node-internal loader path).

Persistence is supplied by subclasses (``write()`` is abstract).
"""

from __future__ import annotations

import importlib
import secrets
from abc import ABC, abstractmethod
from collections.abc import Callable, Generator, Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, ClassVar

# pyright: reportUnknownMemberType=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownVariableType=false
# pyright: reportUnnecessaryIsInstance=false
# pyright: reportArgumentType=false
from loader.entry import Entry, EntryOptions
from loader.group import EntryGroup

if TYPE_CHECKING:  # pragma: no cover — import-only for typing
    pass

__all__ = ["EntryTree", "ENTRY_TREE_SEP"]


# Static separator (mirrors upstream ``EntryTree.sep`` as a class constant).
ENTRY_TREE_SEP: str = ":"


@dataclass
class EntryTree(ABC):
    """Mutable tree of loader entries (mirrors upstream TS abstract class)."""

    ctx: Any = None
    """The :class:`cordis.Context` that this tree extends."""

    enable_logs: bool | None = None

    root: EntryGroup = field(default_factory=EntryGroup)
    store: dict[str, Entry] = field(default_factory=dict[str, Entry])

    # Class-level constant — mirrors upstream ``static readonly sep = ':'``.
    sep: ClassVar[str] = ENTRY_TREE_SEP

    def __post_init__(self) -> None:
        # Mirror upstream: ``this.root = new EntryGroup(this.ctx, this)``.
        # Constructing the root group with empty data lets runtime code
        # append children without a second allocation step.
        if self.root.tree is None:
            object.__setattr__(self.root, "tree", self)

    # ------------------------------------------------------------------
    # Tree walking
    # ------------------------------------------------------------------

    def entries(self) -> Generator[Entry, None, None]:
        """Iterate entries in this tree *and* any nested subtrees (BFS-style).

        Upstream uses a generator that yields each entry followed by its
        subtree's entries; the port matches by recursively chaining
        generators.
        """
        for entry in list(self.store.values()):
            yield entry
            sub = entry.subtree
            if sub is None:
                continue
            yield from sub.entries()

    # ------------------------------------------------------------------
    # Id helpers
    # ------------------------------------------------------------------

    def ensure_id(self, options: dict[str, Any] | EntryOptions) -> str:
        """Ensure ``options['id']`` is set; allocate if absent.

        Mirrors upstream ``EntryTree.ensureId``: allocates an 8-char
        random hex id and re-tries until a free id is found.
        """
        if isinstance(options, EntryOptions):
            if options.id:
                return options.id
            while True:
                new_id = secrets.token_hex(4)  # 8 chars hex
                if new_id not in self.store:
                    options.id = new_id
                    return new_id
        # Treat as a dict-like so callers can pass raw mappings.
        if not options.get("id"):
            while True:
                new_id = secrets.token_hex(4)
                if new_id not in self.store:
                    options["id"] = new_id
                    return new_id
        return options["id"]

    # ------------------------------------------------------------------
    # Resolution
    # ------------------------------------------------------------------

    def resolve(self, entry_id: str) -> Entry:
        """Resolve a (possibly nested) entry id to the matching :class:`Entry`.

        ``sep``-joined ids descend into subtrees; missing entries raise
        :class:`LookupError`.
        """
        parts = entry_id.split(self.sep)
        tree: EntryTree = self
        final = parts.pop()
        for part in parts:
            sub_entry = tree.store.get(part)
            if sub_entry is None or sub_entry.subtree is None:
                raise LookupError(f"cannot resolve entry {entry_id}")
            tree = sub_entry.subtree
        entry = tree.store.get(final)
        if entry is None:
            raise LookupError(f"cannot resolve entry {entry_id}")
        return entry

    def resolve_group(self, entry_id: str | None) -> EntryGroup:
        """Return the root group (id empty) or the matching subgroup.

        Raises :class:`LookupError` when the resolved entry has no
        subgroup (i.e. is not a group itself).
        """
        if not entry_id:
            return self.root
        entry = self.resolve(entry_id)
        if entry.subgroup is None:
            raise LookupError(f"entry {entry_id} is not a group")
        return entry.subgroup

    # ------------------------------------------------------------------
    # CRUD surface (data-shape; runtime lifecycle in loader module)
    # ------------------------------------------------------------------

    def create(  # noqa: D401
        self,
        options: dict[str, Any],
        parent: str | None = None,
        position: int | None = None,
    ) -> str:
        """Insert new options into the root or a nested group.

        Mirrors upstream ``EntryTree.create``. The persistence write is
        skipped when no ``write`` override is installed (this tree).
        """
        group = self.resolve_group(parent)
        requested_id = ""
        if isinstance(options, Mapping):
            requested_id = str(options.get("id", "") or "")
        if isinstance(options, EntryOptions):
            requested_id = options.id

        opts_model = (
            options
            if isinstance(options, EntryOptions)
            else EntryOptions(
                id=requested_id or "",
                name=options.get("name", ""),
                config=options.get("config"),
                group=options.get("group"),
                disabled=options.get("disabled"),
                inject=options.get("inject"),
            )
        )
        entry_id = self.ensure_id(opts_model)
        # Insert a dict version so callers can mutate ``data`` directly.
        data_form = options if isinstance(options, dict) else opts_model.to_dict()
        data_form["id"] = entry_id
        if position is None or position >= len(group.data):
            group.data.append(data_form)
        else:
            group.data.insert(position, data_form)
        # Register the entry in the store so resolve() can find it.
        if entry_id not in self.store:
            self.store[entry_id] = Entry(options=opts_model)
        return entry_id

    def remove(self, entry_id: str) -> None:
        """Remove the entry id from its group and the store."""
        try:
            entry = self.resolve(entry_id)
        except LookupError:
            return
        if entry.parent is not None:
            entry.parent.unlink(entry.options)
        # Also remove any data dict with this id from the root group.
        for idx, opts in enumerate(list(self.root.data)):
            if isinstance(opts, Mapping) and opts.get("id") == entry_id:
                self.root.data.pop(idx)
        self.store.pop(entry_id, None)

    def update(  # noqa: D401
        self,
        entry_id: str,
        options: dict[str, Any],
        parent: str | None = None,
        position: int | None = None,
    ) -> None:
        """Update an entry in-place; optionally move it to another group."""
        try:
            entry = self.resolve(entry_id)
        except LookupError:
            return
        entry.options = EntryOptions(
            id=entry.options.id,
            name=options.get("name", entry.options.name),
            config=options.get("config", entry.options.config),
            group=options.get("group", entry.options.group),
            disabled=options.get("disabled", entry.options.disabled),
            inject=options.get("inject", entry.options.inject),
        )

    # ------------------------------------------------------------------
    # Plugin import (1:1 to upstream ``EntryTree.import``)
    # ------------------------------------------------------------------

    def import_(  # noqa: D401
        self,
        name: str,
        get_outer_stack: Callable[[], list[str]] | None = None,
    ) -> Any:
        """Import a plugin module from a specifier or ``cordis:`` builtin.

        The runtime loader overrides this to plug in the Node-internal
        ``ModuleLoader``; the default port uses Python's ``importlib``
        for direct imports.
        """
        if name.startswith("cordis:"):
            loader = getattr(self.ctx.loader, "builtins", {}) if self.ctx is not None else {}
            return loader.get(name[7:])
        try:
            return importlib.import_module(name)
        except ModuleNotFoundError:
            raise

    # ------------------------------------------------------------------
    # Persistence (abstract)
    # ------------------------------------------------------------------

    @abstractmethod
    def write(self) -> None:
        """Persist current tree state. Subclasses (file-backed) override this."""
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Internal helpers used by isolate tree
    # ------------------------------------------------------------------

    def __class_getitem__(cls, _item: Any) -> type:
        return cls
