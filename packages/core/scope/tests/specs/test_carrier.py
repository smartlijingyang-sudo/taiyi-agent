"""Tests for `taiyi_core_scope.carrier` helpers (is_scope_carrier, carrier_key_of)."""

from __future__ import annotations

from cordis import Context

from taiyi_core_scope.carrier import carrier_key_of, is_scope_carrier
from taiyi_core_scope.scope import scope_target


def test_is_scope_carrier_true_for_scope_target(make_ctx: Context) -> None:
    carrier = scope_target(object(), object())
    assert is_scope_carrier(carrier) is True


def test_is_scope_carrier_false_for_plain(make_ctx: Context) -> None:
    for v in (None, 42, "s", object(), [], {}):
        assert is_scope_carrier(v) is False


def test_carrier_key_of_returns_key_when_keyed(make_ctx: Context) -> None:
    key = object()
    carrier = scope_target(object(), key)
    assert carrier_key_of(carrier) is key


def test_carrier_key_of_returns_none_when_unkeyed(make_ctx: Context) -> None:
    carrier = scope_target(object(), None)
    assert carrier_key_of(carrier) is None


def test_carrier_key_of_returns_none_for_non_carrier(make_ctx: Context) -> None:
    for v in (None, 42, object()):
        assert carrier_key_of(v) is None
