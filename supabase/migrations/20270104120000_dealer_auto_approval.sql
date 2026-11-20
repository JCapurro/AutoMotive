-- Agencias: an agency is approved by its plan, not by hand.
--
-- Juan, 20/11: «la agencia está aprobada siempre que haga el pago y tenga la
-- cuenta activa como agencia. Ese toggle no debería estar». So dealers.approved_at
-- stops being a button of /admin/agencias and becomes the mirror of the plan:
--
--   approved  = a member of the agency has the Pro plan active (plan_limits_for:
--               plan 'pro' and active; an admin counts, as everywhere else);
--   otherwise = not approved: the agency keeps its panel (stock, prices against
--               the market) and loses the demand and the sending to buyers, as an
--               unapproved one did. Its data stays.
--
-- dealers.approved_at keeps its meaning for everything that reads it (the gate
-- dealer_listing_hidden, the demand, the public name, the worker): only who
-- writes it changes. public.dealer_sync_approvals() sets it from the plans; the
-- worker calls it on every dealers tick (a plan that expires has no event), and a
-- trigger calls it when someone becomes a member, so a paying agency is on from
-- its first minute. approved_by is null for an automatic approval.
-- A paused agency (dealers.status) stays hidden whatever its plan: that is now the
-- admin's only brake. Changing the name or the place no longer un-approves
-- (update_my_dealer); the manual check of a dealer's Mercado Libre account
-- (dealer_sources) is untouched.
-- Needs 20261228120000_dealer_program.sql.
--
-- Rollback: drop trigger dealer_members_sync_approval on public.dealer_members;
-- drop function public.dealer_member_sync_approval(), public.dealer_sync_approvals(),
-- public.dealer_plan_active(bigint); re-create update_my_dealer from 20261228120000.

create function public.dealer_plan_active(p_dealer_id bigint) returns boolean
language sql stable security definer set search_path = '' as $$
  select exists (
    select 1
      from public.dealer_members m
     cross join lateral public.plan_limits_for(m.user_id) as lim
     where m.dealer_id = p_dealer_id
       and lim ->> 'plan' = 'pro'
       and (lim ->> 'active')::boolean)
$$;

-- Both ways, for every dealer. Returns how many rows changed.
create function public.dealer_sync_approvals() returns integer
language plpgsql volatile security definer set search_path = '' as $$
declare
  v_on integer; v_off integer;
begin
  update public.dealers d
     set approved_at = now(), approved_by = null
   where d.approved_at is null and public.dealer_plan_active(d.id);
  get diagnostics v_on = row_count;
  update public.dealers d
     set approved_at = null, approved_by = null
   where d.approved_at is not null and not public.dealer_plan_active(d.id);
  get diagnostics v_off = row_count;
  return v_on + v_off;
end $$;

create function public.dealer_member_sync_approval() returns trigger
language plpgsql volatile security definer set search_path = '' as $$
begin
  update public.dealers d
     set approved_at = now(), approved_by = null
   where d.id = new.dealer_id and d.approved_at is null and public.dealer_plan_active(d.id);
  return null;
end $$;

create trigger dealer_members_sync_approval
  after insert on public.dealer_members
  for each row execute function public.dealer_member_sync_approval();

revoke all on function public.dealer_plan_active(bigint), public.dealer_sync_approvals(),
  public.dealer_member_sync_approval() from public, anon, authenticated;
grant execute on function public.dealer_plan_active(bigint), public.dealer_sync_approvals() to service_role;

comment on function public.dealer_sync_approvals() is
  'dealers.approved_at from the plans: set while a member has Pro active, cleared when none does. Worker, every dealers tick.';

-- The agencies that exist get their state from their plan right now.
select public.dealer_sync_approvals();

-- The agency's own data: the same body, without the reset of the approval.
create or replace function public.update_my_dealer(
  p_name text, p_locality_label text, p_lat double precision, p_lon double precision,
  p_phone text default null, p_whatsapp text default null, p_contact_email text default null,
  p_address_text text default null, p_profile_links jsonb default '[]'
) returns void
language plpgsql volatile security definer set search_path = '' as $$
declare
  v_dealer   bigint := public.dealer_require_member();
  v_name     text := btrim(p_name);
  v_locality text := btrim(p_locality_label);
  v_phone    text := nullif(regexp_replace(coalesce(p_phone, ''), '\D', '', 'g'), '');
  v_whatsapp text := nullif(regexp_replace(coalesce(p_whatsapp, ''), '\D', '', 'g'), '');
  v_email    text := nullif(lower(btrim(p_contact_email)), '');
  v_address  text := nullif(btrim(p_address_text), '');
  v_links    jsonb := coalesce(p_profile_links, '[]'::jsonb);
  v_problem  text;
begin
  v_problem := public.dealer_profile_problem(v_name, v_locality, p_lat, p_lon, v_phone, v_whatsapp, v_email,
                                             v_address, v_links);
  if v_problem is not null then
    raise exception 'invalid_dealer:%', v_problem using errcode = 'P0001';
  end if;
  -- A new name or place no longer waits for anybody (20270104120000): the agency
  -- is on while its plan is, whatever its name. Pausing it is the admin's brake.
  update public.dealers d
     set name = v_name, locality_label = v_locality, lat = p_lat, lon = p_lon, phone = v_phone,
         whatsapp = v_whatsapp, contact_email = v_email, address_text = v_address, profile_links = v_links
   where d.id = v_dealer;
end $$;
