"""Tests for the `InvariantRegistry` service and the invariant package surface.

Mirrors the upstream `@deepseek-ai/dsh-invariants` semantics: a registry
holding per-vendor invariant surfaces plus a configurable allow/block
regex filter, an :class:`InvariantError` failure type, and an
``assert_invariant`` test hook that registers + immediately runs a check.
"""

from __future__ import annotations

import pytest

from taiyi_runtime_diagnostics_invariants import (
    InvariantError,
    InvariantRegistry,
    assert_invariant,
    compile_patterns,
)
from taiyi_runtime_diagnostics_invariants.invariant import (
    InvariantError as InvariantErrorBarrel,
)
from taiyi_runtime_diagnostics_invariants.invariant import (
    InvariantRegistry as InvariantRegistryBarrel,
)
from taiyi_runtime_diagnostics_invariants.invariant import (
    assert_invariant as assert_invariant_barrel,
)

# ---------------------------------------------------------------------------
# Barrel / package surface
# ---------------------------------------------------------------------------


def test_public_surface_is_re_exported_by_invariant_barrel() -> None:
    """`taiyi_runtime_diagnostics_invariants.invariant` mirrors the top-level API."""
    assert InvariantError is InvariantErrorBarrel
    assert InvariantRegistry is InvariantRegistryBarrel
    assert assert_invariant is assert_invariant_barrel


def test_compile_patterns_returns_matching_regexes() -> None:
    """Compiled patterns search the package name."""
    patterns = compile_patterns("package_allowlist", ["^cordis$", "^loader$"])
    assert len(patterns) == 2
    assert patterns[0].search("cordis")
    assert not patterns[0].search("loader")
    assert patterns[1].search("loader")


def test_compile_patterns_rejects_blank_entry() -> None:
    """Entries with whitespace or empty strings are rejected."""
    with pytest.raises(ValueError, match="non-blank"):
        compile_patterns("package_allowlist", ["   "])
    with pytest.raises(ValueError, match="non-blank"):
        compile_patterns("package_allowlist", [" leading"])


def test_compile_patterns_rejects_duplicates() -> None:
    """Duplicate regex sources are rejected."""
    with pytest.raises(ValueError, match="duplicate"):
        compile_patterns("package_allowlist", ["^x$", "^x$"])


def test_compile_patterns_rejects_invalid_regex() -> None:
    """Invalid regex sources are rejected."""
    with pytest.raises(ValueError, match="invalid regex"):
        compile_patterns("package_allowlist", ["["])


# ---------------------------------------------------------------------------
# InvariantError
# ---------------------------------------------------------------------------


def test_invariant_error_carries_code_and_package_name() -> None:
    """`InvariantError.code` is `'INVARIANT'`; `packageName` matches constructor."""
    err = InvariantError("cordis", "must be frozen")
    assert err.code == "INVARIANT"
    assert err.package_name == "cordis"
    assert err.name == "InvariantError"
    assert 'invariant violated by "cordis"' in str(err)
    assert "must be frozen" in str(err)


# ---------------------------------------------------------------------------
# InvariantRegistry selection
# ---------------------------------------------------------------------------


def _make_registry(**config) -> InvariantRegistry:
    """Build an `InvariantRegistry` without wiring it into a Context."""
    from cordis import Context

    ctx = Context()
    return InvariantRegistry(ctx, **config)


def test_registry_selected_allows_when_disabled_is_false() -> None:
    """`enabled=False` rejects every package."""
    reg = _make_registry(enabled=False)
    assert reg.selected("anything") is False


def test_registry_selected_honors_allowlist() -> None:
    """Empty allowlist admits everything; non-empty allowlist filters."""
    reg = _make_registry(package_allowlist=["^cordis$"])
    assert reg.selected("cordis") is True
    assert reg.selected("loader") is False


def test_registry_selected_honors_blocklist() -> None:
    """Blocklist drops matching packages regardless of allowlist."""
    reg = _make_registry(
        package_allowlist=["^.*$"],
        package_blocklist=["^cordis$"],
    )
    assert reg.selected("loader") is True
    assert reg.selected("cordis") is False


# ---------------------------------------------------------------------------
# InvariantRegistry register / unregister
# ---------------------------------------------------------------------------


def test_registry_register_accepts_valid_package_name() -> None:
    """A valid package name stores the surface and returns a disposer."""
    reg = _make_registry()
    surface = object()
    dispose = reg.register("cordis", surface)
    assert reg.get("cordis") is surface
    assert "cordis" in reg
    assert "cordis" in list(reg.names())
    dispose()
    assert reg.get("cordis") is None
    assert "cordis" not in reg


def test_registry_register_rejects_blank_or_whitespace_name() -> None:
    """Blank / whitespace package names are rejected."""
    reg = _make_registry()
    with pytest.raises(ValueError, match="non-blank"):
        reg.register("", object())
    with pytest.raises(ValueError, match="non-blank"):
        reg.register("   ", object())
    with pytest.raises(ValueError, match="non-blank"):
        reg.register("a b", object())


def test_registry_register_rejects_duplicates() -> None:
    """Re-registering the same package name raises."""
    reg = _make_registry()
    reg.register("cordis", object())
    with pytest.raises(ValueError, match="already registered"):
        reg.register("cordis", object())


def test_registry_iteration_lists_registered_packages() -> None:
    """`for pkg in registry` yields registered names in sorted order."""
    reg = _make_registry()
    reg.register("loader", object())
    reg.register("cordis", object())
    assert list(reg) == ["cordis", "loader"]


def test_registry_lookup_with_default() -> None:
    """`registry.get(name, default)` returns the default when missing."""
    reg = _make_registry()
    sentinel = object()
    assert reg.get("missing", sentinel) is sentinel


def test_registry_lookup_raises_keyerror_when_missing() -> None:
    """Subscript access raises `KeyError` for unknown packages."""
    reg = _make_registry()
    with pytest.raises(KeyError):
        _ = reg["missing"]


# ---------------------------------------------------------------------------
# assert_invariant (test hook)
# ---------------------------------------------------------------------------


def test_assert_invariant_passes_when_correct(make_ctx) -> None:
    """`assert_invariant` returns `None` when the check returns truthy."""
    reg = InvariantRegistry(make_ctx)
    assert reg.assert_invariant("demo", lambda: True) is None


def test_assert_invariant_raises_on_failure(make_ctx) -> None:
    """`assert_invariant` raises `InvariantError` when the check returns falsy."""
    reg = InvariantRegistry(make_ctx)
    with pytest.raises(InvariantError):
        reg.assert_invariant("demo", lambda: False)


def test_assert_invariant_propagates_user_exception(make_ctx) -> None:
    """Exceptions raised by the check propagate as-is, not wrapped."""
    reg = InvariantRegistry(make_ctx)

    class BoomError(RuntimeError):
        pass

    with pytest.raises(BoomError):
        reg.assert_invariant("demo", lambda: (_ for _ in ()).throw(BoomError("nope")))


def test_assert_invariant_rejects_duplicate_name(make_ctx) -> None:
    """Asserting the same name twice raises `ValueError`."""
    reg = InvariantRegistry(make_ctx)
    reg.assert_invariant("demo", lambda: True)
    with pytest.raises(ValueError, match="already asserted"):
        reg.assert_invariant("demo", lambda: True)


def test_assert_invariant_records_check_for_replay(make_ctx) -> None:
    """A registered check can be replayed via `check(name)`."""
    reg = InvariantRegistry(make_ctx)
    counter = {"calls": 0}

    def check() -> bool:
        counter["calls"] += 1
        return True

    reg.assert_invariant("counter", check)
    # `assert_invariant` ran the check once; two replays add two more.
    reg.check("counter")
    reg.check("counter")
    assert counter["calls"] == 3


def test_check_unknown_name_raises_keyerror(make_ctx) -> None:
    """`check(name)` raises `KeyError` for an unregistered name."""
    reg = InvariantRegistry(make_ctx)
    with pytest.raises(KeyError):
        reg.check("nope")


def test_check_run_returns_falsy_raises_invariant_error(make_ctx) -> None:
    """`check(name)` raises `InvariantError` when the check returns falsy."""
    reg = InvariantRegistry(make_ctx)
    reg.assert_invariant("demo", lambda: True)
    reg._checks["demo"] = lambda: False  # replace the recorded callable
    with pytest.raises(InvariantError):
        reg.check("demo")


# ---------------------------------------------------------------------------
# Module-level helper
# ---------------------------------------------------------------------------


def test_module_level_assert_invariant_delegates_to_registry(make_ctx) -> None:
    """The module-level `assert_invariant` uses the active registry on `ctx`."""
    from taiyi_runtime_diagnostics_invariants import assert_invariant

    ctx = make_ctx
    reg = InvariantRegistry(ctx)
    ctx.reflect.provide("invariants", reg)  # type: ignore[attr-defined]

    # Pass: the registry records the check and runs it.
    assert_invariant(ctx, "demo", lambda: True)
    assert "demo" in reg._checks

    # Fail: the helper propagates InvariantError.
    with pytest.raises(InvariantError):
        assert_invariant(ctx, "demo-fail", lambda: False)


# ---------------------------------------------------------------------------
# Vendor surface registry list
# ---------------------------------------------------------------------------


def test_invariant_registry_lists_all_vendors(make_ctx) -> None:
    """`list_vendors()` enumerates the canonical vendor invariant modules."""
    from taiyi_runtime_diagnostics_invariants.plugin import VENDOR_INVARIANT_MODULES

    expected = {
        "cordis.invariant",
        "schemastery.invariant",
        "loader.invariant",
        "include.invariant",
        "group.invariant",
        "timer.invariant",
        "hmr.invariant",
        "logger_console.invariant",
        "taiyi_core_scope.invariant",
        "taiyi_core_session.invariant",
    }
    assert set(VENDOR_INVARIANT_MODULES) == expected


def test_invariant_registry_lists_all_vendors_runtime(make_ctx) -> None:
    """`list_vendors()` returns only those modules that can be imported."""
    from taiyi_runtime_diagnostics_invariants.plugin import (
        VENDOR_INVARIANT_MODULES,
        list_installed_vendors,
    )

    installed = list_installed_vendors()
    # The set is a subset of the canonical vendor list.
    assert set(installed).issubset(set(VENDOR_INVARIANT_MODULES))
    # And every installed module actually imports.
    for name in installed:
        module = __import__(name, fromlist=["invariant"])
        assert module.__name__ == name
