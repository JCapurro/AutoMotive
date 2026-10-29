begin;
select no_plan();
insert into auth.users(instance_id,id,aud,role,email,created_at,updated_at) values
('00000000-0000-0000-0000-000000000000','51515151-5151-4151-8151-515151515151','authenticated','authenticated','feedback@example.test',now(),now()),
('00000000-0000-0000-0000-000000000000','51515151-5151-4151-8151-515151515152','authenticated','authenticated','other-feedback@example.test',now(),now());
insert into public.search_profiles(id,user_id,name,filters) overriding system value values
(9855,'51515151-5151-4151-8151-515151515151','Ford Fiesta','{"make":"Ford","model":"Fiesta"}'),
(9856,'51515151-5151-4151-8151-515151515152','Other search','{"make":"Ford","model":"Fiesta"}');
update public.profiles set free_trial_started_at=now()-interval '5 days' where id='51515151-5151-4151-8151-515151515151';
set local role authenticated;
set local request.jwt.claim.sub='51515151-5151-4151-8151-515151515151';
select lives_ok($$select public.submit_product_feedback('Me faltan filtros de versión.',9855,'51515151-5151-4151-8151-515151515150')$$,'expired trial can submit feedback');
select lives_ok($$select public.submit_product_feedback('Me faltan filtros de versión.',9855,'51515151-5151-4151-8151-515151515150')$$,'retries with the same key are safe');
select throws_ok($$select public.submit_product_feedback('Me faltan filtros de versión.',9856,gen_random_uuid())$$,'22023','feedback_search_not_owned','cannot attach someone else''s search');
select throws_ok($$select public.submit_product_feedback('corto',9855,gen_random_uuid())$$,'22023','invalid_feedback','short messages rejected');
select throws_ok($$select public.submit_product_feedback(repeat('x',2001),9855,gen_random_uuid())$$,'22023','invalid_feedback','oversized messages rejected');
select lives_ok($$select public.submit_product_feedback('Otro comentario útil sobre los resultados.',null,gen_random_uuid())$$,'context is optional');
select lives_ok($$select public.submit_product_feedback('Tercer comentario sobre la prueba gratis.',null,gen_random_uuid())$$,'three submissions allowed');
select throws_ok($$select public.submit_product_feedback('Cuarto comentario sobre la prueba gratis.',null,gen_random_uuid())$$,'P0001','feedback_rate_limited','daily limit enforced in the database');
select is((select count(*)::int from public.product_feedback),0,'regular users cannot read the private leads');
select throws_ok($$insert into public.product_feedback(user_id,request_id,email,message) values ('51515151-5151-4151-8151-515151515151',gen_random_uuid(),'forged@example.test','Mensaje de prueba no permitido')$$,'42501',null,'direct inserts and forged emails denied');
reset role;
select is((select count(*)::int from public.product_feedback where user_id='51515151-5151-4151-8151-515151515151'),3,'retry did not create a duplicate lead');
select is((select email from public.product_feedback where request_id='51515151-5151-4151-8151-515151515150'),'feedback@example.test','contact comes from the authenticated account');
select is((select search_name from public.product_feedback where request_id='51515151-5151-4151-8151-515151515150'),'Ford Fiesta','search context saved');
select is((select delivery_status from public.product_feedback where request_id='51515151-5151-4151-8151-515151515150'),'pending','lead waits for owner email delivery');
update public.profiles set role='admin' where id='51515151-5151-4151-8151-515151515151';
set local role authenticated;
select is((select count(*)::int from public.product_feedback),3,'admins can read submitted leads');
reset role;
set local role anon;
select throws_ok($$select public.submit_product_feedback('Un comentario anónimo no autorizado.',null,gen_random_uuid())$$,'42501',null,'anonymous submissions denied');
reset role;
select * from finish();
rollback;
