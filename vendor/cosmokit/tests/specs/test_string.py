"""Tests for `cosmokit.string` — case, path, and property helpers."""

import pytest

from cosmokit.string import (
    camelCase,
    camelize,
    capitalize,
    formatProperty,
    hyphenate,
    paramCase,
    sanitize,
    snakeCase,
    trimSlash,
    uncapitalize,
)

# ---------------------------------------------------------------------------
# capitalize / uncapitalize
# ---------------------------------------------------------------------------


def test_capitalize_basic():
    assert capitalize("foo") == "Foo"


def test_capitalize_already_capital():
    assert capitalize("Foo") == "Foo"


def test_capitalize_all_caps_first_only():
    assert capitalize("FOO") == "FOO"


def test_capitalize_camel_case():
    assert capitalize("fooBar") == "FooBar"


def test_capitalize_empty():
    assert capitalize("") == ""


def test_uncapitalize_basic():
    assert uncapitalize("Foo") == "foo"


def test_uncapitalize_already_lower():
    assert uncapitalize("foo") == "foo"


def test_uncapitalize_empty():
    assert uncapitalize("") == ""


def test_uncapitalize_camel_case():
    """Only the first character is touched."""
    assert uncapitalize("FooBar") == "fooBar"


# ---------------------------------------------------------------------------
# camelCase / camelize
# ---------------------------------------------------------------------------


def test_camel_case_dash_to_camel():
    assert camelCase("foo-bar") == "fooBar"


def test_camel_case_underscore_to_camel():
    assert camelCase("foo_bar") == "fooBar"


def test_camel_case_already_camel():
    assert camelCase("fooBar") == "fooBar"


def test_camel_case_no_separator():
    assert camelCase("foo") == "foo"


def test_camel_case_multiple_separators():
    assert camelCase("foo-bar-baz") == "fooBarBaz"


def test_camel_case_mixed_separators():
    assert camelCase("foo-bar_baz") == "fooBarBaz"


def test_camel_case_multiple_uppercase_letters():
    """``FOOBar`` → ``FOOBar`` (uppercase letters before lowercase stay)."""
    assert camelCase("FOOBar") == "FOOBar"


def test_camel_case_separator_then_uppercase_unchanged():
    """``A-B-C`` — the TS regex only triggers on lowercase after the delimiter.
    Since the character after each ``-`` here is uppercase, nothing matches;
    the source passes through unchanged.
    """
    assert camelCase("A-B-C") == "A-B-C"


def test_camelize_alias():
    """``camelize`` is the same callable as ``camelCase``."""
    assert camelize is camelCase


# ---------------------------------------------------------------------------
# paramCase / hyphenate (tokenize with `-` as delimiter)
# ---------------------------------------------------------------------------


def test_param_case_camel_to_dash():
    assert paramCase("fooBar") == "foo-bar"


def test_param_case_pascal_to_dash():
    assert paramCase("FooBar") == "foo-bar"


def test_param_case_already_dash():
    assert paramCase("foo-bar") == "foo-bar"


def test_param_case_already_underscore():
    assert paramCase("foo_bar") == "foo-bar"


def test_param_case_no_separator():
    assert paramCase("foo") == "foo"


def test_param_case_acronym():
    """``FOOBar`` collapses to ``foo-bar``."""
    assert paramCase("FOOBar") == "foo-bar"


def test_param_case_two_uppercase_dash():
    """``FooBARBaz`` → ``foo-bar-baz``."""
    assert paramCase("FooBARBaz") == "foo-bar-baz"


def test_param_case_preserves_non_letter_non_delimiter():
    """Characters that are neither letters nor ``-``/``_`` are passed through."""
    # Digits and punctuation are not delimiters and not letters, so the
    # tokenize state machine falls through to the ``else`` branch.
    assert paramCase("foo9bar") == "foo9bar"
    assert paramCase("foo.bar") == "foo.bar"


def test_hyphenate_alias():
    """``hyphenate`` is the same callable as ``paramCase``."""
    assert hyphenate is paramCase


# ---------------------------------------------------------------------------
# snakeCase
# ---------------------------------------------------------------------------


def test_snake_case_camel_to_underscore():
    assert snakeCase("fooBar") == "foo_bar"


def test_snake_case_pascal_to_underscore():
    assert snakeCase("FooBar") == "foo_bar"


def test_snake_case_already_underscore():
    assert snakeCase("foo_bar") == "foo_bar"


def test_snake_case_already_dash():
    assert snakeCase("foo-bar") == "foo_bar"


def test_snake_case_no_change():
    assert snakeCase("foo") == "foo"


def test_snake_case_acronym():
    assert snakeCase("FOOBar") == "foo_bar"


# ---------------------------------------------------------------------------
# formatProperty
# ---------------------------------------------------------------------------


def test_format_property_simple_identifier():
    assert formatProperty("foo") == ".foo"


def test_format_property_underscore():
    assert formatProperty("_foo") == "._foo"


def test_format_property_dollar():
    assert formatProperty("$foo") == ".$foo"


def test_format_property_with_dash():
    """Identifiers containing ``-`` require bracket notation with quotes."""
    assert formatProperty("foo-bar") == '["foo-bar"]'


def test_format_property_with_spaces():
    assert formatProperty("foo bar") == '["foo bar"]'


def test_format_property_with_dot():
    assert formatProperty("foo.bar") == '["foo.bar"]'


def test_format_property_numeric_string():
    """String keys that start with a digit must be bracket-quoted.

    JSON.stringify of a string adds quotes; this matches the TS behavior.
    """
    assert formatProperty("42") == '["42"]'


def test_format_property_int():
    assert formatProperty(42) == "[42]"


def test_format_property_float():
    assert formatProperty(3.14) == "[3.14]"


# ---------------------------------------------------------------------------
# trimSlash / sanitize
# ---------------------------------------------------------------------------


def test_trim_slash_no_trailing():
    assert trimSlash("foo") == "foo"


def test_trim_slash_with_trailing():
    assert trimSlash("foo/") == "foo"


def test_trim_slash_only_one_trailing():
    """A single trailing slash is removed; only the last is touched."""
    assert trimSlash("foo//") == "foo/"


def test_trim_slash_empty():
    assert trimSlash("") == ""


def test_trim_slash_only_slash():
    assert trimSlash("/") == ""


def test_sanitize_adds_leading_slash():
    assert sanitize("foo/bar") == "/foo/bar"


def test_sanitize_idempotent_for_already_valid():
    assert sanitize("/foo/bar") == "/foo/bar"


def test_sanitize_trims_trailing_slash():
    assert sanitize("/foo/bar/") == "/foo/bar"


def test_sanitize_root():
    assert sanitize("/") == ""


def test_sanitize_empty_results_in_empty():
    """``sanitize("")`` adds ``/`` (no leading) then trims (no trailing) → ``""``.

    The two steps cancel out. Mirrors the TS behavior exactly.
    """
    assert sanitize("") == ""


# ---------------------------------------------------------------------------
# Parametrised
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "input_,expected",
    [
        ("foo", "Foo"),
        ("FOO", "FOO"),
        ("", ""),
        ("foo bar", "Foo bar"),
    ],
)
def test_capitalize_parametrized(input_, expected):
    assert capitalize(input_) == expected


@pytest.mark.parametrize(
    "input_,expected",
    [
        ("foo-bar", "fooBar"),
        ("foo_bar", "fooBar"),
        ("foo", "foo"),
        ("FOOBar", "FOOBar"),
    ],
)
def test_camel_case_parametrized(input_, expected):
    assert camelCase(input_) == expected


@pytest.mark.parametrize(
    "input_,expected",
    [
        ("fooBar", "foo-bar"),
        ("FooBar", "foo-bar"),
        ("foo-bar", "foo-bar"),
        ("FOOBar", "foo-bar"),
    ],
)
def test_param_case_parametrized(input_, expected):
    assert paramCase(input_) == expected


@pytest.mark.parametrize(
    "input_,expected",
    [
        ("fooBar", "foo_bar"),
        ("FooBar", "foo_bar"),
        ("foo_bar", "foo_bar"),
        ("FOOBar", "foo_bar"),
    ],
)
def test_snake_case_parametrized(input_, expected):
    assert snakeCase(input_) == expected


@pytest.mark.parametrize(
    "input_,expected",
    [
        ("foo", "/foo"),
        ("/foo", "/foo"),
        ("/", ""),
        ("", ""),
        ("foo/", "/foo"),
        ("/foo/", "/foo"),
    ],
)
def test_sanitize_parametrized(input_, expected):
    assert sanitize(input_) == expected
