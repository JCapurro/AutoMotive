-- The «7 días gratis» offer (bonus_trial_offer, docs/MAILS_DE_PLAN.md) goes
-- only to accounts that showed interest. Juan, 23/11/2026: «la oferta de 7
-- dias gratis solo se debe enviar si el usuario estuvo activo en la
-- plataforma o clickeo algun aviso. si no demostro ningun interes no».
--
-- Showed interest = any of these, at any time since the account exists:
--   1. looked at a car we found: alert_clicked, listing_detail_viewed,
--      listing_outbound_clicked, listing_saved or listing_discarded (the
--      admin's ENGAGED set, web/lib/admin-users-data.ts), or a notification
--      with clicked_at;
--   2. clicked one of our plan emails (lifecycle_email_clicked);
--   3. did something on an Argentina calendar day after the day its trial
--      started: any event but the ones the system writes on its own and the
--      results page being shown (search_results_viewed).
--
-- bonus_offer_eligible is the one test at claim time and at send time
-- (lifecycle_email_eligible), so an account that shows interest later becomes
-- eligible then: the claim keeps old trials due (bonus_trial.backfill_since).
-- One function replaced, one added; no table changes.

set local lock_timeout = '5s';

-- Events the system writes without the person doing anything at that moment.
-- web/lib/admin-users-data.ts SYSTEM_EVENTS, plus:
--   bonus_trial_ended           worker, record_bonus_trial_ends (any hour)
--   payment_confirmed           record_commercial_payment (admin) and the Mercado Pago webhook
--   payment_refunded            refund_commercial_payment (admin) and the webhook
--   pass_extended               record_commercial_payment and the webhook
--   searches_reactivated        reactivate_paused_searches, inside the payment flow
--   reactivated_from_count_email  the same, after a count email
--   free_trial_enabled, commercial_pilot_enabled, agency_founder_marked,
--   agency_founder_released     admin actions
create function public.showed_interest(p_user uuid) returns boolean
language sql stable security definer set search_path = '' as $$
  select exists (
           select 1 from public.events e
            where e.user_id = p_user
              and e.name in ('alert_clicked', 'listing_detail_viewed', 'listing_outbound_clicked',
                             'listing_saved', 'listing_discarded', 'lifecycle_email_clicked'))
      or exists (select 1 from public.notifications n where n.user_id = p_user and n.clicked_at is not null)
      or exists (
           select 1 from public.profiles p join public.events e on e.user_id = p.id
            where p.id = p_user
              and p.free_trial_started_at is not null
              and e.created_at >= (date_trunc('day', p.free_trial_started_at at time zone 'America/Argentina/Buenos_Aires')
                                   + interval '1 day') at time zone 'America/Argentina/Buenos_Aires'
              and e.name not in ('alert_sent', 'lifecycle_email_sent', 'founder_email_sent', 'search_paused_by_plan',
                                 'trial_ended', 'free_trial_started', 'assisted_review_shown', 'assisted_fallback_shown',
                                 'search_results_viewed',
                                 'bonus_trial_ended', 'payment_confirmed', 'payment_refunded', 'pass_extended',
                                 'searches_reactivated', 'reactivated_from_count_email', 'free_trial_enabled',
                                 'commercial_pilot_enabled', 'agency_founder_marked', 'agency_founder_released'))
$$;

revoke all on function public.showed_interest(uuid) from public, anon, authenticated;

-- 20261111120000's audience, plus showed_interest.
create or replace function public.bonus_offer_eligible(p_user uuid) returns boolean
language sql stable security definer set search_path = '' as $$
  select coalesce((
    select public.lifecycle_contact_ok(p.id)
       and p.plan = 'free'
       and p.free_trial_started_at is not null
       and p.bonus_trial_started_at is null
       and public.plan_limits_for(p.id)->>'state' = 'expired'
       and not exists (select 1 from public.commercial_payments cp where cp.user_id = p.id)
       and not public.checkout_in_progress(p.id)
       and (exists (select 1 from public.matches m join public.search_profiles sp on sp.id = m.search_profile_id
                     where sp.user_id = p.id)
         or exists (select 1 from public.expired_search_matches x join public.search_profiles sp on sp.id = x.search_profile_id
                     where sp.user_id = p.id))
       and public.showed_interest(p.id)
      from public.profiles p where p.id = p_user), false)
$$;

revoke all on function public.bonus_offer_eligible(uuid) from public, anon, authenticated;

notify pgrst, 'reload schema';
