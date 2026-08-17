# Python 移植约定 — 所有 packages/core + packages/llm 共用

taiyi-agent 是 deepseek-harness 的 Python 移植。每个包必须按本约定写代码，保证跨包一致。

## 1. 通用风格

- Python ≥ 3.11，使用现代语法（`X | Y` union、`match`、`async for`、`dataclass`）。
- 类型标注：所有公共 API 必须有类型注解。
- 风格：dataclass for data containers；Protocol for typing；`async def` for async fns；`AsyncIterator[T]` for streams。
- 错误处理：抛具体异常（`ValueError`, `KeyError`, `TypeError`）；不要裸 `except Exception`。
- 字符串：模块字符串用 `"""..."""`；f-string 内插；不用 `%` 或 `.format()`。

## 2. 依赖 cordis

每个包的核心入口是 `@plugin async def setup(ctx, config): ...`。公共 surface 暴露在 `__init__.py`。

```python
# packages/foo/bar/src/foo_bar/__init__.py
from dataclasses import dataclass
from typing import Any
from cordis import Context, Service

@dataclass
class MyType:
    name: str
    value: int

class MyService(Service):
    def __init__(self, ctx: Context, **cfg):
        super().__init__(ctx)
        self._items: dict[str, MyType] = {}

    def register(self, item: MyType) -> None:
        self._items[item.name] = item

    def get(self, name: str) -> MyType | None:
        return self._items.get(name)

__all__ = ["MyType", "MyService"]
```

```python
# packages/foo/bar/src/foo_bar/plugin.py
from cordis import plugin

@plugin
async def setup(ctx, config):
    from . import MyService
    svc = MyService(ctx, **(config or {}))
    ctx.provide("my_service", svc)
    ctx.effect(svc, name="my_service:service")
```

## 3. 事件命名

cordis 的事件名用 `path/segment/segment` 形式（与 dsh 1:1），全部 lower-case + snake/kebab。

```python
# my_types.py
class Event:
    FOO_START = "foo/start"
    FOO_END = "foo/end"
```

事件类型 dispatch mode（与 dsh cordis 一致）：
- `ctx.emit(name, *args)` — serial-await（遇 bail 停）
- `ctx.parallel(name, fn)` — 并发 await
- `ctx.waterfall(name, fn)` — 链式 next
- `ctx.bail(name, fn)` — 同步首遇 bail 停

监听器默认是 serial。`ctx.parallel/warterfall/bail` 只是语义标记。

## 4. 异步 vs 同步

- plugin 必须是 `async def`
- Service.dispose() 是 async
- ctx.dispose() / plugin() / mount() 是 async
- 默认 listeners 可以是 sync 或 async，框架自动 await coroutine

## 5. 错误契约

- 缺少 service：`ctx.inject(key)` 不传 default 抛 `KeyError`
- 缺少 plugin：`mount()` 在 plugin not found 时抛 `ImportError` / `AttributeError`
- schema 校验失败：抛 `pydantic.ValidationError`
- 网络错误：抛原异常（`httpx.HTTPError`）

## 6. 测试

每个包应该有 `tests/test_<pkg>.py`，覆盖：
- 数据类型构造
- Service 注册 / 注销 / 查找
- plugin 挂载后 services 可注入
- 主要事件流（如有）

用 `pytest-asyncio` (`asyncio_mode = "auto"` 已配)。

## 7. 不做

- 不写 TODO / FIXME 占位
- 不抄 TS 代码 1:1；用 Python 习惯
- 不引第三方依赖除非必要（pydantic / httpx 已 OK）
- 不为兼容旧行为加 shim（pre-release 阶段，README 已声明）

## 8. 验证

包完成后跑：
```bash
cd /home/lichao/taiyi-agent
.venv/bin/python -c "from <pkg> import ..."  # import ok
.venv/bin/python -m pytest tests/ -q --no-cov  # tests pass
.venv/bin/python -c "import asyncio; from cordis import Context; from <pkg>.plugin import setup; asyncio.run(Context().plugin(setup, {}))"  # plugin mounts
```