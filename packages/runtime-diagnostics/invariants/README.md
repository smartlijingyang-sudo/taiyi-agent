# taiyi-runtime-diagnostics-invariants

Package-owned runtime invariant registry. 1:1 Python port of
`@deepseek-ai/dsh-invariants`.

## Public surface

```python
from taiyi_runtime_diagnostics_invariants import (
    InvariantError,
    InvariantRegistry,
    InvariantConfig,
    compile_patterns,
    assert_invariant,
)
```

## Port decisions

| Upstream | Python |
|---|---|
| `InvariantRegistry extends Service` | `InvariantRegistry(Service)` (Pydantic-free config dataclass) |
| `Config = z.object({...})` (schemastery) | `InvariantConfig` dataclass validated in `__init__` |
| `compilePatterns(field, values)` | `compile_patterns(field, values)` returning `list[re.Pattern]` |
| `InvariantError extends Error { code='INVARIANT' }` | `InvariantError(Exception)` with class-level `code` |
| `selected(packageName)` private method | public `selected(package_name)` for testability |
| `register(packageName, installer)` returning effect disposer | `register(package_name, surface)` returning a sync disposer |
| `ctx.invariants` via Cordis service | `ctx.invariants` via `ctx.reflect.provide("invariants", registry)` |
| `@plugin setup(ctx)` companion | `@plugin(name="runtime-diagnostics-invariants")` |
| `declare module '@deepseek-ai/cordis'` augment | runtime reflection on `ctx.invariants` |
| `assert_invariant(name, fn)` test hook | `registry.assert_invariant(name, fn)` runs `fn()` immediately |
| Vendor `invariant.ts` barrels | vendor `invariant/__init__.py` modules imported by `list_installed_vendors()` |

## Behaviour

- The plugin walks every installed vendor's `invariant/__init__.py`
  companion and registers it as a surface under `ctx.invariants`.
- Each registration is gated by the configured `enabled` switch and the
  regex-based `package_allowlist` / `package_blocklist`.
- `InvariantRegistry.assert_invariant(name, fn)` records `fn` as the check
  for `name`, runs it once, and raises `InvariantError` on a falsy return.
- `InvariantRegistry.check(name)` re-runs a previously-asserted check.
- Vendors whose companion module is not installed in the current
  environment are silently skipped (no fail-fast on missing optional
  surfaces).