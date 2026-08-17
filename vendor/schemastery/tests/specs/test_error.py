"""Tests for `schemastery.error` — ValidationError, Options, Issue, format_path."""

from __future__ import annotations

from schemastery.error import Issue, Options, ValidationError, format_path


def test_options_default_path() -> None:
    """`Options()` defaults to an empty path, autofix=False, ignore=None."""
    opts = Options()
    assert opts.path == []
    assert opts.autofix is False
    assert opts.ignore is None


def test_options_copy_preserves_fields() -> None:
    """`Options.copy()` returns a detached copy."""
    original = Options(path=["a", 1], autofix=True, ignore=lambda _d, _s: False)
    cloned = original.copy()
    assert cloned.path == ["a", 1]
    assert cloned.autofix is True
    assert cloned.ignore is original.ignore
    # Detached: mutating the clone doesn't affect the original.
    cloned.path.append("b")
    assert original.path == ["a", 1]


def test_options_extend_appends_key() -> None:
    """`Options.extend(key)` returns a new Options with the key appended."""
    base = Options(path=["a"])
    extended = base.extend("b")
    assert extended.path == ["a", "b"]
    # Detached.
    assert base.path == ["a"]


def test_format_path_root_only() -> None:
    """Empty path renders as ``$``."""
    assert format_path([]) == "$"


def test_format_path_strips_leading_dot() -> None:
    """A leading ``.key`` is rendered without the leading dot."""
    assert format_path(["a", "b"]) == "$a.b"


def test_format_path_int_segment() -> None:
    """Integer segments render as ``[i]``."""
    assert format_path(["a", 1]) == "$a[1]"


def test_format_path_symbol_segment() -> None:
    """Symbol-like objects (with a ``name`` attr) render as ``[Symbol(name)]``."""

    class _Sym:
        name = "k"

    assert format_path([_Sym()]) == "$[Symbol(k)]"


def test_format_path_unknown_segment_falls_back() -> None:
    """Segments without a ``name`` attr are rendered via ``repr``."""

    class _Weird:
        def __repr__(self) -> str:
            return "<weird>"

    assert format_path([_Weird()]) == "$[<weird>]"


def test_validation_error_message_format() -> None:
    """ValidationError at a nested path prefixes the dotted path."""
    err = ValidationError("boom", Options(path=["a", 1]))
    assert str(err) == "$a[1] boom"


def test_validation_error_at_root_no_path_prefix() -> None:
    """ValidationError at the root path has no path prefix."""
    err = ValidationError("boom", Options())
    assert str(err) == "boom"


def test_validation_error_default_options() -> None:
    """ValidationError accepts ``None`` for options and uses defaults."""
    err = ValidationError("boom")
    assert str(err) == "boom"


def test_validation_error_is_true_for_self() -> None:
    """``ValidationError.is_`` returns ``True`` for ValidationError instances."""
    err = ValidationError("boom")
    assert ValidationError.is_(err) is True


def test_validation_error_is_false_for_others() -> None:
    """``ValidationError.is_`` returns ``False`` for non-ValidationError errors."""
    assert ValidationError.is_(ValueError("x")) is False
    assert ValidationError.is_(None) is False
    assert ValidationError.is_("not an error") is False
    assert ValidationError.is_(Exception("x")) is False


def test_issue_is_dataclass() -> None:
    """`Issue` is a dataclass carrying message + path."""
    issue = Issue("boom", path=["a", 1])
    assert issue.message == "boom"
    assert issue.path == ["a", 1]
