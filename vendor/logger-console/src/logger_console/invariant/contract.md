# taiyi-logger-console Public Contract

This document describes the public API contract that `logger_console.invariant`
re-exports. All consumers should depend on the symbols re-exported by the
`invariant` subpackage; internal modules may change in breaking ways without a
major version bump.

## Overview

`taiyi-logger-console` is a 1:1 Python port of
[`@deepseek-ai/logger-console`](https://github.com/deepseek-ai/deepseek-harness/tree/master/vendor/logger-console).
It ships two console exporters — one routed to stderr (Node-style), one routed
to stdout/stderr (browser-style) — plus the underlying inspect-style formatter
backed by `pprint.pformat`.

## Public surface

| Symbol | Purpose |
| --- | --- |
| `ConsoleExporter` | Node-routed exporter; writes rendered lines to stderr. |
| `BrowserConsoleExporter` | Browser-routed exporter; dispatches to stdout or stderr by severity. |
| `ConsoleExporterConfig` | Dataclass config namespace (colors, max_length, levels, show_diff, show_time, label). |
| `LabelStyle` | Label alignment / width / margin dataclass. |
| `inspect_format` | Pretty-printer (Python equivalent of `util.inspect`). |
| `inspect_formatter` | Formatter callback used for `%o` / `%O` printf placeholders. |
| `isatty` | True iff `sys.stderr.isatty()` returns True. |
| `level_color` | Maps severity name → ANSI 16-color code. |
| `ANSI_RESET` | ANSI reset escape sequence (`\x1b[0m`). |

## Behavioural guarantees

- `ConsoleExporter.export(message)` writes a single line to `sys.stderr` and
  appends a trailing newline. The line format is:
  `<timestamp> <label> <level> <formatted-body>` with optional `+diff` suffix.
- Colors are emitted iff `colors` is truthy on the exporter instance. The
  default is `True` when `sys.stderr.isatty()`, `False` otherwise.
- The `o` and `O` printf placeholders route through `inspect_formatter`,
  producing `pprint.pformat`-style output.
- `BrowserConsoleExporter.export(message)` routes to `stderr` for
  `error` / `warn`, otherwise to `stdout`. The body uses a simpler
  `[LEVEL] <name> <args>` prefix than the Node exporter.
- Both exporters swallow stream write errors so they never raise during
  log emission (1:1 with the cordis logger contract).

## Testing

```sh
uv run pytest vendor/logger-console --cov=vendor/logger-console --cov-fail-under=100
```

Per-file 100% coverage is enforced. `pyright strict` 0 errors. `ruff` clean.
