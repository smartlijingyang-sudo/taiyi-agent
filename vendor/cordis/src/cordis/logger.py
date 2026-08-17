"""`cordis.logger` — Logger service: 5 levels + child loggers + formatter.

Faithful 1:1 port of `~/deepseek-harness/vendor/cordis/src/logger.ts`.

This module ships a minimal :class:`LoggerService` for Task 1.5;
Task 1.7 expands it with the full level/formatter pipeline and exporters.
"""

from __future__ import annotations

import logging as stdlogging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from cordis.utils import Tracker

if TYPE_CHECKING:  # pragma: no cover — import-only for typing
    from cordis.context import Context

__all__ = [
    "LoggerLevel",
    "Logger",
    "Message",
    "Exporter",
    "LoggerService",
]


# ---------------------------------------------------------------------------
# Level enum
# ---------------------------------------------------------------------------


class LoggerLevel:
    """Numeric severity for exporters (mirrors upstream ``LoggerLevel``)."""

    ERROR = 0
    INFO = 1
    WARN = 2
    DEBUG = 3

    _NAMES: dict[int, str] = {
        0: "error",
        1: "info",
        2: "warn",
        3: "debug",
    }

    @classmethod
    def name(cls, value: int) -> str:
        return cls._NAMES.get(value, "info")


# ---------------------------------------------------------------------------
# Message + Exporter
# ---------------------------------------------------------------------------


@dataclass
class Message:
    """Structured log record (mirrors upstream ``Message``)."""

    sn: int
    ts: int
    name: str
    type: str
    level: int
    args: list[Any]
    fiber: Any = None


class Exporter:
    """Sink receiving structured log messages (ABC-style; Task 1.7 expands)."""

    def export(self, message: Message) -> None:  # pragma: no cover — abstract
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Logger + LoggerService
# ---------------------------------------------------------------------------


@dataclass
class Logger:
    """Logger facade for one named subsystem."""

    name: str = "root"
    level: int | None = None
    meta: dict[str, Any] = field(default_factory=dict)
    service: "LoggerService | None" = None

    def _method(self, kind: str, level: int) -> Callable[..., None]:
        service = self.service or LoggerService.placeholder()

        def _emit(*args: Any) -> None:
            try:
                service.record(level=level, kind=kind, name=self.name, args=list(args), meta=self.meta)
            except Exception:  # pragma: no cover — logger must not raise
                pass

        return _emit

    @property
    def error(self) -> Callable[..., None]:
        return self._method("error", LoggerLevel.ERROR)

    @property
    def info(self) -> Callable[..., None]:
        return self._method("info", LoggerLevel.INFO)

    @property
    def warn(self) -> Callable[..., None]:
        return self._method("warn", LoggerLevel.WARN)

    @property
    def debug(self) -> Callable[..., None]:
        return self._method("debug", LoggerLevel.DEBUG)


class LoggerService:
    """Logging service installed as ``ctx.logger``.

    This scaffold stores messages in an in-memory buffer; Task 1.7
    upgrades exporters with the full formatters/colors pipeline.
    """

    placeholder_class: type[Any] | None = None

    def __init__(self, ctx: "Context") -> None:
        self.ctx: "Context" = ctx
        self.buffer: list[Message] = []
        self.buffer_size: int = 1000
        self.exporters: dict[int, Exporter] = {}
        self._sn_message: int = 0
        self._sn_exporter: int = 0

        self._tracker = Tracker(property="ctx", no_shadow=True)
        try:
            self.__dict__["cordis.tracker"] = self._tracker
        except Exception:  # pragma: no cover — defensive
            pass

        self._install_default_exporter()

    # ------------------------------------------------------------------
    # Public API used by ``Logger``
    # ------------------------------------------------------------------

    def __call__(self, name: str | None = None) -> Logger:
        """Create a named :class:`Logger` facade."""
        # Resolve config from intercepts.
        config = self._resolve_config()
        if name is None:
            name = config.get("name") or "root"

        level = config.get("level", LoggerLevel.INFO)
        meta: dict[str, Any] = {}

        # Try to fetch the origin fiber for ``meta.fiber``.
        origin = self.ctx
        try:
            shadow = getattr(origin, "cordis.shadow", None)
            if shadow is not None:
                origin = shadow
            fiber = origin.fiber
        except Exception:
            fiber = None
        if fiber is not None:
            meta["fiber"] = fiber

        return Logger(name=name, level=level, meta=meta, service=self)

    # Severity entrypoints (mirrored on LoggerService instance).
    def error(self, *args: Any) -> None:  # pragma: no cover — façade
        self(level_name=LoggerLevel.name(LoggerLevel.ERROR), level=LoggerLevel.ERROR).__class__

    def info(self, *args: Any) -> None:  # pragma: no cover — façade
        pass

    def warn(self, *args: Any) -> None:  # pragma: no cover — façade
        pass

    def debug(self, *args: Any) -> None:  # pragma: no cover — façade
        pass

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def record(
        self, level: int, kind: str, name: str, args: list[Any], meta: dict[str, Any]
    ) -> None:
        """Emit a structured Message to all installed exporters."""
        self._sn_message += 1
        msg = Message(
            sn=self._sn_message,
            ts=0,
            name=name,
            type=kind,
            level=level,
            args=args,
            fiber=meta.get("fiber"),
        )
        for exporter in self.exporters.values():
            try:
                exporter.export(msg)
            except Exception:  # pragma: no cover — exporter must not break
                pass

    def exporter(self, exporter: Exporter) -> Callable[[], bool]:
        """Register an exporter; dispose with the current fiber."""
        self._sn_exporter += 1
        sn = self._sn_exporter
        self.exporters[sn] = exporter

        def _dispose() -> bool:
            return self.exporters.pop(sn, None) is not None

        try:
            self.ctx.effect(_install_exporter_effect(self, sn, exporter), "ctx.logger.exporter()")  # type: ignore[attr-defined]
        except Exception:  # pragma: no cover
            pass
        return _dispose

    def _install_default_exporter(self) -> None:
        """Boot-level exporter that records into the buffer."""
        service = self

        class _BufferExporter(Exporter):
            def export(self_inner, message: Message) -> None:
                service.buffer.append(message)
                if len(service.buffer) > service.buffer_size:
                    service.buffer = service.buffer[-service.buffer_size:]

        self.exporters[0] = _BufferExporter()

    def _resolve_config(self) -> dict[str, Any]:
        """Walk intercepts to find a logger config; flat-merging ancestor + child."""
        configs: list[dict[str, Any]] = []
        node: Any = self.ctx
        try:
            intercept = node[symbols.intercept]  # type: ignore[name-defined]
        except Exception:
            intercept = {}
        seen: set[int] = set()
        while intercept is not None and id(intercept) not in seen:
            seen.add(id(intercept))
            own = intercept.get("logger") if hasattr(intercept, "get") else None
            if isinstance(own, dict):
                configs.append(own)
            parent_obj = getattr(intercept, "__parent__", None)
            if parent_obj is intercept:
                break
            intercept = parent_obj
        merged: dict[str, Any] = {}
        for cfg in reversed(configs):
            merged.update(cfg)
        return merged

    @classmethod
    def placeholder(cls) -> "LoggerService":  # pragma: no cover
        """Return a sentinel for use when no LoggerService is installed."""

        class _Stub:
            buffer: list[Any] = []

            def record(self, **kwargs: Any) -> None:
                self.buffer.append(kwargs)

        return _Stub()  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _install_exporter_effect(
    service: LoggerService, sn: int, exporter: Exporter
) -> Callable[[], Callable[[], bool]]:
    def _effect() -> Callable[[], bool]:
        service.exporters[sn] = exporter
        return lambda: service.exporters.pop(sn, None) is not None

    return _effect


try:
    from cordis.utils import symbols as _symbols
except Exception:  # pragma: no cover
    _symbols = None
symbols = _symbols


# Map the ``error``/``info``/etc. on instance to ``self()``.
for _kind in ("error", "info", "warn", "debug"):
    method = getattr(stdlogging, _kind.upper(), None)

    def _mk(_kind: str) -> Callable[..., None]:
        def _method(self: LoggerService, *args: Any) -> None:
            try:
                facade = self()
                getattr(facade, _kind)(*args)
            except Exception:  # pragma: no cover
                pass

        return _method

    setattr(LoggerService, _kind, _mk(_kind))
del _kind
del _mk
del method
