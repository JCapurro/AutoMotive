-- Ruido de avisos (docs/FB_DUPLICADOS_PLACEHOLDER_TERMINADOS.md): three switches, all OFF.
-- Only a row in app_config: no table, no function, no data touched. Idempotent.
--   placeholder_f2  f2 scores a placeholder price (one digit 1-8 repeated 4+ times) as «sin precio»
--                   and caps its level at `match` (as f3 does).
--   repost_groups   one alert per car: the reposts of a car the user was already alerted about, and
--                   all but the best twin of a batch, get no alert.
--   ended_guard     no new_match or price_drop alert for a listing that is no longer active.
-- Rollback without a deploy: update public.app_config set value = '{}' where key = 'listing_noise';
-- (a missing or malformed row, or any value other than JSON true, is off).
-- Not in seed.sql: seed runs after the migrations with on conflict do nothing.

insert into public.app_config (key, value)
values ('listing_noise', '{"placeholder_f2": false, "repost_groups": false, "ended_guard": false}'::jsonb)
on conflict (key) do nothing;
