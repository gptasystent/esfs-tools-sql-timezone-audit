"""Rozpoznawanie SQL w kodzie: helpery, zmienne, f-stringi, kolumny, konfiguracja."""
import unittest

import sql_timezone_audit as sta
from tests.helpers import kategorie, wyniki


class HelperRecognition(unittest.TestCase):
    def test_exact_helper_names(self):
        for h in ("query_one", "query_all", "execute", "execute_return"):
            src = 'def f():\n    %s("SELECT 1 WHERE d = CURRENT_DATE")\n' % h
            self.assertEqual(kategorie(src), ["sql_current_date_utc"], h)

    def test_cursor_methods(self):
        for h in ("cur.execute", "cur.executemany", "self.conn.cursor().execute"):
            src = 'def f(cur):\n    %s("SELECT 1 WHERE d = CURRENT_DATE")\n' % h
            self.assertEqual(kategorie(src), ["sql_current_date_utc"], h)

    def test_similar_name_not_matched(self):
        src = 'def f():\n    my_execute("SELECT 1 WHERE d = CURRENT_DATE")\n    xquery_all("SELECT CURRENT_DATE")\n'
        self.assertEqual(kategorie(src), [])

    def test_alias_import(self):
        src = """
        from db import query_all as qa
        def f():
            qa("SELECT 1 WHERE d = CURRENT_DATE")
        """
        self.assertEqual(kategorie(src), ["sql_current_date_utc"])

    def test_executor_task_is_not_sql(self):
        src = """
        def f(executor, task):
            executor.execute(task)
            executor.execute("print CURRENT_DATE")
        """
        self.assertEqual(kategorie(src), [])

    def test_non_sql_string_first_arg_ignored(self):
        src = 'def f(cur):\n    cur.execute("hello CURRENT_DATE")\n'
        self.assertEqual(kategorie(src), [])

    def test_sql_with_leading_comment(self):
        src = 'def f(cur):\n    cur.execute("-- raport\\nSELECT CURRENT_DATE")\n'
        self.assertEqual(kategorie(src), ["sql_current_date_utc"])

    def test_keyword_argument_sql(self):
        src = 'def f(cur):\n    cur.execute(query="SELECT CURRENT_DATE")\n'
        self.assertEqual(kategorie(src), ["sql_current_date_utc"])


class SqlVariables(unittest.TestCase):
    def test_variable(self):
        src = """
        def f(cur):
            sql = "SELECT 1 WHERE d = CURRENT_DATE"
            cur.execute(sql)
        """
        self.assertEqual(kategorie(src), ["sql_current_date_utc"])

    def test_augmented_assignment(self):
        src = """
        def f(cur):
            sql = "SELECT 1 FROM t"
            sql += " WHERE d = CURRENT_DATE"
            cur.execute(sql)
        """
        self.assertEqual(kategorie(src), ["sql_current_date_utc"])

    def test_concatenation(self):
        src = """
        def f(cur):
            cur.execute("SELECT 1 FROM t " + "WHERE d = CURRENT_DATE")
        """
        self.assertEqual(kategorie(src), ["sql_current_date_utc"])

    def test_join(self):
        src = """
        def f(cur):
            parts = ["SELECT 1 FROM t"]
            parts.append("WHERE d = CURRENT_DATE")
            cur.execute(" ".join(parts))
        """
        self.assertEqual(kategorie(src), ["sql_current_date_utc"])

    def test_join_literal_list(self):
        src = """
        def f(cur):
            cur.execute("\\n".join(["SELECT 1", "WHERE d = CURRENT_DATE"]))
        """
        self.assertEqual(kategorie(src), ["sql_current_date_utc"])

    def test_fstring_insertions_stripped(self):
        src = """
        def f(cur, extra):
            cur.execute(f"SELECT 1 FROM t WHERE {extra} AND d = CURRENT_DATE")
        """
        self.assertEqual(kategorie(src), ["sql_current_date_utc"])

    def test_fstring_with_known_variable(self):
        src = """
        def f(cur):
            base = "SELECT 1 FROM t WHERE d = CURRENT_DATE"
            cur.execute(f"{base} AND x = 1")
        """
        self.assertEqual(kategorie(src), ["sql_current_date_utc"])

    def test_format_call(self):
        src = """
        def f(cur):
            cur.execute("SELECT 1 FROM {} WHERE d = CURRENT_DATE".format("t"))
        """
        self.assertEqual(kategorie(src), ["sql_current_date_utc"])

    def test_percent_format(self):
        src = """
        def f(cur):
            cur.execute("SELECT 1 FROM t WHERE d = CURRENT_DATE AND x = %s" % 1)
        """
        self.assertEqual(kategorie(src), ["sql_current_date_utc"])

    def test_module_constant_used_in_function(self):
        src = """
        SQL = "SELECT 1 WHERE d = CURRENT_DATE"
        def f(cur):
            cur.execute(SQL)
        """
        w = wyniki(src)
        self.assertEqual([(x.kategoria, x.funkcja, x.linia) for x in w], [("sql_current_date_utc", "f", 2)])

    def test_module_constant_defined_after_function(self):
        src = """
        def f(cur):
            cur.execute(SQL)
        SQL = "SELECT 1 WHERE d = CURRENT_DATE"
        """
        self.assertEqual(kategorie(src), ["sql_current_date_utc"])

    def test_class_constant_via_self(self):
        src = """
        class Repo:
            Q = "SELECT 1 WHERE d = CURRENT_DATE"
            def run(self, cur):
                cur.execute(self.Q)
        """
        w = wyniki(src)
        self.assertEqual([(x.kategoria, x.funkcja) for x in w], [("sql_current_date_utc", "Repo.run")])

    def test_multiline_sql_line_numbers(self):
        src = '''
        def f(cur):
            cur.execute("""
                SELECT 1
                FROM t
                WHERE d = CURRENT_DATE
            """)
        '''
        w = wyniki(src)
        self.assertEqual([(x.kategoria, x.linia) for x in w], [("sql_current_date_utc", 6)])

    def test_same_sql_executed_twice_reported_once(self):
        src = """
        def f(cur):
            sql = "SELECT 1 WHERE d = CURRENT_DATE"
            cur.execute(sql)
            cur.execute(sql)
        """
        self.assertEqual(kategorie(src), ["sql_current_date_utc"])

    def test_reassigned_variable_uses_latest_value(self):
        src = """
        def f(cur):
            sql = "SELECT 1 WHERE d = CURRENT_DATE"
            sql = "SELECT 1"
            cur.execute(sql)
        """
        self.assertEqual(kategorie(src), [])


class FragmentsAndMetadata(unittest.TestCase):
    def test_fragment_max_120_and_masks_values(self):
        src = """
        def f(cur):
            cur.execute("SELECT 1 FROM clients WHERE name = 'Fikcyjna Firma' AND d = CURRENT_DATE AND " + "x" * 3)
        """
        for w in wyniki(src):
            self.assertLessEqual(len(w.fragment), 120)
            self.assertNotIn("Fikcyjna", w.fragment)

    def test_long_sql_fragment_truncated(self):
        sql = "SELECT " + ", ".join("col%d" % i for i in range(80)) + " FROM t WHERE d = CURRENT_DATE"
        w = wyniki('def f(cur):\n    cur.execute(%r)\n' % sql)
        self.assertTrue(all(len(x.fragment) <= 120 for x in w))

    def test_result_fields(self):
        src = 'def f(cur):\n    cur.execute("SELECT 1 WHERE d = CURRENT_DATE")\n'
        w = wyniki(src, plik="a/b.py")[0]
        self.assertEqual((w.plik, w.funkcja, w.linia, w.helper), ("a/b.py", "f", 2, "cur.execute"))
        self.assertTrue(w.dlaczego and w.propozycja)
        self.assertIn(w.pewnosc, ("likely", "uncertain"))

    def test_never_certain(self):
        src = """
        def f(cur):
            cur.execute("SELECT date_trunc('day', created_at), to_char(now(), 'YYYY/MM') FROM t WHERE starts_at < now()")
        """
        self.assertTrue(all(w.pewnosc in ("likely", "uncertain") for w in wyniki(src)))

    def test_severity_from_table(self):
        src = 'def f(cur):\n    cur.execute("SELECT 1 WHERE d = CURRENT_DATE")\n'
        self.assertEqual(wyniki(src)[0].waznosc, "wysoka")


class ColumnTypes(unittest.TestCase):
    def test_file_columns_give_likely(self):
        w = wyniki('def f(cur):\n    cur.execute("SELECT 1 FROM t WHERE starts_at < NOW()")\n')
        self.assertEqual(w[0].pewnosc, "likely")

    def test_heuristic_gives_uncertain(self):
        w = wyniki('def f(cur):\n    cur.execute("SELECT 1 FROM t WHERE starts_at < NOW()")\n', tz=[], local=[])
        self.assertEqual([(x.kategoria, x.pewnosc) for x in w], [("sql_local_vs_now", "uncertain")])

    def test_heuristic_system_column(self):
        w = wyniki('def f(cur):\n    cur.execute("SELECT created_at::date FROM t")\n', tz=[], local=[])
        self.assertEqual([(x.kategoria, x.pewnosc) for x in w], [("sql_date_trunc_utc", "uncertain")])

    def test_table_qualified_entry_applies_only_to_that_table(self):
        src = 'def f(cur):\n    cur.execute("SELECT paid_at::date FROM %s")\n'
        pew = lambda t: [w.pewnosc for w in wyniki(src % t, tz=["orders.paid_at"], local=[])]
        self.assertEqual(pew("orders"), ["likely"])
        self.assertEqual(pew("invoices"), ["uncertain"])  # tylko heurystyka po nazwie

    def test_heuristic_function(self):
        self.assertEqual(sta.heurystyka_kolumny("created_at"), "tz")
        self.assertEqual(sta.heurystyka_kolumny("updated"), "tz")
        self.assertEqual(sta.heurystyka_kolumny("sent_at"), "tz")
        self.assertEqual(sta.heurystyka_kolumny("starts_at"), "local")
        self.assertEqual(sta.heurystyka_kolumny("due_date"), "local")
        self.assertEqual(sta.heurystyka_kolumny("planned_date"), "local")
        self.assertEqual(sta.heurystyka_kolumny("scheduled_for"), "local")
        self.assertIsNone(sta.heurystyka_kolumny("amount"))

    def test_parse_column_list(self):
        self.assertEqual(sta.parsuj_liste_kolumn("# c\n\n a \nb.c  # x\n"), ["a", "b.c"])

    def test_classify_prefers_file_over_heuristic(self):
        c = sta.KonfiguracjaKolumn(tz=["starts_at"], local=[])
        self.assertEqual(c.classify([], "starts_at"), ("tz", True))


class SqlHelpers(unittest.TestCase):
    def test_blank_sql_keeps_length(self):
        sql = "SELECT 'a--b' -- c\nFROM /* x */ t"
        code, skel = sta.blank_sql(sql)
        self.assertEqual((len(code), len(skel)), (len(sql), len(sql)))
        self.assertNotIn("c\n", code.replace("--", ""))

    def test_escaped_quote(self):
        code, skel = sta.blank_sql("SELECT 'it''s' , CURRENT_DATE")
        self.assertIn("CURRENT_DATE", skel)

    def test_mask_literals_keeps_dates_and_zones(self):
        m = sta._maskuj_literaly("a = 'Fikcyjny' AND b >= '2026-10-01' AT TIME ZONE 'Europe/Warsaw'", sql_single=True)
        self.assertIn("'2026-10-01'", m)
        self.assertIn("'Europe/Warsaw'", m)
        self.assertNotIn("Fikcyjny", m)


if __name__ == "__main__":
    unittest.main()
