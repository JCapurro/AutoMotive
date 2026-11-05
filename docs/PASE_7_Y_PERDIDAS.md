# Pase de 7 días, pantalla de vencimiento y garantía

Juan aprobó los tres el 05/11/2026 (diagnóstico de conversión, puntos 3, 5 y 6).
Migración: [`20261211120000_pass_7.sql`](../supabase/migrations/20261211120000_pass_7.sql).

## Pase de 7 días (punto 5)

- Oferta `pass_7` en `app_config.pro_offer`: **$5.000 por 7 días**. Particular de 30 días sigue en $15.000.
- Compra el mismo plan (`profiles.plan = 'pass'`) con los mismos límites que el de 30 días.
- Se suma a un pase vigente en cualquier combinación: 7 sobre 30, 30 sobre 7, 7 sobre 7. Se devuelve igual, del más nuevo al más viejo.
- En la base, `is_pass_offer()` define la familia de pases y `offer_days()` los días de cada oferta.
- Mercado Pago: la preferencia se titula «Ese Auto · Particular · 7 días» y su item id es `pass_7`.
- Mails: el pase de 7 días no recibe «te quedan 5 días», que llegaría 2 días después de comprar. Sí recibe «hoy vence» (`pass_expiry_eligible`).
- La versión de la oferta (`ars-pro-2026-10`) no cambia, así que las contrataciones abiertas siguen valiendo. Cambiar un importe pide una versión nueva, también el de 7 días.

## Pantalla de vencimiento (punto 3)

Con el acceso vencido, el inicio (`/app`) muestra arriba:

> Desde que venció tu acceso aparecieron N autos nuevos de tus búsquedas. K están por debajo del precio de autos comparables.

- Hay dos botones que llevan directo a Mercado Pago, uno por pase (7 y 30 días), más «Ver todos los planes».
- Los números salen de `missed_since_expiry()`: lo que contó el worker para el mail 2.5 (`expired_search_matches`) desde el último vencimiento, en publicaciones distintas. «Por debajo» es el nivel `high`, igual que en el mail.
- No aparece con el acceso vigente, sin nada contado o con el piloto comercial apagado.
- Solo cuentan las cuentas que el 2.5 sigue: las que tienen contacto por mail y búsquedas con modelo, hasta 22 días después del vencimiento.

## Garantía (punto 6)

Condición: **si durante el pase no aparece ningún auto para tus búsquedas, devolvemos el 100 %**.

- Se muestra en las tarjetas de planes, en el aviso de cupo, en la pantalla de vencimiento y en los Términos.
- Los Términos agregan que se pide por mail hasta 15 días después del vencimiento y que la devolución revoca el período.
- La devolución es manual: en Cobros, «Registrar devolución» (`refund_commercial_payment`), después de devolver el dinero en Mercado Pago.

Para verificar un pedido, contá los resultados del pase:

```sql
select cp.id, cp.offer, cp.period_start, cp.period_end,
       (select count(*) from public.matches m
          join public.search_profiles sp on sp.id = m.search_profile_id
         where sp.user_id = cp.user_id
           and m.generated_at >= cp.period_start and m.generated_at < cp.period_end) as autos
  from public.commercial_payments cp
 where cp.user_id = '<uuid>' and public.is_pass_offer(cp.offer)
 order by cp.period_start desc;
```

Con `autos = 0`, corresponde la devolución.
