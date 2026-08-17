"""Tests for `schemastery.types` — the primitive-schema re-exports.

The module mirrors the spec's §5 surface table by exposing the primitive
constructors as standalone callables. The behavior is exercised by the
``test_schema.py`` suite; this file proves the re-export wiring is intact.
"""

from __future__ import annotations

from schemastery import types as _types


def test_types_module_exposes_all_primitives() -> None:
    """Every primitive listed in the spec §5 table is exported."""
    expected = {
        "any_",
        "array_buffer",
        "bitset",
        "boolean",
        "const",
        "date",
        "function",
        "is_",
        "natural",
        "never",
        "number",
        "percent",
        "reg_exp",
        "string",
    }
    assert expected.issubset(set(dir(_types)))


def test_types_re_exports_validate_correctly() -> None:
    """Each re-exported primitive produces a working validator."""
    assert _types.string()("x") == "x"
    assert _types.number()(1) == 1
    assert _types.boolean()(True) is True
    assert _types.const("v")("v") == "v"
    assert _types.natural()(0) == 0
    assert _types.never()  # noqa: B018 - never() returns a Schema, not raises
    assert _types.any_()(None) is None


def test_types_function_validator() -> None:
    """`types.function()` accepts a callable."""
    def _fn() -> None:  # pragma: no cover - body irrelevant
        pass

    assert _types.function()(_fn) is _fn


def test_types_bitset_validator() -> None:
    """`types.bitset()` accepts numeric input."""
    assert _types.bitset({"a": 1})(1) == 1


def test_types_is_factory() -> None:
    """`types.is_()` validates instances of the given class."""
    assert _types.is_(int)(42) == 42
