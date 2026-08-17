# `taiyi_core_scope` — Public API Contract

This file describes the contract surface for `taiyi_core_scope`.
Consumers should import from `taiyi_core_scope.invariant` (this subpackage)
rather than the implementation modules.

## Surface

### Types

| Symbol | Kind | Description |
|---|---|---|
| `Scope` | class | Minted registration scope and its quiescent disposal boundaries. |
| `ScopeKey` | alias | Opaque, identity-compared scope identity. |
| `Scoped<T>` | alias | Routing-only event receiver brand. |
| `ScopeParentBinding` | class | Privileged handle to re-link one scope key's parent. |
| `ScopeLayer` | class | One scope's aggregate contribution to a registry. |
| `EntryValues` | class | Internal read contract shared by both entry-table implementations. |
| `NamedEntries<V>` | class | Insertion-ordered named entries with caller-owned duplicate diagnostics. |
| `AnonymousEntries<V>` | class | Insertion-ordered anonymous entries with independent registration identity. |
| `ScopedLayers<L>` | class | Owns the global and exact-scope layers for one registry. |

### Functions

| Symbol | Description |
|---|---|
| `bind_scope_parent(key, parent)` | Bind `parent` as `key`'s enclosing scope; returns a binding that alone may re-link it. |
| `scope_parent_of(key)` | Read one key's enclosing scope, or `None`. |
| `scope_chain_of(key)` | Walk `key` to its root ancestor; nearest first. |
| `create_scope(ctx, key, options?)` | Mint a scope under `ctx`; returns the scoped context and disposal boundaries. |
| `scope_of(ctx)` | Read the nearest scope tag inherited by `ctx`. |
| `scope_target(base, key)` | Build an opaque carrier that preserves `base`'s filter and routes by `key`. |
| `is_scope_carrier(value)` | Return True iff `value` was produced by `scope_target`. |
| `carrier_key_of(value)` | Read a carrier's routing key; `None` for unkeyed/non-carrier. |

## Behavior

1. **Identity-compared keys.** `ScopeKey` is any opaque object; the binding
   table compares by identity (`is`).
2. **Cycle-checked parents.** `bind_scope_parent` and the rebind handle
   reject any link that would close a cycle. Every chain consumer walks
   parents to the root, so a cycle would never terminate.
3. **One-time binding.** Re-binding a key without using the returned
   `ScopeParentBinding` raises; the binding is the privileged handle.
4. **Listeners admit on-chain ancestors, not descendants.** A carrier built
   by `scope_target(base, key)` admits listeners tagged with `key` or any
   of its ancestors (per `bind_scope_parent`). Tags below the dispatch key
   are excluded — events flow up the chain, never down.
5. **Base filter preserved.** `scope_target` runs the wrapped object's
   `cordis.filter` first; if it rejects, the carrier also rejects.
6. **Quiescent teardown.** `Scope.dispose()` awaits the underlying Cordis
   fiber's pending inertia and returns once cleanup completes. Repeated
   calls return the same future (idempotent).
7. **Empty layers reclaim.** `ScopedLayers.effect` deletes the empty
   scope overlay so callers don't accumulate dead per-scope state.