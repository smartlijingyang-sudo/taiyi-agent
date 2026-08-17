"""Tests for cordis.loader — Entry / EntryGroup / Loader / YAML / dump_config (1:1 to upstream)."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from cordis.loader import (
    Bundle,
    Entry,
    EntryGroup,
    EntryTree,
    Loader,
    dump_config,
    interpolate,
    isolate,
    load_config,
    load_yaml,
    merge_bundles,
)


# ---------------------------------------------------------------------------
# Entry / EntryGroup / EntryTree
# ---------------------------------------------------------------------------


class TestEntry:
    """Entry is a typed container for plugin configuration (1:1 with upstream)."""

    def test_create_minimal(self):
        entry = Entry(id="foo")
        assert entry.id == "foo"
        assert entry.name is None
        assert entry.config is None
        assert entry.disabled is None
        assert entry.inject is None

    def test_create_full(self):
        entry = Entry(
            id="foo",
            name="Foo Plugin",
            config={"setting": 1},
            disabled=False,
            inject=["bar"],
        )
        assert entry.name == "Foo Plugin"
        assert entry.config == {"setting": 1}
        assert entry.disabled is False
        assert entry.inject == ["bar"]

    def test_getitem(self):
        entry = Entry(id="x", name="X")
        assert entry["id"] == "x"
        assert entry["name"] == "X"

    def test_getitem_config_disabled_inject(self):
        entry = Entry(id="x", config={"k": 1}, disabled=True, inject=["y"])
        assert entry["config"] == {"k": 1}
        assert entry["disabled"] is True
        assert entry["inject"] == ["y"]

    def test_getitem_extra(self):
        entry = Entry(id="x")
        entry["custom"] = "value"
        assert entry["custom"] == "value"

    def test_setitem_arbitrary(self):
        entry = Entry(id="x")
        entry["custom"] = "value"
        assert entry.extra == {"custom": "value"}
        assert entry["custom"] == "value"

    def test_to_dict_round_trip(self):
        entry = Entry(id="x", name="X", config={"k": 1}, disabled=True, inject=["y"])
        d = entry.to_dict()
        assert d == {"id": "x", "name": "X", "config": {"k": 1}, "disabled": True, "inject": ["y"]}


class TestEntryGroup:
    """EntryGroup holds a list of entries sharing a key."""

    def test_create(self):
        e1 = Entry(id="a")
        e2 = Entry(id="b")
        group = EntryGroup(key="my-key", entries=[e1, e2])
        assert group.key == "my-key"
        assert group.entries == [e1, e2]


class TestEntryTree:
    """EntryTree is a hierarchical structure."""

    def test_create_empty(self):
        tree = EntryTree()
        assert tree.entries == []
        assert tree.find("missing") is None

    def test_add_entry(self):
        tree = EntryTree()
        tree.add(Entry(id="foo"))
        assert tree.find("foo") is not None

    def test_find_walks_parent_chain(self):
        parent = EntryTree()
        parent.add(Entry(id="parent-entry"))
        child = EntryTree(parent=parent)
        assert child.find("parent-entry") is not None

    def test_dispose_clears(self):
        tree = EntryTree()
        tree.disposables.push("disposable")
        tree.dispose()
        assert len(tree.disposables) == 0


# ---------------------------------------------------------------------------
# Interpolate
# ---------------------------------------------------------------------------


class TestInterpolate:
    """interpolate substitutes ${...} tokens in strings/containers."""

    def test_no_tokens_returns_unchanged(self):
        assert interpolate("hello", {}) == "hello"

    def test_simple_substitution(self):
        assert interpolate("hello ${name}", {"name": "world"}) == "hello world"

    def test_nested_path(self):
        assert interpolate("${a.b.c}", {"a": {"b": {"c": 42}}}) == "42"

    def test_missing_path_left_as_is(self):
        assert interpolate("${missing}", {}) == "${missing}"

    def test_partial_missing_left_as_is(self):
        assert interpolate("${a.missing}", {"a": {"b": 1}}) == "${a.missing}"

    def test_dict_interpolation(self):
        # Upstream semantics: string substitution is type-coerced to string.
        result = interpolate({"key": "${val}"}, {"val": 42})
        assert result == {"key": "42"}

    def test_list_interpolation(self):
        # Upstream semantics: substituted tokens become strings.
        result = interpolate(["${a}", "${b}"], {"a": 1, "b": 2})
        assert result == ["1", "2"]

    def test_non_string_passes_through(self):
        assert interpolate(42, {}) == 42
        assert interpolate(None, {}) is None


# ---------------------------------------------------------------------------
# Isolate
# ---------------------------------------------------------------------------


class TestIsolate:
    """isolate runs a factory with a fresh child tree."""

    def test_returns_factory_result(self):
        tree = EntryTree()
        result = isolate(tree, "test", lambda child: "ok")
        assert result == "ok"

    def test_child_tree_has_given_parent(self):
        parent = EntryTree()
        result = isolate(parent, "label", lambda child: child.parent)
        assert result is parent


# ---------------------------------------------------------------------------
# load_config / load_yaml
# ---------------------------------------------------------------------------


class TestLoadConfig:
    """load_config parses dict/list/YAML into an EntryTree."""

    def test_load_single_entry_dict(self):
        tree = load_config({"id": "foo", "name": "Foo"})
        assert len(tree.entries) == 1
        assert tree.entries[0].id == "foo"
        assert tree.entries[0].name == "Foo"

    def test_load_list_of_entries(self):
        tree = load_config([
            {"id": "a"},
            {"id": "b", "config": {"x": 1}},
        ])
        assert len(tree.entries) == 2
        assert tree.entries[1].config == {"x": 1}

    def test_load_entry_group_shape(self):
        data = {"key": "my-group", "entries": [{"id": "a"}, {"id": "b"}]}
        tree = load_config(data)
        assert len(tree.entries) == 2

    def test_load_yaml_string(self):
        yaml = """
- id: a
  name: A
- id: b
  name: B
"""
        tree = load_config(yaml)
        assert len(tree.entries) == 2
        assert tree.entries[0].id == "a"

    def test_load_empty_string(self):
        tree = load_config("")
        assert len(tree.entries) == 0

    def test_load_invalid_raises(self):
        with pytest.raises(ValueError):
            load_config({"name": "no id here"})  # type: ignore[arg-type]

    def test_load_list_with_invalid_entry_raises(self):
        with pytest.raises(ValueError):
            load_config([{"name": "no id"}])


class TestLoadYaml:
    """load_yaml reads from disk."""

    def test_load_yaml_file(self, tmp_path: Path):
        yaml_path = tmp_path / "config.yaml"
        yaml_path.write_text("- id: alpha\n  name: Alpha\n- id: beta\n")
        tree = load_yaml(str(yaml_path))
        assert len(tree.entries) == 2
        assert tree.entries[0].id == "alpha"


# ---------------------------------------------------------------------------
# dump_config
# ---------------------------------------------------------------------------


class TestDumpConfig:
    """dump_config serializes back to a dict (round-trip)."""

    def test_dump_entry(self):
        entry = Entry(id="foo", name="Foo")
        d = dump_config(entry)
        assert d == {"id": "foo", "name": "Foo"}

    def test_dump_tree(self):
        tree = EntryTree()
        tree.add(Entry(id="a"))
        tree.add(Entry(id="b"))
        d = dump_config(tree)
        assert d == {"entries": [{"id": "a"}, {"id": "b"}]}

    def test_dump_list(self):
        entries = [Entry(id="a"), Entry(id="b")]
        d = dump_config(entries)
        assert d == {"entries": [{"id": "a"}, {"id": "b"}]}

    def test_round_trip_dict(self):
        original = [
            {"id": "a", "name": "A", "config": {"k": 1}},
            {"id": "b", "inject": ["a"]},
        ]
        tree = load_config(original)
        d = dump_config(tree)
        assert d == {"entries": original}

    def test_dump_invalid_type_raises(self):
        with pytest.raises(TypeError):
            dump_config("not a tree")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Bundle / merge_bundles
# ---------------------------------------------------------------------------


class TestBundle:
    """Bundle is a named group of entries; merge_bundles overlays them."""

    def test_create_bundle(self):
        bundle = Bundle(name="b1", entries=[Entry(id="a")])
        assert bundle.name == "b1"
        assert len(bundle.entries) == 1

    def test_merge_bundles_concatenates(self):
        b1 = Bundle(name="b1", entries=[Entry(id="a")])
        b2 = Bundle(name="b2", entries=[Entry(id="b")])
        tree = merge_bundles(b1, b2)
        assert len(tree.entries) == 2
        assert tree.find("a") is not None
        assert tree.find("b") is not None

    def test_merge_overrides_same_id(self):
        b1 = Bundle(name="b1", entries=[Entry(id="a", name="first")])
        b2 = Bundle(name="b2", entries=[Entry(id="a", name="second")])
        tree = merge_bundles(b1, b2)
        # The later bundle's entry wins (replaces)
        entry = tree.find("a")
        assert entry is not None
        assert entry.name == "second"


# ---------------------------------------------------------------------------
# Loader facade
# ---------------------------------------------------------------------------


class TestLoader:
    """Loader is the high-level facade combining parse + interpolate."""

    def test_load_dict_with_interpolation(self):
        loader = Loader({"name": "world"})
        tree = loader.load({"id": "greeting", "config": {"msg": "hello ${name}"}})
        entry = tree.entries[0]
        assert entry.config == {"msg": "hello world"}

    def test_load_yaml_with_interpolation(self, tmp_path: Path):
        yaml_path = tmp_path / "config.yaml"
        yaml_path.write_text("- id: x\n  config:\n    msg: hi ${ENV.USER}\n")
        loader = Loader()
        tree = loader.load_yaml(str(yaml_path))
        # ENV.USER might not be set; interpolation leaves it as-is.
        # At minimum the loader should not crash.
        assert len(tree.entries) == 1

    def test_with_scope(self):
        loader = Loader({"a": 1})
        child = loader.with_scope({"b": 2})
        assert child.scope["a"] == 1
        assert child.scope["b"] == 2

    def test_dump_round_trip(self):
        loader = Loader({"x": "val"})
        tree = loader.load([{"id": "foo", "config": {"k": "${x}"}}])
        d = loader.dump(tree)
        assert d["entries"][0]["config"]["k"] == "val"

    def test_from_internal(self):
        loader = Loader.from_internal()
        assert loader is not None


# ---------------------------------------------------------------------------
# Coverage: edge branches / fallback paths not hit by happy-path tests
# ---------------------------------------------------------------------------


class TestEntrySetitemBranches:
    """Entry.__setitem__ branches for known fields."""

    def test_setitem_id(self):
        e = Entry(id="old")
        e["id"] = "new"
        assert e.id == "new"

    def test_setitem_name(self):
        e = Entry(id="x")
        e["name"] = "X"
        assert e.name == "X"

    def test_setitem_config(self):
        e = Entry(id="x")
        e["config"] = {"k": 1}
        assert e.config == {"k": 1}

    def test_setitem_disabled(self):
        e = Entry(id="x")
        e["disabled"] = True
        assert e.disabled is True

    def test_setitem_inject(self):
        e = Entry(id="x")
        e["inject"] = ["a"]
        assert e.inject == ["a"]


class TestEntryGroupGetitem:
    """EntryGroup.__getitem__ returns key/entries or None for unknown."""

    def test_getitem_key(self):
        g = EntryGroup(key="k", entries=[])
        assert g["key"] == "k"

    def test_getitem_entries(self):
        e = Entry(id="a")
        g = EntryGroup(key="k", entries=[e])
        assert g["entries"] == [e]

    def test_getitem_unknown_returns_none(self):
        g = EntryGroup(key="k", entries=[])
        assert g["unknown"] is None


class TestInterpolateNoneScope:
    """interpolate() defaults scope to empty dict when None is passed."""

    def test_none_scope_string_passes_through(self):
        # String with no tokens: same as before, but exercises scope=None branch.
        assert interpolate("plain text", None) == "plain text"

    def test_none_scope_keeps_unknown_tokens(self):
        # ${x} is unknown, no scope supplied → left as-is.
        assert interpolate("${x}", None) == "${x}"


class TestParseEntryExtraFields:
    """_parse_entry captures fields outside the known schema into ``extra``."""

    def test_extra_fields_captured(self):
        tree = load_config([{"id": "x", "weird_field": "hello", "n": 42}])
        entry = tree.find("x")
        assert entry is not None
        assert entry.extra == {"weird_field": "hello", "n": 42}


class TestLoadConfigInvalidEntry:
    """load_config raises ValueError for non-Mapping entries inside a list."""

    def test_non_dict_in_list_raises(self):
        with pytest.raises(ValueError, match="entry must be a dict"):
            load_config([{"id": "x"}, "not-a-dict"])  # type: ignore[list-item]


class TestBundleToDict:
    """Bundle.to_dict serializes name + entries."""

    def test_to_dict_round_trip(self):
        b = Bundle(name="b1", entries=[Entry(id="a", name="A")])
        assert b.to_dict() == {
            "name": "b1",
            "entries": [{"id": "a", "name": "A"}],
        }

    def test_to_dict_empty(self):
        b = Bundle(name="empty")
        assert b.to_dict() == {"name": "empty", "entries": []}


__all__ = [
    "TestEntry",
    "TestEntryGroup",
    "TestEntryTree",
    "TestInterpolate",
    "TestIsolate",
    "TestLoadConfig",
    "TestLoadYaml",
    "TestDumpConfig",
    "TestBundle",
    "TestLoader",
    "TestEntrySetitemBranches",
    "TestEntryGroupGetitem",
    "TestInterpolateNoneScope",
    "TestParseEntryExtraFields",
    "TestLoadConfigInvalidEntry",
    "TestBundleToDict",
]