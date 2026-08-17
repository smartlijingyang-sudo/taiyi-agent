# taiyi-core-system-prompt

Registry for ordered system sections, dynamic context, tool schemas, and
prompt variables. 1:1 Python port of `@deepseek-ai/dsh-system-prompt`.

## Public surface

```python
from taiyi_core_system_prompt import (
    SystemPrompt, PromptLayer,
    PromptSection, PromptContext, AssembledSection, AssembledContext,
    PromptAssembly, ContextSnapshotSection, ToolProviderResult, ToolSchema,
    AssembleContext, Config,
    render_prompt, render_context_snapshot,
    render_context_sections, join_context_sections,
    validate_tool_order, order_tools,
    PERSONA_SECTION, PERSONA_ORDER, TOOL_ORDER_REST,
)
from taiyi_core_system_prompt.plugin import setup
```

## Port decisions

| Upstream | Python |
|---|---|
| `z` schema (schemastery) | `pydantic.BaseModel` (Config) |
| `structuredClone(tool.parameters)` | `copy.deepcopy(tool.parameters)` |
| `cordis.EventsService.waterfall(...)` (`Promise`-returning) | `cordis.EventsService.waterfall(...)`; result awaited when it is a coroutine |
| `cordis.Service` | `cordis.Service` |
| `z.object({...}).default(undefined)` (omission-preserving) | `field default=None` with explicit `None` preserved through `validate_tool_order` |
| `regex /^[a-z][a-z0-9_]*$/` | `re.compile(r"^[a-z][a-z0-9_]*$")` |
| `regex /^\{\{([^{}]*)\}\}/` | `re.compile(r"^\{\{([^{}]*)\}\}")` |
| `cordis.ScopedLayers` | `taiyi_core_scope.store.ScopedLayers` |
| `Scoped<SystemPrompt>` carrier for the assembly waterfall | `scope_target(self, scope)` from `taiyi_core_scope.scope` |
| `NamedEntries` | `taiyi_core_scope.store.NamedEntries` |
| `AnonymousEntries` | `taiyi_core_scope.store.AnonymousEntries` |
| `emit('system-prompt/change')` | `ctx.emit('system-prompt/change')` (sync fire-and-forget) |
| `typescript.set.call()` listener binding (no extra `this`) | Python listener receives the dispatch context as its first positional arg (`_bind_callbacks` prepends `this_arg`) — test listeners declare `def _listener(_self, assembly, ...)` |
| `@deepseek-ai/dsh-invariants` companion | Re-export barrel `taiyi_core_system_prompt.invariant` (no Python equivalent of `dsh-invariants`; companion is documentation-only) |
| `Persona section` default text | Empty string when `Config.persona` is `""` |

## Phase 0 scope

In-scope files (1:1 ports of upstream):
- `types.py` — ToolSchema, AssembleContext, PromptSection, PromptContext,
  AssembledSection, AssembledContext, ContextSnapshotSection,
  ToolProviderResult, PromptAssembly, Config (pydantic)
- `render.py` — constants, `render_prompt`, `render_context_snapshot`,
  `render_context_sections`, `join_context_sections`, `_interpolate`,
  `validate_tool_order`, `order_tools`, `compare_tool_names`
- `service.py` — PromptLayer + SystemPrompt Service
- `plugin.py` — cordis plugin entry

Out-of-scope for Phase 0 (deferred):
- The full `dsh-invariants` companion runtime in Python — only the barrel
  re-exporting the public surface is shipped.
