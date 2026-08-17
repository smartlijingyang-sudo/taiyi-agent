"""Tests for taiyi-include JsExpr module.

Mirrors upstream ``vendor/loader/src/config/utils.ts`` plus the include's
``JsExpr`` YAML tag. Evaluates ``!!js <expr>`` markers with an injected
scope (``ctx`` / ``dshHomePath`` / ``process``).

Implementation note: the include port runs the expression through Python
``eval`` (with a tiny ``===``/``!==`` token shim) rather than embedding a JS
engine. The expression syntax is therefore Python-compatible; the upstream
JS dialect is the source-of-truth that the include tag round-trips.
"""

from __future__ import annotations

import pytest

from include.js_expr import JsExpr, evaluate, is_js_expr

# ---------------------------------------------------------------------------
# JsExpr marker shape
# ---------------------------------------------------------------------------


class TestJsExprShape:
    """``JsExpr`` is a tagged string with ``__jsExpr`` key."""

    def test_construction(self) -> None:
        node = JsExpr("process.platform == 'win32'")
        assert node.source == "process.platform == 'win32'"
        assert node.__jsExpr__ == "process.platform == 'win32'"

    def test_dict_representation(self) -> None:
        """Round-trip via dict (the form YAML parses/serializes)."""
        node = JsExpr("1 + 1")
        d = node.to_dict()
        assert d == {"__jsExpr": "1 + 1"}

    def test_from_dict(self) -> None:
        node = JsExpr.from_dict({"__jsExpr": "process.platform"})
        assert node.source == "process.platform"


# ---------------------------------------------------------------------------
# is_js_expr predicate
# ---------------------------------------------------------------------------


class TestIsJsExpr:
    """``is_js_expr`` distinguishes JsExpr nodes from regular values."""

    def test_js_expr_instance(self) -> None:
        assert is_js_expr(JsExpr("foo")) is True

    def test_plain_dict_with_marker(self) -> None:
        """Upstream accepts both ``JsExpr`` instance and ``{__jsExpr: str}``."""
        assert is_js_expr({"__jsExpr": "foo"}) is True

    def test_rejects_other_dicts(self) -> None:
        assert is_js_expr({"foo": "bar"}) is False

    def test_rejects_strings(self) -> None:
        assert is_js_expr("foo") is False

    def test_rejects_none(self) -> None:
        assert is_js_expr(None) is False

    def test_rejects_numbers(self) -> None:
        assert is_js_expr(42) is False

    def test_rejects_empty_dict(self) -> None:
        assert is_js_expr({}) is False


# ---------------------------------------------------------------------------
# evaluate() — expression evaluation against injected scope
# ---------------------------------------------------------------------------


class TestEvaluate:
    """``evaluate(scope, expr)`` runs the expression and returns the value."""

    def test_evaluate_simple_expression(self) -> None:
        result = evaluate({}, "1 + 2")
        assert result == 3

    def test_evaluate_with_ctx_scope(self) -> None:
        result = evaluate({"ctx": {"phase": "one"}}, "ctx.phase")
        assert result == "one"

    def test_evaluate_with_dsh_home_path_scope(self) -> None:
        result = evaluate({"dshHomePath": "/home/me/.dsh"}, "dshHomePath")
        assert result == "/home/me/.dsh"

    def test_evaluate_with_process_scope(self) -> None:
        scope = {"process": {"platform": "linux", "version": "v18.0.0"}}
        assert evaluate(scope, "process.platform") == "linux"
        assert evaluate(scope, "len(process.version) > 0") is True

    def test_evaluate_compares_values(self) -> None:
        scope = {"process": {"platform": "win32"}}
        assert evaluate(scope, "process.platform == 'win32'") is True
        assert evaluate(scope, "process.platform == 'linux'") is False

    def test_evaluate_strict_equality_translated(self) -> None:
        """JS ``===`` / ``!==`` are normalized to ``==`` / ``!=`` by the
        token shim so a JS-style ``!!js`` payload can be evaluated."""
        scope = {"process": {"platform": "win32"}}
        assert evaluate(scope, "process.platform === 'win32'") is True
        assert evaluate(scope, "process.platform !== 'linux'") is True

    def test_evaluate_returns_truthy_object(self) -> None:
        scope = {"ctx": {"value": 42}}
        result = evaluate(scope, "{'value': ctx.value, 'kind': 'answer'}")
        assert result["value"] == 42
        assert result["kind"] == "answer"

    def test_evaluate_returns_list(self) -> None:
        scope = {"n": 5}
        result = evaluate(scope, "[i + 1 for i in range(n)]")
        assert result == [1, 2, 3, 4, 5]

    def test_evaluate_with_combined_scope(self) -> None:
        scope = {
            "ctx": {"flag": True},
            "dshHomePath": "/home/me/.dsh",
            "process": {"platform": "darwin"},
        }
        result = evaluate(
            scope,
            "ctx.flag and 'dsh' in dshHomePath and process.platform == 'darwin'",
        )
        assert result is True

    def test_evaluate_attribute_access_via_proxy(self) -> None:
        """The scope proxy exposes dict keys as attributes so JS-style
        ``ctx.phaseOne.value`` works on Python dicts."""
        scope = {"ctx": {"phaseOne": {"value": "ok"}}}
        assert evaluate(scope, "ctx.phaseOne.value") == "ok"

    def test_evaluate_nested_attribute_access(self) -> None:
        """Deeper chains work via recursive wrapping."""
        scope = {"ctx": {"phaseOne": {"fail": False, "value": "v1"}}}
        assert evaluate(scope, "ctx.phaseOne.value") == "v1"
        assert evaluate(scope, "ctx.phaseOne.fail") is False

    def test_evaluate_returns_name_error_for_missing(self) -> None:
        """A missing identifier raises ``NameError`` (Python's equivalent
        of upstream's ``ReferenceError``)."""
        with pytest.raises(NameError):
            evaluate({}, "nothing")

    def test_evaluate_returns_attribute_error_for_missing_attribute(self) -> None:
        """Missing *attributes* on a scope-proxy raise ``AttributeError``
        (mirrors upstream ``undefined.foo`` returning ``undefined``,
        which Python reifies as an attribute lookup failure)."""
        with pytest.raises(AttributeError):
            evaluate({"ctx": {}}, "ctx.missing")

    def test_evaluate_exception_propagates(self) -> None:
        """An error inside the expression should bubble up (upstream
        ``new Function(...)`` throws on invalid source)."""
        with pytest.raises(SyntaxError):
            evaluate({}, "this is not valid @@ syntax @@")

    def test_evaluate_passes_through_non_string(self) -> None:
        """Non-string / non-dict exprs are evaluated as raw Python."""
        # Numbers and other literals pass through Python ``eval`` unchanged.
        assert evaluate({}, 42) == 42
        assert evaluate({}, True) is True

    def test_evaluate_js_expr_instance(self) -> None:
        """A :class:`JsExpr` instance evaluates its source."""
        scope = {"process": {"platform": "linux"}}
        expr = JsExpr("process.platform")
        assert evaluate(scope, expr) == "linux"

    def test_evaluate_bare_string(self) -> None:
        """A bare string is evaluated as Python source (matches upstream)."""
        scope = {"x": 5}
        assert evaluate(scope, "x * 2") == 10

    def test_from_dict_raises_without_marker(self) -> None:
        """``JsExpr.from_dict`` raises ValueError without ``__jsExpr``."""
        with pytest.raises(ValueError, match="__jsExpr"):
            JsExpr.from_dict({})  # type: ignore[arg-type]

    def test_from_dict_raises_for_non_string_source(self) -> None:
        """``JsExpr.from_dict`` raises TypeError when source isn't a string."""
        with pytest.raises(TypeError, match="str"):
            JsExpr.from_dict({"__jsExpr": 123})  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# ScopeProxy behavior
# ---------------------------------------------------------------------------


class TestScopeProxy:
    """The scope proxy wraps dicts so JS-style attribute access works."""

    def test_getitem_returns_wrapped_dict(self) -> None:
        from include.js_expr import _ScopeProxy

        proxy = _ScopeProxy({"a": {"b": 1}})
        nested = proxy["a"]
        assert nested["b"] == 1

    def test_contains(self) -> None:
        from include.js_expr import _ScopeProxy

        proxy = _ScopeProxy({"a": 1})
        assert "a" in proxy
        assert "missing" not in proxy

    def test_iter(self) -> None:
        from include.js_expr import _ScopeProxy

        proxy = _ScopeProxy({"a": 1, "b": 2})
        assert set(iter(proxy)) == {"a", "b"}

    def test_len(self) -> None:
        from include.js_expr import _ScopeProxy

        proxy = _ScopeProxy({"a": 1, "b": 2, "c": 3})
        assert len(proxy) == 3


# ---------------------------------------------------------------------------
# Round-trip
# ---------------------------------------------------------------------------


class TestRoundTrip:
    """JsExpr marker survives dict ↔ instance round-trip."""

    def test_to_dict_from_dict(self) -> None:
        original = JsExpr("process.platform == 'win32'")
        d = original.to_dict()
        restored = JsExpr.from_dict(d)
        assert restored.source == original.source
        assert restored.to_dict() == d

    def test_evaluate_via_dict(self) -> None:
        """Upstream evaluates plain dicts as well as JsExpr instances."""
        scope = {"process": {"platform": "linux"}}
        assert evaluate(scope, {"__jsExpr": "process.platform"}) == "linux"


__all__: list[str] = []
