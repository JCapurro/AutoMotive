-- Serialize quota checks per account before counting queued/running/finished
-- jobs. Otherwise concurrent INSERTs can each observe the same free slot.
-- Keep this trigger VOLATILE: at READ COMMITTED the count needs a fresh
-- snapshot after waiting for the other transaction's profile lock.
create or replace function public.enforce_llm_rate_limit() returns trigger
language plpgsql
volatile
security definer
set search_path = ''
as $$
declare
  v_limits jsonb;
  v_max integer;
  v_count integer;
begin
  -- Model guides keep their separate budget (20261205120000_par04_model_guides).
  if new.kind = 'model_guide' then
    return new;
  end if;
  perform 1 from public.profiles where id = new.user_id for update;

  select value into v_limits from public.app_config where key = 'llm_limits';
  v_max := (v_limits ->> 'per_user_hour')::integer;
  if exists (select 1 from public.profiles where id = new.user_id and email_only) then
    v_max := coalesce((v_limits ->> 'email_only_per_user_hour')::integer, 5);
  end if;
  if v_max is null then
    return new;
  end if;

  select count(*) into v_count from public.llm_jobs
   where user_id = new.user_id and created_at > now() - interval '1 hour'
     and kind <> 'model_guide';
  if v_count >= v_max then
    raise exception 'llm_rate_limited'
      using errcode = 'P0001',
            detail = format('%s LLM jobs in the last hour (max %s)', v_count, v_max);
  end if;
  return new;
end;
$$;

-- CREATE OR REPLACE retains the existing server-only EXECUTE privileges.
notify pgrst, 'reload schema';
