"""``taiyi-logger-console`` — 1:1 Python port of ``@deepseek-ai/logger-console``.

Public surface (re-exported for convenience):

- :class:`ConsoleExporter` — Node-routed exporter writing rendered lines
  to ``stderr`` with ANSI color when attached to a TTY.
- :class:`BrowserConsoleExporter` — Browser-routed exporter; writes to
  ``stdout``/``stderr`` depending on severity.
- :class:`ConsoleExporterConfig` — Configuration namespace.
- :class:`LabelStyle` — Label rendering options.

The :mod:`logger_console.format` module exposes the inspect-style
``pprint`` formatter and ``isatty`` helper used internally.
"""

from __future__ import annotations

from logger_console.browser import BrowserConsoleExporter
from logger_console.exporter import (
    ConsoleExporter,
    ConsoleExporterConfig,
    LabelStyle,
)
from logger_console.format import inspect_format, inspect_formatter, isatty, level_color

__all__ = [
    # Exporter classes
    "BrowserConsoleExporter",
    "ConsoleExporter",
    # Config types
    "ConsoleExporterConfig",
    "LabelStyle",
    # Format helpers
    "inspect_format",
    "inspect_formatter",
    "isatty",
    "level_color",
]
