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

## Implementacja

Stan: zaimplementowane w jednym pliku `sql_timezone_audit.py` (Python 3.8+, wyłącznie stdlib:
`ast`, `re`, `argparse`, `json`, `os`, `fnmatch`, `tokenize`, `dataclasses`). Sprawdzone na Pythonie 3.11–3.13.

### Jak uruchomić

```
python sql_timezone_audit.py --backend examples/backend \
    --tz-columns examples/tz_columns.txt --local-columns examples/local_columns.txt
python -m unittest            # 414 testów, bez sieci i bez bazy (tests/ jest pakietem)
```

- Kod wyjścia: `0` brak nowych wyników blokujących, `1` co najmniej jeden **nowy** wynik z kategorii
  `sql_current_date_utc`, `sql_local_vs_now`, `sql_date_trunc_utc`, `py_naive_now`,
  `scheduler_no_timezone`, `numbering_by_date`, `sql_utc_into_local_column`; `2` błąd użycia (brak katalogu, nieczytelny plik, zły JSON).
- `--write-baseline` zapisuje baseline i kończy kodem `0` (świeżo zaakceptowany stan). Klucz baseline to
  `plik|funkcja|kategoria|znormalizowany fragment` (bez numeru linii), z licznikiem powtórzeń: identyczny
  wynik dodany drugi raz w tej samej funkcji jest nowy.
- Zakres domyślnie wyklucza także `.venv` i `.git` (poza listą z zadania). `--exclude` przyjmuje wzorce
  `fnmatch` dopasowywane do ścieżki, nazwy pliku i każdego członu ścieżki.
- `--files-from` przyjmuje ścieżki względem `--backend` (lub bezwzględne/względem bieżącego katalogu),
  także z `\`; domyślne wykluczenia nadal obowiązują.
- Wyjście: UTF-8, końce linii LF, ścieżki z `/`, niezależnie od systemu (raport pisany jako bajty do
  `sys.stdout.buffer`, pliki JSON/baseline z `newline="\n"`). Źródła są czytane z uwzględnieniem BOM-u,
  deklaracji `coding:` i CRLF. W raporcie nie ma ścieżek bezwzględnych ani czasu, więc jest deterministyczny
  (stąd golden). Na Windowsie uruchamiać dokładnie tak samo (`python -m unittest`); testy nie zakładają
  separatora ścieżek. Nie uruchamiałem ich na prawdziwym Windowsie - tylko na Linuksie (do zrobienia w CI/matrix).
- Golden: `examples/EXPECTED.md` to pełny raport dla fikcyjnego `examples/backend` (sklep z częściami).
  Po zmianie narzędzia: `UPDATE_GOLDEN=1 python -m unittest tests.test_golden`, przejrzeć diff i zacommitować.

### Decyzje

- **Dwa przebiegi na jedno wywołanie SQL.** Tekst SQL jest odtwarzany z AST (literał, f-string z wstawkami
  zdjętymi lub podstawionymi znaną zmienną, `+`, `+=`, `%`, `.format`, `" ".join(lista)`, `.append`,
  stałe modułu i klasy, `self.STAŁA`) w obrębie funkcji i modułu. Potem `blank_sql` zamienia komentarze
  na spacje, a w wersji "szkielet" także zawartość literałów tekstowych. Wszystkie detektory działają
  na tekście o tej samej długości, więc indeksy pasują do oryginału (komentarz SQL ani tekst w literale nigdy
  nie daje trafienia).
- **"To samo wyrażenie" dla `AT TIME ZONE`** = `AT TIME ZONE` bezpośrednio po wyrażeniu (także za
  zamykającymi nawiasami), wywołanie `timezone(...)` obejmujące wyrażenie albo `AT TIME ZONE` wewnątrz
  operandu (np. `date_trunc('day', kol AT TIME ZONE '...')`, `(kol AT TIME ZONE '...')::date`).
- **Operandy porównań** (`kolumna op NOW()`, `NOW() op kolumna`, `BETWEEN`, `kolumna +/- interval ... op NOW()`)
  wyznacza prosty parser nawiasów, nie pełna gramatyka SQL.
- **Typ kolumny**: tabela+kolumna z plików (`tabela.kolumna`, rozpoznawane też przez alias z `FROM/JOIN`),
  potem sama nazwa z plików → `likely`; w przeciwnym razie heurystyka po nazwie → `uncertain`. Kolumna
  nieznana i niepasująca do heurystyki jest ignorowana. Przy podanych plikach niewymienione kolumny
  nadal korzystają z heurystyki (z `uncertain`).
- **Pewność**: kategorie niezależne od typu kolumny (`sql_current_date_utc`, `numbering_by_date`,
  `scheduler_no_timezone`, `py_utcnow_deprecated`) są `likely`; `py_naive_now` jest `likely` tylko gdy zapytanie
  (albo klucz porównywanej wartości z bazy) dotyczy kolumny z plików, `py_naive_now_other` i `py_fixed_offset`
  zawsze `uncertain`. Nigdy `certain`.
- **`py_naive_now` vs `_other`**: śledzony jest przepływ danych w funkcji (`x = datetime.now()` → `x` w parametrach
  `execute`/`query_*`, w liście/krotce parametrów, w f-stringu SQL; porównanie z wartością pochodzącą z wyniku
  `query_*` lub z pętli po nim). Plik/funkcja testowa (`test_*.py`, `*_test.py`, `conftest.py`, katalog `tests`,
  funkcja `test*`) zawsze daje `_other`.
- **`numbering_by_date`** (zawężone w rundzie 2, patrz niżej) zastępuje `sql_current_date_utc` / `py_naive_now(_other)`
  dla tego samego wyrażenia (jedno trafienie, nie dwa).
- **Harmonogramy**: `add_job(..., 'cron', hour=...)`, `@x.scheduled_job('cron', ...)`, `CronTrigger(...)`,
  `CronTrigger.from_crontab(...)`, celery `crontab(...)` i słowniki `{'trigger': 'cron', ...}`. Wyzwalacz `cron` bez
  pola godzinowego/dnia (np. samo `minute="*/5"`) i `interval` są pomijane. Strefa ustawiona w konstruktorze
  `*Scheduler(timezone=...)`, `Celery(...)`, `conf.update(timezone=...)` lub przypisaniu `timezone = ...`
  / `CELERY_TIMEZONE` w tym samym module jest uznawana za jawną.
- **Odporność**: błąd składni → ostrzeżenie na stderr i pominięcie pliku; wyjątek w analizie pojedynczej konstrukcji
  jest łapany (ostrzeżenie), reszta pliku analizowana dalej. Zamknięcie w `try/except` obejmuje także zbyt głęboką
  rekurencję.

### Ograniczenia i znane fałszywe trafienia

- Analizowane jest tylko SQL widoczne w pliku: pierwszy argument wywołań `query_one/query_all/execute/execute_return/
  cur.execute/executemany` (też przez alias importu). SQL składany w innej funkcji i przekazany jako parametr, z pliku
  `.sql` albo z ORM-a nie jest widziany; zmienna SQL, która nie trafia do rozpoznanego helpera, nie jest analizowana.
- Numer linii wyniku SQL = linia początku literału + liczba nowych linii przed trafieniem; przy ciągu literałów
  sklejonych niejawnie (`"a" "b"` na kilku liniach) lub zmiennej złożonej z wielu przypisań bywa przesunięty.
  Klucz baseline nie zależy od linii, więc to tylko wygoda czytania.
- Śledzenie zmiennych jest liniowe (kolejność źródła, obie gałęzie `if` są traktowane jak wykonane po kolei) i nie obejmuje
  przekazywania przez argumenty funkcji ani atrybuty obiektów (poza `self.STAŁA` klasy).
- Znane fałszywe trafienia:
  - `py_fixed_offset` dla zwykłych terminów ważności (`datetime.now() + timedelta(hours=1)` w tokenie) - dlatego zawsze `uncertain`;
  - `sql_fixed_offset` dla `kolumna +/- interval '1 hour'` oznaczającego realne "godzinę przed wydarzeniem" - `uncertain`;
  - `sql_local_vs_now` dla kolumny, którą heurystyka nazwy uznała za lokalną (`end*`, `start*`, `due*`), a w bazie jest
    `timestamptz`; skutek: `uncertain` - rozstrzyga plik `--tz-columns`;
  - `CURRENT_DATE` w `DEFAULT` w DDL wysłanym przez `execute` jest raportowane tak samo jak w zapytaniu (to też UTC);
  - SQL w zwykłym stringu, który wygląda jak SQL i trafia do `execute`, ale nie jest wysyłany do bazy.
- Nie wykrywane (celowo poza zakresem): `timezone(timedelta(hours=2))` jako stała strefa, `time.time()`/`time.localtime()`,
  biblioteki `pendulum`/`arrow`, `datetime.fromtimestamp(ts)` bez strefy, funkcje składowane w bazie, `SET TIME ZONE`.
- Wydajność: 200 plików ~ 0,4 s (test `test_performance_200_files`).

### Otwarte pytania / decyzje do rozstrzygnięcia

1. ~~Zapis `SET starts_at = now()`~~ - rozstrzygnięte w rundzie 2: osobna kategoria `sql_utc_into_local_column`.
2. Czy zaufać strefie ustawionej na poziomie harmonogramu (obecnie tak - brak wyniku), czy raportować jako `uncertain`?
3. Czy `py_fixed_offset` powinno obejmować też `timezone(timedelta(hours=2))` oraz godziny inne niż 1/2?
4. Czy zakres domyślnych wykluczeń ma zawierać także `.venv`/`.git` (dodane tu na własną rękę)?
5. Uruchomienie testów na prawdziwym Windowsie w CI (matrix) - brak w tym repo konfiguracji CI.

### Runda 2 (poprawki po uruchomieniu na dużym prawdziwym backendzie)

Dla każdej klasy najpierw powstał test negatywny na fikcyjnym fixture (`tests/test_round2.py`), potem poprawiony został kod.
Testów jest 231; golden `examples/EXPECTED.md` odświeżony (nowe pliki/funkcje w `examples/backend`).

1. **Końce linii.** `.gitattributes` (`* text=auto eol=lf`, `*.md`/`*.txt`/`*.json`/`*.py` jako `eol=lf`). Testy golden porównują po
   normalizacji `\r\n` → `\n` po obu stronach, a `test_expected_file_is_lf_utf8` toleruje CRLF z checkoutu `autocrlf=true`.
   Sprawdzone lokalnie przez zamianę wszystkich plików `examples/` na CRLF (wszystkie testy zielone); na prawdziwym
   Windowsie z `autocrlf=true` nadal niesprawdzone.
2. **`sql_fixed_offset`.** Interwał flagowany tylko gdy jest dodany do **kolumny** czasu (`kolumna + interval '2 hours'`;
   `likely`, gdy w operandzie jest `AT TIME ZONE`, inaczej `uncertain`) albo dla literałów `'+01'`, `'+02'`, `'+01:00'`, `'+02:00'`.
   Arytmetyka na samym `NOW()` - także `(NOW() AT TIME ZONE '...') - INTERVAL '1 hour'` i `timezone('...', now()) + interval '2 days'` -
   nie daje wyniku. Zachowany (dotychczasowy test) przypadek `(kolumna AT TIME ZONE 'UTC') + interval '2 hours'` nadal jest `likely`,
   bo to właśnie dorabianie przesunięcia do kolumny.
3. **`numbering_by_date` zawężone** do wartości, która wchodzi w identyfikator dokumentu:
   - literał prefiksu dokumentu (wielkie litery + separator: `"ZAM/"`, `"FV-"`) w tym samym f-stringu / konkatenacji / `||` / `concat(...)`;
   - albo nazwa zmiennej, stałej, funkcji lub kolumny pasuje do `numer|nr|number|seq|prefix|numeracja|invoice|order_no`
     (SQL: kolumna w `SET kol = ...`, w pozycji `INSERT ... VALUES`, po lewej/prawej stronie `=`/`LIKE`; Python: cel przypisania
     i nazwa otaczającej funkcji).
   Reszta (klucze w magazynie obiektów `uploads/{...:%Y/%m}`, `to_char(..., 'MM-DD')` dla urodzin, etykiety roku, komunikaty) trafia do
   zwykłych kategorii: `py_naive_now(_other)` albo `sql_current_date_utc` (także dla `to_char(now()/current_timestamp, ...)`,
   gdzie data jest liczona w UTC). Prefiks pisany małymi literami (`"uploads/"`, `"raport_"`) celowo nie liczy się jako prefiks dokumentu.
   Raport i JSON mają licznik zawężeń (`numbering_zawezone`): ile wyników według reguły z rundy 1 było `numbering_by_date`, a teraz nie jest.
   Zmiana wymusiła edycję dwóch testów z rundy 1, bo były sprzeczne z nową specyfikacją: `to_char(CURRENT_DATE,'YYYY/MM')` bez prefiksu
   i `f"{d.year}/{d.month}"` bez nazwy numeru nie są już numeracją (testy dostały prefiks `'FV/' ||` oraz zmienną `nr`).
4. **`sql_utc_into_local_column`** (wysoka, blokująca): `NOW()`/`CURRENT_TIMESTAMP` (także z `+ interval`) w `UPDATE ... SET kol = ...`,
   `ON CONFLICT ... DO UPDATE SET` i na pozycji kolumny w `INSERT ... VALUES`. `likely` tylko dla kolumny z `--local-columns`,
   `uncertain` dla heurystyki nazwy. Zapis do kolumny systemowej (lub nieznanej) jest poprawny/pomijany; `AT TIME ZONE`/`timezone()` wyklucza.
   Zapis nie jest już dodatkowo raportowany jako `sql_local_vs_now`; porównania w `WHERE` zostają tam, gdzie były.
5. **Domyślny parametr z naiwnego now().** Wzorce `x = ....get(...)` + `if not x: x = datetime.now().strftime(...)` (także `x is None`, `x == ""`)
   oraz `x = ....get(...) or date.today()...`, gdy `x` trafia do SQL, zostają `py_naive_now`, ale z ważnością `srednia` i dopiskiem w `dlaczego`.
   Uwaga: kod wyjścia liczy się po **kategorii**, więc taki wynik nadal daje `1` (obniżona jest tylko ważność i miejsce w "najpierw napraw").
6. **Dopasowanie plików kolumn.** Przy podanych `--tz-columns`/`--local-columns` podsumowanie ma linię
   `Kolumny z plików dopasowane w analizowanym SQL: systemowe X/Y, lokalne A/B` (także `kolumny_dopasowane` w JSON). Wpis `tabela.kolumna`
   liczy się, gdy tabela występuje w zapytaniu (też przez alias); wpis samej nazwy - gdy kolumna występuje gdziekolwiek. `0/N` oznacza
   plik kolumn niedopasowany do analizowanego kodu.

Ograniczenia dopisane w rundzie 2:
- Prefiks dokumentu rozpoznawany jest po kształcie (`[A-Z]{1,8}` + `/ - _ .`); prefiks z cyfrą (`"S3/"`) lub małymi literami nie jest widziany,
  więc taka numeracja bez nazwy zmiennej/kolumny sugerującej numer trafi do zwykłych kategorii (fałszywy negatyw `numbering_by_date`).
- Nazwy-podpowiedzi są dopasowywane po podciągu (`nr`, `seq`, `prefix`), więc zmienna `prefix_dir` ścieżki pliku z datą dałaby fałszywy `numbering_by_date`.
- Kolumna zapisu w `SET` jest rozpoznawana tylko dla `kol = NOW()...` bezpośrednio po `SET`/przecinku; zapis przez `CASE`/podzapytanie, `INSERT ... SELECT`
  i wielowierszowe `VALUES (...), (...)` (poza pierwszym wierszem) nie jest śledzony.
- Domyślny parametr (pkt 5) jest rozpoznawany tylko dla `.get(...)` w tym samym zakresie funkcji.

### Runda 3 (numeracja przez zmienną, warianty wartości domyślnej)

Testy: `tests/test_round3.py` (pisane przed zmianą kodu; 13 z nich padało). Razem 258 testów, golden odświeżony.

1. **`numbering_by_date` przez zmienną w tej samej funkcji.** `today = datetime.now()` / `d = date.today()` oraz wynik zapytania
   `SELECT CURRENT_DATE` / `SELECT now()` bez strefy (lista SELECT przed `FROM`; zmienna dostaje "źródło czasu" odtworzone z SQL)
   są śledzone po przypisaniach (`deps`, jak taint) i uznawane za numerację, gdy zmienna lub jej `.year`/`.month`/`strftime` trafia:
   - do f-stringa, `"..." .format(...)`, `"..." % (...)` lub konkatenacji z prefiksem dokumentu (`"FV/"`, `"ZAM/"`),
   - albo do celu przypisania/funkcji o nazwie pasującej do `numer|nr|number|seq|seria|prefix|numeracja|invoice|order_no`,
   - albo jako parametr SQL zapisywany/porównywany z kolumną o takiej nazwie (`SET order_no = %s`, `doc_number LIKE %s`,
     pozycja w `INSERT ... VALUES`); mapowanie jest na poziomie zapytania (jest taka kolumna + parametr pochodzi z roku/miesiąca/strftime),
     nie parametr-do-kolumny.
   Reguła formatu dla `strftime`/`:%Y` została rozluźniona z "rok i miesiąc" do "rok lub miesiąc", ale tylko w kontekście numeru
   (prefiks albo nazwa). Ta sama zmienna użyta tylko do logu/etykiety daje `py_naive_now_other`. Zmienna z innej funkcji nie jest śledzona
   (poza kopią środowiska modułu). Jedno trafienie `numbering_by_date` na linię i funkcję. Źródło z SQL nie daje własnego
   `py_naive_now_other`; sam `SELECT CURRENT_DATE` nadal jest `sql_current_date_utc`.
2. **Wartość domyślna parametru.** Podstawowy wzorzec (`x = request.args.get(..)`, `if not x: x = datetime.now().strftime(..)`)
   był obsłużony już w rundzie 2 (ważność średnia + dopisek w `dlaczego`); ta runda dodaje pominięte warianty, w których nadal wychodziła
   ważność wysoka: wartość domyślna w gałęzi `else` (`if x: ... else: x = now`), warunek `x is None or x == ""` (także `or`/`and`),
   `(a.get(..) or "").strip() or <teraz>`, `a[..] if .. else <teraz>`. Parametrem jest każda zmienna z `.get(...)` lub indeksowania.
   Test negatywny: wartość spoza `.get`/`[]` (np. `cache.compute()`) i bezwarunkowe `datetime.now()` w SQL zostają `wysoka`.

Ograniczenia/fałszywe trafienia dopisane w rundzie 3:
- Nazwa funkcji też jest podpowiedzią numeru: `def invoice_report(): return date.today().strftime("%Y")` da `numbering_by_date`.
- "Parametr" to dowolny `.get(...)`/`[...]`, także zwykły słownik; wartość domyślna z takiego słownika też dostanie ważność średnią.
- Kolumna numeru dla parametru SQL jest rozpoznawana dla całego zapytania, więc `SET order_no = %s, label = %s` z rokiem w `label` też da trafienie.
- Źródło z SQL rozpoznawane tylko dla `SELECT` z `CURRENT_DATE`/`now()` przed pierwszym `FROM`; przez podzapytania/CTE nie.

### Tryb frontendu: `--jezyk ts` (TypeScript / JavaScript / React)

```
python sql_timezone_audit.py --jezyk ts --backend src [--local-columns local.txt] [--tz-columns tz.txt] \
    [--baseline b.json] [--write-baseline b.json] [--files-from lista.txt] [--exclude wzorzec ...] \
    [--json raport.json] [--csv raport.csv]
```

Domyślnie (`--jezyk py`) nic się nie zmienia. `--src` jest aliasem `--backend`. Skanowane są `*.ts`, `*.tsx`, `*.js`, `*.jsx`;
domyślnie pomijane: `node_modules`, `dist`, `build`, `.next`, `out`, `coverage`, `.git`, `.turbo`, `.cache`, `__tests__`, `__mocks__`,
`tests`, `test`, `e2e`, `cypress` oraz pliki `*.test.*`, `*.spec.*`, `*.d.ts`, `*.min.js`, `*.stories.*`. Zero zależności: nie ma parsera TS,
więc analiza to leksyker (komentarze, napisy, szablony `${}`, regexy) + wyrażenia regularne na "szkielecie" kodu + proste śledzenie zmiennych
w obrębie zakresu funkcji. Pliki kolumn (`--local-columns`/`--tz-columns`, te same co dla SQL) służą tu jako lista **pól** (wpis `tabela.kolumna`
liczy się jako nazwa pola; `starts_at` = `startsAt` = `startsat`): pole z `--local-columns` jest "lokalne" (`likely`), z `--tz-columns` "systemowe";
bez plików działa heurystyka nazwy jak w SQL (`start*/end*/planned*/scheduled*/due*` → lokalne, `*At`, `*_at`, `timestamp`, `iso`, `utc` → timestamptz) i daje `uncertain`.

Wyniki mają: `plik:linia`, kod, ważność, pewność, **kontekst** (`komponent Foo`, `hook useBar`, `klient API fetchX`, `funkcja x`, `metoda Klasa.m`, `moduł`;
zagnieżdżone: `komponent Foo › handleSave`), fragment (maks. 120 znaków, wartości tekstowe zamaskowane), `dlaczego` i `podpowiedź` (wspólne helpery
`dzisWarszawa()` / `formatujDateWarszawa()` / `poczatekDobyWarszawa()`). Komentarz `// tz-ok: powód` (lub `/* tz-ok: powód */`) wyłącza linię, w której stoi;
komentarz sam w linii wyłącza tę linię i następną. Kod wyjścia: `1` gdy jest **nowy** wynik o ważności **wysokiej**, `0` w przeciwnym razie, `2` błąd użycia.
Baseline działa jak w trybie py (klucz: plik + kontekst + kod + znormalizowany fragment).

| Kod | Wzorzec | Ważność |
|-----|---------|---------|
| `ts_today_iso_slice` (1) | `new Date().toISOString().slice(0,10)` / `.split('T')[0]` / `.substring(0,10)` (też przez zmienną z "teraz" lub z `toISOString()`, oraz `new Date(r, m, d)` lokalna północ) | wysoka (odbiorca nieznany lub z API: średnia, `uncertain`) |
| `ts_date_only_parse` (2) | `new Date('YYYY-MM-DD')`, `Date.parse('YYYY-MM-DD')`, szablon `${y}-${m}-${d}`, zmienna ze `slice(0,10)` | średnia (tylko do wyświetlenia: niska) |
| `ts_locale_no_timezone` (3) | `toLocale(Date/Time)String`, `Intl.DateTimeFormat` bez `timeZone` | wysoka tylko dla wartości z `Z`/offsetem lub `toISOString()`; pole z nazwą timestamptz: średnia; pole typu date/lokalne: niska; `timeZone: 'UTC'` na timestamptz: średnia |
| `ts_local_getter_on_utc` (4) | `getDate/getMonth/getFullYear/getHours/...` na obiekcie z ISO UTC (literał z `Z`, `toISOString()`, pole `*At`) | średnia |
| `ts_string_date_compare` (5) | string `'YYYY-MM-DD'` (literał, zmienna, `slice(0,10)`) porównany z `Date`/`getTime()`/`Date.now()` | średnia |
| `ts_now_into_local_field` (6) | `new Date()` / `Date.now()` / `.toISOString()` "teraz" w polu lokalnym (`{ startsAt: ... }`, `obj.dueDate = ...`, `setFieldValue('startsAt', ...)`) | wysoka |
| `ts_startof_day_utc` (7) | `setHours(0,0,0,0)` / `setHours(23,59,59,999)` na dacie data-only/`Z`/`*At`; `setUTCHours(0,0,0,0)`; `dayjs.utc(..).startOf('day')`, `.utc().startOf('day')`, `moment('...Z').startOf('day')` | wysoka |
| `ts_manual_hour_shift` (8) | `+ 2 * 3600 * 1000`, `- 1 * 60 * 60 * 1000`, `7200000`, `3_600_000`, `setHours(getHours() + 2)` | średnia (`likely`, gdy linia zawiera offset/utc/warsaw/tz/local) |

Raport tekstowy ma macierz **liczby znalezisk wg kodu i ważności**; JSON (`"tryb": "ts"`) ma `podsumowanie.wg_kodu` (ważność × kod) i `wg_waznosci`;
CSV (`--csv`, UTF-8, LF, przecinek; **nowe także dla trybu py**, bo wcześniej CSV nie istniał) ma kolumny `plik,linia,kod,waznosc,pewnosc,kontekst,fragment,podpowiedz,dlaczego,nowy`.
Test jednostkowy: `tests/test_ts.py`, `tests/test_ts_cli.py`, golden `examples/EXPECTED_TS.md` dla fikcyjnego `examples/frontend`
(odświeżenie: `UPDATE_GOLDEN=1 python -m unittest tests.test_ts_golden`).

Decyzje i ograniczenia trybu ts:
- **Redukcja szumu.** `toLocaleString` jest zgłaszane tylko dla odbiorcy, który wygląda na datę (liczby i tablice też je mają); odbiorca nieznany
  daje najwyżej średnią `uncertain`; pole typu date i pole lokalne dają niską; `new Date(...)` z `'T..:..'` bez strefy oraz `new Date(r, m, d)` uznawane są za lokalne i pomijane.
  Śledzenie zmiennych obejmuje przypisania w tym samym zakresie funkcji (lub zewnętrznym); parametry funkcji i właściwości obiektów są klasyfikowane tylko po nazwie.
  Jedno trafienie na linię i kod. `Date.now() + N*3600*1000` jest pomijane, gdy linia wygląda na wygasanie/cache (`expir|ttl|timeout|delay|cache|debounce|interval|retry|maxAge|snooze|stale`).
- **Brak parsera.** Fałszywe trafienia/negatywy są możliwe przy: apostrofach w tekście JSX (niedomknięty napis kończy się z końcem linii), regexach po `)`, makrach i
  generykach TS w wyrażeniach porównań (`a < b > c`), wieloliniowych wyrażeniach z operatorami na początku linii, łańcuchach przez wiele wywołań pomocniczych.
  Zakresy (kontekst) są rozpoznawane dla `function`, `const x = (..) =>` (także w `memo/forwardRef/useCallback`), klas i metod; funkcje anonimowe należą do zakresu nadrzędnego.
- **Nie wykrywane:** `moment`/`dayjs`/`luxon`/`date-fns` poza `startOf('day')` (wzorzec 7); `Temporal`; daty przekazane do innych funkcji i formatowane gdzie indziej;
  `toLocale*` wywołane na wyniku funkcji o nieznanym typie zwracanym; JSON z datami zdefiniowany poza kodem.
- **Dwie ważności "wysoka" w innym sensie niż w py:** w trybie ts blokuje ważność (nie kategoria), więc wzorzec 3 na wartości bez `Z` nie psuje CI, a wzorzec 7 na polu `*At` z `uncertain` tak.
- Tryb ts jest w tym samym pliku `sql_timezone_audit.py` (jeden plik do skopiowania na Windows); ścieżki, UTF-8/LF i BOM/CRLF w źródłach obsługiwane jak w trybie py.

Otwarte pytania (ts): (1) czy wzorzec 7 na `*At` wyłącznie po nazwie powinien blokować CI; (2) czy `.mjs/.cjs` dołożyć do rozszerzeń; (3) czy `dzisWarszawa()` ma
być nazwą wymuszaną przez narzędzie (obecnie to tylko podpowiedź w tekście); (4) czy wzorzec 1 na nieznanym odbiorcy (np. wartość z datepickera) ma być `wysoka`.
