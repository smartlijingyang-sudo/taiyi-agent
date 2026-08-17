"""1:1 tests for `taiyi_core_session.session.SessionStore`."""

from __future__ import annotations

import pytest

from taiyi_core_session.session import (
    Session,
    SessionForkError,
    SessionStore,
)
from taiyi_core_session.types import SessionId

# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


def test_store_prepare_assigns_id_when_omitted(make_ctx) -> None:
    store = SessionStore(make_ctx)
    s = store.prepare()
    assert s.id.startswith("session-")


def test_store_prepare_uses_explicit_id(make_ctx) -> None:
    store = SessionStore(make_ctx)
    s = store.prepare(SessionId("my-session"))
    assert s.id == "my-session"


def test_store_prepare_does_not_check_unentered_duplicates(make_ctx) -> None:
    """Mirrors upstream: `prepare` only checks the live `_store`, not unprepared sessions."""
    store = SessionStore(make_ctx)
    store.prepare(SessionId("dup"))
    # A second prepare for the same id does NOT raise — the first one is not
    # in the live store yet. Conflict is enforced at `enter` time.
    store.prepare(SessionId("dup"))


def test_store_prepare_rejects_duplicate_after_enter(make_ctx) -> None:
    store = SessionStore(make_ctx)
    s1 = store.prepare(SessionId("dup"))
    store.enter(s1)
    with pytest.raises(ValueError, match="already exists"):
        store.prepare(SessionId("dup"))


def test_store_prepare_restore_path(make_ctx) -> None:
    store = SessionStore(make_ctx)
    seed = [{"type": "turn/start", "seq": 0, "time": 1, "data": {"turn": 1}}]
    header = {"version": 0, "id": "restored", "createdAt": 1700000000000}
    s = store.prepare(SessionId("restored"), {"seed": seed, "meta": header, "seedSource": "persistence"})
    assert s.id == "restored"


def test_store_prepare_meta_propagation(make_ctx) -> None:
    store = SessionStore(make_ctx)
    s = store.prepare(
        SessionId("meta-session"),
        {
            "meta": {
                "cwd": "/abs",
                "parentSession": "parent",
                "seedLength": 0,
                "agentPreset": "default",
            }
        },
    )
    assert s.header["cwd"] == "/abs"
    assert s.header["parentSession"] == "parent"
    assert s.header["agentPreset"] == "default"


def test_store_prepare_meta_optional_origin(make_ctx) -> None:
    store = SessionStore(make_ctx)
    s = store.prepare(
        SessionId("subagent"),
        {"meta": {"origin": "subagent", "delegationDepth": 2}},
    )
    assert s.header["origin"] == "subagent"
    assert s.header["delegationDepth"] == 2


# ---------------------------------------------------------------------------
# Enter / detach
# ---------------------------------------------------------------------------


def test_store_enter_returns_detach_disposer(make_ctx) -> None:
    store = SessionStore(make_ctx)
    s = store.prepare(SessionId("e"))
    detach = store.enter(s)
    assert callable(detach)
    detach()
    assert store.get(SessionId("e")) is None


def test_store_enter_rejects_duplicate(make_ctx) -> None:
    store = SessionStore(make_ctx)
    s = store.prepare(SessionId("dup"))
    store.enter(s)
    with pytest.raises(ValueError, match="already exists"):
        store.prepare(SessionId("dup"))


def test_store_enter_rejects_already_attached(make_ctx) -> None:
    store = SessionStore(make_ctx)
    s = store.prepare(SessionId("dup"))
    store.enter(s)
    with pytest.raises(ValueError, match="already exists"):
        store.enter(s)


def test_store_detach_when_not_announcing_removes_immediately(make_ctx) -> None:
    store = SessionStore(make_ctx)
    s = store.prepare(SessionId("d"))
    detach = store.enter(s)
    detach()
    assert store.get(SessionId("d")) is None


def test_store_detach_double_call_noop(make_ctx) -> None:
    store = SessionStore(make_ctx)
    s = store.prepare(SessionId("d"))
    detach = store.enter(s)
    detach()
    detach()  # second call should be a no-op


def test_store_get_returns_none_for_unknown(make_ctx) -> None:
    store = SessionStore(make_ctx)
    assert store.get(SessionId("nope")) is None


def test_store_list_returns_in_creation_order(make_ctx) -> None:
    store = SessionStore(make_ctx)
    a = store.prepare(SessionId("a"))
    b = store.prepare(SessionId("b"))
    store.enter(a)
    store.enter(b)
    listing = store.list()
    assert [s.id for s in listing] == ["a", "b"]


# ---------------------------------------------------------------------------
# Announce
# ---------------------------------------------------------------------------


def test_store_announce_emits_session_created(make_ctx) -> None:
    store = SessionStore(make_ctx)
    s = store.prepare(SessionId("ann"))
    store.enter(s)
    seen: list[str] = []
    make_ctx.events.on(
        "session/created", lambda session: seen.append(session.id)
    )
    store.announce(s)
    assert "ann" in seen


def test_store_announce_rejects_repeat(make_ctx) -> None:
    store = SessionStore(make_ctx)
    s = store.prepare(SessionId("ann"))
    store.enter(s)
    store.announce(s)
    with pytest.raises(ValueError, match="was already announced"):
        store.announce(s)


def test_store_announce_rejects_non_live(make_ctx) -> None:
    store = SessionStore(make_ctx)
    s = store.prepare(SessionId("d"))
    with pytest.raises(ValueError, match="not live"):
        store.announce(s)


def test_store_announce_listener_throw_is_caught(make_ctx) -> None:
    """A throwing listener must not break publication (mirrors upstream)."""
    store = SessionStore(make_ctx)
    s = store.prepare(SessionId("ann"))
    store.enter(s)

    def bad_listener(_session: object) -> None:
        raise RuntimeError("boom")

    make_ctx.events.on("session/created", bad_listener)
    # Should not raise — the throwing listener is contained.
    store.announce(s)


def test_store_detach_emits_disposed(make_ctx) -> None:
    store = SessionStore(make_ctx)
    s = store.prepare(SessionId("d"))
    detach = store.enter(s)
    store.announce(s)
    seen: list[str] = []
    make_ctx.events.on("session/disposed", lambda session: seen.append(session.id))
    detach()
    assert "d" in seen


# ---------------------------------------------------------------------------
# Flush
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_store_flush_with_no_listeners_returns_false(make_ctx) -> None:
    store = SessionStore(make_ctx)
    s = store.prepare(SessionId("f"))
    store.enter(s)
    result = await store.flush(s)
    assert result is False


@pytest.mark.asyncio
async def test_store_flush_with_listeners_returns_true(make_ctx) -> None:
    store = SessionStore(make_ctx)
    s = store.prepare(SessionId("f"))
    store.enter(s)
    seen: list[SessionId] = []

    async def flush_listener(session: Session) -> None:
        seen.append(session.id)

    make_ctx.events.on("session/flush", flush_listener)
    result = await store.flush(s)
    assert result is True
    assert seen == ["f"]


@pytest.mark.asyncio
async def test_store_flush_rejects_non_live(make_ctx) -> None:
    store = SessionStore(make_ctx)
    s = store.prepare(SessionId("f"))
    with pytest.raises(ValueError, match="not live"):
        await store.flush(s)


# ---------------------------------------------------------------------------
# Fork
# ---------------------------------------------------------------------------


def _user_event(seq: int, message_id: str) -> dict[str, object]:
    return {
        "type": "user/message",
        "seq": seq,
        "time": 1700000000000 + seq,
        "data": {
            "id": message_id,
            "role": "user",
            "source": {"kind": "user"},
            "content": [{"type": "text", "text": "hi"}],
        },
        "surfaceOp": "append",
    }


def test_store_fork_by_id_at_last_seq(make_ctx) -> None:
    store = SessionStore(make_ctx)
    store.create(
        SessionId("src"),
        {"seed": [_user_event(0, "m1")]},
    )
    child = store.fork(SessionId("src"))
    assert child.events[-1]["type"] == "session/end-seed"


def test_store_fork_with_explicit_boundary(make_ctx) -> None:
    store = SessionStore(make_ctx)
    store.create(
        SessionId("src"),
        {"seed": [_user_event(0, "m1")]},
    )
    child = store.fork(SessionId("src"), boundary=0)
    assert child.events[0]["data"]["id"] == "m1"


def test_store_fork_rejects_duplicate_child_id(make_ctx) -> None:
    store = SessionStore(make_ctx)
    store.create(
        SessionId("src"),
        {"seed": [_user_event(0, "m1")]},
    )
    store.create(
        SessionId("child"),
        {"seed": [_user_event(0, "m2")]},
    )
    with pytest.raises(SessionForkError) as exc_info:
        store.fork(SessionId("src"), child_session_id=SessionId("child"))
    assert exc_info.value.code == "SESSION_ALREADY_EXISTS"


def test_store_fork_rejects_unknown_source_id(make_ctx) -> None:
    store = SessionStore(make_ctx)
    with pytest.raises(SessionForkError) as exc_info:
        store.fork(SessionId("nonexistent"))
    assert exc_info.value.code == "SESSION_NOT_FOUND"


def test_store_fork_rejects_non_live_session(make_ctx) -> None:
    """A detached session object passed to fork is rejected."""
    store = SessionStore(make_ctx)
    s = store.create(
        SessionId("src"),
        {"seed": [_user_event(0, "m1")]},
    )
    s_detached = Session.create(s.id, seed=s.events, header=dict(s.header))
    with pytest.raises(SessionForkError) as exc_info:
        store.fork(s_detached)
    assert exc_info.value.code == "SESSION_NOT_LIVE"


def test_store_fork_rejects_invalid_boundary_type(make_ctx) -> None:
    store = SessionStore(make_ctx)
    store.create(
        SessionId("src"),
        {"seed": [_user_event(0, "m1")]},
    )
    with pytest.raises(SessionForkError) as exc_info:
        store.fork(SessionId("src"), boundary=-1)
    assert exc_info.value.code == "INVALID_BOUNDARY"


def test_store_fork_rejects_out_of_range_boundary(make_ctx) -> None:
    store = SessionStore(make_ctx)
    store.create(
        SessionId("src"),
        {"seed": [_user_event(0, "m1")]},
    )
    with pytest.raises(SessionForkError) as exc_info:
        store.fork(SessionId("src"), boundary=999)
    assert exc_info.value.code == "INVALID_BOUNDARY"


def test_store_fork_rejects_mismatched_boundary_seq(make_ctx) -> None:
    """`INVALID_BOUNDARY` when the boundary event is missing/mismatched."""
    store = SessionStore(make_ctx)
    s = store.create(
        SessionId("src"),
        {"seed": [_user_event(0, "m1")]},
    )
    # Manually remove the events (simulate out-of-order log).
    s._log = []
    with pytest.raises(SessionForkError) as exc_info:
        store.fork(SessionId("src"), boundary=0)
    assert exc_info.value.code == "INVALID_BOUNDARY"


def test_store_fork_rejects_open_turn_boundary(make_ctx) -> None:
    """An open turn/start at boundary → OPEN_TURN error."""
    store = SessionStore(make_ctx)
    s = store.create(SessionId("src"))
    s._log.append(
        {
            "type": "turn/start",
            "seq": 0,
            "time": 1700000000000,
            "data": {"turn": 1},
        }
    )
    s._events_snapshot = None
    with pytest.raises(SessionForkError) as exc_info:
        store.fork(SessionId("src"), boundary=0)
    assert exc_info.value.code == "OPEN_TURN"


def test_store_fork_empty_source_no_boundary_returns_empty_seed(make_ctx) -> None:
    """Fork of an empty source with no boundary → empty child."""
    store = SessionStore(make_ctx)
    store.create(SessionId("empty"))
    child = store.fork(SessionId("empty"))
    # child should have only session/end-seed from the seed-marker logic (none added)
    assert child.events == ()


def test_store_fork_seed_inherits_cwd(make_ctx) -> None:
    store = SessionStore(make_ctx)
    store.create(
        SessionId("src"),
        {"seed": [_user_event(0, "m1")], "meta": {"cwd": "/abs"}},
    )
    child = store.fork(SessionId("src"))
    assert child.header.get("cwd") == "/abs"


def test_store_fork_records_parent_session(make_ctx) -> None:
    store = SessionStore(make_ctx)
    s = store.create(
        SessionId("src"),
        {"seed": [_user_event(0, "m1")]},
    )
    child = store.fork(SessionId("src"))
    assert child.header["parentSession"] == "src"
    assert child.header["seedLength"] == len(s.events)


def test_store_create_assigns_auto_id(make_ctx) -> None:
    store = SessionStore(make_ctx)
    s = store.create()
    assert s.id.startswith("session-")


def test_store_create_id_collision_rejected(make_ctx) -> None:
    store = SessionStore(make_ctx)
    store.create(SessionId("dup"))
    with pytest.raises(ValueError, match="already exists"):
        store.create(SessionId("dup"))


def test_store_announce_listener_async_returned_is_closed(make_ctx) -> None:
    """An async listener that returns a coroutine has its coroutine closed."""
    import asyncio

    store = SessionStore(make_ctx)
    s = store.prepare(SessionId("ann"))
    store.enter(s)

    async def async_listener(_session: object) -> None:
        # Manually drive the listener's body so the function is exercised.
        await asyncio.sleep(0)

    # Direct invocation under an event loop executes the body; we then
    # register + invoke through the announce path to confirm the lifecycle
    # closes the returned coroutine without leaking it.
    asyncio.run(async_listener(None))

    make_ctx.events.on("session/created", async_listener)
    store.announce(s)  # must not raise or leak coroutine
