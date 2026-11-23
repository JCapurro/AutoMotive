-- admin_searches: count matches and alerts in one pass instead of three correlated
-- subqueries per search. Measured on production 2026-11-23 (813 searches, ~68k
-- matches, cold cache): the view took 7.9 s (the "high" subquery alone ~4.9 s),
-- right at the statement timeout; /admin/searches failed with "canceling statement
-- due to statement timeout" on 2026-11-22. The same result with one group-by per
-- table takes ~1.6 s. Same columns, same order, same types (bigint counts).
--
-- Rollback: re-run the create view of public.admin_searches from
-- 20261003120000_f6_backoffice_metrics.sql (three correlated subqueries).

create or replace view public.admin_searches with (security_invoker = true) as
select sp.id,
       sp.user_id,
       p.email,
       sp.name,
       sp.filters,
       sp.enabled,
       sp.notification_frequency,
       sp.notify_min_level,
       sp.channels,
       sp.bootstrapped_at,
       sp.rematch_requested_at,
       sp.created_at,
       coalesce(mm.matches, 0)      as matches,
       coalesce(mm.high_matches, 0) as high_matches,
       coalesce(nn.alerts, 0)       as alerts
  from public.search_profiles sp
  join public.profiles p on p.id = sp.user_id
  left join (
    select m.search_profile_id,
           count(*)                           as matches,
           count(*) filter (where m.level = 'high') as high_matches
      from public.matches m
     group by m.search_profile_id
  ) mm on mm.search_profile_id = sp.id
  left join (
    select n.search_profile_id, count(distinct n.dedupe_key) as alerts
      from public.notifications n
     where n.kind <> 'digest' and n.status in ('sent', 'digest')
     group by n.search_profile_id
  ) nn on nn.search_profile_id = sp.id;
