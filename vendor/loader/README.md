# taiyi-loader

1:1 Python port of [`@deepseek-ai/cordis-plugin-loader`](https://github.com/deepseek-ai/deepseek-harness/tree/main/vendor/loader).

The loader owns an `EntryTree`, imports plugin modules by name, applies
their config, and keeps the running plugin graph in sync with entry
updates.

## Usage

```python
from cordis import Context
from loader import Loader

ctx = Context()
loader = Loader(ctx, {"baseUrl": "file:///path/to/config.yml"})

entry_id = await loader.create({"name": "./plugins/example", "config": {"enabled": True}})
await loader.await_()
await loader.update(entry_id, {"config": {"enabled": False}})
```

## Entry Options

| Field      | Description                                                            |
| ---------- | ---------------------------------------------------------------------- |
| `id`       | Stable id for resolving, updating, and removing the entry.             |
| `name`     | Module specifier imported by the loader.                                |
| `config`   | Config passed to the plugin.                                           |
| `group`    | Marks the entry as a group whose `config` is a child entry list.       |
| `disabled` | Stops the entry and prevents it from starting.                         |
| `inject`   | Adds required services or intercept config for this entry.             |

## API

| API                                           | Description                                                          |
| --------------------------------------------- | -------------------------------------------------------------------- |
| `loader.create(options, parent?, position?)`  | Add and start an entry.                                              |
| `loader.update(id, options, parent?, pos?)`   | Update, move, and restart an entry.                                  |
| `loader.remove(id)`                           | Stop and delete an entry.                                            |
| `loader.resolve(id)`                          | Resolve an entry by id, including nested `a:b` ids.                  |
| `loader.resolve_group(id)`                    | Resolve the root group or a nested group.                            |
| `loader.await_()`                             | Wait for pending entry imports and fiber reloads.                    |
| `loader.locate(id?)`                          | Return the loader entry id that owns a fiber.                        |

For file-backed trees, use `taiyi-include`.

## Port-decisions

The upstream TypeScript source is ported to Python idiomatically while
preserving the public API surface. Specific decisions:

| Upstream              | Python port                                                              |
| --------------------- | ------------------------------------------------------------------------ |
| `Symbol.for(x)`       | Python string keys (e.g. `"__js_expr"` for JS-expression markers).       |
| `Symbol(name)`        | String keys carrying the realm suffix (`"<name>#<id>"`).                |
| `Map<K,V>`            | `dict[K,V]`.                                                             |
| `Set<T>`              | `set[T]` / `frozenset[T]`.                                              |
| `WeakRef`             | `weakref.ref` (not used in the data-only port; runtime hooks drop it).  |
| `new Function(...)`   | `eval()` against a constructed AST tree in `loader.utils.evaluate`.     |
| `with (ctx) return eval(expr)` | Scoped namespace: ctx keys are flattened into the eval scope. |
| Node-internal `ModuleLoader` | `importlib.import_module` + `cordis:` builtin dict.            |
| YAML round-trip       | `yaml.safe_load` / `yaml.dump` (PyYAML).                                |
| `Loader.config` Pydantic class attr | Renamed to `loader_config` instance attr to avoid shadowing the `Service.config` classvar. |

### Known port-cuts

- The runtime-only `isolate` plugin (the cordis plugin that installs
  `loader/entry-init` / `loader/patch-context` listeners) lives in
  `loader.isolate` (data layer). The plugin callable is exposed through
  `loader.invariant` and is meant to be installed by an external host;
  the 1:1 plugin install happens on demand in `:func:isolate`.
- The Node-internal `ModuleLoader` surface (v1/v2 enum) is not
  reachable from Python. The runtime port accepts either a normal
  specifier (which goes through `importlib`) or a `cordis:`
  builtin name (which delegates to `loader.builtins`).
- The full file-backed `Loader` subclass lives in the future
  `taiyi-include` port (not in this chunk). This module ships an
  in-memory loader only, with `EntryTree.write()` as a no-op.
