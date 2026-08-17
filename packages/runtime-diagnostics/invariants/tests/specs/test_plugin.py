"""Tests for `taiyi_runtime_diagnostics_invariants.plugin` — the cordis plugin entry."""

from __future__ import annotations

from collections.abc import Callable

import pytest
from cordis import Context, Plugin

from taiyi_runtime_diagnostics_invariants.plugin import (
    PACKAGE_NAME,
    VENDOR_INVARIANT_MODULES,
    list_installed_vendors,
    setup,
)


def test_setup_is_a_plugin_instance() -> None:
    """The exported entry is a `cordis.Plugin`."""
    assert isinstance(setup, Plugin)
    assert setup.name == "runtime-diagnostics-invariants"


def test_setup_runs_against_a_fresh_context(make_ctx) -> None:
    """`setup(ctx, config)` registers `InvariantRegistry` under `ctx.invariants`."""
    dispose = await_setup(make_ctx, {})
    registry = make_ctx.invariants  # type: ignore[attr-defined]
    from taiyi_runtime_diagnostics_invariants import InvariantRegistry

    assert isinstance(registry, InvariantRegistry)
    dispose()


def test_setup_loads_vendor_invariants(make_ctx) -> None:
    """After setup, every installed vendor's invariant module is registered."""
    from taiyi_runtime_diagnostics_invariants.plugin import _short_name

    dispose = await_setup(make_ctx, {})
    registry = make_ctx.invariants  # type: ignore[attr-defined]
    installed = list_installed_vendors()

    for vendor in installed:
        # Each installed vendor surfaces under its canonical name (the module
        # root, not its dotted path).
        short = _short_name(vendor)
        assert short in registry, f"vendor {vendor!r} not registered"
    dispose()


def test_setup_honors_package_blocklist(make_ctx) -> None:
    """A `package_blocklist` config prevents matching vendors from loading."""
    installed = list_installed_vendors()
    if not installed:
        pytest.skip("no installed vendors in this environment")
    target = installed[0].split(".")[-1]
    dispose = await_setup(make_ctx, {"package_blocklist": [f"^{target}$"]})
    registry = make_ctx.invariants  # type: ignore[attr-defined]
    assert target not in registry
    dispose()


def test_setup_honors_enabled_false(make_ctx) -> None:
    """`enabled=False` disables vendor registration but keeps the service alive."""
    dispose = await_setup(make_ctx, {"enabled": False})
    registry = make_ctx.invariants  # type: ignore[attr-defined]
    # Service is installed and reachable...
    assert registry.enabled is False
    # ...but no vendors were registered.
    assert registry.names() == []
    dispose()


def test_setup_dispose_releases_invariants(make_ctx) -> None:
    """After dispose, `ctx.invariants` is no longer reachable."""
    dispose = await_setup(make_ctx, {})
    registry = make_ctx.invariants  # type: ignore[attr-defined]
    assert registry.names()  # something is registered
    dispose()
    with pytest.raises(AttributeError):
        _ = make_ctx.invariants  # type: ignore[attr-defined]


def test_setup_dispose_is_idempotent(make_ctx) -> None:
    """Calling the disposer twice does not raise."""
    dispose = await_setup(make_ctx, {})
    dispose()
    dispose()  # second call must be a safe no-op


def test_setup_can_be_called_as_a_plain_async_function(make_ctx) -> None:
    """`setup.setup(ctx, config)` works outside the cordis plugin runner."""
    import asyncio

    async def _runner() -> None:
        dispose = await setup.setup(make_ctx, {})
        dispose()

    asyncio.run(_runner())


def test_package_name_constant() -> None:
    """`PACKAGE_NAME` matches the upstream package convention."""
    assert PACKAGE_NAME == "@deepseek-ai/dsh-invariants"


def test_vendor_module_listing_is_sorted_and_unique() -> None:
    """`VENDOR_INVARIANT_MODULES` is a tuple of unique, sorted module paths."""
    assert isinstance(VENDOR_INVARIANT_MODULES, tuple)
    assert len(VENDOR_INVARIANT_MODULES) == len(set(VENDOR_INVARIANT_MODULES))
    assert list(VENDOR_INVARIANT_MODULES) == sorted(VENDOR_INVARIANT_MODULES)


def test_short_name_handles_module_paths() -> None:
    """`_short_name` strips the trailing `.invariant` segment when present."""
    from taiyi_runtime_diagnostics_invariants.plugin import _short_name

    assert _short_name("cordis.invariant") == "cordis"
    assert _short_name("taiyi_core_scope.invariant") == "taiyi_core_scope"
    # When the trailing segment isn't "invariant", the last segment wins.
    assert _short_name("foo.bar.baz") == "baz"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def await_setup(ctx: Context, config: object) -> Callable[[], None]:
    """Await `setup.setup(ctx, config)` from a sync test."""
    import asyncio

    return asyncio.run(setup.setup(ctx, config))
