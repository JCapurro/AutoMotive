-- Oportunidad creible (docs/OPORTUNIDAD_CREIBLE.md). Juan, 2026-11-24: 15 %.
--
-- app_config.opportunity_gate, read only by the worker (notifications.service.load_rules): with enabled true the
-- alert kind `opportunity` asks for a credible discount (diff_pct >= min_pct) over enough comparables
-- (n >= min_n); a high that does not reach it is alerted as `new_match`, with its usual text. Nobody loses an
-- alert: only its kind changes. The Pro thresholds (opportunity_threshold_pct / _usd) are not touched.
-- Inserted off: inert until Juan turns it on in /admin/config; turning it off is the rollback.
set local lock_timeout = '5s';

insert into public.app_config(key, value)
values ('opportunity_gate', jsonb_build_object('enabled', false, 'min_pct', 15, 'min_n', 10))
on conflict (key) do nothing;
