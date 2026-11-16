# Prospección automática

Every day the bot leaves about 30 first messages for agencies and resellers, plus the
follow-ups that are due. Juan sends them from his own WhatsApp, from `/admin/prospeccion`.
The bot sends nothing and reads no chats: Juan marks the replies by hand.

Criteria (Juan, 15/11/2026):

- Sellers with 3 to 60 active listings, nationwide, agencies and people in the same batch.
- WhatsApp only, from Juan's number.
- The offer is the agencies plan at the founder price: $50.000 per month for 3 months, then
  $100.000. It goes through the `/fundador/<code>` link, which only appears in the ready-made
  replies, never in the first message.
- Cadence: first message, a follow-up 5 business days later, and a last message 15 days after
  that. Then the prospect is closed. There is no opt-out line.

## Flow

`python -m prospector` from `worker/` (task `\AutoMotive\Prospector`, every day at 7:30 on the PC):

1. **Base.** Active `listings`, grouped by (source, seller_name), 3 to 60 listings each.
   - Sellers that share 2 or more identical listings (make, model, year, price), or the same
     phone, become one prospect.
   - Left out: chains and official dealers, savings plans, paying clients (by phone), anyone
     already in the `prospects` table, and the people in the local manual list
     `%LOCALAPPDATA%\EseAuto\prospeccion\ya-contactados.json`. That list holds personal data
     and is never committed.
2. **Phone** (`prospector/phones.py`, `lookup.py`).
   - First, a number the seller wrote in their own listing.
   - Then, the wa.me link on the RosarioGarage listing page.
   - Then, the WhatsApp button on their Mercado Libre listing (`lookup.ml_button`). The page
     state says whether the button is on (`"action_type":"WHATSAPP"`); the number only appears
     when a person taps it, behind reCAPTCHA, so the bot never asks for it. Up to 2 of their
     live listings are read, freshest first, on every run. The prospect stays without a phone,
     with `phone_source = 'boton_ml'` and the listing URL in `phone_evidence`. It counts for a
     person too, since the button is their own channel. Needs migration 20261226120000: before
     it, a live run skips this path and says so in the log.
   - For agencies only, a public WhatsApp found by web search, accepted only when certain and
     with the source URL.
   - **A person's phone is only the one they wrote in their own listing.** It is never
     searched for anywhere else.
   - With no number the prospect is «sin contacto»: it does not use a slot and is retried
     after 21 days.
3. **Facts** (`facts.py`). A JSON built from SQL only:
   - their stock (listings, models, ages, prices);
   - their price position against comparables (`comparable_pool`, same zone);
   - hooks: a private listing at most 72 h old in their zone, of a model they sell, at 10–35 %
     below comparables (`public.comparables`), with no placeholder prices;
   - their listings that stopped being published;
   - aggregate search demand near them.
   A hook must also look like a real total price:
   - no down payment, installments or «entrega»;
   - no damage («chocado», «para repuestos», «a reparar», «con detalles»...);
   - at least 2 photos;
   - a price that fits its currency and matches the description.
   Past 25 % below comparables it also needs 20+ comparables, 4+ photos, a description and km.
   Before a hook goes into a message, its listing page is read and a removed one is dropped:
   - Mercado Libre, deRuedas and RosarioGarage are read with the collectors' `parse_detail`, one
     page every 4 s.
   - Facebook is never fetched: there a hook counts only if the collector saw the card in the
     last 12 h.
   - The card shows when that was checked and, past 24 h, asks Juan to open the listing before
     sending.
   The zone is derived from lat/lon with `normalization.zone`, because `listing_zones` has not
   been filled since 09/11/2026.
4. **Writing** (`writer.py`). It runs `claude -p` with `claude-opus-5-5` at high effort, in
   batches of 6.
   - It writes 2 variants, each tagged with a hook type: oportunidad, stock_viejo,
     precio_vs_zona, demanda or dejaron_de_publicarse.
   - The greeting is fixed in code (`saludo`):
     - a person gets their first name;
     - a business whose name starts with a first name and surname gets that first name
       («Hola, Julio.»);
     - any other business gets «Hola, ¿cómo andan?», never the business name.
   - The stock fact is the total or the models they have several of, never «tenés un Gol Trend».
   - Rules: voseo, about 450 characters, «Soy Juan, armé Ese Auto», one fact about their stock
     and one hook, one closing question, no links, no price, no «IA», no «vendido», and every
     number taken from the facts.
   - The examples are the last messages that got a reply.
5. **Review.** A separate call checks the numbers against the facts and the rules, then picks
   a variant, asks for one rewrite, or drops the prospect for today.
   - `rules.py` checks the same hard rules in code; a message that breaks one never gets out.
   - The follow-up and the last message bring a hook that was not used before.
6. **Storage.** The bot writes `prospects`, `prospect_messages` and `prospect_events`
   (migration `20261225120000_prospecting`). The tables are service_role only, with RLS on and
   no policies. The page acts through `admin_prospect_action`, which checks the actor is an
   admin and logs an event.
   - A message that was not sent expires the next day and its slot is refilled.

## Page `/admin/prospeccion`

- The follow-ups due today come first, then today's batch.
- Each card has the editable text, the other variant, the facts and the listing link.
- «Abrir en WhatsApp» opens `wa.me` with the text ready to send.
- For a seller reached through the ML button the card says «Abrí su aviso y tocá WhatsApp»:
  «Copiar mensaje», then «Abrir su aviso en ML» (the ML app on the phone), tap WhatsApp, paste.
  Below it, «Guardar número» stores the number WhatsApp showed (`phone_set`), so the follow-ups
  go by `wa.me`.
- Each card also has the states: Enviado, No le interesa, Número equivocado, Descartar.
- «Respondieron» lists who replied, with the ready-made replies.
- The weekly summary shows the reply rate by hook, source, agency or person, and region.

## Running

```
cd worker
python -m prospector --dry-run --new 5     # writes nothing to the database; leaves a report
python -m prospector --dry-run --new 5 --solo-boton-ml   # only ML sellers without a number
python -m prospector                       # the daily run
```

- The DATABASE_URL comes from the root `.env` (`--env-file`).
- Reports go to `%LOCALAPPDATA%\EseAuto\prospeccion\corridas\`. They are local and hold
  business names and phones, so they are never committed.
- `ops\install-prospector.ps1` registers the task and `ops\uninstall-prospector.ps1` removes
  it.
- `claude` has to be logged in on the PC (`claude auth status`). The task uses Juan's
  subscription.

## Tests

- `python -m pytest worker/tests/test_prospector.py`
- `npx vitest run lib/admin-prospecting.test.ts` (in `web/`)
- `supabase/tests/prospecting_test.sql` (pgTAP, on a local database)
