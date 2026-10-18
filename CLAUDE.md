# Zasady pracy — izolowane narzędzia ESFS (cloud session)

Ten projekt jest budowany przez Claude Code Cloud, odłączony od infrastruktury i baz
danych firmy ESFS. Poniższe zasady obowiązują dla każdego takiego zadania.

## 1. Zero danych firmowych
Zero prawdziwych nazw klientów/kontrahentów, NIP-ów, adresów, cen, nazw produktów,
haseł, adresów e-mail pracowników ani odniesień do konkretnych tabel/schematów bazy
ESFS. Wszystkie przykłady, fixture'y i dane testowe muszą być syntetyczne/fikcyjne.
Jeśli zadanie wymaga prawdziwych danych firmowych do sensownego działania — to zły
kandydat na to repo, zgłoś to zamiast zgadywać/fabrykować dane.

## 2. Sekrety tylko przez zmienne środowiskowe
Nigdy hardcode. Zawsze `.env.example` jako wzorzec + realny `.env` w `.gitignore`.

## 3. Testy obowiązkowe
Każda nietrywialna logika ma testy jednostkowe (poprzednie narzędzia w tej organizacji:
11–59 testów każde). Jeśli kod dotyka bazy danych, testy muszą działać BEZ prawdziwego
Postgresa (mock / sqlite / lekki fixture) — opisz w README jak je uruchomić.

## 4. README.md obowiązkowe
Cel projektu, jak uruchomić, jak (ewentualnie) zintegrować z prawdziwą aplikacją,
jakie są otwarte pytania/decyzje pozostawione do rozstrzygnięcia.

## 5. Nazwy schematów/tabel SQL
Unikaj nazw kolidujących z realnymi schematami ESFS: `hr`, `office`, `crm`,
`accounting`, `zakupy`, `config` są zajęte w produkcji. Użyj nazwy własnej projektu.

## 6. Branch → main
Pracuj na branchu z opisową nazwą, na koniec zmerguj do `main` (repo powinno mieć
`main` jako gałąź docelową po zakończeniu zadania).

## 7. Commity
Małe, opisowe kroki zamiast jednego ogromnego commita.
