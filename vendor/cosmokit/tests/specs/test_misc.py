"""Tests for `cosmokit.misc` — utility types and object/dict helpers."""

import pytest

from cosmokit.misc import (
    defineProperty,
    filterKeys,
    isNonNullable,
    isNullable,
    isPlainObject,
    mapValues,
    noop,
    omit,
    pick,
    valueMap,
)

# ---------------------------------------------------------------------------
# noop
# ---------------------------------------------------------------------------


def test_noop_returns_none():
    """``noop`` is a side-effect-only callable that returns ``None``."""
    result = noop()
    assert result is None


def test_noop_callable():
    """``noop`` is callable."""
    assert callable(noop)


# ---------------------------------------------------------------------------
# isNullable / isNonNullable
# ---------------------------------------------------------------------------


def test_is_nullable_true_for_none():
    assert isNullable(None) is True


def test_is_nullable_false_for_string():
    assert isNullable("foo") is False


def test_is_nullable_false_for_empty_string():
    """``''`` is falsy in Python but is NOT nullish — must stay False."""
    assert isNullable("") is False


def test_is_nullable_false_for_zero():
    """``0`` is falsy in Python but is NOT nullish — must stay False."""
    assert isNullable(0) is False


def test_is_nullable_false_for_empty_list():
    """``[]`` is falsy in Python but is NOT nullish — must stay False."""
    assert isNullable([]) is False


def test_is_nullable_false_for_empty_dict():
    assert isNullable({}) is False


def test_is_non_nullable_inverse():
    assert isNonNullable(None) is False
    assert isNonNullable(0) is True
    assert isNonNullable("") is True
    assert isNonNullable([]) is True
    assert isNonNullable({}) is True


# ---------------------------------------------------------------------------
# isPlainObject
# ---------------------------------------------------------------------------


def test_is_plain_object_dict():
    assert isPlainObject({}) is True
    assert isPlainObject({"a": 1}) is True


def test_is_plain_object_list_is_false():
    assert isPlainObject([]) is False
    assert isPlainObject([1, 2, 3]) is False


def test_is_plain_object_none_is_false():
    assert isPlainObject(None) is False


def test_is_plain_object_primitives_are_false():
    assert isPlainObject("foo") is False
    assert isPlainObject(42) is False
    assert isPlainObject(3.14) is False
    assert isPlainObject(True) is False
    assert isPlainObject(b"foo") is False
    assert isPlainObject(bytearray(b"foo")) is False


def test_is_plain_object_instance_is_true():

    class Bag:
        def __init__(self) -> None:
            self.x = 1

    assert isPlainObject(Bag()) is True


def test_is_plain_object_class_itself_is_false():
    """A class object itself is not a plain object instance."""

    class Bag:
        pass

    assert isPlainObject(Bag) is False


# ---------------------------------------------------------------------------
# filterKeys
# ---------------------------------------------------------------------------


def test_filter_keys_keeps_matching_entries():
    src = {"a": 1, "b": 2, "c": 3}
    out = filterKeys(src, lambda k, v: v > 1)
    assert out == {"b": 2, "c": 3}


def test_filter_keys_empty_source():
    assert filterKeys({}, lambda k, v: True) == {}


def test_filter_keys_no_matches():
    assert filterKeys({"a": 1}, lambda k, v: False) == {}


def test_filter_keys_all_match():
    assert filterKeys({"a": 1, "b": 2}, lambda k, v: True) == {"a": 1, "b": 2}


def test_filter_keys_does_not_mutate():
    src = {"a": 1, "b": 2}
    out = filterKeys(src, lambda k, v: True)
    assert src == {"a": 1, "b": 2}
    assert out is not src


def test_filter_keys_with_string_keys():
    src = {"foo": 1, "bar": 2, "baz": 3}
    out = filterKeys(src, lambda k, v: k.startswith("b"))
    assert out == {"bar": 2, "baz": 3}


# ---------------------------------------------------------------------------
# mapValues / valueMap
# ---------------------------------------------------------------------------


def test_map_values_transforms_values():
    assert mapValues({"a": 1, "b": 2}, lambda v, k: v * 10) == {"a": 10, "b": 20}


def test_map_values_receives_key():
    out = mapValues({"a": 1, "b": 2}, lambda v, k: f"{k}={v}")
    assert out == {"a": "a=1", "b": "b=2"}


def test_map_values_empty():
    assert mapValues({}, lambda v, k: v) == {}


def test_value_map_alias_for_map_values():
    """``valueMap`` is the same callable as ``mapValues``."""
    assert valueMap is mapValues


# ---------------------------------------------------------------------------
# pick / omit
# ---------------------------------------------------------------------------


def test_pick_no_keys_returns_shallow_copy():
    src = {"a": 1, "b": 2}
    out = pick(src)
    assert out == src
    assert out is not src


def test_pick_with_keys():
    src = {"a": 1, "b": 2, "c": 3}
    out = pick(src, ["a", "c"])
    assert out == {"a": 1, "c": 3}


def test_pick_skips_missing_keys_by_default():
    src = {"a": 1}
    out = pick(src, ["a", "b"])
    assert out == {"a": 1}


def test_pick_skips_none_values_by_default():
    src = {"a": 1, "b": None}
    out = pick(src, ["a", "b"])
    assert out == {"a": 1}


def test_pick_forced_includes_missing_keys_as_none():
    src = {"a": 1}
    out = pick(src, ["a", "b"], forced=True)
    assert out == {"a": 1, "b": None}


def test_pick_forced_includes_none_values():
    src = {"a": 1, "b": None}
    out = pick(src, ["a", "b"], forced=True)
    assert out == {"a": 1, "b": None}


def test_pick_does_not_mutate_source():
    src = {"a": 1, "b": 2}
    pick(src, ["a"])
    assert src == {"a": 1, "b": 2}


def test_pick_accepts_iterator():
    """``keys`` may be any iterable, not just a list."""
    out = pick({"a": 1, "b": 2}, iter(["a"]))
    assert out == {"a": 1}


def test_omit_no_keys_returns_shallow_copy():
    src = {"a": 1, "b": 2}
    out = omit(src)
    assert out == src
    assert out is not src


def test_omit_with_keys():
    src = {"a": 1, "b": 2, "c": 3}
    out = omit(src, ["a", "c"])
    assert out == {"b": 2}


def test_omit_missing_keys_is_no_op():
    src = {"a": 1}
    out = omit(src, ["x", "y"])
    assert out == {"a": 1}


def test_omit_does_not_mutate_source():
    src = {"a": 1, "b": 2}
    omit(src, ["a"])
    assert src == {"a": 1, "b": 2}


# ---------------------------------------------------------------------------
# defineProperty
# ---------------------------------------------------------------------------


def test_define_property_sets_attribute():
    class Obj:
        pass

    obj = Obj()
    defineProperty(obj, "x", 42)
    assert obj.x == 42  # type: ignore[attr-defined]


def test_define_property_returns_object():
    class Obj:
        pass

    obj = Obj()
    result = defineProperty(obj, "x", 42)
    assert result is obj


def test_define_property_overwrites():
    class Obj:
        existing = 1

    obj = Obj()
    defineProperty(obj, "existing", 99)
    assert obj.existing == 99


def test_define_property_bypasses_setattr_override():
    """``Object.defineProperty`` ignores JS setters — the Python port mirrors this
    by using ``object.__setattr__`` to bypass ``__setattr__`` overrides."""

    class Strict:
        def __setattr__(self, name, value):
            if name == "forbidden":
                raise AttributeError("nope")
            object.__setattr__(self, name, value)

    obj = Strict()
    # Normal setattr would raise; defineProperty must not.
    defineProperty(obj, "forbidden", "secret")
    assert obj.forbidden == "secret"  # type: ignore[attr-defined]

    # Also exercise ``Strict.__setattr__`` so the body isn't dead code:
    obj.allowed = "fine"
    assert obj.allowed == "fine"

    # Direct ``setattr`` with the forbidden name still raises —
    # confirms ``__setattr__`` is wired correctly.
    with pytest.raises(AttributeError):
        obj.forbidden = "nope"  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Parametrised
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value,is_null",
    [
        (None, True),
        (0, False),
        ("", False),
        ("foo", False),
        ([], False),
        ({}, False),
        (False, False),
        (True, False),
    ],
)
def test_is_nullable_parametrized(value, is_null):
    assert isNullable(value) is is_null


@pytest.mark.parametrize(
    "value,is_plain",
    [
        ({}, True),
        ({"a": 1}, True),
        ([], False),
        (None, False),
        (0, False),
        ("foo", False),
        (42, False),
        (True, False),
    ],
)
def test_is_plain_object_parametrized(value, is_plain):
    assert isPlainObject(value) is is_plain
