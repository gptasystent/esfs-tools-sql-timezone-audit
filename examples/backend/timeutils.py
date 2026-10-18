"""Poprawne wzorce (fikcyjne): nic tu nie powinno być raportowane."""
from datetime import datetime
from zoneinfo import ZoneInfo

from db import query_all

WARSAW = ZoneInfo("Europe/Warsaw")


def today_local():
    return query_all("SELECT id FROM orders WHERE (created_at AT TIME ZONE 'Europe/Warsaw')::date = (NOW() AT TIME ZONE 'Europe/Warsaw')::date")


def today_local_func():
    return query_all("SELECT timezone('Europe/Warsaw', now())::date")


def now_local():
    return datetime.now(WARSAW)


def save_stamp():
    return query_all("UPDATE parts SET updated_at = now() WHERE id = 1")


def last_hour_local():
    return query_all("SELECT id FROM orders WHERE paid_at > (NOW() AT TIME ZONE 'Europe/Warsaw') - INTERVAL '1 hour'")
