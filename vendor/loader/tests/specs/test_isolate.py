"""Tests for `loader.isolate` — Realm classes (1:1 port).

`Realm` is abstract; `LocalRealm` and `GlobalRealm` give concrete suffixes.
"""

from __future__ import annotations

from loader.entry import Entry, EntryOptions
from loader.isolate import GlobalRealm, LocalRealm


def _make_entry() -> Entry:
    return Entry(options=EntryOptions(id="leaf", name="./leaf"))


class TestRealmAccess:
    """`access(key, create=True)` returns symbols keyed by the realm."""

    def test_create_assigns_symbol(self):
        realm = GlobalRealm("shared")
        sym = realm.access("foo", create=True)
        assert isinstance(sym, str)
        # Symbols become string keys in this port; the suffix is appended.
        assert sym.endswith("@shared")

    def test_repeated_access_returns_same_symbol(self):
        realm = GlobalRealm("shared")
        sym1 = realm.access("foo", create=True)
        sym2 = realm.access("foo", create=True)
        assert sym1 == sym2

    def test_lookup_without_create_returns_fresh_symbol(self):
        # Without `create=True`, missing keys produce a transient symbol
        # that does *not* get cached — same as upstream's ?? Symbol().
        realm = GlobalRealm("shared")
        sym = realm.access("missing", False)
        assert sym is not None
        # Should not appear in `store`.
        assert realm.size == 0


class TestRealmDelete:
    """`delete(key)` removes the cached mapping."""

    def test_removes_cached_symbol(self):
        realm = GlobalRealm("shared")
        realm.access("a", create=True)
        assert realm.size == 1
        realm.delete("a")
        assert realm.size == 0

    def test_delete_missing_is_noop(self):
        realm = GlobalRealm("shared")
        realm.delete("not-there")
        assert realm.size == 0


class TestRealmSize:
    """`size` counts cached symbols."""

    def test_empty(self):
        realm = GlobalRealm("empty")
        assert realm.size == 0

    def test_grows_with_unique_keys(self):
        realm = GlobalRealm("grow")
        realm.access("k1", create=True)
        realm.access("k2", create=True)
        assert realm.size == 2


class TestLocalRealmSuffix:
    """`LocalRealm.suffix` references the entry id."""

    def test_suffix_uses_entry_id(self):
        entry = Entry(options=EntryOptions(id="myid", name="./x"))
        realm = LocalRealm(entry)
        assert realm.suffix == "#myid"


class TestGlobalRealmSuffix:
    """`GlobalRealm.suffix` references the label."""

    def test_suffix_uses_label(self):
        realm = GlobalRealm("foo")
        assert realm.suffix == "@foo"

    def test_label_attribute(self):
        realm = GlobalRealm("my-label")
        assert realm.label == "my-label"


class TestIsolateKeyLookup:
    """`isolate_key_lookup` helper used by the runtime isolate plugin."""

    def test_local_label(self):
        from loader.isolate import isolate_key_lookup

        assert isolate_key_lookup(True, "foo") == "local#foo"

    def test_global_string_label(self):
        from loader.isolate import isolate_key_lookup

        assert isolate_key_lookup("shared", "foo") == "global@shared::foo"

    def test_other_returns_none(self):
        from loader.isolate import isolate_key_lookup

        assert isolate_key_lookup(None, "foo") is None
        assert isolate_key_lookup(False, "foo") is None
