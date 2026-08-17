# Taiyi Agent — 1:1 复刻 deepseek-harness 设计 spec

**日期**：2026-08-17
**范围**：`/home/lichao/taiyi-agent` 全量复刻 `~/deepseek-harness`（dsh），除语言差异外 1:1 对齐
**上游版本锚定**：`~/deepseek-harness` 现状（2026-08-17 checkout）

---

## 0. 已敲定的范围决策

| 决策 | 选择 | 含义 |
|---|---|---|
| 范围 | **199 包全量 1:1**（Phase 0→5）| 不留 MVP 缺口 |
| 现存代码 | **全部清空，从零重建** | 保留 `pyproject.toml` 骨架、`src/taiyi_agent/cli.py`、`profiles/`、`vendor/*`（升级）|
| 前端 | **后端 1:1 + 完整 SPA 移植** | 35 个 client/ui-* 包用 Python 提供等价 host API；React SPA 通过 ts→js transpile 保留为 `apps/web/dist` 静态 bundle |
| 测试 | **1:1 复刻所有 5 个 lane** | unit + e2e + snapshot + perf + stress，pytest marker 区分 |

---

## 1. 顶层架构

```
/home/lichao/taiyi-agent/
├── pyproject.toml                 # workspace root (uv workspace)
├── uv.lock                        # 锁文件
├── src/taiyi_agent/               # 仅放 CLI 入口
│   ├── __init__.py
│   ├── cli.py                     # `taiyi` command: --profile/--patch/--dump-config/web 别名
│   ├── profile_boot.py            # composeProfile + boot() (移植自 apps/cli/src/profile-boot.ts)
│   ├── process_shutdown.py        # SIGTERM(0) / SIGINT(130) + uncaught → exit 1
│   └── __main__.py                # `python -m taiyi_agent`
├── vendor/                        # 9 个 vendored 包（与上游 1:1）
│   ├── cordis/                    # 框架核心：Context / Service / Effect / Event 5 种 dispatch / Fiber 6 状态
│   ├── cosmokit/                  # 工具（array/types/misc/string/time）
│   ├── schemastery/               # Schema DSL（z.object 等）+ ValidationError
│   ├── loader/                    # cordis-plugin-loader（Entry/EntryTree/Group/Isolate）
│   ├── include/                   # cordis-plugin-include（Include / applyEntryPatches / !!js 表达式）
│   ├── group/                     # cordis-plugin-group（entry-group LoadableEntry）
│   ├── timer/                     # cordis-plugin-timer（ctx.timer.setTimeout/interval）
│   ├── hmr/                       # cordis-plugin-hmr（chokidar + registerConfig）
│   └── logger-console/            # console exporter + util.inspect formatter
├── packages/
│   ├── runtime-diagnostics/invariants/     # 1 包：所有包都附 ./invariant
│   ├── core/                       # 8 包：scope / session / system-prompt / tools / agent / agent-default-model / agent-loop / agent-tool-presentation
│   ├── llm/                        # 5 包：llm / token-meter / llm-retry / llm-deepseek / llm-pi-ai
│   ├── typert/                     # 4 包：protocol / registry / loader / generator
│   ├── api/                        # 2 包：gateway / remotes
│   ├── e2b/                        # 3 包：e2b / fs-e2b / subprocess-e2b
│   ├── shell/                      # 9 包：shell / bash-local / pwsh-local / bash-sandbox / pwsh-sandbox / tool-bash / tool-bash-persistent / tool-pwsh / shell-env
│   ├── subprocess/                 # 2 包：subprocess / subprocess-local
│   ├── terminal/                   # 3 包：terminal / terminal-bash / tool-terminal
│   ├── code-runtime/               # 2 包：code-runtime / code-runtime-worker-thread
│   ├── sandbox/                    # 4 包：sandbox / sandbox-local / sandbox-policy / sandbox-windows-acl
│   ├── fs/                         # 6 包：fs / fs-local / fs-observation-policy / fs-sandbox / tool-fs / tool-fs-search / tool-str-replace-editor
│   ├── lsp/                        # 3 包：lsp / lsp-stdio / tool-lsp
│   ├── skill/                      # 4 包：skill / skill-filesystem / skill-badge / tool-skill
│   ├── web/                        # 6 包：web / web-fetch-http / web-search-deepseek / web-search-exa / web-search-perplexity / tool-web
│   ├── compaction/                 # 4 包：compaction / compaction-basic / compaction-tool-result-pruner / command-compact
│   ├── context/                    # 4 包：agent-instructions / time-context / tmux-context / session-reference
│   ├── goal/                       # 4 包：goal / goal-round-driver / tool-goal / command-goal
│   ├── schedule/                   # 1 包
│   ├── feedback/                   # 3 包：feedback / message-feedback / command-feedback
│   ├── identity/                   # 1 包：anonymous-user-id
│   ├── subagent/                   # 11 包：subagent + 4 provider + 4 tool
│   ├── jobs/                       # 3 包：jobs / jobs-local / tool-jobs
│   ├── workflow/                   # 4 包：workflow / workflow-worker-thread / tool-workflow / tool-ralph
│   ├── todo/                       # 1 包：tool-todo
│   ├── plan/                       # 1 包：plan-mode
│   ├── preset/                     # 2 包：agent-presets / persona
│   ├── guard/                      # 2 包：repeat-tool-reminder / timeout-policy
│   ├── bundle/                     # 3 包：base / headless / web-app（cordis.patch.yml）
│   ├── extensions/                 # 4 包：cordis-host-runner / cordis-client-runner / tool-cordis / ui-cordis
│   ├── hooks/                      # 3 包：hook-protocol / hooks-claude-code / hooks-codex
│   ├── session/                    # 13 包：persistence 系 (3) + projection 系 (2) + telemetry 系 (2) + title 系 (4) + checkpoint + log-export
│   ├── session-query/              # 4 包：session-query / session-query-sqlite / tool-session-query
│   ├── settings/                   # 2 包：settings / settings-file
│   ├── credentials/                # 2 包：credentials / credentials-local
│   ├── storage/                    # 4 包：storage / storage-json / storage-sqlite / storage-domain
│   ├── workspace/                  # 1 包
│   ├── sdk/                        # 3 包：protocol / server / client
│   ├── acp/                        # 1 包
│   ├── interaction/                # 5 包：commands / user-approval / user-questions / permission-presets / tool-ask-user
│   ├── boot/                       # 2 包：app-boot / cmdline
│   ├── host/                       # 9 包：webserver / apiproxy / plugin-inventory / frontend-static / directory-picker×4
│   ├── client/                     # 35 包：connection / hmr / locale / modules / runtime / schema-form / web-react / web / ui-slots / ui-attachment / ui-primitives / ui-layout / ui-sidebar / ui-conversation / ui-deliverables / ui-tool / ui-trajectory / ui-input-trigger / ui-commands / ui-model-selection / ui-message-feedback / ui-goal / ui-plan / ui-subagent / ui-jobs / ui-workflow-run / ui-user-questions / ui-skill / ui-agent-preset / ui-permission-presets / ui-theme / ui-settings / ui-settings-general / ui-settings-models / ui-settings-plugin-inventory / ui-settings-plugins / ui-workspace / ui-directory-picker-browse / ui-directory-picker-native / ui-cordis
│   ├── examples/                   # 3 包：agent-spine-demo / acp-demo / jsonrpc-demo
│   ├── test-support/               # 7 包：agent-loop-testkit / acp-snapshot / client-runtime / llm-mock-server / llm-replay / loader-smoke
│   └── util/                       # 7 包：brand / home-paths / launch-environment / native-command / output-retention / timeout / atomic-write
├── profiles/                       # 模板（web / headless，运行时初始化）
│   ├── web/{cordis.yml,cordis.patch.yml,package.json}
│   └── headless/{cordis.yml,cordis.patch.yml,package.json}
├── apps/
│   ├── cli/                        # taiyi 命令的入口（src/taiyi_agent/cli.py 已在 root，此处保留壳）
│   └── web/                        # SPA 静态资源（src/ + dist/，从上游 apps/web 移植）
├── examples/                       # 平行上游 examples/
├── docs/                           # 平移 docs/（中文 + 英文 + Mermaid + Agent Notes）
├── scripts/                        # 1:1 平移所有 verify-* / gen-* / run-gates / release-* / verify-hygiene 脚本
├── native/                         # 不做（Python 不需要 koffi；fs-local/sandbox-local/sandbox-windows-acl 用 Python ctypes/ctypes.windll 或 subprocess）
│
├── pyrightconfig.json              # strict + noUncheckedIndexedAccess + exactOptionalPropertyTypes
├── ruff.toml                       # 对应 oxlint + jscpd
├── pytest.ini                      # 5 lane marker + 100% coverage gate
├── lefthook.yml                    # pre-commit（lint+typecheck+third-party）
├── scripts/
│   ├── verify_hygiene.py           # 综合 hygiene 10-gate（对应 pnpm run hygiene）
│   ├── verify_cordis_config.py     # 验证 patch 语法
│   ├── verify_vendored_links.py    # uv.lock 中 vendor link: 校验
│   ├── verify_md_wrap.py
│   ├── verify_md_links.py
│   ├── verify_doc_site_fragments.py
│   ├── verify_public_repository_links.py
│   ├── verify_doc_refs.py
│   ├── verify_package_paths.py
│   ├── verify_taiyi_package_licenses.py     # MIT 校验
│   ├── verify_config_source_ownership.py    # 禁止 endpoint inline
│   ├── verify_package_invariants.py
│   ├── verify_built_package_invariants.py
│   ├── verify_package_readme_model_experience.py
│   ├── verify_mermaid.py
│   ├── verify_agent_note_classification.py
│   ├── verify_agent_note_format.py
│   ├── verify_archived_agent_notes.py
│   ├── verify_translation_pairing.py
│   ├── verify_translation_prompt.py
│   ├── verify_doc_budgets.py
│   ├── verify_runtime_closure.py
│   ├── verify_vendored_links.py
│   ├── gen_module_graph.py
│   ├── gen_persistence_catalog.py
│   ├── gen_tool_catalog.py
│   ├── gen_config_catalog.py
│   ├── gen_doc_graphs.py
│   ├── gen_scoped_events.py
│   ├── gen_third_party_notices.py
│   ├── gen_client_catalog.py
│   ├── gen_cordis_catalog.py
│   ├── gen_cordis_api.py
│   ├── gen_cordis_inspect_catalog.py
│   ├── gen_translation_brief.py
│   ├── publish_npm_baseline.py    # 不适用，但占位（always-skips）
│   ├── release/{bump.py,families.py,pack.py,process.py,publish.py,tarball.py,verify.py,verify_packed_install.py}
│   ├── smoke_python_runtime.py
│   ├── run_gates.py                # check:all/check:ci/check:ci:* 一站式入口
│   ├── run_ruff.py                 # 对应 run-oxlint.ts
│   ├── rescope_vendor.py
│   ├── cordis_config_files.py
│   ├── project_reference_faces.py
│   ├── package_graph.py
│   ├── package_invariants.py
│   ├── test_invariants.py
│   ├── test_fixture_cleanup.py
│   ├── repo_files.py
│   ├── client_bundle_purity.py
│   ├── client_tsconfig.py
│   ├── coverage_uncovered_locations.py
│   ├── doc_typecheck.py
│   ├── markdown.py
│   ├── jsdoc.py
│   ├── package_invariants.py
│   ├── publication_payload.py
│   ├── publint_all.py
│   ├── slot_walk.py
│   ├── cordis_walk.py
│   ├── ts_project.py
│   ├── translation_brief.py
│   ├── translation_pairing_git.py
│   ├── translation_pairing_merge.py
│   ├── translation_pairing_record.py
│   ├── translation_pairing.py
│   ├── translation_prompt.py
│   ├── type_equiv.py
│   ├── paired_markdown_derivatives.py
│   └── verify_export_jsdoc.py
├── lefthook.yml
├── .ruff.toml                      # strict + 项目级规则
├── pyrightconfig.json              # strict 模式
└── README.md / README.zh.md / CONTRIBUTING.* / FORK.md / BENCHMARK.md / THIRD_PARTY_NOTICES.md
```

---

## 2. Vendor 移植矩阵（cordis 系 = 整个 1:1 翻译）

| 上游 vendor 包 | Python 实现要点 |
|---|---|
| `cordis` | `Context`（Proxy + reflect + fiber 6 状态机）、`Service`（生命周期 + `Service.config` Schema）、`Effect`（单值/Iterable/AsyncIterable 三种形态，反向释放）、`Event`（emit / parallel / serial / bail / waterfall 五种 dispatch）、`Fiber`（PENDING/LOADING/ACTIVE/FAILED/UNLOADING/DISPOSED）、`RegistryService` / `ReflectService` / `EventsService` / `LoggerService`、`@plugin` 装饰器 |
| `cosmokit` | `array.ts` / `types.ts` / `misc.ts` / `string.ts` / `time.ts` 5 个模块的 Python 翻译 |
| `schemastery` | `Schema` 基类 + `z.object/union/array/string/number/boolean/const/natural` DSL + `ValidationError` + 完整 Object/Array/Union/Intersection/Refinement 推导 |
| `loader` | `Entry` / `EntryOptions` / `EntryGroup` / `EntryTree` / `isolate` / `interpolate` / `ModuleLoader.from_internal()` |
| `include` | `Include` Service + `entryListSchema`（YAML `!!js` 标量类型构造） + `applyEntryPatches` 纯函数 + `apply_patches` 队列 + atomic write |
| `group` | `Group`（`EntryGroup.key` tree-carrier marker + transactional multi-entry update） |
| `timer` | `TimerService` + `ctx.timer.setTimeout/interval/timeout/throttle/debounce` |
| `hmr` | `Hmr` Service + `register_config(filename)` + chokidar watcher + `hmr/change` `hmr/reload` 事件 |
| `logger-console` | `ConsoleExporter` + `util.inspect` 风格 formatter（pprint 替代） |

`cordis` 是整个复刻工作量最大的一块（≈2000 行 TS → Python），所有 plugin 都基于它。

---

## 3. Patch 语法（vendor/include 完整实现）

YAML 顶层是 `PatchOptions[]`：

```python
@dataclass
class PatchOptions:
    id: str | None
    insert: list[EntryOptions] | None
    name: str | None
    config: Any
    group: bool | None
    disabled: bool | None
    inject: list[str] | None
    intercept: Any
    isolate: Any
    # 其他任意字段透传

@dataclass
class EntryOptions:
    id: str
    name: str | None
    config: Any
    disabled: bool | None
    inject: list[str] | None
    # ...
```

`!!js` 标量 → 在 include 解析阶段构造 `JsExpr(string)`，在 `entry.activate()` 时调用 `eval(expr, {'ctx', 'dshHomePath', 'process'})` 求值。

操作语义（与上游严格一致）：

| 操作 | 行为 |
|---|---|
| `insert`（顶层）| append 到根 entry 列表，立即建索引以供后续 patch 引用 |
| `insert`（带 id）| target 必须是 group row；entries 推入 target.config |
| `id + config` | target.config **整替换**（不深 merge） |
| `id + name` | name 不匹配 → warn-skip（防上游 layer 换包） |
| `id + disabled: !!js <bool>` | 唯一「删除」语义 |
| 其他字段 | `target[k] = v` 直接赋值 |

`apply_entry_patches(data, patches, warn)` 返回 **detached** `EntryOptions[]`（`copy.deepcopy` 隔离 mutation）。

---

## 4. CLI 流程（`taiyi --profile <name>`）

```
1. parse_args(argv)
   ├─ --profile <name>           (root command)
   ├─ --patch <path>             (repeatable, collected into overlays)
   ├─ --dump-config              (print composed tree + exit)
   ├─ --dump-default-config      (skip user layer + overlays)
   └─ web                        (硬编码 alias for --profile web)

2. load_layered_env("taiyi")     (.env → process env)

3. compose_profile(name, patch_files)
   ├─ prepare_profile(name)              # 自动 init profiles/<name>/{package.json,cordis.yml,cordis.patch.yml}
   ├─ load_profile("taiyi", name)        # 解析 bundles 列表 + 加载每个 bundle 的 cordis.patch.yml
   ├─ load_optional_patches(home)        # ~/.taiyi/cordis.patch.yml
   ├─ load_overlay_patches([--patch])    # 多次 --patch 按 argv 顺序
   └─ append telemetry/agent-presets overlay（条件性）

4. install_signal_handlers()
   ├─ SIGTERM → shutdown(0)
   ├─ SIGINT  → shutdown(130)
   └─ uncaughtException / unhandledRejection → exit 1

5. boot("taiyi", root_config, composed_patches, host_prepare)
   ├─ new Context()
   ├─ ctx.provide("dshHomePath", dsh_home_path)  # !!js dshHomePath(...) 求值用
   ├─ ctx.plugin(Loader)
   ├─ host_prepare(ctx)                            # 提供 dshLaunchEnvironment / dshCmdline
   └─ mount_root_include(ctx, root_config, patches, base_url)

6. install hmr（if not disabled） + watch_user_patches（profile + home）

7. ctx.plugin loop（自动）完成 → wait SIGTERM/SIGINT
```

---

## 5. Core 包（packages/core/）1:1 对齐

| 包 | Python 关键导出 |
|---|---|
| `scope` | `bind_scope_parent` / `create_scope` / `scope_of` / `scope_target` / `is_scope_carrier` / `carrier_key_of` / `Scope` / `ScopeKey` / `Scoped` / `ScopeLayer` / `AnonymousEntries` / `NamedEntries` / `ScopedLayers` + `invariant` |
| `session` | `Session`（frozen log + surface fold + request_header fold） / `SessionStore`（Service：create/prepare/enter/announce/get/list/flush/fork） / `SessionEventType`（44 种 event 名） / `KNOWN_SESSION_EVENT_TYPES` / `SurfaceOp` / `SurfaceIntent` / `TurnEndReason` / `AgentCancelCause` / `SESSION_FORMAT_VERSION = 0` |
| `system-prompt` | `SystemPrompt`（Service）/ `PERSONA_SECTION = 'deployment:persona'` / `PERSONA_ORDER = 0` / `TOOL_ORDER_REST = '<unlisted-tools>'` / `render_prompt` / `render_context_snapshot` / `join_context_sections` |
| `tools` | `ToolRuntime`（Service）/ `define_tool` / `RUN_CODE_NAME` / `TOOL_RUNTIME_SCHEDULER`（ symbol / `TOOL_ABORTED` / `TOOL_ABORTED_BEFORE_DISPATCH` / `ToolNotFoundError` / `ToolOutputError` / `PreToolDecision` / `PostToolDecision` / `ToolPresentationMode` + 完整执行 5 阶段：create / pre-execute (waterfall) / execute (around waterfall) / post-execute (waterfall) / finalize |
| `agent` | `AgentRegistry`（Service）/ `agent_carrier` / `agent_events` / `assemble_context_for` / `emit_agent_event` / `AgentStatus` / `AgentFactory` / `AgentHandle` / `CreateAgentOptions` / `ResumeAgentOptions` |
| `agent-default-model` | `AgentDefaultModelConfig`（Service）/ `AGENT_DEFAULT_MODEL_SETTINGS_NAMESPACE = 'settingsagent-default'` |
| `agent-loop` | `AgentLoop`（Service，实现 `AgentFactory`）/ `DEFAULT_MAX_PARALLEL_TOOL_CALLS = 10` / `CONFIGURED_AGENT_IDENTITIES_KEY` / `AGENT_LOOP_SETTINGS_NAMESPACE = 'settingsagent-loop'` / **完整 turn/step 状态机**（同 `kick()`/`turn()`/`step()`/`build_request`/`execute_tool_calls`） |
| `agent-tool-presentation` | function-plugin：`ctx.tools.present_as(mode)` |

### 5.1 AgentLoop 状态机完整实现（与上游一致）

```python
Phase = (
    {'kind': 'idle', 'last_turn': int}
    | {'kind': 'maintenance', 'abort': AbortController, 'last_turn': int, 'wake_requested': bool}
    | {'kind': 'running', 'abort': AbortController, 'turn': int, 'step': int, 'wake_requested': bool}
)

async def kick(self):
    while await self.turn():
        pass

async def turn(self) -> bool:
    self.phase['turn'] += 1
    session.append('turn/start', {'turn': turn})
    target = 'next-turn'
    turn_ends = None
    while True:
        signal.throw_if_aborted()
        step = self.phase['step'] + 1
        decision = await pre_step(target, {'turn': turn, 'step': step})
        if decision.kind == 'reject':
            turn_ends = {'kind': 'blocked'}
            return False
        # ... (与上游逐行对齐)
    session.append('turn/end', {'turn': turn, 'reason': turn_ends})
```

---

## 6. LLM 包（packages/llm/）1:1 对齐

| 包 | Python 关键导出 |
|---|---|
| `llm` | `LlmRuntime`（Service）/ `LlmAdapter`（abstract）/ `BlockAssembler` / `LlmError` / `GenerateOptions` / `Message` / `ContentBlock` / `StreamChunk`（`block-start` / `text-delta` / `reasoning-delta` / `tool-call-delta` / `block-end` / `usage` / `finish` 7 种）/ `FinishReason` / `TokenUsage`（disjoint：input/output/cacheRead/cacheWrite/reasoning）/ `LlmFailure` / `RetryPolicyConfig` / `CallId` / `Branding['SessionId']` 等 |
| `token-meter` | `TokenMeter`（Service）/ 3 个 projection 注册 |
| `llm-retry` | function-plugin，监听 `agent/request-error` waterfall |
| `llm-deepseek` | `DeepSeekAdapter` + 单 route `'deepseek-official'` + `eventsource-parser` SSE（httpx） |
| `llm-pi-ai` | `PiAiAdapter` + 多 route（`openai-standard`/`anthropic-standard`/...）+ `supported_protocols = ['openai-completions', 'openai-responses', 'anthropic-messages']` |

### 6.1 LlmRuntime 流式请求路径（与上游一致）

```python
async def stream(self, options):
    async with ctx.waterfall('llm/stream', options, lambda: self._adapter_stream(options)) as stream:
        async for chunk in stream:
            yield chunk

async def _adapter_stream(self, options):
    registration = self.adapters.get(options.provider)  # exact match
    if not registration:
        raise LlmError('NO_ADAPTER', f'no adapter for "{options.provider}"')
    resolved = await resolve_call_for(registration, options, options.signal)
    yield from registration.adapter.stream(resolved)
```

`for_adapter` 剥离跨 adapter 的 `replay_state`（HMR 安全）。

---

## 7. Host 1:1（packages/host/）

| 包 | Python 关键导出 |
|---|---|
| `webserver` | `WebServer`（Service，`http.server` 或 `aiohttp`）+ `register(kind, path, handler)` / `register_upgrade(path, handler)` / `register_fallback(handler)` / `tap_index(transform)` + `--trusted-host` allow-list |
| `apiproxy` | API gateway host：`/api/events.mux` (SSE) / `/api/events.host` (SSE) / `/api/session.export` (ZIP) / `POST /api/<method>` (JSON-RPC)。完整 RPC 表：`session.list/create/prompt/history/cancel/fork/attachment/models/selectModel/rename/search/updateQueue`, `subagent.*`, `host.*`, `workspace.*`, `goal.*`, `skill.list`, `agentPreset.*`, `settings.*`, `credentials.*`, `llm.providers/models/discoverModels` |
| `plugin-inventory` | Typert host + remote-client |
| `frontend-static` | serve_static + fallback SPA serving + index_tap |
| `directory-picker` / `directory-picker-browse` / `directory-picker-native` / `directory-picker-auto` | 4 个 picker |
| `web-app/startup` | commander 解析 `--host` / `--port` / `--trusted-host`，提供 `webStartup` |

### 7.1 `/v1/chat` 不存在；web surface 是 JSON-RPC + SSE

- 浏览器信任围栏：`--trusted-host` 加入 allow-list（LAN IPv4 + extras）
- `POST /api/session.prompt` → 同步返回 sessionId；流通过 `/api/events.mux` SSE（`session/subscribed` / `assistant/message` / `tool/call` / `tool/result` / `turn/start` / `turn/end` 等帧）
- 所有 POST 必须 `Content-Type: application/json`（强制 CORS preflight）
- 业务错误用 `200 + err` 表达，不抛

---

## 8. Client 包 35 个（高工作量移植）

策略：每个 `packages/client/ui-*` 包写一个 Python 模块，提供**等价 host API**（即 SSE/JSON-RPC 路径不变）；React UI 代码用 Vite + ts→js transpile 保留为 `apps/web/dist/`。

```python
# packages/client/ui-conversation/taiyi_client_ui_conversation/__init__.py
class ConversationService(Service):
    """host-side: serve conversation frames via /api/events.mux.
    
    The browser-side React component reads from the SSE stream and
    renders the same Chat UI as dsh (transpiled to JS via apps/web/build.py).
    """
    @inject('agents')
    async def mount_sse_endpoint(self, request):
        return StreamingResponse(self._stream_sessions(), media_type='text/event-stream')
```

`apps/web/`：保留上游 `index.html` / `main.ts` / `vite.config.ts` + 所有 client modules 的 .ts 源代码；`apps/web/build.py` 调用 `node_modules/.bin/vite build` 一次（需要 npm + node，仅 build 时需要），产出的 `apps/web/dist/` 是静态资源。

测试 `apps/web/dist/` 也在 `apps/web/tests/` 下保留 .e2e.ts / .snapshot.ts。

---

## 9. Bundle（`packages/bundle/`）1:1

### 9.1 `base/cordis.patch.yml`（451 行，逐行移植）

完整内容在 `packages/bundle/base/cordis.patch.yml`，包含 80+ 个 insert / config 替换 / `!!js` 表达式：

- `timer` / `hmr` / `llm` / `session` / `typert` / `typert-loader` / `typert-gateway`
- `session-title` / `session-title-llm` / `user-questions` / `agent` / `agent-default-model`（默认 `provider: deepseek-official, model: deepseek-v4-flash`）
- `jobs` / `llm-retry` / `settings` / `credentials` / `llm-pi-ai`（dormant）
- `session-persistence-jsonl` / `attachment-local` / `session-query-sqlite`（`openAt: never`）/ `session-projection` / `session-telemetry-otel`
- `subprocess` / `sandbox` / `sandbox-policy` / `bash-sandbox` / `pwsh-sandbox` / `approval` / `permission` / `shell-env`
- `tool-bash` / `tool-pwsh` / `tool-jobs` / `fs-observation-policy` / `tool-fs` / `tool-fs-search` / `agent-instructions`
- `skill` / `skill-filesystem` / `skill-badge` / `tool-skill`
- `commands` / `command-feedback` / `goal` / `goal-round-driver` / `command-goal` / `plan-mode` / `token-meter`
- `compaction-basic` / `command-compact` / `subagent` / `subagent-spawn-in-process` / `subagent-fork-in-process` / `tool-subagent-control` / `tool-subagent-list-agents` / `tool-subagent` / `tool-subagent-fork` / `tool-subagent-report`
- `workflow-worker-thread` / `tool-workflow` / `timeout-policy` / `spill-local` / `spill-policy`
- `session-checkpoint-policy` / `tool-result-pruner` / `tool-todo` / `tool-goal` / `tool-ralph` / `tool-str-replace-editor` / `repeat-tool-reminder`
- `web` / `web-search-deepseek` / `tool-web`
- `tools` / `system-prompt` / `agent-loop` / `fs-sandbox` / `llm-deepseek`

### 9.2 `headless/cordis.patch.yml`

覆盖 `system-prompt.persona` / 禁 `hmr` / 设 `tools.mode = process.env.DSH_TOOLS_MODE` / insert `code-runtime` `headless-startup` `headless-runner`（`!!js ctx.headlessStartup.task`）。

### 9.3 `web-app/cordis.patch.yml`（420 行）

覆盖 base 的 `system-prompt` `hmr` `session-query-sqlite` `tools` + insert 80+ 个 host + browser roster（`webserver` / `web-runtime` / `web-startup` / `connection` / `modules` / `client-hmr` / 35 个 `ui-*` / `agent-presets`）+ disable 23 个工具行（迁到 preset）。

---

## 10. 测试（5 lane 1:1）

`pytest.ini`：

```ini
[pytest]
markers =
    unit: 默认（*.spec.py）
    e2e: *.e2e.py
    snapshot: *.snapshot.py
    perf: *.perf.py
    stress: *.stress.py
testpaths = packages apps examples
addopts = -ra --strict-markers
```

每个包：

```
packages/<group>/<pkg>/tests/
├── <feature>.spec.py            # unit (pytest default)
├── <feature>.e2e.py             # e2e (pytest -m e2e)
├── <feature>.snapshot.py        # snapshot (TAIYI_SNAPSHOT=record|replay|refresh)
├── <feature>.perf.py            # perf (pytest -m perf, 600s timeout)
└── <feature>.stress.py          # stress (pytest -m stress, opt-in)
```

`TAIYI_SNAPSHOT` 环境变量模拟上游 `DSH_SNAPSHOT`：

- `record`：capture 当前调用并存为 golden
- `replay`：对照 golden 重放
- `refresh`：force refresh + show diff

覆盖门：`pytest --cov=packages --cov-fail-under=100`（每包 100% per-file；`scripts/coverage_uncovered_locations.py` 输出未覆盖 path:line:col）。

---

## 11. Build/CI

| 上游 | Python 等价 |
|---|---|
| `pnpm run build` | `uv build` + `apps/web/build.py`（Vite build for SPA）|
| `pnpm run typecheck` | `pyright packages/` + `mypy packages/` |
| `pnpm run lint` | `ruff check .`（strict + 项目规则，对应 oxlint override） |
| `pnpm run lint:fix` | `ruff check --fix .` |
| `pnpm run duplication` | `pylint --disable=all --enable=duplicate-code` |
| `pnpm run test` | `pytest`（unit + coverage gate） |
| `pnpm run test:e2e` | `pytest -m e2e` |
| `pnpm run test:snapshot` | `pytest -m snapshot` |
| `pnpm run test:web` | `pytest -m web`（浏览器 + dist） |
| `pnpm run test:web:perf` | `pytest -m web_perf` |
| `pnpm run test:web:stress` | `pytest -m web_stress` |
| `pnpm run check:all` | `python -m scripts.run_gates check-all` |
| `pnpm run check:ci:linux-primary` | `python -m scripts.run_gates ci-primary` |
| `pnpm run hygiene` | `python -m scripts.verify_hygiene`（10-gate composite） |
| `pnpm run knip` | `vulture packages/ scripts/` |
| `pnpm run publint` | `python -m scripts.publint_all` |
| `pnpm run doc-typecheck` | `python -m scripts.doc_typecheck`（构建 host 后 fence-check） |
| `pnpm run verify-md-wrap` / `verify-md-links` / `verify-doc-site-fragments` / `verify-public-repository-links` / `verify-doc-refs` / `verify-package-paths` / `verify-dsh-package-licenses` / `verify-config-source-ownership` / `verify-package-invariants` / `verify-built-package-invariants` / `verify-package-readme-model-experience` / `verify-mermaid` / `verify-agent-note-classification` / `verify-agent-note-format` / `verify-archived-agent-notes` / `verify-type-equiv` / `verify-skill-invocation-metadata` / `verify-translation-prompt` / `verify-translation-pairing` / `verify-doc-budgets` / `verify-runtime-closure` / `verify-vendored-links` / `verify-cordis-config` / `verify-client-domain-graph` | 全部平移为 `scripts/verify_*.py` |
| `pnpm run gen-*` 系列 | 全部平移为 `scripts/gen_*.py` |
| `pnpm run release:*` | 全部平移为 `scripts/release/*.py` |
| `pnpm run dsh` | `taiyi`（`uv run taiyi`） |
| `pnpm run demo:*` | `python -m scripts.demo_*` |
| `pnpm run mock:llm` | `python -m scripts.mock_llm` |
| `pnpm run dev:web` | `python -m scripts.dev_web --poll`（watch-rebuild client HMR） |
| `postinstall` | `uv run lefthook install` |

---

## 12. 阶段交付（Phase 0→5）

每阶段**独立可工作**（能 `uv run taiyi web` 跑起来），后续 phase 叠加。

### Phase 0 — 框架 + 最简会话（P0，约 70 包）

- **vendor/* 全部 9 个**（cordis / cosmokit / schemastery / loader / include / group / timer / hmr / logger-console）
- **packages/runtime-diagnostics/invariants/**
- **packages/core/* 全部 8 个**（scope / session / system-prompt / tools / agent / agent-default-model / agent-loop / agent-tool-presentation）
- **packages/llm/* 全部 5 个**（llm / token-meter / llm-retry / llm-deepseek / llm-pi-ai）
- **packages/typert/* 全部 4 个**（protocol / registry / loader / generator）
- **packages/api/* 全部 2 个**（gateway / remotes）
- **packages/session/* 持久化骨架**（persistence / persistence-jsonl / projection / projection-cache / session-title / session-title-first-prompt-llm / session-checkpoint-policy）
- **packages/session-query/* 全部 4 个**
- **packages/storage/* 全部 4 个**（storage / storage-json / storage-sqlite / storage-domain）
- **packages/credentials/* 全部 2 个**
- **packages/settings/* 全部 2 个**
- **packages/identity/anonymous-user-id/**
- **packages/interaction/* 全部 5 个**（commands / user-approval / user-questions / permission-presets / tool-ask-user）
- **packages/boot/* 全部 2 个**（app-boot / cmdline）
- **packages/util/* 全部 7 个**（brand / home-paths / launch-environment / native-command / output-retention / timeout / atomic-write）
- **packages/bundle/base/**（完整 cordis.patch.yml）
- **packages/host/webserver** + **packages/host/apiproxy**（完整 RPC 表）
- **packages/host/frontend-static**（SPA shell）
- **packages/host/directory-picker***（4 个）+ **packages/host/plugin-inventory**
- **src/taiyi_agent/{cli.py, profile_boot.py, process_shutdown.py}**
- **profiles/{web,headless}/**
- **scripts/run_gates.py + verify_*.py + gen_*.py 全部**（对应上游所有）
- **lefthook.yml / pyrightconfig.json / ruff.toml / pytest.ini**

**验证**：Phase 0 末尾可以 `uv run taiyi web` → 浏览器看到 `http://127.0.0.1:3080/` → 完整 session 创建 + agent loop + DeepSeek 流式 + session 持久化 + title 自动 + checkpoint。

### Phase 1 — 工具能力（P1，约 35 包）

- **packages/feedback/* 全部 3 个**（feedback / message-feedback / command-feedback）
- **packages/compaction/* 全部 4 个**（compaction / compaction-basic / compaction-tool-result-pruner / command-compact）
- **packages/context/* 全部 4 个**（agent-instructions / time-context / tmux-context / session-reference）
- **packages/goal/* 全部 4 个**（goal / goal-round-driver / tool-goal / command-goal）
- **packages/schedule/**
- **packages/guard/* 全部 2 个**（repeat-tool-reminder / timeout-policy）
- **packages/preset/* 全部 2 个**（agent-presets / persona）
- **packages/plan/plan-mode/**
- **packages/todo/tool-todo/**
- **packages/shell/* 全部 9 个**（shell / bash-local / pwsh-local / bash-sandbox / pwsh-sandbox / tool-bash / tool-bash-persistent / tool-pwsh / shell-env）
- **packages/subprocess/* 全部 2 个**（subprocess / subprocess-local）
- **packages/terminal/* 全部 3 个**（terminal / terminal-bash / tool-terminal）
- **packages/code-runtime/* 全部 2 个**（code-runtime / code-runtime-worker-thread）
- **packages/sandbox/* 全部 4 个**（sandbox / sandbox-local / sandbox-policy / sandbox-windows-acl）
- **packages/fs/* 全部 6 个**（fs / fs-local / fs-observation-policy / fs-sandbox / tool-fs / tool-fs-search / tool-str-replace-editor）
- **packages/lsp/* 全部 3 个**（lsp / lsp-stdio / tool-lsp）
- **packages/skill/* 全部 4 个**（skill / skill-filesystem / skill-badge / tool-skill）
- **packages/web/* 全部 6 个**（web / web-fetch-http / web-search-deepseek / web-search-exa / web-search-perplexity / tool-web）
- **packages/e2b/* 全部 3 个**（e2b / fs-e2b / subprocess-e2b）

**验证**：可调 `bash` / `read_file` / `write_file` / `edit_file` / `grep` / `glob` / `web_search` / `skill` / `goal` / `compact` 等所有工具；session compaction + checkpoint + spill 全部工作。

### Phase 2 — 子代理与工作流（P2，约 20 包）

- **packages/subagent/* 全部 11 个**（subagent + 4 provider（in-process-driver / spawn / fork / dsh-sdk / codex / claude-code / acp）+ 3 tool）
- **packages/jobs/* 全部 3 个**（jobs / jobs-local / tool-jobs）
- **packages/workflow/* 全部 4 个**（workflow / workflow-worker-thread / tool-workflow / tool-ralph）
- **packages/session/telemetry* 全部**（session-telemetry / session-telemetry-otel）
- **packages/session/log-export**
- **packages/session/persistence-sqlite**

**验证**：subagent 委派 + workflow + jobs + telemetry OTLP 全部就绪。

### Phase 3 — 客户端 UI（P3，约 35 包 + apps/web）

- **packages/host/web-app/startup** + **packages/bundle/web-app/**（420 行 cordis.patch.yml）
- **packages/host/frontend-static**（完整 SPA serving）
- **packages/client/* 全部 35 个包**（每个 Python 模块 + React/TS UI）
- **packages/extensions/cordis-host-runner** + **cordis-client-runner** + **tool-cordis** + **ui-cordis**
- **packages/hooks/* 全部 3 个**（hook-protocol / hooks-claude-code / hooks-codex）
- **apps/web/**（完整 SPA from 上游）

**验证**：浏览器完整 UI（layout / sidebar / conversation / tool cards / settings / model selection / theme / locale / hmr / directory picker / subagent UI / workflow run / goals / plan / deliverables / trajectory）。

### Phase 4 — 扩展与生态（P4，约 25 包）

- **packages/acp/acp**（Agent Client Protocol server）
- **packages/sdk/* 全部 3 个**（protocol / server / client）
- **packages/examples/* 全部 3 个**（agent-spine-demo / acp-demo / jsonrpc-demo）
- **examples/**（平行上游所有 examples/）
- **packages/test-support/* 全部 7 个**（agent-loop-testkit / acp-snapshot / client-runtime / llm-mock-server / llm-replay / loader-smoke）
- **apps/cli/**（如需要壳）
- **native/**（不做，仅在 pyproject.toml 注明）

**验证**：ACP + SDK + test-support 全部就绪。

### Phase 5 — 收尾（P5，无新代码）

- **docs/**（平行上游所有 docs/）
- **THIRD_PARTY_NOTICES.md**（重生成）
- **README.md / README.zh.md / CONTRIBUTING.* / FORK.md / BENCHMARK.md**
- 跑全 10-gate hygiene：
  1. rescope_vendor ✅
  2. vulture ✅
  3. publint_all ✅
  4. check_workspace_constraints ✅
  5. verify_taiyi_package_licenses ✅
  6. verify_package_invariants ✅
  7. verify_built_package_invariants ✅
  8. verify_cordis_config ✅
  9. node_next_types → N/A（Python 没有）
  10. verify_runtime_closure ✅
- 跑全 100% per-file coverage gate
- 跑全 5 lane test（unit / e2e / snapshot / perf / stress）

---

## 13. 错误处理 & 边界

- **FATAL → exit 1**：`install_fail_loud` 监 `asyncio.CancelledError` 之外的所有未捕获
- **`LlmError`**：8 个 code：`NO_ADAPTER` / `MISSING_CREDENTIAL` / `INVALID_CREDENTIAL_CODE` / `EMPTY_RESPONSE_CODE` / `RATE_LIMIT` / `SERVER` / `TIMEOUT` / `TRANSPORT` / `AUTH` / `CONTEXT_WINDOW_EXCEEDED` / `QUOTA_EXCEEDED` / `LLM_STREAM_IDLE_TIMEOUT` / `UNKNOWN`
- **Patch warn-skip**：未知 `id` / name 不匹配 / target 不是 group → `logger.warn` + skip（不抛）
- **CLI shutdown**：`SIGTERM` exit 0 / `SIGINT` exit 130 / 业务错 exit 1
- **`TaskGroup`** 等价：`asyncio.TaskGroup`（3.11+）
- **`AsyncLocalStorage`** 等价：`contextvars.ContextVar`
- **`fetch`** 等价：`httpx.AsyncClient` + `aiohttp.web`（host）
- **`node-pty`** 等价：`ptyprocess` + `pyte`（terminal-bash）
- **`koffi` (Win32)**：不实现；`sandbox-windows-acl` 用 ctypes（受限功能）

---

## 14. 风险与开放问题

| 风险 | 缓解 |
|---|---|
| 工程量极大（199 包 × 实现 + 5 lane 测试 + 158 个 verify/gen script） | 分 5 phase，每 phase 独立可验证；用 subagent 并行 |
| cordis Python 端口有隐藏语义差（如 `Symbol.for` → `id()` 映射） | 在 vendor/cordis/README.md 列出每个改写决策；每个 vendor 包含 `invariant` companion |
| React SPA 移植（35 包 UI + Vite build） | 仅 Python 提供 host API；React 代码保留 ts 源，由 `apps/web/build.py` 一次性 Vite build 出 dist |
| 100% coverage gate 极难达成 | per-file 100%（非整体），对齐上游；用 `coverage_uncovered_locations.py` 暴露漏点 |
| `DSH_*` env var 命名（Python 用 `TAIYI_*` 还是保留 `DSH_*`）？ | **默认全量使用 `DSH_*`**（保持与上游兼容，让上游 .env 文件可移植）；`TAIYI_*` 仅作为 alias |
| `python -m scripts.run_gates` 性能 | 用 asyncio + 并行 |
| ~~lefthook pre-commit 性能~~ | 用 ruff（足够快）|

---

## 15. 验证清单（每个 phase 末尾必跑）

1. `uv sync` 无错
2. `uv run ruff check .` 0 警告
3. `uv run pyright packages/` 0 错
4. `uv run pytest`（unit lane）全绿
5. `uv run pytest -m e2e --runxfail` 全绿
6. `uv run pytest --cov=packages --cov-fail-under=100`（per-file 100%）
7. `uv run python -m scripts.run_gates check-all` 全绿
8. `uv run taiyi --dump-config` 正确打印 composed tree
9. `uv run taiyi web` 启动 3080 端口
10. 浏览器 `http://127.0.0.1:3080/` → 发消息 → 收到流式回复 → session 持久化到 `~/.taiyi/sessions/`
11. `TAIYI_SNAPSHOT=replay pytest -m snapshot` 全绿
12. `uv run pytest -m web` 全绿（含 SPA dist 渲染）

---

## 16. 下一步

进入 `writing-plans` 技能，按本 spec 生成 Phase 0 的详细实施 plan（含任务拆分、依赖图、goal-backward verification），再开 Phase 0 实施。