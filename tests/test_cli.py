"""CLI: baseline, --files-from, wykluczenia, JSON, UTF-8/LF, ścieżki z '/'."""
import contextlib
import io
import json
import os
import time

import sql_timezone_audit as sta
from tests.helpers import TmpTestCase

BAD = 'def f(cur):\n    cur.execute("SELECT 1 WHERE d = CURRENT_DATE")\n'
OK = 'def f(cur):\n    cur.execute("SELECT 1")\n'


class CliBase(TmpTestCase):
    def uruchom(self, *argv):
        out, err = io.BytesIO(), io.BytesIO()
        kod = sta.main(list(argv), stdout=out, stderr=err)
        return kod, out.getvalue(), err.getvalue()

    def json_raportu(self):
        with open(os.path.join(self.tmp, "r.json"), encoding="utf-8") as f:
            return json.load(f)

    def backend(self, *argv):
        return self.uruchom("--backend", self.tmp, *argv)


class ExitCodes(CliBase):
    def test_exit_1_on_new_blocking(self):
        self.zapisz("a.py", BAD)
        self.assertEqual(self.backend()[0], 1)

    def test_exit_0_when_clean(self):
        self.zapisz("a.py", OK)
        self.assertEqual(self.backend()[0], 0)

    def test_exit_0_for_non_blocking_only(self):
        self.zapisz("a.py", "from datetime import datetime\ndef f():\n    return datetime.utcnow()\n")
        self.assertEqual(self.backend()[0], 0)

    def test_exit_2_missing_backend(self):
        kod, _, err = self.uruchom("--backend", os.path.join(self.tmp, "nie-ma"))
        self.assertEqual(kod, 2)
        self.assertIn("błąd", err.decode("utf-8"))

    def test_exit_2_missing_columns_file(self):
        self.zapisz("a.py", OK)
        self.assertEqual(self.backend("--tz-columns", os.path.join(self.tmp, "brak.txt"))[0], 2)

    def test_exit_2_without_backend_argument(self):
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(self.uruchom()[0], 2)


class Baseline(CliBase):
    def test_write_then_read_baseline(self):
        self.zapisz("a.py", BAD)
        bl = os.path.join(self.tmp, "..", "bl_%d.json" % id(self))
        bl = os.path.abspath(bl)
        self.addCleanup(lambda: os.path.exists(bl) and os.remove(bl))
        kod, _, _ = self.backend("--write-baseline", bl)
        self.assertEqual(kod, 0)
        kod, out, _ = self.backend("--baseline", bl)
        self.assertEqual(kod, 0)
        self.assertIn("[znany]", out.decode("utf-8"))

    def test_new_result_after_baseline(self):
        self.zapisz("a.py", BAD)
        bl = os.path.abspath(os.path.join(self.tmp, "..", "bl2_%d.json" % id(self)))
        self.addCleanup(lambda: os.path.exists(bl) and os.remove(bl))
        self.backend("--write-baseline", bl)
        self.zapisz("b.py", BAD)
        self.assertEqual(self.backend("--baseline", bl)[0], 1)

    def test_baseline_key_ignores_line_numbers(self):
        self.zapisz("a.py", BAD)
        bl = os.path.abspath(os.path.join(self.tmp, "..", "bl3_%d.json" % id(self)))
        self.addCleanup(lambda: os.path.exists(bl) and os.remove(bl))
        self.backend("--write-baseline", bl)
        self.zapisz("a.py", "\n\n\n# przesunięcie linii\n" + BAD)
        self.assertEqual(self.backend("--baseline", bl)[0], 0)

    def test_baseline_counts_duplicates(self):
        dwa = ('def f(cur):\n    cur.execute("SELECT 1 WHERE d = CURRENT_DATE")\n'
               '    cur.execute("SELECT 1 WHERE d = CURRENT_DATE")\n')
        self.zapisz("a.py", BAD)
        bl = os.path.abspath(os.path.join(self.tmp, "..", "bl4_%d.json" % id(self)))
        self.addCleanup(lambda: os.path.exists(bl) and os.remove(bl))
        self.backend("--write-baseline", bl)
        self.zapisz("a.py", dwa)
        self.assertEqual(self.backend("--baseline", bl)[0], 1)

    def test_baseline_file_is_utf8_lf_posix(self):
        self.zapisz("sub/a.py", BAD)
        bl = os.path.abspath(os.path.join(self.tmp, "..", "bl5_%d.json" % id(self)))
        self.addCleanup(lambda: os.path.exists(bl) and os.remove(bl))
        self.backend("--write-baseline", bl)
        with open(bl, "rb") as f:
            dane = f.read()
        self.assertNotIn(b"\r", dane)
        self.assertIn("sub/a.py", dane.decode("utf-8"))
        self.assertNotIn("\\", json.loads(dane.decode("utf-8"))["klucze"][0]["klucz"])

    def test_invalid_baseline_json(self):
        self.zapisz("a.py", OK)
        zly = self.zapisz("bad.json", "{nie json")
        self.assertEqual(self.backend("--baseline", zly)[0], 2)


class FileSelection(CliBase):
    def test_recursive_and_default_excludes(self):
        for rel in ("app/a.py", "venv/v.py", "node_modules/n.py", "__pycache__/p.py", "tests/t.py",
                    "migrations/m.py", "archive/x.py", "app/migrations/m.py"):
            self.zapisz(rel, BAD)
        kod, out, _ = self.backend("--json", os.path.join(self.tmp, "r.json"))
        dane = self.json_raportu()
        self.assertEqual([p["plik"] for p in dane["pliki"]], ["app/a.py"])

    def test_exclude_pattern(self):
        self.zapisz("a.py", BAD)
        self.zapisz("gen/b.py", BAD)
        self.zapisz("c_pb2.py", BAD)
        self.backend("--exclude", "gen", "*_pb2.py", "--json", os.path.join(self.tmp, "r.json"))
        dane = self.json_raportu()
        self.assertEqual([p["plik"] for p in dane["pliki"]], ["a.py"])

    def test_files_from(self):
        self.zapisz("a.py", BAD)
        self.zapisz("b.py", BAD)
        lista = self.zapisz("lista.txt", "# zmienione\nb.py\n")
        self.backend("--files-from", lista, "--json", os.path.join(self.tmp, "r.json"))
        dane = self.json_raportu()
        self.assertEqual([p["plik"] for p in dane["pliki"]], ["b.py"])

    def test_files_from_windows_separators(self):
        self.zapisz("pkg/sub/b.py", BAD)
        lista = self.zapisz("lista.txt", "pkg\\sub\\b.py\r\n")
        self.backend("--files-from", lista, "--json", os.path.join(self.tmp, "r.json"))
        dane = self.json_raportu()
        self.assertEqual([p["plik"] for p in dane["pliki"]], ["pkg/sub/b.py"])

    def test_files_from_missing_file_warns(self):
        self.zapisz("a.py", OK)
        lista = self.zapisz("lista.txt", "nie_ma.py\n")
        kod, _, err = self.backend("--files-from", lista)
        self.assertEqual(kod, 0)
        self.assertIn("nie_ma.py", err.decode("utf-8"))

    def test_files_from_respects_default_excludes(self):
        self.zapisz("tests/t.py", BAD)
        lista = self.zapisz("lista.txt", "tests/t.py\n")
        self.assertEqual(self.backend("--files-from", lista)[0], 0)

    def test_non_python_files_ignored(self):
        self.zapisz("a.txt", BAD)
        self.assertEqual(self.backend()[0], 0)


class Robustness(CliBase):
    def test_syntax_error_warns_and_skips(self):
        self.zapisz("zly.py", "def f(:\n")
        self.zapisz("a.py", BAD)
        kod, out, err = self.backend()
        self.assertEqual(kod, 1)
        self.assertIn("zly.py", err.decode("utf-8"))

    def test_weird_code_does_not_raise(self):
        self.zapisz("a.py", "x = " + " + ".join(['"a"'] * 400) + "\ndef f(c):\n    c.execute(x)\n"
                    "async def g():\n    async with a as b:\n        await b.execute(1 if c else 2)\n"
                    "lambda: (yield)\nclass A(B, metaclass=M):\n    pass\n")
        self.assertIn(self.backend()[0], (0, 1))

    def test_deeply_nested_expression(self):
        self.zapisz("a.py", "x = " + "(" * 150 + "1" + ")" * 150 + "\n")
        self.assertIn(self.backend()[0], (0, 1))

    def test_null_bytes_file_skipped(self):
        self.zapisz("n.py", b"x = 1\x00\n", bajty=True)
        kod, _, _ = self.backend()
        self.assertEqual(kod, 0)

    def test_utf8_bom_and_polish_text(self):
        self.zapisz("a.py", b"\xef\xbb\xbf" + "# za\u017c\u00f3\u0142\u0107 g\u0119\u015bl\u0105\n".encode("utf-8") + BAD.encode("utf-8"), bajty=True)
        self.assertEqual(self.backend()[0], 1)

    def test_crlf_source(self):
        self.zapisz("a.py", BAD.replace("\n", "\r\n").encode("utf-8"), bajty=True)
        kod, out, _ = self.backend()
        self.assertEqual(kod, 1)
        self.assertNotIn(b"\r", out)

    def test_cp1250_coding_cookie(self):
        tresc = "# -*- coding: cp1250 -*-\n# za\u017c\u00f3\u0142\u0107\n" + BAD
        self.zapisz("a.py", tresc.encode("cp1250"), bajty=True)
        self.assertEqual(self.backend()[0], 1)

    def test_performance_200_files(self):
        for i in range(200):
            self.zapisz("m%03d.py" % i, BAD * 3 + "from datetime import datetime\n" + OK * 10)
        t = time.time()
        self.backend()
        self.assertLess(time.time() - t, 10)

    def test_empty_backend(self):
        kod, out, _ = self.backend()
        self.assertEqual(kod, 0)
        self.assertIn("Przeanalizowane pliki: 0", out.decode("utf-8"))


class OutputFormat(CliBase):
    def test_stdout_is_utf8_with_lf_only(self):
        self.zapisz("a.py", BAD)
        _, out, _ = self.backend()
        out.decode("utf-8")
        self.assertNotIn(b"\r", out)
        self.assertTrue(out.endswith(b"\n"))
        self.assertIn("Rozkład kategorii".encode("utf-8"), out)

    def test_paths_always_forward_slashes(self):
        self.zapisz("pkg/sub/a.py", BAD)
        _, out, _ = self.backend()
        self.assertIn("pkg/sub/a.py:2", out.decode("utf-8"))
        self.assertNotIn("\\", out.decode("utf-8"))

    def test_json_report(self):
        self.zapisz("pkg/a.py", BAD)
        sciezka = os.path.join(self.tmp, "r.json")
        self.backend("--json", sciezka)
        with open(sciezka, "rb") as f:
            surowe = f.read()
        self.assertNotIn(b"\r", surowe)
        dane = json.loads(surowe.decode("utf-8"))
        w = dane["wyniki"][0]
        self.assertEqual((w["plik"], w["funkcja"], w["linia"], w["kategoria"]),
                         ("pkg/a.py", "f", 2, "sql_current_date_utc"))
        for klucz in ("helper", "fragment", "dlaczego", "propozycja", "pewnosc", "waznosc"):
            self.assertIn(klucz, w)
        self.assertEqual(dane["podsumowanie"]["nowe_blokujace"], 1)
        self.assertEqual(dane["pliki"][0]["wywolania_sql"], 1)

    def test_report_sections(self):
        self.zapisz("a.py", BAD)
        tekst = self.backend()[1].decode("utf-8")
        for sekcja in ("Podsumowanie", "Najpierw napraw", "Wyniki wg ważności", "Rozkład per plik"):
            self.assertIn(sekcja, tekst)

    def test_no_absolute_paths_in_report(self):
        self.zapisz("a.py", BAD)
        self.assertNotIn(self.tmp.replace("\\", "/"), self.backend()[1].decode("utf-8"))

    def test_najpierw_napraw_orders_by_risk(self):
        self.zapisz("a.py", BAD + 'def g(s, j):\n    s.add_job(j, "cron", hour=6)\n'
                    'from datetime import date\ndef h():\n    return f"N/{date.today():%Y/%m}"\n')
        tekst = self.backend()[1].decode("utf-8")
        sekcja = tekst.split("Najpierw napraw")[1].split("Wyniki wg ważności")[0]
        self.assertLess(sekcja.index("numbering_by_date"), sekcja.index("scheduler_no_timezone"))
        self.assertLess(sekcja.index("scheduler_no_timezone"), sekcja.index("sql_current_date_utc"))

    def test_podsumuj_lines(self):
        self.zapisz("a.py", BAD)
        raport = sta.audyt(self.tmp, sta.KonfiguracjaKolumn())
        linie = sta.podsumuj(raport)
        self.assertIn("Wywołania SQL: 1 (z funkcjami czasu: 1)", linie)

    def test_per_file_table_counts(self):
        self.zapisz("a.py", BAD + OK)
        raport = sta.audyt(self.tmp, sta.KonfiguracjaKolumn())
        st = raport.pliki[0]
        self.assertEqual((st.sql, st.sql_czas, st.wyniki), (2, 1, 1))
