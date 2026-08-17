"""taiyi-logger-console — Console logger exporter.

对齐 dsh vendor/logger-console：提供带颜色、时间戳、标签样式的控制台日志输出。
"""
from __future__ import annotations

import sys
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from cordis import Context, Service

__all__ = ["ConsoleExporter", "plugin"]

# 颜色支持级别（兼容 supports-color）
ColorSupportLevel = int | bool

# ANSI 颜色代码
COLORS = {
    "reset": "\033[0m",
    "bold": "\033[1m",
    "red": "\033[31m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "blue": "\033[34m",
    "magenta": "\033[35m",
    "cyan": "\033[36m",
    "gray": "\033[90m",
}


@dataclass
class LabelStyle:
    """标签样式配置。"""

    width: int = 0
    margin: int = 1
    align: str = "left"  # 'left' | 'right'


@dataclass
class Message:
    """日志消息。"""

    name: str
    type: str  # 'debug' | 'info' | 'warn' | 'error'
    args: tuple
    ts: int = field(default_factory=lambda: int(time.time() * 1000))


class ConsoleExporter:
    """控制台日志导出器。

    支持：
      - 颜色输出（自动检测终端支持）
      - 时间戳格式化
      - 标签样式（宽度、对齐）
      - 时间差显示
    """

    name = "logger-console"

    def __init__(self, ctx: Context, config: dict[str, Any] | None = None) -> None:
        self.ctx = ctx
        cfg = config or {}

        # 配置
        self.colors: ColorSupportLevel = cfg.get("colors", self._detect_colors())
        self.show_time: str = cfg.get("show_time", "%Y-%m-%d %H:%M:%S ")
        self.show_diff: bool = cfg.get("show_diff", False)
        self.label = LabelStyle(
            width=cfg.get("label", {}).get("width", 0),
            margin=cfg.get("label", {}).get("margin", 1),
            align=cfg.get("label", {}).get("align", "left"),
        )

        self.timestamp = int(time.time() * 1000)

        # 注册为 logger exporter
        logger = ctx.inject("logger", None)
        if logger and hasattr(logger, "add_exporter"):
            logger.add_exporter(self)

    @staticmethod
    def _detect_colors() -> ColorSupportLevel:
        """检测终端颜色支持。"""
        if not hasattr(sys.stdout, "isatty"):
            return 0
        if not sys.stdout.isatty():
            return 0
        # 简单检测：如果有 TERM 环境变量，假设有颜色支持
        if "TERM" in __import__("os").environ:
            return 1
        return 0

    def export(self, message: Message) -> None:
        """输出日志消息到控制台。"""
        print(self.render(message))

    def render(self, message: Message) -> str:
        """渲染日志消息为字符串。"""
        # 前缀：[TYPE]
        prefix = f"[{message.type[0].upper()}]"
        space = " " * self.label.margin

        output = ""
        indent = 3 + len(space)

        # 时间戳
        if self.show_time:
            indent += len(self.show_time)
            time_str = time.strftime(self.show_time, time.localtime(message.ts / 1000))
            output += self._color(8, time_str)

        # 标签（logger name）
        code = self._code(message.name)
        label = self._color(code, message.name, bold=True)
        pad_length = self.label.width + len(label) - len(message.name)

        if self.label.align == "right":
            output += label.rjust(pad_length) + space + prefix + space
            indent += self.label.width + len(space)
        else:
            output += prefix + space + label.ljust(pad_length) + space

        # 消息内容
        msg_str = " ".join(str(arg) for arg in message.args)
        output += msg_str.replace("\n", "\n" + " " * indent)

        # 时间差
        if self.show_diff and self.timestamp:
            diff = message.ts - self.timestamp
            output += self._color(code, f" +{self._format_time(diff)}")

        self.timestamp = message.ts
        return output

    def _color(self, code: int, text: str, bold: bool = False) -> str:
        """应用颜色代码。"""
        if not self.colors:
            return text
        # 简化：使用固定颜色映射
        color_map = {
            0: "gray",
            1: "cyan",
            2: "green",
            3: "yellow",
            4: "blue",
            5: "magenta",
            6: "red",
            7: "white",
            8: "gray",
        }
        color = color_map.get(code % 8, "white")
        prefix = COLORS.get(color, "")
        if bold:
            prefix += COLORS.get("bold", "")
        return f"{prefix}{text}{COLORS['reset']}"

    @staticmethod
    def _code(name: str) -> int:
        """根据 logger name 生成颜色代码（0-7）。"""
        return hash(name) % 8

    @staticmethod
    def _format_time(ms: int) -> str:
        """格式化时间差。"""
        if ms < 1000:
            return f"{ms}ms"
        elif ms < 60000:
            return f"{ms / 1000:.1f}s"
        elif ms < 3600000:
            return f"{ms / 60000:.1f}m"
        else:
            return f"{ms / 3600000:.1f}h"


def plugin(ctx: Context, config: dict[str, Any] | None) -> None:
    """挂载 ConsoleExporter。"""
    exporter = ConsoleExporter(ctx, config)
    # ConsoleExporter 在构造时自动注册到 logger
