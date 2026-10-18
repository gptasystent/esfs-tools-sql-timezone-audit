"""Kategorie SQL: przypadki pozytywne i negatywne."""
import unittest

from tests.helpers import sql, sql_kat, wyniki


class CurrentDateUtc(unittest.TestCase):
    def test_current_date_flagged(self):
        self.assertEqual(sql_kat("SELECT id FROM orders WHERE day = CURRENT_DATE"), ["sql_current_date_utc"])

    def test_lowercase_current_date(self):
        self.assertEqual(sql_kat("select 1 where d = current_date"), ["sql_current_date_utc"])

    def test_now_cast_date(self):
        self.assertEqual(sql_kat("SELECT now()::date"), ["sql_current_date_utc"])

    def test_current_timestamp_cast_date(self):
        self.assertEqual(sql_kat("SELECT CURRENT_TIMESTAMP::date"), ["sql_current_date_utc"])

    def test_cast_as_date(self):
        self.assertEqual(sql_kat("SELECT CAST(now() AS date)"), ["sql_current_date_utc"])

    def test_localtimestamp(self):
        self.assertEqual(sql_kat("SELECT localtimestamp"), ["sql_current_date_utc"])

    def test_at_time_zone_same_expression_not_flagged(self):
        self.assertEqual(sql_kat("SELECT (NOW() AT TIME ZONE 'Europe/Warsaw')::date"), [])

    def test_timezone_function_not_flagged(self):
        self.assertEqual(sql_kat("SELECT timezone('Europe/Warsaw', now())::date"), [])

    def test_current_date_at_time_zone_not_flagged(self):
        self.assertEqual(sql_kat("SELECT date_trunc('month', CURRENT_DATE) AT TIME ZONE 'Europe/Warsaw'"), [])

    def test_line_comment_ignored(self):
        self.assertEqual(sql_kat("SELECT 1 -- CURRENT_DATE here\nFROM t"), [])

    def test_block_comment_ignored(self):
        self.assertEqual(sql_kat("SELECT 1 /* CURRENT_DATE */ FROM t"), [])

    def test_string_literal_ignored(self):
        self.assertEqual(sql_kat("SELECT 'CURRENT_DATE' AS txt FROM t"), [])

    def test_plain_now_write_not_flagged(self):
        self.assertEqual(sql_kat("UPDATE parts SET updated_at = now() WHERE id = 1"), [])


class LocalVsNow(unittest.TestCase):
    def test_local_column_vs_now(self):
        self.assertEqual(sql_kat("SELECT 1 FROM shifts WHERE starts_at < NOW()"), ["sql_local_vs_now"])

    def test_reversed_operands(self):
        self.assertEqual(sql_kat("SELECT 1 FROM shifts WHERE NOW() > starts_at"), ["sql_local_vs_now"])

    def test_current_timestamp(self):
        self.assertEqual(sql_kat("SELECT 1 FROM shifts WHERE starts_at <= CURRENT_TIMESTAMP"), ["sql_local_vs_now"])

    def test_between_now(self):
        self.assertEqual(sql_kat("SELECT 1 FROM t WHERE starts_at BETWEEN NOW() AND NOW() + interval '1 day'"),
                         ["sql_local_vs_now"])

    def test_interval_arithmetic_on_now(self):
        self.assertEqual(sql_kat("SELECT 1 FROM t WHERE starts_at > NOW() - interval '7 days'"), ["sql_local_vs_now"])

    def test_system_column_vs_now_ok(self):
        self.assertEqual(sql_kat("SELECT 1 FROM t WHERE created_at < NOW()"), [])

    def test_at_time_zone_on_now_ok(self):
        self.assertEqual(sql_kat("SELECT 1 FROM t WHERE starts_at > NOW() AT TIME ZONE 'Europe/Warsaw'"), [])

    def test_timezone_func_on_now_ok(self):
        self.assertEqual(sql_kat("SELECT 1 FROM t WHERE starts_at > timezone('Europe/Warsaw', now())"), [])

    def test_qualified_table_column(self):
        self.assertEqual(sql_kat("SELECT 1 FROM shifts s WHERE s.ends_at < NOW()"), ["sql_local_vs_now"])

    def test_unknown_column_not_flagged(self):
        self.assertEqual(sql_kat("SELECT 1 FROM t WHERE amount < NOW()"), [])

    def test_local_minus_interval_compared(self):
        self.assertEqual(sql_kat("SELECT 1 FROM t WHERE starts_at - interval '1 hour' < now()"),
                         ["sql_fixed_offset", "sql_local_vs_now"])


class DateTruncUtc(unittest.TestCase):
    def test_date_trunc(self):
        self.assertEqual(sql_kat("SELECT date_trunc('day', created_at) FROM t"), ["sql_date_trunc_utc"])

    def test_date_trunc_with_tz_ok(self):
        self.assertEqual(sql_kat("SELECT date_trunc('day', created_at AT TIME ZONE 'Europe/Warsaw') FROM t"), [])

    def test_date_trunc_three_args_ok(self):
        self.assertEqual(sql_kat("SELECT date_trunc('day', created_at, 'Europe/Warsaw') FROM t"), [])

    def test_cast_operator_date(self):
        self.assertEqual(sql_kat("SELECT created_at::date FROM t"), ["sql_date_trunc_utc"])

    def test_cast_function_date(self):
        self.assertEqual(sql_kat("SELECT CAST(created_at AS date) FROM t"), ["sql_date_trunc_utc"])

    def test_date_function(self):
        self.assertEqual(sql_kat("SELECT DATE(sent_at) FROM t"), ["sql_date_trunc_utc"])

    def test_extract(self):
        self.assertEqual(sql_kat("SELECT EXTRACT(MONTH FROM created_at) FROM t"), ["sql_date_trunc_utc"])

    def test_extract_epoch_ok(self):
        self.assertEqual(sql_kat("SELECT EXTRACT(EPOCH FROM created_at) FROM t"), [])

    def test_date_part(self):
        self.assertEqual(sql_kat("SELECT date_part('hour', sent_at) FROM t"), ["sql_date_trunc_utc"])

    def test_parenthesised_at_time_zone_cast_ok(self):
        self.assertEqual(sql_kat("SELECT (created_at AT TIME ZONE 'Europe/Warsaw')::date FROM t"), [])

    def test_local_column_cast_ok(self):
        self.assertEqual(sql_kat("SELECT starts_at::date FROM t"), [])

    def test_to_date_not_matched_as_date(self):
        self.assertEqual(sql_kat("SELECT to_date(txt, 'YYYY') FROM t"), [])

    def test_nested_cast_reported_once(self):
        self.assertEqual(sql_kat("SELECT date_trunc('day', created_at)::date FROM t"), ["sql_date_trunc_utc"])

    def test_chained_cast(self):
        self.assertEqual(sql_kat("SELECT created_at::timestamptz::date FROM t"), ["sql_date_trunc_utc"])

    def test_alias_qualified_column(self):
        self.assertEqual(sql_kat("SELECT 1 FROM orders o WHERE DATE(o.paid_at) = x"), ["sql_date_trunc_utc"])


class LiteralBoundary(unittest.TestCase):
    def test_date_literal(self):
        self.assertEqual(sql_kat("SELECT 1 FROM t WHERE created_at >= '2026-10-01'"), ["sql_literal_boundary"])

    def test_datetime_literal(self):
        self.assertEqual(sql_kat("SELECT 1 FROM t WHERE created_at < '2026-10-01 00:00'"), ["sql_literal_boundary"])

    def test_date_keyword_literal(self):
        self.assertEqual(sql_kat("SELECT 1 FROM t WHERE created_at >= DATE '2026-10-01'"), ["sql_literal_boundary"])

    def test_reversed(self):
        self.assertEqual(sql_kat("SELECT 1 FROM t WHERE '2026-10-01' <= created_at"), ["sql_literal_boundary"])

    def test_between_literals(self):
        self.assertEqual(sql_kat("SELECT 1 FROM t WHERE created_at BETWEEN '2026-10-01' AND '2026-10-31'"),
                         ["sql_literal_boundary"])

    def test_literal_with_zone_ok(self):
        self.assertEqual(sql_kat("SELECT 1 FROM t WHERE created_at >= '2026-10-01 00:00+02'"), [])

    def test_literal_at_time_zone_ok(self):
        self.assertEqual(
            sql_kat("SELECT 1 FROM t WHERE created_at >= '2026-10-01'::timestamp AT TIME ZONE 'Europe/Warsaw'"), [])

    def test_local_column_literal_ok(self):
        self.assertEqual(sql_kat("SELECT 1 FROM t WHERE starts_at >= '2026-10-01'"), [])

    def test_literal_in_comment_ignored(self):
        self.assertEqual(sql_kat("SELECT 1 FROM t WHERE x = 1 -- created_at >= '2026-10-01'"), [])


class FixedOffset(unittest.TestCase):
    def test_offset_literal_plus02(self):
        self.assertEqual(sql_kat("SELECT created_at AT TIME ZONE '+02' FROM t"), ["sql_fixed_offset"])

    def test_offset_literal_plus0100(self):
        self.assertEqual(sql_kat("SELECT created_at AT TIME ZONE '+01:00' FROM t"), ["sql_fixed_offset"])

    def test_interval_on_column(self):
        w = sql("SELECT created_at + interval '2 hours' FROM t")
        self.assertEqual([(x.kategoria, x.pewnosc) for x in w], [("sql_fixed_offset", "uncertain")])

    def test_interval_in_zone_context_is_likely(self):
        w = sql("SELECT (created_at AT TIME ZONE 'UTC') + interval '2 hours' FROM t")
        self.assertEqual([(x.kategoria, x.pewnosc) for x in w], [("sql_fixed_offset", "likely")])

    def test_relative_window_from_now_ok(self):
        self.assertEqual(sql_kat("SELECT 1 FROM t WHERE sent_at > NOW() - interval '2 hours'"), [])

    def test_three_hours_ok(self):
        self.assertEqual(sql_kat("SELECT created_at + interval '3 hours' FROM t"), [])

    def test_named_zone_ok(self):
        self.assertEqual(sql_kat("SELECT created_at AT TIME ZONE 'Europe/Warsaw' FROM t"), [])


class Numbering(unittest.TestCase):
    def test_to_char_current_date(self):
        self.assertEqual(sql_kat("SELECT to_char(CURRENT_DATE, 'YYYY/MM')"), ["numbering_by_date"])

    def test_to_char_now(self):
        self.assertEqual(sql_kat("SELECT 'N/' || to_char(now(), 'YYYY-MM')"), ["numbering_by_date"])

    def test_to_char_with_zone_ok(self):
        self.assertEqual(sql_kat("SELECT to_char(now() AT TIME ZONE 'Europe/Warsaw', 'YYYY/MM')"), [])

    def test_to_char_column_ok(self):
        self.assertEqual(sql_kat("SELECT to_char(starts_at, 'YYYY/MM') FROM t"), [])


if __name__ == "__main__":
    unittest.main()
