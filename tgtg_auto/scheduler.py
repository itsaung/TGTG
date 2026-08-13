"""Waiting until a target wall-clock time.

Bags are released at a fixed time and go in seconds, so the wait ends with a
short spin rather than a single long sleep: sleep() only guarantees a lower
bound on its duration, and being a second late is the difference between
getting a bag and not.
"""

import re
import time
from datetime import datetime, timedelta, timezone

TIME_PATTERN = re.compile(r"^(\d{1,2}):(\d{2})(?::(\d{2}))?$")

# how long before the target to stop sleeping and start spinning
SPIN_LEAD_SECONDS = 2.0


class TimeFormatError(ValueError):
    pass


def parse_time(value: str) -> tuple:
    """Parse 'HH:MM' or 'HH:MM:SS' into (hour, minute, second)."""
    match = TIME_PATTERN.match(value.strip())
    if not match:
        raise TimeFormatError(f"Expected HH:MM or HH:MM:SS, got {value!r}")

    hour, minute, second = (int(part or 0) for part in match.groups())
    if hour > 23 or minute > 59 or second > 59:
        raise TimeFormatError(f"Not a valid time of day: {value!r}")
    return hour, minute, second


def utc_to_local(value: str) -> datetime:
    """Convert an API timestamp like 2026-08-13T04:49:14Z to local naive time.

    The rest of the module works in naive local time because that is what the
    user types; this is the one place the two meet.
    """
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone().replace(tzinfo=None)


def next_occurrence(hour: int, minute: int, second: int, now: datetime = None) -> datetime:
    """The next datetime matching the given time, tomorrow if it passed today."""
    now = now or datetime.now()
    target = now.replace(hour=hour, minute=minute, second=second, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return target


def wait_until(target: datetime, announce=print) -> None:
    remaining = (target - datetime.now()).total_seconds()
    if remaining <= 0:
        return

    announce(f"Waiting until {target:%Y-%m-%d %H:%M:%S} ({remaining:.0f}s)")

    coarse = remaining - SPIN_LEAD_SECONDS
    if coarse > 0:
        time.sleep(coarse)

    # tighten up for the last couple of seconds
    while datetime.now() < target:
        time.sleep(0.005)
