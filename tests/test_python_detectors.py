"""Kategorie Pythona, śledzenie SQL w funkcji, aliasy, harmonogramy."""
import unittest

from tests.helpers import kategorie, wyniki


class NaiveNow(unittest.TestCase):
    def test_now_param_to_sql(self):
        src = """
        from datetime import datetime
        def f(cur):
            cur.execute("SELECT 1 FROM t WHERE x < %s", (datetime.now(),))
        """
        self.assertEqual(kategorie(src), ["py_naive_now"])

    def test_now_via_variable_to_sql(self):
        src = """
        from datetime import datetime
        def f(cur):
            teraz = datetime.now()
            params = (1, teraz)
            cur.execute("UPDATE t SET x = %s", params)
        """
        self.assertEqual(kategorie(src), ["py_naive_now"])

    def test_today_param_to_sql(self):
        src = """
        from datetime import date
        def f(q):
            q.query_all("SELECT 1 FROM t WHERE d = %s", (date.today(),))
        """
        self.assertEqual(kategorie(src), ["py_naive_now"])

    def test_compare_with_db_value(self):
        src = """
        from datetime import datetime
        from db import query_one
        def f():
            row = query_one("SELECT due_date FROM t")
            return row[0] < datetime.now()
        """
        self.assertEqual(kategorie(src), ["py_naive_now"])

    def test_compare_in_loop(self):
        src = """
        from datetime import datetime
        from db import query_all
        def f():
            for r in query_all("SELECT starts_at FROM t"):
                if r["starts_at"] > datetime.now():
                    return r
        """
        w = wyniki(src)
        self.assertEqual([(x.kategoria, x.pewnosc) for x in w], [("py_naive_now", "likely")])

    def test_unknown_usage_is_other(self):
        src = """
        from datetime import datetime
        def f():
            return datetime.now()
        """
        self.assertEqual(kategorie(src), ["py_naive_now_other"])

    def test_tz_positional_not_naive(self):
        src = """
        from datetime import datetime, timezone
        def f():
            return datetime.now(timezone.utc)
        """
        self.assertEqual(kategorie(src), [])

    def test_tz_keyword_not_naive(self):
        src = """
        import datetime
        def f(tz):
            return datetime.datetime.now(tz=tz)
        """
        self.assertEqual(kategorie(src), [])

    def test_tz_none_is_naive(self):
        src = """
        from datetime import datetime
        def f():
            return datetime.now(tz=None)
        """
        self.assertEqual(kategorie(src), ["py_naive_now_other"])

    def test_import_alias(self):
        src = """
        from datetime import datetime as dt
        def f(cur):
            cur.execute("SELECT 1 WHERE x < %s", (dt.now(),))
        """
        self.assertEqual(kategorie(src), ["py_naive_now"])

    def test_module_alias(self):
        src = """
        import datetime as dtm
        def f(cur):
            cur.execute("SELECT 1 WHERE x < %s", (dtm.date.today(),))
        """
        self.assertEqual(kategorie(src), ["py_naive_now"])

    def test_non_datetime_now_ignored(self):
        src = """
        def f(clock):
            return clock.now()
        """
        self.assertEqual(kategorie(src), [])

    def test_in_test_file_is_other(self):
        src = """
        from datetime import date
        def f(cur):
            cur.execute("SELECT 1 WHERE d = %s", (date.today(),))
        """
        self.assertEqual(kategorie(src, plik="test_orders.py", plik_testowy=True), ["py_naive_now_other"])

    def test_in_test_function_is_other(self):
        src = """
        from datetime import date
        def test_something(cur):
            cur.execute("SELECT 1 WHERE d = %s", (date.today(),))
        """
        self.assertEqual(kategorie(src), ["py_naive_now_other"])

    def test_filename_use_is_other(self):
        src = """
        from datetime import date
        def f():
            return "raport_%s.csv" % date.today().isoformat()
        """
        self.assertEqual(kategorie(src), ["py_naive_now_other"])

    def test_default_argument_is_other(self):
        src = """
        from datetime import date
        def f(day=date.today()):
            return day
        """
        self.assertEqual(kategorie(src), ["py_naive_now_other"])

    def test_sql_text_in_plain_string_is_not_sql(self):
        src = """
        def f(x):
            msg = "SELECT CURRENT_DATE"
            return msg
        """
        self.assertEqual(kategorie(src), [])


class UtcnowAndOffsets(unittest.TestCase):
    def test_utcnow_deprecated_always(self):
        src = """
        from datetime import datetime
        def f():
            return datetime.utcnow()
        """
        self.assertEqual(kategorie(src), ["py_naive_now_other", "py_utcnow_deprecated"])

    def test_utcnow_in_sql_both(self):
        src = """
        from datetime import datetime
        def f(cur):
            cur.execute("INSERT INTO t (x) VALUES (%s)", (datetime.utcnow(),))
        """
        self.assertEqual(kategorie(src), ["py_naive_now", "py_utcnow_deprecated"])

    def test_utcfromtimestamp(self):
        src = """
        from datetime import datetime
        def f(ts):
            return datetime.utcfromtimestamp(ts)
        """
        self.assertIn("py_utcnow_deprecated", kategorie(src))

    def test_utcnow_reference_as_default(self):
        src = """
        from datetime import datetime
        def f(factory=datetime.utcnow):
            return factory
        """
        self.assertEqual(kategorie(src), ["py_utcnow_deprecated"])

    def test_timedelta_two_hours(self):
        src = """
        from datetime import datetime, timedelta
        def f():
            return datetime.now() + timedelta(hours=2)
        """
        self.assertIn("py_fixed_offset", kategorie(src))

    def test_timedelta_via_variable(self):
        src = """
        from datetime import datetime, timedelta
        def f():
            n = datetime.utcnow()
            return n - timedelta(hours=1)
        """
        self.assertIn("py_fixed_offset", kategorie(src))

    def test_timedelta_three_hours_ignored(self):
        src = """
        from datetime import datetime, timedelta
        def f():
            return datetime.now() + timedelta(hours=3)
        """
        self.assertNotIn("py_fixed_offset", kategorie(src))

    def test_timedelta_days_ignored(self):
        src = """
        from datetime import datetime, timedelta
        def f():
            return datetime.now() + timedelta(days=1)
        """
        self.assertNotIn("py_fixed_offset", kategorie(src))

    def test_timedelta_without_now_ignored(self):
        src = """
        from datetime import timedelta
        def f(x):
            return x + timedelta(hours=2)
        """
        self.assertEqual(kategorie(src), [])


class NumberingPython(unittest.TestCase):
    def test_fstring_year_month(self):
        src = """
        from datetime import date
        def f():
            return f"ZAM/{date.today():%Y/%m}/1"
        """
        self.assertEqual(kategorie(src), ["numbering_by_date"])

    def test_strftime_year_month(self):
        src = """
        from datetime import datetime
        def f():
            return "FV/" + datetime.now().strftime("%Y/%m")
        """
        self.assertEqual(kategorie(src), ["numbering_by_date"])

    def test_year_month_attributes(self):
        src = """
        from datetime import date
        def f():
            d = date.today()
            return f"{d.year}/{d.month:02d}"
        """
        self.assertEqual(kategorie(src), ["numbering_by_date"])

    def test_filename_with_day_is_not_numbering(self):
        src = """
        from datetime import date
        def f():
            return f"raport_{date.today():%Y%m%d}.csv"
        """
        self.assertEqual(kategorie(src), ["py_naive_now_other"])

    def test_day_format_with_number_hint(self):
        src = """
        from datetime import date
        def make_order_number():
            return f"{date.today():%Y%m%d}"
        """
        self.assertEqual(kategorie(src), ["numbering_by_date"])

    def test_aware_date_not_numbering(self):
        src = """
        from datetime import datetime
        def f(tz):
            return f"{datetime.now(tz):%Y/%m}"
        """
        self.assertEqual(kategorie(src), [])


class Scheduler(unittest.TestCase):
    def test_add_job_cron_without_timezone(self):
        src = """
        def f(scheduler, job):
            scheduler.add_job(job, "cron", hour=6, minute=30)
        """
        self.assertEqual(kategorie(src), ["scheduler_no_timezone"])

    def test_add_job_cron_with_timezone(self):
        src = """
        def f(scheduler, job):
            scheduler.add_job(job, "cron", hour=6, timezone="Europe/Warsaw")
        """
        self.assertEqual(kategorie(src), [])

    def test_interval_ignored(self):
        src = """
        def f(scheduler, job):
            scheduler.add_job(job, "interval", minutes=5)
        """
        self.assertEqual(kategorie(src), [])

    def test_decorator_cron(self):
        src = """
        @scheduler.scheduled_job("cron", hour=7)
        def job():
            pass
        """
        self.assertEqual(kategorie(src), ["scheduler_no_timezone"])

    def test_cron_trigger_object(self):
        src = """
        from apscheduler.triggers.cron import CronTrigger
        def f(scheduler, job):
            scheduler.add_job(job, CronTrigger(hour=3))
        """
        self.assertEqual(kategorie(src), ["scheduler_no_timezone"])

    def test_cron_trigger_with_timezone(self):
        src = """
        from apscheduler.triggers.cron import CronTrigger
        def f(scheduler, job):
            scheduler.add_job(job, CronTrigger(hour=3, timezone="Europe/Warsaw"))
        """
        self.assertEqual(kategorie(src), [])

    def test_cron_trigger_inside_job_with_timezone(self):
        src = """
        from apscheduler.triggers.cron import CronTrigger
        def f(scheduler, job):
            scheduler.add_job(job, CronTrigger(hour=3), timezone="Europe/Warsaw")
        """
        self.assertEqual(kategorie(src), [])

    def test_scheduler_level_timezone_trusted(self):
        src = """
        from apscheduler.schedulers.background import BackgroundScheduler
        sched = BackgroundScheduler(timezone="Europe/Warsaw")
        sched.add_job(print, "cron", hour=6)
        """
        self.assertEqual(kategorie(src), [])

    def test_cron_only_minutes_ignored(self):
        src = """
        def f(scheduler, job):
            scheduler.add_job(job, "cron", minute="*/5")
        """
        self.assertEqual(kategorie(src), [])

    def test_crontab_celery(self):
        src = """
        from celery.schedules import crontab
        S = {"nightly": {"schedule": crontab(hour=2, minute=0)}}
        """
        self.assertEqual(kategorie(src), ["scheduler_no_timezone"])

    def test_crontab_with_celery_timezone_config(self):
        src = """
        from celery.schedules import crontab
        timezone = "Europe/Warsaw"
        S = {"nightly": {"schedule": crontab(hour=2, minute=0)}}
        """
        self.assertEqual(kategorie(src), [])

    def test_from_crontab(self):
        src = """
        from apscheduler.triggers.cron import CronTrigger
        t = CronTrigger.from_crontab("30 6 * * *")
        """
        self.assertEqual(kategorie(src), ["scheduler_no_timezone"])

    def test_dict_config_trigger(self):
        src = """
        JOBS = [{"id": "a", "func": "x:y", "trigger": "cron", "hour": 6}]
        """
        self.assertEqual(kategorie(src), ["scheduler_no_timezone"])


if __name__ == "__main__":
    unittest.main()
