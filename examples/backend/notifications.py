"""Powiadomienia (fikcyjne): sztywne przesunięcia."""
from datetime import datetime, timedelta

from db import query_all


def shifted_sql():
    return query_all("SELECT sent_at + interval '2 hours' FROM mails")


def zone_offset_sql():
    return query_all("SELECT created_at AT TIME ZONE '+02' FROM orders")


def relative_window_is_fine():
    return query_all("SELECT id FROM mails WHERE sent_at > NOW() - interval '2 hours'")


def local_now_py():
    return datetime.utcnow() + timedelta(hours=2)
