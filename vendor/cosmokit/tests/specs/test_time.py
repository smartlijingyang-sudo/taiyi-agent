"""Tests for `cosmokit.time` — time constants, parsing, and formatting."""

import time as _time
from datetime import UTC, datetime

import pytest

from cosmokit.time import Time

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


def test_constants_in_seconds():
    """Standard time-unit constants match the TS values."""
    assert Time.millisecond == 1
    assert Time.second == 1000
    assert Time.minute == Time.second * 60
    assert Time.hour == Time.minute * 60
    assert Time.day == Time.hour * 24
    assert Time.week == Time.day * 7


# ---------------------------------------------------------------------------
# Timezone offset
# ---------------------------------------------------------------------------


def test_get_timezone_offset_returns_int():
    assert isinstance(Time.get_timezone_offset(), int)


def test_set_timezone_offset_then_get():
    Time.set_timezone_offset(-300)
    assert Time.get_timezone_offset() == -300
    # Restore a reasonable default so other tests behave.
    Time.set_timezone_offset(_time.timezone // 60)


# ---------------------------------------------------------------------------
# parseTime
# ---------------------------------------------------------------------------


def test_parse_time_days():
    assert Time.parseTime("1d") == Time.day
    assert Time.parseTime("7d") == 7 * Time.day


def test_parse_time_hours():
    assert Time.parseTime("1h") == Time.hour
    assert Time.parseTime("12h") == 12 * Time.hour


def test_parse_time_minutes():
    assert Time.parseTime("1m") == Time.minute
    assert Time.parseTime("30m") == 30 * Time.minute


def test_parse_time_seconds():
    assert Time.parseTime("1s") == Time.second
    assert Time.parseTime("5s") == 5 * Time.second


def test_parse_time_weeks():
    assert Time.parseTime("1w") == Time.week
    assert Time.parseTime("2w") == 2 * Time.week


def test_parse_time_combined_short():
    assert Time.parseTime("1h30m") == Time.hour + 30 * Time.minute


def test_parse_time_combined_full():
    expected = Time.week + 2 * Time.day + 3 * Time.hour + 4 * Time.minute + 5 * Time.second
    assert Time.parseTime("1w2d3h4m5s") == expected


def test_parse_time_with_decimal():
    assert Time.parseTime("1.5h") == int(1.5 * Time.hour)


def test_parse_time_singular_unit_names():
    assert Time.parseTime("1day") == Time.day
    assert Time.parseTime("1hour") == Time.hour
    assert Time.parseTime("1minute") == Time.minute
    assert Time.parseTime("1second") == Time.second
    assert Time.parseTime("1week") == Time.week


def test_parse_time_invalid_returns_zero():
    assert Time.parseTime("abc") == 0
    assert Time.parseTime("1") == 0  # No unit → no match
    assert Time.parseTime("") == 0


# ---------------------------------------------------------------------------
# parseDate
# ---------------------------------------------------------------------------


def test_parse_date_offset_returns_datetime_in_one_hour():
    """``parseDate("1h")`` returns a datetime approximately one hour from now."""
    before_ms = int(_time.time() * 1000)
    result = Time.parseDate("1h")
    delta_ms = result - before_ms
    # The function uses ``Date.now() + parsed`` so allow generous bounds.
    assert Time.hour - 100 < delta_ms < Time.hour + 1000


def test_parse_date_empty_returns_now():
    """Empty input falls through to ``new Date()``."""
    before_ms = int(_time.time() * 1000)
    result = Time.parseDate("")
    delta_ms = result - before_ms
    assert -100 < delta_ms < 1000


def test_parse_date_iso_format():
    """``parseDate("2024-06-15")`` recognises an ISO-style date string."""
    result = Time.parseDate("2024-06-15")
    assert isinstance(result, int)  # implementation returns ms since epoch
    # Sanity check: ~2024-06-15 epoch ms
    expected_ms = int(datetime(2024, 6, 15, tzinfo=UTC).timestamp() * 1000)
    assert abs(result - expected_ms) < Time.day


def test_parse_date_hh_mm_colon():
    """``"HH:MM"`` pattern combines with today's date in MM/DD/YYYY form."""
    before_ms = int(_time.time() * 1000)
    result = Time.parseDate("12:30")
    after_ms = int(_time.time() * 1000)
    assert isinstance(result, int)
    # The result should land within the current 24-hour window.
    assert before_ms - Time.day <= result <= after_ms + Time.day


def test_parse_date_hh_mm_ss_colon():
    """``"HH:MM:SS"`` is also supported."""
    before_ms = int(_time.time() * 1000)
    result = Time.parseDate("12:30:45")
    after_ms = int(_time.time() * 1000)
    assert isinstance(result, int)
    assert before_ms - Time.day <= result <= after_ms + Time.day


def test_parse_date_dmy():
    """``"DD-MM-YY"`` pattern uses the current year."""
    current_year = datetime.now(tz=UTC).year
    result = Time.parseDate("15-06-24")
    assert isinstance(result, int)
    # Convert back and check the year matches.
    result_year = datetime.fromtimestamp(result / 1000, tz=UTC).year
    assert result_year == current_year


def test_parse_date_dmy_with_time():
    """``"DD-MM-YY:HH:MM"`` combines date and time."""
    result = Time.parseDate("15-06-24:14:30")
    assert isinstance(result, int)


def test_parse_date_dmy_with_time_one_colon():
    """``"DD-MM-YY:HH"`` is also supported (matches the 1-colon regex group)."""
    result = Time.parseDate("15-06-24:14")
    assert isinstance(result, int)


def test_parse_date_hms_with_invalid_hour_falls_back():
    """An unparseable HMS string falls back to ``now`` rather than raising."""
    before_ms = int(_time.time() * 1000)
    result = Time.parseDate("99:30")  # hour 99 is invalid
    after_ms = int(_time.time() * 1000)
    assert before_ms - 100 <= result <= after_ms + 1000


def test_parse_date_dmy_with_invalid_day_falls_back():
    """An unparseable DMY string falls back to ``now`` rather than raising."""
    before_ms = int(_time.time() * 1000)
    result = Time.parseDate("99-99-24")
    after_ms = int(_time.time() * 1000)
    assert before_ms - 100 <= result <= after_ms + 1000


def test_parse_date_iso_with_z_suffix():
    """Freeform parses ISO ``...Z`` (Zulu) variants."""
    # ``2024-06-15T12:00:00Z`` is unambiguous UTC.
    expected_ms = int(datetime(2024, 6, 15, 12, 0, 0, tzinfo=UTC).timestamp() * 1000)
    result = Time.parseDate("2024-06-15T12:00:00Z")
    assert abs(result - expected_ms) < 1000


def test_parse_date_invalid_returns_now():
    """Unrecognised strings fall back to ``now``."""
    before_ms = int(_time.time() * 1000)
    result = Time.parseDate("not a date at all")
    after_ms = int(_time.time() * 1000)
    assert before_ms - 100 <= result <= after_ms + 1000


# ---------------------------------------------------------------------------
# format
# ---------------------------------------------------------------------------


def test_format_days():
    assert Time.format(Time.day) == "1d"
    assert Time.format(2 * Time.day) == "2d"


def test_format_hours():
    assert Time.format(Time.hour) == "1h"
    assert Time.format(2 * Time.hour) == "2h"


def test_format_minutes():
    assert Time.format(Time.minute) == "1m"
    assert Time.format(5 * Time.minute) == "5m"


def test_format_seconds():
    assert Time.format(Time.second) == "1s"
    assert Time.format(5 * Time.second) == "5s"


def test_format_milliseconds():
    assert Time.format(500) == "500ms"
    assert Time.format(0) == "0ms"
    assert Time.format(999) == "999ms"


def test_format_negative_keeps_sign():
    """Negative durations keep their sign in the output."""
    assert Time.format(-Time.day) == "-1d"
    assert Time.format(-Time.hour) == "-1h"


def test_format_thresholds_round_nearest():
    """Format thresholds round to the nearest unit (JS Math.round semantics)."""
    # Just below 1 day → hours
    assert Time.format(Time.day - Time.hour // 2 - 1) == "23h"
    # Just below 1 hour → minutes
    assert Time.format(Time.hour - Time.minute // 2 - 1) == "59m"


# ---------------------------------------------------------------------------
# toDigits
# ---------------------------------------------------------------------------


def test_to_digits_default_two():
    assert Time.toDigits(5) == "05"
    assert Time.toDigits(12) == "12"
    assert Time.toDigits(0) == "00"
    assert Time.toDigits(99) == "99"


def test_to_digits_custom_length():
    assert Time.toDigits(5, 4) == "0005"
    assert Time.toDigits(123, 3) == "123"
    assert Time.toDigits(0, 3) == "000"


def test_to_digits_already_wide_enough():
    """Values longer than the target length are returned unchanged."""
    assert Time.toDigits(1234, 2) == "1234"
    assert Time.toDigits(123456, 4) == "123456"


# ---------------------------------------------------------------------------
# template
# ---------------------------------------------------------------------------


@pytest.fixture
def fixed_time() -> datetime:
    # ``678_000`` microseconds = 678 milliseconds (datetime stores μs only).
    return datetime(2024, 6, 15, 12, 30, 45, 678_000, tzinfo=UTC)


def test_template_yyyy(fixed_time):
    assert Time.template("yyyy", fixed_time) == "2024"


def test_template_yy(fixed_time):
    assert Time.template("yy", fixed_time) == "24"


def test_template_MM(fixed_time):
    assert Time.template("MM", fixed_time) == "06"


def test_template_dd(fixed_time):
    assert Time.template("dd", fixed_time) == "15"


def test_template_hh(fixed_time):
    assert Time.template("hh", fixed_time) == "12"


def test_template_mm(fixed_time):
    assert Time.template("mm", fixed_time) == "30"


def test_template_ss(fixed_time):
    assert Time.template("ss", fixed_time) == "45"


def test_template_SSS(fixed_time):
    """``SSS`` is always 3-digit padded milliseconds."""
    assert Time.template("SSS", fixed_time) == "678"


def test_template_combined(fixed_time):
    assert Time.template("yyyy-MM-dd hh:mm:ss.SSS", fixed_time) == "2024-06-15 12:30:45.678"


def test_template_no_match_passes_through():
    """Placeholder-less templates pass through unchanged."""
    assert Time.template("hello world", datetime(2024, 1, 1, tzinfo=UTC)) == "hello world"


def test_template_default_time_is_now():
    """``template`` without a ``time`` arg uses ``new Date()`` — result has current year."""
    result = Time.template("yyyy")
    current_year = str(datetime.now(tz=UTC).year)
    assert result == current_year


# ---------------------------------------------------------------------------
# getDateNumber / fromDateNumber
# ---------------------------------------------------------------------------


def test_get_date_number_returns_int():
    assert isinstance(Time.getDateNumber(), int)


def test_get_date_number_with_epoch_zero():
    """Epoch ms 0 with offset 0 → 0 (the day-number of Jan 1 1970 UTC)."""
    Time.set_timezone_offset(0)
    n = Time.getDateNumber(0, 0)
    assert n == 0


def test_get_date_number_with_specific_date_and_explicit_offset():
    """Fixed offset gives a stable result regardless of system timezone.

    Using midnight UTC keeps the round-trip lossless.
    """
    Time.set_timezone_offset(0)
    epoch_ms = datetime(2024, 6, 15, 0, 0, 0, tzinfo=UTC).timestamp() * 1000
    n = Time.getDateNumber(epoch_ms, 0)
    # Recompute expected value with the same TS formula
    # (Math.floor is JS-style floor = Python's math.floor).
    import math
    expected = math.floor((epoch_ms / Time.minute - 0) / 1440)
    assert n == expected


def test_get_date_number_accepts_datetime_with_valueOf():
    """Objects exposing ``valueOf()`` are accepted (mirrors ``Date.valueOf``)."""

    class FakeDate:
        def valueOf(self) -> float:
            return datetime(2024, 6, 15, tzinfo=UTC).timestamp() * 1000

    Time.set_timezone_offset(0)
    n = Time.getDateNumber(FakeDate(), 0)  # type: ignore[arg-type]
    # Sample: 2024-06-15 UTC midnight → day 19889 from epoch day 0.
    import math
    ms = datetime(2024, 6, 15, tzinfo=UTC).timestamp() * 1000
    expected = math.floor((ms / Time.minute - 0) / 1440)
    assert n == expected


def test_from_date_number_default_offset():
    """``fromDateNumber`` falls back to the cached timezone when no offset given."""
    Time.set_timezone_offset(-300)
    result = Time.fromDateNumber(0)
    expected = int(0 * Time.day + (-300) * Time.minute)
    assert result == expected
    # Restore.
    Time.set_timezone_offset(_time.timezone // 60)


def test_from_date_number_round_trip_with_zero_offset():
    """``from_date_number(get_date_number(d, 0), 0)`` yields ``d`` (lossless for midnight)."""
    Time.set_timezone_offset(0)
    epoch_ms = datetime(2024, 6, 15, 0, 0, 0, tzinfo=UTC).timestamp() * 1000
    n = Time.getDateNumber(epoch_ms, 0)
    reconstructed = Time.fromDateNumber(n, 0)
    assert reconstructed == epoch_ms


# ---------------------------------------------------------------------------
# Parametrised
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "input_,expected_ms",
    [
        ("1w", Time.week),
        ("1d", Time.day),
        ("1h", Time.hour),
        ("1m", Time.minute),
        ("1s", Time.second),
        ("2h", 2 * Time.hour),
        ("30m", 30 * Time.minute),
    ],
)
def test_parse_time_parametrized(input_, expected_ms):
    assert Time.parseTime(input_) == expected_ms


@pytest.mark.parametrize(
    "ms,expected",
    [
        (Time.day, "1d"),
        (2 * Time.day, "2d"),
        (Time.hour, "1h"),
        (Time.minute, "1m"),
        (Time.second, "1s"),
        (500, "500ms"),
        (0, "0ms"),
        (-Time.day, "-1d"),
    ],
)
def test_format_parametrized(ms, expected):
    assert Time.format(ms) == expected
