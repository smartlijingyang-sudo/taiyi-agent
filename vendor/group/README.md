# taiyi-group

`taiyi-group` — 1:1 Python port of `@deepseek-ai/cordis-plugin-group`
(`vendor/group` in `deepseek-harness`). The upstream TypeScript file is
3 lines, but it re-exports the runtime `Group` class from
`@deepseek-ai/cordis-plugin-loader` — the real semantics live in
`vendor/loader/src/config/group.ts`. This package ports both files.

## Public surface

- :class:`taiyi_group.service.Group` — the nested plugin Group service.
- :class:`taiyi_group.service.GroupEntry` — entry wrapper with
  `apply` / `dispose` hooks used by the Group.
- :const:`taiyi_group.service.GROUP_MARKER` — `"cordis.group"`, the
  loader tree-carrier marker (1:1 with upstream
  `Symbol.for('cordis.group')`).
- :func:`taiyi_group.service.is_group_carrier`,
  :func:`taiyi_group.service.carrier_key_of` — carrier detection helpers.
- :class:`taiyi_group.service.GroupUpdateError` — error type raised when
  the transactional update and rollback both fail.

## Port decisions

The upstream file is trivially small; the semantics are complex. The
following table records every decision taken when the Python port
diverges from the TypeScript surface.

| # | Upstream (TS)                              | Python port                                           | Why |
|---|--------------------------------------------|-------------------------------------------------------|-----|
| 1 | `export { Group } from '@deepseek-ai/cordis-plugin-loader'` | Self-contained `Group` defined in this package | `taiyi-loader` is still placeholder; Group has no loader-runtime dependency for its own logic |
| 2 | `Group extends EntryGroup` from loader | `Group(Service)` carrying a plain `cordis.EntryGroup` dataclass + a list of `GroupEntry` | Avoid coupling Group to the loader's runtime internals; tests drive behavior via `GroupEntry.apply`/`dispose` hooks |
| 3 | `static readonly [EntryGroup.key] = true`  | `Group.MARKER = "cordis.group"` (string), plus an instance-level `_marker_key` | Python lacks computed symbol-properties; the class-level marker is a string constant used by both loader and invariant comparisons |
| 4 | `update(config: EntryOptions[])`           | `update(config: Sequence[Entry \| GroupEntry])` | Accept either raw `cordis.Entry` (apply via stored hooks) or `GroupEntry` (explicit apply/dispose callables). Mirrors TS where each `Entry` has `update()` + `_dispose()` methods |
| 5 | `Promise.allSettled` + AggregateError       | `asyncio.gather(..., return_exceptions=True)` + custom exception grouping with shared base | asyncio lacks `Promise.allSettled`; we aggregate failures ourselves and surface via a single `GroupUpdateError` |
| 6 | `ctx.on('internal/update', config => this.update(config))` (hot-reload wiring) | Not wired automatically; callers can opt in via `Group(ctx, config).on_hot_reload()` | The Python `cordis.Service` does not auto-subscribe events; explicit opt-in avoids surprising side effects |
| 7 | `async* [Service.init]() { yield stop; await update }` (TS generator init) | `__init__` is sync; users call `update(config)` explicitly | The Python `cordis.Service` has no generator-init lifecycle; same effect via direct method |
| 8 | Per-instance carrier routing via `cordis.scope` | Same idea: each Group has a unique `_marker_key`. Carrier detection via `taiyi_core_scope.scope_target` is exercised in a unit test (separate from the 5 contract tests). The `is_group_carrier` helper exposes the routing key without coupling to scope internals | Reusing `scope_target` would require wrapping `self` in a new carrier object; keeping our own carrier_keys dict is simpler and test-friendly |
