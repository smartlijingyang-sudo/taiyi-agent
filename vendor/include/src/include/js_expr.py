"""``include.js_expr`` — ``!!js`` expression marker + scope-aware evaluator.

1:1 port of upstream ``~/deepseek-harness/vendor/loader/src/config/utils.ts``
combined with the include-side YAML tag definition. The Loader's include
dialect registers a custom YAML scalar tag ``tag:yaml.org,2002:js`` so a
``!!js`` value round-trips as ``{ __jsExpr: <source> }``. The runtime
evaluates the expression against an injected scope (``ctx``, ``dshHomePath``,
``process``) — exactly as upstream's
``new Function('ctx', 'expr', 'with (ctx) { return eval(expr) }')``.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

__all__ = ["JsExpr", "evaluate", "is_js_expr"]


class _ScopeProxy:
    """Wrap a mapping so attribute access maps to key lookup.

    Mirrors JavaScript's ``with (ctx) { eval(expr) }`` semantics: in JS,
    ``process.platform`` resolves ``process`` as an identifier from the
    with-scope, then accesses ``.platform`` as an attribute on the
    resulting object. In Python, bare ``eval`` performs attribute lookup
    on names, not subscript; this proxy bridges the gap by exposing
    mapping keys as attributes for the duration of an evaluation.
    """

    __slots__ = ("_data",)

    def __init__(self, data: Mapping[str, Any]) -> None:
        self._data = data

    def __getattr__(self, name: str) -> Any:
        try:
            value = self._data[name]
        except KeyError as exc:
            raise AttributeError(name) from exc
        return _wrap(value)

    def __getitem__(self, key: str) -> Any:
        return _wrap(self._data[key])

    def __contains__(self, key: object) -> bool:
        return key in self._data

    def __iter__(self):  # type: ignore[no-untyped-def]
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)


def _wrap(value: Any) -> Any:
    """Recursively wrap dicts so their keys are also attribute-accessible."""
    if isinstance(value, dict) and not isinstance(value, _ScopeProxy):
        return _ScopeProxy(value)
    return value


@dataclass(frozen=True)
class JsExpr:
    """A serialized JavaScript expression node.

    Mirrors upstream ``interface JsExpr { __jsExpr: string }``. The
    attribute name ``__jsExpr`` is intentional: YAML round-trip and the
    upstream ``is_js_expr`` predicate both key on it.
    """

    source: str

    @property
    def __jsExpr__(self) -> str:  # noqa: N802 — upstream API contract
        """Match upstream's tagged-key naming for ``is_js_expr``."""
        return self.source

    def to_dict(self) -> dict[str, str]:
        """Return the dict shape YAML produces."""
        return {"__jsExpr": self.source}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> JsExpr:
        """Construct from a parsed dict (YAML output)."""
        try:
            source = data["__jsExpr"]
        except KeyError as exc:
            raise ValueError("JsExpr.from_dict requires a '__jsExpr' key") from exc
        if not isinstance(source, str):
            raise TypeError(f"JsExpr source must be str, got {type(source).__name__}")
        return cls(source)


def is_js_expr(value: Any) -> bool:
    """Return True when ``value`` is a serialized loader JS expression.

    Accepts both :class:`JsExpr` instances and ``{"__jsExpr": str}`` dicts,
    matching upstream ``value instanceof Object && '__jsExpr' in value``.
    """
    if isinstance(value, JsExpr):
        return True
    if not isinstance(value, dict):
        return False
    raw = value.get("__jsExpr")
    return isinstance(raw, str)


def evaluate(scope: Mapping[str, Any], expr: Any) -> Any:
    """Evaluate ``expr`` against ``scope`` and return the result.

    ``expr`` may be a string (raw JS source) or a :class:`JsExpr` /
    ``{"__jsExpr": str}`` dict. The scope is exposed via ``with`` semantics,
    so identifiers inside the expression resolve directly (matches
    upstream's ``new Function('ctx', 'expr', 'with (ctx) { return eval(expr) }')``).

    Implementation note: Python has no JS engine, so we run the expression
    through Python ``eval`` after a tiny JS→Python token shim: ``===`` and
    ``!==`` become ``==`` / ``!=``. This covers the upstream dsh config
    dialect (``process.platform === 'win32'`` etc.); more advanced JS
    constructs (``typeof``, ``Array.from``, arrow functions) require a real
    JS engine (out of scope for the include port; the upstream loader
    evaluates those expressions in-process via the V8 runtime it embeds).
    """
    if isinstance(expr, JsExpr):
        source = expr.source
    elif isinstance(expr, dict) and isinstance(expr.get("__jsExpr"), str):
        source = expr["__jsExpr"]
    elif isinstance(expr, str):
        source = expr
    else:
        # Non-string expressions are passed through to ``eval`` unchanged.
        return expr

    # Token-level shim: JS strict-equality operators are Python-compatible
    # at the boolean-coercion level. We avoid a full regex rewrite to keep
    # the substitution exact (``===`` / ``!==`` only, not ``==`` inside
    # identifiers).
    source = source.replace("!==", "!=").replace("===", "==")

    namespace: dict[str, Any] = {"__builtins__": __builtins__}
    for key, value in scope.items():
        namespace[key] = _wrap(value)
    code = compile(source, "<js_expr>", "eval")
    return eval(code, namespace)
