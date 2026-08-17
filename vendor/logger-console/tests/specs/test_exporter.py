"""Tests for logger_console.exporter — ConsoleExporter writes to stderr.

1:1 port of `@deepseek-ai/logger-console` shared `ConsoleExporter`,
adapted to write to stderr (the TS upstream calls console.log) and to
detect TTY via ``sys.stderr.isatty()``.
"""

from __future__ import annotations

import sys as _sys
from dataclasses import dataclass
from typing import Any
from unittest.mock import patch

import pytest
from cordis.logger import LoggerLevel, Message

from logger_console.exporter import ConsoleExporter, ConsoleExporterConfig, LabelStyle

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


@dataclass
class _Buffer:
    """Minimal stand-in for ``sys.stderr``; lets tests inspect written lines."""

    text: str = ""
    is_tty: bool = False

    def write(self, payload: str) -> int:
        self.text += payload
        return len(payload)

    def flush(self) -> None:
        pass

    def isatty(self) -> bool:
        return self.is_tty


def _make_message(
    args: list[Any] | None = None,
    name: str = "test",
    type: str = "info",
    level: int = LoggerLevel.INFO,
) -> Message:
    return Message(
        sn=1,
        ts=1_700_000_000_000,
        name=name,
        type=type,
        level=level,
        args=args if args is not None else ["hello"],
    )


def _make_ctx(logger: Any = None) -> Any:
    """A minimal Context-shaped stub that exposes ``ctx.logger``.

    The ConsoleExporter constructor does not call any methods on the
    context beyond registering itself with ``ctx.logger.exporter()``,
    so a tiny stub is sufficient.
    """

    class _Ctx:
        def __init__(self) -> None:
            self.logger = logger or _LoggerStub()

    class _LoggerStub:
        def __init__(self) -> None:
            self.exporters: list[Any] = []

        def exporter(self, exporter: Any) -> Any:
            self.exporters.append(exporter)
            return lambda: True

    return _Ctx()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestConsoleExporterWritesToStderr:
    """ConsoleExporter writes rendered lines to ``sys.stderr``."""

    def test_writes_to_stderr(self) -> None:
        buf = _Buffer()
        ctx = _make_ctx()
        with patch.object(_sys, "stderr", buf):
            exporter = ConsoleExporter(ctx)
            exporter.export(_make_message(args=["hello"]))
        assert "hello" in buf.text
        # Trailing newline (TS console.log adds one; we mirror that).
        assert buf.text.endswith("\n")

    def test_writes_full_line_with_level_and_name(self) -> None:
        buf = _Buffer()
        ctx = _make_ctx()
        with patch.object(_sys, "stderr", buf):
            exporter = ConsoleExporter(ctx)
            exporter.export(_make_message(args=["hi"], name="my-scope", type="info"))
        text = buf.text
        # Must contain the message, the level prefix "[I]", and the scope name.
        assert "hi" in text
        assert "[I]" in text
        assert "my-scope" in text


class TestExporterFormatBasic:
    """Default format includes timestamp + level + scope + message."""

    def test_format_basic(self) -> None:
        buf = _Buffer()
        ctx = _make_ctx()
        with patch.object(_sys, "stderr", buf):
            exporter = ConsoleExporter(ctx)
            exporter.export(_make_message(args=["simple message"]))
        rendered = buf.text.rstrip("\n")
        # Timestamp pattern: 4-digit year + 2-digit month/day/hour/min/sec.
        # We don't pin exact digits (timezone-dependent), but the year prefix
        # ``20`` of any 2026 timestamp should appear.
        assert "20" in rendered
        # Level marker
        assert "[I]" in rendered
        # Body
        assert "simple message" in rendered


class TestExporterFormatWithScope:
    """Scope name appears between the level prefix and the body."""

    def test_format_with_scope(self) -> None:
        buf = _Buffer()
        ctx = _make_ctx()
        with patch.object(_sys, "stderr", buf):
            exporter = ConsoleExporter(ctx)
            exporter.export(_make_message(args=["body"], name="alpha-scope", type="info"))
        text = buf.text
        assert "alpha-scope" in text
        assert "body" in text


class TestExporterFormatInspectsArgs:
    """Object args are rendered via the inspect formatter (pformat)."""

    def test_format_inspects_args(self) -> None:
        buf = _Buffer()
        ctx = _make_ctx()
        with patch.object(_sys, "stderr", buf):
            exporter = ConsoleExporter(ctx)
            exporter.export(_make_message(args=[{"key": "value", "n": 1}]))
        # The dict body is rendered through pprint-style formatting. Keys
        # appear quoted; values appear in some form.
        assert "'key'" in buf.text or '"key"' in buf.text
        assert "value" in buf.text
        assert "1" in buf.text

    def test_inspect_formatter_used_for_percent_o(self) -> None:
        buf = _Buffer()
        ctx = _make_ctx()
        with patch.object(_sys, "stderr", buf):
            exporter = ConsoleExporter(ctx)
            # Use printf-style %o to force the inspect formatter.
            exporter.export(_make_message(args=["payload=%o", {"a": 1}]))
        assert "payload=" in buf.text
        assert "'a'" in buf.text or '"a"' in buf.text
        assert "1" in buf.text


class TestExporterLevelColor:
    """ANSI colors are emitted iff stderr is a TTY."""

    def test_color_when_tty(self) -> None:
        buf = _Buffer(is_tty=True)
        ctx = _make_ctx()
        with patch.object(_sys, "stderr", buf):
            exporter = ConsoleExporter(ctx)
            # Disable showTime so output is deterministic; showTime would
            # still be wrapped in ANSI codes but we only check the level marker.
            exporter.show_time = ""
            exporter.export(_make_message(args=["x"], type="warn"))
        text = buf.text
        # ANSI ESC + color prefix should appear (color code 3 == yellow).
        assert "\x1b[" in text
        assert "33" in text  # ANSI yellow uses code 33

    def test_no_color_when_not_tty(self) -> None:
        buf = _Buffer(is_tty=False)
        ctx = _make_ctx()
        with patch.object(_sys, "stderr", buf):
            exporter = ConsoleExporter(ctx)
            exporter.export(_make_message(args=["x"], type="warn"))
        text = buf.text
        # No ANSI escape sequences should be present.
        assert "\x1b[" not in text


class TestExporterDefaults:
    """Defaults match the upstream `getDefaults()` values."""

    def test_default_show_time(self) -> None:
        ctx = _make_ctx()
        exporter = ConsoleExporter(ctx)
        # Upstream default is the timestamp template string.
        assert exporter.show_time == "yyyy-MM-dd hh:mm:ss "

    def test_default_colors_when_not_tty(self) -> None:
        buf = _Buffer(is_tty=False)
        ctx = _make_ctx()
        with patch.object(_sys, "stderr", buf):
            exporter = ConsoleExporter(ctx)
        # Colors should be falsy (no TTY → no colors).
        assert not exporter.colors

    def test_default_colors_when_tty(self) -> None:
        buf = _Buffer(is_tty=True)
        ctx = _make_ctx()
        with patch.object(_sys, "stderr", buf):
            exporter = ConsoleExporter(ctx)
        # Colors should be a positive int (TTY → 1-level colors).
        assert isinstance(exporter.colors, int) and exporter.colors > 0

    def test_default_formatters_include_o_and_uppercase_o(self) -> None:
        ctx = _make_ctx()
        exporter = ConsoleExporter(ctx)
        assert "o" in exporter.formatters
        assert "O" in exporter.formatters
        assert callable(exporter.formatters["o"])
        assert callable(exporter.formatters["O"])


class TestExporterRendersMultipleLevels:
    """Each severity gets its own ANSI color code."""

    @pytest.mark.parametrize(
        ("type_", "ansi_code"),
        [
            ("error", "31"),  # red
            ("warn", "33"),  # yellow
            ("info", "32"),  # green
            ("debug", "34"),  # blue
        ],
    )
    def test_level_color_mapping(self, type_: str, ansi_code: str) -> None:
        buf = _Buffer(is_tty=True)
        ctx = _make_ctx()
        with patch.object(_sys, "stderr", buf):
            exporter = ConsoleExporter(ctx)
            exporter.show_time = ""
            exporter.export(_make_message(args=["m"], type=type_))
        assert ansi_code in buf.text


class TestExporterCustomization:
    """Constructor config overrides defaults."""

    def test_show_diff_appends_time_diff(self) -> None:
        buf = _Buffer(is_tty=False)
        ctx = _make_ctx()
        with patch.object(_sys, "stderr", buf):
            exporter = ConsoleExporter(ctx, show_diff=True)
            # Two messages: the second should show a +diff suffix.
            exporter.export(_make_message(args=["first"]))
            exporter.export(_make_message(args=["second"]))
        # The diff marker should appear at least once (TS upstream uses " +").
        assert " +" in buf.text

    def test_show_time_disabled(self) -> None:
        buf = _Buffer(is_tty=False)
        ctx = _make_ctx()
        with patch.object(_sys, "stderr", buf):
            exporter = ConsoleExporter(ctx, show_time="")
            exporter.export(_make_message(args=["no-time"]))
        # With showTime disabled the line should not contain the template
        # placeholder tokens ("yyyy", "MM", etc.).
        assert "yyyy" not in buf.text
        assert "no-time" in buf.text

    def test_config_as_dict(self) -> None:
        # Config may also be supplied as a plain dict (1:1 with upstream
        # ``Object.assign(this, defaults, config)`` ergonomics).
        ctx = _make_ctx()
        exporter = ConsoleExporter(ctx, {"show_time": "", "show_diff": True})
        assert exporter.show_time == ""
        assert exporter.show_diff is True

    def test_config_as_dataclass(self) -> None:
        # ``ConsoleExporterConfig`` round-trips through the constructor.
        ctx = _make_ctx()
        cfg = ConsoleExporterConfig(show_time="hh:mm:ss ", show_diff=True)
        exporter = ConsoleExporter(ctx, cfg)
        assert exporter.show_time == "hh:mm:ss "
        assert exporter.show_diff is True

    def test_kwargs_override_config(self) -> None:
        # Keyword arguments take precedence over a passed ``config`` dict.
        ctx = _make_ctx()
        exporter = ConsoleExporter(ctx, {"show_time": "yyyy "}, show_time="hh:mm:ss ")
        assert exporter.show_time == "hh:mm:ss "


class TestExporterStderrErrorHandling:
    """Exporter swallows stderr write errors (1:1 with cordis contract)."""

    def test_stderr_write_error_silenced(self) -> None:
        ctx = _make_ctx()

        class _BrokenStderr(_Buffer):
            def write(self, payload: str) -> int:  # type: ignore[override]
                raise OSError("stderr closed")

        with patch.object(_sys, "stderr", _BrokenStderr()):
            exporter = ConsoleExporter(ctx)
            # Must not raise even though ``write`` blows up.
            exporter.export(_make_message(args=["hello"]))


class TestExporterLabelAlignment:
    """Label alignment controls label position vs. level prefix."""

    def test_right_aligned_label(self) -> None:
        buf = _Buffer(is_tty=False)
        ctx = _make_ctx()
        with patch.object(_sys, "stderr", buf):
            exporter = ConsoleExporter(ctx, label=LabelStyle(width=10, align="right"))
            exporter.export(_make_message(args=["body"], name="short", type="info"))
        text = buf.text
        assert "short" in text
        assert "[I]" in text
        assert "body" in text

    def test_label_margin(self) -> None:
        buf = _Buffer(is_tty=False)
        ctx = _make_ctx()
        with patch.object(_sys, "stderr", buf):
            exporter = ConsoleExporter(ctx, label=LabelStyle(margin=3))
            exporter.export(_make_message(args=["x"], type="info"))
        # Margin of 3 means three spaces appear between the prefix ``[I]``
        # and the label ``test`` (render order is ``prefix space label``).
        text = buf.text
        idx_label = text.find("test")
        idx_prefix = text.find("[I]")
        assert idx_label >= 0 and idx_prefix >= 0
        between = text[idx_prefix + len("[I]"):idx_label]
        assert "   " in between

    def test_label_width_pads(self) -> None:
        buf = _Buffer(is_tty=False)
        ctx = _make_ctx()
        with patch.object(_sys, "stderr", buf):
            exporter = ConsoleExporter(ctx, label=LabelStyle(width=15))
            exporter.export(_make_message(args=["x"], type="info"))
        # With width=15 and label "test", at least 11 spaces of padding
        # appear right after the label text.
        text = buf.text
        idx_label = text.find("test")
        assert idx_label >= 0
        after_label = text[idx_label + len("test"):]
        # The first whitespace run after the label should be at least 11 chars.
        run = 0
        for ch in after_label:
            if ch == " ":
                run += 1
            else:
                break
        assert run >= 11
