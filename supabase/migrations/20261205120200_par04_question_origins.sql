-- PAR-04 · origen de las preguntas al vendedor (docs/BACKLOG_PRODUCTO_2026-10.md,
-- ítem PAR-04; diseño docs/superpowers/specs/2026-11-03-par04-guias-design.md,
-- decisión 8).
--
-- matches.question_origins: where each question of seller_questions came from,
-- in order, for the /admin inspector:
--   [{"key": "timing_belt", "origin": "template"},
--    {"key": "guide:12:0", "origin": "guide", "guide_id": 12}]
-- The worker writes it next to seller_questions only when the column exists.
-- matches has column grants: like every column but margin_ref
-- (pro02_margin_test.sql), it is readable by its owner (RLS), so a web select
-- of every column keeps working. It says nothing the questions don't. Applies
-- on an empty base; the web of main does not read it.

alter table public.matches add column if not exists question_origins jsonb
  check (question_origins is null or jsonb_typeof(question_origins) = 'array');

grant select (question_origins) on public.matches to anon, authenticated;

comment on column public.matches.question_origins is
  'PAR-04: origen de cada pregunta de seller_questions (template | guide), para el inspector de /admin.';

notify pgrst, 'reload schema';
