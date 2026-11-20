-- Agencias: a spreadsheet through the reader, as text (migration 20270103120000_dealer_stock_read_text.sql).
-- One transaction, rolled back.
begin;
create extension if not exists pgtap with schema extensions;
select no_plan();

insert into auth.users (instance_id, id, aud, role, email, created_at, updated_at) values
  ('00000000-0000-0000-0000-000000000000', 'd9000000-0000-0000-0000-00000000000a', 'authenticated', 'authenticated', 'a@srt.test', now(), now());
update public.app_config set value = '{"enabled": true}' where key = 'dealer_program';

set local role authenticated;
set local request.jwt.claims = '{"sub": "d9000000-0000-0000-0000-00000000000a", "role": "authenticated"}';
select lives_ok($$select public.create_dealer('Srt A', 'Quilmes', -34.72, -58.25)$$, 'dealer A');
select throws_ok($$select public.dealer_request_stock_read(encode('Auto ; Precio'::bytea, 'base64'), 'text/csv', 'stock.xlsx')$$,
                 'P0001', 'photo_import_off', 'a spreadsheet: off with the reader''s switch off');
reset role;

update public.app_config set value = '{"enabled": true, "photo_import_enabled": true, "photo_import_daily_limit": 2}' where key = 'dealer_program';
set local role authenticated;
set local request.jwt.claims = '{"sub": "d9000000-0000-0000-0000-00000000000a", "role": "authenticated"}';
select lives_ok($$select public.dealer_request_stock_read(encode(convert_to(E'Auto ; Precio\nFocus 1.6 S 2016 ; USD 9.800', 'UTF8'), 'base64'), 'text/csv', 'stock.xlsx')$$,
                'a spreadsheet as text is queued');
select throws_ok($$select public.dealer_request_stock_read(encode('x'::bytea, 'base64'), 'text/plain', 'x.txt')$$,
                 'P0001', 'invalid_file:type', 'any other text type is refused');
select throws_ok($$select public.dealer_request_stock_read(encode('x'::bytea, 'base64'), 'application/vnd.ms-excel', 'x.xls')$$,
                 'P0001', 'invalid_file:type', 'a raw Excel file is refused: the web sends its table as text');
select lives_ok($$select public.dealer_request_stock_read(encode('foto'::bytea, 'base64'), 'image/jpeg', 'a.jpg')$$, 'a photo still is');
select throws_ok($$select public.dealer_request_stock_read(encode('Auto'::bytea, 'base64'), 'text/csv', 'otra.csv')$$,
                 'P0001', 'photo_import_limit', 'spreadsheets count for the same daily cap');
reset role;

select is((select array[r.media_type, r.filename, r.bytes::text, convert_from(r.data, 'UTF8')] from public.dealer_stock_reads r where r.media_type = 'text/csv'),
          array['text/csv', 'stock.xlsx', '42', E'Auto ; Precio\nFocus 1.6 S 2016 ; USD 9.800'], 'the read keeps the text for the worker');
select is((select array[j.kind, j.status::text, (j.input ->> 'read_id' = r.id::text)::text]
             from public.llm_jobs j join public.dealer_stock_reads r on r.job_id = j.id where r.media_type = 'text/csv'),
          array['dealer_stock_read', 'queued', 'true'], '... with its dealer_stock_read job');
select throws_ok($$insert into public.dealer_stock_reads (dealer_id, media_type, bytes) select id, 'text/html', 1 from public.dealers where name = 'Srt A'$$,
                 '23514', null, 'the table accepts only the reader''s types');

select * from finish();
rollback;
