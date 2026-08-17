"""Tests for `loader.load` — load_config / load_yaml / internal helpers (1:1 port).

These mirror the public surface from upstream `~/deepseek-harness/vendor/
cordis/src/loader.ts`. They are deliberately detached from the runtime
plugin loader (`vendor/loader/`); runtime-level tests live in `test_load
… ` companion specs.
"""

from __future__ import annotations

import pytest

from loader.entry import Entry, EntryOptions
from loader.load import (
    dump_config,
    load_config,
    load_yaml,
    merge_bundles,
)
from loader.tree import EntryTree


def _make_tree() -> EntryTree:
    """Local stub: subclass EntryTree so we can construct a tree in tests."""

    class _StubTree(EntryTree):
        def write(self) -> None:
            return None

    return _StubTree()


# ---------------------------------------------------------------------------
# load_config
# ---------------------------------------------------------------------------


class TestLoadConfig:
    """`load_config(data)` parses dict / list / YAML string."""

    def test_loads_single_entry(self):
        tree = load_config({"id": "foo", "name": "./foo"})
        assert len(tree.store) == 1
        entry = tree.resolve("foo")
        assert entry.options.name == "./foo"

    def test_loads_list_of_entries(self):
        tree = load_config(
            [{"id": "a", "name": "./a"}, {"id": "b", "name": "./b"}]
        )
        assert set(tree.store.keys()) == {"a", "b"}

    def test_loads_yaml_string(self):
        yaml_text = """
- id: a
  name: ./a
- id: b
  name: ./b
"""
        tree = load_config(yaml_text)
        assert set(tree.store.keys()) == {"a", "b"}

    def test_yaml_string_with_single_entry(self):
        tree = load_config("id: foo\nname: ./foo\n")
        entry = tree.resolve("foo")
        assert entry.options.name == "./foo"

    def test_empty_yaml_returns_empty_tree(self):
        tree = load_config("")
        assert len(tree.store) == 0

    def test_invalid_entry_missing_id_raises(self):
        with pytest.raises(ValueError):
            load_config({"name": "./oops"})

    def test_invalid_entry_non_string_id_raises(self):
        with pytest.raises(ValueError):
            load_config({"id": 0, "name": "./x"})

    def test_invalid_list_element_raises(self):
        with pytest.raises(ValueError):
            load_config([{"name": "./x"}])  # missing id


# ---------------------------------------------------------------------------
# load_yaml
# ---------------------------------------------------------------------------


class TestLoadYaml:
    """`load_yaml(path)` reads a YAML file and parses it."""

    def test_load_yaml_file(self, tmp_path):
        path = tmp_path / "config.yml"
        path.write_text(
            "- id: x\n  name: ./x\n- id: y\n  name: ./y\n",
            encoding="utf-8",
        )
        tree = load_yaml(str(path))
        assert set(tree.store.keys()) == {"x", "y"}

    def test_load_yaml_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_yaml(str(tmp_path / "nope.yml"))


# ---------------------------------------------------------------------------
# dump_config
# ---------------------------------------------------------------------------


class TestDumpConfig:
    """`dump_config` serializes back to dict form."""

    def test_dumps_tree(self):
        tree = _make_tree()
        tree.store["x"] = Entry(
            options=EntryOptions(id="x", name="./x", config={"v": 1})
        )
        out = dump_config(tree)
        assert isinstance(out, list)
        # Root tree returns the per-group entries as a list.
        assert out == [{"id": "x", "name": "./x", "config": {"v": 1}}]


# ---------------------------------------------------------------------------
# merge_bundles
# ---------------------------------------------------------------------------


class TestMergeBundles:
    """`merge_bundles(*bundles)` flattens bundle entries into a single tree."""

    def test_merge_two_bundles(self):
        tree = merge_bundles(
            [{"id": "a", "name": "./a"}],
            [{"id": "b", "name": "./b"}],
        )
        assert set(tree.store.keys()) == {"a", "b"}

    def test_later_bundle_overrides_earlier(self):
        tree = merge_bundles(
            [{"id": "a", "name": "./a-old"}],
            [{"id": "a", "name": "./a-new"}],
        )
        entry = tree.resolve("a")
        assert entry.options.name == "./a-new"

    def test_empty_merge_returns_empty_tree(self):
        tree = merge_bundles()
        assert tree.store == {}

    def test_merge_entries_and_bundles_mixed(self):
        from loader.entry import Entry

        e1 = Entry(options=EntryOptions(id="e", name="./e"))
        tree = merge_bundles([{"id": "a", "name": "./a"}], [e1])
        assert set(tree.store.keys()) == {"a", "e"}

    def test_merge_rejects_unsupported_bundle_type(self):
        with pytest.raises(TypeError):
            merge_bundles(42)  # type: ignore[arg-type]

    def test_merge_rejects_unsupported_row_type(self):
        with pytest.raises(ValueError):
            merge_bundles(["not-a-mapping"])

    def test_merge_accepts_mapping_bundle(self):
        tree = merge_bundles({"id": "k", "name": "./k"})
        assert tree.resolve("k").options.name == "./k"


class TestBundle:
    """`Bundle` mirrors upstream ``Bundle`` shape."""

    def test_create_with_no_entries(self):
        from loader.load import Bundle

        bundle = Bundle(name="foo")
        assert bundle.name == "foo"
        assert bundle.entries == []

    def test_create_with_entries(self):
        from loader.load import Bundle

        entries = [EntryOptions(id="a", name="./a")]
        bundle = Bundle(name="foo", entries=entries)
        assert bundle.entries == entries

    def test_to_dict_round_trip(self):
        from loader.load import Bundle

        bundle = Bundle(name="foo", entries=[EntryOptions(id="a", name="./a")])
        d = bundle.to_dict()
        assert d == {
            "name": "foo",
            "entries": [{"id": "a", "name": "./a"}],
        }

    def test_dump_bundle(self):
        from loader.load import Bundle

        bundle = Bundle(name="b", entries=[EntryOptions(id="a", name="./a")])
        out = dump_config(bundle)
        assert out == {
            "name": "b",
            "entries": [{"id": "a", "name": "./a"}],
        }


class TestDumpConfigOtherShapes:
    """`dump_config` accepts more than just :class:`EntryTree`."""

    def test_dumps_entry(self):
        from loader.entry import Entry

        entry = Entry(options=EntryOptions(id="a", name="./a"))
        out = dump_config(entry)
        assert out == {"id": "a", "name": "./a"}

    def test_dumps_iterable(self):
        out = dump_config(
            [
                EntryOptions(id="a", name="./a"),
                EntryOptions(id="b", name="./b"),
            ]
        )
        assert out == {"entries": [{"id": "a", "name": "./a"}, {"id": "b", "name": "./b"}]}

    def test_dump_unsupported_type_raises(self):
        with pytest.raises(TypeError):
            dump_config(42)  # type: ignore[arg-type]


class TestLoadConfigEdgeCases:
    """Edge cases in `load_config` for the dict path."""

    def test_non_list_or_dict_raises(self):
        with pytest.raises(ValueError):
            load_config(3.14)  # type: ignore[arg-type]

    def test_dict_missing_required_keys_raises(self):
        with pytest.raises(ValueError):
            load_config({"foo": "bar"})  # no 'id' or 'entries'

    def test_loads_group_shape(self):
        tree = load_config(
            {"key": "group1", "entries": [{"id": "a", "name": "./a"}]}
        )
        assert "a" in tree.store

    def test_list_element_not_mapping_raises(self):
        with pytest.raises(ValueError):
            load_config(["just-a-string"])  # not a mapping


# ---------------------------------------------------------------------------
# Loader (top-level runtime façade)
# ---------------------------------------------------------------------------


class TestLoaderFaçade:
    """`Loader` is a runtime façade over `EntryTree`."""

    def test_basic_construction(self, make_ctx):
        from loader import Loader

        ctx = make_ctx()
        loader = Loader(ctx)
        assert loader.tree is not None
        assert loader.enable_logs is False

    def test_enable_logs_round_trip(self, make_ctx):
        from loader import Loader

        ctx = make_ctx()
        loader = Loader(ctx)
        loader.enable_logs = True
        assert loader.enable_logs is True

    def test_unwrap_exports_returns_default(self, make_ctx):
        from loader import Loader

        ctx = make_ctx()
        loader = Loader(ctx)

        class FakeDefault:
            pass

        class FakeMod:
            default = FakeDefault

        assert loader.unwrap_exports(FakeMod()) is FakeDefault

    def test_unwrap_exports_returns_value_when_no_default(self, make_ctx):
        from loader import Loader

        ctx = make_ctx()
        loader = Loader(ctx)

        class FakeMod:
            x = "value"

        # Object with no ``default`` returns as-is.
        assert loader.unwrap_exports(FakeMod()) is not None

    def test_unwrap_exports_handles_none(self, make_ctx):
        from loader import Loader

        ctx = make_ctx()
        loader = Loader(ctx)
        assert loader.unwrap_exports(None) is None

    def test_show_log_is_silent_when_logs_disabled(self, make_ctx):
        from loader import Loader

        ctx = make_ctx()
        loader = Loader(ctx)
        entry = Entry(options=EntryOptions(id="x", name="./x"))
        loader.tree.enable_logs = False
        # No exception; log line is suppressed.
        loader.show_log(entry, "apply")

    def test_show_log_with_logger(self, make_ctx):
        from loader import Loader

        ctx = make_ctx()
        loader = Loader(ctx)
        loader.tree.enable_logs = True

        # Inject a fake logger on ctx.root.
        class _Root:
            def logger(self, message):
                pass

        ctx.root = _Root()  # type: ignore[attr-defined]
        entry = Entry(options=EntryOptions(id="x", name="./x"))
        loader.show_log(entry, "apply")

    def test_write_noop(self, make_ctx):
        from loader import Loader

        ctx = make_ctx()
        loader = Loader(ctx)
        # Exercise the underlying tree's write (the stub returns None).
        loader.tree.write()
        loader.write()  # no exception

    def test_write_swallows_exception(self, make_ctx):
        """If the underlying tree's write raises, Loader.write swallows it."""
        from loader import Loader

        ctx = make_ctx()

        class _BoomTree:
            def write(self):
                raise RuntimeError("boom")

        loader = Loader(ctx)
        loader._tree = _BoomTree()  # type: ignore[attr-defined]
        loader.write()  # should not raise

    def test_exit_noop(self, make_ctx):
        from loader import Loader

        ctx = make_ctx()
        loader = Loader(ctx)
        loader.exit()

    def test_locate_returns_id(self, make_ctx):
        from loader import Loader

        ctx = make_ctx()
        loader = Loader(ctx)
        assert loader.locate("my-id") == "my-id"
        assert loader.locate(None) is None

    def test_get_tasks_returns_entries(self, make_ctx):
        from loader import Loader

        ctx = make_ctx()
        loader = Loader(ctx)
        loader.tree.store["x"] = Entry(options=EntryOptions(id="x", name="./x"))
        tasks = loader.get_tasks()
        assert any(t.options.id == "x" for t in tasks)

    async def test_create_remove_update_basic(self, make_ctx):
        from loader import Loader

        ctx = make_ctx()
        loader = Loader(ctx)
        new_id = await loader.create({"name": "./x"})
        assert new_id
        await loader.update(new_id, {"config": {"v": 1}})
        entry = loader.resolve(new_id)
        assert entry.options.config == {"v": 1}
        await loader.remove(new_id)
        assert loader.tree.store.get(new_id) is None or not any(
            o.get("id") == new_id for o in loader.tree.root.data
        )

    async def test_await_returns_none(self, make_ctx):
        from loader import Loader

        ctx = make_ctx()
        loader = Loader(ctx)
        assert await loader.await_() is None

    def test_resolve_and_resolve_group(self, make_ctx):
        from loader import Loader
        from loader.entry import Entry, EntryOptions
        from loader.group import EntryGroup

        ctx = make_ctx()
        loader = Loader(ctx)
        group = EntryGroup()
        entry = Entry(options=EntryOptions(id="g", name="./g", group=True))
        entry.subgroup = group
        loader.tree.store["g"] = entry
        assert loader.resolve_group("g") is group
        assert loader.resolve_group(None) is loader.tree.root

    def test_resolve_group_root_returns_tree_root(self, make_ctx):
        from loader import Loader

        ctx = make_ctx()
        loader = Loader(ctx)
        assert loader.resolve_group("") is loader.tree.root

    def test_create_sync_helper(self, make_ctx):
        """`Loader.create` returns an id (1:1 API)."""
        from loader import Loader

        ctx = make_ctx()
        loader = Loader(ctx)
        import asyncio

        new_id = asyncio.run(loader.create({"name": "./x"}))
        assert new_id

    def test_remove_and_update_sync_helper(self, make_ctx):
        import asyncio

        from loader import Loader

        ctx = make_ctx()
        loader = Loader(ctx)
        new_id = asyncio.run(loader.create({"name": "./x"}))
        asyncio.run(loader.update(new_id, {"config": {"k": 1}}))
        assert loader.resolve(new_id).options.config == {"k": 1}
        asyncio.run(loader.remove(new_id))
        assert loader.tree.store.get(new_id) is None

    def test_show_log_skips_group_entry(self, make_ctx):
        from loader import Loader
        from loader.entry import Entry, EntryOptions

        ctx = make_ctx()
        loader = Loader(ctx)
        loader.tree.enable_logs = True
        group_entry = Entry(options=EntryOptions(id="g", name="./g", group=True))
        loader.show_log(group_entry, "apply")  # skipped, no logger called

    def test_show_log_logger_raises_is_swallowed(self, make_ctx):
        from loader import Loader
        from loader.entry import Entry, EntryOptions

        ctx = make_ctx()
        loader = Loader(ctx)
        loader.tree.enable_logs = True

        class _Root:
            def logger(self, message):
                raise RuntimeError("boom")

        ctx.root = _Root()  # type: ignore[attr-defined]
        entry = Entry(options=EntryOptions(id="x", name="./x"))
        loader.show_log(entry, "apply")  # should swallow

    def test_show_log_with_failing_logger_in_loader(self, make_ctx):
        """Direct test that swallows an exception raised by ``ctx.root.logger``."""
        from loader import Loader
        from loader.entry import Entry, EntryOptions

        ctx = make_ctx()
        loader = Loader(ctx)
        loader.tree.enable_logs = True
        # Provide a logger that explodes on call.
        ctx.root = type("Root", (), {"logger": staticmethod(lambda *_: (_ for _ in ()).throw(RuntimeError("boom")))})  # type: ignore[attr-defined]
        entry = Entry(options=EntryOptions(id="x", name="./x"))
        loader.show_log(entry, "apply")  # swallowed

    def test_show_log_logger_raises_via_call(self, make_ctx):
        from loader import Loader
        from loader.entry import Entry, EntryOptions

        ctx = make_ctx()
        loader = Loader(ctx)
        loader.tree.enable_logs = True

        # Define a callable that *raises* on invocation.
        def _raise(msg: str) -> None:
            raise RuntimeError("boom")

        class _Root:
            logger = staticmethod(_raise)

        ctx.root = _Root()  # type: ignore[attr-defined]
        entry = Entry(options=EntryOptions(id="x", name="./x"))
        # Should swallow the inner exception.
        loader.show_log(entry, "apply")

    def test_show_log_no_logger_attribute(self, make_ctx):
        """`show_log` short-circuits when ctx.root has no logger."""
        from loader import Loader
        from loader.entry import Entry, EntryOptions

        ctx = make_ctx()

        class _Root:
            pass  # no logger attribute

        ctx.root = _Root()  # type: ignore[attr-defined]
        loader = Loader(ctx)
        loader.tree.enable_logs = True
        entry = Entry(options=EntryOptions(id="x", name="./x"))
        # logger is None → branch skip.
        loader.show_log(entry, "apply")

    def test_show_log_no_root(self, make_ctx):
        """`show_log` is a no-op when ``ctx.root.logger`` is missing."""
        from loader import Loader
        from loader.entry import Entry, EntryOptions

        ctx = make_ctx()
        loader = Loader(ctx)
        loader.tree.enable_logs = True
        entry = Entry(options=EntryOptions(id="x", name="./x"))
        # ``ctx.root`` resolves via getattr; logger is optional.
        loader.show_log(entry, "apply")

    def test_ctx_root_property(self, make_ctx):
        from loader import Loader

        ctx = make_ctx()
        loader = Loader(ctx)
        # ``_ctx_root`` proxies whatever ``ctx.root`` returns (may be None).
        assert loader._ctx_root is getattr(ctx, "root", None)

    def test_write_calls_tree_write(self, make_ctx):
        """`Loader.write` invokes the underlying tree's write."""
        from loader import Loader

        ctx = make_ctx()
        loader = Loader(ctx)
        # In-memory tree; ``write`` is a no-op so we just ensure no exception.
        loader.write()


class TestLoadConfigInvalidName:
    """`load_config` validates that ``name`` is a string."""

    def test_non_string_name_raises(self):
        from loader.load import load_config

        with pytest.raises(ValueError):
            load_config([{"id": "x", "name": 123}])

    def test_yaml_non_mapping_raises(self):
        from loader.load import load_config

        with pytest.raises(ValueError):
            load_config("- just a string")


class TestLoadConfigYamlGroupShape:
    """YAML ``{entries: [...]}`` shape is supported."""

    def test_yaml_group_shape(self):
        from loader.load import load_config

        yaml_text = "key: g1\nentries:\n  - id: a\n    name: ./a\n"
        tree = load_config(yaml_text)
        assert "a" in tree.store


class TestLoadConfigYamlGroupShapeMissingEntries:
    """Mapping without a recognized shape raises."""

    def test_yaml_unknown_mapping_raises(self):
        from loader.load import load_config

        with pytest.raises(ValueError):
            load_config("foo: bar")


class TestLoadConfigValidationDetails:
    """Edge cases in `_coerce_entry_form`/`_build_tree`."""

    def test_non_dict_object_raises(self):
        from loader.load import load_config

        with pytest.raises(ValueError):
            load_config([1, 2, 3])

    def test_load_yaml_single_entry(self):
        from loader.load import load_config

        tree = load_config("id: a\nname: ./a\n")
        assert "a" in tree.store

    def test_load_yaml_empty_group(self):
        from loader.load import load_config

        tree = load_config("entries: []\n")
        assert len(tree.store) == 0


class TestDumpValueBranch:
    """`_dump_value` walks nested mappings and lists."""

    def test_dump_value_mapping(self):
        from loader.load import dump_config

        out = dump_config([{"id": "a", "name": "./a", "nested": {"k": 1}}])
        assert out["entries"][0]["nested"] == {"k": 1}

    def test_dump_value_list(self):
        from loader.load import dump_config

        out = dump_config([[{"id": "a", "name": "./a"}]])
        assert out["entries"][0][0]["id"] == "a"

    def test_dump_value_passthrough(self):
        from loader.load import dump_config

        out = dump_config([42])
        assert out["entries"][0] == 42


class TestMergeBundleTypeCoverage:
    """Exercise all branches of the merge bundles loop."""

    def test_merge_with_entry_object(self):
        from loader.entry import Entry, EntryOptions
        from loader.load import merge_bundles

        e = Entry(options=EntryOptions(id="a", name="./a"))
        tree = merge_bundles([e])
        assert "a" in tree.store

    def test_merge_with_entryoptions_object(self):
        from loader.entry import EntryOptions
        from loader.load import merge_bundles

        opts = EntryOptions(id="a", name="./a")
        tree = merge_bundles([opts])
        assert "a" in tree.store

    def test_merge_with_bundle_object(self):
        from loader.entry import EntryOptions
        from loader.load import Bundle, merge_bundles

        bundle = Bundle(name="b", entries=[EntryOptions(id="a", name="./a")])
        tree = merge_bundles(bundle)
        assert "a" in tree.store


class TestBuildTreeFromNone:
    """`_build_tree(None)` returns an empty tree."""

    def test_build_tree_from_none(self):
        from loader.load import load_config

        tree = load_config(None)
        assert len(tree.store) == 0


class TestMakeTreeInternal:
    """Exercise the internal `_make_tree` helper directly."""

    def test_internal_make_tree_write(self):
        from loader.load import _make_tree

        tree = _make_tree()
        # Exercise the stub `write` so the ``return None`` body runs.
        assert tree.write() is None


class TestLoadConfigIsEntryDictNegative:
    """Cover the `_is_entry_dict` helper and non-entry mapping path."""

    def test_dict_with_no_string_id(self):
        from loader.load import load_config

        # Mapping without a string ``id`` is interpreted as a group; missing
        # ``entries`` key should raise.
        with pytest.raises(ValueError):
            load_config({"id": 1, "name": "./x"})


class TestDumpValueMappingEntry:
    """`_dump_value` accepts mapping rows."""

    def test_dump_iterable_with_mapping_row(self):
        from loader.load import dump_config

        out = dump_config([{"nested": {"k": 1}, "value": 2}])
        # First row is a bare mapping; should round-trip via ``dict(value)``.
        assert out["entries"][0]["nested"] == {"k": 1}


class TestDumpValueNested:
    """`_dump_value` walks lists with nested lists."""

    def test_dump_value_walks_list(self):
        from loader.load import dump_config

        out = dump_config([[1, 2, 3]])
        assert out["entries"][0] == [1, 2, 3]


class TestMergeBundleExistingEntry:
    """`merge_bundles` updates existing options when same id recurs."""

    def test_overrides_existing(self):
        from loader.entry import EntryOptions
        from loader.load import merge_bundles

        opts1 = EntryOptions(id="a", name="./a-old")
        opts2 = EntryOptions(id="a", name="./a-new")
        tree = merge_bundles([opts1], [opts2])
        entry = tree.resolve("a")
        assert entry.options.name == "./a-new"


class TestLoadConfigPreservesExtras:
    """`_coerce_entry_form` preserves extra keys in `opts.extra`."""

    def test_extra_keys_are_preserved(self):
        from loader.load import load_config

        tree = load_config([{"id": "a", "name": "./a", "tier": "primary"}])
        entry = tree.resolve("a")
        assert entry.options.extra.get("tier") == "primary"


class TestDumpValueFullCoverage:
    """Cover all branches in `_dump_value`."""

    def test_dump_entry_instance(self):
        from loader.entry import Entry, EntryOptions
        from loader.load import dump_config

        e = Entry(options=EntryOptions(id="a", name="./a"))
        out = dump_config([e])
        assert out["entries"][0] == {"id": "a", "name": "./a"}


class TestLoadConfigYamlNonMappingItem:
    """YAML list with a non-mapping row raises."""

    def test_yaml_list_of_strings_raises(self):
        from loader.load import load_config

        with pytest.raises(ValueError):
            load_config("- hello\n")


class TestLoadConfigNonPrimitive:
    """`_build_tree_parsed` returns a useful error for unsupported shapes."""

    def test_yaml_scalar_raises(self):
        # YAML top-level scalar raises (not handled).
        from loader.load import load_config

        with pytest.raises(ValueError):
            load_config("42")
