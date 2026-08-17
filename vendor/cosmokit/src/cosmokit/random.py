"""Random — uuid / short id / int."""
from __future__ import annotations

import secrets
import string


class Random:
    """轻量 Random 工具。与 @kosko/cosmokit Random 形态对齐。"""

    @staticmethod
    def uuid() -> str:
        """标准 RFC 4122 UUID v4。"""
        return str(secrets.token_hex(16))

    @staticmethod
    def short_id(length: int = 8) -> str:
        """短 id（base36 字符集）。"""
        alphabet = string.ascii_letters + string.digits
        return "".join(secrets.choice(alphabet) for _ in range(length))

    @staticmethod
    def int(minimum: int = 0, maximum: int = 2**31 - 1) -> int:
        return secrets.randbelow(maximum - minimum + 1) + minimum

    @staticmethod
    def pick(items: list, default=None):
        import secrets as _s
        if not items:
            return default
        return items[_s.randbelow(len(items))]