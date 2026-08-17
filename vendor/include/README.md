# include

`taiyi-include` — 1:1 Python port of `@deepseek-ai/cordis-plugin-include`
(upstream `~/deepseek-harness/vendor/include/src/index.ts`, 377 LOC).

The Include service is a file-backed entry tree: it reads a YAML or JSON
config at `ctx.baseUrl/path`, applies a configured patch list to every read
+ write, and persists edits back to disk through an atomic tempfile +
rename with retry on `EACCES` / `EBUSY` / `EPERM`. The package also
defines the ``!!js`` YAML scalar tag (round-trips as `{ __jsExpr: <src> }`)
that the Loader evaluates at entry activation time.

## Public surface

| Upstream (TS)                 | Python                                | Notes                                  |
| ----------------------------- | ------------------------------------- | -------------------------------------- |
| `Include` class               | `include.service.Include`             | Mirrors upstream `extends EntryTree`   |
| `Include.Config`              | `include.service.Include.Config`      | Dataclass-style container              |
| `Include.add_entries`         | `Include.add_entries`                 | Static hook for offline tooling        |
| `Include.dispose`             | `Include.dispose` (async)             | Cleanup hook                           |
| `applyEntryPatches`           | `include.patch.apply_entry_patches`   | Pure function, detached output         |
| `PatchOptions` interface      | `include.patch.PatchOptions`          | TypedDict, all fields optional         |
| `JsExpr` Type + `isJsExpr`    | `include.js_expr.JsExpr` / `is_js_expr` | Marker + predicate                   |
| `evaluate`                    | `include.js_expr.evaluate`            | Python `eval` + token shim             |
| `entryListSchema`             | `include.service.entry_list_schema()` | YAML loader class for ``!!js`` dialect |
| `ConfigFileError`             | `include.service.ConfigFileError`     | Stage-tagged file errors               |

## Port-decision table

| Upstream semantic                     | Python implementation                                  |
| ------------------------------------- | ------------------------------------------------------ |
| `structuredClone(data)`              | `copy.deepcopy(data)`                                   |
| `Map<string, EntryOptions>` index    | `dict[str, dict[str, Any]]`                             |
| `this.filename` from `ctx.baseUrl`   | `_resolve_filename(base_url, path)` (file:// stripped)  |
| `this.config.path` extension check   | `SUPPORTED_EXTENSIONS` set; `ValueError` on miss       |
| `this.applyPatches` warn sink        | `Include._warn` → `ctx.root.logger('loader').warn`      |
| `this.enqueue` Promise serialization | Async `Future` chain; predecessor outcome isolated      |
| `this._writeFile` retry loop         | `while True` loop; `await asyncio.sleep` between tries  |
| `node-read` → `ENOENT`               | `cause_errno == 2` (Python's `errno.ENOENT`)            |
| `path: 'file://...'` URL             | `os.path.normpath` join after stripping scheme         |
| JS ``!!js`` `Function('ctx', ...)`   | Python `eval` with token shim (`===` → `==`, etc.)      |
| JS ``with (ctx) { eval(expr) }``     | `_ScopeProxy` mapping → attribute access                |
| YAML `Type('tag:yaml.org,2002:js')`  | `yaml.Type` constructor + `_JsExprLoader`/`_JsExprDumper` |
| `Service.init` async iterator        | `Include.__service_init__` awaited as the body         |

## Test coverage

```bash
cd vendor/include
uv run pytest --cov=src/include --cov-branch --cov-fail-under=100
```

All 148 tests pass, 100% branch coverage on `src/include/`.