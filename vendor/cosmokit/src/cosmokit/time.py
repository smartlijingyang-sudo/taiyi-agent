"""Time — millisecond timestamp + ISO 字符串。"""
from __future__ import annotations

import time
from datetime import datetime, timezone


class Time:
    @staticmethod
    def now() -> float:
        """秒（float, monotonic 时钟相对值参考 epoch）。"""
        return time.time()

    @staticmethod
    def now_ms() -> int:
        return int(time.time() * 1000)

    @staticmethod
    def iso(ms: int | None = None) -> str:
        ts = ms / 1000 if ms is not None else time.time()
        return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()