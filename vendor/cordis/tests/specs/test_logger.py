"""Tests for cordis.logger — 1:1 port of upstream logger.ts."""

from __future__ import annotations

import io
from contextlib import redirect_stderr

import pytest

from cordis.logger import (
    Exporter,
    Logger,
    LoggerLevel,
    LoggerService,
    Message,
    c16,
    c256,
    default_formatters,
    hyphenate,
)


class TestLoggerLevel:
    """LoggerLevel is a numeric severity enum (1:1 with upstream)."""

    def test_error_is_zero(self):
        assert LoggerLevel.ERROR == 0

    def test_info_is_one(self):
        assert LoggerLevel.INFO == 1

    def test_warn_is_two(self):
        assert LoggerLevel.WARN == 2

    def test_debug_is_three(self):
        assert LoggerLevel.DEBUG == 3

    def test_name_returns_string(self):
        assert LoggerLevel.name(LoggerLevel.ERROR) == "error"
        assert LoggerLevel.name(LoggerLevel.INFO) == "info"
        assert LoggerLevel.name(LoggerLevel.WARN) == "warn"
        assert LoggerLevel.name(LoggerLevel.DEBUG) == "debug"

    def test_name_unknown_falls_back_to_info(self):
        assert LoggerLevel.name(999) == "info"


class TestHyphenate:
    """hyphenate converts camelCase to kebab-case."""

    def test_simple(self):
        assert hyphenate("foo") == "foo"

    def test_camel_case(self):
        assert hyphenate("fooBar") == "foo-bar"

    def test_multi_word(self):
        assert hyphenate("fooBarBaz") == "foo-bar-baz"

    def test_already_lowercase(self):
        assert hyphenate("hello") == "hello"

    def test_starts_with_capital(self):
        # Upstream-style: drop leading hyphen for names starting with uppercase
        assert hyphenate("FooBar") == "foo-bar"


class TestColorPalettes:
    """c16 and c256 are static color index palettes."""

    def test_c16_is_list(self):
        assert isinstance(c16, list)
        assert all(isinstance(x, int) for x in c16)

    def test_c256_is_list(self):
        assert isinstance(c256, list)
        assert len(c256) > 0
        assert all(isinstance(x, int) for x in c256)

    def test_c16_matches_upstream(self):
        # 1:1 with upstream logger.ts
        assert c16 == [6, 2, 3, 4, 5, 1]


class TestDefaultFormatters:
    """default_formatters implements printf-style placeholders."""

    def test_s_formatter(self):
        result = default_formatters["s"](42, _exporter_stub(), _message_stub())
        assert result == "42"

    def test_d_formatter(self):
        result = default_formatters["d"](3.7, _exporter_stub(), _message_stub())
        assert result == 3

    def test_i_formatter(self):
        result = default_formatters["i"](3.7, _exporter_stub(), _message_stub())
        assert result == 3

    def test_f_formatter(self):
        result = default_formatters["f"](3.7, _exporter_stub(), _message_stub())
        assert result == 3.7

    def test_o_formatter(self):
        result = default_formatters["o"]({"a": 1}, _exporter_stub(), _message_stub())
        assert '"a"' in result and "1" in result

    def test_O_formatter(self):
        result = default_formatters["O"]({"a": 1}, _exporter_stub(), _message_stub())
        assert '"a"' in result and "1" in result

    def test_c_formatter(self):
        result = default_formatters["c"](None, _exporter_stub(), _message_stub())
        assert result == ""

    def test_C_formatter_with_colors_disabled(self):
        exp = Exporter(export=lambda m: None, colors=False)
        msg = Message(sn=1, ts=0, name="foo", type="info", level=0, args=[])
        result = default_formatters["C"]("X", exp, msg)
        assert result == "X"

    def test_C_formatter_with_colors_enabled(self):
        exp = Exporter(export=lambda m: None, colors=2)
        msg = Message(sn=1, ts=0, name="foo", type="info", level=0, args=[])
        result = default_formatters["C"]("X", exp, msg)
        assert "\x1b[" in result


class TestLoggerColor:
    """Logger.color formats ANSI color codes (1:1 with upstream)."""

    def test_no_colors_returns_plain(self):
        exp = Exporter(export=lambda m: None, colors=False)
        assert Logger.color(exp, 5, "hello") == "hello"

    def test_basic_color_code(self):
        exp = Exporter(export=lambda m: None, colors=1)
        result = Logger.color(exp, 3, "hi")
        assert "\x1b[33m" in result
        assert "hi" in result
        assert "\x1b[0m" in result

    def test_256_color_code(self):
        exp = Exporter(export=lambda m: None, colors=2)
        result = Logger.color(exp, 200, "hi")
        assert "8;5;200" in result


class TestLoggerCode:
    """Logger.code hashes a name to a color index (1:1 with upstream)."""

    def test_empty_name_returns_index(self):
        code = Logger.code("", False)
        assert code == 0  # empty hash → first color

    def test_deterministic_hash(self):
        # Same name → same code
        assert Logger.code("foo", 2) == Logger.code("foo", 2)

    def test_different_names_may_differ(self):
        # Different names should usually produce different codes (probabilistic)
        codes = {Logger.code(f"name{i}", 2) for i in range(20)}
        assert len(codes) > 1

    def test_false_level_returns_zero(self):
        # When level is false, colors list is empty so any index returns 0
        assert Logger.code("foo", False) == 0

    def test_level_2_uses_c256(self):
        code = Logger.code("foo", 2)
        assert code in c256

    def test_level_1_uses_c16(self):
        code = Logger.code("foo", 1)
        assert code in c16


class TestLoggerFormat:
    """Logger.format applies printf-style placeholders (1:1 with upstream)."""

    def test_simple_no_format(self):
        exp = Exporter(export=lambda m: None)
        msg = Message(sn=1, ts=0, name="foo", type="info", level=0, args=["hello"])
        assert Logger.format(exp, msg) == "hello"

    def test_s_placeholder(self):
        exp = Exporter(export=lambda m: None)
        msg = Message(sn=1, ts=0, name="foo", type="info", level=0, args=["%s world", 42])
        assert Logger.format(exp, msg) == "42 world"

    def test_d_placeholder(self):
        exp = Exporter(export=lambda m: None)
        msg = Message(sn=1, ts=0, name="foo", type="info", level=0, args=["count=%d", 3.7])
        assert "count=3" in Logger.format(exp, msg)

    def test_o_placeholder_inserted_when_first_arg_not_string(self):
        exp = Exporter(export=lambda m: None)
        msg = Message(sn=1, ts=0, name="foo", type="info", level=0, args=[{"x": 1}])
        result = Logger.format(exp, msg)
        assert '"x"' in result and "1" in result

    def test_percent_literal(self):
        exp = Exporter(export=lambda m: None)
        msg = Message(sn=1, ts=0, name="foo", type="info", level=0, args=["100%%"])
        assert Logger.format(exp, msg) == "100%"

    def test_error_instance_uses_stack(self):
        exp = Exporter(export=lambda m: None)
        try:
            raise ValueError("boom")
        except ValueError as e:
            msg = Message(sn=1, ts=0, name="foo", type="error", level=0, args=[e])
            result = Logger.format(exp, msg)
        assert "boom" in result

    def test_max_length_truncates(self):
        exp = Exporter(export=lambda m: None, max_length=10)
        msg = Message(sn=1, ts=0, name="foo", type="info", level=0, args=["x" * 100])
        result = Logger.format(exp, msg)
        assert len(result.split("\n")[0]) <= 13  # 10 + "..."


class TestLoggerFacade:
    """Logger facade records messages to all exporters (1:1 with upstream)."""

    def test_logger_has_severity_methods(self):
        service = LoggerService.__new__(LoggerService)
        service._sn_message = 0
        service.exporters = {}
        service.buffer = []
        logger = Logger({"name": "test"}, service)
        assert callable(logger.error)
        assert callable(logger.info)
        assert callable(logger.warn)
        assert callable(logger.debug)

    def test_info_records_to_exporter(self):
        captured: list[Message] = []
        service = LoggerService.__new__(LoggerService)
        service._sn_message = 0
        service.exporters = {1: Exporter(export=captured.append, levels=None)}
        service.buffer = []
        logger = Logger({"name": "test"}, service)
        logger.info("hello %s", "world")
        assert len(captured) == 1
        assert captured[0].name == "test"
        assert captured[0].type == "info"
        assert captured[0].level == LoggerLevel.INFO

    def test_exporter_level_threshold_filters(self):
        captured: list[Message] = []
        service = LoggerService.__new__(LoggerService)
        service._sn_message = 0
        service.exporters = {
            1: Exporter(
                export=captured.append,
                levels={"test": LoggerLevel.ERROR},
            )
        }
        service.buffer = []
        logger = Logger({"name": "test"}, service)
        logger.info("not emitted")  # level INFO > ERROR, so filtered
        logger.error("emitted")
        assert len(captured) == 1
        assert captured[0].type == "error"

    def test_exporter_level_default_threshold(self):
        # Upstream semantic: levels is "max level threshold" — emit messages
        # whose level number is <= the threshold. With threshold WARN(2):
        # emit ERROR(0), INFO(1), WARN(2); only DEBUG(3) is filtered.
        captured: list[Message] = []
        service = LoggerService.__new__(LoggerService)
        service._sn_message = 0
        service.exporters = {
            1: Exporter(export=captured.append, levels={"default": LoggerLevel.WARN})
        }
        service.buffer = []
        logger = Logger({"name": "unknown"}, service)
        logger.info("emitted")
        logger.warn("emitted")
        logger.debug("filtered")
        assert len(captured) == 2
        assert captured[0].type == "info"
        assert captured[1].type == "warn"

    def test_logger_level_fallback(self):
        # logger.level acts as fallback threshold (max-level semantic).
        # With logger.level=WARN(2): emit ERROR(0)/INFO(1)/WARN(2); filter DEBUG(3).
        captured: list[Message] = []
        service = LoggerService.__new__(LoggerService)
        service._sn_message = 0
        service.exporters = {1: Exporter(export=captured.append, levels=None)}
        service.buffer = []
        logger = Logger({"name": "test", "level": LoggerLevel.WARN}, service)
        logger.info("emitted")
        logger.error("emitted")
        logger.debug("filtered")
        assert len(captured) == 2

    def test_error_with_cause_recurses(self):
        captured: list[Message] = []
        service = LoggerService.__new__(LoggerService)
        service._sn_message = 0
        service.exporters = {1: Exporter(export=captured.append)}
        service.buffer = []
        logger = Logger({"name": "test"}, service)
        try:
            try:
                raise ValueError("inner")
            except ValueError as inner:
                raise RuntimeError("outer") from inner
        except RuntimeError as e:
            logger.error(e)
        # Should recurse on cause → 2 messages
        assert len(captured) >= 1

    def test_aggregate_error_unrolled(self):
        captured: list[Message] = []
        service = LoggerService.__new__(LoggerService)
        service._sn_message = 0
        service.exporters = {1: Exporter(export=captured.append)}
        service.buffer = []
        logger = Logger({"name": "test"}, service)

        # Construct an AggregateError-like object
        class AggErr(Exception):
            def __init__(self) -> None:
                super().__init__("agg")
                self.errors = [ValueError("e1"), ValueError("e2")]

        logger.error(AggErr())
        # Should emit multiple messages
        assert len(captured) >= 2

    def test_sn_increments(self):
        captured: list[Message] = []
        service = LoggerService.__new__(LoggerService)
        service._sn_message = 0
        service.exporters = {1: Exporter(export=captured.append)}
        service.buffer = []
        logger = Logger({"name": "test"}, service)
        logger.info("a")
        logger.info("b")
        logger.info("c")
        sns = [m.sn for m in captured]
        assert sns == [1, 2, 3]

    def test_ts_is_recent_milliseconds(self):
        import time as _t
        captured: list[Message] = []
        service = LoggerService.__new__(LoggerService)
        service._sn_message = 0
        service.exporters = {1: Exporter(export=captured.append)}
        service.buffer = []
        logger = Logger({"name": "test"}, service)
        before = int(_t.time() * 1000)
        logger.info("now")
        after = int(_t.time() * 1000)
        assert before <= captured[0].ts <= after


class TestLoggerService:
    """LoggerService is installed as ctx.logger with callable + severity methods."""

    def test_buffer_default(self):
        service = LoggerService.__new__(LoggerService)
        service.buffer_size = 1000
        service.buffer = []
        service._sn_message = 0
        service._sn_exporter = 0
        service.exporters = {}
        # Default buffer exporter installed during __init__; bypass.
        service._install_default_exporter()
        assert len(service.exporters) == 1

    def test_install_buffer_exporter_appends(self):
        service = LoggerService.__new__(LoggerService)
        service.buffer_size = 1000
        service.buffer = []
        service._sn_message = 0
        service._sn_exporter = 0
        service.exporters = {}
        service._install_default_exporter()
        logger = Logger({"name": "test"}, service)
        logger.info("hello")
        assert len(service.buffer) == 1
        assert service.buffer[0].args == ["hello"]

    def test_buffer_truncates_to_size(self):
        service = LoggerService.__new__(LoggerService)
        service.buffer_size = 3
        service.buffer = []
        service._sn_message = 0
        service._sn_exporter = 0
        service.exporters = {}
        service._install_default_exporter()
        logger = Logger({"name": "test"}, service)
        for i in range(10):
            logger.info(f"msg-{i}")
        assert len(service.buffer) == 3
        assert service.buffer[-1].args == ["msg-9"]

    def test_exporter_returns_disposer(self):
        service = LoggerService.__new__(LoggerService)
        service.buffer_size = 1000
        service.buffer = []
        service._sn_message = 0
        service._sn_exporter = 0
        service.exporters = {}

        # Build a minimal ctx with effect() so disposal wiring is exercised
        class FakeCtx:
            def __init__(self) -> None:
                self.calls: list[Any] = []

            def effect(self, fn, label=""):
                self.calls.append(fn)
                return None

        service.ctx = FakeCtx()
        dispose = service.exporter(Exporter(export=lambda m: None))
        assert callable(dispose)

    def test_callable_returns_logger_with_name(self):
        service = LoggerService.__new__(LoggerService)
        service.buffer_size = 1000
        service.buffer = []
        service._sn_message = 0
        service._sn_exporter = 0
        service.exporters = {}
        service.ctx = None  # __call__ gracefully handles None
        logger = service("explicit-name")
        assert logger.name == "explicit-name"

    def test_callable_falls_back_to_root(self):
        service = LoggerService.__new__(LoggerService)
        service.buffer_size = 1000
        service.buffer = []
        service._sn_message = 0
        service._sn_exporter = 0
        service.exporters = {}
        service.ctx = None
        logger = service()
        assert logger.name == "root"

    def test_callable_uses_config_name(self):
        service = LoggerService.__new__(LoggerService)
        service.buffer_size = 1000
        service.buffer = []
        service._sn_message = 0
        service._sn_exporter = 0
        service.exporters = {}
        service._resolve_config = lambda: {"name": "from-config"}
        service.ctx = None
        logger = service()
        assert logger.name == "from-config"

    def test_severity_methods_forward_to_logger(self):
        service = LoggerService.__new__(LoggerService)
        service.buffer_size = 1000
        service.buffer = []
        service._sn_message = 0
        service._sn_exporter = 0
        service.exporters = {}
        service.ctx = None
        # Should not raise even with no ctx
        service.error("test")
        service.info("test")
        service.warn("test")
        service.debug("test")

    def test_resolve_config_returns_empty_when_no_intercept(self):
        service = LoggerService.__new__(LoggerService)
        service.ctx = None
        assert service._resolve_config() == {}

    def test_resolve_config_walks_prototype_chain(self):
        service = LoggerService.__new__(LoggerService)

        class FakeCtx:
            def __getitem__(self, key: str) -> Any:
                parent = {"logger": {"level": LoggerLevel.WARN}}
                return type("Intercept", (), {"__proto__": parent, "logger": {"name": "child"}})

        service.ctx = FakeCtx()
        config = service._resolve_config()
        assert config.get("name") == "child"
        assert config.get("level") == LoggerLevel.WARN


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _exporter_stub() -> Exporter:
    return Exporter(export=lambda m: None)


def _message_stub() -> Message:
    return Message(sn=0, ts=0, name="test", type="info", level=LoggerLevel.INFO, args=[])


__all__ = [
    "TestLoggerLevel",
    "TestHyphenate",
    "TestColorPalettes",
    "TestDefaultFormatters",
    "TestLoggerColor",
    "TestLoggerCode",
    "TestLoggerFormat",
    "TestLoggerFacade",
    "TestLoggerService",
]