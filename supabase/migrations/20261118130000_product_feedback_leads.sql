-- Feedback is captured before delivery, including accounts whose trial expired.
create table public.product_feedback (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(id) on delete cascade,
  request_id uuid not null,
  search_profile_id bigint references public.search_profiles(id) on delete set null,
  search_name text,
  email text not null check (length(email) between 3 and 254),
  message text not null check (char_length(btrim(message)) between 10 and 2000),
  source text not null default 'trial_result_limit',
  created_at timestamptz not null default now(),
  delivery_status text not null default 'pending' check (delivery_status in ('pending','sent','failed')),
  attempts integer not null default 0 check (attempts >= 0),
  next_attempt_at timestamptz not null default now(),
  claimed_until timestamptz,
  claim_token uuid,
  sent_at timestamptz,
  provider_id text,
  error text,
  unique(user_id,request_id)
);
create index product_feedback_user_created_idx on public.product_feedback(user_id,created_at);
create index product_feedback_pending_idx on public.product_feedback(next_attempt_at,created_at) where delivery_status='pending';
alter table public.product_feedback enable row level security;
revoke all on public.product_feedback from public,anon,authenticated;
grant select on public.product_feedback to authenticated;
grant all on public.product_feedback to service_role;
create policy "feedback: admin read" on public.product_feedback for select to authenticated
  using (exists(select 1 from public.profiles p where p.id=(select auth.uid()) and p.role='admin'));

-- Server-only configuration, independent of the platform-health recipient.
insert into public.app_config(key,value) values ('feedback_delivery',
  '{"enabled":true,"recipient_email":"juan.capurro12@gmail.com"}')
on conflict(key) do nothing;

create function public.submit_product_feedback(p_message text,p_profile bigint,p_request uuid)
returns uuid language plpgsql security definer set search_path='' as $$
declare
  v_user uuid:=auth.uid(); v_id uuid; v_email text; v_name text; v_message text:=btrim(p_message);
begin
  if v_user is null then raise exception 'authentication_required' using errcode='42501'; end if;
  if p_request is null or v_message is null or char_length(v_message) not between 10 and 2000 then
    raise exception 'invalid_feedback' using errcode='22023';
  end if;
  -- Serialize submissions so concurrent requests cannot bypass the daily cap.
  perform 1 from public.profiles where id=v_user for update;
  select id into v_id from public.product_feedback where user_id=v_user and request_id=p_request;
  if v_id is not null then return v_id; end if;
  if p_profile is not null then
    select name into v_name from public.search_profiles where id=p_profile and user_id=v_user;
    if not found then raise exception 'feedback_search_not_owned' using errcode='22023'; end if;
  end if;
  if (select count(*) from public.product_feedback where user_id=v_user and created_at>now()-interval '24 hours')>=3 then
    raise exception 'feedback_rate_limited';
  end if;
  select email into v_email from auth.users where id=v_user;
  if nullif(v_email,'') is null then raise exception 'email_required' using errcode='22023'; end if;
  insert into public.product_feedback(user_id,request_id,search_profile_id,search_name,email,message)
  values(v_user,p_request,p_profile,v_name,v_email,v_message) returning id into v_id;
  insert into public.events(user_id,name,props) values(v_user,'product_feedback_submitted',
    jsonb_build_object('feedback_id',v_id,'search_profile_id',p_profile,'source','trial_result_limit'));
  return v_id;
end $$;
revoke all on function public.submit_product_feedback(text,bigint,uuid) from public,anon;
grant execute on function public.submit_product_feedback(text,bigint,uuid) to authenticated;
notify pgrst,'reload schema';
