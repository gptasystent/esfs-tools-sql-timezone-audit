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


class UtcIntoLocalColumn(unittest.TestCase):
    def test_update_set_local_column(self):
        w = sql("UPDATE shifts SET starts_at = NOW() WHERE id = 1")
        self.assertEqual([(x.kategoria, x.pewnosc, x.waznosc) for x in w],
                         [("sql_utc_into_local_column", "likely", "wysoka")])

    def test_insert_into_local_column(self):
        self.assertEqual(sql_kat("INSERT INTO shifts (id, starts_at) VALUES (1, now())"),
                         ["sql_utc_into_local_column"])

    def test_insert_current_timestamp_other_column_ok(self):
        self.assertEqual(sql_kat("INSERT INTO shifts (starts_at, created_at) VALUES ('x', current_timestamp)"), [])

    def test_system_column_is_correct(self):
        self.assertEqual(sql_kat("UPDATE shifts SET updated_at = NOW(), sent_at = CURRENT_TIMESTAMP WHERE id = 1"), [])

    def test_system_column_insert_is_correct(self):
        self.assertEqual(sql_kat("INSERT INTO shifts (id, created_at) VALUES (1, now())"), [])

    def test_set_with_at_time_zone_ok(self):
        self.assertEqual(sql_kat("UPDATE shifts SET starts_at = NOW() AT TIME ZONE 'Europe/Warsaw' WHERE id = 1"), [])

    def test_second_assignment_in_set(self):
        self.assertEqual(sql_kat("UPDATE shifts SET note = 'x', scheduled_for = now() + interval '1 day' WHERE id = 1"),
                         ["sql_utc_into_local_column"])

    def test_on_conflict_do_update(self):
        self.assertEqual(sql_kat(
            "INSERT INTO shifts (id) VALUES (1) ON CONFLICT (id) DO UPDATE SET starts_at = now()"),
            ["sql_utc_into_local_column"])

    def test_where_comparison_is_still_local_vs_now(self):
        self.assertEqual(sql_kat("UPDATE shifts SET note = 'x' WHERE starts_at < now()"), ["sql_local_vs_now"])

    def test_set_is_not_reported_as_comparison_too(self):
        self.assertEqual(sql_kat("UPDATE shifts SET starts_at = NOW() WHERE id = 1"), ["sql_utc_into_local_column"])

    def test_heuristic_local_column_uncertain(self):
        w = wyniki('def f(cur):\n    cur.execute("UPDATE shifts SET starts_at = NOW()")\n', tz=[], local=[])
        self.assertEqual([(x.kategoria, x.pewnosc) for x in w], [("sql_utc_into_local_column", "uncertain")])

    def test_blocking_category(self):
        self.assertIn("sql_utc_into_local_column", sta.KATEGORIE_BLOKUJACE)


class DefaultParameterValue(unittest.TestCase):
    SRC = """
    from datetime import datetime
    def report(request, q):
        month = request.args.get("month")
        if not month:
            month = datetime.now().strftime("%Y-%m")
        return q.query_all("SELECT 1 FROM t WHERE to_char(created_at, 'YYYY-MM') = %s", (month,))
    """

    def test_stays_py_naive_now_with_medium_severity(self):
        w = wyniki(self.SRC)
        self.assertEqual([(x.kategoria, x.waznosc) for x in w], [("py_naive_now", "srednia")])

    def test_explains_default_value(self):
        self.assertIn("wartość domyślna parametru", wyniki(self.SRC)[0].dlaczego)

    def test_or_default_form(self):
        src = """
        from datetime import date
        def report(request, q):
            day = request.args.get("day") or date.today().isoformat()
            return q.query_all("SELECT 1 FROM t WHERE d = %s", (day,))
        """
        w = wyniki(src)
        self.assertEqual([(x.kategoria, x.waznosc) for x in w], [("py_naive_now", "srednia")])

    def test_plain_naive_now_in_sql_keeps_high(self):
        src = """
        from datetime import datetime
        def f(q):
            q.query_all("SELECT 1 FROM t WHERE x < %s", (datetime.now(),))
        """
        w = wyniki(src)
        self.assertEqual([(x.kategoria, x.waznosc) for x in w], [("py_naive_now", "wysoka")])
        self.assertNotIn("wartość domyślna", w[0].dlaczego)

    def test_default_not_used_in_sql_is_other(self):
        src = """
        from datetime import datetime
        def f(request):
            m = request.args.get("m")
            if not m:
                m = datetime.now().strftime("%Y-%m")
            return m
        """
        self.assertEqual(kategorie(src), ["py_naive_now_other"])


class ColumnFileMatchSummary(unittest.TestCase):
    def raport(self, src, tz, local):
        import tempfile, os
        d = tempfile.mkdtemp()
        with open(os.path.join(d, "a.py"), "w") as f:
            f.write(src)
        return sta.audyt(d, sta.KonfiguracjaKolumn(tz, local))

    SRC = ('def f(cur):\n    cur.execute("SELECT created_at, starts_at FROM shifts s '
           'WHERE s.ends_at < NOW() AND paid_at IS NULL")\n')

    def test_counts_matched_columns(self):
        r = self.raport(self.SRC, ["created_at", "updated_at", "orders.paid_at", "shifts.paid_at"],
                        ["starts_at", "shifts.ends_at", "due_date"])
        linie = [l for l in sta.podsumuj(r) if l.startswith("Kolumny z plików")]
        self.assertEqual(linie, ["Kolumny z plików dopasowane w analizowanym SQL: "
                                 "systemowe 2/4, lokalne 2/3"])

    def test_no_line_without_column_files(self):
        r = self.raport(self.SRC, [], [])
        self.assertFalse([l for l in sta.podsumuj(r) if l.startswith("Kolumny z plików")])

    def test_zero_match_is_visible(self):
        r = self.raport(self.SRC, ["nic_takiego"], ["nic_innego"])
        self.assertIn("systemowe 0/1, lokalne 0/1", "\n".join(sta.podsumuj(r)))

    def test_in_json(self):
        r = self.raport(self.SRC, ["created_at"], ["starts_at"])
        dane = __import__("json").loads(sta.json_raportu(r))["podsumowanie"]
        self.assertEqual(dane["kolumny_dopasowane"], {"systemowe": 1, "systemowe_z_pliku": 1,
                                                      "lokalne": 1, "lokalne_z_pliku": 1})
