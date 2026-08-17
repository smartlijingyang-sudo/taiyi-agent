"""`taiyi_core_agent.consumed_work` — accounting over one agent's log.

1:1 Python port of `~/deepseek-harness/packages/core/agent/src/consumed-work.ts`.

The turn and step vocabulary alone cannot answer how a log accounts for the
work it consumed. The inbox's own record — :class:`taiyi_core_agent.inbox.Inbox`
— logs each mutation with ``removedCount`` and marks a cancellation
``outcome: 'canceled'``, which separates a turn claiming its input from work
being dropped unrun. This module reads that record.

Public surface:

- :class:`ConsumedWork`
- :func:`fold_consumed_work`
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

__all__ = [
    "ConsumedWork",
    "fold_consumed_work",
    "accounts_for_claim",
]


# ---------------------------------------------------------------------------
# Public result type
# ---------------------------------------------------------------------------


@dataclass
class ConsumedWork:
    """How one agent log accounts for the work it consumed.

    Mirrors upstream :class:`ConsumedWork`:

    - ``end`` — the latest closed turn that accounts for consumed work.
    - ``dropped_unrun`` — whether accepted work was cancelled out of the
      inbox without a turn opening over it.
    """

    end: Mapping[str, Any] | None = None
    dropped_unrun: bool = False


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


_TURN_END_REASONS_ACCOUNING_FOR_CLAIM: frozenset[str] = frozenset(
    {"blocked", "aborted", "interrupted", "error"}
)


def accounts_for_claim(reason: Mapping[str, Any]) -> bool:
    """Whether a turn's ending accounts for input it claimed.

    Mirrors upstream `accountsForClaim`. Only ``completed`` does not: it had
    nothing left to run once its claim was rewritten away. Every other
    named ending ``blocked``, ``aborted``, ``interrupted``, ``error`` is an
    account of consumed input. An unnameable ending (e.g. a backend-added
    variant through :class:`TurnEndReasonMap`'s merge-extensibility)
    reads as success-by-default — the upstream ``default`` branch is
    identity to ``true`` so a nameable mistake over an accounted input
    cannot silently disappear.
    """
    kind = reason.get("kind") if isinstance(reason, Mapping) else None
    if kind == "completed":
        return False
    # ``blocked`` / ``aborted`` / ``interrupted`` / ``error`` accounts for the
    # input; any other (extendable) kind is treated as accountable too,
    # matching upstream ``default: return true``.
    return True


# ---------------------------------------------------------------------------
# Public fold
# ---------------------------------------------------------------------------


def fold_consumed_work(events: "list[Mapping[str, Any]] | tuple[Mapping[str, Any], ...]") -> ConsumedWork:
    """Fold one agent log into its account of consumed work.

    Mirrors upstream `foldConsumedWork`. Single pass, every input is the
    log itself — no caller has to sample live state before cancelling, so
    a cancellation issued by anyone (the owner's teardown, an ancestor's
    interrupt, an unloading plugin) reads the same.
    """
    stepped: set[int] = set()
    claimed: set[int] = set()
    open_turn: int | None = None
    end: Mapping[str, Any] | None = None
    dropped_unrun = False
    for event in events:
        event_type = event.get("type") if isinstance(event, Mapping) else None
        if event_type == "turn/start":
            data = event.get("data") if isinstance(event, Mapping) else None
            if isinstance(data, Mapping):
                turn = data.get("turn")
                if isinstance(turn, int) and not isinstance(turn, bool):
                    open_turn = turn
            continue
        if event_type == "step/start":
            data = event.get("data") if isinstance(event, Mapping) else None
            if isinstance(data, Mapping):
                turn = data.get("turn")
                if isinstance(turn, int) and not isinstance(turn, bool):
                    stepped.add(turn)
            continue
        if event_type == "agent/inbox/spliced":
            data = event.get("data") if isinstance(event, Mapping) else None
            if not isinstance(data, Mapping):
                continue
            removed_count = data.get("removedCount")
            if removed_count is None:
                continue
            outcome = data.get("outcome")
            inserted = data.get("inserted") or []
            # Cancellation that leaves nothing behind drops it; a
            # replacement keeps the work pending under a new identity.
            if outcome == "canceled":
                if len(inserted) == 0:
                    dropped_unrun = True
            elif open_turn is not None:
                claimed.add(open_turn)
            continue
        if event_type == "turn/end":
            data = event.get("data") if isinstance(event, Mapping) else None
            if not isinstance(data, Mapping):
                continue
            turn = data.get("turn")
            reason = data.get("reason")
            open_turn = None
            if not isinstance(turn, int) or isinstance(turn, bool) or not isinstance(reason, Mapping):
                continue
            if turn in stepped:
                stepped.discard(turn)
                end = event
                dropped_unrun = False
                continue
            if turn in claimed and accounts_for_claim(reason):
                claimed.discard(turn)
                end = event
                dropped_unrun = False
                continue
            # No matching account: drop the bookkeeping claim silently
            # and continue scanning. Mirrors the upstream break-on-no-match
            # behaviour — the turn was opened but produced neither a step
            # nor a claim, so it cannot be an accounting turn.
            continue
        # All other event types: pass-through (no bookkeeping).
    return ConsumedWork(end=end, dropped_unrun=dropped_unrun)
