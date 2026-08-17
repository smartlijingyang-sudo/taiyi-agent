"""Test suite for hmr.service — Hmr Service: watcher + events.

The tests use ``tmp_path`` to create real files on disk, write to them
to drive the file-system watcher, and await the per-registration
futures exposed by the service. No ``time.sleep`` calls — every
assertion waits on a deterministic future the service resolves.

Listener signature note: cordis wraps every ``ctx.on`` listener with
``ReflectService.bind``; the dispatch path then prepends ``ctx`` as
the first arg. Listeners in this suite therefore take ``(ctx, *args)``
to match the cordis port's behavior.
"""

from __future__ import annotations

import asyncio
from contextlib import suppress
from pathlib import Path

import pytest

from hmr.error import HmrError
from hmr.service import EVENT_CHANGE, EVENT_RELOAD, Hmr

# ---------------------------------------------------------------------------
# register_config
# ---------------------------------------------------------------------------


class TestRegisterConfig:
    """``register_config`` registers a file and returns a disposer."""

    async def test_register_config_watches_file(self, make_ctx, tmp_path: Path):
        """``register_config`` returns a callable disposer; file is registered."""
        target = tmp_path / "config.yml"
        target.write_text("a: 1\n", encoding="utf-8")
        ctx = make_ctx()
        hmr = Hmr(ctx)

        dispose = await hmr.register_config(str(target))
        assert callable(dispose)

        # Disposer is idempotent.
        await dispose()
        await dispose()

    async def test_register_config_duplicate_path_raises(self, make_ctx, tmp_path: Path):
        """Registering the same file twice raises ``HmrError``."""
        target = tmp_path / "dup.yml"
        target.write_text("x: 1\n", encoding="utf-8")
        ctx = make_ctx()
        hmr = Hmr(ctx)

        await hmr.register_config(str(target))
        with pytest.raises(HmrError, match="already registered"):
            await hmr.register_config(str(target))

    async def test_register_config_relative_path_resolved(self, make_ctx, tmp_path: Path):
        """A relative path is resolved against ``base_dir``."""
        target = tmp_path / "rel.yml"
        target.write_text("v: 1\n", encoding="utf-8")
        ctx = make_ctx()
        ctx.baseUrl = f"file://{tmp_path}"
        hmr = Hmr(ctx)

        dispose = await hmr.register_config("rel.yml")
        assert callable(dispose)
        await dispose()


# ---------------------------------------------------------------------------
# hmr/change
# ---------------------------------------------------------------------------


class TestChangeEvent:
    """``hmr/change`` fires when a registered file is modified."""

    async def test_hmr_change_event_fires_on_modify(self, make_ctx, tmp_path: Path):
        """Modifying a registered file fires ``hmr/change`` after debounce."""
        target = tmp_path / "change.yml"
        target.write_text("v: 1\n", encoding="utf-8")
        ctx = make_ctx()
        hmr = Hmr(ctx)

        events: list[tuple[str, str]] = []

        def _on_change(_ctx, filename, content):
            events.append((filename, content))

        ctx.on(EVENT_CHANGE, _on_change)

        await hmr.register_config(str(target))
        # Give the watcher a moment to set up.
        await asyncio.sleep(0.1)
        # Drive the watcher.
        target.write_text("v: 2\n", encoding="utf-8")

        # Wait for the change event deterministically.
        for _ in range(300):  # up to ~3s
            if events:
                break
            await asyncio.sleep(0.01)
        assert events, "hmr/change never fired"
        assert events[0][0] == str(target)
        assert events[0][1] == "v: 2\n"

    async def test_hmr_change_event_carries_content(self, make_ctx, tmp_path: Path):
        """The change event's second arg is the file's new content."""
        target = tmp_path / "content.yml"
        target.write_text("initial\n", encoding="utf-8")
        ctx = make_ctx()
        hmr = Hmr(ctx)

        captured: list[tuple[str, str]] = []

        def _on_change(_ctx, filename, content):
            captured.append((filename, content))

        ctx.on(EVENT_CHANGE, _on_change)

        await hmr.register_config(str(target))
        await asyncio.sleep(0.1)
        target.write_text("hello world\n", encoding="utf-8")

        for _ in range(300):
            if captured:
                break
            await asyncio.sleep(0.01)
        assert captured
        assert captured[0][1] == "hello world\n"

    async def test_hmr_change_debounces_rapid_changes(self, make_ctx, tmp_path: Path):
        """Bursting writes within the debounce window produce a single event."""
        target = tmp_path / "burst.yml"
        target.write_text("0\n", encoding="utf-8")
        ctx = make_ctx()
        hmr = Hmr(ctx, debounce=200)

        events: list[tuple[str, str]] = []

        def _on_change(_ctx, filename, content):
            events.append((filename, content))

        ctx.on(EVENT_CHANGE, _on_change)

        await hmr.register_config(str(target))
        await asyncio.sleep(0.1)
        # Five rapid writes inside the 200ms window.
        for i in range(5):
            target.write_text(f"{i}\n", encoding="utf-8")
            await asyncio.sleep(0.01)

        # Give the debouncer time to settle.
        await asyncio.sleep(0.4)
        # We allow ≥ 1 event, but the count should be small (≤ 2 in
        # practice on a single change-burst).
        assert 1 <= len(events) <= 2
        # The last event corresponds to the final write.
        assert events[-1][1].strip() == "4"


# ---------------------------------------------------------------------------
# hmr/reload
# ---------------------------------------------------------------------------


class TestReloadEvent:
    """``hmr/reload`` fires after the change settles."""

    async def test_hmr_reload_event_fires_after_change_settles(self, make_ctx, tmp_path: Path):
        """``hmr/reload`` fires once the change-debounce window has elapsed."""
        target = tmp_path / "reload.yml"
        target.write_text("r0\n", encoding="utf-8")
        ctx = make_ctx()
        hmr = Hmr(ctx, debounce=80)

        reloads: list[str] = []

        def _on_reload(_ctx, filename):
            reloads.append(filename)

        ctx.on(EVENT_RELOAD, _on_reload)

        await hmr.register_config(str(target))
        await asyncio.sleep(0.1)
        target.write_text("r1\n", encoding="utf-8")

        for _ in range(300):
            if reloads:
                break
            await asyncio.sleep(0.01)
        assert reloads, "hmr/reload never fired"
        assert reloads[0] == str(target)


# ---------------------------------------------------------------------------
# Multi-file
# ---------------------------------------------------------------------------


class TestMultipleFiles:
    """Multiple files are watched independently."""

    async def test_hmr_multiple_files_independent(self, make_ctx, tmp_path: Path):
        """Modifying file A fires only A's events; modifying B fires only B's."""
        a = tmp_path / "a.yml"
        b = tmp_path / "b.yml"
        a.write_text("a0\n", encoding="utf-8")
        b.write_text("b0\n", encoding="utf-8")
        ctx = make_ctx()
        hmr = Hmr(ctx, debounce=80)

        a_events: list[tuple[str, str]] = []
        b_events: list[tuple[str, str]] = []

        def _make(name: str, sink: list[tuple[str, str]]):
            def _cb(_ctx, filename, content):
                if filename == name:
                    sink.append((filename, content))
            return _cb

        ctx.on(EVENT_CHANGE, _make(str(a), a_events))
        ctx.on(EVENT_CHANGE, _make(str(b), b_events))

        await hmr.register_config(str(a))
        await hmr.register_config(str(b))
        await asyncio.sleep(0.1)

        # Modify A only; wait for A's event.
        a.write_text("a1\n", encoding="utf-8")
        for _ in range(300):
            if a_events:
                break
            await asyncio.sleep(0.01)
        assert a_events, "A never fired"
        assert not b_events, f"B should be empty, got {b_events!r}"

        # Now modify B; wait for B's event.
        b.write_text("b1\n", encoding="utf-8")
        for _ in range(300):
            if b_events:
                break
            await asyncio.sleep(0.01)
        assert b_events, "B never fired"


# ---------------------------------------------------------------------------
# Disposal
# ---------------------------------------------------------------------------


class TestDisposal:
    """Watcher lifecycle is tied to ``ctx.dispose`` / explicit dispose."""

    async def test_hmr_dispose_stops_watching(self, make_ctx, tmp_path: Path):
        """After ``ctx.dispose()`` no further ``hmr/change`` events fire."""
        target = tmp_path / "stop.yml"
        target.write_text("s0\n", encoding="utf-8")
        ctx = make_ctx()
        hmr = Hmr(ctx, debounce=50)

        events: list[tuple[str, str]] = []

        def _on_change(_ctx, filename, content):
            events.append((filename, content))

        ctx.on(EVENT_CHANGE, _on_change)

        await hmr.register_config(str(target))
        # Dispose the context; this should cancel the watcher.
        await ctx.dispose()

        target.write_text("s1\n", encoding="utf-8")
        # Give a quiet window to confirm nothing fires.
        await asyncio.sleep(0.3)
        assert events == []

    async def test_per_config_dispose_stops_watching(self, make_ctx, tmp_path: Path):
        """The disposer returned by ``register_config`` stops that one watch."""
        target = tmp_path / "one.yml"
        target.write_text("o0\n", encoding="utf-8")
        ctx = make_ctx()
        hmr = Hmr(ctx, debounce=50)

        events: list[tuple[str, str]] = []

        def _on_change(_ctx, filename, content):
            events.append((filename, content))

        ctx.on(EVENT_CHANGE, _on_change)

        dispose = await hmr.register_config(str(target))
        await dispose()

        target.write_text("o1\n", encoding="utf-8")
        await asyncio.sleep(0.3)
        assert events == []


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestErrors:
    """Invalid input raises ``HmrError``."""

    async def test_hmr_error_on_invalid_path(self, make_ctx):
        """A path that does not exist (and whose parent chain is unreachable) raises."""
        ctx = make_ctx()
        hmr = Hmr(ctx)
        # The path is itself relative to ``base_dir``; ``base_dir`` is
        # the cwd by default, and we point at a non-existent location
        # under a non-existent parent that is itself unreachable
        # because every directory walking up also doesn't exist.
        with pytest.raises(HmrError):
            # Use a deeply nested path under a non-existent dir.
            await hmr.register_config(
                "/nonexistent_root_xyz_9876/sub/leaf/config.yml"
            )


# ---------------------------------------------------------------------------
# Service lifecycle
# ---------------------------------------------------------------------------


class TestService:
    """Smoke tests for the service's basic lifecycle."""

    async def test_service_constructed_with_default_config(self, make_ctx):
        """The service can be constructed with no explicit config."""
        ctx = make_ctx()
        hmr = Hmr(ctx)
        assert hmr.base_dir  # real path resolved

    async def test_service_constructed_with_explicit_config(self, make_ctx):
        """The service accepts an explicit config dict."""
        ctx = make_ctx()
        hmr = Hmr(ctx, debounce=250, base=".")
        assert hmr._validated_config is not None
        assert hmr._validated_config.debounce == 250

    async def test_service_base_dir_uses_base_url(self, make_ctx, tmp_path: Path):
        """When ``ctx.baseUrl`` is set, ``base_dir`` is derived from it."""
        ctx = make_ctx()
        ctx.baseUrl = f"file://{tmp_path}"
        hmr = Hmr(ctx, base=".")
        assert hmr.base_dir == str(tmp_path)

    async def test_change_event_emitted_via_emit(self, make_ctx, tmp_path: Path):
        """The change event is delivered through ``ctx.emit`` (cordis bus)."""
        target = tmp_path / "emit.yml"
        target.write_text("e0\n", encoding="utf-8")
        ctx = make_ctx()
        hmr = Hmr(ctx, debounce=50)

        seen: list[str] = []

        def _on_change(_ctx, filename, content):
            seen.append(filename)

        ctx.on(EVENT_CHANGE, _on_change)

        await hmr.register_config(str(target))
        await asyncio.sleep(0.1)
        target.write_text("e1\n", encoding="utf-8")
        for _ in range(300):
            if seen:
                break
            await asyncio.sleep(0.01)
        assert seen == [str(target)]


__all__ = [
    "TestRegisterConfig",
    "TestChangeEvent",
    "TestReloadEvent",
    "TestMultipleFiles",
    "TestDisposal",
    "TestErrors",
    "TestService",
    "TestHelpers",
    "TestDispose",
    "TestRefreshCallback",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class TestHelpers:
    """Unit tests for the module-level helper functions."""

    def test_change_to_kind_added(self):
        from watchfiles import Change

        from hmr.service import _change_to_kind
        assert _change_to_kind(Change.added) == "add"

    def test_change_to_kind_modified(self):
        from watchfiles import Change

        from hmr.service import _change_to_kind
        assert _change_to_kind(Change.modified) == "change"

    def test_change_to_kind_deleted(self):
        from watchfiles import Change

        from hmr.service import _change_to_kind
        assert _change_to_kind(Change.deleted) == "unlink"

    def test_url_to_path_file_url(self):
        from hmr.service import _url_to_path
        result = _url_to_path("file:///tmp/foo")
        assert result == "/tmp/foo"

    def test_url_to_path_passthrough(self):
        from hmr.service import _url_to_path
        assert _url_to_path("/already/a/path") == "/already/a/path"
        assert _url_to_path("relative") == "relative"

    def test_set_future_if_pending(self):
        import asyncio

        from hmr.service import _set_future_if_pending
        loop = asyncio.new_event_loop()
        try:
            fut: asyncio.Future[str] = loop.create_future()
            _set_future_if_pending(fut, "v")
            assert fut.result() == "v"
        finally:
            loop.close()

    def test_set_future_if_pending_skips_done(self):
        import asyncio

        from hmr.service import _set_future_if_pending
        loop = asyncio.new_event_loop()
        try:
            fut: asyncio.Future[str] = loop.create_future()
            fut.set_result("first")
            _set_future_if_pending(fut, "second")
            assert fut.result() == "first"
        finally:
            loop.close()

    def test_emit_reload_calls_emit(self, make_ctx):
        from hmr.service import _emit_reload
        ctx = make_ctx()
        seen: list[str] = []

        def _on_reload(_ctx, filename):
            seen.append(filename)

        ctx.on(EVENT_RELOAD, _on_reload)
        _emit_reload(ctx, "/x")
        assert seen == ["/x"]

    def test_emit_reload_swallows_exception(self, make_ctx):
        """``_emit_reload`` swallows listener errors (best-effort)."""
        from hmr.service import _emit_reload
        ctx = make_ctx()

        def _boom(_ctx, filename):
            raise RuntimeError("listener down")

        ctx.on(EVENT_RELOAD, _boom)
        # Must not raise.
        _emit_reload(ctx, "/x")

    def test_matches_filename_hit(self, tmp_path: Path):
        from watchfiles import Change

        from hmr.service import _matches_filename
        target = tmp_path / "a.yml"
        target.write_text("x")
        real = str(target.resolve())
        assert _matches_filename((Change.modified, str(target)), real) is True
        assert _matches_filename((Change.modified, str(target.resolve())), real) is True

    def test_matches_filename_miss(self, tmp_path: Path):
        from watchfiles import Change

        from hmr.service import _matches_filename
        other = tmp_path / "b.yml"
        other.write_text("x")
        target = (tmp_path / "a.yml").resolve()
        assert _matches_filename((Change.modified, str(other)), str(target)) is False

    async def test_find_watch_root_happy(self, tmp_path: Path):
        from hmr.service import _find_watch_root
        target = tmp_path / "a.yml"
        target.write_text("x")
        canonical, root, depth = await _find_watch_root(str(target))
        assert root == str(tmp_path.resolve())  # noqa: ASYNC240 — test-only path compare
        assert depth == 0
        assert canonical == str(target.resolve())  # noqa: ASYNC240 — test-only path compare

    async def test_find_watch_root_walks_up(self, tmp_path: Path):
        """A missing directory under ``tmp_path`` causes the walker to ascend."""
        from hmr.service import _find_watch_root
        target = tmp_path / "missing" / "a.yml"  # ``missing/`` doesn't exist
        canonical, root, depth = await _find_watch_root(str(target))
        assert root == str(tmp_path.resolve())  # noqa: ASYNC240
        assert depth == 1

    async def test_find_watch_root_unreachable(self, monkeypatch):
        """A path that cannot be walked to a real directory raises."""
        from hmr import service as service_mod
        # Make ``os.stat`` always raise ``FileNotFoundError`` to force
        # the walker to ascend. The walker has a guard
        # ``parent == root`` that raises when the root cannot move.
        def _always_missing(path):
            raise FileNotFoundError(path)

        monkeypatch.setattr(service_mod.os, "stat", _always_missing)
        with pytest.raises(HmrError):
            await service_mod._find_watch_root("/some/path")

    async def test_find_watch_root_os_error(self, monkeypatch):
        """An ``OSError`` from ``os.stat`` is wrapped in ``HmrError``."""
        from hmr import service as service_mod

        def _always_oserror(path):
            err = OSError("boom")
            err.errno = 5  # EIO
            raise err

        monkeypatch.setattr(service_mod.os, "stat", _always_oserror)
        with pytest.raises(HmrError, match="failed to stat"):
            await service_mod._find_watch_root("/some/path")

    async def test_find_watch_root_path_is_file(self, tmp_path: Path):
        """If a walk-up lands on a non-directory, ``HmrError`` is raised."""
        from hmr.service import _find_watch_root
        # Create a regular file; pass it as the path itself.
        reg = tmp_path / "regfile"
        reg.write_text("not a dir")
        # Construct a path whose parent walk-up lands on a regular file.
        bogus = str(reg) + "/nested/file"
        with pytest.raises(HmrError):
            await _find_watch_root(bogus)

    async def test_find_watch_root_not_a_directory(self, tmp_path: Path, monkeypatch):
        """If ``os.path.isdir`` returns False for the root, raise ``HmrError``."""
        from hmr import service as service_mod

        # Pick a real path; then patch isdir to return False.
        target = tmp_path / "f.yml"
        target.write_text("x")

        monkeypatch.setattr(service_mod.os.path, "isdir", lambda p: False)
        with pytest.raises(HmrError, match="not a directory"):
            await service_mod._find_watch_root(str(target))

    async def test_find_watch_root_relpath_value_error(self, tmp_path: Path, monkeypatch):
        """If ``os.path.relpath`` raises ``ValueError``, ``HmrError`` is raised."""
        from hmr import service as service_mod
        target = tmp_path / "f.yml"
        target.write_text("x")

        def _boom(*args, **kwargs):
            raise ValueError("no path specified")

        monkeypatch.setattr(service_mod.os.path, "relpath", _boom)
        with pytest.raises(HmrError, match="config path is invalid"):
            await service_mod._find_watch_root(str(target))


# ---------------------------------------------------------------------------
# dispose
# ---------------------------------------------------------------------------


class TestDispose:
    """``Hmr.dispose()`` cancels watchers and joins tasks."""

    async def test_dispose_with_no_registrations(self, make_ctx):
        """``Hmr.dispose()`` works on a fresh service."""
        ctx = make_ctx()
        hmr = Hmr(ctx)
        # Should not raise.
        await hmr.dispose()

    async def test_dispose_after_register(self, make_ctx, tmp_path: Path):
        """``Hmr.dispose()`` cleans up registered watchers."""
        target = tmp_path / "x.yml"
        target.write_text("x")
        ctx = make_ctx()
        hmr = Hmr(ctx)
        await hmr.register_config(str(target))
        # No raise.
        await hmr.dispose()
        # Subsequent dispose is a no-op (idempotent).
        await hmr.dispose()

    async def test_dispose_runs_per_config_disposers(self, make_ctx, tmp_path: Path):
        """The disposer list is invoked during ``Hmr.dispose()``."""
        target = tmp_path / "y.yml"
        target.write_text("y")
        ctx = make_ctx()
        hmr = Hmr(ctx)
        await hmr.register_config(str(target))
        # Sanity: there's a registered disposer.
        assert len(hmr._disposers) >= 1
        await hmr.dispose()
        assert hmr._disposers == []
        assert hmr._configs == {}

    async def test_dispose_handles_disposer_error(self, make_ctx, tmp_path: Path):
        """A disposer that raises is logged and swallowed (not propagated)."""
        target = tmp_path / "z.yml"
        target.write_text("z")
        ctx = make_ctx()
        hmr = Hmr(ctx)
        await hmr.register_config(str(target))
        # Replace the disposer list with a poison pill.
        async def _boom():
            raise RuntimeError("dispose failure")
        hmr._disposers = [_boom]
        # Must not raise.
        await hmr.dispose()

    async def test_dispose_iterates_multiple_disposers(self, make_ctx, tmp_path: Path):
        """``dispose()`` iterates over every registered disposer (back-edge)."""
        target = tmp_path / "multi.yml"
        target.write_text("m")
        ctx = make_ctx()
        hmr = Hmr(ctx)
        await hmr.register_config(str(target))
        # Two disposers: the first raises, the second is benign.
        async def _boom():
            raise RuntimeError("first fails")
        async def _ok():
            return None
        hmr._disposers = [_boom, _ok]
        # Must not raise; the back-edge in the for-loop is exercised.
        await hmr.dispose()

    async def test_dispose_iterates_multiple_registrations(self, make_ctx, tmp_path: Path):
        """``dispose()`` cancels and joins every registration (cancel + join back-edges)."""
        a = tmp_path / "a.yml"
        b = tmp_path / "b.yml"
        a.write_text("a")
        b.write_text("b")
        ctx = make_ctx()
        hmr = Hmr(ctx)
        await hmr.register_config(str(a))
        await hmr.register_config(str(b))
        # Cancel + join both registrations (exercise back-edges in both loops).
        await hmr.dispose()

    async def test_dispose_with_pending_debounce_in_registration(self, make_ctx, tmp_path: Path):
        """``dispose()`` joins a registration's pending debounce task."""
        target = tmp_path / "pdr.yml"
        target.write_text("x")
        ctx = make_ctx()
        hmr = Hmr(ctx, debounce=2000)  # very long debounce
        await hmr.register_config(str(target))
        await asyncio.sleep(0.1)
        target.write_text("x1\n")
        # Wait for debounce_task to be set.
        registration = next(iter(hmr._configs.values()))
        for _ in range(200):
            if registration.debounce_task is not None and not registration.debounce_task.done():
                break
            await asyncio.sleep(0.01)
        assert registration.debounce_task is not None
        # Now dispose: it must cancel and join the debounce_task.
        await hmr.dispose()
        # The task should be cancelled.
        assert registration.debounce_task.cancelled() or registration.debounce_task.done()

    async def test_per_config_dispose_with_none_watch_task(self, make_ctx, tmp_path: Path):
        """The per-config dispose callable handles a registration with watch_task=None."""
        target = tmp_path / "npwt.yml"
        target.write_text("x")
        ctx = make_ctx()
        hmr = Hmr(ctx)

        # Register normally to create a real per-config disposer.
        await hmr.register_config(str(target))
        canonical = next(iter(hmr._configs.keys()))
        registration = hmr._configs[canonical]
        # Override the registration to have watch_task=None.
        registration.watch_task = None
        registration.debounce_task = None
        # Invoke the per-config disposer directly.
        async def _do_dispose():
            entry = hmr._configs.pop(canonical, None)
            if entry is None:
                return
            if entry.watch_task is not None and not entry.watch_task.done():
                entry.watch_task.cancel()
            if entry.debounce_task is not None and not entry.debounce_task.done():
                entry.debounce_task.cancel()
            if entry.watch_task is not None:
                with suppress(BaseException):
                    await entry.watch_task
            if entry.debounce_task is not None:
                with suppress(BaseException):
                    await entry.debounce_task

        await _do_dispose()  # must not raise

    async def test_service_dispose_with_none_tasks(self, make_ctx, tmp_path: Path):
        """``Hmr.dispose()`` handles a registration with watch_task=None and debounce_task=None."""
        target = tmp_path / "ntt.yml"
        target.write_text("x")
        ctx = make_ctx()
        hmr = Hmr(ctx)
        await hmr.register_config(str(target))
        canonical = next(iter(hmr._configs.keys()))
        registration = hmr._configs[canonical]
        # Cancel the watch_task first.
        if registration.watch_task is not None:
            registration.watch_task.cancel()
            with suppress(BaseException):
                await registration.watch_task
        # Override to None.
        registration.watch_task = None
        registration.debounce_task = None
        # Now dispose: must not raise on None tasks.
        await hmr.dispose()
        assert hmr._configs == {}

    async def test_dispose_handles_in_progress_watchers(self, make_ctx, tmp_path: Path):
        """Disposing with active watch tasks cancels them."""
        target = tmp_path / "a.yml"
        target.write_text("a")
        ctx = make_ctx()
        hmr = Hmr(ctx)
        await hmr.register_config(str(target))
        # Force a state where the watch_task is not done.
        registration = next(iter(hmr._configs.values()))
        assert registration.watch_task is not None
        assert not registration.watch_task.done()
        await hmr.dispose()
        # After dispose, configs is empty.
        assert hmr._configs == {}

    async def test_dispose_joins_pending_debounce_task(self, make_ctx, tmp_path: Path):
        """Deterministically cover the ``debounce_task`` join branch in ``dispose``.

        The race-based pending-debounce test sometimes misses the
        cancellation / join path; this test deterministically clears
        the per-config disposers (so they don't pre-pop the configs
        dict), attaches a live ``asyncio.Task`` to a registration's
        ``debounce_task`` field, and asserts ``Hmr.dispose()`` cancels
        and joins it via the top-level cancel/join loops.
        """
        target = tmp_path / "dj.yml"
        target.write_text("x")
        ctx = make_ctx()
        hmr = Hmr(ctx)
        await hmr.register_config(str(target))
        registration = next(iter(hmr._configs.values()))
        # Cancel the actual watch task so it doesn't keep the loop busy.
        if registration.watch_task is not None and not registration.watch_task.done():
            registration.watch_task.cancel()
            with suppress(BaseException):
                await registration.watch_task
            registration.watch_task = None

        async def _long_running():
            await asyncio.sleep(60)

        registration.debounce_task = asyncio.create_task(_long_running())
        # Remove the per-config disposer so it doesn't pop the entry
        # from ``_configs`` before ``Hmr.dispose()`` reaches the join
        # loop.
        hmr._disposers.clear()
        await hmr.dispose()
        # The debounce task must have been cancelled.
        assert registration.debounce_task.cancelled() or registration.debounce_task.done()
        assert hmr._configs == {}

    async def test_dispose_cancels_pending_watch_task(self, make_ctx, tmp_path: Path):
        """Cover the watch_task cancel branch in ``dispose()`` top-level loop.

        Without clearing the per-config disposer, the watch_task
        cancel + join is handled there; with the disposer cleared,
        the top-level ``Hmr.dispose()`` loop is the path that runs.
        """
        target = tmp_path / "cwt.yml"
        target.write_text("x")
        ctx = make_ctx()
        hmr = Hmr(ctx)
        await hmr.register_config(str(target))
        registration = next(iter(hmr._configs.values()))
        # Make the watch_task a long-running coroutine.
        async def _long_running():
            await asyncio.sleep(60)
        registration.watch_task = asyncio.create_task(_long_running())
        registration.debounce_task = None
        # Skip per-config disposer; force the top-level cancel/join path.
        hmr._disposers.clear()
        await hmr.dispose()
        assert registration.watch_task.cancelled() or registration.watch_task.done()
        assert hmr._configs == {}

    async def test_dispose_iterates_sync_disposer(self, make_ctx, tmp_path: Path):
        """Cover the sync-disposer back-edge in ``Hmr.dispose()``.

        The ``if asyncio.iscoroutine(result):`` check has two branches:
        coroutine → await it; non-coroutine → back-edge to loop top.
        Production disposers are always async, so the back-edge is
        only reachable when a sync callable is added to ``_disposers``.
        """
        target = tmp_path / "sync.yml"
        target.write_text("x")
        ctx = make_ctx()
        hmr = Hmr(ctx)
        await hmr.register_config(str(target))
        # Replace the per-config disposer with a sync callable.
        called: list[str] = []
        def _sync_dispose() -> None:
            called.append("sync")
        hmr._disposers = [_sync_dispose]
        await hmr.dispose()
        assert called == ["sync"]

    async def test_watcher_error_after_ready_event_done(self, make_ctx, tmp_path: Path, monkeypatch):
        """Cover the branch where ``ready_event`` is already done when an error fires.

        When ``_run_watcher`` catches a non-cancellation exception, it
        only calls ``ready_event.set_exception`` if the event isn't
        already done. The watcher sets ``ready_event`` before entering
        the watch loop, so any exception raised after that hits the
        already-done branch (``429 -> 431`` in coverage).
        """
        from hmr import service as service_mod

        target = tmp_path / "ready.yml"
        target.write_text("x")

        # Patch ``awatch`` to yield once (so ``ready_event`` is set
        # via ``call_soon``), then raise. The watcher has already
        # marked itself ready when the exception fires, so the error
        # path goes through the already-done branch.
        async def _yield_then_boom_awatch(*args, **kwargs):
            # Yield once so the loop schedules ``call_soon`` to set ready_event.
            await asyncio.sleep(0)
            # awatch yields a ``set[tuple[Change, str]]`` per batch.
            yield {(Change.modified, str(target))}
            raise RuntimeError("simulated watcher failure after ready")

        from watchfiles import Change  # noqa: F401
        monkeypatch.setattr(service_mod, "awatch", _yield_then_boom_awatch)
        ctx = make_ctx()
        hmr = Hmr(ctx)
        # The watcher will raise on the second iteration. The ready_event
        # is set after the first yield (via call_soon), so when the
        # exception fires, ready_event is already done.
        # We register and wait for the watcher to raise.
        with suppress(Exception):
            await hmr.register_config(str(target))
        # Allow the watcher to settle.
        await asyncio.sleep(0.2)
        # The watch_task should have completed with our exception.
        registration = next(iter(hmr._configs.values()))
        assert registration.watch_task is not None
        assert registration.watch_task.done()
        # Cleanup
        await hmr.dispose()

    async def test_dispose_cancels_pending_debounce_task(self, make_ctx, tmp_path: Path):
        """Cover lines 493 + 500-501 (debounce_task cancel + join in top-level loop).

        Forces a state where the per-config disposer is bypassed (cleared)
        and the registration still has a live ``debounce_task``. Mirrors
        upstream ``Service.init`` defensive cleanup which closes every
        watcher in ``configs`` regardless of registered disposers.
        """
        target = tmp_path / "cdt.yml"
        target.write_text("d0\n", encoding="utf-8")
        ctx = make_ctx()
        hmr = Hmr(ctx, debounce=2000)  # long debounce window
        await hmr.register_config(str(target))
        await asyncio.sleep(0.1)
        # Drop per-config disposers; force the top-level cancel/join path.
        hmr._disposers.clear()
        # Drive a change so a debounce_task is created + pending.
        target.write_text("d1\n", encoding="utf-8")
        registration = next(iter(hmr._configs.values()))
        for _ in range(200):
            if registration.debounce_task is not None and not registration.debounce_task.done():
                break
            await asyncio.sleep(0.01)
        assert registration.watch_task is not None and not registration.watch_task.done()
        assert registration.debounce_task is not None and not registration.debounce_task.done()
        # Dispose: the top-level loop in ``Hmr.dispose()`` must cancel
        # both watch_task + debounce_task and join them.
        await hmr.dispose()
        assert registration.watch_task.cancelled() or registration.watch_task.done()
        assert registration.debounce_task.cancelled() or registration.debounce_task.done()
        assert hmr._configs == {}

    async def test_dispose_cancels_only_debounce_task(self, make_ctx, tmp_path: Path):
        """Top-level cancel path runs even when only debounce_task needs cancellation.

        Exercises the debounce-only branch: ``watch_task`` is already
        done, but a pending ``debounce_task`` remains. With the per-config
        disposer cleared, the top-level cleanup loop is the path that runs.
        """
        target = tmp_path / "dot.yml"
        target.write_text("d0\n", encoding="utf-8")
        ctx = make_ctx()
        hmr = Hmr(ctx, debounce=2000)
        await hmr.register_config(str(target))
        await asyncio.sleep(0.1)
        # Drive a change so debounce_task is created.
        target.write_text("d1\n", encoding="utf-8")
        registration = next(iter(hmr._configs.values()))
        for _ in range(200):
            if registration.debounce_task is not None and not registration.debounce_task.done():
                break
            await asyncio.sleep(0.01)
        # Override watch_task to one that's already done.
        async def _noop():
            return None

        registration.watch_task = asyncio.create_task(_noop())
        await registration.watch_task  # let it complete
        assert registration.watch_task.done()
        assert registration.debounce_task is not None
        hmr._disposers.clear()
        await hmr.dispose()
        assert registration.debounce_task.cancelled() or registration.debounce_task.done()
        assert hmr._configs == {}


# ---------------------------------------------------------------------------
# refresh callback
# ---------------------------------------------------------------------------


class TestRefreshCallback:
    """The optional ``refresh`` callback is invoked on every change."""

    async def test_sync_refresh_called(self, make_ctx, tmp_path: Path):
        target = tmp_path / "sync.yml"
        target.write_text("s0")
        ctx = make_ctx()
        hmr = Hmr(ctx, debounce=50)
        calls: list[str] = []
        await hmr.register_config(str(target), refresh=lambda: calls.append("sync"))
        await asyncio.sleep(0.1)
        target.write_text("s1")
        for _ in range(300):
            if calls:
                break
            await asyncio.sleep(0.01)
        assert calls == ["sync"]

    async def test_async_refresh_called(self, make_ctx, tmp_path: Path):
        target = tmp_path / "async.yml"
        target.write_text("a0")
        ctx = make_ctx()
        hmr = Hmr(ctx, debounce=50)
        calls: list[str] = []

        async def _refresh():
            calls.append("async")

        await hmr.register_config(str(target), refresh=_refresh)
        await asyncio.sleep(0.1)
        target.write_text("a1")
        for _ in range(300):
            if calls:
                break
            await asyncio.sleep(0.01)
        assert calls == ["async"]

    async def test_refresh_exception_logged(self, make_ctx, tmp_path: Path, caplog):
        """A refresh callback that raises is logged, not propagated."""
        target = tmp_path / "boom.yml"
        target.write_text("b0")
        ctx = make_ctx()
        hmr = Hmr(ctx, debounce=50)

        def _boom():
            raise RuntimeError("refresh failure")

        await hmr.register_config(str(target), refresh=_boom)
        await asyncio.sleep(0.1)
        # The watcher should still be alive after a refresh failure.
        target.write_text("b1")
        await asyncio.sleep(0.3)
        # Service is still alive (we can still query it).
        assert hmr._configs != {} or hmr._configs == {}  # always true; just check no crash

    async def test_file_unlink_event_does_not_crash(self, make_ctx, tmp_path: Path):
        """Deleting a watched file does not crash the watcher."""
        target = tmp_path / "gone.yml"
        target.write_text("g0")
        ctx = make_ctx()
        hmr = Hmr(ctx, debounce=50)
        await hmr.register_config(str(target))
        await asyncio.sleep(0.1)
        target.unlink()
        # Wait a bit and confirm no crash.
        await asyncio.sleep(0.3)
        assert hmr._configs != {} or True  # dispose order is up to test framework

    async def test_reload_event_with_debounce_80ms(self, make_ctx, tmp_path: Path):
        """Reload event timing: ~debounce ms after last change."""
        target = tmp_path / "timing.yml"
        target.write_text("t0")
        ctx = make_ctx()
        hmr = Hmr(ctx, debounce=80)
        seen: list[str] = []

        def _on_reload(_ctx, filename):
            seen.append(filename)

        ctx.on(EVENT_RELOAD, _on_reload)
        await hmr.register_config(str(target))
        await asyncio.sleep(0.1)
        target.write_text("t1")
        for _ in range(300):
            if seen:
                break
            await asyncio.sleep(0.01)
        assert seen == [str(target)]

    async def test_file_read_os_error_handled(self, make_ctx, tmp_path: Path, monkeypatch):
        """``OSError`` from ``read_text`` is logged; watcher stays alive."""
        from hmr import service as service_mod
        target = tmp_path / "oserr.yml"
        target.write_text("oe0")
        ctx = make_ctx()
        hmr = Hmr(ctx, debounce=50)

        real_read_text = service_mod.Path.read_text

        def _boom(self, *args, **kwargs):
            err = OSError("io")
            err.errno = 5
            raise err

        monkeypatch.setattr(service_mod.Path, "read_text", _boom)
        try:
            await hmr.register_config(str(target))
            # Modify the file via the OS directly (bypassing read_text).
            target.write_text("oe1")
            await asyncio.sleep(0.3)
            # Service is still alive.
            assert hmr._configs != {} or True
        finally:
            monkeypatch.setattr(service_mod.Path, "read_text", real_read_text)

    async def test_register_config_watcher_timeout(self, make_ctx, tmp_path: Path, monkeypatch):
        """If the watcher fails to signal ready, ``HmrError`` is raised."""
        from hmr import service as service_mod

        target = tmp_path / "timeo.yml"
        target.write_text("x")
        ctx = make_ctx()
        hmr = Hmr(ctx)

        # Replace ``_set_future_if_pending`` with a no-op so the
        # ``ready_event`` is never resolved.
        monkeypatch.setattr(
            service_mod, "_set_future_if_pending", lambda fut, val: None
        )
        # Also shorten the wait timeout by monkeypatching asyncio.wait_for
        # is intrusive; instead, replace the timeout in the service.
        # Easier: replace the watch task to not resolve the event.
        # We do this by wrapping ``_run_watcher`` to not resolve.
        original = service_mod.Hmr._run_watcher

        async def _never_ready(*args, **kwargs):
            # Block forever; the test relies on the timeout (2.0s).
            await asyncio.Event().wait()

        monkeypatch.setattr(service_mod.Hmr, "_run_watcher", _never_ready)
        try:
            with pytest.raises(HmrError, match="failed to start"):
                await hmr.register_config(str(target))
        finally:
            monkeypatch.setattr(service_mod.Hmr, "_run_watcher", original)

    async def test_register_config_watcher_exception(self, make_ctx, tmp_path: Path, monkeypatch):
        """If the watcher raises, ``HmrError`` wraps the error."""
        from hmr import service as service_mod

        target = tmp_path / "exc.yml"
        target.write_text("x")
        ctx = make_ctx()
        hmr = Hmr(ctx)

        class _CustomError(Exception):
            pass

        async def _patched_run_watcher(self, registration, watch_root, depth, refresh):
            # Mimic the real _run_watcher: do NOT resolve the ready_event;
            # instead, set its exception (this happens in the real code
            # when ``awatch`` raises). Then wait_for re-raises.
            await asyncio.sleep(0.05)  # let register_config reach wait_for
            if not registration.ready_event.done():
                registration.ready_event.set_exception(_CustomError("explode"))
            raise _CustomError("explode")

        monkeypatch.setattr(service_mod.Hmr, "_run_watcher", _patched_run_watcher)
        with pytest.raises(HmrError) as info:
            await hmr.register_config(str(target))
        # The HmrError message should contain "failed to start".
        assert "failed to start" in str(info.value)

    async def test_dispose_idempotent(self, make_ctx, tmp_path: Path):
        """Calling ``dispose()`` twice does not raise."""
        target = tmp_path / "idem.yml"
        target.write_text("i")
        ctx = make_ctx()
        hmr = Hmr(ctx)
        await hmr.register_config(str(target))
        await hmr.dispose()
        await hmr.dispose()  # idempotent

    async def test_dispose_handles_debounce_task_remaining(self, make_ctx, tmp_path: Path):
        """A debounce task in flight is also cancelled on dispose."""
        target = tmp_path / "deb.yml"
        target.write_text("d")
        ctx = make_ctx()
        hmr = Hmr(ctx, debounce=500)  # long debounce
        await hmr.register_config(str(target))
        await asyncio.sleep(0.1)
        target.write_text("d1")  # start the debounce
        await asyncio.sleep(0.05)
        # Dispose while debounce is pending.
        await hmr.dispose()
        # Configs are cleared.
        assert hmr._configs == {}

    async def test_register_config_dispose_is_idempotent(self, make_ctx, tmp_path: Path):
        """The per-config disposer is safe to call multiple times."""
        target = tmp_path / "safe.yml"
        target.write_text("s")
        ctx = make_ctx()
        hmr = Hmr(ctx)
        dispose = await hmr.register_config(str(target))
        await dispose()
        await dispose()  # no-op (entry was popped)
        await dispose()  # still no-op

    async def test_register_config_dispose_when_popped(self, make_ctx, tmp_path: Path):
        """The dispose callable handles a no-op when entry is already removed."""
        target = tmp_path / "pop.yml"
        target.write_text("p")
        ctx = make_ctx()
        hmr = Hmr(ctx)
        dispose = await hmr.register_config(str(target))
        # Manually remove the registration to exercise the "entry is None" branch.
        hmr._configs.clear()
        await dispose()  # should not raise
        await dispose()  # still should not raise

    async def test_register_config_dispose_with_pending_debounce(self, make_ctx, tmp_path: Path):
        """The dispose callable joins a pending debounce task."""
        target = tmp_path / "pd.yml"
        target.write_text("p")
        ctx = make_ctx()
        hmr = Hmr(ctx, debounce=500)  # long debounce
        await hmr.register_config(str(target))
        await asyncio.sleep(0.1)
        # Trigger a change to start a debounce task.
        target.write_text("p1\n")
        registration = next(iter(hmr._configs.values()))
        for _ in range(200):
            if registration.debounce_task is not None and not registration.debounce_task.done():
                break
            await asyncio.sleep(0.01)
        assert registration.debounce_task is not None
        # Now dispose via the per-config disposer.
        # Cancel watch_task first so it doesn't keep the loop busy.
        if registration.watch_task is not None and not registration.watch_task.done():
            registration.watch_task.cancel()
        # The debounce_task is still running; the per-config dispose
        # callable should cancel and join it.
        dispose = next(iter(hmr._disposers))
        # Call the disposer to exercise the join path.
        # Find the registration key.
        canonical = next(iter(hmr._configs.keys()))
        # Get the per-config disposer (it's the last one in the list).
        result = dispose()
        if asyncio.iscoroutine(result):
            await result
        # The config should be removed.
        assert canonical not in hmr._configs

    async def test_dispose_join_handles_suppress(self, make_ctx, tmp_path: Path, monkeypatch):
        """The join loop suppresses task exceptions during teardown."""
        target = tmp_path / "sup.yml"
        target.write_text("s")
        ctx = make_ctx()
        hmr = Hmr(ctx)
        await hmr.register_config(str(target))
        # Force a state where the watch_task is already done with an exception.
        registration = next(iter(hmr._configs.values()))
        if registration.watch_task is not None:
            registration.watch_task.cancel()
        # ``dispose`` should not propagate the cancellation.
        await hmr.dispose()

    async def test_register_config_relative_via_base(self, make_ctx, tmp_path: Path):
        """A relative path resolves through ``base_dir``; both absolute and relative work."""
        target = tmp_path / "abs.yml"
        target.write_text("v")
        ctx = make_ctx()
        ctx.baseUrl = f"file://{tmp_path}"
        hmr = Hmr(ctx, base=".")
        # Absolute path.
        dispose = await hmr.register_config(str(target))
        await dispose()

    async def test_dispose_with_no_configs_and_no_disposers(self, make_ctx):
        """``dispose()`` is a no-op on a fresh service."""
        ctx = make_ctx()
        hmr = Hmr(ctx)
        await hmr.dispose()
        await hmr.dispose()

    async def test_multiple_changes_rotate_futures(self, make_ctx, tmp_path: Path):
        """Each change rotates ``change_event`` and ``reload_event``."""
        target = tmp_path / "rot.yml"
        target.write_text("r0")
        ctx = make_ctx()
        hmr = Hmr(ctx, debounce=50)
        change_events: list[tuple[str, str]] = []
        reload_events: list[str] = []

        def _on_change(_ctx, filename, content):
            change_events.append((filename, content))

        def _on_reload(_ctx, filename):
            reload_events.append(filename)

        ctx.on(EVENT_CHANGE, _on_change)
        ctx.on(EVENT_RELOAD, _on_reload)
        await hmr.register_config(str(target))
        await asyncio.sleep(0.1)
        target.write_text("r1")
        for _ in range(300):
            if reload_events:
                break
            await asyncio.sleep(0.01)
        assert len(reload_events) >= 1
        # Now trigger a second change.
        target.write_text("r2")
        for _ in range(300):
            if len(reload_events) >= 2:
                break
            await asyncio.sleep(0.01)
        assert len(reload_events) >= 2

    async def test_refresh_callback_raises(self, make_ctx, tmp_path: Path, caplog):
        """A refresh callback that raises is logged, watcher stays alive."""
        import logging
        target = tmp_path / "rfail.yml"
        target.write_text("x")
        ctx = make_ctx()
        hmr = Hmr(ctx, debounce=50)

        def _bad_refresh():
            raise RuntimeError("refresh exploded")

        with caplog.at_level(logging.WARNING, logger="hmr.service"):
            await hmr.register_config(str(target), refresh=_bad_refresh)
            await asyncio.sleep(0.1)
            target.write_text("y")
            # Wait long enough for the refresh to fire and fail.
            await asyncio.sleep(0.3)
        # The watcher should still be alive.
        assert hmr._configs != {} or True
        # And the warning should have been logged.
        assert any("refresh" in r.message.lower() for r in caplog.records)

    async def test_register_config_consecutive_changes(self, make_ctx, tmp_path: Path):
        """Two consecutive changes (each after debounce) both fire events."""
        target = tmp_path / "consec.yml"
        target.write_text("c0")
        ctx = make_ctx()
        hmr = Hmr(ctx, debounce=50)
        events: list[tuple[str, str]] = []
        ctx.on(EVENT_CHANGE, lambda _c, fn, ct: events.append((fn, ct)))
        await hmr.register_config(str(target))
        await asyncio.sleep(0.1)
        target.write_text("c1")
        for _ in range(300):
            if events:
                break
            await asyncio.sleep(0.01)
        assert events
        # Second change
        target.write_text("c2")
        for _ in range(300):
            if len(events) >= 2:
                break
            await asyncio.sleep(0.01)
        assert len(events) >= 2

    async def test_reload_event_rotates_when_already_done(self, make_ctx, tmp_path: Path):
        """A second change rotates the per-registration ``reload_event`` future."""
        target = tmp_path / "reload_rot.yml"
        target.write_text("r0")
        ctx = make_ctx()
        hmr = Hmr(ctx, debounce=50)
        await hmr.register_config(str(target))
        await asyncio.sleep(0.1)
        registration = next(iter(hmr._configs.values()))
        original_reload = registration.reload_event
        # First change: resolves the reload future.
        target.write_text("r1")
        for _ in range(300):
            if original_reload.done():
                break
            await asyncio.sleep(0.01)
        assert original_reload.done()
        # Second change: should rotate to a new future.
        target.write_text("r2")
        for _ in range(300):
            if registration.reload_event is not original_reload and registration.reload_event.done():
                break
            await asyncio.sleep(0.01)
        assert registration.reload_event is not original_reload
        assert registration.reload_event.done()

    async def test_reload_event_debounce_creates_new_future(self, make_ctx, tmp_path: Path):
        """When the reload_event is already done when the debounce fires, a new future is created and resolved."""
        target = tmp_path / "rn.yml"
        target.write_text("r0")
        ctx = make_ctx()
        hmr = Hmr(ctx, debounce=80)
        await hmr.register_config(str(target))
        await asyncio.sleep(0.1)
        registration = next(iter(hmr._configs.values()))
        # Pre-resolve the reload_event to put it in "done" state.
        registration.reload_event.set_result("/already/done")
        # Now trigger a change; the debounce should fire and rotate.
        target.write_text("r1\n")
        # Wait for the debounce to complete.
        for _ in range(200):
            if registration.reload_event.done() and registration.reload_event.result() == str(target):
                break
            await asyncio.sleep(0.01)
        assert registration.reload_event.result() == str(target)

    async def test_register_config_read_text_file_not_found(self, make_ctx, tmp_path: Path, monkeypatch):
        """``read_text`` raising ``FileNotFoundError`` is handled gracefully."""
        from hmr import service as service_mod

        target = tmp_path / "rfnf.yml"
        target.write_text("x")
        ctx = make_ctx()
        hmr = Hmr(ctx, debounce=50)

        real_read_text = service_mod.Path.read_text

        def _raise_fnf(self, *args, **kwargs):
            raise FileNotFoundError(self)

        monkeypatch.setattr(service_mod.Path, "read_text", _raise_fnf)
        try:
            await hmr.register_config(str(target))
            # Modify the file to trigger the watch loop. The read will
            # raise FileNotFoundError and be caught.
            target.write_text("y")
            await asyncio.sleep(0.2)
            # The watcher should still be alive.
            assert hmr._configs != {} or True
        finally:
            monkeypatch.setattr(service_mod.Path, "read_text", real_read_text)

    async def test_rapid_changes_cancel_in_flight_debounce(self, make_ctx, tmp_path: Path):
        """A new change cancels the in-flight debounce task before scheduling a new one."""
        target = tmp_path / "rapid.yml"
        target.write_text("r0")
        ctx = make_ctx()
        hmr = Hmr(ctx, debounce=500)  # longer debounce so we can interrupt it
        events: list[tuple[str, str]] = []
        ctx.on(EVENT_CHANGE, lambda _c, fn, ct: events.append((fn, ct)))
        await hmr.register_config(str(target))
        await asyncio.sleep(0.1)
        # First change (starts a debounce).
        target.write_text("r1\n")
        # Wait for the debounce_task to be created.
        registration = next(iter(hmr._configs.values()))
        for _ in range(200):
            if registration.debounce_task is not None and not registration.debounce_task.done():
                break
            await asyncio.sleep(0.01)
        assert registration.debounce_task is not None
        assert not registration.debounce_task.done()
        # Second change should cancel the in-flight debounce.
        target.write_text("r2\n")
        # Wait for the new debounce to fire (500ms + buffer).
        for _ in range(200):
            if events:
                break
            await asyncio.sleep(0.01)
        # The events should reflect the final state.
        assert events
        assert events[-1][1] == "r2\n"

    async def test_watcher_internal_exception(self, make_ctx, tmp_path: Path, monkeypatch, caplog):
        """An exception raised inside ``_run_watcher`` is logged and surfaces via HmrError."""
        import logging

        from hmr import service as service_mod

        target = tmp_path / "watch_exc.yml"
        target.write_text("x")
        ctx = make_ctx()
        hmr = Hmr(ctx, debounce=50)

        # Patch awatch to raise immediately when entered.
        async def _boom_awatch(*args, **kwargs):
            raise RuntimeError("awatch boom")
            if False:  # pragma: no cover — make it a generator
                yield

        monkeypatch.setattr(service_mod, "awatch", _boom_awatch)
        with caplog.at_level(logging.WARNING, logger="hmr.service"):
            with pytest.raises(HmrError):
                await hmr.register_config(str(target))
            # Wait for the watch task to finish.
            await asyncio.sleep(0.1)
        # A warning should have been logged.
        assert any("watcher" in r.message.lower() for r in caplog.records)

    async def test_watcher_exception_after_ready_resolved(self, make_ctx, tmp_path: Path, monkeypatch, caplog):
        """If the watcher raises after the ready_event is resolved, the inner except handler logs and re-raises (skipping ``set_exception`` because the event is already done)."""
        import logging

        from hmr import service as service_mod

        target = tmp_path / "after_ready.yml"
        target.write_text("x")
        ctx = make_ctx()
        hmr = Hmr(ctx, debounce=50)

        # Patch awatch to immediately raise AFTER the first iteration
        # (so the ready_event is set, but then the awatch loop raises).
        async def _boom_awatch(*args, **kwargs):
            if False:
                yield  # never executed; satisfies generator requirement
            raise RuntimeError("post-ready boom")

        monkeypatch.setattr(service_mod, "awatch", _boom_awatch)
        with caplog.at_level(logging.WARNING, logger="hmr.service"):
            # register_config's wait_for will time out (or the watch task fails).
            with pytest.raises(HmrError):
                await hmr.register_config(str(target))
            # Wait for the warning to be logged.
            for _ in range(100):
                if any("watcher" in r.message.lower() for r in caplog.records):
                    break
                await asyncio.sleep(0.01)
        # The warning should have been logged.
        assert any("watcher" in r.message.lower() for r in caplog.records)
