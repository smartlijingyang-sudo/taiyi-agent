"""`loader.load` — load / dump helpers (1:1 port of upstream `loader.ts`).

Provides:

- :func:`load_config` — parse dict / list / YAML string into an
  :class:`EntryTree`. Optional interpolation is delegated to
  :mod:`loader.utils`.
- :func:`load_yaml` — read a YAML file from disk and parse it.
- :func:`dump_config` — serialize an :class:`EntryTree` back to a plain
  dict / list (lossless round-trip).
- :func:`merge_bundles` — flatten multiple named bundles into a single
  tree, later entries overriding earlier ones with the same id.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

import yaml

from loader.entry import Entry, EntryOptions
from loader.tree import EntryTree

# pyright: reportUnknownMemberType=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownVariableType=false
# pyright: reportUnnecessaryIsInstance=false

__all__ = [
    "load_config",
    "load_yaml",
    "dump_config",
    "merge_bundles",
    "Bundle",
]


# ---------------------------------------------------------------------------
# Bundle — group of named entries (matches upstream TS ``Bundle`` class).
# ---------------------------------------------------------------------------


def _make_tree() -> EntryTree:
    """Construct an :class:`EntryTree` instance with a stub ``write`` method.

    Subclasses (file-backed) override :meth:`write`; this stub satisfies
    the abstract method while preserving the data-only port shape.
    """

    class _EmptyTree(EntryTree):
        def write(self) -> None:
            return None

    return _EmptyTree()


class Bundle:
    """Named bag of :class:`EntryOptions` rows (1:1 with upstream ``Bundle``)."""

    __slots__ = ("name", "entries")

    def __init__(self, name: str, entries: list[EntryOptions] | None = None) -> None:
        self.name = name
        self.entries: list[EntryOptions] = list(entries or [])

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "entries": [e.to_dict() for e in self.entries]}


# ---------------------------------------------------------------------------
# load_config
# ---------------------------------------------------------------------------


def _coerce_entry_form(row: Mapping[str, Any]) -> EntryOptions:
    """Convert a raw mapping into a validated :class:`EntryOptions`."""
    entry_id = row.get("id")
    if not isinstance(entry_id, str) or not entry_id:
        raise ValueError(f"loader entry requires string 'id', got {entry_id!r}")
    if "name" not in row or not isinstance(row["name"], str):
        raise ValueError(f"loader entry {entry_id!r} requires string 'name'")
    opts = EntryOptions(
        id=entry_id,
        name=row["name"],
        config=row.get("config"),
        group=row.get("group"),
        disabled=row.get("disabled"),
        inject=row.get("inject"),
    )
    # Preserve extra keys for round-trip.
    for key, value in row.items():
        if key in ("id", "name", "config", "group", "disabled", "inject"):
            continue
        opts.extra[key] = value
    return opts


def _is_entry_dict(obj: Any) -> bool:
    return isinstance(obj, Mapping) and isinstance(obj.get("id"), str)


def _build_tree(data: Any) -> EntryTree:
    """Convert ``data`` (dict / list / None) into an :class:`EntryTree`."""
    from loader.utils import interpolate as _interpolate

    # ``None`` → empty tree (after JSON/YAML nulls).
    if data is None:
        return _make_tree()

    # Allow callers to skip interpolation by passing any non-dict/list.
    interpolated = _interpolate({}, data)

    if isinstance(interpolated, list):
        tree = _make_tree()
        for row in interpolated:
            if not isinstance(row, Mapping):
                raise ValueError(
                    f"loader entry must be a mapping, got {type(row).__name__}"
                )
            opts = _coerce_entry_form(row)
            entry = Entry(options=opts)
            tree.ensure_id(opts)
            tree.store[opts.id] = entry
        return tree

    if isinstance(interpolated, Mapping):
        # Single entry (has 'id' AND 'name') vs. group (no id required).
        if _is_entry_dict(interpolated):
            opts = _coerce_entry_form(interpolated)
            tree = _make_tree()
            tree.ensure_id(opts)
            tree.store[opts.id] = Entry(options=opts)
            return tree
        # Group shape: ``{"entries": [...]}``
        if "entries" in interpolated and isinstance(interpolated["entries"], list):
            return _build_tree(interpolated["entries"])
        raise ValueError(f"cannot build loader tree from {interpolated!r}")

    raise ValueError(f"cannot build loader tree from {type(interpolated).__name__}")


def load_config(data: Any) -> EntryTree:
    """Parse ``data`` (dict / list / YAML string) into an :class:`EntryTree`.

    Interpolation is applied *only* for the YAML-string path so that
    raw mappings remain byte-identical to the input (matches upstream's
    split-architecture where ``load_yaml`` interpolates but
    ``loadConfig`` does not).
    """
    if isinstance(data, str):
        # Treat the string as a YAML document.
        parsed = yaml.safe_load(data) if data.strip() else None
        return _build_tree_parsed(parsed)
    return _build_tree(data)


def _build_tree_parsed(data: Any) -> EntryTree:
    """Build a tree from ``yaml.safe_load`` output, with interpolation enabled."""
    from loader.utils import interpolate as _interpolate

    if data is None:
        return _make_tree()

    if isinstance(data, list):
        tree = _make_tree()
        for row in data:
            if not isinstance(row, Mapping):
                raise ValueError(
                    f"loader entry must be a mapping, got {type(row).__name__}"
                )
            # Run interpolation against an empty scope (YAML !js evaluates
            # against the loader context; we resolve to the raw value here).
            row = _interpolate({}, row)
            opts = _coerce_entry_form(row)
            tree.ensure_id(opts)
            tree.store[opts.id] = Entry(options=opts)
        return tree

    if isinstance(data, Mapping):
        if _is_entry_dict(data):
            row = _interpolate({}, data)
            opts = _coerce_entry_form(row)
            tree = _make_tree()
            tree.ensure_id(opts)
            tree.store[opts.id] = Entry(options=opts)
            return tree
        if "entries" in data and isinstance(data["entries"], list):
            return _build_tree_parsed(data["entries"])
        raise ValueError(f"cannot build loader tree from {data!r}")

    raise ValueError(f"cannot build loader tree from {type(data).__name__}")


# ---------------------------------------------------------------------------
# load_yaml
# ---------------------------------------------------------------------------


def load_yaml(path: str | Path) -> EntryTree:
    """Read a YAML file from ``path`` and parse it into an :class:`EntryTree`."""
    raw = Path(path).read_text(encoding="utf-8")
    return load_config(raw)


# ---------------------------------------------------------------------------
# dump_config
# ---------------------------------------------------------------------------


def dump_config(target: EntryTree | Bundle | Iterable[Any] | Entry) -> list[dict[str, Any]] | dict[str, Any]:
    """Serialize ``target`` back into a dict or list.

    - :class:`EntryTree` → list of entry dicts (one per store entry).
    - :class:`Bundle`   → ``{"name": ..., "entries": [...]}``.
    - any iterable of :class:`Entry`/``EntryOptions``/mapping →
      ``{"entries": [...]}`` shape.
    - :class:`Entry`    → single entry dict.
    """
    if isinstance(target, EntryTree):
        return [target.store[k].options.to_dict() for k in sorted(target.store.keys())]
    if isinstance(target, Bundle):
        return target.to_dict()
    if isinstance(target, Entry):
        return target.options.to_dict()
    if isinstance(target, Iterable):
        return {"entries": [_dump_value(v) for v in target]}
    raise TypeError(f"cannot dump {type(target).__name__}")


def _dump_value(value: Any) -> Any:
    if isinstance(value, Entry):
        return value.options.to_dict()
    if isinstance(value, EntryOptions):
        return value.to_dict()
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, list):
        return [_dump_value(v) for v in value]
    return value


# ---------------------------------------------------------------------------
# merge_bundles
# ---------------------------------------------------------------------------


def merge_bundles(*bundles: Bundle | list[Any]) -> EntryTree:
    """Merge multiple ``Bundle``s into a single :class:`EntryTree`.

    Later entries override earlier ones with the same ``id``. Iterable
    inputs are accepted as well — they become synthetic bundles.
    """
    tree = _make_tree()
    for bundle in bundles:
        rows: Iterable[Any]
        if isinstance(bundle, Bundle):
            rows = bundle.entries
        elif isinstance(bundle, Mapping):
            rows = [bundle]
        elif isinstance(bundle, Iterable):
            rows = list(bundle)
        else:
            raise TypeError(f"cannot merge {type(bundle).__name__}")
        for row in rows:
            if isinstance(row, Entry):
                opts = row.options
            elif isinstance(row, EntryOptions):
                opts = row
            elif isinstance(row, Mapping):
                opts = _coerce_entry_form(row)
            else:
                raise ValueError(f"cannot merge bundle row {row!r}")
            tree.ensure_id(opts)
            existing = tree.store.get(opts.id)
            if existing is not None:
                existing.options = opts
            else:
                tree.store[opts.id] = Entry(options=opts)
    return tree
