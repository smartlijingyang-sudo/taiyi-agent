# Taiyi-Agent · 设计稿

> **太一**，中国传统文化中化生万物的本原；taiyi-agent 是 deepseek-harness 的 Python MVP 复刻。
> 设计原则：**一切皆插件**。参考 [deepseek-harness AGENTS.md](https://github.com/deepseek-ai/deepseek-harness) 与其 `vendor/cordis` 的范式，但用 Python 习惯表达（`dataclass`、`Protocol`、`contextvars`、`async`）。

## 1. 范围（Lean MVP）

vendored 框架 + 7 个工作区包 + 2 个 bundle + 1 个 CLI host。能跑、能聊、能扩展。后续要加包（subagent / sandbox / LSP / MCP …）一律作为新插件。

| 层 | 路径 | 角色 | 备注 |
|---|---|---|---|
| vendor | `vendor/cosmokit` | 通用工具（priority queue, Random, makeArray, observe） | 类似 `@deepseek-ai/cosmokit` |
| vendor | `vendor/schemastery` | Schema 校验（dict → typed config） | 类似 `@deepseek-ai/schemastery` |
| vendor | `vendor/cordis` | 插件框架（Context, Service, Effect, Event, Registry, Plugin, Loader） | 类似 `@deepseek-ai/cordis` |
| core | `packages/core/scope` | per-agent 隔离注册原语 | `ctx.scope` |
| core | `packages/core/sessions` | SessionEvent append-only log + in-memory store | `ctx.sessions` |
| core | `packages/core/system-prompt` | prompt section + tool schema 装配 | `ctx.system_prompt` |
| core | `packages/core/tools` | 工具注册 + 守卫执行管线 | `ctx.tools` |
| core | `packages/core/agent` | Agent 接口、live registry、`agent/*` 事件 | `ctx.agents` |
| core | `packages/core/agent-loop` | 默认 driver 实现该接口 | `ctx.agent_loop` |
| llm | `packages/llm/llm` | 消息/流词汇 + adapter seam | `ctx.llm` |
| llm | `packages/llm/llm-deepseek` | DeepSeek provider（OpenAI-compatible HTTP） | |
| llm | `packages/llm/llm-retry` | 指数退避重试 provider 装饰器 | |
| host | `packages/host/webserver` | FastAPI host，绑定 127.0.0.1:3080 | |
| api | `packages/api` | gateway/BFF plugin：`POST /v1/chat` 流式 NDJSON | |
| web | `packages/web` | chat UI plugin：`/chat` vanilla HTML + 流式渲染 | |
| bundle | `packages/bundle/base` | dsh-base 等价物：mount core + llm + base 配置 | |
| bundle | `packages/bundle/web-app` | dsh-web-app 等价物：mount api + web | |
| CLI | `taiyi` | uv-managed workspace，entry point: `taiyi = "taiyi_agent.cli:main"` | |

## 2. 架构对齐

deepseek-harness 的「turn/step 事件流」在 Python 这边的映射：

```
turn/start
  claim next-step input + queued message
  assemble prompt sections + tool schemas
  -> agent/pre-step
  step/start
  -> agent/request -> llm/stream -> assistant/chunk* -> assistant/message
  tool/call* -> tools/pre-execute -> tools/execute -> tools/post-execute -> tool/result*
  step/end
turn/end
```

`turn/* / step/* / user/message / assistant/* / tool/*` 是 durable session event；其余是 live extension point。`agent/pre-step, agent/request, llm/stream, tools/*` 是 waterfall（监听器须调用 `next()` 让流往下走）。

## 3. 一条命令

```bash
uv sync                                    # 安装整个 workspace
taiyi web                                  # 起 base + web-app bundle，监听 127.0.0.1:3080
```

`taiyi web` 内部：
1. 解析 profile = `web-app`
2. 按 order mount：`base` bundle → `web-app` bundle → home `cordis.yml` → CLI `--patch` overlay
3. start FastAPI host
4. 暴露 `/chat`（UI）、`/v1/chat`（流式 NDJSON）、`/healthz`

`uv sync` 触发 `taiyi` 脚本注册 + 所有 workspace 链接；不需要手动 build。

## 4. 不在 MVP 范围（明确 YAGNI）

- subagent / sandbox / LSP / MCP / ACP / compaction / skill / goal / workflow / jobs / todo / plan / preset / guard / hooks / session-query / settings / credentials / attachment / fs / lsp / terminal / code-runtime / shell / subprocess / e2b / feedback / context / identity / interaction / web / extension / storage / workspace — 后续作为独立 PR。

## 5. 验收

- `uv sync` 无错
- `taiyi --profile base --dump-config` 打印插件树（对齐 dsh `--dump-config`）
- `taiyi web` 起服务
- 浏览器打开 `http://127.0.0.1:3080/chat`，输入消息，得到流式回复（用真实 DeepSeek key；无 key 时走 mock provider）
- `curl -N -X POST http://127.0.0.1:3080/v1/chat -d '{"message":"hi"}'` 返回 NDJSON 流