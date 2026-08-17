"""Tests for `cosmokit.types` — runtime type, binary, clone, equality."""

import datetime
import re

import pytest

from cosmokit.types import (
    Binary,
    arrayBufferToBase64,
    arrayBufferToHex,
    base64ToArrayBuffer,
    clone,
    deepEqual,
    hexToArrayBuffer,
    is_,
)

# ---------------------------------------------------------------------------
# is_() — type-name predicate
# ---------------------------------------------------------------------------


def test_is_string_true():
    assert is_("String", "foo") is True


def test_is_string_false_for_non_string():
    assert is_("String", 5) is False


def test_is_number_true_for_int():
    assert is_("Number", 5) is True


def test_is_number_true_for_float():
    assert is_("Number", 5.5) is True


def test_is_number_false_for_bool():
    """Boolean is a distinct primitive in JS — must not be reported as Number."""
    assert is_("Number", True) is False


def test_is_boolean_true():
    assert is_("Boolean", True) is True


def test_is_boolean_false_for_int():
    """``1`` is a Number, not a Boolean."""
    assert is_("Boolean", 1) is False


def test_is_array_true():
    assert is_("Array", [1, 2]) is True


def test_is_array_false_for_string():
    assert is_("Array", "foo") is False


def test_is_object_true_for_dict():
    """Python plain ``dict`` mirrors JS plain ``Object``."""
    assert is_("Object", {}) is True


def test_is_object_false_for_string():
    assert is_("Object", "foo") is False


def test_is_array_buffer_true_for_bytes():
    assert is_("ArrayBuffer", b"abc") is True


def test_is_array_buffer_true_for_bytearray():
    assert is_("ArrayBuffer", bytearray(b"abc")) is True


def test_is_array_buffer_true_for_memoryview():
    assert is_("ArrayBuffer", memoryview(b"abc")) is True


def test_is_array_buffer_false_for_list():
    assert is_("ArrayBuffer", [1, 2, 3]) is False


def test_is_shared_array_buffer_true_for_memoryview():
    assert is_("SharedArrayBuffer", memoryview(b"abc")) is True


def test_is_shared_array_buffer_false_for_bytes():
    """Bytes are ``ArrayBuffer``, not ``SharedArrayBuffer``."""
    assert is_("SharedArrayBuffer", b"abc") is False


def test_is_date_true_for_datetime():
    assert is_("Date", datetime.datetime(2024, 1, 2, 3, 4, 5, tzinfo=datetime.UTC)) is True


def test_is_date_true_for_date():
    assert is_("Date", datetime.date(2024, 1, 2)) is True


def test_is_date_false_for_string():
    assert is_("Date", "2024-01-02") is False


def test_is_regexp_true():
    assert is_("RegExp", re.compile("foo")) is True


def test_is_regexp_false_for_string():
    assert is_("RegExp", "foo") is False


def test_is_curry_returns_predicate():
    """Single-arg call returns a predicate; calling it returns the test result."""
    pred = is_("String")
    assert callable(pred)
    assert pred("foo") is True
    assert pred(5) is False


def test_is_curry_uses_fresh_call_each_time():
    pred = is_("Number")
    assert pred(5) is True
    assert pred("foo") is False


def test_is_falls_back_to_builtins():
    """Unknown JS names fall back to ``builtins`` lookup."""
    assert is_("int", 5) is True
    assert is_("int", "foo") is False
    assert is_("str", "foo") is True
    assert is_("str", 5) is False


def test_is_unknown_name_uses_to_string_tag():
    """A name matching ``type(value).__name__`` is True even without a map."""

    class MyThing:
        pass

    instance = MyThing()
    assert is_("MyThing", instance) is True
    assert is_("MyThing", "foo") is False


# ---------------------------------------------------------------------------
# Binary — ArrayBuffer/source helpers
# ---------------------------------------------------------------------------


def test_binary_is_bytes():
    assert Binary.is_(b"abc") is True


def test_binary_is_bytearray():
    assert Binary.is_(bytearray(b"abc")) is True


def test_binary_is_memoryview():
    assert Binary.is_(memoryview(b"abc")) is True


def test_binary_is_list_false():
    assert Binary.is_([1, 2, 3]) is False


def test_binary_is_source_bytes():
    """Bytes qualify as both ArrayBuffer and source."""
    assert Binary.is_source(b"abc") is True


def test_binary_is_source_memoryview():
    """Memoryview is an ArrayBuffer-like view."""
    assert Binary.is_source(memoryview(b"abc")) is True


def test_binary_is_source_list_false():
    assert Binary.is_source([1, 2, 3]) is False


def test_binary_from_source_passes_through_bytes():
    """``bytes`` are immutable — pass through unchanged."""
    src = b"hello"
    out = Binary.from_source(src)
    assert out == b"hello"
    assert isinstance(out, bytes)


def test_binary_from_source_copies_memoryview_to_bytes():
    """Memoryview → freshly copied ``bytes``."""
    src = memoryview(b"hello")
    out = Binary.from_source(src)
    assert out == b"hello"
    assert isinstance(out, bytes)


def test_binary_to_base64_hello():
    assert Binary.to_base64(b"hello") == "aGVsbG8="


def test_binary_to_base64_empty():
    assert Binary.to_base64(b"") == ""


def test_binary_from_base64_hello():
    assert Binary.from_base64("aGVsbG8=") == b"hello"


def test_binary_from_base64_empty():
    assert Binary.from_base64("") == b""


def test_binary_round_trip_base64():
    """``from_base64(to_base64(x)) == x`` for any bytes."""
    for payload in [b"", b"hello", b"\x00\xff\x7f", bytes(range(256))]:
        assert Binary.from_base64(Binary.to_base64(payload)) == payload


def test_binary_to_hex():
    assert Binary.to_hex(b"\x01\x02\x03") == "010203"


def test_binary_to_hex_empty():
    assert Binary.to_hex(b"") == ""


def test_binary_from_hex_padded():
    assert Binary.from_hex("010203") == b"\x01\x02\x03"


def test_binary_from_hex_odd_length_drops_trailing():
    """Odd-length hex strings drop the trailing character (mirrors TS)."""
    assert Binary.from_hex("012") == b"\x01"


def test_binary_from_hex_empty():
    assert Binary.from_hex("") == b""


def test_binary_round_trip_hex():
    for payload in [b"", b"\x00\xff", bytes(range(256))]:
        assert Binary.from_hex(Binary.to_hex(payload)) == payload


def test_binary_aliases_base64_to_array_buffer():
    assert base64ToArrayBuffer("aGVsbG8=") == b"hello"


def test_binary_aliases_array_buffer_to_base64():
    assert arrayBufferToBase64(b"hello") == "aGVsbG8="


def test_binary_aliases_hex_to_array_buffer():
    assert hexToArrayBuffer("010203") == b"\x01\x02\x03"


def test_binary_aliases_array_buffer_to_hex():
    assert arrayBufferToHex(b"\x01\x02\x03") == "010203"


# ---------------------------------------------------------------------------
# clone
# ---------------------------------------------------------------------------


def test_clone_none():
    assert clone(None) is None


def test_clone_int():
    assert clone(5) == 5


def test_clone_string():
    assert clone("foo") == "foo"


def test_clone_bool():
    assert clone(True) is True
    assert clone(False) is False


def test_clone_bytes_returns_bytes_copy():
    """``bytes`` is immutable; identity is acceptable but value must be equal."""
    src = b"abc"
    out = clone(src)
    assert out == src
    assert isinstance(out, bytes)


def test_clone_list_returns_new_list():
    src = [1, 2, 3]
    out = clone(src)
    assert out == src
    assert out is not src


def test_clone_dict_returns_new_dict():
    src = {"a": 1, "b": 2}
    out = clone(src)
    assert out == src
    assert out is not src


def test_clone_nested_list_is_deep():
    src = [[1, 2], [3, 4]]
    out = clone(src)
    assert out == src
    assert out is not src
    assert out[0] is not src[0]


def test_clone_nested_dict_is_deep():
    src = {"a": [1, 2], "b": {"c": 3}}
    out = clone(src)
    assert out == src
    assert out is not src
    assert out["a"] is not src["a"]
    assert out["b"] is not src["b"]


def test_clone_list_does_not_mutate_source():
    """Modifying the clone must not affect the original."""
    src = [{"x": 1}, {"y": 2}]
    out = clone(src)
    out[0]["x"] = 999
    out.append({"z": 3})
    assert src == [{"x": 1}, {"y": 2}]


def test_clone_cycle_self_reference():
    src: list = []
    src.append(src)
    out = clone(src)
    # Top level is a new list…
    assert out is not src
    # …but the cycle points to itself, not to the original.
    assert out[0] is out
    assert out[0] is not src


def test_clone_mutual_cycle():
    a: dict = {}
    b: dict = {"next": a}
    a["next"] = b
    out_a = clone(a)
    assert out_a is not a
    assert out_a["next"] is not b
    # Inner cycle points back to itself.
    assert out_a["next"]["next"] is out_a


def test_clone_memoryview_to_bytes():
    src = memoryview(b"hello")
    out = clone(src)
    assert out == b"hello"
    assert isinstance(out, bytes)


def test_clone_unsupported_type_passes_through():
    """Types outside the supported shape (e.g. arbitrary objects) pass through."""

    class Box:
        def __init__(self, value: int) -> None:
            self.value = value

    src = Box(42)
    out = clone(src)
    # No __dict__ cloning for arbitrary user objects; identity preserved.
    assert out is src


# ---------------------------------------------------------------------------
# deepEqual
# ---------------------------------------------------------------------------


def test_deep_equal_identity():
    """``x is x`` → True."""
    a = [1, 2, 3]
    assert deepEqual(a, a) is True


def test_deep_equal_equal_ints():
    assert deepEqual(1, 1) is True


def test_deep_equal_unequal_ints():
    assert deepEqual(1, 2) is False


def test_deep_equal_strings():
    assert deepEqual("foo", "foo") is True
    assert deepEqual("foo", "bar") is False


def test_deep_equal_none_none():
    assert deepEqual(None, None) is True


def test_deep_equal_none_vs_value():
    assert deepEqual(None, 0) is False
    assert deepEqual(None, "x") is False


def test_deep_equal_bool_differs_from_int():
    """``True`` and ``1`` are not deeply equal — even loosely."""
    assert deepEqual(True, 1) is False


def test_deep_equal_empty_lists():
    assert deepEqual([], []) is True


def test_deep_equal_lists_same():
    assert deepEqual([1, 2, 3], [1, 2, 3]) is True


def test_deep_equal_lists_diff_length():
    assert deepEqual([1, 2], [1, 2, 3]) is False


def test_deep_equal_lists_same_length_diff_items():
    assert deepEqual([1, 2, 3], [1, 2, 4]) is False


def test_deep_equal_nested_lists():
    assert deepEqual([[1, 2], [3, 4]], [[1, 2], [3, 4]]) is True
    assert deepEqual([[1, 2], [3, 4]], [[1, 2], [3, 5]]) is False


def test_deep_equal_empty_dicts():
    assert deepEqual({}, {}) is True


def test_deep_equal_dicts_same():
    assert deepEqual({"a": 1, "b": 2}, {"a": 1, "b": 2}) is True


def test_deep_equal_dicts_order_independent():
    """Key order must not affect equality."""
    assert deepEqual({"a": 1, "b": 2}, {"b": 2, "a": 1}) is True


def test_deep_equal_dicts_diff_keys():
    assert deepEqual({"a": 1}, {"b": 1}) is False


def test_deep_equal_dicts_extra_key():
    assert deepEqual({"a": 1}, {"a": 1, "b": 2}) is False


def test_deep_equal_nested_dicts():
    assert deepEqual({"a": {"b": 1}}, {"a": {"b": 1}}) is True
    assert deepEqual({"a": {"b": 1}}, {"a": {"b": 2}}) is False


def test_deep_equal_list_vs_dict():
    """Different shapes are not equal."""
    assert deepEqual([1, 2], {"0": 1, "1": 2}) is False


def test_deep_equal_int_and_list_not_equal():
    assert deepEqual(5, [5]) is False


def test_deep_equal_strict_distinguishes_lengths():
    """Strict mode still recognizes length mismatch."""
    assert deepEqual([1], [1, 2], strict=True) is False


def test_deep_equal_recursive_into_lists():
    """Strict is propagated into recursive calls."""
    assert deepEqual([[1]], [[1]], strict=True) is True
    assert deepEqual([[1]], [[2]], strict=True) is False


@pytest.mark.parametrize(
    "a,b,expected",
    [
        (1, 1, True),
        (1, 2, False),
        ("x", "x", True),
        (None, None, True),
        ([], [], True),
        ({}, {}, True),
        ([1, 2], [1, 2], True),
        ({"a": 1}, {"a": 1}, True),
    ],
)
def test_deep_equal_parametrized(a, b, expected):
    assert deepEqual(a, b) is expected
