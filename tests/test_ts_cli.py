"""CLI w trybie --jezyk ts: pliki, wykluczenia, baseline, JSON/CSV, kody wyjścia, zgodność wsteczna."""
import csv
import io
import json
import os
import unittest

import sql_timezone_audit as sta
from tests.helpers import TmpTestCase

HIGH = "export const A = () => { const d = new Date().toISOString().slice(0, 10); return d; };\n"
LOW = "export const B = (v: string) => new Date(v).toLocaleDateString('pl-PL');\n"
CLEAN = "export const C = () => 1;\n"


class TsCliBase(TmpTestCase):
    def uruchom(self, *argv):
        out, err = io.BytesIO(), io.BytesIO()
        kod = sta.main(["--jezyk", "ts", "--backend", self.tmp] + list(argv), stdout=out, stderr=err)
        return kod, out.getvalue().decode("utf-8"), err.getvalue().decode("utf-8")

    def json_(self, *argv):
        sciezka = os.path.join(self.tmp, "_r.json")
        self.uruchom("--json", sciezka, *argv)
        with open(sciezka, encoding="utf-8") as f:
            return json.load(f)


class TsFiles(TsCliBase):
    def test_extensions_scanned(self):
        for rel in ("a.ts", "b.tsx", "c.js", "d.jsx"):
            self.zapisz("src/" + rel, HIGH)
        self.zapisz("src/e.py", "x = 1\n")
        self.zapisz("src/f.mjs", HIGH)
        dane = self.json_()
        self.assertEqual([p["plik"] for p in dane["pliki"]], ["src/a.ts", "src/b.tsx", "src/c.js", "src/d.jsx"])

    def test_default_excludes(self):
        for rel in ("src/ok.ts", "node_modules/x/i.js", "dist/b.js", "build/b.js", ".next/c.js", "coverage/c.js",
                    "src/__tests__/t.ts", "src/__mocks__/m.ts", "tests/t.ts", "src/a.test.ts", "src/a.spec.tsx",
                    "src/types.d.ts", "src/bundle.min.js", "src/A.stories.tsx"):
            self.zapisz(rel, HIGH)
        self.assertEqual([p["plik"] for p in self.json_()["pliki"]], ["src/ok.ts"])

    def test_user_exclude(self):
        self.zapisz("src/a.ts", HIGH)
        self.zapisz("src/generated/g.ts", HIGH)
        self.assertEqual([p["plik"] for p in self.json_("--exclude", "generated")["pliki"]], ["src/a.ts"])

    def test_files_from_with_windows_separators(self):
        self.zapisz("src/a.ts", HIGH)
        self.zapisz("src/b.ts", HIGH)
        lista = self.zapisz("lista.txt", "src\\b.ts\r\nsrc/nie_ma.ts\r\nREADME.md\r\n")
        kod, out, err = self.uruchom("--files-from", lista)
        self.assertIn("src/b.ts:1", out)
        self.assertNotIn("src/a.ts", out)
        self.assertIn("src/nie_ma.ts", err)

    def test_src_alias(self):
        self.zapisz("a.ts", HIGH)
        out = io.BytesIO()
        kod = sta.main(["--jezyk", "ts", "--src", self.tmp], stdout=out, stderr=io.BytesIO())
        self.assertEqual(kod, 1)

    def test_bom_and_utf8_content(self):
        self.zapisz("a.ts", b"\xef\xbb\xbf// za\xc5\xbc\xc3\xb3\xc5\x82\xc4\x87\n" + HIGH.encode("utf-8"), bajty=True)
        self.assertEqual(self.uruchom()[0], 1)

    def test_crlf_files(self):
        self.zapisz("a.ts", HIGH.replace("\n", "\r\n").encode("utf-8"), bajty=True)
        kod, out, _ = self.uruchom()
        self.assertEqual(kod, 1)
        self.assertNotIn("\r", out)

    def test_garbage_file_does_not_crash(self):
        self.zapisz("a.ts", b"\x00\xff\xfe `${ ((( /* \n", bajty=True)
        self.assertEqual(self.uruchom()[0], 0)

    def test_performance_300_files(self):
        import time
        for i in range(300):
            self.zapisz("src/m%03d.tsx" % i, (HIGH + LOW + CLEAN) * 5)
        t = time.time()
        self.uruchom()
        self.assertLess(time.time() - t, 10)


class TsExitCodesAndOutput(TsCliBase):
    def test_exit_1_for_new_high(self):
        self.zapisz("a.ts", HIGH)
        self.assertEqual(self.uruchom()[0], 1)

    def test_exit_0_for_low_only(self):
        self.zapisz("a.ts", LOW)
        kod, out, _ = self.uruchom()
        self.assertEqual(kod, 0)
        self.assertIn("ts_locale_no_timezone", out)

    def test_exit_0_clean(self):
        self.zapisz("a.ts", CLEAN)
        self.assertEqual(self.uruchom()[0], 0)

    def test_exit_0_when_suppressed(self):
        self.zapisz("a.ts", "const d = new Date().toISOString().slice(0, 10); // tz-ok: log\n")
        self.assertEqual(self.uruchom()[0], 0)

    def test_text_report_sections_and_matrix(self):
        self.zapisz("src/a.ts", HIGH + LOW)
        _, out, _ = self.uruchom()
        for s in ("Podsumowanie", "Liczba znalezisk wg kodu i ważności", "Najpierw napraw", "Wyniki wg ważności",
                  "Rozkład per plik", "ts_today_iso_slice", "RAZEM", "kontekst:", "podpowiedź:", "src/a.ts:1"):
            self.assertIn(s, out)

    def test_report_is_lf_utf8_without_absolute_paths(self):
        self.zapisz("src/a.ts", HIGH)
        _, out, _ = self.uruchom()
        self.assertNotIn("\r", out)
        self.assertNotIn(self.tmp.replace("\\", "/"), out)
        self.assertNotIn("\\", out)

    def test_json_summary_by_code_and_severity(self):
        self.zapisz("src/a.ts", HIGH + LOW)
        d = self.json_()
        self.assertEqual(d["tryb"], "ts")
        p = d["podsumowanie"]
        self.assertEqual(p["wg_kodu"]["ts_today_iso_slice"]["wysoka"], 1)
        self.assertEqual(p["wg_kodu"]["ts_locale_no_timezone"]["niska"], 1)
        self.assertEqual(p["wg_kodu"]["ts_manual_hour_shift"]["razem"], 0)
        self.assertEqual(p["wg_waznosci"]["wysoka"], 1)
        self.assertEqual(p["nowe_blokujace"], 1)
        self.assertEqual(sum(v["razem"] for v in p["wg_kodu"].values()), p["wyniki"])
        w = d["wyniki"][0]
        for klucz in ("plik", "linia", "kod", "waznosc", "pewnosc", "kontekst", "fragment", "podpowiedz", "dlaczego"):
            self.assertIn(klucz, w)

    def test_csv_output(self):
        self.zapisz("src/a.ts", HIGH + LOW)
        sciezka = os.path.join(self.tmp, "_r.csv")
        self.uruchom("--csv", sciezka)
        with open(sciezka, "rb") as f:
            surowe = f.read()
        self.assertNotIn(b"\r", surowe)
        wiersze = list(csv.reader(io.StringIO(surowe.decode("utf-8"))))
        self.assertEqual(wiersze[0][:5], ["plik", "linia", "kod", "waznosc", "pewnosc"])
        self.assertEqual(len(wiersze), 3)
        self.assertEqual(wiersze[1][0], "src/a.ts")
        self.assertIn(wiersze[1][2], sta.KODY_TS)

    def test_csv_quotes_commas_and_newlines_safely(self):
        self.zapisz("src/a.ts", "const d = new Date().toISOString().slice(0, 10), e = 1;\n")
        sciezka = os.path.join(self.tmp, "_r.csv")
        self.uruchom("--csv", sciezka)
        with open(sciezka, encoding="utf-8", newline="") as f:
            wiersze = list(csv.reader(f))
        self.assertIn(",", wiersze[1][6])


class TsBaseline(TsCliBase):
    def baseline(self):
        return os.path.abspath(os.path.join(self.tmp, "..", "bl_ts_%d.json" % id(self)))

    def test_baseline_round_trip_and_line_shift(self):
        self.zapisz("src/a.ts", HIGH)
        bl = self.baseline()
        self.addCleanup(lambda: os.path.exists(bl) and os.remove(bl))
        self.assertEqual(self.uruchom("--write-baseline", bl)[0], 0)
        self.zapisz("src/a.ts", "// nowa linia\n\n" + HIGH)
        kod, out, _ = self.uruchom("--baseline", bl)
        self.assertEqual(kod, 0)
        self.assertIn("[znany]", out)

    def test_new_finding_after_baseline(self):
        self.zapisz("src/a.ts", HIGH)
        bl = self.baseline()
        self.addCleanup(lambda: os.path.exists(bl) and os.remove(bl))
        self.uruchom("--write-baseline", bl)
        self.zapisz("src/b.ts", HIGH.replace("A", "Z"))
        self.assertEqual(self.uruchom("--baseline", bl)[0], 1)


class TsColumnFiles(TsCliBase):
    def test_local_columns_make_field_likely(self):
        self.zapisz("src/a.ts", "export const f = () => ({ visitOn: new Date().toISOString() });\n")
        lok = self.zapisz("local.txt", "visits.visit_on\n")
        d = self.json_("--local-columns", lok)
        self.assertEqual([(w["kod"], w["pewnosc"]) for w in d["wyniki"]], [("ts_now_into_local_field", "likely")])

    def test_tz_columns_override_heuristic(self):
        self.zapisz("src/a.ts", "export const f = () => ({ startsAt: new Date().toISOString() });\n")
        tz = self.zapisz("tz.txt", "shifts.starts_at\n")
        self.assertEqual(self.json_("--tz-columns", tz)["wyniki"], [])


class BackwardCompatibility(TmpTestCase):
    def test_default_language_is_python(self):
        self.zapisz("a.py", 'def f(cur):\n    cur.execute("SELECT 1 WHERE d = CURRENT_DATE")\n')
        self.zapisz("b.ts", HIGH)
        out = io.BytesIO()
        kod = sta.main(["--backend", self.tmp], stdout=out, stderr=io.BytesIO())
        tekst = out.getvalue().decode("utf-8")
        self.assertEqual(kod, 1)
        self.assertIn("a.py:2", tekst)
        self.assertNotIn("b.ts", tekst)
        self.assertNotIn("ts_today_iso_slice", tekst)

    def test_explicit_py_equals_default(self):
        self.zapisz("a.py", 'def f(cur):\n    cur.execute("SELECT 1 WHERE d = CURRENT_DATE")\n')
        a, b = io.BytesIO(), io.BytesIO()
        sta.main(["--backend", self.tmp], stdout=a, stderr=io.BytesIO())
        sta.main(["--backend", self.tmp, "--jezyk", "py"], stdout=b, stderr=io.BytesIO())
        self.assertEqual(a.getvalue(), b.getvalue())

    def test_csv_for_python_mode(self):
        self.zapisz("a.py", 'def f(cur):\n    cur.execute("SELECT 1 WHERE d = CURRENT_DATE")\n')
        sciezka = os.path.join(self.tmp, "r.csv")
        sta.main(["--backend", self.tmp, "--csv", sciezka], stdout=io.BytesIO(), stderr=io.BytesIO())
        with open(sciezka, encoding="utf-8", newline="") as f:
            wiersze = list(csv.reader(f))
        self.assertEqual(wiersze[0][:4], ["plik", "linia", "kategoria", "waznosc"])
        self.assertEqual(wiersze[1][2], "sql_current_date_utc")

    def test_python_json_unchanged_shape(self):
        self.zapisz("a.py", 'def f(cur):\n    cur.execute("SELECT 1 WHERE d = CURRENT_DATE")\n')
        sciezka = os.path.join(self.tmp, "r.json")
        sta.main(["--backend", self.tmp, "--json", sciezka], stdout=io.BytesIO(), stderr=io.BytesIO())
        with open(sciezka, encoding="utf-8") as f:
            d = json.load(f)
        self.assertNotIn("tryb", d)
        self.assertIn("kategorie", d["podsumowanie"])

    def test_zbierz_pliki_defaults_unchanged(self):
        self.zapisz("tests/t.py", "x = 1\n")
        self.zapisz("a.py", "x = 1\n")
        self.zapisz("c.ts", "x = 1\n")
        self.assertEqual([r for r, _ in sta.zbierz_pliki(self.tmp)], ["a.py"])


if __name__ == "__main__":
    unittest.main()
