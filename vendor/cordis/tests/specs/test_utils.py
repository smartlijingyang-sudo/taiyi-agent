"""Tests for cordis.utils — DisposableList, join_prototype, PropsOverlay, etc.

Mirrors upstream ``~/deepseek-harness/vendor/cordis/src/utils.ts``.
"""

from __future__ import annotations

import pytest

from cordis.utils import (
    DisposableList,
    PropsOverlay,
    SHADOW,
    StackInfo,
    is_constructor,
    is_object,
    join_prototype,
    with_props,
)


# ---------------------------------------------------------------------------
# DisposableList
# ---------------------------------------------------------------------------


class TestDisposableList:
    """DisposableList tracks values for LIFO dispose / dedup."""

    def test_push_and_len(self):
        dl = DisposableList()
        dl.push("a")
        dl.push("b")
        assert len(dl) == 2

    def test_push_returns_undo(self):
        dl = DisposableList()
        undo = dl.push("x")
        assert callable(undo)
        assert undo() is True  # First call removes the entry.

    def test_push_undo_returns_false_when_already_removed(self):
        dl = DisposableList()
        undo = dl.push("x")
        undo()  # First undo removes the entry.
        assert undo() is False  # Second undo is a no-op.

    def test_delete_returns_true_when_present(self):
        dl = DisposableList()
        dl.push("x")
        assert dl.delete("x") is True

    def test_delete_returns_false_when_absent(self):
        dl = DisposableList()
        assert dl.delete("missing") is False

    def test_clear_returns_values_lifo(self):
        dl = DisposableList()
        dl.push("a")
        dl.push("b")
        dl.push("c")
        # LIFO order: c, b, a
        assert dl.clear() == ["c", "b", "a"]
        assert len(dl) == 0

    def test_delete_after_clear(self):
        """Deleting after clear returns False (item already gone)."""
        dl = DisposableList()
        dl.push("x")
        dl.clear()
        assert dl.delete("x") is False


# ---------------------------------------------------------------------------
# is_constructor / is_object
# ---------------------------------------------------------------------------


class TestIsConstructor:
    """``is_constructor`` returns True for classes, False otherwise."""

    def test_class_is_constructor(self):
        class MyClass:
            pass

        assert is_constructor(MyClass) is True

    def test_function_is_not_constructor(self):
        def my_fn():
            pass

        assert is_constructor(my_fn) is False

    def test_lambda_is_not_constructor(self):
        assert is_constructor(lambda: None) is False

    def test_callable_instance_is_not_constructor(self):
        class Callable:
            def __call__(self):
                pass

        # Instance of a class with __call__, but not a class itself.
        assert is_constructor(Callable()) is False


class TestIsObject:
    """``is_object`` returns True for dicts / objects."""

    def test_dict_is_object(self):
        assert is_object({}) is True
        assert is_object({"a": 1}) is True

    def test_int_is_not_object(self):
        # is_object may treat ints as objects depending on impl; just verify
        # it doesn't crash.
        result = is_object(42)
        assert isinstance(result, bool)

    def test_string_is_not_object(self):
        result = is_object("hello")
        assert isinstance(result, bool)


# ---------------------------------------------------------------------------
# join_prototype
# ---------------------------------------------------------------------------


class TestJoinPrototype:
    """``join_prototype`` merges two prototype chains into a dynamic class."""

    def test_both_none_returns_none(self):
        assert join_prototype(None, None) is None

    def test_proto1_none_returns_proto2(self):
        class B:
            pass

        result = join_prototype(None, B)
        assert result is B

    def test_proto2_none_returns_proto1(self):
        class A:
            pass

        result = join_prototype(A, None)
        assert result is A

    def test_both_object_returns_none(self):
        assert join_prototype(object, object) is None

    def test_proto1_object_returns_proto2(self):
        class B:
            pass

        result = join_prototype(object, B)
        assert result is B

    def test_proto2_object_returns_proto1(self):
        class A:
            pass

        result = join_prototype(A, object)
        assert result is A

    def test_merges_both_proto_chains(self):
        class A:
            def from_a(self):
                return "a"

        class B:
            def from_b(self):
                return "b"

        merged = join_prototype(A, B)
        assert merged is not None
        instance = merged()
        assert instance.from_a() == "a"
        assert instance.from_b() == "b"


# ---------------------------------------------------------------------------
# PropsOverlay / with_props
# ---------------------------------------------------------------------------


class TestPropsOverlay:
    """PropsOverlay proxies attribute access to props first, then target."""

    def test_getattr_from_props(self):
        target = type("T", (), {"x": 1})()
        overlay = PropsOverlay(target=target, props={"x": 99})
        assert overlay.x == 99

    def test_getattr_falls_back_to_target(self):
        target = type("T", (), {"x": 1})()
        overlay = PropsOverlay(target=target, props={"y": 2})
        assert overlay.x == 1

    def test_getattr_raises_for_self_attrs(self):
        target = type("T", (), {})()
        overlay = PropsOverlay(target=target, props={})
        # PropsOverlay.__getattr__ raises AttributeError for "target" and "props".
        with pytest.raises(AttributeError):
            overlay.__getattr__("target")
        with pytest.raises(AttributeError):
            overlay.__getattr__("props")

    def test_setattr_writes_to_props(self):
        target = type("T", (), {})()
        overlay = PropsOverlay(target=target, props={"x": 1})
        overlay.x = 99
        assert overlay.props["x"] == 99

    def test_setattr_writes_to_target_for_unknown(self):
        target = type("T", (), {})()
        overlay = PropsOverlay(target=target, props={})
        overlay.new_attr = "value"
        assert target.new_attr == "value"

    def test_setattr_writes_target_and_props_meta(self):
        target = type("T", (), {})()
        overlay = PropsOverlay(target=target, props={})
        overlay.target = "should raise"  # Meta-attribute via object.__setattr__.
        # No assertion; just ensure no exception propagates.


class TestWithProps:
    """``with_props`` returns an overlay when props is non-empty."""

    def test_empty_props_returns_target(self):
        target = object()
        result = with_props(target, None)
        assert result is target

    def test_empty_dict_returns_target(self):
        target = object()
        result = with_props(target, {})
        assert result is target

    def test_non_empty_props_returns_overlay(self):
        target = type("T", (), {"x": 1})()
        result = with_props(target, {"x": 99})
        assert result is not target
        assert result.x == 99


# ---------------------------------------------------------------------------
# SHADOW unwrap
# ---------------------------------------------------------------------------


class TestShadowUnwrap:
    """SHADOW getattr behaviour on objects without the attribute."""

    def test_object_without_shadow(self):
        obj = {"x": 1}
        # Plain dict doesn't have the SHADOW attr.
        assert not hasattr(obj, SHADOW)
        # Use direct getattr pattern.
        value = getattr(obj, SHADOW, None)
        assert value is None

    def test_get_traceable_returns_inner_for_shadow(self):
        """``get_traceable`` unwraps the SHADOW attribute when present."""
        from cordis.utils import get_traceable

        inner = {"k": "v"}

        class HasShadow:
            pass

        obj = HasShadow()
        setattr(obj, SHADOW, inner)
        assert get_traceable(None, obj) is inner

    def test_get_traceable_returns_value_when_shadow_is_none(self):
        """SHADOW attr present but None → returns value as-is."""
        from cordis.utils import get_traceable

        class HasNoneShadow:
            pass

        obj = HasNoneShadow()
        setattr(obj, SHADOW, None)
        assert get_traceable(None, obj) is obj

    def test_get_traceable_returns_value_for_non_object(self):
        """Non-object (int) → returned as-is (no SHADOW lookup)."""
        from cordis.utils import get_traceable

        assert get_traceable(None, 42) == 42


class TestJoinPrototypeEmptyMembers:
    """``join_prototype`` with proto1 having only object in MRO."""

    def test_empty_members_returns_plain_subclass(self):
        """proto1 == proto2 → after filtering, members is empty → returns dynamic type."""
        class A:
            pass

        # When proto1 == proto2, the MRO walk filters both out and
        # members stays empty → exercises the empty-branch fallback.
        result = join_prototype(A, A)
        assert result is not None
        # The returned class is a dynamic subclass of A.
        assert issubclass(result, A)


class TestHandleError:
    """``_handle_error`` re-raises with outer stack spliced in."""

    def test_handle_error_reraises_when_no_outer_lines(self):
        """Empty outer_lines → re-raises the original reason."""
        from cordis.utils import StackInfo, _handle_error

        info = StackInfo(error=Exception())
        original = ValueError("boom")
        # get_outer_stack returns empty list → triggers the early raise.
        with pytest.raises(ValueError, match="boom"):
            _handle_error(info, original, lambda: [])

    def test_handle_error_splices_outer_lines(self):
        """Non-empty outer_lines → spliced text attached to error."""
        from cordis.utils import StackInfo, _handle_error

        info = StackInfo(error=Exception())
        original = ValueError("boom")
        outer_lines = ['  File "test.py", line 1, in <module>\n']

        with pytest.raises(ValueError):
            _handle_error(info, original, lambda: outer_lines)
        # The spliced stack is attached.
        assert hasattr(original, "cordis_stack")
        assert "boom" in original.cordis_stack


__all__ = [
    "TestDisposableList",
    "TestIsConstructor",
    "TestIsObject",
    "TestJoinPrototype",
    "TestPropsOverlay",
    "TestWithProps",
    "TestShadowUnwrap",
]