# schemastery

`taiyi-schemastery` is a 1:1 Python port of
[`@deepseek-ai/schemastery`](https://github.com/deepseek-ai/deepseek-harness/tree/master/vendor/schemastery),
the schema-DSL that powers the deepseek-harness configuration surface. The
package exposes the same chainable `Schema` constructor with full parity for
the upstream TypeScript resolvers and formatters.

## Architecture decisions

The upstream TypeScript implementation leans on language features that do
not exist in Python. The 10 decisions below describe how each one is
mapped:

1. **`Symbol.for(x)` → string keys.** Schemastery uses `Symbol.for('schemastery')`
   and `Symbol.for('ValidationError')` for cross-realm markers. Python
   strings are hashable and are the natural replacement; the
   `__schemastery_validation_error__` attribute on
   `schemastery.error.ValidationError` carries the marker.

2. **`Symbol.dispose` → `Disposer` protocol.** Not used directly by
   schemastery; the upstream does not rely on it. Kept for parity with
   `cordis` which does.

3. **WeakRef → `weakref.ref`.** Not used by schemastery; resolvers are
   pure functions over a `Schema` snapshot.

4. **`AbortController` → `Options.ignore`.** Schemastery exposes an
   `Options(autofix=..., ignore=..., path=...)` dataclass instead of an
   `AbortController`. The autofix behaviour mirrors the TS autofix flag;
   the `ignore` callback mirrors the TS `ignore(data, schema)` hook.

5. **`EventEmitter` → not applicable.** Schemastery is a pure validator;
   there is no event bus in the TS surface.

6. **`Disposable` / `Mixin.dispose` → not applicable.** No lifecycle
   methods.

7. **`Promise<T>` → not applicable.** Every schema operation is
   synchronous and returns the normalized output (or raises
   `ValidationError`). The TS `parse` / `safeParse` split maps to
   `schema(data)` (raises) and `Schema.resolve(data, schema)` (returns
   `(output, adapted?)`).

8. **`TaskGroup` → not applicable.** Schemastery does not schedule
   parallel work.

9. **`AsyncLocalStorage` → not applicable.** Schemastery has no
   ambient scope.

10. **`tsconfig.strict` → pyright strict + dataclass + `MetaDict`.**
    Public APIs are typed; the `Schema` class is a `@dataclass` and
    carries a custom `MetaDict` (dict subclass) so that
    `schema.meta.role` (TS-style property access) maps directly to the
    Python attribute API.

11. **TS `Schema.is(value)` keyword → `Schema.is_(value)` method.**
    Python reserves `is`. The TS `Schema.is(constructor)` becomes
    `Schema.is_(constructor)`.

12. **TS `Schema.from(value)` → `Schema.from_(value)`.** Python reserves
    `from`. The TS inference helper becomes `Schema.from_(value)`.

## Cosmokit compat stub

The package depends on nine utilities from `@deepseek-ai/cosmokit`
(`Binary`, `clone`, `deepEqual`, `filterKeys`, `isNullable`,
`isPlainObject`, `pick`, `valueMap`, `Dict`). Until the parallel
`vendor/cosmokit` Python package lands, those utilities are inlined in
[`_cosmokit_compat.py`](./src/schemastery/_cosmokit_compat.py) with a
clear TODO marker. Once `taiyi_cosmokit` is wired in, the orchestrator
swaps the inlined module for the real `from taiyi_cosmokit import …`.

## Public surface

The package exposes the same chainable surface as the upstream TS:

- `z.string()`, `z.number()`, `z.boolean()`, `z.const(value)`,
  `z.natural()`, `z.percent()`, `z.date()`, `z.reg_exp(flag="")`,
  `z.array_buffer(encoding=None)`, `z.bitset(bits)`, `z.function()`,
  `z.is_(Class)`, `z.any()`, `z.never()`.
- `z.array(inner)`, `z.dict(inner, s_key=None)`, `z.tuple(list)`,
  `z.object({...})`, `z.union([...])`, `z.intersect([...])`,
  `z.transform(inner, callback, preserve=False)`.
- `z.lazy(builder)` for recursive schemas.
- `refinement(inner, predicate, message=None)` (DSL shortcut wrapping
  `z.transform` with a predicate guard).
- `Schema.extend(type, resolver)` registers a custom resolver;
  `Schema.from_(value)` infers a schema from a primitive.
- `Schema.resolve(data, schema, options, strict)` is the underlying
  static validator — handy for testing.

Chainable metadata setters (`required`, `default`, `min`, `max`,
`step`, `pattern`, `description`, `role`, `link`, `comment`, `deprecated`,
`experimental`, `hidden`, `loose`, `disabled`, `collapse`, `extra`),
plus the array/object helpers (`set`, `push`) and the
serialization / simplification helpers (`toString`, `toJSON`,
`simplify`, `i18n`).

`ValidationError` mirrors the TS `ValidationError` (subclass of
`TypeError`) with a formatted message prefixed by the JSON-pointer-ish
path (`$.foo[1] expected …`).

## Tests

```sh
uv run pytest vendor/schemastery -q --cov=vendor/schemastery --cov-fail-under=100
```

Per-file 100% coverage is enforced; 247 tests cover every primitive,
composite, edge case, and metadata helper.
