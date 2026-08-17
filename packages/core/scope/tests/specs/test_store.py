"""1:1 tests for `taiyi_core_scope.store` (mirrors `~/deepseek-harness/packages/core/scope/src/store.ts`)."""

from __future__ import annotations

from collections.abc import Callable

import pytest
from cordis import Context

from taiyi_core_scope.scope import bind_scope_parent
from taiyi_core_scope.store import AnonymousEntries, NamedEntries, ScopedLayers, ScopeLayer

# ---------------------------------------------------------------------------
# NamedEntries
# ---------------------------------------------------------------------------


def test_named_entries_insert_and_get() -> None:
    table = NamedEntries[str](lambda n: ValueError(f"dup {n}"))
    undo = table.insert("a", "alpha")
    assert table.get("a") == "alpha"
    assert table.has("a") is True
    undo()
    assert table.has("a") is False
    assert table.is_empty() is True


def test_named_entries_insert_rejects_duplicate() -> None:
    table = NamedEntries[str](lambda n: ValueError(f"dup {n}"))
    table.insert("a", "alpha")
    with pytest.raises(ValueError, match="dup a"):
        table.insert("a", "alpha2")


def test_named_entries_iteration_order() -> None:
    table = NamedEntries[int](lambda n: ValueError(n))
    for n in ("a", "b", "c"):
        table.insert(n, ord(n))
    keys = list(table.keys())
    values = list(table.values())
    assert keys == ["a", "b", "c"]
    assert values == [ord("a"), ord("b"), ord("c")]
    entries = list(table.entries())
    assert entries == [("a", ord("a")), ("b", ord("b")), ("c", ord("c"))]


def test_named_entries_undo_is_idempotent() -> None:
    table = NamedEntries[int](lambda n: ValueError(n))
    undo = table.insert("a", 1)
    undo()
    undo()  # second call is a no-op
    assert table.is_empty() is True


def test_named_entries_empty_state() -> None:
    table = NamedEntries[int](lambda n: ValueError(n))
    assert table.is_empty() is True
    assert list(table.keys()) == []
    assert list(table.values()) == []
    assert list(table.entries()) == []
    assert table.get("nope") is None
    assert table.has("nope") is False


# ---------------------------------------------------------------------------
# AnonymousEntries
# ---------------------------------------------------------------------------


def test_anonymous_entries_append_yields_independent_identity() -> None:
    table: AnonymousEntries[str] = AnonymousEntries()
    u1 = table.append("a")
    u2 = table.append("a")  # equal value but separate registration
    assert list(table.values()) == ["a", "a"]
    u1()
    assert list(table.values()) == ["a"]
    u2()
    assert table.is_empty() is True


def test_anonymous_entries_undo_is_idempotent() -> None:
    """Calling `_undo` twice on the same AnonymousEntries entry is a no-op."""
    table: AnonymousEntries[int] = AnonymousEntries()
    undo = table.append(1)
    undo()
    undo()  # idempotent: second call returns early
    assert table.is_empty() is True


def test_anonymous_entries_empty_state() -> None:
    table: AnonymousEntries[int] = AnonymousEntries()
    assert table.is_empty() is True
    assert list(table.values()) == []


def test_anonymous_entries_iteration_order() -> None:
    table: AnonymousEntries[int] = AnonymousEntries()
    table.append(1)
    table.append(2)
    table.append(3)
    assert list(table.values()) == [1, 2, 3]


# ---------------------------------------------------------------------------
# ScopedLayers
# ---------------------------------------------------------------------------


class _CountingLayer(ScopeLayer):
    """Minimal ScopeLayer impl: count entries."""

    def __init__(self) -> None:
        self.named: NamedEntries[int] = NamedEntries(lambda n: ValueError(n))
        self.anons: AnonymousEntries[int] = AnonymousEntries()
        self.created = 0
        self.disposed = 0

    def is_empty(self) -> bool:
        return self.named.is_empty() and self.anons.is_empty()

    def __repr__(self) -> str:  # pragma: no cover
        return f"_CountingLayer(n={sum(1 for _ in self.named.keys())})"


def _change_tracker(calls: list[int]) -> Callable[[], None]:
    """Module-level `on_change` body used by the `notify=True/False` tests."""

    def _tracker() -> None:
        calls.append(1)

    return _tracker


def test_scoped_layers_global_layer_is_eager() -> None:
    layers = ScopedLayers[_CountingLayer](lambda _: _CountingLayer(), lambda: None)
    assert layers.global_layer.is_empty() is True
    # peek with no arg returns None
    assert layers.peek(None) is None  # type: ignore[arg-type]


def test_scoped_layers_effect_attaches_to_context(make_ctx: Context) -> None:
    from taiyi_core_scope.scope import _SCOPE_KEY_ATTR  # noqa: PLC0415

    changes: list[int] = []

    def on_change() -> None:
        changes.append(1)

    layers = ScopedLayers[_CountingLayer](lambda _: _CountingLayer(), on_change)
    scope_key = object()
    tagged = make_ctx.extend({_SCOPE_KEY_ATTR: scope_key})
    layers.effect(tagged, lambda layer: layer.named.insert("a", 1), label="test")
    assert layers.peek(scope_key) is not None
    assert layers.peek(scope_key).named.get("a") == 1  # type: ignore[union-attr]


def test_scoped_layers_merge_global_with_chain() -> None:
    layers = ScopedLayers[_CountingLayer](lambda _: _CountingLayer(), lambda: None)
    # Populate global layer
    layers.global_layer.named.insert("a", 1)
    layers.global_layer.named.insert("b", 2)

    # A viewing scope with no overlays returns global values
    merged = layers.merge(None, lambda lyr: lyr.named)
    assert dict(merged) == {"a": 1, "b": 2}


def test_scoped_layers_merge_nearest_scope_wins() -> None:
    parent_key, child_key = object(), object()
    bind_scope_parent(child_key, parent_key)
    layers = ScopedLayers[_CountingLayer](lambda _: _CountingLayer(), lambda: None)

    # Global: a=1, b=2
    layers.global_layer.named.insert("a", 1)
    layers.global_layer.named.insert("b", 2)
    # Parent scope: a=10 (shadow)
    parent_layer = _CountingLayer()
    parent_layer.named.insert("a", 10)
    layers._scoped[parent_key] = parent_layer
    # Child scope: a=100 (shadow parent)
    child_layer = _CountingLayer()
    child_layer.named.insert("a", 100)
    layers._scoped[child_key] = child_layer

    merged = layers.merge(child_key, lambda lyr: lyr.named)
    # Nearest (child) wins
    assert merged["a"] == 100
    # Falls through to global
    assert merged["b"] == 2


def test_scoped_layers_chain_layers_nearest_last() -> None:
    parent_key, child_key = object(), object()
    bind_scope_parent(child_key, parent_key)
    layers = ScopedLayers[_CountingLayer](lambda _: _CountingLayer(), lambda: None)
    parent_layer = _CountingLayer()
    child_layer = _CountingLayer()
    layers._scoped[parent_key] = parent_layer
    layers._scoped[child_key] = child_layer
    chain = layers.chain_layers(child_key)
    assert len(chain) == 2
    # Farthest ancestor first, nearest last
    assert chain[0] is parent_layer
    assert chain[1] is child_layer


def test_scope_layer_is_empty_abstract_default() -> None:
    """`ScopeLayer.is_empty` raises NotImplementedError by default; subclasses override."""
    with pytest.raises(NotImplementedError):
        ScopeLayer().is_empty()


def test_scoped_layers_empty_scope_returns_global() -> None:
    layers = ScopedLayers[_CountingLayer](lambda _: _CountingLayer(), lambda: None)
    layers.global_layer.named.insert("a", 1)
    # `chainLayers(None)` returns []; merge yields global entries
    assert layers.chain_layers(None) == []  # type: ignore[arg-type]
    assert dict(layers.merge(None, lambda lyr: lyr.named)) == {"a": 1}


def test_scoped_layers_effect_global_layer(make_ctx: Context) -> None:
    """`effect()` on an untagged ctx writes to the global layer."""
    changes: list[int] = []

    def on_change() -> None:
        changes.append(1)

    layers = ScopedLayers[_CountingLayer](lambda _: _CountingLayer(), on_change)
    layers.effect(make_ctx, lambda layer: layer.named.insert("a", 1), label="global-write")
    # `peek(None)` returns None; the global layer is at `layers.global_layer`
    assert layers.global_layer.named.get("a") == 1
    assert changes == [1]


def test_scoped_layers_effect_reuses_existing_layer(make_ctx: Context) -> None:
    """`effect()` on a scope that already has a layer reuses it (not recreated)."""
    from taiyi_core_scope.scope import _SCOPE_KEY_ATTR  # noqa: PLC0415

    layers = ScopedLayers[_CountingLayer](lambda _: _CountingLayer(), lambda: None)
    scope_key = object()
    tagged = make_ctx.extend({_SCOPE_KEY_ATTR: scope_key})

    layers.effect(tagged, lambda layer: layer.named.insert("a", 1), label="first")
    existing = layers.peek(scope_key)
    layers.effect(tagged, lambda layer: layer.named.insert("b", 2), label="second")
    after = layers.peek(scope_key)
    assert existing is after
    assert after.named.get("a") == 1  # type: ignore[union-attr]
    assert after.named.get("b") == 2  # type: ignore[union-attr]


def test_scoped_layers_effect_rolls_back_on_action_exception(make_ctx: Context) -> None:
    """If `action` raises, the freshly-created scope overlay is removed."""
    from taiyi_core_scope.scope import _SCOPE_KEY_ATTR  # noqa: PLC0415

    layers = ScopedLayers[_CountingLayer](lambda _: _CountingLayer(), lambda: None)
    scope_key = object()
    tagged = make_ctx.extend({_SCOPE_KEY_ATTR: scope_key})

    def _boom(layer: _CountingLayer) -> Callable[[], None]:
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        layers.effect(tagged, _boom, label="bad")
    assert layers.peek(scope_key) is None


def test_scoped_layers_effect_action_exception_keeps_existing_layer(make_ctx: Context) -> None:
    """If `action` raises for an EXISTING layer (not freshly created), keep it."""
    from taiyi_core_scope.scope import _SCOPE_KEY_ATTR  # noqa: PLC0415

    layers = ScopedLayers[_CountingLayer](lambda _: _CountingLayer(), lambda: None)
    scope_key = object()
    tagged = make_ctx.extend({_SCOPE_KEY_ATTR: scope_key})

    def _seed(layer: _CountingLayer) -> Callable[[], None]:
        layer.named.insert("seed", 0)
        return lambda: None

    # Seed an entry so the layer is non-empty and "existing".
    layers.effect(tagged, _seed, label="seed")
    existing = layers.peek(scope_key)

    def _boom(layer: _CountingLayer) -> Callable[[], None]:  # noqa: ARG001
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        layers.effect(tagged, _boom, label="bad")
    # The pre-existing non-empty layer survives.
    assert layers.peek(scope_key) is existing


def test_scoped_layers_effect_dispose_releases_scope(make_ctx: Context) -> None:
    """`effect()` returns a disposer; calling it removes the scope overlay."""
    from taiyi_core_scope.scope import _SCOPE_KEY_ATTR  # noqa: PLC0415

    layers = ScopedLayers[_CountingLayer](lambda _: _CountingLayer(), lambda: None)
    scope_key = object()
    tagged = make_ctx.extend({_SCOPE_KEY_ATTR: scope_key})
    dispose = layers.effect(
        tagged, lambda layer: layer.named.insert("a", 1), label="dispose-test"
    )
    assert layers.peek(scope_key) is not None
    dispose()
    assert layers.peek(scope_key) is None


def test_scoped_layers_effect_dispose_global_noop(make_ctx: Context) -> None:
    """The global layer has no entry to remove from `_scoped`."""
    layers = ScopedLayers[_CountingLayer](lambda _: _CountingLayer(), lambda: None)
    dispose = layers.effect(
        make_ctx, lambda layer: layer.named.insert("a", 1), label="global-dispose"
    )
    dispose()
    # The global layer still exists (it was never in `_scoped`).
    assert layers.global_layer.is_empty() is True


def test_scoped_layers_effect_with_notify_false(make_ctx: Context) -> None:
    """`notify=False` skips the change notification — callback must never run."""
    from taiyi_core_scope.scope import _SCOPE_KEY_ATTR  # noqa: PLC0415

    calls: list[int] = []
    layers = ScopedLayers[_CountingLayer](lambda _: _CountingLayer(), _change_tracker(calls))
    scope_key = object()
    tagged = make_ctx.extend({_SCOPE_KEY_ATTR: scope_key})

    def _action(layer: _CountingLayer) -> Callable[[], None]:
        layer.named.insert("a", 1)
        return lambda: None

    # Without notify, on_change is NOT called when seeding, NOR when disposing.
    dispose = layers.effect(tagged, _action, label="quiet", notify=False)
    dispose()
    assert calls == []


def test_scoped_layers_effect_notify_true_calls_on_change(make_ctx: Context) -> None:
    """`notify=True` (default) calls `on_change` on both seed and dispose."""
    from taiyi_core_scope.scope import _SCOPE_KEY_ATTR  # noqa: PLC0415

    calls: list[int] = []
    layers = ScopedLayers[_CountingLayer](lambda _: _CountingLayer(), _change_tracker(calls))
    scope_key = object()
    tagged = make_ctx.extend({_SCOPE_KEY_ATTR: scope_key})

    def _action(layer: _CountingLayer) -> Callable[[], None]:
        layer.named.insert("a", 1)
        return lambda: None

    dispose = layers.effect(tagged, _action, label="loud")
    # Seed triggers notify=True (default).
    assert calls == [1]
    # Dispose also triggers notify.
    dispose()
    assert calls == [1, 1]
