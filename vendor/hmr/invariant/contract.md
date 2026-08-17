# hmr Public Contract

This document describes the public API contract that `hmr.invariant`
re-exports and that all consumers of the package can rely on.

## Overview

`taiyi-hmr` is a 1:1 Python port of
[`@deepseek-ai/hmr`](https://github.com/deepseek-ai/cordis-plugin-hmr)
(upstream `~/deepseek-harness/vendor/hmr/src/index.ts`). The package
provides a hot-module-reload service for `taiyi-agent`: it watches
the file system, debounces change events, and surfaces them through
the cordis event bus (`hmr/change`, `hmr/reload`).

## Re-exports

The `hmr.invariant` companion submodule re-exports every public name
from `hmr`. Consumers should depend on this submodule to decouple
from the implementation layout.

| Name                   | Source                | Purpose                                       |
| ---------------------- | --------------------- | --------------------------------------------- |
| `EVENT_CHANGE`         | `hmr.service`         | Event name constant (`"hmr/change"`)          |
| `EVENT_RELOAD`         | `hmr.service`         | Event name constant (`"hmr/reload"`)          |
| `HmrError`             | `hmr.error`           | Custom error type                             |
| `ConfigRegistration`   | `hmr.service`         | Per-file watcher bookkeeping                  |
| `Hmr`                  | `hmr.service`         | The cordis service that watches files         |
| `HmrConfig`            | `hmr.service`         | Pydantic schema for service config            |

## Watcher surface

- `Hmr(ctx, **config)` — cordis service constructor. Validates the
  config via `HmrConfig` (Pydantic) and resolves `base_dir` from
  `ctx.baseUrl` + `config.base`.
- `await Hmr.register_config(filename, refresh=None)` — register a
  single config file to watch. Returns an **async disposer** that
  cancels the watcher and joins in-flight tasks on call. Re-registering
  the same canonical filename raises `HmrError("already registered")`.
- The optional `refresh` callback fires on every relevant change,
  serially. It may be sync (`() -> None`) or async
  (`() -> Awaitable[None]`). Exceptions are logged on the
  `hmr.service` logger and never propagate.

### Debouncing

- The service collapses bursts inside a configurable window via the
  `debounce` config field (milliseconds; default `100`). Each new
  change cancels the in-flight debounce task and schedules a fresh
  one.
- `EVENT_CHANGE` is emitted through `ctx.emit` after the debounce
  window settles; the event payload is `(filename, content)`.

### Reload

- After the change settles, `EVENT_RELOAD` is dispatched on a small
  fixed delay (`RELOAD_DELAY_S = 0.05` seconds). This guarantees
  subscribers see `change` first and `reload` shortly after, even
  when the user-configured `debounce` window is large.

## Filesystem watching

- `register_config` resolves the filename (relative paths via
  `base_dir`), calls `_find_watch_root` to walk up to a real
  directory, then drives `watchfiles.awatch` on that directory.
- Each registration owns its own `asyncio.Task` that consumes the
  `awatch` async generator, filters events by canonical filename,
  reads the file content via `Path.read_text(encoding="utf-8")`, and
  resolves per-registration `change_event` + `reload_event` futures.
- All active watcher + debounce tasks are tracked on the
  `ConfigRegistration` so `dispose()` can cancel and join them.

## Lifecycle

- `Hmr.dispose()` is the single cleanup path. It invokes every
  disposer registered through `register_config` (each disposer
  cancels the matching watcher + debounce and joins the tasks).
- The owning cordis `Context.dispose` propagates through to `Hmr`'s
  `dispose`, so watcher tasks never outlive the context.
- Disposers are idempotent: calling them after the entry has been
  popped from `_configs` is a no-op.
- Disposer exceptions are logged but swallowed so remaining disposers
  still run.

## Error handling

- `HmrError` is raised for invalid input (unreachable path, already
  registered, watcher failed to start).
- `OSError` / `FileNotFoundError` from `Path.read_text` are caught
  per-change, logged, and treated as empty content; the watcher
  itself stays alive.
- `refresh` callback exceptions are logged with the filename on the
  `hmr.service` logger (`WARNING` level).

## Coverage

The package ships with 78 tests covering the watcher surface, the
debounce + reload event ordering, all disposal paths, the
`register_config` error paths, and every module-level helper. Source
coverage is 100% (branch + line) on `src/hmr/`.
