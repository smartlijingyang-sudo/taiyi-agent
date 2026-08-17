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

## 7.5. 移植范围与质量要求（1:1 移植的硬性约定）

**每个 chunk 的实现必须是上游对应的 1:1 port，不允许为了「先跑起来」「缩短工期」「降低复杂度」而跳过 validation/helpers/edge-case。**

- **Plan 列出的每个文件都要 port。** Plan 的 `Files:` 清单是 port scope 的下限——不能因为文件多就拆掉、合并掉、或跳过其中某些。
- **不要精简上游逻辑。** 看到 `assert_message_event_shape` / `assert_session_event_envelope` / `deep_freeze` / `snapshot_json_value` / `adopt_session_event` 之类的 helper 就 port 进去——它们是上游 append 路径的强制校验，删了就把"构造坏 session 时直接报错"变成"序列化时才静默失败"。
- **不要省略 edge case。** 上游写的 `boundary 不能落在 open turn 中间`、`seq 必须连续`、`sourceEventSeqs 必须包含每个 shadowed node` 之类的 invariant，是 fork / append / replay 的契约，省了就破坏持久化往返。
- **TODO 注释禁用于"占位"**。如果某段逻辑暂时用不到，应直接删掉或 `# pragma: no cover`，不能留 `# TODO: implement later` 在 port 文件里假装存在。
- **Plan 之外的上游文件要 port 吗？** 看 spec §X 表格（如 spec §6 列了 core/session 的 6 个文件）。如果 spec 表格里有，plan 漏了 = plan 漏了，要补；spec 表格没有的，port 也不需要。判断依据是 spec，不是主观"够用就行"。

**违反这条的下游表现**：
- 100% 测试覆盖仍可能过，但实际跑起来时遇到上游能 catch 的错误这边静默掉
- fork / replay / restore 这些跨进程场景一上来就 silent divergence
- "实现完成"看着 OK，但持久化往返不正确（持久化插件读旧 log 时崩或重建错历史）

## 8. 验证

包完成后跑：
```bash
cd /home/lichao/taiyi-agent
.venv/bin/python -c "from <pkg> import ..."  # import ok
.venv/bin/python -m pytest tests/ -q --no-cov  # tests pass
.venv/bin/python -c "import asyncio; from cordis import Context; from <pkg>.plugin import setup; asyncio.run(Context().plugin(setup, {}))"  # plugin mounts
```