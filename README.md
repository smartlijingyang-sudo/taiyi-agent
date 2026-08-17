# 太一 · Taiyi Agent

> Python 复刻 [deepseek-harness](https://github.com/deepseek-ai/deepseek-harness) 的 MVP，贯彻「一切皆插件」。

**太一**，中国传统文化中化生万物的本原。本仓库是 deepseek-harness（`dsh`）的 Python 等价物：相同的心智模型（plugin / service / event / waterfall / fiber），Python 习惯表达。

## ✨ 特性

- **Plugin 框架**：`vendor/cordis` — async / Service / Effect / Event / waterfall
- **Core**：`sessions`、`agent`、`agent-loop`、`tools`、`system-prompt`、`scope`
- **LLM**：`llm`（seam） + `llm-deepseek`（OpenAI-compatible provider） + `llm-retry`（指数退避）
- **Bundles**：`bundle/base`（dsh-base 等价物） + `bundle/web-app`（dsh-web-app 等价物）
- **Host + Gateway + Web**：FastAPI host，`POST /v1/chat` 流式 NDJSON，vanilla HTML 聊天 UI
- **Mock fallback**：未配置 `DEEPSEEK_API_KEY` 时自动 mock，前端可即时演示

## 🚀 一条命令启动

```bash
uv sync                                    # 安装整个 workspace（17 包）
taiyi web                                  # 起 base + web-app bundle，监听 127.0.0.1:3080
# → 浏览器打开 http://127.0.0.1:3080/chat
```

可选：

```bash
taiyi web --host 0.0.0.0 --port 3080       # 自定义监听
taiyi chat "你好"                          # headless 单轮
taiyi --profile web-app --dump-config      # 打印插件树（对齐 dsh --dump-config）
```

## 🏗 架构

```
src/taiyi_agent/cli.py             CLI 入口（taiyi 命令）
vendor/
  ├ cosmokit/                      工具（priority queue / Random / logger）
  ├ schemastery/                   Schema 校验
  └ cordis/                        插件框架（Context, Service, Effect, Event）
packages/
  ├ core/
  │   ├ scope/                     per-agent 隔离原语
  │   ├ sessions/                  SessionEvent append-only log
  │   ├ system-prompt/             prompt 装配
  │   ├ tools/                     工具注册 + 守卫执行管线
  │   ├ agent/                     Agent 接口 + registry
  │   └ agent-loop/                默认 driver（turn/step 事件流）
  ├ llm/
  │   ├ llm/                       消息/流词汇 + adapter seam
  │   ├ llm-deepseek/              DeepSeek provider
  │   └ llm-retry/                 指数退避 provider 装饰器
  ├ host/webserver/                FastAPI host
  ├ api/                           gateway/BFF：/v1/chat, /v1/healthz
  ├ web/                           chat UI（vanilla HTML）
  └ bundle/
      ├ base/                      dsh-base 等价
      └ web-app/                   dsh-web-app 等价
```

### turn / step 事件流（对齐 dsh）

```
turn/start
  claim input + queued message
  assemble prompt + tools
  -> agent/pre-step (waterfall)
  step/start
    -> agent/request -> llm/stream -> assistant/chunk* -> assistant/message
    -> tool/call* -> tools/pre-execute -> tools/execute -> tools/post-execute -> tool/result*
  step/end
turn/end
```

### 一切皆插件

每个 `packages/<group>/<pkg>/` 是一个 workspace 成员，提供一个 `@plugin async def setup(ctx, config)` 入口。`bundle/*` 把多个 plugin 串成 mount 列表。Loader 从 YAML 或 Python dict 装配。

Web 端、API 网关、LLM provider 都是插件——换前端 / 换模型 / 加 sandbox 不需要改 host。

## 🔑 配置

```bash
export DEEPSEEK_API_KEY=sk-...                  # 真实模型
export DEEPSEEK_BASE_URL=https://api.deepseek.com
export TAIYI_LOG_LEVEL=info                     # trace|debug|info|warn|error
```

未配置 key 时自动 mock，前端聊天可即时演示。

## 🧪 验证

```bash
uv run taiyi --dump-config                      # 11 plugins 列表
uv run taiyi chat "hi"                          # 流式 mock 回复
uv run taiyi web --port 3081                    # 启动 → /chat, /v1/chat
curl http://127.0.0.1:3081/v1/healthz           # {"status":"ok"}
curl -N -X POST http://127.0.0.1:3081/v1/chat -d '{"message":"hi"}'   # NDJSON
```

## 🗺 Roadmap（明确不在 MVP 范围）

subagent / sandbox / LSP / MCP / ACP / compaction / skill / goal / workflow / jobs / todo / plan / preset / guard / hooks / session-query / settings / credentials / attachment / fs / terminal / code-runtime / shell / subprocess / e2b / feedback / context / identity / interaction / web / extension / storage / workspace

后续按 deepseek-harness 同名 1:1 添加，每个作为独立 PR + 独立包。

## 📜 License

MIT — 见 [LICENSE](./LICENSE)。

灵感来自：[deepseek-harness](https://github.com/deepseek-ai/deepseek-harness)（Apache-2.0 / MIT），由 DeepSeek AI 团队主导。