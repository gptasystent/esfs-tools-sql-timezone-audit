"""Kolumny spoza plików wejściowych: tylko heurystyka po nazwie (uncertain)."""
from db import query_all


def planned_today():
    return query_all("SELECT id FROM deliveries WHERE planned_date < NOW()")


def built_sql(table):
    parts = ["SELECT id FROM " + table]
    parts.append("WHERE delivered_at >= '2026-10-01'")
    return query_all(" ".join(parts))


def dynamic_sql(extra):
    sql = f"SELECT id FROM parts WHERE {extra} AND created_at::date = CURRENT_DATE"
    return query_all(sql)
