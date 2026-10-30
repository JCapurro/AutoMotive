-- PAR-02 (tramo 1) · Checklist «Antes de señar» y texto de much_cheaper desde 35 %
-- (docs/BACKLOG_PRODUCTO_2026-10.md, ítem PAR-02; diseño
-- docs/superpowers/specs/2026-10-29-par02-checklist-design.md; plan
-- docs/superpowers/plans/2026-10-29-par02-checklist.md).
--
-- Data only, idempotent:
-- * app_config.red_flags.much_cheaper_verify_pct (35): from there the much_cheaper
--   flag text asks to verify everything before a down payment. Only added when
--   missing, so a value already tuned in /admin/config is kept.
-- * app_config.risk: the «Antes de señar» checklist switch and its official
--   links. Every link starts empty: Juan loads them from /admin/config. An
--   existing row is left alone.
-- No table, column, RLS, function or SCORING_VERSION change.

update public.app_config
   set value = value || '{"much_cheaper_verify_pct": 35}'::jsonb
 where key = 'red_flags'
   and jsonb_typeof(value) = 'object'
   and not (value ? 'much_cheaper_verify_pct');

insert into public.app_config(key, value) values
  ('risk', '{"checklist_enabled": true, "links": {"dnrpa": null, "patentes": [], "infracciones": [], "vtv": null, "form_08": null}}')
on conflict (key) do nothing;
