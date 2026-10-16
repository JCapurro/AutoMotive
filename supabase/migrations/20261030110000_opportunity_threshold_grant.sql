-- Fix: 20261025120000 added search_profiles.opportunity_threshold_pct after
-- 20261007120000 had replaced the table UPDATE grant by a column list, so
-- editing any search from the web (actions.ts always sends the column) fails
-- with permission denied. Its own migration, so it can go to prod ahead of
-- the body-type rollout. Idempotent: a manual hotfix already in prod is fine.
--
-- Before applying in prod:
--   select has_column_privilege('authenticated', 'public.search_profiles',
--                               'opportunity_threshold_pct', 'UPDATE');

grant update (opportunity_threshold_pct) on public.search_profiles to authenticated;

notify pgrst, 'reload schema';
