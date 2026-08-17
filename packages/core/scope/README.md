# taiyi-core-scope

Per-agent isolation primitive: mint a Cordis context that tags registrations
with an opaque identity and build routing-only event carriers for that
identity. 1:1 Python port of `@deepseek-ai/dsh-scope`.

## Public surface

```python
from taiyi_core_scope import (
    Scope, ScopeKey, Scoped,
    bind_scope_parent, scope_parent_of, scope_chain_of,
    create_scope, scope_of, scope_target,
    is_scope_carrier, carrier_key_of,
    AnonymousEntries, NamedEntries, ScopedLayers, ScopeLayer,
)
```

## Port decisions

| Upstream | Python |
|---|---|
| `ScopeKey = object` | `ScopeKey = object` (identity-compared) |
| `WeakMap<key, parent>` | `weakref.WeakKeyDictionary[key, parent]` |
| `WeakMap<object, key>` (carrier keys) | `weakref.WeakKeyDictionary[object, ScopeKey \| None]` |
| `ScopedBrand: unique symbol` | `_SCOPED_BRAND` private sentinel on carrier instance |
| `CordisContext.filter` symbol | `Context.filter` class attribute |
| `ctx.plugin(scope)` no-op function plugin | `ctx.plugin(_scope_noop)` |
| `fiber.dispose()` | `fiber.dispose` (sync callable) |
| `fiber.inertia` Task | awaited inside `quiesce_fiber` |