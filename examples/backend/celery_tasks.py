"""Harmonogram w stylu Celery beat (fikcyjny)."""
from celery.schedules import crontab

BEAT = {
    "nightly": {"task": "tasks.nightly", "schedule": crontab(hour=2, minute=0)},
    "every-five": {"task": "tasks.ping", "schedule": crontab(minute="*/5")},
}
