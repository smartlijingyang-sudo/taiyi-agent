# cosmokit

`taiyi-cosmokit` is a 1:1 Python port of
[`@deepseek-ai/cosmokit`](https://github.com/deepseek-ai/cosmokit),
the zero-dependency utility library that powers the rest of the
`taiyi-agent` workspace. It ships runtime-type predicates, binary
(ArrayBuffer / base64 / hex) helpers, clone / deep-equal, case / path /
property string helpers, and time constants + parsing + formatting helpers.

## Architecture decisions

The upstream TypeScript library is pure functions with no platform-
specific dependencies, so the port is essentially a name-by-name
translation. The notes below cover each adaptation needed to land cleanly
in Python.

1. **`is(type)` → `is_(type)`.** TypeScript's `is` is a reserved word in
   Python. The module-level function is exposed as `is_`; the `Binary`
   namespace similarly exposes `Binary.is_`. Callers can re-alias if they
   need the bare name.

2. **`globalThis` lookup → `_TYPE_MAP` + `builtins`.** TS uses
   `globalThis[type]` (e.g. `Array`, `Map`); Python has no globalThis. We
   walk a small `_TYPE_MAP` for JS names with no exact Python equivalent
   (`"ArrayBuffer"`, `"Date"`, `"RegExp"`, …) and fall back to
   `builtins`.

3. **`Object.prototype.toString.call(value)` fallback** is mapped to
   `type(value).__name__`. We deliberately do NOT remap Python names
   (`dict` → `"Object"`, etc.); the string-tag fallback only fires when
   neither the map nor `builtins` recognised the name, in which case the
   actual class name is the most informative tag.

4. **`Object.defineProperty` → `object.__setattr__`.** JS setters are
   bypassed; the Python port mirrors this via `object.__setattr__` to
   skip Python's `__setattr__` override. Non-enumerability has no Python
   analogue; the trailing-underscore name is the only concession.

5. **`string.charCodeAt(i)`-style state machines** (tokenize) keep the
   same byte-by-byte FSM and convert back to `chr` at the end.

6. **`parseDate` returns `int` (epoch ms)** rather than a `Date` object.
   This is more directly comparable and lets tests assert bounds.

7. **`Math.floor` → Python's `math.floor`.** The TS uses
   `Math.floor(...)`; we mirror with `math.floor` (not Python's built-in
   `int()` which truncates towards zero on negatives).

8. **`String#padStart` → `str#rjust`.** Mirrors left-padding semantics
   without truncation.

## Public surface (summary)

| TS module   | Python module    | Notable exports                                                      |
| ----------- | ---------------- | -------------------------------------------------------------------- |
| `array.ts`  | `cosmokit.array` | `contain`, `intersection`, `difference`, `union`, `deduplicate`,    |
|             |                  | `remove`, `makeArray` → `make_array`                                 |
| `types.ts`  | `cosmokit.types` | `is` → `is_`, `Binary`, `clone`, `deepEqual`,                        |
|             |                  | `base64ToArrayBuffer`, `arrayBufferToBase64`,                        |
|             |                  | `hexToArrayBuffer`, `arrayBufferToHex`                               |
| `misc.ts`   | `cosmokit.misc`  | `noop`, `isNullable`, `isNonNullable`, `isPlainObject`,              |
|             |                  | `filterKeys`, `mapValues`, `valueMap`, `pick`, `omit`,               |
|             |                  | `defineProperty` (note: trailing capital P)                          |
| `string.ts` | `cosmokit.string`| `capitalize`, `uncapitalize`, `camelCase`, `camelize`,               |
|             |                  | `paramCase`, `snakeCase`, `hyphenate`, `formatProperty`,             |
|             |                  | `trimSlash`, `sanitize`                                              |
| `time.ts`   | `cosmokit.time`  | `Time` (class) with constants + `setTimezoneOffset`,                 |
|             |                  | `getTimezoneOffset`, `getDateNumber`, `fromDateNumber`,              |
|             |                  | `parseTime`, `parseDate`, `format`, `toDigits`, `template`           |

The convention is **direct port** of every function — names, signatures,
and observable behaviour match where Python types allow.

## Tests

```sh
uv run pytest vendor/cosmokit/tests --cov=vendor/cosmokit --cov-fail-under=100
```

Per-module 100% coverage is enforced.
