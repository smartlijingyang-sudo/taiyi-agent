"""``logger_console.browser`` — Browser-style exporter (stdout-routed).

1:1 port of ``@deepseek-ai/logger-console`` ``src/browser.ts``. The TS
upstream overrides ``export(message)`` to dispatch to the native browser
console (``console.error``, ``console.warn``, ``console.log``); Python
has no native browser console, so this module mirrors the same routing
contract by emitting to ``sys.stdout`` (for ``info`` / ``debug``) and
``sys.stderr`` (for ``warn`` / ``error``).
"""

from __future__ import annotations

import sys as _sys
from typing import Any

from cordis.logger import Message

from logger_console.exporter import ConsoleExporter

__all__ = ["BrowserConsoleExporter"]


class BrowserConsoleExporter(ConsoleExporter):
    """Browser-routed exporter; prints to stdout/stderr instead of stderr.

    Mirrors the upstream ``browser.ts`` behaviour:
    - ``message.type == 'error'`` → ``stderr``
    - ``message.type == 'warn'`` → ``stderr``
    - otherwise → ``stdout``

    The TS upstream calls ``console.error`` / ``console.warn`` / ``console.log``
    directly. Python lacks a native "browser console", so this exporter
    emulates the same routing by choosing the appropriate stream.
    """

    def export(self, message: Message) -> Any:
        """Render ``message`` and write it to stdout/stderr.

        The body uses a simpler ``[LEVEL] <name> <args>`` prefix than
        the Node ``ConsoleExporter``; this matches the TS browser build,
        which intentionally drops the timestamp / scope-padding logic
        in favour of the browser's own styling.
        """
        prefix = f"[{message.type[0].upper()}] {message.name}"
        body = " ".join(str(arg) for arg in message.args)
        line = f"{prefix} {body}".rstrip()

        if message.type in ("error", "warn"):
            stream = _sys.stderr
        else:
            stream = _sys.stdout

        try:
            stream.write(line + "\n")
            stream.flush()
        except Exception:
            # Never let an exporter raise (1:1 with cordis logger contract).
            pass
        return None
