-- Tablero de experimentos de /admin/experiments.
--
-- Hasta hoy las fechas de arranque, las bases de comparación y el día de volver
-- a medir de cada experimento vivían en notas. Esta tabla las guarda junto a
-- la clave de app_config que prende o apaga cada experimento (el interruptor y
-- su historial se leen de app_config y admin_config_audit, no se copian acá).
--
-- Los resultados se cargan a mano: la primera versión no los calcula.
--
-- Acceso: igual que admin_config_audit (20261027145911). Solo el cliente de
-- servicio de la web llama a las funciones, después de requireAdmin; cada una
-- vuelve a comprobar que el actor sea admin y falla con admin_required.

create table public.admin_experiments (
  slug text primary key check (slug ~ '^[a-z0-9_]{1,60}$'),
  title text not null check (length(btrim(title)) between 1 and 120),
  config_key text check (config_key is null or length(config_key) between 1 and 200),
  hypothesis text not null default '' check (length(hypothesis) <= 2000),
  metric text not null default '' check (length(metric) <= 2000),
  baseline_text text check (baseline_text is null or length(baseline_text) <= 1000),
  baseline_value numeric,
  started_at timestamptz,
  review_at date,
  status text not null default 'running' check (status in ('running', 'won', 'lost', 'inconclusive', 'paused')),
  result_text text check (result_text is null or length(result_text) <= 1000),
  result_value numeric,
  verdict_note text check (verdict_note is null or length(verdict_note) <= 2000),
  decided_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  -- Un veredicto lleva fecha de decisión; un experimento abierto o pausado, no.
  constraint admin_experiments_decided_check check (
    (status in ('won', 'lost', 'inconclusive')) = (decided_at is not null)
  )
);
create index admin_experiments_status_idx on public.admin_experiments (status, review_at);

alter table public.admin_experiments enable row level security;
revoke all on public.admin_experiments from public, anon, authenticated, service_role;
grant select, insert, update on public.admin_experiments to service_role;

-- Crear un experimento. Devuelve el slug.
create function public.admin_create_experiment(
  p_actor_id uuid, p_slug text, p_title text, p_config_key text, p_hypothesis text, p_metric text,
  p_baseline_text text, p_baseline_value numeric, p_started_at timestamptz, p_review_at date
) returns text
language plpgsql security invoker set search_path = '' as $$
begin
  perform 1 from public.profiles where id = p_actor_id and role = 'admin';
  if not found then raise exception 'admin_required' using errcode = '42501'; end if;
  if exists (select 1 from public.admin_experiments where slug = p_slug) then
    raise exception 'experiment_exists' using errcode = '23505';
  end if;
  insert into public.admin_experiments (slug, title, config_key, hypothesis, metric, baseline_text, baseline_value, started_at, review_at)
  values (p_slug, btrim(p_title), nullif(btrim(p_config_key), ''), coalesce(p_hypothesis, ''), coalesce(p_metric, ''),
          nullif(btrim(p_baseline_text), ''), p_baseline_value, p_started_at, p_review_at);
  return p_slug;
end;
$$;

-- Editar lo que describe al experimento. No toca el estado ni el resultado.
create function public.admin_update_experiment(
  p_actor_id uuid, p_slug text, p_title text, p_config_key text, p_hypothesis text, p_metric text,
  p_baseline_text text, p_baseline_value numeric, p_started_at timestamptz, p_review_at date
) returns void
language plpgsql security invoker set search_path = '' as $$
begin
  perform 1 from public.profiles where id = p_actor_id and role = 'admin';
  if not found then raise exception 'admin_required' using errcode = '42501'; end if;
  update public.admin_experiments set
    title = btrim(p_title), config_key = nullif(btrim(p_config_key), ''), hypothesis = coalesce(p_hypothesis, ''),
    metric = coalesce(p_metric, ''), baseline_text = nullif(btrim(p_baseline_text), ''), baseline_value = p_baseline_value,
    started_at = p_started_at, review_at = p_review_at, updated_at = now()
  where slug = p_slug;
  if not found then raise exception 'experiment_not_found' using errcode = 'P0002'; end if;
end;
$$;

-- Registrar el veredicto o cambiar el estado. won/lost/inconclusive guardan el
-- resultado y la fecha de decisión; running (reabrir) los borra; paused solo
-- conserva la nota (por qué se pausó).
create function public.admin_record_experiment_verdict(
  p_actor_id uuid, p_slug text, p_status text, p_result_text text, p_result_value numeric, p_verdict_note text
) returns void
language plpgsql security invoker set search_path = '' as $$
declare
  v_decided boolean := p_status in ('won', 'lost', 'inconclusive');
begin
  perform 1 from public.profiles where id = p_actor_id and role = 'admin';
  if not found then raise exception 'admin_required' using errcode = '42501'; end if;
  if p_status is null or p_status not in ('running', 'won', 'lost', 'inconclusive', 'paused') then
    raise exception 'invalid_status' using errcode = '22023';
  end if;
  update public.admin_experiments set
    status = p_status,
    result_text = case when v_decided then nullif(btrim(p_result_text), '') end,
    result_value = case when v_decided then p_result_value end,
    verdict_note = case when v_decided or p_status = 'paused' then nullif(btrim(p_verdict_note), '') end,
    decided_at = case when v_decided then coalesce(decided_at, now()) end,
    updated_at = now()
  where slug = p_slug;
  if not found then raise exception 'experiment_not_found' using errcode = 'P0002'; end if;
end;
$$;

revoke all on function public.admin_create_experiment(uuid, text, text, text, text, text, text, numeric, timestamptz, date) from public, anon, authenticated;
revoke all on function public.admin_update_experiment(uuid, text, text, text, text, text, text, numeric, timestamptz, date) from public, anon, authenticated;
revoke all on function public.admin_record_experiment_verdict(uuid, text, text, text, numeric, text) from public, anon, authenticated;
grant execute on function public.admin_create_experiment(uuid, text, text, text, text, text, text, numeric, timestamptz, date) to service_role;
grant execute on function public.admin_update_experiment(uuid, text, text, text, text, text, text, numeric, timestamptz, date) to service_role;
grant execute on function public.admin_record_experiment_verdict(uuid, text, text, text, numeric, text) to service_role;

comment on table public.admin_experiments is
  'Tablero de experimentos de /admin/experiments: fechas, base y resultado cargado a mano. El interruptor vive en app_config (config_key).';

-- Los cuatro experimentos en marcha al 14/11/2026 (fechas en UTC). Lo que no
-- tiene una fuente queda en null: no se inventan bases.
insert into public.admin_experiments
  (slug, title, config_key, hypothesis, metric, baseline_text, baseline_value, started_at, review_at, status)
values
  ('trial_reserve', 'Prueba honesta (reserva de la prueba)', 'trial_reserve',
   'Si de los resultados de la prueba gratis solo una parte son publicaciones que ya estaban al crear la búsqueda y el resto queda para autos nuevos, más personas reciben una alerta de un auto nuevo durante la prueba.',
   'Porcentaje de las personas que hicieron una búsqueda y recibieron al menos una alerta. Se compara a quienes empiezan la prueba después de prender la reserva contra las de antes (docs/PRUEBA_HONESTA.md).',
   '48 % de las personas que buscaron recibieron una alerta (medido antes de prender la reserva).', 48,
   '2026-11-14 14:13:00+00', '2026-11-21', 'running'),
  ('landing_hero', 'Portada nueva (para tocar)', 'landing_hero',
   'Una portada donde la búsqueda se arma tocando modelo, presupuesto y zona, y que muestra los autos marcados hoy, hace que más visitantes empiecen una búsqueda y se registren que con la portada de siempre.',
   'Cada visita sin sesión queda en una variante (cookie hero_bucket de 0 a 99, la nueva si el número es menor al porcentaje de landing_hero). Los eventos landing_viewed, landing_search_started y landing_dialog_opened guardan props.variant: a = portada de siempre, b = nueva. signup_completed guarda props.hero (a o b). Se compara la tasa de b contra la de a, visitas vistas contra búsquedas empezadas y registros.',
   null, null,
   '2026-11-14 15:08:00+00', '2026-11-24', 'running'),
  ('zone_notice', 'Aviso de zona', 'zone_notice',
   'Avisar «En tu zona hay solo N publicaciones» y ofrecer ampliar la zona hace que más búsquedas autoguardadas lleguen a tener resultados.',
   'Búsquedas autoguardadas del modo asistido sin zona en el borrador, con 4 resultados o más a las 24 h de creadas. Objetivo: 65 % o más. Resguardo: que el cupo de la prueba no se llene dentro de la hora de creada en más del 30 % (docs/AVISO_ZONA.md).',
   '57 de 102 búsquedas (56 %) tenían 4 resultados o más a las 24 h, en la semana del 26/10.', 56,
   '2026-11-03 13:11:24+00', '2026-11-11', 'running'),
  ('near_zone', 'Aviso de auto cerca de la zona', 'near_zone',
   'Un email cuando aparece un auto nuevo que cumple todo menos la zona (unos km pasado el radio) recupera búsquedas con pocos resultados.',
   'Emails enviados (near_zone_notices con status = sent) contra las ampliaciones de zona (search_zone_widened) posteriores de la misma búsqueda (docs/AVISO_CERCA_DE_ZONA.md).',
   null, null,
   null, null, 'paused');

update public.admin_experiments set
  verdict_note = 'Apagado tras una primera pasada mala: 4 de 6 avisos estaban mal. El arreglo está en una PR sin mergear; se vuelve a prender cuando se apruebe.'
where slug = 'near_zone';

notify pgrst, 'reload schema';
