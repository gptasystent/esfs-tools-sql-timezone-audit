"""Runda 2: klasy fałszywych trafień z prawdziwego backendu (fikcyjny sklep)."""
import unittest

import sql_timezone_audit as sta
from tests.helpers import cfg, kategorie, sql, sql_kat, wyniki


class FixedOffsetAfterAtTimeZone(unittest.TestCase):
    def test_hour_window_after_at_time_zone_not_flagged(self):
        self.assertEqual(sql_kat(
            "SELECT 1 FROM t WHERE x > (NOW() AT TIME ZONE 'Europe/Warsaw') - INTERVAL '1 hour'"), [])

    def test_two_hours_plus_after_at_time_zone_not_flagged(self):
        self.assertEqual(sql_kat(
            "SELECT (NOW() AT TIME ZONE 'Europe/Warsaw') + INTERVAL '2 hours'"), [])

    def test_days_after_at_time_zone_not_flagged(self):
        self.assertEqual(sql_kat(
            "SELECT 1 FROM t WHERE x < (NOW() AT TIME ZONE 'Europe/Warsaw') + INTERVAL '2 days'"), [])

    def test_timezone_function_window_not_flagged(self):
        self.assertEqual(sql_kat(
            "SELECT timezone('Europe/Warsaw', now()) - interval '2 hours'"), [])

    def test_column_plus_interval_without_zone_still_flagged(self):
        self.assertEqual(sql_kat("SELECT created_at + interval '2 hours' FROM t"), ["sql_fixed_offset"])

    def test_offset_literal_still_flagged(self):
        self.assertEqual(sql_kat("SELECT now() AT TIME ZONE '+02'"), ["sql_fixed_offset"])


class NumberingNarrowed(unittest.TestCase):
    # --- SQL
    def test_sql_prefix_literal_is_numbering(self):
        self.assertEqual(sql_kat("SELECT 'FV/' || to_char(CURRENT_DATE, 'YYYY/MM')"), ["numbering_by_date"])

    def test_sql_suffix_literal_is_not_prefix(self):
        # '/FV' to nie prefiks dokumentu; now() w to_char to data w UTC -> zwykła kategoria
        self.assertEqual(sql_kat("SELECT to_char(now(), 'YYYY/MM') || '/FV'"), ["sql_current_date_utc"])

    def test_sql_bare_to_char_is_ordinary(self):
        self.assertEqual(sql_kat("SELECT to_char(CURRENT_DATE, 'YYYY/MM')"), ["sql_current_date_utc"])

    def test_sql_birthday_comparison_is_ordinary(self):
        self.assertEqual(
            sql_kat("SELECT id FROM customers WHERE to_char(birth_day, 'MM-DD') = to_char(CURRENT_DATE, 'MM-DD')"),
            ["sql_current_date_utc"])

    def test_sql_object_key_is_ordinary(self):
        self.assertEqual(sql_kat("SELECT 'exports/' || to_char(CURRENT_DATE, 'YYYY/MM') || '/file'"),
                         ["sql_current_date_utc"])

    def test_sql_now_year_label_not_numbering(self):
        self.assertEqual(sql_kat("SELECT to_char(now(), 'YYYY') AS year_label"), ["sql_current_date_utc"])

    def test_sql_set_numbering_column(self):
        self.assertEqual(sql_kat("UPDATE orders SET order_no = to_char(CURRENT_DATE, 'YYYYMM') WHERE id = 1"),
                         ["numbering_by_date"])

    def test_sql_insert_numbering_column(self):
        self.assertEqual(sql_kat(
            "INSERT INTO orders (id, invoice_number) VALUES (1, to_char(CURRENT_DATE, 'YYYY/MM'))"),
            ["numbering_by_date"])

    def test_sql_insert_other_column_ordinary(self):
        self.assertEqual(sql_kat(
            "INSERT INTO orders (invoice_number, label) VALUES (1, to_char(CURRENT_DATE, 'YYYY/MM'))"),
            ["sql_current_date_utc"])

    def test_sql_like_on_number_column(self):
        self.assertEqual(sql_kat(
            "SELECT count(*) FROM orders WHERE doc_number LIKE to_char(CURRENT_DATE, 'YYYY/MM') || '%'"),
            ["numbering_by_date"])

    def test_sql_variable_name_hint(self):
        src = """
        def f(q):
            invoice_no = q.query_one("SELECT to_char(CURRENT_DATE, 'YYYYMM')")
        """
        self.assertEqual(kategorie(src), ["numbering_by_date"])

    # --- Python
    def test_py_prefix_in_fstring(self):
        src = """
        from datetime import date
        def f():
            return f"ZAM/{date.today():%Y/%m}/1"
        """
        self.assertEqual(kategorie(src), ["numbering_by_date"])

    def test_py_target_name_hint(self):
        src = """
        from datetime import datetime
        def f():
            order_no = datetime.now().strftime("%Y%m")
            return order_no
        """
        self.assertEqual(kategorie(src), ["numbering_by_date"])

    def test_py_storage_key_is_ordinary(self):
        src = """
        from datetime import date
        def f(name):
            return f"uploads/{date.today():%Y/%m}/{name}"
        """
        self.assertEqual(kategorie(src), ["py_naive_now_other"])

    def test_py_birthday_format_is_ordinary(self):
        src = """
        from datetime import date
        def f(cur):
            cur.execute("SELECT id FROM customers WHERE to_char(born, 'MM-DD') = %s", (date.today().strftime("%m-%d"),))
        """
        self.assertEqual(kategorie(src), ["py_naive_now"])

    def test_py_year_label_and_message(self):
        src = """
        from datetime import date
        def f():
            label = f"Rok {date.today():%Y}"
            msg = "Raport za " + date.today().strftime("%Y/%m")
            return label, msg
        """
        self.assertEqual(kategorie(src), ["py_naive_now_other"] * 2)

    def test_py_strftime_concat_prefix(self):
        src = """
        from datetime import datetime
        def f():
            return "FV/" + datetime.now().strftime("%Y/%m")
        """
        self.assertEqual(kategorie(src), ["numbering_by_date"])

    def test_demoted_counter(self):
        src = """
        from datetime import date
        def f():
            return f"uploads/{date.today():%Y/%m}/x"
        """
        a = sta.AnalizatorModulu(__import__("textwrap").dedent(src), "m.py", cfg())
        a.uruchom()
        self.assertEqual(a.numeracja_zdegradowane, 1)

    def test_demoted_counter_in_report_and_json(self):
        import io, json, os, tempfile
        d = tempfile.mkdtemp()
        with open(os.path.join(d, "a.py"), "w") as f:
            f.write("from datetime import date\ndef f():\n    return f'uploads/{date.today():%Y/%m}/x'\n")
        out = io.BytesIO()
        sta.main(["--backend", d, "--json", os.path.join(d, "r.json")], stdout=out, stderr=io.BytesIO())
        self.assertIn("Zawężenie numbering_by_date: 1 wyników przestało być numbering_by_date", out.getvalue().decode("utf-8"))
        with open(os.path.join(d, "r.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f)["podsumowanie"]["numbering_zawezone"], 1)


if __name__ == "__main__":
    unittest.main()
