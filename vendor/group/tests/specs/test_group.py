"""1:1 tests for ``taiyi-group.service`` — covers the 5 plan-required tests
plus supplementary cases for branch coverage."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import MagicMock

import pytest
from cordis import Context, Entry, EntryGroup, Service

from group.service import (
    GROUP_MARKER,
    Group,
    GroupEntry,
    GroupUpdateError,
    carrier_key_of,
    is_group_carrier,
)

# ---------------------------------------------------------------------------
# Helpers — test doubles for GroupEntry.apply / dispose.
# ---------------------------------------------------------------------------


def _entry(entry_id: str = "e1", name: str | None = None) -> Entry:
    """Build a minimal cordis Entry with sensible defaults."""
    return Entry(id=entry_id, name=name or f"plugin-{entry_id}")


def _hook(events: list[str], label: str) -> Any:
    """Async hook that appends ``label`` to ``events``."""

    async def _hook_impl(_options: Entry) -> None:
        events.append(label)

    return _hook_impl


def _fail_hook(exc: BaseException) -> Any:
    """Async hook that always raises ``exc``."""

    async def _hook_impl(_options: Entry) -> None:
        raise exc

    return _hook_impl


def _fail_after(events: list[str], label: str, exc: BaseException) -> Any:
    """Async hook that succeeds on the first call, then raises ``exc``."""

    state = {"calls": 0}

    async def _hook_impl(_options: Entry) -> None:
        state["calls"] += 1
        if state["calls"] == 1:
            events.append(label)
            return
        raise exc

    return _hook_impl


# ---------------------------------------------------------------------------
# Constants & class-level invariants.
# ---------------------------------------------------------------------------


def test_marker_string_constant_equals_cordis_group() -> None:
    """The marker key mirrors upstream ``Symbol.for('cordis.group')``."""
    assert GROUP_MARKER == "cordis.group"


def test_group_class_marker_matches_constant() -> None:
    """Class attribute matches the module-level constant."""
    assert Group.MARKER == GROUP_MARKER


# ---------------------------------------------------------------------------
# 1) Register creates an EntryGroup (plan-required).
# ---------------------------------------------------------------------------


def test_group_register_creates_entry_group(make_ctx: Context) -> None:
    """Constructing a Group mints an ``EntryGroup`` with the right marker."""
    group = Group(make_ctx)
    try:
        assert isinstance(group.entry_group, EntryGroup)
        assert group.entry_group.key == GROUP_MARKER
        assert group.entries == []
        assert group.is_disposed is False
    finally:
        asyncio.run(group.dispose())


# ---------------------------------------------------------------------------
# 2) Marker key distinct per group (plan-required).
# ---------------------------------------------------------------------------


def test_group_marker_key_distinct_per_group(make_ctx: Context) -> None:
    """Two Groups have distinct marker keys (carrier routing identity)."""
    a = Group(make_ctx)
    b = Group(make_ctx)
    try:
        assert a.marker_key != b.marker_key
        assert carrier_key_of(a) is a.marker_key
        assert carrier_key_of(b) is b.marker_key
        assert is_group_carrier(a) is True
        assert is_group_carrier(b) is True
    finally:
        asyncio.run(a.dispose())
        asyncio.run(b.dispose())


def test_explicit_marker_key_is_respected(make_ctx: Context) -> None:
    """An explicit ``marker_key`` arg is used verbatim."""
    key = ("namespace", "explicit")
    group = Group(make_ctx, marker_key=key)
    try:
        assert group.marker_key == key
        assert carrier_key_of(group) == key
    finally:
        asyncio.run(group.dispose())


def test_carrier_helpers_reject_non_groups() -> None:
    """Carriers are only Group instances, never arbitrary objects."""
    for value in (None, 42, "string", object(), [], {}, Entry(id="x")):
        assert is_group_carrier(value) is False
        assert carrier_key_of(value) is None


def test_carrier_key_deregistered_on_dispose(make_ctx: Context) -> None:
    """Disposed Group no longer reads as a carrier."""
    group = Group(make_ctx)
    key = group.marker_key
    assert carrier_key_of(group) is key
    asyncio.run(group.dispose())
    assert is_group_carrier(group) is False
    assert carrier_key_of(group) is None


# ---------------------------------------------------------------------------
# GroupEntry behaviour — covers the wrapper surface.
# ---------------------------------------------------------------------------


async def test_groupentry_default_apply_is_noop() -> None:
    entry = GroupEntry(options=_entry())
    assert await entry.apply() is None


async def test_groupentry_default_dispose_is_noop() -> None:
    entry = GroupEntry(options=_entry())
    assert await entry.dispose() is None


async def test_groupentry_invokes_async_apply_hook() -> None:
    events: list[str] = []
    entry = GroupEntry(options=_entry(), on_apply=_hook(events, "apply"))
    await entry.apply()
    assert events == ["apply"]


async def test_groupentry_invokes_async_dispose_hook() -> None:
    events: list[str] = []
    entry = GroupEntry(options=_entry(), on_dispose=_hook(events, "dispose"))
    await entry.dispose()
    assert events == ["dispose"]


async def test_groupentry_accepts_sync_callable() -> None:
    """A non-awaitable return value from a sync callable is awaited cleanly."""
    events: list[str] = []

    def _sync_hook(_options: Entry) -> None:
        events.append("apply-sync")

    entry = GroupEntry(options=_entry(), on_apply=_sync_hook)
    await entry.apply()
    assert events == ["apply-sync"]


async def test_groupentry_sync_dispose_hook() -> None:
    """A sync dispose hook that returns nothing is handled without awaiting."""
    events: list[str] = []

    def _sync_dispose(_options: Entry) -> None:
        events.append("dispose-sync")

    entry = GroupEntry(options=_entry(), on_dispose=_sync_dispose)
    await entry.dispose()
    assert events == ["dispose-sync"]


# ---------------------------------------------------------------------------
# 3) Atomic update on success (plan-required).
# ---------------------------------------------------------------------------


async def test_group_update_atomic_on_success(make_ctx: Context) -> None:
    """All entries apply successfully; Group records them in order."""
    events: list[str] = []
    group = Group(make_ctx)
    try:
        entries = [
            GroupEntry(options=_entry("a"), on_apply=_hook(events, "apply:a")),
            GroupEntry(options=_entry("b"), on_apply=_hook(events, "apply:b")),
            GroupEntry(options=_entry("c"), on_apply=_hook(events, "apply:c")),
        ]
        await group.update(entries)
        # All three applies were recorded; rollback never ran.
        assert events == ["apply:a", "apply:b", "apply:c"]
        assert [e.options.id for e in group.entries] == ["a", "b", "c"]
    finally:
        await group.dispose()


async def test_update_accepts_raw_cordis_entries(make_ctx: Context) -> None:
    """Plain ``cordis.Entry`` objects are wrapped into ``GroupEntry``."""
    group = Group(make_ctx)
    try:
        await group.update([_entry("a"), _entry("b")])
        assert [e.options.id for e in group.entries] == ["a", "b"]
    finally:
        await group.dispose()


async def test_update_with_empty_list_clears_existing_entries(make_ctx: Context) -> None:
    """An empty update disposes every previously applied entry (forward order)."""
    events: list[str] = []
    group = Group(make_ctx)
    try:
        await group.update(
            [
                GroupEntry(
                    options=_entry("a"),
                    on_dispose=_hook(events, "dispose:a"),
                ),
                GroupEntry(
                    options=_entry("b"),
                    on_dispose=_hook(events, "dispose:b"),
                ),
            ]
        )
        events.clear()
        await group.update([])
        assert group.entries == []
        # 1:1 with upstream `for (const id of Object.keys(oldMap))` — forward order.
        assert events == ["dispose:a", "dispose:b"]
    finally:
        await group.dispose()


async def test_update_replaces_entries_removing_old_only(make_ctx: Context) -> None:
    """Old entries not present in the new config are disposed (forward order)."""
    events: list[str] = []
    group = Group(make_ctx)
    try:
        await group.update(
            [
                GroupEntry(options=_entry("a"), on_dispose=_hook(events, "dispose:a")),
                GroupEntry(options=_entry("b"), on_dispose=_hook(events, "dispose:b")),
                GroupEntry(options=_entry("c"), on_apply=_hook(events, "apply:c")),
            ]
        )
        events.clear()
        # Drop a, keep c, add d. The re-apply of c re-fires (c is in new).
        await group.update(
            [
                GroupEntry(options=_entry("c"), on_apply=_hook(events, "apply:c")),
                GroupEntry(options=_entry("d"), on_apply=_hook(events, "apply:d")),
            ]
        )
        assert [e.options.id for e in group.entries] == ["c", "d"]
        # The full event trace: c + d apply concurrently, then a + b dispose in forward order.
        assert events[:2] == sorted(["apply:c", "apply:d"])
        assert events[2:] == ["dispose:a", "dispose:b"]
    finally:
        await group.dispose()


# ---------------------------------------------------------------------------
# 4) Update rolls back on failure (plan-required).
# ---------------------------------------------------------------------------


async def test_group_update_rolls_back_on_failure(make_ctx: Context) -> None:
    """One failing entry rolls the whole batch back; original error surfaces."""
    events: list[str] = []
    boom = RuntimeError("simulated apply failure")
    group = Group(make_ctx)
    try:
        entries = [
            GroupEntry(
                options=_entry("a"),
                on_apply=_hook(events, "apply:a"),
                on_dispose=_hook(events, "dispose:a"),
            ),
            GroupEntry(
                options=_entry("b"),
                on_apply=_fail_hook(boom),
                on_dispose=_hook(events, "dispose:b"),
            ),
            GroupEntry(
                options=_entry("c"),
                on_apply=_hook(events, "apply:c"),
                on_dispose=_hook(events, "dispose:c"),
            ),
        ]
        with pytest.raises(GroupUpdateError) as info:
            await group.update(entries)
        # Original failure surfaced.
        assert info.value.original is boom
        assert info.value.rollback_errors == []
        # State restored — no entry remains applied.
        assert group.entries == []
        # Track apply trace (the failed 'b' records no event because its hook
        # raises before appending) and the rollback dispose trace in reverse.
        assert events == [
            "apply:a", "apply:c",
            "dispose:c", "dispose:b", "dispose:a",
        ]
    finally:
        await group.dispose()


async def test_rollback_leaves_pre_existing_entries_intact(make_ctx: Context) -> None:
    """Pre-existing entries are NOT disposed on a failed update."""
    events: list[str] = []
    apply_boom = RuntimeError("apply blew up (second call)")
    new_apply_boom = RuntimeError("apply blew up (new)")

    # Stateful hook: succeeds first call (initial setup), fails subsequent.
    def _flake(_options: Entry):
        state = {"calls": 0}

        async def _impl(_options: Entry) -> None:
            state["calls"] += 1
            if state["calls"] == 1:
                events.append("apply:pre")
                return
            raise apply_boom

        return _impl

    group = Group(make_ctx)
    try:
        # Seed a preexisting entry that succeeds to apply the first time.
        await group.update(
            [GroupEntry(options=_entry("preexisting"), on_apply=_flake(_entry("x")))]
        )
        events.clear()

        # Trigger a rollback — the new entry's apply raises.
        with pytest.raises(GroupUpdateError) as info:
            await group.update(
                [
                    GroupEntry(
                        options=_entry("newok"),
                        on_apply=_hook(events, "apply:newok"),
                        on_dispose=_hook(events, "dispose:newok"),
                    ),
                    GroupEntry(options=_entry("newbad"), on_apply=_fail_hook(new_apply_boom)),
                ]
            )
        # Surface the originating failure (the apply of 'newbad').
        assert info.value.original is new_apply_boom
        # Preexisting is still applied; newbad failed; newok succeeded then was disposed.
        assert "dispose:newok" in events
        assert [e.options.id for e in group.entries] == ["preexisting"]
    finally:
        await group.dispose()


async def test_rollback_collects_dispose_failures(make_ctx: Context) -> None:
    """If rollback dispose itself fails, errors are collected (1:1 with AggregateError)."""
    events: list[str] = []
    dispose_boom = RuntimeError("dispose blew up")
    apply_boom = RuntimeError("apply blew up (after seeding)")

    # Stateful hook: 'preexisting' first apply is OK; subsequent apply raises.
    def _flake():
        state = {"calls": 0}

        async def _impl(_options: Entry) -> None:
            state["calls"] += 1
            if state["calls"] == 1:
                return
            raise apply_boom

        return _impl

    group = Group(make_ctx)
    try:
        # Seed with a pre-existing entry; this also doubles as the rollback
        # re-apply path. Make 'preexisting' fail to re-apply.
        hook = _flake()
        await group.update(
            [
                GroupEntry(options=_entry("preexisting"), on_apply=hook),
                GroupEntry(
                    options=_entry("newentry"),
                    on_dispose=_fail_hook(dispose_boom),
                ),
            ]
        )
        events.clear()

        # Trigger an apply failure during update that requires rollback.
        # 'newentry' has a flaky apply that fails on second call; 'fresh'
        # applies fine but its rollback dispose hits the no-op (no dispose
        # hook). We assert that the re-apply failure shows up in rollback_errors.
        with pytest.raises(GroupUpdateError) as info:
            await group.update(
                [
                    # Re-add 'preexisting' to force a re-apply that fails.
                    GroupEntry(options=_entry("preexisting"), on_apply=hook),
                    GroupEntry(options=_entry("fresh"), on_apply=_hook(events, "apply:fresh")),
                ]
            )
        assert info.value.original is apply_boom
        # The re-apply failure surfaces in rollback_errors.
        assert any(e is apply_boom for e in info.value.rollback_errors)
    finally:
        await group.dispose()


async def test_rollback_collects_dispose_boom_for_new_entries(make_ctx: Context) -> None:
    """A reverse-order dispose of NEW entries that fails is collected (1:1 with AggregateError)."""
    new_dispose_boom = RuntimeError("new dispose boom")
    apply_boom = RuntimeError("apply boom")

    group = Group(make_ctx)
    try:
        # 'dies' fails to apply. 'dies2' applies; on rollback it must be
        # disposed, which raises new_dispose_boom.
        with pytest.raises(GroupUpdateError) as info:
            await group.update(
                [
                    GroupEntry(options=_entry("dies"), on_apply=_fail_hook(apply_boom)),
                    GroupEntry(
                        options=_entry("dies2"),
                        on_apply=_hook([], "apply:dies2"),
                        on_dispose=_fail_hook(new_dispose_boom),
                    ),
                ]
            )
        assert info.value.original is apply_boom
        # The dispose of 'dies2' raised during rollback and was collected.
        assert new_dispose_boom in info.value.rollback_errors
    finally:
        await group.dispose()


async def test_group_update_error_original_is_re_raise_when_no_rollback_failures(
    make_ctx: Context,
) -> None:
    """A clean rollback (no failures) raises GroupUpdateError(original) only."""
    boom = RuntimeError("simulated apply failure")
    group = Group(make_ctx)
    try:
        entries = [
            GroupEntry(options=_entry("bad"), on_apply=_fail_hook(boom)),
        ]
        with pytest.raises(GroupUpdateError) as info:
            await group.update(entries)
        assert info.value.original is boom
        assert info.value.rollback_errors == []
    finally:
        await group.dispose()


# ---------------------------------------------------------------------------
# 5) Dispose releases entries (plan-required).
# ---------------------------------------------------------------------------


async def test_group_dispose_releases_entries(make_ctx: Context) -> None:
    """Dispose invokes every entry's dispose hook and clears the list."""
    events: list[str] = []
    group = Group(make_ctx)
    await group.update(
        [
            GroupEntry(options=_entry("a"), on_dispose=_hook(events, "dispose:a")),
            GroupEntry(options=_entry("b"), on_dispose=_hook(events, "dispose:b")),
        ]
    )
    await group.dispose()
    # 1:1 with upstream `for (const options of this.data)` — forward order.
    assert events == ["dispose:a", "dispose:b"]
    assert group.entries == []
    assert group.is_disposed is True


async def test_group_dispose_is_idempotent(make_ctx: Context) -> None:
    """A second ``dispose`` is a no-op; hooks are not invoked twice."""
    events: list[str] = []
    group = Group(make_ctx)
    await group.update([GroupEntry(options=_entry("a"), on_dispose=_hook(events, "dispose:a"))])
    await group.dispose()
    await group.dispose()
    assert events == ["dispose:a"]


async def test_dispose_swallows_entry_errors_but_still_clears(
    make_ctx: Context, caplog: pytest.LogCaptureFixture
) -> None:
    """A failing entry dispose is logged but does not block the rest."""
    events: list[str] = []
    group = Group(make_ctx)
    await group.update(
        [
            GroupEntry(options=_entry("ok"), on_dispose=_hook(events, "dispose:ok")),
            GroupEntry(options=_entry("bad"), on_dispose=_fail_hook(RuntimeError("nope"))),
        ]
    )
    with caplog.at_level("WARNING"):
        await group.dispose()
    assert "dispose:ok" in events
    assert group.entries == []
    assert group.is_disposed is True


async def test_success_path_dispose_failure_triggers_rollback(
    make_ctx: Context, caplog: pytest.LogCaptureFixture
) -> None:
    """A dispose failure during the success path triggers a rollback (1:1 with TS)."""
    dispose_boom = RuntimeError("stale dispose blew up")
    group = Group(make_ctx)

    # Seed 'keeper' and 'to_be_dropped'; 'to_be_dropped' will fail to dispose
    # during a later update that tries to remove it.
    await group.update(
        [
            GroupEntry(options=_entry("keeper")),
            GroupEntry(options=_entry("to_be_dropped"), on_dispose=_fail_hook(dispose_boom)),
        ]
    )

    # Update: drop 'to_be_dropped', add 'fresh'.
    with caplog.at_level("WARNING"):
        with pytest.raises(GroupUpdateError) as info:
            await group.update(
                [GroupEntry(options=_entry("keeper")), GroupEntry(options=_entry("fresh"))]
            )
    # The dispose of 'to_be_dropped' became the rollback's primary error.
    assert info.value.original is dispose_boom
    # State restored: only the originally-applied entries remain (and that
    # requires re-apply to have succeeded).
    assert {e.options.id for e in group.entries} == {"keeper", "to_be_dropped"}
    await group.dispose()


async def test_dispose_registered_through_cordis_service(make_ctx: Context) -> None:
    """Group is a cordis.Service, so ``ctx.dispose`` triggers our ``dispose``."""

    async def _record_apply(_entry: Entry) -> None:
        pass

    async def _record_dispose(_entry: Entry) -> None:
        pass

    group = Group(make_ctx)
    await group.update(
        [GroupEntry(options=_entry("a"), on_apply=_record_apply, on_dispose=_record_dispose)]
    )
    await make_ctx.dispose()
    assert group.is_disposed is True
    assert group.entries == []


# ---------------------------------------------------------------------------
# Validation paths.
# ---------------------------------------------------------------------------


async def test_update_rejects_duplicate_id(make_ctx: Context) -> None:
    """Duplicate entry ids are rejected before any apply runs."""
    group = Group(make_ctx)
    try:
        with pytest.raises(ValueError, match="duplicate loader entry id"):
            await group.update([_entry("dup"), _entry("dup")])
        assert group.entries == []
    finally:
        await group.dispose()


async def test_update_rejects_entry_without_id(make_ctx: Context) -> None:
    """An entry with no id is rejected before any apply runs."""
    bare = MagicMock(spec=Entry)
    bare.id = ""
    group = Group(make_ctx)
    try:
        with pytest.raises(ValueError, match="missing required 'id'"):
            await group.update([bare])
        assert group.entries == []
    finally:
        await group.dispose()


# ---------------------------------------------------------------------------
# Property: dispose is the cordis Service default route.
# ---------------------------------------------------------------------------


def test_group_inherits_from_cordis_service() -> None:
    """Group is a cordis Service (auto-dispose via ctx.dispose)."""
    assert issubclass(Group, Service)
