"""loader.invariant — companion subpackage exposing the public API contract.

This subpackage re-exports the public surface of :mod:`loader` so other
packages in the taiyi workspace can declare a stable dependency on the
contract without coupling to the implementation layout.

1:1 with upstream `vendor/loader/src/invariant.ts` (which is just a
re-export barrel in TS; we mirror that pattern as a Python subpackage).
"""

from __future__ import annotations

from loader import (
    Bundle,
    Entry,
    EntryGroup,
    EntryOptions,
    EntryTree,
    GlobalRealm,
    Group,
    JsExpr,
    Loader,
    LocalRealm,
    Realm,
    dump_config,
    evaluate,
    interpolate,
    is_js_expr,
    load_config,
    load_yaml,
    merge_bundles,
    parse_entry,
)
from loader.isolate import isolate_key_lookup

__all__ = [
    # Core classes
    "Bundle",
    "Entry",
    "EntryGroup",
    "EntryOptions",
    "EntryTree",
    "GlobalRealm",
    "Group",
    "JsExpr",
    "Loader",
    "LocalRealm",
    "Realm",
    # Pure helpers
    "dump_config",
    "evaluate",
    "interpolate",
    "is_js_expr",
    "load_config",
    "load_yaml",
    "merge_bundles",
    "parse_entry",
    "isolate_key_lookup",
]
