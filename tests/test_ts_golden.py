"""Golden dla trybu ts: raport dla fikcyjnego frontendu examples/frontend == examples/EXPECTED_TS.md.

Odświeżenie wzorca po świadomej zmianie narzędzia:
    UPDATE_GOLDEN=1 python -m unittest tests.test_ts_golden
"""
import io
import json
import os
import unittest

import sql_timezone_audit as sta
from tests.helpers import TmpTestCase

KORZEN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EX = os.path.join(KORZEN, "examples")
ARGS = ["--jezyk", "ts", "--backend", os.path.join(EX, "frontend"),
        "--tz-columns", os.path.join(EX, "tz_columns.txt"),
        "--local-columns", os.path.join(EX, "local_columns.txt")]


def uruchom(*extra):
    out, err = io.BytesIO(), io.BytesIO()
    kod = sta.main(ARGS + list(extra), stdout=out, stderr=err)
    return kod, out.getvalue(), err.getvalue()


def _lf(tekst):
    return tekst.replace("\r\n", "\n")


class GoldenTs(TmpTestCase):
    def test_report_matches_expected(self):
        kod, out, err = uruchom()
        sciezka = os.path.join(EX, "EXPECTED_TS.md")
        if os.environ.get("UPDATE_GOLDEN"):
            with open(sciezka, "wb") as f:
                f.write(out)
        with open(sciezka, "rb") as f:
            oczekiwane = f.read()
        self.assertEqual(_lf(out.decode("utf-8")), _lf(oczekiwane.decode("utf-8")))
        self.assertEqual(kod, 1)
        self.assertEqual(err, b"")

    def test_deterministic(self):
        self.assertEqual(uruchom()[1], uruchom()[1])

    def test_every_code_present_in_examples(self):
        sciezka = os.path.join(self.tmp, "r.json")
        uruchom("--json", sciezka)
        with open(sciezka, encoding="utf-8") as f:
            dane = json.load(f)
        for kod, wiersz in dane["podsumowanie"]["wg_kodu"].items():
            self.assertGreater(wiersz["razem"], 0, kod)

    def test_clean_helper_file_has_no_findings(self):
        sciezka = os.path.join(self.tmp, "r.json")
        uruchom("--json", sciezka)
        with open(sciezka, encoding="utf-8") as f:
            dane = json.load(f)
        self.assertNotIn("src/lib/dates.ts", set(w["plik"] for w in dane["wyniki"]))

    def test_high_only_for_allowed_patterns(self):
        sciezka = os.path.join(self.tmp, "r.json")
        uruchom("--json", sciezka)
        with open(sciezka, encoding="utf-8") as f:
            dane = json.load(f)
        dozwolone = {"ts_today_iso_slice", "ts_now_into_local_field", "ts_startof_day_utc", "ts_locale_no_timezone"}
        for w in dane["wyniki"]:
            if w["waznosc"] == "wysoka":
                self.assertIn(w["kod"], dozwolone)

    def test_expected_file_tolerates_crlf_checkout(self):
        with open(os.path.join(EX, "EXPECTED_TS.md"), "rb") as f:
            dane = f.read()
        dane.decode("utf-8")
        self.assertNotIn(b"\r", dane.replace(b"\r\n", b"\n"))


if __name__ == "__main__":
    unittest.main()
