"""`loader.isolate` — scope-aware isolate helpers (1:1 port of `isolate.ts`).

Provides:

- :class:`Realm` — abstract symbol-keyed namespace; allocate and cache
  per-realm symbols with a stable suffix.
- :class:`LocalRealm` — entry-scoped symbols (suffix uses entry id).
- :class:`GlobalRealm` — label-scoped symbols (suffix uses label).

The full :func:`isolate` plugin (which hooks ``loader/entry-init`` and
``loader/patch-context`` events) lives in the runtime-level port since
it depends on the loader's ``internal/plugin`` event machinery. This
module hosts the *data* helpers.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from loader.entry import Entry

__all__ = ["Realm", "LocalRealm", "GlobalRealm"]


class Realm(ABC):
    """Symbol-keyed namespace backing the runtime's ``isolate`` map.

    Mirrors upstream ``Realm``: symbols are stored as a dict indexed by
    ``name``. Symbol values are Python strings in this port (the JS
    runtime uses ``Symbol(name)``; we name-suffix with the realm suffix
    instead).
    """

    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    @property
    @abstractmethod
    def suffix(self) -> str:
        """Symbol suffix used by the realm."""

    def access(self, name: str, create: bool = False) -> str | None:
        """Return the cached symbol for ``name`` (allocating if ``create``)."""
        if create:
            existing = self.store.get(name)
            if existing is None:
                self.store[name] = f"{name}{self.suffix}"
                return self.store[name]
            return existing
        # Without ``create``, missing keys return a transient symbol that
        # is *not* cached — same as upstream's ``store[name] ?? Symbol(...)``.
        return self.store.get(name) or f"{name}{self.suffix}"

    def delete(self, name: str) -> None:
        """Remove a cached symbol (no-op if absent)."""
        self.store.pop(name, None)

    @property
    def size(self) -> int:
        """Number of cached symbols."""
        return len(self.store)


class LocalRealm(Realm):
    """Entry-scoped realm (symbol suffix references the entry id)."""

    def __init__(self, entry: Entry) -> None:
        super().__init__()
        self._entry = entry

    @property
    def suffix(self) -> str:
        return f"#{self._entry.options.id}"


class GlobalRealm(Realm):
    """Label-scoped realm (symbol suffix references the label)."""

    def __init__(self, label: str) -> None:
        super().__init__()
        self.label = label

    @property
    def suffix(self) -> str:
        return f"@{self.label}"


# ---------------------------------------------------------------------------
# Pure helper exposed for the runtime-level isolate plugin.
# ---------------------------------------------------------------------------


def isolate_key_lookup(label: str | bool | None, name: str) -> str | None:
    """Return a normalized label suitable for the runtime ``isolate`` map.

    Helper used by the runtime-level port — not used by tests but kept
    here to round out the public surface.
    """
    if label is True:
        return f"local#{name}"
    if isinstance(label, str):
        return f"global@{label}::{name}"
    return None
