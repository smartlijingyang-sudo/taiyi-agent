"""`taiyi_core_scope.carrier` — thin re-exports of the scope-carrier helpers.

1:1 Python port of the helpers exported from
`~/deepseek-harness/packages/core/scope/src/index.ts`:

- :func:`is_scope_carrier`
- :func:`carrier_key_of`

The implementation lives in :mod:`taiyi_core_scope.scope`; this module
exists so callers can ``from taiyi_core_scope.carrier import ...``
without dragging in the rest of the package's surface.
"""

from __future__ import annotations

from taiyi_core_scope.scope import carrier_key_of, is_scope_carrier

__all__ = ["is_scope_carrier", "carrier_key_of"]
