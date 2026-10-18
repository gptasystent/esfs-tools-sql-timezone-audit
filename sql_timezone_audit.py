#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sql_timezone_audit - statyczny audyt błędów strefy czasowej i granicy doby.

Analizuje kod Pythona (Flask + psycopg2) przez ``ast``: szuka zapytań SQL i kodu,
który miesza czas UTC (``timestamptz``) z czasem lokalnym (``timestamp`` bez strefy).
Tylko raport - nic nie poprawia. Python 3.8+, zero zależności zewnętrznych.

Wyjście zawsze UTF-8 z końcami linii LF, ścieżki zawsze ze znakiem ``/``.
"""
import argparse
import ast
import fnmatch
import io
import json
import os
import re
import sys
import tokenize
from collections import Counter, OrderedDict
from dataclasses import dataclass, field

WERSJA = 1

DOMYSLNE_WYKLUCZENIA = ("venv", ".venv", "node_modules", "__pycache__", "tests",
                        "migrations", "archive", ".git")

WAZNOSCI = ("wysoka", "srednia", "niska", "informacja")

# kategoria -> (ważność, dlaczego, propozycja)
KATEGORIE = OrderedDict([
    ("sql_current_date_utc", (
        "wysoka",
        "CURRENT_DATE / now()::date liczone jest w strefie sesji bazy (UTC): między 00:00 "
        "a 02:00 czasu lokalnego to jeszcze \"wczoraj\".",
        "Zastąp przez (NOW() AT TIME ZONE 'Europe/Warsaw')::date.")),
    ("sql_local_vs_now", (
        "wysoka",
        "Kolumna lokalna (timestamp bez strefy) porównywana z NOW(), które jest w UTC: "
        "okno przesunięte o 1-2 godziny.",
        "Porównuj z NOW() AT TIME ZONE 'Europe/Warsaw'.")),
    ("sql_date_trunc_utc", (
        "wysoka",
        "Dzień/miesiąc liczony w UTC na kolumnie timestamptz: zdarzenie o 23:30 lokalnie "
        "ląduje w następnym dniu.",
        "Dodaj AT TIME ZONE 'Europe/Warsaw' do kolumny, np. date_trunc('day', kol AT TIME ZONE 'Europe/Warsaw').")),
    ("sql_literal_boundary", (
        "srednia",
        "Kolumna timestamptz porównywana z literałem daty/czasu bez strefy: granica doby "
        "wypada w UTC, nie lokalnie.",
        "Zapisz granicę jako ('2026-10-01'::timestamp AT TIME ZONE 'Europe/Warsaw').")),
    ("sql_fixed_offset", (
        "srednia",
        "Sztywne przesunięcie godzinowe psuje się przy zmianie czasu (ostatnie niedziele "
        "marca i października).",
        "Zamień przesunięcie na AT TIME ZONE 'Europe/Warsaw'.")),
    ("sql_utc_into_local_column", (
        "wysoka",
        "NOW()/CURRENT_TIMESTAMP (UTC) zapisywane do kolumny lokalnej (timestamp bez strefy): "
        "kolumna ma przechowywać czas ze ściany zegara, a dostaje UTC.",
        "Zapisz NOW() AT TIME ZONE 'Europe/Warsaw' albo zmień kolumnę na timestamptz.")),
    ("py_naive_now", (
        "wysoka",
        "Naiwny \"teraz/dziś\" (bez tzinfo) trafia do SQL albo jest porównywany z wartością "
        "z bazy; w kontenerze to czas UTC.",
        "Użyj datetime.now(ZoneInfo('Europe/Warsaw')) albo policz wartość w SQL z AT TIME ZONE.")),
    ("py_naive_now_other", (
        "informacja",
        "Naiwny \"teraz/dziś\" (bez tzinfo); nie ustalono użycia w SQL (log, nazwa pliku, test?).",
        "Jeśli wartość trafia do danych biznesowych, podaj jawną strefę (ZoneInfo('Europe/Warsaw')).")),
    ("py_utcnow_deprecated", (
        "niska",
        "datetime.utcnow() / utcfromtimestamp() jest przestarzałe od Pythona 3.12 i zwraca "
        "obiekt naiwny.",
        "Użyj datetime.now(timezone.utc).")),
    ("py_fixed_offset", (
        "srednia",
        "Sztywne timedelta(hours=1|2) dodawane do bieżącego czasu psuje się przy zmianie "
        "czasu letni/zimowy.",
        "Przelicz strefą (ZoneInfo('Europe/Warsaw')) zamiast stałego przesunięcia.")),
    ("scheduler_no_timezone", (
        "wysoka",
        "Zadanie cron bez jawnej strefy odpala się w UTC, czyli godzinę lub dwie później "
        "niż zamierzono lokalnie.",
        "Dodaj timezone='Europe/Warsaw' do wyzwalacza lub konfiguracji harmonogramu.")),
    ("numbering_by_date", (
        "wysoka",
        "Numer dokumentu budowany z naiwnej daty: na granicy miesiąca (po północy lokalnie) "
        "dostaje zły miesiąc.",
        "Weź datę lokalną: (NOW() AT TIME ZONE 'Europe/Warsaw') w SQL lub datetime.now(ZoneInfo('Europe/Warsaw')).")),
])

KATEGORIE_BLOKUJACE = frozenset([
    "sql_current_date_utc", "sql_local_vs_now", "sql_date_trunc_utc",
    "py_naive_now", "scheduler_no_timezone", "numbering_by_date", "sql_utc_into_local_column",
])

# kolejność w sekcji "najpierw napraw" (od największego ryzyka)
KOLEJNOSC_RYZYKA = ("numbering_by_date", "scheduler_no_timezone", "sql_utc_into_local_column",
                    "sql_current_date_utc", "sql_local_vs_now", "sql_date_trunc_utc", "py_naive_now")

MAKS_FRAGMENT = 120

OPIS_DOMYSLNEJ = ("To wartość domyślna parametru zapytania (np. miesiąc/dzień, gdy nie podano): "
                  "błąd widać tylko tuż po północy czasu lokalnego.")


# --------------------------------------------------------------------------- model

@dataclass
class Wynik:
    plik: str
    funkcja: str
    linia: int
    helper: str
    kategoria: str
    waznosc: str
    pewnosc: str
    fragment: str
    dlaczego: str
    propozycja: str
    nowy: bool = True

    def klucz(self):
        return "|".join([self.plik, self.funkcja, self.kategoria, normalizuj(self.fragment)])

    def jako_dict(self):
        return OrderedDict([
            ("plik", self.plik), ("funkcja", self.funkcja), ("linia", self.linia),
            ("helper", self.helper), ("kategoria", self.kategoria),
            ("waznosc", self.waznosc), ("pewnosc", self.pewnosc),
            ("fragment", self.fragment), ("dlaczego", self.dlaczego),
            ("propozycja", self.propozycja), ("nowy", self.nowy),
        ])


@dataclass
class StatPliku:
    plik: str
    sql: int = 0
    sql_czas: int = 0
    wyniki: int = 0


@dataclass
class Raport:
    pliki: list = field(default_factory=list)
    wyniki: list = field(default_factory=list)
    pominiete: list = field(default_factory=list)
    numeracja_zawezona: int = 0
    trafione: set = field(default_factory=set)
    kolumn_tz: int = 0
    kolumn_local: int = 0


def normalizuj(tekst):
    """Normalizacja fragmentu do klucza baseline: małe litery, pojedyncze spacje."""
    return re.sub(r"\s+", " ", tekst).strip().lower()


def _ws(tekst):
    return re.sub(r"\s+", " ", tekst).strip()


# --------------------------------------------------------------------------- konfiguracja kolumn

def heurystyka_kolumny(nazwa):
    """Typ kolumny wyłącznie po nazwie: 'local', 'tz' albo None."""
    c = nazwa.lower()
    if re.match(r"(start|end|planned|scheduled|due)", c):
        return "local"
    if c.endswith("_at") or re.search(r"created|updated|sent", c):
        return "tz"
    if c.endswith("_date"):
        return "local"
    return None


class KonfiguracjaKolumn:
    """Kolumny systemowe (UTC, timestamptz) i lokalne (timestamp, czas ze ściany zegara)."""

    def __init__(self, tz=(), local=()):
        self.tz = set(self._norm(x) for x in tz)
        self.local = set(self._norm(x) for x in local)
        self.tz.discard("")
        self.local.discard("")

    @staticmethod
    def _norm(wpis):
        czesci = [c for c in wpis.strip().lower().split(".") if c]
        return ".".join(czesci[-2:])

    @classmethod
    def z_tekstow(cls, tz_tekst="", local_tekst=""):
        return cls(parsuj_liste_kolumn(tz_tekst), parsuj_liste_kolumn(local_tekst))

    def dopasowania(self, tabele, kolumna):
        """Wpisy z plików pasujące do kolumny: lista (rodzaj, wpis)."""
        kolumna = kolumna.lower()
        wynik = []
        for rodzaj, zbior in (("tz", self.tz), ("local", self.local)):
            for t in tabele:
                if t + "." + kolumna in zbior:
                    wynik.append((rodzaj, t + "." + kolumna))
            if kolumna in zbior:
                wynik.append((rodzaj, kolumna))
        return wynik

    def classify(self, tabele, kolumna):
        """-> (rodzaj, pewne): rodzaj 'tz'/'local'/None, pewne=True gdy z plików wejściowych."""
        kolumna = kolumna.lower()
        for t in tabele:
            k = t + "." + kolumna
            if k in self.tz:
                return "tz", True
            if k in self.local:
                return "local", True
        if kolumna in self.tz:
            return "tz", True
        if kolumna in self.local:
            return "local", True
        return heurystyka_kolumny(kolumna), False


def parsuj_liste_kolumn(tekst):
    wynik = []
    for linia in tekst.splitlines():
        linia = linia.split("#", 1)[0].strip()
        if linia:
            wynik.append(linia)
    return wynik


# --------------------------------------------------------------------------- narzędzia SQL

SQL_KEYWORDS = frozenset("""
select from where and or not null true false is in as on join left right inner outer full cross natural
using group by order having limit offset union all distinct case when then else end between like ilike
similar to interval date timestamp timestamptz time zone at now current_date current_timestamp
current_time localtimestamp localtime extract epoch year month day hour minute second dow doy week
quarter isodow with recursive insert into values update set delete returning default exists any some
array over partition filter asc desc nulls first last cast coalesce nullif only lateral for text integer
int bigint smallint numeric varchar boolean double precision char uuid json jsonb timezone window fetch
conflict do nothing excluded
""".split())

SQL_START = frozenset("""select insert update delete with create alter drop truncate merge call values
explain copy""".split())

_PARAM_RE = re.compile(r"%\(\w+\)[sdfi]|%[sdfi]")
_DOLLAR_RE = re.compile(r"\$([A-Za-z_]\w*)?\$")


def _puste(seg):
    return "".join("\n" if ch == "\n" else " " for ch in seg)


def blank_sql(sql):
    """-> (code, skel), obie tej samej długości co ``sql``.

    code: komentarze zamienione na spacje (literały zostają), skel: dodatkowo
    treść literałów tekstowych zamieniona na spacje (nawiasy/słowa w tekście nie mylą).
    """
    n = len(sql)
    code, skel = [], []
    i = 0
    while i < n:
        c = sql[i]
        dwa = sql[i:i + 2]
        if dwa == "--":
            j = sql.find("\n", i)
            j = n if j == -1 else j
            code.append(" " * (j - i))
            skel.append(" " * (j - i))
            i = j
        elif dwa == "/*":
            j = sql.find("*/", i + 2)
            j = n if j == -1 else j + 2
            b = _puste(sql[i:j])
            code.append(b)
            skel.append(b)
            i = j
        elif c == "'":
            j = i + 1
            domkniety = False
            while j < n:
                if sql[j] == "'":
                    if j + 1 < n and sql[j + 1] == "'":
                        j += 2
                        continue
                    domkniety = True
                    break
                j += 1
            if domkniety:
                seg = sql[i:j + 1]
                skel.append("'" + _puste(seg[1:-1]) + "'")
            else:
                seg = sql[i:]
                skel.append("'" + _puste(seg[1:]))
            code.append(seg)
            i += len(seg)
        elif c == '"':
            j = sql.find('"', i + 1)
            j = n - 1 if j == -1 else j
            seg = sql[i:j + 1]
            code.append(seg)
            skel.append(" " + seg[1:-1] + " " if len(seg) >= 2 else seg)
            i += len(seg)
        elif c == "$":
            m = _DOLLAR_RE.match(sql, i)
            if m:
                j = sql.find(m.group(0), m.end())
                j = n if j == -1 else j + len(m.group(0))
                seg = sql[i:j]
                code.append(seg)
                skel.append(_puste(seg))
                i = j
            else:
                code.append(c)
                skel.append(c)
                i += 1
        else:
            code.append(c)
            skel.append(c)
            i += 1
    skel_s = "".join(skel)
    skel_s = _PARAM_RE.sub(lambda m: "?" + " " * (len(m.group(0)) - 1), skel_s)
    return "".join(code), skel_s


def _match_fwd(s, i):
    depth = 0
    for j in range(i, len(s)):
        ch = s[j]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return j
    return -1


def _match_back(s, i):
    depth = 0
    for j in range(i, -1, -1):
        ch = s[j]
        if ch == ")":
            depth += 1
        elif ch == "(":
            depth -= 1
            if depth == 0:
                return j
    return -1


def _split_top(s, a, b):
    """Dzieli s[a:b] po przecinkach na poziomie 0 -> lista (start, koniec)."""
    wynik = []
    depth = 0
    start = a
    for j in range(a, b):
        ch = s[j]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif ch == "," and depth == 0:
            wynik.append((start, j))
            start = j + 1
    wynik.append((start, b))
    return wynik


_IDENT = r"[A-Za-z_][\w$]*"
_CHAIN_END = re.compile(r"(?:%s\s*\.\s*)*%s\s*$" % (_IDENT, _IDENT))
_CHAIN_START = re.compile(r"(?:%s\s*\.\s*)*%s" % (_IDENT, _IDENT))
_NUM = re.compile(r"[-+]?\d+(?:\.\d+)?")
_CAST_AFTER = re.compile(r"\s*::\s*[A-Za-z_][\w$]*(?:\(\d+\))?")
_TZ_MARK = re.compile(r"\bat\s+time\s+zone\b|\btimezone\s*\(", re.I)
_TZ_AFTER = re.compile(r"[\s)]*at\s+time\s+zone\b", re.I)


def operand_before(skel, pos):
    """Operand (kolumna, wywołanie, grupa w nawiasach) kończący się tuż przed ``pos``."""
    j = pos
    while j > 0 and skel[j - 1].isspace():
        j -= 1
    if j == 0:
        return None
    end = j
    if skel[j - 1] == ")":
        o = _match_back(skel, j - 1)
        if o < 0:
            return None
        start = o
        m = re.search(r"(%s)\s*$" % _IDENT, skel[:o])
        if m and m.group(1).lower() not in SQL_KEYWORDS:
            start = m.start(1)
    elif skel[j - 1] == "'":
        k = skel.rfind("'", 0, j - 1)
        start = k if k >= 0 else j - 1
    else:
        lo = max(0, j - 160)
        m = _CHAIN_END.search(skel[lo:j])
        if not m:
            return None
        start = lo + m.start()
    pre = skel[:start].rstrip()
    if pre.endswith("::"):
        wewn = operand_before(skel, len(pre) - 2)
        if wewn:
            start = wewn[0]
    # "kolumna +/- interval '...'" to jedno wyrażenie arytmetyczne
    for _ in range(4):
        pre = skel[:start].rstrip()
        if pre[-8:].lower() == "interval" and not re.search(r"[\w$]", pre[-9:-8] or " "):
            start = len(pre) - 8
            pre = skel[:start].rstrip()
            if pre and pre[-1] in "+-":
                wewn = operand_before(skel, len(pre) - 1)
                if wewn:
                    start = wewn[0]
                    continue
        break
    return start, end


def operand_after(skel, pos):
    n = len(skel)
    j = pos
    while j < n and skel[j].isspace():
        j += 1
    if j >= n:
        return None
    start = j
    if skel[j] == "(":
        c = _match_fwd(skel, j)
        if c < 0:
            return None
        end = c + 1
    elif skel[j] == "'":
        k = skel.find("'", j + 1)
        end = n if k < 0 else k + 1
    else:
        m = _CHAIN_START.match(skel, j)
        if m:
            end = m.end()
            k = end
            while k < n and skel[k].isspace():
                k += 1
            if k < n and skel[k] == "(":
                c = _match_fwd(skel, k)
                if c >= 0:
                    end = c + 1
        else:
            m2 = _NUM.match(skel, j)
            if not m2:
                return None
            end = m2.end()
    while True:
        m = _CAST_AFTER.match(skel, end)
        if not m:
            break
        end = m.end()
    return start, end


def _ma_strefe(skel, s, e):
    return bool(_TZ_MARK.search(skel[s:e]))


def _w_funkcji_timezone(skel, pos):
    depth = 0
    for j in range(pos - 1, -1, -1):
        ch = skel[j]
        if ch == ")":
            depth += 1
        elif ch == "(":
            if depth == 0:
                m = re.search(r"(%s)\s*$" % _IDENT, skel[:j])
                if m and m.group(1).lower() == "timezone":
                    return True
            else:
                depth -= 1
    return False


def _strefa_jawna(skel, s, e):
    """Czy wyrażenie [s,e) ma w obrębie siebie jawną strefę (AT TIME ZONE / timezone())."""
    return bool(_TZ_AFTER.match(skel, e)) or _w_funkcji_timezone(skel, s) or _ma_strefe(skel, s, e)


_COLREF = re.compile(r"(?<![\w$.:?])(?:(%s)\s*\.\s*)?(%s)(?![\w$])(?!\s*[.(])" % (_IDENT, _IDENT))
_ALIAS_RE = re.compile(r"\b(?:from|join|update|into)\s+(?:only\s+)?(?:%s\s*\.\s*)?(%s)"
                       r"(?:\s+(?:as\s+)?(%s))?" % (_IDENT, _IDENT, _IDENT), re.I)

_TIME_RE = re.compile(
    r"\b(?:now|current_date|current_timestamp|current_time|localtimestamp|localtime|date_trunc|"
    r"date_part|extract|age|timezone|make_date|make_timestamp)\b|\bdate\s*\(|"
    r"::\s*(?:date|timestamp|timestamptz|time)\b|\bat\s+time\s+zone\b|\binterval\b", re.I)

_NOW_RE = re.compile(r"\bnow\s*\(\s*\)|\bcurrent_timestamp\b|\btransaction_timestamp\s*\(\s*\)"
                     r"|\bstatement_timestamp\s*\(\s*\)|\bclock_timestamp\s*\(\s*\)", re.I)
_CUR_DATE_RE = re.compile(
    r"\bcurrent_date\b|\blocaltimestamp\b|\bnow\s*\(\s*\)\s*::\s*date\b|"
    r"\bcurrent_timestamp\s*::\s*date\b|"
    r"\bcast\s*\(\s*(?:now\s*\(\s*\)|current_timestamp|localtimestamp)\s+as\s+date\s*\)", re.I)
_NOWISH = re.compile(r"\bcurrent_date\b|\bnow\s*\(|\bcurrent_timestamp\b|\blocaltimestamp\b|\bcurrent_time\b", re.I)
_INTERVAL_TAIL = re.compile(r"\s*[+-]\s*interval\s*'[^']*'", re.I)
_OP_BEFORE = re.compile(r"(<=|>=|<>|!=|=|<|>|-)\s*$")
_OP_AFTER = re.compile(r"\s*(<=|>=|<>|!=|=|<|>|-)")
_BETWEEN_BEFORE = re.compile(
    r"((?:%s\s*\.\s*)?%s)\s+(?:not\s+)?between\s+(?:[^()]{0,80}?\s+and\s+)?$" % (_IDENT, _IDENT), re.I)

_LIT = (r"(?:(?:date|timestamp|timestamptz)\s+)?'(\d{4}-\d{2}-\d{2}(?:[ T]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?)?)'"
        r"(?:\s*::\s*(?:date|timestamp|timestamptz))?")
_CHAIN_PATTERN = r"(?:%s\s*\.\s*)?%s" % (_IDENT, _IDENT)
_COL = r"(%s)" % _CHAIN_PATTERN
_CMP = r"(?:<=|>=|<>|!=|=|<|>)"
_LIT_FWD = re.compile(_COL + r"\s*" + _CMP + r"\s*" + _LIT, re.I)
_LIT_REV = re.compile(_LIT + r"\s*" + _CMP + r"\s*" + _COL + r"(?![\w$])(?!\s*[.(])", re.I)
_LIT_BETWEEN = re.compile(_COL + r"\s+(?:not\s+)?between\s+" + _LIT + r"\s+and\s+" + _LIT, re.I)
_OFFSET_LIT = re.compile(r"'[+-]0[12](?::00)?'")
_INTERVAL_HOURS = re.compile(r"([+-])\s*interval\s*'\s*([12])\s*hours?\s*'", re.I)


class KontekstSql:
    """Jedno zapytanie SQL: kod bez komentarzy, szkielet, aliasy tabel, typy kolumn."""

    def __init__(self, sql, cfg):
        self.sql = sql
        self.code, self.skel = blank_sql(sql)
        self.cfg = cfg
        self.aliases = {}
        self.tabele = []
        for m in _ALIAS_RE.finditer(self.skel):
            tab = m.group(1).lower()
            if tab in SQL_KEYWORDS:
                continue
            if tab not in self.tabele:
                self.tabele.append(tab)
            self.aliases[tab] = tab
            al = m.group(2)
            if al and al.lower() not in SQL_KEYWORDS:
                self.aliases[al.lower()] = tab
        self.maska = _maskuj_literaly(self.code, sql_single=True)
        self.trafione = set()
        if cfg.tz or cfg.local:
            for m in _COLREF.finditer(self.skel):
                if m.group(2).lower() in SQL_KEYWORDS:
                    continue
                q = m.group(1)
                tabele = [self.aliases.get(q.lower(), q.lower())] if q else self.tabele
                self.trafione.update(cfg.dopasowania(tabele, m.group(2)))

    def rodzaj(self, kwal, nazwa):
        if nazwa.lower() in SQL_KEYWORDS:
            return None, False
        if kwal:
            q = kwal.lower()
            tabele = [self.aliases.get(q, q)]
        else:
            tabele = self.tabele
        return self.cfg.classify(tabele, nazwa)

    def kolumny(self, s, e):
        """Kolumny czasu w zakresie [s,e): lista (rodzaj, pewne, nazwa)."""
        wynik = []
        for m in _COLREF.finditer(self.skel, s, e):
            rodzaj, pewne = self.rodzaj(m.group(1), m.group(2))
            if rodzaj:
                wynik.append((rodzaj, pewne, m.group(2)))
        return wynik

    def parametr_do_kolumny_numeru(self):
        """Czy któryś parametr (?) jest zapisywany/porównywany z kolumną o nazwie numeru dokumentu."""
        for m in re.finditer(r"(%s)\s*(?:=|like|ilike)\s*\?" % _CHAIN_PATTERN, self.skel, re.I):
            if nazwa_identyfikatora([m.group(1).split(".")[-1]]):
                return True
        for m in re.finditer(r"\?", self.skel):
            kol = _kolumna_insertu(self.skel, m.start())
            if kol and nazwa_identyfikatora([kol]):
                return True
        return False

    def czy_sql_z_czasem(self):
        if _TIME_RE.search(self.skel):
            return True
        return bool(self.kolumny(0, len(self.skel)))

    def ma_pewna_kolumne(self):
        return any(p for _, p, _ in self.kolumny(0, len(self.skel)))

    def snippet(self, s, e):
        lo = max(0, s - 40)
        hi = min(len(self.maska), e + 40)
        while 0 < lo < s and not self.maska[lo - 1].isspace():
            lo += 1
        while e < hi < len(self.maska) and not self.maska[hi].isspace():
            hi -= 1
        fr = _ws(self.maska[lo:hi])
        fr = re.sub(r"\?{2,}", "?", fr)
        return _przytnij(fr)


def _przytnij(tekst):
    if len(tekst) > MAKS_FRAGMENT:
        return tekst[:MAKS_FRAGMENT - 3] + "..."
    return tekst


_KEEP = re.compile(
    r"""^(?:\d{4}-\d{2}-\d{2}(?:[ T][\d:.]+)?|[+-]\d{2}(?::?\d{2})?|\d+\s*(?:seconds?|minutes?|hours?|days?|weeks?|months?|years?)
    |(?:year|quarter|month|week|day|hour|minute|second|dow|doy|epoch|isodow|cron|interval|date|utc)
    |[A-Za-z_]+/[A-Za-z_]+
    |(?:[%A-Za-z]|[\s/_.:\-])*%(?:[%A-Za-z]|[\s/_.:\-])*
    |[YMDHSyAm0-9/\-:.\s]*(?:YY|MM|DD|HH)[YMDHSAm0-9/\-:.\s]*)$""", re.I | re.X)


def _maskuj_literaly(tekst, sql_single=False):
    """Maskuje wartości literałów tekstowych (``'?'``), zostawia daty/strefy/jednostki.

    Długość tekstu zostaje zachowana (indeksy pasują do oryginału).
    """
    wzor = r"'((?:[^']|'')*)'" if sql_single else r"""(['"])((?:\\.|(?!\1).)*?)\1"""

    def podmien(m):
        if sql_single:
            tresc, calosc = m.group(1), m.group(0)
        else:
            tresc, calosc = m.group(2), m.group(0)
        if _KEEP.match(tresc.strip()) or tresc == "":
            return calosc
        q = calosc[0]
        return q + "?" * (len(calosc) - 2) + q

    return re.sub(wzor, podmien, tekst, flags=re.S)


# --------------------------------------------------------------------------- detektory SQL

def _usun_zawarte(surowe):
    """Usuwa wyniki tej samej kategorii zawarte w szerszym wyniku."""
    wynik = []
    for r in surowe:
        zawarty = False
        for q in surowe:
            if q is r or q[0] != r[0]:
                continue
            if q[1] <= r[1] and r[2] <= q[2] and (q[1], q[2]) != (r[1], r[2]):
                zawarty = True
                break
        if not zawarty and (r[0], r[1], r[2]) not in [(w[0], w[1], w[2]) for w in wynik]:
            wynik.append(r)
    return wynik


def _pewnosc(kolumny_rodzaj):
    return "likely" if any(p for _, p, _ in kolumny_rodzaj) else "uncertain"


_NAZWA_ID = re.compile(r"numer|(?<![a-z])nr(?![a-z])|number|seq|seri[ae]|prefix|numeracja|invoice|order_no", re.I)
_PREFIKS_DOK = re.compile(r"[A-Z]{1,8}[/\-_.]")


def nazwa_identyfikatora(nazwy):
    return any(_NAZWA_ID.search(n or "") for n in nazwy)


def _kolumna_insertu(skel, pos):
    """Nazwa kolumny, do której trafia wartość z pozycji ``pos`` w INSERT ... VALUES (...)."""
    for m in re.finditer(r"\binsert\s+into\s+[\w$.\"]+\s*\(([^)]*)\)\s*values\s*\(", skel, re.I):
        o = m.end() - 1
        c = _match_fwd(skel, o)
        if c < 0 or not (o < pos < c):
            continue
        kol = [x.strip().strip('"').lower() for x in m.group(1).split(",")]
        for i, (a, b) in enumerate(_split_top(skel, o + 1, c)):
            if a <= pos < b:
                return kol[i] if i < len(kol) else None
    return None


def _kolumna_zapisu(skel, poz):
    """Kolumna, do której zapisywana jest wartość z pozycji ``poz`` (INSERT ... VALUES lub SET kol = ...)."""
    kol = _kolumna_insertu(skel, poz)
    if kol:
        return kol
    pre = skel[:poz]
    ostatni_set = max((m.start() for m in re.finditer(r"\bset\b", pre, re.I)), default=-1)
    ostatni_where = max((m.start() for m in re.finditer(r"\bwhere\b", pre, re.I)), default=-1)
    if ostatni_set < 0 or ostatni_set < ostatni_where:
        return None
    m = re.search(r"(%s)\s*=\s*(?:\(\s*)*$" % _CHAIN_PATTERN, pre)
    if m and not pre[:m.start()].rstrip().endswith(("<", ">", "!")):
        return m.group(1).split(".")[-1].lower()
    return None


def _numeracja_sql(skel, code, start, koniec, nazwy):
    """Czy wynik to_char(teraz, ...) WCHODZI W IDENTYFIKATOR dokumentu."""
    if nazwa_identyfikatora(nazwy):
        return True
    przed = re.search(r"'([^']*)'\s*(?:\|\||,)\s*$", code[:start])
    if przed and _PREFIKS_DOK.match(przed.group(1)):
        return True
    po = re.match(r"\s*\|\|\s*'([^']*)'", code[koniec:])
    if po and _PREFIKS_DOK.match(po.group(1)):
        return True
    lewa = re.search(r"(%s)\s*(?:=|like|ilike)\s*(?:'[^']*'\s*\|\|\s*)*$" % _CHAIN_PATTERN, skel[:start], re.I)
    if lewa and nazwa_identyfikatora([lewa.group(1).split(".")[-1]]):
        return True
    prawa = re.match(r"\s*(?:\|\|\s*'[^']*'\s*)*(?:=|like|ilike)\s*(%s)" % _CHAIN_PATTERN, skel[koniec:], re.I)
    if prawa and nazwa_identyfikatora([prawa.group(1).split(".")[-1]]):
        return True
    kol = _kolumna_insertu(skel, start)
    return bool(kol and nazwa_identyfikatora([kol]))


def analizuj_sql(sql, cfg, nazwy=()):
    """-> (kontekst, lista surowych wyników (kategoria, start, koniec, pewnosc)).

    ``nazwy``: nazwy zmiennych/funkcji wokół wywołania (podpowiedź dla numeracji dokumentów).
    """
    ctx = KontekstSql(sql, cfg)
    ctx.numeracja_zdegradowane = 0
    skel, code = ctx.skel, ctx.code
    surowe = []
    spany_numeracji = []

    # --- numbering_by_date: to_char(<teraz>, 'YYYY/MM')
    for m in re.finditer(r"\bto_char\s*\(", skel, re.I):
        o = m.end() - 1
        c = _match_fwd(skel, o)
        if c < 0:
            continue
        arg = _split_top(skel, o + 1, c)
        if len(arg) < 2:
            continue
        a0, a1 = arg[0], arg[1]
        pierwszy = skel[a0[0]:a0[1]]
        fmt = code[a1[0]:a1[1]]
        if _NOWISH.search(pierwszy) and not _TZ_MARK.search(pierwszy) \
                and re.search(r"y{2,4}|mm|month|mon", fmt, re.I):
            if _numeracja_sql(skel, code, m.start(), c + 1, nazwy):
                surowe.append(("numbering_by_date", m.start(), c + 1, "likely"))
                spany_numeracji.append((m.start(), c + 1))
            else:
                ctx.numeracja_zdegradowane += 1
                if not _CUR_DATE_RE.search(pierwszy):  # NOW()/CURRENT_TIMESTAMP: data liczona w UTC
                    surowe.append(("sql_current_date_utc", m.start(), c + 1, "likely"))

    def w_numeracji(p):
        return any(a <= p < b for a, b in spany_numeracji)

    # --- sql_current_date_utc
    spany_data = []
    for m in _CUR_DATE_RE.finditer(skel):
        s, e = m.start(), m.end()
        spany_data.append((s, e))
        if w_numeracji(s) or _strefa_jawna(skel, s, e):
            continue
        surowe.append(("sql_current_date_utc", s, e, "likely"))

    # --- sql_local_vs_now
    for m in _NOW_RE.finditer(skel):
        s, e = m.start(), m.end()
        if any(a <= s < b for a, b in spany_data) or w_numeracji(s):
            continue
        if _strefa_jawna(skel, s, e):
            continue
        # rozszerz o "+/- interval '...'" i otaczające nawiasy (nie wywołanie funkcji)
        while True:
            t = _INTERVAL_TAIL.match(skel, e)
            if not t:
                break
            e = t.end()
        while True:
            pre = skel[:s].rstrip()
            post_m = re.compile(r"\s*\)").match(skel, e)
            if pre.endswith("(") and post_m:
                fm = re.search(r"(%s)\s*$" % _IDENT, pre[:-1])
                if fm and fm.group(1).lower() not in SQL_KEYWORDS:
                    break
                s = len(pre) - 1
                e = post_m.end()
            else:
                break
        zapis = _kolumna_zapisu(skel, m.start())
        if zapis:
            rodzaj, pewne = ctx.rodzaj(None, zapis)
            if rodzaj == "local":
                surowe.append(("sql_utc_into_local_column", m.start(), e, "likely" if pewne else "uncertain"))
            continue
        kolumny = []
        pre = skel[:s]
        mo = _OP_BEFORE.search(pre)
        if mo:
            op = operand_before(skel, mo.start())
            if op:
                kolumny += ctx.kolumny(op[0], op[1])
        mb = _BETWEEN_BEFORE.search(pre)
        if mb:
            kolumny += ctx.kolumny(mb.start(1), mb.end(1))
        ma = _OP_AFTER.match(skel, e)
        if ma:
            op = operand_after(skel, ma.end())
            if op:
                kolumny += ctx.kolumny(op[0], op[1])
        lokalne = [k for k in kolumny if k[0] == "local"]
        if lokalne:
            surowe.append(("sql_local_vs_now", m.start(), e, _pewnosc(lokalne)))

    # --- sql_date_trunc_utc
    def sprawdz_systemowe(s_op, e_op, s_all, e_all):
        if _ma_strefe(skel, s_op, e_op):
            return
        sys_kol = [k for k in ctx.kolumny(s_op, e_op) if k[0] == "tz"]
        if sys_kol:
            surowe.append(("sql_date_trunc_utc", s_all, e_all, _pewnosc(sys_kol)))

    for m in re.finditer(r"\bdate_trunc\s*\(", skel, re.I):
        o = m.end() - 1
        c = _match_fwd(skel, o)
        if c < 0:
            continue
        arg = _split_top(skel, o + 1, c)
        if len(arg) == 2:
            sprawdz_systemowe(arg[1][0], arg[1][1], m.start(), c + 1)
    for m in re.finditer(r"::\s*date\b", skel, re.I):
        op = operand_before(skel, m.start())
        if op:
            sprawdz_systemowe(op[0], op[1], op[0], m.end())
    for m in re.finditer(r"\bcast\s*\(", skel, re.I):
        o = m.end() - 1
        c = _match_fwd(skel, o)
        if c < 0:
            continue
        mi = re.search(r"\bas\s+date\s*$", skel[o + 1:c], re.I)
        if mi:
            sprawdz_systemowe(o + 1, o + 1 + mi.start(), m.start(), c + 1)
    for m in re.finditer(r"(?<![\w$.])date\s*\(", skel, re.I):
        o = m.end() - 1
        c = _match_fwd(skel, o)
        if c >= 0:
            sprawdz_systemowe(o + 1, c, m.start(), c + 1)
    for m in re.finditer(r"\bextract\s*\(\s*(\w+)\s+from\b", skel, re.I):
        o = skel.find("(", m.start())
        c = _match_fwd(skel, o)
        if c < 0 or m.group(1).lower() == "epoch":
            continue
        sprawdz_systemowe(m.end(), c, m.start(), c + 1)
    for m in re.finditer(r"\bdate_part\s*\(", skel, re.I):
        o = m.end() - 1
        c = _match_fwd(skel, o)
        if c < 0:
            continue
        arg = _split_top(skel, o + 1, c)
        if len(arg) == 2 and "epoch" not in code[arg[0][0]:arg[0][1]].lower():
            sprawdz_systemowe(arg[1][0], arg[1][1], m.start(), c + 1)

    # --- sql_literal_boundary
    def po_literale_strefa(e):
        return bool(re.compile(r"\s*at\s+time\s+zone\b", re.I).match(code, e))

    def kolumna_systemowa(tekst):
        if "." in tekst:
            kw, nz = [x.strip() for x in tekst.split(".", 1)]
        else:
            kw, nz = None, tekst.strip()
        rodzaj, pewne = ctx.rodzaj(kw, nz)
        return (rodzaj, pewne, nz) if rodzaj == "tz" else None

    for rx in (_LIT_FWD, _LIT_REV, _LIT_BETWEEN):
        for m in rx.finditer(code):
            if rx is _LIT_REV:
                kol_txt = m.group(m.lastindex)
            else:
                kol_txt = m.group(1)
            k = kolumna_systemowa(kol_txt)
            if not k or po_literale_strefa(m.end()):
                continue
            surowe.append(("sql_literal_boundary", m.start(), m.end(), _pewnosc([k])))

    # --- sql_fixed_offset
    for m in _OFFSET_LIT.finditer(code):
        surowe.append(("sql_fixed_offset", m.start(), m.end(), "likely"))
    for m in _INTERVAL_HOURS.finditer(code):
        lewy = operand_before(skel, m.start())
        if not lewy:
            continue
        # arytmetyka na samym NOW() (także po AT TIME ZONE) to okno czasowe, nie przesunięcie strefy;
        # flagujemy tylko interwał dodany do KOLUMNY czasu
        if not ctx.kolumny(lewy[0], lewy[1]):
            continue
        if _ma_strefe(skel, lewy[0], lewy[1]) or _TZ_AFTER.match(skel, m.end()):
            surowe.append(("sql_fixed_offset", lewy[0], m.end(), "likely"))
        else:
            surowe.append(("sql_fixed_offset", lewy[0], m.end(), "uncertain"))

    kategorie = OrderedDict()
    for r in surowe:
        kategorie.setdefault(r[0], []).append(r)
    wynik = []
    for lista in kategorie.values():
        wynik.extend(_usun_zawarte(lista))
    wynik.sort(key=lambda r: (r[1], r[2], r[0]))
    return ctx, wynik


# --------------------------------------------------------------------------- analiza Pythona

NAZWY_SQL = frozenset(["query_one", "query_all", "execute", "execute_return", "executemany"])
ATRYBUTY_SQL = frozenset(["execute", "executemany", "query_one", "query_all", "execute_return"])

_TIME_CALLS = {
    "datetime.datetime.now": "now",
    "datetime.datetime.utcnow": "utcnow",
    "datetime.datetime.today": "today",
    "datetime.date.today": "today",
    "datetime.datetime.utcfromtimestamp": "utcfromtimestamp",
}

_SQL_ZACZYNA = re.compile(r"[\s(]*([A-Za-z]+)")
_CRON_KW = frozenset(["hour", "day", "day_of_week", "week", "month", "year"])
_NAZWA_NUMERU = re.compile(r"numer|number|nr(?![a-z])|(?<![a-z])no(?![a-z])|_no\b|num|doc|zlec|order|invoice|faktur|ident",
                           re.I)


@dataclass
class InfoCzas:
    rodzaj: str
    naiwny: bool
    syntetyczny: bool = False  # źródło czasu odtworzone z SQL (SELECT CURRENT_DATE), nie wywołanie Pythona


class Zakres:
    def __init__(self, qual, env=None, deps=None, taint=None, cls=None, klasa=False):
        self.qual = qual
        self.env = dict(env) if env else {}
        self.deps = dict(deps) if deps else {}
        self.getnames = set()
        self.taint = set(taint) if taint else set()
        self.cls = cls
        self.klasa = klasa


def _nazwa_koncowa(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _kropkowana(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        baza = _kropkowana(node.value)
        return baza + "." + node.attr if baza else None
    return None


def _kw(call, nazwa):
    for k in call.keywords:
        if k.arg == nazwa:
            return k.value
    return None


def _z_parametru(node):
    """Wyrażenie czyta wartość z żądania/słownika: ``x.get(...)`` lub ``x[...]``."""
    return any((isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "get")
               or isinstance(n, ast.Subscript) for n in ast.walk(node))


def _stala_tekst(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _klucz_subscript(node):
    sl = node.slice
    if type(sl).__name__ == "Index":
        sl = sl.value
    return _stala_tekst(sl)


class AnalizatorModulu:
    def __init__(self, tekst, plik, cfg, plik_testowy=False):
        self.plik = plik
        self.cfg = cfg
        self.plik_testowy = plik_testowy
        self.tekst = tekst.replace("\r\n", "\n").replace("\r", "\n")
        self.linie = self.tekst.split("\n")
        self.tree = ast.parse(self.tekst)
        self.wyniki = []
        self._widziane = set()
        self.sql_wywolan = 0
        self.sql_czas = 0
        self.importy = {}
        self.czas = {}
        self.czas_rej = []
        self._czas_ids = set()
        self.uzycie_sql = {}
        self.uzycie_db = {}
        self.zuzyte = set()
        self.bez_cron = set()
        self.numeracja_zdegradowane = 0
        self.trafione = set()
        self.domyslne = set()
        self._num_linie = set()
        self.wyniki_ostrzezenia = []
        self._przygotuj()

    # ----- przygotowanie
    def _przygotuj(self):
        for n in ast.walk(self.tree):
            if isinstance(n, ast.Import):
                for a in n.names:
                    self.importy[(a.asname or a.name.split(".")[0])] = a.name if a.asname else a.name.split(".")[0]
            elif isinstance(n, ast.ImportFrom) and n.module and not n.level:
                for a in n.names:
                    if a.name != "*":
                        self.importy[a.asname or a.name] = n.module + "." + a.name
        self.rodzic = {}
        for p in ast.walk(self.tree):
            for ch in ast.iter_child_nodes(p):
                self.rodzic[id(ch)] = p
        self.func_ids = set(id(c.func) for c in ast.walk(self.tree) if isinstance(c, ast.Call))
        for n in ast.walk(self.tree):
            if isinstance(n, ast.Call):
                rodzaj = _TIME_CALLS.get(self.kanon(n.func) or "")
                if rodzaj:
                    self.czas[id(n)] = InfoCzas(rodzaj, self._naiwny(n, rodzaj))
        self.tz_skonfigurowana = self._czy_tz_skonfigurowana()

    def kanon(self, node):
        if isinstance(node, ast.Name):
            return self.importy.get(node.id, node.id)
        if isinstance(node, ast.Attribute):
            baza = self.kanon(node.value)
            return baza + "." + node.attr if baza else None
        return None

    @staticmethod
    def _naiwny(call, rodzaj):
        if rodzaj != "now":
            return True
        arg = call.args[0] if call.args else _kw(call, "tz")
        if arg is None:
            arg = _kw(call, "tzinfo")
        if arg is None:
            return True
        return isinstance(arg, ast.Constant) and arg.value is None

    def _czy_tz_skonfigurowana(self):
        for n in ast.walk(self.tree):
            if isinstance(n, ast.Call) and _kw(n, "timezone") is not None:
                nm = _nazwa_koncowa(n.func) or ""
                if nm.endswith("Scheduler") or nm in ("configure", "Celery", "update", "config_from_object"):
                    return True
            elif isinstance(n, ast.Assign):
                for t in n.targets:
                    nm = t.attr if isinstance(t, ast.Attribute) else getattr(t, "id", "")
                    if nm in ("timezone", "CELERY_TIMEZONE", "SCHEDULER_TIMEZONE"):
                        return True
        return False

    def segment(self, node):
        try:
            l1, l2 = node.lineno - 1, node.end_lineno - 1
            c1, c2 = node.col_offset, node.end_col_offset
            if l1 == l2:
                tekst = self.linie[l1].encode("utf-8")[c1:c2].decode("utf-8", "replace")
            else:
                pierwsza = self.linie[l1].encode("utf-8")[c1:].decode("utf-8", "replace")
                ostatnia = self.linie[l2].encode("utf-8")[:c2].decode("utf-8", "replace")
                tekst = "\n".join([pierwsza] + self.linie[l1 + 1:l2] + [ostatnia])
        except Exception:
            return type(node).__name__
        return _przytnij(_ws(tekst))

    def dodaj(self, kategoria, qual, linia, helper, fragment, pewnosc, waznosc=None, dlaczego_extra=""):
        waz, dlaczego, propozycja = KATEGORIE[kategoria]
        waz = waznosc or waz
        if dlaczego_extra:
            dlaczego = dlaczego + " " + dlaczego_extra
        fragment = _przytnij(_ws(fragment))
        k = (qual, linia, kategoria, normalizuj(fragment))
        if k in self._widziane:
            return
        self._widziane.add(k)
        self.wyniki.append(Wynik(self.plik, qual, linia, helper, kategoria, waz, pewnosc,
                                 fragment, dlaczego, propozycja))

    # ----- przejście po drzewie
    def uruchom(self):
        modul = Zakres("<module>")
        for st in self.tree.body:  # stałe modułu mogą być zdefiniowane za funkcją, która ich używa
            if isinstance(st, (ast.Assign, ast.AnnAssign)):
                self._bezpiecznie(self.on_assign, st, modul)
        self.visit_body(self.tree.body, modul)
        self.zakoncz()

    def _bezpiecznie(self, fn, *args):
        try:
            fn(*args)
        except Exception as exc:  # nigdy nie wywalaj się na dziwnym kodzie
            self.wyniki_ostrzezenia.append("%s: pominięto konstrukcję (%s)" % (self.plik, type(exc).__name__))

    def visit_body(self, stmts, sc):
        for st in stmts:
            self._bezpiecznie(self.visit_stmt, st, sc)

    def dziecko(self, sc, nazwa, klasa=False):
        qual = nazwa if sc.qual == "<module>" else sc.qual + "." + nazwa
        return Zakres(qual, sc.env, sc.deps, sc.taint, nazwa if klasa else sc.cls, klasa)

    def visit_stmt(self, st, sc):
        if isinstance(st, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for d in st.decorator_list:
                self.scan(d, sc)
            for d in list(st.args.defaults) + [k for k in st.args.kw_defaults if k is not None]:
                self.scan(d, sc)
            self.visit_body(st.body, self.dziecko(sc, st.name))
        elif isinstance(st, ast.ClassDef):
            for d in st.decorator_list + st.bases:
                self.scan(d, sc)
            self.visit_body(st.body, self.dziecko(sc, st.name, klasa=True))
        elif isinstance(st, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
            self.on_assign(st, sc)
            self.hint = self._nazwy_celow(st)
            self.scan(st, sc)
            self.hint = []
        elif isinstance(st, ast.If):
            self.on_if(st, sc)
            for _, wartosc in ast.iter_fields(st):
                for it in (wartosc if isinstance(wartosc, list) else [wartosc]):
                    self.visit_item(it, sc)
        elif isinstance(st, ast.Expr):
            self.on_expr_stmt(st, sc)
            self.scan(st, sc)
        elif isinstance(st, (ast.For, ast.AsyncFor)):
            self.scan(st.iter, sc)
            self.on_for(st, sc)
            self.visit_body(st.body, sc)
            self.visit_body(st.orelse, sc)
        else:
            for _, wartosc in ast.iter_fields(st):
                if isinstance(wartosc, list):
                    for it in wartosc:
                        self.visit_item(it, sc)
                elif isinstance(wartosc, ast.AST):
                    self.visit_item(wartosc, sc)

    hint = []

    def visit_item(self, it, sc):
        if isinstance(it, ast.stmt):
            self._bezpiecznie(self.visit_stmt, it, sc)
        elif isinstance(it, ast.ExceptHandler):
            if it.type is not None:
                self.scan(it.type, sc)
            self.visit_body(it.body, sc)
        elif isinstance(it, ast.AST):
            self.scan(it, sc)

    @staticmethod
    def _nazwy_celow(st):
        cele = st.targets if isinstance(st, ast.Assign) else [st.target]
        return [n.id.lower() for c in cele for n in ast.walk(c) if isinstance(n, ast.Name)]

    # ----- zmienne: SQL, zależności czasowe, "skażenie" wynikami bazy
    def sql_value(self, node, sc):
        if isinstance(node, (ast.List, ast.Tuple)):
            elem = []
            for e in node.elts:
                r = self.sql_text(e, sc)
                if r:
                    elem.append(r)
            return ("l", elem)
        r = self.sql_text(node, sc)
        return ("s", r[0], r[1]) if r else None

    def sql_text(self, node, sc, glebia=0):
        """Odtwarza tekst SQL z wyrażenia. -> (tekst, linia) albo None."""
        if glebia > 60:
            return None
        g = glebia + 1
        if isinstance(node, ast.Constant):
            return (node.value, node.lineno) if isinstance(node.value, str) else None
        if isinstance(node, ast.JoinedStr):
            czesci = []
            for v in node.values:
                if isinstance(v, ast.Constant):
                    czesci.append(str(v.value))
                elif isinstance(v, ast.FormattedValue):
                    r = self.sql_text(v.value, sc, g)
                    czesci.append(r[0] if r else " ")
            return ("".join(czesci), node.lineno)
        if isinstance(node, ast.Name):
            w = sc.env.get(node.id)
            return (w[1], w[2]) if w and w[0] == "s" else None
        if isinstance(node, ast.Attribute):
            if isinstance(node.value, ast.Name):
                baza = sc.cls if node.value.id in ("self", "cls") else node.value.id
                w = sc.env.get("%s.%s" % (baza, node.attr)) if baza else None
                if w and w[0] == "s":
                    return (w[1], w[2])
            return None
        if isinstance(node, ast.BinOp):
            if isinstance(node.op, ast.Add):
                l, r = self.sql_text(node.left, sc, g), self.sql_text(node.right, sc, g)
                if l and r:
                    return (l[0] + r[0], l[1])
                return l or r
            if isinstance(node.op, ast.Mod):
                return self.sql_text(node.left, sc, g)
            return None
        if isinstance(node, ast.IfExp):
            a, b = self.sql_text(node.body, sc, g), self.sql_text(node.orelse, sc, g)
            if a and b:
                return (a[0] + "\n" + b[0], a[1])
            return a or b
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            nm = node.func.attr
            if nm == "format":
                r = self.sql_text(node.func.value, sc, g)
                return (re.sub(r"\{[^{}]*\}", " ", r[0]), r[1]) if r else None
            if nm in ("strip", "lstrip", "rstrip", "replace", "lower", "upper"):
                return self.sql_text(node.func.value, sc, g)
            if nm == "join" and node.args:
                sep = self.sql_text(node.func.value, sc, g)
                elem = self._elementy(node.args[0], sc, g)
                if sep is not None and elem:
                    return (sep[0].join(t for t, _ in elem), elem[0][1])
            return None
        if isinstance(node, ast.Call) and (_nazwa_koncowa(node.func) == "dedent") and node.args:
            return self.sql_text(node.args[0], sc, g)
        return None

    def _elementy(self, node, sc, g):
        if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
            wynik = []
            for e in node.elts:
                r = self.sql_text(e, sc, g)
                if r:
                    wynik.append(r)
            return wynik
        if isinstance(node, ast.Name):
            w = sc.env.get(node.id)
            if w and w[0] == "l":
                return list(w[1])
        return []

    def rejestruj_zrodlo_sql(self, call, sc):
        """``SELECT CURRENT_DATE`` / ``SELECT now()`` bez strefy: wynik zapytania jest naiwnym "teraz"."""
        if id(call) in self.czas:
            return
        arg = call.args[0] if call.args else _kw(call, "sql") or _kw(call, "query")
        res = self.sql_text(arg, sc) if arg is not None else None
        if not res:
            return
        _, skel = blank_sql(res[0])
        if not re.match(r"[\s(]*select\b", skel, re.I):
            return
        od = re.search(r"\bfrom\b", skel, re.I)
        granica = od.start() if od else len(skel)
        for rx in (_CUR_DATE_RE, _NOW_RE):
            for m in rx.finditer(skel, 0, granica):
                if not _strefa_jawna(skel, m.start(), m.end()):
                    self.czas[id(call)] = InfoCzas("sqlnow", True, True)
                    return

    def czasy_w(self, wyr, sc):
        ids = set()
        for n in ast.walk(wyr):
            if isinstance(n, ast.Call) and id(n) in self.czas:
                ids.add(id(n))
            elif isinstance(n, ast.Name) and n.id in sc.deps:
                ids |= sc.deps[n.id]
        return ids

    def skazone(self, wyr, sc):
        for n in ast.walk(wyr):
            if isinstance(n, ast.Name) and n.id in sc.taint:
                return True
            if isinstance(n, ast.Call) and self.helper_sql(n):
                return True
        return False

    def on_assign(self, st, sc):
        if isinstance(st, ast.Assign):
            cele, wartosc, aug = st.targets, st.value, False
        elif isinstance(st, ast.AugAssign):
            cele, wartosc, aug = [st.target], st.value, isinstance(st.op, ast.Add)
        else:
            cele, wartosc, aug = [st.target], st.value, False
        if wartosc is None:
            return
        for n in ast.walk(wartosc):
            if isinstance(n, ast.Call) and self.helper_sql(n):
                self.rejestruj_zrodlo_sql(n, sc)
        nazwy = [n.id for c in cele for n in ast.walk(c) if isinstance(n, ast.Name)]
        proste = [c.id for c in cele if isinstance(c, ast.Name)]
        wart = self.sql_value(wartosc, sc)
        for nm in proste:
            kluczne = [nm] + (["%s.%s" % (sc.cls, nm)] if sc.klasa and sc.cls else [])
            for k in kluczne:
                if aug:
                    stary = sc.env.get(k)
                    if wart and wart[0] == "s":
                        if stary and stary[0] == "s":
                            sc.env[k] = ("s", stary[1] + wart[1], stary[2])
                        else:
                            sc.env[k] = wart
                elif wart:
                    sc.env[k] = wart
                else:
                    sc.env.pop(k, None)
        czasy = self.czasy_w(wartosc, sc)
        skaz = self.skazone(wartosc, sc)
        if _z_parametru(wartosc) and not czasy:
            sc.getnames.update(proste)
        for n in ast.walk(wartosc):  # ``a.get(..) or <teraz>`` oraz ``a[..] if .. else <teraz>``
            if isinstance(n, ast.BoolOp) and isinstance(n.op, ast.Or):
                for i, v in enumerate(n.values[1:], 1):
                    if any(_z_parametru(w) for w in n.values[:i]):
                        self.domyslne |= self.czasy_w(v, sc)
            elif isinstance(n, ast.IfExp):
                if _z_parametru(n.body):
                    self.domyslne |= self.czasy_w(n.orelse, sc)
                if _z_parametru(n.orelse):
                    self.domyslne |= self.czasy_w(n.body, sc)
        for nm in nazwy:
            if aug:
                sc.deps[nm] = sc.deps.get(nm, set()) | czasy
            elif czasy:
                sc.deps[nm] = set(czasy)
            else:
                sc.deps.pop(nm, None)
            if skaz:
                sc.taint.add(nm)
            elif not aug:
                sc.taint.discard(nm)

    def on_if(self, st, sc):
        """``if not x: x = <naiwne teraz>`` gdy x pochodzi z ``.get(...)`` - wartość domyślna parametru."""
        puste, niepuste = set(), set()
        for t in (st.test.values if isinstance(st.test, ast.BoolOp) else [st.test]):
            if isinstance(t, ast.UnaryOp) and isinstance(t.op, ast.Not) and isinstance(t.operand, ast.Name):
                puste.add(t.operand.id)
            elif isinstance(t, ast.Compare) and isinstance(t.left, ast.Name) and len(t.comparators) == 1 \
                    and isinstance(t.comparators[0], ast.Constant) and t.comparators[0].value in (None, ""):
                if isinstance(t.ops[0], (ast.Is, ast.Eq)):
                    puste.add(t.left.id)
                else:
                    niepuste.add(t.left.id)
            elif isinstance(t, ast.Name):
                niepuste.add(t.id)
        for nazwy, galaz in ((puste, st.body), (niepuste, st.orelse)):
            for nm in nazwy & sc.getnames:
                for b in galaz:
                    for a in ast.walk(b):
                        if isinstance(a, ast.Assign) and any(isinstance(x, ast.Name) and x.id == nm for x in a.targets):
                            self.domyslne |= self.czasy_w(a.value, sc)

    def on_expr_stmt(self, st, sc):
        v = st.value
        if isinstance(v, ast.Call) and isinstance(v.func, ast.Attribute) and v.func.attr == "append" \
                and isinstance(v.func.value, ast.Name) and v.args:
            w = sc.env.get(v.func.value.id)
            if w and w[0] == "l":
                r = self.sql_text(v.args[0], sc)
                if r:
                    w[1].append(r)

    def on_for(self, st, sc):
        czasy = self.czasy_w(st.iter, sc)
        skaz = self.skazone(st.iter, sc)
        for n in ast.walk(st.target):
            if isinstance(n, ast.Name):
                if czasy:
                    sc.deps[n.id] = set(czasy)
                if skaz:
                    sc.taint.add(n.id)

    # ----- skanowanie wyrażeń
    def scan(self, wezel, sc):
        for n in ast.walk(wezel):
            try:
                if isinstance(n, ast.Call):
                    self.on_call(n, sc)
                elif isinstance(n, ast.Compare):
                    self.on_compare(n, sc)
                elif isinstance(n, ast.BinOp):
                    self.on_binop(n, sc)
                elif isinstance(n, ast.JoinedStr):
                    self.on_fstring(n, sc)
                elif isinstance(n, ast.Attribute):
                    self.on_attribute(n, sc)
                elif isinstance(n, ast.Dict):
                    self.on_dict(n, sc)
            except Exception as exc:
                self.wyniki_ostrzezenia.append("%s: pominięto konstrukcję (%s)" % (self.plik, type(exc).__name__))

    def helper_sql(self, call):
        f = call.func
        if isinstance(f, ast.Name):
            real = self.importy.get(f.id, f.id).split(".")[-1]
            return real if real in NAZWY_SQL else None
        if isinstance(f, ast.Attribute) and f.attr in ATRYBUTY_SQL:
            baza = _kropkowana(f.value)
            return (baza + "." + f.attr) if baza else f.attr
        return None

    def czy_testowy(self, qual):
        if self.plik_testowy:
            return True
        ostatni = qual.split(".")[-1]
        return ostatni.startswith("test")

    def on_call(self, call, sc):
        info = self.czas.get(id(call))
        if info and id(call) not in self._czas_ids:
            self._czas_ids.add(id(call))
            self.czas_rej.append((call, sc.qual))
            if info.rodzaj in ("utcnow", "utcfromtimestamp"):
                self.dodaj("py_utcnow_deprecated", sc.qual, call.lineno, "", self.segment(call), "likely")
        helper = self.helper_sql(call)
        if helper:
            self.on_sql_call(call, sc, helper)
        self.sprawdz_harmonogram(call, sc)
        if isinstance(call.func, ast.Attribute) and call.func.attr == "format":
            self.numeracja_format_call(call, sc)
        if isinstance(call.func, ast.Attribute) and call.func.attr == "strftime" and call.args:
            fmt = _stala_tekst(call.args[0])
            ids = self._naiwne(self.czasy_w(call.func.value, sc))
            if fmt and ids:
                stary, nowy = self.numeracja_formatu(fmt, sc, self.prefiks_wokol(call))
                if nowy:
                    self.zglos_numeracje(ids, call, sc)
                elif stary:
                    self.numeracja_zdegradowane += 1

    def on_sql_call(self, call, sc, helper):
        arg = call.args[0] if call.args else (_kw(call, "sql") or _kw(call, "query")
                                              or _kw(call, "statement") or _kw(call, "operation"))
        res = self.sql_text(arg, sc) if arg is not None else None
        ctx, surowe, pewna = None, [], False
        if res is not None:
            m = _SQL_ZACZYNA.match(blank_sql(res[0])[0])
            if not m or m.group(1).lower() not in SQL_START:
                return
            nazwy = list(self.hint) + [sc.qual.split(".")[-1].lower()]
            ctx, surowe = analizuj_sql(res[0], self.cfg, nazwy)
            self.numeracja_zdegradowane += ctx.numeracja_zdegradowane
            self.trafione |= ctx.trafione
            self.sql_wywolan += 1
            if ctx.czy_sql_z_czasem():
                self.sql_czas += 1
            pewna = ctx.ma_pewna_kolumne()
            for kat, s, e, pew in surowe:
                linia = res[1] + ctx.code.count("\n", 0, s)
                self.dodaj(kat, sc.qual, linia, helper, ctx.snippet(s, e), pew)
        elif len(call.args) < 2 and _kw(call, "params") is None and _kw(call, "vars") is None:
            return
        if ctx is not None:
            self.numeracja_parametru_sql(call, ctx, sc)
        ids = set()
        for a in list(call.args) + [k.value for k in call.keywords]:
            ids |= self.czasy_w(a, sc)
        for i in ids:
            self.uzycie_sql[i] = self.uzycie_sql.get(i, False) or pewna

    def on_compare(self, cmp, sc):
        operandy = [cmp.left] + list(cmp.comparators)
        ids = set()
        for o in operandy:
            ids |= self.czasy_w(o, sc)
        if not ids or not any(self.skazone(o, sc) for o in operandy):
            return
        pewna = False
        for o in operandy:
            for n in ast.walk(o):
                klucz = None
                if isinstance(n, ast.Subscript):
                    klucz = _klucz_subscript(n)
                elif isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "get" and n.args:
                    klucz = _stala_tekst(n.args[0])
                elif isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id in sc.taint:
                    klucz = n.attr
                if klucz and self.cfg.classify([], klucz)[1]:
                    pewna = True
        for i in ids:
            self.uzycie_db[i] = self.uzycie_db.get(i, False) or pewna

    def on_binop(self, b, sc):
        if isinstance(b.op, (ast.Add, ast.Mod)):
            self.numeracja_binop(b, sc)
        if not isinstance(b.op, (ast.Add, ast.Sub)):
            return
        for a, c in ((b.left, b.right), (b.right, b.left)):
            if self.stale_przesuniecie(a):
                ids = [i for i in self.czasy_w(c, sc) if self.czas[i].rodzaj in ("now", "utcnow")]
                if ids:
                    self.dodaj("py_fixed_offset", sc.qual, b.lineno, "", self.segment(b), "uncertain")
                    return

    def stale_przesuniecie(self, node):
        if isinstance(node, ast.Call) and (self.kanon(node.func) or "") == "datetime.timedelta":
            h = _kw(node, "hours")
            if isinstance(h, ast.Constant) and isinstance(h.value, (int, float)) and abs(h.value) in (1, 2):
                return True
        return False

    def on_attribute(self, n, sc):
        if id(n) not in self.func_ids and (self.kanon(n) or "") in (
                "datetime.datetime.utcnow", "datetime.datetime.utcfromtimestamp"):
            self.dodaj("py_utcnow_deprecated", sc.qual, n.lineno, "", self.segment(n), "likely")

    def _naiwne(self, ids):
        return sorted(i for i in ids if self.czas[i].naiwny)

    def kontekst_numeru(self, sc, prefiks):
        return bool(prefiks or nazwa_identyfikatora(list(self.hint) + [sc.qual.split(".")[-1].lower()]))

    def numeracja_formatu(self, fmt, sc, prefiks):
        """-> (stary, nowy): szeroka reguła z rundy 1 i zawężona (identyfikator dokumentu).

        Nowa reguła: rok LUB miesiąc w formacie, ale tylko w kontekście numeru (prefiks / nazwa).
        """
        rok, mies = re.search(r"%[Yy]", fmt), re.search(r"%[mbB]", fmt)
        if not (rok or mies):
            return False, False
        nazwy = list(self.hint) + [sc.qual.split(".")[-1].lower()]
        stary = bool(rok and mies) and ((not re.search(r"%[dHMSjaAIpf]", fmt))
                                        or any(_NAZWA_NUMERU.search(x) for x in nazwy))
        return stary, self.kontekst_numeru(sc, prefiks)

    def rok_mies(self, node, sc):
        """Naiwne źródła czasu (także przez zmienną), których rok/miesiąc (.year/.month) użyto w ``node``."""
        ids = set()
        for n in ast.walk(node):
            if isinstance(n, ast.Attribute) and n.attr in ("year", "month"):
                ids |= set(self._naiwne(self.czasy_w(n.value, sc)))
        return ids

    def numeracja_binop(self, b, sc):
        """``"FV/" + str(d.year)``, ``"FV/%d" % d.year``: prefiks dokumentu + rok/miesiąc zmiennej czasowej."""
        for stala, reszta in ((b.left, b.right), (b.right, b.left)):
            if isinstance(b.op, ast.Mod) and stala is not b.left:
                continue
            ma_prefiks = isinstance(stala, ast.Constant) and isinstance(stala.value, str) \
                and bool(_PREFIKS_DOK.match(stala.value))
            ids = self.rok_mies(reszta, sc)
            if ids and self.kontekst_numeru(sc, ma_prefiks):
                self.zglos_numeracje(sorted(ids), b, sc)
                return

    def numeracja_format_call(self, call, sc):
        """``"FV/{}/{}".format(d.year, seq)`` oraz ``"FV/{:%Y}".format(d)``."""
        tpl = call.func.value
        if not (isinstance(tpl, ast.Constant) and isinstance(tpl.value, str)):
            return
        ids = set()
        for a in list(call.args) + [k.value for k in call.keywords]:
            ids |= self.rok_mies(a, sc)
            if re.search(r"%[YymbB]", tpl.value):
                ids |= set(self._naiwne(self.czasy_w(a, sc)))
        if ids and self.kontekst_numeru(sc, bool(_PREFIKS_DOK.match(tpl.value))):
            self.zglos_numeracje(sorted(ids), call, sc)

    def numeracja_parametru_sql(self, call, ctx, sc):
        """Rok/miesiąc zmiennej czasowej zapisywany/porównywany z kolumną o nazwie numeru dokumentu."""
        if not ctx.parametr_do_kolumny_numeru():
            return
        ids = set()
        for a in list(call.args[1:]) + [k.value for k in call.keywords]:
            ids |= self.rok_mies(a, sc)
            for n in ast.walk(a):
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr in ("strftime", "format"):
                    ids |= set(self._naiwne(self.czasy_w(n.func.value if n.func.attr == "strftime" else n, sc)))
        if ids:
            self.zglos_numeracje(sorted(ids), call, sc)

    @staticmethod
    def _prefiks_w(stale):
        return any(isinstance(c, ast.Constant) and isinstance(c.value, str) and _PREFIKS_DOK.match(c.value)
                   for c in stale)

    def prefiks_wokol(self, node):
        """Czy wartość jest składana z literałem prefiksu dokumentu ("ZAM/", "FV/")."""
        cur = node
        while True:
            p = self.rodzic.get(id(cur))
            if isinstance(p, ast.BinOp) and isinstance(p.op, (ast.Add, ast.Mod)):
                if self._prefiks_w([p.left, p.right]):
                    return True
            elif isinstance(p, ast.FormattedValue):
                p = self.rodzic.get(id(p))
                if isinstance(p, ast.JoinedStr) and self._prefiks_w(p.values):
                    return True
                return False
            else:
                return False
            cur = p

    def zglos_numeracje(self, ids, node, sc):
        self.zuzyte.update(ids)
        if (sc.qual, node.lineno) in self._num_linie:  # jedno trafienie na linię (najszerszy zapis)
            return
        self._num_linie.add((sc.qual, node.lineno))
        self.dodaj("numbering_by_date", sc.qual, node.lineno, "", self.segment(node), "likely")

    def on_fstring(self, js, sc):
        atrybuty = set()
        ids_atr = set()
        prefiks = self._prefiks_w(js.values)
        for v in js.values:
            if not isinstance(v, ast.FormattedValue):
                continue
            ids = self._naiwne(self.czasy_w(v.value, sc))
            if not ids:
                continue
            if v.format_spec is not None:
                fmt = "".join(str(x.value) for x in v.format_spec.values if isinstance(x, ast.Constant))
                stary, nowy = self.numeracja_formatu(fmt, sc, prefiks)
                if nowy:
                    self.zglos_numeracje(ids, js, sc)
                    return
                if stary:
                    self.numeracja_zdegradowane += 1
            if isinstance(v.value, ast.Attribute) and v.value.attr in ("year", "month"):
                atrybuty.add(v.value.attr)
            ids_atr |= self.rok_mies(v.value, sc)
        if ids_atr and self.kontekst_numeru(sc, prefiks):
            self.zglos_numeracje(sorted(ids_atr), js, sc)
        elif atrybuty == {"year", "month"}:
            self.numeracja_zdegradowane += 1

    # ----- harmonogramy
    def sprawdz_harmonogram(self, call, sc):
        f = call.func
        nm = _nazwa_koncowa(f)
        if isinstance(f, ast.Attribute) and f.attr in ("add_job", "scheduled_job"):
            idx = 1 if f.attr == "add_job" else 0
            trig = _kw(call, "trigger")
            if trig is None and len(call.args) > idx:
                trig = call.args[idx]
            if _kw(call, "timezone") is not None and trig is not None:
                self.bez_cron.add(id(trig))
            t = _stala_tekst(trig) if trig is not None else None
            if t and t.strip().lower() == "cron" and _kw(call, "timezone") is None \
                    and not self.tz_skonfigurowana \
                    and any(k.arg in _CRON_KW for k in call.keywords):
                self.dodaj("scheduler_no_timezone", sc.qual, call.lineno, f.attr, self.segment(call), "likely")
            return
        if nm == "CronTrigger" or (isinstance(f, ast.Attribute) and f.attr == "from_crontab"
                                   and _nazwa_koncowa(f.value) == "CronTrigger"):
            if id(call) in self.bez_cron or _kw(call, "timezone") is not None or self.tz_skonfigurowana:
                return
            if isinstance(f, ast.Attribute) and f.attr == "from_crontab":
                pola = (_stala_tekst(call.args[0]) or "").split() if call.args else []
                if len(pola) >= 5 and pola[1].startswith("*") and all(p == "*" for p in pola[2:5]):
                    return
            elif not any(k.arg in _CRON_KW for k in call.keywords) and len(call.args) < 2:
                return
            self.dodaj("scheduler_no_timezone", sc.qual, call.lineno, "CronTrigger", self.segment(call), "likely")
            return
        if nm == "crontab" and not self.tz_skonfigurowana:
            if any(k.arg in _CRON_KW for k in call.keywords) or len(call.args) >= 2:
                self.dodaj("scheduler_no_timezone", sc.qual, call.lineno, "crontab", self.segment(call), "likely")

    def on_dict(self, d, sc):
        klucze = {}
        for k, v in zip(d.keys, d.values):
            t = _stala_tekst(k) if k is not None else None
            if t:
                klucze[t] = v
        trig = klucze.get("trigger")
        if trig is not None and (_stala_tekst(trig) or "").lower() == "cron" \
                and "timezone" not in klucze and not self.tz_skonfigurowana \
                and any(k in _CRON_KW for k in klucze):
            self.dodaj("scheduler_no_timezone", sc.qual, d.lineno, "dict", self.segment(d), "likely")

    # ----- podsumowanie wyników czasu
    def zakoncz(self):
        for node, qual in self.czas_rej:
            info = self.czas[id(node)]
            if not info.naiwny or info.syntetyczny or id(node) in self.zuzyte:
                continue
            i = id(node)
            testowy = self.czy_testowy(qual)
            if not testowy and (i in self.uzycie_sql or i in self.uzycie_db):
                pewna = self.uzycie_sql.get(i) or self.uzycie_db.get(i)
                if i in self.domyslne:
                    self.dodaj("py_naive_now", qual, node.lineno, "", self.segment(node),
                               "likely" if pewna else "uncertain", "srednia", OPIS_DOMYSLNEJ)
                else:
                    self.dodaj("py_naive_now", qual, node.lineno, "", self.segment(node),
                               "likely" if pewna else "uncertain")
            else:
                self.dodaj("py_naive_now_other", qual, node.lineno, "", self.segment(node), "uncertain")


def analizuj_zrodlo(tekst, plik="modul.py", cfg=None, plik_testowy=False):
    """-> (lista Wynik, StatPliku). Rzuca SyntaxError dla niepoprawnego kodu."""
    cfg = cfg or KonfiguracjaKolumn()
    a = AnalizatorModulu(tekst, plik, cfg, plik_testowy)
    a.uruchom()
    stat = StatPliku(plik, a.sql_wywolan, a.sql_czas, len(a.wyniki))
    return a.wyniki, stat


def czy_plik_testowy(rel):
    baza = rel.rsplit("/", 1)[-1]
    if baza.startswith("test_") or baza.endswith("_test.py") or baza == "conftest.py":
        return True
    return any(c in ("test", "tests", "testing") for c in rel.split("/")[:-1])


# --------------------------------------------------------------------------- pliki

def czytaj_tekst(sciezka):
    with open(sciezka, "rb") as f:
        dane = f.read()
    try:
        kodowanie, _ = tokenize.detect_encoding(io.BytesIO(dane).readline)
    except SyntaxError:
        kodowanie = "utf-8"
    try:
        return dane.decode(kodowanie, errors="replace")
    except LookupError:
        return dane.decode("utf-8", errors="replace")


def _norm_sciezka(s):
    return s.strip().strip('"').replace("\\", "/")


def czy_wykluczony(rel, wzorce):
    czesci = rel.split("/")
    for w in wzorce:
        w = _norm_sciezka(w).rstrip("/")
        if not w:
            continue
        if fnmatch.fnmatchcase(rel, w) or fnmatch.fnmatchcase(czesci[-1], w) \
                or any(fnmatch.fnmatchcase(c, w) for c in czesci) or rel.startswith(w + "/"):
            return True
    return False


def zbierz_pliki(backend, wykluczenia=(), files_from=None, ostrzez=None):
    """-> posortowana lista (rel_posix, sciezka_fizyczna)."""
    ostrzez = ostrzez or (lambda m: None)
    korzen = os.path.abspath(backend)
    domyslne = set(x.lower() for x in DOMYSLNE_WYKLUCZENIA)
    wynik = {}

    def wykluczony(rel):
        if any(c.lower() in domyslne for c in rel.split("/")[:-1]):
            return True
        return czy_wykluczony(rel, wykluczenia)

    if files_from is None:
        for kat, podkat, pliki in os.walk(korzen):
            wzgl = os.path.relpath(kat, korzen).replace(os.sep, "/").replace("\\", "/")
            wzgl = "" if wzgl == "." else wzgl
            podkat[:] = sorted(
                d for d in podkat
                if d.lower() not in domyslne and not czy_wykluczony((wzgl + "/" + d).lstrip("/"), wykluczenia))
            for p in sorted(pliki):
                if not p.endswith(".py"):
                    continue
                rel = (wzgl + "/" + p).lstrip("/")
                if not czy_wykluczony(rel, wykluczenia):
                    wynik[rel] = os.path.join(kat, p)
    else:
        for linia in files_from.splitlines():
            linia = linia.strip()
            if not linia or linia.startswith("#"):
                continue
            p = _norm_sciezka(linia)
            if not p.endswith(".py"):
                continue
            kandydaci = [p] if os.path.isabs(p) or re.match(r"^[A-Za-z]:/", p) else [
                os.path.join(korzen, p), p]
            fiz = next((k for k in kandydaci if os.path.isfile(k)), None)
            if fiz is None:
                ostrzez("plik z --files-from nie istnieje: %s" % p)
                continue
            rel = os.path.relpath(os.path.abspath(fiz), korzen).replace(os.sep, "/")
            if rel.startswith("../"):
                rel = p
            if not wykluczony(rel):
                wynik[rel] = fiz
    return sorted(wynik.items())


def audyt(backend, cfg, wykluczenia=(), files_from=None, ostrzez=None):
    ostrzez = ostrzez or (lambda m: None)
    raport = Raport()
    raport.kolumn_tz, raport.kolumn_local = len(cfg.tz), len(cfg.local)
    for rel, fiz in zbierz_pliki(backend, wykluczenia, files_from, ostrzez):
        try:
            tekst = czytaj_tekst(fiz)
        except OSError as exc:
            ostrzez("nie można odczytać %s: %s" % (rel, exc.__class__.__name__))
            raport.pominiete.append(rel)
            continue
        try:
            a = AnalizatorModulu(tekst, rel, cfg, czy_plik_testowy(rel))
        except (SyntaxError, ValueError, RecursionError, MemoryError) as exc:
            linia = getattr(exc, "lineno", None)
            ostrzez("pominięto %s: błąd składni%s" % (rel, " (linia %s)" % linia if linia else ""))
            raport.pominiete.append(rel)
            continue
        a.uruchom()
        for w in sorted(set(a.wyniki_ostrzezenia)):
            ostrzez(w)
        raport.numeracja_zawezona += a.numeracja_zdegradowane
        raport.trafione |= a.trafione
        raport.pliki.append(StatPliku(rel, a.sql_wywolan, a.sql_czas, len(a.wyniki)))
        raport.wyniki.extend(a.wyniki)
    raport.wyniki.sort(key=lambda w: (WAZNOSCI.index(w.waznosc), w.plik, w.linia, w.kategoria, w.fragment))
    return raport


# --------------------------------------------------------------------------- baseline

def zapisz_baseline(sciezka, wyniki):
    licznik = Counter(w.klucz() for w in wyniki)
    dane = OrderedDict([
        ("wersja", WERSJA),
        ("klucze", [OrderedDict([("klucz", k), ("liczba", licznik[k])]) for k in sorted(licznik)]),
    ])
    zapisz_plik(sciezka, json.dumps(dane, ensure_ascii=False, indent=2) + "\n")


def wczytaj_baseline(sciezka):
    dane = json.loads(czytaj_tekst(sciezka))
    wpisy = dane.get("klucze", []) if isinstance(dane, dict) else dane
    licznik = Counter()
    for w in wpisy:
        if isinstance(w, str):
            licznik[w] += 1
        elif isinstance(w, dict) and "klucz" in w:
            licznik[w["klucz"]] += int(w.get("liczba", 1))
    return licznik


def oznacz_nowe(wyniki, baseline):
    pozostalo = Counter(baseline)
    for w in wyniki:
        k = w.klucz()
        if pozostalo[k] > 0:
            pozostalo[k] -= 1
            w.nowy = False
        else:
            w.nowy = True


def zapisz_plik(sciezka, tekst):
    with open(sciezka, "w", encoding="utf-8", newline="\n") as f:
        f.write(tekst)


# --------------------------------------------------------------------------- raport

def podsumuj(raport):
    """Podsumowanie jako lista linii tekstu."""
    sql = sum(p.sql for p in raport.pliki)
    sql_czas = sum(p.sql_czas for p in raport.pliki)
    nowe = sum(1 for w in raport.wyniki if w.nowy)
    blok = sum(1 for w in raport.wyniki if w.nowy and w.kategoria in KATEGORIE_BLOKUJACE)
    licznik = Counter(w.kategoria for w in raport.wyniki)
    linie = [
        "Przeanalizowane pliki: %d" % len(raport.pliki),
        "Wywołania SQL: %d (z funkcjami czasu: %d)" % (sql, sql_czas),
        "Wyniki: %d (nowe: %d, znane z baseline: %d)" % (len(raport.wyniki), nowe, len(raport.wyniki) - nowe),
        "Nowe wyniki blokujące (kod wyjścia 1): %d" % blok,
        "Zawężenie numbering_by_date: %d wyników przestało być numbering_by_date (trafiają do zwykłych kategorii)"
        % raport.numeracja_zawezona,
    ]
    if raport.kolumn_tz or raport.kolumn_local:
        linie.append("Kolumny z plików dopasowane w analizowanym SQL: systemowe %d/%d, lokalne %d/%d" % (
            sum(1 for r, _ in raport.trafione if r == "tz"), raport.kolumn_tz,
            sum(1 for r, _ in raport.trafione if r == "local"), raport.kolumn_local))
    linie += ["", "Rozkład kategorii:"]
    for kat in KATEGORIE:
        linie.append("  %-26s %-10s %d" % (kat, KATEGORIE[kat][0], licznik.get(kat, 0)))
    return linie


def _opis_wyniku(w, wciecie="    "):
    znacznik = "" if w.nowy else " [znany]"
    linie = ["%s:%d  [%s] %s/%s%s" % (w.plik, w.linia, w.kategoria, w.waznosc, w.pewnosc, znacznik),
             "%sfunkcja: %s%s" % (wciecie, w.funkcja, ("  helper: " + w.helper) if w.helper else ""),
             "%sfragment: %s" % (wciecie, w.fragment),
             "%sdlaczego: %s" % (wciecie, w.dlaczego),
             "%spropozycja: %s" % (wciecie, w.propozycja)]
    return linie


def najpierw_napraw(wyniki):
    kandydaci = [w for w in wyniki if w.nowy and w.waznosc == "wysoka" and w.pewnosc == "likely"]
    kandydaci.sort(key=lambda w: (KOLEJNOSC_RYZYKA.index(w.kategoria) if w.kategoria in KOLEJNOSC_RYZYKA else 99,
                                  w.plik, w.linia))
    return kandydaci


def tekst_raportu(raport):
    out = ["sql-timezone-audit - raport", "", "Podsumowanie", "------------"]
    out += podsumuj(raport)
    out += ["", "Najpierw napraw", "---------------"]
    pilne = najpierw_napraw(raport.wyniki)
    if not pilne:
        out.append("(brak nowych wyników o ważności wysokiej i pewności likely)")
    for i, w in enumerate(pilne, 1):
        opis = _opis_wyniku(w)
        out.append("%d. %s" % (i, opis[0]))
        out += opis[1:]
    out += ["", "Wyniki wg ważności", "------------------"]
    for waz in WAZNOSCI:
        grupa = [w for w in raport.wyniki if w.waznosc == waz]
        out += ["", "%s (%d)" % (waz, len(grupa))]
        for w in grupa:
            out += _opis_wyniku(w)
    out += ["", "Rozkład per plik", "----------------"]
    szer = max([len("plik")] + [len(p.plik) for p in raport.pliki])
    out.append("%-*s  %6s  %9s  %6s" % (szer, "plik", "sql", "sql+czas", "wyniki"))
    for p in raport.pliki:
        out.append("%-*s  %6d  %9d  %6d" % (szer, p.plik, p.sql, p.sql_czas, p.wyniki))
    return "\n".join(out) + "\n"


def json_raportu(raport):
    licznik = Counter(w.kategoria for w in raport.wyniki)
    nowe = sum(1 for w in raport.wyniki if w.nowy)
    dane = OrderedDict([
        ("wersja", WERSJA),
        ("narzedzie", "sql_timezone_audit"),
        ("podsumowanie", OrderedDict([
            ("pliki", len(raport.pliki)),
            ("wywolania_sql", sum(p.sql for p in raport.pliki)),
            ("wywolania_sql_z_czasem", sum(p.sql_czas for p in raport.pliki)),
            ("wyniki", len(raport.wyniki)),
            ("nowe", nowe),
            ("znane", len(raport.wyniki) - nowe),
            ("numbering_zawezone", raport.numeracja_zawezona),
            ("kolumny_dopasowane", OrderedDict([
                ("systemowe", sum(1 for r, _ in raport.trafione if r == "tz")),
                ("systemowe_z_pliku", raport.kolumn_tz),
                ("lokalne", sum(1 for r, _ in raport.trafione if r == "local")),
                ("lokalne_z_pliku", raport.kolumn_local),
            ])),
            ("nowe_blokujace", sum(1 for w in raport.wyniki if w.nowy and w.kategoria in KATEGORIE_BLOKUJACE)),
            ("kategorie", OrderedDict((k, licznik.get(k, 0)) for k in KATEGORIE)),
        ])),
        ("wyniki", [w.jako_dict() for w in raport.wyniki]),
        ("pliki", [OrderedDict([("plik", p.plik), ("wywolania_sql", p.sql),
                                ("wywolania_sql_z_czasem", p.sql_czas), ("wyniki", p.wyniki)])
                   for p in raport.pliki]),
    ])
    return json.dumps(dane, ensure_ascii=False, indent=2) + "\n"


# --------------------------------------------------------------------------- CLI

def _pisz(strumien, tekst):
    dane = tekst.encode("utf-8")
    if isinstance(strumien, (io.RawIOBase, io.BufferedIOBase)):
        strumien.write(dane)
    elif getattr(strumien, "buffer", None) is not None:
        strumien.buffer.write(dane)
    else:
        strumien.write(tekst)
    try:
        strumien.flush()
    except Exception:
        pass


def parser_argumentow():
    p = argparse.ArgumentParser(
        prog="sql_timezone_audit.py",
        description="Statyczny audyt błędów strefy czasowej i granicy doby (tylko raport).")
    p.add_argument("--backend", required=True, help="katalog z kodem (rekurencyjnie *.py)")
    p.add_argument("--tz-columns", help="plik z kolumnami systemowymi (UTC, timestamptz)")
    p.add_argument("--local-columns", help="plik z kolumnami lokalnymi (timestamp, czas ze ściany zegara)")
    p.add_argument("--baseline", help="baseline.json: wyniki z niego są traktowane jako znane")
    p.add_argument("--write-baseline", help="zapisz bieżące wyniki jako baseline.json")
    p.add_argument("--files-from", help="plik z listą plików do analizy (po jednym w linii)")
    p.add_argument("--exclude", action="append", nargs="+", default=[], metavar="WZORZEC",
                   help="dodatkowe wzorce wykluczeń (fnmatch)")
    p.add_argument("--json", help="zapisz pełny raport maszynowy do pliku")
    return p


def main(argv=None, stdout=None, stderr=None):
    stdout = stdout if stdout is not None else sys.stdout
    stderr = stderr if stderr is not None else sys.stderr

    def ostrzez(msg):
        _pisz(stderr, "ostrzeżenie: %s\n" % msg)

    def blad(msg):
        _pisz(stderr, "błąd: %s\n" % msg)
        return 2

    try:
        args = parser_argumentow().parse_args(argv)
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 2
    if not os.path.isdir(args.backend):
        return blad("katalog --backend nie istnieje: %s" % args.backend.replace("\\", "/"))
    try:
        tz = parsuj_liste_kolumn(czytaj_tekst(args.tz_columns)) if args.tz_columns else []
        lokalne = parsuj_liste_kolumn(czytaj_tekst(args.local_columns)) if args.local_columns else []
        files_from = czytaj_tekst(args.files_from) if args.files_from else None
        baseline = wczytaj_baseline(args.baseline) if args.baseline else None
    except (OSError, ValueError) as exc:
        return blad("nie można wczytać pliku wejściowego: %s" % exc)
    wykluczenia = [w for grupa in args.exclude for w in grupa]
    raport = audyt(args.backend, KonfiguracjaKolumn(tz, lokalne), wykluczenia, files_from, ostrzez)
    if baseline is not None:
        oznacz_nowe(raport.wyniki, baseline)
    try:
        if args.write_baseline:
            zapisz_baseline(args.write_baseline, raport.wyniki)
            oznacz_nowe(raport.wyniki, wczytaj_baseline(args.write_baseline))
        if args.json:
            zapisz_plik(args.json, json_raportu(raport))
    except OSError as exc:
        return blad("nie można zapisać pliku: %s" % exc)
    _pisz(stdout, tekst_raportu(raport))
    blokujace = [w for w in raport.wyniki if w.nowy and w.kategoria in KATEGORIE_BLOKUJACE]
    return 1 if blokujace else 0


if __name__ == "__main__":
    sys.exit(main())
