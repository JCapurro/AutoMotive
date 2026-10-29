-- F-03 fase 0 (migration 20261119110000_f03_market_stats.sql): who reads the
-- three new tables, their checks and the config the job is born with. The job
-- itself is tested in worker/tests/test_market_stats_postgres.py.
-- Run with: supabase test db
begin;
create extension if not exists pgtap with schema extensions;
select no_plan();

insert into auth.users(instance_id,id,aud,role,email,created_at,updated_at) values
('00000000-0000-0000-0000-000000000000','f0300000-0000-4000-8000-000000000001','authenticated','authenticated','market-user@example.test',now(),now());

-- ---------------------------------------------------------------- fixtures, as the worker (service_role)
insert into public.listings(id,source,external_id,url,title,make,model,year,lat,lon) overriding system value values
(980301,'mercadolibre','f03-1','https://example.test/f03-1','Ford Fiesta','Ford','Fiesta',2018,-34.4708,-58.5286),
(980302,'mercadolibre','f03-2','https://example.test/f03-2','Ford Fiesta','Ford','Fiesta',2019,-32.9442,-60.6505);
set local role service_role;
select lives_ok($$insert into public.listing_zones(listing_id,province_id,department,locality_id,dist_km,precision,lat,lon)
                  values (980301,'06','San Isidro','06756010',1.8,'locality',-34.4708,-58.5286),
                         (980302,'82','Rosario','82084270',0.7,'locality',-32.9442,-60.6505)$$,
                'service_role writes listing_zones');
select lives_ok($$insert into public.market_stats_runs(id,week_start,mode,status) overriding system value
                  values (980301,'2026-10-26','dry_run','ok')$$,
                'service_role writes market_stats_runs');
select lives_ok($$insert into public.market_stats(week_start,group_kind,make,model,year_from,zone,active_count,run_id)
                  values ('2026-10-26','model','ford','fiesta',2018,'amba',1,980301),
                         ('2026-10-26','model','ford','fiesta',2018,'todas',2,980301)$$,
                'service_role writes market_stats');
reset role;

-- ---------------------------------------------------------------- checks and uniqueness
select throws_ok($$insert into public.market_stats(week_start,group_kind,zone) values ('2026-10-26','trim','todas')$$,
                 '23514', null, 'group_kind is model or body_type');
select throws_ok($$insert into public.market_stats_runs(week_start,mode) values ('2026-10-26','write_all')$$,
                 '23514', null, 'mode is dry_run or write');
select throws_ok($$insert into public.listing_zones(listing_id,precision,lat,lon) values (980302,'street',0,0)$$,
                 '23505', null, 'one zone per listing');
select throws_ok($$insert into public.market_stats(week_start,group_kind,make,model,body_type,year_from,zone)
                   values ('2026-10-26','model','ford','fiesta',null,2018,'amba')$$,
                 '23505', null, 'the key treats nulls as equal: a week is replaced, never duplicated');
select lives_ok($$insert into public.market_stats(week_start,group_kind,body_type,year_from,zone)
                  values ('2026-10-26','body_type','hatchback',2018,'amba')$$,
                'another group of the same week');

-- ---------------------------------------------------------------- a common user reads nothing
set local role authenticated;
set local request.jwt.claim.sub='f0300000-0000-4000-8000-000000000001';
select is((select count(*)::int from public.listing_zones),0,'a user reads no listing_zones');
select is((select count(*)::int from public.market_stats),0,'a user reads no market_stats');
select is((select count(*)::int from public.market_stats_runs),0,'a user reads no market_stats_runs');
select throws_ok($$insert into public.market_stats(week_start,group_kind,zone) values ('2026-11-02','model','todas')$$,
                 '42501', null, 'a user cannot insert market_stats');
select throws_ok($$insert into public.market_stats_runs(week_start,mode) values ('2026-11-02','write')$$,
                 '42501', null, 'a user cannot insert market_stats_runs');
select throws_ok($$insert into public.listing_zones(listing_id,precision,lat,lon) values (980301,'locality',0,0)$$,
                 '42501', null, 'a user cannot insert listing_zones');
reset role;

set local role anon;
select throws_ok($$select count(*) from public.market_stats$$, '42501', null, 'anon cannot read market_stats');
select throws_ok($$select count(*) from public.market_stats_runs$$, '42501', null, 'anon cannot read market_stats_runs');
select throws_ok($$select count(*) from public.listing_zones$$, '42501', null, 'anon cannot read listing_zones');
reset role;

-- ---------------------------------------------------------------- an admin reads the stats, not the zones
update public.profiles set role='admin' where id='f0300000-0000-4000-8000-000000000001';
set local role authenticated;
set local request.jwt.claim.sub='f0300000-0000-4000-8000-000000000001';
select is((select count(*)::int from public.market_stats),3,'an admin reads market_stats');
select is((select count(*)::int from public.market_stats_runs),1,'an admin reads market_stats_runs');
select is((select count(*)::int from public.listing_zones),0,'listing_zones has no policy, not even for admins');
reset role;

-- ---------------------------------------------------------------- cascade
delete from public.listings where id = 980302;
select is((select count(*)::int from public.listing_zones where listing_id = 980302),0,
          'a deleted listing takes its zone with it');

-- ---------------------------------------------------------------- config the job is born with
select is((select value->>'mode' from public.app_config where key='market_stats'),'off','market_stats: mode off');
select is((select value->'write_enabled' from public.app_config where key='market_stats'),'false'::jsonb,
          'market_stats: writing disabled');
select is((select value->'min_n' from public.app_config where key='market_stats'),'{"price":8,"days":5}'::jsonb,
          'market_stats: min_n 8 prices, 5 days');
select is((select value->'confirm_since' from public.app_config where key='market_stats'),
          '{"mercadolibre":"2026-10-24"}'::jsonb, 'market_stats: Mercado Libre counts its ends since 24/10/2026');
select is((select (value->>'version')::int from public.app_config where key='market_zones'),1,'market_zones: version 1');
select is((select jsonb_array_length(value->'rules') from public.app_config where key='market_zones'),25,
          'market_zones: the rules of the 24 provinces');
select is((select (value->>'market_stats_weeks')::int from public.app_config where key='retention'),26,
          'retention: 26 weeks of market_stats');

select * from finish();
rollback;
