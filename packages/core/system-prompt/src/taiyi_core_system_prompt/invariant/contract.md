# `taiyi_core_system_prompt` — Public API Contract

This file describes the contract surface for `taiyi_core_system_prompt`.
Consumers should import from `taiyi_core_system_prompt.invariant` (this
subpackage) rather than the implementation modules.

## Surface

### Constants (render.py)

| Symbol | Kind | Description |
|---|---|---|
| `PERSONA_SECTION` | str | `"deployment:persona"` — section name of the persona slot |
| `PERSONA_ORDER` | int | `0` — prompt order of the persona slot |
| `TOOL_ORDER_REST` | str | `"<unlisted-tools>"` — reserved marker in `Config.tool_order` |

### Render helpers (render.py)

| Symbol | Description |
|---|---|
| `render_prompt(assembly)` | Interpolate sections, drop empties, join with blank lines |
| `render_context_snapshot(assembly)` | Joined runtime-context snapshot |
| `render_context_sections(assembly)` | Per-context snapshot sections (filtered to non-empty) |
| `join_context_sections(sections)` | Join pre-rendered snapshot sections |

### Types (types.py)

| Symbol | Kind | Description |
|---|---|---|
| `ToolSchema` | class | Provider-facing tool schema (`name`, `description`, `parameters`) |
| `AssembleContext` | class | Per-assembly context (`scope`, `signal`) |
| `PromptSection` | class | Registry input — name, order, text, complete |
| `PromptContext` | class | Registry input — name, order, text |
| `AssembledSection` | class | Resolved section (name + text) |
| `AssembledContext` | class | Resolved context (name + text) |
| `ContextSnapshotSection` | class | Snapshot section returned by `render_context_sections` |
| `ToolProviderResult` | class | Tool provider return — schemas + knownNames |
| `PromptAssembly` | class | Composed model input |
| `Config` | pydantic | `include_harness_identity`, `include_runtime_context`, `persona`, `tool_order` |

### Service (service.py)

| Symbol | Description |
|---|---|
| `SystemPrompt(ctx, config)` | Registry Service |
| `SystemPrompt.section(section)` | Register a section in calling scope |
| `SystemPrompt.context(context)` | Register a context in calling scope |
| `SystemPrompt.suppress_runtime_context()` | Suppress runtime context in calling scope |
| `SystemPrompt.tools(provider)` | Register a tool-schema provider in calling scope |
| `SystemPrompt.variable(name, provider)` | Register a prompt variable in calling scope |
| `SystemPrompt.assemble(context)` | Build a `PromptAssembly` from global + scoped providers |
| `PromptLayer` | One scope's storage (sections, contexts, ...); reports `is_empty()` |

## Behavior

1. **Strict interpolation.** `{{name}}` references resolve against the
   `PromptAssembly.variables` map; malformed syntax (no matching `}}`),
   invalid names (regex `^[a-z][a-z0-9_]*$`), unregistered names, and
   `None`-valued variables all raise. A lone `{{` without a later `}}` is
   literal prose. Substituted values are not re-scanned.
2. **Whitespace-stable ordering.** Sections render in ascending `order`;
   tools render lex-ordered (or in `Config.tool_order` order with
   `<unlisted-tools>` insertion point).
3. **Scope hierarchy.** Scoped sections / variables shadow globals; with
   cascading parents, the nearest scope wins a name.
4. **`complete` semantics.** A `PromptSection {complete: true}` is restored
   after the waterfall as the sole prompt section. More than one
   effective complete section makes `assemble` fail.
5. **Tool-order validation.** `Config.tool_order` must contain
   `<unlisted-tools>` exactly once and may not list duplicate names.
   Unknown names fail at assembly (registered names are checked later
   because plugins have not loaded yet).
6. **Tool parameter isolation.** Each `assemble` deep-copies tool
   parameters (`copy.deepcopy`) so listener mutations cannot leak between
   assemblies.

## 1:1 port notes

| Upstream | Python |
|---|---|
| `z` schema (schemastery) | `pydantic.BaseModel` (Config) |
| `structuredClone(parameters)` | `copy.deepcopy` |
| Regex `^[a-z][a-z0-9_]*$` | `re.compile(r"^[a-z][a-z0-9_]*$")` |
| `<unlisted-tools>` rest marker | `TOOL_ORDER_REST` constant |
| `cordis.waterfall(...)` | `ctx.waterfall(...)`; result awaited if it is a coroutine |
| `cordis.emit('system-prompt/change')` | `ctx.emit('system-prompt/change')` |
| `ScopedLayers` | `taiyi_core_scope.store.ScopedLayers` |
| `cordis.Service` | `cordis.Service` |
