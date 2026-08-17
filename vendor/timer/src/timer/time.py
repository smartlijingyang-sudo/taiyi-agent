"""`timer.time` — Time-unit constants used by the agent's scheduling helpers.

The values are expressed in milliseconds (matching the upstream
`@deepseek-ai/timer` `Time` namespace and the JS `Date.now()` epoch).
Downstream code uses these constants to compute durations without
hard-coding the `1e3 / 60 / 60 / 24` ladder.
"""

from __future__ import annotations

from typing import Final


class Time:
    """Millisecond-based time unit constants.

    Mirrors the upstream `Time` namespace:

    - `none` — zero (sentinel for "no delay").
    - `millisecond` — 1 ms.
    - `second` — 1 000 ms.
    - `minute` — 60 × `second`.
    - `hour` — 60 × `minute`.
    - `day` — 24 × `hour`.
    """

    none: Final[int] = 0
    millisecond: Final[int] = 1
    second: Final[int] = 1_000
    minute: Final[int] = 60 * 1_000
    hour: Final[int] = 60 * 60 * 1_000
    day: Final[int] = 24 * 60 * 60 * 1_000


__all__ = ["Time"]
