"""``logger_console.exporter`` — ConsoleExporter writing to stderr.

1:1 port of ``@deepseek-ai/logger-console`` shared ``ConsoleExporter``
(``vendor/logger-console/src/shared.ts``) + Node entry
(``vendor/logger-console/src/index.ts``), adapted to Python.

Behavioural differences from the TS upstream:

1. **stderr instead of stdout.** The TS upstream calls ``console.log``
   (which writes to stdout). Python conventions write log records to
   ``stderr``; the Python port mirrors that convention.
2. **TTY detection via ``sys.stderr.isatty()``** instead of
   ``supports-color``. Both produce a falsy value when stderr is not a
   terminal, so the resulting ``colors`` field carries an analogous
   ``int | False`` shape (``int 1`` on TTY, ``False`` otherwise).
3. **No ``util.inspect`` import.** The Python formatter delegates to
   ``pprint.pformat`` (see :mod:`logger_console.format`).
"""

from __future__ import annotations

import sys as _sys
import time as _time
from dataclasses import dataclass
from typing import Any, cast

from cordis.logger import Exporter, Formatter, Logger, Message
from cosmokit.time import Time

from logger_console.format import inspect_formatter, isatty, level_color

__all__ = [
    "ConsoleExporter",
    "ConsoleExporterConfig",
    "LabelStyle",
]


# ---------------------------------------------------------------------------
# Config types (mirror upstream `ConsoleExporter.Config` and `LabelStyle`)
# ---------------------------------------------------------------------------


@dataclass
class LabelStyle:
    """Formatting options for the logger-name label (1:1 with upstream)."""

    width: int = 0
    margin: int = 1
    align: str = "left"  # 'left' | 'right'


@dataclass
class ConsoleExporterConfig:
    """Configuration namespace for ConsoleExporter (1:1 with upstream)."""

    colors: bool | int = False
    max_length: int = 10240
    levels: dict[str, int] | None = None
    show_diff: bool = False
    show_time: str = "yyyy-MM-dd hh:mm:ss "
    label: LabelStyle | None = None


# ---------------------------------------------------------------------------
# ConsoleExporter (1:1 port of upstream shared.ts + index.ts)
# ---------------------------------------------------------------------------


class ConsoleExporter:
    """Shared console log exporter writing rendered lines to stderr.

    Implements the :class:`cordis.logger.Exporter` contract (one
    ``export(message: Message) -> None`` method) and the upstream's
    shared ``ConsoleExporter`` semantics: timestamp + level prefix +
    scope label + formatted body, with optional ANSI coloring and a
    trailing diff since the previous message.
    """

    static_name: str = "logger-console"

    # Per-instance fields. Defaults applied by ``get_defaults`` and merged
    # with the caller's ``config`` in the constructor.
    colors: bool | int
    max_length: int
    levels: dict[str, int] | None
    show_diff: bool
    show_time: str
    label: LabelStyle | None
    timestamp: int

    # Formatter override table — mirrors the Node entry's
    # ``formatters = { o, O }`` dict.
    formatters: dict[str, Formatter]

    def __init__(
        self,
        ctx: Any,
        config: ConsoleExporterConfig | dict[str, Any] | None = None,
        *,
        colors: bool | int | None = None,
        max_length: int | None = None,
        levels: dict[str, int] | None = None,
        show_diff: bool | None = None,
        show_time: str | None = None,
        label: LabelStyle | None = None,
    ) -> None:
        # Apply defaults, then overlay caller config. Mirrors upstream
        # ``Object.assign(this, this.getDefaults(), config)``: every
        # recognised field may be supplied as a kwarg for ergonomics.
        defaults = self.get_defaults()
        merged: dict[str, Any] = dict(defaults)
        if config is not None:
            if isinstance(config, ConsoleExporterConfig):
                overlay: dict[str, Any] = {
                    "colors": config.colors,
                    "max_length": config.max_length,
                    "levels": config.levels,
                    "show_diff": config.show_diff,
                    "show_time": config.show_time,
                    "label": config.label,
                }
            else:
                overlay = dict(config)
            merged.update(overlay)
        # Keyword overrides take precedence over a passed ``config`` object.
        for kw_name, kw_value in (
            ("colors", colors),
            ("max_length", max_length),
            ("levels", levels),
            ("show_diff", show_diff),
            ("show_time", show_time),
            ("label", label),
        ):
            if kw_value is not None:
                merged[kw_name] = kw_value

        self.colors = merged["colors"]
        self.max_length = merged["max_length"]
        self.levels = merged["levels"]
        self.show_diff = merged["show_diff"]
        self.show_time = merged["show_time"]
        self.label = merged["label"]
        # Use Python's wall-clock for the initial ``timestamp`` (matches
        # the TS upstream's ``Date.now()``). ``Time`` does not expose a
        # ``now_ms`` helper in the cosmokit Python port.
        self.timestamp = int(_time.time() * 1000)

        # Per-instance formatters (1:1 with upstream's per-instance
        # ``formatters = { o, O }`` assignment).
        self.formatters = {
            "o": inspect_formatter,
            "O": inspect_formatter,
        }

        # Register with the cordis logger service so messages route here.
        # The exporter stays usable even if the ctx has no logger.
        logger = getattr(ctx, "logger", None)
        if logger is not None and hasattr(logger, "exporter"):
            logger.exporter(self)

    # ------------------------------------------------------------------
    # Defaults (1:1 with upstream `getDefaults()`)
    # ------------------------------------------------------------------

    def get_defaults(self) -> dict[str, Any]:
        """Return default config values (1:1 with upstream ``getDefaults``).

        The Node-specific entry overrides this to also set ``colors``
        from ``supports-color``. The Python port does the same — TTY
        detection uses ``sys.stderr.isatty()`` and produces an integer
        colour level (1) when attached, ``False`` otherwise.
        """
        colors: bool | int = 1 if isatty() else False
        return {
            "colors": colors,
            "max_length": 10240,
            "levels": None,
            "show_diff": False,
            "show_time": "yyyy-MM-dd hh:mm:ss ",
            "label": None,
        }

    # ------------------------------------------------------------------
    # Export / render (1:1 with upstream `export` / `render`)
    # ------------------------------------------------------------------

    def export(self, message: Message) -> None:
        """Render ``message`` and write the resulting line to stderr."""
        line = self.render(message)
        try:
            _sys.stderr.write(line + "\n")
            _sys.stderr.flush()
        except Exception:
            # Never let an exporter raise (1:1 with cordis logger contract).
            pass

    def render(self, message: Message) -> str:
        """Build a single rendered log line.

        Format: ``<timestamp> <label> <level> <formatted-body>``
        (with optional ``+diff`` suffix when ``show_diff`` is enabled).

        The level prefix is colored with a severity-specific ANSI code
        (red / yellow / green / blue) when colors are enabled, matching
        the task contract (``Level-based prefix... with ANSI colors when
        TTY``). The TS upstream does not color the prefix itself; the
        Python port adds this on top.

        The ``indent`` value tracks how wide the prefix line is so that
        continuation lines (produced by multi-line message bodies) stay
        aligned with the body start.
        """
        # ``self`` implements the ``Exporter`` interface (same fields,
        # same ``export()`` method) but is not a subclass; cast to the
        # ``Exporter`` shape so the cordis ``Logger`` static helpers
        # accept it.
        exporter = cast(Exporter, self)

        type_name = message.type or "info"
        level_letter = (type_name[:1] if type_name else "i").upper()
        plain_prefix = f"[{level_letter}]"
        if self.colors:
            colored_prefix = Logger.color(exporter, level_color(type_name), plain_prefix)
        else:
            colored_prefix = plain_prefix
        space = " " * (self.label.margin if self.label else 1)

        # ``plain_prefix`` is 3 chars regardless of ANSI decoration, so
        # the indent (which feeds continuation-line alignment) is based
        # on the visual prefix length: ``3 + space`` plus the timestamp.
        indent = len(plain_prefix) + len(space)
        output = ""

        if self.show_time:
            indent += len(self.show_time)
            output += Logger.color(exporter, 8, Time.template(self.show_time))

        code = Logger.code(message.name, self.colors)
        label_text = Logger.color(exporter, code, message.name, ";1")
        pad_length = (
            (self.label.width if self.label else 0)
            + len(label_text)
            - len(message.name)
        )
        if self.label is not None and self.label.align == "right":
            output += label_text.rjust(pad_length) + space + colored_prefix + space
            indent += (self.label.width if self.label else 0) + len(space)
        else:
            output += colored_prefix + space + label_text.ljust(pad_length) + space

        body = Logger.format(exporter, message)
        output += body.replace("\n", "\n" + " " * indent)

        if self.show_diff and self.timestamp:
            diff_ms = message.ts - self.timestamp
            output += Logger.color(exporter, code, " +" + Time.format(diff_ms))

        self.timestamp = message.ts
        return output
