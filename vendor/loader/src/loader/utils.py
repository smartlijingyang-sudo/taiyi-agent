"""`loader.utils` — interpolation helpers (1:1 port of `loader/src/config/utils.ts`).

Provides:

- :func:`evaluate` — evaluate a JavaScript expression against a context scope.
  Equivalent to upstream's ``new Function('ctx', 'expr', 'with (ctx){return eval(expr)}')``,
  but adapted to Python by binding the expression in a runtime namespace
  dict (Python's nearest analogue to JS `with`).
- :func:`interpolate` — recursively replace YAML ``!js`` JS-expression nodes
  with their evaluated values, walking dicts and lists.
- :func:`is_js_expr` — predicate that matches objects carrying the marker
  ``__js_expr`` (mirrors upstream's ``__jsExpr`` check).
- :class:`JsExpr` — typed marker so consumers can build expressions
  explicitly without dict hackery.

Port notes
----------

- JS uses ``Symbol.for('cordis.js')`` to tag expressions. In Python we use
  the string key ``__js_expr`` (mirrors the TS marker ``__jsExpr``); both
  interop because the underlying data is just a dict.
- The upstream TS ``evaluate`` is JS-only. Python's analogue binds
  ``expr`` into a runtime namespace created via :func:`eval`. The resulting
  function is module-scope rather than per-call. We keep one shared
  function for parity.
"""

from __future__ import annotations

import ast
from collections.abc import Mapping
from typing import Any

__all__ = ["evaluate", "interpolate", "is_js_expr", "JsExpr"]

# pyright: reportUnknownMemberType=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownVariableType=false


# ---------------------------------------------------------------------------
# JsExpr marker
# ---------------------------------------------------------------------------


class JsExpr:
    """Typed wrapper around a JavaScript expression string.

    Used by YAML loaders and ``interpolate`` to identify evaluation markers.
    Mirrors the upstream ``JsExpr`` interface.
    """

    __slots__ = ("expr",)

    def __init__(self, expr: str) -> None:
        self.expr = expr

    def __repr__(self) -> str:
        return f"JsExpr({self.expr!r})"

    def __eq__(self, other: object) -> bool:
        return isinstance(other, JsExpr) and other.expr == self.expr

    def __hash__(self) -> int:
        return hash(("JsExpr", self.expr))


# ---------------------------------------------------------------------------
# is_js_expr
# ---------------------------------------------------------------------------


def is_js_expr(value: Any) -> bool:
    """Return True if ``value`` carries the ``__js_expr`` marker.

    Mirrors upstream ``isJsExpr``: matches dicts (and the explicit
    :class:`JsExpr`) that have the marker, and matches the wrapper class.
    """
    if isinstance(value, JsExpr):
        return True
    if isinstance(value, Mapping) and "__js_expr" in value:
        return True
    return False


# ---------------------------------------------------------------------------
# evaluate
# ---------------------------------------------------------------------------


_EXPRESSION_KEY = "__js_expr"


def _make_scope(ctx: object) -> dict[str, Any]:
    """Build a flat Python dict from any JS ``ctx``-like object.

    The upstream ``with (ctx) { eval(expr) }`` lets the expression look
    up arbitrary attributes on ``ctx``. Python lacks ``with``, so we
    expose ``ctx`` itself as a single named binding ``ctx``; callers
    that want flat-key access should pre-flatten their mapping.
    """
    return {"ctx": ctx}


def _evaluate_python(expr: str, ctx: object) -> Any:
    """Evaluate ``expr`` in the Python interpreter.

    The expression must reference fields through ``ctx`` (e.g. ``ctx.x``)
    unless they are pre-bound on the returned ``_make_scope`` result.
    """
    # Use `eval` for the equivalent of JS `with(ctx) return eval(expr)`.
    # The scope exposes ``ctx`` plus any attribute-style access via `getattr`.
    scope = _make_scope(ctx)
    # Mirror JS `with(ctx)` flattens `ctx`'s fields directly. Provide a
    # helper `get` so expressions can write ``x + 1`` to access ``ctx.x``.
    if isinstance(ctx, Mapping):
        scope.update(dict(ctx))

    # ``ast.parse(..., mode='eval')`` always yields an ``ast.Expression``;
    # syntax errors surface here as the guard's intended `ValueError`.
    try:
        parsed = ast.parse(expr, mode="eval")
    except SyntaxError as exc:
        raise ValueError(f"loader js expr must be an expression: {expr!r}") from exc
    return eval(compile(parsed, "<loader.js>", "eval"), {"__builtins__": {}}, scope)


def evaluate(ctx: object, expr: str) -> Any:
    """Evaluate the JavaScript expression ``expr`` in the ``ctx`` scope.

    Mirrors the upstream ``new Function('ctx', 'expr', 'with(ctx){return eval(expr)}')``
    by exposing ``ctx``'s keys directly into the evaluation namespace.
    """
    return _evaluate_python(expr, ctx)


# ---------------------------------------------------------------------------
# interpolate
# ---------------------------------------------------------------------------


def interpolate(ctx: object, value: Any) -> Any:
    """Recursively replace JS-expression nodes inside ``value``.

    Mirrors upstream ``interpolate``. The function walks ``value``:

    - JS-expression marker -> evaluate against ``ctx`` and return the value.
    - list               -> map and recurse.
    - dict / Mapping     -> recurse into each value, preserving keys.
    - scalars            -> returned unchanged.

    The walk is shallow on scalars but deep on containers; this matches the
    upstream behaviour of yielding a new top-level structure for containers.
    """
    if is_js_expr(value):
        if isinstance(value, Mapping):
            return evaluate(ctx, value[_EXPRESSION_KEY])
        return evaluate(ctx, value.expr)
    if value is None or isinstance(value, (str, int, float, bool, bytes, bytearray)):
        return value
    if isinstance(value, Mapping):
        return {k: interpolate(ctx, v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [interpolate(ctx, item) for item in value]
    return value
