# include Public Contract

This document describes the public API contract that `include.invariant`
re-exports and that all consumers of the package can rely on.

## Overview

`taiyi-include` is a 1:1 Python port of
`@deepseek-ai/cordis-plugin-include` (upstream
`~/deepseek-harness/vendor/include/src/index.ts`). The package provides
a file-backed entry tree that reads a YAML or JSON config, applies a
configured patch list to every read + write, and persists edits through
an atomic tempfile + rename.

## Re-exports

The `include.invariant` companion submodule re-exports every public
name from `include`. Consumers should depend on this submodule to
decouple from the implementation layout.

| Name                  | Source                  | Purpose                                   |
| --------------------- | ----------------------- | ----------------------------------------- |
| `Include`             | `include.service`       | File-backed entry tree                    |
| `ConfigFileError`     | `include.service`       | Stage-tagged file error                   |
| `entry_list_schema`   | `include.service`       | YAML loader class for the `!!js` dialect  |
| `PatchOptions`        | `include.patch`         | TypedDict for a single patch              |
| `apply_entry_patches` | `include.patch`         | Pure patch application (detached output)  |
| `JsExpr`              | `include.js_expr`       | `!!js` marker node                        |
| `is_js_expr`          | `include.js_expr`       | Marker predicate                          |
| `evaluate`            | `include.js_expr`       | Scope-aware expression evaluator          |

## Patch semantics (1:1 to upstream)

The pure function `apply_entry_patches(data, patches, warn)` applies
patches in declaration order, indexing inserted rows so a later patch
in the same list can target them. The result is **always detached**
(deepcopy) — patching or mounting shared entry objects would bake
earlier values into the cached parse, so repeated application (config
hot-reloads) could never revert a removed or changed patch.

Operation summary:

1. `insert` (no id) → append to top-level data + index immediately.
2. `insert` (with id) → push into `target.config` (group required).
3. `id + config` → shallow replacement (no deep merge).
4. `id + name` mismatch → warn-skip.
5. `id + disabled: !!js <bool>` → direct field assignment; the Loader
   evaluates the `!!js` expression at entry activation time.
6. Other fields (`inject`, `intercept`, `isolate`, …) → direct assign.

## JsExpr semantics

`!!js <expr>` markers round-trip as `{ __jsExpr: <expr> }` dicts. The
runtime evaluates the expression against an injected scope that mirrors
upstream's `new Function('ctx', 'expr', 'with (ctx) { return eval(expr) }')`.
In Python this is implemented as:

- A `_ScopeProxy` wraps mapping values so JS-style attribute access
  (`process.platform`) works on Python dicts via attribute lookup.
- `evaluate(scope, expr)` compiles the source and runs it through
  Python's `eval` with a token shim (`===` → `==`, `!==` → `!=`).
- The expression must be Python-compatible (the upstream JS dialect
  is the source of truth for what the YAML tag round-trips; full JS
  expression evaluation requires a real JS engine, out of scope for
  this Python port).

## Lifecycle

- `Include.__init__(ctx, config)` validates the file extension and
  resolves `ctx.baseUrl + config.path` into an absolute filename.
- `Include.__service_init__` (equivalent to upstream's `[Service.init]`
  body) reads the file (or writes `config.initial` if missing), then
  emits `internal/update` with the patched data.
- `Include.enqueue(task)` serializes concurrent applies so two updates
  on the same tree can't race.
- `Include.dispose` releases pending tasks and cancels timers.
- `Include.write` schedules a debounced atomic write of the current
  root entry data.

## Coverage

The package ships with 148 tests covering all six patch operations,
the full JsExpr surface, and every Include lifecycle path. Source
coverage is 100% (branch + line).