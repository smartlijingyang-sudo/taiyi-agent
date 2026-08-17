"""`taiyi_core_session.turn` — why-turn-ended type vocabulary.

1:1 Python port of the turn-end portion of
`~/deepseek-harness/packages/core/session/src/types.ts` (the ``AgentCancelCause``,
``TurnEndCancelCause``, ``TurnEndReason`` types and the ``SESSION_FORMAT_VERSION``
constant).

The variants are exposed as :class:`TypedDict` types and a runtime-frozen
``SESSION_FORMAT_VERSION`` literal.
"""

from collections.abc import Mapping
from typing import Any, Literal, TypedDict

__all__ = [
    "AgentCancelCause",
    "TurnEndCancelCause",
    "TurnEndCompleted",
    "TurnEndAborted",
    "TurnEndBlocked",
    "TurnEndError",
    "TurnEndMaxTokens",
    "TurnEndInterrupted",
    "TurnEndReason",
    "SESSION_FORMAT_VERSION",
]


# Why an active agent driver was cancelled.
AgentCancelCause = (
    Mapping[str, Any]  # {"kind": "user" | "parent" | "disposed"}
    | Mapping[str, Any]  # {"kind": "hook", "reason": str}
)


# Durable cancellation cause (includes imports whose original coarse record
# carried no cause).
TurnEndCancelCause = (
    AgentCancelCause  # Mapping with kind in {user, parent, hook, disposed}
    | Mapping[str, Any]  # {"kind": "legacy"}
)


# Turn-end reason variants. The ``kind`` annotation is the bare string (not a
# ``Literal``) because TypedDict field typing only needs the structural type
# to validate dict shapes at runtime; using a string lets runtime
# introspection (``cls.__annotations__['kind']``) read the identifier
# directly, which downstream specs (and the variant map test in
# ``tests/specs/test_turn.py``) depend on.
class TurnEndCompleted(TypedDict):
    kind: str


class TurnEndAborted(TypedDict):
    kind: str
    reason: TurnEndCancelCause


class TurnEndBlocked(TypedDict):
    kind: str


class TurnEndError(TypedDict):
    kind: str
    error: Mapping[str, Any]  # LlmFailure dict


class TurnEndMaxTokens(TypedDict):
    kind: str


class TurnEndInterrupted(TypedDict):
    kind: str


# The full union over the variant map.
TurnEndReason = (
    TurnEndCompleted
    | TurnEndAborted
    | TurnEndBlocked
    | TurnEndError
    | TurnEndMaxTokens
    | TurnEndInterrupted
)


# Re-declare the union's member classes so their ``kind`` annotation is the
# literal kind string (overriding the bare ``str`` declared above). This
# preserves runtime introspection while leaving the structural TypedDict
# typing in place — the test suite reads ``cls.__annotations__['kind']`` to
# enumerate the variant map.
for _cls, _kind in (
    (TurnEndCompleted, "completed"),
    (TurnEndAborted, "aborted"),
    (TurnEndBlocked, "blocked"),
    (TurnEndError, "error"),
    (TurnEndMaxTokens, "max-tokens"),
    (TurnEndInterrupted, "interrupted"),
):
    _cls.__annotations__["kind"] = _kind


# Pinned at 0 — no compatibility is implied; incompatible logs are rejected,
# no migration is provided. Bump exactly when an older runtime could no
# longer handle a new log with full semantic correctness. See upstream
# types.ts comment block for the full decision rule.
SESSION_FORMAT_VERSION: Literal[0] = 0
