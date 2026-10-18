"""Wspólne pomocniki testów (fikcyjne dane, bez sieci i bazy)."""
import os
import shutil
import tempfile
import textwrap
import unittest

import sql_timezone_audit as sta

TZ = ["created_at", "updated_at", "sent_at", "orders.paid_at"]
LOCAL = ["starts_at", "scheduled_for", "due_date", "shifts.ends_at"]


def cfg(tz=TZ, local=LOCAL):
    return sta.KonfiguracjaKolumn(tz, local)


def wyniki(src, tz=TZ, local=LOCAL, plik="modul.py", plik_testowy=False):
    w, _ = sta.analizuj_zrodlo(textwrap.dedent(src), plik, cfg(tz, local), plik_testowy)
    return w


def kategorie(src, **kw):
    return sorted(w.kategoria for w in wyniki(src, **kw))


def sql(zapytanie, **kw):
    """Wyniki dla jednego wywołania cur.execute z podanym SQL-em."""
    return wyniki('def f(cur):\n    cur.execute(%r)\n' % zapytanie, **kw)


def sql_kat(zapytanie, **kw):
    return sorted(w.kategoria for w in sql(zapytanie, **kw))


class TmpTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def zapisz(self, rel, tresc, bajty=False):
        sciezka = os.path.join(self.tmp, *rel.split("/"))
        os.makedirs(os.path.dirname(sciezka), exist_ok=True)
        with open(sciezka, "wb") as f:
            f.write(tresc if bajty else textwrap.dedent(tresc).encode("utf-8"))
        return sciezka
