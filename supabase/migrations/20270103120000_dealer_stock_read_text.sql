-- Agencias: every stock list goes through the reader, a spreadsheet too.
--
-- Juan, 20/11: «el input de stock, por imagen, xlsx, csv, excel o lo que sea, debe
-- pasar por un modelo de llm donde interprete la carga». A photo or a PDF already
-- did (20261229120000, dealer_stock_read). Now the web also sends a CSV/XLSX: it
-- reads the file to a table as before (plate columns dropped), and sends that
-- table as text (media type 'text/csv') through the same RPC, the same daily cap
-- and the same switch (dealer_program.photo_import_enabled, off by default: it
-- uses the LLM, it costs per read). With the switch off, the cap reached or the
-- read failed, the web falls back to the column guesser it had.
--
-- Only the accepted type changes: the table's check and the RPC's list.
-- Needs 20261229120000_dealer_phase1_extras.sql.
--
-- Rollback: put the two lists back without 'text/csv'.

alter table public.dealer_stock_reads drop constraint dealer_stock_reads_media_type_check;
alter table public.dealer_stock_reads add constraint dealer_stock_reads_media_type_check
  check (media_type in ('image/jpeg', 'image/png', 'image/webp', 'application/pdf', 'text/csv'));

create or replace function public.dealer_request_stock_read(p_data text, p_media_type text, p_filename text default null)
returns bigint
language plpgsql volatile security definer set search_path = '' as $$
declare
  v_dealer bigint := public.dealer_require_member();
  v_uid    uuid := (select auth.uid());
  v_prog   jsonb := public.dealer_program();
  v_bytes  bytea;
  v_today  timestamptz := date_trunc('day', now() at time zone 'America/Argentina/Buenos_Aires')
                            at time zone 'America/Argentina/Buenos_Aires';
  v_read   bigint;
  v_job    bigint;
begin
  if not (v_prog ->> 'photo_import_enabled')::boolean then
    raise exception 'photo_import_off' using errcode = 'P0001';
  end if;
  if p_media_type is null or p_media_type not in ('image/jpeg', 'image/png', 'image/webp', 'application/pdf', 'text/csv') then
    raise exception 'invalid_file:type' using errcode = 'P0001';
  end if;
  if p_data is null or length(p_data) = 0 then
    raise exception 'invalid_file:data' using errcode = 'P0001';
  end if;
  if length(p_data) > 5600000 then                          -- 4 MB of base64, with room for line breaks
    raise exception 'file_too_big' using errcode = 'P0001';
  end if;
  begin
    v_bytes := decode(p_data, 'base64');
  exception when others then
    raise exception 'invalid_file:data' using errcode = 'P0001';
  end;
  if length(v_bytes) = 0 then
    raise exception 'invalid_file:data' using errcode = 'P0001';
  end if;
  if length(v_bytes) > 4194304 then
    raise exception 'file_too_big' using errcode = 'P0001';
  end if;

  perform 1 from public.dealers d where d.id = v_dealer for update;
  if (select count(*) from public.dealer_stock_reads r
       where r.dealer_id = v_dealer and r.created_at >= v_today)
     >= (v_prog ->> 'photo_import_daily_limit')::integer then
    raise exception 'photo_import_limit' using errcode = 'P0001';
  end if;

  insert into public.dealer_stock_reads (dealer_id, media_type, filename, bytes, data, created_by)
  values (v_dealer, p_media_type, left(nullif(btrim(p_filename), ''), 200), length(v_bytes), v_bytes, v_uid)
  returning id into v_read;
  -- The hourly llm_jobs cap (enforce_llm_rate_limit) runs here too: llm_rate_limited.
  insert into public.llm_jobs (user_id, kind, input)
  values (v_uid, 'dealer_stock_read', jsonb_build_object('read_id', v_read, 'dealer_id', v_dealer))
  returning id into v_job;
  update public.dealer_stock_reads set job_id = v_job where id = v_read;
  return v_job;
end $$;
