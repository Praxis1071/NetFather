"""Time helpers shared across NetFather.

SQLite currently stores NetFather timestamps as naive UTC datetimes.  Python
3.12+ deprecates :func:`datetime.datetime.utcnow`, so this module keeps the
existing storage contract while obtaining the time from an explicit UTC
clock.
"""

from __future__ import annotations

import datetime as dt


def utc_now() -> dt.datetime:
    """Return the current UTC time as a naive ``datetime`` for SQLite storage."""
    return dt.datetime.now(dt.UTC).replace(tzinfo=None)


def to_local(value: dt.datetime, tz: dt.tzinfo | None = None) -> dt.datetime:
    """Render stored naive UTC timestamps without interpreting them as local."""
    aware = value if value.tzinfo is not None else value.replace(tzinfo=dt.UTC)
    return aware.astimezone(tz)
