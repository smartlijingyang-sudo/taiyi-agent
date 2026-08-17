"""Test suite for cordis.service — Service base class with auto-dispose."""

from __future__ import annotations

import pytest
from pydantic import BaseModel, ValidationError

from cordis.context import Context
from cordis.service import Service


class TestService:
    """Service base class tests."""

    async def test_service_lifecycle(self):
        """Service is created, used, and disposed with context."""
        class MyService(Service):
            def __init__(self, ctx: Context):
                super().__init__(ctx)
                self.disposed = False

            async def dispose(self) -> None:
                self.disposed = True

        ctx = Context()
        svc = MyService(ctx)
        ctx.provide("my_service", svc)

        # Service is accessible
        assert ctx.inject("my_service") is svc
        assert not svc.disposed

        # Dispose context
        await ctx.dispose()

        # Service was disposed
        assert svc.disposed

    async def test_service_config_validation(self):
        """Service validates config via Pydantic model."""
        class ConfigModel(BaseModel):
            host: str
            port: int

        class MyService(Service):
            config = ConfigModel

            def __init__(self, ctx: Context, **config):
                super().__init__(ctx, **config)
                # Access validated config
                self.host = self._validated_config.host if self._validated_config else None
                self.port = self._validated_config.port if self._validated_config else None

        ctx = Context()

        # Valid config
        svc = MyService(ctx, host="localhost", port=8080)
        assert svc.host == "localhost"
        assert svc.port == 8080

        # Invalid config should raise ValidationError
        with pytest.raises(ValidationError):
            MyService(ctx, host="localhost", port="not-a-number")

        await ctx.dispose()

    async def test_service_dispose_order_lifo(self):
        """Services are disposed in LIFO order."""
        dispose_order = []

        class ServiceA(Service):
            async def dispose(self) -> None:
                dispose_order.append("A")

        class ServiceB(Service):
            async def dispose(self) -> None:
                dispose_order.append("B")

        class ServiceC(Service):
            async def dispose(self) -> None:
                dispose_order.append("C")

        ctx = Context()
        a = ServiceA(ctx)
        b = ServiceB(ctx)
        c = ServiceC(ctx)

        ctx.provide("a", a)
        ctx.provide("b", b)
        ctx.provide("c", c)

        await ctx.dispose()

        # LIFO: C, B, A
        assert dispose_order == ["C", "B", "A"]

    async def test_service_dispose_error_swallowed(self):
        """Errors in one service's dispose don't prevent others."""
        dispose_order = []

        class FailingService(Service):
            async def dispose(self) -> None:
                dispose_order.append("fail")
                raise RuntimeError("dispose failed")

        class SuccessService(Service):
            async def dispose(self) -> None:
                dispose_order.append("success")

        ctx = Context()
        fail = FailingService(ctx)
        success = SuccessService(ctx)

        ctx.provide("fail", fail)
        ctx.provide("success", success)

        # Should not raise
        await ctx.dispose()

        # Both were attempted
        assert "success" in dispose_order
        assert "fail" in dispose_order

    async def test_service_without_dispose(self):
        """Service without custom dispose() still works."""
        class SimpleService(Service):
            def __init__(self, ctx: Context, **config):
                super().__init__(ctx, **config)
                self.value = 42

        ctx = Context()
        svc = SimpleService(ctx)
        ctx.provide("simple", svc)

        assert ctx.inject("simple").value == 42

        # Should not raise
        await ctx.dispose()

    async def test_service_config_default_none(self):
        """Service without config class attribute works."""
        class NoConfigService(Service):
            pass

        ctx = Context()
        svc = NoConfigService(ctx)
        ctx.provide("no_config", svc)

        assert ctx.inject("no_config") is svc
        await ctx.dispose()


__all__ = ["TestService"]
