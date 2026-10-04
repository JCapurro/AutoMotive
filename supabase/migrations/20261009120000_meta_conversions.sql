-- Meta Conversions API (server-side Purchase). Written only by the server.
-- What the browser had when the checkout started: Meta's cookie ids, IP, user agent
-- and the ads consent answer. Purchase is sent only when consent was granted.
alter table public.billing_checkouts add column ad_attribution jsonb;
-- Claimed before sending, so reconciliation re-reading a payment never sends it twice.
alter table public.commercial_payments add column meta_sent_at timestamptz;
