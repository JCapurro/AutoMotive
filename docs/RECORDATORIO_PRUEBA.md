# Recordatorio de fin de prueba

Cuando termina la prueba gratis de 72 horas y la cuenta no compró ningún plan, el worker le manda **un único email** que avisa que la prueba terminó e invita a elegir Particular o Agencia. Se manda una sola vez por cuenta, en horario diurno de Argentina, y se configura desde `/admin/config` sin desplegar.

No es una alerta: no pasa por el motor de notificaciones ni por la tabla `notifications`. Esa tabla descarta filas de cuentas vencidas (`guard_notification_access`, `prepare_notification_delivery`, `expire_commercial_access`) y sus métricas cuentan cada fila como alerta enviada. El recordatorio tiene su propio registro de envíos, `trial_reminders`: una fila por cuenta, para siempre.

```
termina la prueba ──(delay_hours)──> pendiente de aviso ──(window_hours)──> ya no se manda
                                          │
                     el worker, cada 15 min, entre send_from y send_until (hora argentina):
                     reserva hasta max_per_day por día → trial_reminders 'pending'
                                          │
                     ¿sigue cumpliendo los criterios? ── no ──> 'skipped'
                                          │ sí
                     Resend (Idempotency-Key trial-reminder-<user_id>) ──> 'sent' · 'failed'
```

Código: migración [`20261017120000_free_trial_reminder.sql`](../supabase/migrations/20261017120000_free_trial_reminder.sql), [`worker/notifications/trial_reminder.py`](../worker/notifications/trial_reminder.py), registro en [`worker/db/repos/trial_reminders.py`](../worker/db/repos/trial_reminders.py) y texto en [`worker/notifications/templates.py`](../worker/notifications/templates.py).

## A quién

Solo a cuentas que activaron una búsqueda gratis, cuya prueba terminó y que **nunca** compraron. No se manda a quienes compraron Particular o Agencia y dejaron vencer el plan. `public.trial_reminder_eligible(user_id)` exige todo esto:

- La cuenta existe y no es `admin`.
- Tiene email y `email` está en `profiles.default_channels`. La baja desde `/baja` o Ajustes lo quita, así que nunca recibe el aviso quien se dio de baja.
- `plan = 'free'` y `free_trial_started_at` no es nulo: la prueba empezó.
- `plan_limits_for(id)->>'state' = 'expired'`: los límites se aplican (`plan_limits.enforced = true`), la prueba terminó y no hay un plan pago vigente.
- No tiene ninguna fila en `commercial_payments`. Una compra devuelta también cuenta como compra: no se la invita a volver a comprar.
- No tiene un checkout en curso en `billing_checkouts`: estado `creating`, `authorized` o `paused`; `pending` creado hace menos de 72 horas (los pagos en efectivo se acreditan tarde); o con `sync_error` y sin estado final (`failed`, `cancelled`, `paid`). Un `pending` de más de 72 horas se considera abandonado y deja de bloquear.
- `commercial_pilot.enabled = true`: no tiene sentido invitar a comprar con el checkout cerrado.

Los criterios se revisan dos veces: al reservar la cuenta y otra vez justo antes de enviar. Si en el medio pagó o se dio de baja, la fila queda `skipped` con `error = 'not_eligible'` y no se manda nada.

## Cuándo

- La cuenta queda pendiente de aviso cuando `fin de la prueba + delay_hours <= ahora`. El reloj es el de la base de datos.
- Se manda solo entre `send_from` y `send_until`, hora argentina (UTC-3). Si la prueba termina de noche, sale a la mañana siguiente, a partir de `send_from`.
- Pasadas `window_hours` desde que quedó pendiente, ya no se manda. Así, habilitar los límites por primera vez o volver a habilitarlos no le escribe a pruebas vencidas hace días. La ventana tiene que superar la noche sin envíos (12 horas con 09:00–21:00); si no la supera, el worker usa 48.
- `max_per_day` limita cuántas cuentas se reservan por día calendario argentino. Las que no entran salen en las siguientes pasadas, mientras sigan dentro de la ventana.
- El worker revisa cada `TRIAL_REMINDER_TICK_SECONDS` (900 segundos por defecto, en `.env`). Con `delay_hours = 0`, el aviso sale dentro de los 15 minutos posteriores al vencimiento cuando este ocurre en horario de envío.

## Configuración: `app_config.trial_reminder`

Se edita desde `/admin/config`; el worker toma el cambio en menos de un minuto. Un valor inválido se reemplaza por su valor por defecto.

| Campo | Por defecto | Qué hace |
|---|---|---|
| `enabled` | `true` | `false` deja de reservar y de mandar. |
| `delay_hours` | `0` | Horas después del fin de la prueba antes de mandar. |
| `window_hours` | `48` | Plazo para mandar desde que la cuenta quedó pendiente. Debe superar la noche sin envíos. |
| `send_from` | `"09:00"` | Inicio del horario de envío, `HH:MM`, hora argentina. |
| `send_until` | `"21:00"` | Fin del horario de envío (no incluido). Debe ser posterior a `send_from`; si no, se usan 09:00–21:00. |
| `max_per_day` | `30` | Reservas por día calendario argentino, cualquiera sea su resultado. `0` frena los envíos. Resend gratis permite 100 emails por día entre alertas y avisos. |

## El email

- Asunto: «Terminó tu prueba gratis en Ese Auto».
- Cuenta cuándo venció la prueba (fecha y hora argentina), que la búsqueda quedó pausada y que se conservan resultados y favoritos.
- Muestra Particular y Agencia con los importes de `app_config.pro_offer`. Si la oferta falta o es inválida, nombra los planes sin precio, nunca con un precio equivocado.
- Botón «Ver planes» a `/app/pro?utm_source=email&utm_medium=email&utm_campaign=trial_reminder`. No usa `/r/`, que solo registra clics de publicaciones.
- Nota: «No hay cobros automáticos: solo pagás si elegís un plan.»
- Pie propio: aclara que es el único aviso sobre el fin de la prueba, con el link de baja. Lleva también `List-Unsubscribe` de un clic, igual que las alertas.

Snapshot revisado en `worker/tests/snapshots/notifications/trial_reminder.txt`.

## Baja

Usa el mismo token y la misma página que las alertas (`/baja?t=…` y `/api/baja`). La baja quita `email` de los canales, así que una cuenta dada de baja nunca recibe el aviso. Sin `WEB_BASE_URL` no hay link de baja: el worker no reserva ni manda nada.

## Medir conversión

`trial_reminders` es el registro del embudo; el recordatorio no escribe `events`. Compras posteriores al envío, por semana:

```sql
select date_trunc('week', r.sent_at at time zone 'America/Argentina/Buenos_Aires')::date as semana,
       count(*) as enviados,
       count(*) filter (where exists (
         select 1 from commercial_payments cp
          where cp.user_id = r.user_id and cp.refunded_at is null
            and cp.paid_at between r.sent_at and r.sent_at + interval '7 days')) as compraron_7_dias,
       count(*) filter (where exists (
         select 1 from commercial_payments cp
          where cp.user_id = r.user_id and cp.refunded_at is null and cp.paid_at >= r.sent_at)) as compraron
  from trial_reminders r
 where r.status = 'sent'
 group by 1 order by 1;
```

Para el paso intermedio, contar `events` con `name = 'checkout_started'` posteriores a `sent_at`. No hay grupo de control: la cifra muestra compras después del aviso, no cuántas causó.

## Desactivar

Poner `enabled` en `false` desde `/admin/config`. Las filas `pending` quedan sin enviar; si después se vuelve a activar, solo se mandan las que siguen dentro de la ventana. Las demás quedan `skipped` con `error = 'outside_window'`.

## Verificar en producción

1. Configuración: `select value from app_config where key = 'trial_reminder';`.
2. Cuentas que se reservarían ahora, sin enviar nada:
   ```sql
   select p.id, (plan_limits_for(p.id)->>'trial_expires_at')::timestamptz as vencio
     from profiles p
    where trial_reminder_eligible(p.id)
      and not exists (select 1 from trial_reminders r where r.user_id = p.id);
   ```
3. Envíos: `select status, count(*) from trial_reminders group by 1;` y las últimas filas por `created_at`.
4. Errores: `select * from pipeline_errors where stage = 'trial_reminder' order by created_at desc;`.
5. Log del worker: líneas `trial reminders: N claimed` / `N sent`, y `trial reminders off: …` si falta canal o `WEB_BASE_URL`.
6. En Resend, el email con el asunto y la clave `trial-reminder-<user_id>`.

## Límites conocidos

- Si el worker está caído más de `window_hours`, las pruebas vencidas en ese lapso se quedan sin aviso. Una fila reservada y no enviada antes de una caída larga queda `skipped` (`outside_window`).
- La fila se borra con la cuenta: una cuenta borrada y creada de nuevo con el mismo email puede recibir otro aviso.
- El tope diario cuenta reservas, incluidas las que terminan `skipped` o `failed`, y no ve el volumen de alertas que comparte la cuota de Resend.
- `sent` significa que Resend aceptó el email; rebotes y quejas no se registran.
- La reserva preselecciona cuentas con una prueba de 72 horas, igual que `plan_limits_for`. Si cambia esa duración, revisar `claim_trial_reminders`.
- La clave de idempotencia de Resend dura 24 horas. Los reintentos ocurren minutos después, dentro de ese plazo.

## Estado de activación — 9/10/2026: implementado, sin desplegar

- Migración probada en una base local aislada. No se aplicó en producción.
- Para activarlo: aplicar la migración antes de actualizar el worker, desplegar el worker con `RESEND_API_KEY`, `EMAIL_FROM` y `WEB_BASE_URL`, y confirmar `plan_limits.enforced` y `commercial_pilot.enabled`. Después, seguir **Verificar en producción**.
- Las páginas `/privacidad` y `/baja` mencionan este aviso.
