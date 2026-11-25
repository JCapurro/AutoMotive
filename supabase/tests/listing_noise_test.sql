-- Ruido de avisos (migration 20270113120000_listing_noise_switches): app_config.listing_noise, every switch off.
begin;
select no_plan();

select is((select value from public.app_config where key = 'listing_noise'),
          '{"placeholder_f2": false, "repost_groups": false, "ended_guard": false}'::jsonb,
          'listing_noise exists with every switch off');

-- A value turned on from /admin/config or SQL survives the migration's re-run.
update public.app_config set value = '{"repost_groups": true}' where key = 'listing_noise';
insert into public.app_config (key, value)
values ('listing_noise', '{"placeholder_f2": false, "repost_groups": false, "ended_guard": false}'::jsonb)
on conflict (key) do nothing;
select is((select value->>'repost_groups' from public.app_config where key = 'listing_noise'), 'true',
          'a re-run leaves the tuned value alone');

select * from finish();
rollback;
