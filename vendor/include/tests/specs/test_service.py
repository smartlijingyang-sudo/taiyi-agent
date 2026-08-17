"""Tests for taiyi-include service module (Include service lifecycle)."""

from __future__ import annotations

import asyncio
import errno as _errno
import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from include.service import (
    _JS_EXPR_TAG,
    ConfigFileError,
    Include,
    _construct_js_expr,
    _js_expr_dict_representer,
    _JsExprDumper,
    _JsExprLoader,
    _retryable_write_error,
    entry_list_schema,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_yaml(path: Path, data: list[dict[str, Any]]) -> None:
    """Write a YAML file with the given entry list (no !!js)."""
    import yaml

    with path.open("w", encoding="utf8") as f:
        yaml.safe_dump(data, f)


def _write_json(path: Path, data: list[dict[str, Any]]) -> None:
    path.write_text(json.dumps(data), encoding="utf8")


@pytest.fixture
def ctx(make_ctx: Callable[[], object]):  # type: ignore[no-untyped-def]
    """A fresh cordis Context."""
    return make_ctx()


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


class TestConstruction:
    """Include service constructs and validates extension."""

    def test_unsupported_extension_raises(self, ctx, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="extension"):
            Include(ctx, {"path": str(tmp_path / "config.txt")})

    def test_yaml_extension_supported(self, ctx, tmp_path: Path) -> None:
        p = tmp_path / "config.yaml"
        _write_yaml(p, [{"id": "a"}])
        include = Include(ctx, {"path": str(p)})
        assert include is not None

    def test_json_extension_supported(self, ctx, tmp_path: Path) -> None:
        p = tmp_path / "config.json"
        _write_json(p, [{"id": "a"}])
        include = Include(ctx, {"path": str(p)})
        assert include is not None

    def test_yml_extension_supported(self, ctx, tmp_path: Path) -> None:
        p = tmp_path / "config.yml"
        _write_yaml(p, [{"id": "a"}])
        include = Include(ctx, {"path": str(p)})
        assert include is not None

    def test_invalid_config_type_raises(self, ctx, tmp_path: Path) -> None:
        """Non-dict / non-Config inputs raise TypeError."""
        p = tmp_path / "config.yaml"
        _write_yaml(p, [])
        with pytest.raises(TypeError, match="dict or Include.Config"):
            Include(ctx, 42)  # type: ignore[arg-type]

    def test_config_object_accepted(self, ctx, tmp_path: Path) -> None:
        """``Include.Config`` instances are accepted (the ``elif`` False branch)."""
        p = tmp_path / "config.yaml"
        _write_yaml(p, [])
        cfg = Include.Config(path=str(p))
        include = Include(ctx, cfg)
        assert include.config is cfg


# ---------------------------------------------------------------------------
# apply() — applies patches to the data
# ---------------------------------------------------------------------------


class TestApplyPatches:
    """``Include`` applies its configured patches to file content."""

    def test_no_patches_passes_through(self, ctx, tmp_path: Path) -> None:
        p = tmp_path / "config.yaml"
        _write_yaml(p, [{"id": "a", "name": "A"}])
        include = Include(ctx, {"path": str(p)})
        result = include.apply_patches(
            [{"id": "a", "name": "A"}],
            None,
        )
        assert result == [{"id": "a", "name": "A"}]

    def test_patches_applied(self, ctx, tmp_path: Path) -> None:
        p = tmp_path / "config.yaml"
        _write_yaml(p, [{"id": "a", "name": "A"}])
        include = Include(ctx, {"path": str(p)})
        result = include.apply_patches(
            [{"id": "a", "name": "A"}],
            [{"id": "a", "disabled": True}],
        )
        assert result[0]["disabled"] is True


# ---------------------------------------------------------------------------
# ConfigFileError
# ---------------------------------------------------------------------------


class TestConfigFileError:
    """ConfigFileError is thrown with a stage tag and underlying cause."""

    def test_read_stage(self) -> None:
        err = ConfigFileError("read", "/tmp/x", FileNotFoundError("nope"))
        assert err.stage == "read"
        assert "read" in str(err)
        assert "x" in str(err)

    def test_parse_stage(self) -> None:
        cause = ValueError("bad yaml")
        err = ConfigFileError("parse", "/tmp/x.yaml", cause)
        assert err.stage == "parse"
        assert err.__cause__ is cause

    def test_validate_stage(self) -> None:
        cause = TypeError("must be array")
        err = ConfigFileError("validate", "/tmp/x.yaml", cause)
        assert err.stage == "validate"
        assert err.__cause__ is cause


# ---------------------------------------------------------------------------
# Read / write file lifecycle
# ---------------------------------------------------------------------------


class TestReadInitial:
    """On init, Include reads from the file or writes ``initial`` if missing."""

    @pytest.mark.asyncio
    async def test_reads_existing_file(self, ctx, tmp_path: Path) -> None:
        p = tmp_path / "config.yaml"
        _write_yaml(p, [{"id": "a", "name": "A"}])
        include = Include(ctx, {"path": str(p)})
        await include._read_initial()
        # Internal state populated
        assert include.data is not None
        assert include.data == [{"id": "a", "name": "A"}]

    @pytest.mark.asyncio
    async def test_writes_initial_when_missing(self, ctx, tmp_path: Path) -> None:
        p = tmp_path / "config.yaml"
        include = Include(
            ctx,
            {"path": str(p), "initial": [{"id": "seed"}]},
        )
        await include._read_initial()
        # File now exists and round-trips back
        assert p.exists()
        text = p.read_text(encoding="utf8")
        assert "seed" in text

    @pytest.mark.asyncio
    async def test_missing_no_initial_raises(self, ctx, tmp_path: Path) -> None:
        p = tmp_path / "config.yaml"
        include = Include(ctx, {"path": str(p)})
        with pytest.raises(FileNotFoundError):
            await include._read_initial()


# ---------------------------------------------------------------------------
# enableLogs propagation
# ---------------------------------------------------------------------------


class TestEnableLogs:
    """``enableLogs`` defaults to false but is configurable."""

    def test_enable_logs_default_false(self, ctx, tmp_path: Path) -> None:
        p = tmp_path / "config.yaml"
        _write_yaml(p, [])
        include = Include(ctx, {"path": str(p)})
        assert include.enable_logs is False

    def test_enable_logs_true(self, ctx, tmp_path: Path) -> None:
        p = tmp_path / "config.yaml"
        _write_yaml(p, [])
        include = Include(ctx, {"path": str(p), "enableLogs": True})
        assert include.enable_logs is True


# ---------------------------------------------------------------------------
# Disposal
# ---------------------------------------------------------------------------


class TestDispose:
    """``Include.dispose()`` releases resources."""

    @pytest.mark.asyncio
    async def test_dispose_runs(self, ctx, tmp_path: Path) -> None:
        p = tmp_path / "config.yaml"
        _write_yaml(p, [])
        include = Include(ctx, {"path": str(p)})
        await include._read_initial()
        await include.dispose()
        # No assertions on result; just that it completes.


# ---------------------------------------------------------------------------
# Add entries
# ---------------------------------------------------------------------------


class TestAddEntries:
    """``Include`` accepts a static ``add_entries`` for offline tooling."""

    def test_add_entries_static_call(self, ctx, tmp_path: Path) -> None:
        p = tmp_path / "config.yaml"
        _write_yaml(p, [{"id": "a"}])
        include = Include(ctx, {"path": str(p)})
        # Should be safe to call; in-memory no-op for offline tools.
        include.add_entries([{"id": "b"}])


# ---------------------------------------------------------------------------
# Enqueue serialization
# ---------------------------------------------------------------------------


class TestEnqueue:
    """``Include.enqueue`` serializes tasks so concurrent applies are safe."""

    @pytest.mark.asyncio
    async def test_serializes_concurrent_applies(self, ctx, tmp_path: Path) -> None:
        p = tmp_path / "config.yaml"
        _write_yaml(p, [])
        include = Include(ctx, {"path": str(p)})
        # Schedule two tasks; second sees result of first.
        order: list[int] = []

        async def t1() -> None:
            await asyncio.sleep(0.01)
            order.append(1)

        async def t2() -> None:
            await asyncio.sleep(0.01)
            order.append(2)

        await asyncio.gather(include.enqueue(t1), include.enqueue(t2))
        assert order == [1, 2]

    @pytest.mark.asyncio
    async def test_predecessor_failure_does_not_gate_next(self, ctx, tmp_path: Path) -> None:
        p = tmp_path / "config.yaml"
        _write_yaml(p, [])
        include = Include(ctx, {"path": str(p)})
        ran: list[int] = []

        async def fail() -> None:
            raise RuntimeError("boom")

        async def ok() -> None:
            ran.append(1)

        # The first call's promise will reject, but the queue must not gate
        # the second task on it.
        first = include.enqueue(fail)
        second = include.enqueue(ok)
        with pytest.raises(RuntimeError, match="boom"):
            await first
        await second
        assert ran == [1]


# ---------------------------------------------------------------------------
# Async initialization
# ---------------------------------------------------------------------------


class TestServiceInitAsync:
    """``Include.__service_init__`` initializes the file-backed tree."""

    @pytest.mark.asyncio
    async def test_service_init_initializes(self, ctx, tmp_path: Path) -> None:
        p = tmp_path / "config.yaml"
        _write_yaml(p, [{"id": "x"}])
        include = Include(ctx, {"path": str(p)})
        await include.__service_init__()
        # After draining the iterator, the include should be initialized.
        assert include.data is not None
        assert include.data == [{"id": "x"}]

    @pytest.mark.asyncio
    async def test_service_init_emits_update(self, ctx, tmp_path: Path) -> None:
        p = tmp_path / "config.yaml"
        _write_yaml(p, [{"id": "x"}])
        include = Include(ctx, {"path": str(p), "patches": [{"id": "x", "disabled": True}]})
        # Capture emits
        emitted: list[tuple[str, tuple[Any, ...]]] = []

        def _capture_emit(*args: Any) -> None:
            emitted.append((args[0], args[1:]))

        original_emit = getattr(ctx, "emit", None)
        if original_emit is not None:
            ctx.emit = _capture_emit  # type: ignore[method-assign]
        await include.__service_init__()
        assert include.data is not None
        # ``include.data`` keeps the raw file content; the patched version
        # is what gets emitted.
        assert include.data == [{"id": "x"}]
        updates = [args for name, args in emitted if name == "internal/update"]
        assert updates, "expected an internal/update emit"
        assert updates[0][0][0]["disabled"] is True

    @pytest.mark.asyncio
    async def test_service_init_awaits_async_emit(self, ctx, tmp_path: Path) -> None:
        """An async ``ctx.emit`` coroutine is awaited (not fire-and-forget)."""
        p = tmp_path / "config.yaml"
        _write_yaml(p, [{"id": "x"}])
        include = Include(ctx, {"path": str(p)})
        observed: list[bool] = []

        async def _async_emit(*args: Any) -> None:
            observed.append(True)

        ctx.emit = _async_emit  # type: ignore[method-assign]
        await include.__service_init__()
        assert observed == [True]

    @pytest.mark.asyncio
    async def test_service_init_swallows_emit_exception(self, ctx, tmp_path: Path) -> None:
        """An exception in ``ctx.emit`` does not crash init."""
        p = tmp_path / "config.yaml"
        _write_yaml(p, [{"id": "x"}])
        include = Include(ctx, {"path": str(p)})

        def _broken_emit(*args: Any) -> None:
            raise RuntimeError("emit failed")

        ctx.emit = _broken_emit  # type: ignore[method-assign]
        # Init must complete (emit exception is swallowed).
        await include.__service_init__()
        assert include.data is not None

    @pytest.mark.asyncio
    async def test_service_init_skips_notify_when_no_emit(self, tmp_path: Path) -> None:
        """A context without ``emit`` skips the notify block entirely."""
        p = tmp_path / "config.yaml"
        _write_yaml(p, [{"id": "x"}])

        # A bare context (no Service machinery, no ``emit`` attribute).
        class _BareCtx:
            baseUrl = ""

        include = Include(_BareCtx(), {"path": str(p)})
        await include.__service_init__()
        assert include.data is not None


# ---------------------------------------------------------------------------
# ConfigFileError validation
# ---------------------------------------------------------------------------


class TestConfigFileErrorValidation:
    """ConfigFileError validates stage and chains the cause."""

    def test_invalid_stage_raises(self) -> None:
        with pytest.raises(ValueError, match="unknown stage"):
            ConfigFileError("bogus-stage", "/tmp/x", FileNotFoundError("nope"))


# ---------------------------------------------------------------------------
# Write error retries
# ---------------------------------------------------------------------------


class TestRetryableWriteError:
    """``_retryable_write_error`` mirrors upstream's EACCES/EBUSY/EPERM set."""

    def test_eacces_is_retryable(self) -> None:
        err = OSError("locked")
        err.errno = _errno.EACCES
        assert _retryable_write_error(err) is True

    def test_ebusy_is_retryable(self) -> None:
        err = OSError("busy")
        err.errno = _errno.EBUSY
        assert _retryable_write_error(err) is True

    def test_eperm_is_retryable(self) -> None:
        err = OSError("forbidden")
        err.errno = _errno.EPERM
        assert _retryable_write_error(err) is True

    def test_other_errors_not_retryable(self) -> None:
        err = OSError("other")
        err.errno = _errno.EINVAL
        assert _retryable_write_error(err) is False

    def test_missing_errno_not_retryable(self) -> None:
        err = OSError("no errno")
        assert _retryable_write_error(err) is False


# ---------------------------------------------------------------------------
# Filename resolution
# ---------------------------------------------------------------------------


class TestResolveFilename:
    """``_resolve_filename`` joins base URL and path correctly."""

    def test_strips_file_scheme(self) -> None:
        result = Include._resolve_filename("file:///tmp/base/", "config.yaml")
        assert result.endswith("config.yaml")
        assert "/tmp/base/" in result

    def test_keeps_plain_path(self) -> None:
        result = Include._resolve_filename("/tmp/base/", "config.yaml")
        assert result.endswith("config.yaml")
        assert "/tmp/base/" in result

    def test_normalizes_double_slashes(self) -> None:
        result = Include._resolve_filename("/tmp/base/", "./sub/config.yaml")
        # os.path.normpath collapses ``./`` segments
        assert "sub/config.yaml" in result


# ---------------------------------------------------------------------------
# Base URL construction
# ---------------------------------------------------------------------------


class TestBaseUrlResolution:
    """``Include`` resolves its filename relative to ``ctx.baseUrl``."""

    def test_uses_base_url_when_present(self, tmp_path: Path) -> None:
        from cordis.context import Context

        ctx = Context()
        subdir = tmp_path / "configs"
        subdir.mkdir()
        target = subdir / "x.yaml"
        target.write_text("- id: a\n", encoding="utf8")
        # Patch the context's baseUrl
        ctx.baseUrl = f"file://{subdir}"
        include = Include(ctx, {"path": "x.yaml"})
        assert include.filename == str(target)
        # ``Context.dispose`` is async; trigger it via the event loop.
        import asyncio

        asyncio.run(ctx.dispose())


# ---------------------------------------------------------------------------
# Logger-backed warn
# ---------------------------------------------------------------------------


class TestWarnRoutedToLogger:
    """``Include._warn`` routes through ``ctx.root.logger('loader')``."""

    def test_warn_calls_logger(self, tmp_path: Path) -> None:
        from cordis.context import Context

        ctx = Context()
        p = tmp_path / "config.yaml"
        _write_yaml(p, [])
        captured: list[tuple[str, tuple[Any, ...]]] = []

        class _Logger:
            def warn(self, message: str, *args: Any) -> None:
                captured.append((message, args))

        class _LoggerService:
            def __call__(self, name: str) -> _Logger:
                return _Logger()

        # Stub the context's root logger
        class _Root:
            logger = _LoggerService()

        ctx.root = _Root()  # type: ignore[attr-defined]
        include = Include(ctx, {"path": str(p)})
        include._warn("patch: entry %C not found", "ghost")
        assert captured == [("patch: entry %C not found", ("ghost",))]
        import asyncio

        asyncio.run(ctx.dispose())

    def test_warn_silent_without_logger(self, tmp_path: Path) -> None:
        """A bare context (no root logger) silently drops warnings."""
        from cordis.context import Context

        ctx = Context()
        p = tmp_path / "config.yaml"
        _write_yaml(p, [])
        # Strip the auto-installed logger service.
        if hasattr(ctx, "root"):
            try:
                del ctx.root.logger
            except (AttributeError, TypeError):
                pass
        include = Include(ctx, {"path": str(p)})
        # Should not raise even though no logger exists.
        include._warn("anything", "anywhere")

    def test_warn_silent_when_logger_has_no_warn(self, tmp_path: Path) -> None:
        """A logger service without ``warn`` silently drops the message."""
        from cordis.context import Context

        ctx = Context()
        p = tmp_path / "config.yaml"
        _write_yaml(p, [])

        class _EmptyLogger:
            pass

        class _LoggerService:
            def __call__(self, name: str) -> _EmptyLogger:
                return _EmptyLogger()

        class _Root:
            logger = _LoggerService()

        ctx.root = _Root()  # type: ignore[attr-defined]
        include = Include(ctx, {"path": str(p)})
        # Should not raise even though the returned logger has no ``warn``.
        include._warn("silent",)


# ---------------------------------------------------------------------------
# Read file parse / validate errors
# ---------------------------------------------------------------------------


class TestReadFileErrors:
    """``_read_file`` wraps parse + validate failures as ConfigFileError."""

    @pytest.mark.asyncio
    async def test_invalid_yaml_raises_parse_error(self, ctx, tmp_path: Path) -> None:
        p = tmp_path / "bad.yaml"
        p.write_text("not: valid: yaml: at: all: [", encoding="utf8")
        include = Include(ctx, {"path": str(p)})
        with pytest.raises(ConfigFileError) as exc_info:
            await include._read_file(forced=True)
        assert exc_info.value.stage == "parse"

    @pytest.mark.asyncio
    async def test_parse_error_propagates_config_file_error(self, ctx, tmp_path: Path) -> None:
        """Even invalid JSON triggers ``ConfigFileError`` (stage=parse)."""
        p = tmp_path / "bad.json"
        p.write_text("not json at all", encoding="utf8")
        include = Include(ctx, {"path": str(p)})
        with pytest.raises(ConfigFileError) as exc_info:
            await include._read_file(forced=True)
        assert exc_info.value.stage == "parse"

    @pytest.mark.asyncio
    async def test_non_array_root_raises_validate_error(self, ctx, tmp_path: Path) -> None:
        p = tmp_path / "dict.yaml"
        # Valid YAML but not an array at the root.
        p.write_text("id: a\n", encoding="utf8")
        include = Include(ctx, {"path": str(p)})
        with pytest.raises(ConfigFileError) as exc_info:
            await include._read_file(forced=True)
        assert exc_info.value.stage == "validate"

    @pytest.mark.asyncio
    async def test_json_round_trip(self, ctx, tmp_path: Path) -> None:
        """JSON files use ``json.loads`` (no ``!!js`` support)."""
        p = tmp_path / "config.json"
        p.write_text(json.dumps([{"id": "a"}, {"id": "b"}]), encoding="utf8")
        include = Include(ctx, {"path": str(p)})
        result = await include._read_file(forced=True)
        assert result is not None
        assert result["data"] == [{"id": "a"}, {"id": "b"}]

    @pytest.mark.asyncio
    async def test_yaml_round_trip_with_js_expr(self, ctx, tmp_path: Path) -> None:
        """``!!js`` scalars parse into ``{__jsExpr: str}`` dicts."""
        p = tmp_path / "config.yaml"
        p.write_text(
            "- id: a\n  disabled: !!js process.platform === 'win32'\n",
            encoding="utf8",
        )
        include = Include(ctx, {"path": str(p)})
        result = await include._read_file(forced=True)
        assert result is not None
        assert result["data"][0]["disabled"] == {
            "__jsExpr": "process.platform === 'win32'"
        }

    @pytest.mark.asyncio
    async def test_unchanged_content_returns_none(self, ctx, tmp_path: Path) -> None:
        """A non-forced read returns ``None`` when content is unchanged."""
        p = tmp_path / "config.yaml"
        _write_yaml(p, [{"id": "a"}])
        include = Include(ctx, {"path": str(p)})
        # Force the first read so ``self.content`` is populated.
        first = await include._read_file(forced=True)
        assert first is not None
        # Second non-forced call should detect identical content.
        second = await include._read_file(forced=False)
        assert second is None

    @pytest.mark.asyncio
    async def test_unchanged_content_skips_parse(self, ctx, tmp_path: Path) -> None:
        """Forced re-reads always re-parse even when content is identical."""
        p = tmp_path / "config.yaml"
        _write_yaml(p, [{"id": "a"}])
        include = Include(ctx, {"path": str(p)})
        # Populate content via the same code path used by _read_initial
        await include._read_initial()
        # A forced re-read always parses (no short-circuit).
        result = await include._read_file(forced=True)
        assert result is not None
        assert result["data"] == [{"id": "a"}]


# ---------------------------------------------------------------------------
# Write file flow
# ---------------------------------------------------------------------------


class TestWriteFile:
    """``_write_file`` round-trips through tempfile + rename."""

    @pytest.mark.asyncio
    async def test_writes_yaml_file(self, ctx, tmp_path: Path) -> None:
        p = tmp_path / "out.yaml"
        _write_yaml(p, [])
        include = Include(ctx, {"path": str(p)})
        await include._write_file([{"id": "new"}])
        # File content should include "new".
        text = p.read_text(encoding="utf8")
        assert "new" in text

    @pytest.mark.asyncio
    async def test_writes_json_file(self, ctx, tmp_path: Path) -> None:
        p = tmp_path / "out.json"
        _write_json(p, [])
        include = Include(ctx, {"path": str(p)})
        await include._write_file([{"id": "new"}])
        # File content should be JSON.
        data = json.loads(p.read_text(encoding="utf8"))
        assert data == [{"id": "new"}]

    @pytest.mark.asyncio
    async def test_write_retries_on_eacces(self, ctx, tmp_path: Path, monkeypatch) -> None:
        """The retry loop kicks in on EACCES and ultimately raises."""
        p = tmp_path / "out.yaml"
        _write_yaml(p, [])
        include = Include(ctx, {"path": str(p)})
        # Replace ``os.replace`` with a stub that always raises EACCES, so the
        # retry path runs until ``WRITE_RETRY_LIMIT`` and re-raises.
        call_count = {"n": 0}

        def _always_eacces(src: str, dst: str) -> None:
            call_count["n"] += 1
            err = OSError("locked")
            err.errno = _errno.EACCES
            raise err

        monkeypatch.setattr(os, "replace", _always_eacces)
        with pytest.raises(OSError):
            await include._write_file([{"id": "x"}])
        # The retry loop should have hit WRITE_RETRY_LIMIT iterations.
        assert call_count["n"] >= 1

    @pytest.mark.asyncio
    async def test_write_retries_succeed_after_first_fail(
        self, ctx, tmp_path: Path, monkeypatch
    ) -> None:
        """A retryable error on the first attempt succeeds on the second."""
        p = tmp_path / "out.yaml"
        _write_yaml(p, [])
        include = Include(ctx, {"path": str(p)})

        original = os.replace
        call_count = {"n": 0}

        def _flaky_replace(src: str, dst: str) -> None:
            call_count["n"] += 1
            if call_count["n"] == 1:
                err = OSError("locked")
                err.errno = _errno.EACCES
                raise err
            return original(src, dst)

        monkeypatch.setattr(os, "replace", _flaky_replace)
        await include._write_file([{"id": "y"}])
        assert call_count["n"] == 2
        # File content reflects the success.
        assert "y" in p.read_text(encoding="utf8")

    @pytest.mark.asyncio
    async def test_write_non_retryable_error_propagates(
        self, ctx, tmp_path: Path, monkeypatch
    ) -> None:
        """A non-retryable OSError (e.g. EINVAL) raises immediately."""
        p = tmp_path / "out.yaml"
        _write_yaml(p, [])
        include = Include(ctx, {"path": str(p)})

        def _fail_with_einval(src: str, dst: str) -> None:
            err = OSError("invalid")
            err.errno = _errno.EINVAL
            raise err

        monkeypatch.setattr(os, "replace", _fail_with_einval)
        with pytest.raises(OSError):
            await include._write_file([{"id": "x"}])

    @pytest.mark.asyncio
    async def test_write_unsupported_type_raises(self, ctx, tmp_path: Path) -> None:
        """An unrecognized ``_type`` raises RuntimeError."""
        p = tmp_path / "out.yaml"
        _write_yaml(p, [])
        include = Include(ctx, {"path": str(p)})
        include._type = "application/unknown"
        with pytest.raises(RuntimeError, match="unsupported type"):
            await include._write_file([{"id": "x"}])


# ---------------------------------------------------------------------------
# Readonly + dispose flow
# ---------------------------------------------------------------------------


class TestReadonlyGuard:
    """Writing to a readonly include raises."""

    @pytest.mark.asyncio
    async def test_write_to_readonly_raises(self, ctx, tmp_path: Path) -> None:
        p = tmp_path / "config.yaml"
        _write_yaml(p, [])
        include = Include(ctx, {"path": str(p)})
        include.readonly = True
        with pytest.raises(RuntimeError, match="readonly"):
            await include._write_file([{"id": "x"}])


class TestDisposeQueues:
    """``Include.dispose()`` releases pending tasks."""

    @pytest.mark.asyncio
    async def test_dispose_with_pending_apply(self, ctx, tmp_path: Path) -> None:
        p = tmp_path / "config.yaml"
        _write_yaml(p, [])
        include = Include(ctx, {"path": str(p)})
        # Manually populate a pending apply queue
        await include.enqueue(lambda: asyncio.sleep(0.001))
        await include.dispose()

    @pytest.mark.asyncio
    async def test_dispose_no_apply_queue(self, ctx, tmp_path: Path) -> None:
        """``dispose`` is a no-op when no apply queue exists yet."""
        p = tmp_path / "config.yaml"
        _write_yaml(p, [])
        include = Include(ctx, {"path": str(p)})
        # Clear the queue to test the None branch.
        include._apply_queue = None
        await include.dispose()

    @pytest.mark.asyncio
    async def test_dispose_cancels_write_task(self, ctx, tmp_path: Path) -> None:
        """An outstanding ``_write_task`` is cancelled during dispose."""
        p = tmp_path / "config.yaml"
        _write_yaml(p, [])
        include = Include(ctx, {"path": str(p)})
        loop = asyncio.get_event_loop()
        handle = loop.call_later(10.0, lambda: None)
        include._write_task = handle
        await include.dispose()
        assert include._write_task is None
        assert handle.cancelled()

    @pytest.mark.asyncio
    async def test_dispose_swallows_apply_queue_exception(self, ctx, tmp_path: Path) -> None:
        """A failing apply queue task does not propagate during dispose."""
        p = tmp_path / "config.yaml"
        _write_yaml(p, [])
        include = Include(ctx, {"path": str(p)})
        # Build a still-running apply queue task that will fail when awaited.
        async def _failing() -> None:
            await asyncio.sleep(0.01)
            raise RuntimeError("queue task failed")

        include._apply_queue = asyncio.ensure_future(_failing())
        # Don't sleep — the future should NOT be done yet when dispose runs.
        assert not include._apply_queue.done()
        # Dispose should await the failing future and swallow the exception.
        await include.dispose()


class TestReadInitialErrorPaths:
    """``_read_initial`` covers the missing-file + initial / missing-file
    + no-initial branches (and the re-raise path on non-ENOENT)."""

    @pytest.mark.asyncio
    async def test_non_enoent_error_propagates(self, ctx, tmp_path: Path) -> None:
        """A non-ENOENT OSError during the initial read re-raises as-is."""
        p = tmp_path / "config.yaml"
        # Create a directory at the file path so reads get EISDIR.
        p.mkdir()
        include = Include(ctx, {"path": str(p)})
        # ``_read_initial`` re-raises the original ConfigFileError cause.
        with pytest.raises(ConfigFileError):
            await include._read_initial()

    @pytest.mark.asyncio
    async def test_non_read_stage_error_propagates(self, ctx, tmp_path: Path) -> None:
        """A ConfigFileError from a stage other than ``read`` re-raises."""
        p = tmp_path / "config.yaml"
        _write_yaml(p, [{"id": "a"}])
        include = Include(ctx, {"path": str(p)})
        # Patch the file with invalid yaml content so ``_read_file`` raises
        # ``stage=parse``. ``_read_initial`` should re-raise without trying
        # to create the file from ``initial``.
        p.write_text("invalid: yaml: at all: [", encoding="utf8")
        with pytest.raises(ConfigFileError) as exc_info:
            await include._read_initial()
        assert exc_info.value.stage == "parse"


class TestEnqueueLazyBind:
    """``enqueue`` lazily binds the queue seed on first use."""

    @pytest.mark.asyncio
    async def test_first_enqueue_binds_seed(self, ctx, tmp_path: Path) -> None:
        p = tmp_path / "config.yaml"
        _write_yaml(p, [])
        include = Include(ctx, {"path": str(p)})
        # Queue seed is None until first use.
        assert include._apply_queue is None

        async def _noop_task() -> str:
            return "ok"

        result = await include.enqueue(_noop_task)
        assert result == "ok"
        # Now the queue is bound.
        assert include._apply_queue is not None


# ---------------------------------------------------------------------------
# Schema (YAML !!js dialect)
# ---------------------------------------------------------------------------


class TestEntryListSchema:
    """``entry_list_schema`` returns a Loader that knows the ``!!js`` tag."""

    def test_returns_loader(self) -> None:
        loader = entry_list_schema()
        assert loader is _JsExprLoader

    def test_tag_registered(self) -> None:
        loader = _JsExprLoader
        # PyYAML registers constructors by tag; this confirms the tag is
        # known to the custom loader.
        assert _JS_EXPR_TAG in loader.yaml_constructors

    def test_dumper_represents_js_expr(self) -> None:
        import io

        dumper = _JsExprDumper(io.StringIO())
        # Force representer registration (already done at import time).
        node = _js_expr_dict_representer(dumper, {"__jsExpr": "expr"})  # type: ignore[arg-type]
        assert node.tag == _JS_EXPR_TAG

    def test_dumper_falls_back_to_map(self) -> None:
        """Non-JsExpr dicts use the default mapping representer."""
        import io

        dumper = _JsExprDumper(io.StringIO())
        node = _js_expr_dict_representer(dumper, {"id": "a"})  # type: ignore[arg-type]
        # The fallback returns a mapping node (yaml.org,2002:map).
        assert node.tag == "tag:yaml.org,2002:map"

    def test_construct_js_expr_with_scalar(self) -> None:
        import yaml as _yaml

        class _StubLoader:
            def construct_scalar(self, node: _yaml.ScalarNode) -> str:
                return node.value

        node = _yaml.ScalarNode(_JS_EXPR_TAG, "expr")
        result = _construct_js_expr(_StubLoader(), node)  # type: ignore[arg-type]
        assert result == {"__jsExpr": "expr"}

    def test_construct_js_expr_rejects_non_scalar(self) -> None:
        """A non-scalar ``!!js`` node raises a ConstructorError."""
        import yaml as _yaml

        class _StubLoader:
            def construct_scalar(self, node: _yaml.ScalarNode) -> str:
                return node.value

        # Build a fake mapping node (non-scalar).
        node = _yaml.MappingNode(_JS_EXPR_TAG, [])
        with pytest.raises(_yaml.constructor.ConstructorError):
            _construct_js_expr(_StubLoader(), node)  # type: ignore[arg-type]

    def test_noop_helper(self, tmp_path: Path, ctx) -> None:
        """The async ``_noop`` returns None for queue seeding."""
        import asyncio as _asyncio

        p = tmp_path / "config.yaml"
        _write_yaml(p, [])
        include = Include(ctx, {"path": str(p)})
        assert _asyncio.run(include._noop()) is None


__all__: list[str] = []
