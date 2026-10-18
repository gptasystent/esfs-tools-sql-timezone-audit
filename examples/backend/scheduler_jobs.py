"""Zadania cykliczne (fikcyjne)."""
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

scheduler = BackgroundScheduler()


def send_digest():
    pass


def purge():
    pass


scheduler.add_job(send_digest, "cron", hour=6, minute=30)
scheduler.add_job(send_digest, "cron", hour=6, minute=30, timezone="Europe/Warsaw")
scheduler.add_job(purge, "interval", minutes=15)
scheduler.add_job(purge, CronTrigger(hour=3))
scheduler.add_job(purge, CronTrigger(hour=3, timezone="Europe/Warsaw"))


@scheduler.scheduled_job("cron", day_of_week="mon", hour=7)
def weekly_report():
    pass
