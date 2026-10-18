"""Raporty sprzedaży (fikcyjne)."""
from db import query_all


def daily_totals():
    return query_all(
        "SELECT date_trunc('day', created_at) AS d, count(*) FROM orders GROUP BY 1")


def monthly_hours():
    return query_all("SELECT EXTRACT(HOUR FROM sent_at), count(*) FROM mails GROUP BY 1")


def october_orders():
    return query_all(
        "SELECT id FROM orders WHERE created_at >= '2026-10-01' AND created_at < '2026-11-01'")


def daily_totals_ok():
    return query_all(
        "SELECT date_trunc('day', created_at AT TIME ZONE 'Europe/Warsaw') AS d FROM orders")


def epoch_is_fine():
    return query_all("SELECT EXTRACT(EPOCH FROM created_at) FROM orders")


def by_alias():
    sql = "SELECT o.id FROM orders o WHERE DATE(o.paid_at) = %s"
    return query_all(sql, ("x",))
