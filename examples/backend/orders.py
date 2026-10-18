"""Zamówienia sklepu z częściami (fikcyjne)."""
from datetime import date, datetime

from db import execute, query_all, query_one


def next_order_number():
    prefix = f"ZAM/{date.today():%Y/%m}/"
    row = query_one("SELECT count(*) FROM orders WHERE number LIKE %s", (prefix + "%",))
    return prefix + str(row[0] + 1)


def next_invoice_number_sql():
    return query_one("SELECT 'FV/' || to_char(CURRENT_DATE, 'YYYY/MM') || '/1'")


def orders_today():
    return query_all("SELECT id FROM orders WHERE created_at::date = CURRENT_DATE")


def mark_paid(order_id):
    execute("UPDATE orders SET paid_at = now(), updated_at = now() WHERE id = %s", (order_id,))


def close_overdue():
    stamp = datetime.now()
    execute("UPDATE orders SET status = 'closed' WHERE due_date < %s", (stamp,))


def is_overdue(order_id):
    row = query_one("SELECT due_date FROM orders WHERE id = %s", (order_id,))
    return row[0] < datetime.now()


def next_invoice_number(seq):
    today = datetime.now()
    return f"FV/{today.year}/{seq}"
