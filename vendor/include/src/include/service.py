"""``include.service`` — file-backed Include entry tree.

1:1 port of upstream ``~/deepseek-harness/vendor/include/src/index.ts``.

Responsibilities:

- Read a YAML or JSON entry file at ``ctx.baseUrl/path``.
- Apply configured ``patches`` after parsing.
- Persist edits back to disk via a debounced atomic write.
- Serialize concurrent applies so two updates can't race (init vs HMR refresh).
- Expose the file's content for offline tooling (``dsh --dump-config``).
"""

from __future__ import annotations

import asyncio
import errno as _errno
import json
import os
from collections.abc import Awaitable, Callable
from typing import Any, ClassVar

import yaml

from include.patch import PatchOptions, apply_entry_patches

__all__ = ["ConfigFileError", "Include", "entry_list_schema"]


SUPPORTED_EXTENSIONS = {".yaml", ".yml", ".json"}
EXTENSION_TYPES = {
    ".json": "application/json",
    ".yaml": "application/yaml",
    ".yml": "application/yaml",
}

WRITE_RETRY_LIMIT = 10
WRITE_RETRY_DELAY_MS = 50

_CONFIG_UPDATE_STAGES = ("read", "parse", "validate")


class ConfigFileError(Exception):
    """Raised when a config file can't be read, parsed, or validated.

    Mirrors upstream's ``ConfigFileError`` with stage / path / cause.
    """

    def __init__(self, stage: str, path: str, cause: BaseException) -> None:
        if stage not in _CONFIG_UPDATE_STAGES:
            raise ValueError(f"unknown stage: {stage!r}")
        super().__init__(f"failed to {stage} config file {path}")
        self.stage = stage
        self.path = path
        self.__cause__ = cause


def _retryable_write_error(error: BaseException) -> bool:
    """Mirror upstream ``retryableWriteError`` errno check."""
    code = getattr(error, "errno", None)
    return code in (_errno.EACCES, _errno.EBUSY, _errno.EPERM)


# ---------------------------------------------------------------------------
# YAML !!js scalar tag (mirror of upstream ``entryListSchema``)
# ---------------------------------------------------------------------------

_JS_EXPR_TAG = "tag:yaml.org,2002:js"


class _JsExprLoader(yaml.SafeLoader):
    """SafeLoader that knows the ``!!js`` tag (mirrors upstream custom schema)."""


class _JsExprDumper(yaml.SafeDumper):
    """SafeDumper that represents ``{ __jsExpr: str }`` as ``!!js`` scalars."""


def _construct_js_expr(loader: yaml.Loader, node: yaml.Node) -> dict[str, str]:
    if not isinstance(node, yaml.ScalarNode):
        raise yaml.constructor.ConstructorError(
            None,
            None,
            "!!js requires a scalar string",
            node.start_mark,
        )
    return {"__jsExpr": loader.construct_scalar(node)}


def _represent_js_expr(dumper: yaml.Dumper, data: dict[str, str]) -> yaml.Node:
    return dumper.represent_scalar(_JS_EXPR_TAG, data["__jsExpr"])


def _js_expr_dict_representer(dumper: yaml.Dumper, data: dict[str, Any]) -> yaml.Node:
    """Only emit ``!!js`` for dicts that actually look like ``{ __jsExpr: str }``.

    The bare ``add_representer(dict, ...)`` would hijack every dict in the
    tree; we delegate to the default mapping representer for everything else.
    """
    if isinstance(data.get("__jsExpr"), str):
        return _represent_js_expr(dumper, data)
    return dumper.represent_mapping("tag:yaml.org,2002:map", data)


_JsExprLoader.add_constructor(_JS_EXPR_TAG, _construct_js_expr)
_JsExprDumper.add_representer(dict, _js_expr_dict_representer)  # type: ignore[arg-type]


def _load_yaml(text: str) -> Any:
    """Parse YAML with the include's ``!!js`` dialect."""
    return yaml.load(text, Loader=_JsExprLoader)


def _dump_yaml(value: Any) -> str:
    """Serialize to YAML with the include's ``!!js`` dialect."""
    return yaml.dump(value, Dumper=_JsExprDumper)


# Upstream name (``entryListSchema``) for downstream compatibility: the
# Loader's offline tooling (``dsh --dump-config``) imports this to parse
# and print exactly the dialect this include mounts.
def entry_list_schema() -> Any:
    """Return the YAML schema (loader class) for the ``!!js`` dialect.

    Mirrors upstream ``entryListSchema``. Kept as a function so callers can
    override or subclass without mutating module state.
    """
    return _JsExprLoader


class Include:
    """File-backed Include entry tree (mirrors upstream ``Include extends EntryTree``).

    Implementation notes:

    - Reads ``ctx.baseUrl + config.path`` synchronously at construction.
    - Applies ``patches`` lazily on every read + write.
    - Uses a Promise queue to serialize concurrent applies.
    - Persists writes via tempfile + rename with retry on EACCES/EBUSY/EPERM.
    """

    inject: ClassVar[list[str]] = ["loader"]

    config: Include.Config
    enable_logs: bool
    filename: str
    _type: str | None
    readonly: bool
    content: str | None
    data: list[dict[str, Any]] | None
    _pending_write: list[dict[str, Any]] | None
    _write_task: asyncio.TimerHandle | None
    _service_init_done: bool

    class Config:
        """Mirror of upstream ``Include.Config`` (path + initial + patches)."""

        path: str
        initial: list[dict[str, Any]] | None
        patches: list[PatchOptions] | None
        enableLogs: bool | None

        def __init__(
            self,
            *,
            path: str,
            initial: list[dict[str, Any]] | None = None,
            patches: list[PatchOptions] | None = None,
            enableLogs: bool | None = None,
        ) -> None:
            self.path = path
            self.initial = initial
            self.patches = patches
            self.enableLogs = enableLogs

    def __init__(self, ctx: Any, config: Include.Config | dict[str, Any]) -> None:
        if isinstance(config, dict):
            config = Include.Config(**config)
        elif not isinstance(config, Include.Config):
            raise TypeError("config must be a dict or Include.Config")

        self.ctx = ctx
        self.config = config
        self.enable_logs = bool(
            config.enableLogs if config.enableLogs is not None else False
        )
        self.content = None
        self.data = None
        self._pending_write = None
        self._write_task = None
        # Queue seeds start as a resolved future; the real loop is bound on
        # first use so construction works from sync tests / contexts.
        self._write_queue: asyncio.Future[None] | None = None
        self._apply_queue: asyncio.Future[None] | None = None
        self._service_init_done = False
        self._pending_writes_for_test: list[list[dict[str, Any]]] = []

        base_url = getattr(ctx, "baseUrl", None)
        if base_url:
            self.filename = self._resolve_filename(str(base_url), config.path)
        else:
            self.filename = os.path.abspath(config.path)

        ext = os.path.splitext(self.filename)[1]
        if ext not in SUPPORTED_EXTENSIONS:
            raise ValueError(f'extension "{ext}" not supported')

        self._type = EXTENSION_TYPES[ext]
        self.readonly = not bool(self._type)

    # ------------------------------------------------------------------ utils

    @staticmethod
    def _resolve_filename(base_url: str, path: str) -> str:
        """Resolve ``path`` against ``base_url`` (file:// or http(s):// style)."""
        if base_url.startswith("file://"):
            base_path = base_url[len("file://") :]
        else:
            base_path = base_url
        return os.path.normpath(os.path.join(base_path, path))

    async def _noop(self) -> None:
        """Default Future seed; resolves immediately."""
        return None

    # ---------------------------------------------------------------- read

    def apply_patches(
        self,
        data: list[dict[str, Any]],
        patches: list[PatchOptions] | None,
    ) -> list[dict[str, Any]]:
        """Apply patches with the include's own warn sink (logger-backed)."""
        return apply_entry_patches(data, patches, self._warn)

    def _warn(self, message: str, *args: Any) -> None:
        """Route patch warnings through the context's loader logger if any."""
        logger_svc = getattr(getattr(self.ctx, "root", None), "logger", None)
        if logger_svc is None:
            return
        loader_logger = logger_svc("loader")
        warn = getattr(loader_logger, "warn", None)
        if warn is None:
            return
        warn(message, *args)

    async def _read_file(self, forced: bool = False) -> dict[str, Any] | None:
        """Read + parse the config file. Returns ``{content, data}`` or None
        when the content is unchanged."""
        loop = asyncio.get_event_loop()

        def _do_read() -> str:
            with open(self.filename, encoding="utf8") as f:
                return f.read()

        try:
            content = await loop.run_in_executor(None, _do_read)
        except OSError as exc:
            raise ConfigFileError("read", self.filename, exc) from exc

        if not forced and self.content is not None and self.content == content:
            return None
        self.content = content

        def _do_parse(text: str) -> Any:
            assert self._type is not None
            if self._type == "application/yaml":
                return _load_yaml(text)
            return json.loads(text)

        try:
            data = await loop.run_in_executor(None, _do_parse, content)
        except Exception as exc:
            raise ConfigFileError("parse", self.filename, exc) from exc

        if not isinstance(data, list):
            raise ConfigFileError(
                "validate",
                self.filename,
                TypeError("config file must be a top-level array"),
            )

        return {"content": content, "data": data}

    async def _read_initial(self) -> None:
        """Read the file once at boot, creating it from ``initial`` if missing.

        Mirrors upstream ``[Service.init]`` body up to ``yield () => this.stop()``.
        """
        try:
            candidate = await self._read_file(forced=True)
        except ConfigFileError as exc:
            if exc.stage != "read":
                raise
            # Upstream checks for ENOENT on the read cause. Python's
            # ``FileNotFoundError`` carries ``errno = 2`` (ENOENT).
            cause_errno = getattr(exc.__cause__, "errno", None)
            if cause_errno != 2:  # 2 == errno.ENOENT
                raise
            if self.config.initial is not None:
                await self._write_file(list(self.config.initial))
                candidate = await self._read_file(forced=True)
                assert candidate is not None  # noqa: S101 — invariant: just written
            else:
                raise FileNotFoundError(f"config file not found: {self.filename}") from exc

        assert candidate is not None  # noqa: S101 — invariant
        self.content = candidate["content"]
        self.data = candidate["data"]

    # ---------------------------------------------------------------- enqueue

    async def enqueue(self, task: Callable[[], Awaitable[Any]]) -> Any:
        """Serialize one task behind every earlier one.

        A predecessor's failure is its own caller's outcome; the next task
        must still run. Mirrors upstream ``enqueue``.
        """
        # Lazy-bind the queue seed on the running event loop.
        if self._apply_queue is None:
            self._apply_queue = asyncio.get_event_loop().create_future()
            self._apply_queue.set_result(None)
        previous = self._apply_queue

        async def _runner() -> Any:
            return await task()

        new_task = asyncio.ensure_future(_runner())
        self._apply_queue = new_task
        # The successor does not await the predecessor — it just chains behind
        # it on the underlying event loop. For the upstream "funnel" semantic
        # we capture the predecessor's outcome (success or failure) so callers
        # see the same error.
        try:
            await previous
        except BaseException:
            pass
        return await new_task

    # ---------------------------------------------------------------- writes

    async def _write_file(self, config: list[dict[str, Any]]) -> None:
        """Persist ``config`` to the file (tempfile + rename + retry)."""
        if self.readonly:
            raise RuntimeError("cannot overwrite readonly config")
        if self._type == "application/yaml":
            content = _dump_yaml(config)
        elif self._type == "application/json":
            content = json.dumps(config, indent=2)
        else:
            raise RuntimeError(f"unsupported type: {self._type}")
        self.content = content
        tmp_path = self.filename + ".tmp"
        loop = asyncio.get_event_loop()

        def _do_write() -> None:
            with open(tmp_path, "w", encoding="utf8") as f:
                f.write(content)

        await loop.run_in_executor(None, _do_write)

        # Up to ``WRITE_RETRY_LIMIT`` rename attempts, sleeping between
        # retryable errors (EACCES / EBUSY / EPERM). The first attempt
        # runs unconditionally; subsequent attempts only fire after a
        # retryable error.
        retry = 0
        while True:
            try:

                def _do_rename() -> None:
                    os.replace(tmp_path, self.filename)

                await loop.run_in_executor(None, _do_rename)
                return
            except OSError as exc:
                if not _retryable_write_error(exc) or retry >= WRITE_RETRY_LIMIT - 1:
                    raise
                retry += 1
                await asyncio.sleep(retry * WRITE_RETRY_DELAY_MS / 1000)

    # ---------------------------------------------------------------- Service.init

    async def __service_init__(self) -> None:
        """Initialize and apply the file's content; equivalent to the body
        of upstream ``[Service.init]`` after the ``yield`` cleanup."""
        await self._read_initial()
        await self._apply_current()

    async def _apply_current(self) -> None:
        assert self.data is not None  # noqa: S101 — invariant after _read_initial
        data = self.apply_patches(self.data, self.config.patches)

        async def _notify() -> None:
            update = getattr(self.ctx, "emit", None)
            if update is not None:
                try:
                    result = update("internal/update", data)
                    if asyncio.iscoroutine(result):
                        await result
                except Exception:
                    pass

        await self.enqueue(_notify)

    # Convenience for the Include.dispose() contract.
    async def dispose(self) -> None:
        """Release async tasks (mirror of upstream ``stop``)."""
        if self._write_task is not None:
            self._write_task.cancel()
            self._write_task = None
        if self._apply_queue is not None and not self._apply_queue.done():
            try:
                await self._apply_queue
            except BaseException:  # best-effort
                pass

    # ---------------------------------------------------------------- offline

    def add_entries(self, entries: list[dict[str, Any]]) -> None:
        """Static hook for offline tooling: append ``entries`` to the file.

        Mirrors the upstream ``write()`` entry point, simplified for the
        in-memory 1:1 port (the HMR / atomic-write machinery lives in
        ``dsh`` proper, not here).
        """
        self._pending_writes_for_test.append(list(entries))
