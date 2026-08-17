"""Tests for cordis.invariant — verifies the public contract re-exports."""

from __future__ import annotations

import cordis.invariant as inv


class TestInvariantExports:
    """invariant re-exports the stable public surface of cordis."""

    def test_context_exported(self):
        assert inv.Context is not None

    def test_helpers_exported(self):
        assert inv.DisposableMixin is not None
        assert inv.DisposableList is not None
        assert inv.Tracker is not None
        assert inv.symbols is not None
        assert inv.is_constructor is not None
        assert inv.is_object is not None

    def test_event_exports(self):
        assert inv.EventsService is not None
        assert inv.is_bailed is not None

    def test_fiber_exports(self):
        assert inv.Fiber is not None
        assert inv.FiberState is not None
        assert inv.CordisError is not None
        assert inv.ValidationError is not None

    def test_loader_exports(self):
        assert inv.Entry is not None
        assert inv.EntryGroup is not None
        assert inv.EntryTree is not None
        assert inv.Loader is not None
        assert inv.Bundle is not None
        assert inv.load_config is not None
        assert inv.load_yaml is not None
        assert inv.dump_config is not None
        assert inv.interpolate is not None
        assert inv.merge_bundles is not None

    def test_logger_exports(self):
        assert inv.Logger is not None
        assert inv.LoggerLevel is not None
        assert inv.LoggerService is not None
        assert inv.Exporter is not None
        assert inv.Message is not None
        assert inv.default_formatters is not None

    def test_plugin_exports(self):
        assert inv.Plugin is not None
        assert inv.plugin is not None
        assert inv.is_plugin is not None
        assert inv.get_plugin_meta is not None
        assert inv.get_plugin_name is not None
        assert inv.get_plugin_inject is not None

    def test_reflect_exports(self):
        assert inv.ReflectService is not None
        assert inv.Impl is not None
        assert inv.Property is not None

    def test_registry_exports(self):
        assert inv.RegistryService is not None
        assert inv.PluginRuntime is not None

    def test_service_export(self):
        assert inv.Service is not None


class TestInvariantContract:
    """The contract re-exports point to the same objects as the implementation."""

    def test_context_is_cordis_context(self):
        from cordis.context import Context as RealContext
        assert inv.Context is RealContext

    def test_fiber_is_cordis_fiber(self):
        from cordis.fiber import Fiber as RealFiber
        assert inv.Fiber is RealFiber

    def test_logger_service_is_cordis_logger(self):
        from cordis.logger import LoggerService as RealLoggerService
        assert inv.LoggerService is RealLoggerService

    def test_reflect_service_is_cordis_reflect(self):
        from cordis.reflect import ReflectService as RealReflectService
        assert inv.ReflectService is RealReflectService

    def test_loader_is_cordis_loader(self):
        from cordis.loader import Loader as RealLoader
        assert inv.Loader is RealLoader

    def test_plugin_is_cordis_plugin(self):
        from cordis.plugin import Plugin as RealPlugin
        assert inv.Plugin is RealPlugin

    def test_registry_service_is_cordis_registry(self):
        from cordis.registry import RegistryService as RealRegistryService
        assert inv.RegistryService is RealRegistryService


class TestInvariantAllExports:
    """All symbols in __all__ are actually importable."""

    def test_all_exports_resolve(self):
        for name in inv.__all__:
            obj = getattr(inv, name)
            assert obj is not None, f"{name} is None"


__all__ = [
    "TestInvariantExports",
    "TestInvariantContract",
    "TestInvariantAllExports",
]