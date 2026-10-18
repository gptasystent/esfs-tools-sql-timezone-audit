"""Zmiany pracowników magazynu (fikcyjne)."""
from db import execute, query_all

UPCOMING_SQL = """
    SELECT id, starts_at
    FROM shifts
    -- starts_at porównywane z CURRENT_DATE w komentarzu nie liczy się
    WHERE starts_at BETWEEN NOW() AND NOW() + interval '1 day'
    ORDER BY starts_at
"""


def upcoming_shifts():
    return query_all(UPCOMING_SQL)


def late_shifts():
    return query_all("SELECT id FROM shifts WHERE ends_at < CURRENT_TIMESTAMP")


def shifts_local_ok():
    return query_all(
        "SELECT id FROM shifts WHERE starts_at > NOW() AT TIME ZONE 'Europe/Warsaw'")


def restart_shift(shift_id):
    execute("UPDATE shifts SET starts_at = NOW() WHERE id = %s", (shift_id,))


def touch_shift(shift_id):
    execute("UPDATE shifts SET updated_at = NOW() WHERE id = %s", (shift_id,))
