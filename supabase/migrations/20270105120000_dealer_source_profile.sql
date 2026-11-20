-- Agencias: the Mercado Libre profile link loads the whole profile.
--
-- Juan, 20/11: «hacé que el link de mercadolibre cargue el perfil entero». Until
-- now a source only linked the listings we had already read for someone's
-- search (6 of 17 for the first agency that gave its profile). Now the worker
-- reads the seller's public page (…mercadolibre.com.ar/_CustId_<id>, every
-- page) when the source arrives and every DEALER_PROFILE_HOURS once approved
-- (worker pipeline/dealers.py read_profiles), stores its cars as ordinary
-- Mercado Libre listings with the seller's key, and the existing link step
-- makes them the agency's. These columns are that read's memory:
--
--   profile_read_at   the last read (null = never: read on the next tick)
--   profile_count     how many cars it saw
--   profile_error     why it was not complete, null when it was
--
-- While a source is pending the read also fills seller_key and
-- seller_name_hint with the seller it saw: the suggestion Juan approves in
-- /admin/agencias. Approving stays by hand (it is the check that the account
-- is the agency's). No function changes: members already read their sources.
-- Needs 20261228120000_dealer_program.sql.
--
-- Rollback: alter table public.dealer_sources drop column profile_read_at,
-- drop column profile_count, drop column profile_error;

alter table public.dealer_sources
  add column profile_read_at timestamptz,
  add column profile_count   integer check (profile_count is null or profile_count >= 0),
  add column profile_error   text check (profile_error is null or char_length(profile_error) <= 200);

create index dealer_sources_profile_due_idx on public.dealer_sources (profile_read_at nulls first)
  where source = 'mercadolibre' and status in ('pending', 'approved') and profile_url is not null;
