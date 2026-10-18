# sql-timezone-audit

Samodzielny analizator statyczny kodu Pythona (Flask + psycopg2): wyszukuje **błędy związane ze strefą
czasową i granicą doby** w zapytaniach SQL oraz w kodzie, który ich wyniki porównuje z "teraz" lub "dziś".
Bez uruchamiania aplikacji, bez sieci, bez bazy.

To narzędzie jest **tylko audytem (raport)**. Nie poprawia żadnego kodu.

> **Najpierw przeczytaj `CLAUDE.md`** (zasady dla każdego zadania w tej organizacji).
> Zasada nr 1: zero prawdziwych nazw. Przykłady w `examples/` pisz od zera, w fikcyjnej domenie
> (np. "sklep z częściami", tabele `parts`, `orders`, `shifts`).

## Po co to jest (geneza)

Aplikacja działa w Polsce (strefa `Europe/Warsaw`, UTC+1/UTC+2 z czasem letnim), ale baza i kontenery
pracują w UTC. Kolumny czasu mają dwa rodzaje:

- **systemowe** (`created_at`, `updated_at`, `sent_at`) — typ `timestamptz`, wartość w UTC, wypełniana
  przez `now()`;
- **wpisywane ręcznie przez użytkownika** (`starts_at`, `scheduled_for`, `due_date`) — typ `timestamp`
  bez strefy, wartość to **czas lokalny "ze ściany zegara"**.

Mieszanie tych dwóch światów daje błędy, które widać tylko o określonych porach doby:

1. **`CURRENT_DATE` / `now()::date` / `date.today()` / `datetime.now()` w UTC.** W Polsce między 00:00 a
   02:00 (latem) lub 01:00 (zimą) "dziś" w UTC to jeszcze **wczoraj**. Skutek: wpis przypisany do
   złego dnia, zły miesiąc w numerze dokumentu na granicy miesiąca, raport "na dziś" bez ostatnich godzin.
2. **Porównanie kolumny lokalnej (`timestamp`) z `NOW()`** (które jest UTC) → okno "nadchodzące" lub
   "zaległe" przesunięte o 1–2 godziny. Poprawnie: `NOW() AT TIME ZONE 'Europe/Warsaw'`.
3. **Porównanie kolumny `timestamptz` z literałem daty/czasu bez strefy** (`WHERE created_at >= '2026-10-01'`)
   → granica doby wypada w UTC, nie lokalnie.
4. **`date_trunc('day'|'month'|..., kolumna_timestamptz)` bez `AT TIME ZONE`** → "dzień" i "miesiąc"
   liczone w UTC; zdarzenie o 23:30 lokalnie ląduje w następnym dniu.
5. **`kolumna::date` / `DATE(kolumna)` / `EXTRACT(... FROM kolumna)` na `timestamptz`** bez `AT TIME ZONE`
   — jak wyżej.
6. **Python: `datetime.now()` / `datetime.utcnow()` / `date.today()`** (naiwne, bez `tzinfo`) wstawiane do
   zapytań lub porównywane z danymi z bazy; `utcnow()` jest dodatkowo przestarzałe od Pythona 3.12.
7. **Sztywny offset zamiast strefy** (`+ interval '2 hours'`, `timedelta(hours=2)`, `'+02'`) — psuje się
   przy zmianie czasu (ostatnie niedziele marca i października).
8. **Harmonogram bez jawnej strefy**: zadanie typu "cron o 06:30" tworzone bez `timezone=` (APScheduler,
   Celery) odpala się o 06:30 UTC, czyli 07:30/08:30 lokalnie.

## Zadanie

Zbuduj od zera, przetestuj i udokumentuj CLI w **Pythonie 3.8+, zero zależności zewnętrznych**
(`ast`, `re`, `pathlib`, `argparse`, `json`). Plik główny: `sql_timezone_audit.py`.
Testy: `tests/` (`unittest`, bez sieci i bazy). Wszystkie ścieżki w wynikach zawsze z `/`, wyjście
UTF-8 z końcami linii LF, niezależnie od systemu (narzędzie będzie uruchamiane na Windowsie).

```
python sql_timezone_audit.py --backend <katalog> \
    [--tz-columns plik.txt] [--local-columns plik.txt] \
    [--baseline baseline.json] [--write-baseline baseline.json] \
    [--files-from lista.txt] [--exclude wzorzec ...] [--json raport.json]
```

- `--backend` — katalog z kodem (rekurencyjnie `*.py`; domyślnie wyklucz `venv`, `node_modules`,
  `__pycache__`, `tests`, `migrations`, `archive`).
- `--tz-columns` — plik z nazwami kolumn **systemowych** (UTC, `timestamptz`), po jednej w linii
  (`tabela.kolumna` albo samo `kolumna`). `--local-columns` — plik z kolumnami **lokalnymi**
  (`timestamp`, czas wpisany ręcznie). Gdy brak plików: heurystyka po nazwie (`*_at`, `created`, `updated`,
  `sent` → systemowa; `*_date`, `start*`, `end*`, `planned*`, `scheduled*`, `due*` → lokalna) i
  **obniżenie pewności do `uncertain`**.
- `--baseline` / `--write-baseline` / `--files-from` — jak w innych narzędziach tej serii
  (klucz wyniku: plik + funkcja + kategoria + znormalizowany fragment, NIE numer linii).
- Parsuj przez `ast`. Plik z błędem składni: ostrzeżenie na stderr, pomiń. Konstrukcje, których nie umiesz
  rozstrzygnąć: wynik `uncertain`, nigdy wyjątek.
- SQL rozpoznawaj w literałach przekazywanych do `query_one`, `query_all`, `execute`, `execute_return`,
  `cur.execute`, `cur.executemany` (nazwy dokładne, rozpoznawaj aliasy `as`; `executor.execute(task)`
  to nie SQL — wymagaj, by pierwszy argument wyglądał jak SQL: `SELECT|INSERT|UPDATE|DELETE|WITH|...`).
  Śledź zmienną SQL w obrębie funkcji (`sql = "..."`, `+=`, `.join`), f-stringi traktuj jak tekst ze
  zdjętymi wstawkami.

## Co ma wykrywać

| Kategoria | Opis | Ważność |
|-----------|------|---------|
| `sql_current_date_utc` | `CURRENT_DATE`, `current_date`, `now()::date`, `CURRENT_TIMESTAMP::date`, `localtimestamp` w SQL, gdzie nie ma w pobliżu (to samo wyrażenie) `AT TIME ZONE` | wysoka |
| `sql_local_vs_now` | porównanie kolumny **lokalnej** z `NOW()`/`CURRENT_TIMESTAMP` bez `AT TIME ZONE` na `NOW()` | wysoka |
| `sql_date_trunc_utc` | `date_trunc(...)`, `::date`, `DATE(...)`, `EXTRACT(...)` na kolumnie **systemowej** bez `AT TIME ZONE` | wysoka |
| `sql_literal_boundary` | porównanie kolumny systemowej z literałem daty/czasu bez strefy (`'2026-10-01'`, `'2026-10-01 00:00'`, `DATE '...'`) | średnia |
| `sql_fixed_offset` | `interval '1 hour'/'2 hours'` w kontekście strefy, `+ INTERVAL '2 hours'` obok kolumny czasu, literał `'+02'`/`'+01'`/`'+02:00'` | średnia |
| `py_naive_now` | `datetime.now()` bez argumentu strefy, `datetime.utcnow()`, `date.today()`, `datetime.today()` — **wynik używany w SQL** (parametr zapytania) lub porównywany z wartością z bazy | wysoka |
| `py_naive_now_other` | to samo, ale nie da się ustalić użycia w SQL (np. log, nazwa pliku) | informacja |
| `py_utcnow_deprecated` | każde użycie `datetime.utcnow()` / `utcfromtimestamp()` | niska |
| `py_fixed_offset` | `timedelta(hours=1|2)` dodawane/odejmowane od `datetime.now()`/`utcnow()` | średnia |
| `scheduler_no_timezone` | zadanie harmonogramu z wyzwalaczem `cron`/`CronTrigger`/`crontab` **bez** `timezone=` (APScheduler: `add_job(..., 'cron', hour=...)`, dekorator `@scheduler.scheduled_job('cron', ...)`, `CronTrigger(...)`; wyzwalacze `interval` pomiń — bez wpływu) | wysoka |
| `numbering_by_date` | numer dokumentu/zlecenia budowany z `date.today()`/`CURRENT_DATE`/`datetime.now()` (`f"{...:%Y/%m}"`, `to_char(CURRENT_DATE,...)`) — granica miesiąca | wysoka |

`pewnosc` każdego wyniku: `likely` albo `uncertain` — **nigdy `certain`**. Typ kolumny (lokalna vs
systemowa) ustalony z plików `--tz-columns`/`--local-columns` → `likely`; z heurystyki nazwy → `uncertain`.
W wyniku: plik, funkcja, linia, helper, krótki fragment SQL/kodu (maks. 120 znaków, bez wartości),
`dlaczego`, `propozycja` (jedno zdanie, np. `CURRENT_DATE` → `(NOW() AT TIME ZONE 'Europe/Warsaw')::date`).

Kod wyjścia `1`, gdy jest co najmniej jeden **nowy** (względem baseline) wynik kategorii:
`sql_current_date_utc`, `sql_local_vs_now`, `sql_date_trunc_utc`, `py_naive_now`,
`scheduler_no_timezone`, `numbering_by_date`.

## Wyjście

1. Raport tekstowy: `podsumuj()` (liczba wywołań SQL, ile zawiera funkcje czasu, rozkład kategorii), potem
   wyniki wg ważności.
2. `--json` — pełne dane maszynowe.
3. Tabela "rozkład per plik" (ile wywołań SQL, ile z funkcjami czasu) — żeby znaleźć pliki odstające.
4. Sekcja "najpierw napraw": wyniki o ważności wysokiej i pewności `likely`, posortowane wg ryzyka
   (`numbering_by_date` i `scheduler_no_timezone` na górze).

## Dane testowe

`examples/` — **fikcyjny** mini-backend (kilkanaście plików: sklep, zmiany pracowników, zamówienia)
ilustrujący każdą kategorię, z `examples/EXPECTED.md` (golden), plik `examples/tz_columns.txt` i
`examples/local_columns.txt`. Osobne testy jednostkowe dla: każdej kategorii (przypadek pozytywny i
negatywny), `AT TIME ZONE` w tym samym wyrażeniu (nie flaguj), kolumn lokalnych vs systemowych,
aliasów importu (`from datetime import datetime as dt`), wielolinijkowego SQL, komentarzy SQL
(`-- CURRENT_DATE` NIE liczy się), f-stringów, baseline, `--files-from`, ścieżek z `/` i UTF-8.

## Definicja "gotowe"

- `python -m unittest` zielone, **co najmniej 70 testów**, w tym golden. Uruchomione na Linuksie
  i (CI/matrix albo ręcznie) na Windowsie.
- Zero zależności zewnętrznych. Na ~200 plikach backendu < 10 s. Nie wywala się na dziwnym kodzie.
- **Test regresji fałszywych trafień** (lekcja z poprzednich narzędzi): `CURRENT_DATE` w komentarzu SQL
  lub w stringu niebędącym SQL nie jest wynikiem; `AT TIME ZONE 'Europe/Warsaw'` w obrębie tego samego
  wyrażenia wyklucza trafienie; `datetime.now(tz=...)` i `datetime.now(timezone.utc)` NIE są naiwne;
  `date.today()` w teście lub w nazwie pliku/logu to `py_naive_now_other`, nie `py_naive_now`;
  nazwy helperów dopasowuj dokładnie, nie po podciągu.
- Sekcja "Implementacja" w README: decyzje, ograniczenia, znane fałszywe trafienia, otwarte pytania.
- Praca na branchu, małe commity, na koniec merge do `main`.

## Czego NIE robić

- Nie poprawiaj kodu, nie generuj łatek; tylko raport.
- Nie zakładaj schematu bazy — typy kolumn wyłącznie z plików wejściowych lub heurystyki (wtedy `uncertain`).
- Nie flaguj każdego `now()` — `now()` jako **wartość zapisywana** do kolumny `timestamptz`
  (`DEFAULT now()`, `SET updated_at = now()`) jest poprawne.
