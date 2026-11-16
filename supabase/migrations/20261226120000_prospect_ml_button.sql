-- Prospección: vendedores de Mercado Libre que se contactan por el botón de WhatsApp de su
-- propio aviso (docs/PROSPECCION.md). Juan, 16/11/2026: «Sí, sumalos».
--
-- La página del aviso dice si el botón está activo, pero el número aparece recién cuando
-- una persona lo toca. Ese prospecto queda sin phone, con phone_source = 'boton_ml' y en
-- phone_evidence la URL del aviso: Juan lo abre en el celular, toca WhatsApp y pega el
-- mensaje. Si después carga el número (admin_prospect_action 'phone_set'), el seguimiento
-- y el último mensaje ya van por wa.me.

alter table public.prospects drop constraint prospects_phone_source_check;
alter table public.prospects add constraint prospects_phone_source_check check (
  phone_source is null or phone_source in ('aviso', 'pagina_aviso', 'web', 'guardado', 'manual', 'boton_ml'));
