-- Bot de prospección en frío (docs/PROSPECCION.md).
--
-- Todos los días el bot (worker/prospector, en la PC de Juan) deja listos unos
-- 30 mensajes de WhatsApp para agencias y revendedores; Juan los manda a mano
-- desde /admin/prospeccion y marca ahí quién respondió.
--
--   prospects          un vendedor (o varios perfiles del mismo negocio) y su estado
--   prospect_messages  cada mensaje escrito: hechos, variantes, revisión, texto final
--   prospect_events    lo que hizo Juan: enviado, respondió, no le interesa...
--
-- Acceso: solo service_role, RLS sin políticas, nada que pueda leer un cliente.
-- La web escribe solo con public.admin_prospect_action, que vuelve a comprobar
-- que el actor sea admin (como admin_experiments, 20261220120000).
--
-- Cadencia (Juan, 15/11/2026): primer mensaje; si no responde, seguimiento a
-- los 5 días hábiles; si sigue sin responder, último mensaje 15 días después del
-- seguimiento; después, cerrado. Días hábiles = lunes a viernes, en hora argentina.

create table public.prospects (
  id bigint generated always as identity primary key,
  -- La clave estable: el primer "fuente|nombre" de sus perfiles, en orden.
  prospect_key text not null unique check (length(prospect_key) between 3 and 300),
  seller_keys text[] not null check (cardinality(seller_keys) between 1 and 20),
  kind text not null check (kind in ('agencia', 'persona')),
  display_name text not null check (length(display_name) between 1 and 200),
  first_name text check (first_name is null or length(first_name) <= 60),
  sources text[] not null default '{}',
  province_id text,
  region text,
  locality text,
  -- 549 + característica + número, el formato de wa.me.
  phone text check (phone is null or phone ~ '^549[1-3][0-9]{9}$'),
  -- aviso: lo escribió en su aviso; pagina_aviso: lo muestra la página del aviso;
  -- web: canal público del negocio; manual: lo cargó Juan.
  phone_source text check (phone_source is null or phone_source in ('aviso', 'pagina_aviso', 'web', 'guardado', 'manual')),
  phone_evidence text check (phone_evidence is null or length(phone_evidence) <= 1000),
  phone_checked_at timestamptz,
  status text not null default 'new' check (status in (
    'new',             -- conocido, sin mensaje
    'no_contact',      -- sin WhatsApp: no ocupa lugar en la tanda
    'queued',          -- primer mensaje listo, sin enviar
    'contacted',       -- primer mensaje enviado
    'followed_up',     -- seguimiento enviado
    'replied',         -- respondió (lo marca Juan)
    'not_interested',
    'wrong_number',
    'closed')),        -- se cerró: a mano o al enviar el último mensaje
  step_sent smallint not null default 0 check (step_sent between 0 and 3),
  next_due_on date,
  listing_count integer,
  first_sent_at timestamptz,
  last_sent_at timestamptz,
  replied_at timestamptz,
  closed_at timestamptz,
  notes text check (notes is null or length(notes) <= 2000),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index prospects_status_idx on public.prospects (status, next_due_on);
create index prospects_seller_keys_idx on public.prospects using gin (seller_keys);
create index prospects_phone_idx on public.prospects (phone) where phone is not null;

create table public.prospect_messages (
  id bigint generated always as identity primary key,
  prospect_id bigint not null references public.prospects (id) on delete cascade,
  step text not null check (step in ('first', 'followup', 'last')),
  batch_date date not null,
  -- ready: listo para mandar; sent: enviado; skipped: Juan no lo quiso;
  -- rejected: no pasó la revisión; expired: nadie lo mandó a tiempo.
  status text not null default 'ready' check (status in ('ready', 'sent', 'skipped', 'rejected', 'expired')),
  facts jsonb not null,
  variants jsonb not null default '[]',
  chosen_index smallint check (chosen_index is null or chosen_index between 0 and 1),
  final_text text check (final_text is null or length(final_text) <= 2000),
  edited boolean not null default false,
  hook_type text check (hook_type is null or hook_type in
    ('oportunidad', 'stock_viejo', 'precio_vs_zona', 'demanda', 'dejaron_de_publicarse')),
  hook_listing_id bigint,
  hook_url text,
  review jsonb not null default '{}',
  model text,
  sent_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint prospect_messages_ready_text check (status not in ('ready', 'sent') or final_text is not null)
);
create index prospect_messages_status_idx on public.prospect_messages (status, batch_date);
create index prospect_messages_prospect_idx on public.prospect_messages (prospect_id, created_at);
-- Un solo mensaje listo por prospecto a la vez.
create unique index prospect_messages_one_ready on public.prospect_messages (prospect_id) where status = 'ready';

create table public.prospect_events (
  id bigint generated always as identity primary key,
  prospect_id bigint not null references public.prospects (id) on delete cascade,
  message_id bigint references public.prospect_messages (id) on delete set null,
  kind text not null check (kind in ('sent', 'replied', 'not_interested', 'wrong_number', 'closed',
                                     'skipped', 'edited', 'chose_variant', 'reopened', 'phone_set')),
  note text check (note is null or length(note) <= 2000),
  actor_id uuid,
  created_at timestamptz not null default now()
);
create index prospect_events_kind_idx on public.prospect_events (kind, created_at);
create index prospect_events_prospect_idx on public.prospect_events (prospect_id, created_at);

alter table public.prospects enable row level security;
alter table public.prospect_messages enable row level security;
alter table public.prospect_events enable row level security;
revoke all on public.prospects, public.prospect_messages, public.prospect_events
  from public, anon, authenticated, service_role;
grant select, insert, update on public.prospects, public.prospect_messages, public.prospect_events to service_role;

-- n días hábiles (lunes a viernes) después de d.
create function public.prospect_add_business_days(d date, n integer) returns date
language sql immutable set search_path = '' as $$
  select max(x)::date from (
    select x from generate_series(d + 1, d + n * 2 + 7, interval '1 day') as g(x)
     where extract(isodow from x) < 6
     order by x limit greatest(n, 0)
  ) s;
$$;

-- Lo que hace Juan desde /admin/prospeccion. Una sola función para que cada
-- cambio de estado y su evento queden juntos.
--   p_action: sent | replied | not_interested | wrong_number | closed | skipped
--             | edited (p_text = texto nuevo) | chose_variant (p_text = '0' o '1')
--             | reopened | phone_set (p_text = número en formato 549...)
--   p_message_id: el mensaje al que se refiere (sent, skipped, edited, chose_variant).
create function public.admin_prospect_action(
  p_actor_id uuid, p_prospect_id bigint, p_message_id bigint, p_action text, p_text text
) returns text
language plpgsql security invoker set search_path = '' as $$
declare
  v_today date := (now() at time zone 'America/Argentina/Buenos_Aires')::date;
  v_msg public.prospect_messages;
  v_variant jsonb;
begin
  perform 1 from public.profiles where id = p_actor_id and role = 'admin';
  if not found then raise exception 'admin_required' using errcode = '42501'; end if;
  perform 1 from public.prospects where id = p_prospect_id for update;
  if not found then raise exception 'prospect_not_found' using errcode = 'P0002'; end if;

  if p_message_id is not null then
    select * into v_msg from public.prospect_messages where id = p_message_id and prospect_id = p_prospect_id for update;
    if not found then raise exception 'message_not_found' using errcode = 'P0002'; end if;
  end if;

  if p_action in ('sent', 'skipped', 'edited', 'chose_variant') and v_msg.id is null then
    raise exception 'message_required' using errcode = '22023';
  end if;
  if p_action in ('sent', 'skipped', 'edited', 'chose_variant') and v_msg.status <> 'ready' then
    raise exception 'message_not_ready' using errcode = '22023';
  end if;

  case p_action
  when 'sent' then
    update public.prospect_messages set status = 'sent', sent_at = now(), updated_at = now() where id = v_msg.id;
    update public.prospects set
      step_sent = greatest(step_sent, case v_msg.step when 'first' then 1 when 'followup' then 2 else 3 end),
      status = case
        when status in ('replied', 'not_interested', 'wrong_number') then status
        when v_msg.step = 'first' then 'contacted'
        when v_msg.step = 'followup' then 'followed_up'
        else 'closed' end,
      next_due_on = case
        when status in ('replied', 'not_interested', 'wrong_number') then null
        when v_msg.step = 'first' then public.prospect_add_business_days(v_today, 5)
        when v_msg.step = 'followup' then v_today + 15
        else null end,
      closed_at = case when v_msg.step = 'last' then now() else closed_at end,
      first_sent_at = coalesce(first_sent_at, now()), last_sent_at = now(), updated_at = now()
    where id = p_prospect_id;
  when 'replied' then
    update public.prospects set status = 'replied', replied_at = coalesce(replied_at, now()), next_due_on = null,
      updated_at = now() where id = p_prospect_id;
    update public.prospect_messages set status = 'skipped', updated_at = now()
     where prospect_id = p_prospect_id and status = 'ready';
  when 'not_interested', 'wrong_number', 'closed' then
    update public.prospects set status = p_action, next_due_on = null, closed_at = coalesce(closed_at, now()),
      updated_at = now() where id = p_prospect_id;
    update public.prospect_messages set status = 'skipped', updated_at = now()
     where prospect_id = p_prospect_id and status = 'ready';
  when 'skipped' then
    update public.prospect_messages set status = 'skipped', updated_at = now() where id = v_msg.id;
    -- Un primer mensaje descartado devuelve al prospecto a la base: el bot puede volver a escribirle otro día.
    update public.prospects set status = 'new', updated_at = now()
     where id = p_prospect_id and status = 'queued';
  when 'edited' then
    if p_text is null or length(btrim(p_text)) = 0 or length(p_text) > 2000 then
      raise exception 'invalid_text' using errcode = '22023';
    end if;
    update public.prospect_messages set final_text = btrim(p_text), edited = true, updated_at = now() where id = v_msg.id;
  when 'chose_variant' then
    if p_text not in ('0', '1') then raise exception 'invalid_variant' using errcode = '22023'; end if;
    v_variant := v_msg.variants -> p_text::int;
    if v_variant is null then raise exception 'invalid_variant' using errcode = '22023'; end if;
    update public.prospect_messages set chosen_index = p_text::int, final_text = v_variant ->> 'text',
      hook_type = v_variant ->> 'hook_type', edited = false, updated_at = now() where id = v_msg.id;
  when 'reopened' then
    update public.prospects set
      status = case step_sent when 0 then 'new' when 1 then 'contacted' when 2 then 'followed_up' else 'closed' end,
      next_due_on = case when step_sent between 1 and 2 then v_today else null end,
      replied_at = null, closed_at = null, updated_at = now()
    where id = p_prospect_id;
  when 'phone_set' then
    if p_text !~ '^549[1-3][0-9]{9}$' then raise exception 'invalid_phone' using errcode = '22023'; end if;
    update public.prospects set phone = p_text, phone_source = 'manual', phone_evidence = null,
      status = case when status = 'no_contact' then 'new' else status end, updated_at = now()
    where id = p_prospect_id;
  else
    raise exception 'invalid_action' using errcode = '22023';
  end case;

  insert into public.prospect_events (prospect_id, message_id, kind, note, actor_id)
  values (p_prospect_id, v_msg.id, p_action,
          case when p_action in ('edited', 'phone_set') then null else nullif(btrim(coalesce(p_text, '')), '') end,
          p_actor_id);
  return p_action;
end;
$$;

revoke all on function public.admin_prospect_action(uuid, bigint, bigint, text, text) from public, anon, authenticated;
grant execute on function public.admin_prospect_action(uuid, bigint, bigint, text, text) to service_role;
revoke all on function public.prospect_add_business_days(date, integer) from public, anon, authenticated;
grant execute on function public.prospect_add_business_days(date, integer) to service_role;
