"""Logger — minimal structlog 替代。"""
from __future__ import annotations

import logging
import os
import sys
from typing import Any

_LEVELS = {
    "trace": 5,
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warn": logging.WARNING,
    "error": logging.ERROR,
    "fatal": logging.CRITICAL,
}


def get_logger(name: str = "taiyi") -> logging.LoggerAdapter:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        env_level = os.environ.get("TAIYI_LOG_LEVEL", "info").lower()
        handler.setLevel(_LEVELS.get(env_level, logging.INFO))
        fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
        handler.setFormatter(fmt)
        logger.addHandler(handler)
        logger.setLevel(handler.level)
        logger.propagate = False
    return logger


def configure(level: str = "info") -> None:
    """全局调整日志级别。"""
    logging.getLogger("taiyi").setLevel(_LEVELS.get(level.lower(), logging.INFO))


def bind(logger: logging.LoggerAdapter, **kv: Any) -> "_Bound":
    """structlog 风格的 bind()。"""
    return _Bound(logger, kv)


class _Bound:
    def __init__(self, logger: logging.LoggerAdapter, kv: dict[str, Any]) -> None:
        self._logger = logger
        self._kv = kv

    def _emit(self, level: int, msg: str, extra: dict[str, Any] | None = None) -> None:
        payload = {**self._kv, **(extra or {})}
        suffix = " ".join(f"{k}={v!r}" for k, v in payload.items())
        self._logger.log(level, f"{msg} {suffix}".rstrip())

    def debug(self, msg: str, **kv: Any) -> None:
        self._emit(logging.DEBUG, msg, kv)

    def info(self, msg: str, **kv: Any) -> None:
        self._emit(logging.INFO, msg, kv)

    def warning(self, msg: str, **kv: Any) -> None:
        self._emit(logging.WARNING, msg, kv)

    def warn(self, msg: str, **kv: Any) -> None:
        self._emit(logging.WARNING, msg, kv)

    def error(self, msg: str, **kv: Any) -> None:
        self._emit(logging.ERROR, msg, kv)

    def exception(self, msg: str, **kv: Any) -> None:
        self._emit(logging.ERROR, msg, kv)