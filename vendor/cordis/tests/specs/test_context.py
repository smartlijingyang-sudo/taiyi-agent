"""Tests for `cordis.context.Context` — DI container, scope, isolate, fork."""

from __future__ import annotations

import asyncio

import pytest

from cordis.context import Context, Hook, dispose, hook, ready


def test_ctx_provide_and_inject(make_ctx):
    """`provide` registers a value, `inject` retrieves it."""
    ctx = make_ctx()
    ctx.provide("foo", 1)
    assert ctx.inject("foo") == 1


def test_ctx_inject_missing_raises(make_ctx):
    """Missing keys (no default) raise `KeyError`."""
    ctx = make_ctx()
    with pytest.raises(KeyError):
        ctx.inject("missing")


def test_ctx_inject_with_default(make_ctx):
    """A default is returned when the key is not provided."""
    ctx = make_ctx()
    assert ctx.inject("missing", default="fallback") == "fallback"
    ctx.provide("present", "value")
    assert ctx.inject("present", default="fallback") == "value"


def test_ctx_dispose_lifecycle(make_ctx):
    """After disposal, `provide` raises; further dispose() is a no-op."""
    ctx = make_ctx()
    ctx.provide("foo", 1)
    assert ctx.inject("foo") == 1

    asyncio.run(ctx.dispose())
    assert ctx.state_disposed is True

    with pytest.raises(RuntimeError):
        ctx.provide("foo2", 2)

    # Idempotent.
    asyncio.run(ctx.dispose())
    assert ctx.state_disposed is True


def test_ctx_dispose_runs_disposers(make_ctx):
    """Disposers registered via `provide(..., dispose=cb)` are called on dispose."""
    calls: list[str] = []

    async def _go():
        ctx = make_ctx()
        ctx.provide("a", 1, dispose=lambda: calls.append("a"))
        ctx.provide("b", 2, dispose=lambda: calls.append("b"))
        await ctx.dispose()

    asyncio.run(_go())
    # LIFO: reverse registration order.
    assert calls == ["b", "a"]


def test_ctx_dispose_lifo_await(make_ctx):
    """Async disposers (awaitables) are awaited during dispose."""
    calls: list[str] = []

    async def _async_disp(label: str) -> None:
        calls.append(f"start:{label}")
        await asyncio.sleep(0)
        calls.append(f"end:{label}")

    async def _go():
        ctx = make_ctx()
        ctx.provide("a", 1, dispose=lambda: _async_disp("a"))
        ctx.provide("b", 2, dispose=lambda: _async_disp("b"))
        await ctx.dispose()

    asyncio.run(_go())
    assert calls == ["start:b", "end:b", "start:a", "end:a"]


def test_ctx_isolate_isolates_state(make_ctx):
    """`isolate` runs the callback in an isolated child; parent's bindings are unchanged."""
    parent = make_ctx()

    def setup(child: Context) -> None:
        child.provide("foo", "isolated")

    result = parent.isolate("scope-x", setup)
    assert result is None  # nothing returned

    # Parent did not absorb the child binding.
    with pytest.raises(KeyError):
        parent.inject("foo")


def test_ctx_isolate_returns_sync_result(make_ctx):
    """Sync callback return value is returned to the caller."""
    parent = make_ctx()
    assert parent.isolate("x", lambda c: "sync-result") == "sync-result"


def test_ctx_isolate_runs_async_callback(make_ctx):
    """Async callback gets awaited by the isolate harness."""
    parent = make_ctx()

    async def task(c: Context) -> str:
        return "async-ok"

    coro = parent.isolate("async", task)
    # Should return a coroutine, awaiting it yields the result.
    result = asyncio.run(coro)
    assert result == "async-ok"


def test_ctx_fork_returns_child(make_ctx):
    """`fork` returns a child that can have its own bindings without affecting parent."""
    parent = make_ctx()
    child = parent.fork()
    assert isinstance(child, Context)
    assert child is not parent

    child.provide("only-child", 42)
    assert child.inject("only-child") == 42
    with pytest.raises(KeyError):
        parent.inject("only-child")


def test_ctx_fork_inherits_parent_bindings(make_ctx):
    """Child contexts can read bindings from ancestors."""
    parent = make_ctx()
    parent.provide("foo", "from-parent")
    child = parent.fork()
    assert child.inject("foo") == "from-parent"


def test_ctx_child_provide_shadows_parent(make_ctx):
    """Re-providing in a child does not affect parent (parent shadow remains)."""
    parent = make_ctx()
    parent.provide("foo", "parent")
    child = parent.fork()
    child.provide("foo", "child")
    assert child.inject("foo") == "child"
    assert parent.inject("foo") == "parent"


def test_ctx_scope_nearest_overrides(make_ctx):
    """`scope` overrides active binding resolution with the nearest in-scope value."""
    ctx = make_ctx()
    ctx.provide("foo", "outer")

    async def _go():
        async with ctx.scope("x") as x_ctx:
            x_ctx.provide("foo", "inner")
            # The scoped value beats the outer one because it's the active scope.
            assert x_ctx.inject("foo") == "inner"
        # Outside the scope, outer value is visible again.
        assert ctx.inject("foo") == "outer"

    asyncio.run(_go())


def test_ctx_scope_releases_on_exit(make_ctx):
    """Exiting a scope disposes disposers registered inside the scope."""
    log: list[str] = []

    async def _go():
        ctx = make_ctx()
        ctx.provide("base", 1)
        async with ctx.scope("nested") as scoped:
            scoped.provide("temp", "x", dispose=lambda: log.append("temp-disposed"))
            # Still alive inside the scope.
            assert log == []
        # After exit, disposer fired.
        assert log == ["temp-disposed"]

    asyncio.run(_go())


def test_ctx_root_attribute(make_ctx):
    """Each fork's `root` points at the same root context."""
    root = make_ctx()
    child1 = root.fork()
    child2 = root.fork()
    grandchild = child1.fork()
    assert root.root is root
    assert child1.root is root
    assert child2.root is root
    assert grandchild.root is root


def test_ctx_ancestor_helper_true(make_ctx):
    """`_is_ancestor_of` is true for direct ancestors."""
    root = make_ctx()
    child = root.fork()
    grandchild = child.fork()
    assert root._is_ancestor_of(child) is True  # noqa: SLF001 — internal helper
    assert root._is_ancestor_of(grandchild) is True  # noqa: SLF001
    assert child._is_ancestor_of(grandchild) is True  # noqa: SLF001


def test_ctx_ancestor_helper_false(make_ctx):
    """`_is_ancestor_of` is false for siblings and self."""
    root = make_ctx()
    a = root.fork()
    b = root.fork()
    assert a._is_ancestor_of(b) is False  # noqa: SLF001
    assert a._is_ancestor_of(root) is False  # noqa: SLF001


def test_ctx_scope_descendant_true_and_false(make_ctx):
    """`_is_scope_descendant` matches same root or descendants; false otherwise."""
    root = make_ctx()
    scoped = Context(parent=root, root=root.root, isolation_label="lab")
    deep = Context(parent=scoped, root=root.root, isolation_label="deep")
    sibling = Context(parent=root, root=root.root, isolation_label="sib")
    assert scoped._is_scope_descendant(scoped, deep) is True  # noqa: SLF001
    assert scoped._is_scope_descendant(scoped, scoped) is True  # noqa: SLF001
    assert scoped._is_scope_descendant(scoped, sibling) is False  # noqa: SLF001


def test_ctx_local_lookup_active_scope_match(make_ctx):
    """Reading via an active scope child returns the scope-bound value."""
    parent = make_ctx()
    parent.provide("foo", "parent")

    async def _go():
        async with parent.scope("s") as s_ctx:
            s_ctx.provide("foo", "scoped")
            assert parent.inject("foo") == "scoped"
            assert s_ctx.inject("foo") == "scoped"

    asyncio.run(_go())


def test_ctx_local_lookup_scope_descendant(make_ctx):
    """Descendants of the active scope are honored by `inject`."""
    parent = make_ctx()
    parent.provide("foo", "outer")

    async def _go():
        async with parent.scope("s") as s_ctx:
            child_of_scope = s_ctx.fork()
            child_of_scope.provide("foo", "deeper")
            assert parent.inject("foo") == "deeper"

    asyncio.run(_go())


def test_ctx_inject_after_dispose_uses_own_bindings(make_ctx):
    """Disposal does not retroactively erase provided values; only mutators are blocked."""
    ctx = make_ctx()
    ctx.provide("foo", "value")
    asyncio.run(ctx.dispose())
    # Inject on a disposed context returns the value already provided before disposal.
    assert ctx.inject("foo") == "value"


# --------------------------------------------------------------------------
# Module-level placeholder functions (coverage)
# --------------------------------------------------------------------------


def test_hook_factory_raises():
    """`hook()` is a legacy placeholder and raises `NotImplementedError`."""
    with pytest.raises(NotImplementedError):
        hook(lambda: None)


def test_ready_stub_raises():
    """`ready()` is a placeholder until the Event module fills it in."""
    with pytest.raises(NotImplementedError):
        ready(None)  # type: ignore[arg-type]


def test_dispose_stub_raises():
    """`dispose()` module-level stub raises `NotImplementedError`."""
    with pytest.raises(NotImplementedError):
        dispose(None)  # type: ignore[arg-type]


def test_hook_slot_class(make_ctx):
    """`Hook` slots are populated via constructor (for parity coverage)."""
    ctx = make_ctx()
    fn = lambda *a, **k: None  # noqa: E731
    h = Hook(ctx, fn)
    assert h.ctx is ctx
    assert h.callback is fn


def test_ctx_root_init_explicit():
    """The root context can be created without a parent (`root` defaults to self)."""
    ctx = Context()
    assert ctx.root is ctx
    assert ctx.parent is None


def test_ctx_inject_scope_no_match(make_ctx):
    """When the active scope has no binding, `inject` falls back to the parent chain."""
    parent = make_ctx()
    parent.provide("foo", "outer")

    async def _go():
        async with parent.scope("s") as s_ctx:
            # Active scope `s_ctx` has no `foo` binding; should fall back to parent's.
            assert parent.inject("foo") == "outer"
            assert s_ctx.inject("foo") == "outer"

    asyncio.run(_go())


def test_ctx_inject_active_is_self(make_ctx):
    """`inject` skips the local_lookup fast path when the active ctx is `self`."""
    ctx = make_ctx()
    ctx.provide("foo", "self-value")

    async def _go():
        async with ctx.scope("s") as s_ctx:
            # Active = s_ctx, but we call inject on a forked child whose active
            # ancestor is the active scope. We want inject on s_ctx itself to
            # skip the local_lookup branch (active is self in that lookup).
            assert s_ctx.inject("foo") == "self-value"

    asyncio.run(_go())


def test_ctx_inject_active_not_descendant(make_ctx):
    """If the active context is not a descendant, skip the local_lookup branch.

    Two sibling forks; both have an "active" — we ask inject on the *other*
    fork and confirm the local_lookup fast path is skipped (we tested by
    getting the right answer).
    """
    root = make_ctx()
    a = root.fork()
    b = root.fork()
    root.provide("shared", "from-root")

    async def _go():
        async with a.scope("a-scope") as a_sc:
            a_sc.provide("only-a", 1)
            # `b.inject` is called while `a_sc` is active.
            # `a` (and a_sc) are not ancestors of `b`, so the local_lookup fast path
            # is skipped; `b.inject` falls through to `_inject_chain`.
            assert b.inject("only-a", default="missing") == "missing"
            assert b.inject("shared") == "from-root"

    asyncio.run(_go())


def test_ctx_inject_disposed_state_skips_lookup(make_ctx):
    """On a disposed context, `inject` skips the active-scope lookup."""
    ctx = make_ctx()
    ctx.provide("foo", "kept")

    async def _go():
        async with ctx.scope("s") as s_ctx:
            s_ctx.provide("foo", "scoped")
            await ctx.dispose()
            # Even though `s_ctx` is active and has `foo`, we read `kept` because
            # the fast path is skipped on a disposed ctx.
            assert ctx.inject("foo") == "kept"

    asyncio.run(_go())


def test_ctx_walk_local_returns_missing_when_no_descendants(make_ctx):
    """`_walk_local` returns _MISSING when no descendants carry the key."""
    root = make_ctx()

    async def _go():
        async with root.scope("s") as s_ctx:
            # No descendants of s_ctx, no key in own.
            # Reading a key via s_ctx.inject should NOT find it
            with pytest.raises(KeyError):
                s_ctx.inject("absent")

    asyncio.run(_go())


def test_ctx_walk_local_descendant_match(make_ctx):
    """`_walk_local` finds the key when a descendant (fork) provides it."""
    root = make_ctx()

    async def _go():
        async with root.scope("s") as s_ctx:
            fork = s_ctx.fork()
            fork.provide("nested", "from-fork")
            # Reading `nested` should walk the fork tree.
            assert s_ctx.inject("nested") == "from-fork"

    asyncio.run(_go())


def test_ctx_scope_cm_without_enter(make_ctx):
    """`__aexit__` is a no-op when called without a prior `__aenter__`."""
    root = make_ctx()
    cm = root.scope("never-entered")

    async def _go():
        # Don't enter, just exit. Should not raise.
        await cm.__aexit__(None, None, None)

    asyncio.run(_go())


def test_ctx_scope_cm_scoped_property(make_ctx):
    """The `scoped` property exposes the underlying scope Context."""
    root = make_ctx()
    cm = root.scope("expose")

    async def _go():
        async with cm as s_ctx:
            assert cm.scoped is s_ctx

    asyncio.run(_go())


def test_ctx_isolate_label_reused_in_scope(make_ctx):
    """A scope using the same label as an existing isolate re-uses the scope child."""
    root = make_ctx()

    def setup(child: Context) -> None:
        child.provide("shared", "via-isolate")

    root.isolate("label-x", setup)

    async def _go():
        async with root.scope("label-x") as scoped:
            assert scoped.inject("shared") == "via-isolate"

    asyncio.run(_go())


def test_ctx_local_lookup_direct_no_active(make_ctx):
    """`_local_lookup` returns the module-level `_MISSING` sentinel."""
    from cordis.context import _MISSING

    ctx = make_ctx()
    # No scope is active → _active_ctx.get() is None → _local_lookup returns _MISSING.
    assert ctx._local_lookup("anything") is _MISSING  # type: ignore[attr-defined]


def test_ctx_walk_local_skips_empty_descendants(make_ctx):
    """`_walk_local` continues iterating when a descendant has no match."""
    root = make_ctx()

    async def _go():
        async with root.scope("s") as s_ctx:
            s_ctx.fork()  # empty descendant so _walk_local must iterate over it
            fork2 = s_ctx.fork()
            # fork2 has the key; walk must continue past the empty fork1.
            fork2.provide("bar", "from-fork2")
            assert s_ctx.inject("bar") == "from-fork2"

    asyncio.run(_go())
