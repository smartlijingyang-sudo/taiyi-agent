"""Tests for `loader.group` — `EntryGroup` (1:1 port).

The dataclass form keeps the data fields identical to TS; lifecycle
methods (`create`/`update`/`stop`/`remove`/`unlink`) are exercised under
the `loader.load` flow and tested there.
"""

from __future__ import annotations

from loader.entry import Entry, EntryOptions
from loader.group import EntryGroup


class TestEntryGroupConstruction:
    """Construction sets ``data`` to an empty list and accepts a tree."""

    def test_default(self):
        group = EntryGroup()
        assert group.data == []

    def test_with_tree(self):
        tree = object()  # The Group class accepts any ``tree`` argument.
        group = EntryGroup(tree=tree)
        assert group.tree is tree
        assert group.data == []


class TestEntryGroupUnlink:
    """`unlink` removes a specific options object from `data`."""

    def test_unlink_existing(self):
        group = EntryGroup()
        a = EntryOptions(id="a", name="./a")
        b = EntryOptions(id="b", name="./b")
        group.data.extend([a, b])
        group.unlink(a)
        assert group.data == [b]

    def test_unlink_missing_is_noop(self):
        group = EntryGroup()
        a = EntryOptions(id="a", name="./a")
        group.unlink(a)  # no raise
        assert group.data == []


class TestEntryGroupCreate:
    """`create` mirrors the upstream ``EntryGroup.create`` helper."""

    def test_create_assigns_id_via_ensure_id(self):

        group = EntryGroup(tree=object())
        opts = EntryOptions(id="a", name="./x")
        store: dict = {}
        loader = object()
        ctx = object()
        new_id = group.create(
            opts,
            ensure_id=lambda o: o.id,  # passthrough of id
            loader=loader,
            ctx=ctx,
            store=store,
        )
        assert new_id == "a"
        assert "a" in store
        assert isinstance(store["a"], Entry)

    def test_create_assigns_id_when_missing(self):
        group = EntryGroup(tree=object())
        opts = EntryOptions(id="", name="./x")  # type: ignore[arg-type]
        store: dict = {}
        new_id = group.create(
            opts,
            ensure_id=lambda o: o.id or "fallback",
            loader=object(),
            ctx=object(),
            store=store,
        )
        assert new_id == "fallback"

    def test_create_falls_back_when_args_missing(self):
        group = EntryGroup(tree=object())
        opts = EntryOptions(id="a", name="./a")
        # When ensure_id / loader / ctx / store are None, just return id.
        assert group.create(opts) == "a"


class TestEntryGroupUpdate:
    """`update` replaces `data` with the new config list."""

    def test_update_replaces_data(self):
        group = EntryGroup()
        old = [EntryOptions(id="a", name="./a")]
        new = [EntryOptions(id="b", name="./b")]
        group.update(new)
        assert group.data == new
        # Old list reference is not mutated.
        assert old == [EntryOptions(id="a", name="./a")]

    def test_update_accepts_empty(self):
        group = EntryGroup()
        group.update([])
        assert group.data == []


class TestEntryGroupStop:
    """`stop` clears `data`."""

    def test_stop_clears(self):
        group = EntryGroup()
        group.data.append(EntryOptions(id="a", name="./a"))
        group.stop()
        assert group.data == []


class TestEntryGroupCreateExisting:
    """`create` reuses an entry that already exists in the store."""

    def test_create_reuses_existing_entry(self):

        group = EntryGroup(tree=object())
        opts_a = EntryOptions(id="a", name="./a")
        opts_b = EntryOptions(id="a", name="./a-new")  # same id, different content
        store: dict = {}
        # First create.
        group.create(
            opts_a,
            ensure_id=lambda o: o.id,
            loader=object(),
            ctx=object(),
            store=store,
        )
        existing = store["a"]
        assert isinstance(existing, Entry)
        # Second create reuses the existing entry (id collisions update existing).
        new_id = group.create(
            opts_b,
            ensure_id=lambda o: o.id,
            loader=object(),
            ctx=object(),
            store=store,
        )
        assert new_id == "a"


class TestGroupInit:
    """`Group.__init__` mirrors upstream `static initial = []` behaviour."""

    def test_default_initial(self):
        from loader.group import Group

        g = Group()
        assert g.data == []
        assert g.initial == []

    def test_with_explicit_config(self):
        from loader.entry import EntryOptions
        from loader.group import Group

        g = Group(config=[EntryOptions(id="a", name="./a")])
        assert g.data == [EntryOptions(id="a", name="./a")]

    def test_with_tree_argument(self):
        from loader.group import Group

        g = Group(tree=object())
        assert g.tree is not None


class TestEntryGroupStaticMembers:
    """`Group` is a subclass of `EntryGroup` with class-level defaults."""

    def test_group_class_inherits_entry_group(self):
        from loader.group import Group

        assert issubclass(Group, EntryGroup)

    def test_group_initial_is_empty(self):
        from loader.group import Group

        assert Group.initial == []

    def test_group_key_marker_truthy(self):
        # Upstream uses `[EntryGroup.key] = true` so consumers can check
        # ``plugin[EntryGroup.key]`` to detect group plugins.
        from loader.group import Group

        assert bool(getattr(Group, "key", False)) is True
