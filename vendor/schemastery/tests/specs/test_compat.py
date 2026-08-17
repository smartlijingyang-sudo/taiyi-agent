"""Tests for `schemastery._cosmokit_compat` — the inline cosmokit stubs.

These tests cover the nine utility functions inlined from the parallel
``vendor/cosmokit`` package until the cosmokit subagent lands. Once the
real `taiyi_cosmokit` package is wired in, this file should still pass.
"""

from __future__ import annotations

import datetime as _dt

from schemastery._cosmokit_compat import (
    Binary,
    clone,
    deep_equal,
    filter_keys,
    is_nullable,
    is_plain_object,
    pick,
    value_map,
)

# ---------------------------------------------------------------------------
# is_nullable
# ---------------------------------------------------------------------------


def test_is_nullable_true_for_none() -> None:
    assert is_nullable(None) is True


def test_is_nullable_false_for_value() -> None:
    assert is_nullable(0) is False
    assert is_nullable("") is False
    assert is_nullable([]) is False
    assert is_nullable({}) is False


# ---------------------------------------------------------------------------
# is_plain_object
# ---------------------------------------------------------------------------


def test_is_plain_object_for_mapping() -> None:
    assert is_plain_object({}) is True
    assert is_plain_object({"a": 1}) is True


def test_is_plain_object_rejects_non_mapping() -> None:
    assert is_plain_object(None) is False
    assert is_plain_object([]) is False
    assert is_plain_object("x") is False
    assert is_plain_object(0) is False
    assert is_plain_object(b"x") is False


# ---------------------------------------------------------------------------
# deep_equal — exhaustive branch coverage
# ---------------------------------------------------------------------------


def test_deep_equal_primitives() -> None:
    assert deep_equal(1, 1) is True
    assert deep_equal(1.5, 1.5) is True
    assert deep_equal("x", "x") is True
    assert deep_equal(1, 2) is False
    assert deep_equal("x", "y") is False
    assert deep_equal(1, "1") is False
    assert deep_equal(True, False) is False
    assert deep_equal(True, True) is True


def test_deep_equal_is_branch() -> None:
    """``a is b`` early-return covers distinct-but-equal objects."""
    a = [1, 2, 3]
    b = a  # same reference
    assert deep_equal(a, b) is True
    # Large int outside the small-int cache.
    big = 10**18
    assert deep_equal(big, big) is True


def test_deep_equal_nullable_short_circuit() -> None:
    """Both sides ``None`` short-circuits the function via line 79."""
    # Cover the ``is_nullable(a) and is_nullable(b)`` True branch.
    assert deep_equal(None, None) is True
    # Force a strict-True path that doesn't short-circuit on null.
    assert deep_equal(None, None, strict=True) is True
    # One None + one object path (the False branch of the nullable check).
    assert deep_equal(None, {"a": 1}) is False
    assert deep_equal({"a": 1}, None) is False


def test_deep_equal_strict_none() -> None:
    """strict=True requires explicit None matching; non-strict accepts null==null."""
    assert deep_equal(None, None, strict=True) is True
    assert deep_equal(None, None) is True
    assert deep_equal(None, 0, strict=True) is False
    assert deep_equal(None, 0) is False


def test_deep_equal_int_vs_float() -> None:
    assert deep_equal(1, 1.0) is False
    assert deep_equal(1, 1.0, strict=True) is False


def test_deep_equal_lists() -> None:
    assert deep_equal([1, 2], [1, 2]) is True
    assert deep_equal([1, 2], [1, 2, 3]) is False
    assert deep_equal([1, 2], [1, 3]) is False


def test_deep_equal_dicts() -> None:
    assert deep_equal({"a": 1}, {"a": 1}) is True
    assert deep_equal({"a": 1}, {"b": 1}) is False
    assert deep_equal({"a": [1, 2]}, {"a": [1, 2]}) is True


def test_deep_equal_bytes() -> None:
    assert deep_equal(b"abc", b"abc") is True
    assert deep_equal(b"abc", b"abd") is False


def test_deep_equal_regex() -> None:
    import re as _re

    a = _re.compile(r"\d+")
    b = _re.compile(r"\d+")
    c = _re.compile(r"\w+")
    assert deep_equal(a, b) is True
    assert deep_equal(a, c) is False


def test_deep_equal_datetime() -> None:
    a = _dt.date(2024, 1, 1)
    b = _dt.date(2024, 1, 1)
    c = _dt.date(2024, 1, 2)
    assert deep_equal(a, b) is True
    assert deep_equal(a, c) is False


def test_deep_equal_fallback_object_eq() -> None:
    """Arbitrary objects fall back to ``==``."""
    assert deep_equal(object(), object()) is False


def test_deep_equal_none_vs_value() -> None:
    """``None`` vs non-null primitive is unequal."""
    assert deep_equal(None, 0) is False
    assert deep_equal(None, "x") is False
    assert deep_equal(0, None) is False


def test_clone_fallback_returns_source() -> None:
    """Objects whose ``__new__`` raises hit the fallback path."""

    class Frozen:
        __slots__ = ("x",)

        def __init__(self, x: int) -> None:
            self.x = x

    instance = Frozen(7)
    # ``Frozen`` has ``__slots__`` so ``__dict__`` copy is skipped; the
    # fallback branch returns the original source object unchanged.
    assert clone(instance) is instance


# ---------------------------------------------------------------------------
# clone
# ---------------------------------------------------------------------------


def test_clone_primitives() -> None:
    assert clone(1) == 1
    assert clone("x") == "x"
    assert clone(None) is None


def test_clone_dict_deep() -> None:
    src = {"a": [1, 2], "b": {"c": 3}}
    dst = clone(src)
    assert dst == src
    dst["a"].append(3)
    assert src["a"] == [1, 2]
    assert dst["a"] == [1, 2, 3]


def test_clone_list_and_tuple() -> None:
    assert clone([1, 2, 3]) == [1, 2, 3]
    assert clone((1, 2, 3)) == (1, 2, 3)
    # Mutable copy semantics — clones of tuples stay tuples.
    assert isinstance(clone((1, 2)), tuple)


def test_clone_set() -> None:
    out = clone({1, 2, 3})
    assert out == {1, 2, 3}


def test_clone_regex() -> None:
    import re as _re

    pattern = _re.compile(r"\d+")
    cloned = clone(pattern)
    assert cloned.pattern == pattern.pattern
    assert cloned.flags == pattern.flags


def test_clone_cycles() -> None:
    a: dict = {}
    a["self"] = a
    cloned = clone(a)
    assert cloned["self"] is cloned


def test_clone_object_via_dict() -> None:
    class Obj:
        def __init__(self, x: int) -> None:
            self.x = x

    out = clone(Obj(7))
    assert out.x == 7
    assert out.__class__ is Obj


# ---------------------------------------------------------------------------
# filter_keys
# ---------------------------------------------------------------------------


def test_filter_keys_keeps_match() -> None:
    assert filter_keys({"a": 1, "b": 2, "c": 3}, lambda k, v: k in ("a", "c")) == {"a": 1, "c": 3}


# ---------------------------------------------------------------------------
# value_map
# ---------------------------------------------------------------------------


def test_value_map_preserves_keys() -> None:
    assert value_map({"a": 1, "b": 2}, lambda v, k: (v, k)) == {"a": (1, "a"), "b": (2, "b")}


# ---------------------------------------------------------------------------
# pick
# ---------------------------------------------------------------------------


def test_pick_with_keys() -> None:
    assert pick({"a": 1, "b": 2, "c": 3}, ["a", "c"]) == {"a": 1, "c": 3}


def test_pick_without_keys() -> None:
    assert pick({"a": 1, "b": 2}) == {"a": 1, "b": 2}


def test_pick_skips_missing() -> None:
    assert pick({"a": 1}, ["a", "z"]) == {"a": 1}


# ---------------------------------------------------------------------------
# Binary
# ---------------------------------------------------------------------------


def test_binary_is_source_recognizes_bytes() -> None:
    assert Binary.is_source(b"x") is True
    assert Binary.is_source(bytearray(b"x")) is True
    assert Binary.is_source(memoryview(b"x")) is True


def test_binary_is_source_rejects_non_bytes() -> None:
    assert Binary.is_source("x") is False
    assert Binary.is_source(None) is False


def test_binary_from_source_normalises() -> None:
    assert Binary.from_source(b"abc") == b"abc"
    assert Binary.from_source(bytearray(b"abc")) == b"abc"
    assert Binary.from_source(memoryview(b"abc")) == b"abc"


def test_binary_from_source_rejects_other_types() -> None:
    import pytest

    with pytest.raises(TypeError):
        Binary.from_source("x")


def test_binary_base64_roundtrip() -> None:
    data = b"\x00\x01\x02hello"
    assert Binary.from_base64(Binary.to_base64(data)) == data


def test_binary_hex_roundtrip() -> None:
    data = b"\xde\xad\xbe\xef"
    assert Binary.from_hex(Binary.to_hex(data)) == data


def test_binary_from_hex_handles_odd_length() -> None:
    """Odd-length hex strings drop the last char (TS parity)."""
    assert Binary.from_hex("abc") == bytes.fromhex("ab")
