"""`loader.entry` — single plugin entry (1:1 port of `loader/src/config/entry.ts`).

Provides:

- :class:`EntryOptions` — TypedDict-shaped dict container with the same
  optional/nullable semantics as upstream.
- :class:`Entry` — owned by exactly one :class:`EntryGroup` at a time;
  tracks the current fiber and the subgroup / subtree it owns.
- :func:`parse_entry` — Validate a raw dict → ``EntryOptions``.

The full update/init/refresh loop lives in the runtime-level port (it
depends on the loader's `tree.import` machinery). This module is the
*data* layer, intentionally separated so it can be imported and tested
without a live :class:`cordis.Context`.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover — import-only for typing
    from loader.group import EntryGroup
    from loader.tree import EntryTree

__all__ = [
    "Entry",
    "EntryOptions",
    "parse_entry",
]


# ---------------------------------------------------------------------------
# EntryOptions
# ---------------------------------------------------------------------------


@dataclass
class EntryOptions:
    """Serialized plugin entry options (1:1 with upstream TS interface).

    All fields except ``id`` and ``name`` are optional / nullable to
    match upstream's permissive shapes. ``extra`` holds any unrecognized
    keys so the round-trip is lossless.
    """

    id: str
    name: str
    config: Any = None
    group: bool | None = None
    disabled: Any = None
    inject: Any = None
    extra: dict[str, Any] = field(default_factory=dict[str, Any])

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict (used by ``load.dump_config``)."""
        out: dict[str, Any] = {"id": self.id, "name": self.name}
        if self.config is not None:
            out["config"] = self.config
        if self.group is not None:
            out["group"] = self.group
        if self.disabled is not None:
            out["disabled"] = self.disabled
        if self.inject is not None:
            out["inject"] = self.inject
        out.update(self.extra)
        return out


# ---------------------------------------------------------------------------
# Entry
# ---------------------------------------------------------------------------


@dataclass
class Entry:
    """One configured plugin node inside an :class:`EntryTree`.

    Mirrors the upstream ``Entry`` class:

    - ``options`` is replaced wholesale by :meth:`update` once validated.
    - ``subgroup`` and ``subtree`` are populated lazily when this entry
      itself becomes a group or mounts a nested entry tree.
    - ``fiber`` is set by the runtime loader once the plugin callback has
      been applied to the framework.
    """

    options: EntryOptions
    parent: EntryGroup | None = None
    subgroup: EntryGroup | None = None
    subtree: EntryTree | None = None
    fiber: Any = None  # ``cordis.Fiber`` instance; weakref-able.


# ---------------------------------------------------------------------------
# parse_entry
# ---------------------------------------------------------------------------


def parse_entry(options: Mapping[str, Any]) -> Entry:
    """Validate a raw mapping and instantiate an :class:`Entry`.

    Mirrors the upstream ``parseEntry`` validator (mirrors the
    ``assertEntry`` helpers upstream uses, see `conventions.md` §7.5):
    missing / non-string ``id`` or ``name`` raise :class:`ValueError`.
    """
    raw_id = options.get("id")
    raw_name = options.get("name")
    if not isinstance(raw_id, str) or not raw_id:
        raise ValueError(f"loader entry requires string 'id', got {raw_id!r}")
    if not isinstance(raw_name, str) or not raw_name:
        raise ValueError(f"loader entry {raw_id!r} requires string 'name'")
    opts = EntryOptions(
        id=raw_id,
        name=raw_name,
        config=options.get("config"),
        group=options.get("group"),
        disabled=options.get("disabled"),
        inject=options.get("inject"),
    )
    # Capture arbitrary extra keys for round-trip serialisation.
    for key, value in options.items():
        if key in ("id", "name", "config", "group", "disabled", "inject"):
            continue
        opts.extra[key] = value
    return Entry(options=opts)
