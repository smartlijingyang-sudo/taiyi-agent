"""Tests for logger_console.format — pprint-based inspect-style formatter.

1:1 with upstream `@deepseek-ai/logger-console` shared formatter behaviour,
adapted to Python's ``pprint.pformat``.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from logger_console.format import (
    inspect_format,
    inspect_formatter,
    isatty,
    level_color,
)


def _exporter(colors: int | bool | None = 0) -> MagicMock:
    """Build a minimal Exporter-shaped mock with a `colors` attribute."""
    exp = MagicMock()
    exp.colors = colors
    return exp


def _message() -> MagicMock:
    """Build a minimal Message-shaped mock (no fields needed by inspect)."""
    return MagicMock()


class TestInspectFormat:
    """`inspect_format` is the underlying pprint-style pretty-printer."""

    def test_pformat_dict(self) -> None:
        result = inspect_format({"a": 1, "b": 2})
        # pprint.pformat keeps keys in insertion order with sort_dicts=False
        assert "'a'" in result and "1" in result
        assert "'b'" in result and "2" in result

    def test_pformat_nested(self) -> None:
        result = inspect_format({"outer": {"inner": [1, 2, 3]}})
        assert "'outer'" in result
        assert "'inner'" in result
        assert "1" in result and "2" in result and "3" in result

    def test_pformat_handles_long_strings(self) -> None:
        # pprint does not truncate strings by default (mirrors util.inspect
        # with default maxStringLength=null); we only assert that the call
        # returns a string and contains the long payload.
        long_string = "x" * 500
        result = inspect_format({"key": long_string})
        assert isinstance(result, str)
        assert long_string in result

    def test_pformat_list(self) -> None:
        result = inspect_format([1, 2, 3])
        assert "1" in result and "2" in result and "3" in result

    def test_pformat_scalar(self) -> None:
        # Scalars are still rendered through pformat (matches util.inspect
        # which can also format primitives)
        result = inspect_format(42)
        assert result == "42"

    def test_pformat_string(self) -> None:
        result = inspect_format("hello")
        # pprint quotes strings
        assert result == "'hello'"


class TestInspectFormatter:
    """`inspect_formatter` is the callable Formatter for %o / %O placeholders."""

    def test_returns_pformat_of_dict(self) -> None:
        result = inspect_formatter({"k": "v"}, _exporter(colors=0), _message())
        assert "'k'" in result and "'v'" in result

    def test_returns_pformat_of_nested(self) -> None:
        result = inspect_formatter({"a": {"b": 1}}, _exporter(colors=0), _message())
        assert "'a'" in result and "'b'" in result and "1" in result

    def test_returns_pformat_of_list(self) -> None:
        result = inspect_formatter([1, 2, 3], _exporter(colors=0), _message())
        assert "1" in result and "2" in result and "3" in result

    def test_handles_long_strings(self) -> None:
        long_string = "z" * 500
        result = inspect_formatter({"k": long_string}, _exporter(colors=0), _message())
        assert isinstance(result, str)
        assert long_string in result

    def test_handles_primitive(self) -> None:
        # Primitives pass through pformat too.
        assert inspect_formatter(7, _exporter(colors=0), _message()) == "7"


class TestLevelColor:
    """`level_color` maps log severity to an ANSI color code."""

    def test_error_is_red(self) -> None:
        assert level_color("error") == 1  # ANSI red

    def test_warn_is_yellow(self) -> None:
        assert level_color("warn") == 3  # ANSI yellow

    def test_info_is_green(self) -> None:
        assert level_color("info") == 2  # ANSI green

    def test_debug_is_blue(self) -> None:
        assert level_color("debug") == 4  # ANSI blue

    def test_unknown_falls_back_to_default(self) -> None:
        # Anything not in {error, warn, info, debug} should fall back to
        # a sensible default (gray / code 7).
        assert level_color("trace") == 7


class TestIsatty:
    """`isatty` reports whether stderr is attached to a TTY."""

    def test_isatty_default_is_false(self, monkeypatch: object) -> None:
        # We can't rely on the actual stream state under pytest (capture),
        # so exercise the helper directly with explicit values.
        # The helper delegates to ``sys.stderr.isatty()``.
        import sys as _sys

        original = _sys.stderr.isatty

        class _Fake:
            def isatty(self) -> bool:
                return False

        _sys.stderr = _Fake()  # type: ignore[assignment]
        try:
            assert isatty() is False
        finally:
            _sys.stderr.isatty = original  # type: ignore[attr-defined]

    def test_isatty_true(self) -> None:
        import sys as _sys

        original = _sys.stderr.isatty

        class _Fake:
            def isatty(self) -> bool:
                return True

        _sys.stderr = _Fake()  # type: ignore[assignment]
        try:
            assert isatty() is True
        finally:
            _sys.stderr.isatty = original  # type: ignore[attr-defined]

    def test_isatty_handles_attribute_error(self) -> None:
        # ``isatty`` should swallow ``AttributeError`` raised by streams
        # that do not implement ``isatty`` (e.g. test doubles).
        import sys as _sys

        class _BareStream:
            pass

        _sys.stderr = _BareStream()  # type: ignore[assignment]
        assert isatty() is False
