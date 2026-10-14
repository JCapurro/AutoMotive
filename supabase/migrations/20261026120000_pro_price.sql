-- Planes 2026-10, fase 3 (3.1): Pro replaces Agencia at $100.000 a month for
-- new subscriptions. It touches charges: Juan approved it on 14/10/2026.
--
--   pro_offer.pro_monthly.amount 75000 → 100000, under a new offer version.
--     Only checkouts started from now on take it: every subscription keeps
--     its own billing_checkouts.amount, and Mercado Pago its own
--     auto_recurring amount (each preapproval carries its price; there is no
--     shared plan to update). No existing subscription changes.
--   agency_founders.slots → 0. Founders are the first Agencia subscriptions
--     (1.6); a Pro subscription at the new price is not one. The ones already
--     marked keep their founder_price_until.

update public.app_config
   set value = jsonb_set(jsonb_set(value, '{pro_monthly,amount}', '100000'), '{version}', '"ars-pro-2026-10"')
 where key = 'pro_offer';

update public.app_config
   set value = jsonb_set(value, '{slots}', '0')
 where key = 'agency_founders';
