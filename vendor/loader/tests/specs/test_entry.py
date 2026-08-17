"""Tests for `loader.entry` — `Entry`, `EntryOptions`, `parse_entry` (1:1 port).

The TS class extends nothing beyond what Python's data model offers; the
port keeps the same field set and explicit constructor invariants.
"""

from __future__ import annotations

from typing import Any

import pytest

from loader.entry import Entry, EntryOptions, parse_entry


class TestEntryOptions:
    """`EntryOptions` is a TypedDict-shaped record; port uses a dataclass for clarity."""

    def test_required_fields_only(self):
        opts: dict[str, Any] = {"id": "x", "name": "./plugin"}
        # The "bare" shape upstream uses is just a plain object; check parse_entry accepts it.
        entry = parse_entry(opts)
        assert entry.options.id == "x"
        assert entry.options.name == "./plugin"

    def test_optional_fields(self):
        opts: dict[str, Any] = {
            "id": "x",
            "name": "./plugin",
            "config": {"k": 1},
            "group": True,
            "disabled": False,
            "inject": ["foo"],
        }
        entry = parse_entry(opts)
        assert entry.options.config == {"k": 1}
        assert entry.options.group is True
        assert entry.options.disabled is False
        assert entry.options.inject == ["foo"]


class TestParseEntryValidation:
    """`parse_entry` mirrors upstream validation; missing fields raise."""

    def test_missing_id_raises(self):
        with pytest.raises(ValueError):
            parse_entry({"name": "./plugin"})

    def test_missing_name_raises(self):
        with pytest.raises(ValueError):
            parse_entry({"id": "x"})

    def test_non_string_id_raises(self):
        with pytest.raises(ValueError):
            parse_entry({"id": 1, "name": "./plugin"})  # type: ignore[arg-type]

    def test_returns_typed_options(self):
        entry = parse_entry({"id": "x", "name": "./plugin"})
        assert isinstance(entry.options, EntryOptions)


class TestEntryClass:
    """The `Entry` dataclass retains identity, options, and group references."""

    def test_construct_basic(self):
        opts = EntryOptions(id="x", name="./plugin")
        entry = Entry(options=opts)
        assert entry.options.id == "x"
        assert entry.options.name == "./plugin"
        assert entry.subgroup is None

    def test_subgroup_assignment(self):
        opts = EntryOptions(id="x", name="./plugin", group=True)
        entry = Entry(options=opts)
        assert entry.options.group is True

    def test_to_dict_omits_none_fields(self):
        opts = EntryOptions(id="x", name="./plugin")
        d = opts.to_dict()
        assert d == {"id": "x", "name": "./plugin"}

    def test_to_dict_includes_all(self):
        opts = EntryOptions(
            id="x",
            name="./plugin",
            config={"v": 1},
            group=True,
            disabled=False,
            inject=["svc"],
            extra={"custom": "v"},
        )
        d = opts.to_dict()
        assert d["config"] == {"v": 1}
        assert d["group"] is True
        assert d["disabled"] is False
        assert d["inject"] == ["svc"]
        assert d["custom"] == "v"

    def test_parse_entry_preserves_extra_fields(self):
        entry = parse_entry({"id": "x", "name": "./x", "tier": "primary"})
        assert entry.options.extra.get("tier") == "primary"
