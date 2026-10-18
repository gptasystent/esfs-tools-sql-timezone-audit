"""Stare helpery czasu (fikcyjne): aliasy importu i utcnow."""
import datetime as dtm
from datetime import datetime as dt, timezone

from db import execute


def stamp_event(event_id):
    ts = dt.utcnow()
    execute("INSERT INTO events (id, happened) VALUES (%s, %s)", (event_id, ts))


def aware_is_fine(event_id):
    execute("INSERT INTO events (id, happened) VALUES (%s, %s)",
            (event_id, dt.now(timezone.utc)))


def aware_tz_kw_is_fine(tz):
    return dtm.datetime.now(tz=tz)


def from_epoch(value):
    return dt.utcfromtimestamp(value)
