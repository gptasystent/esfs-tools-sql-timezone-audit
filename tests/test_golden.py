"""Golden: raport dla fikcyjnego backendu examples/ musi zgadzać się z examples/EXPECTED.md.

Odświeżenie wzorca po świadomej zmianie narzędzia:
    UPDATE_GOLDEN=1 python -m unittest tests.test_golden
"""
import io
import json
import os
import unittest

import sql_timezone_audit as sta
from tests.helpers import TmpTestCase

KORZEN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EX = os.path.join(KORZEN, "examples")
ARGS = ["--backend", os.path.join(EX, "backend"),
        "--tz-columns", os.path.join(EX, "tz_columns.txt"),
        "--local-columns", os.path.join(EX, "local_columns.txt")]


def _lf(tekst):
    return tekst.replace("\r\n", "\n")


def uruchom(*extra):
    out, err = io.BytesIO(), io.BytesIO()
    kod = sta.main(ARGS + list(extra), stdout=out, stderr=err)
    return kod, out.getvalue(), err.getvalue()


class Golden(TmpTestCase):
    def test_report_matches_expected(self):
        kod, out, err = uruchom()
        sciezka = os.path.join(EX, "EXPECTED.md")
        if os.environ.get("UPDATE_GOLDEN"):
            with open(sciezka, "wb") as f:
                f.write(out)
        with open(sciezka, "rb") as f:
            oczekiwane = f.read()
        # niezależnie od core.autocrlf: porównanie po normalizacji końców linii
        self.assertEqual(_lf(out.decode("utf-8")), _lf(oczekiwane.decode("utf-8")))
        self.assertEqual(kod, 1)
        self.assertEqual(err, b"")

    def test_expected_file_is_lf_utf8(self):
        with open(os.path.join(EX, "EXPECTED.md"), "rb") as f:
            dane = f.read()
        dane.decode("utf-8")
        self.assertNotIn(b"\r", dane.replace(b"\r\n", b"\n"))  # CRLF z checkoutu autocrlf jest dopuszczalny

    def test_every_category_present_in_examples(self):
        sciezka = os.path.join(self.tmp, "r.json")
        uruchom("--json", sciezka)
        with open(sciezka, encoding="utf-8") as f:
            dane = json.load(f)
        for kat, ile in dane["podsumowanie"]["kategorie"].items():
            self.assertGreater(ile, 0, kat)

    def test_examples_clean_files_have_no_findings(self):
        sciezka = os.path.join(self.tmp, "r.json")
        uruchom("--json", sciezka)
        with open(sciezka, encoding="utf-8") as f:
            dane = json.load(f)
        pliki = set(w["plik"] for w in dane["wyniki"])
        self.assertNotIn("timeutils.py", pliki)
        self.assertNotIn("db.py", pliki)

    def test_deterministic(self):
        self.assertEqual(uruchom()[1], uruchom()[1])

    def test_heuristics_file_is_uncertain_only_for_unlisted_columns(self):
        sciezka = os.path.join(self.tmp, "r.json")
        uruchom("--json", sciezka)
        with open(sciezka, encoding="utf-8") as f:
            dane = json.load(f)
        pew = [w["pewnosc"] for w in dane["wyniki"] if w["plik"] == "heuristics.py" and w["kategoria"] in ("sql_local_vs_now", "sql_literal_boundary")]
        self.assertTrue(pew and all(p == "uncertain" for p in pew))

    def test_without_column_files_everything_is_uncertain_or_column_free(self):
        out, err = io.BytesIO(), io.BytesIO()
        sta.main(["--backend", os.path.join(EX, "backend"), "--json", os.path.join(self.tmp, "r.json")],
                 stdout=out, stderr=err)
        with open(os.path.join(self.tmp, "r.json"), encoding="utf-8") as f:
            dane = json.load(f)
        zalezne = ("sql_local_vs_now", "sql_date_trunc_utc", "sql_literal_boundary")
        self.assertTrue(all(w["pewnosc"] == "uncertain" for w in dane["wyniki"] if w["kategoria"] in zalezne))


if __name__ == "__main__":
    unittest.main()
