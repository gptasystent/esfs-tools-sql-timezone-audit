"""Pliki i logi (fikcyjne): data nie trafia do SQL."""
import logging
from datetime import date, datetime

log = logging.getLogger(__name__)


def export_name():
    return f"export_{date.today():%Y%m%d}.csv"


def log_start():
    log.info("start %s", datetime.now())


def sql_in_text_is_fine():
    note = "SELECT CURRENT_DATE is only text here"
    return note
