# Taiyi Agent — Phase 0 1:1 复刻实施 plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `~/deepseek-harness`（dsh）的 Phase 0 范围（70 包 + 9 vendor + ~30 scripts）按 spec `docs/superpowers/specs/2026-08-17-taiyi-agent-1to1-design.md` §12 1:1 翻译为 Python，使 `uv run taiyi web` 能在 3080 端口起可工作的 web surface（chat UI + 流式回复 + session 持久化 + DeepSeek adapter）。

**Architecture:** 一切皆插件（cordis plugin model）。每个包是 uv workspace member，命名 `taiyi-<group>-<pkg>`；公共 surface 在 `__init__.py`，plugin 入口在 `plugin.py`，按 `@plugin async def setup(ctx, config)` 契约挂载。YAML `cordis.yml` + `cordis.patch.yml` 驱动加载。Phase 0 仅交付 `bundle/base`（451 行 patch）。

**Tech Stack:**
- Python ≥ 3.11（dataclass / Protocol / `X | Y` / `async def` / `match`）
- uv workspace + uv.lock
- cordis 框架（vendored Python 复刻）
- pydantic v2 + PyYAML + httpx
- FastAPI + uvicorn（webserver host）+ aiohttp（SSE streaming）
- pytest + pytest-asyncio + coverage（5 lane + per-file 100%）
- ruff（lint） + pyright（typecheck strict）
- 上游锚定：`~/deepseek-harness`（每个 implementer subagent 自行 cat 对应 ts 文件做 1:1 翻译）

**Reference spec:** `docs/superpowers/specs/2026-08-17-taiyi-agent-1to1-design.md`
**Reference conventions:** `CONVENTIONS.md`
**上游源码：** `~/deepseek-harness`

> **移植范围硬性约束**：每个 chunk 的实现必须严格 1:1 对应上游对应文件。Plan 列出的 `Files:` 清单是 port scope 的下限——不能因为工作量大就拆掉、合并、跳过 helper / validation / edge case。看到 `assert_*` / `snapshot_*` / `deep_freeze` / `adopt_*` / `freeze_restored_object` 之类的 helper 必须 port 进去，因为它们是上游 append / restore / replay 路径的强制校验，删了就破坏持久化往返。详见 `CONVENTIONS.md` §7.5。

---

## Chunk 0: Pre-flight（决策 + 准备）

> 这是 Phase 0 的真正第 1 步；不通过就不进入 Chunk 1。

### Task 0.1: 用户授权 + 工作区切换

**Files:**
- Modify: `pyproject.toml`（workspace members 列表 → 与 Chunk 23 同步最终态）
- Delete: 见 Task 0.2
- Create: branch `phase0/1to1-rebuild`（基于 origin/main HEAD，与本地 main 解耦）

- [ ] **Step 1: 用户确认**
  - 弹出 `ask_user_question` 二次确认是否真要 `rm` 现有 16 包 + 9 vendor + MVP CLI。
  - 默认答案：「是」按 spec §0 决策「全部清空，从零重建」。
  - 默认答案：「否」则保留 MVP，phase 0 用新目录 `packages.new/`、`vendor.new/`、最后替换；spec §0 默认是前者，本任务按前者执行。

- [ ] **Step 2: 建分支**
  - `git fetch origin`
  - `git checkout -b phase0/1to1-rebuild origin/main`（基于 origin/main；本地 main 的 2 commits 已并入 origin/main 假设它们 push 过；否则基于本地 main HEAD）

- [ ] **Step 3: 准备 worktree（推荐）**
  - `git worktree add ../taiyi-agent-phase0 phase0/1to1-rebuild`
  - 在 worktree 里所有后续步骤执行；最后 `git worktree remove` + 切回 main + merge

### Task 0.2: 清空 + 重建骨架目录

**Files:**
- Delete: `packages/`、`vendor/`、`src/taiyi_agent/`、`profiles/`、`apps/`（如存在）、`tests/`、`scripts/`（如存在）
- Keep: `pyproject.toml`（仅保留 `[project] name/version/requires-python`、`[build-system]`、`[tool.uv.workspace]` 占位——后续 Chunk 23 重写；本步骤先留 `[project.scripts]` 空 + `[tool.uv.workspace] members = []` 直至 Chunk 23）、`uv.lock`（删了重建）、`README.md`（保留覆盖警告）、`.gitignore`、`.ruff.toml`、`pyrightconfig.json`、`pytest.ini`（若已存在则保留，否则新建空骨架）
- Create: 目录骨架
  - `packages/{core,llm,typert,api,session,session-query,storage,credentials,settings,identity,interaction,boot,util,host,client,bundle,extensions,hooks,plan,todo,preset,guard,context,goal,schedule,feedback,subagent,jobs,workflow,sandbox,shell,subprocess,terminal,code-runtime,fs,lsp,skill,web,compaction,examples,test-support,runtime-diagnostics}/` 占位
  - `vendor/{cordis,cosmokit,schemastery,loader,include,group,timer,hmr,logger-console}/` 占位
  - `src/taiyi_agent/` 占位
  - `profiles/{base,web,headless}/` 占位
  - `apps/{cli,web}/` 占位
  - `scripts/`
  - `docs/{superpowers/specs,superpowers/plans}/`（specs 已存在）

- [ ] **Step 1: 备份 + 删除**
  - `git stash`（如有未提交改动）
  - `git rm -rf packages/ vendor/ src/ profiles/ tests/` （保守起见 apps/scripts 不删，避免误伤下游）
  - `rm -rf apps/ scripts/`（如有）

- [ ] **Step 2: 创建骨架目录**
  - 用 `mkdir -p` 创建上面 `Create:` 列表的占位目录
  - 每个空目录放 `.gitkeep`（避免 git 不跟踪）

- [ ] **Step 3: 写 root pyproject.toml（最小骨架）**
  - 仅保留 `[project]`、`[build-system]`、`[tool.uv.workspace]`（空 members）、`[tool.uv.sources]`（空）；Chunk 23 再扩展
  - 删除 `[project.scripts]` 直至 CLI 重建

- [ ] **Step 4: Commit**
  - `git add -A`
  - `git commit -m "chore: wipe MVP and scaffold 1:1 phase 0 directories"`

- [ ] **Step 5: 验证**
  - `uv sync` 应成功（空 workspace，无依赖解析错误）
  - `git status` 应为空（除 .gitkeep 占位）

---

## Chunk 1: Vendor — cordis（基础框架，9 文件 / 2693 LOC upstream）

> cordis 是整个 1:1 工作量最大的一块。所有 plugin 都基于它。**必须先于其他所有 package**。

### Task 1.1: vendor/cordis 包骨架

**Files:**
- Create: `vendor/cordis/pyproject.toml`（name=`taiyi-cordis`，depends 仅 stdlib，conftest 不引第三方）
- Create: `vendor/cordis/README.md`（列每个改写决策，对应 spec §14 风险「cordis Python 端口有隐藏语义差」）
- Create: `vendor/cordis/src/cordis/__init__.py`
- Create: `vendor/cordis/tests/__init__.py`
- Create: `vendor/cordis/tests/conftest.py`
- Create: `vendor/cordis/tests/specs/__init__.py`

- [ ] **Step 1: 写 pyproject.toml**
  ```toml
  [project]
  name = "taiyi-cordis"
  version = "0.1.0"
  requires-python = ">=3.11"
  dependencies = []

  [build-system]
  requires = ["hatchling"]
  build-backend = "hatchling.build"

  [tool.hatch.build.targets.wheel]
  packages = ["src/cordis"]
  ```

- [ ] **Step 2: 写 README 改写决策**
  - `Symbol.for(x)` → Python `id(x)`（同一个对象同一个 id，但跨进程不复用；OK，因为 plugin 名总是字符串）
  - `Symbol.dispose` → 用 `Disposer` 协议 + `__disposer__` 协议
  - `WeakRef` → `weakref.ref`
  - `AbortController` → `asyncio.Event` + 标识
  - `EventEmitter` → 自实现 `EventEmitter` class，listener list 持弱引用
  - `Disposable` / `Mixin.dispose` → 协议化
  - `Promise<T>` → `Awaitable[T]` / `AsyncIterator[T]`
  - `TaskGroup` → `asyncio.TaskGroup`（3.11+）
  - `AsyncLocalStorage` → `contextvars.ContextVar`
  - tsconfig `strict` → pyright strict + dataclass(frozen=True) where possible

- [ ] **Step 3: 把 src/taiyi_agent/.../cordis/{__init__,context,disposer,event,loader,plugin,registry,service}.py 搬过来（已是 Python MVP 状态，作为起点）**

- [ ] **Step 4: 写 conftest.py**
  - 提供 `make_ctx()` fixture：new `Context()`、`ctx.on('dispose', lambda: ...)` 清理

- [ ] **Step 5: 注册到根 workspace**
  - 在 `pyproject.toml` 的 `[tool.uv.workspace] members` 加 `"vendor/*"`
  - `[tool.uv.sources]` 加 `taiyi-cordis = { workspace = true }`
  - `[project] dependencies` 加 `taiyi-cordis`
  - `uv sync` 验证

- [ ] **Step 6: Commit**
  - `git add vendor/cordis/ pyproject.toml`
  - `git commit -m "feat(vendor): scaffold taiyi-cordis"`

### Task 1.2: vendor/cordis — `Context` 实现（对齐 `context.ts` 146 LOC）

**Upstream:** `~/deepseek-harness/vendor/cordis/src/context.ts`
**Files:**
- Modify: `vendor/cordis/src/cordis/context.py`
- Create: `vendor/cordis/tests/specs/test_context.py`

- [ ] **Step 1: 写失败测试**
  - `test_ctx_provide_and_inject`：`ctx.provide('foo', 1)` + `ctx.inject('foo')` → 1
  - `test_ctx_inject_missing_raises`：`ctx.inject('missing')` → `KeyError`
  - `test_ctx_inject_with_default`：default 返回
  - `test_ctx_dispose_lifecycle`：ctx.dispose() 后 provide 抛 `RuntimeError`
  - `test_ctx_isolate_isolates_state`：`ctx.isolate('x', lambda c: c.provide('foo', 1))`，父 ctx.inject('foo') 仍 None
  - `test_ctx_fork_returns_child`：child 提供不污染 parent
  - `test_ctx_nearest`：`with ctx.scope('x'): ctx.inject('foo')` 取最近

- [ ] **Step 2: 运行测试确认 red**
  - `uv run pytest vendor/cordis/tests/specs/test_context.py -v`
  - Expected: FAIL（function/methods not yet defined）

- [ ] **Step 3: 实现**
  - 重写 `context.py` 对齐 `context.ts`：使用 `ContextVar` 提供 scope-like 行为 + isolate 的 fork
  - `Context.provide(key, value, *, dispose=None)`：注册到当前 ctx；记 disposer
  - `Context.inject(key, default=_MISSING)`：从 ctx → parent chain 找
  - `Context.isolate(label, fn)`：clone + with 临时 chain
  - `Context.fork()`：new child sharing root
  - `Context.dispose()`：逆序调用 disposer，标记 disposed
  - 用 `__aenter__` / `__aexit__` 支持 `async with ctx.scope(...)`

- [ ] **Step 4: 运行测试确认 green**
  - `uv run pytest vendor/cordis/tests/specs/test_context.py -v --no-cov`
  - Expected: PASS

- [ ] **Step 5: 100% 覆盖该模块**
  - `uv run pytest vendor/cordis/tests/specs/test_context.py --cov=vendor/cordis/src/cordis/context --cov-report=term-missing`
  - Expected: 100%

- [ ] **Step 6: Commit**
  - `git add vendor/cordis/`
  - `git commit -m "feat(vendor/cordis): Context with isolate/fork"`

### Task 1.3: vendor/cordis — `Service` 实现（`service.ts` 115 LOC）

**Upstream:** `~/deepseek-harness/vendor/cordis/src/service.ts`
**Files:**
- Modify: `vendor/cordis/src/cordis/service.py`
- Create: `vendor/cordis/tests/specs/test_service.py`

- [ ] **Step 1: 失败测试**
  - `test_service_disposes_on_ctx_dispose`：ctx 释放时 service.dispose() 被调用
  - `test_service_disposes_in_reverse_order`：LIFO
  - `test_service_disposes_swallow_errors`：单个 disposer 抛错不阻塞其他
  - `test_service_with_config`：config 字段传给 ctor
  - `test_service_schema_validation`：schema 不匹配抛 `pydantic.ValidationError`

- [ ] **Step 2-3: 实现**
  - `Service.__init__(ctx, **config)` + `Service.config: BaseModel` class attr
  - `ctx.effect(disposer)`：注册 disposer；ctx.dispose() 时调用
  - LIFO 顺序用 list stack
  - 用 `try/except Exception as e: logger.exception(...)` swallow

- [ ] **Step 4: 100% 覆盖**
- [ ] **Step 5: Commit**

### Task 1.4: vendor/cordis — `Effect`（`utils.ts` 287 LOC 中 effect 部分）

**Upstream:** `~/deepseek-harness/vendor/cordis/src/utils.ts`
**Files:**
- Modify: `vendor/cordis/src/cordis/disposer.py`
- Create: `vendor/cordis/tests/specs/test_effect.py`

- [ ] **Step 1: 失败测试**
  - `test_effect_single_value`：`Effect.of(1)` dispose 返回 1
  - `test_effect_iterable`：`Effect.of([1,2,3])` 三个 disposer
  - `test_effect_async_iterable`：async iter
  - `test_effect_reverse_order`：[1,2,3] 逆序 dispose
  - `test_effect_dedup`：同 fn 不重复注册

- [ ] **Step 2-5: 实现 + Commit**

### Task 1.5: vendor/cordis — `Event` 五种 dispatch（`events.ts` 352 LOC）

**Upstream:** `~/deepseek-harness/vendor/cordis/src/events.ts`
**Files:**
- Modify: `vendor/cordis/src/cordis/event.py`
- Create: `vendor/cordis/tests/specs/test_event.py`

- [ ] **Step 1: 失败测试**（每个 dispatch 模式）
  - `test_emit_serial_await`：`ctx.emit('foo', 1)` 所有 listener await
  - `test_emit_bail_first_bail_stops`：`ctx.bail('foo', lambda: 'bail')` listener1 throw 后 listener2 不调用
  - `test_emit_parallel_concurrent`：所有 listener `asyncio.gather`
  - `test_emit_serial_serial`：await 链
  - `test_emit_waterfall`：每个 listener 调 `next()` 传值；不调 next 终止
  - `test_listener_priority`：`ctx.on('foo', fn, priority=10)` 先于 priority=1
  - `test_off_unsubscribe`
  - `test_await_event`：fire-and-await pattern

- [ ] **Step 2-5: 实现 + Commit**

### Task 1.6: vendor/cordis — `Fiber` 6 状态机（`fiber.ts` 754 LOC）

**Upstream:** `~/deepseek-harness/vendor/cordis/src/fiber.ts`
**Files:**
- Create: `vendor/cordis/src/cordis/fiber.py`
- Create: `vendor/cordis/tests/specs/test_fiber.py`

- [ ] **Step 1: 失败测试**
  - `test_fiber_pending_to_loading`：`await fiber.ready` → LOADING
  - `test_fiber_loading_to_active`：setup 完成
  - `test_fiber_dispose_to_unloading`：dispose 触发
  - `test_fiber_unloading_to_disposed`：cleanup 完
  - `test_fiber_failed_state`：setup 抛 → FAILED + 保留 error
  - `test_fiber_restart_from_failed`
  - `test_fiber_cascade_dispose`：child 自动 dispose

- [ ] **Step 2-5: 实现 + Commit**

### Task 1.7: vendor/cordis — `Registry` + `Reflect` + `Logger`（`registry.ts`/`reflect.ts`/`logger.ts`）

**Files:**
- Modify: `vendor/cordis/src/cordis/registry.py`
- Create: `vendor/cordis/src/cordis/reflect.py`
- Create: `vendor/cordis/src/cordis/logger.py`
- Create: `vendor/cordis/tests/specs/test_registry.py`
- Create: `vendor/cordis/tests/specs/test_reflect.py`
- Create: `vendor/cordis/tests/specs/test_logger.py`

- [ ] **Step 1-5: 每个子模块独立 TDD**
  - Registry：typed collection、`register/unregister/get/keys`、per-key schema
  - Reflect：`get_metadata/set_metadata` + key 映射
  - Logger：5 个 level、child logger、formatter 接口

- [ ] **Step 6: 整合到 `__init__.py` 公共 surface**
  ```python
  from .context import Context, Hook, hook, ready, dispose
  from .service import Service, ServiceConfig
  from .disposer import Disposer, DisposableMixin
  from .event import Event, EventOptions, DispatchMode, emit, bail, parallel, serial, waterfall
  from .fiber import Fiber, FiberState
  from .registry import Registry, RegistryService
  from .reflect import ReflectService, reflect_key
  from .logger import Logger, LoggerService, LogLevel
  from .plugin import plugin, Plugin, PluginOptions
  __all__ = [...]
  ```

- [ ] **Step 7: 跑全 cordis 测试**
  - `uv run pytest vendor/cordis/ --cov=vendor/cordis --cov-fail-under=100`
- [ ] **Step 8: Commit**
  - `git commit -m "feat(vendor/cordis): registry + reflect + logger + fiber"`

### Task 1.8: vendor/cordis — `Loader`（`context.ts` 中 loader 部分 + `mount()`）

**Files:**
- Modify: `vendor/cordis/src/cordis/loader.py`
- Create: `vendor/cordis/tests/specs/test_loader.py`

- [ ] **Step 1: 失败测试**
  - `test_load_dict_config`：dict → plugin tree
  - `test_load_yaml_config`：yaml → plugin tree
  - `test_mount_unknown_plugin_raises`
  - `test_mount_optional_disabled`
  - `test_dump_config_round_trip`：`ctx.dump_config()` → dict（不抛）
  - `test_bundle_merging`：Bundle A + Bundle B

- [ ] **Step 2-5: 实现 + Commit**

### Task 1.9: vendor/cordis — `plugin` 装饰器 + `Plugin` 协议（`context.ts` + ts decorator）

**Files:**
- Modify: `vendor/cordis/src/cordis/plugin.py`
- Create: `vendor/cordis/tests/specs/test_plugin.py`

- [ ] **Step 1: 失败测试**
  - `test_plugin_decorator_basic`：`@plugin async def setup(ctx, config)` 等价于 `Plugin(setup)`
  - `test_plugin_with_schema`：config schema 校验
  - `test_plugin_filter`：filter 字段在 ctx.inject 缺失时 raise

- [ ] **Step 2-5: 实现 + Commit**

### Task 1.10: vendor/cordis — invariant companion + 全包验证

**Files:**
- Create: `vendor/cordis/invariant/__init__.py`
- Create: `vendor/cordis/invariant/contract.md`

- [ ] **Step 1: invariant 暴露**
  - 每个 vendor 包都有 `./invariant` 子包
  - 重新导出关键类型 + contract.md（人类可读：cordis 提供的契约 surface）

- [ ] **Step 2: ruff + pyright + 100% coverage + 0 error**
  - `uv run ruff check vendor/cordis/`
  - `uv run pyright vendor/cordis/`
  - `uv run pytest vendor/cordis/ --cov=vendor/cordis --cov-fail-under=100`

- [ ] **Step 3: Commit**
  - `git commit -m "feat(vendor/cordis): invariant + 100% coverage"`

---

## Chunk 2: Vendor — cosmokit + schemastery

### Task 2.1: vendor/cosmokit（5 模块 / 477 LOC）

**Upstream:** `~/deepseek-harness/vendor/cosmokit/src/{array,types,misc,string,time,index}.ts`

**Files:**
- Create: `vendor/cosmokit/pyproject.toml`
- Create: `vendor/cosmokit/src/cosmokit/__init__.py`
- Create: `vendor/cosmokit/src/cosmokit/array.py`（`make_array`, `chunk`, `priority_queue`, `cartesian_product`）
- Create: `vendor/cosmokit/src/cosmokit/types.py`（`Dict`, `List`, `Awaitable`, `Await` 别名）
- Create: `vendor/cosmokit/src/cosmokit/misc.py`（`Random`, `observe`, `deep_equal`, `deep_merge`, `escape_regexp`）
- Create: `vendor/cosmokit/src/cosmokit/string.py`（`capitalize`, `snake_case`, `kebab_case`, `pad`, `truncate`）
- Create: `vendor/cosmokit/src/cosmokit/time.py`（`Time` class, `format_time`, `parse_time`）
- Create: `vendor/cosmokit/invariant/__init__.py`
- Create: `vendor/cosmokit/tests/specs/test_*.py`（每个模块一个测试文件）

- [ ] **Step 1: TDD 每个函数 + 100% 覆盖**
- [ ] **Step 2: 注册到 workspace + `uv sync`**
- [ ] **Step 3: Commit**

### Task 2.2: vendor/schemastery（1 文件 / 902 LOC）

**Upstream:** `~/deepseek-harness/vendor/schemastery/src/index.ts`

**Files:**
- Create: `vendor/schemastery/pyproject.toml`（depends: `pydantic>=2.6`）
- Create: `vendor/schemastery/src/schemastery/__init__.py`
- Create: `vendor/schemastery/src/schemastery/schema.py`
- Create: `vendor/schemastery/src/schemastery/types.py`（`object/union/array/string/number/boolean/const/natural/refinement`）
- Create: `vendor/schemastery/src/schemastery/dsl.py`
- Create: `vendor/schemastery/src/schemastery/error.py`
- Create: `vendor/schemastery/invariant/__init__.py`
- Create: `vendor/schemastery/tests/specs/test_schema.py`

- [ ] **Step 1: TDD Schema DSL**
  - `z.object({a: z.string()})` 构造 + 校验 dict
  - `z.union([z.string(), z.number()])`
  - `z.array(z.number())`
  - `z.refinement(z.string(), lambda v: len(v) > 0)`
  - `z.const('foo')`
  - `ValidationError` 类型 + message 格式
  - 100% 覆盖

- [ ] **Step 2: 注册 + 验证**
- [ ] **Step 3: Commit**

---

## Chunk 3: Vendor — loader + include + group

### Task 3.1: vendor/loader（7 文件 / 1137 LOC）

**Upstream:** `~/deepseek-harness/vendor/loader/src/{entry,group,interpolate,isolate,tree,index,loader}.ts`

**Files:**
- Create: `vendor/loader/pyproject.toml`（depends: `taiyi-cordis`, `taiyi-schemastery`, `pyyaml`）
- Create: `vendor/loader/src/loader/__init__.py`
- Create: `vendor/loader/src/loader/entry.py`（`Entry`, `EntryOptions`, `EntryGroup`, `EntryTree`）
- Create: `vendor/loader/src/loader/interpolate.py`（`${ENV}` / `${ctx.foo}` 替换）
- Create: `vendor/loader/src/loader/isolate.py`（scope-aware isolate）
- Create: `vendor/loader/src/loader/module_loader.py`（`ModuleLoader.from_internal()`）
- Create: `vendor/loader/invariant/__init__.py`
- Create: `vendor/loader/tests/specs/test_entry.py`
- Create: `vendor/loader/tests/specs/test_tree.py`
- Create: `vendor/loader/tests/specs/test_interpolate.py`

- [ ] **Step 1: TDD Entry 数据结构**
  - `Entry(id, name, config, disabled, inject, ...)`
  - `EntryGroup(key, entries)`
  - `EntryTree` parent/children 树 + 索引
- [ ] **Step 2: TDD interpolate（env + ctx + nested）**
- [ ] **Step 3: TDD isolate + ModuleLoader**
- [ ] **Step 4: 100% 覆盖**
- [ ] **Step 5: Commit**

### Task 3.2: vendor/include（1 文件 / 377 LOC）

**Upstream:** `~/deepseek-harness/vendor/include/src/index.ts`

**Files:**
- Create: `vendor/include/pyproject.toml`（depends: `taiyi-cordis`, `taiyi-loader`, `taiyi-schemastery`, `pyyaml`）
- Create: `vendor/include/src/include/__init__.py`
- Create: `vendor/include/src/include/service.py`（`Include` Service：`add_entries`, `apply`, `dispose`）
- Create: `vendor/include/src/include/patch.py`（`PatchOptions`, `apply_entry_patches(data, patches, warn)` 纯函数）
- Create: `vendor/include/src/include/js_expr.py`（`JsExpr` 类 + `eval(expr, scope)` 求值；`!!js` 标记处理）
- Create: `vendor/include/invariant/__init__.py`
- Create: `vendor/include/tests/specs/test_patch.py`
- Create: `vendor/include/tests/specs/test_js_expr.py`

- [ ] **Step 1: TDD `apply_entry_patches`（spec §3 全部 6 操作）**
  - `insert` 顶层 append + 立即建索引
  - `insert` 带 id target 是 group → 推入 target.config
  - `id + config` 整替换（不深 merge）
  - `id + name` 不匹配 → warn-skip
  - `id + disabled: !!js <bool>` 删除语义
  - 其他字段直接赋值
  - 返回 detached `EntryOptions[]`（deepcopy 隔离 mutation）
- [ ] **Step 2: TDD `JsExpr` 求值（注入 `ctx`/`dshHomePath`/`process` scope）**
- [ ] **Step 3: 100% 覆盖**
- [ ] **Step 4: Commit**

### Task 3.3: vendor/group（1 文件 / 3 LOC，但语义复杂）

**Upstream:** `~/deepseek-harness/vendor/group/src/index.ts`

**Files:**
- Create: `vendor/group/pyproject.toml`（depends: `taiyi-cordis`, `taiyi-loader`）
- Create: `vendor/group/src/group/__init__.py`
- Create: `vendor/group/src/group/service.py`（`Group` Service：`EntryGroup.key` tree-carrier marker + transactional multi-entry update）
- Create: `vendor/group/invariant/__init__.py`
- Create: `vendor/group/tests/specs/test_group.py`

- [ ] **Step 1: TDD Group transactional update**
  - `group.update({key: [entry1, entry2]})` 事务性；rollback on fail
  - marker key 标识 group 载体
- [ ] **Step 2: 100% 覆盖**
- [ ] **Step 3: Commit**

---

## Chunk 4: Vendor — timer + hmr + logger-console

### Task 4.1: vendor/timer（1 文件 / 147 LOC）

**Upstream:** `~/deepseek-harness/vendor/timer/src/index.ts`

**Files:**
- Create: `vendor/timer/pyproject.toml`（depends: `taiyi-cordis`）
- Create: `vendor/timer/src/timer/__init__.py`
- Create: `vendor/timer/src/timer/service.py`（`TimerService.setTimeout/setInterval/timeout/throttle/debounce`）
- Create: `vendor/timer/invariant/__init__.py`
- Create: `vendor/timer/tests/specs/test_timer.py`

- [ ] **Step 1: TDD TimerService**
  - `setTimeout(fn, ms, args)` 返回 cancel handle
  - `setInterval(fn, ms)` 返回 cancel handle
  - `throttle(fn, ms)` 头一次立即 + 间隔内只一次
  - `debounce(fn, ms)` 间隔内合并
  - `timeout(promise, ms)` 超时抛 `TimeoutError`
- [ ] **Step 2: 100% 覆盖**
- [ ] **Step 3: Commit**

### Task 4.2: vendor/hmr（2 文件 / 612 LOC）

**Upstream:** `~/deepseek-harness/vendor/hmr/src/{service,index}.ts`

**Files:**
- Create: `vendor/hmr/pyproject.toml`（depends: `taiyi-cordis`, `watchfiles`（替代 chokidar））
- Create: `vendor/hmr/src/hmr/__init__.py`
- Create: `vendor/hmr/src/hmr/service.py`（`Hmr` Service + `register_config(filename)`）
- Create: `vendor/hmr/invariant/__init__.py`
- Create: `vendor/hmr/tests/specs/test_hmr.py`

- [ ] **Step 1: TDD Hmr 服务**
  - `register_config(path)` 监听文件变更
  - `hmr/change` 事件 fire
  - `hmr/reload` 事件 fire
  - watcher 生命周期随 ctx.dispose
- [ ] **Step 2: 100% 覆盖**
- [ ] **Step 3: Commit**

### Task 4.3: vendor/logger-console（3 文件 / 145 LOC）

**Upstream:** `~/deepseek-harness/vendor/logger-console/src/{exporter,format,index}.ts`

**Files:**
- Create: `vendor/logger-console/pyproject.toml`（depends: `taiyi-cordis`）
- Create: `vendor/logger-console/src/logger_console/__init__.py`
- Create: `vendor/logger-console/src/logger_console/exporter.py`（`ConsoleExporter`）
- Create: `vendor/logger-console/src/logger_console/format.py`（pprint 风格的 `util.inspect` formatter）
- Create: `vendor/logger-console/invariant/__init__.py`
- Create: `vendor/logger-console/tests/specs/test_exporter.py`

- [ ] **Step 1: TDD ConsoleExporter**
  - 输出到 stderr
  - 颜色化 level
  - inspect 风格对象展示
- [ ] **Step 2: 100% 覆盖**
- [ ] **Step 3: Commit**

---

## Chunk 5: runtime-diagnostics/invariants（1 包）

### Task 5.1: packages/runtime-diagnostics/invariants

**Files:**
- Create: `packages/runtime-diagnostics/invariants/pyproject.toml`（name=`taiyi-runtime-diagnostics-invariants`）
- Create: `packages/runtime-diagnostics/invariants/src/taiyi_runtime_diagnostics_invariants/__init__.py`
- Create: `packages/runtime-diagnostics/invariants/src/taiyi_runtime_diagnostics_invariants/plugin.py`（`invariant` re-export 入口：`@plugin async def setup(ctx, config)`）
- Create: `packages/runtime-diagnostics/invariants/tests/specs/test_invariants.py`

- [ ] **Step 1: 实现 invariant 包装器**
  - 每个 vendor 包都有 `invariant/__init__.py` 子包；本插件在 boot 时枚举已挂载 vendor 的 invariant 并 re-export 为 `ctx.invariants`
  - 提供 `assert_invariant(name, fn)` 测试 hook
- [ ] **Step 2: 100% 覆盖**
- [ ] **Step 3: 注册 + Commit**

---

## Chunk 6: core/scope（per-agent 隔离原语，1 包）

**Files:**
- Create: `packages/core/scope/pyproject.toml`（name=`taiyi-core-scope`，depends: `taiyi-cordis`）
- Create: `packages/core/scope/src/taiyi_core_scope/__init__.py`
- Create: `packages/core/scope/src/taiyi_core_scope/scope.py`（`Scope`, `ScopeKey`, `ScopeLayer`, `Scoped` 协议）
- Create: `packages/core/scope/src/taiyi_core_scope/carrier.py`（`is_scope_carrier`, `carrier_key_of`）
- Create: `packages/core/scope/src/taiyi_core_scope/entries.py`（`AnonymousEntries`, `NamedEntries`, `ScopedLayers`）
- Create: `packages/core/scope/src/taiyi_core_scope/plugin.py`（`bind_scope_parent`, `create_scope`, `scope_of`, `scope_target`）
- Create: `packages/core/scope/tests/specs/test_scope.py`

- [ ] **Step 1: TDD Scope 创建 + 嵌套**
  - `create_scope(ctx, key)` 返回 Scope
  - 嵌套：child scope 自动 dispose on parent
  - carrier-key 映射
- [ ] **Step 2: TDD entries + layers**
- [ ] **Step 3: 100% 覆盖 + Commit**

---

## Chunk 7: core/session（44 events + Session + SessionStore，1 包）

**Files:**
- Create: `packages/core/session/pyproject.toml`
- Create: `packages/core/session/src/taiyi_core_session/__init__.py`
- Create: `packages/core/session/src/taiyi_core_session/events.py`（`SessionEventType` 44 种常量 + `KNOWN_SESSION_EVENT_TYPES`）
- Create: `packages/core/session/src/taiyi_core_session/session.py`（`Session` frozen log + surface fold + request_header fold）
- Create: `packages/core/session/src/taiyi_core_session/store.py`（`SessionStore` Service：`create/prepare/enter/announce/get/list/flush/fork`）
- Create: `packages/core/session/src/taiyi_core_session/surface.py`（`SurfaceOp`, `SurfaceIntent`）
- Create: `packages/core/session/src/taiyi_core_session/turn.py`（`TurnEndReason`, `AgentCancelCause`, `SESSION_FORMAT_VERSION = 0`）
- Create: `packages/core/session/src/taiyi_core_session/plugin.py`
- Create: `packages/core/session/tests/specs/test_session.py`

- [ ] **Step 1: TDD SessionEventType 44 个常量**
  - 上游 `~/deepseek-harness/packages/core/session/src/events.ts` 列全；每个常量赋值给字符串
- [ ] **Step 2: TDD Session 不可变 log**
  - `Session.append(event_type, data)` → new Session
  - `Session.fold_surfaces()` / `Session.fold_request_headers()`
- [ ] **Step 3: TDD SessionStore**
  - `create()`, `prepare()`, `enter()`, `announce()`, `get()`, `list()`, `flush()`, `fork()`
- [ ] **Step 4: 100% 覆盖 + Commit**

---

## Chunk 8: core/system-prompt + core/tools + core/agent

### Task 8.1: core/system-prompt

**Files:**
- Create: `packages/core/system-prompt/pyproject.toml`
- Create: `packages/core/system-prompt/src/taiyi_core_system_prompt/__init__.py`
- Create: `packages/core/system-prompt/src/taiyi_core_system_prompt/service.py`（`SystemPrompt` Service：`PERSONA_SECTION`, `PERSONA_ORDER`, `TOOL_ORDER_REST`）
- Create: `packages/core/system-prompt/src/taiyi_core_system_prompt/render.py`（`render_prompt`, `render_context_snapshot`, `join_context_sections`）
- Create: `packages/core/system-prompt/src/taiyi_core_system_prompt/plugin.py`
- Create: `packages/core/system-prompt/tests/specs/test_system_prompt.py`

### Task 8.2: core/tools（5 阶段执行管线）

**Files:**
- Create: `packages/core/tools/pyproject.toml`
- Create: `packages/core/tools/src/taiyi_core_tools/__init__.py`
- Create: `packages/core/tools/src/taiyi_core_tools/runtime.py`（`ToolRuntime` Service）
- Create: `packages/core/tools/src/taiyi_core_tools/define.py`（`define_tool`）
- Create: `packages/core/tools/src/taiyi_core_tools/symbols.py`（`RUN_CODE_NAME`, `TOOL_RUNTIME_SCHEDULER`, `TOOL_ABORTED`, `TOOL_ABORTED_BEFORE_DISPATCH`, `ToolNotFoundError`, `ToolOutputError`）
- Create: `packages/core/tools/src/taiyi_core_tools/decision.py`（`PreToolDecision`, `PostToolDecision`, `ToolPresentationMode`）
- Create: `packages/core/tools/src/taiyi_core_tools/pipeline.py`（5 阶段：create / pre-execute (waterfall) / execute (around waterfall) / post-execute (waterfall) / finalize）
- Create: `packages/core/tools/src/taiyi_core_tools/plugin.py`
- Create: `packages/core/tools/tests/specs/test_tools.py`

### Task 8.3: core/agent

**Files:**
- Create: `packages/core/agent/pyproject.toml`
- Create: `packages/core/agent/src/taiyi_core_agent/__init__.py`
- Create: `packages/core/agent/src/taiyi_core_agent/registry.py`（`AgentRegistry` Service）
- Create: `packages/core/agent/src/taiyi_core_agent/carrier.py`（`agent_carrier`, `agent_events`）
- Create: `packages/core/agent/src/taiyi_core_agent/context.py`（`assemble_context_for`）
- Create: `packages/core/agent/src/taiyi_core_agent/event.py`（`emit_agent_event`）
- Create: `packages/core/agent/src/taiyi_core_agent/status.py`（`AgentStatus`）
- Create: `packages/core/agent/src/taiyi_core_agent/factory.py`（`AgentFactory`, `AgentHandle`, `CreateAgentOptions`, `ResumeAgentOptions`）
- Create: `packages/core/agent/src/taiyi_core_agent/plugin.py`
- Create: `packages/core/agent/tests/specs/test_agent.py`

- [ ] **Step 1-3: TDD 每个包 + 100% 覆盖**
- [ ] **Step 4: 注册 + Commit**

---

## Chunk 9: core/agent-default-model + agent-loop + agent-tool-presentation

### Task 9.1: core/agent-default-model

**Files:**
- Create: `packages/core/agent-default-model/pyproject.toml`
- Create: `packages/core/agent-default-model/src/taiyi_core_agent_default_model/__init__.py`
- Create: `packages/core/agent-default-model/src/taiyi_core_agent_default_model/config.py`（`AgentDefaultModelConfig` Service + `AGENT_DEFAULT_MODEL_SETTINGS_NAMESPACE = 'settingsagent-default'`）
- Create: `packages/core/agent-default-model/src/taiyi_core_agent_default_model/plugin.py`
- Create: `packages/core/agent-default-model/tests/specs/test_default_model.py`

### Task 9.2: core/agent-loop（**完整 turn/step 状态机**）

**Upstream:** `~/deepseek-harness/packages/core/agent-loop/src/index.ts`（~500 LOC）

**Files:**
- Create: `packages/core/agent-loop/pyproject.toml`
- Create: `packages/core/agent-loop/src/taiyi_core_agent_loop/__init__.py`
- Create: `packages/core/agent-loop/src/taiyi_core_agent_loop/loop.py`（`AgentLoop` Service 实现 `AgentFactory`）
- Create: `packages/core/agent-loop/src/taiyi_core_agent_loop/phase.py`（`Phase` tagged union：`idle`/`maintenance`/`running`，spec §5.1 完整字段）
- Create: `packages/core/agent-loop/src/taiyi_core_agent_loop/kick.py`（`async def kick()` while-turn 循环）
- Create: `packages/core/agent-loop/src/taiyi_core_agent_loop/turn.py`（`async def turn()`：turn/start event → decision 循环 → turn/end event）
- Create: `packages/core/agent-loop/src/taiyi_core_agent_loop/step.py`（`async def step()`）
- Create: `packages/core/agent-loop/src/taiyi_core_agent_loop/build_request.py`
- Create: `packages/core/agent-loop/src/taiyi_core_agent_loop/execute_tool_calls.py`
- Create: `packages/core/agent-loop/src/taiyi_core_agent_loop/constants.py`（`DEFAULT_MAX_PARALLEL_TOOL_CALLS = 10`, `CONFIGURED_AGENT_IDENTITIES_KEY`, `AGENT_LOOP_SETTINGS_NAMESPACE = 'settingsagent-loop'`）
- Create: `packages/core/agent-loop/src/taiyi_core_agent_loop/plugin.py`
- Create: `packages/core/agent-loop/tests/specs/test_agent_loop.py`

### Task 9.3: core/agent-tool-presentation

**Files:**
- Create: `packages/core/agent-tool-presentation/pyproject.toml`
- Create: `packages/core/agent-tool-presentation/src/taiyi_core_agent_tool_presentation/__init__.py`
- Create: `packages/core/agent-tool-presentation/src/taiyi_core_agent_tool_presentation/plugin.py`（`ctx.tools.present_as(mode)` function-plugin）
- Create: `packages/core/agent-tool-presentation/tests/specs/test_tool_presentation.py`

- [ ] **Step 1-3: TDD 每个包 + 100% 覆盖**
- [ ] **Step 4: 注册 + Commit**

---

## Chunk 10: llm/llm + token-meter + llm-retry

### Task 10.1: llm/llm（核心 vocabulary，~1500 LOC）

**Upstream:** `~/deepseek-harness/packages/llm/llm/src/{adapter,block,error,message,runtime,stream,types,usage,retry,token-meter}.ts`

**Files:**
- Create: `packages/llm/llm/pyproject.toml`
- Create: `packages/llm/llm/src/taiyi_llm/__init__.py`
- Create: `packages/llm/llm/src/taiyi_llm/types.py`（`Message`, `ContentBlock`, `GenerateOptions`, `CallId`, `Branding['SessionId']`）
- Create: `packages/llm/llm/src/taiyi_llm/stream.py`（`StreamChunk` 7 种：`block-start/text-delta/reasoning-delta/tool-call-delta/block-end/usage/finish`，`FinishReason`）
- Create: `packages/llm/llm/src/taiyi_llm/usage.py`（`TokenUsage` disjoint：`input/output/cacheRead/cacheWrite/reasoning`）
- Create: `packages/llm/llm/src/taiyi_llm/error.py`（`LlmError` 13 codes：`NO_ADAPTER/MISSING_CREDENTIAL/INVALID_CREDENTIAL_CODE/EMPTY_RESPONSE_CODE/RATE_LIMIT/SERVER/TIMEOUT/TRANSPORT/AUTH/CONTEXT_WINDOW_EXCEEDED/QUOTA_EXCEEDED/LLM_STREAM_IDLE_TIMEOUT/UNKNOWN`，`LlmFailure`）
- Create: `packages/llm/llm/src/taiyi_llm/adapter.py`（`LlmAdapter` abstract + `BlockAssembler`）
- Create: `packages/llm/llm/src/taiyi_llm/runtime.py`（`LlmRuntime` Service：`stream()`, `_adapter_stream()`, `for_adapter()` 剥离 `replay_state`）
- Create: `packages/llm/llm/src/taiyi_llm/retry.py`（`RetryPolicyConfig`）
- Create: `packages/llm/llm/src/taiyi_llm/plugin.py`
- Create: `packages/llm/llm/tests/specs/test_llm_runtime.py`

### Task 10.2: llm/token-meter

**Files:**
- Create: `packages/llm/token-meter/pyproject.toml`
- Create: `packages/llm/token-meter/src/taiyi_llm_token_meter/__init__.py`
- Create: `packages/llm/token-meter/src/taiyi_llm_token_meter/service.py`（`TokenMeter` Service + 3 个 projection 注册）
- Create: `packages/llm/token-meter/src/taiyi_llm_token_meter/plugin.py`
- Create: `packages/llm/token-meter/tests/specs/test_token_meter.py`

### Task 10.3: llm/llm-retry

**Files:**
- Create: `packages/llm/llm-retry/pyproject.toml`
- Create: `packages/llm/llm-retry/src/taiyi_llm_retry/__init__.py`
- Create: `packages/llm/llm-retry/src/taiyi_llm_retry/plugin.py`（function-plugin，监听 `agent/request-error` waterfall，指数退避重试）
- Create: `packages/llm/llm-retry/tests/specs/test_llm_retry.py`

- [ ] **Step 1-3: TDD + 100% 覆盖**
- [ ] **Step 4: Commit**

---

## Chunk 11: llm/llm-deepseek + llm-pi-ai

### Task 11.1: llm/llm-deepseek

**Upstream:** `~/deepseek-harness/packages/llm/llm-deepseek/src/{adapter,eventsource,sse,index}.ts`

**Files:**
- Create: `packages/llm/llm-deepseek/pyproject.toml`（depends: `httpx`）
- Create: `packages/llm/llm-deepseek/src/taiyi_llm_deepseek/__init__.py`
- Create: `packages/llm/llm-deepseek/src/taiyi_llm_deepseek/adapter.py`（`DeepSeekAdapter` + 单 route `'deepseek-official'`）
- Create: `packages/llm/llm-deepseek/src/taiyi_llm_deepseek/sse.py`（基于 httpx 的 SSE 解析）
- Create: `packages/llm/llm-deepseek/src/taiyi_llm_deepseek/plugin.py`（注册 adapter）
- Create: `packages/llm/llm-deepseek/tests/specs/test_deepseek_adapter.py`
- Create: `packages/llm/llm-deepseek/tests/specs/test_deepseek_sse.py`（用本地 mock SSE server）

### Task 11.2: llm/llm-pi-ai

**Upstream:** `~/deepseek-harness/packages/llm/llm-pi-ai/src/{adapter,routes/openai,anthropic,...}.ts`

**Files:**
- Create: `packages/llm/llm-pi-ai/pyproject.toml`
- Create: `packages/llm/llm-pi-ai/src/taiyi_llm_pi_ai/__init__.py`
- Create: `packages/llm/llm-pi-ai/src/taiyi_llm_pi_ai/adapter.py`（`PiAiAdapter` + 多 route + `supported_protocols = ['openai-completions', 'openai-responses', 'anthropic-messages']`）
- Create: `packages/llm/llm-pi-ai/src/taiyi_llm_pi_ai/routes/openai.py`
- Create: `packages/llm/llm-pi-ai/src/taiyi_llm_pi_ai/routes/anthropic.py`
- Create: `packages/llm/llm-pi-ai/src/taiyi_llm_pi_ai/plugin.py`
- Create: `packages/llm/llm-pi-ai/tests/specs/test_pi_ai_adapter.py`

- [ ] **Step 1-3: TDD + 100% 覆盖**
- [ ] **Step 4: Commit**

---

## Chunk 12: typert/* 4 包

### Task 12.1: typert/protocol

**Files:**
- Create: `packages/typert/protocol/pyproject.toml`
- Create: `packages/typert/protocol/src/taiyi_typert_protocol/__init__.py`（Typert IDL 解析：types/fields/inheritance）
- Create: `packages/typert/protocol/tests/specs/test_protocol.py`

### Task 12.2: typert/registry

**Files:**
- Create: `packages/typert/registry/pyproject.toml`
- Create: `packages/typert/registry/src/taiyi_typert_registry/__init__.py`（type registry + 版本管理）
- Create: `packages/typert/registry/tests/specs/test_registry.py`

### Task 12.3: typert/loader

**Files:**
- Create: `packages/typert/loader/pyproject.toml`
- Create: `packages/typert/loader/src/taiyi_typert_loader/__init__.py`（protocol → Python class 生成）
- Create: `packages/typert/loader/tests/specs/test_loader.py`

### Task 12.4: typert/generator

**Files:**
- Create: `packages/typert/generator/pyproject.toml`
- Create: `packages/typert/generator/src/taiyi_typert_generator/__init__.py`（host + client 代码生成）
- Create: `packages/typert/generator/tests/specs/test_generator.py`

- [ ] **Step 1-4: TDD + 100% 覆盖 + Commit**

---

## Chunk 13: api/* 2 包

### Task 13.1: api/gateway

**Files:**
- Create: `packages/api/gateway/pyproject.toml`
- Create: `packages/api/gateway/src/taiyi_api_gateway/__init__.py`（JSON-RPC + SSE mux；spec §7.1 完整 RPC 表：`session.list/create/prompt/history/cancel/fork/attachment/models/selectModel/rename/search/updateQueue`, `subagent.*`, `host.*`, `workspace.*`, `goal.*`, `skill.list`, `agentPreset.*`, `settings.*`, `credentials.*`, `llm.providers/models/discoverModels`）
- Create: `packages/api/gateway/src/taiyi_api_gateway/sse.py`
- Create: `packages/api/gateway/src/taiyi_api_gateway/rpc.py`
- Create: `packages/api/gateway/src/taiyi_api_gateway/plugin.py`
- Create: `packages/api/gateway/tests/specs/test_gateway.py`

### Task 13.2: api/remotes

**Files:**
- Create: `packages/api/remotes/pyproject.toml`
- Create: `packages/api/remotes/src/taiyi_api_remotes/__init__.py`（远端 typert client 注册）
- Create: `packages/api/remotes/tests/specs/test_remotes.py`

- [ ] **Step 1-2: TDD + 100% 覆盖 + Commit**

---

## Chunk 14: session 持久化骨架（7 包）

### Task 14.1-14.7: persistence / persistence-jsonl / projection / projection-cache / session-title / session-title-first-prompt-llm / session-checkpoint-policy

**For each of:**
- `packages/session/persistence`
- `packages/session/persistence-jsonl`
- `packages/session/projection`
- `packages/session/projection-cache`
- `packages/session/session-title`
- `packages/session/session-title-first-prompt-llm`
- `packages/session/session-checkpoint-policy`

**Files per pkg:**
- Create: `pyproject.toml`
- Create: `src/taiyi_session_<name>/__init__.py`
- Create: `src/taiyi_session_<name>/<core>.py`
- Create: `src/taiyi_session_<name>/plugin.py`
- Create: `tests/specs/test_<name>.py`

**Per-task TDD:**
- **persistence**：`SessionPersistence` Service 抽象：append / load / list
- **persistence-jsonl**：JSONL backend，写 `~/.taiyi/sessions/<sid>/events.jsonl`
- **projection**：`SessionProjection` 把 events 投影为可查询字段
- **projection-cache**：内存 + 持久化双层缓存
- **session-title**：`SessionTitle` Service：根据首条 user message 生成 title
- **session-title-first-prompt-llm**：title 由 LLM 生成
- **session-checkpoint-policy**：`SessionCheckpointPolicy`：定期快照

- [ ] **Step 1-7: 顺序 TDD + 100% 覆盖**
- [ ] **Step 8: 注册 + Commit**

---

## Chunk 15: session-query/* 4 包 + storage/* 4 包

### Task 15.1-15.4: session-query (4) — query / sqlite / tool-session-query

- **session-query**：SQL builder + 查询 DSL
- **session-query-sqlite**：sqlite backend（spec §9.1：`openAt: never`）
- **tool-session-query**：`@tool query_sessions(query)` 暴露给 agent

### Task 15.5-15.8: storage (4) — storage / storage-json / storage-sqlite / storage-domain

- **storage**：`Storage` Service 抽象
- **storage-json**：JSON 文件 backend
- **storage-sqlite**：sqlite backend
- **storage-domain**：domain-typed wrapper

**For each:** pyproject + src + plugin + tests/specs/test_*.py + 100% 覆盖

- [ ] **Step 1-8: TDD + 100% 覆盖 + Commit**

---

## Chunk 16: credentials/* 2 + settings/* 2 + identity/anonymous-user-id

### Task 16.1-16.5

- **credentials**：`Credentials` Service 抽象
- **credentials-local**：本地 keyring/file backend（用 `keyring` 或加密文件）
- **settings**：`Settings` Service + 命名空间
- **settings-file**：file backend
- **identity/anonymous-user-id**：UUIDv4 持久化到 `~/.taiyi/anonymous_id`

**Per-task:** pyproject + src + plugin + tests + 100% 覆盖 + Commit

---

## Chunk 17: interaction/* 5 包

### Task 17.1-17.5

- **commands**：`Command` 协议 + `ctx.command.register()` 注册 slash command
- **user-approval**：审批流程 + UI hook
- **user-questions**：问题收集 + 多选项
- **permission-presets**：权限预设（`safe`/`standard`/`dangerous`）
- **tool-ask-user**：agent 调 `ask_user(question, options)` 工具

**Per-task:** pyproject + src + plugin + tests + 100% 覆盖 + Commit

---

## Chunk 18: boot/* 2 + util/* 7

### Task 18.1-18.2: boot/app-boot + boot/cmdline

- **app-boot**：app lifecycle plugin，提供 `app_start`/`app_stop` 事件
- **cmdline**：解析 argv → Service handle

### Task 18.3-18.9: util 7 包

- **brand**：`Brand[T]` 新类型包装
- **home-paths**：`get_home_path()` → `~/.taiyi`
- **launch-environment**：`get_launch_env()` → dict
- **native-command**：wrapper for native binaries
- **output-retention**：限制大输出截断
- **timeout**：`async with timeout(secs): ...`
- **atomic-write**：tempfile + rename 的原子写

**Per-task:** pyproject + src + plugin (where applicable) + tests + 100% 覆盖 + Commit

---

## Chunk 19: bundle/base（cordis.patch.yml 451 行 + pyproject）

### Task 19.1: packages/bundle/base/cordis.patch.yml

**Files:**
- Create: `packages/bundle/base/pyproject.toml`（name=`taiyi-bundle-base`，depends: 所有 Phase 0 包）
- Create: `packages/bundle/base/cordis.yml`（base plugin 列表）
- Create: `packages/bundle/base/cordis.patch.yml`（**451 行逐行移植**，spec §9.1 列全 80+ insert/config 替换/`!!js`）

**移植步骤：**
- [ ] **Step 1: cat 上游 `~/deepseek-harness/packages/bundle/base/cordis.patch.yml`**
- [ ] **Step 2: 创建本地文件，1:1 复制（保留 `!!js` 标量、`insert`/`id`/`name`/`disabled` 字段顺序）**
- [ ] **Step 3: 验证 patch 语法（run vendor/include 自检）**
- [ ] **Step 4: Commit**

### Task 19.2: packages/bundle/base/plugin.py

**Files:**
- Create: `packages/bundle/base/src/taiyi_bundle_base/__init__.py`
- Create: `packages/bundle/base/src/taiyi_bundle_base/plugin.py`（re-export 所有 base plugins 的 mount 顺序）

- [ ] **Step 1: 实现 base plugin，引用 cordis.yml 中所有 entry**
- [ ] **Step 2: 100% 覆盖 + Commit**

---

## Chunk 20: host/* Phase 0（8 包）

### Task 20.1: host/webserver

**Files:**
- Create: `packages/host/webserver/pyproject.toml`（depends: `fastapi`, `uvicorn[standard]`）
- Create: `packages/host/webserver/src/taiyi_host_webserver/__init__.py`
- Create: `packages/host/webserver/src/taiyi_host_webserver/server.py`（`WebServer` Service + `register/register_upgrade/register_fallback/tap_index` + `--trusted-host` allow-list）
- Create: `packages/host/webserver/src/taiyi_host_webserver/plugin.py`
- Create: `packages/host/webserver/tests/specs/test_webserver.py`

### Task 20.2: host/apiproxy

**Files:**
- Create: `packages/host/apiproxy/pyproject.toml`
- Create: `packages/host/apiproxy/src/taiyi_host_apiproxy/__init__.py`
- Create: `packages/host/apiproxy/src/taiyi_host_apiproxy/routes/{events_mux,events_host,session_export,session_methods,subagent_methods,host_methods,workspace_methods,goal_methods,settings_methods,credentials_methods,llm_methods,skill_methods,agent_preset_methods}.py`
- Create: `packages/host/apiproxy/src/taiyi_host_apiproxy/plugin.py`
- Create: `packages/host/apiproxy/tests/specs/test_apiproxy_routes.py`

### Task 20.3: host/frontend-static

**Files:**
- Create: `packages/host/frontend-static/pyproject.toml`
- Create: `packages/host/frontend-static/src/taiyi_host_frontend_static/__init__.py`（`serve_static` + SPA fallback + `index_tap`）
- Create: `packages/host/frontend-static/src/taiyi_host_frontend_static/plugin.py`
- Create: `packages/host/frontend-static/tests/specs/test_frontend_static.py`

### Task 20.4-20.7: host/directory-picker × 4

- **directory-picker**：抽象 picker Service
- **directory-picker-browse**：browser-side picker（API 端点）
- **directory-picker-native**：OS native dialog（PyQt? tkinter? Phase 0 用 stub 标记 TODO）
- **directory-picker-auto**：auto-select browse/native

**Per-task:** pyproject + src + plugin + tests + 100% 覆盖

### Task 20.8: host/plugin-inventory

**Files:**
- Create: `packages/host/plugin-inventory/pyproject.toml`
- Create: `packages/host/plugin-inventory/src/taiyi_host_plugin_inventory/__init__.py`（typert host + remote-client）
- Create: `packages/host/plugin-inventory/tests/specs/test_plugin_inventory.py`

- [ ] **Step 1-8: TDD + 100% 覆盖 + Commit**

---

## Chunk 21: src/taiyi_agent/{cli, profile_boot, process_shutdown, __main__} + profiles/{base,web,headless}

### Task 21.1: src/taiyi_agent/cli.py

**Upstream:** `~/deepseek-harness/apps/cli/src/cli.ts`

**Files:**
- Modify: `src/taiyi_agent/cli.py`（spec §4 完整 CLI 流程：`--profile/--patch/--dump-config/--dump-default-config/web alias`）
- Create: `src/taiyi_agent/__main__.py`（`python -m taiyi_agent`）
- Create: `tests/test_cli.py`（spec §15 验证项 8）

### Task 21.2: src/taiyi_agent/profile_boot.py

**Upstream:** `~/deepseek-harness/apps/cli/src/profile-boot.ts`

**Files:**
- Create: `src/taiyi_agent/profile_boot.py`（`compose_profile`, `boot()`；spec §4 步骤 2-6 全部）
- Create: `tests/test_profile_boot.py`

### Task 21.3: src/taiyi_agent/process_shutdown.py

**Files:**
- Create: `src/taiyi_agent/process_shutdown.py`（SIGTERM(0)/SIGINT(130) + uncaught → exit 1）
- Create: `tests/test_process_shutdown.py`

### Task 21.4: profiles/{base,web,headless}/

**For each profile:**
- `package.json`（保留上游格式，Python 用 `pyproject` 字段等价）
- `cordis.yml`（plugin 列表）
- `cordis.patch.yml`（覆盖层）

- **profiles/base/**：base 必需 plugins
- **profiles/web/**：web bundle + 客户端 host plugins（Phase 0 用占位 SPA shell，Phase 3 替换为完整 SPA）
- **profiles/headless/**：headless runner plugins

### Task 21.5: src/taiyi_agent/profiles.py（auto-init 模板）

**Files:**
- Modify: `src/taiyi_agent/profiles.py`（`prepare_profile(name)`：自动 init `profiles/<name>/{package.json,cordis.yml,cordis.patch.yml}`）

- [ ] **Step 1-5: TDD + 100% 覆盖 + Commit**

---

## Chunk 22: scripts/verify_*.py（~28 个脚本）

### Task 22.1-22.28: 每个 verify 脚本

**For each of:**
`verify_hygiene`, `verify_cordis_config`, `verify_vendored_links`, `verify_md_wrap`, `verify_md_links`, `verify_doc_site_fragments`, `verify_public_repository_links`, `verify_doc_refs`, `verify_package_paths`, `verify_taiyi_package_licenses`, `verify_config_source_ownership`, `verify_package_invariants`, `verify_built_package_invariants`, `verify_package_readme_model_experience`, `verify_mermaid`, `verify_agent_note_classification`, `verify_agent_note_format`, `verify_archived_agent_notes`, `verify_translation_pairing`, `verify_translation_prompt`, `verify_doc_budgets`, `verify_runtime_closure`

**Files per script:**
- Create: `scripts/verify_<name>.py`（入口 `main()` 返回 0/非 0；CLI 直接 `python -m scripts.verify_<name>`）
- Create: `scripts/tests/specs/test_verify_<name>.py`（用临时 fixture 验证检测对错）

**实现策略：**
- 每个脚本对应上游 `~/deepseek-harness/scripts/verify-*` 同名 .ts
- 对应关系见 spec §11 表格

- [ ] **Step 1-28: TDD + 100% 覆盖 + Commit**

---

## Chunk 23: scripts/gen_*.py（~11 个脚本）

### Task 23.1-23.11

`gen_module_graph`, `gen_persistence_catalog`, `gen_tool_catalog`, `gen_config_catalog`, `gen_doc_graphs`, `gen_scoped_events`, `gen_third_party_notices`, `gen_client_catalog`, `gen_cordis_catalog`, `gen_cordis_api`, `gen_cordis_inspect_catalog`, `gen_translation_brief`

- [ ] **Step 1-11: TDD + 100% 覆盖 + Commit**

---

## Chunk 24: scripts/run_gates + run_ruff + lefthook/pyright/ruff/pytest config

### Task 24.1: scripts/run_gates.py

**Files:**
- Create: `scripts/run_gates.py`（spec §11：`check-all`/`ci-primary`/`ci-*` 一站式入口）
- Create: `scripts/tests/specs/test_run_gates.py`

### Task 24.2: scripts/run_ruff.py

**Files:**
- Create: `scripts/run_ruff.py`（替代 `run-oxlint.ts`）
- Create: `scripts/tests/specs/test_run_ruff.py`

### Task 24.3: scripts/smoke_python_runtime.py

**Files:**
- Create: `scripts/smoke_python_runtime.py`（`uv sync` + 关键 import smoke）
- Create: `scripts/tests/specs/test_smoke.py`

### Task 24.4: 配置文件

**Files:**
- Modify: `pyproject.toml`（最终形态：`[project]` 全 Phase 0 deps + `[tool.uv.workspace]` 全 members + `[tool.uv.sources]` 全 sources + `[tool.ruff]` strict + `[project.scripts] taiyi = "taiyi_agent.cli:main"`）
- Create: `pyrightconfig.json`（strict + noUncheckedIndexedAccess + exactOptionalPropertyTypes）
- Modify: `.ruff.toml`（strict + 项目规则）
- Create: `pytest.ini`（5 lane marker + 100% coverage gate）
- Create: `lefthook.yml`（pre-commit：ruff + pyright + third-party）
- Create: `conftest.py`（workspace 根）
- Create: `scripts/cordis_config_files.py`、`scripts/package_graph.py`、`scripts/package_invariants.py`（helpers for verify_*.py）

- [ ] **Step 1-4: TDD + 100% 覆盖 + Commit**

---

## Chunk 25: Final verification（spec §15 全部 12 项）

### Task 25.1: 跑全 12 项验证

- [ ] **Step 1: `uv sync` 无错**
- [ ] **Step 2: `uv run ruff check .` 0 警告**
- [ ] **Step 3: `uv run pyright packages/` 0 错**
- [ ] **Step 4: `uv run pytest`（unit lane）全绿**
- [ ] **Step 5: `uv run pytest -m e2e --runxfail` 全绿**（若 e2e 测试已写）
- [ ] **Step 6: `uv run pytest --cov=packages --cov-fail-under=100`（per-file 100%）**
- [ ] **Step 7: `uv run python -m scripts.run_gates check-all` 全绿**
- [ ] **Step 8: `uv run taiyi --dump-config` 正确打印 composed tree**
- [ ] **Step 9: `uv run taiyi web` 启动 3080 端口**
- [ ] **Step 10: 浏览器 `http://127.0.0.1:3080/` → 发消息 → 收到流式回复 → session 持久化到 `~/.taiyi/sessions/`**
- [ ] **Step 11: `TAIYI_SNAPSHOT=replay pytest -m snapshot` 全绿**（若 snapshot 已写）
- [ ] **Step 12: `uv run pytest -m web` 全绿**（SPA dist 渲染）

### Task 25.2: 文档 + 收尾

- [ ] **Step 1: 更新 README.md（重写 Phase 0 描述）**
- [ ] **Step 2: `uv run python -m scripts.gen_third_party_notices` 生成 `THIRD_PARTY_NOTICES.md`**
- [ ] **Step 3: Commit + push**
- [ ] **Step 4: merge 工作分支**

---

## Verification（goal-backward）

按 spec §15 全 12 项 + 下列逐项 goal：

| Goal | 验证方式 | 通过条件 |
|---|---|---|
| vendor 完整 | `pytest vendor/ --cov=vendor --cov-fail-under=100` | 100% |
| core 完整 | `pytest packages/core/ --cov=packages/core --cov-fail-under=100` | 100% |
| llm 完整 | `pytest packages/llm/ --cov=packages/llm --cov-fail-under=100` | 100% |
| typert 完整 | `pytest packages/typert/ --cov=packages/typert --cov-fail-under=100` | 100% |
| api 完整 | `pytest packages/api/ --cov=packages/api --cov-fail-under=100` | 100% |
| session 持久化骨架 | e2e：创建 session → write → read back → title 自动生成 | 持久化 + title 通过 |
| session-query + storage | e2e：query 列出最近 10 sessions | OK |
| credentials + settings + identity | 单元：写读 + 默认 fallback | OK |
| interaction | 单元：commands 注册 + permission check | OK |
| boot + util | 单元：home-path/atomic-write/timeout | OK |
| bundle/base patch 合法 | `python -m scripts.verify_cordis_config` | OK |
| host/webserver + apiproxy | 集成：起 3080，curl `/api/session.list` | 200 |
| profiles 模板 | `taiyi --dump-config --profile web` 打印 | OK |
| scripts/verify_*.py | 每个：3+ testcases（pass case + fail case + edge） | 100% |
| scripts/gen_*.py | 每个：snapshot 测试（输入 → 输出对照） | OK |
| 全栈门禁 | spec §15 全部 12 项 | 12/12 |

---

## 风险与决策日志

- **Wipe & rebuild**：默认按 spec §0 执行；若用户拒绝则 Task 0.1 Step 1 走 fallback（保留 MVP）
- **100% coverage gate**：per-file（非整体），上游一致；难达处用 `# pragma: no cover` + 在 PR 中标注
- **DSH_* env var**：spec §14 决策——用 `DSH_*` 兼容上游 `.env`；`TAIYI_*` 作为 alias
- **`lefthook` 性能**：用 ruff pre-commit（足够快）
- **`Promise`/`TaskGroup`/`AsyncLocalStorage` 等价**：见 Task 1.1 README 改写决策

---

**Plan complete. Ready to execute via superpowers:subagent-driven-development.**
