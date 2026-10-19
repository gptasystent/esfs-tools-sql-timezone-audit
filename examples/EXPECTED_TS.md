sql-timezone-audit - raport (TypeScript/JavaScript)

Podsumowanie
------------
Przeanalizowane pliki: 6
Wyniki: 17 (nowe: 17, znane z baseline: 0)
Nowe wyniki blokujące - ważność wysoka (kod wyjścia 1): 8

Liczba znalezisk wg kodu i ważności:
  kod                      wysoka srednia niska informacja  razem
  ts_today_iso_slice            2       0     0          0      2
  ts_date_only_parse            0       2     1          0      3
  ts_locale_no_timezone         1       1     1          0      3
  ts_local_getter_on_utc        0       1     0          0      1
  ts_string_date_compare        0       1     0          0      1
  ts_now_into_local_field       3       0     0          0      3
  ts_startof_day_utc            2       0     0          0      2
  ts_manual_hour_shift          0       2     0          0      2
  RAZEM                         8       7     2          0     17

Najpierw napraw
---------------
1. src/api/orders.ts:4  [ts_today_iso_slice] wysoka/likely
    kontekst: klient API fetchTodayOrders
    fragment: const today = new Date().toISOString().slice(0, 10);
    dlaczego: toISOString() zwraca datę UTC: w nocy (do 01:00/02:00 w Polsce) "dzisiejsza data" to jeszcze wczoraj; data lokalna (np. północ z datepickera) przesuwa się o dzień wstecz.
    podpowiedź: Użyj wspólnego helpera dzisWarszawa(), np. new Intl.DateTimeFormat('sv-SE', { timeZone: 'Europe/Warsaw' }).format(new Date()) daje YYYY-MM-DD.
2. src/api/orders.ts:16  [ts_startof_day_utc] wysoka/likely
    kontekst: klient API fetchOrdersSince
    fragment: stamp.setHours(0, 0, 0, 0);
    dlaczego: Początek/koniec doby liczony na dacie pochodzącej z UTC (data-only, ISO z 'Z', .utc()) wyznacza granicę doby w UTC zamiast w Warszawie: filtry zakresu gubią lub dublują godziny przy północy.
    podpowiedź: Policz granice doby w Warszawie (poczatekDobyWarszawa(data)) i dopiero potem zamień na UTC.
3. src/api/orders.ts:21  [ts_now_into_local_field] wysoka/likely
    kontekst: klient API scheduleShift
    fragment: return post('???????', { note, startsAt: new Date().toISOString(), createdAt: new Date().toISOString() });
    dlaczego: Bieżący czas UTC (toISOString() z 'Z' / Date.now()) trafia do pola typu timestamp bez strefy, które ma przechowywać czas lokalny (ze ściany zegara).
    podpowiedź: Wyślij czas lokalny bez 'Z' (formatujDateWarszawa()) albo niech czas ustawi serwer; nie wysyłaj UTC do kolumny lokalnej.
4. src/components/OrderList.tsx:15  [ts_locale_no_timezone] wysoka/likely
    kontekst: komponent OrderList
    fragment: <span>{new Date('2026-10-19T10:00:00Z').toLocaleTimeString('pl-PL')}</span>
    dlaczego: toLocale*String / Intl.DateTimeFormat bez timeZone pokazują czas w strefie przeglądarki, nie firmy; dla wartości z timestamptz (ISO z 'Z') data i godzina mogą się różnić o 1-2 godziny.
    podpowiedź: Podaj { timeZone: 'Europe/Warsaw' } albo użyj wspólnego helpera formatujDateWarszawa(wartosc).
5. src/components/ShiftForm.tsx:6  [ts_now_into_local_field] wysoka/likely
    kontekst: komponent ShiftForm › save
    fragment: send({ scheduledFor: new Date().toISOString() });
    dlaczego: Bieżący czas UTC (toISOString() z 'Z' / Date.now()) trafia do pola typu timestamp bez strefy, które ma przechowywać czas lokalny (ze ściany zegara).
    podpowiedź: Wyślij czas lokalny bez 'Z' (formatujDateWarszawa()) albo niech czas ustawi serwer; nie wysyłaj UTC do kolumny lokalnej.
6. src/components/ShiftForm.tsx:7  [ts_now_into_local_field] wysoka/likely
    kontekst: komponent ShiftForm › save
    fragment: send({ dueDate: Date.now() });
    dlaczego: Bieżący czas UTC (toISOString() z 'Z' / Date.now()) trafia do pola typu timestamp bez strefy, które ma przechowywać czas lokalny (ze ściany zegara).
    podpowiedź: Wyślij czas lokalny bez 'Z' (formatujDateWarszawa()) albo niech czas ustawi serwer; nie wysyłaj UTC do kolumny lokalnej.
7. src/components/ShiftForm.tsx:9  [ts_startof_day_utc] wysoka/likely
    kontekst: komponent ShiftForm
    fragment: const dayStart = dayjs.utc('2026-10-19T22:00:00Z').startOf('day');
    dlaczego: Początek/koniec doby liczony na dacie pochodzącej z UTC (data-only, ISO z 'Z', .utc()) wyznacza granicę doby w UTC zamiast w Warszawie: filtry zakresu gubią lub dublują godziny przy północy. Obiekt jest w trybie UTC (.utc()).
    podpowiedź: Policz granice doby w Warszawie (poczatekDobyWarszawa(data)) i dopiero potem zamień na UTC.
8. src/hooks/useToday.ts:3  [ts_today_iso_slice] wysoka/likely
    kontekst: hook useToday
    fragment: export const useToday = () => useMemo(() => new Date().toISOString().split('T')[0], []);
    dlaczego: toISOString() zwraca datę UTC: w nocy (do 01:00/02:00 w Polsce) "dzisiejsza data" to jeszcze wczoraj; data lokalna (np. północ z datepickera) przesuwa się o dzień wstecz.
    podpowiedź: Użyj wspólnego helpera dzisWarszawa(), np. new Intl.DateTimeFormat('sv-SE', { timeZone: 'Europe/Warsaw' }).format(new Date()) daje YYYY-MM-DD.

Wyniki wg ważności
------------------

wysoka (8)
src/api/orders.ts:4  [ts_today_iso_slice] wysoka/likely
    kontekst: klient API fetchTodayOrders
    fragment: const today = new Date().toISOString().slice(0, 10);
    dlaczego: toISOString() zwraca datę UTC: w nocy (do 01:00/02:00 w Polsce) "dzisiejsza data" to jeszcze wczoraj; data lokalna (np. północ z datepickera) przesuwa się o dzień wstecz.
    podpowiedź: Użyj wspólnego helpera dzisWarszawa(), np. new Intl.DateTimeFormat('sv-SE', { timeZone: 'Europe/Warsaw' }).format(new Date()) daje YYYY-MM-DD.
src/api/orders.ts:16  [ts_startof_day_utc] wysoka/likely
    kontekst: klient API fetchOrdersSince
    fragment: stamp.setHours(0, 0, 0, 0);
    dlaczego: Początek/koniec doby liczony na dacie pochodzącej z UTC (data-only, ISO z 'Z', .utc()) wyznacza granicę doby w UTC zamiast w Warszawie: filtry zakresu gubią lub dublują godziny przy północy.
    podpowiedź: Policz granice doby w Warszawie (poczatekDobyWarszawa(data)) i dopiero potem zamień na UTC.
src/api/orders.ts:21  [ts_now_into_local_field] wysoka/likely
    kontekst: klient API scheduleShift
    fragment: return post('???????', { note, startsAt: new Date().toISOString(), createdAt: new Date().toISOString() });
    dlaczego: Bieżący czas UTC (toISOString() z 'Z' / Date.now()) trafia do pola typu timestamp bez strefy, które ma przechowywać czas lokalny (ze ściany zegara).
    podpowiedź: Wyślij czas lokalny bez 'Z' (formatujDateWarszawa()) albo niech czas ustawi serwer; nie wysyłaj UTC do kolumny lokalnej.
src/components/OrderList.tsx:15  [ts_locale_no_timezone] wysoka/likely
    kontekst: komponent OrderList
    fragment: <span>{new Date('2026-10-19T10:00:00Z').toLocaleTimeString('pl-PL')}</span>
    dlaczego: toLocale*String / Intl.DateTimeFormat bez timeZone pokazują czas w strefie przeglądarki, nie firmy; dla wartości z timestamptz (ISO z 'Z') data i godzina mogą się różnić o 1-2 godziny.
    podpowiedź: Podaj { timeZone: 'Europe/Warsaw' } albo użyj wspólnego helpera formatujDateWarszawa(wartosc).
src/components/ShiftForm.tsx:6  [ts_now_into_local_field] wysoka/likely
    kontekst: komponent ShiftForm › save
    fragment: send({ scheduledFor: new Date().toISOString() });
    dlaczego: Bieżący czas UTC (toISOString() z 'Z' / Date.now()) trafia do pola typu timestamp bez strefy, które ma przechowywać czas lokalny (ze ściany zegara).
    podpowiedź: Wyślij czas lokalny bez 'Z' (formatujDateWarszawa()) albo niech czas ustawi serwer; nie wysyłaj UTC do kolumny lokalnej.
src/components/ShiftForm.tsx:7  [ts_now_into_local_field] wysoka/likely
    kontekst: komponent ShiftForm › save
    fragment: send({ dueDate: Date.now() });
    dlaczego: Bieżący czas UTC (toISOString() z 'Z' / Date.now()) trafia do pola typu timestamp bez strefy, które ma przechowywać czas lokalny (ze ściany zegara).
    podpowiedź: Wyślij czas lokalny bez 'Z' (formatujDateWarszawa()) albo niech czas ustawi serwer; nie wysyłaj UTC do kolumny lokalnej.
src/components/ShiftForm.tsx:9  [ts_startof_day_utc] wysoka/likely
    kontekst: komponent ShiftForm
    fragment: const dayStart = dayjs.utc('2026-10-19T22:00:00Z').startOf('day');
    dlaczego: Początek/koniec doby liczony na dacie pochodzącej z UTC (data-only, ISO z 'Z', .utc()) wyznacza granicę doby w UTC zamiast w Warszawie: filtry zakresu gubią lub dublują godziny przy północy. Obiekt jest w trybie UTC (.utc()).
    podpowiedź: Policz granice doby w Warszawie (poczatekDobyWarszawa(data)) i dopiero potem zamień na UTC.
src/hooks/useToday.ts:3  [ts_today_iso_slice] wysoka/likely
    kontekst: hook useToday
    fragment: export const useToday = () => useMemo(() => new Date().toISOString().split('T')[0], []);
    dlaczego: toISOString() zwraca datę UTC: w nocy (do 01:00/02:00 w Polsce) "dzisiejsza data" to jeszcze wczoraj; data lokalna (np. północ z datepickera) przesuwa się o dzień wstecz.
    podpowiedź: Użyj wspólnego helpera dzisWarszawa(), np. new Intl.DateTimeFormat('sv-SE', { timeZone: 'Europe/Warsaw' }).format(new Date()) daje YYYY-MM-DD.

srednia (7)
src/components/DeliveryFilter.tsx:5  [ts_date_only_parse] srednia/likely
    kontekst: komponent DeliveryFilter
    fragment: const limit = new Date('2026-10-19');
    dlaczego: Data bez czasu ('YYYY-MM-DD') jest parsowana jako północ UTC, a nie lokalna: porównania z lokalnym "dziś" i granice doby są błędne.
    podpowiedź: Parsuj lokalnie: new Date(rok, miesiac - 1, dzien), albo trzymaj datę jako string 'YYYY-MM-DD' i porównuj ze stringiem z dzisWarszawa().
src/components/DeliveryFilter.tsx:7  [ts_string_date_compare] srednia/likely
    kontekst: komponent DeliveryFilter
    fragment: const lateText = '2026-10-19' < new Date();
    dlaczego: Data jako string 'YYYY-MM-DD' porównywana z obiektem Date (lub jego liczbą): porównanie typów mieszanych daje wynik zależny od koercji i strefy.
    podpowiedź: Porównuj tę samą reprezentację: dwa stringi YYYY-MM-DD (z dzisWarszawa()) albo dwa Date (getTime()).
src/components/DeliveryFilter.tsx:9  [ts_date_only_parse] srednia/likely
    kontekst: komponent DeliveryFilter
    fragment: const parsed = Date.parse('2026-10-20');
    dlaczego: Data bez czasu ('YYYY-MM-DD') jest parsowana jako północ UTC, a nie lokalna: porównania z lokalnym "dziś" i granice doby są błędne.
    podpowiedź: Parsuj lokalnie: new Date(rok, miesiac - 1, dzien), albo trzymaj datę jako string 'YYYY-MM-DD' i porównuj ze stringiem z dzisWarszawa().
src/components/OrderList.tsx:11  [ts_local_getter_on_utc] srednia/likely
    kontekst: komponent OrderList
    fragment: const hour = created.getHours();
    dlaczego: getDate()/getMonth()/getFullYear()/getHours() zwracają części daty w strefie przeglądarki, a obiekt pochodzi z ISO UTC (timestamptz): wynik zależy od strefy użytkownika, nie firmy.
    podpowiedź: Pobierz części daty przez formatujDateWarszawa() / Intl.DateTimeFormat z timeZone: 'Europe/Warsaw'.
src/components/OrderList.tsx:14  [ts_locale_no_timezone] srednia/likely
    kontekst: komponent OrderList
    fragment: <span>{created.toLocaleString('pl-PL')}</span>
    dlaczego: toLocale*String / Intl.DateTimeFormat bez timeZone pokazują czas w strefie przeglądarki, nie firmy; dla wartości z timestamptz (ISO z 'Z') data i godzina mogą się różnić o 1-2 godziny.
    podpowiedź: Podaj { timeZone: 'Europe/Warsaw' } albo użyj wspólnego helpera formatujDateWarszawa(wartosc).
src/hooks/useToday.ts:7  [ts_manual_hour_shift] srednia/uncertain
    kontekst: hook useShiftEnd
    fragment: const end = new Date(base.getTime() + 2 * 3600 * 1000);
    dlaczego: Ręczne dodawanie/odejmowanie 1-2 godzin psuje się przy zmianie czasu (ostatnie niedziele marca i października).
    podpowiedź: Nie przesuwaj o stałą liczbę godzin; przelicz strefą Europe/Warsaw (Intl / date-fns-tz).
src/hooks/useToday.ts:8  [ts_manual_hour_shift] srednia/likely
    kontekst: hook useShiftEnd
    fragment: const warsawOffset = new Date(base.getTime() - 3600000);
    dlaczego: Ręczne dodawanie/odejmowanie 1-2 godzin psuje się przy zmianie czasu (ostatnie niedziele marca i października).
    podpowiedź: Nie przesuwaj o stałą liczbę godzin; przelicz strefą Europe/Warsaw (Intl / date-fns-tz).

niska (2)
src/components/DeliveryFilter.tsx:8  [ts_date_only_parse] niska/likely
    kontekst: komponent DeliveryFilter
    fragment: const label = new Date('2026-10-19').toLocaleDateString('pl-PL');
    dlaczego: Data bez czasu ('YYYY-MM-DD') jest parsowana jako północ UTC, a nie lokalna: porównania z lokalnym "dziś" i granice doby są błędne. Użyte tylko do wyświetlenia (w Polsce data wyświetli się poprawnie).
    podpowiedź: Parsuj lokalnie: new Date(rok, miesiac - 1, dzien), albo trzymaj datę jako string 'YYYY-MM-DD' i porównuj ze stringiem z dzisWarszawa().
src/components/OrderList.tsx:16  [ts_locale_no_timezone] niska/uncertain
    kontekst: komponent OrderList
    fragment: <span>{new Date(o.dueDate).toLocaleDateString('pl-PL')}</span>
    dlaczego: toLocale*String / Intl.DateTimeFormat bez timeZone pokazują czas w strefie przeglądarki, nie firmy; dla wartości z timestamptz (ISO z 'Z') data i godzina mogą się różnić o 1-2 godziny. Pole lokalne (timestamp bez strefy / data) - niskie ryzyko.
    podpowiedź: Podaj { timeZone: 'Europe/Warsaw' } albo użyj wspólnego helpera formatujDateWarszawa(wartosc).

informacja (0)

Rozkład per plik
----------------
plik                               wyniki
src/api/orders.ts                       3
src/components/DeliveryFilter.tsx       4
src/components/OrderList.tsx            4
src/components/ShiftForm.tsx            3
src/hooks/useToday.ts                   3
src/lib/dates.ts                        0
