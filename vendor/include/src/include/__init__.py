"""``taiyi-include`` — 1:1 Python port of ``@deepseek-ai/cordis-plugin-include``.

File-backed loader entry tree backed by a YAML or JSON config file. Applies
configured patches at every read/write so a dump can never drift from what
boots. The ``!!js`` scalar tag round-trips expressions that the Loader
evaluates at entry activation.

Public surface (re-exported from submodules):

- :class:`Include` — the include service.
- :class:`ConfigFileError` — raised on read / parse / validate failures.
- :func:`apply_entry_patches` — pure patch semantics shared with offline
  tooling (``dsh --dump-config``).
- :class:`PatchOptions` — TypedDict shape for a patch.
- :class:`JsExpr`, :func:`evaluate`, :func:`is_js_expr` — ``!!js`` marker
  + scope-aware expression evaluator.
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
