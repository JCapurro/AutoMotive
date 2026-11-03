-- PAR-05 · Prueba B: public.sell_intent (RLS, timestamps, the agencies flag)
-- and public.admin_sell_intent_metrics (migration 20261204120000_par05_sell_intent).
begin;
select no_plan();

insert into auth.users(instance_id,id,aud,role,email,created_at,updated_at) values
('00000000-0000-0000-0000-000000000000','52525252-5252-4252-8252-525252525251','authenticated','authenticated','vende@example.test',now(),now()),
('00000000-0000-0000-0000-000000000000','52525252-5252-4252-8252-525252525252','authenticated','authenticated','otro@example.test',now(),now()),
('00000000-0000-0000-0000-000000000000','52525252-5252-4252-8252-525252525253','authenticated','authenticated','admin-vende@example.test',now(),now());
update public.profiles set role='admin' where id='52525252-5252-4252-8252-525252525253';

select is((select value->>'agencies_contact' from public.app_config where key='sell_intent'),'false','the agencies checkbox starts off');
select is((select value->>'ask' from public.app_config where key='sell_intent'),'true','the question is asked');

-- An account answers from the listing page.
set local role authenticated;
set local request.jwt.claim.sub='52525252-5252-4252-8252-525252525251';
set local request.jwt.claims='{"sub":"52525252-5252-4252-8252-525252525251","role":"authenticated","is_anonymous":false}';
select lives_ok($$insert into public.sell_intent(user_id,answer,source) values ('52525252-5252-4252-8252-525252525251','yes','ficha')$$,'own answer');
select throws_ok($$insert into public.sell_intent(user_id,answer,source) values ('52525252-5252-4252-8252-525252525252','yes','ficha')$$,'42501',null,'nobody answers for another account');
select throws_ok($$insert into public.sell_intent(user_id,answer,source,answered_at) values ('52525252-5252-4252-8252-525252525251','no','ficha',now())$$,'42501',null,'the timestamps are not the client''s');
select lives_ok($$update public.sell_intent set wants_notice=true where user_id='52525252-5252-4252-8252-525252525251'$$,'asks for the notice');
select isnt((select wants_notice_at from public.sell_intent),null,'the notice is stamped');
select throws_ok($$update public.sell_intent set agencies_contact_ok=true where user_id='52525252-5252-4252-8252-525252525251'$$,'42501','sell_intent_agencies_off','the agencies preference needs the flag');
select throws_ok($$update public.sell_intent set answer='no' where user_id='52525252-5252-4252-8252-525252525251'$$,'23514',null,'«No» clears the notice first');
select lives_ok($$update public.sell_intent set answer='no',wants_notice=false where user_id='52525252-5252-4252-8252-525252525251'$$,'changes the answer');
select is((select wants_notice_at from public.sell_intent),null,'no notice, no timestamp');
select is((select count(*)::int from public.sell_intent),1,'reads only its own row');

set local request.jwt.claim.sub='52525252-5252-4252-8252-525252525252';
set local request.jwt.claims='{"sub":"52525252-5252-4252-8252-525252525252","role":"authenticated","is_anonymous":false}';
select is((select count(*)::int from public.sell_intent),0,'another account sees nothing');
update public.sell_intent set source='email';
reset role;
select is((select source from public.sell_intent where user_id='52525252-5252-4252-8252-525252525251'),'ficha','and changes nothing');
set local role authenticated;
select throws_ok($$select public.admin_sell_intent_metrics()$$,'42501',null,'the metrics are not for accounts');

-- An anonymous session (Telegram) never answers.
set local request.jwt.claims='{"sub":"52525252-5252-4252-8252-525252525252","role":"authenticated","is_anonymous":true}';
select throws_ok($$insert into public.sell_intent(user_id,answer,source) values ('52525252-5252-4252-8252-525252525252','yes','ficha')$$,'42501',null,'anonymous sessions cannot answer');
reset role;

set local role anon;
select throws_ok($$select count(*) from public.sell_intent$$,'42501',null,'anon reads nothing');
reset role;

-- The email links write with the service role; the flag on lets the agencies box through.
set local role service_role;
select lives_ok($$insert into public.sell_intent(user_id,answer,source,wants_notice) values ('52525252-5252-4252-8252-525252525252','yes','email',true)$$,'the email link answers');
select throws_ok($$update public.sell_intent set agencies_contact_ok=true where user_id='52525252-5252-4252-8252-525252525252'$$,'42501','sell_intent_agencies_off','not even the service role without the flag');
reset role;
update public.app_config set value=value||'{"agencies_contact":true}' where key='sell_intent';
set local role service_role;
select lives_ok($$update public.sell_intent set agencies_contact_ok=true where user_id='52525252-5252-4252-8252-525252525252'$$,'with the flag on');
reset role;
select isnt((select agencies_contact_at from public.sell_intent where user_id='52525252-5252-4252-8252-525252525252'),null,'the agencies preference is stamped');

-- Admins answer too, but never count.
insert into public.sell_intent(user_id,answer,source) values ('52525252-5252-4252-8252-525252525253','yes','email');

set local role service_role;
select is((public.admin_sell_intent_metrics(now()-interval '1 hour')->>'answered')::int,2,'answered (admins left out)');
select is((public.admin_sell_intent_metrics(now()-interval '1 hour')->>'yes')::int,1,'yes');
select is((public.admin_sell_intent_metrics(now()-interval '1 hour')->>'pctYes')::numeric,50.0,'% yes');
select is((public.admin_sell_intent_metrics(now()-interval '1 hour')->>'wantsNotice')::int,1,'wants the notice');
select is((public.admin_sell_intent_metrics(now()-interval '1 hour')->>'agenciesContactOk')::int,1,'agencies preference');
select is((public.admin_sell_intent_metrics(now()-interval '1 hour')->'bySource'->'ficha'->>'no')::int,1,'by source: ficha');
select is((public.admin_sell_intent_metrics(now()-interval '1 hour')->'bySource'->'email'->>'yes')::int,1,'by source: email');
select ok((public.admin_sell_intent_metrics(now()-interval '1 hour')->>'newAccounts')::int>=2,'new accounts since the start');
select is((public.admin_sell_intent_metrics(now()+interval '1 hour')->>'answered')::int,0,'only since the start');
reset role;

select * from finish();
rollback;
