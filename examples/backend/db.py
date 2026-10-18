"""Cienkie helpery bazy (fikcyjne) - definicje nie są SQL-em."""
import psycopg2


def _cursor():
    return psycopg2.connect("dbname=demo").cursor()


def query_one(sql, params=None):
    cur = _cursor()
    cur.execute(sql, params)
    return cur.fetchone()


def query_all(sql, params=None):
    cur = _cursor()
    cur.execute(sql, params)
    return cur.fetchall()


def execute(sql, params=None):
    cur = _cursor()
    cur.execute(sql, params)
