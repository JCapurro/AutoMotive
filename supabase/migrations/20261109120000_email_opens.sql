-- Aperturas de email: un píxel de 1 px en cada alerta y cada mail de plan.
--
-- Hasta acá opened_at solo se marcaba con el clic (track_notification_click),
-- así que un email sin clic no distinguía «no llegó» de «no interesó». El
-- píxel (/o/<id>, web/app/o/[id]/route.ts) marca la primera apertura. Los
-- proxys de imágenes (Gmail) cuentan como apertura real; Apple Mail
-- precarga las imágenes y puede contar de más.
--
-- track_email_open(kind, id): 'n' para notifications, 'm' para
-- lifecycle_emails. Solo emails enviados; devuelve si marcó algo nuevo.

alter table public.lifecycle_emails add column opened_at timestamptz;

create function public.track_email_open(p_kind text, p_id bigint) returns boolean
language plpgsql security definer set search_path = '' as $$
declare
  v_found integer;
begin
  if p_kind = 'n' then
    update public.notifications set opened_at = now()
     where id = p_id and channel = 'email' and status = 'sent' and opened_at is null;
  elsif p_kind = 'm' then
    update public.lifecycle_emails set opened_at = now()
     where id = p_id and status = 'sent' and opened_at is null;
  else
    return false;
  end if;
  get diagnostics v_found = row_count;
  return v_found > 0;
end $$;

-- The click opened it too: a lifecycle click before the pixel loads (images off) still counts as an open.
create or replace function public.track_lifecycle_click(p_id bigint) returns text
language plpgsql security definer set search_path = '' as $$
declare
  v public.lifecycle_emails;
begin
  update public.lifecycle_emails set clicked_at = coalesce(clicked_at, now()), opened_at = coalesce(opened_at, now())
   where id = p_id and status = 'sent'
  returning * into v;
  if v.id is null then
    return null;
  end if;
  insert into public.events (user_id, name, props) values (v.user_id, 'lifecycle_email_clicked',
    jsonb_build_object('email_id', v.id, 'kind', v.kind, 'search_profile_id', v.search_profile_id));
  return v.target;
end $$;

revoke all on function public.track_email_open(text, bigint) from public, anon, authenticated;
grant execute on function public.track_email_open(text, bigint) to service_role;

notify pgrst, 'reload schema';
