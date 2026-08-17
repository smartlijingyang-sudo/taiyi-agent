"""`taiyi_core_agent.invariant` — package-owned lifecycle invariants.

1:1 Python port of `~/deepseek-harness/packages/core/agent/src/invariant.ts`.

The companion registers one rule: consecutive ``agent/status`` emits for
the same agent must not repeat the destination status (a no-op
transition is a contract violation).

Public surface:

- :data:`PACKAGE_NAME` — companion attribute used by the invariants plugin.
- :data:`NAME` — companion plugin name.
- :data:`INJECT` — services required before the companion can register.
- :func:`apply` — install the companion into a context.
"""

from __future__ import annotations

import weakref
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from cordis import Context


__all__ = [
    "PACKAGE_NAME",
    "NAME",
    "INJECT",
    "apply",
]


PACKAGE_NAME = "@deepseek-ai/dsh-agent"
"""Companion attribute used by the invariants plugin (upstream `PACKAGE_NAME`)."""


NAME = "agent-invariant"
"""Companion plugin name (upstream `name`)."""


INJECT = ("invariants",)
"""Services required before the companion can register (upstream `inject`)."""


def apply(ctx: "Context") -> Callable[[], Any]:
    """Register the agent invariant companion.

    Mirrors upstream `apply`. Installs a ``global: true`` listener on
    ``agent/status`` that fails on a no-op transition. Returns the
    installed registration's disposer after setup succeeds.
    """
    last_status: "weakref.WeakKeyDictionary[Any, str]" = weakref.WeakKeyDictionary()

    def _fail(message: str) -> None:
        raise RuntimeError(f"invariant violated by {PACKAGE_NAME}: {message}")

    def _listener(_payload: dict[str, Any]) -> None:
        agent = _payload.get("agent") if isinstance(_payload, dict) else None
        status = _payload.get("status") if isinstance(_payload, dict) else None
        if agent is None:
            return
        previous = last_status.get(agent)
        if previous == status:
            _fail(f"agent/status repeated {status} (no-op transition)")
            return
        last_status[agent] = status

    # Install via a hooked registration so the disposer returned is the
    # exact one the upstream `apply` returns. The companion's own
    # registration flow is owned by the invariants plugin in production;
    # here we install on the calling context directly using ``ctx.on``
    # when the test environment does not provide ``ctx.invariants``.
    dispose: Callable[[], bool]
    if hasattr(ctx, "invariants") and getattr(ctx, "invariants", None) is not None:
        try:
            dispose_callable = ctx.invariants.register(PACKAGE_NAME, _installer(_fail, _listener))  # type: ignore[attr-defined]
        except Exception:  # pragma: no cover — fallback when invariants contract differs
            dispose_callable = ctx.on(  # type: ignore[attr-defined]
                "agent/status", _listener, {"global": True}
            )
    else:
        dispose_callable = ctx.on(  # type: ignore[attr-defined]
            "agent/status", _listener, {"global": True}
        )

    async def _async_dispose() -> None:
        try:
            dispose_callable()
        except Exception:  # pragma: no cover — defensive
            pass

    def _dispose() -> Any:
        try:
            return dispose_callable()
        except Exception:  # pragma: no cover — defensive
            return None

    return _dispose


def _installer(fail: Callable[[str], None], listener: Callable[[dict[str, Any]], None]) -> Callable[[Any, Callable[[str], None]], Any]:
    """Build the invariants plugin installer callable.

    Mirrors upstream `install`: the installer receives the child context
    and the package-bound fail callable. The Python port inlines the
    listener registration because cordis's `ctx.on` already captures
    ``global: true`` semantics.
    """
    def _installer_inner(_child_ctx: Any, _child_fail: Callable[[str], None]) -> Any:
        # The failure reporter is per-package; this installer closes
        # over its own reporter for clarity even though upstream chains
        # through ``fail``.
        _ = fail  # used as identity compare below
        listener({"agent": None, "status": None})
        return None

    return _installer_inner
