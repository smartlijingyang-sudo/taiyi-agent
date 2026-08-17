"""Tests for `loader.utils` — interpolation + JS expression helpers.

The JS expression evaluator runs in a constrained Python scope equivalent
to upstream's ``new Function('ctx', 'expr', 'with (ctx) { return eval(expr) }')``.
"""

from __future__ import annotations

import pytest

from loader.utils import JsExpr, evaluate, interpolate, is_js_expr


class TestEvaluate:
    """`evaluate(ctx, expr)` mirrors upstream's ``eval`` in a `with`-bound scope."""

    def test_returns_constant(self):
        assert evaluate({}, "1 + 2") == 3

    def test_reads_ctx_property(self):
        assert evaluate({"x": 42}, "x") == 42

    def test_undefined_lookup_raises(self):
        # Upstream mirrors the JS `with (ctx)` block where unbound
        # identifiers surface as `undefined`. Python's nearest equivalent
        # surfaces the same as a ``NameError`` — both reject the lookup.
        with pytest.raises(NameError):
            evaluate({}, "missing")

    def test_can_call_method_on_ctx(self):
        class Holder:
            value = 7

        assert evaluate({"obj": Holder()}, "obj.value") == 7


class TestIsJsExpr:
    """`is_js_expr` matches objects that carry the ``__js_expr`` marker."""

    def test_dict_with_marker_matches(self):
        assert is_js_expr({"__js_expr": "1 + 2"}) is True

    def test_dict_without_marker_does_not_match(self):
        assert is_js_expr({"other": "value"}) is False

    def test_non_object_does_not_match(self):
        assert is_js_expr(42) is False
        assert is_js_expr("string") is False
        assert is_js_expr(None) is False
        assert is_js_expr([1, 2, 3]) is False

    def test_empty_dict_does_not_match(self):
        # Upstream checks ``value instanceof Object && '__jsExpr' in value``.
        # An empty dict has no ``__js_expr`` key.
        assert is_js_expr({}) is False


class TestJsExpr:
    """`JsExpr` — typed wrapper used by interpolate / yaml loaders."""

    def test_repr(self):
        assert repr(JsExpr("a + b")) == "JsExpr('a + b')"

    def test_equality(self):
        assert JsExpr("foo") == JsExpr("foo")
        assert JsExpr("foo") != JsExpr("bar")
        assert JsExpr("foo") != "foo"

    def test_hashable(self):
        # Same expressions hash the same; different ones do not.
        assert hash(JsExpr("a")) == hash(JsExpr("a"))
        assert len({JsExpr("a"), JsExpr("a"), JsExpr("b")}) == 2


class TestInterpolate:
    """`interpolate` recursively replaces YAML ``!js`` JS-expression nodes."""

    def test_js_expr_node_is_evaluated(self):
        ctx = {"v": 5}
        assert interpolate(ctx, {"__js_expr": "v * 2"}) == 10

    def test_non_object_passthrough(self):
        assert interpolate({}, "plain") == "plain"
        assert interpolate({}, 42) == 42
        assert interpolate({}, None) is None

    def test_list_recurses(self):
        ctx = {"v": 3}
        result = interpolate(ctx, [{"__js_expr": "v + 1"}, "raw", 5])
        assert result == [4, "raw", 5]

    def test_dict_recurses(self):
        ctx = {"v": 9}
        result = interpolate(ctx, {"computed": {"__js_expr": "v - 1"}, "static": "ok"})
        assert result == {"computed": 8, "static": "ok"}

    def test_nested_dict_with_primitives(self):
        ctx = {}
        # No markers anywhere — input is returned structurally identical.
        assert interpolate(ctx, {"a": 1, "b": [2, 3]}) == {"a": 1, "b": [2, 3]}

    def test_js_expr_protocol(self):
        # When marked as a `JsExpr` instance, `is_js_expr` must agree.
        expr = JsExpr("1 + 1")
        assert is_js_expr(expr) is True
        assert interpolate({}, expr) == 2

    def test_passes_through_other_objects(self):
        # Mirror upstream: anything not a mapping / list is returned as-is.
        assert interpolate({}, 3.14) == 3.14
        assert interpolate({}, b"bytes") == b"bytes"
        assert interpolate({}, object()) is not None

    def test_tuple_returns_list(self):
        # The map branch returns a list (JS .map semantics).
        result = interpolate({}, (1, 2))
        assert result == [1, 2]
        assert isinstance(result, list)

    def test_js_expr_through_mapping(self):
        # Dict-shaped JS expression (the upstream shape).
        ctx = {"x": 5}
        assert interpolate(ctx, {"__js_expr": "x * 3"}) == 15


class TestEvaluateNonMappingCtx:
    """`evaluate` accepts non-mapping contexts (objects, etc.)."""

    def test_with_non_mapping_ctx(self):
        # When ctx is not a Mapping, scope.update is skipped.
        class _Holder:
            x = 4

        # Use a positional ``Holder`` so the ctx-shape branches both run.
        # Note that the expression can only see ``ctx.x`` since the holder
        # is opaque (no ``items()``).
        assert evaluate(_Holder(), "1 + 2") == 3


class TestInterpolateUnknownObject:
    """`interpolate` returns unknown types unchanged (final `return value`)."""

    def test_returns_arbitrary_object(self):
        sentinel = object()
        assert interpolate({}, sentinel) is sentinel


class TestEvaluateStatementRejected:
    """`evaluate` raises on bare statements (triggers the AST guard)."""

    def test_syntax_error_raises_value_error(self):
        # A genuinely invalid expression triggers the SyntaxError catch.
        with pytest.raises(ValueError):
            evaluate({}, "this is not (+ valid (*")

    def test_unparseable_string_is_rejected(self):
        with pytest.raises(ValueError):
            evaluate({}, "1 +@")
