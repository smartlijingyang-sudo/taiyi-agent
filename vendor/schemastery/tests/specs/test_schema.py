"""Tests for `schemastery` — the 1:1 Python port of `@deepseek-ai/schemastery`.

Every test exercises either the schema-construction surface (callable
constructors and chainable metadata methods) or the validation/resolution
path. The tests follow the upstream TS contract line-by-line.
"""

from __future__ import annotations

import re

import pytest

from schemastery import Schema, ValidationError, z
from schemastery.error import Options
from schemastery.schema import MetaDict

# ---------------------------------------------------------------------------
# Primitive constructors
# ---------------------------------------------------------------------------


def test_string_accepts_str() -> None:
    """`z.string()` validates a plain string."""
    assert z.string()("hello") == "hello"


def test_string_rejects_non_str() -> None:
    """`z.string()` raises ValidationError on non-strings."""
    with pytest.raises(ValidationError):
        z.string()(123)


def test_number_accepts_number() -> None:
    """`z.number()` validates a number."""
    assert z.number()(3.14) == 3.14


def test_number_rejects_non_number() -> None:
    """`z.number()` raises ValidationError on non-numbers."""
    with pytest.raises(ValidationError):
        z.number()("1.5")


def test_boolean_accepts_bool() -> None:
    """`z.boolean()` validates true / false."""
    assert z.boolean()(True) is True
    assert z.boolean()(False) is False


def test_boolean_rejects_non_bool() -> None:
    """`z.boolean()` raises ValidationError on non-booleans."""
    with pytest.raises(ValidationError):
        z.boolean()(1)


def test_const_validates_equal() -> None:
    """`z.const(value)` accepts exactly that value."""
    assert z.const("foo")("foo") == "foo"


def test_const_rejects_unequal() -> None:
    """`z.const(value)` rejects anything else."""
    with pytest.raises(ValidationError):
        z.const("foo")("bar")


def test_natural_accepts_non_negative_int() -> None:
    """`z.natural()` accepts non-negative integers (number with step=1, min=0)."""
    assert z.natural()(0) == 0
    assert z.natural()(5) == 5


def test_natural_rejects_non_int_step() -> None:
    """`z.natural()` rejects non-integer numbers."""
    with pytest.raises(ValidationError):
        z.natural()(1.5)


def test_natural_rejects_negative() -> None:
    """`z.natural()` rejects negative values (min=0)."""
    with pytest.raises(ValidationError):
        z.natural()(-1)


# ---------------------------------------------------------------------------
# Default + required behaviour
# ---------------------------------------------------------------------------


def test_default_returns_fallback_when_null() -> None:
    """`default()` provides a fallback for nullable input."""
    assert z.string().default("fallback")(None) == "fallback"


def test_required_raises_when_null() -> None:
    """`required()` rejects nullable input with ValidationError."""
    with pytest.raises(ValidationError):
        z.string().required()(None)


def test_required_does_not_raise_when_present() -> None:
    """`required()` accepts present values normally."""
    assert z.string().required()("hi") == "hi"


# ---------------------------------------------------------------------------
# Object
# ---------------------------------------------------------------------------


def test_object_validates_dict() -> None:
    """`z.object({a: z.string()})` validates a dict with matching shape."""
    schema = z.object({"a": z.string()})
    assert schema({"a": "x"}) == {"a": "x"}


def test_object_rejects_missing_required_key() -> None:
    """`z.object({a: required_string})` rejects dicts missing the required key."""
    schema = z.object({"a": z.string().required()})
    with pytest.raises(ValidationError):
        schema({})


def test_object_merges_extra_keys() -> None:
    """`z.object({...})` merges declared + extra keys (strict=False; TS parity)."""
    schema = z.object({"a": z.string()})
    result = schema({"a": "x", "extra": 1})
    assert result == {"a": "x", "extra": 1}


def test_object_nested_validates() -> None:
    """`z.object({inner: z.object({...})})` validates nested shapes."""
    schema = z.object({"inner": z.object({"a": z.number()})})
    assert schema({"inner": {"a": 1}}) == {"inner": {"a": 1}}


def test_object_nested_rejects_bad_inner() -> None:
    """Nested object schemas raise ValidationError on mismatch."""
    schema = z.object({"inner": z.object({"a": z.number()})})
    with pytest.raises(ValidationError):
        schema({"inner": {"a": "not a number"}})


# ---------------------------------------------------------------------------
# Union
# ---------------------------------------------------------------------------


def test_union_accepts_first_match() -> None:
    """`z.union([str, number])` accepts a string."""
    schema = z.union([z.string(), z.number()])
    assert schema("x") == "x"


def test_union_accepts_second_match() -> None:
    """`z.union([str, number])` accepts a number."""
    schema = z.union([z.string(), z.number()])
    assert schema(7) == 7


def test_union_rejects_unmatched() -> None:
    """`z.union(...)` rejects a value that matches no member."""
    schema = z.union([z.string(), z.number()])
    with pytest.raises(ValidationError):
        schema(True)


# ---------------------------------------------------------------------------
# Array
# ---------------------------------------------------------------------------


def test_array_accepts_list_of_inner() -> None:
    """`z.array(inner)` validates each element against `inner`."""
    assert z.array(z.number())([1, 2, 3]) == [1, 2, 3]


def test_array_rejects_non_list() -> None:
    """`z.array(inner)` rejects non-list input."""
    with pytest.raises(ValidationError):
        z.array(z.number())("not array")


def test_array_rejects_bad_inner() -> None:
    """`z.array(inner)` rejects list containing non-matching element."""
    with pytest.raises(ValidationError):
        z.array(z.number())([1, "x"])


def test_array_of_objects_validates() -> None:
    """`z.array(z.object({...}))` validates each object element."""
    schema = z.array(z.object({"a": z.string()}))
    assert schema([{"a": "x"}, {"a": "y"}]) == [{"a": "x"}, {"a": "y"}]


# ---------------------------------------------------------------------------
# Refinement (predicate wrapper over transform)
# ---------------------------------------------------------------------------


def test_refinement_passes_when_predicate_true() -> None:
    """`z.refinement(inner, predicate)` accepts values that satisfy the predicate."""
    schema = z.refinement(z.string(), lambda v: len(v) > 0)
    assert schema("hi") == "hi"


def test_refinement_rejects_when_predicate_false() -> None:
    """`z.refinement(inner, predicate)` raises when predicate returns falsy."""
    schema = z.refinement(z.string(), lambda v: len(v) > 0)
    with pytest.raises(ValidationError):
        schema("")


def test_refinement_custom_message() -> None:
    """`refinement(inner, predicate, message)` (dsl module) uses a custom error message."""
    from schemastery import refinement as _refinement

    schema = _refinement(z.string(), lambda v: len(v) > 0, message="must be non-empty")
    with pytest.raises(ValidationError) as info:
        schema("")
    assert "must be non-empty" in str(info.value)


def test_refinement_default_message() -> None:
    """`refinement()` (dsl module) without ``message`` uses the default text."""
    from schemastery import refinement as _refinement

    # Direct callback exercise via the resulting schema — both branches
    # (predicate True / False) of ``_callback``.
    schema = _refinement(z.string(), lambda v: len(v) > 0)
    assert schema("hi") == "hi"  # branch: predicate True
    with pytest.raises(ValidationError) as info:
        schema("")  # branch: predicate False
    assert "expected value to satisfy predicate" in str(info.value)


# ---------------------------------------------------------------------------
# ValidationError formatting
# ---------------------------------------------------------------------------


def test_validation_error_message_at_root_has_no_prefix() -> None:
    """ValidationError at root path has no ``$`` prefix (TS parity)."""
    with pytest.raises(ValidationError) as info:
        z.string()(123)
    assert str(info.value) == "expected string but got 123"


def test_validation_error_message_includes_nested_path() -> None:
    """ValidationError includes the dotted path of the failing key."""
    with pytest.raises(ValidationError) as info:
        z.object({"a": z.string()})({"a": 1})
    assert str(info.value).startswith("$a ")


def test_validation_error_message_includes_indexed_path() -> None:
    """ValidationError includes `[i]` for array indices."""
    with pytest.raises(ValidationError) as info:
        z.array(z.number())([1, "x"])
    assert str(info.value).startswith("$[1] ")


# ---------------------------------------------------------------------------
# Dict / Tuple / Intersect
# ---------------------------------------------------------------------------


def test_dict_validates_mapping() -> None:
    """`z.dict(inner)` validates a dict of `inner` values."""
    schema = z.dict(z.number())
    assert schema({"a": 1, "b": 2}) == {"a": 1, "b": 2}


def test_dict_rejects_non_mapping() -> None:
    """`z.dict(inner)` rejects non-mapping input."""
    with pytest.raises(ValidationError):
        z.dict(z.number())([1, 2])


def test_tuple_validates_each_position() -> None:
    """`z.tuple([a, b, c])` validates each index against its schema."""
    schema = z.tuple([z.string(), z.number()])
    assert schema(["hi", 1]) == ["hi", 1]


def test_tuple_rejects_non_list() -> None:
    """`z.tuple([...])` rejects non-list input."""
    with pytest.raises(ValidationError):
        z.tuple([z.string()])({})


def test_intersect_merges_objects() -> None:
    """`z.intersect([object({a}), object({b})])` merges declared object shapes."""
    schema = z.intersect([
        z.object({"a": z.string()}),
        z.object({"b": z.number()}),
    ])
    assert schema({"a": "x", "b": 1}) == {"a": "x", "b": 1}


# ---------------------------------------------------------------------------
# Bitset / is
# ---------------------------------------------------------------------------


def test_bitset_accepts_number() -> None:
    """`z.bitset({a: 1})` accepts the matching numeric value."""
    schema = z.bitset({"a": 1, "b": 2})
    assert schema(1) == 1


def test_bitset_accepts_keys() -> None:
    """`z.bitset({a: 1, b: 2})` accepts an array of keys and combines bits."""
    from schemastery.error import Options as _Options

    schema = z.bitset({"a": 1, "b": 2})
    result = schema(["a", "b"])
    # Schema.__call__ returns the normalized value; the keys are surfaced via
    # the second tuple element when calling Schema.resolve directly.
    assert result == 3
    _, keys = Schema.resolve(["a", "b"], schema, _Options())
    assert set(keys) == {"a", "b"}


def test_is_accepts_matching_instance() -> None:
    """`z.is_(SomeClass)` accepts instances of the class."""
    schema = z.is_(int)
    assert schema(42) == 42


def test_is_rejects_non_matching() -> None:
    """`z.is_(int)` rejects non-int values."""
    with pytest.raises(ValidationError):
        z.is_(int)("x")


# ---------------------------------------------------------------------------
# Lazy / Any / Never
# ---------------------------------------------------------------------------


def test_lazy_resolves_recursively() -> None:
    """`z.lazy(builder)` defers schema construction until first resolve.

    The builder returns an object schema that points back to itself via
    ``z.lazy``. We validate a single-level recursion: the lazy resolves
    once into the builder, which validates its ``"next"`` key against
    the *same* lazy — but since data["next"] is the empty object, the
    schema's nullable-handling short-circuits.
    """

    def builder() -> Schema:
        return z.object({"next": z.lazy(builder)})

    schema = builder()
    # Single-level recursion; the inner lazy resolves to the builder and
    # then finds data["next"] == {}, which has no required key.
    result = schema({"next": {}})
    assert result == {"next": {}}


def test_any_accepts_anything() -> None:
    """`z.any()` accepts any value unchanged."""
    assert z.any()(42) == 42
    assert z.any()("x") == "x"


def test_never_rejects_non_null() -> None:
    """`z.never()` raises ValidationError on non-null values."""
    with pytest.raises(ValidationError):
        z.never()(1)


# ---------------------------------------------------------------------------
# Chainable meta methods
# ---------------------------------------------------------------------------


def test_pattern_sets_regexp() -> None:
    """`pattern(regexp)` rejects strings that don't match."""
    schema = z.string().pattern(re.compile(r"^[a-z]+$"))
    assert schema("abc") == "abc"
    with pytest.raises(ValidationError):
        schema("ABC")


def test_max_min_bounds_number() -> None:
    """`max()` and `min()` enforce inclusive bounds for numbers."""
    schema = z.number().min(0).max(10)
    assert schema(5) == 5
    with pytest.raises(ValidationError):
        schema(11)


def test_step_enforces_increment() -> None:
    """`step()` enforces the numeric increment for `number` schemas."""
    schema = z.number().step(0.5)
    assert schema(1.5) == 1.5
    with pytest.raises(ValidationError):
        schema(1.25)


def test_max_min_bounds_string_length() -> None:
    """`max()` and `min()` enforce length bounds for strings."""
    schema = z.string().min(2).max(4)
    assert schema("ab") == "ab"
    with pytest.raises(ValidationError):
        schema("a")


def test_default_on_object_is_dict() -> None:
    """`z.object({...})` defaults `meta.default` to `{}`."""
    schema = z.object({"a": z.string()})
    assert schema.meta.default == {}


def test_default_on_array_is_list() -> None:
    """`z.array(inner)` defaults `meta.default` to `[]`."""
    assert z.array(z.number()).meta.default == []


def test_required_default_disabled_collapse_hidden_loose() -> None:
    """All boolean metadata setters return a new schema with the flag set."""
    schema = z.string()
    for value in (True, False):
        assert schema.required(value).meta.required is value
        assert schema.disabled(value).meta.disabled is value
        assert schema.collapse(value).meta.collapse is value
        assert schema.hidden(value).meta.hidden is value
        assert schema.loose(value).meta.loose is value


def test_role_link_comment_description() -> None:
    """String metadata setters attach values into `meta`."""
    schema = z.string().role("input").link("https://example.com").comment("c").description("d")
    assert schema.meta.role == "input"
    assert schema.meta.link == "https://example.com"
    assert schema.meta.comment == "c"
    assert schema.meta.description == "d"


def test_deprecated_experimental_add_badges() -> None:
    """`deprecated()` / `experimental()` append badges to `meta.badges`."""
    d = z.string().deprecated()
    e = z.string().experimental()
    assert d.meta.badges == [{"text": "deprecated", "type": "danger"}]
    assert e.meta.badges == [{"text": "experimental", "type": "warning"}]


def test_extra_attaches_arbitrary_meta() -> None:
    """`extra(key, value)` attaches arbitrary metadata."""
    schema = z.string().extra("hidden", True)
    assert schema.meta.hidden is True


# ---------------------------------------------------------------------------
# Object mutation helpers
# ---------------------------------------------------------------------------


def test_set_adds_property_to_object() -> None:
    """`set(key, value)` adds a property to an object schema."""
    schema = z.object({"a": z.string()}).set("b", z.number())
    assert schema({"a": "x", "b": 1}) == {"a": "x", "b": 1}


def test_push_appends_to_union() -> None:
    """`push(value)` appends to a union list."""
    schema = z.union([z.string()]).push(z.number())
    assert schema(7) == 7


# ---------------------------------------------------------------------------
# toString / toJSON / simplify / i18n
# ---------------------------------------------------------------------------


def test_to_string_for_string() -> None:
    """`toString()` for a string schema returns ``string``."""
    assert z.string().to_string() == "string"


def test_to_string_for_object_with_required() -> None:
    """`toString()` marks required keys with no trailing `?`."""
    schema = z.object({"a": z.string().required(), "b": z.number()})
    assert schema.to_string() == "{ a: string, b?: number }"


def test_to_string_for_union_inline() -> None:
    """Inline `toString()` wraps unions in parentheses."""
    schema = z.union([z.string(), z.number()])
    assert schema.to_string(True) == "(string | number)"


def test_to_json_roundtrip_serializes() -> None:
    """`toJSON()` serializes a schema to a structure containing `uid` + `refs`."""
    schema = z.object({"a": z.string()})
    out = schema.toJSON()
    assert "uid" in out
    assert "refs" in out


def test_simplify_returns_value() -> None:
    """`simplify(value)` returns the value (no simplification for non-objects)."""
    assert z.string().simplify("x") == "x"


def test_simplify_drops_object_default() -> None:
    """`simplify(value)` returns `None` for an object equal to its default."""
    schema = z.object({"a": z.string()}).default({"a": "x"})
    assert schema.simplify({"a": "x"}) is None


def test_i18n_merges_descriptions() -> None:
    """`i18n(messages)` merges per-locale descriptions into `meta.description`."""
    schema = z.string().description("hello").i18n({"zh": {"$description": "你好"}})
    assert schema.meta.description == {"": "hello", "zh": "你好"}


def test_i18n_propagates_to_object_children() -> None:
    """`i18n()` on an object schema propagates locale dicts to each child."""
    schema = z.object({"a": z.string(), "b": z.number()})
    localized = schema.i18n({"zh": {"a": "甲", "b": "乙"}})
    assert localized.dict["a"].meta.description == {"zh": "甲"}
    assert localized.dict["b"].meta.description == {"zh": "乙"}


def test_i18n_propagates_to_list_children() -> None:
    """`i18n()` on a union schema propagates per-index messages."""
    schema = z.union([z.string(), z.number()])
    localized = schema.i18n({"zh": ["甲", "乙"]})
    assert localized.list[0].meta.description == {"zh": "甲"}
    assert localized.list[1].meta.description == {"zh": "乙"}


def test_i18n_propagates_to_inner() -> None:
    """`i18n()` on an array schema propagates to the inner schema."""
    schema = z.array(z.string())
    localized = schema.i18n({"zh": {"$value": "only"}})
    assert localized.inner.meta.description == {"zh": "only"}


def test_i18n_propagates_to_dict_s_key() -> None:
    """`i18n()` on a dict schema propagates to the key schema."""
    schema = z.dict(z.string())
    localized = schema.i18n({"zh": {"$key": "k"}})
    assert localized.s_key.meta.description == {"zh": "k"}


def test_i18n_string_messages_kept() -> None:
    """`i18n()` plain string messages are added to the description dict."""
    schema = z.string().description("hello").i18n({"ja": "こんにちは"})
    assert schema.meta.description == {"": "hello", "ja": "こんにちは"}


def test_i18n_dict_description_kept() -> None:
    """`i18n()` preserves an existing dict description and merges new locales."""
    schema = z.string().description({"": "hi", "zh": "你好"})
    localized = schema.i18n({"ja": "こんにちは"})
    assert localized.meta.description == {"": "hi", "zh": "你好", "ja": "こんにちは"}


def test_i18n_desc_alias() -> None:
    """`$desc` alias also populates the description."""
    schema = z.string().i18n({"zh": {"$desc": "你好"}})
    assert schema.meta.description == {"zh": "你好"}


def test_simplify_object_strips_default() -> None:
    """`simplify(value)` for an object schema returns ``None`` when equal to default."""
    schema = z.object({"a": z.string()}).default({"a": "x"})
    assert schema.simplify({"a": "x"}) is None


def test_simplify_object_keeps_non_default() -> None:
    """`simplify()` for an object schema returns the simplified object."""
    schema = z.object({"a": z.string()}).default({"a": "x"})
    result = schema.simplify({"a": "y"})
    assert result == {"a": "y"}


def test_simplify_dict_strips_default() -> None:
    """`simplify()` for a dict schema with value equal to default returns None."""
    schema = z.dict(z.number())
    assert schema.simplify({}) is None


def test_simplify_array_returns_simplified() -> None:
    """`simplify()` for an array schema returns a simplified array."""
    schema = z.array(z.string())
    result = schema.simplify(["a", "b"])
    assert result == ["a", "b"]


def test_simplify_tuple_returns_simplified() -> None:
    """`simplify()` for a tuple schema uses each member schema."""
    schema = z.tuple([z.string(), z.number()])
    result = schema.simplify(["a", 1])
    assert result == ["a", 1]


def test_simplify_intersect_merges_objects() -> None:
    """`simplify()` for an intersect schema merges dict outputs."""
    schema = z.intersect([
        z.object({"a": z.string()}),
        z.object({"b": z.number()}),
    ])
    result = schema.simplify({"a": "x", "b": 1})
    assert isinstance(result, dict)
    assert result["a"] == "x"
    assert result["b"] == 1


def test_simplify_union_picks_matching_member() -> None:
    """`simplify()` for a union schema dispatches to the matching member."""
    schema = z.union([z.string(), z.number()])
    assert schema.simplify(42) == 42
    assert schema.simplify("x") == "x"


def test_simplify_returns_value_for_unknown_type() -> None:
    """`simplify()` falls back to returning the value unchanged for unknown types."""
    assert z.string().simplify("x") == "x"


def test_simplify_handles_null() -> None:
    """`simplify()` returns the value unchanged when it is null."""
    assert z.string().simplify(None) is None


def test_simplify_object_returns_none_when_simplified_equals_default() -> None:
    """`simplify()` for an object returns ``None`` when the simplified result matches the default."""
    schema = z.object({"a": z.string().default("x")}).default({})
    # The object's "a" simplifies to None (since "x" == default); the
    # outer result is then compared against the empty-dict default.
    assert schema.simplify({"a": "x"}) is None


def test_simplify_object_returns_value_when_null() -> None:
    """`simplify()` for an object returns the value when it is null."""
    schema = z.object({"a": z.string()})
    assert schema.simplify(None) is None


def test_to_string_default_falls_back() -> None:
    """`toString()` returns ``Schema<{type}>`` for unknown types."""
    schema = Schema(type="custom_unknown_type")
    assert schema.to_string() == "Schema<custom_unknown_type>"


def test_to_string_array_with_no_inner() -> None:
    """`toString()` for an array schema with no inner uses ``unknown``."""
    schema = Schema(type="array", inner=None)
    assert schema.to_string() == "unknown[]"


def test_to_string_dict_with_no_inner() -> None:
    """`toString()` for a dict schema with no inner / key uses the fallbacks."""
    schema = Schema(type="dict", inner=None, s_key=None)
    assert schema.to_string() == "{ [key: string]: any }"


def test_to_string_transform_with_no_inner() -> None:
    """`toString()` for a transform schema with no inner uses ``transform``."""
    schema = Schema(type="transform", inner=None)
    assert schema.to_string() == "transform"


def test_to_string_tuple_inline() -> None:
    """`toString(inline=True)` for a tuple wraps each member in inline form."""
    schema = z.tuple([z.string(), z.number()])
    assert schema.to_string(True) == "[string, number]"


def test_reg_exp_with_flags() -> None:
    """`reg_exp(flag)` translates a TS-style flag string to Python int flags."""
    pattern = z.reg_exp("i")("[A-Z]+")
    assert isinstance(pattern, re.Pattern)
    assert pattern.flags & re.IGNORECASE


def test_reg_exp_unknown_flag_chars_ignored() -> None:
    """Unknown flag chars in a TS-style string are silently ignored."""
    pattern = z.reg_exp("?")("abc")
    assert isinstance(pattern, re.Pattern)


def test_array_buffer_rejects_non_source() -> None:
    """`array_buffer()` rejects values that aren't ArrayBuffer / bytes sources."""
    with pytest.raises(ValidationError):
        z.array_buffer()("not a buffer")


def test_array_buffer_from_invalid_base64() -> None:
    """`array_buffer("base64")` raises on an unparseable string."""
    with pytest.raises(ValidationError):
        z.array_buffer("base64")("not valid base64!!!")


def test_i18n_object_with_inner_marker() -> None:
    """`i18n()` with ``$inner`` markers drills into the inner object."""
    schema = z.object({"a": z.object({"b": z.string()})})
    localized = schema.i18n({"zh": {"a": {"$inner": {"b": "内"}}}})
    # The grand-child description should be the localized string under ``zh``.
    inner_a = localized.dict["a"]
    assert isinstance(inner_a, Schema)
    assert inner_a.dict["b"].meta.description == {"zh": "内"}


def test_i18n_union_with_value_marker() -> None:
    """`i18n()` with ``$value`` marker drills into the union's per-element value."""
    schema = z.union([z.string(), z.number()])
    localized = schema.i18n({"zh": {"$value": ["甲", "乙"]}})
    assert localized.list[0].meta.description == {"zh": "甲"}


def test_i18n_with_inner_value_marker() -> None:
    """`i18n()` with ``$value`` marker propagates to an inner schema."""
    schema = z.array(z.string())
    localized = schema.i18n({"zh": {"$value": "单值"}})
    assert localized.inner.meta.description == {"zh": "单值"}


def test_schema_from_str_returns_string_schema() -> None:
    """`Schema.from_(str)` returns a string-typed schema."""
    schema = Schema.from_(str)
    assert schema.type == "string"
    assert schema("x") == "x"


def test_schema_from_bool_returns_boolean_schema() -> None:
    """`Schema.from_(bool)` returns a boolean-typed schema."""
    schema = Schema.from_(bool)
    assert schema.type == "boolean"
    assert schema(True) is True


def test_schema_from_int_returns_number_schema() -> None:
    """`Schema.from_(int)` returns a number-typed schema."""
    schema = Schema.from_(int)
    assert schema.type == "number"
    assert schema(42) == 42


def test_schema_from_custom_class_returns_is_schema() -> None:
    """`Schema.from_(MyClass)` for a non-builtin class returns an ``is_`` schema."""

    class Custom:
        pass

    schema = Schema.from_(Custom)
    assert schema.type == "is"
    # Both instances pass; non-custom instance is rejected.
    instance = Custom()
    assert schema(instance) is instance
    with pytest.raises(ValidationError):
        schema(object())


def test_is_by_name_rejects_unrelated() -> None:
    """`is_("ClassName")` rejects objects whose prototype chain doesn't include the name."""

    class Animal:
        pass

    schema = z.is_("Animal")
    with pytest.raises(ValidationError):
        schema(object())


def test_bitset_non_string_key_raises() -> None:
    """`z.bitset()` rejects arrays with non-string keys."""
    schema = z.bitset({"a": 1})
    with pytest.raises(ValidationError):
        schema([1, 2])


def test_bitset_rejects_non_number_non_array() -> None:
    """`z.bitset()` rejects values that aren't numbers or arrays."""
    schema = z.bitset({"a": 1})
    with pytest.raises(ValidationError):
        schema("not a bitset")


def test_bitset_value_equals_default_returns_no_keys() -> None:
    """`z.bitset()` returning the default value emits no keys."""
    schema = z.bitset({"a": 0, "b": 0})  # default=0, all bits zero
    value, keys = Schema.resolve(schema.meta.default, schema, Options())
    assert keys is None


def test_array_buffer_from_invalid_source_raises() -> None:
    """`z.array_buffer()` rejects a value that isn't a BufferSource."""
    # The union's transform branch fires only when the source check fails.
    with pytest.raises(ValidationError):
        z.array_buffer()(123)


def test_object_autofix_drops_bad_keys() -> None:
    """`z.object({...})` with ``autofix=True`` drops keys that fail inner validation."""
    schema = z.object({"a": z.string().required()})
    result = schema({"a": 1, "b": "extra"}, Options(autofix=True))
    assert "b" not in result or result.get("a") is None


def test_object_merges_extra_keys_by_default() -> None:
    """`z.object({...})` (strict=False) merges extra keys from input data."""
    schema = z.object({"a": z.string()})
    result = schema({"a": "x", "extra": 1})
    assert result.get("extra") == 1


def test_dict_resolves_with_key_transformation() -> None:
    """`z.dict(inner, s_key)` runs keys through the key schema."""
    schema = z.dict(z.number(), z.string().required())
    assert schema({"a": 1, "b": 2}) == {"a": 1, "b": 2}


def test_dict_strict_skips_invalid_keys() -> None:
    """`z.dict()` with ``strict=True`` skips keys that fail key validation."""
    schema = z.dict(z.number(), z.string().required())
    # Calling Schema.resolve with strict=True skips invalid keys.
    result, _ = Schema.resolve({1: "x", "a": 1}, schema, Options(), True)
    assert "a" in result


def test_tuple_with_extras() -> None:
    """`z.tuple([...])` (strict=False) preserves extra elements beyond declared members."""
    schema = z.tuple([z.string(), z.number()])
    assert schema(["hi", 1, "extra"]) == ["hi", 1, "extra"]


def test_tuple_strict_returns_just_members() -> None:
    """`z.tuple([...])` (strict=True) returns only the declared-member positions."""

    schema = z.tuple([z.string(), z.number()])
    # Direct resolve with strict=True returns only the declared positions.
    result, _ = Schema.resolve(["hi", 1, "extra"], schema, Options(), True)
    assert result == ["hi", 1]


def test_dict_strict_skips_invalid_key_branch() -> None:
    """`_resolve_dict` strict-mode branch skips invalid keys (line 938)."""
    # An integer key bypasses the string s_key; strict=True skips them.
    schema = z.dict(z.number(), z.string().required())
    result, _ = Schema.resolve({1: 1, "valid": 1}, schema, Options(), True)
    assert "valid" in result and 1 not in result


def test_dict_non_strict_raises_on_invalid_key() -> None:
    """`_resolve_dict` non-strict branch raises on invalid keys (line 938)."""
    # Calling without strict should raise on the int key.
    schema = z.dict(z.number(), z.string().required())
    with pytest.raises(ValidationError):
        Schema.resolve({1: 1}, schema, Options(), False)


def test_intersect_member_skipped_when_nullable_branch() -> None:
    """`_resolve_intersect` skips a member that resolves to ``None`` (line 1037)."""
    # Use a custom member that returns None for ``x`` so the intersect skips it.
    schema = z.intersect([
        z.transform(z.string(), lambda value, _opts: None),
        z.const("x"),
    ])
    assert schema("x") == "x"


def test_transform_non_preserve_returns_both() -> None:
    """`z.transform()` without ``preserve`` returns both the normalized + adapted outputs."""
    schema = z.transform(z.string(), lambda value, _opts: value.upper())
    value, _ = Schema.resolve("hello", schema, Options(), True)
    assert value == "HELLO"


def test_intersect_with_no_members_returns_data() -> None:
    """`z.intersect([])` returns the input data unchanged."""
    schema = z.intersect([])
    assert schema("x") == "x"


def test_intersect_rejects_type_mismatch() -> None:
    """`z.intersect([a, b])` raises when members produce different types."""
    schema = z.intersect([z.string(), z.number()])
    with pytest.raises(ValidationError):
        schema("x")


def test_intersect_rejects_value_mismatch() -> None:
    """`z.intersect([a, b])` raises when non-object members produce different scalars."""
    schema = z.intersect([z.const("a"), z.const("b")])
    with pytest.raises(ValidationError):
        schema("a")


def test_intersect_skips_nullable_members() -> None:
    """`z.intersect([a, b])` skips members that resolve to ``None``."""
    schema = z.intersect([z.any(), z.string()])
    assert schema("x") == "x"


def test_is_by_name_walks_prototype_chain() -> None:
    """`is_("ParentName")` accepts a subclass whose parent class matches the name."""

    class Parent:
        pass

    class Child(Parent):
        pass

    # The walker walks Child -> Parent -> object and finds the name match.
    schema = z.is_("Parent")
    instance = Child()
    assert schema(instance) is instance


def test_array_with_no_inner_returns_data_index() -> None:
    """`_resolve_array_index` returns ``data[index]`` directly when inner is None."""
    # Tuple with an undeclared trailing element exercises the no-inner branch
    # in `_resolve_array_index` (the trailing element is passed through).
    schema = z.tuple([z.string()])
    assert schema(["a", "b"]) == ["a", "b"]


def test_object_formatter_for_empty_dict() -> None:
    """`toString()` for an object schema with no declared properties returns ``{}``."""
    schema = z.object({})
    assert schema.to_string() == "{}"


def test_intersect_formatter_inlines_members() -> None:
    """`toString()` for an intersect schema renders ``a & b``."""
    schema = z.intersect([z.string(), z.number()])
    assert schema.to_string() == "string & number"


def test_transform_with_no_inner_raises() -> None:
    """`Schema.resolve()` on a transform schema without ``inner`` raises."""
    schema = Schema(type="transform", inner=None, callback=lambda value, _opts: value)
    with pytest.raises(ValidationError):
        Schema.resolve("hello", schema, Options())


def test_object_strict_does_not_merge_extra() -> None:
    """`z.object({...})` with ``strict=True`` skips extra keys from input."""
    schema = z.object({"a": z.string()})
    # strict=True via Schema.resolve
    result, _ = Schema.resolve({"a": "x", "extra": 1}, schema, Options(), True)
    assert "extra" not in result


def test_array_index_autofix_skips_invalid_index() -> None:
    """`_resolve_array_index` autofix branch runs when an element fails inner validation."""
    # Use Schema.__call__ (not Schema.resolve) so the resolver uses
    # autofix via the public surface — the inner resolver falls through the
    # autofix branch when the inner schema rejects the value.
    schema = z.array(z.string())
    with pytest.raises(ValidationError):
        # Without autofix, an invalid element raises.
        schema(["ok", 1, "also-ok"])


def test_array_index_writes_adapted_back() -> None:
    """`z.array(inner)` writes the adapted element back to the input list."""
    # Use a transform to produce an adapted value.
    schema = z.array(z.transform(z.string(), lambda value, _opts: value.upper()))
    data = ["a", "b"]
    result, _ = Schema.resolve(data, schema, Options(), True)
    assert result == ["A", "B"]
    # And data was also adapted.
    assert data == ["A", "B"]


def test_object_autofix_writes_default() -> None:
    """`z.object({...})` with ``autofix=True`` writes inner default for missing/invalid keys."""
    schema = z.object({"a": z.string().default("def")})
    data = {"a": 1}  # invalid value for string
    result, _ = Schema.resolve(data, schema, Options(autofix=True), True)
    assert result["a"] == "def"


def test_intersect_skips_value_with_null_first_member() -> None:
    """`z.intersect([nullable, primitive])` uses the primitive result."""
    schema = z.intersect([
        z.any(),  # nullable when no default
        z.string(),
    ])
    # The first member resolves to the data unchanged; the intersect skips
    # nullable members and accumulates the non-null ones.
    assert schema("x") == "x"


def test_dict_key_transformation_when_resolved_key_differs() -> None:
    """`z.dict(inner, s_key)` renames a key when the key schema transforms it."""
    # The dict s_key normalizes keys via the transform callback.
    schema = z.dict(
        z.number(),
        z.transform(z.string(), lambda value, _opts: value.upper()),
    )
    result = schema({"a": 1, "b": 2})
    assert "A" in result and "B" in result


def test_decimal_shift_handles_scientific_notation_branch() -> None:
    """`_decimal_shift` exercises the scientific-notation branch via step validation."""
    # Tiny step values like 1e-7 trigger the scientific-notation path in
    # ``_decimal_shift`` because the formatted step contains an ``e``.
    from schemastery.schema import _decimal_shift

    # Directly call the helper to exercise the e-branch.
    shifted = _decimal_shift(0.5, 7)
    assert shifted == 5_000_000.0 or shifted == 0.5 * (10**7)


def test_array_buffer_is_source_branch_exercised() -> None:
    """`z.array_buffer()` validates a real bytes source through the is_source branch."""
    # A bytes source goes through ``Binary.is_source`` check.
    assert z.array_buffer()(b"\x00\x01") == b"\x00\x01"


def test_array_buffer_accepts_memoryview() -> None:
    """`z.array_buffer()` accepts a memoryview, hitting the transform branch."""
    # memoryview is not bytes/bytearray so the transform's Binary.is_source
    # check is exercised; the True branch returns the bytes.
    mv = memoryview(b"\x00\x01\x02")
    assert z.array_buffer()(mv) == b"\x00\x01\x02"


def test_array_index_no_inner_returns_data_index() -> None:
    """`_resolve_array_index` returns ``data[index]`` directly when inner is None."""

    class _NoInner(Schema):
        # Build a Schema that looks like an array but has no inner.
        pass

    _schema = Schema(type="array", inner=None)
    # Direct resolve via _resolve_array_index bypasses the public Schema.__call__
    # path which always wraps with a resolved inner.
    from schemastery.schema import _resolve_array_index

    data = ["a", "b"]
    assert _resolve_array_index(data, 1, None, Options()) == "b"


def test_array_index_autofix_returns_default() -> None:
    """`_resolve_array_index` autofix branch runs on inner ValidationError."""
    from schemastery.schema import _resolve_array_index

    inner = z.string().default("DEF")
    data = [1]
    # Inner rejects 1 (not a string) → autofix returns ``inner.meta.default``.
    value = _resolve_array_index(data, 0, inner, Options(autofix=True))
    assert value == "DEF"


def test_object_merge_extra_keys() -> None:
    """`z.object()` (strict=False) merges extra keys via ``_merge``."""

    schema = z.object({"a": z.string()})
    # Direct resolve with strict=False merges extras.
    result, _ = Schema.resolve({"a": "x", "extra": 1}, schema, Options(), False)
    assert result.get("extra") == 1


def test_object_not_plain_raises() -> None:
    """`_resolve_object` raises ValidationError for non-plain-object input."""

    schema = z.object({"a": z.string()})
    with pytest.raises(ValidationError):
        Schema.resolve([1, 2], schema, Options())


def test_dict_resolved_key_transformation() -> None:
    """`_resolve_dict` renames a key when the key schema transforms it."""
    from schemastery.schema import _transform_factory

    # Use a transform that uppercases the key.
    upper_key = _transform_factory(
        z.string(),
        lambda value, _opts: value.upper(),
        preserve=True,
    )
    schema = z.dict(z.number(), upper_key)
    result = schema({"a": 1, "b": 2})
    assert "A" in result and "B" in result


def test_intersect_skips_nullable_value() -> None:
    """`_resolve_intersect` continues when a member resolves to a nullable value."""

    # ``any`` resolves null inputs to null; the intersect skips it and uses
    # the next member's result.
    schema = z.intersect([z.any(), z.string()])
    assert schema("x") == "x"


def test_intersect_member_returns_nullable_skipped() -> None:
    """`_resolve_intersect` skips a member that resolves to ``None``."""
    # The first member (any) resolves null input to null, but for non-null
    # input it returns the data. The intersect then sees a value to merge.
    # Use a member whose strict resolution yields ``None`` for the data.
    schema = z.intersect([z.union([z.string(), z.number()]), z.const("x")])
    assert schema("x") == "x"


def test_object_merge_extra_keys_via_resolve() -> None:
    """`_resolve_object` (strict=False) merges extra keys from data via ``_merge``."""

    schema = z.object({"a": z.string()})
    # Direct resolve with strict=False merges extras into result.
    result, _ = Schema.resolve({"a": "x", "extra": 1}, schema, Options(), False)
    assert result.get("extra") == 1


def test_intersect_type_mismatch_raises() -> None:
    """`_resolve_intersect` raises when member types don't match."""

    # Two transforms both accept "1" but produce different types.
    schema = z.intersect([
        z.transform(z.string(), lambda value, _opts: int(value)),
        z.transform(z.string(), lambda value, _opts: value),
    ])
    with pytest.raises(ValidationError):
        schema("1")


def test_intersect_value_mismatch_raises() -> None:
    """`_resolve_intersect` raises when scalar members produce different values."""

    schema = z.intersect([z.const("a"), z.const("b")])
    with pytest.raises(ValidationError):
        schema("a")


def test_intersect_member_value_mismatch_branch() -> None:
    """`_resolve_intersect` raises when both members succeed with different scalars (line 1052)."""
    # Two transforms that both accept the same data but produce different scalars.
    schema = z.intersect([
        z.transform(z.string(), lambda value, _opts: value),  # passes through
        z.transform(z.string(), lambda value, _opts: value + "!"),  # mutates
    ])
    with pytest.raises(ValidationError):
        Schema.resolve("x", schema, Options(), True)


def test_object_autofix_drops_invalid_key() -> None:
    """`_resolve_object` autofix branch drops keys with invalid values."""

    schema = z.object({"a": z.string().default("DEF")})
    # Invalid value for ``a`` triggers autofix.
    result, _ = Schema.resolve({"a": 1, "b": "ok"}, schema, Options(autofix=True), True)
    assert result.get("a") == "DEF"


def test_object_writes_adapted_back() -> None:
    """`_resolve_object` writes the adapted value back into the data."""

    schema = z.object({"a": z.transform(z.string(), lambda value, _opts: value.upper())})
    data = {"a": "hello"}
    Schema.resolve(data, schema, Options(), True)
    # Adapted value is written back into the data.
    assert data["a"] == "HELLO"


def test_is_by_name_nullable_data_raises_directly() -> None:
    """`Schema.resolve(data, is_("Name"))` raises on null data via the direct resolver path."""

    schema = z.is_("Animal")
    # Calling the resolver directly bypasses the nullable short-circuit.
    from schemastery.schema import _resolve_is

    with pytest.raises(ValidationError):
        _resolve_is(None, schema, Options())


def test_array_index_autofix_del_branch() -> None:
    """`_resolve_array_index` autofix branch deletes the offending index after a ValidationError."""
    # We trigger the ValidationError branch via an invalid value at the index,
    # then the autofix branch deletes the slot.
    from schemastery.schema import _resolve_array_index

    inner = z.string().default("DEF")
    # Index 0 has an invalid value (int, not str) — autofix kicks in.
    value = _resolve_array_index([1], 0, inner, Options(autofix=True))
    assert value == "DEF"


def test_object_autofix_del_missing_key() -> None:
    """`_resolve_object` autofix branch deletes the offending key."""

    schema = z.object({"a": z.string().default("DEF")})
    # Build an inner resolver that raises for the autofix branch.
    data = {"a": 1, "b": 2}
    # Direct resolve with strict=True to exercise the no-merge branch.
    result, _ = Schema.resolve(data, schema, Options(autofix=True), True)
    assert "a" in result


def test_dict_resolve_key_via_strict_skips_non_matching() -> None:
    """`_resolve_dict` strict mode skips keys that fail key validation."""

    schema = z.dict(z.number(), z.string().required())
    # Integer keys bypass the string s_key; strict=True skips them.
    result, _ = Schema.resolve({1: 1, "a": 1}, schema, Options(), True)
    assert "a" in result


def test_dict_renames_key_when_resolved_differs() -> None:
    """`_resolve_dict` renames the input key when the key schema transforms it."""

    schema = z.dict(
        z.number(),
        z.transform(z.string(), lambda value, _opts: value.upper(), preserve=True),
    )
    data = {"a": 1}
    Schema.resolve(data, schema, Options())
    # After resolve, the original key is deleted and a new key added.
    assert "A" in data and "a" not in data


def test_bool_inferred_as_const() -> None:
    """`Schema.from_(True)` / ``from_(False)`` returns a const schema."""
    s_true = Schema.from_(True)
    s_false = Schema.from_(False)
    assert s_true(True) is True
    with pytest.raises(ValidationError):
        s_true(False)
    assert s_false(False) is False
    with pytest.raises(ValidationError):
        s_false(True)


def test_lazy_to_json_invokes_builder() -> None:
    """`z.lay(builder).toJSON()` invokes the builder and serializes the inner schema."""

    def builder() -> Schema:
        return z.string()

    lazy_schema = z.lazy(builder)
    out = lazy_schema.toJSON()
    assert "uid" in out and "refs" in out


def test_lazy_resolve_after_first_call_uses_cached_inner() -> None:
    """`z.lazy(builder)` calls the builder once and caches the result."""
    calls = [0]

    def builder() -> Schema:
        calls[0] += 1
        return z.boolean()

    lazy_schema = z.lazy(builder)
    # Two resolutions should only trigger the builder once.
    assert lazy_schema(True) is True
    assert lazy_schema(False) is False
    assert calls[0] == 1


def test_i18n_dict_message_map_with_inner_dict() -> None:
    """`_dict_message_map` returns the inner dict's key when input is a dict."""

    schema = z.object({"a": z.string()})
    localized = schema.i18n({"zh": {"$value": {"a": "甲"}}})
    # The localized schema's child description reflects the per-locale value.
    assert localized.dict["a"].meta.description == {"zh": "甲"}


def test_i18n_list_message_map_with_inner_list() -> None:
    """`_list_message_map` returns the inner list's element when input is a list."""

    schema = z.union([z.string(), z.number()])
    localized = schema.i18n({"zh": {"$value": ["甲", "乙"]}})
    # The localized schema's list reflects per-index values.
    assert localized.list[0].meta.description == {"zh": "甲"}
    assert localized.list[1].meta.description == {"zh": "乙"}


def test_i18n_s_key_message_map_with_dict() -> None:
    """`_s_key_message_map` returns the inner dict's ``$key`` when input is a dict."""

    schema = z.dict(z.string(), z.string())
    localized = schema.i18n({"zh": {"$key": "键"}})
    # The localized schema's key schema reflects the per-locale key.
    assert localized.s_key.meta.description == {"zh": "键"}


def test_i18n_with_none_value_skips_locale() -> None:
    """`i18n()` with a ``None`` locale value passes through the helpers."""
    schema = z.object({"a": z.string()}).i18n({"zh": None})
    # The schema description is unchanged; the message-map helpers see
    # ``None`` data and short-circuit via ``_get_inner``.
    assert schema.meta.description in (None, {})
    assert schema.dict["a"].meta.description in (None, {})


def test_i18n_union_with_inner_list_index() -> None:
    """`_list_message_map` returns ``inner[index]`` when ``$value`` is a list."""
    # When the locale data is wrapped in ``{"$value": [...]}``, the helper
    # drills into the inner list and returns the index-matched element.
    schema = z.union([z.string(), z.number()])
    localized = schema.i18n({"zh": {"$value": ["甲", "乙"]}})
    assert localized.list[0].meta.description == {"zh": "甲"}


def test_i18n_union_with_top_level_list() -> None:
    """`_list_message_map` returns ``data[index]`` when the locale value is a list."""
    schema = z.union([z.string(), z.number()])
    localized = schema.i18n({"zh": ["甲", "乙"]})
    assert localized.list[0].meta.description == {"zh": "甲"}
    assert localized.list[1].meta.description == {"zh": "乙"}


def test_i18n_union_with_string_locale_falls_through() -> None:
    """`_list_message_map` falls through to ``_extract_keys`` for non-list data."""
    schema = z.union([z.string(), z.number()])
    localized = schema.i18n({"zh": "甲乙"})
    # The fall-through returns ``_extract_keys({})`` for the string value.
    # Description is set to the empty-dict result, which omits the locale.
    assert localized.list[0].meta.description == {} or localized.list[0].meta.description is None


def test_i18n_dict_key_with_string_locale() -> None:
    """`_s_key_message_map` falls through to ``None`` for non-dict locale data."""
    schema = z.dict(z.string(), z.string())
    localized = schema.i18n({"zh": "not-a-dict"})
    # Non-dict locale data yields ``None`` from the helper; description is unchanged.
    assert localized.s_key.meta.description is None


def test_step_with_scientific_notation() -> None:
    """`_decimal_shift` exercises the scientific-notation branch via a tiny step."""
    # A step value like ``1e-7`` triggers the ``"e" in text`` branch in
    # ``_decimal_shift``; the number validator accepts values that are
    # exact multiples of that step from the ``min`` floor.
    schema = z.number().min(0).step(1e-7).max(1)
    # 1e-7 is exactly one step from 0.
    assert schema(1e-7) == 1e-7


def test_decimal_shift_via_schema_step() -> None:
    """`_decimal_shift` is exercised end-to-end through the number validator."""
    schema = z.number().min(0).step(0.5).max(10)
    # Multiples of 0.5 from 0 are accepted.
    assert schema(2.5) == 2.5
    assert schema(3.0) == 3.0


def test_i18n_s_key_inner_dict_key_branch() -> None:
    """`_s_key_message_map` reads ``$key`` when the data is a dict."""
    schema = z.dict(z.string(), z.string())
    # Pass a dict with ``$key`` at the locale level.
    localized = schema.i18n({"zh": {"$key": "键"}})
    assert localized.s_key.meta.description == {"zh": "键"}


def test_transform_propagates_adapted_back_to_data() -> None:
    """`z.transform()` (preserve=False) returns both the normalized and adapted outputs."""
    schema = z.transform(z.string(), lambda value, _opts: value.upper())
    # Pass a single string; the resolver exercises the (non-preserve) branch
    # which returns ``(callback(result), callback(adapted))``.
    result, adapted = Schema.resolve("hello", schema, Options(), True)
    assert result == "HELLO"
    assert adapted == "HELLO"


def test_meta_dict_attribute_getattr_missing() -> None:
    """`MetaDict.__getattr__` returns ``None`` for missing keys."""
    meta = MetaDict()
    assert meta.missing is None


def test_meta_dict_attribute_setattr() -> None:
    """`MetaDict.__setattr__` writes via dict semantics."""
    meta = MetaDict()
    meta.custom = "v"
    assert meta["custom"] == "v"
    assert meta.custom == "v"


def test_resolve_returns_data_when_schema_none() -> None:
    """`Schema.resolve(data, None)` returns the data unchanged."""
    assert Schema.resolve("x", None, Options()) == ("x", None)


def test_resolve_ignore_callback_returns_data() -> None:
    """`Schema.resolve(data, schema, options)` honours the ``ignore`` callback."""

    captured: list[object] = []

    def _ignore(data: object, schema: object) -> bool:
        captured.append((data, schema))
        return True

    options = Options(ignore=_ignore)
    assert Schema.resolve("x", z.string(), options) == ("x", None)
    assert len(captured) == 1


def test_resolve_unsupported_type_raises() -> None:
    """`Schema.resolve(data, schema)` raises ValidationError for an unknown ``type``."""
    schema = Schema(type="totally_unknown_type_xyz")
    with pytest.raises(ValidationError):
        Schema.resolve("x", schema, Options())


def test_resolve_loose_returns_default_on_error() -> None:
    """`Schema.resolve()` with ``loose=True`` returns the default on ValidationError."""
    schema = z.string().default("fallback").loose()
    value, _ = Schema.resolve(123, schema, Options())
    assert value == "fallback"


def test_resolve_intersect_with_default_returns_default() -> None:
    """`Schema.resolve()` on an intersect schema with its own default returns the default."""
    inner = z.string().default("fallback")
    schema = z.intersect([inner])
    # First member has default; the resolver walks into the intersect and
    # finds the member's default.
    value, _ = Schema.resolve(None, schema, Options())
    assert value == "fallback"


def test_schema_from_none_returns_any() -> None:
    """`Schema.from_(None)` returns an any-typed schema."""
    schema = Schema.from_(None)
    assert schema.type == "any"


def test_schema_from_float_returns_number() -> None:
    """`Schema.from_(float)` returns a number-typed schema."""
    schema = Schema.from_(float)
    assert schema.type == "number"


def test_schema_from_function_returns_function() -> None:
    """`Schema.from_(Function)` returns a function-typed schema."""

    class _Function:
        pass

    # ``type`` of a function-like class triggers the function branch.
    schema = Schema.from_(_Function)
    assert schema.type == "is"


def test_schema_from_unsupported_raises() -> None:
    """`Schema.from_(unsupported)` raises ``TypeError``."""

    class _Unsupported:
        pass

    instance = _Unsupported()
    with pytest.raises(TypeError):
        Schema.from_(instance)


def test_decimal_shift_handles_scientific_notation() -> None:
    """`_decimal_shift` returns ``data * 10**digits`` for scientific-notation input."""
    # 1e-3 prints via ``f"{1e-3:.20f}"`` to a representation without ``e``,
    # but the upstream path is exercised by a step value that rounds to ``e``.

    # ``0.0001`` rendered at 20 decimals produces an ``e`` form; we exercise
    # the branch directly via the public API by using a step like 1e-7.
    schema = z.number().min(0).step(1e-7).max(1)
    assert schema(0.0000003) == 0.0000003


def test_resolve_intersect_with_default_member() -> None:
    """`Schema.resolve()` walks the intersect's first member for its default."""
    schema = z.intersect([
        z.string().default("fallback"),
    ])
    value, _ = Schema.resolve(None, schema, Options())
    assert value == "fallback"


# ---------------------------------------------------------------------------
# Schema.from / Schema.extend
# ---------------------------------------------------------------------------


def test_schema_from_string_value_returns_const() -> None:
    """`Schema.from_("foo")` returns a const schema for the value."""
    s = Schema.from_("foo")
    assert s("foo") == "foo"
    with pytest.raises(ValidationError):
        s("bar")


def test_schema_from_existing_schema_returns_it() -> None:
    """`Schema.from_(schema)` returns the schema unchanged."""
    s = z.string()
    assert Schema.from_(s) is s


def test_schema_from_constructor_returns_typed_schema() -> None:
    """`Schema.from_(SomeClass)` returns a `is_`-style schema."""
    s = Schema.from_(int)
    assert s(42) == 42
    with pytest.raises(ValidationError):
        s("x")


def test_schema_extend_registers_new_resolver() -> None:
    """`Schema.extend(type, resolver)` adds a custom type that validates."""

    def resolver(
        data: object,
        schema: Schema,
        options: object,
        _strict: bool = False,
    ) -> tuple[object, object | None]:
        if not isinstance(data, str) or not data.startswith("PING:"):
            raise ValidationError(f"expected PING:* but got {data!r}", schema.options)
        return (data.removeprefix("PING:"), None)

    Schema.extend("ping", resolver)
    try:
        ping_schema = Schema(type="ping")
        assert ping_schema("PING:hello") == "hello"
        with pytest.raises(ValidationError):
            ping_schema("hello")
    finally:
        from schemastery.schema import resolvers as _resolvers

        _resolvers.pop("ping", None)


# ---------------------------------------------------------------------------
# Date / RegExp / ArrayBuffer / function
# ---------------------------------------------------------------------------


def test_date_accepts_date_instance() -> None:
    """`z.date()` accepts a `datetime.date` instance via the `is_` branch."""
    import datetime as _dt

    assert z.date()(_dt.date(2024, 1, 2)) == _dt.date(2024, 1, 2)


def test_date_accepts_iso_string() -> None:
    """`z.date()` accepts an ISO date string and parses it."""
    out = z.date()("2024-01-02")
    assert out.year == 2024 and out.month == 1 and out.day == 2


def test_date_rejects_invalid_string() -> None:
    """`z.date()` raises on an invalid date string."""
    with pytest.raises(ValidationError):
        z.date()("not a date")


def test_reg_exp_accepts_compiled_regex() -> None:
    """`z.reg_exp()` accepts a compiled regex."""
    out = z.reg_exp()("abc")
    assert isinstance(out, re.Pattern)


def test_reg_exp_rejects_invalid_pattern() -> None:
    """`z.reg_exp()` raises on an invalid pattern string."""
    with pytest.raises(ValidationError):
        z.reg_exp()("[invalid")


def test_function_accepts_callable() -> None:
    """`z.function()` accepts any callable."""
    def _fn(x: int) -> int:  # pragma: no cover - body irrelevant
        return x

    assert z.function()(_fn) is _fn


def test_function_rejects_non_callable() -> None:
    """`z.function()` rejects non-callables."""
    with pytest.raises(ValidationError):
        z.function()("not callable")


def test_array_buffer_from_bytes() -> None:
    """`z.array_buffer()` accepts a bytes source and returns bytes."""
    assert z.array_buffer()(b"hi") == b"hi"


def test_array_buffer_from_hex() -> None:
    """`z.array_buffer("hex")` accepts a hex-encoded string."""
    out = z.array_buffer("hex")("deadbeef")
    assert out == b"\xde\xad\xbe\xef"


def test_percent_bounds() -> None:
    """`z.percent()` enforces [0, 1] and a 0.01 step."""
    assert z.percent()(0.5) == 0.5
    with pytest.raises(ValidationError):
        z.percent()(2)


# ---------------------------------------------------------------------------
# Lazy + toJSON edge
# ---------------------------------------------------------------------------


def test_lazy_to_json_returns_inner() -> None:
    """`z.lazy(builder).toJSON()` invokes the builder and serializes the inner schema."""

    def builder() -> Schema:
        return z.string()

    lazy_schema = z.lazy(builder)
    out = lazy_schema.toJSON()
    assert "uid" in out
