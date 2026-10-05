-- The web authorizes the verified owner's email before using service_role.
-- No browser role, including authenticated admins, can read this snapshot directly.
create table public.platform_health_checks (
  id smallint primary key check (id = 1),
  checked_at timestamptz not null,
  checks jsonb not null check (jsonb_typeof(checks) = 'object'),
  email_pending boolean not null default false,
  last_email_at timestamptz
);
alter table public.platform_health_checks enable row level security;
revoke all on public.platform_health_checks from public, anon, authenticated;
grant select, insert, update on public.platform_health_checks to service_role;
