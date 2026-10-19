"""Tryb --jezyk ts: fikcyjne fragmenty frontendu (sklep z częściami), trafienia i NIE-trafienia."""
import textwrap
import unittest

import sql_timezone_audit as sta


def ts(src, plik="src/Widget.tsx", lokalne=(), systemowe=()):
    a = sta.AnalizatorTs(textwrap.dedent(src), plik, sta.pola_z_wpisow(lokalne), sta.pola_z_wpisow(systemowe))
    return a.uruchom()


def kody(src, **kw):
    return sorted((w.kategoria, w.waznosc) for w in ts(src, **kw))


def tylko(src, kod, **kw):
    return [w for w in ts(src, **kw) if w.kategoria == kod]


class P1TodayIsoSlice(unittest.TestCase):
    def test_slice(self):
        self.assertEqual(kody("const today = new Date().toISOString().slice(0, 10);"),
                         [("ts_today_iso_slice", "wysoka")])

    def test_split_t(self):
        self.assertEqual(kody("const today = new Date().toISOString().split('T')[0];"),
                         [("ts_today_iso_slice", "wysoka")])

    def test_substring_and_substr(self):
        self.assertEqual(len(tylko("a = new Date().toISOString().substring(0,10);\nb = new Date().toISOString().substr(0,10);",
                                   "ts_today_iso_slice")), 2)

    def test_double_quoted_split(self):
        self.assertEqual(kody('const d = new Date().toISOString().split("T")[0];'), [("ts_today_iso_slice", "wysoka")])

    def test_date_now_receiver(self):
        self.assertEqual(kody("const d = new Date(Date.now()).toISOString().slice(0, 10);"),
                         [("ts_today_iso_slice", "wysoka")])

    def test_through_now_variable(self):
        src = """
        function f() {
          const now = new Date();
          return now.toISOString().slice(0, 10);
        }
        """
        self.assertEqual(kody(src), [("ts_today_iso_slice", "wysoka")])

    def test_through_iso_string_variable(self):
        src = """
        function f() {
          const iso = new Date().toISOString();
          return iso.slice(0, 10);
        }
        """
        self.assertEqual(kody(src), [("ts_today_iso_slice", "wysoka")])

    def test_local_midnight_constructed_date(self):
        self.assertEqual(kody("const d = new Date(2026, 9, 19).toISOString().slice(0, 10);"),
                         [("ts_today_iso_slice", "wysoka")])

    def test_unknown_receiver_is_medium_uncertain(self):
        w = ts("const d = picked.toISOString().slice(0, 10);")
        self.assertEqual([(x.kategoria, x.waznosc, x.pewnosc) for x in w], [("ts_today_iso_slice", "srednia", "uncertain")])

    def test_multiline_chain(self):
        src = """
        const d = new Date()
          .toISOString()
          .slice(0, 10);
        """
        self.assertEqual(kody(src), [("ts_today_iso_slice", "wysoka")])

    def test_negative_plain_string_slice(self):
        self.assertEqual(kody("const d = value.slice(0, 10);"), [])

    def test_negative_other_slice_range(self):
        self.assertEqual(kody("const t = new Date().toISOString().slice(11, 16);"), [])

    def test_negative_date_only_literal_roundtrip(self):
        self.assertEqual([k for k in kody("const d = new Date('2026-10-19').toISOString().slice(0, 10);")
                          if k[0] == "ts_today_iso_slice"], [])

    def test_negative_warsaw_helper(self):
        self.assertEqual(kody("const d = new Intl.DateTimeFormat('sv-SE', { timeZone: 'Europe/Warsaw' }).format(new Date());"), [])

    def test_negative_in_comment_and_string(self):
        src = """
        // const d = new Date().toISOString().slice(0, 10);
        const s = "new Date().toISOString().slice(0, 10)";
        /* new Date().toISOString().split('T')[0] */
        """
        self.assertEqual(kody(src), [])


class P2DateOnlyParse(unittest.TestCase):
    def test_new_date_literal(self):
        w = ts("const d = new Date('2026-10-19');")
        self.assertEqual([(x.kategoria, x.waznosc, x.pewnosc) for x in w], [("ts_date_only_parse", "srednia", "likely")])

    def test_date_parse(self):
        self.assertEqual(kody("const t = Date.parse('2026-10-19');"), [("ts_date_only_parse", "srednia")])

    def test_template_literal_date_only(self):
        self.assertEqual(kody("const d = new Date(`${y}-${m}-${day}`);"), [("ts_date_only_parse", "srednia")])

    def test_variable_from_slice(self):
        src = """
        const iso = row.value;
        const ymd = iso.slice(0, 10);
        const d = new Date(ymd);
        """
        self.assertEqual(kody(src), [("ts_date_only_parse", "srednia")])

    def test_comparison_with_today_stays_medium(self):
        self.assertEqual(kody("const late = new Date('2026-10-19') < new Date();"),
                         [("ts_date_only_parse", "srednia"), ("ts_string_date_compare", "srednia")][:1])

    def test_display_only_is_low(self):
        self.assertEqual(kody("const s = new Date('2026-10-19').toLocaleDateString('pl-PL');"),
                         [("ts_date_only_parse", "niska")])

    def test_negative_local_time(self):
        self.assertEqual(kody("const d = new Date('2026-10-19T00:00:00');"), [])

    def test_negative_with_zone(self):
        self.assertEqual(kody("const d = new Date('2026-10-19T00:00:00+02:00');"), [])

    def test_negative_numeric_parts(self):
        self.assertEqual(kody("const d = new Date(2026, 9, 19);"), [])

    def test_negative_concatenated_time(self):
        self.assertEqual(kody("const d = new Date('2026-10-19' + 'T00:00:00');"), [])

    def test_negative_dayjs_is_local(self):
        self.assertEqual(kody("const d = dayjs('2026-10-19');"), [])

    def test_negative_plain_variable(self):
        self.assertEqual(kody("const d = new Date(value);"), [])


class P3Locale(unittest.TestCase):
    def test_z_literal_is_high(self):
        w = ts("const s = new Date('2026-10-19T10:00:00Z').toLocaleString('pl-PL');")
        self.assertEqual([(x.kategoria, x.waznosc, x.pewnosc) for x in w], [("ts_locale_no_timezone", "wysoka", "likely")])

    def test_offset_literal_is_high(self):
        self.assertEqual(kody("const s = new Date('2026-10-19T10:00:00+00:00').toLocaleTimeString('pl-PL');"),
                         [("ts_locale_no_timezone", "wysoka")])

    def test_iso_string_variable_is_high(self):
        src = """
        function f() {
          const iso = new Date().toISOString();
          return new Date(iso).toLocaleTimeString('pl-PL');
        }
        """
        self.assertEqual(kody(src), [("ts_locale_no_timezone", "wysoka")])

    def test_timestamp_field_by_name_is_medium(self):
        w = ts("const s = new Date(row.createdAt).toLocaleString('pl-PL');")
        self.assertEqual([(x.waznosc, x.pewnosc) for x in w], [("srednia", "uncertain")])

    def test_timestamp_field_from_column_file_is_likely(self):
        w = ts("const s = new Date(row.paidOn).toLocaleString('pl-PL');", systemowe=["orders.paid_on"])
        self.assertEqual([(x.waznosc, x.pewnosc) for x in w], [("srednia", "likely")])

    def test_date_only_field_is_low(self):
        self.assertEqual(kody("const s = new Date(order.dueDate).toLocaleDateString('pl-PL');"),
                         [("ts_locale_no_timezone", "niska")])

    def test_unknown_locale_date_string_is_low(self):
        self.assertEqual(kody("const s = value.toLocaleDateString('pl-PL');"), [("ts_locale_no_timezone", "niska")])

    def test_unknown_time_string_is_medium(self):
        self.assertEqual(kody("const s = value.toLocaleTimeString('pl-PL');"), [("ts_locale_no_timezone", "srednia")])

    def test_intl_formatter_inline(self):
        self.assertEqual(kody("const s = new Intl.DateTimeFormat('pl-PL', { hour: '2-digit' }).format(new Date('2026-10-19T10:00:00Z'));"),
                         [("ts_locale_no_timezone", "wysoka")])

    def test_intl_formatter_stored(self):
        self.assertEqual(kody("const fmt = new Intl.DateTimeFormat('pl-PL', { hour: '2-digit', minute: '2-digit' });"),
                         [("ts_locale_no_timezone", "srednia")])

    def test_utc_timezone_on_timestamp_value(self):
        self.assertEqual(kody("const s = new Date('2026-10-19T10:00:00Z').toLocaleString('pl-PL', { timeZone: 'UTC' });"),
                         [("ts_locale_no_timezone", "srednia")])

    def test_negative_explicit_warsaw(self):
        self.assertEqual(kody("const s = new Date('2026-10-19T10:00:00Z').toLocaleString('pl-PL', { timeZone: 'Europe/Warsaw' });"), [])

    def test_negative_utc_on_date_only_value(self):
        self.assertEqual(kody("const s = new Date('2026-10-19').toLocaleDateString('pl-PL', { timeZone: 'UTC' });"),
                         [("ts_date_only_parse", "niska")])

    def test_negative_number_to_locale_string(self):
        self.assertEqual(kody("const s = price.toLocaleString('pl-PL');"), [])

    def test_negative_array_and_total(self):
        self.assertEqual(kody("const s = items.length.toLocaleString();\nconst t = (total / 100).toLocaleString('pl-PL');"), [])

    def test_negative_local_timestamp_literal(self):
        self.assertEqual(kody("const s = new Date('2026-10-19T10:00:00').toLocaleString('pl-PL');"), [])


class P4Getters(unittest.TestCase):
    def test_inline_z_literal(self):
        w = ts("const h = new Date('2026-10-19T22:30:00Z').getHours();")
        self.assertEqual([(x.kategoria, x.waznosc, x.pewnosc) for x in w], [("ts_local_getter_on_utc", "srednia", "likely")])

    def test_variable_from_api_field(self):
        src = """
        function f(row) {
          const created = new Date(row.createdAt);
          return created.getDate() + '.' + (created.getMonth() + 1);
        }
        """
        w = tylko(src, "ts_local_getter_on_utc")
        self.assertEqual(len(w), 1)  # jedno trafienie na linię i kod
        self.assertEqual(w[0].pewnosc, "uncertain")

    def test_get_full_year_from_iso_variable(self):
        src = """
        function f() {
          const iso = new Date().toISOString();
          return new Date(iso).getFullYear();
        }
        """
        self.assertEqual(len(tylko(src, "ts_local_getter_on_utc")), 1)  # łańcuch z toISOString() ma 'Z' 

    def test_negative_utc_getters(self):
        self.assertEqual(kody("const h = new Date('2026-10-19T22:30:00Z').getUTCHours();"), [])

    def test_negative_local_constructed_date(self):
        self.assertEqual(kody("const d = new Date(2026, 9, 19).getDate();"), [])

    def test_negative_now_date(self):
        self.assertEqual(kody("const h = new Date().getHours();"), [])

    def test_negative_unknown_receiver(self):
        self.assertEqual(kody("const h = value.getHours();"), [])

    def test_negative_local_timestamp_literal(self):
        self.assertEqual(kody("const h = new Date('2026-10-19T10:00:00').getHours();"), [])


class P5StringCompare(unittest.TestCase):
    def test_literal_vs_new_date(self):
        w = ts("if ('2026-10-19' < new Date()) { go(); }")
        self.assertEqual([(x.kategoria, x.pewnosc) for x in w], [("ts_string_date_compare", "likely")])

    def test_new_date_vs_literal(self):
        self.assertEqual(kody("const late = new Date() > '2026-10-19';"), [("ts_string_date_compare", "srednia")])

    def test_slice_string_variable_vs_date_object(self):
        src = """
        function f(d) {
          const ymd = d.toISOString().slice(0, 10);
          return ymd >= new Date();
        }
        """
        self.assertIn(("ts_string_date_compare", "srednia"), kody(src))

    def test_string_vs_get_time(self):
        src = """
        function f(a) {
          const d = new Date(a);
          return '2026-10-19' < d.getTime();
        }
        """
        self.assertIn(("ts_string_date_compare", "srednia"), kody(src))

    def test_negative_two_strings(self):
        self.assertEqual(kody("if ('2026-10-19' < other) {}\nconst x = '2026-10-19' === '2026-10-20';"), [])

    def test_negative_two_dates(self):
        self.assertEqual(kody("const x = new Date(a) < new Date(b);\nconst y = a.getTime() < Date.now();"), [])

    def test_negative_arrow_and_generics(self):
        self.assertEqual(kody("const f = (a: number) => a > 1;\nconst m = new Map<string, Date>();"), [])

    def test_negative_jsx(self):
        self.assertEqual(kody("const el = <div className='x'>{count > 1 ? 'a' : 'b'}</div>;"), [])


class P6NowIntoLocalField(unittest.TestCase):
    def test_object_property_heuristic(self):
        w = ts("const body = { startsAt: new Date().toISOString() };")
        self.assertEqual([(x.kategoria, x.waznosc, x.pewnosc) for x in w], [("ts_now_into_local_field", "wysoka", "uncertain")])

    def test_local_column_file_makes_it_likely(self):
        w = ts("const body = { visitOn: new Date().toISOString() };", lokalne=["visits.visit_on"])
        self.assertEqual([(x.waznosc, x.pewnosc) for x in w], [("wysoka", "likely")])

    def test_snake_case_key_matches_camel_column(self):
        w = ts("const body = { scheduled_for: Date.now() };")
        self.assertEqual([x.kategoria for x in w], ["ts_now_into_local_field"])

    def test_raw_new_date_serialised_by_json(self):
        self.assertEqual(kody("const body = JSON.stringify({ dueDate: new Date() });"), [("ts_now_into_local_field", "wysoka")])

    def test_property_assignment(self):
        self.assertEqual(kody("form.plannedAt = new Date().toISOString();"), [("ts_now_into_local_field", "wysoka")])

    def test_set_field_value_call(self):
        self.assertEqual(kody("setFieldValue('startsAt', new Date().toISOString());"), [("ts_now_into_local_field", "wysoka")])

    def test_via_now_variable(self):
        src = """
        function f() {
          const ts = new Date().toISOString();
          return { endsAt: ts };
        }
        """
        self.assertEqual(kody(src), [("ts_now_into_local_field", "wysoka")])

    def test_negative_system_column(self):
        self.assertEqual(kody("const body = { createdAt: new Date().toISOString(), updatedAt: Date.now() };"), [])

    def test_negative_system_column_file_overrides_heuristic(self):
        self.assertEqual(kody("const body = { startsAt: new Date().toISOString() };", systemowe=["shifts.starts_at"]), [])

    def test_negative_warsaw_formatted(self):
        src = "const body = { startsAt: new Date().toLocaleString('sv-SE', { timeZone: 'Europe/Warsaw' }) };"
        self.assertEqual(kody(src), [])

    def test_negative_helper_wrapper(self):
        self.assertEqual(kody("const body = { startsAt: formatujDateWarszawa(new Date()) };"), [])

    def test_negative_user_picked_value(self):
        self.assertEqual(kody("const body = { startsAt: form.startsAt };"), [])


class P7StartOfDay(unittest.TestCase):
    def test_set_hours_on_date_only_parsed(self):
        src = """
        function f() {
          const from = new Date('2026-10-19');
          from.setHours(0, 0, 0, 0);
          return from;
        }
        """
        self.assertIn(("ts_startof_day_utc", "wysoka"), kody(src))

    def test_set_hours_on_z_value(self):
        src = """
        function f() {
          const d = new Date('2026-10-19T22:00:00Z');
          d.setHours(0, 0, 0, 0);
        }
        """
        self.assertIn(("ts_startof_day_utc", "wysoka"), kody(src))

    def test_end_of_day_23_59(self):
        src = """
        function f() {
          const d = new Date('2026-10-19T22:00:00Z');
          d.setHours(23, 59, 59, 999);
        }
        """
        self.assertIn(("ts_startof_day_utc", "wysoka"), kody(src))

    def test_set_utc_hours(self):
        self.assertEqual(kody("const d = pick; d.setUTCHours(0, 0, 0, 0);"), [("ts_startof_day_utc", "wysoka")])

    def test_dayjs_utc_start_of_day(self):
        self.assertEqual(kody("const s = dayjs.utc(value).startOf('day');"), [("ts_startof_day_utc", "wysoka")])

    def test_dayjs_utc_method(self):
        self.assertEqual(kody("const s = dayjs(value).utc().startOf('day');"), [("ts_startof_day_utc", "wysoka")])

    def test_moment_z_literal(self):
        self.assertEqual(kody("const s = moment('2026-10-19T22:00:00Z').startOf('day');"), [("ts_startof_day_utc", "wysoka")])

    def test_api_field_by_name_is_uncertain(self):
        w = tylko("const d = new Date(row.createdAt);\nd.setHours(0, 0, 0, 0);", "ts_startof_day_utc")
        self.assertEqual([(x.waznosc, x.pewnosc) for x in w], [("wysoka", "uncertain")])

    def test_negative_local_now(self):
        self.assertEqual(kody("const d = new Date();\nd.setHours(0, 0, 0, 0);"), [])

    def test_negative_local_constructed(self):
        self.assertEqual(kody("const d = new Date(2026, 9, 19);\nd.setHours(0, 0, 0, 0);"), [])

    def test_negative_dayjs_tz(self):
        self.assertEqual(kody("const s = dayjs(value).tz('Europe/Warsaw').startOf('day');"), [])

    def test_negative_dayjs_local_start_of_day(self):
        self.assertEqual(kody("const s = dayjs().startOf('day');"), [])

    def test_negative_other_set_hours(self):
        self.assertEqual(kody("const d = new Date('2026-10-19T22:00:00Z');\nd.setHours(12, 0, 0, 0);"), [])

    def test_negative_start_of_month(self):
        self.assertEqual(kody("const s = dayjs.utc(value).startOf('month');"), [])


class P8HourShift(unittest.TestCase):
    def test_two_hours_ms(self):
        self.assertEqual(kody("const t = new Date(d.getTime() + 2 * 3600 * 1000);"), [("ts_manual_hour_shift", "srednia")])

    def test_one_hour_60_60_1000(self):
        self.assertEqual(kody("const t = new Date(x.getTime() - 1 * 60 * 60 * 1000);"), [("ts_manual_hour_shift", "srednia")])

    def test_literal_milliseconds(self):
        self.assertEqual(kody("const t = new Date(x.getTime() + 7200000);"), [("ts_manual_hour_shift", "srednia")])

    def test_numeric_separator(self):
        self.assertEqual(kody("const t = new Date(x.getTime() + 3_600_000);"), [("ts_manual_hour_shift", "srednia")])

    def test_set_hours_get_hours_plus(self):
        self.assertEqual(kody("d.setHours(d.getHours() + 2);"), [("ts_manual_hour_shift", "srednia")])

    def test_tz_named_line_is_likely(self):
        w = ts("const warsawOffset = d.getTime() + 2 * 3600 * 1000;")
        self.assertEqual([x.pewnosc for x in w], ["likely"])

    def test_negative_expiry_cache_ttl(self):
        self.assertEqual(kody("const expiresAt = Date.now() + 2 * 3600 * 1000;\nconst ttl = 3600 * 1000;"), [])

    def test_negative_three_hours(self):
        self.assertEqual(kody("const t = d.getTime() + 3 * 3600 * 1000;"), [])

    def test_negative_minutes_and_days(self):
        self.assertEqual(kody("const t = d.getTime() + 15 * 60 * 1000;\nconst u = d.getTime() + 24 * 3600 * 1000;"), [])

    def test_negative_in_string_and_comment(self):
        self.assertEqual(kody("const s = 'x + 2 * 3600 * 1000';\n// d.getTime() + 2 * 3600 * 1000"), [])


class Suppression(unittest.TestCase):
    def test_trailing_tz_ok(self):
        self.assertEqual(kody("const d = new Date().toISOString().slice(0, 10); // tz-ok: tylko do logu"), [])

    def test_previous_line_tz_ok(self):
        src = """
        // tz-ok: nazwa pliku eksportu
        const d = new Date().toISOString().slice(0, 10);
        const e = new Date().toISOString().slice(0, 10);
        """
        self.assertEqual(kody(src), [("ts_today_iso_slice", "wysoka")])

    def test_block_comment_tz_ok(self):
        self.assertEqual(kody("const d = new Date().toISOString().slice(0, 10); /* tz-ok: log */"), [])

    def test_other_comment_does_not_suppress(self):
        self.assertEqual(kody("const d = new Date().toISOString().slice(0, 10); // todo"), [("ts_today_iso_slice", "wysoka")])

    def test_tz_ok_only_on_its_line(self):
        src = """
        const a = new Date().toISOString().slice(0, 10); // tz-ok: log
        const b = new Date().toISOString().slice(0, 10);
        """
        w = ts(src)
        self.assertEqual([x.linia for x in w], [3])


class LexerAndContext(unittest.TestCase):
    def test_lexer_same_length_and_blanks(self):
        src = "a = 'x // y'; // c\n/* b */ `t ${ f('z') } u` /re[/]g/.test(s);\n"
        code, skel, _ = sta.lex_js(src)
        self.assertEqual((len(code), len(skel)), (len(src), len(src)))
        self.assertNotIn("// c", code)
        self.assertNotIn("x // y", skel)
        self.assertIn("f(", skel)

    def test_template_expression_is_analysed(self):
        self.assertEqual(kody("const s = `dzis: ${new Date().toISOString().slice(0, 10)}`;"), [("ts_today_iso_slice", "wysoka")])

    def test_nested_template(self):
        src = "const s = `a ${ `b ${new Date().toISOString().slice(0, 10)}` } c`;"
        self.assertEqual(kody(src), [("ts_today_iso_slice", "wysoka")])

    def test_regex_literal_with_slash_in_class(self):
        self.assertEqual(kody("const r = /[/]'\"/.test(s);\nconst d = new Date().toISOString().slice(0, 10);"),
                         [("ts_today_iso_slice", "wysoka")])

    def test_jsx_apostrophe_does_not_swallow_code(self):
        src = """
        export const A = () => (
          <p>Don't forget</p>
        );
        const d = new Date().toISOString().slice(0, 10);
        """
        self.assertEqual(kody(src), [("ts_today_iso_slice", "wysoka")])

    def test_division_is_not_regex(self):
        self.assertEqual(kody("const a = x / 2; const d = new Date().toISOString().slice(0, 10); const b = y / 3;"),
                         [("ts_today_iso_slice", "wysoka")])

    def test_context_component(self):
        src = """
        export function ShiftList() {
          const d = new Date().toISOString().slice(0, 10);
        }
        """
        self.assertEqual(ts(src)[0].funkcja, "komponent ShiftList")

    def test_context_arrow_component_and_inner_handler(self):
        src = """
        export const OrderForm = () => {
          const save = async () => {
            const d = new Date().toISOString().slice(0, 10);
          };
          return null;
        };
        """
        self.assertEqual(ts(src)[0].funkcja, "komponent OrderForm › save")

    def test_context_hook(self):
        src = "export const useToday = () => { return new Date().toISOString().slice(0, 10); };"
        self.assertEqual(ts(src)[0].funkcja, "hook useToday")

    def test_context_api_client(self):
        src = """
        export async function fetchOrders() {
          return get('/orders?from=' + new Date().toISOString().slice(0, 10));
        }
        """
        self.assertEqual(ts(src, plik="src/api/orders.ts")[0].funkcja, "klient API fetchOrders")

    def test_context_plain_function_and_module(self):
        self.assertEqual(ts("function helper() { return new Date().toISOString().slice(0, 10); }", plik="src/util.ts")[0].funkcja,
                         "funkcja helper")
        self.assertEqual(ts("const d = new Date().toISOString().slice(0, 10);", plik="src/util.ts")[0].funkcja, "moduł")

    def test_context_class_method(self):
        src = """
        class Repo {
          today() {
            return new Date().toISOString().slice(0, 10);
          }
        }
        """
        self.assertEqual(ts(src, plik="src/repo.ts")[0].funkcja, "metoda Repo.today")

    def test_line_numbers(self):
        src = "\n\nconst d = new Date().toISOString().slice(0, 10);\n"
        self.assertEqual(ts(src)[0].linia, 3)

    def test_fragment_short_and_masks_values(self):
        w = ts("const q = fetchIt('Fikcyjny Klient', new Date().toISOString().slice(0, 10));")[0]
        self.assertLessEqual(len(w.fragment), 120)
        self.assertNotIn("Fikcyjny", w.fragment)

    def test_never_raises_on_garbage(self):
        for smiec in ("", "((((", "`${", "/* nie zamkniety", "'a\n'b", "function (", "a.b.c.(", "=> => =>", "}}}{{{"):
            self.assertIsInstance(ts(smiec), list)

    def test_p4_getter_with_optional_chaining(self):
        self.assertEqual(kody("const h = new Date('2026-10-19T22:30:00Z')?.getHours();"), [("ts_local_getter_on_utc", "srednia")])

    def test_crlf_source(self):
        a = sta.AnalizatorTs("const d = new Date().toISOString().slice(0, 10);\r\nconst e = 1;\r\n", "a.ts")
        self.assertEqual([w.linia for w in a.uruchom()], [1])

    def test_all_codes_have_metadata(self):
        self.assertEqual(len(sta.KODY_TS), 8)
        for kod, (waz, dlaczego, podp) in sta.KODY_TS.items():
            self.assertIn(waz, sta.WAZNOSCI)
            self.assertTrue(dlaczego and podp)

    def test_hints_mention_shared_helper(self):
        tekst = " ".join(v[2] for v in sta.KODY_TS.values())
        self.assertIn("dzisWarszawa", tekst)
        self.assertIn("formatujDateWarszawa", tekst)


class Performance(unittest.TestCase):
    def test_large_file_is_not_quadratic(self):
        import time
        blok = ("export const Comp%d = ({ rows }) => {\n  const created = new Date(rows[0].createdAt);\n"
                "  const label = created.toLocaleString('pl-PL');\n  const today = new Date().toISOString().slice(0, 10);\n"
                "  return <div className=\"x\">{label}{today}</div>;\n};\n")
        src = "".join(blok % i for i in range(600))
        t = time.time()
        wyniki = ts(src)
        self.assertLess(time.time() - t, 8)
        self.assertEqual(len(wyniki), 1200)

    def test_minified_single_line(self):
        src = "var a=" + "+".join(["new Date().getTime()"] * 3000) + ";"
        self.assertEqual(ts(src, plik="min.js"), [])


class Severity(unittest.TestCase):
    """Wysoka tylko dla wzorców 1, 6, 7 i 3 na wartości z 'Z'."""

    def test_only_allowed_codes_are_high(self):
        src = """
        function f(row, picked) {
          const a = new Date('2026-10-19');
          const b = new Date(row.createdAt).toLocaleString('pl-PL');
          const c = new Date(row.createdAt).getHours();
          const d = '2026-10-19' < new Date();
          const e = d.getTime() + 2 * 3600 * 1000;
          const g = new Date(row.dueDate).toLocaleDateString('pl-PL');
          const h = picked.toISOString().slice(0, 10);
        }
        """
        for w in ts(src):
            self.assertNotEqual(w.waznosc, "wysoka", w.kategoria)

    def test_date_only_display_is_low(self):
        for w in ts("const g = new Date(order.dueDate).toLocaleDateString('pl-PL');"):
            self.assertEqual(w.waznosc, "niska")


if __name__ == "__main__":
    unittest.main()
