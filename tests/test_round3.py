"""Runda 3: numeracja przez zmienną w funkcji i warianty wartości domyślnej parametru."""
import unittest

from tests.helpers import kategorie, wyniki


class NumberingThroughVariable(unittest.TestCase):
    def test_positive_year_in_fstring_with_prefix(self):
        src = """
        from datetime import datetime
        def f(seq):
            today = datetime.now()
            nr = f"FV/{today.year}/{seq}"
            return nr
        """
        self.assertEqual(kategorie(src), ["numbering_by_date"])

    def test_negative_variable_only_logged(self):
        src = """
        import logging
        from datetime import datetime
        log = logging.getLogger("x")
        def f(seq):
            today = datetime.now()
            log.info("start %s", today)
            return seq
        """
        self.assertEqual(kategorie(src), ["py_naive_now_other"])

    def test_negative_same_variable_in_log_fstring_with_year(self):
        src = """
        from datetime import datetime
        def f(log):
            today = datetime.now()
            log.info(f"Rok {today.year}")
        """
        self.assertEqual(kategorie(src), ["py_naive_now_other"])

    def test_date_today_variable_strftime_with_numbering_name(self):
        src = """
        from datetime import date
        def f(seq):
            d = date.today()
            order_no = d.strftime("%Y") + str(seq)
            return order_no
        """
        self.assertEqual(kategorie(src), ["numbering_by_date"])

    def test_variable_month_with_prefix_in_format_call(self):
        src = """
        from datetime import datetime
        def f(seq):
            teraz = datetime.now()
            return "ZAM/{}/{}".format(teraz.month, seq)
        """
        self.assertEqual(kategorie(src), ["numbering_by_date"])

    def test_percent_format_with_prefix(self):
        src = """
        from datetime import date
        def f(seq):
            d = date.today()
            return "FV/%d/%d" % (d.year, seq)
        """
        self.assertEqual(kategorie(src), ["numbering_by_date"])

    def test_concat_with_prefix_and_year(self):
        src = """
        from datetime import date
        def f(seq):
            d = date.today()
            return "FV/" + str(d.year) + "/" + str(seq)
        """
        self.assertEqual(kategorie(src), ["numbering_by_date"])

    def test_series_name_hint(self):
        src = """
        from datetime import datetime
        def f():
            now = datetime.now()
            seria = now.strftime("%Y")
            return seria
        """
        self.assertEqual(kategorie(src), ["numbering_by_date"])

    def test_variable_in_other_function_not_tracked(self):
        src = """
        from datetime import datetime
        def a():
            today = datetime.now()
            return today
        def b(today, seq):
            return f"{today.year}-{seq}"
        """
        self.assertEqual(kategorie(src), ["py_naive_now_other"])

    def test_variable_year_without_prefix_or_name_is_ordinary(self):
        src = """
        from datetime import datetime
        def f():
            today = datetime.now()
            title = f"Raport {today.year}"
            return title
        """
        self.assertEqual(kategorie(src), ["py_naive_now_other"])

    def test_aware_variable_not_numbering(self):
        src = """
        from datetime import datetime
        def f(tz, seq):
            today = datetime.now(tz)
            return f"FV/{today.year}/{seq}"
        """
        self.assertEqual(kategorie(src), [])

    def test_sql_param_written_to_numbering_column(self):
        src = """
        from datetime import date
        def f(cur, oid):
            d = date.today()
            cur.execute("UPDATE orders SET order_no = %s WHERE id = %s", (d.strftime("%Y/%m"), oid))
        """
        self.assertIn("numbering_by_date", kategorie(src))

    def test_sql_param_compared_with_numbering_column(self):
        src = """
        from datetime import date
        def f(q):
            d = date.today()
            return q.query_all("SELECT 1 FROM orders WHERE doc_number LIKE %s", (f"{d.year}/%",))
        """
        self.assertIn("numbering_by_date", kategorie(src))

    def test_sql_param_other_column_stays_py_naive_now(self):
        src = """
        from datetime import date
        def f(cur, oid):
            d = date.today()
            cur.execute("UPDATE orders SET label = %s WHERE id = %s", (d.strftime("%Y/%m"), oid))
        """
        self.assertEqual(kategorie(src), ["py_naive_now"])

    def test_sql_current_date_result_variable(self):
        src = """
        from db import query_one
        def f(seq):
            today = query_one("SELECT CURRENT_DATE")[0]
            nr = f"FV/{today.year}/{seq}"
            return nr
        """
        self.assertEqual(kategorie(src), ["numbering_by_date", "sql_current_date_utc"])

    def test_sql_current_date_result_only_logged(self):
        src = """
        from db import query_one
        def f(log):
            today = query_one("SELECT CURRENT_DATE")[0]
            log.info("dzis %s", today)
        """
        self.assertEqual(kategorie(src), ["sql_current_date_utc"])

    def test_sql_where_current_date_is_not_a_date_source(self):
        src = """
        from db import query_one
        def f(seq):
            row = query_one("SELECT id FROM t WHERE d = CURRENT_DATE")
            return f"FV/{row[0].year}/{seq}"
        """
        self.assertEqual(kategorie(src), ["sql_current_date_utc"])

    def test_sql_date_with_timezone_not_a_source(self):
        src = """
        from db import query_one
        def f(seq):
            today = query_one("SELECT (NOW() AT TIME ZONE 'Europe/Warsaw')::date")[0]
            return f"FV/{today.year}/{seq}"
        """
        self.assertEqual(kategorie(src), [])


class DefaultParameterVariants(unittest.TestCase):
    PRE = "from datetime import datetime, date\n"

    def check(self, body, ile=1):
        import textwrap
        src = self.PRE + "def f(request, q):\n" + textwrap.indent(textwrap.dedent(body), "    ")
        w = wyniki(src)
        self.assertEqual([x.kategoria for x in w], ["py_naive_now"] * ile, [x.kategoria for x in w])
        for x in w:
            self.assertEqual(x.waznosc, "srednia")
            self.assertIn("wartość domyślna parametru", x.dlaczego)

    def test_if_not(self):
        self.check('''
        x = request.args.get("m")
        if not x:
            x = datetime.now().strftime("%Y-%m")
        return q.query_all("SELECT 1 WHERE m = %s", (x,))''')

    def test_else_branch(self):
        self.check('''
        x = request.args.get("m")
        if x:
            pass
        else:
            x = datetime.now().strftime("%Y-%m")
        return q.query_all("SELECT 1 WHERE m = %s", (x,))''')

    def test_is_none_or_empty(self):
        self.check('''
        x = request.args.get("m")
        if x is None or x == "":
            x = datetime.now().strftime("%Y-%m")
        return q.query_all("SELECT 1 WHERE m = %s", (x,))''')

    def test_or_with_strip(self):
        self.check('''
        x = (request.args.get("m") or "").strip() or datetime.now().strftime("%Y-%m")
        return q.query_all("SELECT 1 WHERE m = %s", (x,))''')

    def test_conditional_expression(self):
        self.check('''
        x = request.args["m"] if "m" in request.args else datetime.now().strftime("%Y-%m")
        return q.query_all("SELECT 1 WHERE m = %s", (x,))''')

    def test_get_with_default_argument(self):
        self.check('''
        x = request.args.get("m", "")
        if not x:
            x = date.today().isoformat()
        return q.query_all("SELECT 1 WHERE m = %s", [x])''')

    def test_value_via_json_body_and_fstring_sql(self):
        self.check('''
        data = request.get_json()
        x = data.get("m")
        if not x:
            x = date.today().isoformat()
        return q.query_all(f"SELECT 1 WHERE m = '{x}'")''')

    def test_negative_not_a_parameter(self):
        import textwrap
        src = self.PRE + "def f(q, cache):\n" + textwrap.indent(textwrap.dedent('''
        x = cache.compute()
        if not x:
            x = datetime.now().strftime("%Y-%m")
        return q.query_all("SELECT 1 WHERE m = %s", (x,))'''), "    ")
        w = wyniki(src)
        self.assertEqual([(x.kategoria, x.waznosc) for x in w], [("py_naive_now", "wysoka")])
        self.assertNotIn("domyślna", w[0].dlaczego)

    def test_negative_unconditional_now_in_sql(self):
        import textwrap
        src = self.PRE + "def f(q):\n" + textwrap.indent(textwrap.dedent('''
        q.query_all("SELECT 1 WHERE x < %s", (datetime.now(),))'''), "    ")
        w = wyniki(src)
        self.assertEqual([x.waznosc for x in w], ["wysoka"])


if __name__ == "__main__":
    unittest.main()
