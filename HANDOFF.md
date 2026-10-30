# Handoff: backlog de producto, cierre de la Fase 1

Fecha: 30/10/2026. Sesión en la nube de Claude Code. Respuestas a Juan siempre en español.

## Objetivo

Implementar el backlog de producto por fases según `docs/PLAN_FASES_BACKLOG_PRODUCTO_2026-10.md`. El estado por ítem está en `docs/BACKLOG_PRODUCTO_2026-10.md` («Estado al 30/10») y el de la fase, en la sección 7 del plan.

## Qué está hecho

| Ítem | Dónde |
|---|---|
| H-01, X-01, F-03 fase 0, PAR-03 por aviso | en `main` (#50, #51, #52, #53) |
| PAR-02 tramo 1 (checklist «Antes de señar»), textos aprobados por Juan | #56 |
| PAR-03 con precio de contado o anticipo (opción B, aprobada por Juan) | #56 |
| e2e de aceptación al día | #56 (antes en #55, que quedó en una rama intermedia) |
| Migraciones aplicables desde una base vacía (`lock table` dentro de `do`) | #56 |
| Privacidad: ítem «Tus notas» (X-01) | #56 |
| Tests de repairbot independientes de la plataforma | #56 |
| Tests de base viejos (pgTAP y `-m db`) | #57 |

#54 y #55 se mergearon en ramas intermedias (`claude/par03-dias-y-bajas`, `claude/par02-checklist`), no en `main`: por eso #56 apunta a `main` y lleva PAR-02 completo.

### PAR-03 con precio de contado (opción B)
- Tarjeta, email de oportunidad y digest: sin línea de bajas cuando el precio mostrado sale de la descripción (`price_source = 'description'`).
- Ficha: el histórico se oculta cuando el precio publicado es un anticipo o una cuota.
- Ingest: no hay `price_drop` cuando el publicado, antes o después, es parcial.
- La decisión «el publicado es parcial» la toma `resolve_price` y queda guardada en `description_facts.price_check.published_partial`. No se reconstruye después comparando monedas: con cotizaciones distintas, eso silenciaba bajas reales.
- Avisos guardados antes del deploy, sin ese campo: cuentan solo `published_kind` (down_payment/installment) y `price_partial`.

## Producción (30/10, con OK de Juan)

Aplicadas el 30/10 (antes `max(version)` = `20261118130000`, ahora `20261122120100`; verificadas por md5 contra la base local), en este orden, cada una en una transacción con el insert de su versión exacta en `supabase_migrations.schema_migrations`:

1. `20261027145911_admin_config_audit` (nunca se aplicó: sin ella `/admin/config` no guarda)
2. `20261119110000_f03_market_stats`
3. `20261119120000_x01_tracking`
4. `20261119130000_x01_outcome_metric`
5. `20261121120000_par03_price_tracks`
6. `20261122120000_par02_risk_config`
7. `20261122120100_par02_decision_metrics_checklist`

`risk.links` cargado (auditoría #1). Falta: worker en el VPS con el código de `main` (`wait_idle` antes de reiniciar). La web de `main` ya tolera la base vieja: X-01 cae a «Todos», PAR-03 no muestra bajas y el checklist se ve sin links. 

### Links oficiales cargados en `risk.links` (aprobados por Juan el 30/10)
```json
{
  "dnrpa": {"label": "Informe de dominio (DNRPA)", "url": "https://www.argentina.gob.ar/servicio/solicitar-un-informe-de-dominio-del-automotor"},
  "patentes": [
    {"label": "CABA (AGIP)", "url": "https://buenosaires.gob.ar/tramites/patentes-automotores-consulta-de-boletas-saldos-y-deuda"},
    {"label": "Provincia de Buenos Aires (ARBA)", "url": "https://web.arba.gov.ar/consulta-de-deuda-automotor"}
  ],
  "infracciones": [
    {"label": "CABA", "url": "https://buenosaires.gob.ar/consulta-de-infracciones"},
    {"label": "Provincia de Buenos Aires", "url": "https://infraccionesba.gba.gob.ar/"}
  ],
  "vtv": {"label": "VTV Provincia de Buenos Aires", "url": "https://vtv.gba.gob.ar/"},
  "form_08": {"label": "Transferencia y formulario 08", "url": "https://www.argentina.gob.ar/servicio/hacer-la-transferencia-de-dominio-de-un-auto-moto-o-maquinaria"}
}
```
Todas respondieron 200 el 30/10. `vtv` acepta un solo link: va el de Provincia; el de CABA es `https://buenosaires.gob.ar/tramites/verificacion-tecnica-vehicular-obligatoria`.

## Próximos pasos
1. Juan: mergear #57 y #56 (en cualquier orden; los dos tienen merge limpio con `main`).
2. Juan: desplegar el worker en el VPS.
3. Fase 2: decisiones tomadas (sección 8 del plan). F-02 en la rama `claude/f02-vendedor`; costos oficiales de PAR-01 en investigación.

## Reglas operativas que no están en el código
- Sin cambios en producción sin OK explícito de Juan. Migración manual en prod = transacción + insert de la versión exacta.
- Mergear a `main` despliega la web en Vercel: no mergear antes de que la base tolere el cambio.
- Nunca crear proyectos Supabase en la org tecc. El proyecto hosted es `dnqyravczgcpuowijbja`.
- `web/types/database.ts` se mantiene a mano; no correr `gen:types` sobre él.
- Migraciones nuevas por encima de `20261122120100`.
- En la nube: `supabase start` con la CLI 2.119.0 y `supabase/.env` con claves propias (`python -m tools.supabase_keys generate`); `-x analytics,vector` si esos contenedores no levantan. La base de tests es `automotive_test` (`python -m tools.test_db`).
