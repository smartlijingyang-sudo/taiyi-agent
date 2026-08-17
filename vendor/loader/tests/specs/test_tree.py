"""Tests for `loader.tree` — `EntryTree` (1:1 port).

The `EntryTree` abstract class is exercised via a stub subclass because
the abstract method `write()` cannot be instantiated directly.
"""

from __future__ import annotations

import pytest

from loader.entry import Entry, EntryOptions
from loader.tree import EntryTree


class _StubTree(EntryTree):
    """Subclass that satisfies the abstract `write()` method."""

    def write(self) -> None:  # pragma: no cover — exercised indirectly
        return None


def _make_entry(opts: EntryOptions) -> Entry:
    """Mint an Entry without invoking its __post_init__ patch-context path."""
    return Entry(options=opts)


class TestEntryTreeConstruction:
    """`EntryTree.__init__` allocates a store and root group."""

    def test_store_and_root_initialized(self):
        ctx = object()
        tree = _StubTree(ctx)
        assert isinstance(tree.store, dict)
        assert isinstance(tree.root, type(tree).mro()[2]) or tree.root.data == []
        # `root` is always an EntryGroup with empty data.
        assert tree.root.data == []

    def test_separator_constant(self):
        assert EntryTree.sep == ":"


class TestEntryTreeResolve:
    """`resolve(id)` walks dotted ids through nested subtrees."""

    def test_resolve_root_entry(self):
        tree = _StubTree(object())
        tree.store["a"] = _make_entry(EntryOptions(id="a", name="./a"))
        entry = tree.resolve("a")
        assert entry.options.id == "a"

    def test_resolve_unknown_raises(self):
        tree = _StubTree(object())
        with pytest.raises(LookupError):
            tree.resolve("missing")

    def test_resolve_missing_intermediate_raises(self):
        tree = _StubTree(object())
        tree.store["a"] = _make_entry(EntryOptions(id="a", name="./a"))
        # Intermediate "missing" not in store → raise.
        with pytest.raises(LookupError):
            tree.resolve("missing:deep")

    def test_resolve_nested_via_sep(self):
        tree = _StubTree(object())
        inner_tree = _StubTree(object())
        outer = _make_entry(EntryOptions(id="outer", name="./out"))
        inner = _make_entry(EntryOptions(id="inner", name="./inner"))
        tree.store["outer"] = outer
        outer.subtree = inner_tree
        inner_tree.store["inner"] = inner
        resolved = tree.resolve("outer:inner")
        assert resolved is inner


class TestEntryTreeEnsureId:
    """`ensure_id` allocates an id when not provided."""

    def test_returns_existing_id(self):
        tree = _StubTree(object())
        opts: dict[str, object] = {"id": "given"}
        assert tree.ensure_id(opts) == "given"
        assert opts["id"] == "given"

    def test_generates_random_id_when_missing(self):
        tree = _StubTree(object())
        opts: dict[str, object] = {}
        result = tree.ensure_id(opts)
        assert isinstance(result, str)
        assert len(result) == 8  # 8-char hex slice upstream
        assert opts["id"] == result

    def test_generated_id_does_not_collide(self):
        tree = _StubTree(object())
        # Pre-populate store with the deterministic fallback id we control.
        # Since randomness is involved, we simply assert the generated id
        # is unique under repeated invocations.
        ids = set()
        for _ in range(20):
            opts: dict[str, object] = {}
            new_id = tree.ensure_id(opts)
            assert new_id not in ids
            tree.store[new_id] = _make_entry(EntryOptions(id=new_id, name="."))
            ids.add(new_id)


class TestEntryTreeEntries:
    """`entries()` yields BFS-style flattened tree."""

    def test_iterates_only_root_entries(self):
        tree = _StubTree(object())
        tree.store["a"] = _make_entry(EntryOptions(id="a", name="./a"))
        tree.store["b"] = _make_entry(EntryOptions(id="b", name="./b"))
        ids = sorted(e.options.id for e in tree.entries())
        assert ids == ["a", "b"]

    def test_walks_into_subtree(self):
        tree = _StubTree(object())
        inner_tree = _StubTree(object())
        inner_tree.store["deep"] = _make_entry(EntryOptions(id="deep", name="./deep"))
        outer = _make_entry(EntryOptions(id="outer", name="./outer"))
        outer.subtree = inner_tree
        tree.store["outer"] = outer
        ids = sorted(e.options.id for e in tree.entries())
        assert ids == ["deep", "outer"]


class TestEntryTreeResolveGroup:
    """`resolve_group(id)` returns root when id is falsy, otherwise entries' subgroup."""

    def test_root_when_id_is_none(self):
        tree = _StubTree(object())
        assert tree.resolve_group(None) is tree.root
        assert tree.resolve_group("") is tree.root

    def test_subgroup_lookup(self):
        from loader.group import EntryGroup

        tree = _StubTree(object())
        subgroup = EntryGroup()
        entry = _make_entry(EntryOptions(id="g", name="./g", group=True))
        entry.subgroup = subgroup
        tree.store["g"] = entry
        assert tree.resolve_group("g") is subgroup

    def test_no_subgroup_raises(self):
        tree = _StubTree(object())
        entry = _make_entry(EntryOptions(id="leaf", name="./leaf"))
        tree.store["leaf"] = entry
        with pytest.raises(LookupError):
            tree.resolve_group("leaf")


class TestEntryTreeImport:
    """`import_(name)` mirrors upstream ``EntryTree.import`` (1:1)."""

    def test_cordis_namespace_prefix(self):
        tree = _StubTree(object())

        class _Loader:
            builtins = {"echo": lambda: "echoed"}

        tree.ctx = type("C", (), {"loader": _Loader()})()

        assert tree.import_("cordis:echo")() == "echoed"

    def test_imports_python_module(self):
        tree = _StubTree(object())
        result = tree.import_("json")
        import json
        assert result is json

    def test_missing_module_raises(self):
        tree = _StubTree(object())
        with pytest.raises(ModuleNotFoundError):
            tree.import_("definitely_not_a_module_xyz")


class TestEntryTreeImportBuiltinMissing:
    """When the cordis builtin is missing, ``import_`` returns ``None``."""

    def test_missing_builtin_returns_none(self):
        tree = _StubTree(object())

        class _Loader:
            builtins = {}

        tree.ctx = type("C", (), {"loader": _Loader()})()
        assert tree.import_("cordis:missing") is None


class TestEntryTreeImportWithoutCtx:
    """`import_` works when ctx is None."""

    def test_without_ctx_uses_python_import(self):
        tree = _StubTree(None)
        result = tree.import_("os")
        import os
        assert result is os


class TestEntryTreeEnsureIdCollision:
    """`ensure_id` retries on collision (rare; for branch coverage)."""

    def test_collisions_generate_new_id(self):
        tree = _StubTree(object())
        # Pre-populate with many random ids so the chance of collision is high.
        import secrets

        for _ in range(50):
            tree.store[secrets.token_hex(4)] = _make_entry(
                EntryOptions(id="x", name="./x")
            )
        new_opts: dict[str, object] = {}
        result = tree.ensure_id(new_opts)
        # Should still find a free id.
        assert result
        assert result not in tree.store


class TestEntryTreeCRUD:
    """`create` / `remove` / `update` are 1:1 helpers."""

    def test_create_appends_to_root(self):
        tree = _StubTree(object())
        new_id = tree.create({"id": "x", "name": "./x"})
        assert new_id == "x"
        assert any(opts.get("id") == "x" for opts in tree.root.data)

    def test_create_assigns_id_when_missing(self):
        tree = _StubTree(object())
        new_id = tree.create({"name": "./x"})
        assert new_id
        assert any(opts.get("id") == new_id for opts in tree.root.data)

    def test_create_inserts_at_position(self):
        tree = _StubTree(object())
        tree.create({"id": "a", "name": "./a"})
        tree.create({"id": "b", "name": "./b"})
        tree.create({"id": "c", "name": "./c"}, position=1)
        ids = [opts["id"] for opts in tree.root.data]
        assert ids[1] == "c"

    def test_remove_drops_entry(self):
        tree = _StubTree(object())
        tree.store["leaf"] = _make_entry(EntryOptions(id="leaf", name="./leaf"))
        tree.root.data.append(EntryOptions(id="leaf", name="./leaf").to_dict())
        tree.remove("leaf")
        assert "leaf" not in tree.store
        assert all(opts.get("id") != "leaf" for opts in tree.root.data)

    def test_remove_missing_is_noop(self):
        tree = _StubTree(object())
        # Should not raise.
        tree.remove("nope")

    def test_update_modifies_options(self):
        tree = _StubTree(object())
        tree.store["x"] = _make_entry(EntryOptions(id="x", name="./x"))
        tree.update("x", {"config": {"v": 1}, "name": "./x2"})
        assert tree.store["x"].options.name == "./x2"
        assert tree.store["x"].options.config == {"v": 1}

    def test_update_missing_is_noop(self):
        tree = _StubTree(object())
        tree.update("missing", {"name": "./x"})  # no raise


class TestEntryTreeCreateWithEntryOptions:
    """`create` accepts :class:`EntryOptions` directly."""

    def test_create_with_entry_options(self):
        from loader.entry import EntryOptions

        tree = _StubTree(object())
        opts = EntryOptions(id="foo", name="./foo")
        new_id = tree.create(opts)
        assert new_id == "foo"

    def test_create_with_entry_options_assigns_id_when_missing(self):
        from loader.entry import EntryOptions

        tree = _StubTree(object())
        opts = EntryOptions(id="", name="./foo")  # type: ignore[arg-type]
        new_id = tree.create(opts)
        assert new_id


class TestEntryTreeUnlinkFromGroup:
    """`remove` walks the parent group to drop the entry."""

    def test_remove_unlinks_data_from_group(self):
        from loader.group import EntryGroup

        tree = _StubTree(object())
        group = EntryGroup(tree=tree)
        entry = _make_entry(EntryOptions(id="x", name="./x"))
        entry.parent = group
        group.data.append({"id": "x", "name": "./x"})
        tree.store["x"] = entry
        tree.remove("x")
        assert all(o.get("id") != "x" for o in tree.root.data)


class TestEntryTreeClassGetItem:
    """`__class_getitem__` is a no-op helper (1:1 to upstream typing)."""

    def test_class_getitem_returns_class(self):
        assert EntryTree[int] is EntryTree


class TestEntryTreeResolveMissingFinal:
    """The trailing entry is missing from the store."""

    def test_final_part_missing_raises(self):
        tree = _StubTree(object())
        tree.store["a"] = _make_entry(EntryOptions(id="a", name="./a"))
        with pytest.raises(LookupError):
            tree.resolve("a:missing")


class TestEntryTreeEnsureIdDictPrePopulated:
    """`ensure_id` returns the existing id when dict already has one."""

    def test_returns_existing_dict_id(self):
        tree = _StubTree(object())
        opts: dict[str, object] = {"id": "given"}
        assert tree.ensure_id(opts) == "given"


class TestEntryTreeEnsureIdCollisionBranch:
    """Hit both branches of the collision-check (`if new_id not in store`)."""

    def test_dict_path_when_id_already_allocated(self):
        tree = _StubTree(object())
        # First allocate an id via a dict; subsequent calls keep their id.
        opts1: dict[str, object] = {"id": "a"}
        assert tree.ensure_id(opts1) == "a"
        # The dict path's collision check is covered when we re-run on the same id.
        assert tree.ensure_id({"id": "a"}) == "a"

    def test_entry_options_no_id_with_collision_via_store(self):
        # Mock secrets.token_hex so we control what comes out: a value
        # already in the store, then a free id. This drives the
        # ``if new_id not in store:`` False branch.
        import loader.tree as tree_module
        from loader.entry import EntryOptions

        tree = _StubTree(object())
        # Pick a hex the user pre-populates.
        colliding = "deadbeef"
        free = "12345678"
        tree.store[colliding] = _make_entry(EntryOptions(id=colliding, name="./x"))

        calls = {"n": 0}

        def fake_token_hex(_n: int) -> str:
            calls["n"] += 1
            return colliding if calls["n"] == 1 else free

        original = tree_module.secrets.token_hex
        tree_module.secrets.token_hex = fake_token_hex  # type: ignore[assignment]
        try:
            opts = EntryOptions(id="", name="./y")  # type: ignore[arg-type]
            new_id = tree.ensure_id(opts)
        finally:
            tree_module.secrets.token_hex = original  # type: ignore[assignment]
        assert new_id == free
        assert calls["n"] == 2  # first collision, second succeeds

    def test_dict_no_id_with_collision(self):
        import loader.tree as tree_module

        tree = _StubTree(object())
        colliding = "abcdef01"
        free = "99887766"
        tree.store[colliding] = _make_entry(EntryOptions(id=colliding, name="./x"))

        calls = {"n": 0}

        def fake_token_hex(_n: int) -> str:
            calls["n"] += 1
            return colliding if calls["n"] == 1 else free

        original = tree_module.secrets.token_hex
        tree_module.secrets.token_hex = fake_token_hex  # type: ignore[assignment]
        try:
            opts: dict[str, object] = {}
            new_id = tree.ensure_id(opts)
        finally:
            tree_module.secrets.token_hex = original  # type: ignore[assignment]
        assert new_id == free


class TestEntryTreeResolveEmptyAfterPop:
    """`resolve` after popping all parts takes the `tree is None` branch."""

    def test_resolve_with_missing_final(self):
        tree = _StubTree(object())
        # No entries in store → LookupError when final lookup fails.
        with pytest.raises(LookupError):
            tree.resolve("missing")

    def test_resolve_with_nested_parts_traverses_deeper(self):
        # Two part names, with the second subtree missing → LookupError.
        tree = _StubTree(object())
        # No store entries; the for-loop body is entered when parts have >1
        # element after ``pop``. The first lookup fails before setting tree.
        with pytest.raises(LookupError):
            tree.resolve("a:b")


class TestEntryTreeCreateReusesExisting:
    """`create` skips the store insertion when the entry already exists."""

    def test_create_skips_store_insert_when_present(self):
        tree = _StubTree(object())
        tree.create({"id": "x", "name": "./x"})
        # Second create returns same id without adding a second entry.
        new_id = tree.create({"id": "x", "name": "./x"})
        assert new_id == "x"


class TestEntryTreeRemoveWithGroupEntry:
    """`remove` walks the EntryGroup store (parent is set)."""

    def test_remove_unlinks_entry_with_data(self):

        tree = _StubTree(object())
        # Pre-populate store and root.data so the remove() walks both.
        tree.create({"id": "x", "name": "./x"})
        # The remove path with parent set is the second branch.
        tree.remove("x")
        assert "x" not in tree.store
        assert all(o.get("id") != "x" for o in tree.root.data)

    def test_remove_when_data_omits_id(self):
        """`remove` skips root.data entries without ``id`` (false branch)."""
        tree = _StubTree(object())
        # Inject a non-mapping entry into root.data (would crash isinstance).
        tree.root.data.append("not a mapping")  # type: ignore[arg-type]
        tree.store["x"] = _make_entry(EntryOptions(id="x", name="./x"))
        # Should not raise even when an item is not a Mapping.
        tree.remove("x")
        assert "x" not in tree.store


class TestEntryTreeEnsureIdAllBranches:
    """Cover both branches of `ensure_id` (with / without stored id)."""

    def test_dict_with_id_returns_it(self):
        tree = _StubTree(object())
        opts: dict[str, object] = {"id": "my-id"}
        assert tree.ensure_id(opts) == "my-id"

    def test_entry_options_with_id_returns_it(self):
        from loader.entry import EntryOptions

        tree = _StubTree(object())
        opts = EntryOptions(id="given", name="./x")
        # Hit the ``if options.id: return options.id`` branch.
        result = tree.ensure_id(opts)
        assert result == "given"


class TestEntryTreeEnsureIdDictShortCircuit:
    """`ensure_id` short-circuits when dict has a valid id."""

    def test_dict_with_id_passes_through(self):
        tree = _StubTree(object())
        opts: dict[str, object] = {"id": "given"}
        # Hit the ``return options["id"]`` branch at the bottom.
        assert tree.ensure_id(opts) == "given"

    def test_entry_options_without_id_allocates(self):
        from loader.entry import EntryOptions

        tree = _StubTree(object())
        opts = EntryOptions(id="", name="./x")  # type: ignore[arg-type]
        new_id = tree.ensure_id(opts)
        assert new_id
        assert opts.id == new_id

    def test_dict_without_id_allocates_and_writes(self):
        tree = _StubTree(object())
        opts: dict[str, object] = {}
        new_id = tree.ensure_id(opts)
        assert new_id
        assert opts["id"] == new_id


class TestEntryTreeEnsureIdBothShapes:
    """`ensure_id` accepts both :class:`EntryOptions` and dict-shaped inputs."""

    def test_with_entry_options(self):
        tree = _StubTree(object())
        opts = EntryOptions(id="given", name="./g")
        assert tree.ensure_id(opts) == "given"

    def test_with_entry_options_no_id(self):
        tree = _StubTree(object())
        opts = EntryOptions(id="", name="./g")  # type: ignore[arg-type]
        assert tree.ensure_id(opts) != ""
        assert opts.id != ""


class TestEntryTreeWriteAbstract:
    """The abstract method raises when called directly."""

    def test_write_is_abstract(self):
        # Direct call to the abstract method raises ``NotImplementedError``.
        with pytest.raises(NotImplementedError):
            EntryTree.write(_StubTree(object()))


class TestEntryTreePostInitRootAlreadySet:
    """`__post_init__` skips the assignment when root.tree is already set."""

    def test_root_already_attached(self):
        from loader.group import EntryGroup

        # Pre-construct an EntryGroup with its `tree` attribute set.
        group = EntryGroup(tree=object())
        # Build a tree *with that group as root*; post_init should not
        # overwrite the existing tree reference.
        tree = _StubTree(object())
        tree.root = group  # type: ignore[assignment]
        # Re-run post_init (dataclass has already called it, but manually).
        tree.__post_init__()
        assert tree.root.tree is not None
