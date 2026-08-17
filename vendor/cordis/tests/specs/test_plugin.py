"""Tests for cordis.plugin — @plugin decorator + Plugin metadata (1:1 to upstream)."""

from __future__ import annotations

import pytest

from cordis.plugin import (
    Plugin,
    get_plugin_inject,
    get_plugin_meta,
    get_plugin_name,
    is_plugin,
    plugin,
)


class TestPluginBare:
    """Bare @plugin (no args) wraps a setup function."""

    def test_decorates_function(self):
        @plugin
        async def setup(ctx, config):
            return None

        assert isinstance(setup, Plugin)
        assert setup.setup.__name__ == "setup"

    def test_bare_plugin_no_args(self):
        @plugin
        async def my_setup(ctx, config):
            return None

        assert my_setup.Config is None
        assert my_setup.name is None
        assert my_setup.inject is None

    def test_is_plugin_detects_decorated(self):
        @plugin
        async def setup(ctx, config):
            return None

        assert is_plugin(setup) is True

    def test_is_plugin_rejects_plain_function(self):
        async def plain(ctx, config):
            return None

        assert is_plugin(plain) is False

    def test_is_plugin_rejects_non_callable(self):
        assert is_plugin(42) is False
        assert is_plugin(None) is False
        assert is_plugin("string") is False


class TestPluginWithArgs:
    """@plugin(config, name=..., inject=..., meta=...) with arguments."""

    def test_with_name(self):
        @plugin(name="my-plugin")
        async def setup(ctx, config):
            return None

        assert setup.name == "my-plugin"
        assert get_plugin_name(setup) == "my-plugin"

    def test_with_inject(self):
        @plugin(inject=["foo", "bar"])
        async def setup(ctx, config):
            return None

        assert setup.inject == ["foo", "bar"]
        assert get_plugin_inject(setup) == ["foo", "bar"]

    def test_with_meta(self):
        meta_dict = {"author": "alice", "version": "1.0"}
        @plugin(meta=meta_dict)
        async def setup(ctx, config):
            return None

        assert setup.meta == {"author": "alice", "version": "1.0"}
        assert get_plugin_meta(setup) == {"author": "alice", "version": "1.0"}

    def test_with_pydantic_config(self):
        from pydantic import BaseModel

        class Cfg(BaseModel):
            host: str
            port: int

        @plugin(Config=Cfg)
        async def setup(ctx, config):
            return None

        assert setup.Config is Cfg


class TestPluginMetadata:
    """get_plugin_* helpers extract metadata from Plugin objects."""

    def test_get_plugin_meta_empty(self):
        @plugin
        async def setup(ctx, config):
            return None

        assert get_plugin_meta(setup) == {}

    def test_get_plugin_inject_none(self):
        @plugin
        async def setup(ctx, config):
            return None

        assert get_plugin_inject(setup) is None

    def test_get_plugin_name_none(self):
        @plugin
        async def setup(ctx, config):
            return None

        assert get_plugin_name(setup) is None

    def test_metadata_returns_copy(self):
        @plugin(meta={"a": 1})
        async def setup(ctx, config):
            return None

        meta = get_plugin_meta(setup)
        meta["b"] = 2  # mutate the returned dict
        # Original plugin metadata should be unchanged
        assert setup.meta == {"a": 1}


class TestPluginCallable:
    """Plugin.setup is callable and can be invoked."""

    async def test_call_setup_directly(self):
        @plugin
        async def setup(ctx, config):
            return "result"

        result = await setup.setup(None, {})
        assert result == "result"

    async def test_call_setup_with_config(self):
        @plugin
        async def setup(ctx, config):
            return config.get("x")

        result = await setup.setup(None, {"x": 42})
        assert result == 42


class TestPluginProtocol:
    """Plugin can be passed as a value (Protocol/typing)."""

    def test_plugin_can_be_stored(self):
        @plugin
        async def setup(ctx, config):
            return None

        registry: dict[str, Plugin] = {"first": setup}
        assert registry["first"] is setup
        assert is_plugin(registry["first"]) is True


class TestPluginDuckTypedFallback:
    """Duck-typed detection fallbacks when attribute access raises."""

    def test_is_plugin_with_raising_attr(self):
        # Object whose __getattr__ raises on attribute lookup (no flag attr).
        class FlagRaise:
            def __getattr__(self, _name: str):
                raise OSError("no flag")

        assert is_plugin(FlagRaise()) is False

    def test_get_plugin_meta_with_raising_attr(self):
        # Non-Plugin object whose meta-attr access raises -> returns {}.
        class MetaRaise:
            def __getattr__(self, _name: str):
                raise OSError("no meta")

        assert get_plugin_meta(MetaRaise()) == {}

    def test_get_plugin_meta_with_falsy_meta(self):
        # Non-Plugin object whose __cordis_plugin_meta__ attr is None/0 -> {}.
        class MetaNone:
            __cordis_plugin_meta__ = None

        assert get_plugin_meta(MetaNone()) == {}

    def test_get_plugin_meta_returns_copy_of_meta(self):
        # Non-Plugin object with a real meta dict -> returns a copy.
        class MetaHolder:
            __cordis_plugin_meta__ = {"x": 1}

        meta = get_plugin_meta(MetaHolder())
        meta["y"] = 2
        assert MetaHolder.__cordis_plugin_meta__ == {"x": 1}

    def test_get_plugin_name_with_raising_attr(self):
        class Raise:
            def __getattr__(self, _name: str):
                raise OSError("no name")

        assert get_plugin_name(Raise()) is None

    def test_get_plugin_inject_with_raising_attr(self):
        class Raise:
            def __getattr__(self, _name: str):
                raise OSError("no inject")

        assert get_plugin_inject(Raise()) is None

    def test_get_plugin_inject_returns_copy(self):
        class InjectHolder:
            inject = ["a", "b"]

        inj = get_plugin_inject(InjectHolder())
        inj.append("c")
        assert InjectHolder.inject == ["a", "b"]

    def test_get_plugin_inject_none_inject(self):
        class InjectNone:
            inject = None

        assert get_plugin_inject(InjectNone()) is None


__all__ = [
    "TestPluginBare",
    "TestPluginWithArgs",
    "TestPluginMetadata",
    "TestPluginCallable",
    "TestPluginProtocol",
    "TestPluginDuckTypedFallback",
]