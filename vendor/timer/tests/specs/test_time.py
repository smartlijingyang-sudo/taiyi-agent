"""Tests for `timer.time` — Time constant helpers.

Mirrors upstream `Time` constants (1e3 / 60 / 60 / 24 ladder) used by other
packages to express ms-based durations.
"""

from __future__ import annotations

from timer import Time


class TestTimeConstants:
    """Time constants expose the standard millisecond ladder."""

    def test_time_none(self) -> None:
        """`Time.none` is the zero sentinel (no delay)."""
        assert Time.none == 0

    def test_time_millisecond(self) -> None:
        """`Time.millisecond` is 1 (one ms)."""
        assert Time.millisecond == 1

    def test_time_second(self) -> None:
        """`Time.second` is 1 000 ms."""
        assert Time.second == 1000

    def test_time_minute(self) -> None:
        """`Time.minute` is 60 × `Time.second`."""
        assert Time.minute == 60 * 1000

    def test_time_hour(self) -> None:
        """`Time.hour` is 60 × `Time.minute`."""
        assert Time.hour == 60 * 60 * 1000

    def test_time_day(self) -> None:
        """`Time.day` is 24 × `Time.hour`."""
        assert Time.day == 24 * 60 * 60 * 1000

    def test_time_constants_are_integers(self) -> None:
        """All constants are plain `int` (compatible with `asyncio.sleep`)."""
        for value in (Time.none, Time.millisecond, Time.second, Time.minute, Time.hour, Time.day):
            assert isinstance(value, int)


class TestTimeNone:
    """`Time.none` is the canonical "no delay" sentinel."""

    def test_none_is_falsy(self) -> None:
        """`Time.none` evaluates to false in boolean context."""
        assert not Time.none

    def test_none_is_zero(self) -> None:
        """`Time.none` is exactly `0`."""
        assert Time.none == 0
        assert Time.none is not None

    def test_none_distinct_from_millisecond(self) -> None:
        """`Time.none` and `Time.millisecond` are different values."""
        assert Time.none != Time.millisecond


__all__ = ["TestTimeConstants", "TestTimeNone"]
