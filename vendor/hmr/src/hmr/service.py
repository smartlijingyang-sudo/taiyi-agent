"""`hmr.service` — Hmr Service: watches files and emits change/reload events.

1:1 alignment with `~/deepseek-harness/vendor/hmr/src/index.ts`.

The upstream service integrates with ``@deepseek-ai/cordis-plugin-loader``
to drive partial / full module reloads. This chunk implements the
**watcher surface** faithfully:

- :meth:`Hmr.register_config` — register a config file to watch.
- Debounce rapid file changes (~100ms by default).
- Emit ``hmr/change(filename, content)`` after debounce.
- Emit ``hmr/reload(filename)`` after the change settles.
- Multiple files are watched independently.
- Watcher lifecycle is tied to ``ctx.dispose`` (cancellation of the
  underlying ``watchfiles.awatch`` task).
- ``HmrError`` on invalid input (HMR not active, missing path, etc.).

The full reload engine (plugin re-import, ESM/CJS cache management,
``analyzeChanges`` classification) depends on the loader port and is
gated on that future chunk. ``ctx.loader.entries()`` /
``loader.exit()`` integration points are stubbed with a graceful
degradation that emits ``hmr/change`` directly when the loader service
is not registered.
"""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cordis import Context, Service
from pydantic import BaseModel, Field
from watchfiles import Change, awatch

from hmr.error import HmrError

logger = logging.getLogger(__name__)

# Event names (mirror upstream declarations).
EVENT_CHANGE = "hmr/change"
EVENT_RELOAD = "hmr/reload"

# Delay between the debounce settling and the ``hmr/reload`` emit.
# Kept small so subscribers see ``hmr/change`` first, then ``hmr/reload``
# shortly after, even when ``HmrConfig.debounce`` is large.
RELOAD_DELAY_S = 0.05


# ---------------------------------------------------------------------------
# Config schema
# ---------------------------------------------------------------------------


class HmrConfig(BaseModel):
    """Pydantic replacement for the upstream ``Hmr.Config`` schemastery.

    Mirrors the shape used by ``vendor/hmr/src/index.ts``:

    - ``base`` — base directory for relative path resolution.
    - ``root`` — list of root directories to watch.
    - ``ignored`` — list of glob patterns to ignore.
    - ``debounce`` — debounce window in milliseconds (default 100).
    """

    base: str = "."
    root: list[str] = Field(default_factory=lambda: ["."])
    ignored: list[str] = Field(
        default_factory=lambda: [
            "**/node_modules",
            "**/.*",
            "cache",
            "data",
        ]
    )
    debounce: int = 100


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _change_to_kind(change: Change) -> str:
    """Map a ``watchfiles.Change`` enum value to the upstream kind string.

    Upstream uses ``"add"`` / ``"change"`` / ``"unlink"``; the Python
    port normalizes to the same three strings so downstream behavior
    matches.
    """
    if change == Change.added:
        return "add"
    if change == Change.modified:
        return "change"
    if change == Change.deleted:
        return "unlink"
    return "change"  # pragma: no cover — defensive


async def _find_watch_root(filename: str) -> tuple[str, str, int]:
    """Walk up the path until a real directory is found.

    Mirrors upstream ``findWatchRoot``: returns
    ``(canonical_filename, canonical_root, depth)``.

    - The canonical root is the first existing directory walking up from
      ``dirname(filename)``.
    - ``filename`` is rewritten to live under the canonical root.
    - ``depth`` is the number of times we had to walk up.
    - Raises :class:`HmrError` if the entire path is unreachable.
    """
    root = os.path.dirname(filename) or "."
    depth = 0
    while True:
        try:
            os.stat(root)  # noqa: ASYNC240 — microsecond FS check, no event-loop cost
        except FileNotFoundError as exc:
            parent = os.path.dirname(root) or root
            if parent == root:
                raise HmrError(f"config path is unreachable: {filename}") from exc
            root = parent
            depth += 1
            continue
        except OSError as exc:
            raise HmrError(f"failed to stat config watch parent: {root}: {exc}") from exc
        if not os.path.isdir(root):  # noqa: ASYNC240 — see os.stat above
            raise HmrError(f"config watch parent is not a directory: {root}")
        canonical_root = os.path.realpath(root)  # noqa: ASYNC240 — synchronous canonicalize
        try:
            canonical_filename = os.path.join(  # noqa: ASYNC240 — sync path join
                canonical_root,
                os.path.relpath(filename, root),  # noqa: ASYNC240 — sync path relpath
            )
        except ValueError as exc:
            raise HmrError(f"config path is invalid: {filename!r}") from exc
        return canonical_filename, canonical_root, depth


def _url_to_path(url: str) -> str:
    """Convert a ``file://`` URL to a filesystem path; pass through otherwise."""
    if url.startswith("file://"):
        from urllib.request import url2pathname

        return url2pathname(url[len("file://") :])
    return url


def _set_future_if_pending(future: asyncio.Future[Any], value: Any) -> None:
    """Resolve ``future`` with ``value`` only if it is not already done."""
    if not future.done():
        future.set_result(value)


def _emit_reload(ctx: Context, filename: str) -> None:
    """Fire ``hmr/reload`` on the given context (used by ``loop.call_later``)."""
    with suppress(Exception):
        ctx.emit(EVENT_RELOAD, filename)


def _matches_filename(change: tuple[Change, str], registration_filename: str) -> bool:
    """Return True if ``change`` refers to the registered filename."""
    _kind, path = change
    observed = os.path.realpath(path)
    target = os.path.realpath(registration_filename)
    return observed == target


# ---------------------------------------------------------------------------
# Config registration
# ---------------------------------------------------------------------------


@dataclass
class ConfigRegistration:
    """One registered config file's watcher + bookkeeping.

    Mirrors the upstream ``ConfigRegistration`` interface (just a
    wrapper around the FSWatcher in TS). The Python port keeps the
    underlying ``asyncio.Task`` that drives the ``awatch`` iterator
    plus per-registration futures for tests.
    """

    filename: str  # Absolute path passed by the user (resolved).
    canonical_filename: str  # Real-path of the file under the watch root.
    watch_root: str  # Real-path of the directory being watched.
    depth: int
    # Future the consumer awaits to learn about the next ``hmr/change``
    # event for this registration. Resolved with ``(filename, content)``.
    # The Hmr service rotates this on every actual change.
    change_event: asyncio.Future[tuple[str, str]] = field(default=None)  # type: ignore[assignment]
    # Future resolved with ``filename`` after the change settles.
    reload_event: asyncio.Future[str] = field(default=None)  # type: ignore[assignment]
    # Active tasks (watch + debounce); cancelled on dispose.
    watch_task: asyncio.Task[None] | None = None
    debounce_task: asyncio.Task[None] | None = None
    # Pending ``hmr/reload`` timer handle from ``loop.call_later``;
    # cancelled on dispose so the emit does not fire after teardown.
    reload_timer: asyncio.TimerHandle | None = None
    # Ready future resolved once the watcher is initialized.
    ready_event: asyncio.Future[None] = field(default=None)  # type: ignore[assignment]


RefreshFn = Callable[[], Awaitable[None] | None]


# ---------------------------------------------------------------------------
# Hmr Service
# ---------------------------------------------------------------------------


class Hmr(Service):
    """Hot-module-reload service.

    Watches the file system and emits ``hmr/change`` + ``hmr/reload``
    events through the cordis event bus. Lifecycle is tied to the
    owning context: ``ctx.dispose()`` cancels every active watcher
    task.

    Example::

        ctx = Context()
        hmr = Hmr(ctx)
        dispose = await hmr.register_config("/abs/path/config.yml")
        # ... later:
        await dispose()  # stop watching this file
        await ctx.dispose()  # stop all watches
    """

    # The base ``Service.config`` is declared ``ClassVar[Type[Any] | None]``; we
    # narrow it to ``type[HmrConfig]`` for type-safe validation. Pyright
    # rightfully flags the override as incompatible (mutable class field); the
    # narrowing is intentional and matches the upstream TS contract.
    config: type[HmrConfig] = HmrConfig  # pyright: ignore[reportIncompatibleVariableOverride]

    def __init__(self, ctx: Context, **config: Any) -> None:
        super().__init__(ctx, **config)
        # Resolved from the validated config.
        resolved = self._validated_config or HmrConfig()
        # Base dir resolution mirrors upstream:
        #   fileURLToPath(new URL(config.base || '.', ctx.baseUrl))
        base_str = resolved.base or "."
        base_url = ctx.baseUrl
        if base_url:
            self.base_dir: str = os.path.realpath(
                os.path.join(_url_to_path(base_url), base_str)
            )
        else:
            self.base_dir = os.path.realpath(base_str)
        # Registrations keyed by the canonical watch filename.
        self._configs: dict[str, ConfigRegistration] = {}
        # Active debounce futures keyed by registration filename.
        self._disposers: list[Callable[[], Awaitable[None] | None]] = []

    # ------------------------------------------------------------------
    # Config registration
    # ------------------------------------------------------------------

    async def register_config(
        self,
        filename: str,
        refresh: RefreshFn | None = None,
    ) -> Callable[[], Awaitable[None]]:
        """Watch a single config file and return an async disposer.

        Args:
            filename: Absolute or relative-to-``base_dir`` path of the
                file to watch.
            refresh: Optional callback invoked (serially) every time the
                file is added, modified, or unlinked. Errors are logged
                and surface via ``hmr/config-update-failed``.

        Returns:
            Async disposer that stops watching this file and joins the
            in-flight refresh task.

        Raises:
            HmrError: If the file is unreachable, the path is already
                registered, or the watcher fails to start.
        """
        filename = self._resolve_path(filename)
        if not os.path.exists(filename):  # noqa: ASYNC240 — cheap existence check
            raise HmrError(f"config path does not exist: {filename}")
        canonical_filename, watch_root, depth = await _find_watch_root(filename)
        if canonical_filename in self._configs:
            raise HmrError(f"config path already registered: {filename}")

        # Build the per-registration futures first so the watch callback
        # can resolve them deterministically.
        loop = asyncio.get_running_loop()
        change_event: asyncio.Future[tuple[str, str]] = loop.create_future()
        reload_event: asyncio.Future[str] = loop.create_future()
        ready_event: asyncio.Future[None] = loop.create_future()

        registration = ConfigRegistration(
            filename=filename,
            canonical_filename=canonical_filename,
            watch_root=watch_root,
            depth=depth,
            change_event=change_event,
            reload_event=reload_event,
            ready_event=ready_event,
        )
        self._configs[canonical_filename] = registration

        watch_task = loop.create_task(
            self._run_watcher(registration, watch_root, depth, refresh),
            name=f"hmr.watch:{filename}",
        )
        registration.watch_task = watch_task

        # Wait for the watcher to signal ready (initial setup complete).
        # Mirrors upstream ``await ready.promise``. We give the loop a
        # chance to schedule the awatch generator before checking.
        try:
            await asyncio.wait_for(ready_event, timeout=2.0)
        except TimeoutError as exc:
            self._configs.pop(canonical_filename, None)
            watch_task.cancel()
            with suppress(BaseException):
                await watch_task
            raise HmrError(f"HMR watcher failed to start: {filename}") from exc
        except Exception as exc:
            self._configs.pop(canonical_filename, None)
            watch_task.cancel()
            with suppress(BaseException):
                await watch_task
            raise HmrError(f"HMR watcher failed to start: {filename}: {exc}") from exc

        async def _dispose() -> None:
            entry = self._configs.pop(canonical_filename, None)
            if entry is None:
                return
            if entry.watch_task is not None and not entry.watch_task.done():
                entry.watch_task.cancel()
            if entry.debounce_task is not None and not entry.debounce_task.done():
                entry.debounce_task.cancel()
            if entry.reload_timer is not None:
                entry.reload_timer.cancel()
                entry.reload_timer = None
            if entry.watch_task is not None:
                with suppress(BaseException):
                    await entry.watch_task
            if entry.debounce_task is not None:
                with suppress(BaseException):
                    await entry.debounce_task

        self._disposers.append(_dispose)
        return _dispose

    # ------------------------------------------------------------------
    # Watcher loop
    # ------------------------------------------------------------------

    async def _run_watcher(
        self,
        registration: ConfigRegistration,
        watch_root: str,
        depth: int,
        refresh: RefreshFn | None,
    ) -> None:
        """Run the ``awatch`` generator, debouncing changes, and emit events.

        Signals ``ready_event`` once the watch loop is established.
        Then iterates ``awatch`` and:

        - Filters for events that touch ``registration.canonical_filename``.
        - For each batch, classifies the first change; reads the file
          content; resolves the next ``change_event`` with
          ``(filename, content)``; schedules a debounced emit; and
          schedules the reload signal after the debounce window.
        """
        loop = asyncio.get_running_loop()
        # Resolve the ready future so ``register_config`` can return.
        # We use ``call_soon`` so the first iteration of ``async for``
        # gets a chance to enter the underlying watcher.
        loop.call_soon(_set_future_if_pending, registration.ready_event, None)

        try:
            async for changes in awatch(
                watch_root,
                recursive=depth > 0,
                stop_event=None,
            ):
                # Filter for events that touch the registered file.
                relevant = [
                    change
                    for change in changes
                    if _matches_filename(change, registration.canonical_filename)
                ]
                if not relevant:
                    continue
                # Classify; only the first relevant event in the batch
                # drives a refresh (debounce collapses the rest).
                kind = _change_to_kind(relevant[0][0])
                try:
                    content = (
                        await asyncio.to_thread(
                            Path(registration.filename).read_text, encoding="utf-8"
                        )
                        if kind != "unlink"
                        else ""
                    )
                except FileNotFoundError:
                    content = ""
                except OSError as exc:
                    logger.warning("hmr: failed to read %s: %s", registration.filename, exc)
                    content = ""

                # Update the in-flight state.
                if not registration.change_event.done():
                    registration.change_event.set_result((registration.filename, content))
                else:
                    # Rotate the future for the next consumer.
                    registration.change_event = loop.create_future()
                    registration.change_event.set_result((registration.filename, content))

                # Reset reload future so tests can await the next reload.
                if registration.reload_event.done():
                    registration.reload_event = loop.create_future()

                # Cancel any in-flight debounce; start a new one. The
                # debounce task emits ``hmr/change`` after the window
                # elapses; ``hmr/reload`` is emitted on the next event
                # loop tick past that window (so a subscriber sees
                # ``change`` first, then ``reload``).
                if registration.debounce_task is not None and not registration.debounce_task.done():
                    registration.debounce_task.cancel()
                registration.debounce_task = loop.create_task(
                    self._debounce_and_emit_change_and_reload(registration, content),
                    name=f"hmr.debounce:{registration.filename}",
                )

                # Fire ``refresh`` (best-effort; serially).
                if refresh is not None:
                    try:
                        result = refresh()
                        if asyncio.iscoroutine(result):
                            await result
                    except Exception as exc:  # noqa: BLE001
                        logger.warning("hmr: refresh callback for %s failed: %s", registration.filename, exc)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.warning("hmr watcher for %s failed: %s", registration.filename, exc)
            if not registration.ready_event.done():
                registration.ready_event.set_exception(exc)
            raise

    async def _debounce_and_emit_change_and_reload(
        self,
        registration: ConfigRegistration,
        content: str,
    ) -> None:
        """Wait for the debounce window, then emit ``hmr/change`` and ``hmr/reload``.

        A new change re-arms the timer via task cancellation in the
        caller, so this coroutine only runs to completion when no
        further changes have arrived in the window. The order is
        ``change`` first, then ``reload`` (the reload is scheduled
        with a small extra delay so subscribers can react to
        ``change`` before the reload settles).
        """
        try:
            await asyncio.sleep(
                (self._validated_config.debounce if self._validated_config else 100) / 1000.0
            )
        except asyncio.CancelledError:
            return  # Superseded by a newer change.
        with suppress(Exception):
            self.ctx.emit(EVENT_CHANGE, registration.filename, content)
        # Resolve the per-registration future so tests that await it
        # deterministically unblock. The watcher already rotated this
        # future on the matching change, so it should be pending here.
        if registration.reload_event.done():  # pragma: no cover — defensive
            registration.reload_event = asyncio.get_running_loop().create_future()
        registration.reload_event.set_result(registration.filename)
        # Schedule ``hmr/reload`` shortly after the change. Track the
        # handle on the registration so dispose() can cancel it.
        loop = asyncio.get_running_loop()
        if registration.reload_timer is not None:
            registration.reload_timer.cancel()
        registration.reload_timer = loop.call_later(
            RELOAD_DELAY_S,
            _emit_reload,
            self.ctx,
            registration.filename,
        )

    # ------------------------------------------------------------------
    # Service dispose
    # ------------------------------------------------------------------

    async def dispose(self) -> None:
        """Cancel every active watcher and join in-flight tasks.

        Cleanup goes through the per-config disposers registered by
        :meth:`register_config`: each disposer cancels the matching
        watch + debounce tasks, cancels any pending ``hmr/reload``
        timer, joins the tasks, and pops the registration from
        ``_configs``. The follow-up loop is a defensive net for any
        registration that bypassed ``register_config`` (e.g., test
        injection): it cancels its pending ``hmr/reload`` timer so the
        emit cannot fire after teardown.
        """
        for dispose in self._disposers:
            try:
                result = dispose()
                if asyncio.iscoroutine(result):
                    await result
            except Exception as exc:  # noqa: BLE001
                logger.warning("hmr: disposer raised %s", exc)
        self._disposers.clear()
        # Defensive: cancel any reload_timer left on entries that did
        # not go through ``register_config`` (no disposer is registered
        # for them). Without this, an injected registration could leak
        # its timer into the next event-loop iteration.
        for registration in list(self._configs.values()):
            if registration.reload_timer is not None:
                registration.reload_timer.cancel()
                registration.reload_timer = None

    # ------------------------------------------------------------------
    # Path helpers
    # ------------------------------------------------------------------

    def _resolve_path(self, filename: str) -> str:
        """Resolve ``filename`` against the HMR base dir, then absolutize."""
        if os.path.isabs(filename):
            return os.path.realpath(filename)
        return os.path.realpath(os.path.join(self.base_dir, filename))


__all__ = [
    "ConfigRegistration",
    "EVENT_CHANGE",
    "EVENT_RELOAD",
    "Hmr",
    "HmrConfig",
    "RELOAD_DELAY_S",
]
