# hmr

`taiyi-hmr` is a 1:1 Python port of
[`@deepseek-ai/hmr`](https://github.com/deepseek-ai/cordis-plugin-hmr) — the
hot-module-reload service for `taiyi-agent`. It watches the file system,
debounces change events, and surfaces them through the cordis event bus
(`hmr/change`, `hmr/reload`).

## Architecture decisions

The upstream TypeScript implementation depends on Node-specific APIs that
need to be mapped carefully for Python:

1. **`chokidar.watch(path)` → `watchfiles.awatch(path, ...)`**. The
   upstream file-system watcher (chokidar) is replaced by the
   [`watchfiles`](https://github.com/samuelcolvin/watchfiles) Rust-based
   async watcher. The Python port uses `awatch()` which returns an
   `AsyncIterator[set[FileChange]]` — the same shape used by chokidar
   callbacks in TS.

2. **`FSWatcher` events → `FileChange` enum**. Chokidar's
   `add` / `change` / `unlink` events map 1:1 to `watchfiles.Change.added`,
   `Change.modified`, `Change.deleted`. The port normalizes these to a
   single string per kind so the rest of the logic mirrors upstream.

3. **`FSWatcher.close()` → task cancellation**. Chokidar's
   `await watcher.close()` is replaced by cancelling the `awatch()` task
   that wraps the async generator. The HMR service stores a
   `set[asyncio.Task]` and cancels every active task on dispose.

4. **`Promise.withResolvers()` → a small `Future` helper**. Used for
   "ready" promises that the upstream code uses to defer callback setup
   until chokidar's initial scan completes. We use `asyncio.Future` with
   a dedicated `_state` flag so we can reject only on first error.

5. **Debouncing via `asyncio.wait_for` + a per-future event**. The
   upstream `ctx.debounce(fn, ms)` from `@deepseek-ai/cordis-plugin-timer`
   has no direct Python equivalent. We implement a small inline
   debouncer that re-arms an `asyncio.Event` on every change and resolves
   the consumer task once no new changes have arrived within the window.

6. **File reading via `pathlib.Path.read_text()`**. The upstream
   `fs.readFile(path, 'utf8')` becomes `Path(path).read_text(encoding='utf-8')`.
   For `hmr/change` we read content synchronously on the watcher's
   callback thread; debounce + emit happens on the asyncio loop.

7. **Path resolution via `os.path.realpath` + `os.path.relpath`**. The
   upstream `node:path` / `node:fs/promises` helpers map cleanly to
   their Python equivalents. The HMR base dir is resolved relative to
   the context's `baseUrl` (which upstream sets to a `file://` URL).

8. **`onChange` callbacks map the `watchfiles.FileChange` enum to
   upstream's `add` / `change` / `unlink` strings**. Behavior is
   identical (we dispatch the same HMR events).

9. **`--expose-internals` check → `ctx.loader.internal is None`**. The
   upstream guard "is exposed" becomes a check that
   `ctx.inject('loader')` returns an object with an `internal` attribute;
   we raise a clear `HmrError` if missing.

10. **Schema-driven config via `pydantic.BaseModel`** rather than the
    upstream `schemastery` library. The port uses a Pydantic model for
    the same shape (`base`, `root`, `ignored`, `debounce`); the
    `schemastery` runtime is not vendored.

11. **ModuleLoader + ModuleJob → not vendored in this chunk.** The
    upstream HMR service integrates with `@deepseek-ai/cordis-plugin-loader`
    to drive partial / full reloads. This chunk implements the
    **watcher surface** (`register_config` + `hmr/change` + `hmr/reload`)
    faithfully. The full reload engine depends on the loader port and is
    gated on that future chunk; the `ctx.loader.entries()` /
    `loader.exit()` integration points are stubbed with a runtime check
    that degrades gracefully when the loader service is not registered.

## Public surface (summary)

- `Hmr` — the cordis service.
- `register_config(filename, refresh=...)` — register a config file to
  watch; returns an async disposer.
- Events: `hmr/change(url, content)` and `hmr/reload(reloads)`.
- `HmrError` — the custom error type (raised on invalid paths, missing
  internals, etc.).

See `invariant/contract.md` for the full contract description.

## Tests

```sh
uv run pytest vendor/hmr/tests -q --cov=vendor/hmr/src --cov-fail-under=100
```

Per-file 100% coverage is enforced. File-watcher code paths are
exercised deterministically by writing the file from inside the test
and awaiting the corresponding future on the service (no `sleep()` /
`# pragma: no cover` workarounds).
