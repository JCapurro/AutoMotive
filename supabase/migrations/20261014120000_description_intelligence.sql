-- Reserve every description API attempt before calling the provider, including failures.
create table public.description_llm_runs (
  id bigint generated always as identity primary key,
  listing_id bigint references public.listings(id) on delete set null,
  input_hash text not null,
  started_at timestamptz not null default now(),
  completed_at timestamptz,
  error text
);
create index description_llm_runs_started_idx on public.description_llm_runs(started_at);
create index description_llm_runs_input_idx on public.description_llm_runs(listing_id, input_hash, started_at);
alter table public.description_llm_runs enable row level security;
revoke all on public.description_llm_runs from anon, authenticated;
grant all on public.description_llm_runs to postgres, service_role;
grant usage, select on sequence public.description_llm_runs_id_seq to postgres, service_role;
comment on table public.description_llm_runs is
  'Worker-only usage ledger: no description text, secrets or model responses. Counts failed attempts toward the daily cap.';
