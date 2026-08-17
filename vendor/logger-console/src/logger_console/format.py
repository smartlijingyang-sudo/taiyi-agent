"""``logger_console.format`` — pprint-based inspect-style formatter.

1:1 port of ``@deepseek-ai/logger-console`` shared formatter, adapted to
``pprint.pformat`` (the Python equivalent of ``util.inspect``).

Key adaptation notes (mirrored in the README):

- ``util.inspect(value, { colors, depth: Infinity, compact: true, breakLength: Infinity })``
  → ``pprint.pformat(value, indent=2, width=120, depth=4, sort_dicts=False)``.
  The Python port uses a finite ``depth`` (4) and finite ``width`` (120)
  to keep the rendered output within terminal norms; the TS upstream's
  ``depth: Infinity`` would explode recursion for cyclic structures.
- ``Logger.color(exporter, code, value, ';1')`` is replaced by direct
  ANSI escape emission (``\\x1b[3{code}m{value}\\x1b[0m``), preserving
  the upstream visual.
"""

from __future__ import annotations

import pprint
import sys as _sys
from typing import Any

__all__ = [
    "inspect_format",
    "inspect_formatter",
    "level_color",
    "isatty",
    "ANSI_RESET",
]


# ANSI 16-color foreground codes for log severity levels. Mirrors the TS
# upstream's choice of red / yellow / green / blue for ERROR / WARN / INFO
# / DEBUG, plus a gray fallback for unknown levels.
_LEVEL_COLORS: dict[str, int] = {
    "error": 1,   # red
    "warn": 3,    # yellow
    "info": 2,    # green
    "debug": 4,   # blue
}

_DEFAULT_LEVEL_COLOR: int = 7  # gray (fallback for "trace" or unknown)

# ANSI reset code (kept as a module-level constant for readability).
ANSI_RESET: str = "\x1b[0m"


def inspect_format(value: Any) -> str:
    """Render ``value`` via ``pprint.pformat`` (Python equivalent of ``util.inspect``).

    Configuration:

    - ``indent=2`` — two-space indent for nested structures.
    - ``width=120`` — line-width budget (TS upstream uses ``breakLength: Infinity``).
    - ``depth=4`` — recursion guard (TS uses ``Infinity``; Python gets a
      finite cap to avoid stack blowups on cyclic / deeply nested data).
    - ``sort_dicts=False`` — preserve insertion order, mirroring
      ``util.inspect``'s default key ordering.
    """
    return pprint.pformat(
        value,
        indent=2,
        width=120,
        depth=4,
        sort_dicts=False,
    )


def inspect_formatter(value: Any, exporter: Any, message: Any) -> str:
    """Printf-style ``Formatter`` used by ``%o`` / ``%O`` placeholders.

    Mirrors the upstream ``inspectFormatter`` (1:1 behaviour, same call
    signature as :class:`cordis.logger.Formatter`).
    """
    return inspect_format(value)


def level_color(level: str) -> int:
    """Map a log-level name to an ANSI 16-color foreground code.

    Unknown levels fall back to gray (code 7).
    """
    return _LEVEL_COLORS.get(level, _DEFAULT_LEVEL_COLOR)


def isatty() -> bool:
    """Return ``True`` iff ``sys.stderr`` is attached to a TTY.

    Mirrors the upstream ``supports-color`` detection for stderr.
    """
    try:
        return bool(_sys.stderr.isatty())
    except (AttributeError, ValueError):
        return False
