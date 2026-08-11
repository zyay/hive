"""
Full cron expression parser — supports standard 5-field cron syntax.
No external dependencies.
"""

import re
import time
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def is_due(cron_expression: str, last_run: float = None) -> bool:
    """Check if a cron job is due to run."""
    if last_run is None:
        return True
    next_run = next_run_time(cron_expression, last_run)
    return datetime.now() >= next_run


def next_run_time(cron_expression: str, from_timestamp: float = None) -> datetime:
    """Calculate the next run time for a cron expression."""
    if from_timestamp is None:
        from_timestamp = time.time()

    fields = cron_expression.strip().split()
    if len(fields) != 5:
        raise ValueError(f"Invalid cron expression: {cron_expression} (expected 5 fields)")

    minute_f, hour_f, dom_f, month_f, dow_f = fields
    now = datetime.fromtimestamp(from_timestamp)

    # Start checking from the next minute
    dt = now.replace(second=0, microsecond=0)
    for _ in range(525960):  # max ~1 year of minutes
        dt = _add_minute(dt)
        if _matches(dt, minute_f, hour_f, dom_f, month_f, dow_f):
            return dt

    raise ValueError(f"Could not find next run time for: {cron_expression}")


def _add_minute(dt: datetime) -> datetime:
    """Add one minute to a datetime."""
    from datetime import timedelta
    return dt + timedelta(minutes=1)


def _matches(dt: datetime, minute_f: str, hour_f: str, dom_f: str, month_f: str, dow_f: str) -> bool:
    """Check if a datetime matches all cron fields."""
    return (
        _field_matches(dt.minute, minute_f, 0, 59)
        and _field_matches(dt.hour, hour_f, 0, 23)
        and _field_matches(dt.day, dom_f, 1, 31)
        and _field_matches(dt.month, month_f, 1, 12)
        and _field_matches(dt.weekday(), dow_f, 0, 6, offset=1)  # cron: 0=Sunday, Python: 0=Monday
    )


def _field_matches(value: int, field: str, min_val: int, max_val: int, offset: int = 0) -> bool:
    """Check if a value matches a single cron field."""
    if field == "*":
        return True

    # Handle comma-separated values
    for part in field.split(","):
        # Handle step values (e.g., */5, 1-10/2)
        if "/" in part:
            range_part, step = part.split("/", 1)
            step = int(step)
            if range_part == "*":
                start, end = min_val, max_val
            elif "-" in range_part:
                start, end = map(int, range_part.split("-"))
            else:
                start = int(range_part)
                end = max_val
            adjusted = value - offset if offset else value
            if start <= adjusted <= end and (adjusted - start) % step == 0:
                return True
        # Handle ranges (e.g., 1-5)
        elif "-" in part:
            start, end = map(int, part.split("-"))
            adjusted = value - offset if offset else value
            if start <= adjusted <= end:
                return True
        # Handle single values
        else:
            adjusted = int(part)
            if offset:
                adjusted = (adjusted + offset) % 7
            if value == adjusted:
                return True

    return False


def describe_cron(expression: str) -> str:
    """Return a human-readable description of a cron expression."""
    fields = expression.strip().split()
    if len(fields) != 5:
        return "Invalid cron expression"

    minute_f, hour_f, dom_f, month_f, dow_f = fields

    parts = []
    if minute_f == "*" and hour_f == "*":
        parts.append("every minute")
    elif minute_f.startswith("*/"):
        parts.append(f"every {minute_f[2:]} minutes")
    elif hour_f == "*":
        parts.append(f"at minute {minute_f} of every hour")
    elif hour_f.startswith("*/"):
        parts.append(f"every {hour_f[2:]} hours at minute {minute_f}")
    else:
        parts.append(f"at {hour_f.zfill(2)}:{minute_f.zfill(2)}")

    if dom_f != "*":
        parts.append(f"on day {dom_f} of month")
    if month_f != "*":
        months = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        try:
            parts.append(f"in {months[int(month_f)]}")
        except (ValueError, IndexError):
            parts.append(f"in month {month_f}")
    if dow_f != "*":
        days = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
        try:
            parts.append(f"on {days[int(dow_f)]}")
        except (ValueError, IndexError):
            parts.append(f"on weekday {dow_f}")

    return " ".join(parts)
