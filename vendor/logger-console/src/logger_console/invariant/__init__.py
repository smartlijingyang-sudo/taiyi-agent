"""``logger_console.invariant`` — stable public API contract.

Re-exports the same names as :mod:`logger_console` so consumers can
declare a stable dependency on the contract without coupling to the
implementation layout. Mirrors the upstream TS pattern where
``vendor/logger-console/src/invariant/index.ts`` is a re-export barrel.
"""

from __future__ import annotations

from logger_console.browser import BrowserConsoleExporter
from logger_console.exporter import (
    ConsoleExporter,
    ConsoleExporterConfig,
    LabelStyle,
)
from logger_console.format import (
    ANSI_RESET,
    inspect_format,
    inspect_formatter,
    isatty,
    level_color,
)

__all__ = [
    # Exporter classes
    "BrowserConsoleExporter",
    "ConsoleExporter",
    # Config types
    "ConsoleExporterConfig",
    "LabelStyle",
    # Format helpers
    "ANSI_RESET",
    "inspect_format",
    "inspect_formatter",
    "isatty",
    "level_color",
]
