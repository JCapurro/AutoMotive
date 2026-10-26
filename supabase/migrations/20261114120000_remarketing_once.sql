-- Una sola vez por cuenta (decisión de Juan, 26/10/2026): los mails de
-- remarketing no insisten.
--
--   2.5 (count_after_expiry, «la oportunidad que te perdiste»): un mail por
--   cuenta, en toda su vida. Antes salían hasta 3 por vencimiento (días 7, 14
--   y 21) y un ciclo nuevo por cada vencimiento. Sale el primero que tenga
--   algo para contar; después, nada más.
--
--   Remarketing a cuentas sin búsqueda: un solo mail por cuenta, 1A o 1B. El
--   seguimiento (search_feedback) se manda solo después de uno de esos, así
--   que deja de salir.
--
-- Cuenta lo que ya salió (status 'sent'): un mail fallido o salteado no llegó
-- y no bloquea. La regla está en las funciones de elegibilidad, así que vale
-- al reservar y otra vez justo antes de mandar.

create or replace function public.count_after_expiry_eligible(p_user uuid, p_event text) returns boolean
language sql stable security definer set search_path = '' as $$
  select coalesce((
    select extract(epoch from a.ended_at)::bigint::text = split_part(p_event, ':', 1)
       and a.ended_at > now() - interval '23 days'
       and not public.checkout_in_progress(p_user)
       and not exists (select 1 from public.lifecycle_emails e
                        where e.user_id = p_user and e.kind = 'count_after_expiry' and e.status = 'sent')
      from (select public.count_after_expiry_end(p_user) as ended_at) a), false)
$$;

create or replace function public.no_search_eligible(p_user uuid) returns boolean
language sql stable security definer set search_path = '' as $$
  select public.lifecycle_contact_ok(p_user)
     and not exists (select 1 from public.search_profiles sp where sp.user_id = p_user)
     and not exists (select 1 from public.lifecycle_emails e
                      where e.user_id = p_user and e.status = 'sent'
                        and e.kind in ('search_abandoned', 'search_not_started', 'search_feedback'))
$$;
