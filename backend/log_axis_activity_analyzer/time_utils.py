"""Shared timestamp parsing, formatting, duration, and PWM-normalization helpers."""

from __future__ import annotations

from datetime import datetime

from .config import TIMESTAMP_FORMAT


def parse_log_timestamp(timestamp_text: str) -> datetime | None:
    """Parse one log timestamp string, preserving millisecond precision."""

    try:
        return datetime.strptime(timestamp_text, TIMESTAMP_FORMAT)
    except ValueError:
        return None


def format_log_timestamp(value: datetime | None) -> str:
    """Format a datetime value back to the log timestamp layout."""

    if value is None:
        return ""
    return value.strftime("%Y-%m-%d %H:%M:%S:%f")[:-3]


def calculate_duration_values(start_time: datetime, end_time: datetime) -> tuple[int, float]:
    """Return duration in milliseconds and seconds for one matched event pair."""

    duration_ms = int(round((end_time - start_time).total_seconds() * 1000))
    duration_s = duration_ms / 1000.0
    return duration_ms, duration_s


def compute_time_delta_ms(left: datetime | None, right: datetime | None) -> int | None:
    """Return the absolute time delta in milliseconds between two datetimes."""

    if left is None or right is None:
        return None
    return int(round(abs((left - right).total_seconds()) * 1000))


def compute_range_distance_ms(
    reference_time: datetime | None,
    range_start: datetime | None,
    range_end: datetime | None,
) -> int | None:
    """Return the distance in milliseconds from a time to a file time window."""

    if reference_time is None or range_start is None or range_end is None:
        return None
    if range_start <= reference_time <= range_end:
        return 0
    if reference_time < range_start:
        return compute_time_delta_ms(reference_time, range_start)
    return compute_time_delta_ms(reference_time, range_end)


def normalize_pwm_percent(raw_value: float) -> float:
    """Return the absolute PWM percentage from a signed raw value."""

    return abs(raw_value)


def resolve_pwm_direction(raw_value: float) -> str:
    """Return a human-readable direction label for a signed PWM value."""

    return "Reverse" if raw_value < 0 else "Forward"
