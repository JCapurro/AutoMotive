-- PRO-01 · Solo particulares y mensaje listo (docs/BACKLOG_PRODUCTO_2026-10.md,
-- ítem PRO-01; diseño docs/superpowers/specs/2026-10-31-pro01-contacto-design.md;
-- plan docs/superpowers/plans/2026-10-31-pro01-contacto.md).
--
-- * plan_limits.pro.seller_filter: the strict seller filter
--   (search_profiles.filters.seller_types) applies. The worker reads it per
--   search (db/repos/profiles.py); without it the stored type is a soft
--   preference, as Particular has today. Never rejected on save.
-- * plan_limits.pro.contact_email: the «mensaje listo» block in Pro's
--   opportunity email. Both only added when missing, so a toggle already
--   turned off in /admin/config stays off.
-- * profiles.contact_template: the user's template for that message (null =
--   the default one). The web lints it on save; the worker and the listing
--   page lint it again on read and fall back to the default one.
-- * matches.contact_questions: the listing's specific seller questions
--   (intelligence/seller_questions.question_texts), written with seller_questions.
-- * search_filters_problem: filters.seller_types is absent, null or a
--   one-element array of 'private' or 'dealer'.
-- No SCORING_VERSION change.

update public.app_config
   set value = jsonb_set(value, '{pro}', coalesce(value->'pro', '{}')
                 || case when value->'pro' ? 'seller_filter' then '{}'::jsonb else '{"seller_filter": true}' end
                 || case when value->'pro' ? 'contact_email' then '{}'::jsonb else '{"contact_email": true}' end)
 where key = 'plan_limits';

alter table public.profiles
  add column contact_template text
    constraint profiles_contact_template_check
    check (contact_template is null or (char_length(contact_template) <= 500 and btrim(contact_template, E' \t\n\r\f\x0b') <> ''));
comment on column public.profiles.contact_template is
  'PRO-01: the template of the message for sellers ({auto}, {preguntas}); null = the default. Linted by the web on save and again on read.';
grant update (contact_template) on public.profiles to authenticated;

alter table public.matches add column contact_questions text[];
comment on column public.matches.contact_questions is
  'PRO-01: the questions specific to this listing (question_texts, up to 3) for the ready-to-send message; null on rows before PRO-01.';

-- 20261030120000's, plus filters.seller_types. create or replace keeps the
-- grants (server-only) and the volatility.
create or replace function public.search_filters_problem(p_filters jsonb) returns text
language sql immutable set search_path = '' as $$
  select case
    when coalesce(jsonb_typeof(p_filters->'make'), 'null') not in ('null', 'string')
      or coalesce(jsonb_typeof(p_filters->'model'), 'null') not in ('null', 'string')
      or coalesce(jsonb_typeof(p_filters->'body_types'), 'null') not in ('null', 'array')
      or (jsonb_typeof(p_filters->'body_types') = 'array'
          and exists (select 1 from jsonb_array_elements(p_filters->'body_types') b
                       where jsonb_typeof(b) <> 'string'))
      or coalesce(jsonb_typeof(p_filters->'seller_types'), 'null') not in ('null', 'array')
      or (jsonb_typeof(p_filters->'seller_types') = 'array'
          and (jsonb_array_length(p_filters->'seller_types') <> 1
               or not (p_filters->'seller_types'->0) <@ '["private", "dealer"]'::jsonb
               or jsonb_typeof(p_filters->'seller_types'->0) <> 'string'))
    then 'invalid_filters'
  end
$$;

notify pgrst, 'reload schema';
