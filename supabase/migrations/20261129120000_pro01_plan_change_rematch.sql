-- PRO-01 · Respuestas de Juan 02/11 (docs/superpowers/specs/2026-10-31-pro01-contacto-design.md,
-- «Respuestas de Juan 02/11», 3 y 4).
--
-- 3. Recalcular al cambiar de plan. When plan_feature(user, 'seller_filter')
--    flips, that user's searches with filters.seller_types are marked for
--    rematch (rematch_requested_at), so the strict filter is applied or lifted
--    at once with the rematch's semantics (worker/pipeline/rematch.py): what
--    stops matching is deleted, what starts matching is backfill (never
--    notified), what kept matching keeps its row and its notifications.
--    One mechanism at the database, whatever wrote the change:
--    * profiles.seller_filter_access: the flag as last seen (backfilled here).
--    * sync_seller_filter_access(p_user, p_everyone): recomputes the flag,
--      stores it and marks the searches of the users whose flag changed.
--    * profiles_sync_seller_filter: after insert or a change of plan,
--      plan_expires_at or role (the only inputs of the plan's limits in
--      plan_limits_for), whoever wrote it: record_commercial_payment,
--      refund_commercial_payment, apply_mercadopago_payment (webhook),
--      refresh_paid_access, link_telegram's merge, an admin by SQL.
--    * app_config_sync_seller_filter: plan_limits edited (admin_update_setting,
--      /admin/config) with a plan's seller_filter changed: every user.
--    * search_profiles_owner_seller_rematch: a search moved to another user
--      (link_telegram) whose flag differs.
--    * expire_commercial_access: also syncs. Without a user (the worker's
--      enabled_profiles, every scheduler tick, right before the rematch) it
--      sweeps the users whose stored flag is on and whose plan_expires_at
--      passed: the time-based expiry, which writes nothing.
-- 4. Option C: match_cards.seller_unknown, the strict filter let a listing
--    without a known seller through (match_reasons.seller unknown and hard).
--    The card, the listing page and the Pro opportunity email say
--    «vendedor sin dato». Appended last (create or replace only appends).
-- No SCORING_VERSION change.

alter table public.profiles add column seller_filter_access boolean not null default false;
comment on column public.profiles.seller_filter_access is
  'PRO-01: plan_feature(id, ''seller_filter'') as last synced (sync_seller_filter_access). A change marks the user''s strict searches for rematch.';

-- Only the true ones: no updated_at bump for everyone else.
update public.profiles p set seller_filter_access = true where public.plan_feature(p.id, 'seller_filter');

-- The sweep's candidates: few rows (Pro and admins).
create index profiles_seller_filter_expiry_idx on public.profiles (plan_expires_at) where seller_filter_access;

create function public.sync_seller_filter_access(p_user uuid default null, p_everyone boolean default false)
returns integer
language plpgsql security definer set search_path = '' as $$
declare v_marked integer;
begin
  with cand as (
    select p.id, public.plan_feature(p.id, 'seller_filter') v
      from public.profiles p
     where case when p_user is not null then p.id = p_user
                when p_everyone then true
                -- Time is the one input that changes without a write: a paid
                -- plan whose plan_expires_at passed (admins never expire).
                else p.seller_filter_access and p.role <> 'admin' and p.plan_expires_at <= now() end
  ), changed as (
    update public.profiles p set seller_filter_access = c.v
      from cand c
     where p.id = c.id and p.seller_filter_access is distinct from c.v
    returning p.id
  ), marked as (
    update public.search_profiles sp set rematch_requested_at = now()
      from changed c
     where sp.user_id = c.id and jsonb_typeof(sp.filters->'seller_types') = 'array'
    returning sp.id
  )
  select count(*) into v_marked from marked;
  return v_marked;
end $$;
comment on function public.sync_seller_filter_access(uuid, boolean) is
  'PRO-01: recompute profiles.seller_filter_access (one user, every user, or the expired ones) and mark the strict searches of those whose flag changed for rematch. Returns how many searches it marked.';

create function public.profiles_sync_seller_filter() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  if tg_op = 'INSERT' or old.plan is distinct from new.plan
     or old.plan_expires_at is distinct from new.plan_expires_at or old.role is distinct from new.role then
    perform public.sync_seller_filter_access(new.id);
  end if;
  return null;
end $$;

-- After: plan_feature reads the row as written. seller_filter_access is not in
-- the column list, so the sync's own update doesn't fire it again.
create trigger profiles_sync_seller_filter
  after insert or update of plan, plan_expires_at, role on public.profiles
  for each row execute function public.profiles_sync_seller_filter();

create function public.app_config_sync_seller_filter() returns trigger
language plpgsql security definer set search_path = '' as $$
declare v_old jsonb := case when tg_op = 'UPDATE' then old.value else '{}'::jsonb end;
begin
  if jsonb_typeof(new.value) = 'object' and exists (
       select 1 from jsonb_object_keys(new.value || case when jsonb_typeof(v_old) = 'object' then v_old else '{}' end) k
        where (case when jsonb_typeof(v_old) = 'object' then v_old else '{}' end)->k->'seller_filter'
              is distinct from new.value->k->'seller_filter') then
    perform public.sync_seller_filter_access(null, true);
  end if;
  return null;
end $$;

create trigger app_config_sync_seller_filter
  after insert or update of value on public.app_config
  for each row when (new.key = 'plan_limits') execute function public.app_config_sync_seller_filter();

create function public.search_profiles_owner_seller_rematch() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  if jsonb_typeof(new.filters->'seller_types') = 'array'
     and public.plan_feature(old.user_id, 'seller_filter') is distinct from public.plan_feature(new.user_id, 'seller_filter') then
    new.rematch_requested_at := now();
  end if;
  return new;
end $$;

create trigger search_profiles_owner_seller_rematch
  before update of user_id on public.search_profiles
  for each row when (old.user_id is distinct from new.user_id)
  execute function public.search_profiles_owner_seller_rematch();

revoke all on function public.sync_seller_filter_access(uuid, boolean), public.profiles_sync_seller_filter(),
  public.app_config_sync_seller_filter(), public.search_profiles_owner_seller_rematch()
  from public, anon, authenticated;

-- 20261007120000's, plus the sync (first, so the sweep sees the expiry the
-- pause below acts on).
create or replace function public.expire_commercial_access(p_user uuid default null) returns integer
language plpgsql security definer set search_path = '' as $$
declare v_count int;
begin
  perform public.sync_seller_filter_access(p_user);
  with paused as (
    update public.search_profiles sp set enabled = false
    where sp.enabled and (p_user is null or sp.user_id = p_user)
      and not public.search_access_active(sp.id) returning sp.user_id, sp.id
  ) insert into public.events(user_id, name, props)
    select user_id, 'search_paused_by_plan', jsonb_build_object('search_profile_id', id) from paused;
  get diagnostics v_count = row_count;
  update public.notifications n set status = 'skipped', error = 'plan_access_expired'
    where n.status in ('queued', 'digest') and (p_user is null or n.user_id = p_user)
      and not public.commercial_access_active(n.user_id);
  return v_count;
end $$;

-- match_cards: 20261119120000_x01_tracking.sql's definition plus seller_unknown last.
create or replace view public.match_cards with (security_invoker = true) as
select m.id                              as match_id,
       m.search_profile_id,
       sp.name                           as profile_name,
       sp.user_id,
       m.listing_id,
       m.score,
       m.level,
       m.is_backfill,
       m.generated_at,
       m.price_ref,
       m.red_flags,
       l.title,
       l.make,
       l.model,
       l.trim,
       l.year,
       l.price,
       l.currency,
       l.price_usd,
       l.mileage_km,
       l.transmission,
       l.fuel,
       l.location_text,
       l.source,
       l.images,
       l.published_at,
       l.first_seen_at,
       l.status                          as listing_status,
       l.probable_repost_of,
       coalesce(i.status, 'new')         as status,
       coalesce(i.saved, false)          as saved,
       i.rejection_reason,
       l.price_published,
       l.price_published_currency,
       l.price_source,
       l.description_facts -> 'price_check' ->> 'effective_kind' as price_kind,
       coalesce((l.description_facts -> 'financing' ->> 'offered')::boolean, false) as financing_offered,
       l.body_type,
       i.note,
       coalesce(m.match_reasons -> 'seller' ->> 'result' = 'unknown'
                and m.match_reasons -> 'seller' ->> 'kind' = 'hard', false) as seller_unknown
  from public.matches m
  join public.search_profiles sp on sp.id = m.search_profile_id
  join public.listings l on l.id = m.listing_id
  left join public.user_listing_interactions i
    on i.user_id = sp.user_id and i.listing_id = m.listing_id;

notify pgrst, 'reload schema';
