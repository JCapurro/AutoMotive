-- search_activated: el email de bienvenida (docs/MAILS_DE_PLAN.md).
--
-- 45 minutos después de la primera búsqueda de una cuenta, un email dice que
-- la búsqueda está activa, cuántos autos ya coinciden y pide guardar el
-- remitente. Es el primer email que recibe la persona: si llega a Principal y
-- lo abre, los que siguen tienen más chances de llegar también. Desde el
-- 15/10/2026 salieron 66 emails a usuarios reales sin un solo clic.
--
-- Una vez por cuenta (event_key 'first'). Los 45 minutos dejan que el primer
-- rastreo cuente coincidencias. Va por el mismo circuito que los mails de
-- plan: ventana horaria, tope diario, baja y /m/<id>.
--
-- claim_lifecycle_emails y lifecycle_email_eligible se renombran a *_base y
-- las nuevas atienden search_activated y delegan el resto, para no copiar sus
-- cinco ramas.

alter table public.lifecycle_emails drop constraint lifecycle_emails_kind_check;
alter table public.lifecycle_emails add constraint lifecycle_emails_kind_check
  check (kind in ('trial_no_matches', 'trial_ended', 'pass_expiring', 'pass_expires_today',
                  'count_after_expiry', 'search_activated'));

alter function public.claim_lifecycle_emails(text, interval, integer) rename to claim_lifecycle_emails_base;
alter function public.lifecycle_email_eligible(bigint) rename to lifecycle_email_eligible_base;

-- Still worth sending: the account takes emails and the search is still on.
create function public.search_activated_eligible(p_user uuid, p_search bigint) returns boolean
language sql stable security definer set search_path = '' as $$
  select public.lifecycle_contact_ok(p_user)
     and exists (select 1 from public.search_profiles sp
                  where sp.id = p_search and sp.user_id = p_user and sp.enabled)
$$;

create function public.lifecycle_email_eligible(p_id bigint) returns boolean
language sql stable security definer set search_path = '' as $$
  select case when e.kind = 'search_activated' then public.search_activated_eligible(e.user_id, e.search_profile_id)
              else public.lifecycle_email_eligible_base(p_id) end
    from public.lifecycle_emails e where e.id = p_id
$$;

create function public.claim_lifecycle_emails(p_kind text, p_window interval, p_limit integer)
returns setof public.lifecycle_emails
language plpgsql security definer set search_path = '' as $$
begin
  if p_kind <> 'search_activated' then
    return query select * from public.claim_lifecycle_emails_base(p_kind, p_window, p_limit);
    return;
  end if;
  if p_window is null or coalesce(p_limit, 0) <= 0 then
    return;
  end if;
  return query
  with firsts as materialized (
    select sp.user_id, min(sp.created_at) + interval '45 minutes' as due_at
      from public.search_profiles sp
     group by sp.user_id
  ), due as (
    select f.user_id, f.due_at
      from firsts f
     where f.due_at <= now()
       and f.due_at > now() - p_window
       and not exists (select 1 from public.lifecycle_emails e where e.user_id = f.user_id and e.kind = p_kind)
  ), picked as (
    -- The account's active search that already found the most; "below
    -- comparables" is level high, as in trial_ended.
    select d.user_id, d.due_at, s.id as search_id, s.model, s.found_n, s.below_n
      from due d
      cross join lateral (
        select sp.id,
               coalesce(nullif(trim(concat_ws(' ', sp.filters->>'make', sp.filters->>'model')), ''), sp.name) as model,
               count(m.id) as found_n,
               count(m.id) filter (where m.level = 'high') as below_n
          from public.search_profiles sp
          left join public.matches m on m.search_profile_id = sp.id
         where sp.user_id = d.user_id and sp.enabled
         group by sp.id
         order by count(m.id) desc, sp.id
         limit 1) s
     where public.lifecycle_contact_ok(d.user_id)
     order by d.due_at, d.user_id
     limit p_limit
  )
  insert into public.lifecycle_emails (user_id, kind, event_key, search_profile_id, payload, target)
  select user_id, p_kind, 'first', search_id,
         jsonb_build_object('model', model, 'found', found_n, 'below', below_n),
         '/app/searches/' || search_id
    from picked
  on conflict (user_id, kind, event_key) do nothing
  returning *;
end $$;

revoke all on function public.claim_lifecycle_emails_base(text, interval, integer),
  public.lifecycle_email_eligible_base(bigint), public.search_activated_eligible(uuid, bigint),
  public.lifecycle_email_eligible(bigint), public.claim_lifecycle_emails(text, interval, integer)
  from public, anon, authenticated;
grant execute on function public.lifecycle_email_eligible(bigint), public.claim_lifecycle_emails(text, interval, integer)
  to service_role;

notify pgrst, 'reload schema';
