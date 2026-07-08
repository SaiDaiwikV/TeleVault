"""Time helpers.

`datetime.utcnow()` is deprecated (and scheduled for removal) because it returns
a naive datetime that *looks* like local time. We still want naive UTC values so
they compare cleanly with the timezone-naive `DateTime` columns already in the
database, so `utcnow()` produces an aware UTC value and drops the tzinfo.
"""
from datetime import datetime, timezone


def utcnow() -> datetime:
    """Current UTC time as a timezone-naive datetime (for naive DB columns)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)
