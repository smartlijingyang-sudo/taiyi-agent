"""Public surface for the include invariant companion barrel.

Exposes a stable API contract independent of internal layout, mirroring the
``cordis.invariant`` pattern. Consumers should depend on this submodule for
any cross-package references.
"""

from include.js_expr import JsExpr, evaluate, is_js_expr
from include.patch import PatchOptions, apply_entry_patches
from include.service import ConfigFileError, Include, entry_list_schema

__all__ = [
    "ConfigFileError",
    "Include",
    "JsExpr",
    "PatchOptions",
    "apply_entry_patches",
    "entry_list_schema",
    "evaluate",
    "is_js_expr",
]
