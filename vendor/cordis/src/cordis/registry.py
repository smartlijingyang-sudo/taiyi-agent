"""Registry — typed collection of services。

cordis RegistryService 的等价物：
  - 按 name 注册 / 注销
  - 按 name 查找
  - 维护插入顺序（services()）
  - 命名冲突报错
"""
from __future__ import annotations

from typing import Generic, Iterable, Iterator, TypeVar

T = TypeVar("T")


class Registry(Generic[T]):
    """typed registry — 命名空间内的 service 集合。"""

    def __init__(self) -> None:
        self._services: dict[str, T] = {}
        self._order: list[str] = []

    def register(self, name: str, service: T) -> None:
        if name in self._services:
            raise ValueError(f"service {name!r} already registered")
        self._services[name] = service
        self._order.append(name)

    def unregister(self, name: str) -> Optional[T]:
        svc = self._services.pop(name, None)
        if name in self._order:
            self._order.remove(name)
        return svc

    def get(self, name: str, default: Optional[T] = None) -> Optional[T]:
        return self._services.get(name, default)

    def has(self, name: str) -> bool:
        return name in self._services

    def names(self) -> list[str]:
        return list(self._order)

    def services(self) -> list[T]:
        return [self._services[n] for n in self._order]

    def items(self) -> Iterator[tuple[str, T]]:
        for n in self._order:
            yield n, self._services[n]

    def __iter__(self) -> Iterator[tuple[str, T]]:
        return self.items()

    def __len__(self) -> int:
        return len(self._services)

    def __contains__(self, name: object) -> bool:
        return isinstance(name, str) and name in self._services

    def __repr__(self) -> str:
        names = ", ".join(self._order)
        return f"<Registry({len(self._services)}) [{names}]>"