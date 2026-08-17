# taiyi-runtime-diagnostics-invariants Public Contract

This document describes the public API contract that
`taiyi_runtime_diagnostics_invariants.invariant` re-exports and that
all consumers of the runtime-diagnostics layer can rely on.

## Overview

The package is a 1:1 Python port of `@deepseek-ai/dsh-invariants` (the
TypeScript runtime diagnostic registry). Every workspace package may
declare an `invariant/__init__.py` companion barrel; this package's plugin
walks those companions at boot and re-exports them under
`ctx.invariants`.

## Service

`InvariantRegistry` is a Cordis service installed by the package's
`@plugin setup` callable. It is reachable as `ctx.invariants` after the
plugin runs.

### Lifecycle

- Construction registers the service with its parent `Context`; disposal
  is automatic when the context disposes.
- Each `register(package_name, surface)` call returns a sync disposer.
- The plugin's disposer releases every vendor registration plus the
  service binding.

### Selection

- `enabled` (default `True`) — global switch.
- `package_allowlist` (default `[]`) — list of regex sources; non-empty
  admit only packages that match at least one pattern.
- `package_blocklist` (default `[]`) — list of regex sources; packages
  matching any pattern are rejected.
- `compile_patterns(field, values)` validates and compiles a filter list,
  rejecting blank / duplicate / invalid regex sources.

### `assert_invariant(name, fn)` test hook

- Records `fn` under `name` and runs it immediately.
- `fn` returning `False` raises `InvariantError`.
- Exceptions raised inside `fn` propagate as-is (callers see the root
  cause rather than a wrapped error).
- Re-using the same `name` twice raises `ValueError`.

### `check(name)` replay

- Runs the check previously stored under `name`.
- Unknown `name` raises `KeyError`; falsy return raises
  `InvariantError`.

## Error Contract

- `InvariantError.code == "INVARIANT"` (stable machine-readable code).
- `InvariantError.package_name` records the source of the violation.
- `InvariantError.__str__` produces
  `invariant violated by "<package>": <message>`.

## Stability Guarantees

All symbols exported from `taiyi_runtime_diagnostics_invariants.invariant`
are stable and will not change in breaking ways without a major version
bump. Symbols not exported there are internal and may change at any time.

## Testing

- Per-file 100% coverage is enforced.
- `pyright strict` 0 errors.
- `ruff` clean.