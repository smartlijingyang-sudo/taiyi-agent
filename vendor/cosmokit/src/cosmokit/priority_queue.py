"""Priority queue — 异步调度友好。"""
from __future__ import annotations

import heapq
from dataclasses import dataclass, field
from typing import Generic, TypeVar

T = TypeVar("T")


@dataclass(order=True)
class _Entry(Generic[T]):
    priority: float
    counter: int
    item: T = field(compare=False)


class PriorityQueue(Generic[T]):
    """min-heap；priority 越小越先出。FIFO 通过 counter 维持。"""

    def __init__(self) -> None:
        self._heap: list[_Entry[T]] = []
        self._counter = 0
        self._cancelled: set[int] = set()

    def push(self, item: T, priority: float = 0.0) -> int:
        self._counter += 1
        entry = _Entry(priority=priority, counter=self._counter, item=item)
        heapq.heappush(self._heap, entry)
        return self._counter

    def pop(self) -> T | None:
        while self._heap:
            entry = heapq.heappop(self._heap)
            if entry.counter in self._cancelled:
                self._cancelled.discard(entry.counter)
                continue
            return entry.item
        return None

    def cancel(self, handle: int) -> None:
        self._cancelled.add(handle)

    def __len__(self) -> int:
        return len(self._heap)

    def __bool__(self) -> bool:
        return bool(self._heap)