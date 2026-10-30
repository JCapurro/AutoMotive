-- Bot de pocos resultados (docs/POCOS_RESULTADOS.md).
--
-- The worker (pipeline/low_results.py) measures every enabled search by model:
-- one with app_config.low_results.max_results results or fewer, whatever
-- their level, gets a diagnosis. Its make/model's market of the last 30 days
-- goes through the search's hard filters (intelligence/low_results.py) and an
-- LLM explains, from that funnel, why so few came up ("elegiste solo 2015:
-- de ese año hubo 3"). The user gets it once per set of filters on the
-- search's channels and on the search's page, with "seguimos atentos".
--
-- * search_diagnoses: the latest diagnosis per search. The owner reads it and
--   may only set dismissed_at (hide the card); the worker writes the rest.
-- * app_config.low_results: the bot's knobs, editable from /admin/config.

create table public.search_diagnoses (
  search_profile_id    bigint primary key references public.search_profiles (id) on delete cascade,
  user_id              uuid not null references public.profiles (id) on delete cascade,
  -- intelligence/low_results.fingerprint: filters, place and radius when diagnosed.
  fingerprint          text not null,
  result_count         integer not null check (result_count >= 0),
  max_results          integer not null check (max_results >= 0),
  funnel               jsonb not null default '{}' check (jsonb_typeof(funnel) = 'object'),
  explanation          text not null check (length(explanation) between 1 and 2000),
  suggestions          jsonb not null default '[]' check (jsonb_typeof(suggestions) = 'array'),
  -- llm_jobs.provider style ("openai:gpt-6-luna"); null when the fixed text was used.
  provider             text,
  llm_error            text,
  created_at           timestamptz not null default now(),
  notified_at          timestamptz,
  notified_fingerprint text,
  dismissed_at         timestamptz
);
create index search_diagnoses_user_idx on public.search_diagnoses (user_id);

comment on table public.search_diagnoses is
  'Bot de pocos resultados: why a search brings few results (worker pipeline/low_results.py).';

alter table public.search_diagnoses enable row level security;
revoke all on public.search_diagnoses from public, anon, authenticated;
grant select on public.search_diagnoses to authenticated;
grant update (dismissed_at) on public.search_diagnoses to authenticated;
grant all on public.search_diagnoses to service_role;
create policy "search_diagnoses: read own" on public.search_diagnoses for select to authenticated
  using (user_id = (select auth.uid()));
create policy "search_diagnoses: dismiss own" on public.search_diagnoses for update to authenticated
  using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));

insert into public.app_config (key, value) values ('low_results', '{
  "enabled": true,
  "max_results": 3,
  "min_age_hours": 24,
  "recheck_days": 7,
  "max_per_tick": 10,
  "notify": true
}') on conflict (key) do nothing;
