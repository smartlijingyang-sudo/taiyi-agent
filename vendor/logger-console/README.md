# logger-console

`taiyi-logger-console` is a 1:1 Python port of
[`@deepseek-ai/logger-console`](https://github.com/deepseek-ai/deepseek-harness/tree/master/vendor/logger-console),
the console-logging exporters that ship alongside the deepseek-harness
plugin framework. The package exposes a Node-routed `ConsoleExporter`
(writes to `stderr`) and a `BrowserConsoleExporter` (writes to
`stdout`/`stderr`), both implementing the
[`cordis.logger.Exporter`](../cordis/README.md) contract.

## Architecture decisions

The upstream TypeScript implementation leans on a few Node-specific
APIs (`util.inspect`, `console.log`, `supports-color`); the 6 decisions
below describe how each one is mapped to Python.

1. **`util.inspect(value, { colors, depth: Infinity, compact: true, breakLength: Infinity })`
   → `pprint.pformat(value, indent=2, width=120, depth=4, sort_dicts=False)`.**
   `pprint.pformat` is the closest Python equivalent — it produces
   readable, multi-line output for dicts, lists, and nested objects.
   The Python port uses a finite `depth=4` (the TS uses `Infinity`)
   to keep recursion bounded and avoid stack blowups on cyclic data;
   `width=120` keeps lines terminal-friendly. `sort_dicts=False` mirrors
   `util.inspect`'s default key ordering (insertion order).

2. **`supports-color.stdout.level` → `sys.stderr.isatty()`.**
   The Node entry (`src/index.ts`) overrides `getDefaults()` to set
   `colors` based on whether stdout is attached to a TTY. The Python
   port does the same — `isatty()` returns a boolean, mapped to
   `colors = 1` (TTY) or `colors = False` (pipe / capture).

3. **`console.log(...)` → `sys.stderr.write(line + "\n")`.**
   The TS upstream calls `console.log` for every rendered message.
   Python logging conventions write to `stderr`; the Python port mirrors
   that contract so `python my_app.py 2> errors.log` captures the log
   stream naturally.

4. **Module name `logger_console` (underscore).** Python identifiers
   cannot contain hyphens; the upstream package `@deepseek-ai/logger-console`
   becomes `logger_console` in Python. The wheel name remains
   `taiyi-logger-console` for npm-style discoverability in the
   workspace.

5. **Per-instance `formatters` table.** The upstream Node entry assigns
   `formatters = { o: inspectFormatter, O: inspectFormatter }` on each
   instance. The Python port keeps the same per-instance dict shape so
   that `Logger.format` (in `cordis.logger`) walks it identically and
   substitutes the inspect formatter for `%o` / `%O` printf
   placeholders.

6. **ANSI coloring on the level prefix.** The TS upstream only colors
   the scope label (hash-derived code via `Logger.color`). The Python
   port also colors the level prefix (`[I]`, `[W]`, `[E]`, `[D]`)
   with a severity-specific code (green / yellow / red / blue) so the
   prefix itself carries the visual signal. This matches the task
   contract ("Level-based prefix... with ANSI colors when TTY").

## Public surface

The package exposes the same chainable surface as the upstream TS:

- `ConsoleExporter(ctx, config=...)` — Node-routed exporter writing to
  `stderr`; config may be a `ConsoleExporterConfig`, a `dict`, or a
  mix of kwargs (mirroring `Object.assign(this, defaults, config)`).
- `BrowserConsoleExporter(ctx, config=...)` — Browser-routed exporter;
  routes to `stderr` for `error` / `warn` and to `stdout` otherwise.
- `ConsoleExporterConfig` — dataclass config namespace (colors,
  max_length, levels, show_diff, show_time, label).
- `LabelStyle` — label width / margin / alignment dataclass.
- `inspect_format(value)` — the pprint-based pretty-printer.
- `inspect_formatter(value, exporter, message)` — Formatter callback
  used by `Logger.format` for `%o` / `%O`.
- `isatty()` — TTY detection helper (`sys.stderr.isatty()`).
- `level_color(level)` — severity → ANSI 16-color code.
- `ANSI_RESET` — the reset escape sequence (`\x1b[0m`).

## Render output

A typical rendered line (TTY, colors enabled):

```
\x1b[38;5;243m2026-08-17 14:22:18 \x1b[0m\x1b[32m[I]\x1b[0m \x1b[33mapi\x1b[0m\x1b[33m;1m\x1b[0m GET /health
```

Format breakdown:

```
<timestamp> <level> <label> <body>
```

`<level>` is colored with `level_color(message.type)` (red/yellow/green/blue).
`<label>` is colored with `Logger.code(name)` (16-color or 256-color
palette hash, depending on the configured color level).
`<body>` is produced by `Logger.format(self, message)` and may include
multi-line `pprint`-style object dumps when args are objects.

## Tests

```sh
uv run pytest vendor/logger-console --cov=vendor/logger-console --cov-fail-under=100
```

Per-file 100% coverage is enforced; 52 tests cover the formatter, the
stderr exporter, and the browser exporter.
