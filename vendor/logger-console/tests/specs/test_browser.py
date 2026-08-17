"""Tests for logger_console.browser — BrowserConsoleExporter.

1:1 port of upstream ``@deepseek-ai/logger-console`` ``src/browser.ts``.
"""

from __future__ import annotations

import sys as _sys
from dataclasses import dataclass
from typing import Any
from unittest.mock import patch

from cordis.logger import LoggerLevel, Message

from logger_console import invariant as _invariant
from logger_console.browser import BrowserConsoleExporter

# Ensure invariant re-exports load (kept for coverage).
_ = (
    _invariant.BrowserConsoleExporter,
    _invariant.ConsoleExporter,
    _invariant.ConsoleExporterConfig,
    _invariant.LabelStyle,
    _invariant.ANSI_RESET,
    _invariant.inspect_format,
    _invariant.inspect_formatter,
    _invariant.isatty,
    _invariant.level_color,
)


# ---------------------------------------------------------------------------
# Test helpers (mirror the buffer/context helpers in test_exporter.py).
# ---------------------------------------------------------------------------


@dataclass
class _Buffer:
    text: str = ""
    is_tty: bool = False

    def write(self, payload: str) -> int:
        self.text += payload
        return len(payload)

    def flush(self) -> None:
        pass


def _make_message(
    args: list[Any] | None = None,
    name: str = "browser-scope",
    type: str = "info",
    level: int = LoggerLevel.INFO,
) -> Message:
    return Message(
        sn=1,
        ts=1_700_000_000_000,
        name=name,
        type=type,
        level=level,
        args=args if args is not None else ["hi"],
    )


def _make_ctx() -> Any:
    class _LoggerStub:
        def __init__(self) -> None:
            self.exporters: list[Any] = []

        def exporter(self, exporter: Any) -> Any:
            self.exporters.append(exporter)
            return lambda: True

    class _Ctx:
        def __init__(self) -> None:
            self.logger = _LoggerStub()

    return _Ctx()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestBrowserConsoleExporter:
    """BrowserConsoleExporter dispatches by severity (1:1 with browser.ts)."""

    def test_info_goes_to_stdout(self) -> None:
        out = _Buffer()
        err = _Buffer()
        ctx = _make_ctx()
        with patch.object(_sys, "stdout", out), patch.object(_sys, "stderr", err):
            exporter = BrowserConsoleExporter(ctx)
            exporter.export(_make_message(args=["hi"], type="info"))
        assert "hi" in out.text
        assert out.text == "" or err.text == "" or "browser-scope" not in err.text
        assert err.text == ""

    def test_debug_goes_to_stdout(self) -> None:
        out = _Buffer()
        err = _Buffer()
        ctx = _make_ctx()
        with patch.object(_sys, "stdout", out), patch.object(_sys, "stderr", err):
            exporter = BrowserConsoleExporter(ctx)
            exporter.export(_make_message(args=["debug-msg"], type="debug"))
        assert "debug-msg" in out.text
        assert err.text == ""

    def test_warn_goes_to_stderr(self) -> None:
        out = _Buffer()
        err = _Buffer()
        ctx = _make_ctx()
        with patch.object(_sys, "stdout", out), patch.object(_sys, "stderr", err):
            exporter = BrowserConsoleExporter(ctx)
            exporter.export(_make_message(args=["warn-msg"], type="warn"))
        assert "warn-msg" in err.text
        assert out.text == ""

    def test_error_goes_to_stderr(self) -> None:
        out = _Buffer()
        err = _Buffer()
        ctx = _make_ctx()
        with patch.object(_sys, "stdout", out), patch.object(_sys, "stderr", err):
            exporter = BrowserConsoleExporter(ctx)
            exporter.export(_make_message(args=["boom"], type="error"))
        assert "boom" in err.text
        assert out.text == ""

    def test_emits_prefix_with_level_letter(self) -> None:
        out = _Buffer()
        ctx = _make_ctx()
        with patch.object(_sys, "stdout", out), patch.object(_sys, "stderr", _Buffer()):
            exporter = BrowserConsoleExporter(ctx)
            exporter.export(_make_message(args=["x"], type="info"))
        # Browser build uses a simpler ``[L] <name> <args>`` prefix.
        assert "[I]" in out.text
        assert "browser-scope" in out.text

    def test_multiple_args_space_separated(self) -> None:
        out = _Buffer()
        ctx = _make_ctx()
        with patch.object(_sys, "stdout", out), patch.object(_sys, "stderr", _Buffer()):
            exporter = BrowserConsoleExporter(ctx)
            exporter.export(_make_message(args=["one", "two", "three"], type="info"))
        assert "one" in out.text
        assert "two" in out.text
        assert "three" in out.text

    def test_write_error_silenced(self) -> None:
        ctx = _make_ctx()

        class _BrokenStream(_Buffer):
            def write(self, payload: str) -> int:  # type: ignore[override]
                raise OSError("stream closed")

        with patch.object(_sys, "stdout", _BrokenStream()), patch.object(
            _sys, "stderr", _BrokenStream()
        ):
            exporter = BrowserConsoleExporter(ctx)
            # Must not raise even though write blows up.
            exporter.export(_make_message(args=["hello"]))

    def test_inherits_console_exporter_config(self) -> None:
        ctx = _make_ctx()
        exporter = BrowserConsoleExporter(ctx)
        # Inherited from ConsoleExporter
        assert exporter.show_time == "yyyy-MM-dd hh:mm:ss "
        assert "o" in exporter.formatters
        assert "O" in exporter.formatters
