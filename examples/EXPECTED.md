sql-timezone-audit - raport

Podsumowanie
------------
Przeanalizowane pliki: 11
Wywołania SQL: 31 (z funkcjami czasu: 28)
Wyniki: 36 (nowe: 36, znane z baseline: 0)
Nowe wyniki blokujące (kod wyjścia 1): 22
Zawężenie numbering_by_date: 3 wyników przestało być numbering_by_date (trafiają do zwykłych kategorii)
Kolumny z plików dopasowane w analizowanym SQL: systemowe 4/4, lokalne 3/4

Rozkład kategorii:
  sql_current_date_utc       wysoka     3
  sql_local_vs_now           wysoka     3
  sql_date_trunc_utc         wysoka     5
  sql_literal_boundary       srednia    3
  sql_fixed_offset           srednia    2
  sql_utc_into_local_column  wysoka     1
  py_naive_now               wysoka     4
  py_naive_now_other         informacja 5
  py_utcnow_deprecated       niska      3
  py_fixed_offset            srednia    1
  scheduler_no_timezone      wysoka     4
  numbering_by_date          wysoka     2

Najpierw napraw
---------------
1. orders.py:8  [numbering_by_date] wysoka/likely
    funkcja: next_order_number
    fragment: f"ZAM/{date.today():%Y/%m}/"
    dlaczego: Numer dokumentu budowany z naiwnej daty: na granicy miesiąca (po północy lokalnie) dostaje zły miesiąc.
    propozycja: Weź datę lokalną: (NOW() AT TIME ZONE 'Europe/Warsaw') w SQL lub datetime.now(ZoneInfo('Europe/Warsaw')).
2. orders.py:14  [numbering_by_date] wysoka/likely
    funkcja: next_invoice_number_sql  helper: query_one
    fragment: SELECT '?' || to_char(CURRENT_DATE, 'YYYY/MM') || '?'
    dlaczego: Numer dokumentu budowany z naiwnej daty: na granicy miesiąca (po północy lokalnie) dostaje zły miesiąc.
    propozycja: Weź datę lokalną: (NOW() AT TIME ZONE 'Europe/Warsaw') w SQL lub datetime.now(ZoneInfo('Europe/Warsaw')).
3. celery_tasks.py:5  [scheduler_no_timezone] wysoka/likely
    funkcja: <module>  helper: crontab
    fragment: crontab(hour=2, minute=0)
    dlaczego: Zadanie cron bez jawnej strefy odpala się w UTC, czyli godzinę lub dwie później niż zamierzono lokalnie.
    propozycja: Dodaj timezone='Europe/Warsaw' do wyzwalacza lub konfiguracji harmonogramu.
4. scheduler_jobs.py:16  [scheduler_no_timezone] wysoka/likely
    funkcja: <module>  helper: add_job
    fragment: scheduler.add_job(send_digest, "cron", hour=6, minute=30)
    dlaczego: Zadanie cron bez jawnej strefy odpala się w UTC, czyli godzinę lub dwie później niż zamierzono lokalnie.
    propozycja: Dodaj timezone='Europe/Warsaw' do wyzwalacza lub konfiguracji harmonogramu.
5. scheduler_jobs.py:19  [scheduler_no_timezone] wysoka/likely
    funkcja: <module>  helper: CronTrigger
    fragment: CronTrigger(hour=3)
    dlaczego: Zadanie cron bez jawnej strefy odpala się w UTC, czyli godzinę lub dwie później niż zamierzono lokalnie.
    propozycja: Dodaj timezone='Europe/Warsaw' do wyzwalacza lub konfiguracji harmonogramu.
6. scheduler_jobs.py:23  [scheduler_no_timezone] wysoka/likely
    funkcja: <module>  helper: scheduled_job
    fragment: scheduler.scheduled_job("cron", day_of_week="mon", hour=7)
    dlaczego: Zadanie cron bez jawnej strefy odpala się w UTC, czyli godzinę lub dwie później niż zamierzono lokalnie.
    propozycja: Dodaj timezone='Europe/Warsaw' do wyzwalacza lub konfiguracji harmonogramu.
7. shifts.py:27  [sql_utc_into_local_column] wysoka/likely
    funkcja: restart_shift  helper: execute
    fragment: UPDATE shifts SET starts_at = NOW() WHERE id = %s
    dlaczego: NOW()/CURRENT_TIMESTAMP (UTC) zapisywane do kolumny lokalnej (timestamp bez strefy): kolumna ma przechowywać czas ze ściany zegara, a dostaje UTC.
    propozycja: Zapisz NOW() AT TIME ZONE 'Europe/Warsaw' albo zmień kolumnę na timestamptz.
8. heuristics.py:16  [sql_current_date_utc] wysoka/likely
    funkcja: dynamic_sql  helper: query_all
    fragment: parts WHERE AND created_at::date = CURRENT_DATE
    dlaczego: CURRENT_DATE / now()::date liczone jest w strefie sesji bazy (UTC): między 00:00 a 02:00 czasu lokalnego to jeszcze "wczoraj".
    propozycja: Zastąp przez (NOW() AT TIME ZONE 'Europe/Warsaw')::date.
9. housekeeping.py:26  [sql_current_date_utc] wysoka/likely
    funkcja: birthday_customers  helper: query_all
    fragment: to_char(born_on, 'MM-DD') = to_char(CURRENT_DATE, 'MM-DD')
    dlaczego: CURRENT_DATE / now()::date liczone jest w strefie sesji bazy (UTC): między 00:00 a 02:00 czasu lokalnego to jeszcze "wczoraj".
    propozycja: Zastąp przez (NOW() AT TIME ZONE 'Europe/Warsaw')::date.
10. orders.py:18  [sql_current_date_utc] wysoka/likely
    funkcja: orders_today  helper: query_all
    fragment: id FROM orders WHERE created_at::date = CURRENT_DATE
    dlaczego: CURRENT_DATE / now()::date liczone jest w strefie sesji bazy (UTC): między 00:00 a 02:00 czasu lokalnego to jeszcze "wczoraj".
    propozycja: Zastąp przez (NOW() AT TIME ZONE 'Europe/Warsaw')::date.
11. shifts.py:8  [sql_local_vs_now] wysoka/likely
    funkcja: upcoming_shifts  helper: query_all
    fragment: WHERE starts_at BETWEEN NOW() AND NOW() + interval '1 day' ORDER
    dlaczego: Kolumna lokalna (timestamp bez strefy) porównywana z NOW(), które jest w UTC: okno przesunięte o 1-2 godziny.
    propozycja: Porównuj z NOW() AT TIME ZONE 'Europe/Warsaw'.
12. shifts.py:18  [sql_local_vs_now] wysoka/likely
    funkcja: late_shifts  helper: query_all
    fragment: SELECT id FROM shifts WHERE ends_at < CURRENT_TIMESTAMP
    dlaczego: Kolumna lokalna (timestamp bez strefy) porównywana z NOW(), które jest w UTC: okno przesunięte o 1-2 godziny.
    propozycja: Porównuj z NOW() AT TIME ZONE 'Europe/Warsaw'.
13. heuristics.py:16  [sql_date_trunc_utc] wysoka/likely
    funkcja: dynamic_sql  helper: query_all
    fragment: SELECT id FROM parts WHERE AND created_at::date = CURRENT_DATE
    dlaczego: Dzień/miesiąc liczony w UTC na kolumnie timestamptz: zdarzenie o 23:30 lokalnie ląduje w następnym dniu.
    propozycja: Dodaj AT TIME ZONE 'Europe/Warsaw' do kolumny, np. date_trunc('day', kol AT TIME ZONE 'Europe/Warsaw').
14. orders.py:18  [sql_date_trunc_utc] wysoka/likely
    funkcja: orders_today  helper: query_all
    fragment: SELECT id FROM orders WHERE created_at::date = CURRENT_DATE
    dlaczego: Dzień/miesiąc liczony w UTC na kolumnie timestamptz: zdarzenie o 23:30 lokalnie ląduje w następnym dniu.
    propozycja: Dodaj AT TIME ZONE 'Europe/Warsaw' do kolumny, np. date_trunc('day', kol AT TIME ZONE 'Europe/Warsaw').
15. reports.py:9  [sql_date_trunc_utc] wysoka/likely
    funkcja: daily_totals  helper: query_all
    fragment: SELECT date_trunc('day', created_at) AS d, count(*) FROM orders GROUP BY 1
    dlaczego: Dzień/miesiąc liczony w UTC na kolumnie timestamptz: zdarzenie o 23:30 lokalnie ląduje w następnym dniu.
    propozycja: Dodaj AT TIME ZONE 'Europe/Warsaw' do kolumny, np. date_trunc('day', kol AT TIME ZONE 'Europe/Warsaw').
16. reports.py:13  [sql_date_trunc_utc] wysoka/likely
    funkcja: monthly_hours  helper: query_all
    fragment: SELECT EXTRACT(HOUR FROM sent_at), count(*) FROM mails GROUP BY 1
    dlaczego: Dzień/miesiąc liczony w UTC na kolumnie timestamptz: zdarzenie o 23:30 lokalnie ląduje w następnym dniu.
    propozycja: Dodaj AT TIME ZONE 'Europe/Warsaw' do kolumny, np. date_trunc('day', kol AT TIME ZONE 'Europe/Warsaw').
17. reports.py:31  [sql_date_trunc_utc] wysoka/likely
    funkcja: by_alias  helper: query_all
    fragment: SELECT o.id FROM orders o WHERE DATE(o.paid_at) = %s
    dlaczego: Dzień/miesiąc liczony w UTC na kolumnie timestamptz: zdarzenie o 23:30 lokalnie ląduje w następnym dniu.
    propozycja: Dodaj AT TIME ZONE 'Europe/Warsaw' do kolumny, np. date_trunc('day', kol AT TIME ZONE 'Europe/Warsaw').
18. orders.py:26  [py_naive_now] wysoka/likely
    funkcja: close_overdue
    fragment: datetime.now()
    dlaczego: Naiwny "teraz/dziś" (bez tzinfo) trafia do SQL albo jest porównywany z wartością z bazy; w kontenerze to czas UTC.
    propozycja: Użyj datetime.now(ZoneInfo('Europe/Warsaw')) albo policz wartość w SQL z AT TIME ZONE.

Wyniki wg ważności
------------------

wysoka (21)
celery_tasks.py:5  [scheduler_no_timezone] wysoka/likely
    funkcja: <module>  helper: crontab
    fragment: crontab(hour=2, minute=0)
    dlaczego: Zadanie cron bez jawnej strefy odpala się w UTC, czyli godzinę lub dwie później niż zamierzono lokalnie.
    propozycja: Dodaj timezone='Europe/Warsaw' do wyzwalacza lub konfiguracji harmonogramu.
heuristics.py:6  [sql_local_vs_now] wysoka/uncertain
    funkcja: planned_today  helper: query_all
    fragment: id FROM deliveries WHERE planned_date < NOW()
    dlaczego: Kolumna lokalna (timestamp bez strefy) porównywana z NOW(), które jest w UTC: okno przesunięte o 1-2 godziny.
    propozycja: Porównuj z NOW() AT TIME ZONE 'Europe/Warsaw'.
heuristics.py:16  [sql_current_date_utc] wysoka/likely
    funkcja: dynamic_sql  helper: query_all
    fragment: parts WHERE AND created_at::date = CURRENT_DATE
    dlaczego: CURRENT_DATE / now()::date liczone jest w strefie sesji bazy (UTC): między 00:00 a 02:00 czasu lokalnego to jeszcze "wczoraj".
    propozycja: Zastąp przez (NOW() AT TIME ZONE 'Europe/Warsaw')::date.
heuristics.py:16  [sql_date_trunc_utc] wysoka/likely
    funkcja: dynamic_sql  helper: query_all
    fragment: SELECT id FROM parts WHERE AND created_at::date = CURRENT_DATE
    dlaczego: Dzień/miesiąc liczony w UTC na kolumnie timestamptz: zdarzenie o 23:30 lokalnie ląduje w następnym dniu.
    propozycja: Dodaj AT TIME ZONE 'Europe/Warsaw' do kolumny, np. date_trunc('day', kol AT TIME ZONE 'Europe/Warsaw').
housekeeping.py:26  [sql_current_date_utc] wysoka/likely
    funkcja: birthday_customers  helper: query_all
    fragment: to_char(born_on, 'MM-DD') = to_char(CURRENT_DATE, 'MM-DD')
    dlaczego: CURRENT_DATE / now()::date liczone jest w strefie sesji bazy (UTC): między 00:00 a 02:00 czasu lokalnego to jeszcze "wczoraj".
    propozycja: Zastąp przez (NOW() AT TIME ZONE 'Europe/Warsaw')::date.
legacy_time.py:9  [py_naive_now] wysoka/uncertain
    funkcja: stamp_event
    fragment: dt.utcnow()
    dlaczego: Naiwny "teraz/dziś" (bez tzinfo) trafia do SQL albo jest porównywany z wartością z bazy; w kontenerze to czas UTC.
    propozycja: Użyj datetime.now(ZoneInfo('Europe/Warsaw')) albo policz wartość w SQL z AT TIME ZONE.
orders.py:8  [numbering_by_date] wysoka/likely
    funkcja: next_order_number
    fragment: f"ZAM/{date.today():%Y/%m}/"
    dlaczego: Numer dokumentu budowany z naiwnej daty: na granicy miesiąca (po północy lokalnie) dostaje zły miesiąc.
    propozycja: Weź datę lokalną: (NOW() AT TIME ZONE 'Europe/Warsaw') w SQL lub datetime.now(ZoneInfo('Europe/Warsaw')).
orders.py:14  [numbering_by_date] wysoka/likely
    funkcja: next_invoice_number_sql  helper: query_one
    fragment: SELECT '?' || to_char(CURRENT_DATE, 'YYYY/MM') || '?'
    dlaczego: Numer dokumentu budowany z naiwnej daty: na granicy miesiąca (po północy lokalnie) dostaje zły miesiąc.
    propozycja: Weź datę lokalną: (NOW() AT TIME ZONE 'Europe/Warsaw') w SQL lub datetime.now(ZoneInfo('Europe/Warsaw')).
orders.py:18  [sql_current_date_utc] wysoka/likely
    funkcja: orders_today  helper: query_all
    fragment: id FROM orders WHERE created_at::date = CURRENT_DATE
    dlaczego: CURRENT_DATE / now()::date liczone jest w strefie sesji bazy (UTC): między 00:00 a 02:00 czasu lokalnego to jeszcze "wczoraj".
    propozycja: Zastąp przez (NOW() AT TIME ZONE 'Europe/Warsaw')::date.
orders.py:18  [sql_date_trunc_utc] wysoka/likely
    funkcja: orders_today  helper: query_all
    fragment: SELECT id FROM orders WHERE created_at::date = CURRENT_DATE
    dlaczego: Dzień/miesiąc liczony w UTC na kolumnie timestamptz: zdarzenie o 23:30 lokalnie ląduje w następnym dniu.
    propozycja: Dodaj AT TIME ZONE 'Europe/Warsaw' do kolumny, np. date_trunc('day', kol AT TIME ZONE 'Europe/Warsaw').
orders.py:26  [py_naive_now] wysoka/likely
    funkcja: close_overdue
    fragment: datetime.now()
    dlaczego: Naiwny "teraz/dziś" (bez tzinfo) trafia do SQL albo jest porównywany z wartością z bazy; w kontenerze to czas UTC.
    propozycja: Użyj datetime.now(ZoneInfo('Europe/Warsaw')) albo policz wartość w SQL z AT TIME ZONE.
orders.py:32  [py_naive_now] wysoka/uncertain
    funkcja: is_overdue
    fragment: datetime.now()
    dlaczego: Naiwny "teraz/dziś" (bez tzinfo) trafia do SQL albo jest porównywany z wartością z bazy; w kontenerze to czas UTC.
    propozycja: Użyj datetime.now(ZoneInfo('Europe/Warsaw')) albo policz wartość w SQL z AT TIME ZONE.
reports.py:9  [sql_date_trunc_utc] wysoka/likely
    funkcja: daily_totals  helper: query_all
    fragment: SELECT date_trunc('day', created_at) AS d, count(*) FROM orders GROUP BY 1
    dlaczego: Dzień/miesiąc liczony w UTC na kolumnie timestamptz: zdarzenie o 23:30 lokalnie ląduje w następnym dniu.
    propozycja: Dodaj AT TIME ZONE 'Europe/Warsaw' do kolumny, np. date_trunc('day', kol AT TIME ZONE 'Europe/Warsaw').
reports.py:13  [sql_date_trunc_utc] wysoka/likely
    funkcja: monthly_hours  helper: query_all
    fragment: SELECT EXTRACT(HOUR FROM sent_at), count(*) FROM mails GROUP BY 1
    dlaczego: Dzień/miesiąc liczony w UTC na kolumnie timestamptz: zdarzenie o 23:30 lokalnie ląduje w następnym dniu.
    propozycja: Dodaj AT TIME ZONE 'Europe/Warsaw' do kolumny, np. date_trunc('day', kol AT TIME ZONE 'Europe/Warsaw').
reports.py:31  [sql_date_trunc_utc] wysoka/likely
    funkcja: by_alias  helper: query_all
    fragment: SELECT o.id FROM orders o WHERE DATE(o.paid_at) = %s
    dlaczego: Dzień/miesiąc liczony w UTC na kolumnie timestamptz: zdarzenie o 23:30 lokalnie ląduje w następnym dniu.
    propozycja: Dodaj AT TIME ZONE 'Europe/Warsaw' do kolumny, np. date_trunc('day', kol AT TIME ZONE 'Europe/Warsaw').
scheduler_jobs.py:16  [scheduler_no_timezone] wysoka/likely
    funkcja: <module>  helper: add_job
    fragment: scheduler.add_job(send_digest, "cron", hour=6, minute=30)
    dlaczego: Zadanie cron bez jawnej strefy odpala się w UTC, czyli godzinę lub dwie później niż zamierzono lokalnie.
    propozycja: Dodaj timezone='Europe/Warsaw' do wyzwalacza lub konfiguracji harmonogramu.
scheduler_jobs.py:19  [scheduler_no_timezone] wysoka/likely
    funkcja: <module>  helper: CronTrigger
    fragment: CronTrigger(hour=3)
    dlaczego: Zadanie cron bez jawnej strefy odpala się w UTC, czyli godzinę lub dwie później niż zamierzono lokalnie.
    propozycja: Dodaj timezone='Europe/Warsaw' do wyzwalacza lub konfiguracji harmonogramu.
scheduler_jobs.py:23  [scheduler_no_timezone] wysoka/likely
    funkcja: <module>  helper: scheduled_job
    fragment: scheduler.scheduled_job("cron", day_of_week="mon", hour=7)
    dlaczego: Zadanie cron bez jawnej strefy odpala się w UTC, czyli godzinę lub dwie później niż zamierzono lokalnie.
    propozycja: Dodaj timezone='Europe/Warsaw' do wyzwalacza lub konfiguracji harmonogramu.
shifts.py:8  [sql_local_vs_now] wysoka/likely
    funkcja: upcoming_shifts  helper: query_all
    fragment: WHERE starts_at BETWEEN NOW() AND NOW() + interval '1 day' ORDER
    dlaczego: Kolumna lokalna (timestamp bez strefy) porównywana z NOW(), które jest w UTC: okno przesunięte o 1-2 godziny.
    propozycja: Porównuj z NOW() AT TIME ZONE 'Europe/Warsaw'.
shifts.py:18  [sql_local_vs_now] wysoka/likely
    funkcja: late_shifts  helper: query_all
    fragment: SELECT id FROM shifts WHERE ends_at < CURRENT_TIMESTAMP
    dlaczego: Kolumna lokalna (timestamp bez strefy) porównywana z NOW(), które jest w UTC: okno przesunięte o 1-2 godziny.
    propozycja: Porównuj z NOW() AT TIME ZONE 'Europe/Warsaw'.
shifts.py:27  [sql_utc_into_local_column] wysoka/likely
    funkcja: restart_shift  helper: execute
    fragment: UPDATE shifts SET starts_at = NOW() WHERE id = %s
    dlaczego: NOW()/CURRENT_TIMESTAMP (UTC) zapisywane do kolumny lokalnej (timestamp bez strefy): kolumna ma przechowywać czas ze ściany zegara, a dostaje UTC.
    propozycja: Zapisz NOW() AT TIME ZONE 'Europe/Warsaw' albo zmień kolumnę na timestamptz.

srednia (7)
heuristics.py:10  [sql_literal_boundary] srednia/uncertain
    funkcja: built_sql  helper: query_all
    fragment: SELECT id FROM WHERE delivered_at >= '2026-10-01'
    dlaczego: Kolumna timestamptz porównywana z literałem daty/czasu bez strefy: granica doby wypada w UTC, nie lokalnie.
    propozycja: Zapisz granicę jako ('2026-10-01'::timestamp AT TIME ZONE 'Europe/Warsaw').
notifications.py:8  [sql_fixed_offset] srednia/uncertain
    funkcja: shifted_sql  helper: query_all
    fragment: SELECT sent_at + interval '2 hours' FROM mails
    dlaczego: Sztywne przesunięcie godzinowe psuje się przy zmianie czasu (ostatnie niedziele marca i października).
    propozycja: Zamień przesunięcie na AT TIME ZONE 'Europe/Warsaw'.
notifications.py:12  [sql_fixed_offset] srednia/likely
    funkcja: zone_offset_sql  helper: query_all
    fragment: SELECT created_at AT TIME ZONE '+02' FROM orders
    dlaczego: Sztywne przesunięcie godzinowe psuje się przy zmianie czasu (ostatnie niedziele marca i października).
    propozycja: Zamień przesunięcie na AT TIME ZONE 'Europe/Warsaw'.
notifications.py:20  [py_fixed_offset] srednia/uncertain
    funkcja: local_now_py
    fragment: datetime.utcnow() + timedelta(hours=2)
    dlaczego: Sztywne timedelta(hours=1|2) dodawane do bieżącego czasu psuje się przy zmianie czasu letni/zimowy.
    propozycja: Przelicz strefą (ZoneInfo('Europe/Warsaw')) zamiast stałego przesunięcia.
reports.py:18  [sql_literal_boundary] srednia/likely
    funkcja: october_orders  helper: query_all
    fragment: SELECT id FROM orders WHERE created_at >= '2026-10-01' AND created_at < '2026-11-01'
    dlaczego: Kolumna timestamptz porównywana z literałem daty/czasu bez strefy: granica doby wypada w UTC, nie lokalnie.
    propozycja: Zapisz granicę jako ('2026-10-01'::timestamp AT TIME ZONE 'Europe/Warsaw').
reports.py:18  [sql_literal_boundary] srednia/likely
    funkcja: october_orders  helper: query_all
    fragment: WHERE created_at >= '2026-10-01' AND created_at < '2026-11-01'
    dlaczego: Kolumna timestamptz porównywana z literałem daty/czasu bez strefy: granica doby wypada w UTC, nie lokalnie.
    propozycja: Zapisz granicę jako ('2026-10-01'::timestamp AT TIME ZONE 'Europe/Warsaw').
reports.py:38  [py_naive_now] srednia/likely
    funkcja: monthly_report
    fragment: datetime.now()
    dlaczego: Naiwny "teraz/dziś" (bez tzinfo) trafia do SQL albo jest porównywany z wartością z bazy; w kontenerze to czas UTC. To wartość domyślna parametru zapytania (np. miesiąc/dzień, gdy nie podano): błąd widać tylko tuż po północy czasu lokalnego.
    propozycja: Użyj datetime.now(ZoneInfo('Europe/Warsaw')) albo policz wartość w SQL z AT TIME ZONE.

niska (3)
legacy_time.py:9  [py_utcnow_deprecated] niska/likely
    funkcja: stamp_event
    fragment: dt.utcnow()
    dlaczego: datetime.utcnow() / utcfromtimestamp() jest przestarzałe od Pythona 3.12 i zwraca obiekt naiwny.
    propozycja: Użyj datetime.now(timezone.utc).
legacy_time.py:23  [py_utcnow_deprecated] niska/likely
    funkcja: from_epoch
    fragment: dt.utcfromtimestamp(value)
    dlaczego: datetime.utcnow() / utcfromtimestamp() jest przestarzałe od Pythona 3.12 i zwraca obiekt naiwny.
    propozycja: Użyj datetime.now(timezone.utc).
notifications.py:20  [py_utcnow_deprecated] niska/likely
    funkcja: local_now_py
    fragment: datetime.utcnow()
    dlaczego: datetime.utcnow() / utcfromtimestamp() jest przestarzałe od Pythona 3.12 i zwraca obiekt naiwny.
    propozycja: Użyj datetime.now(timezone.utc).

informacja (5)
housekeeping.py:9  [py_naive_now_other] informacja/uncertain
    funkcja: export_name
    fragment: date.today()
    dlaczego: Naiwny "teraz/dziś" (bez tzinfo); nie ustalono użycia w SQL (log, nazwa pliku, test?).
    propozycja: Jeśli wartość trafia do danych biznesowych, podaj jawną strefę (ZoneInfo('Europe/Warsaw')).
housekeeping.py:13  [py_naive_now_other] informacja/uncertain
    funkcja: log_start
    fragment: datetime.now()
    dlaczego: Naiwny "teraz/dziś" (bez tzinfo); nie ustalono użycia w SQL (log, nazwa pliku, test?).
    propozycja: Jeśli wartość trafia do danych biznesowych, podaj jawną strefę (ZoneInfo('Europe/Warsaw')).
housekeeping.py:22  [py_naive_now_other] informacja/uncertain
    funkcja: storage_key
    fragment: date.today()
    dlaczego: Naiwny "teraz/dziś" (bez tzinfo); nie ustalono użycia w SQL (log, nazwa pliku, test?).
    propozycja: Jeśli wartość trafia do danych biznesowych, podaj jawną strefę (ZoneInfo('Europe/Warsaw')).
legacy_time.py:23  [py_naive_now_other] informacja/uncertain
    funkcja: from_epoch
    fragment: dt.utcfromtimestamp(value)
    dlaczego: Naiwny "teraz/dziś" (bez tzinfo); nie ustalono użycia w SQL (log, nazwa pliku, test?).
    propozycja: Jeśli wartość trafia do danych biznesowych, podaj jawną strefę (ZoneInfo('Europe/Warsaw')).
notifications.py:20  [py_naive_now_other] informacja/uncertain
    funkcja: local_now_py
    fragment: datetime.utcnow()
    dlaczego: Naiwny "teraz/dziś" (bez tzinfo); nie ustalono użycia w SQL (log, nazwa pliku, test?).
    propozycja: Jeśli wartość trafia do danych biznesowych, podaj jawną strefę (ZoneInfo('Europe/Warsaw')).

Rozkład per plik
----------------
plik                  sql   sql+czas  wyniki
celery_tasks.py         0          0       1
db.py                   0          0       0
heuristics.py           3          3       4
housekeeping.py         1          1       4
legacy_time.py          2          0       4
notifications.py        3          3       5
orders.py               6          5       6
reports.py              7          7       6
scheduler_jobs.py       0          0       3
shifts.py               5          5       3
timeutils.py            4          4       0
