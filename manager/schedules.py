"""Minute-resolution weekly schedules evaluated on real UTC instants.

An overnight window belongs to its starting weekday. A repeated DST wall time
applies in both folds; a skipped wall time has no real instant to execute in.
"""
from __future__ import annotations

import datetime as dt
from functools import lru_cache
import os
from pathlib import Path
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from core.exceptions import ValidationError

WINDOW = re.compile(r"^\s*(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})\s*$")


def normalize_windows(value: str) -> str:
    parts = value.split(";")
    if not 1 <= len(parts) <= 16:
        raise ValidationError("Use one to sixteen HH:MM-HH:MM windows separated by semicolons.")
    result = []
    for part in parts:
        match = WINDOW.fullmatch(part)
        if not match:
            raise ValidationError("Schedule must use HH:MM-HH:MM windows separated by semicolons.")
        sh, sm, eh, em = map(int, match.groups())
        if sh > 23 or eh > 23 or sm > 59 or em > 59:
            raise ValidationError("Schedule must contain valid 24-hour times.")
        result.append(f"{sh:02d}:{sm:02d}-{eh:02d}:{em:02d}")
    return ";".join(dict.fromkeys(result))


def normalize_days(value="0,1,2,3,4,5,6") -> str:
    try:
        days = {int(item) for item in value.split(",")}
    except (ValueError, AttributeError) as exc:
        raise ValidationError("Weekdays must be comma-separated numbers 0 (Monday) to 6 (Sunday).") from exc
    if not days or not days <= set(range(7)):
        raise ValidationError("Select at least one weekday from 0 (Monday) to 6 (Sunday).")
    return ",".join(map(str, sorted(days)))


@lru_cache(maxsize=64)
def _iana_zone(name):
    return ZoneInfo(name)


@lru_cache(maxsize=4)
def _system_zone(stamp):
    with Path("/etc/localtime").open("rb") as stream:
        return ZoneInfo.from_file(stream)


def zone(name="local"):
    try:
        if name == "local":
            if os.environ.get("TZ"):
                return _iana_zone(os.environ["TZ"].lstrip(":"))
            try:
                return _system_zone(Path("/etc/localtime").stat().st_mtime_ns)
            except OSError:
                return dt.datetime.now().astimezone().tzinfo
        return _iana_zone(name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValidationError(f"Unknown IANA time zone: {name}") from exc


def utc_instant(when: dt.datetime | None = None) -> dt.datetime:
    when = when or dt.datetime.now(dt.UTC)
    return when.astimezone(dt.UTC) if when.tzinfo else when.replace(tzinfo=zone()).astimezone(dt.UTC)


@lru_cache(maxsize=1024)
def windows(schedule):
    return tuple(tuple(int(t[:2]) * 60 + int(t[3:]) for t in part.split("-"))
                 for part in normalize_windows(schedule).split(";"))


def active(schedule, when=None, *, timezone="local", weekdays="0,1,2,3,4,5,6"):
    tz = zone(timezone)
    if isinstance(when, dt.time):
        # Legacy time-only calls retain daily wall-clock semantics.
        minute, day = when.hour * 60 + when.minute, 0
        days = set(range(7))
    else:
        when = when or dt.datetime.now(dt.UTC)
        local = when.astimezone(tz) if when.tzinfo else when.replace(tzinfo=tz)
        minute, day = local.hour * 60 + local.minute, local.weekday()
        days = {int(item) for item in normalize_days(weekdays).split(",")}
    for start, end in windows(schedule):
        if start == end and day in days:
            return True
        if start < end and day in days and start <= minute < end:
            return True
        if start > end and (minute >= start and day in days or minute < end and (day - 1) % 7 in days):
            return True
    return False


@lru_cache(maxsize=2048)
def _next_change(schedule, timezone, weekdays, minute):
    before = active(schedule, minute, timezone=timezone, weekdays=weekdays)
    if weekdays == "0,1,2,3,4,5,6" and any(a == b for a, b in windows(schedule)):
        return None
    # UTC iteration covers DST gaps and both folds without inventing local
    # instants. Eight days include the next weekly transition across DST.
    for offset in range(1, 8 * 24 * 60 + 1):
        candidate = minute + dt.timedelta(minutes=offset)
        if active(schedule, candidate, timezone=timezone, weekdays=weekdays) != before:
            return candidate
    return None


def next_change(rule, when=None):
    if not rule.enabled:
        return None
    minute = utc_instant(when).replace(second=0, microsecond=0)
    return _next_change(rule.schedule, rule.timezone, rule.weekdays, minute)


@lru_cache(maxsize=512)
def _week_mask(schedule, timezone, weekdays, anchor):
    mask = 0
    for minute in range(8 * 24 * 60):
        if active(schedule, anchor + dt.timedelta(minutes=minute), timezone=timezone, weekdays=weekdays):
            mask |= 1 << minute
    return mask


def overlaps(left, right, when=None):
    anchor = utc_instant(when).replace(hour=0, minute=0, second=0, microsecond=0)
    return bool(_week_mask(left.schedule, left.timezone, left.weekdays, anchor) &
                _week_mask(right.schedule, right.timezone, right.weekdays, anchor))
