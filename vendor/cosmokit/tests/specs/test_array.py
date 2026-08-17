"""Tests for `cosmokit.array` — set/array normalization helpers."""

import pytest

from cosmokit.array import (
    contain,
    deduplicate,
    difference,
    intersection,
    make_array,
    remove,
    union,
)


def test_contain_subset_true():
    """All items in array2 are members of array1."""
    assert contain([1, 2, 3], [2, 3]) is True


def test_contain_subset_false():
    """An item not in array1 produces False."""
    assert contain([1, 2, 3], [2, 4]) is False


def test_contain_empty_array2_is_true():
    """Every item in an empty list is vacuously contained."""
    assert contain([1, 2, 3], []) is True


def test_contain_empty_array1_with_non_empty_array2_is_false():
    assert contain([], [1]) is False


def test_contain_strings():
    assert contain(["a", "b", "c"], ["a"]) is True
    assert contain(["a", "b", "c"], ["x"]) is False


def test_intersection_basic():
    """Items present in both arrays."""
    assert intersection([1, 2, 3], [2, 3, 4]) == [2, 3]


def test_intersection_no_overlap():
    assert intersection([1, 2], [3, 4]) == []


def test_intersection_preserves_array1_duplicates_and_order():
    """TS implementation filters array1; duplicates/multiplicity come from array1."""
    assert intersection([1, 1, 2, 3], [1, 2]) == [1, 1, 2]


def test_intersection_empty_inputs():
    assert intersection([], [1, 2]) == []
    assert intersection([1, 2], []) == []


def test_difference_basic():
    assert difference([1, 2, 3], [2]) == [1, 3]


def test_difference_empty_array2_keeps_array1():
    assert difference([1, 2, 3], []) == [1, 2, 3]


def test_difference_empty_array1():
    assert difference([], [1, 2]) == []


def test_difference_no_overlap():
    assert difference([1, 2, 3], [4, 5]) == [1, 2, 3]


def test_difference_full_overlap():
    assert difference([1, 2, 3], [1, 2, 3]) == []


def test_union_distinct():
    assert union([1, 2], [3, 4]) == [1, 2, 3, 4]


def test_union_overlap_dedupes_preserving_first_occurrence():
    assert union([1, 2, 3], [2, 3, 4]) == [1, 2, 3, 4]


def test_union_with_empty():
    assert union([1, 2], []) == [1, 2]
    assert union([], [1, 2]) == [1, 2]
    assert union([], []) == []


def test_deduplicate_basic():
    assert deduplicate([1, 1, 2, 2, 3]) == [1, 2, 3]


def test_deduplicate_empty():
    assert deduplicate([]) == []


def test_deduplicate_strings_preserves_order():
    assert deduplicate(["a", "b", "a"]) == ["a", "b"]


def test_remove_returns_true_and_removes_first_match():
    src = [1, 2, 3]
    assert remove(src, 2) is True
    assert src == [1, 3]


def test_remove_only_first_occurrence():
    src = [1, 2, 2, 3]
    assert remove(src, 2) is True
    assert src == [1, 2, 3]


def test_remove_returns_false_when_item_missing():
    src = [1, 2, 3]
    assert remove(src, 4) is False
    assert src == [1, 2, 3]


def test_remove_on_none_list_returns_false():
    """Mirror TS optional chaining: `list?.indexOf(item)` on None → False, no exception."""
    assert remove(None, 1) is False


def test_make_array_from_array_returns_same_list():
    src = [1, 2]
    out = make_array(src)
    assert out == [1, 2]


def test_make_array_from_none_returns_empty():
    assert make_array(None) == []


def test_make_array_from_scalar_wraps_it():
    assert make_array(5) == [5]
    assert make_array("foo") == ["foo"]


def test_make_array_from_empty_array_returns_empty():
    """Empty list is already an array — should pass through unchanged."""
    assert make_array([]) == []


@pytest.mark.parametrize(
    "source,expected",
    [
        (None, []),
        (1, [1]),
        ("x", ["x"]),
        ([], []),
        ([1, 2], [1, 2]),
    ],
)
def test_make_array_parametrized(source, expected):
    assert make_array(source) == expected
